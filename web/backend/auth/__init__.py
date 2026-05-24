"""API auth subpackage.

Re-exports the new X-API-Key scaffold so callers can do:
    from auth import APIKey, verify_api_key
"""
from auth.api_key import (  # noqa: F401
    APIKey,
    CURRENT_API_KEY,
    CURRENT_TIER,
    VALID_TIERS,
    force_reload_keys,
    list_seed_keys,
    resolve_tier_from_request,
    verify_api_key,
)

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
