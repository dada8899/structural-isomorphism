"""Authenticated account export/delete and registry symmetry tests."""
from __future__ import annotations

import builtins
import concurrent.futures
import hashlib
import json
import multiprocessing
import sqlite3
import sys
import threading
import time
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


def _construct_auth_store_after_barrier(path: str, barrier, results) -> None:
    """Exercise one cold-start migrator in an independent process."""
    try:
        barrier.wait(timeout=10)
        auth.AuthStore(Path(path))
    except BaseException as exc:  # pragma: no cover - asserted in parent
        results.put(f"{type(exc).__name__}: {exc}")
    else:
        results.put("ok")


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


def _research_bookmark(client: TestClient, suffix: str = "one") -> dict:
    response = client.post(
        "/api/favorites/bookmarks",
        headers={"Origin": "http://testserver"},
        json={
            "kind": "structural_analysis",
            "title": f"Research {suffix}",
            "query": f"Question {suffix}",
            "source_id": f"source-{suffix}",
            "target_id": f"target-{suffix}",
        },
    )
    assert response.status_code in {200, 201}, response.text
    return response.json()["bookmark"]


def test_registry_rejects_asymmetric_or_duplicate_assets():
    with pytest.raises(ValueError, match="export and delete"):
        AccountDataRegistry([AccountAsset("bad", "email", "forever", None, lambda _: None)])  # type: ignore[arg-type]
    asset = AccountAsset("same", "email", "until delete", lambda _: {}, lambda _: {})
    with pytest.raises(ValueError, match="unique"):
        AccountDataRegistry([asset, asset])
    with pytest.raises(ValueError, match="snapshot must be callable"):
        AccountDataRegistry([AccountAsset(
            "bad-snapshot", "email", "until delete", lambda _: {}, lambda _: {},
            snapshot="not-callable",  # type: ignore[arg-type]
        )])


