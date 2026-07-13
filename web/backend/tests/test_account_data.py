"""Authenticated account export/delete and registry symmetry tests."""
from __future__ import annotations

import json
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api import auth, favorites, report_account, sso  # noqa: E402
from services.report_store import ReportStore  # noqa: E402
from services.account_data_registry import AccountAsset, AccountDataRegistry  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(auth, "_data_dir", lambda: tmp_path)
    monkeypatch.setenv("STRUCTURAL_FAVORITES_PATH", str(tmp_path / "favorites.jsonl"))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("JWT_SECRET", "account-data-test-secret-32-chars-long")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "http://testserver")
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "account-data-sso-secret-32-characters-long")
    monkeypatch.setenv("STRUCTURAL_SSO_DATA_DIR", str(tmp_path / "sso"))
    report_account._store = ReportStore(tmp_path / "history.db")
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(favorites.router, prefix="/api")
    yield TestClient(app)
    report_account._store = None


def _login(client: TestClient, email: str = "alice@example.com") -> str:
    auth._ensure_user(email)
    token, _ = auth._issue_jwt(email, "free")
    client.cookies.set("phase_session", token)
    return token


def _favorite(client: TestClient, ticker: str) -> None:
    response = client.post(
        f"/api/favorites/{ticker}", headers={"Origin": "http://testserver"}
    )
    assert response.status_code in {200, 201}, response.text


def test_registry_rejects_asymmetric_or_duplicate_assets():
    with pytest.raises(ValueError, match="export and delete"):
        AccountDataRegistry([AccountAsset("bad", "email", "forever", None, lambda _: None)])  # type: ignore[arg-type]
    asset = AccountAsset("same", "email", "until delete", lambda _: {}, lambda _: {})
    with pytest.raises(ValueError, match="unique"):
        AccountDataRegistry([asset, asset])


def test_export_requires_session_and_derives_owner_from_cookie(client):
    assert client.get("/api/me/export").status_code == 401
    _login(client)
    response = client.get("/api/me/export")
    assert response.status_code == 200
    body = response.json()
    assert [item["name"] for item in body["assets"]] == [
        "favorites", "claimed_reports", "authentication"
    ]
    assert body["data"]["authentication"]["account"]["email"] == "alice@example.com"


def test_export_includes_favorites_without_credential_hashes(client):
    _login(client)
    _favorite(client, "AAPL")
    response = client.get("/api/me/export")
    assert response.json()["data"]["favorites"]["tickers"] == ["AAPL"]
    serialized = response.text.lower()
    assert "token_hash" not in serialized
    assert "phase_session" not in serialized
    assert "jwt" not in serialized


def test_export_and_delete_include_owner_linked_revocation_events(client):
    token = _login(client)
    claims = auth._decode_jwt(token)
    assert claims is not None
    auth._store().revoke(claims["jti"], "2026-07-12T00:00:00+00:00", claims["sub"])
    # Use a fresh valid session after revoking the first one.
    _login(client)
    exported = client.get("/api/me/export").json()["data"]["authentication"]
    assert exported["revoked_session_events"] == [
        {"revoked_at": "2026-07-12T00:00:00+00:00"}
    ]
    deleted = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert deleted.json()["removed"]["authentication"]["revoked_session_events"] == 1


def test_export_never_accepts_email_override(client):
    _login(client, "alice@example.com")
    auth._ensure_user("bob@example.com")
    response = client.get("/api/me/export?email=bob@example.com")
    assert response.status_code == 200
    assert response.json()["data"]["authentication"]["account"]["email"] == "alice@example.com"


