"""Unit tests for /api/privacy/export + /api/privacy/delete — W14-C.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_privacy.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from api.privacy import export as exp_mod  # noqa: E402
from api.privacy import delete as del_mod  # noqa: E402


@pytest.fixture
def app_with_data(tmp_path, monkeypatch):
    """Boot a fresh FastAPI app with isolated data dir for each test."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    # Seed newsletter
    nl = data_dir / "newsletter-subscribers.jsonl"
    nl.write_text(
        json.dumps({"email": "alice@example.com", "source": "test", "ts": 1, "iso": "x"})
        + "\n"
        + json.dumps({"email": "bob@example.com", "source": "test", "ts": 2, "iso": "y"})
        + "\n",
        encoding="utf-8",
    )

    # Seed mock_checkouts
    ck = data_dir / "mock_checkouts.jsonl"
    ck.write_text(
        json.dumps({"email": "alice@example.com", "tier": "pro", "ts": 3, "iso": "z"})
        + "\n"
        + json.dumps({"email": "alice@example.com", "tier": "team", "ts": 4, "iso": "w"})
        + "\n",
        encoding="utf-8",
    )

    # Seed error_log
    el = data_dir / "error_log.jsonl"
    el.write_text(
        json.dumps({"message": "foo", "sessionId": "sess-1", "ts": 5})
        + "\n"
        + json.dumps({"message": "bar", "sessionId": "sess-2", "ts": 6})
        + "\n",
        encoding="utf-8",
    )

    # Monkeypatch _data_dir in both modules
    monkeypatch.setattr(exp_mod, "_data_dir", lambda: data_dir)
    monkeypatch.setattr(del_mod, "_data_dir", lambda: data_dir)

    # Reset rate-limit buckets
    exp_mod._buckets.clear()
    del_mod._buckets.clear()

    # Ensure deterministic mock code
    monkeypatch.setenv("STRUCTURAL_PRIVACY_MOCK_CODE", "123456")

    app = FastAPI()
    app.include_router(exp_mod.router, prefix="/api")
    app.include_router(del_mod.router, prefix="/api")
    return TestClient(app), data_dir


# ===========================================================================
# Export
# ===========================================================================


def test_export_returns_correct_shape(app_with_data):
    client, _ = app_with_data
    r = client.get("/api/privacy/export?email=alice@example.com&code=123456")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["email"] == "alice@example.com"
    assert "exported_at" in body
    assert "data" in body
    assert set(body["data"].keys()) == {
        "newsletter_subscribers",
        "mock_checkouts",
        "error_log",
        "search_history",
    }


def test_export_finds_user_records(app_with_data):
    client, _ = app_with_data
    r = client.get("/api/privacy/export?email=alice@example.com&code=123456")
    body = r.json()
    assert len(body["data"]["newsletter_subscribers"]) == 1
    assert len(body["data"]["mock_checkouts"]) == 2
    # No session id supplied → error_log empty even though sess-1 exists
    assert body["data"]["error_log"] == []


def test_export_with_session_id_includes_errors(app_with_data):
    client, _ = app_with_data
    r = client.get(
        "/api/privacy/export?email=alice@example.com&session_id=sess-1&code=123456"
    )
    body = r.json()
    assert len(body["data"]["error_log"]) == 1
    assert body["data"]["error_log"][0]["sessionId"] == "sess-1"


def test_export_other_users_not_leaked(app_with_data):
    """Bob's data must not appear in Alice's export."""
    client, _ = app_with_data
    r = client.get("/api/privacy/export?email=alice@example.com&code=123456")
    body = r.json()
    emails = {x["email"] for x in body["data"]["newsletter_subscribers"]}
    assert emails == {"alice@example.com"}


def test_export_missing_code_returns_401(app_with_data):
    client, _ = app_with_data
    r = client.get("/api/privacy/export?email=alice@example.com")
    assert r.status_code == 401
    assert "verification code" in r.json()["error"]


