"""Integration tests for /api/report/* endpoints (M1.4).

Uses FastAPI TestClient against a focused sub-app — we don't need the
full lifespan / search load for these endpoints.
"""
from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))
from tests.deep_report_fixtures import report_payload  # noqa: E402


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
    a.middleware("http")(report_api.no_store_report_share_responses)
    a.include_router(report_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_payload():
    return {
        "shared_structure": {"name": "Cascade"},
        "your_problem_breakdown": {"summary": "..."},
        "action_plan": {"immediate_actions": ["a"]},
    }


def _create_current_v2_report(store, *, fingerprint: bool = False):
    """Create the same sealed query-mode archive emitted by analyze.py."""
    from api.analyze import (
        _canonical_digest,
        _persisted_report_receipt,
        _query_binding,
        _record_digest,
        _source_ref,
    )
    from services.deep_report import (
        GeneratedDeepReportV2,
        SourceBinding,
        bind_deep_report,
    )
    from services.evidence_envelope import build_evidence_envelope

    query = "如何区分反馈延迟与共同趋势？"
    source = {
        "id": "b_target",
        "name": "Target phenomenon",
        "domain": "test-domain",
        "type_id": "T",
        "description": "Internal source description for a candidate pattern.",
    }
    model = "test/deep-report-model"
    raw = deepcopy(report_payload())
    # Keep this report-boundary fixture independent of the semantic Builder's
    # moving regex work; these are neutral candidate-planning statements, not
    # completed evidence or causal claims.
    raw["action_plan"]["if_time_short"]["rationale"] = (
        "先固定比较方案，避免后续解释口径漂移。"
    )
    raw["research_directions"]["source_types_to_check"] = [
        "待核查的研究资料", "待核查的可复现数据",
    ]
    raw["target_domain_intro"]["corresponding_phenomenon"]["source_ref_ids"] = [
        "kb:b_target"
    ]
    persisted_fingerprint = None
    if fingerprint:
        persisted_fingerprint = {
            "summary": "用户确认反馈延迟可能影响目标波动。",
            "variables": ["反馈延迟", "波动"],
            "constraints": ["同一数据窗口"],
            "unknowns": ["共同趋势强度"],
            "revision": 2,
            "provenance": "user_confirmed",
        }
    else:
        raw["your_problem_breakdown"]["fingerprint_revision"] = None
    source_ref = _source_ref(source, lang="zh")
    binding = SourceBinding(
        source_kb_id=source["id"],
        source_record_sha256=_record_digest(source),
        kb_artifact_id="artifact-test-v1",
        target_kind="query",
        target_kb_id=None,
        query_binding=_query_binding(query, b_id=source["id"], lang="zh"),
        fingerprint_sha256=(
            _canonical_digest(persisted_fingerprint)
            if persisted_fingerprint is not None else None
        ),
        fingerprint_revision=(
            persisted_fingerprint["revision"]
            if persisted_fingerprint is not None else None
        ),
        lang="zh",
        model_id=model,
        prompt_version="deep-report-v2",
        schema_version="deep-analysis-report-v2",
    )
    report = bind_deep_report(
        GeneratedDeepReportV2.model_validate(raw),
        source_binding=binding,
        source_refs=[source_ref],
        source_record=source,
    ).model_dump(mode="json")
    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        candidate_label=source["name"],
        requested_level="candidate",
        source_kind="internal_kb",
        source_label="Structural internal KB candidate",
        result_provenance="NOT_TESTED",
        result_verdict="NOT_TESTED",
        independence_kind="not_recorded",
        counterexample_status="gap_recorded",
        counterexample_summary="报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。",
    )
    sealed = {
        **report,
        "_report_sha256": _canonical_digest(report),
        "_source_record": source,
        "_evidence": evidence,
        **({"_fingerprint": persisted_fingerprint} if persisted_fingerprint else {}),
        "_source": {
            key: source[key] for key in ("id", "name", "domain", "type_id")
        },
    }
    sealed["_report_receipt"] = _persisted_report_receipt(
        query=query,
        b_id=source["id"],
        lang="zh",
        model=model,
        prompt_version="deep-report-v2",
        payload=sealed,
    )
    out = store.create(
        query=query,
        b_id=source["id"],
        lang="zh",
        payload=sealed,
        model=model,
        prompt_version="deep-report-v2",
        creator_anon_id="device-owner",
    )
    return out, source


