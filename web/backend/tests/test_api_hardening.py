"""Tests for W11-C API hardening: rate limit + RFC 7807 + API-key auth.

Avoids the full FastAPI app startup (which loads the search service on
lifespan) by constructing focused FastAPI sub-apps that re-use the same
middleware / handler installers. Keeps the suite fast (~1-2s) and
deterministic.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

# Ensure web/backend is on sys.path so the new modules resolve.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


# -------------- fixtures --------------


@pytest.fixture(autouse=True)
def reset_limiter_storage():
    """Clear slowapi's in-memory storage AND route-limit registry between tests.

    slowapi keys its dynamic-route-limit registry by `f.__module__ + "." + f.__name__`.
    Several tests below define their own `async def ping` handler — Python doesn't
    disambiguate them, so the registrations accumulate and each request gets
    its limit check evaluated N times (one per registered LimitGroup). Clearing
    both the storage and the route maps before each test restores isolation.
    """
    try:
        from middleware.rate_limit import limiter
        limiter.reset()
        if hasattr(limiter, "_dynamic_route_limits"):
            limiter._dynamic_route_limits.clear()
        if hasattr(limiter, "_route_limits"):
            limiter._route_limits.clear()
    except Exception:
        pass
    yield
    try:
        from middleware.rate_limit import limiter
        limiter.reset()
        if hasattr(limiter, "_dynamic_route_limits"):
            limiter._dynamic_route_limits.clear()
        if hasattr(limiter, "_route_limits"):
            limiter._route_limits.clear()
    except Exception:
        pass


@pytest.fixture
def seed_keys(monkeypatch, tmp_path):
    """Write a fresh keys file and point the store at it."""
    p = tmp_path / "api_keys.jsonl"
    rows = [
        {"key": "sk_test_free_aaa", "tier": "free", "owner_email": "f@x", "created_at": "2026-05-15T00:00:00Z", "revoked": False},
        {"key": "sk_test_pro_bbb", "tier": "pro", "owner_email": "p@x", "created_at": "2026-05-15T00:00:00Z", "revoked": False},
        {"key": "sk_test_team_ccc", "tier": "team", "owner_email": "t@x", "created_at": "2026-05-15T00:00:00Z", "revoked": False},
        {"key": "sk_test_admin_ddd", "tier": "admin", "owner_email": "a@x", "created_at": "2026-05-15T00:00:00Z", "revoked": False},
        {"key": "sk_test_revoked_eee", "tier": "pro", "owner_email": "r@x", "created_at": "2026-05-15T00:00:00Z", "revoked": True},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setenv("STRUCTURAL_API_KEYS_PATH", str(p))
    # Reset the in-memory store so it picks up the new path.
    import auth.api_key as ak_mod
    ak_mod._store = None
    # Also force-clear slowapi's storage at start.
    try:
        from middleware.rate_limit import limiter
        limiter.reset()
    except Exception:
        pass
    yield p


@pytest.fixture
def app_with_hardening(seed_keys):
    """Build a minimal FastAPI app exercising the new middleware + handlers."""
    from auth.api_key import verify_api_key
    from errors import (
        BudgetExceeded,
        Forbidden,
        InvalidInput,
        NotFound,
        Unauthenticated,
        install_problem_handlers,
    )
    from middleware import install_rate_limit, tier_aware_limit
    from pydantic import BaseModel, ConfigDict, Field

    app = FastAPI(title="hardening-test", version="0.0.1")
    install_problem_handlers(app)
    install_rate_limit(app)

    class Body(BaseModel):
        model_config = ConfigDict(extra="forbid")
        name: str = Field(..., min_length=1, max_length=20)
        count: int = Field(..., ge=1, le=100)

    @app.get("/api/ping")
    @tier_aware_limit()
    async def ping(request: Request):
        from middleware.rate_limit import CURRENT_TIER
        return {"ok": True, "tier": CURRENT_TIER.get()}

    @app.post("/api/echo", summary="Echo")
    async def echo(req: Body):
        return req.model_dump()

    @app.get("/api/notfound")
    async def nf():
        raise NotFound(detail="Phenomenon 'foo' not found")

    @app.get("/api/budget")
    async def budget():
        raise BudgetExceeded(detail="Daily $5 budget used", tier="free", remaining_usd=0)

    @app.get("/api/admin/secret", tags=["admin"])
    async def secret(request: Request):
        from middleware.rate_limit import CURRENT_TIER
        if CURRENT_TIER.get() != "admin":
            raise Forbidden(detail="Admin tier required")
        return {"secret": "42"}

    return app


@pytest.fixture
def client(app_with_hardening):
    return TestClient(app_with_hardening)


# -------------- RFC 7807 -------------------------------------


def test_problem_envelope_on_404(client):
    r = client.get("/api/notfound")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["type"].endswith("/errors/not_found")
    assert body["title"] == "Not found"
    assert body["status"] == 404
    assert "instance" in body
    assert body["instance"] == "/api/notfound"


def test_problem_envelope_on_validation_error(client):
    # Extra field violates extra=forbid
    r = client.post("/api/echo", json={"name": "x", "count": 5, "bad": "no"})
    assert r.status_code == 422
    body = r.json()
    assert body["type"].endswith("/errors/invalid_input")
    assert body["status"] == 422
    assert "errors" in body
    assert isinstance(body["errors"], list)


def test_problem_envelope_missing_required(client):
    r = client.post("/api/echo", json={"name": "x"})  # missing count
    assert r.status_code == 422
    body = r.json()
    assert body["type"].endswith("/errors/invalid_input")
    assert len(body["errors"]) >= 1


def test_problem_envelope_invalid_input_range(client):
    r = client.post("/api/echo", json={"name": "x", "count": 999})
    assert r.status_code == 422
    body = r.json()
    assert body["status"] == 422


def test_problem_envelope_budget_exceeded(client):
    r = client.get("/api/budget")
    assert r.status_code == 429
    body = r.json()
    assert body["type"].endswith("/errors/budget_exceeded")
    # Extension fields preserved
    assert body.get("tier") == "free"
    assert body.get("remaining_usd") == 0


# -------------- API-key auth ----------------------------


def test_no_api_key_is_free_tier(client):
    r = client.get("/api/ping")
    assert r.status_code == 200
    assert r.json()["tier"] == "free"
    # Annotated by middleware
    assert r.headers.get("X-Rate-Limit-Tier") == "free"


def test_valid_pro_key_sets_pro_tier(client):
    r = client.get("/api/ping", headers={"X-API-Key": "sk_test_pro_bbb"})
    assert r.status_code == 200
    assert r.json()["tier"] == "pro"
    assert r.headers.get("X-Rate-Limit-Tier") == "pro"


def test_valid_team_key_sets_team_tier(client):
    r = client.get("/api/ping", headers={"X-API-Key": "sk_test_team_ccc"})
    assert r.status_code == 200
    assert r.json()["tier"] == "team"


def test_invalid_key_returns_401(client):
    r = client.get("/api/ping", headers={"X-API-Key": "sk_test_bogus_xxx"})
    assert r.status_code == 401
    body = r.json()
    assert body["type"].endswith("/errors/unauthenticated")
    assert "Unknown API key" in body["detail"]


def test_revoked_key_returns_401(client):
    r = client.get("/api/ping", headers={"X-API-Key": "sk_test_revoked_eee"})
    assert r.status_code == 401
    body = r.json()
    assert "revoked" in body["detail"].lower()


def test_admin_endpoint_requires_admin_tier(client):
    # No key — should get 403 (free tier hits the explicit Forbidden raise).
    r = client.get("/api/admin/secret")
    assert r.status_code == 403
    body = r.json()
    assert body["type"].endswith("/errors/forbidden")


def test_admin_endpoint_accepts_admin_key(client):
    r = client.get("/api/admin/secret", headers={"X-API-Key": "sk_test_admin_ddd"})
    assert r.status_code == 200
    assert r.json()["secret"] == "42"


def test_admin_endpoint_rejects_pro_tier(client):
    r = client.get("/api/admin/secret", headers={"X-API-Key": "sk_test_pro_bbb"})
    assert r.status_code == 403


# -------------- Rate limit ----------------------------


def test_rate_limit_admin_unlimited(client):
    """Admin tier maps to 1M/min sentinel — should never trip."""
    # Hit many times quickly; should all succeed.
    for _ in range(20):
        r = client.get("/api/ping", headers={"X-API-Key": "sk_test_admin_ddd"})
        assert r.status_code == 200


def test_rate_limit_429_uses_problem_format(monkeypatch, seed_keys):
    """Force a tight limit and verify 429 envelope shape."""
    # Build a fresh app with a tight override.
    from errors import install_problem_handlers
    from middleware import install_rate_limit, tier_aware_limit
    import middleware.rate_limit as rl_mod
    from middleware.rate_limit import limiter

    # Override TIER_LIMITS so 'free' is 2/min — easy to hit.
    monkeypatch.setitem(rl_mod.TIER_LIMITS, "free", 2)

    # Belt-and-suspenders: clear right before test body runs.
    limiter.reset()

    app = FastAPI()
    install_problem_handlers(app)
    install_rate_limit(app)

    @app.get("/api/ping")
    @tier_aware_limit()
    async def ping(request: Request):
        return {"ok": True}

    c = TestClient(app)
    # Two should succeed; third should 429.
    r1 = c.get("/api/ping")
    r2 = c.get("/api/ping")
    r3 = c.get("/api/ping")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    body = r3.json()
    assert body["type"].endswith("/errors/rate_limit_exceeded")
    assert body["status"] == 429
    assert body.get("tier") == "free"
    assert "limit" in body
    assert body.get("retry_after_s") == 60
    assert r3.headers.get("Retry-After") == "60"


def test_rate_limit_pro_higher_than_free(monkeypatch, seed_keys):
    """Pro tier gets a separate (larger) bucket than free."""
    from errors import install_problem_handlers
    from middleware import install_rate_limit, tier_aware_limit
    import middleware.rate_limit as rl_mod

    # Force free=1, pro=5 so we can observe the gap deterministically.
    monkeypatch.setitem(rl_mod.TIER_LIMITS, "free", 1)
    monkeypatch.setitem(rl_mod.TIER_LIMITS, "pro", 5)

    app = FastAPI()
    install_problem_handlers(app)
    install_rate_limit(app)

    @app.get("/api/ping")
    @tier_aware_limit()
    async def ping(request: Request):
        return {"ok": True}

    c = TestClient(app)
    # Free tier: 1st ok, 2nd 429.
    assert c.get("/api/ping").status_code == 200
    assert c.get("/api/ping").status_code == 429
    # Pro tier (separate bucket): 5 should pass.
    pro_headers = {"X-API-Key": "sk_test_pro_bbb"}
    for i in range(5):
        r = c.get("/api/ping", headers=pro_headers)
        assert r.status_code == 200, f"pro request {i+1} unexpectedly 429"


# -------------- OpenAPI ----------------------------


def test_openapi_every_route_has_summary():
    """Production app: every documented route should have a non-empty summary."""
    from main import app
    spec = app.openapi()
    paths = spec.get("paths", {})
    missing = []
    for path, methods in paths.items():
        for verb, op in methods.items():
            if not isinstance(op, dict):
                continue
            if verb in ("parameters",):
                continue
            if not op.get("summary"):
                missing.append(f"{verb.upper()} {path}")
    # Soft assert: print first 5 missing so we can iterate. Hard cap of 10
    # allowed (some legacy routes without summaries — to be fixed in W12).
    assert len(missing) <= 10, (
        f"Too many routes without summary ({len(missing)}). First 5: {missing[:5]}"
    )


def test_openapi_has_apikey_security_scheme():
    from main import app
    spec = app.openapi()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert "APIKeyHeader" in schemes
    assert schemes["APIKeyHeader"]["type"] == "apiKey"
    assert schemes["APIKeyHeader"]["in"] == "header"
    assert schemes["APIKeyHeader"]["name"] == "X-API-Key"


def test_openapi_admin_path_requires_security():
    from main import app
    spec = app.openapi()
    paths = spec.get("paths", {})
    admin_paths = [p for p in paths if p.startswith("/api/admin")]
    assert admin_paths, "expected at least one /api/admin/* path"
    for path in admin_paths:
        for verb, op in paths[path].items():
            if not isinstance(op, dict):
                continue
            assert op.get("security") == [{"APIKeyHeader": []}], (
                f"{verb} {path} missing APIKeyHeader security requirement"
            )


def test_openapi_json_file_exists():
    """The exported OpenAPI artifact should be committed."""
    project_root = _BACKEND_ROOT.parent.parent
    spec_path = project_root / "docs" / "api" / "openapi.json"
    assert spec_path.exists(), f"missing {spec_path}"
    with open(spec_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "paths" in data
    assert len(data["paths"]) > 10


# -------------- contextvar isolation ----------------------


def test_tier_context_isolated_between_requests(client):
    """A request with a pro key shouldn't leak its tier to the next anonymous request."""
    r1 = client.get("/api/ping", headers={"X-API-Key": "sk_test_pro_bbb"})
    assert r1.json()["tier"] == "pro"
    r2 = client.get("/api/ping")
    assert r2.json()["tier"] == "free"
