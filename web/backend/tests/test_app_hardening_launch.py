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
    ***REMOVED*** prod path requires the share-token secret env (report_store guards it).
    monkeypatch.setenv("STRUCTURAL_SHARE_TOKEN_SECRET", "test-secret-for-suite")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main  ***REMOVED*** noqa: WPS433 — deliberate reload
    return main


@pytest.fixture
def dev_client(monkeypatch):
    main = _fresh_main(monkeypatch, "dev")
    return TestClient(main.app)


@pytest.fixture
def prod_client(monkeypatch):
    main = _fresh_main(monkeypatch, "prod")
    return TestClient(main.app)


***REMOVED*** --------- P1-4: HEAD / --------- ***REMOVED***


def test_head_root_returns_200(dev_client):
    """HEAD / must be 200 — health checkers / CDNs probe with HEAD."""
    r = dev_client.head("/")
    assert r.status_code == 200


def test_get_root_still_works(dev_client):
    r = dev_client.get("/")
    assert r.status_code == 200


***REMOVED*** --------- P1-4: docs gating by env --------- ***REMOVED***


def test_docs_open_in_dev(dev_client):
    assert dev_client.get("/openapi.json").status_code == 200
    assert dev_client.get("/docs").status_code == 200


def test_docs_disabled_in_prod(prod_client):
    """In prod the API surface map must not be publicly browsable."""
    assert prod_client.get("/openapi.json").status_code == 404
    assert prod_client.get("/docs").status_code == 404
    assert prod_client.get("/redoc").status_code == 404


***REMOVED*** --------- P0-3: security headers on the real app --------- ***REMOVED***


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
