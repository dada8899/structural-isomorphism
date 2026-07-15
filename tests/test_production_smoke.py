"""Unit tests for the production synthetic monitor (no network access)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "production_smoke.py"
SERVICE_UNIT = Path(__file__).resolve().parents[1] / "web" / "scripts" / "structural-web.service"
SPEC = importlib.util.spec_from_file_location("production_smoke", SCRIPT)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def encoded(value):
    return json.dumps(value).encode()


def successful_transport(method, url, body, timeout):
    assert 1 <= timeout <= 60
    if url == f"{smoke.STRUCTURAL}/":
        return smoke.Response(
            200,
            (
                '<html><a href="https://beta.structural.bytedance.city/auth/login">'
                "注册 / 登录</a>" + "x" * 120 + "</html>"
            ).encode(),
        )
    if url.endswith("/api/version"):
        requirements_sha = smoke.EXPECTED_RUNTIME_REQUIREMENTS_SHA256
        freeze_sha = "f" * 64
        return smoke.Response(200, encoded({
            "semver": "1.0", "git_sha": "a" * 40, "python_version": "3.11.6",
            "env": "prod", "model": "model", "deployed_at": "2026-07-11",
            "python_abi": "cpython-311",
            "runtime_id": f"cpython-311-{requirements_sha}-{freeze_sha}",
            "requirements_sha256": requirements_sha,
            "installed_freeze_sha256": freeze_sha,
            "fastapi": "0.115.14", "pydantic": "2.6.1",
            "starlette": "0.46.2", "uvicorn": "0.27.1",
        }))
    if url.endswith("/assets/runtime-attestation.json"):
        requirements_sha = smoke.EXPECTED_RUNTIME_REQUIREMENTS_SHA256
        freeze_sha = "f" * 64
        return smoke.Response(200, encoded({
            "schema_version": 1,
            "runtime_id": f"cpython-311-{requirements_sha}-{freeze_sha}",
            "requirements_sha256": requirements_sha,
            "installed_freeze_sha256": freeze_sha,
            "python_abi": "cpython-311",
            "python_version": "3.11.6",
            "fastapi": "0.115.14",
            "pydantic": "2.6.1",
            "starlette": "0.46.2",
            "uvicorn": "0.27.1",
            "git_sha": "a" * 40,
            "deployed_at": "2026-07-11",
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
    assert monitor.run() == 55
    assert waits == [2.1] * 29
    assert "PASS production smoke: 55 checks, 55 HTTP attempts" in capsys.readouterr().out


def test_systemd_activation_waits_for_deep_readiness():
    unit = SERVICE_UNIT.read_text(encoding="utf-8")
    start_post = next(line for line in unit.splitlines() if line.startswith("ExecStartPost="))
    assert "/bin/bash -c" in start_post
    assert "for attempt in {1..18}" in start_post
    assert "/usr/bin/curl -fsS --max-time 2" in start_post
    assert "127.0.0.1:5004/api/health?deep=1" in start_post
    assert "&& exit 0" in start_post and start_post.endswith("exit 1'")
    assert "TimeoutStartSec=135" in unit
    assert "Restart=on-failure" in unit
    # Worst case: 18 two-second probes plus 18 five-second sleeps = 126s.
    assert 18 * (2 + 5) < 135


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


@pytest.mark.parametrize(("field", "value", "expected"), [
    ("fastapi", "0.110.0", "fastapi must equal 0.115.14"),
    ("pydantic", "1.10.0", "pydantic must equal 2.6.1"),
    ("starlette", "0.36.3", "starlette must equal 0.46.2"),
    ("python_abi", "cpython-312", "python_abi must equal cpython-311"),
    ("git_sha", "stale", "API and runtime git SHAs differ"),
])
def test_runtime_attestation_drift_fails_closed(field, value, expected):
    def transport(method, url, body, timeout):
        response = successful_transport(method, url, body, timeout)
        if url.endswith("/assets/runtime-attestation.json"):
            payload = json.loads(response.body)
            payload[field] = value
            return smoke.Response(200, encoded(payload))
        return response

    with pytest.raises(smoke.SmokeFailure, match=expected):
        smoke.Monitor(transport).check_beta_system()


def test_checked_out_git_sha_prevents_two_consistently_stale_fingerprints():
    with pytest.raises(
        smoke.SmokeFailure,
        match="running git SHA does not exactly match the expected beta release",
    ):
        smoke.Monitor(
            successful_transport,
            expected_git_sha="d" * 40,
        ).check_beta_system()


def test_checked_out_full_git_sha_requires_exact_running_identity():
    monitor = smoke.Monitor(
        successful_transport,
        expected_git_sha="a" * 40,
    )
    monitor.check_beta_system()


def test_docs_only_main_advance_keeps_last_successful_beta_release_as_authority():
    last_successful_beta_sha = "a" * 40
    docs_only_main_sha = "b" * 40
    assert docs_only_main_sha != last_successful_beta_sha

    smoke.Monitor(
        successful_transport,
        expected_git_sha=last_successful_beta_sha,
    ).check_beta_system()
    with pytest.raises(
        smoke.SmokeFailure,
        match="running git SHA does not exactly match the expected beta release",
    ):
        smoke.Monitor(
            successful_transport,
            expected_git_sha=docs_only_main_sha,
        ).check_beta_system()


@pytest.mark.parametrize("invalid", ["a" * 12, "a" * 64, "A" * 40, "g" * 40])
def test_cli_requires_exactly_one_lowercase_full_sha1_identity(invalid):
    with pytest.raises(SystemExit) as caught:
        smoke.main(["--expected-git-sha", invalid])
    assert caught.value.code == 2


def test_checked_out_full_git_sha_rejects_a_matching_prefix_only():
    with pytest.raises(
        smoke.SmokeFailure,
        match="running git SHA does not exactly match the expected beta release",
    ):
        smoke.Monitor(
            successful_transport,
            expected_git_sha="a" * 12 + "b" * 28,
        ).check_beta_system()


def test_invalid_json_fails_without_echoing_body():
    secret_like_body = b'{"token":"must-not-appear"'
    def transport(method, url, body, timeout):
        return smoke.Response(200, secret_like_body)
    with pytest.raises(smoke.SmokeFailure) as caught:
        smoke.Monitor(transport).json("probe", "GET", "https://example.test")
    assert "must-not-appear" not in str(caught.value)


def test_docs_homepage_without_account_entry_fails_closed():
    def transport(method, url, body, timeout):
        return smoke.Response(200, b"<html>" + b"x" * 120 + b"</html>")

    with pytest.raises(smoke.SmokeFailure, match="registration/login entry is missing"):
        smoke.Monitor(transport).check_structural_docs()


def test_unexpected_status_fails_closed():
    def transport(method, url, body, timeout):
        return smoke.Response(502, b"upstream details")
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 200, got 502"):
        smoke.Monitor(transport).check_structural_docs()


def test_get_retries_transient_network_and_upstream_failures_only():
    outcomes = [
        smoke.SmokeFailure("temporary network failure"),
        smoke.Response(502, b"starting"),
        smoke.Response(200, b"<html>" + b"x" * 120 + b"</html>"),
    ]
    calls = []
    waits = []

    def transport(method, url, body, timeout):
        calls.append((method, url))
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monitor = smoke.Monitor(
        transport, sleeper=waits.append, get_retry_delays=(0.1, 0.2)
    )
    monitor.check_page("page", "https://example.test/")
    assert len(calls) == 3
    assert waits == [0.1, 0.2]
    assert monitor.checked == 1
    assert monitor.attempted_requests == 3


def test_get_retry_remains_fail_closed_after_budget():
    calls = 0

    def transport(method, url, body, timeout):
        nonlocal calls
        calls += 1
        return smoke.Response(503, b"still unavailable")

    monitor = smoke.Monitor(
        transport, sleeper=lambda _delay: None, get_retry_delays=(0.0, 0.0)
    )
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 200, got 503"):
        monitor.check_structural_docs()
    assert calls == 3


def test_post_is_never_retried():
    calls = 0

    def transport(method, url, body, timeout):
        nonlocal calls
        calls += 1
        return smoke.Response(503, b"unavailable")

    monitor = smoke.Monitor(
        transport, sleeper=lambda _delay: None, get_retry_delays=(0.0, 0.0)
    )
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 200, got 503"):
        monitor.request("write", "POST", "https://example.test/write", payload={"x": 1})
    assert calls == 1


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


def test_disabled_billing_surface_accidental_200_fails():
    def transport(method, url, body, timeout):
        if url.endswith("/api/billing/checkout-session"):
            return smoke.Response(200, encoded({"ok": True}))
        return successful_transport(method, url, body, timeout)
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 503, got 200"):
        smoke.Monitor(transport).check_disabled_surfaces()


def test_beta_auth_disabled_or_accidentally_public_fails():
    def transport(method, url, body, timeout):
        result = successful_transport(method, url, body, timeout)
        if url.endswith("/api/auth/me"):
            return smoke.Response(503, encoded({"error": "auth unavailable"}))
        return result
    with pytest.raises(smoke.SmokeFailure, match="expected HTTP 401, got 503"):
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
