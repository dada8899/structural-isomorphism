"""Tier-aware rate limit via ContextVar — P0 coverage.

Covers the fix in `services/rate_limit.py:tier_limit_decorator` which
previously returned a static `default_anon` spec regardless of the
caller's tier. The resolved spec now reads `middleware.rate_limit.
CURRENT_TIER` (set by `TierResolutionMiddleware` on every /api/* request)
and maps tier → req/min via `TIER_LIMITS`.

Also asserts that every known LLM-expensive endpoint (search / mapping /
synthesize / ask / analyze / admin logs) is decorated with
`tier_limit_decorator` so we don't regress on missing-limit coverage.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# --- ContextVar-driven resolve_spec ---


def _extract_resolve_callable(decorator):
    """Reach into the decorator's closure to grab the inner spec callable.

    `tier_limit_decorator(default_anon)` returns `limiter.limit(_resolve_spec)`
    which is itself a function whose closure carries `_resolve_spec` as
    `limit_value`. This helper plucks it out so we can call it directly
    under different ContextVar states.
    """
    # Walk slowapi's wrapper closure for the `limit_value` cell.
    for cell in decorator.__closure__ or []:
        val = cell.cell_contents
        if callable(val) and getattr(val, "__name__", "") == "_resolve_spec":
            return val
    raise AssertionError("Could not locate _resolve_spec inside decorator closure")


@pytest.fixture
def resolver():
    from services.rate_limit import tier_limit_decorator
    dec = tier_limit_decorator(default_anon="5/minute")
    return _extract_resolve_callable(dec)


def test_resolver_free_tier_uses_table(resolver):
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("free")
    try:
        # free → 60/minute from TIER_LIMITS table
        assert resolver() == "60/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_pro_tier_promotes(resolver):
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("pro")
    try:
        assert resolver() == "1000/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_team_tier_promotes(resolver):
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("team")
    try:
        assert resolver() == "5000/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_admin_is_effectively_unlimited(resolver):
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("admin")
    try:
        spec = resolver()
        # 1M/min — slowapi can't be fully bypassed from a callable but the
        # cap is inert for any realistic admin traffic.
        assert spec == "1000000/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_anonymous_falls_back_to_default_anon(resolver):
    """Anonymous (= no token) gets the per-endpoint anon floor, not 60/min."""
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("anonymous")
    try:
        # default_anon='5/minute' was passed into the resolver's parent.
        assert resolver() == "5/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_legacy_paid_normalised_to_pro(resolver):
    """services/auth.verify_api_token still emits "paid" for legacy
    Bearer-token callers; the resolver must treat that as pro."""
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("paid")
    try:
        assert resolver() == "1000/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_resolver_unknown_tier_safely_buckets_as_free(resolver):
    from middleware.rate_limit import CURRENT_TIER
    tok = CURRENT_TIER.set("vip-platinum")
    try:
        # Unknown tier — safest default is the free bucket so we never
        # accidentally upgrade a request to a looser limit.
        assert resolver() == "60/minute"
    finally:
        CURRENT_TIER.reset(tok)


def test_default_anon_param_is_respected_per_endpoint():
    """Two endpoints can configure different anonymous floors."""
    from services.rate_limit import tier_limit_decorator
    from middleware.rate_limit import CURRENT_TIER

    strict = _extract_resolve_callable(tier_limit_decorator("2/minute"))
    relaxed = _extract_resolve_callable(tier_limit_decorator("30/minute"))

    tok = CURRENT_TIER.set("anonymous")
    try:
        assert strict() == "2/minute"
        assert relaxed() == "30/minute"
    finally:
        CURRENT_TIER.reset(tok)


# --- Endpoint coverage: every LLM-expensive route must have a limit ---


@pytest.mark.parametrize(
    "module_name,route_path,method",
    [
        ("api.ask", "/ask/stream", "POST"),
        ("api.analyze", "/analyze/stream", "GET"),
        ("api.search", "/search", "POST"),
        ("api.search", "/search/assess", "POST"),
        ("api.mapping", "/mapping", "POST"),
        ("api.mapping", "/mapping/stream", "GET"),
        ("api.synthesize", "/synthesize", "POST"),
        ("api.synthesize", "/synthesize/stream", "POST"),
        ("api.admin.logs", "/admin/logs/tail", "GET"),
    ],
)
def test_endpoint_has_rate_limit_decorator(module_name, route_path, method):
    """Every LLM-expensive endpoint must be wrapped by tier_limit_decorator.

    slowapi stamps the limit metadata onto the underlying endpoint function
    (FastAPI stores it under `route.endpoint`). We just confirm the route
    exists and is wired through a slowapi-decorated handler.
    """
    import importlib

    mod = importlib.import_module(module_name)
    router = mod.router

    matches = [
        r for r in router.routes
        if getattr(r, "path", None) == route_path and method in getattr(r, "methods", set())
    ]
    assert matches, (
        f"Route {method} {route_path} not found on {module_name}. "
        "Did the path or method change?"
    )

    route = matches[0]
    endpoint = route.endpoint

    # slowapi attaches limit metadata as `_limiter` on the wrapped fn or
    # leaves it discoverable via the limiter's internal storage. The simplest
    # contract test: the endpoint function must NOT be the bare async def
    # — it must have gone through a decorator wrap. We detect this by
    # checking for the slowapi `_rate_limits` attribute that gets set, OR
    # by inspecting the wrapped function chain.
    has_limit = (
        hasattr(endpoint, "_rate_limit")
        or hasattr(endpoint, "__wrapped__")
        or "limit" in (getattr(endpoint, "__qualname__", "") or "").lower()
        or _endpoint_uses_slowapi(endpoint)
    )
    assert has_limit, (
        f"Endpoint {module_name}:{endpoint.__qualname__} ({method} {route_path}) "
        f"appears to have no slowapi rate-limit decorator. "
        "Add @tier_limit_decorator(default_anon='...') above the route."
    )


def _endpoint_uses_slowapi(fn) -> bool:
    """Heuristic: walk the closure chain looking for slowapi sentinels."""
    seen = set()
    stack = [fn]
    while stack:
        f = stack.pop()
        if id(f) in seen:
            continue
        seen.add(id(f))
        # slowapi typically wraps with an attribute named like 'limit' or
        # the closure carries the limiter reference itself.
        if getattr(f, "__module__", "").startswith("slowapi"):
            return True
        closure = getattr(f, "__closure__", None) or []
        for cell in closure:
            try:
                v = cell.cell_contents
            except ValueError:
                continue
            if callable(v):
                stack.append(v)
                if getattr(v, "__module__", "").startswith("slowapi"):
                    return True
            # Catch the Limiter instance directly.
            if v.__class__.__name__ == "Limiter":
                return True
    return False
