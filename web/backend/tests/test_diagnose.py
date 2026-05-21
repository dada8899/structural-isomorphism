"""Tests for feature F — structural diagnosis (Session ***REMOVED***18).

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

from services import diagnose_service as ds  ***REMOVED*** noqa: E402


***REMOVED*** ===========================================================================
***REMOVED*** Unit — validate_situation
***REMOVED*** ===========================================================================


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
        ds.validate_situation(12345)  ***REMOVED*** type: ignore[arg-type]


***REMOVED*** ===========================================================================
***REMOVED*** Unit — _coerce_state_id (whitelist guardrail)
***REMOVED*** ===========================================================================


def test_coerce_state_id_accepts_whitelist_id():
    assert ds._coerce_state_id("hysteresis_trap") == "hysteresis_trap"


def test_coerce_state_id_case_insensitive():
    assert ds._coerce_state_id("  Cascade_Fragility ") == "cascade_fragility"


def test_coerce_state_id_accepts_chinese_name():
    ***REMOVED*** LLM sometimes returns the display name instead of the id.
    assert ds._coerce_state_id("阻尼收敛（稳定）") == "damped_convergence"


def test_coerce_state_id_rejects_invented_state():
    assert ds._coerce_state_id("quantum_collapse_state") is None


def test_coerce_state_id_rejects_non_str():
    assert ds._coerce_state_id(None) is None
    assert ds._coerce_state_id(42) is None


***REMOVED*** ===========================================================================
***REMOVED*** Unit — _coerce_confidence (boundary clamping)
***REMOVED*** ===========================================================================


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


***REMOVED*** ===========================================================================
***REMOVED*** Unit — coerce_result (schema coercion / degradation)
***REMOVED*** ===========================================================================


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
    ***REMOVED*** Missing confidence → neutral default.
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


***REMOVED*** ===========================================================================
***REMOVED*** Integration — POST /api/diagnose
***REMOVED*** ===========================================================================


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
    """
    from services import llm_client

    state = {"available": True, "raw": _good_raw()}

    def _available() -> bool:
        return state["available"]

    async def _complete_json(**_kwargs):
        return state["raw"]

    monkeypatch.setattr(llm_client, "llm_available", _available)
    monkeypatch.setattr(llm_client, "complete_json", _complete_json)
    return state


def test_endpoint_success(client, mock_llm):
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷，加人反而更慢。"})
    assert r.status_code == 200
    body = r.json()
    assert body["primary_state"]["state_id"] == "hysteresis_trap"
    assert body["primary_state"]["confidence"] == 0.82
    assert body["situation"].startswith("一个 30 人公司")
    assert "signals_to_watch" in body


def test_endpoint_503_when_llm_unavailable(client, mock_llm):
    mock_llm["available"] = False
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_503_when_llm_returns_none(client, mock_llm):
    mock_llm["raw"] = None
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_503_when_llm_returns_illegal_state(client, mock_llm):
    ***REMOVED*** Guardrail: an LLM that invents a state must NOT leak through — the
    ***REMOVED*** service coerces to None, the endpoint degrades to 503.
    mock_llm["raw"] = {
        "primary_state": {"state_id": "totally_made_up", "confidence": 0.9},
        "reasoning": "x",
    }
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 503


def test_endpoint_illegal_secondary_does_not_break_response(client, mock_llm):
    raw = _good_raw()
    raw["secondary_state"] = {"state_id": "nonsense"}
    mock_llm["raw"] = raw
    r = client.post("/api/diagnose", json={"situation": "一个 30 人公司的效率塌陷情况。"})
    assert r.status_code == 200
    assert r.json()["secondary_state"] is None


def test_endpoint_rejects_empty_situation(client, mock_llm):
    r = client.post("/api/diagnose", json={"situation": ""})
    assert r.status_code == 422


def test_endpoint_rejects_whitespace_only(client, mock_llm):
    ***REMOVED*** Passes pydantic min_length=1, rejected by validate_situation after strip.
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