def _replace_report_row(store, report_id: str, *, payload: dict, query: str) -> None:
    with store._connect() as conn:
        conn.execute(
            "UPDATE reports SET payload=?, query=? WHERE id=?",
            (json.dumps(payload, ensure_ascii=False), query, report_id),
        )


# --------- /api/report/{id} --------- #


def test_get_by_id_not_found(client):
    r = client.get("/api/report/r_doesnotexist")
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"


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
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"
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
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"
    body = r.json()
    assert body["id"] == out["id"]


def test_current_v2_archive_is_bound_minimal_and_capability_safe(
    client, isolated_store,
):
    out, source = _create_current_v2_report(isolated_store, fingerprint=True)
    owner = client.get(
        f"/api/report/{out['id']}", headers={"X-Anon-Id": "device-owner"},
    )
    public = client.get(f"/api/report/share/{out['share_token']}")
    assert owner.status_code == public.status_code == 200
    assert owner.headers["cache-control"] == "no-store"
    assert public.headers["cache-control"] == "no-store"

    owner_body = owner.json()
    public_body = public.json()
    common_keys = {
        "id", "query", "b_id", "lang", "payload", "model",
        "prompt_version", "created_at", "view_count", "is_partial",
        "fingerprint", "source", "evidence", "report_sha256",
        "snapshot_status",
    }
    assert set(public_body) == common_keys
    assert set(owner_body) == common_keys | {"share_url"}
    assert owner_body["share_url"] == f"/report/share/{out['share_token']}"
    assert public_body["snapshot_status"] == "historical_snapshot"
    assert public_body["source"] == {
        key: source[key] for key in ("id", "name", "domain", "type_id")
    }
    assert public_body["fingerprint"]["source_query"] == public_body["query"]
    assert public_body["payload"]["source_binding"]["source_kb_id"] == source["id"]
    serialized = json.dumps(public_body, ensure_ascii=False)
    assert out["share_token"] not in serialized
    assert "share_token" not in serialized
    assert "share_url" not in public_body


@pytest.mark.parametrize(
    "location", ["query", "rewritten", "nested", "key", "encoded"],
)
def test_any_internal_share_capability_is_rejected_everywhere(
    client, isolated_store, sample_payload, location,
):
    other_token = "b" * 32
    capability = f"https://beta.structural.bytedance.city/report/share/{other_token}"
    query = capability if location == "query" else "safe query"
    rewritten = f"/api/report/share/{other_token}" if location == "rewritten" else None
    payload = deepcopy(sample_payload)
    if location == "nested":
        payload["nested"] = [{"deeper": capability}]
    elif location == "key":
        payload[f"copied:{capability}"] = "value"
    elif location == "encoded":
        payload["nested"] = "%2Freport%2Fshare%2F" + other_token
    out = isolated_store.create(
        query=query,
        rewritten_query=rewritten,
        b_id="b",
        lang="en",
        payload=payload,
        model="m",
        creator_anon_id="device-owner",
    )
    owner = client.get(
        f"/api/report/{out['id']}", headers={"X-Anon-Id": "device-owner"},
    )
    public = client.get(f"/api/report/share/{out['share_token']}")
    assert owner.status_code == 409
    assert owner.headers["cache-control"] == "no-store"
    assert public.status_code == 404
    assert public.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "case",
    [
        "missing_receipt", "wrong_receipt", "missing_hash", "wrong_hash",
        "wrong_source", "wrong_query", "wrong_fingerprint", "wrong_artifact",
    ],
)
def test_current_v2_archive_tampering_fails_closed(
    client, isolated_store, case,
):
    from api.analyze import _canonical_digest, _persisted_report_receipt
    from services.deep_report import DeepAnalysisReportV2

    out, _ = _create_current_v2_report(isolated_store, fingerprint=True)
    row = isolated_store.get_by_id(out["id"])
    payload = deepcopy(row["payload"])
    query = row["query"]
    if case == "missing_receipt":
        payload.pop("_report_receipt")
    elif case == "wrong_receipt":
        payload["_report_receipt"] = "0" * 64
    elif case == "missing_hash":
        payload.pop("_report_sha256")
    elif case == "wrong_hash":
        payload["_report_sha256"] = "0" * 64
    elif case == "wrong_source":
        payload["_source_record"]["description"] = "tampered description"
    elif case == "wrong_query":
        query = "receipt-valid but binding-invalid query"
    elif case == "wrong_fingerprint":
        payload["_fingerprint"]["revision"] = 3
    elif case == "wrong_artifact":
        payload["source_binding"].pop("kb_artifact_id")
        report_keys = set(DeepAnalysisReportV2.model_fields)
        report = {key: payload[key] for key in report_keys if key in payload}
        payload["_report_sha256"] = _canonical_digest(report)

    if case not in {"missing_receipt", "wrong_receipt", "missing_hash"}:
        sealed = {key: value for key, value in payload.items() if key != "_report_receipt"}
        payload["_report_receipt"] = _persisted_report_receipt(
            query=query,
            b_id=row["b_id"],
            lang=row["lang"],
            model=row["model"],
            prompt_version=row["prompt_version"],
            payload=sealed,
        )
    _replace_report_row(isolated_store, out["id"], payload=payload, query=query)

    owner = client.get(
        f"/api/report/{out['id']}", headers={"X-Anon-Id": "device-owner"},
    )
    public = client.get(f"/api/report/share/{out['share_token']}")
    assert owner.status_code == 409
    assert owner.headers["cache-control"] == "no-store"
    assert public.status_code == 404
    assert public.headers["cache-control"] == "no-store"


