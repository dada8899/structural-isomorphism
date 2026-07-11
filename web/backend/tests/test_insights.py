"""Tests for the B Data Flywheel (Session #18).

Three layers in one file:
  * unit  — ReportStore flywheel methods (list_by_anon followup join,
            verified_isomorphisms, stuck_structures, insights_summary)
            + verified_isomorphisms.shape_verified, incl. empty/edge cases.
  * integ — TestClient against a sub-app mounting api.insights.router and
            api.report.router, seeded with reports + followups.

Does NOT touch test_report_api.py / test_report_store.py — additive only.
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

from services.report_store import ReportStore  # noqa: E402
from services.verified_isomorphisms import (  # noqa: E402
    _short,
    list_verified,
    shape_verified,
)


# ============================ fixtures ============================ #


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path / "flywheel.db")


@pytest.fixture
def payload_with_credibility():
    """A payload carrying _credibility + shared_structure, as analyze.py
    persists it (the _credibility key is lifted out by api/report.py)."""
    return {
        "shared_structure": {"name": "Cascade dynamics"},
        "_credibility": {"source_domain": "Forest fire spread"},
        "action_plan": {"immediate_actions": ["a"]},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Sub-app with insights + report routers, both pointed at one fresh DB."""
    from api import insights as insights_api
    from api import report as report_api

    fresh = ReportStore(tmp_path / "app_flywheel.db")
    monkeypatch.setattr(insights_api, "_store", fresh)
    monkeypatch.setattr(report_api, "_store", fresh)

    a = FastAPI()
    a.include_router(insights_api.router, prefix="/api")
    a.include_router(report_api.router, prefix="/api")
    a._flywheel_store = fresh  # expose for seeding
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


def _seed_report(store, *, query="q", b_id="b1", anon="A", payload=None):
    return store.create(
        query=query, b_id=b_id, lang="zh",
        payload=payload or {"shared_structure": {"name": "S"}},
        model="m", creator_anon_id=anon,
    )


# ====================== unit: list_by_anon ======================== #


def test_list_by_anon_no_followup_marks_unrevisited(store):
    _seed_report(store, query="q1", anon="A")
    rows = store.list_by_anon("A")
    assert len(rows) == 1
    assert rows[0]["has_followup"] is False
    assert rows[0]["followup_outcome"] == ""
    assert rows[0]["followup_status"] == ""


