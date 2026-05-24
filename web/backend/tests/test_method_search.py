"""Tests for A1 method-search (Session #18).

Layer 1 — unit: signature coercion, note coercion, ranking, top_n clamp.
Layer 2 — integration: TestClient against the method_search router, with
          llm_client and the search service mocked (no real LLM / no KB).
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

from services import method_search_service as mss  # noqa: E402


# ============================ Layer 1: unit ============================ #

# --- _coerce_signature --- #

def test_coerce_signature_valid():
    raw = {"signature": "  沿局部信息迭代逼近极值  ", "keywords": ["迭代", "局部"]}
    out = mss._coerce_signature(raw, "梯度下降")
    assert out["signature"] == "沿局部信息迭代逼近极值"
    assert out["keywords"] == ["迭代", "局部"]
    assert out["llm"] is True


def test_coerce_signature_none_falls_back_to_method_text():
    """LLM returned None → degrade to the raw method text, llm=False."""
    out = mss._coerce_signature(None, "梯度下降算法")
    assert out["signature"] == "梯度下降算法"
    assert out["keywords"] == []
    assert out["llm"] is False


def test_coerce_signature_malformed_payload():
    """Malformed: signature missing / wrong type / keywords non-list+dirty."""
    # signature is not a string
    assert mss._coerce_signature({"signature": 123}, "m")["llm"] is False
    # empty signature string
    assert mss._coerce_signature({"signature": "   "}, "m")["llm"] is False
    # keywords with non-strings, dups, over-long → cleaned + capped
    raw = {
        "signature": "x",
        "keywords": ["a", "a", 5, None, "b" * 99] + [f"k{i}" for i in range(10)],
    }
    out = mss._coerce_signature(raw, "m")
    assert out["llm"] is True
    assert len(out["keywords"]) <= mss.MAX_KEYWORDS
    assert "a" in out["keywords"] and out["keywords"].count("a") == 1
    assert all(len(k) <= mss.MAX_KEYWORD_LEN for k in out["keywords"])


def test_coerce_signature_caps_long_signature():
    long_sig = "结构" * 500
    out = mss._coerce_signature({"signature": long_sig}, "m")
    assert len(out["signature"]) <= mss.MAX_SIGNATURE_LEN


# --- _coerce_notes --- #

def test_coerce_notes_drops_unknown_ids():
    """LLM may invent ids — only ids in the valid set survive."""
    raw = {"notes": {"p1": "套用说明", "FAKE": "幻觉 id", "p2": "另一条"}}
    out = mss._coerce_notes(raw, {"p1", "p2"})
    assert set(out.keys()) == {"p1", "p2"}
    assert "FAKE" not in out


def test_coerce_notes_malformed_and_empty():
    assert mss._coerce_notes(None, {"p1"}) == {}
    assert mss._coerce_notes({"notes": "not a dict"}, {"p1"}) == {}
    # non-string note value dropped, blank note dropped
    raw = {"notes": {"p1": 42, "p2": "  ", "p3": "ok"}}
    assert mss._coerce_notes(raw, {"p1", "p2", "p3"}) == {"p3": "ok"}


def test_coerce_notes_caps_length():
    raw = {"notes": {"p1": "字" * 999}}
    out = mss._coerce_notes(raw, {"p1"})
    assert len(out["p1"]) <= mss.MAX_NOTE_LEN


# --- build_query --- #

def test_build_query_combines_and_caps():
    sig = {"signature": "迭代逼近极值", "keywords": ["局部信息", "噪声反馈"]}
    q = mss.build_query(sig)
    assert "迭代逼近极值" in q and "局部信息" in q
    assert len(q) <= mss.MAX_QUERY_LEN
    # empty keywords still works
    assert mss.build_query({"signature": "abc", "keywords": []}) == "abc"


# --- normalize_top_n --- #

def test_normalize_top_n_bounds():
    assert mss.normalize_top_n(8) == 8
    assert mss.normalize_top_n(0) == 1          # below floor
    assert mss.normalize_top_n(999) == mss.MAX_TOP_N  # above ceiling
    assert mss.normalize_top_n(None) == mss.DEFAULT_TOP_N
    assert mss.normalize_top_n("bad") == mss.DEFAULT_TOP_N  # wrong type


# --- rank_matches --- #

def test_rank_matches_attaches_notes_and_trims():
    results = [
        {"id": "p1", "name": "N1", "domain": "D1", "type_id": "t",
         "description": "d1", "relevance": 0.9, "score": 0.8},
        {"id": "p2", "name": "N2", "domain": "D2", "type_id": "t",
         "description": "d2", "relevance": 0.7, "score": 0.6},
        {"id": "p3", "name": "N3", "domain": "D3", "type_id": "t",
         "description": "d3", "relevance": 0.5, "score": 0.4},
    ]
    out = mss.rank_matches(results, {"p1": "套用 p1"}, top_n=2)
    assert len(out) == 2  # trimmed
    assert out[0]["apply_note"] == "套用 p1"
    assert out[1]["apply_note"] == ""  # no note → empty string


def test_rank_matches_skips_idless_rows():
    results = [{"name": "no id"}, {"id": "p1", "name": "ok"}]
    out = mss.rank_matches(results, {}, top_n=10)
    assert len(out) == 1 and out[0]["id"] == "p1"


# --- run_method_search degrade path (no LLM, sync helpers) --- #

class _FakeSearch:
    """Minimal SearchService stand-in."""
    def __init__(self, results):
        self._results = results

    def search(self, query, top_k=12):
        return self._results[:top_k]


@pytest.mark.anyio
async def test_run_method_search_degrades_without_llm(monkeypatch):
    """No LLM key → signature = raw method text, no notes, search still runs."""
    from services import llm_client
    monkeypatch.setattr(llm_client, "llm_available", lambda: False)

    fake = _FakeSearch([
        {"id": "p1", "name": "N1", "domain": "D1", "type_id": "t",
         "description": "d1", "relevance": 0.9, "score": 0.8},
    ])
    out = await mss.run_method_search("梯度下降", fake, top_n=5)
    assert out["llm_used"] is False
    assert out["signature"] == "梯度下降"
    assert out["count"] == 1
    assert out["matches"][0]["apply_note"] == ""  # no LLM → no note


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ========================= Layer 2: integration ========================= #

@pytest.fixture
def app():
    """Sub-app exposing only the method_search router."""
    from api import method_search as ms_api
    a = FastAPI()
    a.include_router(ms_api.router, prefix="/api")
    return a


@pytest.fixture
def client(app):
    return TestClient(app)


_SAMPLE_RESULTS = [
    {"id": "p1", "name": "蚁群觅食", "domain": "生物学", "type_id": "T1",
     "description": "蚂蚁通过信息素强化路径", "relevance": 0.88, "score": 0.8},
    {"id": "p2", "name": "城市交通流", "domain": "交通工程", "type_id": "T2",
     "description": "车流在路网中自组织", "relevance": 0.71, "score": 0.6},
]


@pytest.fixture
def patched(monkeypatch):
    """Patch app_state['search'] and llm_client for the endpoint.

    Returns a control dict so each test can flip llm_available / payloads.
    """
    import main as main_mod
    from services import llm_client

    main_mod.app_state["search"] = _FakeSearch(list(_SAMPLE_RESULTS))

    ctrl = {"llm": True}

    async def fake_complete_json(*, system, user, **kw):
        if "结构分析专家" in system:  # signature call
            return {"signature": "在反馈下沿局部信息迭代逼近最优",
                    "keywords": ["迭代", "局部信息"]}
        # note call
        return {"notes": {"p1": "用信息素强化类比方法的更新步",
                          "p2": "把路网当作搜索地形"}}

    monkeypatch.setattr(llm_client, "llm_available", lambda: ctrl["llm"])
    monkeypatch.setattr(llm_client, "complete_json", fake_complete_json)
    yield ctrl
    main_mod.app_state.pop("search", None)


def test_endpoint_success_with_llm(client, patched):
    """Happy path: signature extracted + notes attached."""
    resp = client.post("/api/method/apply", json={"method": "梯度下降算法", "top_n": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_used"] is True
    assert body["signature"] == "在反馈下沿局部信息迭代逼近最优"
    assert body["keywords"] == ["迭代", "局部信息"]
    assert body["count"] == 2
    assert body["matches"][0]["id"] == "p1"
    assert body["matches"][0]["apply_note"]  # note present


def test_endpoint_degrades_when_llm_unavailable(client, patched):
    """LLM off → 200, still returns search results, no notes, no crash."""
    patched["llm"] = False
    resp = client.post("/api/method/apply", json={"method": "梯度下降算法"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_used"] is False
    assert body["signature"] == "梯度下降算法"  # raw method text
    assert body["count"] == 2
    assert all(m["apply_note"] == "" for m in body["matches"])


def test_endpoint_rejects_empty_input(client, patched):
    """Empty / too-short method → 422 from pydantic min_length."""
    assert client.post("/api/method/apply", json={"method": ""}).status_code == 422
    assert client.post("/api/method/apply", json={"method": "ab"}).status_code == 422


def test_endpoint_rejects_overlong_input(client, patched):
    """Over-long method → 422 from pydantic max_length."""
    resp = client.post("/api/method/apply",
                        json={"method": "梯" * (mss.MAX_METHOD_LEN + 50)})
    assert resp.status_code == 422


def test_endpoint_rejects_blank_whitespace(client, patched):
    """Whitespace-only that passes min_length char count → 422 from explicit check."""
    resp = client.post("/api/method/apply", json={"method": "      "})
    assert resp.status_code == 422


def test_endpoint_503_when_search_not_ready(client, monkeypatch):
    """Search service missing → 503."""
    import main as main_mod
    main_mod.app_state.pop("search", None)
    resp = client.post("/api/method/apply", json={"method": "梯度下降"})
    assert resp.status_code == 503


def test_endpoint_top_n_clamped(client, patched):
    """top_n above le=20 rejected by pydantic; valid value honoured."""
    assert client.post("/api/method/apply",
                       json={"method": "梯度下降", "top_n": 99}).status_code == 422
    resp = client.post("/api/method/apply", json={"method": "梯度下降", "top_n": 1})
    assert resp.status_code == 200
    assert resp.json()["count"] == 1
