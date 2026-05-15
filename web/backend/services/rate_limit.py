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
except Exception as e:  # pragma: no cover
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
        # Local import keeps this module importable even if middleware
        # subpackage isn't wired (e.g. lean test harnesses that don't
        # install_rate_limit). The ContextVar default of "free" gives a
        # sensible fallback in those cases.
        try:
            from middleware.rate_limit import CURRENT_TIER, TIER_LIMITS
            tier = CURRENT_TIER.get()
        except Exception:
            tier = "anonymous"
            TIER_LIMITS = None  # type: ignore[assignment]

        # Tier → req/minute. Mirrors middleware.rate_limit.TIER_LIMITS but
        # tolerates absence to keep this module self-sufficient.
        defaults = {"free": 60, "pro": 1000, "team": 5000, "admin": None}
        if TIER_LIMITS:
            defaults = dict(TIER_LIMITS)  # type: ignore[arg-type]

        # Normalise legacy tier names (verify_api_token still returns
        # "anonymous" / "paid" in some code paths).
        tier_norm = (tier or "free").lower()
        if tier_norm == "anonymous":
            # Anonymous gets the per-endpoint default_anon floor — this
            # is the whole point of the parameter.
            return default_anon
        if tier_norm == "paid":
            tier_norm = "pro"

        base = defaults.get(tier_norm, defaults.get("free", 60))
        if base is None:
            # admin — effectively unlimited (slowapi can't be fully bypassed
            # from a callable, but a 1M/min cap is inert in practice).
            return "1000000/minute"
        return f"{base}/minute"

    return limiter.limit(_resolve_spec)