def test_delete_requires_exact_confirmation_and_same_origin(client):
    _login(client)
    wrong = client.post("/api/me/delete", json={"confirmation": "delete"})
    assert wrong.status_code == 400
    cross_site = client.post(
        "/api/me/delete",
        json={"confirmation": "DELETE"},
        headers={"Origin": "https://evil.example"},
    )
    assert cross_site.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_delete_erases_auth_tokens_notifications_and_favorites(client, tmp_path):
    token = _login(client)
    _favorite(client, "AAPL")
    response = client.post(
        "/api/me/delete",
        json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"]["favorites"] == {"records": 1, "tickers": 1}
    assert response.json()["removed"]["authentication"]["account"] == 1
    assert "phase_session=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]

    # A copied JWT also fails: account existence is the global revocation epoch.
    replay = TestClient(client.app)
    replay.cookies.set("phase_session", token)
    assert replay.get("/api/auth/me").status_code == 401
    assert replay.get("/api/me/export").status_code == 401

    # Re-registering the same address creates a fresh generation; the copied
    # pre-deletion JWT must remain permanently invalid.
    auth._ensure_user("alice@example.com")
    assert replay.get("/api/auth/me").status_code == 401

    audit = json.loads((tmp_path / "account_deletion_audit.jsonl").read_text().strip())
    assert "email" not in audit
    assert len(audit["owner_hash"]) == 16


def test_delete_erases_claimed_beta_reports_and_revokes_beta_session(client):
    _login(client)
    subject = sso._subject_id("alice@example.com")
    report_account._store.create(
        query="claimed", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="anon-owner",
    )
    report_account._store.claim_by_anon("anon-owner", subject)
    now = int(__import__("time").time())
    beta_token = __import__("jwt").encode(
        {"iss": sso._beta_origin(), "aud": "structural-beta-session", "sub": subject, "tier": "free",
         "jti": "beta-jti", "iat": now, "issued_ns": __import__("time").time_ns(),
         "exp": now + 3600},
        sso._secret(), algorithm="HS256",
    )
    sso.SsoReplayStore(sso._data_dir() / "sso_replay.sqlite3").issue(
        "trusted-binding", subject, "free", now + 120, email="alice@example.com",
    )
    before = TestClient(client.app)
    before.cookies.set("structural_beta_session", beta_token)
    # The auth-only fixture does not mount report-account routes; resolver is
    # the security primitive used by those routes.
    from starlette.requests import Request
    request = Request({"type": "http", "headers": [(b"cookie", f"structural_beta_session={beta_token}".encode())]})
    assert sso.resolve_beta_user(request)[1] == "valid"

    deleted = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["removed"]["claimed_reports"]["reports"] == 1
    assert report_account._store.list_by_owner(subject) == []
    assert sso.resolve_beta_user(request)[1] == "revoked"


def test_delete_isolates_other_accounts(client):
    _login(client, "alice@example.com")
    _favorite(client, "AAPL")
    client.cookies.clear()
    bob_token = _login(client, "bob@example.com")
    _favorite(client, "TSLA")
    client.cookies.clear()
    _login(client, "alice@example.com")
    assert client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    ).status_code == 200

    bob = TestClient(client.app)
    bob.cookies.set("phase_session", bob_token)
    exported = bob.get("/api/me/export").json()["data"]
    assert exported["authentication"]["account"]["email"] == "bob@example.com"
    assert exported["favorites"]["tickers"] == ["TSLA"]


def test_late_failure_rolls_back_favorites_and_keeps_account(client, monkeypatch):
    _login(client)
    _favorite(client, "AAPL")
    subject = sso._subject_id("alice@example.com")
    report_account._store.create(
        query="rollback", b_id="b", lang="zh", payload={}, model="m",
        creator_anon_id="anon-rollback",
    )
    report_account._store.claim_by_anon("anon-rollback", subject)

    def fail(_email: str):
        raise OSError("simulated auth database failure")

    monkeypatch.setattr(auth.AuthStore, "delete_account_data", fail)
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 500
    assert client.get("/api/auth/me").status_code == 200
    assert client.get("/api/favorites").json()["tickers"] == ["AAPL"]
    assert len(report_account._store.list_by_owner(subject)) == 1
    assert sso.SsoReplayStore(
        sso._data_dir() / "sso_replay.sqlite3"
    ).subject_revoked_at(subject) is None


