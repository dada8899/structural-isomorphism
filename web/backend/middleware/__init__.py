"""Middleware subpackage.

Re-exports the rate-limit installer so main.py can do:
    from middleware import install_rate_limit
"""
from middleware.rate_limit import (  # noqa: F401
    CURRENT_PATH,
    CURRENT_TIER,
    TIER_LIMITS,
    TierResolutionMiddleware,
    install_rate_limit,
    limiter,
    tier_aware_limit,
)

__all__ = [
    "install_rate_limit",
    "TierResolutionMiddleware",
    "tier_aware_limit",
    "limiter",
    "TIER_LIMITS",
    "CURRENT_TIER",
    "CURRENT_PATH",
]
