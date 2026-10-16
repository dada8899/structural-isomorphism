"""Ask pure incremental parser, evidence and retired streaming boundaries.

Parser/schema helpers are exercised directly. No provider/SSE runtime ordering or
latency claim remains: retired stream/retry entrypoints emit nothing.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import unittest
from pathlib import Path
from typing import AsyncIterator, List, Tuple
from unittest.mock import patch

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.ask_orchestrator import (  # noqa: E402
    AskOrchestrator,
    _AnswerFieldExtractor,
)


# ------------------------------------------------------------------ #
# 1. JSON answer-field extractor unit tests                          #
# ------------------------------------------------------------------ #


class AnswerFieldExtractorTests(unittest.TestCase):
    def test_happy_path_extracts_answer_chars(self):
        """Whole-string feed: extractor returns the answer field unescaped."""
        ext = _AnswerFieldExtractor()
        raw = '{"answer": "你好世界", "citations": []}'
        out = ext.feed(raw)
        self.assertEqual(out, "你好世界")
        # State machine should have closed.
        self.assertEqual(ext.state, _AnswerFieldExtractor.DONE)

    def test_chunked_feed_yields_incrementally(self):
        """Feed the same JSON one char at a time — same final output."""
        ext = _AnswerFieldExtractor()
        raw = '{"answer": "hello world"}'
        collected = []
        for ch in raw:
            collected.append(ext.feed(ch))
        self.assertEqual("".join(collected), "hello world")

    def test_escape_sequences_decoded(self):
        ext = _AnswerFieldExtractor()
        raw = r'{"answer": "line1\nline2\t\"quoted\""}'
        out = ext.feed(raw)
        self.assertEqual(out, 'line1\nline2\t"quoted"')

    def test_unicode_escape_decoded(self):
        ext = _AnswerFieldExtractor()
        raw = r'{"answer": "你好"}'
        out = ext.feed(raw)
        self.assertEqual(out, "你好")

    def test_never_matched_returns_empty(self):
        """Envelope without `answer` field → no chars emitted."""
        ext = _AnswerFieldExtractor()
        raw = '{"reply": "hello", "citations": []}'
        out = ext.feed(raw)
        self.assertEqual(out, "")
        self.assertEqual(ext.state, _AnswerFieldExtractor.SCANNING)

    def test_preamble_with_whitespace(self):
        """Realistic OpenRouter stream may emit whitespace between key/value."""
        ext = _AnswerFieldExtractor()
        # Note tabs + newlines between key and value.
        raw = '{\n  "answer"\t :\t  "abc"\n}'
        out = ext.feed(raw)
        self.assertEqual(out, "abc")

    def test_value_with_internal_braces(self):
        """Braces inside the answer string don't fool the state machine."""
        ext = _AnswerFieldExtractor()
        raw = '{"answer": "function f() { return 1; }"}'
        out = ext.feed(raw)
        self.assertEqual(out, "function f() { return 1; }")

    def test_idempotent_after_done(self):
        """Feeding after DONE returns empty (no late emissions)."""
        ext = _AnswerFieldExtractor()
        raw = '{"answer": "ok", "citations": [{"idx":1,"kb_id":"a","label":"b"}]}'
        ext.feed(raw)
        self.assertEqual(ext.state, _AnswerFieldExtractor.DONE)
        more = ext.feed(' more raw bytes ')
        self.assertEqual(more, "")


# ------------------------------------------------------------------ #
# 2. SSE pipeline integration: retrieval_done comes BEFORE answer    #
# ------------------------------------------------------------------ #

_FIXED_KB = [
    {
        "id": "phen-1",
        "name": "Bank run cascade",
        "domain": "finance",
        "type_id": "Network_cascade",
        "description": "Depositors withdraw en masse once trust evaporates.",
        "score": 0.91,
    },
    {
        "id": "phen-2",
        "name": "Forest fire spread",
        "domain": "ecology",
        "type_id": "Network_cascade",
        "description": "Power-law cluster sizes near percolation threshold.",
        "score": 0.84,
    },
    {
        "id": "phen-3",
        "name": "Power grid blackout",
        "domain": "engineering",
        "type_id": "Cascading_failure",
        "description": "Overload trip cascades through coupled lines.",
        "score": 0.78,
    },
]


_MOCK_FULL_JSON = json.dumps({
    "answer": (
        "你的问题本质上是一个网络级联问题 [1]。当节点间的耦合超过临界值，"
        "局部扰动会沿着边自我放大，最终触发大规模重排。这种结构在生态、"
        "工程、社会系统里都成立 [2][3]。"
    ),
    "citations": [
        {"idx": 1, "kb_id": "phen-1", "label": "银行挤兑级联"},
        {"idx": 2, "kb_id": "phen-2", "label": "森林火灾蔓延"},
        {"idx": 3, "kb_id": "phen-3", "label": "电网级联停电"},
    ],
    "followups": [
        "在什么耦合强度下会跨过临界点？",
        "哪种干预最便宜——切边还是降载？",
        "是否存在领先指标可以预警？",
    ],
}, ensure_ascii=False)


class _FakeSearch:
    def __init__(self, results):
        self._results = results

    def search(self, query: str, top_k: int = 12):
        return self._results[:top_k]