def test_registry_uses_private_snapshot_for_delete_compensation():
    restored: list[object] = []
    raw_snapshot = {"opaque": [{"schema_version": "future-v9"}, 7]}
    first = AccountAsset(
        "first", "email", "until delete",
        export=lambda _owner: {"public": []},
        delete=lambda _owner: {"records": 1},
        restore=lambda _owner, snapshot, _result: restored.append(snapshot),
        snapshot=lambda _owner: raw_snapshot,
    )
    failing = AccountAsset(
        "failing", "email", "until delete",
        export=lambda _owner: {},
        delete=lambda _owner: (_ for _ in ()).throw(OSError("late failure")),
    )
    registry = AccountDataRegistry([first, failing])

    assert registry.export_all("alice@example.com") == {
        "first": {"public": []}, "failing": {},
    }
    with pytest.raises(OSError, match="late failure"):
        registry.delete_all("alice@example.com")
    assert restored == [raw_snapshot]


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
    bookmark = _research_bookmark(client)
    response = client.get("/api/me/export")
    assert response.json()["data"]["favorites"]["tickers"] == ["AAPL"]
    assert response.json()["data"]["favorites"]["bookmarks"] == [bookmark]
    assert response.json()["data"]["favorites"]["schema_version"] == "favorites-v2"
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
    _research_bookmark(client)
    response = client.post(
        "/api/me/delete",
        json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["removed"]["favorites"] == {
        "records": 1, "tickers": 1, "bookmarks": 1,
    }
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

    audit_text = (tmp_path / "account_deletion_audit.jsonl").read_text()
    audit = json.loads(audit_text.strip())
    assert "email" not in audit
    assert "alice@example.com" not in audit_text
    assert len(audit["owner_hash"]) == 16
    assert audit["owner_hash"] != hashlib.sha256(b"alice@example.com").hexdigest()[:16]


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
    bookmark = _research_bookmark(client, "rollback")
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
    restored_favorites = client.get("/api/favorites").json()
    assert restored_favorites["tickers"] == ["AAPL"]
    assert any(
        item["bookmark_id"] == bookmark["bookmark_id"]
        and item["kind"] == "structural_analysis"
        for item in restored_favorites["bookmarks"]
    )
    assert len(report_account._store.list_by_owner(subject)) == 1
    assert sso.SsoReplayStore(
        sso._data_dir() / "sso_replay.sqlite3"
    ).subject_revoked_at(subject) is None


def test_successful_delete_serializes_predeletion_favorite_write(
    client, monkeypatch,
):
    token = _login(client)
    _favorite(client, "AAPL")
    reached_later_asset = threading.Event()
    release_delete = threading.Event()
    original_delete_reports = report_account.delete_account_reports

    def blocked_delete_reports(owner: str):
        reached_later_asset.set()
        assert release_delete.wait(5)
        return original_delete_reports(owner)

    monkeypatch.setattr(
        report_account, "delete_account_reports", blocked_delete_reports
    )
    delete_result: dict[str, object] = {}
    mutation_result: dict[str, object] = {}

    def delete_account():
        delete_result["response"] = client.post(
            "/api/me/delete", json={"confirmation": "DELETE"},
            headers={"Origin": "http://testserver"},
        )

    def write_with_predeletion_session(writer: TestClient):
        try:
            mutation_result["response"] = writer.post(
                "/api/favorites/TSLA",
                headers={"Origin": "http://testserver"},
            )
        except Exception as exc:
            # This focused fixture does not install the production RFC 7807
            # handler, so TestClient surfaces the intended 401 exception.
            mutation_result["exception"] = exc

    with TestClient(client.app) as writer:
        writer.cookies.set("phase_session", token)
        deleting = threading.Thread(target=delete_account)
        deleting.start()
        assert reached_later_asset.wait(5)

        writing = threading.Thread(
            target=write_with_predeletion_session, args=(writer,)
        )
        writing.start()
        writing.join(0.1)
        assert writing.is_alive(), "same-owner mutation escaped account transaction gate"

        release_delete.set()
        deleting.join(5)
        writing.join(5)
        assert not deleting.is_alive() and not writing.is_alive()
        assert delete_result["response"].status_code == 200  # type: ignore[union-attr]
        assert getattr(mutation_result.get("exception"), "status", None) == 401
        assert "response" not in mutation_result
        assert writer.get("/api/auth/me").status_code == 401

    path = favorites._data_file()
    assert not path.exists() or path.read_text(encoding="utf-8").strip() == ""


def test_failed_delete_releases_gate_after_raw_restore_then_write_succeeds(
    client, monkeypatch,
):
    token = _login(client)
    _favorite(client, "AAPL")
    reached_favorites_delete = threading.Event()
    release_delete = threading.Event()
    original_delete_favorites = favorites.delete_account_favorites

    def blocked_delete_favorites(owner: str):
        reached_favorites_delete.set()
        assert release_delete.wait(5)
        return original_delete_favorites(owner)

    monkeypatch.setattr(
        favorites, "delete_account_favorites", blocked_delete_favorites
    )
    monkeypatch.setattr(
        auth.AuthStore, "delete_account_data",
        lambda _self, _email: (_ for _ in ()).throw(OSError("late failure")),
    )
    delete_result: dict[str, object] = {}
    mutation_result: dict[str, object] = {}

    def delete_account():
        delete_result["response"] = client.post(
            "/api/me/delete", json={"confirmation": "DELETE"},
            headers={"Origin": "http://testserver"},
        )

    with TestClient(client.app) as writer:
        writer.cookies.set("phase_session", token)
        deleting = threading.Thread(target=delete_account)
        deleting.start()
        assert reached_favorites_delete.wait(5)

        writing = threading.Thread(target=lambda: mutation_result.setdefault(
            "response", writer.post(
                "/api/favorites/TSLA",
                headers={"Origin": "http://testserver"},
            ),
        ))
        writing.start()
        writing.join(0.1)
        assert writing.is_alive(), "mutation raced snapshot/delete compensation"

        release_delete.set()
        deleting.join(5)
        writing.join(5)
        assert not deleting.is_alive() and not writing.is_alive()
        assert delete_result["response"].status_code == 500  # type: ignore[union-attr]
        assert mutation_result["response"].status_code == 201  # type: ignore[union-attr]
        assert writer.get("/api/favorites").json()["tickers"] == ["AAPL", "TSLA"]
        assert writer.get("/api/auth/me").status_code == 200


def test_delete_retires_queued_legacy_api_key_but_allows_rotated_key(
    client, monkeypatch,
):
    _login(client)
    _favorite(client, "AAPL")
    active_key = {
        "value": favorites.APIKey(
            key="queued-key",
            tier="free",
            owner_email="alice@example.com",
            # Deliberately future-dated: the queued-request generation check,
            # not only timestamp retirement, must still reject it.
            created_at="2099-01-01T00:00:00Z",
            revoked=False,
        )
    }
    client.app.dependency_overrides[favorites.verify_api_key] = (
        lambda: active_key["value"]
    )
    reached_later_asset = threading.Event()
    release_delete = threading.Event()
    original_delete_reports = report_account.delete_account_reports

    def blocked_delete_reports(owner: str):
        reached_later_asset.set()
        assert release_delete.wait(5)
        return original_delete_reports(owner)

    monkeypatch.setattr(
        report_account, "delete_account_reports", blocked_delete_reports
    )
    delete_result: dict[str, object] = {}
    mutation_result: dict[str, object] = {}

    def delete_account():
        delete_result["response"] = client.post(
            "/api/me/delete", json={"confirmation": "DELETE"},
            headers={"Origin": "http://testserver"},
        )

    def write_with_key(writer: TestClient):
        try:
            mutation_result["response"] = writer.post("/api/favorites/TSLA")
        except Exception as exc:
            mutation_result["exception"] = exc

    with TestClient(client.app) as writer:
        deleting = threading.Thread(target=delete_account)
        deleting.start()
        assert reached_later_asset.wait(5)
        writing = threading.Thread(target=write_with_key, args=(writer,))
        writing.start()
        writing.join(0.1)
        assert writing.is_alive(), "legacy API key escaped owner transaction gate"

        release_delete.set()
        deleting.join(5)
        writing.join(5)
        assert not deleting.is_alive() and not writing.is_alive()
        assert delete_result["response"].status_code == 200  # type: ignore[union-attr]
        assert getattr(mutation_result.get("exception"), "status", None) == 401
        assert "response" not in mutation_result
        assert auth.api_key_retired_by_account_deletion(
            "alice@example.com", "2000-01-01T00:00:00Z",
        )
        assert auth.api_key_retired_by_account_deletion(
            "alice@example.com", "not-a-timestamp",
        )
        assert not auth.api_key_retired_by_account_deletion(
            "alice@example.com", active_key["value"].created_at,
        )

        # A post-deletion rotation is an explicit new standalone credential,
        # not a stale request selected before the deletion transaction.
        active_key["value"] = favorites.APIKey(
            key="rotated-key",
            tier="free",
            owner_email="alice@example.com",
            created_at="2100-01-01T00:00:00Z",
            revoked=False,
        )
        assert not auth.api_key_retired_by_account_deletion(
            "alice@example.com", active_key["value"].created_at,
        )
        assert writer.post("/api/favorites/NVDA").status_code == 201


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
    assert snapshot["bookmarks"] == []


def test_account_delete_storage_read_failure_is_503_and_changes_nothing(
    client, monkeypatch, tmp_path, caplog,
):
    _login(client)
    _favorite(client, "AAPL")
    path = favorites._data_file()
    original = path.read_bytes()
    caplog.clear()
    real_open = builtins.open

    def fail_target_open(candidate, *args, **kwargs):
        if Path(candidate) == path:
            raise OSError("simulated favorites read failure")
        return real_open(candidate, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fail_target_open)
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 503
    assert path.read_bytes() == original
    assert not (tmp_path / "account_deletion_audit.jsonl").exists()
    assert "alice@example.com" not in caplog.text
    assert "AAPL" not in caplog.text
    assert client.get("/api/auth/me").status_code == 200


def test_account_delete_replace_failure_preserves_assets_and_owner(
    client, monkeypatch, tmp_path,
):
    _login(client)
    _favorite(client, "AAPL")
    bookmark = _research_bookmark(client, "replace-failure")
    path = favorites._data_file()
    original = path.read_bytes()
    monkeypatch.setattr(
        favorites.os, "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("simulated replace failure")),
    )
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 503
    assert path.read_bytes() == original
    assert client.get("/api/auth/me").status_code == 200
    assert not (tmp_path / "account_deletion_audit.jsonl").exists()
    assert bookmark["bookmark_id"].encode() in original
    assert list(path.parent.glob(".favorites-*.jsonl.tmp")) == []


def test_late_failure_rollback_preserves_mixed_legacy_tickers(client, monkeypatch):
    _login(client)
    _favorite(client, "AAPL")
    path = favorites._data_file()
    record = json.loads(path.read_text(encoding="utf-8"))
    mixed = ["AAPL", {"raw": 1}, ["nested"], 7, "bad ticker", "AAPL"]
    record["tickers"] = mixed
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    # Public account export projects only current canonical values; the
    # private compensation snapshot still retains every raw storage value.
    assert client.get("/api/me/export").json()["data"]["favorites"]["tickers"] == [
        "AAPL"
    ]
    assert favorites.snapshot_account_favorites(
        "alice@example.com"
    )["record"]["tickers"] == mixed

    monkeypatch.setattr(
        auth.AuthStore, "delete_account_data",
        lambda _self, _email: (_ for _ in ()).throw(OSError("late failure")),
    )
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 500
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored["tickers"] == mixed
    assert client.get("/api/auth/me").status_code == 200


def test_export_projects_and_delete_rollback_restores_opaque_bookmarks(
    client, monkeypatch,
):
    _login(client)
    known = _research_bookmark(client, "opaque-rollback")
    path = favorites._data_file()
    record = json.loads(path.read_text(encoding="utf-8"))
    opaque = [
        {
            "schema_version": "bookmark-v9",
            "bookmark_id": known["bookmark_id"],
            "kind": "structural_analysis",
            "title": "Future collision",
            "query": "future",
            "source_id": None,
            "target_id": "future-target",
            "future": {"nested": [1, 2]},
        },
        {
            "schema_version": "bookmark-v1",
            "kind": "structural_analysis",
            "title": "<script>hidden</script>",
            "query": "malformed",
            "source_id": None,
            "target_id": "target",
        },
        {"legacy": ["raw", 3]},
        ["array"],
        11,
        None,
    ]
    record["bookmarks"] = [*opaque, *record["bookmarks"]]
    record["future_envelope"] = {"version": 9, "raw": [True, None]}
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    exported = client.get("/api/me/export")
    assert exported.status_code == 200
    public_favorites = exported.json()["data"]["favorites"]
    assert public_favorites["bookmarks"] == [known]
    assert "Future collision" not in exported.text
    assert favorites.snapshot_account_favorites(
        "alice@example.com"
    )["record"]["bookmarks"] == [*opaque, known]

    monkeypatch.setattr(
        auth.AuthStore, "delete_account_data",
        lambda _self, _email: (_ for _ in ()).throw(OSError("late failure")),
    )
    response = client.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://testserver"},
    )
    assert response.status_code == 500
    restored = json.loads(path.read_text(encoding="utf-8"))
    assert restored == record
    assert restored["bookmarks"] == [*opaque, known]
    assert client.get("/api/favorites").json()["bookmarks"] == [known]
    assert client.get("/api/auth/me").status_code == 200


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


