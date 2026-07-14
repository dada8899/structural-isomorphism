"""Unit tests for api.auth — W15-B (session #10).

Covers magic-link request, verify, logout, /me, JWT signature, rate
limiting, expiry, replay attack, invalid token.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_auth.py -q
"""
from __future__ import annotations

import json
import hashlib
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor
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


def test_jwt_secret_fails_closed_in_production(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        auth_mod._jwt_secret()


@pytest.mark.parametrize(
    "secret",
    [
        "replace-with-private-32-plus-character-secret",
        "change-me-please-this-is-not-a-real-secret-1234",
        "a" * 64,
    ],
)
def test_jwt_secret_rejects_predictable_production_values(monkeypatch, secret):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", secret)
    with pytest.raises(RuntimeError, match="non-placeholder"):
        auth_mod._jwt_secret()


def test_jwt_secret_accepts_high_entropy_production_value(monkeypatch):
    secret = "5b7fF9d2A8c4E1g6H3j0K7m9N2p5Q8s1V4x6Z0r3T7w9Y2u5"
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("JWT_SECRET", secret)
    assert auth_mod._jwt_secret() == secret


@pytest.fixture(autouse=True)
def _fixed_jwt_secret(monkeypatch):
    """Lock the JWT secret so tokens are stable across test runs."""
    monkeypatch.setenv("JWT_SECRET", "test-secret-deterministic-32-chars-please-ok")
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
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
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM magic_tokens").fetchall()
    assert len(rows) == 1
    row = dict(rows[0])
    assert row["email"] == "alice@example.com"
    assert row["consumed_at"] is None
    assert "token" not in row
    assert len(row["token_hash"]) == 64
    # Mock outbox should also have the link.
    outbox = (tmp_path / "mock_email_outbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(outbox) == 1
    assert "auth/verify?token=" in json.loads(outbox[0])["text"]


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
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        row = conn.execute("SELECT email FROM magic_tokens").fetchone()
    assert row[0] == "alice@example.com"


def test_request_link_rate_limit(client):
    # 3 requests allowed per hour per email, 4th should 429.
    for _ in range(3):
        r = _request_link(client, "rl@example.com")
        assert r.status_code == 200
    r = _request_link(client, "rl@example.com")
    assert r.status_code == 429
    assert "rate limit" in r.json()["error"].lower()


def test_rate_limit_keys_are_domain_separated_hmacs(client, tmp_path):
    email = "rate-private@example.com"
    response = _request_link(client, email)
    assert response.status_code == 200
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        keys = {
            row[0]
            for row in conn.execute("SELECT DISTINCT email FROM auth_rate_requests")
        }
    assert "global:magic-link-email" in keys
    private_keys = keys - {"global:magic-link-email"}
    assert len(private_keys) == 2
    assert {key.split(":", 1)[0] for key in private_keys} == {"email", "ip"}
    serialized = json.dumps(sorted(keys))
    assert email not in serialized
    assert hashlib.sha256(email.encode()).hexdigest() not in serialized

    same_value = "same-value"
    assert auth_mod._privacy_rate_key("email", same_value) != auth_mod._privacy_rate_key(
        "ip", same_value
    )
    assert auth_mod._privacy_rate_key("email", same_value) == auth_mod._privacy_rate_key(
        "email", same_value
    )


def test_request_link_dev_mode_returns_link(client, monkeypatch):
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    r = _request_link(client, "dev@example.com")
    body = r.json()
    assert "dev_link" in body and "dev_token" in body
    assert body["dev_link"].startswith("http")


# ---------------- verify ----------------

def _extract_latest_token(tmp_path) -> str:
    rows = (tmp_path / "mock_email_outbox.jsonl").read_text(encoding="utf-8").strip().splitlines()
    text = json.loads(rows[-1])["text"]
    return text.split("token=", 1)[1].strip()


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
    token = _extract_latest_token(tmp_path)
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        conn.execute(
            "UPDATE magic_tokens SET expires_at=?",
            ((datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),),
        )

    r = client.post("/api/auth/verify", json={"token": token})
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


def test_verify_token_is_atomic_under_concurrency(client, tmp_path):
    _request_link(client, "race@example.com")
    token = _extract_latest_token(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(
            lambda _: client.post("/api/auth/verify", json={"token": token}).status_code,
            range(8),
        ))
    assert statuses.count(200) == 1
    assert statuses.count(400) == 7


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
    forged = pyjwt.encode(claims, "wrong-secret-that-is-at-least-32-bytes", algorithm="HS256")
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


def test_auth_disabled_fails_closed(client, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "false")
    assert _request_link(client).status_code == 503
    assert client.get("/api/auth/me").status_code == 503


def test_cross_origin_cookie_mutation_rejected(client, monkeypatch):
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "https://phase.example.com")
    r = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example"},
    )
    assert r.status_code == 403


def test_first_registration_notifies_admin_once(client, tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_NOTIFICATION_EMAIL", "owner@example.com")
    _request_link(client, "new@example.com")
    client.post("/api/auth/verify", json={"token": _extract_latest_token(tmp_path)})
    outbox = [json.loads(row) for row in (tmp_path / "mock_email_outbox.jsonl").read_text().splitlines()]
    notifications = [row for row in outbox if row["to"] == "owner@example.com"]
    assert len(notifications) == 1

    _request_link(client, "new@example.com")
    client.post("/api/auth/verify", json={"token": _extract_latest_token(tmp_path)})
    outbox = [json.loads(row) for row in (tmp_path / "mock_email_outbox.jsonl").read_text().splitlines()]
    assert len([row for row in outbox if row["to"] == "owner@example.com"]) == 1


def test_notification_failure_does_not_rollback_user(client, tmp_path, monkeypatch):
    monkeypatch.delenv("ADMIN_NOTIFICATION_EMAIL", raising=False)
    _request_link(client, "durable@example.com")
    r = client.post("/api/auth/verify", json={"token": _extract_latest_token(tmp_path)})
    assert r.status_code == 200
    assert client.get("/api/auth/me").status_code == 200
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        retry = conn.execute(
            "SELECT email, delivered_at FROM auth_notification_outbox"
        ).fetchone()
    assert retry == ("durable@example.com", None)

    monkeypatch.setenv("ADMIN_NOTIFICATION_EMAIL", "owner@example.com")
    sent, remaining = auth_mod.retry_registration_notifications()
    assert (sent, remaining) == (1, 0)
    with sqlite3.connect(tmp_path / "auth.sqlite3") as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM auth_notification_outbox WHERE delivered_at IS NULL"
        ).fetchone()[0] == 0


def test_production_email_config_fails_closed(client, monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    r = _request_link(client)
    assert r.status_code == 503
    assert r.json()["error"] == "auth unavailable"


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
