"""Unit + integration tests for C2 structural lint (Session ***REMOVED***18).

Unit: doc-length validation, enum guardrails, LLM-output normalization.
Integration: TestClient on a sub-app mounting struct_lint.router, with
llm_client mocked — never a real OpenRouter call.
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

from services import struct_lint_service as svc  ***REMOVED*** noqa: E402


***REMOVED*** =========================================================================
***REMOVED*** Unit — check_doc_length
***REMOVED*** =========================================================================


def test_check_doc_length_normal_ok():
    assert svc.check_doc_length("这是一份正常长度的策略文档。") is None


def test_check_doc_length_empty_rejected():
    assert svc.check_doc_length("") == "empty_document"
    assert svc.check_doc_length("   \n  ") == "empty_document"
    assert svc.check_doc_length(None) == "empty_document"


def test_check_doc_length_over_cap_rejected():
    too_long = "x" * (svc.MAX_DOC_CHARS + 1)
    assert svc.check_doc_length(too_long) == "document_too_long"
    ***REMOVED*** Exactly at the cap is allowed.
    assert svc.check_doc_length("x" * svc.MAX_DOC_CHARS) is None


***REMOVED*** =========================================================================
***REMOVED*** Unit — normalize_lint_result guardrail
***REMOVED*** =========================================================================


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
    ***REMOVED*** Non-dict top-level → None.
    assert svc.normalize_lint_result(["not", "a", "dict"]) is None
    assert svc.normalize_lint_result(None) is None
    ***REMOVED*** claims not a list → treated as empty.
    out = svc.normalize_lint_result({"summary": "s", "claims": "oops"})
    assert out["claims"] == []
    ***REMOVED*** Non-dict claim entries are dropped.
    out2 = svc.normalize_lint_result({"claims": ["string", 42, None]})
    assert out2["claims"] == []
    ***REMOVED*** Missing summary gets a sensible fallback.
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


***REMOVED*** =========================================================================
***REMOVED*** Integration — TestClient against struct_lint.router
***REMOVED*** =========================================================================


@pytest.fixture
def client():
    from api import struct_lint as struct_lint_api

    app = FastAPI()
    app.include_router(struct_lint_api.router, prefix="/api")
    return TestClient(app)


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


def test_endpoint_success(client, monkeypatch):
    """Happy path: LLM available + returns a clean payload."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return _GOOD_LLM_REPLY

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={"document": "我们的增长方案……"})
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]
    assert len(body["claims"]) == 2
    assert body["claims"][0]["claim_type"] == "analogy"


def test_endpoint_llm_unavailable(client, monkeypatch):
    """No API key → clean 503, no LLM call attempted."""
    from services import struct_lint_service
    from api import struct_lint as struct_lint_api

    monkeypatch.setattr(struct_lint_api.llm_client, "llm_available", lambda: False)

    r = client.post("/api/struct-lint", json={"document": "一段文档"})
    assert r.status_code == 503
    assert r.json()["error"] == "llm_unavailable"


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


def test_endpoint_filters_malformed_claims(client, monkeypatch):
    """LLM returns a mix of good + malformed claims — guardrail keeps good only."""
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
                ***REMOVED*** bad claim_type → dropped
                {"quote": "坏类型", "claim_type": "nonsense", "risk_level": "low"},
                ***REMOVED*** no quote → dropped
                {"claim_type": "assumption", "risk_level": "low"},
                ***REMOVED*** bad risk_level → kept, normalized to medium
                {"quote": "坏风险", "claim_type": "analogy", "risk_level": "???"},
            ],
        }

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={"document": "doc"})
    assert r.status_code == 200
    claims = r.json()["claims"]
    assert len(claims) == 2
    quotes = {c["quote"] for c in claims}
    assert quotes == {"合法主张", "坏风险"}
    bad_risk = next(c for c in claims if c["quote"] == "坏风险")
    assert bad_risk["risk_level"] == "medium"


def test_endpoint_llm_returns_unusable_payload(client, monkeypatch):
    """LLM returns None (parse failure) → 503 llm_failed."""
    from services import struct_lint_service

    monkeypatch.setattr(struct_lint_service.llm_client, "llm_available", lambda: True)

    async def fake_complete_json(**kwargs):
        return None

    monkeypatch.setattr(
        struct_lint_service.llm_client, "complete_json", fake_complete_json
    )

    r = client.post("/api/struct-lint", json={"document": "doc"})
    assert r.status_code == 503
    assert r.json()["error"] == "llm_failed"
