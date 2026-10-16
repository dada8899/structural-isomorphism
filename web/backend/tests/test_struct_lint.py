"""Unit + integration tests for C2 structural lint (Session #18).

Unit: doc-length validation, enum guardrails, LLM-output normalization.
Integration: TestClient on a sub-app mounting struct_lint.router, with
llm_client mocked — never a real OpenRouter call.
"""
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

from services import struct_lint_service as svc  # noqa: E402


@pytest.fixture
def anyio_backend():
    """Run @pytest.mark.anyio tests on the asyncio backend."""
    return "asyncio"


# =========================================================================
# Unit — check_doc_length
# =========================================================================


def test_check_doc_length_normal_ok():
    assert svc.check_doc_length("这是一份正常长度的策略文档。") is None


def test_check_doc_length_empty_rejected():
    assert svc.check_doc_length("") == "empty_document"
    assert svc.check_doc_length("   \n  ") == "empty_document"
    assert svc.check_doc_length(None) == "empty_document"


def test_check_doc_length_over_cap_rejected():
    too_long = "x" * (svc.MAX_DOC_CHARS + 1)
    assert svc.check_doc_length(too_long) == "document_too_long"
    # Exactly at the cap is allowed.
    assert svc.check_doc_length("x" * svc.MAX_DOC_CHARS) is None


# =========================================================================
# Unit — normalize_lint_result guardrail
# =========================================================================


def test_normalize_valid_payload_passes_through():
    raw = {
        "summary": "最大风险是单点假设。",
        "claims": [
            {
                "quote": "只要投放就会有转化",
                "claim_type": "causal_judgment",
                "structure": "线性因果链",
                "failure_mode": "中间环节失效时因果断裂",
                "risk_level": "high",
                "suggestion": "做小规模 A/B 验证",
            }
        ],
    }
    out = svc.normalize_lint_result(raw)
    assert out["summary"] == "最大风险是单点假设。"
    assert len(out["claims"]) == 1
    assert out["claims"][0]["claim_type"] == "causal_judgment"
    assert out["claims"][0]["risk_level"] == "high"


def test_normalize_drops_bad_claim_type():
    """A claim with an out-of-enum claim_type is dropped entirely."""
    raw = {
        "summary": "s",
        "claims": [
            {"quote": "q1", "claim_type": "wild_guess", "risk_level": "low"},
            {"quote": "q2", "claim_type": "assumption", "risk_level": "low"},
        ],
    }
    out = svc.normalize_lint_result(raw)
    assert len(out["claims"]) == 1
    assert out["claims"][0]["quote"] == "q2"


def test_normalize_bad_risk_level_falls_back_to_medium():
    """Unknown risk_level is normalized to medium (claim kept, not dropped)."""
    raw = {
        "summary": "s",
        "claims": [
            {"quote": "q", "claim_type": "analogy", "risk_level": "catastrophic"},
        ],
    }
    out = svc.normalize_lint_result(raw)
    assert len(out["claims"]) == 1
    assert out["claims"][0]["risk_level"] == "medium"


def test_normalize_drops_claim_without_quote():
    raw = {
        "summary": "s",
        "claims": [
            {"claim_type": "assumption", "risk_level": "high"},
            {"quote": "", "claim_type": "assumption", "risk_level": "high"},
            {"quote": "good", "claim_type": "assumption", "risk_level": "high"},
        ],
    }
    out = svc.normalize_lint_result(raw)
    assert len(out["claims"]) == 1
    assert out["claims"][0]["quote"] == "good"


def test_normalize_handles_non_dict_and_missing_fields():
    # Non-dict top-level → None.
    assert svc.normalize_lint_result(["not", "a", "dict"]) is None
    assert svc.normalize_lint_result(None) is None
    # claims not a list → treated as empty.
    out = svc.normalize_lint_result({"summary": "s", "claims": "oops"})
    assert out["claims"] == []
    # Non-dict claim entries are dropped.
    out2 = svc.normalize_lint_result({"claims": ["string", 42, None]})
    assert out2["claims"] == []
    # Missing summary gets a sensible fallback.
    assert out2["summary"]


def test_normalize_caps_claim_count():
    raw = {
        "claims": [
            {"quote": f"q{i}", "claim_type": "assumption", "risk_level": "low"}
            for i in range(svc.MAX_CLAIMS + 10)
        ]
    }
    out = svc.normalize_lint_result(raw)
    assert len(out["claims"]) == svc.MAX_CLAIMS


