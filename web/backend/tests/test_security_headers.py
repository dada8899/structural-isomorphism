"""Tests for the security-headers middleware — launch P0-3.

Before this middleware the app shipped zero security headers. These tests
assert every required header is present and sane, and that the CSP keeps
the CDN resources the frontend depends on (KaTeX, Plausible) whitelisted.
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from middleware.security_headers import install_security_headers  ***REMOVED*** noqa: E402


def _client() -> TestClient:
    app = FastAPI()
    install_security_headers(app)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    return TestClient(app)


def test_all_security_headers_present():
    r = _client().get("/api/ping")
    assert r.status_code == 200
    h = r.headers
    assert h.get("X-Frame-Options") == "DENY"
    assert h.get("X-Content-Type-Options") == "nosniff"
    assert h.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "Content-Security-Policy" in h
    ***REMOVED*** HSTS sent on the default (https-assumed) path.
    assert "Strict-Transport-Security" in h
    assert "max-age=31536000" in h["Strict-Transport-Security"]


def test_csp_whitelists_cdn_dependencies():
    """The CSP must NOT break the frontend's external resources:
    KaTeX (cdn.jsdelivr.net) and Plausible (both hosts)."""
    csp = _client().get("/api/ping").headers["Content-Security-Policy"]
    assert "cdn.jsdelivr.net" in csp           ***REMOVED*** KaTeX
    assert "plausible.bytedance.city" in csp   ***REMOVED*** self-hosted analytics
    assert "plausible.io" in csp               ***REMOVED*** report.html legacy host
    ***REMOVED*** Clickjacking hard-stop.
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_hsts_skipped_on_plain_http():
    """HSTS only makes sense over HTTPS — skipped when X-Forwarded-Proto
    says the request arrived over plain http."""
    r = _client().get("/api/ping", headers={"X-Forwarded-Proto": "http"})
    assert "Strict-Transport-Security" not in r.headers


def test_headers_applied_to_404_too():
    """Security headers ride on every response, including error ones."""
    r = _client().get("/does-not-exist")
    assert r.status_code == 404
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
