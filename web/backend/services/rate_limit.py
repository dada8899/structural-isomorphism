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
    that takes the request and returns a string. We forward to the callable
    form so a single endpoint can serve paid/free/anonymous tiers with
    different limits.

    Usage:
        @router.post("/ask/stream")
        @tier_limit_decorator()
        async def ask_stream(request: Request, req: AskRequest): ...

    Behaviour:
        - When slowapi is available, returns a real decorator that asks
          services.auth for the tier on every call.
        - When slowapi is missing (test envs, lean installs), returns a
          no-op decorator — endpoints still work, just unrate-limited.
        - The `default_anon` argument lets callers override the fallback
          limit if they want stricter handling for anonymous traffic on
          specific endpoints.
    """
    if not (_ENABLED and limiter is not None):
        def _noop(f):
            return f
        return _noop

    # Local import to avoid a hard dep at module load — auth.py only needs
    # to be importable when this decorator actually fires.
    try:
        from services.auth import verify_api_token, get_rate_limit_tier
    except Exception as e:  # pragma: no cover
        logger.warning(f"tier_limit_decorator: auth import failed ({e}), falling back to static limit")
        return limiter.limit(default_anon)

    def _spec_for(request) -> str:
        tier = verify_api_token(request)
        # Invalid token → fall back to default_anon; the endpoint itself
        # is expected to raise 401, but if it doesn't we still rate-limit.
        if tier is None or tier == "anonymous":
            return default_anon if tier is None else get_rate_limit_tier("anonymous")
        return get_rate_limit_tier(tier)

    return limiter.limit(_spec_for)