def test_normalize_fills_missing_text_fields():
    raw = {
        "claims": [
            {"quote": "q", "claim_type": "assumption", "risk_level": "low"},
        ]
    }
    out = svc.normalize_lint_result(raw)
    c = out["claims"][0]
    assert c["structure"] and c["failure_mode"] and c["suggestion"]


def test_normalize_claim_carries_isomorph_key():
    """Every normalized claim must carry an isomorph key, defaulting to None."""
    out = svc.normalize_lint_result(
        {"claims": [{"quote": "q", "claim_type": "assumption", "risk_level": "low"}]}
    )
    assert "isomorph" in out["claims"][0]
    assert out["claims"][0]["isomorph"] is None


# =========================================================================
# Unit — build_isomorph_query (claim → KB search query)
# =========================================================================


def test_build_query_uses_structure_and_failure_mode():
    claim = {
        "structure": "单案例归纳到普适结论",
        "failure_mode": "幸存者偏差",
    }
    q = svc.build_isomorph_query(claim)
    assert "单案例归纳到普适结论" in q
    assert "幸存者偏差" in q


def test_build_query_empty_structure_returns_blank():
    """A claim with no real structure text yields no query (skip KB lookup)."""
    assert svc.build_isomorph_query({"structure": "未提供结构描述"}) == ""
    assert svc.build_isomorph_query({"structure": "短"}) == ""
    assert svc.build_isomorph_query({}) == ""
    assert svc.build_isomorph_query("not a dict") == ""


def test_build_query_structure_only_when_no_failure_mode():
    claim = {"structure": "线性外推的因果链条", "failure_mode": "未提供失效模式"}
    q = svc.build_isomorph_query(claim)
    assert q == "线性外推的因果链条"


# =========================================================================
# Unit — normalize_isomorph (KB search result → anchor)
# =========================================================================


def test_normalize_isomorph_valid():
    raw = {
        "id": "ph-001",
        "name": "捕食者-猎物震荡",
        "domain": "生态学",
        "relevance": 0.82,
        "description": "种群数量周期性波动",
        "score": 0.9,
        "type_id": "T3",
    }
    out = svc.normalize_isomorph(raw)
    assert out["id"] == "ph-001"
    assert out["name"] == "捕食者-猎物震荡"
    assert out["domain"] == "生态学"
    assert out["relevance"] == 0.82
    assert out["description"] == "种群数量周期性波动"


def test_normalize_isomorph_rejects_no_id():
    assert svc.normalize_isomorph({"name": "无 id"}) is None
    assert svc.normalize_isomorph("not a dict") is None
    assert svc.normalize_isomorph(None) is None


def test_normalize_isomorph_clamps_bad_relevance():
    assert svc.normalize_isomorph({"id": "x", "relevance": 9.5})["relevance"] == 1.0
    assert svc.normalize_isomorph({"id": "x", "relevance": -1})["relevance"] == 0.0
    assert svc.normalize_isomorph({"id": "x", "relevance": "oops"})["relevance"] == 0.0


# =========================================================================
# Unit — _search_isomorph degradation
# =========================================================================


def test_search_isomorph_degrades_when_no_service():
    """No search service → None, no exception."""
    assert svc._search_isomorph(None, "any query") is None


def test_search_isomorph_degrades_on_empty_query():
    class _Svc:
        def search(self, *a, **k):
            raise AssertionError("should not be called for empty query")

    assert svc._search_isomorph(_Svc(), "") is None


def test_search_isomorph_degrades_when_search_raises():
    class _Svc:
        def search(self, *a, **k):
            raise RuntimeError("KB index not loaded")

    assert svc._search_isomorph(_Svc(), "结构查询文本") is None


def test_search_isomorph_returns_top_anchor():
    class _Svc:
        def search(self, query, top_k=2):
            return [
                {"id": "ph-9", "name": "热力学第二定律", "domain": "物理",
                 "relevance": 0.7, "description": "熵增"},
            ]

    out = svc._search_isomorph(_Svc(), "结构查询文本")
    assert out is not None
    assert out["id"] == "ph-9"


# =========================================================================
# Integration — TestClient against struct_lint.router
# =========================================================================


