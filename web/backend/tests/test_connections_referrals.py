"""Integration tests for /api/connections/referral* (G-P3, Session #22).

Covers:
  1. Auth + three-distinct-emails validation
  2. Happy path: X creates referral → A accepts → B accepts → completed
  3. Mute-referrals: B muted → still writes (A未 mute) but B's GET filters it out
  4. Non-party cannot accept/decline (fail-closed 404)
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

    db = tmp_path / "test_ref.db"
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


# --------- validation --------- #


def test_referral_requires_three_distinct_emails(client):
    """X cannot referral themselves as one of A/B."""
    r = client.post(
        "/api/connections/referral",
        json={
            "referee_a_email": "alice@x.com",
            "referee_b_email": "alice@x.com",  # same as A
            "reason": "duplicate",
        },
        cookies=_cookie("xavier@x.com"),
    )
    assert r.status_code == 400


# --------- happy path --------- #


def test_referral_full_double_accept_completes(client):
    xavier = _cookie("xavier@x.com")
    alice = _cookie("alice@x.com")
    bob = _cookie("bob@x.com")

    # 1. X creates referral
    r = client.post(
        "/api/connections/referral",
        json={
            "referee_a_email": "alice@x.com",
            "referee_b_email": "bob@x.com",
            "reason": "both work on delay-debt org problems",
        },
        cookies=xavier,
    )
    assert r.status_code == 200
    rid = r.json()["referral"]["id"]
    assert r.json()["referral"]["status_a"] == "pending"
    assert r.json()["referral"]["status_b"] == "pending"

    # 2. A and B both see it
    a_refs = client.get("/api/connections/referrals", cookies=alice).json()["referrals"]
    b_refs = client.get("/api/connections/referrals", cookies=bob).json()["referrals"]
    assert len(a_refs) == 1 and a_refs[0]["role"] == "referee_a"
    assert len(b_refs) == 1 and b_refs[0]["role"] == "referee_b"

    # 3. A accepts (not yet completed)
    r = client.post(f"/api/connections/referrals/{rid}/accept", cookies=alice)
    assert r.status_code == 200
    assert r.json()["completed"] is False
    assert r.json()["referral"]["status_a"] == "accepted"
    assert r.json()["referral"]["status_b"] == "pending"

    # 4. B accepts → completed_at set
    r = client.post(f"/api/connections/referrals/{rid}/accept", cookies=bob)
    assert r.status_code == 200
    assert r.json()["completed"] is True
    assert r.json()["referral"]["completed_at"] is not None

    # 5. X sees completion in their referrals list
    x_refs = client.get("/api/connections/referrals", cookies=xavier).json()["referrals"]
    assert len(x_refs) == 1
    assert x_refs[0]["role"] == "referrer"
    assert x_refs[0]["completed_at"] is not None


def test_mute_referrals_hides_from_referee_inbox(client, isolated_stores):
    """B has mute_referrals=True → referral isn't shown to B in GET /referrals.

    The row still exists (A isn't muted, so write must succeed); we just
    spare B the spam in the UI. X and A still see it normally.
    """
    _, p3 = isolated_stores
    p3.set_user_prefs("bob@x.com", mute_referrals=True)

    xavier = _cookie("xavier@x.com")
    alice = _cookie("alice@x.com")
    bob = _cookie("bob@x.com")

    r = client.post(
        "/api/connections/referral",
        json={
            "referee_a_email": "alice@x.com",
            "referee_b_email": "bob@x.com",
        },
        cookies=xavier,
    )
    assert r.status_code == 200

    # Alice (not muted) sees it
    a_refs = client.get("/api/connections/referrals", cookies=alice).json()["referrals"]
    assert len(a_refs) == 1

    # Bob (muted) → hidden as receiver. (His own muted preference filters out
    # referee rows; referrer rows would still show, but he has none here.)
    b_refs = client.get("/api/connections/referrals", cookies=bob).json()["referrals"]
    assert b_refs == []


# --------- abuse --------- #


def test_non_party_cannot_respond(client):
    """Carol (not in the referral) cannot accept Alice/Bob's referral."""
    xavier = _cookie("xavier@x.com")
    carol = _cookie("carol@x.com")

    rid = client.post(
        "/api/connections/referral",
        json={
            "referee_a_email": "alice@x.com",
            "referee_b_email": "bob@x.com",
        },
        cookies=xavier,
    ).json()["referral"]["id"]

    r = client.post(f"/api/connections/referrals/{rid}/accept", cookies=carol)
    assert r.status_code == 404