@pytest.mark.parametrize("_round", range(5))
def test_old_sqlite_schema_migrates_once_across_concurrent_processes(
    tmp_path, _round,
):
    try:
        process_context = multiprocessing.get_context("fork")
    except ValueError:
        pytest.skip("requires a POSIX fork context")

    path = tmp_path / "legacy-concurrent.sqlite3"
    with sqlite3.connect(path) as conn:
        conn.executescript("""
            CREATE TABLE auth_users(email TEXT PRIMARY KEY,tier TEXT NOT NULL,created_at TEXT NOT NULL);
            INSERT INTO auth_users VALUES('old@example.com','free','2026-07-01T00:00:00+00:00');
            CREATE TABLE revoked_sessions(jti TEXT PRIMARY KEY,revoked_at TEXT NOT NULL);
            CREATE TABLE account_deletion_epochs(email TEXT PRIMARY KEY,deleted_at TEXT NOT NULL);
            INSERT INTO account_deletion_epochs VALUES('deleted@example.com','2026-07-01T00:00:00+00:00');
        """)

    process_count = 16
    barrier = process_context.Barrier(process_count + 1)
    results = process_context.Queue()
    processes = [
        process_context.Process(
            target=_construct_auth_store_after_barrier,
            args=(str(path), barrier, results),
        )
        for _index in range(process_count)
    ]
    try:
        for process in processes:
            process.start()
        barrier.wait(timeout=10)
        messages = [results.get(timeout=20) for _process in processes]
        for process in processes:
            process.join(timeout=20)
        assert messages == ["ok"] * process_count
        assert all(process.exitcode == 0 for process in processes)
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        results.close()
        results.join_thread()

    store = auth.AuthStore(path)
    user = store.user("old@example.com")
    assert user and len(user["session_generation"]) == 32
    with sqlite3.connect(path) as conn:
        assert "email" in {
            row[1] for row in conn.execute("PRAGMA table_info(revoked_sessions)")
        }
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(account_deletion_epochs)")
        }
        assert columns == {"owner_hash", "deleted_at"}
        assert conn.execute(
            "SELECT COUNT(*) FROM account_deletion_epochs"
        ).fetchone()[0] == 1


def test_auth_store_concurrent_construction_keeps_wal_available(tmp_path):
    path = tmp_path / "concurrent.sqlite3"

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        stores = list(executor.map(lambda _index: auth.AuthStore(path), range(30)))

    assert len(stores) == 30
    assert all(store.user("missing@example.com") is None for store in stores)
    with sqlite3.connect(path) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_auth_store_rejects_non_wal_database_without_retrying():
    started_at = time.monotonic()
    with pytest.raises(RuntimeError, match="refused WAL journal mode: memory"):
        auth.AuthStore(Path(":memory:"))
    assert time.monotonic() - started_at < 2


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
