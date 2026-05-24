"""Unit tests for api.auth — W15-B (session #10).

Covers magic-link request, verify, logout, /me, JWT signature, rate
limiting, expiry, replay attack, invalid token.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_auth.py -q
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt as pyjwt
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import auth as auth_mod  # noqa: E402


@pytest.fixture(autouse=True)
def _fixed_jwt_secret(monkeypatch):
    """Lock the JWT secret so tokens are stable across test runs."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-deterministic-32-chars-please-ok")
    yield


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Spin up an isolated FastAPI app with auth router + tmp data dir."""
    monkeypatch.setattr(auth_mod, "_data_dir", lambda: tmp_path)
    # Reset any state — module-level files all derive from _data_dir(),
    # so changing _data_dir() is enough to isolate this test's data.

    app = FastAPI()
    app.include_router(auth_mod.router, prefix="/api")
    return TestClient(app)


def _request_link(client, email: str = "alice@example.com"):
    return client.post("/api/auth/request-link", json={"email": email})


# ---------------- request-link ----------------

def test_request_link_happy_path(client, tmp_path):
    r = _request_link(client, "alice@example.com")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    # Token file should now contain 1 record.
    tokens = (tmp_path / "magic_tokens.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(tokens) == 1
    row = json.loads(tokens[0])
    assert row["email"] == "alice@example.com"
    assert row["consumed_at"] is None
    # Mock outbox should also have the link.
    outbox = (tmp_path / "mock_email_outbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(outbox) == 1
    assert "auth/verify?token=" in json.loads(outbox[0])["link"]


def test_request_link_invalid_email(client):
    r = client.post("/api/auth/request-link", json={"email": "not-an-email"})
    assert r.status_code == 400
    assert "invalid email" in r.json()["error"]


def test_request_link_missing_email(client):
    # pydantic enforces the required field → 422
    r = client.post("/api/auth/request-link", json={})
    assert r.status_code == 422


def test_request_link_normalizes_email(client, tmp_path):
    r = _request_link(client, "  Alice@Example.COM  ")
    assert r.status_code == 200
    row = json.loads((tmp_path / "magic_tokens.jsonl").read_text().strip().splitlines()[0])
    assert row["email"] == "alice@example.com"


def test_request_link_rate_limit(client):
    # 3 requests allowed per hour per email, 4th should 429.
    for _ in range(3):
        r = _request_link(client, "rl@example.com")
        assert r.status_code == 200
    r = _request_link(client, "rl@example.com")
    assert r.status_code == 429
    assert "rate limit" in r.json()["error"].lower()


def test_request_link_dev_mode_returns_link(client, monkeypatch):
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    r = _request_link(client, "dev@example.com")
    body = r.json()
    assert "dev_link" in body and "dev_token" in body
    assert body["dev_link"].startswith("http")


# ---------------- verify ----------------

def _extract_latest_token(tmp_path) -> str:
    rows = (tmp_path / "magic_tokens.jsonl").read_text(encoding="utf-8").strip().splitlines()
    return json.loads(rows[-1])["token"]


def test_verify_happy_path(client, tmp_path):
    _request_link(client, "bob@example.com")
    token = _extract_latest_token(tmp_path)

    r = client.post("/api/auth/verify", json={"token": token})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["user"]["email"] == "bob@example.com"
    assert body["user"]["tier"] == "free"
    # Session cookie set.
    assert "phase_session" in r.cookies


def test_verify_invalid_token(client):
    r = client.post("/api/auth/verify", json={"token": "this-does-not-exist"})
    assert r.status_code == 400
    assert "invalid token" in r.json()["error"]


def test_verify_expired_token(client, tmp_path, monkeypatch):
    _request_link(client, "exp@example.com")
    # Rewrite the expires_at to be in the past.
    path = tmp_path / "magic_tokens.jsonl"
    rows = [json.loads(l) for l in path.read_text().strip().splitlines()]
    rows[-1]["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    r = client.post("/api/auth/verify", json={"token": rows[-1]["token"]})
    assert r.status_code == 400
    assert "expired" in r.json()["error"].lower()


def test_verify_replay_attack(client, tmp_path):
    _request_link(client, "replay@example.com")
    token = _extract_latest_token(tmp_path)
    r1 = client.post("/api/auth/verify", json={"token": token})
    assert r1.status_code == 200
    r2 = client.post("/api/auth/verify", json={"token": token})
    assert r2.status_code == 400
    assert "already used" in r2.json()["error"]


def test_verify_missing_token(client):
    r = client.post("/api/auth/verify", json={})
    assert r.status_code == 422


# ---------------- /me ----------------

def test_me_no_session(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "no session" in r.json()["error"]


def test_me_after_verify(client, tmp_path):
    _request_link(client, "me@example.com")
    token = _extract_latest_token(tmp_path)
    v = client.post("/api/auth/verify", json={"token": token})
    assert v.status_code == 200
    # TestClient carries the cookie automatically.
    r = client.get("/api/auth/me")
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == "me@example.com"


def test_me_invalid_jwt(client):
    client.cookies.set("phase_session", "not-a-valid-jwt-at-all")
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "invalid session" in r.json()["error"]


def test_me_tampered_signature(client, tmp_path):
    """Verify the JWT signature is actually checked (not just decoded)."""
    _request_link(client, "tamper@example.com")
    token = _extract_latest_token(tmp_path)
    client.post("/api/auth/verify", json={"token": token})
    real = client.cookies.get("phase_session")
    # Forge a token with the SAME claims but a different secret.
    claims = pyjwt.decode(real, options={"verify_signature": False})
    forged = pyjwt.encode(claims, "wrong-secret", algorithm="HS256")
    client.cookies.clear()
    client.cookies.set("phase_session", forged)
    r = client.get("/api/auth/me")
    assert r.status_code == 401, "tampered JWT must be rejected"


# ---------------- logout ----------------

def test_logout_clears_cookie(client, tmp_path):
    _request_link(client, "out@example.com")
    token = _extract_latest_token(tmp_path)
    client.post("/api/auth/verify", json={"token": token})
    assert client.cookies.get("phase_session")

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    # After logout, /me should 401.
    # TestClient retains cookies unless we explicitly clear; the
    # Set-Cookie header from the logout response carries Max-Age=0 which
    # clears the cookie in a real browser. TestClient doesn't always
    # honor that, so we clear manually to mimic browser behavior.
    client.cookies.clear()
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 401


def test_logout_revokes_jti(client, tmp_path):
    """Even if the JWT cookie is replayed after logout, /me should 401."""
    _request_link(client, "revoke@example.com")
    token = _extract_latest_token(tmp_path)
    v = client.post("/api/auth/verify", json={"token": token})
    jwt_str = v.cookies.get("phase_session")
    assert jwt_str

    client.post("/api/auth/logout")
    # Replay the old cookie.
    client.cookies.clear()
    client.cookies.set("phase_session", jwt_str)
    r = client.get("/api/auth/me")
    assert r.status_code == 401
    assert "revoked" in r.json()["error"].lower()


def test_logout_no_session_still_200(client):
    r = client.post("/api/auth/logout")
    assert r.status_code == 200


# ---------------- JWT structural checks ----------------

def test_jwt_has_required_claims(client, tmp_path):
    _request_link(client, "claims@example.com")
    token = _extract_latest_token(tmp_path)
    v = client.post("/api/auth/verify", json={"token": token})
    jwt_str = v.cookies.get("phase_session")
    claims = pyjwt.decode(jwt_str, "test-secret-deterministic-32-chars-please-ok", algorithms=["HS256"])
    assert claims["sub"] == "claims@example.com"
    assert claims["tier"] == "free"
    assert "iat" in claims and "exp" in claims and "jti" in claims
    # 30-day TTL.
    assert claims["exp"] - claims["iat"] == 30 * 24 * 3600