def test_list_by_anon_carries_followup_summary(store):
    out = _seed_report(store, query="q1", anon="A")
    store.record_followup(
        report_id=out["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    rows = store.list_by_anon("A")
    assert rows[0]["has_followup"] is True
    assert rows[0]["followup_outcome"] == "worked"
    assert rows[0]["followup_status"] == "tried"


def test_list_by_anon_followup_join_is_per_anon(store):
    """A followup left by anon B must NOT show on anon A's list row."""
    out = _seed_report(store, query="q1", anon="A")
    store.record_followup(
        report_id=out["id"], anon_id="B",
        action_status="tried", outcome="worked",
    )
    rows = store.list_by_anon("A")
    # A owns the report but never revisited → still unrevisited for A.
    assert rows[0]["has_followup"] is False


def test_list_by_anon_empty(store):
    assert store.list_by_anon("nobody") == []


# ================== unit: verified_isomorphisms =================== #


def test_verified_empty_db(store):
    assert store.verified_isomorphisms() == []


def test_verified_only_worked_outcomes_count(store):
    worked = _seed_report(store, query="worked-one", anon="A")
    partial = _seed_report(store, query="partial-one", anon="A")
    store.record_followup(
        report_id=worked["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=partial["id"], anon_id="A",
        action_status="tried", outcome="partial",
    )
    rows = store.verified_isomorphisms()
    assert len(rows) == 1
    assert rows[0]["query"] == "worked-one"
    assert rows[0]["verifier_count"] == 1


def test_verified_multiple_verifiers_aggregate(store):
    out = _seed_report(store, query="popular", anon="A")
    for v in ("A", "B", "C"):
        store.record_followup(
            report_id=out["id"], anon_id=v,
            action_status="tried", outcome="worked",
        )
    rows = store.verified_isomorphisms()
    assert len(rows) == 1
    # Only the report creator's revisit is admissible research evidence;
    # public share readers may not inflate verification counts.
    assert rows[0]["verifier_count"] == 1
    assert rows[0]["last_verified_at"]


def test_verified_payload_decoded(store, payload_with_credibility):
    out = _seed_report(
        store, query="q", anon="A", payload=payload_with_credibility,
    )
    store.record_followup(
        report_id=out["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    rows = store.verified_isomorphisms()
    assert isinstance(rows[0]["payload"], dict)
    assert rows[0]["payload"]["_credibility"]["source_domain"] == "Forest fire spread"


# ==================== unit: stuck_structures ====================== #


def test_stuck_structures_empty_db(store):
    assert store.stuck_structures() == []


def test_stuck_structures_groups_by_b_id(store):
    for q in ("q1", "q2", "q3"):
        _seed_report(store, query=q, b_id="hot", anon="A")
    _seed_report(store, query="q4", b_id="cold", anon="A")
    rows = store.stuck_structures()
    assert rows[0]["b_id"] == "hot"
    assert rows[0]["report_count"] == 3
    assert rows[1]["b_id"] == "cold"
    assert rows[1]["report_count"] == 1


def test_stuck_structures_worked_rate(store):
    a = _seed_report(store, query="q1", b_id="hot", anon="A")
    b = _seed_report(store, query="q2", b_id="hot", anon="A")
    _seed_report(store, query="q3", b_id="hot", anon="A")  # no followup
    store.record_followup(
        report_id=a["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=b["id"], anon_id="A",
        action_status="tried", outcome="no_effect",
    )
    rows = store.stuck_structures()
    hot = rows[0]
    assert hot["report_count"] == 3
    assert hot["followup_count"] == 2
    assert hot["worked_count"] == 1
    assert hot["worked_rate"] == 0.5  # 1 worked / 2 followups


def test_stuck_structures_no_followup_rate_is_zero(store):
    _seed_report(store, query="q1", b_id="hot", anon="A")
    rows = store.stuck_structures()
    assert rows[0]["worked_rate"] == 0.0
    assert rows[0]["followup_count"] == 0


# ==================== unit: insights_summary ====================== #


def test_summary_empty_db(store):
    s = store.insights_summary()
    assert s == {
        "total_reports": 0,
        "total_followups": 0,
        "worked_count": 0,
        "verified_isomorphisms": 0,
    }


def test_summary_counts(store):
    a = _seed_report(store, query="q1", anon="A")
    b = _seed_report(store, query="q2", anon="A")
    store.record_followup(
        report_id=a["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=b["id"], anon_id="A",
        action_status="planned", outcome="",
    )
    s = store.insights_summary()
    assert s["total_reports"] == 2
    assert s["total_followups"] == 2
    assert s["worked_count"] == 1
    assert s["verified_isomorphisms"] == 1


# ============== unit: verified_isomorphisms helpers =============== #


def test_short_trims_long_text():
    assert _short("abc") == "abc"
    long = "x" * 200
    out = _short(long, limit=120)
    assert len(out) == 121 and out.endswith("…")


def test_short_handles_none():
    assert _short(None) == ""


def test_shape_verified_full_payload(payload_with_credibility):
    row = {
        "id": "r_1", "query": "我的招聘卡住了", "b_id": "b1", "lang": "zh",
        "payload": payload_with_credibility,
        "created_at": "2026-05-01T00:00:00Z",
        "verifier_count": 2, "last_verified_at": "2026-05-10T00:00:00Z",
    }
    out = shape_verified(row)
    assert out["report_id"] == "r_1"
    assert out["source_phenomenon"] == "Forest fire spread"
    assert out["structure_name"] == "Cascade dynamics"
    assert out["verifier_count"] == 2


def test_shape_verified_missing_payload_degrades():
    row = {"id": "r_2", "query": "q", "b_id": "b", "lang": "en",
           "payload": None, "created_at": "", "verifier_count": 0,
           "last_verified_at": ""}
    out = shape_verified(row)
    assert out["source_phenomenon"] == ""
    assert out["structure_name"] == ""


def test_list_verified_empty(store):
    assert list_verified(store) == []


# ===================== integ: /api/insights/* ==================== #


def test_summary_endpoint_empty(client):
    r = client.get("/api/insights/summary")
    assert r.status_code == 200
    assert r.json() == {
        "total_reports": 0, "total_followups": 0,
        "worked_count": 0, "verified_isomorphisms": 0,
    }


def test_summary_endpoint_with_data(client, app):
    store = app._flywheel_store
    out = _seed_report(store, query="q1", anon="A")
    store.record_followup(
        report_id=out["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    r = client.get("/api/insights/summary")
    body = r.json()
    assert body["total_reports"] == 1
    assert body["worked_count"] == 1
    assert body["verified_isomorphisms"] == 1


def test_stuck_structures_endpoint_empty(client):
    r = client.get("/api/insights/stuck-structures")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_stuck_structures_endpoint_with_data(client, app):
    store = app._flywheel_store
    for q in ("q1", "q2"):
        _seed_report(store, query=q, b_id="hot", anon="A")
    _seed_report(store, query="q3", b_id="cold", anon="A")
    r = client.get("/api/insights/stuck-structures")
    items = r.json()["items"]
    assert items[0]["b_id"] == "hot"
    assert items[0]["report_count"] == 2


def test_stuck_structures_limit_validation(client):
    assert client.get("/api/insights/stuck-structures?limit=0").status_code == 422
    assert client.get("/api/insights/stuck-structures?limit=999").status_code == 422
    assert client.get("/api/insights/stuck-structures?limit=5").status_code == 200


def test_verified_endpoint_empty(client):
    r = client.get("/api/insights/verified")
    assert r.status_code == 200
    assert r.json() == {"items": []}


def test_verified_endpoint_with_data(client, app, payload_with_credibility):
    store = app._flywheel_store
    out = _seed_report(
        store, query="招聘漏斗", anon="A", payload=payload_with_credibility,
    )
    store.record_followup(
        report_id=out["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    r = client.get("/api/insights/verified")
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["problem"] == "招聘漏斗"
    assert items[0]["source_phenomenon"] == "Forest fire spread"
    assert items[0]["verifier_count"] == 1


def test_verified_endpoint_excludes_non_worked(client, app):
    store = app._flywheel_store
    out = _seed_report(store, query="partial-only", anon="A")
    store.record_followup(
        report_id=out["id"], anon_id="A",
        action_status="tried", outcome="partial",
    )
    r = client.get("/api/insights/verified")
    assert r.json()["items"] == []


def test_verified_limit_validation(client):
    assert client.get("/api/insights/verified?limit=0").status_code == 422
    assert client.get("/api/insights/verified?limit=200").status_code == 422


# ============== integ: /reports/mine followup fields ============= #


def test_reports_mine_includes_followup_status(client, app):
    store = app._flywheel_store
    revisited = _seed_report(store, query="done", anon="A")
    _seed_report(store, query="todo", anon="A")
    store.record_followup(
        report_id=revisited["id"], anon_id="A",
        action_status="tried", outcome="worked",
    )
    r = client.get("/api/reports/mine", headers={"X-Anon-Id": "A"})
    items = {it["query"]: it for it in r.json()["items"]}
    assert items["done"]["has_followup"] is True
    assert items["done"]["followup_outcome"] == "worked"
    assert items["done"]["followup_status"] == "tried"
    assert items["todo"]["has_followup"] is False
    assert items["todo"]["followup_outcome"] == ""
    assert items["todo"]["followup_status"] == ""


def test_reports_mine_empty_still_has_shape(client):
    r = client.get("/api/reports/mine", headers={"X-Anon-Id": "nobody"})
    assert r.status_code == 200
    assert r.json() == {"items": [], "has_more": False}
