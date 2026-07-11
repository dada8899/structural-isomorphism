"""Launch P1-4 / P0-3 — full-app hardening tests.

Covers behaviour that only manifests on the real `main.app`:
  * HEAD / returns 200 (was 405 — broke HEAD-based health checks).
  * /docs /redoc /openapi.json are disabled when STRUCTURAL_ENV=prod.
  * Security headers ride on every response (integration with main.app).

We build a TestClient WITHOUT the `with` block so the lifespan (which
loads the heavy search service) never runs — these routes don't need it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _fresh_main(monkeypatch, env: str):
    """Reload `main` under a given STRUCTURAL_ENV and return the module."""
    monkeypatch.setenv("STRUCTURAL_ENV", env)
    # prod path requires the share-token secret env (report_store guards it).
    monkeypatch.setenv("STRUCTURAL_SHARE_TOKEN_SECRET", "test-secret-for-suite")
    monkeypatch.setenv("AUTH_ENABLED", "false")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  # noqa: WPS433 — deliberate reload
    return main


@pytest.fixture
def dev_client(monkeypatch):
    main = _fresh_main(monkeypatch, "dev")
    return TestClient(main.app)


@pytest.fixture
def prod_client(monkeypatch):
    main = _fresh_main(monkeypatch, "prod")
    return TestClient(main.app)


# --------- P1-4: HEAD / --------- #


def test_head_root_returns_200(dev_client):
    """HEAD / must be 200 — health checkers / CDNs probe with HEAD."""
    r = dev_client.head("/")
    assert r.status_code == 200


def test_get_root_still_works(dev_client):
    r = dev_client.get("/")
    assert r.status_code == 200


# --------- P1-4: docs gating by env --------- #


def test_docs_open_in_dev(dev_client):
    assert dev_client.get("/openapi.json").status_code == 200
    assert dev_client.get("/docs").status_code == 200


def test_docs_disabled_in_prod(prod_client):
    """In prod the API surface map must not be publicly browsable."""
    assert prod_client.get("/openapi.json").status_code == 404
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404


def test_unfinished_surfaces_fail_closed_in_prod(prod_client):
    auth = prod_client.post("/api/auth/request-link", json={"email": "a@example.com"})
    assert auth.status_code == 503
    assert auth.json()["error"] == "account_features_not_available"

    legacy_api = prod_client.post("/phase/api/redteam", json={})
    assert legacy_api.status_code == 410
    assert legacy_api.json()["error"] == "legacy_phase_api_retired"

    legacy_page = prod_client.get("/phase", follow_redirects=False)
    assert legacy_page.status_code == 308
    assert legacy_page.headers["location"] == "https://phase.bytedance.city"

    connections = prod_client.get("/connections", follow_redirects=False)
    assert connections.status_code == 308
    assert connections.headers["location"] == "/tools"


# --------- P0-3: security headers on the real app --------- #


def test_security_headers_on_main_app(dev_client):
    r = dev_client.get("/api/health")
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert "Strict-Transport-Security" in r.headers


def test_security_headers_on_html_page(dev_client):
    """Headers ride on static HTML responses too, not just /api/*."""
    r = dev_client.get("/")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in r.headers


# --------- P1-5: unmatched /api 404 uses RFC 7807 --------- #


def test_unmatched_api_route_returns_problem_json(dev_client):
    """An unknown /api/* path must answer with the RFC 7807 envelope,
    not the ad-hoc `{"detail": "not found"}` that bypassed errors.py."""
    r = dev_client.get("/api/report/r_deadbeef00000000")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    # Canonical RFC 7807 members.
    assert body["status"] == 404
    assert body["type"].endswith("/not_found")
    assert "title" in body and "detail" in body


def test_unmatched_html_route_still_serves_404_page(dev_client):
    """Non-/api unknown routes keep the full HTML 404 template."""
    r = dev_client.get("/definitely-not-a-page")
    assert r.status_code == 404
    assert "text/html" in r.headers["content-type"]


# --------- P2-3: /api/version never forks a git subprocess --------- #


def test_version_no_subprocess_when_sha_present(dev_client, monkeypatch):
    """With STRUCTURAL_GIT_SHA set, /api/version must not shell out."""
    import subprocess as _sp

    def _boom(*a, **k):  # any subprocess call = test failure
        raise AssertionError("/api/version forked a subprocess")

    monkeypatch.setattr(_sp, "check_output", _boom)
    monkeypatch.setenv("STRUCTURAL_GIT_SHA", "feedface1234")
    r = dev_client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "feedface1234"


def test_version_prod_missing_sha_returns_unknown(monkeypatch):
    """In prod a missing SHA yields 'unknown' — never a git fork."""
    import subprocess as _sp

    monkeypatch.setattr(
        _sp, "check_output",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("prod /api/version forked git")
        ),
    )
    monkeypatch.delenv("STRUCTURAL_GIT_SHA", raising=False)
    main = _fresh_main(monkeypatch, "prod")
    client = TestClient(main.app)
    r = client.get("/api/version")
    assert r.status_code == 200
    assert r.json()["git_sha"] == "unknown"


# --------- P2: query-embedding cache hit-rate observability --------- #


def test_search_service_cache_stats_shape():
    """SearchService.cache_stats() reports LRU hits / misses / hit_rate."""
    from services.search_service import SearchService

    svc = SearchService(data_dir=None)  # no KB — we only exercise the cache
    stats = svc.cache_stats()
    assert set(stats) == {"hits", "misses", "hit_rate", "size", "maxsize"}
    assert stats["maxsize"] == 1024
    assert stats["hit_rate"] == 0.0  # nothing encoded yet

    # Encode the same query twice → exactly one cache hit.
    svc.encode_query("phase transition")
    svc.encode_query("phase transition")
    stats2 = svc.cache_stats()
    assert stats2["hits"] == 1
    assert stats2["misses"] == 1
    assert stats2["hit_rate"] == 0.5
