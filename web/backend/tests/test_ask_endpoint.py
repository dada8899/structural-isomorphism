"""Unit tests for AskOrchestrator.

We mock the LLM call (`AskOrchestrator._call_llm_once`) and a fake
SearchService that returns a fixed top-k list, then run the async
generator to completion and assert that the SSE event sequence covers
every spec-required event type.

Run with:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_ask_endpoint.py -q
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import unittest
from pathlib import Path
from typing import List
from unittest.mock import patch

# Ensure `web/backend` is on sys.path when running directly so the
# `services.*` imports resolve the same way as in production.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.ask_orchestrator import AskOrchestrator  # noqa: E402
from services.ask_schemas import AskAnswerPayload  # noqa: E402


class _FakeSearch:
    """Minimal stand-in for SearchService.search()."""

    def __init__(self, results):
        self._results = results
        self.calls: List[str] = []

    def search(self, query: str, top_k: int = 12):
        self.calls.append(query)
        return self._results[:top_k]


_FIXED_KB = [
    {
        "id": "phen-1",
        "name": "Bank run cascade",
        "domain": "finance",
        "type_id": "Network_cascade",
        "description": "Depositors withdraw en masse once trust evaporates. Failures propagate through interbank exposures, producing a heavy-tailed distribution of insolvency events.",
        "score": 0.91,
    },
    {
        "id": "phen-2",
        "name": "Forest fire spread",
        "domain": "ecology",
        "type_id": "Network_cascade",
        "description": "A spark on a flammable patch triggers neighbors; cluster sizes follow a power law near the percolation threshold.",
        "score": 0.84,
    },
    {
        "id": "phen-3",
        "name": "Power grid blackout",
        "domain": "engineering",
        "type_id": "Cascading_failure",
        "description": "An overloaded line trips, redistributing load to neighbors that then trip in turn. The avalanche size depends on coupling strength.",
        "score": 0.78,
    },
    {
        "id": "phen-4",
        "name": "Information cascade in social networks",
        "domain": "sociology",
        "type_id": "Network_cascade",
        "description": "Once enough peers adopt a behavior, others follow based on observed signals rather than private evidence; minority can flip the majority.",
        "score": 0.71,
    },
    {
        "id": "phen-5",
        "name": "Avalanches in sandpile models",
        "domain": "physics",
        "type_id": "Avalanche_dynamics",
        "description": "Self-organized criticality: grains added one at a time produce avalanches whose sizes are power-law distributed.",
        "score": 0.66,
    },
]


_MOCK_LLM_JSON = json.dumps({
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


def _parse_sse_events(chunks: List[str]):
    """Convert raw SSE-formatted strings into a list of (event, data) tuples."""
    out = []
    text = "".join(chunks)
    # Each event is "event: <name>\ndata: <json>\n\n"
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


class AskOrchestratorTests(unittest.TestCase):
    def test_full_stream_event_sequence(self):
        """Happy path: mock LLM returns valid JSON, all 7 event types emit."""
        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)

        # Patch out the network call and the typewriter sleep so the test
        # runs in <100ms regardless of asyncio loop scheduling.
        with patch.object(AskOrchestrator, "_call_llm_once", return_value=_MOCK_LLM_JSON), \
             patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("为什么银行系统会突然崩溃？", lang="zh")))

        events = _parse_sse_events(chunks)
        names = [e[0] for e in events]

        # Spec ordering: meta first, kb_cards second, done last.
        self.assertEqual(names[0], "meta")
        self.assertEqual(names[1], "kb_cards")
        self.assertEqual(names[-1], "done")

        # All required event types present.
        for required in (
            "meta",
            "kb_cards",
            "answer_chunk",
            "answer_done",
            "similar_phenomena",
            "followups",
            "done",
        ):
            self.assertIn(required, names, f"missing event: {required}")

        # meta payload sanity.
        meta_data = events[names.index("meta")][1]
        self.assertEqual(meta_data["query"], "为什么银行系统会突然崩溃？")
        self.assertEqual(meta_data["lang"], "zh")
        self.assertIn("started_at", meta_data)

        # kb_cards: 5 cards from fixture.
        kb_data = events[names.index("kb_cards")][1]
        self.assertEqual(kb_data["count"], 5)
        self.assertEqual(len(kb_data["cards"]), 5)
        self.assertEqual(kb_data["cards"][0]["id"], "phen-1")

        # answer_chunk events accumulate to the full answer text.
        accumulated = "".join(
            ev["delta"] for name, ev in events if name == "answer_chunk"
        )
        answer_done = next(ev for name, ev in events if name == "answer_done")
        self.assertEqual(accumulated, answer_done["full_text"])
        self.assertGreater(len(answer_done["full_text"]), 20)

        # Citations: 3 emitted, all idx in 1..5, kb_id rewritten to canonical.
        citations = answer_done["citations"]
        self.assertEqual(len(citations), 3)
        for cit in citations:
            self.assertIn(cit["idx"], (1, 2, 3, 4, 5))
            self.assertTrue(cit["kb_id"].startswith("phen-"))

        # similar_phenomena: top-3 with key_metric and kb_id.
        sim = next(ev for name, ev in events if name == "similar_phenomena")
        self.assertEqual(len(sim["phenomena"]), 3)
        for p in sim["phenomena"]:
            self.assertIn("name", p)
            self.assertIn("domain", p)
            self.assertIn("key_metric", p)
            self.assertIn("kb_id", p)

        # followups: 3 questions, all non-empty strings.
        fu = next(ev for name, ev in events if name == "followups")
        self.assertEqual(len(fu["questions"]), 3)
        for q in fu["questions"]:
            self.assertIsInstance(q, str)
            self.assertGreater(len(q.strip()), 0)

        # done: latency_ms is a non-negative int.
        done = next(ev for name, ev in events if name == "done")
        self.assertGreaterEqual(done["latency_ms"], 0)

    def test_citation_idx_out_of_cards_range_dropped(self):
        """LLM returns idx=8 (passes schema 1-20 but exceeds cards=5) -> dropped at canonicalization."""
        # idx=8 satisfies the pydantic schema (1..20) but our fake KB has
        # only 5 cards, so _validate_citations must drop it.
        partly_bad = json.dumps({
            "answer": "网络级联 [1] 与森林火灾 [8] 是同一结构。" * 3,
            "citations": [
                {"idx": 1, "kb_id": "phen-1", "label": "ok"},
                {"idx": 8, "kb_id": "fake", "label": "should-be-dropped"},
            ],
            "followups": ["问题a?", "问题b?", "问题c?"],
        }, ensure_ascii=False)

        search = _FakeSearch(_FIXED_KB)
        orch = AskOrchestrator(search_service=search)

        with patch.object(AskOrchestrator, "_call_llm_once", return_value=partly_bad), \
             patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("test", lang="zh")))

        events = _parse_sse_events(chunks)
        answer_done = next(ev for name, ev in events if name == "answer_done")
        # The idx=8 must be dropped at the cards-range validation step;
        # only the valid idx=1 survives with canonical kb_id from cards.
        self.assertEqual(len(answer_done["citations"]), 1)
        self.assertEqual(answer_done["citations"][0]["idx"], 1)
        self.assertEqual(answer_done["citations"][0]["kb_id"], "phen-1")

    def test_pydantic_schema_directly(self):
        """Sanity-check the schema rejects too-short answers."""
        with self.assertRaises(Exception):
            AskAnswerPayload(
                answer="short",  # < 20 chars → reject
                citations=[{"idx": 1, "kb_id": "k", "label": "L"}],
                followups=["a?", "b?"],
            )


if __name__ == "__main__":
    unittest.main()