@pytest.fixture
def client(monkeypatch):
    from api import struct_lint as endpoint
    from errors import install_problem_handlers
    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(endpoint.router, prefix="/api")
    from unittest.mock import Mock
    checks = []
    check = Mock(side_effect=AssertionError("retired generator must not run"))
    monkeypatch.setattr(endpoint, "lint_document", check)
    checks.append(check)
    check = Mock(side_effect=AssertionError("retired generator must not run"))
    monkeypatch.setattr(endpoint, "lint_document_streamed", check)
    checks.append(check)
    with TestClient(app) as connection:
        yield connection
    assert all(check.call_count == 0 for check in checks)


_GOOD_LLM_REPLY = {
    "summary": "最大结构性风险是把单一案例的成功线性外推。",
    "claims": [
        {
            "quote": "竞品这么做成了，我们照搬也能成",
            "claim_type": "analogy",
            "structure": "单案例归纳 → 普适结论",
            "failure_mode": "幸存者偏差，忽略前提条件差异",
            "risk_level": "high",
            "suggestion": "列出竞品成功的隐含前提，逐条核对自身是否满足",
        },
        {
            "quote": "用户量上来收入自然就有了",
            "claim_type": "causal_judgment",
            "structure": "规模 → 收入的线性因果",
            "failure_mode": "变现链路缺失时规模不转化为收入",
            "risk_level": "medium",
            "suggestion": "先验证单用户付费意愿再放量",
        },
    ],
}

_GOOD_DOCUMENT = (
    "策略写道：竞品这么做成了，我们照搬也能成。"
    "同时假设用户量上来收入自然就有了。"
)


def test_retired_endpoint_success(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return _GOOD_LLM_REPLY

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={
        "document": _GOOD_DOCUMENT,
        "client_request_id": "lint-request-000001",
    })
    _assert_retired_response(r)


def test_endpoint_rejects_out_of_scope_before_model(client, monkeypatch):
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: True)
    response = client.post(
        "/api/struct-lint", json={"document": "2 + 2 等于多少，请直接告诉我答案"}
    )
    assert response.status_code == 422
    assert response.json()["error"] == "out_of_scope"


def test_retired_endpoint_llm_unavailable(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: False)

    r = client.post("/api/struct-lint", json={"document": "一段文档"})
    _assert_retired_response(r)


def test_endpoint_empty_document(client, monkeypatch):
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: True)
    r = client.post("/api/struct-lint", json={"document": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_document"


def test_endpoint_document_too_long(client, monkeypatch):
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: True)
    too_long = "字" * (svc.MAX_DOC_CHARS + 1)
    r = client.post("/api/struct-lint", json={"document": too_long})
    assert r.status_code == 400
    body = r.json()
    assert body["error"] == "document_too_long"
    assert body["limit"] == svc.MAX_DOC_CHARS
    assert body["received"] == len(too_long)


def test_retired_endpoint_rejects_partially_malformed_claim_set(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return {
            "summary": "混合输出测试",
            "claims": [
                {
                    "quote": "合法主张",
                    "claim_type": "assumption",
                    "risk_level": "high",
                    "structure": "s",
                    "failure_mode": "f",
                    "suggestion": "g",
                },
                # bad claim_type → dropped
                {"quote": "坏类型", "claim_type": "nonsense", "risk_level": "low"},
                # no quote → dropped
                {"claim_type": "assumption", "risk_level": "low"},
                # bad risk_level → kept, normalized to medium
                {"quote": "坏风险", "claim_type": "analogy", "risk_level": "???"},
            ],
        }

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={"document": "doc"})
    _assert_retired_response(r)


def test_retired_endpoint_llm_returns_unusable_payload(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return None

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={"document": "doc"})
    _assert_retired_response(r)


# =========================================================================
# Integration — Session #18 deepening: KB structural-isomorphism pass
# =========================================================================


class _FakeSearch:
    """Stand-in for the running SearchService. `hits` is what search()
    returns; set it to [] to simulate an empty KB match, or raise via
    `raises=True` to simulate a search failure."""

    def __init__(self, hits=None, raises=False):
        self._hits = hits or []
        self._raises = raises
        self.calls = []

    def search(self, query, top_k=2):
        self.calls.append(query)
        if self._raises:
            raise RuntimeError("KB index not loaded")
        return self._hits


def _install_search(monkeypatch, fake):
    """Point main.app_state['search'] at a fake for the duration of a test."""
    import main

    monkeypatch.setitem(main.app_state, "search", fake)


def _stub_two_llm_calls(monkeypatch, extract_reply, anchor_reply):
    """First complete_json call → the extract reply; every later call
    (the per-claim anchor pass) → anchor_reply."""
    from services import struct_lint_service

    state = {"n": 0}

    async def fake_complete_json(**kwargs):
        state["n"] += 1
        return extract_reply if state["n"] == 1 else anchor_reply

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)
    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )


