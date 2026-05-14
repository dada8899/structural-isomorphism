"""
API auth + tier classification.

Anonymous-first design: no token = "anonymous" tier (still allowed, just
rate-limited harder). Bearer token or cookie can promote a request to
"free" or "paid" tier with looser limits.

Token configuration via env:

    STRUCTURAL_API_TOKENS="paid:tok_abc,paid:tok_def,free:tok_xyz"

Each entry is `<tier>:<token>`. Legacy entries without a tier prefix are
treated as "free". Tokens never appear in git — they are env-only.

Public API:

    verify_api_token(request) -> "paid" | "free" | "anonymous" | None
        None is returned ONLY when the caller explicitly provided a token
        that does not match the configured allowlist (HTTP 401 territory).
        Missing token returns "anonymous" so callers can rate-limit by IP.

    get_rate_limit_tier(tier) -> "60/minute" | "10/minute" | "5/minute"

    tier_limit(request) -> slowapi key/limit string
        Suitable for slowapi's dynamic-limit `key_func` style; returns a
        composite "<tier>:<ip>" key so limits are tracked per tier+IP.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("structural.auth")

# Tier ordering: higher tier wins if a token is registered in multiple buckets.
_TIER_RANK = {"paid": 2, "free": 1, "anonymous": 0}

_COOKIE_NAME = "structural_api_token"
_BEARER_PREFIX = "Bearer "

# Per-tier rate-limit policy. Tweak via env if needed without code change.
_DEFAULT_LIMITS = {
    "paid": "60/minute",
    "free": "10/minute",
    "anonymous": "5/minute",
}


def _parse_token_env() -> dict[str, str]:
    """Read STRUCTURAL_API_TOKENS env into a {token: tier} map.

    Format: comma-separated `tier:token` pairs. Bare entries default to
    "free" (back-compat with single-tier deployments).
    """
    raw = os.getenv("STRUCTURAL_API_TOKENS", "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" in chunk:
            tier, _, token = chunk.partition(":")
            tier = tier.strip().lower()
            token = token.strip()
            if tier not in _TIER_RANK:
                logger.warning("auth: unknown tier %r in STRUCTURAL_API_TOKENS, treating as free", tier)
                tier = "free"
        else:
            tier = "free"
            token = chunk
        if not token:
            continue
        # If a token is reused across tiers, keep the higher tier.
        prev = out.get(token)
        if prev is None or _TIER_RANK[tier] > _TIER_RANK[prev]:
            out[token] = tier
    return out


def _extract_token(request) -> Optional[str]:
    """Pull a token from Authorization header or cookie. Returns None if absent."""
    # Header takes precedence.
    auth = request.headers.get("Authorization") or request.headers.get("authorization")
    if auth:
        if auth.startswith(_BEARER_PREFIX):
            tok = auth[len(_BEARER_PREFIX):].strip()
            if tok:
                return tok
    # Cookie fallback (handy for browser flows).
    try:
        cookie_val = request.cookies.get(_COOKIE_NAME)
    except Exception:  # pragma: no cover — non-FastAPI Request types
        cookie_val = None
    if cookie_val:
        return cookie_val.strip()
    return None


def verify_api_token(request) -> Optional[str]:
    """Classify the request into a tier.

    Returns:
        "paid" / "free"   — valid token recognised in env allowlist.
        "anonymous"       — no token provided; treat as best-effort caller.
        None              — token WAS provided but does not match → 401.
    """
    token = _extract_token(request)
    if not token:
        return "anonymous"
    allow = _parse_token_env()
    tier = allow.get(token)
    if tier is None:
        # Provided but invalid → caller should raise 401.
        return None
    return tier


def get_rate_limit_tier(tier: str) -> str:
    """Map a tier string to a slowapi-compatible limit spec.

    Unknown / invalid tiers fall back to the strictest bucket so we never
    accidentally upgrade a request to a looser limit.
    """
    if not isinstance(tier, str):
        return _DEFAULT_LIMITS["anonymous"]
    return _DEFAULT_LIMITS.get(tier.lower(), _DEFAULT_LIMITS["anonymous"])


def tier_limit(request) -> str:
    """Return a slowapi key string that bakes the tier into the bucket.

    Used with slowapi's `key_func` so different tiers don't share the same
    counter. We pair the tier with the remote IP so anonymous callers still
    get individualised limits.

    On invalid token (verify_api_token → None) we still return a bucket
    keyed to anonymous — the 401 is raised separately by the endpoint, so
    this just keeps slowapi happy if it's invoked anyway.
    """
    tier = verify_api_token(request)
    if tier is None:
        tier = "anonymous"
    # Best-effort IP extraction; slowapi.util.get_remote_address handles
    # X-Forwarded-For but we don't depend on slowapi here (it may be absent
    # in test environments).
    try:
        ip = request.client.host if request.client else "unknown"
    except Exception:  # pragma: no cover
        ip = "unknown"
    return f"{tier}:{ip}"


__all__ = [
    "verify_api_token",
    "get_rate_limit_tier",
    "tier_limit",
]