def test_valid_archive_rolls_to_historical_when_live_artifact_changes(
    client, isolated_store, monkeypatch,
):
    from api import report as report_api

    out, source = _create_current_v2_report(isolated_store)

    class Search:
        @staticmethod
        def get_by_id(value):
            return source if value == source["id"] else None

    monkeypatch.setattr(report_api, "_runtime_report_state", lambda: {
        "search": Search(), "artifact": {"artifact_id": "artifact-test-v1"},
    })
    current = client.get(f"/api/report/share/{out['share_token']}")
    assert current.status_code == 200
    assert current.json()["snapshot_status"] == "current_artifact"

    monkeypatch.setattr(report_api, "_runtime_report_state", lambda: {
        "search": Search(), "artifact": {"artifact_id": "artifact-test-v2"},
    })
    historical = client.get(f"/api/report/share/{out['share_token']}")
    assert historical.status_code == 200
    assert historical.json()["snapshot_status"] == "historical_snapshot"


def test_get_by_share_token_invalid_format(client):
    r = client.get("/api/report/share/short-token")
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"


def test_get_by_share_token_unknown(client):
    r = client.get("/api/report/share/" + "0" * 32)
    assert r.status_code == 404
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["pragma"] == "no-cache"


@pytest.mark.parametrize(
    "path,status",
    [("/api/report/share", 404), ("/api/report/share/", 307)],
)
def test_share_parent_and_redirect_are_also_no_store(client, path, status):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == status
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_get_by_share_token_unhandled_failure_is_minimal_and_no_store(
    client, monkeypatch,
):
    from api import report as report_api

    class ExplodingStore:
        def get_by_share_token(self, token):
            raise RuntimeError("private database detail")

    monkeypatch.setattr(report_api, "_store", ExplodingStore())
    response = client.get("/api/report/share/" + "a" * 32)
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_get_by_id_unhandled_failure_is_minimal_and_no_store(client, monkeypatch):
    from api import report as report_api

    class ExplodingStore:
        def get_by_id(self, report_id):
            raise RuntimeError("private database detail")

    monkeypatch.setattr(report_api, "_store", ExplodingStore())
    response = client.get("/api/report/r_0123456789abcdef")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal Server Error"}
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["pragma"] == "no-cache"


