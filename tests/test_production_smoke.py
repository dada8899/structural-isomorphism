"""Unit tests for the production synthetic monitor (no network access)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "production_smoke.py"
SPEC = importlib.util.spec_from_file_location("production_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def encoded(value):
    return json.dumps(value).encode()


def successful_transport(method, url, body, timeout):
    assert 1 <= timeout <= 60
    if url.endswith("/api/version"):
        return smoke.Response(200, encoded({
            "semver": "1.0", "git_sha": "abc", "python_version": "3.12",
            "env": "prod", "model": "model", "deployed_at": "2026-07-11",
        }))
    if "api/health?deep=1" in url:
        return smoke.Response(200, encoded({
            "status": "ok", "kb_size": 4443, "artifact_id": "structural-v2-kb4443-20260711",
            "embedding_shape": [4443, 768], "checks": {
                "search_service": "ok", "knowledge_base": "ok", "artifact_manifest": "ok",
                "history_db": "ok", "llm_env": "missing",
            },
        }))
    if url.endswith("/api/search"):
        query = json.loads(body)["query"]
        if query in smoke.OOS_QUERIES:
            return smoke.Response(200, encoded({
                "out_of_scope": True, "scope_reason": "test", "count": 0, "results": [],
            }))
        return smoke.Response(200, encoded({
            "out_of_scope": False, "count": 1, "results": [{
                "id": "x", "name": "name", "domain": "domain", "type_id": "soc",
                "cross_domain": True,
            }],
        }))
    if url.endswith("/api/billing/checkout-session"):
        return smoke.Response(503, encoded({"error": "billing_not_available"}))
    if url.endswith("/api/auth/request-link"):
        return smoke.Response(503, encoded({"error": "account_features_not_available"}))
    if url.endswith("/api/auth/me"):
        return smoke.Response(401, encoded({"ok": False, "error": "no session"}))
    if url.endswith("/api/ews/meta"):
        return smoke.Response(200, encoded({"n_tickers": 597, "price_provenance": "demo"}))
    if url.endswith("/api/health"):
        return smoke.Response(200, encoded({"status": "ok"}))
    if url.endswith("/pricing.html"):
        return smoke.Response(404, b"retired")
    if url.endswith("/auth/login"):
        return smoke.Response(200, "<html>发送登录链接</html>".encode())
    return smoke.Response(200, b"<html>" + b"x" * 120 + b"</html>")


def test_full_monitor_contract_passes_with_mock_transport(capsys):
    waits = []
    monitor = smoke.Monitor(
        successful_transport, timeout=3, search_interval=2.1, sleeper=waits.append
    )
    assert monitor.run() == 54
    assert waits == [2.1] * 29
    assert "PASS production smoke: 54 requests" in capsys.readouterr().out


@pytest.mark.parametrize("mutation, expected", [
    (("kb_size", 0), "kb_size must equal 4443"),
    (("embedding_shape", [4856, 768]), "embedding_shape must equal"),
    (("artifact_id", ""), "artifact_id must match canonical"),
])
def test_deep_health_fails_closed(mutation, expected):
    key, value = mutation
    def transport(method, url, body, timeout):
        response = successful_transport(method, url, body, timeout)
        if "api/health?deep=1" in url:
            payload = json.loads(response.body)
            payload[key] = value
            return smoke.Response(200, encoded(payload))
        return response
    with pytest.raises(smoke.SmokeFailure, match=expected):
        smoke.Monitor(transport).check_beta_system()


def test_invalid_json_fails_without_echoing_body():
    secret_like_body = b'{"token":"must-not-appear"'
    def transport(method, url, body, timeout):
        return smoke.Response(200, secret_like_body)
    with pytest.raises(smoke.SmokeFailure) as caught:
        smoke.Monitor(transport).json("probe", "GET", "https://example.test")
    assert "must-not-appear" not in str(caught.value)


def test_unexpected_status_fails_closed():
    def transport(method, url, body, timeout):
        return smoke.Response(502, b"upstream details")
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 200, got 502"):
        smoke.Monitor(transport).check_structural_docs()


def test_in_scope_empty_results_fail():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/search") and json.loads(body)["query"] in smoke.ZH_QUERIES:
            return smoke.Response(200, encoded({"out_of_scope": False, "count": 0, "results": []}))
        return result
    with pytest.raises(smoke.SmokeFailure, match="results must be non-empty"):
        smoke.Monitor(transport).check_search()


def test_oos_leak_fails():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/search") and json.loads(body)["query"] == smoke.OOS_QUERIES[0]:
            return smoke.Response(200, encoded({"out_of_scope": False, "count": 1, "results": [{}]}))
        return result
    with pytest.raises(smoke.SmokeFailure, match="must be explicitly refused"):
        smoke.Monitor(transport).check_search()


def test_missing_cross_domain_candidate_fails():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/search") and json.loads(body)["query"] not in smoke.OOS_QUERIES:
            payload = json.loads(result.body)
            payload["results"][0]["cross_domain"] = False
            return smoke.Response(200, encoded(payload))
        return result
    with pytest.raises(smoke.SmokeFailure, match="no cross-domain candidate"):
        smoke.Monitor(transport).check_search()


@pytest.mark.parametrize("url_suffix", ["/api/billing/checkout-session", "/api/auth/request-link"])
def test_disabled_surface_accidental_200_fails(url_suffix):
    def transport(method, url, body, timeout):
        if url.endswith(url_suffix):
            return smoke.Response(200, encoded({"ok": True}))
        return successful_transport(method, url, body, timeout)
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 503, got 200"):
        smoke.Monitor(transport).check_disabled_surfaces()


def test_phase_wrong_provenance_fails():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/ews/meta"):
            return smoke.Response(200, encoded({"n_tickers": 597, "price_provenance": "live"}))
        return result
    with pytest.raises(smoke.SmokeFailure, match="price_provenance must equal demo"):
        smoke.Monitor(transport).check_phase()


def test_phase_auth_disabled_or_accidentally_public_fails():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/auth/me"):
            return smoke.Response(503, encoded({"error": "auth unavailable"}))
        return result
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 401, got 503"):
        smoke.Monitor(transport).check_phase()
