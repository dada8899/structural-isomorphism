"""
Shared rate limiter instance.

Kept in its own module so routers can import it without creating a circular
dependency with main.py. main.py imports this module at startup and registers
`limiter` on the FastAPI app; routers import `limiter` here to decorate their
endpoints.
"""
import logging

logger = logging.getLogger("structural.rate_limit")

try:
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    limiter = Limiter(key_func=get_remote_address, default_limits=[])
    _ENABLED = True
except Exception as e:  ***REMOVED*** pragma: no cover
    logger.warning(f"slowapi not available, rate limiting disabled: {e}")
    limiter = None
    _ENABLED = False


def limit(spec: str):
    """Decorator wrapper: applies a slowapi limit if available, else no-op."""
    if _ENABLED and limiter is not None:
        return limiter.limit(spec)

    def _noop(f):
        return f

    return _noop


def tier_limit_decorator(default_anon: str = "10/minute"):
    """Per-request tier-aware rate-limit decorator.

    slowapi's `Limiter.limit` accepts either a static string OR a callable
    that takes no arguments and returns a string (per memory
    `feedback_slowapi_dynamic_limit_signature.md`: the callable does NOT
    receive `request`, so per-request tier must arrive via ContextVar).

    Usage:
        @router.post("/ask/stream")
        @tier_limit_decorator(default_anon="5/minute")
        async def ask_stream(request: Request, req: AskRequest): ...

    Behaviour:
        - When slowapi is available, returns a real decorator whose limit
          callable reads `middleware.rate_limit.CURRENT_TIER` (set by
          TierResolutionMiddleware before the route runs) and maps tier →
          spec via `TIER_LIMITS`. `default_anon` is the floor used when
          the resolved tier is free/anonymous (so individual endpoints can
          tighten anonymous traffic without touching the global table).
        - For `admin` tier we return a very high cap so slowapi is
          effectively a no-op without breaking its callable contract.
        - When slowapi is missing (test envs, lean installs), returns a
          no-op decorator — endpoints still work, just unrate-limited.
    """
    if not (_ENABLED and limiter is not None):
        def _noop(f):
            return f
        return _noop

    def _resolve_spec() -> str:
        ***REMOVED*** Local import keeps this module importable even if middleware
        ***REMOVED*** subpackage isn't wired (e.g. lean test harnesses that don't
        ***REMOVED*** install_rate_limit). The ContextVar default of "free" gives a
        ***REMOVED*** sensible fallback in those cases.
        try:
            from middleware.rate_limit import CURRENT_TIER, TIER_LIMITS
            tier = CURRENT_TIER.get()
        except Exception:
            tier = "anonymous"
            TIER_LIMITS = None  ***REMOVED*** type: ignore[assignment]

        ***REMOVED*** Tier → req/minute. Mirrors middleware.rate_limit.TIER_LIMITS but
        ***REMOVED*** tolerates absence to keep this module self-sufficient.
        defaults = {"free": 60, "pro": 1000, "team": 5000, "admin": None}
        if TIER_LIMITS:
            defaults = dict(TIER_LIMITS)  ***REMOVED*** type: ignore[arg-type]

        ***REMOVED*** Normalise legacy tier names (verify_api_token still returns
        ***REMOVED*** "anonymous" / "paid" in some code paths).
        tier_norm = (tier or "free").lower()
        ***REMOVED*** Launch P1-1 fix — anonymous traffic carries the per-endpoint
        ***REMOVED*** `default_anon` floor. `TierResolutionMiddleware` resolves an
        ***REMOVED*** un-keyed (anonymous) request to the "free" tier — there is no
        ***REMOVED*** separate "anonymous" tier in middleware.rate_limit.TIER_LIMITS.
        ***REMOVED*** So we MUST treat "free" the same as "anonymous" here, otherwise
        ***REMOVED*** `default_anon` (e.g. 5/min on /api/ask) is dead code and anon
        ***REMOVED*** traffic silently runs at the 60/min free-tier table value.
        ***REMOVED*** An explicit free-tier API key is also rate-limited at the
        ***REMOVED*** endpoint floor: the floor is always <= the table value, and a
        ***REMOVED*** free key holder shouldn't get looser limits than an anon user
        ***REMOVED*** on an LLM-expensive endpoint.
        if tier_norm in ("anonymous", "free"):
            return default_anon
        if tier_norm == "paid":
            tier_norm = "pro"

        base = defaults.get(tier_norm, defaults.get("free", 60))
        if base is None:
            ***REMOVED*** admin — effectively unlimited (slowapi can't be fully bypassed
            ***REMOVED*** from a callable, but a 1M/min cap is inert in practice).
            return "1000000/minute"
        return f"{base}/minute"

    return limiter.limit(_resolve_spec)