def test_shared_historical_snapshots_recursively_drop_user_aggregates(
    client, isolated_store, sample_payload,
):
    payload = {
        **sample_payload,
        "_credibility": {
            "similarity": 0.72,
            "human_verified_count": 20,
            "userRecordedOutcomeCount": 11,
            "humanVerificationTotal": 9,
            "用户反馈数": 7,
            "historical_note": "20 user-recorded outcomes",
            "nested": {"worked_count": 19, "recent": "2026-07-13"},
        },
        "_evidence": {
            "schema_version": "evidence-envelope-v1",
            "result": {
                "provenance": "USER_RECORDED_OUTCOME",
                "verdict": "INCONCLUSIVE",
                "summary": "20 user-recorded worked outcomes",
            },
        },
        "nested_history": {
            "_credibility": {"verifier_count": 6, "kb_source": True},
            "_evidence": {
                "result": {"provenance": "USER_RECORDED_OUTCOME"},
            },
        },
        "text_only_history": {
            "_evidence": {"summary": "20 user-recorded outcomes"},
        },
    }
    out = isolated_store.create(
        query="private", b_id="b", lang="en", payload=payload, model="m",
        creator_anon_id="device-a",
    )
    isolated_store.record_followup(
        report_id=out["id"], anon_id="device-a", action_status="tried",
        outcome="worked", publish_to_insights=True,
    )
    isolated_store.claim_by_anon("device-a", "account-a")
    isolated_store.withdraw_insights_consent_by_owner(out["id"], "account-a")

    response = client.get(f"/api/report/share/{out['share_token']}")
    assert response.status_code == 200
    body = response.json()
    assert body["credibility"] == {"similarity": 0.72}
    assert "evidence" not in body
    assert body["payload"]["nested_history"]["_credibility"] == {
        "kb_source": True,
    }
    assert body["payload"]["nested_history"]["_evidence"] is None
    assert body["payload"]["text_only_history"]["_evidence"] is None
    serialized = str(body)
    for forbidden in (
        "human_verified", "worked_count", "verifier_count",
        "userRecordedOutcomeCount", "humanVerificationTotal", "用户反馈数",
        "USER_RECORDED_OUTCOME", "20 user-recorded",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "surface,summary",
    [
        (
            "credibility",
            "5 user-recorded worked outcome(s); not an independent "
            "mechanism validation.",
        ),
        ("evidence", "5 条用户“管用”回填；不是独立机制验证。"),
        ("nested_evidence", "已有 5 位用户反馈管用"),
        ("credibility", "Across seven users, three reported that it worked."),
        ("evidence", "Eight participants reported successful results."),
        ("nested_evidence", "用户复测后有部分结果有效"),
        ("evidence", "Five customer responses found the transfer useful."),
        ("nested_evidence", "5 条反馈记录显示改善有效"),
    ],
)
def test_share_sanitizer_rejects_user_result_language_families(
    client, isolated_store, sample_payload, surface, summary,
):
    payload = {**sample_payload}
    if surface == "credibility":
        payload["_credibility"] = {
            "similarity": 0.61,
            "summary": summary,
        }
    elif surface == "evidence":
        payload["_evidence"] = {
            "schema_version": "evidence-envelope-v1",
            "result": {"summary": summary},
        }
    else:
        payload["history"] = {
            "deeper": {"_evidence": {"result": {"summary": summary}}},
        }

    out = isolated_store.create(
        query="historical private snapshot", b_id="b", lang="zh",
        payload=payload, model="m", creator_anon_id="original-device",
    )
    response = client.get(f"/api/report/share/{out['share_token']}")
    assert response.status_code == 200
    body = response.json()
    serialized = json.dumps(body, ensure_ascii=False)
    assert summary not in serialized
    if surface == "credibility":
        assert body["credibility"] == {"similarity": 0.61}
    elif surface == "evidence":
        assert "evidence" not in body
    else:
        assert body["payload"]["history"]["deeper"]["_evidence"] is None


@pytest.mark.parametrize(
    "provenance,summary",
    [
        (
            "EXTERNAL_REVIEW",
            "Independent human reviewers confirmed the algebraic mapping.",
        ),
        (
            "INDEPENDENT_REPLICATION",
            "An independent team reproduced the recorded result.",
        ),
        (
            "INTERNAL_REAL_DATA",
            "The controlled experiment recorded successful results.",
        ),
        (
            "INTERNAL_AI_SCREEN",
            "Human feedback control improved stability in the benchmark.",
        ),
        (
            "INTERNAL_REAL_DATA",
            "实验记录显示改善有效，但仍需复现。",
        ),
        (
            "NOT_TESTED",
            "No result has been recorded; this is a candidate only.",
        ),
    ],
)
def test_share_projection_preserves_valid_scientific_evidence_by_provenance(
    client, isolated_store, sample_payload, provenance, summary,
):
    from services.evidence_envelope import build_evidence_envelope

    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        candidate_label="Feedback control",
        candidate_score=0.72,
        source_kind="internal_kb",
        source_label="Structural KB record",
        result_provenance=provenance,
        result_verdict=(
            "NOT_TESTED" if provenance == "NOT_TESTED" else "INCONCLUSIVE"
        ),
        result_summary=summary,
        independence_kind=(
            "not_recorded" if provenance == "NOT_TESTED" else "internal"
        ),
        counterexample_status="gap_recorded",
    )
    out = isolated_store.create(
        query="valid science", b_id="b", lang="en",
        payload={**sample_payload, "_evidence": evidence}, model="m",
    )
    body = client.get(f"/api/report/share/{out['share_token']}").json()
    assert body["evidence"] == evidence
    assert body["evidence"]["result"]["summary"] == summary


