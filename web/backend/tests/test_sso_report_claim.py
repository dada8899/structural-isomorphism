"""Cross-domain SSO and anonymous report claim security contracts."""
from __future__ import annotations

import time
import concurrent.futures
import threading
from urllib.parse import parse_qs, urlsplit

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth, report, report_account, sso
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
    report._store = report_account._store
    app = FastAPI()
    app.include_router(auth.router, prefix="/api")
    app.include_router(sso.router, prefix="/api")
    app.include_router(report.router, prefix="/api")
    app.include_router(report_account.router, prefix="/api")
    yield app, report_account._store
    report_account._store = None
    report._store = None


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


def test_predeletion_exchange_code_cannot_recreate_deleted_account(stack):
    app, _ = stack
    beta, code, state, _ = exchange_session(app)
    phase = TestClient(app, base_url="http://phase.test")
    phase_login(phase)
    exported = phase.get("/api/me/export")
    assert exported.status_code == 200
    exchange_events = exported.json()["data"]["claimed_reports"][
        "sso_exchange_events"
    ]
    assert len(exchange_events) == 1
    code_jti = jwt.decode(
        code, options={"verify_signature": False}, algorithms=["HS256"],
    )["jti"]
    assert code_jti not in exported.text
    deleted = phase.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://phase.test"},
    )
    assert deleted.status_code == 200, deleted.text

    exchanged = beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    )
    assert exchanged.status_code == 409
    assert exchanged.json()["error"] in {
        "account no longer active", "exchange already used",
    }
    assert not beta.cookies.get("structural_beta_session")


def test_reregistered_binding_does_not_reactivate_predeletion_code(stack):
    app, _ = stack
    old_beta, old_code, old_state, _ = exchange_session(app)
    phase = TestClient(app, base_url="http://phase.test")
    phase_login(phase)
    assert phase.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://phase.test"},
    ).status_code == 200

    new_beta, new_code, new_state, _ = exchange_session(app)
    assert new_beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": new_code, "state": new_state},
    ).status_code == 200
    retired = old_beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": old_code, "state": old_state},
    )
    assert retired.status_code == 409


def test_failed_account_delete_restores_pending_exchange_code(
    stack, monkeypatch,
):
    app, _ = stack
    beta, code, state, _ = exchange_session(app)
    phase = TestClient(app, base_url="http://phase.test")
    phase_login(phase)
    monkeypatch.setattr(
        auth.AuthStore, "delete_account_data",
        lambda _self, _email: (_ for _ in ()).throw(OSError("late failure")),
    )
    failed = phase.post(
        "/api/me/delete", json={"confirmation": "DELETE"},
        headers={"Origin": "http://phase.test"},
    )
    assert failed.status_code == 500

    exchanged = beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    )
    assert exchanged.status_code == 200, exchanged.text
    assert beta.get("/api/me/reports").status_code == 200


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
    original_list = store.list_by_owner

    def future_store_shape(*args, **kwargs):
        rows = original_list(*args, **kwargs)
        for row in rows:
            # Regression guard: even if a future store query accidentally
            # adds a capability column, FastAPI's response model must drop it.
            row["share_token"] = owned["share_token"]
        return rows

    store.list_by_owner = future_store_shape
    reports = other_device.get("/api/me/reports")
    assert reports.status_code == 200
    assert [item["id"] for item in reports.json()["items"]] == [owned["id"]]
    item = reports.json()["items"][0]
    assert set(item) == {
        "id", "query", "b_id", "lang", "created_at", "view_count",
        "claimed_at", "has_followup", "followup_status",
        "followup_outcome", "experiment_status", "publish_to_insights",
    }
    assert "share_token" not in item
    assert reports.headers["cache-control"] == "no-store"
    assert reports.headers["pragma"] == "no-cache"
    assert other_device.post("/api/me/reports/claim").status_code == 403


def test_owner_withdraws_consent_cross_device_while_anon_requires_original_id(
    stack,
):
    app, store = stack
    owned = store.create(
        query="owned", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="origin-device",
    )
    url = f"/api/report/{owned['id']}/followup"
    origin = TestClient(app, base_url="http://beta.test")
    assert origin.post(
        url,
        headers={"X-Anon-Id": "origin-device"},
        json={
            "action_status": "tried", "outcome": "worked",
            "publish_to_insights": True,
        },
    ).status_code == 200
    assert origin.post(
        url,
        headers={"X-Anon-Id": "different-device"},
        json={
            "action_status": "tried", "outcome": "worked",
            "publish_to_insights": False,
        },
    ).status_code == 404

    beta, code, state, _ = exchange_session(app)
    assert beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    ).status_code == 200
    assert beta.post(
        "/api/reports/anon-proof",
        headers={"X-Anon-Id": "origin-device", "Origin": "http://beta.test"},
    ).status_code == 200
    assert beta.post(
        "/api/me/reports/claim", headers={"Origin": "http://beta.test"},
    ).status_code == 200

    other_device = TestClient(app, base_url="http://beta.test")
    other_device.cookies.set(
        "structural_beta_session", beta.cookies.get("structural_beta_session"),
    )
    listed = other_device.get("/api/me/reports")
    assert listed.status_code == 200
    assert listed.json()["items"][0]["publish_to_insights"] is True
    withdrawn = other_device.delete(
        f"/api/me/reports/{owned['id']}/insights-consent",
        headers={"Origin": "http://beta.test"},
    )
    assert withdrawn.status_code == 200
    assert withdrawn.headers["cache-control"] == "no-store"
    assert withdrawn.headers["pragma"] == "no-cache"
    assert withdrawn.json()["publish_to_insights"] is False
    assert withdrawn.json()["consent_version"] == "insights-public-v1"
    assert withdrawn.json()["consented_at"]
    assert withdrawn.json()["withdrawn_at"]


