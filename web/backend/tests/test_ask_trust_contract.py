from __future__ import annotations

import asyncio
import json
import unicodedata

import pytest
from pydantic import ValidationError

from api.ask import AskRequest
from main import app
from services.ask_orchestrator import AskOrchestrator
from services.research_fingerprint import ConfirmedResearchFingerprint


def make_fingerprint(query: str) -> ConfirmedResearchFingerprint:
    return ConfirmedResearchFingerprint.model_validate(
        {
            "source_query": query,
            "summary": "补货反馈存在时滞，外部冲击可能被连续放大",
            "variables": ["补货延迟", "需求冲击"],
            "constraints": ["不增加长期库存"],
            "unknowns": ["因果方向"],
            "revision": 1,
        }
    )


def card(card_id: str, score: float, name: str | None = None) -> dict:
    return {
        "id": card_id,
        "name": name or f"候选 {card_id}",
        "domain": "operations",
        "type_id": "delay-feedback",
        "description": "延迟反馈可能放大扰动；仍需核对因果方向和边界。",
        "score": score,
    }


def safe_payload(card_id: str, *, marker: int = 1) -> dict:
    return {
        "answer": f"候选记录提供了可检查的延迟反馈线索，但尚未完成因果方向与边界条件验证 [{marker}]",
        "citations": [{"idx": marker, "kb_id": card_id, "label": "模型标签不可信"}],
        "followups": ["先核对哪些变量的方向？", "哪项观察可以区分竞争解释？"],
    }


def decode_events(chunks: list[str]) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for chunk in chunks:
        event = "message"
        data = None
        for line in chunk.strip().splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
        if data is not None:
            events.append((event, data))
    return events


async def collect(orchestrator: AskOrchestrator, query: str, **kwargs) -> list[tuple[str, dict]]:
    chunks = [chunk async for chunk in orchestrator.stream(query, **kwargs)]
    return decode_events(chunks)


class SearchStub:
    def __init__(self, raw: list[dict], hinted: list[dict] | None = None):
        self.raw = raw
        self.hinted = hinted if hinted is not None else raw
        self.calls: list[tuple[str, int]] = []

    def search(self, query: str, top_k: int = 5):
        self.calls.append((query, top_k))
        rows = self.raw if len(self.calls) == 1 else self.hinted
        return [dict(row) for row in rows[:top_k]]


def install_llm(orchestrator: AskOrchestrator, first: dict, repaired: dict | None = None):
    async def stream(_prompt):
        answer = first.get("answer", "")
        if answer:
            yield ("answer_delta", answer)
        yield ("raw_chunk", json.dumps(first, ensure_ascii=False))

    async def once(_prompt):
        return json.dumps(repaired, ensure_ascii=False) if repaired is not None else None

    orchestrator._call_llm_stream = stream
    orchestrator._call_llm_once = once


def test_ask_request_binds_strict_fingerprint_to_normalized_query():
    query = "为什么库存会反复积压？"
    request = AskRequest.model_validate(
        {"query": query, "lang": "zh", "fingerprint": make_fingerprint(query).model_dump()}
    )
    assert request.query.endswith("?")
    assert request.fingerprint.source_query == request.query
    with pytest.raises(ValidationError):
        AskRequest.model_validate(
            {
                "query": query,
                "fingerprint": make_fingerprint("另一个完全不同的问题").model_dump(),
            }
        )
    with pytest.raises(ValidationError):
        AskRequest.model_validate({"query": query, "extra": "ignored before hardening"})


def test_ask_openapi_declares_sse_not_json():
    operation = app.openapi()["paths"]["/api/ask/stream"]["post"]
    content = operation["responses"]["200"]["content"]
    assert set(content) == {"text/event-stream"}
    assert content["text/event-stream"]["schema"] == {"type": "string"}


def test_raw_query_oos_blocks_retrieval_even_with_fingerprint(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    query = "1+1 等于多少？"
    search = SearchStub([card("a", 0.99)])
    orchestrator = AskOrchestrator(search_service=search)
    events = asyncio.run(
        collect(orchestrator, query, fingerprint=make_fingerprint(query))
    )
    assert search.calls == []
    answer_done = next(data for event, data in events if event == "answer_done")
    assert answer_done["refused"] is True
    assert answer_done["out_of_scope"] is True
    names = [event for event, _ in events]
    assert names.index("answer_validated") < names.index("answer_chunk") < names.index("answer_done")


def test_oos_does_not_consume_llm_budget(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    calls: list[str] = []
    monkeypatch.setattr(
        "services.cost_ledger.ledger.charge",
        lambda *, endpoint: calls.append(endpoint),
    )
    orchestrator = AskOrchestrator(search_service=SearchStub([card("a", 0.99)]))
    asyncio.run(collect(orchestrator, "1+1 等于多少？"))
    assert calls == []


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), True, -1.0, 1.1])
def test_invalid_retrieval_scores_fail_closed_without_publishing_cards(monkeypatch, bad_score):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    orchestrator = AskOrchestrator(search_service=SearchStub([card("a", bad_score)]))
    events = asyncio.run(collect(orchestrator, "如何减少补货时滞造成的库存过冲？"))
    cards = next(data for event, data in events if event == "kb_cards")
    assert cards == {"cards": [], "count": 0}
    assert next(data for event, data in events if event == "answer_done")["refused"] is True