@pytest.mark.parametrize(
    "mutation",
    [
        lambda row: row["result"].update(
            {"provenance": "USER_RECORDED_OUTCOME", "status": "recorded"}
        ),
        lambda row: row["result"].update({"provenance": "AI_VERIFIED"}),
        lambda row: row["result"].pop("provenance"),
        lambda row: row.update({"result": ["INTERNAL_REAL_DATA"]}),
        lambda row: row.pop("candidate"),
        lambda row: row["source"].update({
            "status": "recorded",
            "kind": "external_source",
            "label": "Future review",
            "url": "https://example.com/review",
            "source_review": {
                "reviewer": "Reviewer A",
                "reviewed_at": "2999-01-01",
            },
        }),
        lambda row: row["ledger"].update({
            "status": "bound",
            "claim_id": "claim-1",
            "version": "v1",
            "recorded_at": "2999-01-01",
            "artifact_sha256": "a" * 64,
            "url": "https://example.com/ledger",
        }),
    ],
)
def test_share_projection_fails_closed_for_private_or_malformed_evidence(
    client, isolated_store, sample_payload, mutation,
):
    from services.evidence_envelope import build_evidence_envelope

    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        result_provenance="INTERNAL_REAL_DATA",
        result_verdict="INCONCLUSIVE",
    )
    mutation(evidence)
    out = isolated_store.create(
        query="malformed", b_id="b", lang="en",
        payload={**sample_payload, "_evidence": evidence}, model="m",
    )
    body = client.get(f"/api/report/share/{out['share_token']}").json()
    assert "evidence" not in body


def test_share_projection_recursively_drops_unknown_camelcase_and_arrays(
    client, isolated_store, sample_payload,
):
    from services.evidence_envelope import build_evidence_envelope

    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        result_provenance="EXTERNAL_REVIEW",
        result_verdict="INCONCLUSIVE",
        result_summary="Independent reviewers confirmed the mapping.",
        independence_kind="external_review",
    )
    evidence["userRecordedOutcomeCount"] = 12
    evidence["result"]["outcomeCounts"] = ["worked", "partial"]
    evidence["candidate"]["privateHistory"] = {
        "userResults": [{"workedCount": 9}],
    }
    evidence["ledger"]["participants"] = ["private-a", "private-b"]
    credibility = {
        "kb_source": True,
        "similarity": 0.71,
        "source_domain": "Control science",
        "has_verified_pairs": False,
        "verified_pair_count": 0,
        "best_verified_pair": None,
        "userRecordedOutcomeCount": 12,
        "outcomeCounts": ["worked"],
        "nestedPrivateHistory": [{"humanVerificationTotal": 4}],
    }
    out = isolated_store.create(
        query="strict projection", b_id="b", lang="en",
        payload={
            **sample_payload,
            "_credibility": credibility,
            "_evidence": evidence,
        },
        model="m",
    )
    body = client.get(f"/api/report/share/{out['share_token']}").json()
    assert body["credibility"] == {
        "kb_source": True,
        "similarity": 0.71,
        "source_domain": "Control science",
        "has_verified_pairs": False,
        "verified_pair_count": 0,
        "best_verified_pair": None,
    }
    assert body["evidence"]["result"]["provenance"] == "EXTERNAL_REVIEW"
    serialized = json.dumps(body, ensure_ascii=False)
    for forbidden in (
        "userRecordedOutcomeCount", "outcomeCounts", "privateHistory",
        "nestedPrivateHistory", "humanVerificationTotal", "participants",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "credibility",
    [
        ["similarity", 0.7],
        {"similarity": "0.7"},
        {"has_verified_pairs": False, "verified_pair_count": 2},
        {"best_verified_pair": ["private"]},
        {
            "has_verified_pairs": True,
            "verified_pair_count": 1,
            "best_verified_pair": {
                "other_name": "A",
                "other_domain": "B",
                "score": 4.5,
            },
        },
    ],
)
def test_share_projection_fails_closed_for_malformed_credibility(
    client, isolated_store, sample_payload, credibility,
):
    out = isolated_store.create(
        query="bad credibility", b_id="b", lang="en",
        payload={**sample_payload, "_credibility": credibility}, model="m",
    )
    body = client.get(f"/api/report/share/{out['share_token']}").json()
    assert "credibility" not in body


