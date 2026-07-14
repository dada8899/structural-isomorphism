"""Tests for feature F — structural diagnosis (Session #18).

Two layers in one file:
  1. Unit — whitelist coercion, schema coercion / degradation, confidence
     clamping (pure functions in services.diagnose_service).
  2. Integration — TestClient against a sub-app mounting api.diagnose only,
     with services.llm_client monkeypatched (no real LLM call).
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

from services import diagnose_service as ds  # noqa: E402


# ===========================================================================
# Unit — validate_situation
# ===========================================================================


def test_validate_situation_strips_and_returns():
    assert ds.validate_situation("  一个 30 人公司的效率塌陷  ") == "一个 30 人公司的效率塌陷"


def test_validate_situation_rejects_too_short():
    with pytest.raises(ValueError):
        ds.validate_situation("太短了")


def test_validate_situation_rejects_too_long():
    with pytest.raises(ValueError):
        ds.validate_situation("公" * (ds.SITUATION_MAX_LEN + 1))


def test_validate_situation_rejects_non_str():
    with pytest.raises(ValueError):
        ds.validate_situation(12345)  # type: ignore[arg-type]


# ===========================================================================
# Unit — _coerce_state_id (whitelist guardrail)
# ===========================================================================


def test_coerce_state_id_accepts_whitelist_id():
    assert ds._coerce_state_id("hysteresis_trap") == "hysteresis_trap"


def test_coerce_state_id_case_insensitive():
    assert ds._coerce_state_id("  Cascade_Fragility ") == "cascade_fragility"


def test_coerce_state_id_accepts_chinese_name():
    # LLM sometimes returns the display name instead of the id.
    assert ds._coerce_state_id("阻尼收敛（稳定）") == "damped_convergence"


def test_coerce_state_id_rejects_invented_state():
    assert ds._coerce_state_id("quantum_collapse_state") is None


def test_coerce_state_id_rejects_non_str():
    assert ds._coerce_state_id(None) is None
    assert ds._coerce_state_id(42) is None


# ===========================================================================
# Unit — _coerce_confidence (boundary clamping)
# ===========================================================================


def test_coerce_confidence_in_range():
    assert ds._coerce_confidence(0.73) == 0.73


def test_coerce_confidence_percentage_scaled():
    assert ds._coerce_confidence(80) == 0.8


def test_coerce_confidence_clamps_high():
    assert ds._coerce_confidence(250) == 1.0


def test_coerce_confidence_clamps_negative():
    assert ds._coerce_confidence(-0.5) == 0.0


def test_coerce_confidence_non_numeric_defaults():
    assert ds._coerce_confidence("very sure") == 0.5
    assert ds._coerce_confidence(None) == 0.5


# ===========================================================================
# Unit — coerce_result (schema coercion / degradation)
# ===========================================================================


def _good_raw() -> dict:
    return {
        "primary_state": {"state_id": "hysteresis_trap", "confidence": 0.82},
        "secondary_state": {"state_id": "cascade_fragility"},
        "reasoning": "改了管理方式但旧的协作模式还在。",
        "evolution": "不干预会继续卡在旧状态。",
        "signals_to_watch": ["新流程的实际采用率", "返工率"],
        "recommendations": ["打破路径依赖", "重建协作回路"],
    }


def test_coerce_result_happy_path():
    out = ds.coerce_result(_good_raw())
    assert out is not None
    assert out["primary_state"]["state_id"] == "hysteresis_trap"
    assert out["primary_state"]["name"] == ds.STRUCTURAL_STATES["hysteresis_trap"]["name"]
    assert out["primary_state"]["confidence"] == 0.82
    assert out["secondary_state"]["state_id"] == "cascade_fragility"
    assert len(out["signals_to_watch"]) == 2
    assert len(out["recommendations"]) == 2


def test_coerce_result_none_when_not_dict():
    assert ds.coerce_result("not a dict") is None
    assert ds.coerce_result(None) is None
    assert ds.coerce_result([1, 2]) is None


def test_coerce_result_none_when_primary_state_id_illegal():
    raw = _good_raw()
    raw["primary_state"]["state_id"] = "made_up_state"
    assert ds.coerce_result(raw) is None


def test_coerce_result_none_when_primary_missing():
    raw = _good_raw()
    del raw["primary_state"]
    assert ds.coerce_result(raw) is None


def test_coerce_result_drops_illegal_secondary():
    raw = _good_raw()
    raw["secondary_state"] = {"state_id": "garbage"}
    out = ds.coerce_result(raw)
    assert out is not None
    assert out["secondary_state"] is None


def test_coerce_result_drops_secondary_equal_to_primary():
    raw = _good_raw()
    raw["secondary_state"] = {"state_id": "hysteresis_trap"}
    out = ds.coerce_result(raw)
    assert out is not None
    assert out["secondary_state"] is None


def test_coerce_result_fills_missing_text_fields():
    raw = {"primary_state": {"state_id": "damped_convergence"}}
    out = ds.coerce_result(raw)
    assert out is not None
    assert out["reasoning"].startswith("（模型未")
    assert out["evolution"].startswith("（模型未")
    assert out["signals_to_watch"] == []
    assert out["recommendations"] == []
    # Missing confidence → neutral default.
    assert out["primary_state"]["confidence"] == 0.5


def test_coerce_result_caps_runaway_lists():
    raw = _good_raw()
    raw["signals_to_watch"] = [f"信号{i}" for i in range(30)]
    raw["recommendations"] = [f"建议{i}" for i in range(30)]
    out = ds.coerce_result(raw)
    assert len(out["signals_to_watch"]) == ds.MAX_SIGNALS
    assert len(out["recommendations"]) == ds.MAX_RECOMMENDATIONS


def test_coerce_result_filters_non_string_list_items():
    raw = _good_raw()
    raw["signals_to_watch"] = ["有效信号", "", 123, None, "  ", "另一个"]
    out = ds.coerce_result(raw)
    assert out["signals_to_watch"] == ["有效信号", "另一个"]


# ===========================================================================
# Unit — build_reference_query (state → KB search query)
# ===========================================================================


def test_build_reference_query_leads_with_structure():
    q = ds.build_reference_query("cascade_fragility", "我们公司依赖一个核心客户")
    # The structural phrasing of the state must lead the query.
    assert q.startswith(ds.STRUCTURAL_STATES["cascade_fragility"]["structure_query"])
    # The user's words are appended for grounding.
    assert "核心客户" in q


def test_build_reference_query_unknown_state_returns_empty():
    assert ds.build_reference_query("made_up_state", "随便什么处境") == ""


def test_build_reference_query_truncates_long_situation():
    q = ds.build_reference_query("damped_convergence", "处" * 5000)
    # structure_query + at most _SITUATION_QUERY_CHARS of user text.
    structure = ds.STRUCTURAL_STATES["damped_convergence"]["structure_query"]
    assert len(q) <= len(structure) + 1 + ds._SITUATION_QUERY_CHARS


def test_build_reference_query_structure_only_when_no_situation():
    q = ds.build_reference_query("hysteresis_trap", "   ")
    assert q == ds.STRUCTURAL_STATES["hysteresis_trap"]["structure_query"]


# ===========================================================================
# Unit — _coerce_reference_case (reference_case schema guardrail)
# ===========================================================================


def _good_hit() -> dict:
    return {
        "id": "phen_0421",
        "name": "银行挤兑",
        "domain": "金融",
        "type_id": "T7",
        "description": "储户因预期违约而集中提款，提款本身导致违约。",
        "relevance": 0.81,
        "cross_domain": True,
    }


def test_coerce_reference_case_happy_path():
    out = ds._coerce_reference_case(_good_hit())
    assert out is not None
    assert out["id"] == "phen_0421"
    assert out["name"] == "银行挤兑"
    assert out["domain"] == "金融"
    assert out["relevance"] == 0.81
    assert out["source"] == "kb_search"


def test_coerce_reference_case_rejects_non_dict():
    assert ds._coerce_reference_case("not a dict") is None
    assert ds._coerce_reference_case(None) is None


def test_coerce_reference_case_rejects_missing_id_or_name():
    h = _good_hit()
    h["id"] = ""
    assert ds._coerce_reference_case(h) is None
    h2 = _good_hit()
    del h2["name"]
    assert ds._coerce_reference_case(h2) is None


def test_coerce_reference_case_clamps_bad_relevance():
    h = _good_hit()
    h["relevance"] = "not a number"
    out = ds._coerce_reference_case(h)
    assert out is not None
    assert out["relevance"] == 0.0
    h2 = _good_hit()
    h2["relevance"] = 5.0
    assert ds._coerce_reference_case(h2)["relevance"] == 1.0


# ===========================================================================
# Unit — fetch_reference_case (search degradation + fallback)
# ===========================================================================


class _FakeSearch:
    """Minimal stand-in for SearchService — returns / raises on demand."""

    def __init__(self, hits=None, raises=False):
        self._hits = hits or []
        self._raises = raises
        self.last_query = None

    def search(self, query, top_k=12, min_score=0.05):
        self.last_query = query
        if self._raises:
            raise RuntimeError("search backend down")
        return self._hits


def test_fetch_reference_case_returns_search_hit():
    svc = _FakeSearch(hits=[_good_hit()])
    out = ds.fetch_reference_case("self_fulfilling_run", "信心崩塌的处境", svc)
    assert out is not None
    assert out["id"] == "phen_0421"
    assert out["source"] == "kb_search"


def test_fetch_reference_case_prefers_cross_domain_hit():
    same = _good_hit()
    same["id"] = "phen_same"
    same["cross_domain"] = False
    cross = _good_hit()
    cross["id"] = "phen_cross"
    cross["cross_domain"] = True
    svc = _FakeSearch(hits=[same, cross])
    out = ds.fetch_reference_case("cascade_fragility", "处境描述", svc)
    assert out["id"] == "phen_cross"


def test_fetch_reference_case_drops_low_relevance_hits():
    weak = _good_hit()
    weak["relevance"] = 0.20  # below _REFERENCE_MIN_RELEVANCE
    svc = _FakeSearch(hits=[weak])
    out = ds.fetch_reference_case("cascade_fragility", "处境描述", svc)
    # Falls back to the class hub (a string, no id).
    assert out is not None
    assert out["source"] == "class_hub"
    assert out["id"] == ""


def test_fetch_reference_case_falls_back_when_no_search_svc():
    out = ds.fetch_reference_case("self_organized_criticality", "处境", None)
    assert out is not None
    assert out["source"] == "class_hub"
    assert out["name"] == ds.STRUCTURAL_STATES["self_organized_criticality"]["class_hub"]


def test_fetch_reference_case_degrades_when_search_raises():
    svc = _FakeSearch(raises=True)
    out = ds.fetch_reference_case("hysteresis_trap", "处境", svc)
    # Search exploded → fall back to class hub, never raise.
    assert out is not None
    assert out["source"] == "class_hub"


def test_fetch_reference_case_none_when_no_hub_and_no_search():
    # damped_convergence has an empty class_hub → no fallback possible.
    out = ds.fetch_reference_case("damped_convergence", "处境", None)
    assert out is None


def test_fetch_reference_case_unknown_state_returns_none():
    svc = _FakeSearch(hits=[_good_hit()])
    assert ds.fetch_reference_case("made_up_state", "处境", svc) is None


# ===========================================================================
# Integration — POST /api/diagnose
# ===========================================================================


@pytest.fixture
def app():
    from api import diagnose as diagnose_api

    a = FastAPI()
    a.include_router(diagnose_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_llm(monkeypatch):
    """Patch llm_client used inside the diagnose API + service.

    Returns a small helper to configure availability + the raw JSON the
    fake LLM hands back. No network call is ever made.

    The fake `complete_json` echoes a diagnosis for the main call and a
    reference-note JSON for the second (reference-enrichment) call — it
    keys off the presence of "真实现象" in the prompt.
    """
    from services import llm_client

    runtime_raw = _good_raw()
    runtime_raw["primary_state"].pop("confidence")
    state = {
        "available": True,
        "raw": runtime_raw,
        "note": "值得核查恢复时长；若状态变量不同，应放弃这个参照。",
    }

    def _available() -> bool:
        return state["available"]

    async def _complete_json(**kwargs):
        user = kwargs.get("user", "")
        if "知识库候选" in user:  # candidate-note enrichment call
            return {"candidate_note": state["note"]}
        return state["raw"]

    monkeypatch.setattr(llm_client, "llm_available", _available)
    monkeypatch.setattr(llm_client, "complete_json", _complete_json)
    return state


@pytest.fixture
def mock_search():
    """Register a fake search service into main.app_state for the endpoint.

    The diagnose endpoint pulls `app_state["search"]` lazily; here we set
    it to a configurable fake. `state["svc"]` can be reassigned by a test
    before issuing the request. Cleaned up afterwards.
    """
    import main

    state = {"svc": _FakeSearch(hits=[_good_hit()])}

    class _Proxy:
        """Forwards to whatever state['svc'] currently is."""

        def search(self, *a, **kw):
            return state["svc"].search(*a, **kw)

    main.app_state["search"] = _Proxy()
    yield state
    main.app_state.pop("search", None)


def test_endpoint_success(client, mock_llm):
    r = client.post("/api/diagnose", json={
        "situation": "一个 30 人公司的效率塌陷，加人反而更慢。",
        "client_request_id": "diagnose-request-001",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["primary_state"]["state_id"] == "hysteresis_trap"
    assert "confidence" not in body["primary_state"]
    assert body["assessment_kind"] == "structural_state_hypothesis"
    assert body["request_id"] == "diagnose-request-001"
    assert body["contract_version"] == "secondary-tools-v2"
    assert body["evidence"]["evidence_level"] == "candidate"
    assert body["situation"].startswith("一个 30 人公司")
    assert "signals_to_watch" in body


def test_endpoint_rejects_out_of_scope_before_model(client, mock_llm):
    r = client.post("/api/diagnose", json={"situation": "2 + 2 等于多少，请直接告诉我答案"})
    assert r.status_code == 422
    assert r.json()["detail"]["error"] == "out_of_scope"


def test_endpoint_503_when_llm_unavailable(client, mock_llm):
    mock_llm["available"] = False
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_503_when_llm_returns_none(client, mock_llm):
    mock_llm["raw"] = None
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_503_when_llm_returns_illegal_state(client, mock_llm):
    # Guardrail: an LLM that invents a state must NOT leak through — the
    # service coerces to None, the endpoint degrades to 503.
    raw = _good_raw()
    raw["primary_state"] = {"state_id": "totally_made_up"}
    mock_llm["raw"] = raw
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_illegal_secondary_fails_closed(client, mock_llm):
    raw = _good_raw()
    raw["primary_state"].pop("confidence")
    raw["secondary_state"] = {"state_id": "nonsense"}
    mock_llm["raw"] = raw
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_rejects_empty_situation(client, mock_llm):
    r = client.post("/api/diagnose", json={"situation": ""})
    assert r.status_code == 422


def test_endpoint_rejects_whitespace_only(client, mock_llm):
    # Passes pydantic min_length=1, rejected by validate_situation after strip.
    r = client.post("/api/diagnose", json={"situation": "          "})
    assert r.status_code == 422


def test_endpoint_rejects_too_long(client, mock_llm):
    r = client.post(
        "/api/diagnose",
        json={"situation": "公" * (ds.SITUATION_MAX_LEN + 50)},
    )
    assert r.status_code == 422


def test_states_catalogue_endpoint(client):
    r = client.get("/api/diagnose/states")
    assert r.status_code == 200
    states = r.json()["states"]
    assert len(states) == len(ds.STRUCTURAL_STATES)
    assert all("state_id" in s and "name" in s for s in states)


# ===========================================================================
# Integration — reference_case (KB anchor) on POST /api/diagnose
# ===========================================================================


def test_endpoint_includes_candidate_reference_from_search(client, mock_llm, mock_search):
    """A successful diagnosis may carry a source-bound KB candidate."""
    r = client.post(
        "/api/diagnose",
        json={"situation": "一个 30 人公司的效率塌陷，加人反而更慢。"},
    )
    assert r.status_code == 200
    ref = r.json()["candidate_reference"]
    assert ref is not None
    assert ref["id"] == "phen_0421"
    assert ref["retrieval_rank"] == 1
    assert ref["evidence"]["evidence_level"] == "candidate"
    assert ref["candidate_note"] == "值得核查恢复时长;若状态变量不同,应放弃这个参照。"


def test_endpoint_candidate_reference_absent_without_search(client, mock_llm):
    """A class-hub label without a KB record is not surfaced as evidence."""
    r = client.post(
        "/api/diagnose",
        json={"situation": "一个 30 人公司的效率塌陷情况。"},
    )
    assert r.status_code == 200
    assert r.json()["candidate_reference"] is None


def test_endpoint_reference_case_null_when_no_hit_and_no_hub(client, mock_llm, mock_search):
    """Search yields nothing + state has no class_hub → reference_case null.

    damped_convergence has an empty class_hub, so when search returns
    nothing there is no reference to show — the diagnosis still succeeds.
    """
    mock_search["svc"] = _FakeSearch(hits=[])
    raw = _good_raw()
    raw["primary_state"] = {"state_id": "damped_convergence"}
    mock_llm["raw"] = raw
    r = client.post(
        "/api/diagnose",
        json={"situation": "扰动后能自己回到平衡的健康团队。"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["primary_state"]["state_id"] == "damped_convergence"
    assert body["candidate_reference"] is None


def test_endpoint_survives_search_failure(client, mock_llm, mock_search):
    """A search backend that raises must not break the diagnosis."""
    mock_search["svc"] = _FakeSearch(raises=True)
    r = client.post(
        "/api/diagnose",
        json={"situation": "一个 30 人公司的效率塌陷情况。"},
    )
    assert r.status_code == 200
    # Diagnosis still completes, but an unbound class-hub label is not shown.
    assert r.json()["candidate_reference"] is None
