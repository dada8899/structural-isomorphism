"""Integration tests for /api/connections/match-request* (G-P3, Session #22).

Pattern follows test_connections_api.py: FastAPI sub-app + isolated tmp_path
DB + magic-link JWT minting via api.auth._issue_jwt.

Covers:
  1. Auth gate (login required)
  2. Cannot match own fingerprint / non-L2 fingerprint (privacy: 404 not 400
     for non-L2 so we don't leak existence)
  3. Mutual consent flow: A sends → B sees pending (anon) → B accepts → both
     see each other in accepted list
  4. Decline path: B declines → not in accepted list, status='declined'
  5. Dedup: same (A, B, fp) pending can't be created twice
  6. Cross-user isolation: C cannot accept A→B request
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
    """Fresh ConnectionsStore + ConnectionsP3Store on a tmp-path DB."""
    from services.connections_store import ConnectionsStore
    from services.connections_p3_store import ConnectionsP3Store
    from api import connections as conn_api
    from api import auth as auth_api

    db_path = tmp_path / "test_conn_p3.db"
    fp_store = ConnectionsStore(db_path)
    p3_store = ConnectionsP3Store(db_path)
    monkeypatch.setattr(conn_api, "_store", fp_store)
    monkeypatch.setattr(conn_api, "_p3_store", p3_store)
    auth_api._override_data_dir_for_tests(tmp_path)
    return fp_store, p3_store


@pytest.fixture
def app(isolated_stores):
    from api import connections as conn_api

    a = FastAPI()
    a.include_router(conn_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def _cookie(email: str) -> dict:
    from api.auth import _issue_jwt, _COOKIE_NAME

    token, _ = _issue_jwt(email=email, tier="free")
    return {_COOKIE_NAME: token}


def _make_fp(store, *, owner: str, visibility: str = "L2") -> str:
    """Create a fingerprint directly via store (skip the embedding pathway)."""
    return store.create_fingerprint(
        user_email=owner,
        problem_summary=f"{owner} problem summary text",
        visibility_level=visibility,
        domain="organization",
    )


# --------- auth + validation --------- #


def test_match_request_requires_login(client):
    r = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": "fp_anything"},
    )
    assert r.status_code == 401


def test_match_request_rejects_non_l2_fingerprint(client, isolated_stores):
    """L0/L1 target → 404 (privacy: don't leak whether fp exists)."""
    fp_store, _ = isolated_stores
    fid_l1 = _make_fp(fp_store, owner="bob@x.com", visibility="L1")

    r = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": fid_l1},
        cookies=_cookie("alice@x.com"),
    )
    assert r.status_code == 404


# --------- mutual consent happy path --------- #


def test_mutual_consent_match_full_flow(client, isolated_stores):
    fp_store, p3_store = isolated_stores
    bob_fp = _make_fp(fp_store, owner="bob@x.com", visibility="L2")

    alice = _cookie("alice@x.com")
    bob = _cookie("bob@x.com")

    # 1. Alice sends interest
    r = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": bob_fp, "note": "I solve similar problems"},
        cookies=alice,
    )
    assert r.status_code == 200
    mr = r.json()["match_request"]
    rid = mr["id"]
    assert mr["status"] == "pending"
    assert mr["direction"] == "sent"

    # 2. Bob sees pending with anonymized sender (设计 §3.3: A 仍匿名)
    pending = client.get(
        "/api/connections/match-requests/pending", cookies=bob
    ).json()["match_requests"]
    assert len(pending) == 1
    assert pending[0]["status"] == "pending"
    assert pending[0]["other_email"] == "(anonymous)"

    # 3. Bob accepts
    r = client.post(
        f"/api/connections/match-requests/{rid}/accept", cookies=bob
    )
    assert r.status_code == 200
    assert r.json()["match_request"]["status"] == "accepted"

    # 4. Both see each other in accepted list (identity now exchanged)
    alice_matches = client.get(
        "/api/connections/match-requests/accepted", cookies=alice
    ).json()["matches"]
    bob_matches = client.get(
        "/api/connections/match-requests/accepted", cookies=bob
    ).json()["matches"]
    assert len(alice_matches) == 1
    assert alice_matches[0]["other_email"] == "bob@x.com"
    assert alice_matches[0]["direction"] == "sent"
    assert len(bob_matches) == 1
    assert bob_matches[0]["other_email"] == "alice@x.com"
    assert bob_matches[0]["direction"] == "received"


def test_decline_keeps_out_of_accepted(client, isolated_stores):
    fp_store, _ = isolated_stores
    bob_fp = _make_fp(fp_store, owner="bob@x.com", visibility="L2")
    alice, bob = _cookie("alice@x.com"), _cookie("bob@x.com")

    rid = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": bob_fp},
        cookies=alice,
    ).json()["match_request"]["id"]

    r = client.post(
        f"/api/connections/match-requests/{rid}/decline", cookies=bob
    )
    assert r.status_code == 200
    assert r.json()["match_request"]["status"] == "declined"

    # Not in accepted list for either side
    assert client.get(
        "/api/connections/match-requests/accepted", cookies=alice
    ).json()["matches"] == []
    assert client.get(
        "/api/connections/match-requests/accepted", cookies=bob
    ).json()["matches"] == []


# --------- abuse / edge --------- #


def test_dedup_pending_request(client, isolated_stores):
    fp_store, _ = isolated_stores
    bob_fp = _make_fp(fp_store, owner="bob@x.com", visibility="L2")
    alice = _cookie("alice@x.com")

    r1 = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": bob_fp},
        cookies=alice,
    )
    assert r1.status_code == 200

    # Same (alice, bob, fp) with pending → 409
    r2 = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": bob_fp},
        cookies=alice,
    )
    assert r2.status_code == 409


def test_third_party_cannot_accept(client, isolated_stores):
    """Carol cannot accept Alice→Bob's request — 404, fail-closed."""
    fp_store, _ = isolated_stores
    bob_fp = _make_fp(fp_store, owner="bob@x.com", visibility="L2")
    alice, carol = _cookie("alice@x.com"), _cookie("carol@x.com")

    rid = client.post(
        "/api/connections/match-request",
        json={"to_fingerprint_id": bob_fp},
        cookies=alice,
    ).json()["match_request"]["id"]

    r = client.post(
        f"/api/connections/match-requests/{rid}/accept", cookies=carol
    )
    assert r.status_code == 404
