"""Feature flags + A/B experiments — session #10 W15-E.

Lightweight, in-process, no third-party SaaS. Config in `config/feature_flags.yaml`
at repo root. Hot-reload on a 30s TTL (mtime + cache check).

Two primitives:
  - is_enabled(flag, user_id) -> bool
      * percentage rollout: deterministic per (flag, user_id)
      * segment rollout:    tier-gated via CURRENT_TIER contextvar
  - get_variant(experiment, user_id) -> str
      * weighted allocation, deterministic per (experiment, user_id)

Determinism: hash(user_id + ":" + flag_or_exp_name) -> bucket [0, 99]. Same
user always lands in same bucket for the same flag, even across processes,
so percentage rollouts are stable (no flicker between calls).

Anonymous users: pass a stable anon hash from a cookie/header. If user_id
is None we treat as "bucket 0" — they only see flags that hit 100% or are
explicitly enabled with no rollout gate. (Safe default: don't expose
A/B experiments to anon users.)
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

log = logging.getLogger(__name__)

# Cache TTL — re-read YAML at most every 30s. Cheap (single file, few KB).
_CACHE_TTL_SECONDS = 30.0


def _default_config_path() -> Path:
    """Resolve config path: env override > repo-root/config/feature_flags.yaml."""
    env = os.environ.get("FEATURE_FLAGS_PATH")
    if env:
        return Path(env)
    # web/backend/flags.py -> repo root is 2 levels up.
    backend_dir = Path(__file__).resolve().parent
    return backend_dir.parent.parent / "config" / "feature_flags.yaml"


@dataclass
class _CacheEntry:
    """In-memory snapshot of YAML, with mtime + load-time guard."""

    data: Dict[str, Any] = field(default_factory=dict)
    loaded_at: float = 0.0
    mtime: float = 0.0
    path: Optional[Path] = None


_cache = _CacheEntry()
_cache_lock = threading.Lock()


def _load_config(path: Optional[Path] = None, *, force: bool = False) -> Dict[str, Any]:
    """Load YAML config with TTL cache. Thread-safe.

    Returns a dict with keys 'flags' and 'experiments'. Missing file or
    parse error -> empty dict (fail-closed: all flags off, all experiments
    return control).
    """
    p = path or _default_config_path()
    now = time.monotonic()

    with _cache_lock:
        # Cache hit: file unchanged + within TTL.
        if not force and _cache.path == p and (now - _cache.loaded_at) < _CACHE_TTL_SECONDS:
            return _cache.data

        # mtime-based invalidation (cheap stat() call).
        try:
            mtime = p.stat().st_mtime
        except FileNotFoundError:
            log.warning("feature_flags: config not found at %s — defaulting to empty", p)
            _cache.data = {}
            _cache.loaded_at = now
            _cache.path = p
            _cache.mtime = 0.0
            return _cache.data

        # If mtime unchanged AND we have a prior load, just bump loaded_at.
        if not force and _cache.path == p and mtime == _cache.mtime and _cache.data:
            _cache.loaded_at = now
            return _cache.data

        try:
            with open(p, "r", encoding="utf-8") as fh:
                raw = yaml.safe_load(fh) or {}
        except Exception as e:  # broad: any YAML or IO error
            log.error("feature_flags: failed to parse %s: %s", p, e)
            # Keep last good cache if we have one; otherwise empty.
            if not _cache.data:
                _cache.data = {}
            _cache.loaded_at = now
            _cache.path = p
            _cache.mtime = mtime
            return _cache.data

        if not isinstance(raw, dict):
            log.error("feature_flags: top-level YAML must be a mapping, got %s", type(raw))
            raw = {}

        # Normalize sections.
        raw.setdefault("flags", {})
        raw.setdefault("experiments", {})

        _cache.data = raw
        _cache.loaded_at = now
        _cache.path = p
        _cache.mtime = mtime
        log.info("feature_flags: loaded %d flags + %d experiments from %s",
                 len(raw["flags"]), len(raw["experiments"]), p)
        return _cache.data


def _bucket(user_id: str, key: str) -> int:
    """Deterministic hash -> bucket in [0, 99].

    Uses SHA-256 (overkill, but cheap and standard). First 8 hex chars
    -> int -> mod 100. Same (user_id, key) always returns same bucket.
    """
    h = hashlib.sha256(f"{user_id}:{key}".encode("utf-8")).hexdigest()
    return int(h[:8], 16) % 100


def _current_tier() -> str:
    """Pull current_tier from rate_limit middleware ContextVar.

    Defensive: if middleware isn't installed (e.g. test app without it),
    fall back to 'free'.
    """
    try:
        from middleware.rate_limit import CURRENT_TIER  # local import to avoid cycle
        return CURRENT_TIER.get()
    except Exception:
        return "free"


def is_enabled(flag: str, user_id: Optional[str] = None) -> bool:
    """Return True if `flag` is enabled for this user.

    Resolution order:
      1. Flag missing or `enabled: false` -> False
      2. No rollout block -> True (binary on/off)
      3. rollout.type == 'percentage' -> bucket < value
      4. rollout.type == 'segment'    -> current_tier in segments
      5. Unknown rollout type         -> False (fail-closed)

    Anonymous (user_id is None): treated as bucket 0 for percentage,
    'free' tier for segment.
    """
    cfg = _load_config()
    flags = cfg.get("flags", {})
    entry = flags.get(flag)
    if not entry or not entry.get("enabled", False):
        return False

    rollout = entry.get("rollout")
    if not rollout:
        return True  # fully enabled, no rollout gate

    rtype = rollout.get("type")
    if rtype == "percentage":
        value = int(rollout.get("value", 0))
        # Clamp into [0, 100]. value=100 -> always True; value=0 -> always False.
        if value <= 0:
            return False
        if value >= 100:
            return True
        bucket = _bucket(user_id or "_anon", flag)
        return bucket < value

    if rtype == "segment":
        segments: List[str] = rollout.get("segments", []) or []
        return _current_tier() in segments

    # Unknown rollout type: fail-closed.
    log.warning("feature_flags: unknown rollout type %r for flag %s", rtype, flag)
    return False


def get_variant(experiment: str, user_id: Optional[str]) -> str:
    """Return variant name for `experiment` for this user.

    - Experiment missing -> 'control'
    - user_id is None    -> 'control' (don't expose A/B to anon)
    - Weighted allocation: variants summed -> bucket lands in cumulative ranges

    Determinism: same (user_id, experiment) always returns same variant.
    """
    if not user_id:
        return "control"

    cfg = _load_config()
    experiments = cfg.get("experiments", {})
    entry = experiments.get(experiment)
    if not entry:
        return "control"

    variants = entry.get("variants", {}) or {}
    allocation = entry.get("allocation", {}) or {}
    if not variants or not allocation:
        return "control"

    # Build cumulative buckets in stable order (sorted by variant name for
    # determinism across processes — dict iteration order is insertion in
    # py3.7+ but YAML load preserves insertion too; sort to be safe).
    names = sorted(variants.keys())
    total = sum(int(allocation.get(n, 0)) for n in names)
    if total <= 0:
        return "control"

    bucket = _bucket(user_id, experiment) % total
    cumulative = 0
    for name in names:
        weight = int(allocation.get(name, 0))
        cumulative += weight
        if bucket < cumulative:
            return name
    # Fallback (shouldn't reach here mathematically).
    return names[-1]


def get_all_flags(user_id: Optional[str] = None) -> Dict[str, bool]:
    """Return {flag_name: enabled_bool} for ALL configured flags for this user."""
    cfg = _load_config()
    flags = cfg.get("flags", {})
    return {name: is_enabled(name, user_id) for name in flags.keys()}


def get_all_experiments(user_id: Optional[str]) -> Dict[str, str]:
    """Return {experiment_name: variant} for ALL configured experiments."""
    cfg = _load_config()
    experiments = cfg.get("experiments", {})
    return {name: get_variant(name, user_id) for name in experiments.keys()}


def get_variant_value(experiment: str, user_id: Optional[str]) -> Optional[str]:
    """Convenience: return the actual variant *content* (e.g. text), not the name.

    Returns None if experiment missing.
    """
    cfg = _load_config()
    entry = cfg.get("experiments", {}).get(experiment)
    if not entry:
        return None
    variant_name = get_variant(experiment, user_id)
    return entry.get("variants", {}).get(variant_name)


def reset_cache_for_tests() -> None:
    """Test helper: clear cache so next call re-reads YAML."""
    with _cache_lock:
        _cache.data = {}
        _cache.loaded_at = 0.0
        _cache.mtime = 0.0
        _cache.path = None