def _parse_sse_events(chunks: List[str]):
    out = []
    text = "".join(chunks)
    for block in re.split(r"\n\n", text):
        block = block.strip()
        if not block:
            continue
        m = re.match(r"event:\s*(\S+)\s*\ndata:\s*(.+)$", block, re.DOTALL)
        if not m:
            continue
        name, data = m.group(1), m.group(2)
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            payload = {"_raw": data}
        out.append((name, payload))
    return out


async def _collect(stream):
    out = []
    async for chunk in stream:
        out.append(chunk)
    return out


def _mock_stream_factory(json_payload: str, chunk_size: int = 16):
    """Build a fake `_call_llm_stream` that emits `json_payload` in chunks.

    Yields the same tuple protocol as the real method:
        ("raw_chunk", str)
        ("answer_delta", str)  — driven by feeding through the extractor
    The orchestrator's stream() consumes this directly.
    """
    async def fake(self, prompt):  # noqa: ARG001 (signature match)
        # Re-import inside to dodge stale binding across patches.
        from services.ask_orchestrator import _AnswerFieldExtractor as _Ext
        ext = _Ext()
        for i in range(0, len(json_payload), chunk_size):
            piece = json_payload[i : i + chunk_size]
            yield ("raw_chunk", piece)
            emitted = ext.feed(piece)
            if emitted:
                yield ("answer_delta", emitted)
            # Microscopic await so other coroutines can interleave; mirrors
            # real network arrival pattern more closely.
            await asyncio.sleep(0)
    return fake


class StreamingPipelineTests(unittest.TestCase):
    """Pure helpers and explicit retired stream entrypoint guards."""

    def test_retired_stream_emits_nothing_before_retrieval(self):
        from errors import LegacyPaidUnavailable
        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(search,'search',side_effect=AssertionError('no retrieval')) as retrieve, patch.object(orch,'_call_llm_stream',side_effect=AssertionError('no provider')) as send:
            chunks = []
            async def collect():
                async for chunk in orch.stream('Why do banks fail',lang='en'):
                    chunks.append(chunk)
            with self.assertRaises(LegacyPaidUnavailable):
                asyncio.run(collect())
        self.assertEqual(chunks,[])
        retrieve.assert_not_called()
        send.assert_not_called()

    def test_pure_sse_encoder_preserves_named_event_shape(self):
        from services.ask_orchestrator import _sse
        # Serializer contract only; retired stream ordering is no longer promised.
        self.assertEqual(_parse_sse_events([_sse('retrieval_done',{'count':0})]), [('retrieval_done',{'count':0})])

    def test_pure_candidate_envelope_does_not_claim_verified_transfer(self):
        from services.evidence_envelope import retrieval_candidate
        envelope = retrieval_candidate(_FIXED_KB[0],counterexample='No variable mapping has been completed.')
        self.assertEqual(envelope['evidence_level'],'candidate')
        self.assertIn('No variable mapping',json.dumps(envelope))

    def test_pure_relevance_rejects_invalid_retrieval_score(self):
        from services.ask_orchestrator import _display_score
        bad = {**_FIXED_KB[0],'score':'not-a-number'}
        self.assertEqual(_display_score(bad),0.0)
        self.assertTrue(AskOrchestrator(search_service=None)._evaluate_relevance([bad])[0])

    def test_retired_retry_stream_emits_no_partial_answer(self):
        from errors import LegacyPaidUnavailable
        orch = AskOrchestrator(search_service=_FakeSearch(_FIXED_KB))
        emitted = []
        async def collect():
            async for item in orch._stream_llm_answer_with_retry('Q',_FIXED_KB,'zh'):
                emitted.append(item)
        with patch.object(orch,'_call_llm_stream',side_effect=AssertionError('no send')) as send:
            with self.assertRaises(LegacyPaidUnavailable):
                asyncio.run(collect())
        send.assert_not_called()
        self.assertEqual(emitted,[])

    def test_pure_malformed_envelope_rejected_and_local_fallback_bounded(self):
        bad_json = json.dumps({'reply':'wrong shape','citations':[],'followups':[]})
        orch = AskOrchestrator(search_service=None)
        self.assertIsNone(orch._try_validate(bad_json,cards=_FIXED_KB))
        fallback = orch._fallback_payload('UNTRUSTED_QUERY',_FIXED_KB,'zh')
        self.assertNotIn('UNTRUSTED_QUERY',fallback['answer'])
        self.assertIn('尚未验证',fallback['answer'])
        self.assertEqual(fallback['citations'][0]['kb_id'],'phen-1')


async def _async_value(v):
    return v


# ------------------------------------------------------------------ #
# 3. The streaming forwarding latency invariant                       #
# ------------------------------------------------------------------ #


class StreamingLatencyTests(unittest.TestCase):
    """Incremental parser timing only, without a live streaming claim."""

    def test_pure_extractor_yields_early_without_publishing_runtime_events(self):
        # Incremental parsing remains a pure helper; no provider/SSE latency claim.
        payload = json.dumps({'answer':'a'*300,'citations':[],'followups':[]})
        ext = _AnswerFieldExtractor()
        positions = []
        answer = ''
        pieces = [payload[i:i+8] for i in range(0,len(payload),8)]
        for i,piece in enumerate(pieces):
            emitted = ext.feed(piece)
            if emitted: positions.append(i)
            answer += emitted
        self.assertEqual(answer,'a'*300)
        self.assertLess(positions[0],len(pieces)//4)
        self.assertEqual(ext.state,_AnswerFieldExtractor.DONE)


if __name__ == "__main__":
    unittest.main()
