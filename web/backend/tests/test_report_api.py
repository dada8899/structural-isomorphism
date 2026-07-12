"""Integration tests for /api/report/* endpoints (M1.4).

Uses FastAPI TestClient against a focused sub-app — we don't need the
full lifespan / search load for these endpoints.
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
    """Point api.report._store at a fresh DB inside tmp_path."""
    from services.report_store import ReportStore
    from api import report as report_api

    fresh = ReportStore(tmp_path / "test_history.db")
    monkeypatch.setattr(report_api, "_store", fresh)
    return fresh


@pytest.fixture
def app(isolated_store):
    """Minimal app exposing just the report router."""
    from api import report as report_api

    a = FastAPI()
    a.include_router(report_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def sample_payload():
    return {
        "shared_structure": {"name": "Cascade"},
        "your_problem_breakdown": {"summary": "..."},
        "action_plan": {"immediate_actions": ["a"]},
    }


# --------- /api/report/{id} --------- #


def test_get_by_id_not_found(client):
    r = client.get("/api/report/r_doesnotexist")
    assert r.status_code == 404


def test_get_by_id_anonymous_owner_allows_read(client, isolated_store, sample_payload):
    """Row with no creator_anon_id can be read without X-Anon-Id."""
    out = isolated_store.create(
        query="q", b_id="b1", lang="en", payload=sample_payload, model="m",
    )
    r = client.get(f"/api/report/{out['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == out["id"]
    assert body["payload"]["shared_structure"]["name"] == "Cascade"
    # Owner-shape response must NOT include the share_token (caller of
    # this endpoint already has the id; the token is for the /share path).
    assert "share_token" not in body


def test_detail_lifts_decision_brief_provenance_without_leaking_reserved_keys(
    client, isolated_store, sample_payload,
):
    payload = {
        **sample_payload,
        "_fingerprint": {"summary": "用户确认的结构问题", "revision": 1},
        "_source": {"id": "p_1", "name": "Ant routing", "domain": "Biology"},
    }
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=payload, model="model-v1",
        prompt_version="prompt-v3",
    )
    body = client.get(f"/api/report/{out['id']}").json()
    assert body["fingerprint"]["summary"] == "用户确认的结构问题"
    assert body["source"] == {"id": "p_1", "name": "Ant routing", "domain": "Biology"}
    assert body["model"] == "model-v1"
    assert body["prompt_version"] == "prompt-v3"
    assert "_fingerprint" not in body["payload"]
    assert "_source" not in body["payload"]


def test_get_by_id_with_owner_requires_matching_anon(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="en", payload=sample_payload, model="m",
        creator_anon_id="A",
    )
    # Wrong anon-id → 404 (hide existence, NOT 403)
    r = client.get(f"/api/report/{out['id']}", headers={"X-Anon-Id": "B"})
    assert r.status_code == 404
    # Right anon-id → 200
    r = client.get(f"/api/report/{out['id']}", headers={"X-Anon-Id": "A"})
    assert r.status_code == 200


def test_get_by_id_records_view(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    client.get(f"/api/report/{out['id']}")
    client.get(f"/api/report/{out['id']}")
    r = client.get(f"/api/report/{out['id']}")
    assert r.json()["view_count"] >= 2


# --------- /api/report/share/{token} --------- #


def test_get_by_share_token_round_trip(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        creator_anon_id="A",
    )
    # No anon-id needed for share access — that's the whole point.
    r = client.get(f"/api/report/share/{out['share_token']}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == out["id"]


def test_get_by_share_token_invalid_format(client):
    r = client.get("/api/report/share/short-token")
    assert r.status_code == 404


def test_get_by_share_token_unknown(client):
    r = client.get("/api/report/share/" + "0" * 32)
    assert r.status_code == 404


# --------- /api/reports/mine --------- #


def test_list_mine_without_anon_returns_empty(client):
    r = client.get("/api/reports/mine")
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "has_more": False}


def test_list_mine_filters_by_anon(client, isolated_store, sample_payload):
    for q in ("q1", "q2"):
        isolated_store.create(
            query=q, b_id="b", lang="en", payload=sample_payload, model="m",
            creator_anon_id="A",
        )
    isolated_store.create(
        query="q3-other", b_id="b", lang="en", payload=sample_payload, model="m",
        creator_anon_id="B",
    )
    r = client.get("/api/reports/mine", headers={"X-Anon-Id": "A"})
    body = r.json()
    assert len(body["items"]) == 2
    assert all("other" not in i["query"] for i in body["items"])


def test_list_mine_pagination(client, isolated_store, sample_payload):
    for i in range(5):
        isolated_store.create(
            query=f"q{i}", b_id="b", lang="en", payload=sample_payload, model="m",
            creator_anon_id="A",
        )
    r = client.get(
        "/api/reports/mine?limit=2",
        headers={"X-Anon-Id": "A"},
    )
    body = r.json()
    assert len(body["items"]) == 2
    assert body["has_more"] is True

    r2 = client.get(
        "/api/reports/mine?limit=2&offset=4",
        headers={"X-Anon-Id": "A"},
    )
    body2 = r2.json()
    assert len(body2["items"]) == 1
    assert body2["has_more"] is False


# --------- POST /api/report/{id}/feedback --------- #


def test_feedback_up_vote(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/feedback",
        json={"section": "shared_structure", "vote": 1},
        headers={"X-Anon-Id": "V"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "total_up": 1, "total_down": 0}


def test_feedback_section_must_be_known(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/feedback",
        json={"section": "made_up_section_name", "vote": 1},
        headers={"X-Anon-Id": "V"},
    )
    assert r.status_code == 400


def test_feedback_vote_must_be_signed_one(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/feedback",
        json={"section": None, "vote": 7},
        headers={"X-Anon-Id": "V"},
    )
    assert r.status_code == 400


def test_feedback_404_on_missing_report(client):
    r = client.post(
        "/api/report/r_nope/feedback",
        json={"section": None, "vote": 1},
        headers={"X-Anon-Id": "V"},
    )
    assert r.status_code == 404


def test_feedback_same_voter_section_overwrites(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    headers = {"X-Anon-Id": "V"}
    body = {"section": "risks_and_limits", "vote": 1}
    client.post(f"/api/report/{out['id']}/feedback", json=body, headers=headers)
    body["vote"] = -1
    r = client.post(f"/api/report/{out['id']}/feedback", json=body, headers=headers)
    out_body = r.json()
    assert out_body == {"ok": True, "total_up": 0, "total_down": 1}


def test_feedback_different_voters_accumulate(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b", lang="en", payload=sample_payload, model="m",
    )
    for v in ("A", "B", "C"):
        client.post(
            f"/api/report/{out['id']}/feedback",
            json={"section": "action_plan", "vote": 1},
            headers={"X-Anon-Id": v},
        )
    # One more down-vote from a new voter
    r = client.post(
        f"/api/report/{out['id']}/feedback",
        json={"section": "action_plan", "vote": -1},
        headers={"X-Anon-Id": "D"},
    )
    body = r.json()
    assert body["total_up"] == 3
    assert body["total_down"] == 1


# --------- Session #17 V6 — /api/report/{id}/followup --------- #


def test_followup_404_for_missing_report(client):
    r = client.post(
        "/api/report/r_nope/followup",
        json={"action_status": "tried"},
    )
    assert r.status_code == 404


def test_followup_records_and_reads_back(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/followup",
        json={"action_status": "tried", "outcome": "worked", "note": "成了"},
        headers={"X-Anon-Id": "anon-x"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["action_status"] == "tried"
    assert body["outcome"] == "worked"

    # Read it back via GET — same anon.
    g = client.get(
        f"/api/report/{out['id']}/followup",
        headers={"X-Anon-Id": "anon-x"},
    )
    assert g.status_code == 200
    assert g.json()["followup"]["note"] == "成了"


def test_public_share_reader_cannot_mutate_owner_followup(
    client, isolated_store, sample_payload,
):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
        creator_anon_id="owner-device",
    )
    url = f"/api/report/{out['id']}/followup"
    denied = client.post(
        url,
        json={"action_status": "tried", "outcome": "worked"},
        headers={"X-Anon-Id": "share-reader"},
    )
    assert denied.status_code == 404
    assert isolated_store.get_followup(out["id"], "share-reader") is None
    allowed = client.post(
        url,
        json={"action_status": "tried", "outcome": "worked"},
        headers={"X-Anon-Id": "owner-device"},
    )
    assert allowed.status_code == 200


def test_followup_get_returns_null_when_absent(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    g = client.get(
        f"/api/report/{out['id']}/followup",
        headers={"X-Anon-Id": "nobody"},
    )
    assert g.status_code == 200
    assert g.json()["followup"] is None


def test_followup_upsert_via_api(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    hdr = {"X-Anon-Id": "anon-x"}
    client.post(
        f"/api/report/{out['id']}/followup",
        json={"action_status": "planned"}, headers=hdr,
    )
    r = client.post(
        f"/api/report/{out['id']}/followup",
        json={"action_status": "tried", "outcome": "partial"}, headers=hdr,
    )
    assert r.json()["action_status"] == "tried"
    assert r.json()["outcome"] == "partial"


def test_followup_rejects_bad_action_status(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/followup",
        json={"action_status": "garbage"},
    )
    assert r.status_code == 400


def test_followup_rejects_bad_outcome(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    r = client.post(
        f"/api/report/{out['id']}/followup",
        json={"action_status": "tried", "outcome": "exploded"},
    )
    assert r.status_code == 400


def test_followup_structured_experiment_lifecycle(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    url = f"/api/report/{out['id']}/followup"
    headers = {"X-Anon-Id": "workbench-user"}
    planned = client.post(url, headers=headers, json={
        "action_status": "planned",
        "experiment": {
            "hypothesis": "Onboarding examples improve activation",
            "owner": "researcher",
            "deadline": "2026-08-01",
            "baseline": 0.2,
            "primary_metric": "activation_rate",
            "success_threshold": 0.3,
            "stop_condition": "500 users",
            "status": "planned",
            "notes": "Use a holdout",
        },
    })
    assert planned.status_code == 200
    assert planned.json()["experiment"]["primary_metric"] == "activation_rate"

    running = client.post(url, headers=headers, json={
        "action_status": "in_progress",
        "experiment": {
            "status": "in_progress",
        },
    })
    assert running.status_code == 200
    completed = client.post(url, headers=headers, json={
        "action_status": "tried",
        "outcome": "worked",
        "experiment": {
            "status": "completed",
        },
        "outcome_detail": {
            "actual_metric": 0.34,
            "result": "success",
            "learning": "Examples reduced uncertainty",
            "next_decision": "scale",
        },
    })
    assert completed.status_code == 200
    assert completed.json()["experiment"]["owner"] == "researcher"
    assert completed.json()["experiment"]["deadline"] == "2026-08-01"
    assert completed.json()["outcome_detail"]["result"] == "success"
    got = client.get(url, headers=headers).json()["followup"]
    assert got["experiment"]["status"] == "completed"
    assert got["outcome_detail"]["actual_metric"] == 0.34


@pytest.mark.parametrize("body", [
    {"action_status": "planned", "experiment": {"hypothesis": ""}},
    {"action_status": "planned", "experiment": {"hypothesis": "h", "extra": 1}},
    {"action_status": "planned", "experiment": {"hypothesis": "h", "deadline": "tomorrow"}},
    {"action_status": "tried", "outcome_detail": {"result": "maybe"}},
])
def test_followup_rejects_invalid_structured_payload(
    client, isolated_store, sample_payload, body,
):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    r = client.post(f"/api/report/{out['id']}/followup", json=body)
    assert r.status_code == 422


def test_followup_api_rejects_conflicting_state(client, isolated_store, sample_payload):
    out = isolated_store.create(
        query="q", b_id="b1", lang="zh", payload=sample_payload, model="m",
    )
    r = client.post(f"/api/report/{out['id']}/followup", json={
        "action_status": "abandoned",
        "outcome": "worked",
        "experiment": {"hypothesis": "h", "status": "in_progress"},
    })
    assert r.status_code == 400
    assert "conflicts" in r.json()["detail"]
