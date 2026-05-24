"""
API-key authentication scaffold (W11-C, session #10).

Lightweight scaffold for `X-API-Key` header auth on /api/admin/* and
optional tier promotion on /api/* (so paid customers can hit higher
rate-limit buckets without a user account).

This is NOT a full user-management system — keys are seeded via a JSONL
file at `web/backend/data/api_keys.jsonl`. No UI to create/rotate yet;
that comes in the W12 admin console.

Storage format (one JSON per line):
    {
      "key":           "sk_test_pro_abc123",
      "tier":          "pro",
      "owner_email":   "alice@example.com",
      "created_at":    "2026-05-15T00:00:00Z",
      "last_used_at":  null,
      "revoked":       false
    }

The store is loaded lazily on first lookup and refreshed every 30s so
operational key revocations propagate without a process restart.

Public API:
    - verify_api_key(header) -> APIKey | None
    - APIKey pydantic model
    - CURRENT_TIER context var (set by middleware on each request)
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, Request
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("structural.auth.api_key")

# Tier set — must stay in sync with middleware.rate_limit.TIER_LIMITS.
VALID_TIERS = ("free", "pro", "team", "admin")


class APIKey(BaseModel):
    """Pydantic schema for an API key record."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=10, max_length=200)
    tier: str = Field(..., pattern="^(free|pro|team|admin)$")
    owner_email: str = Field(..., max_length=200)
    created_at: str = Field(...)
    last_used_at: Optional[str] = None
    revoked: bool = False


# ---- contextvar set by middleware so rate-limiter can read tier ----

CURRENT_TIER: ContextVar[str] = ContextVar("CURRENT_TIER", default="free")
CURRENT_API_KEY: ContextVar[Optional[str]] = ContextVar("CURRENT_API_KEY", default=None)


# ---- key store ----


_DEFAULT_KEYS_PATH = Path(__file__).resolve().parent.parent / "data" / "api_keys.jsonl"
_REFRESH_INTERVAL_S = 30


class _KeyStore:
    """Thread-safe in-memory mirror of api_keys.jsonl with periodic refresh."""

    def __init__(self, path: Path):
        self.path = path
        self._keys: dict[str, APIKey] = {}
        self._last_loaded_at: float = 0.0
        self._lock = threading.RLock()

    def _maybe_reload(self) -> None:
        with self._lock:
            now = time.time()
            if now - self._last_loaded_at < _REFRESH_INTERVAL_S and self._keys:
                return
            self._reload_unlocked()

    def _reload_unlocked(self) -> None:
        keys: dict[str, APIKey] = {}
        if not self.path.exists():
            self._keys = {}
            self._last_loaded_at = time.time()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                for line_no, raw in enumerate(f, 1):
                    raw = raw.strip()
                    if not raw or raw.startswith("#"):
                        continue
                    try:
                        data = json.loads(raw)
                        ak = APIKey(**data)
                        keys[ak.key] = ak
                    except Exception as e:
                        logger.warning(
                            "api_keys.jsonl line %d malformed: %s", line_no, e
                        )
            self._keys = keys
            self._last_loaded_at = time.time()
        except Exception as e:
            logger.error("failed to load %s: %s", self.path, e)

    def lookup(self, key: str) -> Optional[APIKey]:
        if not key:
            return None
        self._maybe_reload()
        with self._lock:
            return self._keys.get(key)

    def force_reload(self) -> None:
        with self._lock:
            self._reload_unlocked()


_store: Optional[_KeyStore] = None


def _get_store() -> _KeyStore:
    global _store
    if _store is None:
        path_override = os.getenv("STRUCTURAL_API_KEYS_PATH")
        path = Path(path_override) if path_override else _DEFAULT_KEYS_PATH
        _store = _KeyStore(path)
    return _store


# ---- public API ----


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Optional[APIKey]:
    """FastAPI dependency: validate an X-API-Key header.

    Returns:
        APIKey instance on valid+active key.
        None if no header was supplied (anonymous → free tier).

    Raises:
        Unauthenticated if a header is supplied but the key is invalid or
        revoked. This is intentionally NOT silent — sending a bad key
        shouldn't fall back to free tier.
    """
    # Local import to avoid circular: errors.py is imported by main.py at
    # startup, and auth.api_key may be imported by main.py before errors.py.
    from errors import Unauthenticated

    if not x_api_key:
        return None
    ak = _get_store().lookup(x_api_key)
    if ak is None:
        raise Unauthenticated(detail="Unknown API key")
    if ak.revoked:
        raise Unauthenticated(detail="API key revoked")
    return ak


def resolve_tier_from_request(request: Request) -> str:
    """Inspect the request for an X-API-Key and return the resulting tier.

    Used by the rate-limit middleware *before* the endpoint runs so the
    bucket selection is correct. Invalid keys raise Unauthenticated (the
    middleware translates it to RFC 7807 401).
    """
    from errors import Unauthenticated

    hdr = request.headers.get("X-API-Key") or request.headers.get("x-api-key")
    if not hdr:
        return "free"
    ak = _get_store().lookup(hdr)
    if ak is None:
        raise Unauthenticated(detail="Unknown API key")
    if ak.revoked:
        raise Unauthenticated(detail="API key revoked")
    return ak.tier


def list_seed_keys() -> list[APIKey]:
    """Return all currently loaded keys (test/debug helper)."""
    _get_store()._maybe_reload()
    return list(_get_store()._keys.values())


def force_reload_keys() -> None:
    """Force-reload the key store from disk. Useful in tests."""
    _get_store().force_reload()


__all__ = [
    "APIKey",
    "verify_api_key",
    "resolve_tier_from_request",
    "list_seed_keys",
    "force_reload_keys",
    "CURRENT_TIER",
    "CURRENT_API_KEY",
    "VALID_TIERS",
]
