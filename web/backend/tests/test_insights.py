"""Adversarial privacy contracts for the paused public Insights surface."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.report_store import ReportStore  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path / "flywheel.db")


@pytest.fixture
def app(tmp_path):
    from api import insights as insights_api

    fresh = ReportStore(tmp_path / "app_flywheel.db")
    application = FastAPI()
    application.middleware("http")(
        insights_api.no_store_insights_responses
    )
    application.include_router(insights_api.router, prefix="/api")

    @application.get("/api/insights/_unhandled-test")
    async def unhandled_test():
        raise RuntimeError("sentinel must not escape")

    application._flywheel_store = fresh
    return application


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _seed_report(store, *, b_id="b1", anon="owner-0", publish=True):
    report = store.create(
        query=f"private {anon}",
        b_id=b_id,
        lang="zh",
        payload={"shared_structure": {"name": "private"}},
        model="m",
        creator_anon_id=anon,
    )
    followup = store.record_followup(
        report_id=report["id"],
        anon_id=anon,
        action_status="tried",
        outcome="worked",
        publish_to_insights=publish,
    )
    return report, followup


def _seed_accounts(store, *, size, start=0, b_id="b1"):
    rows = []
    for index in range(start, start + size):
        anon = f"device-{index}"
        report, followup = _seed_report(store, b_id=b_id, anon=anon)
        store.claim_by_anon(anon, f"account-{index}")
        rows.append((report, followup))
    return rows


def _public_snapshot(client, suffix=""):
    query = suffix if suffix.startswith("?") else ""
    return {
        "summary": client.get("/api/insights/summary").json(),
        "stuck": client.get(
            "/api/insights/stuck-structures" + query
        ).json(),
        "verified": client.get(
            "/api/insights/verified" + query
        ).json(),
    }


def test_store_has_no_public_aggregate_compatibility_methods(store):
    for removed in (
        "insights_summary", "stuck_structures", "verified_isomorphisms",
        "count_human_verified",
    ):
        assert not hasattr(store, removed)


def test_adding_four_five_six_accounts_never_changes_public_response(
    client, app,
):
    initial = _public_snapshot(client)
    _seed_accounts(app._flywheel_store, size=4)
    after_four = _public_snapshot(client)
    _seed_accounts(app._flywheel_store, size=1, start=4)
    after_five = _public_snapshot(client)
    _seed_accounts(app._flywheel_store, size=1, start=5)
    after_six = _public_snapshot(client)
    assert initial == after_four == after_five == after_six


def test_adding_nineteenth_and_twentieth_account_never_changes_band_or_card(
    client, app,
):
    _seed_accounts(app._flywheel_store, size=18)
    before = _public_snapshot(client)
    _seed_accounts(app._flywheel_store, size=1, start=18)
    at_nineteen = _public_snapshot(client)
    _seed_accounts(app._flywheel_store, size=1, start=19)
    at_twenty = _public_snapshot(client)
    assert before == at_nineteen == at_twenty


def test_anonymous_creators_never_produce_a_public_participant(client, app):
    for index in range(30):
        _seed_report(app._flywheel_store, anon=f"anonymous-device-{index}")
    assert _public_snapshot(client) == {
        "summary": {"status": "public_aggregation_paused"},
        "stuck": {"status": "public_aggregation_paused"},
        "verified": {"status": "public_aggregation_paused"},
    }
    source = (_BACKEND / "services" / "report_store.py").read_text(
        encoding="utf-8"
    )
    assert "'anon:' ||" not in source


def test_limit_and_sort_sentinels_cannot_change_or_query_public_state(
    client, app,
):
    low = _public_snapshot(client, "?limit=1")
    high = _public_snapshot(client, "?limit=100")
    assert low == high
    assert low["stuck"] == {"status": "public_aggregation_paused"}
    assert low["verified"] == {"status": "public_aggregation_paused"}
    source = (_BACKEND / "api" / "insights.py").read_text(encoding="utf-8")
    for forbidden in ("ReportStore", "_get_store", "ORDER BY", "sorted("):
        assert forbidden not in source


@pytest.mark.parametrize(
    "path,status",
    [
        ("/api/insights/summary", 200),
        ("/api/insights/stuck-structures", 200),
        ("/api/insights/verified", 200),
        ("/api/insights", 404),
        ("/api/insights/not-a-route", 404),
        ("/api/insights/stuck-structures?limit=0", 422),
        ("/api/insights/verified?limit=101", 422),
        ("/api/insights/_unhandled-test", 500),
    ],
)
def test_every_insights_status_is_no_store(client, path, status):
    response = client.get(path)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_public_schema_contains_no_count_category_recency_or_identifier(client):
    serialized = str(_public_snapshot(client)).lower()
    for forbidden in (
        "count", "worked", "partial", "recent", "rate", "participant",
        "verifier", "canonical_b_id", "report_id", "band",
    ):
        assert forbidden not in serialized


def test_openapi_exposes_only_paused_status_and_no_band_or_card_schema(app):
    serialized = json.dumps(app.openapi(), ensure_ascii=False).lower()
    for forbidden in (
        "participation_band", "verification_band", "stuckstructureitem",
        "verifieditem", '"5+"', '"20+"', '"100+"', '"500+"',
    ):
        assert forbidden not in serialized
