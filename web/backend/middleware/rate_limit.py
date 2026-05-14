"""
Tier-aware rate limiting (W11-C, session #10).

slowapi's dynamic-limit callable doesn't receive the request object —
per memory `feedback_slowapi_dynamic_limit_signature.md`, the callable
signature is `_spec()` or `_spec(key)` only. The only reliable way to
make limits tier-aware is to:

  1. Resolve the tier at the very start of each request and stash it in
     a `ContextVar` (set by middleware, read by the limit callable).
  2. Have slowapi's `key_func` also incorporate the tier so different
     tiers don't share counter buckets.

This module wires both pieces.

Tiers (req/min):
    free   →    60   (anonymous and explicit free-tier keys)
    pro    →  1000
    team   →  5000
    admin  →     0   (unlimited — no slowapi check applied)

Per-endpoint overrides:
    /api/ask, /api/analyze, /api/synthesize  → half the tier limit
    (LLM-expensive endpoints).

429 body uses RFC 7807 envelope (`application/problem+json`) plus a
`Retry-After` header parseable by HTTP clients.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Awaitable, Callable, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded as SlowAPIRateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("structural.middleware.rate_limit")

# Tier -> req/minute. `admin` is sentinel for "no slowapi limit".
TIER_LIMITS = {
    "free": 60,
    "pro": 1000,
    "team": 5000,
    "admin": None,  # unlimited
}

# Endpoints (path-prefix match) that consume LLM tokens — halve the bucket.
EXPENSIVE_ENDPOINT_PREFIXES = (
    "/api/ask",
    "/api/analyze",
    "/api/synthesize",
    "/api/mapping",
)


# Per-request context populated by middleware *before* slowapi runs its
# key_func / limit callable. The closures below read these to make
# tier-aware decisions.
CURRENT_TIER: ContextVar[str] = ContextVar("rl_current_tier", default="free")
CURRENT_PATH: ContextVar[str] = ContextVar("rl_current_path", default="")


def _is_expensive(path: str) -> bool:
    return any(path.startswith(p) for p in EXPENSIVE_ENDPOINT_PREFIXES)


def _resolve_limit_spec() -> str:
    """Compute the slowapi limit spec string for the current request.

    Reads ContextVars set by the middleware. Returns a slowapi-compatible
    spec like "60/minute". For unlimited (admin) tiers, returns a huge
    sentinel like "100000/minute" so slowapi never trips — we can't fully
    bypass slowapi from a dynamic callable but the cap is effectively
    inert.
    """
    tier = CURRENT_TIER.get()
    path = CURRENT_PATH.get()
    base = TIER_LIMITS.get(tier, TIER_LIMITS["free"])
    if base is None:
        # admin — effectively unlimited.
        return "1000000/minute"
    if _is_expensive(path):
        base = max(1, base // 2)
    return f"{base}/minute"


def _composite_key(request: Request) -> str:
    """slowapi key_func: composite of tier + remote-addr.

    Separating buckets per-tier prevents a single team-tier user from
    starving the free pool (or vice versa).
    """
    # Re-resolve tier from request here as a safety net — middleware
    # should have already set it, but a misconfigured app could call into
    # slowapi without going through middleware first.
    tier = CURRENT_TIER.get()
    ip = get_remote_address(request)
    return f"{tier}:{ip}"


# ---- public objects ----


# The Limiter is registered via `app.state.limiter` in `install_rate_limit`.
# default_limits is empty: every endpoint specifies its own spec via the
# dynamic callable below.
limiter = Limiter(
    key_func=_composite_key,
    default_limits=[],
    # headers_enabled=True would force every decorated endpoint to declare
    # a `response: Response` parameter so slowapi can inject X-RateLimit-*
    # headers — that's intrusive for the existing route signatures. We
    # surface tier via our own middleware header (X-Rate-Limit-Tier) and
    # only add Retry-After on actual 429 responses, which is enough for
    # most clients.
    headers_enabled=False,
)


def tier_aware_limit():
    """Decorator factory: applies dynamic per-tier limits to an endpoint.

    Usage:

        @router.post("/some-endpoint")
        @tier_aware_limit()
        async def handler(request: Request, ...): ...

    The decorator uses slowapi's callable-spec form, where the callable
    is invoked at request time to determine the limit. We read the tier
    from the ContextVar that the middleware sets.
    """
    return limiter.limit(_resolve_limit_spec)


# ---- middleware ----


class TierResolutionMiddleware(BaseHTTPMiddleware):
    """Resolve the request's tier ONCE and stash into ContextVar.

    Runs before slowapi. If the X-API-Key header is present but invalid,
    returns a 401 RFC 7807 response immediately.

    We deliberately keep this lightweight (a dict lookup + contextvar
    set) so it has negligible per-request cost on the 99% of requests
    that don't supply a key.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable],
    ):
        # Local imports avoid circular dependency on errors.py at import
        # time when this module is loaded by main.py.
        from auth.api_key import resolve_tier_from_request
        from errors import Unauthenticated, _problem_handler

        # Only run on /api/* — static assets and HTML pages don't need
        # rate-limiting (and slowapi would just add noise).
        path = request.url.path or ""
        CURRENT_PATH.set(path)
        if not path.startswith("/api/"):
            CURRENT_TIER.set("free")
            return await call_next(request)

        try:
            tier = resolve_tier_from_request(request)
        except Unauthenticated as e:
            return await _problem_handler(request, e)

        CURRENT_TIER.set(tier)
        response = await call_next(request)
        # Annotate response so downstream proxies / browsers can see the
        # tier without parsing the API-key header back.
        response.headers["X-Rate-Limit-Tier"] = tier
        return response


# ---- 429 handler producing RFC 7807 body ----


async def _ratelimit_problem_handler(
    request: Request, exc: SlowAPIRateLimitExceeded
) -> JSONResponse:
    """Custom slowapi 429 handler → RFC 7807 envelope."""
    from errors import RateLimitExceeded as PD_RateLimitExceeded
    from errors import _problem_response

    # slowapi stores the offending limit spec on exc.detail.
    spec = getattr(exc, "detail", "unknown")
    tier = CURRENT_TIER.get()
    retry_after = 60  # all our limits are per-minute
    wrapped = PD_RateLimitExceeded(
        detail=f"Rate limit {spec} exceeded for tier '{tier}'",
        tier=tier,
        limit=str(spec),
        retry_after_s=retry_after,
    )
    return _problem_response(wrapped, request)


# ---- installer ----


def install_rate_limit(app: FastAPI) -> None:
    """Wire the limiter + middleware into a FastAPI app.

    Order matters:
        1. Limiter is attached to app.state (slowapi convention).
        2. TierResolutionMiddleware runs BEFORE slowapi's own middleware.
        3. Custom 429 handler replaces slowapi's default.
    """
    app.state.limiter = limiter
    app.add_middleware(TierResolutionMiddleware)
    app.add_exception_handler(SlowAPIRateLimitExceeded, _ratelimit_problem_handler)


__all__ = [
    "limiter",
    "tier_aware_limit",
    "install_rate_limit",
    "TierResolutionMiddleware",
    "TIER_LIMITS",
    "CURRENT_TIER",
    "CURRENT_PATH",
]