def test_share_projection_preserves_deep_public_content_and_removes_reserved_origin(
    client, isolated_store, sample_payload,
):
    nested = {
        "public": "must survive",
        "_origin_candidate": {"private": "must disappear"},
    }
    for _ in range(34):
        nested = {"deeper": nested}
    out = isolated_store.create(
        query="deep historical payload", b_id="b", lang="en",
        payload={**sample_payload, "history": nested}, model="m",
    )
    body = client.get(f"/api/report/share/{out['share_token']}").json()
    cursor = body["payload"]["history"]
    for _ in range(34):
        cursor = cursor["deeper"]
    assert cursor == {"public": "must survive"}
    assert "must disappear" not in json.dumps(body)


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


def test_list_mine_includes_experiment_deadline_for_local_reminders(
    client, isolated_store, sample_payload,
):
    out = isolated_store.create(
        query="q", b_id="b", lang="zh", payload=sample_payload, model="m",
        creator_anon_id="A",
    )
    isolated_store.record_followup(
        report_id=out["id"], anon_id="A", action_status="planned",
        experiment={"hypothesis": "h", "status": "planned", "deadline": "2026-07-15"},
    )
    body = client.get("/api/reports/mine", headers={"X-Anon-Id": "A"}).json()
    assert body["items"][0]["experiment_status"] == "planned"
    assert body["items"][0]["experiment_deadline"] == "2026-07-15"


def test_list_by_owner_includes_experiment_deadline_for_cross_device_reminders(
    isolated_store, sample_payload,
):
    out = isolated_store.create(
        query="q", b_id="b", lang="zh", payload=sample_payload, model="m",
        creator_anon_id="A",
    )
    isolated_store.record_followup(
        report_id=out["id"], anon_id="A", action_status="in_progress",
        experiment={"hypothesis": "h", "status": "in_progress", "deadline": "2026-07-16"},
    )
    isolated_store.claim_by_anon("A", "user-1")
    item = isolated_store.list_by_owner("user-1")[0]
    assert item["experiment_status"] == "in_progress"
    assert item["experiment_deadline"] == "2026-07-16"


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


def test_followup_publication_consent_api_is_explicit_and_revocable(
    client, isolated_store, sample_payload,
):
    out = isolated_store.create(
        query="private question", b_id="b1", lang="zh",
        payload=sample_payload, model="m", creator_anon_id="owner",
    )
    url = f"/api/report/{out['id']}/followup"
    headers = {"X-Anon-Id": "owner"}

    private = client.post(
        url, headers=headers,
        json={"action_status": "tried", "outcome": "worked"},
    )
    assert private.status_code == 200
    assert private.json()["publish_to_insights"] is False

    ambiguous = client.post(
        url, headers=headers,
        json={
            "action_status": "tried", "outcome": "worked",
            "publish_to_insights": "true",
        },
    )
    assert ambiguous.status_code == 422

    opted_in = client.post(
        url, headers=headers,
        json={
            "action_status": "tried", "outcome": "worked",
            "publish_to_insights": True,
        },
    )
    assert opted_in.json()["publish_to_insights"] is True
    assert opted_in.json()["consent_version"] == "insights-public-v1"
    assert opted_in.json()["consented_at"]
    assert opted_in.json()["withdrawn_at"] is None
    assert client.get(url, headers=headers).json()["followup"][
        "publish_to_insights"
    ] is True

    preserved = client.post(
        url, headers=headers,
        json={"action_status": "tried", "outcome": "worked"},
    )
    assert preserved.json()["publish_to_insights"] is True

    revoked = client.post(
        url, headers=headers,
        json={
            "action_status": "tried", "outcome": "worked",
            "publish_to_insights": False,
        },
    )
    assert revoked.json()["publish_to_insights"] is False
    assert revoked.json()["consent_version"] == "insights-public-v1"
    assert revoked.json()["consented_at"]
    assert revoked.json()["withdrawn_at"]


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