def test_retired_endpoint_attaches_candidate_reference_on_kb_hit(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    fake = _FakeSearch(hits=[
        {
            "id": "ph-eco-01",
            "name": "捕食者-猎物种群震荡",
            "domain": "生态学",
            "type_id": "T3",
            "relevance": 0.78,
            "description": "两个物种数量周期性此消彼长",
        },
    ])
    _install_search(monkeypatch, fake)
    _stub_two_llm_calls(
        monkeypatch,
        extract_reply=_GOOD_LLM_REPLY,
        anchor_reply={
            "failure_mode": "这条主张的结构与『生态学的捕食者-猎物震荡』同构……",
            "suggestion": "基于震荡现象的对冲建议",
        },
    )

    r = client.post("/api/struct-lint", json={"document": _GOOD_DOCUMENT})
    _assert_retired_response(r)
    assert fake.calls == []


def test_retired_endpoint_degrades_when_search_unavailable(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    import main

    monkeypatch.delitem(main.app_state, "search", raising=False)
    _stub_two_llm_calls(monkeypatch, _GOOD_LLM_REPLY, {})

    r = client.post("/api/struct-lint", json={"document": _GOOD_DOCUMENT})
    _assert_retired_response(r)


def test_retired_endpoint_degrades_on_empty_kb_match(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    fake = _FakeSearch(hits=[])
    _install_search(monkeypatch, fake)
    _stub_two_llm_calls(monkeypatch, _GOOD_LLM_REPLY, {})

    r = client.post("/api/struct-lint", json={"document": _GOOD_DOCUMENT})
    _assert_retired_response(r)
    assert fake.calls == []


def test_retired_endpoint_degrades_when_search_raises(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    fake = _FakeSearch(raises=True)
    _install_search(monkeypatch, fake)
    _stub_two_llm_calls(monkeypatch, _GOOD_LLM_REPLY, {})

    r = client.post("/api/struct-lint", json={"document": _GOOD_DOCUMENT})
    _assert_retired_response(r)
    assert fake.calls == []


# =========================================================================
# Unit — lint_document_streamed (the SSE pipeline generator)
# =========================================================================


@pytest.mark.anyio
async def test_streamed_emits_progress_then_done(monkeypatch):
    """Happy path: extract → claims → isomorph progress events, then done.

    Asserts the events actually appear (a `done` with a result), not just
    that no exception was raised —加 log 行 ≠ 加 SSE event.
    """
    from services import struct_lint_service

    _stub_two_llm_calls(
        monkeypatch,
        extract_reply=_GOOD_LLM_REPLY,
        anchor_reply={"failure_mode": "同构重写后的失效模式", "suggestion": "重写建议"},
    )
    fake = _FakeSearch(hits=[
        {"id": "ph-eco-01", "name": "捕食者-猎物震荡", "domain": "生态学",
         "relevance": 0.78, "description": "周期性波动"},
    ])

    events = []
    async for ev in struct_lint_service.lint_document_streamed(
        _GOOD_DOCUMENT, search_svc=fake
    ):
        events.append(ev)

    stages = [e.get("stage") for e in events if e.get("type") == "progress"]
    # extract → claims → one candidate-reference event per claim (2 claims).
    assert "extract" in stages
    assert "claims" in stages
    assert stages.count("candidate_reference") == 2

    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    result = done[0]["result"]
    assert len(result["claims"]) == 2
    assert result["claims"][0]["reference_candidate"]["id"] == "ph-eco-01"
    assert result["claims"][0]["failure_mode"] == "幸存者偏差,忽略前提条件差异"


@pytest.mark.anyio
async def test_streamed_emits_error_on_llm_failure(monkeypatch):
    """First LLM call returns None → a single terminal error event."""
    from services import struct_lint_service

    async def fake_complete_json(**kwargs):
        return None

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    events = []
    async for ev in struct_lint_service.lint_document_streamed(_GOOD_DOCUMENT, search_svc=None):
        events.append(ev)

    assert any(e.get("type") == "error" for e in events)
    assert not any(e.get("type") == "done" for e in events)


@pytest.mark.anyio
async def test_streamed_degrades_without_search(monkeypatch):
    """No search service → no isomorph stage, but still a done event."""
    from services import struct_lint_service

    async def fake_complete_json(**kwargs):
        return _GOOD_LLM_REPLY

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    events = []
    async for ev in struct_lint_service.lint_document_streamed(
        _GOOD_DOCUMENT, search_svc=None
    ):
        events.append(ev)

    stages = [e.get("stage") for e in events if e.get("type") == "progress"]
    assert "candidate_reference" not in stages
    done = [e for e in events if e.get("type") == "done"]
    assert len(done) == 1
    for c in done[0]["result"]["claims"]:
        assert c["reference_candidate"] is None


# =========================================================================
# Integration — SSE endpoint /api/struct-lint/stream
# =========================================================================


def _parse_sse(text: str):
    """Parse a raw SSE response body into a list of (event, data) tuples."""
    events = []
    for block in text.strip().split("\n\n"):
        if not block.strip():
            continue
        event_type = None
        data_lines = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_type = line[len("event:"):].strip()
            elif line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if event_type:
            payload = "\n".join(data_lines)
            try:
                payload = json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                pass
            events.append((event_type, payload))
    return events


def test_stream_get_transport_is_retired_without_echoing_document(client):
    secret = "confidential-roadmap-do-not-log"
    response = client.get(
        "/api/struct-lint/stream",
        params={"document": secret},
    )
    assert response.status_code == 410
    assert response.json()["error"] == "sensitive_get_retired"
    assert secret not in response.text
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "payload",
    [
        {"document": ["not", "text"]},
        {"document": "visible\u200bhidden"},
        {"document": "x", "unexpected": True},
        {"document": "x" * 25_001},
    ],
)
def test_stream_body_rejects_wrong_type_controls_extra_and_hard_ceiling(client, payload):
    response = client.post("/api/struct-lint/stream", json=payload)
    assert response.status_code == 422


def test_retired_stream_accepts_20k_cjk_in_body(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from api import struct_lint as struct_lint_api

    document = "策" * 20_000
    seen = []
    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: True)

    async def fake_stream(doc, search_svc=None):
        seen.append((doc, search_svc))
        yield {"type": "done", "result": {"summary": "ok", "claims": []}}

    monkeypatch.setattr(struct_lint_api, "lint_document_streamed", fake_stream)
    response = client.post(
        "/api/struct-lint/stream",
        json={"document": document},
    )
    _assert_retired_response(response)
    assert seen == []
    assert not response.request.url.query


def test_retired_stream_endpoint_emits_meta_progress_done(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    fake = _FakeSearch(hits=[
        {"id": "ph-eco-01", "name": "捕食者-猎物震荡", "domain": "生态学",
         "relevance": 0.78, "description": "周期性波动"},
    ])
    _install_search(monkeypatch, fake)
    _stub_two_llm_calls(
        monkeypatch,
        extract_reply=_GOOD_LLM_REPLY,
        anchor_reply={"failure_mode": "同构失效模式", "suggestion": "建议"},
    )

    r = client.post("/api/struct-lint/stream", json={
        "document": _GOOD_DOCUMENT,
        "client_request_id": "lint-stream-000001",
    })
    _assert_retired_response(r)
    assert fake.calls == []


def test_stream_empty_document_is_http_400_before_sse(client, monkeypatch):
    """Empty doc is rejected before any SSE/meta response."""
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: True)
    r = client.post("/api/struct-lint/stream", json={"document": "   "})
    assert r.status_code == 400
    assert r.json()["error"] == "empty_document"
    assert r.headers["content-type"].startswith("application/json")
    assert _parse_sse(r.text) == []


def test_retired_stream_endpoint_llm_unavailable_emits_error(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: False)
    r = client.post("/api/struct-lint/stream", json={"document": "一段文档"})
    _assert_retired_response(r)


def test_retired_stream_endpoint_llm_failure_emits_error(client, monkeypatch):
    """Retired runtime rejects this former generation scenario before preparation."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return None

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )
    import main
    monkeypatch.delitem(main.app_state, "search", raising=False)

    r = client.post("/api/struct-lint/stream", json={"document": "一段文档"})
    _assert_retired_response(r)


def _assert_retired_response(response):
    """The retired endpoint cannot publish a report, fallback, or SSE."""
    assert response.status_code == 503, response.text
    body = response.json()
    assert body["code"] == "FEATURE_UNAVAILABLE"
    assert body["retryable"] is False and body["canonical"] == "/research"
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "event: meta" not in response.text and "event: done" not in response.text