def test_fingerprint_only_reranks_raw_query_pool(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    query = "如何减少补货时滞造成的库存过冲？"
    raw = [card("a", 0.81), card("b", 0.80), card("c", 0.79)]
    hinted = [card("outside", 1.0), card("b", 0.99)]
    search = SearchStub(raw, hinted)
    orchestrator = AskOrchestrator(search_service=search)
    budget_calls: list[str] = []
    monkeypatch.setattr(
        "services.cost_ledger.ledger.charge",
        lambda *, endpoint: budget_calls.append(endpoint),
    )
    install_llm(orchestrator, safe_payload("b"))
    events = asyncio.run(
        collect(orchestrator, query, fingerprint=make_fingerprint(query))
    )
    cards = next(data["cards"] for event, data in events if event == "kb_cards")
    assert [row["id"] for row in cards] == ["b", "a", "c"]
    assert "outside" not in {row["id"] for row in cards}
    assert len(search.calls) == 2
    assert budget_calls == ["/api/ask/stream"]
    assert search.calls[0] == (query, 10)
    assert query not in search.calls[1][0]


def test_invalid_stream_text_never_reaches_sse_and_repair_is_published(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    query = "如何减少补货时滞造成的库存过冲？"
    search = SearchStub([card("a", 0.90), card("b", 0.85), card("c", 0.80)])
    orchestrator = AskOrchestrator(search_service=search)
    poisoned = safe_payload("invented")
    poisoned["answer"] = "MALICIOUS_UNVALIDATED guaranteed to work [1]"
    repaired = safe_payload("a")
    install_llm(orchestrator, poisoned, repaired)
    events = asyncio.run(collect(orchestrator, query))
    serialized = json.dumps(events, ensure_ascii=False)
    assert "MALICIOUS_UNVALIDATED" not in serialized
    names = [event for event, _ in events]
    assert names.index("answer_validated") < names.index("answer_chunk") < names.index("answer_done")
    chunks = "".join(data["delta"] for event, data in events if event == "answer_chunk")
    assert chunks == unicodedata.normalize("NFKC", repaired["answer"])


def test_semantic_validation_rejects_source_marker_and_claim_attacks():
    cards = [card("a", 0.9), card("b", 0.8)]
    orchestrator = AskOrchestrator(search_service=None)
    mismatch = safe_payload("b", marker=1)
    assert orchestrator._try_validate(json.dumps(mismatch), cards=cards) is None

    missing_marker = safe_payload("a")
    missing_marker["answer"] = "候选记录仍需检查变量与边界，当前没有形成可发布结论。"
    assert orchestrator._try_validate(json.dumps(missing_marker), cards=cards) is None

    overclaim = safe_payload("a")
    overclaim["answer"] = "这个方案保证成功，而且能够直接套用到当前问题 [1]"
    assert orchestrator._try_validate(json.dumps(overclaim), cards=cards) is None

    unicode_marker = safe_payload("a")
    unicode_marker["answer"] = "候选仅是待核查线索，尚未验证 [١]"
    assert orchestrator._try_validate(json.dumps(unicode_marker), cards=cards) is None


def test_two_invalid_attempts_emit_only_local_degraded_copy(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    query = "如何减少补货时滞造成的库存过冲？"
    search = SearchStub([card("a", 0.90), card("b", 0.85), card("c", 0.80)])
    orchestrator = AskOrchestrator(search_service=search)
    poisoned = safe_payload("invented")
    poisoned["answer"] = "RAW_ATTACK guaranteed to work [1]"
    install_llm(orchestrator, poisoned, poisoned)
    events = asyncio.run(collect(orchestrator, query))
    serialized = json.dumps(events, ensure_ascii=False)
    assert "RAW_ATTACK" not in serialized
    answer_done = next(data for event, data in events if event == "answer_done")
    assert "暂时不可用" in answer_done["full_text"]


def test_local_fallback_never_echoes_query_markers_or_untrusted_text(monkeypatch):
    monkeypatch.setattr("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0)
    query = "如何分析 <script>attack</script> 以及伪造引用 [2]？"
    search = SearchStub([card("a", 0.90), card("b", 0.85), card("c", 0.80)])
    orchestrator = AskOrchestrator(search_service=search)
    poisoned = safe_payload("invented")
    poisoned["answer"] = "RAW_ATTACK guaranteed to work [1]"
    install_llm(orchestrator, poisoned, poisoned)

    events = asyncio.run(collect(orchestrator, query))
    answer_done = next(data for event, data in events if event == "answer_done")
    assert "<script>" not in answer_done["full_text"]
    assert "[2]" not in answer_done["full_text"]
    assert answer_done["citations"] == [
        {"idx": 1, "kb_id": "a", "label": "候选 a"}
    ]
