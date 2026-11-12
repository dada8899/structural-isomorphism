"""Tests for /api/version endpoint.

Session #16 added `model` + `deployed_at` to the response so dogfood scripts
can fingerprint-check prod in a single request (session #15 incident: 5-day
deploy pipeline failure was undetected because no single endpoint exposed
the actually-running model).

These tests pin the schema fields so we never silently drop them again.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Ensure web/backend is on sys.path
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_ASK_IMPORT_GLOBALS = (
    "ASK_MODEL", "RELEVANCE_TOP1_MIN", "RELEVANCE_TOP3_MEAN_MIN",
)


def _snapshot_ask_globals():
    """Import under the caller's real env before tests apply overrides."""
    import services.ask_orchestrator as module  # noqa: WPS433
    return module, {name: getattr(module, name) for name in _ASK_IMPORT_GLOBALS}


def _restore_ask_globals(module, snapshot) -> None:
    for name, value in snapshot.items():
        setattr(module, name, value)


@pytest.fixture
def client(monkeypatch):
    """Build a TestClient that doesn't trigger the full lifespan (search load).

    We import main *after* monkeypatching env so version() picks up our overrides.
    """
    ask_orchestrator, original_globals = _snapshot_ask_globals()
    # Set deterministic env so the assertions don't drift with the host.
    monkeypatch.setenv("STRUCTURAL_GIT_SHA", "a" * 40)
    monkeypatch.setenv("STRUCTURAL_BUILD_DATE", "2026-05-20T15:00:00Z")
    monkeypatch.setenv("STRUCTURAL_DEPLOYED_AT", "2026-05-20T16:30:00Z")
    monkeypatch.setenv("STRUCTURAL_ENV", "test")
    monkeypatch.setenv("STRUCTURAL_RUNTIME_ID", "cpython-311-runtime-test")
    monkeypatch.setenv("STRUCTURAL_RUNTIME_REQUIREMENTS_SHA256", "a" * 64)
    monkeypatch.setenv("STRUCTURAL_RUNTIME_FREEZE_SHA256", "b" * 64)
    monkeypatch.setenv("ASK_LLM_MODEL", "deepseek/deepseek-chat:nitro")

    # Reload main to pick up fresh env.
    if "main" in sys.modules:
        del sys.modules["main"]
    import main as _main  # noqa: WPS433

    # Do not enter the context manager: that would run the heavy app lifespan.
    c = TestClient(_main.app, raise_server_exceptions=True)
    try:
        yield c
    finally:
        c.close()
        _restore_ask_globals(ask_orchestrator, original_globals)


def test_version_returns_all_required_fields(client):
    """All fields the dogfood fingerprint check + Plausible analytics rely on."""
    r = client.get("/api/version")
    assert r.status_code == 200, r.text
    body = r.json()

    # Original fields (must not regress)
    assert "semver" in body
    assert "git_sha" in body
    assert "build_date" in body
    assert "python_version" in body
    for field in (
        "python_abi", "runtime_id", "requirements_sha256", "installed_freeze_sha256",
        "fastapi", "pydantic", "starlette", "uvicorn",
    ):
        assert field in body
    assert "env" in body
    # New in session #16 — the fields that close the session-15 incident gap
    assert "model" in body, "model field is required for dogfood fingerprint check"
    assert "deployed_at" in body, "deployed_at field is required to detect stale deploys"


def test_version_picks_up_env_overrides(client):
    """STRUCTURAL_* env should flow through end-to-end."""
    r = client.get("/api/version")
    body = r.json()
    assert body["git_sha"] == "a" * 40
    assert body["build_date"] == "2026-05-20T15:00:00Z"
    assert body["deployed_at"] == "2026-05-20T16:30:00Z"
    assert body["env"] == "test"
    assert body["model"] == "deepseek/deepseek-chat:nitro"


@pytest.mark.parametrize("invalid_sha", ["a" * 12, "a" * 64, "A" * 40, "g" * 40])
def test_version_rejects_noncanonical_git_identity(monkeypatch, invalid_sha):
    monkeypatch.setenv("STRUCTURAL_GIT_SHA", invalid_sha)
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    if "main" in sys.modules:
        del sys.modules["main"]
    import main as _main  # noqa: WPS433

    assert _main._resolve_git_sha() == "unknown"


def test_version_deployed_at_falls_back_to_build_date(monkeypatch):
    """If STRUCTURAL_DEPLOYED_AT is unset, deployed_at == build_date."""
    monkeypatch.setenv("STRUCTURAL_BUILD_DATE", "2026-05-20T15:00:00Z")
    monkeypatch.delenv("STRUCTURAL_DEPLOYED_AT", raising=False)
    monkeypatch.setenv("STRUCTURAL_GIT_SHA", "d" * 40)
    monkeypatch.setenv("ASK_LLM_MODEL", "deepseek/deepseek-chat:nitro")

    if "main" in sys.modules:
        del sys.modules["main"]
    import main as _main  # noqa: WPS433

    c = TestClient(_main.app)
    try:
        r = c.get("/api/version")
    finally:
        c.close()
    body = r.json()
    assert body["deployed_at"] == body["build_date"] == "2026-05-20T15:00:00Z"


def test_version_model_default_when_env_missing(monkeypatch):
    """If ASK_LLM_MODEL unset, model field still resolves to the in-code default
    so dogfood scripts don't crash on a missing key — they should be able to
    detect 'model field is the WRONG model' just as well as 'model is missing'.
    """
    monkeypatch.delenv("ASK_LLM_MODEL", raising=False)
    monkeypatch.setenv("STRUCTURAL_GIT_SHA", "e" * 40)

    # Earlier tests may have imported the module while a host/test override was
    # present. Reload it under the environment this test is asserting.
    ask_orchestrator, original_globals = _snapshot_ask_globals()
    try:
        importlib.reload(ask_orchestrator)

        if "main" in sys.modules:
            del sys.modules["main"]
        import main as _main  # noqa: WPS433

        c = TestClient(_main.app)
        try:
            r = c.get("/api/version")
        finally:
            c.close()
        body = r.json()
        # Default in main.version() matches ask_orchestrator.ASK_MODEL default.
        assert body["model"] == "openai/gpt-5.6-luna-pro"
    finally:
        _restore_ask_globals(ask_orchestrator, original_globals)


def test_version_schema_typed_strings(client):
    """All fields must be strings — Plausible / dogfood consume them as strings."""
    r = client.get("/api/version")
    body = r.json()
    for field in ("semver", "git_sha", "build_date", "python_version", "env",
                  "python_abi", "runtime_id", "requirements_sha256",
                  "installed_freeze_sha256", "fastapi", "pydantic", "starlette",
                  "uvicorn", "model", "deployed_at"):
        assert isinstance(body[field], str), f"{field} should be a string, got {type(body[field])}"
        assert body[field], f"{field} should not be empty"
