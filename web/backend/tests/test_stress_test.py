"""Tests for feature E — structural stress-test (Session ***REMOVED***18).

Three layers:
  1. Unit — validate_claim, _coerce_verdict, coerce_result pure functions.
  2. Integration — TestClient against a sub-app mounting only the
     stress_test router, with llm_client mocked (no real network).
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services import stress_test_service as sts  ***REMOVED*** noqa: E402


***REMOVED*** ============================================================== ***REMOVED***
***REMOVED*** Layer 1 — unit tests                                           ***REMOVED***
***REMOVED*** ============================================================== ***REMOVED***


***REMOVED*** --------- validate_claim --------- ***REMOVED***


def test_validate_claim_normal():
    out = sts.validate_claim("  我们是中国版的 Notion  ")
    assert out == "我们是中国版的 Notion"


def test_validate_claim_empty_raises():
    with pytest.raises(ValueError):
        sts.validate_claim("")
    with pytest.raises(ValueError):
        sts.validate_claim("   ")


def test_validate_claim_too_short_raises():
    with pytest.raises(ValueError):
        sts.validate_claim("abc")  ***REMOVED*** 3 chars < CLAIM_MIN_LEN


def test_validate_claim_too_long_raises():
    with pytest.raises(ValueError):
        sts.validate_claim("x" * (sts.CLAIM_MAX_LEN + 1))


def test_validate_claim_non_str_raises():
    with pytest.raises(ValueError):
        sts.validate_claim(12345)
    with pytest.raises(ValueError):
        sts.validate_claim(None)


***REMOVED*** --------- _coerce_verdict --------- ***REMOVED***


def test_coerce_verdict_exact_enum():
    assert sts._coerce_verdict("PASS") == "PASS"
    assert sts._coerce_verdict("FAIL") == "FAIL"
    assert sts._coerce_verdict("CONDITIONAL") == "CONDITIONAL"


def test_coerce_verdict_case_insensitive():
    assert sts._coerce_verdict("pass") == "PASS"
    assert sts._coerce_verdict("  Conditional ") == "CONDITIONAL"


def test_coerce_verdict_synonyms():
    assert sts._coerce_verdict("passed") == "PASS"
    assert sts._coerce_verdict("INVALID") == "FAIL"
    assert sts._coerce_verdict("partial") == "CONDITIONAL"


def test_coerce_verdict_illegal_returns_none():
    assert sts._coerce_verdict("MAYBE") is None
    assert sts._coerce_verdict("") is None
    assert sts._coerce_verdict(42) is None
    assert sts._coerce_verdict(None) is None


***REMOVED*** --------- coerce_result --------- ***REMOVED***


def _good_raw():
    return {
        "source": "Notion",
        "target": "我们的产品",
        "structural_correspondences": [
            {"claim": "都靠 PLG 增长", "stress_result": "成立", "holds": True},
            {"claim": "都有网络效应", "stress_result": "中国市场不成立", "holds": False},
        ],
        "weakest_link": "网络效应在中国不成立",
        "verdict": "CONDITIONAL",
        "verdict_reason": "部分对应成立但护城河存疑。",
    }


def test_coerce_result_normal():
    out = sts.coerce_result(_good_raw())
    assert out is not None
    assert out["source"] == "Notion"
    assert out["verdict"] == "CONDITIONAL"
    assert len(out["structural_correspondences"]) == 2
    assert out["structural_correspondences"][1]["holds"] is False


def test_coerce_result_not_dict_returns_none():
    assert sts.coerce_result(None) is None
    assert sts.coerce_result("FAIL") is None
    assert sts.coerce_result(["a", "b"]) is None


def test_coerce_result_illegal_verdict_falls_back():
    raw = _good_raw()
    raw["verdict"] = "DEFINITELY_TRUE"  ***REMOVED*** illegal, not a synonym
    out = sts.coerce_result(raw)
    assert out is not None
    ***REMOVED*** Mixed holds → CONDITIONAL fallback.
    assert out["verdict"] == "CONDITIONAL"
    assert "推导" in out["verdict_reason"]


def test_coerce_result_illegal_verdict_all_hold_passes():
    raw = _good_raw()
    raw["verdict"] = None
    for c in raw["structural_correspondences"]:
        c["holds"] = True
    out = sts.coerce_result(raw)
    assert out["verdict"] == "PASS"


def test_coerce_result_illegal_verdict_none_hold_fails():
    raw = _good_raw()
    del raw["verdict"]
    for c in raw["structural_correspondences"]:
        c["holds"] = False
    out = sts.coerce_result(raw)
    assert out["verdict"] == "FAIL"


def test_coerce_result_missing_fields_filled():
    ***REMOVED*** Only correspondences present — everything else missing.
    raw = {
        "structural_correspondences": [
            {"claim": "唯一一条", "holds": True},
        ]
    }
    out = sts.coerce_result(raw)
    assert out is not None
    assert out["source"] == "（未识别）"
    assert out["target"] == "（未识别）"
    assert out["weakest_link"].startswith("（")
    ***REMOVED*** holds True → no-corr-fails branch; single holds True → PASS.
    assert out["verdict"] == "PASS"
    ***REMOVED*** Missing stress_result gets a placeholder.
    assert out["structural_correspondences"][0]["stress_result"].startswith("（")


def test_coerce_result_empty_and_no_verdict_returns_none():
    ***REMOVED*** No correspondences AND no verdict → unrecoverable.
    assert sts.coerce_result({}) is None
    assert sts.coerce_result({"structural_correspondences": []}) is None
    assert sts.coerce_result({"source": "x", "target": "y"}) is None


def test_coerce_result_malformed_correspondences_filtered():
    raw = {
        "verdict": "FAIL",
        "verdict_reason": "崩了",
        "structural_correspondences": [
            "not a dict",
            {"no_claim": True},
            {"claim": "", "holds": True},  ***REMOVED*** empty claim
            {"claim": "有效一条", "stress_result": "崩", "holds": False},
        ],
    }
    out = sts.coerce_result(raw)
    assert out is not None
    ***REMOVED*** Only the one valid entry survives.
    assert len(out["structural_correspondences"]) == 1
    assert out["structural_correspondences"][0]["claim"] == "有效一条"


def test_coerce_result_holds_only_true_when_explicitly_true():
    ***REMOVED*** holds = "true" string / 1 / missing → all coerced to False.
    raw = {
        "verdict": "PASS",
        "verdict_reason": "ok",
        "structural_correspondences": [
            {"claim": "a", "holds": "true"},
            {"claim": "b", "holds": 1},
            {"claim": "c"},
        ],
    }
    out = sts.coerce_result(raw)
    assert all(c["holds"] is False for c in out["structural_correspondences"])


def test_coerce_result_caps_correspondences():
    raw = {
        "verdict": "FAIL",
        "verdict_reason": "x",
        "structural_correspondences": [
            {"claim": f"c{i}", "holds": False} for i in range(50)
        ],
    }
    out = sts.coerce_result(raw)
    assert len(out["structural_correspondences"]) == sts.MAX_CORRESPONDENCES


***REMOVED*** --------- build_precedent_query --------- ***REMOVED***


def test_build_precedent_query_normal():
    q = sts.build_precedent_query("网络效应在中国市场不成立", "我们的产品")
    assert "网络效应" in q
    assert "我们的产品" in q


def test_build_precedent_query_no_target():
    q = sts.build_precedent_query("规模假设崩了")
    assert q == "规模假设崩了"


def test_build_precedent_query_placeholder_returns_none():
    ***REMOVED*** The placeholder coerce_result emits when LLM gave nothing.
    assert sts.build_precedent_query("（模型未指出最薄弱环节）") is None


def test_build_precedent_query_empty_and_nonstr_returns_none():
    assert sts.build_precedent_query("") is None
    assert sts.build_precedent_query("   ") is None
    assert sts.build_precedent_query(None) is None
    assert sts.build_precedent_query(123) is None


def test_build_precedent_query_placeholder_target_skipped():
    q = sts.build_precedent_query("有效薄弱环节", "（未识别）")
    assert q == "有效薄弱环节"


***REMOVED*** --------- coerce_precedent --------- ***REMOVED***


def _kb_hit():
    return {
        "id": "ph-001",
        "name": "种群崩溃",
        "domain": "生态学",
        "description": "猎物耗尽时捕食者种群骤降",
        "relevance": 0.72,
        "cross_domain": True,
    }


def test_coerce_precedent_normal():
    out = sts.coerce_precedent(
        {"failure_precedent": "猎物耗尽后种群在数月内崩溃。"}, _kb_hit()
    )
    assert out is not None
    assert out["phenomenon_id"] == "ph-001"
    assert out["phenomenon_name"] == "种群崩溃"
    assert out["domain"] == "生态学"
    assert out["relevance"] == 0.72
    assert "崩溃" in out["failure_precedent"]


def test_coerce_precedent_no_failure_text_returns_none():
    assert sts.coerce_precedent({}, _kb_hit()) is None
    assert sts.coerce_precedent({"failure_precedent": ""}, _kb_hit()) is None
    assert sts.coerce_precedent({"failure_precedent": 42}, _kb_hit()) is None
    assert sts.coerce_precedent(None, _kb_hit()) is None


def test_coerce_precedent_bad_phenomenon_returns_none():
    raw = {"failure_precedent": "有效文本"}
    ***REMOVED*** Missing id.
    assert sts.coerce_precedent(raw, {"name": "x"}) is None
    ***REMOVED*** Missing name.
    assert sts.coerce_precedent(raw, {"id": "x"}) is None
    ***REMOVED*** Not a dict.
    assert sts.coerce_precedent(raw, None) is None


def test_coerce_precedent_missing_optional_fields_filled():
    hit = {"id": "ph-9", "name": "现象", "failure_precedent": "ignored"}
    out = sts.coerce_precedent({"failure_precedent": "崩了"}, hit)
    assert out["domain"] == "（未知领域）"
    assert out["description"] == ""
    assert out["relevance"] is None


***REMOVED*** --------- _pick_precedent_hit --------- ***REMOVED***


def test_pick_precedent_hit_prefers_cross_domain():
    results = [
        {"id": "a", "relevance": 0.9, "cross_domain": False},
        {"id": "b", "relevance": 0.6, "cross_domain": True},
    ]
    ***REMOVED*** Same-domain 0.9 loses to cross-domain 0.6.
    assert sts._pick_precedent_hit(results)["id"] == "b"


def test_pick_precedent_hit_below_floor_returns_none():
    results = [{"id": "a", "relevance": 0.3, "cross_domain": True}]
    assert sts._pick_precedent_hit(results) is None


def test_pick_precedent_hit_falls_back_to_best_when_no_cross_domain():
    results = [
        {"id": "a", "relevance": 0.6, "cross_domain": False},
        {"id": "b", "relevance": 0.8, "cross_domain": False},
    ]
    assert sts._pick_precedent_hit(results)["id"] == "b"


def test_pick_precedent_hit_empty_or_bad_returns_none():
    assert sts._pick_precedent_hit([]) is None
    assert sts._pick_precedent_hit(None) is None
    assert sts._pick_precedent_hit(["junk", {"no_id": 1}]) is None


***REMOVED*** --------- enrich_with_precedent (degradation) --------- ***REMOVED***


def test_enrich_no_search_svc_degrades():
    result = sts.coerce_result(_good_raw())
    out = asyncio.run(sts.enrich_with_precedent(result, None))
    assert out["precedent"] is None


def test_enrich_search_raises_degrades():
    class _Boom:
        def search(self, *a, **k):
            raise RuntimeError("index down")

    result = sts.coerce_result(_good_raw())
    out = asyncio.run(sts.enrich_with_precedent(result, _Boom()))
    assert out["precedent"] is None


def test_enrich_no_hit_degrades():
    class _Empty:
        def search(self, *a, **k):
            return []

    result = sts.coerce_result(_good_raw())
    out = asyncio.run(sts.enrich_with_precedent(result, _Empty()))
    assert out["precedent"] is None


***REMOVED*** ============================================================== ***REMOVED***
***REMOVED*** Layer 2 — integration tests (TestClient + mocked llm_client)   ***REMOVED***
***REMOVED*** ============================================================== ***REMOVED***


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """Reset slowapi's in-memory counters before each test.

    The endpoint is decorated with a 10/minute limit; without a reset the
    later tests in this file (now > 10 POSTs) would trip a 429.
    """
    try:
        from services.rate_limit import limiter

        if limiter is not None:
            limiter.reset()
    except Exception:
        pass
    yield


@pytest.fixture
def app():
    from api import stress_test as st_api

    a = FastAPI()
    a.include_router(st_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_llm(monkeypatch):
    """Helper to stub the llm_client used by both api + service modules.

    Returns a setter: call set(available=..., json_return=...).
    `json_return` may be a single value (returned for every complete_json
    call) or a list (consumed call-by-call — the stress test makes one call
    and the precedent enrichment makes a second).
    """
    from api import stress_test as st_api
    from services import stress_test_service as svc

    def _set(available: bool, json_return=None):
        ***REMOVED*** llm_available() is called by the API module.
        monkeypatch.setattr(
            st_api.llm_client, "llm_available", lambda: available
        )

        if isinstance(json_return, list):
            queue = list(json_return)

            async def _fake_complete_json(**kwargs):
                return queue.pop(0) if queue else None
        else:
            async def _fake_complete_json(**kwargs):
                return json_return

        ***REMOVED*** complete_json is called by the service module.
        monkeypatch.setattr(
            svc.llm_client, "complete_json", _fake_complete_json
        )

    return _set


@pytest.fixture
def mock_search(monkeypatch):
    """Stub the live KB search engine reachable via `main.app_state`.

    Returns a setter: call set(results) — the endpoint will see a search
    service whose .search() yields those results. set(None) makes app_state
    have no search service (degraded path).
    """
    import main as main_mod

    def _set(results):
        if results is None:
            main_mod.app_state.pop("search", None)
            return

        class _FakeSearch:
            def search(self, query, top_k=12):
                return results

        main_mod.app_state["search"] = _FakeSearch()

    yield _set
    main_mod.app_state.pop("search", None)


***REMOVED*** Strong cross-domain KB hit used by precedent integration tests.
def _kb_search_results():
    return [
        {
            "id": "ph-eco-1",
            "name": "种群崩溃",
            "domain": "生态学",
            "type_id": "tip",
            "description": "猎物耗尽时捕食者种群骤降",
            "score": 0.8,
            "relevance": 0.78,
            "cross_domain": True,
        }
    ]


def test_endpoint_success(client, mock_llm):
    mock_llm(available=True, json_return=_good_raw())
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["claim"] == "我们是中国版的 Notion"
    assert body["verdict"] == "CONDITIONAL"
    assert body["source"] == "Notion"
    assert len(body["structural_correspondences"]) == 2


def test_endpoint_llm_unavailable_503(client, mock_llm):
    mock_llm(available=False)
    resp = client.post("/api/stress-test", json={"claim": "这是一个有效的类比判断"})
    assert resp.status_code == 503
    assert "LLM" in resp.json()["detail"]


def test_endpoint_llm_returns_none_503(client, mock_llm):
    ***REMOVED*** LLM available but the call yields None (network/parse failure).
    mock_llm(available=True, json_return=None)
    resp = client.post("/api/stress-test", json={"claim": "这是一个有效的类比判断"})
    assert resp.status_code == 503


def test_endpoint_llm_garbage_guardrailed_503(client, mock_llm):
    ***REMOVED*** LLM available but returns unrecoverable garbage → coerce_result None.
    mock_llm(available=True, json_return={"random": "noise", "foo": 1})
    resp = client.post("/api/stress-test", json={"claim": "这是一个有效的类比判断"})
    assert resp.status_code == 503


def test_endpoint_malformed_llm_still_coerced(client, mock_llm):
    ***REMOVED*** Garbage verdict + partly-broken correspondences → guardrail recovers.
    mock_llm(
        available=True,
        json_return={
            "source": "S",
            "target": "T",
            "verdict": "TOTALLY_BOGUS",
            "structural_correspondences": [
                "junk",
                {"claim": "一条成立的", "holds": True},
            ],
        },
    )
    resp = client.post("/api/stress-test", json={"claim": "这是一个有效的类比判断"})
    assert resp.status_code == 200
    body = resp.json()
    ***REMOVED*** Bogus verdict + single holds-True corr → PASS fallback.
    assert body["verdict"] in sts.VERDICTS
    assert len(body["structural_correspondences"]) == 1


def test_endpoint_empty_claim_422(client, mock_llm):
    mock_llm(available=True, json_return=_good_raw())
    resp = client.post("/api/stress-test", json={"claim": ""})
    assert resp.status_code == 422


def test_endpoint_whitespace_claim_422(client, mock_llm):
    ***REMOVED*** Passes pydantic min_length=1 but validate_claim rejects after strip.
    mock_llm(available=True, json_return=_good_raw())
    resp = client.post("/api/stress-test", json={"claim": "        "})
    assert resp.status_code == 422


def test_endpoint_too_long_claim_422(client, mock_llm):
    mock_llm(available=True, json_return=_good_raw())
    resp = client.post(
        "/api/stress-test", json={"claim": "x" * (sts.CLAIM_MAX_LEN + 50)}
    )
    assert resp.status_code == 422


def test_endpoint_missing_claim_422(client, mock_llm):
    mock_llm(available=True, json_return=_good_raw())
    resp = client.post("/api/stress-test", json={})
    assert resp.status_code == 422


***REMOVED*** --------- precedent integration --------- ***REMOVED***


def test_endpoint_success_with_precedent(client, mock_llm, mock_search):
    ***REMOVED*** 1st LLM call → stress result; 2nd → precedent failure text.
    mock_llm(
        available=True,
        json_return=[
            _good_raw(),
            {"failure_precedent": "猎物耗尽后种群在数月内崩溃，规模假设同样脆弱。"},
        ],
    )
    mock_search(_kb_search_results())
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "CONDITIONAL"
    prec = body["precedent"]
    assert prec is not None
    assert prec["phenomenon_id"] == "ph-eco-1"
    assert prec["phenomenon_name"] == "种群崩溃"
    assert prec["domain"] == "生态学"
    assert "崩溃" in prec["failure_precedent"]


def test_endpoint_success_search_unavailable_degrades(client, mock_llm, mock_search):
    ***REMOVED*** No search service in app_state → precedent null, verdict still emitted.
    mock_llm(available=True, json_return=_good_raw())
    mock_search(None)
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "CONDITIONAL"
    assert body["precedent"] is None


def test_endpoint_success_no_kb_hit_degrades(client, mock_llm, mock_search):
    ***REMOVED*** Search returns nothing structurally close → precedent null.
    mock_llm(available=True, json_return=_good_raw())
    mock_search([])
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["precedent"] is None


def test_endpoint_precedent_llm_garbage_degrades(client, mock_llm, mock_search):
    ***REMOVED*** KB hit found but precedent LLM returns unusable JSON → precedent null,
    ***REMOVED*** the stress test itself still succeeds.
    mock_llm(
        available=True,
        json_return=[_good_raw(), {"noise": "no failure_precedent here"}],
    )
    mock_search(_kb_search_results())
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["verdict"] == "CONDITIONAL"
    assert body["precedent"] is None


def test_endpoint_precedent_weak_relevance_degrades(client, mock_llm, mock_search):
    ***REMOVED*** KB hit exists but relevance below the floor → not a real precedent.
    weak = _kb_search_results()
    weak[0]["relevance"] = 0.3
    mock_llm(
        available=True,
        json_return=[_good_raw(), {"failure_precedent": "不该被用到"}],
    )
    mock_search(weak)
    resp = client.post("/api/stress-test", json={"claim": "我们是中国版的 Notion"})
    assert resp.status_code == 200
    assert resp.json()["precedent"] is None
