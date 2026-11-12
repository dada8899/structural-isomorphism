"""Ask pure trust contracts and zero-effect retired stream boundaries.

Fingerprint schema/reranking, relevance, citations and claim validation remain
direct helper tests. No dynamic generation or model repair is simulated.
"""
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


def test_oos_fingerprint_remains_bound_and_retired_stream_never_retrieves(monkeypatch):
    from services.scope_guard import is_out_of_scope
    from errors import LegacyPaidUnavailable
    query = '1+1 等于多少？'
    fp = make_fingerprint(query)
    assert fp.source_query == query.replace('？','?')
    assert is_out_of_scope(query)[0]
    search = SearchStub([card('a',0.99)])
    with pytest.raises(LegacyPaidUnavailable):
        asyncio.run(collect(AskOrchestrator(search_service=search),query,fingerprint=fp))
    assert search.calls == []


def test_retired_oos_does_not_consume_llm_budget(monkeypatch):
    from errors import LegacyPaidUnavailable
    calls = []
    monkeypatch.setattr('services.cost_ledger.ledger.charge',lambda *,endpoint:calls.append(endpoint))
    with pytest.raises(LegacyPaidUnavailable):
        asyncio.run(collect(AskOrchestrator(search_service=SearchStub([])),'1+1 等于多少？'))
    assert calls == []


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), True, -1.0, 1.1])
def test_pure_invalid_retrieval_scores_fail_relevance_gate(monkeypatch, bad_score):
    from services.ask_orchestrator import _display_score
    row = card('a',bad_score)
    assert _display_score(row) == 0.0
    assert AskOrchestrator(search_service=None)._evaluate_relevance([row])[0] is True


def test_pure_fingerprint_only_reranks_raw_query_pool(monkeypatch):
    from services.research_fingerprint import bounded_fingerprint_rerank,build_fingerprint_retrieval_hint
    query = '如何减少补货时滞造成的库存过冲？'
    raw = [card('a',.81),card('b',.80),card('c',.79)]
    original = [dict(row) for row in raw]
    hinted = [card('outside',1.0),card('b',.99)]
    result = bounded_fingerprint_rerank(raw,hinted,top_k=5)
    assert [row['id'] for row in result] == ['b','a','c']
    assert raw == original and all(row['id']!='outside' for row in result)
    assert {r['id']:r['score'] for r in result} == {r['id']:r['score'] for r in raw}
    assert query not in build_fingerprint_retrieval_hint(make_fingerprint(query))


def test_pure_invalid_payload_rejected_and_repaired_payload_validated(monkeypatch):
    orch = AskOrchestrator(search_service=None)
    cards = [card('a',.90),card('b',.85),card('c',.80)]
    poisoned = safe_payload('invented')
    poisoned['answer'] = 'MALICIOUS_UNVALIDATED guaranteed to work [1]'
    assert orch._try_validate(json.dumps(poisoned),cards=cards) is None
    repaired = safe_payload('a')
    validated = orch._try_validate(json.dumps(repaired),cards=cards)
    assert validated['answer'] == unicodedata.normalize('NFKC',repaired['answer'])
    assert validated['citations'][0]['label'] == '候选 a'


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


def test_pure_repeated_invalid_payloads_never_become_validated(monkeypatch):
    orch = AskOrchestrator(search_service=None)
    cards = [card('a',.9)]
    poisoned = safe_payload('invented')
    poisoned['answer'] = 'RAW_ATTACK guaranteed to work [1]'
    for _ in range(2):
        assert orch._try_validate(json.dumps(poisoned),cards=cards) is None
    fallback = orch._fallback_payload('private query',cards,'zh')
    assert 'RAW_ATTACK' not in json.dumps(fallback)
    assert '暂时不可用' in fallback['answer']


def test_pure_local_fallback_never_echoes_query_markers_or_untrusted_text(monkeypatch):
    query = '如何分析 <script>attack</script> 以及伪造引用 [2]？'
    payload = AskOrchestrator(search_service=None)._fallback_payload(query,[card('a',.90)],'zh')
    assert '<script>' not in payload['answer'] and '[2]' not in payload['answer']
    assert payload['citations'] == [{'idx':1,'kb_id':'a','label':'候选 a'}]
