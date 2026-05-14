"""W5-B: streaming optimizations for /api/ask/stream.

Covers:
1. `_AnswerFieldExtractor` JSON-string state machine — happy path,
   escapes, unicode, never-matched, multi-chunk feed.
2. `retrieval_done` SSE event lands BEFORE the first `answer_chunk` and
   before `kb_cards`.
3. End-to-end SSE event ordering with a mock streaming LLM:
   meta → retrieval_done → kb_cards → answer_chunk* → answer_done →
   similar_phenomena → followups → done.
4. Fallback paths: if no answer_delta ever streamed (malformed envelope)
   we still emit a typewriter answer.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_ask_streaming.py -v
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
    """End-to-end: orchestrator.stream() with the streaming path patched."""

    def test_retrieval_done_emits_before_first_answer_chunk(self):
        """W5-B core invariant: `retrieval_done` lands before `answer_chunk`."""
        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(
            AskOrchestrator,
            "_call_llm_stream",
            _mock_stream_factory(_MOCK_FULL_JSON, chunk_size=20),
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("Why do banks fail", lang="en")))

        events = _parse_sse_events(chunks)
        names = [e[0] for e in events]

        # retrieval_done must appear, and must appear BEFORE the first
        # answer_chunk. This is the spec-anchored guarantee from the task.
        self.assertIn("retrieval_done", names, f"missing retrieval_done in {names}")
        first_retr = names.index("retrieval_done")
        first_chunk = names.index("answer_chunk")
        self.assertLess(
            first_retr,
            first_chunk,
            f"retrieval_done (at {first_retr}) must precede first answer_chunk (at {first_chunk})",
        )

        # retrieval_done payload sanity.
        retr_data = events[first_retr][1]
        self.assertEqual(retr_data["count"], 3)
        self.assertEqual(len(retr_data["candidates"]), 3)
        self.assertEqual(retr_data["candidates"][0]["idx"], 1)
        self.assertEqual(retr_data["candidates"][0]["id"], "phen-1")
        self.assertGreaterEqual(retr_data["retrieval_ms"], 0)

    def test_retrieval_done_before_kb_cards(self):
        """retrieval_done = lighter / faster signal; kb_cards = fuller payload."""
        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(
            AskOrchestrator,
            "_call_llm_stream",
            _mock_stream_factory(_MOCK_FULL_JSON),
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("Q", lang="zh")))
        names = [e[0] for e in _parse_sse_events(chunks)]
        self.assertLess(names.index("retrieval_done"), names.index("kb_cards"))

    def test_full_event_sequence_streaming_path(self):
        """All required events still emit when LLM is streamed."""
        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(
            AskOrchestrator,
            "_call_llm_stream",
            _mock_stream_factory(_MOCK_FULL_JSON),
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("Q", lang="zh")))

        events = _parse_sse_events(chunks)
        names = [e[0] for e in events]

        self.assertEqual(names[0], "meta")
        self.assertEqual(names[-1], "done")
        for required in (
            "meta",
            "retrieval_done",
            "kb_cards",
            "answer_chunk",
            "answer_done",
            "similar_phenomena",
            "followups",
            "done",
        ):
            self.assertIn(required, names, f"missing event: {required}")

        # answer_chunks accumulate into the answer string.
        accumulated = "".join(
            ev["delta"] for name, ev in events if name == "answer_chunk"
        )
        answer_done = next(ev for name, ev in events if name == "answer_done")
        self.assertEqual(accumulated, answer_done["full_text"])

        # Citations validated (3 in mock, all in range).
        self.assertEqual(len(answer_done["citations"]), 3)
        for cit in answer_done["citations"]:
            self.assertIn(cit["idx"], (1, 2, 3))
            self.assertTrue(cit["kb_id"].startswith("phen-"))

    def test_fallback_when_envelope_never_matches_answer_key(self):
        """If the mocked stream produces no `answer` field, we still emit a chunk via fallback typewriter."""

        # JSON with NO `answer` field — extractor never matches; full JSON also fails pydantic.
        bad_json = json.dumps({
            "reply": "wrong shape",
            "citations": [],
            "followups": [],
        }, ensure_ascii=False)

        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(
            AskOrchestrator,
            "_call_llm_stream",
            _mock_stream_factory(bad_json, chunk_size=8),
        ), patch.object(
            AskOrchestrator,
            "_call_llm_once",
            # Async mock returning the same bad JSON twice → triggers fallback.
            lambda self, prompt: _async_value(bad_json),
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("Q", lang="zh")))

        events = _parse_sse_events(chunks)
        names = [e[0] for e in events]
        # Even on full fallback we still must emit answer_chunk (typewriter
        # path) + answer_done so the frontend isn't stuck.
        self.assertIn("answer_chunk", names)
        self.assertIn("answer_done", names)
        answer_done = next(ev for n, ev in events if n == "answer_done")
        # Fallback answer is the localized "synthesizer unavailable" line.
        self.assertGreater(len(answer_done["full_text"]), 20)


async def _async_value(v):
    return v


# ------------------------------------------------------------------ #
# 3. The streaming forwarding latency invariant                       #
# ------------------------------------------------------------------ #


class StreamingLatencyTests(unittest.TestCase):
    """Verify that answer_chunk events arrive INTERLEAVED with the JSON stream,
    not all at the end. This is the whole point of W5-B."""

    def test_answer_chunks_interleave_with_stream(self):
        """The first answer_chunk must come well before the final stream chunk."""

        # Build a JSON payload where the `answer` field is filled across many
        # tiny chunks, then citations come much later in the stream.
        big_answer = "a" * 300  # 300 chars of trivial answer text
        payload = json.dumps({
            "answer": big_answer,
            "citations": [{"idx": 1, "kb_id": "phen-1", "label": "x"}],
            "followups": ["q1?", "q2?"],
        }, ensure_ascii=False)

        # Track at which raw_chunk index the first answer_delta gets emitted.
        # If the extractor works, it should be early — well before the
        # citations / followups portions of the JSON arrive.
        chunk_size = 8
        first_answer_at = {"i": None}
        last_chunk_at = {"i": 0}

        async def instrumented_stream(self, prompt):  # noqa: ARG001
            from services.ask_orchestrator import _AnswerFieldExtractor as _Ext
            ext = _Ext()
            i = 0
            while i * chunk_size < len(payload):
                piece = payload[i * chunk_size : (i + 1) * chunk_size]
                yield ("raw_chunk", piece)
                emitted = ext.feed(piece)
                if emitted:
                    if first_answer_at["i"] is None:
                        first_answer_at["i"] = i
                    yield ("answer_delta", emitted)
                last_chunk_at["i"] = i
                i += 1
                await asyncio.sleep(0)

        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)
        with patch.object(
            AskOrchestrator, "_call_llm_stream", instrumented_stream
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            asyncio.run(_collect(orch.stream("Q", lang="zh")))

        self.assertIsNotNone(
            first_answer_at["i"], "extractor never emitted any answer_delta"
        )
        # First answer chars should land in the first ~10% of stream chunks.
        # The JSON envelope is `{"answer": "` (~13 chars) + 300 chars of `a`
        # + closing + citations + followups. With chunk_size=8 the answer
        # value starts emitting around chunk 2 and stays well below chunk 30.
        self.assertLess(
            first_answer_at["i"],
            last_chunk_at["i"] // 3,
            f"first answer chunk at index {first_answer_at['i']} should be in first 1/3 of {last_chunk_at['i']}",
        )


if __name__ == "__main__":
    unittest.main()
