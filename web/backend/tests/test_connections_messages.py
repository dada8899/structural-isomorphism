"""Integration tests for /api/connections/messages* (G-P3, Session #22).

Covers:
  1. Cannot message without prior accepted match (403 fail-closed)
  2. Happy path: send → inbox sees it → mark read flips read_at
  3. PII content filter blocks URL / phone / email
  4. Rate limit: 10/day → 11th gets 429
  5. Block + close-messages: blocking recipient or closing messages → 403
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture
def isolated_stores(tmp_path, monkeypatch):
    from services.connections_store import ConnectionsStore
    from services.connections_p3_store import ConnectionsP3Store
    from api import connections as conn_api
    from api import auth as auth_api

    db = tmp_path / "test_msg.db"
    monkeypatch.setattr(conn_api, "_store", ConnectionsStore(db))
    monkeypatch.setattr(conn_api, "_p3_store", ConnectionsP3Store(db))
    auth_api._override_data_dir_for_tests(tmp_path)
    return conn_api._store, conn_api._p3_store


@pytest.fixture
def client(isolated_stores):
    from api import connections as conn_api

    a = FastAPI()
    a.include_router(conn_api.router, prefix="/api")
    return TestClient(a)


def _cookie(email: str) -> dict:
    from api.auth import _issue_jwt, _COOKIE_NAME

    token, _ = _issue_jwt(email=email, tier="free")
    return {_COOKIE_NAME: token}


def _matched(p3, a: str, b: str) -> None:
    """Seed an accepted match between a and b directly via the store."""
    rid = p3.create_match_request(
        from_user_email=a, to_user_email=b, to_fingerprint_id="fp_seed"
    )
    assert rid is not None
    assert p3.respond_match_request(rid, b, accept=True)


# --------- gate: must be matched --------- #


def test_message_requires_prior_match(client):
    r = client.post(
        "/api/connections/messages",
        json={"to_email": "bob@x.com", "body": "hello bob"},
        cookies=_cookie("alice@x.com"),
    )
    assert r.status_code == 403


# --------- happy path --------- #


def test_send_inbox_and_read(client, isolated_stores):
    _, p3 = isolated_stores
    _matched(p3, "alice@x.com", "bob@x.com")

    alice, bob = _cookie("alice@x.com"), _cookie("bob@x.com")
    r = client.post(
        "/api/connections/messages",
        json={
            "to_email": "bob@x.com",
            "body": "hey bob, want to chat about delay-debt patterns?",
        },
        cookies=alice,
    )
    assert r.status_code == 200
    mid = r.json()["message"]["id"]
    assert r.json()["message"]["read_at"] is None

    # Bob's inbox shows it
    inbox = client.get("/api/connections/messages/inbox", cookies=bob).json()["messages"]
    assert len(inbox) == 1
    assert inbox[0]["body"].startswith("hey bob")
    assert inbox[0]["from_email"] == "alice@x.com"

    # Bob marks read
    r = client.post(f"/api/connections/messages/{mid}/read", cookies=bob)
    assert r.status_code == 200

    # Alice can't mark her own outbound as read (404 — she's not the recipient)
    r2 = client.post(f"/api/connections/messages/{mid}/read", cookies=alice)
    assert r2.status_code == 404

    # Now read_at is set
    inbox = client.get("/api/connections/messages/inbox", cookies=bob).json()["messages"]
    assert inbox[0]["read_at"] is not None


# --------- content filter --------- #


@pytest.mark.parametrize("payload,kind", [
    ("see my site https://evil.example/x", "url"),
    ("email me at bad@actor.io for details", "email"),
    ("ring me at +1 555 123 4567 tomorrow", "phone"),
])
def test_pii_filter_rejects_leaks(client, isolated_stores, payload, kind):
    _, p3 = isolated_stores
    _matched(p3, "alice@x.com", "bob@x.com")

    r = client.post(
        "/api/connections/messages",
        json={"to_email": "bob@x.com", "body": payload},
        cookies=_cookie("alice@x.com"),
    )
    assert r.status_code == 400
    assert r.json()["category"] == kind


# --------- rate limit --------- #


def test_daily_rate_limit_blocks_11th(client, isolated_stores):
    _, p3 = isolated_stores
    _matched(p3, "alice@x.com", "bob@x.com")
    alice = _cookie("alice@x.com")

    for i in range(p3.MESSAGE_DAILY_LIMIT):
        r = client.post(
            "/api/connections/messages",
            json={
                "to_email": "bob@x.com",
                "body": f"message number {i} on universality",
            },
            cookies=alice,
        )
        assert r.status_code == 200, f"msg {i} unexpectedly failed"

    # 11th → 429
    r = client.post(
        "/api/connections/messages",
        json={"to_email": "bob@x.com", "body": "one too many"},
        cookies=alice,
    )
    assert r.status_code == 429
    assert r.json()["limit"] == p3.MESSAGE_DAILY_LIMIT


# --------- block + close messages --------- #


def test_block_and_close_messages_both_403(client, isolated_stores):
    _, p3 = isolated_stores
    _matched(p3, "alice@x.com", "bob@x.com")

    alice, bob = _cookie("alice@x.com"), _cookie("bob@x.com")

    # Bob blocks Alice via PATCH /prefs
    r = client.patch(
        "/api/connections/prefs",
        json={"block_email": "alice@x.com"},
        cookies=bob,
    )
    assert r.status_code == 200
    assert "alice@x.com" in r.json()["prefs"]["blocked_emails"]

    # Alice's message → 403
    r = client.post(
        "/api/connections/messages",
        json={"to_email": "bob@x.com", "body": "still trying to reach you"},
        cookies=alice,
    )
    assert r.status_code == 403

    # Bob unblocks, then closes messages globally
    client.patch(
        "/api/connections/prefs",
        json={"unblock_email": "alice@x.com", "messages_open": False},
        cookies=bob,
    )
    r = client.post(
        "/api/connections/messages",
        json={"to_email": "bob@x.com", "body": "now closed"},
        cookies=alice,
    )
    assert r.status_code == 403
