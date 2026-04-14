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
