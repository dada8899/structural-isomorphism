"""
Shared rate limiter instance.

Kept in its own module so routers can import it without creating a circular
dependency with main.py. main.py imports this module at startup and registers
`limiter` on the FastAPI app; routers import `limiter` here to decorate their
endpoints.
"""
import functools
import logging
import types

logger = logging.getLogger("structural.rate_limit")


class _ChainedGlobals(dict):
    """A `__globals__` dict that chains lookups: handler module first,
    then a fallback namespace (slowapi's own module).

    A function's `__globals__` MUST be a real `dict`; this `dict`
    subclass satisfies that. It is kept EMPTY itself; every lookup is a
    live read of `_primary` (handler module) with `_fallback` (slowapi
    module) as backstop — so symbols defined in either module after the
    decorator runs are still resolved.
    """

    __slots__ = ("_primary", "_fallback")

    def __init__(self, primary: dict, fallback: dict):
        super().__init__()
        self._primary = primary
        self._fallback = fallback

    def __missing__(self, key):
        try:
            return self._primary[key]
        except KeyError:
            return self._fallback[key]

    def __contains__(self, key):
        return (
            super().__contains__(key)
            or key in self._primary
            or key in self._fallback
        )


def _rebind_to_handler_globals(wrapper, handler):
    """Give the slowapi wrapper a `__globals__` that resolves BOTH the
    handler's module symbols and slowapi's own runtime symbols.

    ROOT-CAUSE FIX for the prod 502.

    `slowapi`'s `limiter.limit()` builds its wrapper with
    `functools.wraps(func)`. `functools.wraps` copies `__name__`,
    `__doc__`, `__wrapped__`, `__annotations__`, ... but it CANNOT copy
    `__globals__` — a function's `__globals__` is bound to its code
    object and lives in the module where the code was compiled (here:
    `slowapi.extension`).

    FastAPI resolves a route's parameter annotations via
    `get_typed_signature(call)`. On the prod-pinned FastAPI 0.110.0 that
    is `globalns = getattr(call, "__globals__", {})` with NO
    `inspect.unwrap`. So when a handler module uses
    `from __future__ import annotations` (PEP 563), its annotations are
    stringified ("DiagnoseRequest") and get evaluated against slowapi's
    namespace — which has no such symbol — raising NameError at app
    construction → startup crash → nginx 502.

    Naively swapping `__globals__` to the handler's module is WRONG: the
    slowapi `async_wrapper` body itself references slowapi's module-level
    names (`Request`, `Response`, `Any`, ...) at *runtime*, so it would
    then `NameError` on every request.

    The fix re-creates the wrapper as a fresh `FunctionType` with the
    SAME code object + closure (slowapi's rate-limiting behaviour is
    byte-for-byte unchanged) but a `_ChainedGlobals` namespace:
      * handler module symbols take precedence  → FastAPI annotation
        resolution finds the local Pydantic models;
      * slowapi's module globals are the fallback → slowapi's own
        runtime body still finds `Request` / `Response` / `Any`.
    This fixes the decorator mechanism itself — every PEP-563 handler is
    safe, on every FastAPI version, without per-file patching.
    """
    handler_globals = getattr(handler, "__globals__", None)
    wrapper_code = getattr(wrapper, "__code__", None)
    wrapper_globals = getattr(wrapper, "__globals__", None)
    if handler_globals is None or wrapper_code is None or wrapper_globals is None:
        ***REMOVED*** Not a plain Python function (C wrapper / unusual slowapi build) —
        ***REMOVED*** nothing safe to rebind; leave it untouched.
        return wrapper

    chained = _ChainedGlobals(primary=handler_globals, fallback=wrapper_globals)
    rebound = types.FunctionType(
        wrapper_code,
        chained,
        name=wrapper.__name__,
        argdefs=wrapper.__defaults__,
        closure=wrapper.__closure__,
    )
    rebound.__kwdefaults__ = wrapper.__kwdefaults__
    ***REMOVED*** Carry over everything functools.wraps put on the slowapi wrapper
    ***REMOVED*** (__wrapped__, __annotations__, __dict__, __qualname__, __doc__, ...).
    functools.update_wrapper(rebound, wrapper)
    ***REMOVED*** update_wrapper sets __wrapped__ = wrapper; we want it to point at the
    ***REMOVED*** ORIGINAL handler so `inspect.unwrap` reaches the real function.
    rebound.__wrapped__ = handler
    return rebound

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
    """Decorator wrapper: applies a slowapi limit if available, else no-op.

    The slowapi wrapper is rebound to the handler's `__globals__` — see
    `_rebind_to_handler_globals` — so PEP-563 stringified annotations
    resolve correctly on every FastAPI version.
    """
    if _ENABLED and limiter is not None:
        _slow = limiter.limit(spec)

        def _decorate(handler):
            return _rebind_to_handler_globals(_slow(handler), handler)

        return _decorate

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

    _slow = limiter.limit(_resolve_spec)

    def _decorate(handler):
        ***REMOVED*** Rebind the slowapi wrapper to the handler's own __globals__ so
        ***REMOVED*** PEP-563 stringified annotations resolve on every FastAPI version
        ***REMOVED*** (prod 502 root-cause fix — see `_rebind_to_handler_globals`).
        return _rebind_to_handler_globals(_slow(handler), handler)

    return _decorate