def test_owner_deletes_one_report_cascades_children_and_invalidates_share(stack):
    app, store = stack
    owned = store.create(
        query="delete only me", b_id="b1", lang="zh", payload={}, model="m",
        creator_anon_id="delete-origin",
    )
    store.record_feedback(
        report_id=owned["id"], section=None, vote=1, voter_anon="reader",
    )
    store.record_followup(
        report_id=owned["id"], anon_id="delete-origin",
        action_status="planned", publish_to_insights=False,
    )
    foreign = store.create(
        query="foreign", b_id="b2", lang="zh", payload={}, model="m",
        creator_anon_id="foreign-origin",
    )
    store.claim_by_anon("foreign-origin", "another-account")

    beta, code, state, _ = exchange_session(app)
    assert beta.post(
        "/api/sso/exchange", headers={"Origin": "http://beta.test"},
        json={"code": code, "state": state},
    ).status_code == 200
    assert beta.post(
        "/api/reports/anon-proof",
        headers={"X-Anon-Id": "delete-origin", "Origin": "http://beta.test"},
    ).status_code == 200
    assert beta.post(
        "/api/me/reports/claim", headers={"Origin": "http://beta.test"},
    ).status_code == 200

    cross_site = beta.delete(
        f"/api/me/reports/{owned['id']}",
        headers={"Origin": "http://evil.test"},
    )
    assert cross_site.status_code == 403
    assert store.get_by_id(owned["id"]) is not None
    denied = beta.delete(
        f"/api/me/reports/{foreign['id']}",
        headers={"Origin": "http://beta.test"},
    )
    assert denied.status_code == 404
    assert store.get_by_id(foreign["id"]) is not None

    deleted = beta.delete(
        f"/api/me/reports/{owned['id']}",
        headers={"Origin": "http://beta.test"},
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.headers["cache-control"] == "no-store"
    assert deleted.headers["pragma"] == "no-cache"
    assert deleted.json() == {
        "ok": True,
        "report_id": owned["id"],
        "reports": 1,
        "followups": 1,
        "feedback": 1,
        "share_revoked": True,
    }
    assert store.get_by_id(owned["id"]) is None
    assert beta.get(
        f"/api/report/share/{owned['share_token']}"
    ).status_code == 404
    assert all(
        item["id"] != owned["id"]
        for item in beta.get("/api/me/reports").json()["items"]
    )


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


def test_account_delete_serializes_claim_and_erases_the_newly_claimed_report(
    stack, monkeypatch,
):
    app, store = stack
    report_row = store.create(
        query="claim-delete race", b_id="b", lang="zh", payload={}, model="m",
        creator_anon_id="anon-delete-race",
    )
    auth._ensure_user("owner@example.com")
    token, _ = auth._issue_jwt("owner@example.com", "free")
    beta = TestClient(app, base_url="http://beta.test")
    phase = TestClient(app, base_url="http://phase.test")
    beta.cookies.set("phase_session", token)
    phase.cookies.set("phase_session", token)
    assert beta.post(
        "/api/reports/anon-proof",
        headers={"X-Anon-Id": "anon-delete-race", "Origin": "http://beta.test"},
    ).status_code == 200

    reached_claim_write = threading.Event()
    release_claim = threading.Event()
    original_claim = store.claim_by_anon

    def blocked_claim(anon_id: str, owner_id: str):
        reached_claim_write.set()
        assert release_claim.wait(5)
        return original_claim(anon_id, owner_id)

    monkeypatch.setattr(store, "claim_by_anon", blocked_claim)
    outcome: dict[str, object] = {}
    claiming = threading.Thread(target=lambda: outcome.setdefault(
        "claim", beta.post(
            "/api/me/reports/claim", headers={"Origin": "http://beta.test"},
        ),
    ))
    claiming.start()
    assert reached_claim_write.wait(5)

    deleting = threading.Thread(target=lambda: outcome.setdefault(
        "delete", phase.post(
            "/api/me/delete", json={"confirmation": "DELETE"},
            headers={"Origin": "http://phase.test"},
        ),
    ))
    deleting.start()
    deleting.join(0.1)
    assert deleting.is_alive(), "account deletion escaped the owner claim gate"

    release_claim.set()
    claiming.join(5)
    deleting.join(5)
    assert not claiming.is_alive() and not deleting.is_alive()
    assert outcome["claim"].status_code == 200  # type: ignore[union-attr]
    assert outcome["delete"].status_code == 200  # type: ignore[union-attr]
    assert store.get_by_id(report_row["id"]) is None
    assert phase.get("/api/auth/me").status_code == 401


def test_production_secret_and_origins_fail_closed(monkeypatch):
    monkeypatch.setenv("STRUCTURAL_ENV", "prod")
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "replace-with-private-64-hex-chars")
    with pytest.raises(RuntimeError, match="high-entropy"):
        sso._secret()
    monkeypatch.setenv("STRUCTURAL_SSO_SECRET", "A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3")
    monkeypatch.setenv("STRUCTURAL_SSO_PHASE_ORIGIN", "https://evil.example")
    with pytest.raises(RuntimeError, match="canonical"):
        sso._phase_origin()
