"""Integration tests for /api/connections/* (G-MVP, Session #19).

FastAPI TestClient against a focused sub-app. Auth: we mint a real
magic-link JWT via api.auth._issue_jwt and set it as the session cookie,
so the connections router's _current_user_email() resolves it the same
way prod does.

SearchService is NOT loaded — _encode_problem degrades to None embeddings.
That exercises the graceful-degradation path; the matching algorithm
itself is unit-tested with real vectors in test_connections_store.py.
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


# --------- fixtures --------- #


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point api.connections._store at a fresh DB + isolate auth data dir."""
    from services.connections_store import ConnectionsStore
    from api import connections as conn_api
    from api import auth as auth_api

    fresh = ConnectionsStore(tmp_path / "test_conn.db")
    monkeypatch.setattr(conn_api, "_store", fresh)
    # Isolate auth JSONL storage (user records / revoked sessions).
    auth_api._override_data_dir_for_tests(tmp_path)
    return fresh


@pytest.fixture
def app(isolated_store):
    from api import connections as conn_api

    a = FastAPI()
    a.include_router(conn_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def _session_cookie(email: str) -> dict:
    """Mint a valid magic-link JWT for `email`, return as a cookie dict."""
    from api.auth import _issue_jwt, _COOKIE_NAME

    token, _jti = _issue_jwt(email=email, tier="free")
    return {_COOKIE_NAME: token}


# --------- auth gate --------- #


def test_create_requires_login(client):
    r = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "a problem statement"},
    )
    assert r.status_code == 401


def test_list_requires_login(client):
    assert client.get("/api/connections/fingerprints").status_code == 401


# --------- fingerprint lifecycle --------- #


def test_create_and_list_fingerprint(client):
    cookies = _session_cookie("alice@x.com")
    r = client.post(
        "/api/connections/fingerprints",
        json={
            "problem_summary": "30 人公司的效率塌陷",
            "domain": "organization",
            "universality_class": "delay-debt",
        },
        cookies=cookies,
    )
    assert r.status_code == 200
    fp = r.json()["fingerprint"]
    assert fp["problem_summary"] == "30 人公司的效率塌陷"
    # 默认 L0（私密）。
    assert fp["visibility_level"] == "L0"
    # No SearchService in tests → embedding absent (graceful degrade).
    assert fp["has_embedding"] is False

    r2 = client.get("/api/connections/fingerprints", cookies=cookies)
    assert r2.status_code == 200
    assert len(r2.json()["fingerprints"]) == 1


def test_create_rejects_too_short_summary(client):
    r = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "ab"},  # < 4 chars → 422
        cookies=_session_cookie("alice@x.com"),
    )
    assert r.status_code == 422


def test_create_rejects_bad_visibility(client):
    r = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "valid problem", "visibility_level": "PUBLIC"},
        cookies=_session_cookie("alice@x.com"),
    )
    assert r.status_code == 400


def test_users_only_see_own_fingerprints(client):
    client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem one"},
        cookies=_session_cookie("alice@x.com"),
    )
    r = client.get(
        "/api/connections/fingerprints", cookies=_session_cookie("bob@x.com")
    )
    assert r.status_code == 200
    assert r.json()["fingerprints"] == []


# --------- visibility patch --------- #


def test_patch_visibility_opt_in(client):
    cookies = _session_cookie("alice@x.com")
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem"},
        cookies=cookies,
    ).json()["fingerprint"]["id"]

    r = client.patch(
        f"/api/connections/fingerprints/{fid}",
        json={"visibility_level": "L1"},
        cookies=cookies,
    )
    assert r.status_code == 200
    assert r.json()["fingerprint"]["visibility_level"] == "L1"


def test_patch_visibility_owner_only(client):
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem"},
        cookies=_session_cookie("alice@x.com"),
    ).json()["fingerprint"]["id"]

    # Bob can't flip Alice's fingerprint — 404 (no existence leak).
    r = client.patch(
        f"/api/connections/fingerprints/{fid}",
        json={"visibility_level": "L2"},
        cookies=_session_cookie("bob@x.com"),
    )
    assert r.status_code == 404


def test_patch_visibility_rejects_bad_level(client):
    cookies = _session_cookie("alice@x.com")
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem"},
        cookies=cookies,
    ).json()["fingerprint"]["id"]
    r = client.patch(
        f"/api/connections/fingerprints/{fid}",
        json={"visibility_level": "L99"},
        cookies=cookies,
    )
    assert r.status_code == 400


# --------- delete --------- #


def test_delete_fingerprint_owner_only(client):
    cookies = _session_cookie("alice@x.com")
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem"},
        cookies=cookies,
    ).json()["fingerprint"]["id"]

    # Bob can't delete.
    assert client.delete(
        f"/api/connections/fingerprints/{fid}",
        cookies=_session_cookie("bob@x.com"),
    ).status_code == 404
    # Alice can.
    assert client.delete(
        f"/api/connections/fingerprints/{fid}", cookies=cookies
    ).status_code == 200
    # Gone.
    assert client.get(
        "/api/connections/fingerprints", cookies=cookies
    ).json()["fingerprints"] == []


# --------- neighbors --------- #


def test_neighbors_owner_only(client):
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem"},
        cookies=_session_cookie("alice@x.com"),
    ).json()["fingerprint"]["id"]
    r = client.get(
        f"/api/connections/fingerprints/{fid}/neighbors",
        cookies=_session_cookie("bob@x.com"),
    )
    assert r.status_code == 404


def test_neighbors_no_embedding_returns_zero(client):
    """No SearchService → no embeddings → 0 neighbors, no crash."""
    cookies = _session_cookie("alice@x.com")
    fid = client.post(
        "/api/connections/fingerprints",
        json={"problem_summary": "alice problem", "domain": "organization"},
        cookies=cookies,
    ).json()["fingerprint"]["id"]
    r = client.get(
        f"/api/connections/fingerprints/{fid}/neighbors", cookies=cookies
    )
    assert r.status_code == 200
    body = r.json()
    assert body["neighbor_count"] == 0
    assert body["neighbors"] == []


def test_neighbors_response_hides_identity(client, isolated_store):
    """Even with matches, the neighbors payload must not leak user_email.

    We seed a discoverable match directly in the store with real vectors
    so the matcher actually returns a hit.
    """
    import numpy as np
    from services.connections_match import encode_to_blob

    base = np.random.default_rng(42).standard_normal(16).astype("<f4")
    # Alice's own fingerprint (L0, organization domain).
    alice_fid = isolated_store.create_fingerprint(
        user_email="alice@x.com",
        problem_summary="alice org problem",
        embedding=encode_to_blob(base),
        domain="organization",
        universality_class="delay-debt",
        visibility_level="L0",
    )
    # Bob's discoverable cross-domain fingerprint, near-identical vector.
    isolated_store.create_fingerprint(
        user_email="bob@x.com",
        problem_summary="bob ecology problem",
        embedding=encode_to_blob(base + 0.0001),
        domain="ecology",
        universality_class="delay-debt",
        visibility_level="L1",
    )

    r = client.get(
        f"/api/connections/fingerprints/{alice_fid}/neighbors",
        cookies=_session_cookie("alice@x.com"),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["neighbor_count"] == 1
    n = body["neighbors"][0]
    # Identity must be stripped — L1 is "N people", not "who".
    assert "user_email" not in n
    assert "fingerprint_id" not in n
    assert n["problem_summary"] == "bob ecology problem"
    assert n["domain"] == "ecology"