def test_export_wrong_code_returns_401(app_with_data):
    client, _ = app_with_data
    r = client.get(
        "/api/privacy/export?email=alice@example.com&code=wrongcode"
    )
    assert r.status_code == 401


def test_export_no_identifier_returns_400(app_with_data):
    client, _ = app_with_data
    r = client.get("/api/privacy/export?code=123456")
    assert r.status_code == 400


def test_export_rate_limit_kicks_in(app_with_data):
    client, _ = app_with_data
    # First request OK
    r1 = client.get("/api/privacy/export?email=alice@example.com&code=123456")
    assert r1.status_code == 200
    # Second within 1h hits limit
    r2 = client.get("/api/privacy/export?email=alice@example.com&code=123456")
    assert r2.status_code == 429
    assert r2.json()["error"] == "rate_limited"


def test_export_rate_limit_independent_per_email(app_with_data):
    """Alice hitting limit shouldn't block Bob."""
    client, _ = app_with_data
    client.get("/api/privacy/export?email=alice@example.com&code=123456")
    r = client.get("/api/privacy/export?email=bob@example.com&code=123456")
    assert r.status_code == 200


# ===========================================================================
# Delete
# ===========================================================================


def test_delete_removes_data(app_with_data):
    client, data_dir = app_with_data
    r = client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com&code=123456",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["removed"]["newsletter_subscribers"] == 1
    assert body["removed"]["mock_checkouts"] == 2

    # Confirm files no longer contain alice
    nl = (data_dir / "newsletter-subscribers.jsonl").read_text(encoding="utf-8")
    assert "alice@example.com" not in nl
    assert "bob@example.com" in nl  # bob preserved

    ck = (data_dir / "mock_checkouts.jsonl").read_text(encoding="utf-8")
    assert "alice@example.com" not in ck


def test_delete_writes_audit_entry(app_with_data):
    client, data_dir = app_with_data
    client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com&code=123456",
    )
    audit = data_dir / "privacy_audit.jsonl"
    assert audit.exists()
    entries = [json.loads(line) for line in audit.read_text().splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["event"] == "delete_requested"
    assert entries[0]["email"] == "alice@example.com"
    assert "removed_counts" in entries[0]


def test_delete_with_session_removes_errors(app_with_data):
    client, data_dir = app_with_data
    r = client.request(
        "DELETE",
        "/api/privacy/delete?session_id=sess-1&code=123456",
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["removed"]["error_log"] == 1
    # sess-2 preserved
    el = (data_dir / "error_log.jsonl").read_text(encoding="utf-8")
    assert "sess-2" in el
    assert "sess-1" not in el


def test_delete_missing_code_returns_401(app_with_data):
    client, _ = app_with_data
    r = client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com",
    )
    assert r.status_code == 401


def test_delete_wrong_code_returns_401(app_with_data):
    client, _ = app_with_data
    r = client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com&code=wrongcode",
    )
    assert r.status_code == 401


def test_delete_rate_limit_kicks_in(app_with_data):
    client, _ = app_with_data
    r1 = client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com&code=123456",
    )
    assert r1.status_code == 200
    r2 = client.request(
        "DELETE",
        "/api/privacy/delete?email=alice@example.com&code=123456",
    )
    assert r2.status_code == 429


def test_delete_nonexistent_email_still_audited(app_with_data):
    """Deleting an email that has no records should still succeed + audit
    (so an attacker can't probe "does this email exist?" via differing
    response codes)."""
    client, data_dir = app_with_data
    r = client.request(
        "DELETE",
        "/api/privacy/delete?email=ghost@example.com&code=123456",
    )
    assert r.status_code == 200
    body = r.json()
    assert body["removed"]["newsletter_subscribers"] == 0

    # Audit still written
    audit = data_dir / "privacy_audit.jsonl"
    assert audit.exists()


def test_delete_no_identifier_returns_400(app_with_data):
    client, _ = app_with_data
    r = client.request("DELETE", "/api/privacy/delete?code=123456")
    assert r.status_code == 400