def test_report_delete_failure_does_not_leave_beta_session_revoked(client, monkeypatch):
    _login(client)
    subject = sso._subject_id("alice@example.com")
    monkeypatch.setattr(
        report_account._store, "delete_by_owner",
        lambda _owner: (_ for _ in ()).throw(OSError("simulated report db failure")),
    )
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 500
    assert sso.SsoReplayStore(
        sso._data_dir() / "sso_replay.sqlite3"
    ).subject_revoked_at(subject) is None
    assert client.get("/api/auth/me").status_code == 200


def test_late_failure_restores_an_existing_empty_favorites_record(client, monkeypatch):
    _login(client)
    _favorite(client, "AAPL")
    assert client.delete(
        "/api/favorites/AAPL", headers={"Origin": "http://testserver"}
    ).status_code == 204
    assert favorites.export_account_favorites("alice@example.com")["exists"] is True

    monkeypatch.setattr(
        auth.AuthStore, "delete_account_data",
        lambda _self, _email: (_ for _ in ()).throw(OSError("simulated failure")),
    )
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 500
    snapshot = favorites.export_account_favorites("alice@example.com")
    assert snapshot["exists"] is True
    assert snapshot["tickers"] == []


def test_old_sqlite_schema_migrates_without_losing_user(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE auth_users(email TEXT PRIMARY KEY,tier TEXT NOT NULL,created_at TEXT NOT NULL);
            INSERT INTO auth_users VALUES('old@example.com','free','2026-07-01T00:00:00+00:00');
            CREATE TABLE revoked_sessions(jti TEXT PRIMARY KEY,revoked_at TEXT NOT NULL);
            CREATE TABLE account_deletion_epochs(email TEXT PRIMARY KEY,deleted_at TEXT NOT NULL);
            INSERT INTO account_deletion_epochs VALUES('deleted@example.com','2026-07-01T00:00:00+00:00');
        """)
    store = auth.AuthStore(path)
    user = store.user("old@example.com")
    assert user and len(user["session_generation"]) == 32
    with sqlite3.connect(path) as conn:
        assert "email" in {row[1] for row in conn.execute("PRAGMA table_info(revoked_sessions)")}
        columns = {row[1] for row in conn.execute("PRAGMA table_info(account_deletion_epochs)")}
        assert columns == {"owner_hash", "deleted_at"}
        assert conn.execute("SELECT COUNT(*) FROM account_deletion_epochs").fetchone()[0] == 1
        assert "deleted@example.com" not in path.read_bytes().decode("utf-8", errors="ignore")


def test_delete_blocks_concurrent_predeletion_magic_link(client, monkeypatch):
    _login(client)
    store = auth._store()
    raw_token = "predeletion-magic-token-1234567890"
    created_at = "2026-07-12T00:00:00+00:00"
    store.add_token(
        auth._token_hash(raw_token), "alice@example.com", created_at,
        "2099-01-01T00:00:00+00:00",
    )
    entered = threading.Event()
    release = threading.Event()
    original = auth.AuthStore.ensure_user_from_token

    result = {}

    def delayed_ensure(self, *args, **kwargs):
        entered.set()
        assert release.wait(5)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(auth.AuthStore, "ensure_user_from_token", delayed_ensure)

    def finish_login_after_delete():
        verifier = TestClient(client.app)
        result["response"] = verifier.post(
            "/api/auth/verify", json={"token": raw_token},
            headers={"Origin": "http://testserver"},
        )

    # Model the boundary after atomic token consumption but before account
    # creation: deletion must win over a credential issued before it.
    thread = threading.Thread(target=finish_login_after_delete)
    thread.start()
    assert entered.wait(5)
    deleted = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert deleted.status_code == 200
    release.set()
    thread.join(5)
    assert not thread.is_alive()
    assert result["response"].status_code == 400
    assert result["response"].json()["error"] == "invalid token"
    assert store.user("alice@example.com") is None
