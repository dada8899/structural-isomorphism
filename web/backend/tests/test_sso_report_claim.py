"""Cross-domain SSO and anonymous report claim security contracts."""
from __future__ import annotations

import time
import concurrent.futures
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth, report_account, sso
from services.report_store import ReportStore


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "true")
    monkeypatch.setenv("AUTH_DATA_DIR", str(tmp_path / "auth"))
    monkeypatch.setenv("JWT_SECRET", "unit-auth-secret-with-at-least-32-characters")
    monkeypatch.setenv("AUTH_LINK_BASE_URL", "http://phase.test")
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "unit-sso-secret-with-at-least-32-characters")
    monkeypatch.setenv("STRUCTURAL_SSO_PHASE_ORIGIN", "http://phase.test")
    monkeypatch.setenv("STRUCTURAL_SSO_BETA_ORIGIN", "http://beta.test")
    auth._override_data_dir_for_tests(tmp_path / "auth")
    report_account._store = ReportStore(tmp_path / "history.db")
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(sso.router, prefix="/api")
    app.include_router(report_account.router, prefix="/api")
    yield app, report_account._store
    report_account._store = None


def phase_login(client: TestClient, email: str = "owner@example.com") -> None:
    auth._ensure_user(email)
    token, _ = auth._issue_jwt(email, "free")
    client.cookies.set("phase_session", token)


def exchange_session(app: FastAPI):
    beta = TestClient(app, base_url="http://beta.test")
    phase = TestClient(app, base_url="http://phase.test")
    phase_login(phase)
    started = beta.get(
        "/api/sso/start", headers={"Origin": "http://beta.test"}, follow_redirects=False,
    )
    assert started.status_code == 303
    query = parse_qs(urlsplit(started.headers["location"]).query)
    issued = phase.post(
        "/api/sso/issue", headers={"Origin": "http://phase.test"},
        json={"audience": "structural-beta", "state": query["state"][0], "nonce": query["nonce"][0]},
    )
    assert issued.status_code == 200
    binding = beta.cookies.get("structural_sso_state")
    return beta, issued.json()["code"], query["state"][0], binding


def test_code_is_state_nonce_audience_bound_and_single_use(stack):
    app, _ = stack
    beta, code, state, binding = exchange_session(app)
    public_claims = jwt.decode(
        code, options={"verify_signature": False}, algorithms=["HS256"]
    )
    assert "sub" not in public_claims and "tier" not in public_claims
    replay = TestClient(app, base_url="http://beta.test")
    replay.cookies.set("structural_sso_state", binding)

    wrong_state = beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": "x" * 43},
    )
    assert wrong_state.status_code == 400
    exchanged = beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    )
    assert exchanged.status_code == 200
    assert beta.cookies.get("structural_beta_session")
    replayed = replay.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    )
    assert replayed.status_code == 409


def test_expired_code_and_cross_site_mutations_fail_closed(stack):
    app, _ = stack
    beta, _, state, _ = exchange_session(app)
    now = int(time.time())
    expired = jwt.encode(
        {"iss": "http://phase.test", "aud": "structural-beta", "sub": "u",
         "tier": "free", "state": state,
         "nonce": "n" * 43, "jti": "expired", "iat": now - 300, "exp": now - 1},
        sso._secret(), algorithm="HS256",
    )
    assert beta.post(
        "/api/sso/exchange", headers={"Origin": "http://evil.test"},
        json={"code": expired, "state": state},
    ).status_code == 403
    assert beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": expired, "state": state},
    ).status_code == 400


def test_claim_uses_anon_proof_not_share_token_and_restores_cross_device(stack):
    app, store = stack
    owned = store.create(
        query="owned", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="anon-current-browser",
    )
    store.create(
        query="other", b_id="b2", lang="zh", payload={}, model="m",
        creator_anon_id="anon-other-browser",
    )
    beta, code, state, _ = exchange_session(app)
    assert beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    ).status_code == 200
    assert beta.post(
        "/api/reports/anon-proof", headers={"X-Anon-Id": "anon-current-browser", "Origin": "http://beta.test"},
    ).status_code == 200
    claimed = beta.post(
        "/api/me/reports/claim", headers={"Origin": "http://beta.test"},
        json={"share_token": owned["share_token"]},
    )
    # The endpoint has no body contract: a public share token cannot prove
    # ownership and is ignored. Only the HttpOnly anon proof is used.
    assert claimed.status_code == 200
    assert claimed.json()["claimed"] == 1

    other_device = TestClient(app, base_url="http://beta.test")
    other_device.cookies.set(
        "structural_beta_session", beta.cookies.get("structural_beta_session"),
    )
    reports = other_device.get("/api/me/reports")
    assert reports.status_code == 200
    assert [item["id"] for item in reports.json()["items"]] == [owned["id"]]
    assert reports.json()["items"][0]["share_token"] == owned["share_token"]
    assert other_device.post("/api/me/reports/claim").status_code == 403


def test_claim_is_idempotent_and_never_transfers_existing_owner(stack):
    app, store = stack
    store.create(
        query="owned", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="anon-current-browser",
    )
    store.claim_by_anon("anon-current-browser", "another-user")
    beta, code, state, _ = exchange_session(app)
    beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    )
    beta.post("/api/reports/anon-proof", headers={"X-Anon-Id": "anon-current-browser", "Origin": "http://beta.test"})
    conflict = beta.post("/api/me/reports/claim", headers={"Origin": "http://beta.test"})
    assert conflict.status_code == 409
    assert conflict.json()["claimed"] == 0
    assert store.get_by_id(store.list_by_anon("anon-current-browser")[0]["id"])["owner_user_id"] == "another-user"


def test_concurrent_claim_has_one_owner_and_no_partial_transfer(stack):
    _, store = stack
    for idx in range(8):
        store.create(
            query=f"r{idx}", b_id="b", lang="zh", payload={}, model="m",
            creator_anon_id="anon-race",
        )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda owner: store.claim_by_anon("anon-race", owner),
            ("owner-a", "owner-b"),
        ))
    owners = {
        store.get_by_id(row["id"])["owner_user_id"]
        for row in store.list_by_anon("anon-race")
    }
    assert len(owners) == 1
    assert sum(result["claimed"] for result in results) == 8
    assert sorted(result["conflicts"] for result in results) == [0, 8]


def test_production_secret_and_origins_fail_closed(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "replace-with-private-64-hex-chars")
    with pytest.raises(RuntimeError, match="high-entropy"):
        sso._secret()
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3")
    monkeypatch.setenv("STRUCTURAL_SSO_PHASE_ORIGIN", "https://evil.example")
    with pytest.raises(RuntimeError, match="canonical"):
        sso._phase_origin()
