"""Unit tests for the W5-A out-of-scope rejection guardrail.

Background — W4-D dogfood report (docs/dogfood-ask-2026-05-15.md) found
that edge queries like "我女朋友为什么生气" / "1+1=?" / "BTC 明天涨跌"
硬拗 isomorphism answers despite all retrieved KB items scoring < 0.75.
q6 burned 33s of LLM time producing 494 chars of forced analogy.

Two-layer guardrail tested here:
  - Layer A (code): AskOrchestrator._evaluate_relevance gates on
    top-1 < RELEVANCE_TOP1_MIN  OR  top-3 mean < RELEVANCE_TOP3_MEAN_MIN
  - Layer B (LLM):  _build_prompt(..., low_relevance=True) switches to
    an out-of-scope branch that asks for a short, honest decline.

We mock the search service + LLM and verify the prompt path + the SSE
event payload exposes `out_of_scope=True` on `answer_done`.

Run:
    cd web/backend
    PYTHONPATH=. ../../.venv/bin/python -m pytest tests/test_out_of_scope.py -v
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure web/backend is importable when running from repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from services.ask_orchestrator import AskOrchestrator  # noqa: E402


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

# Low-relevance KB — mirrors the dogfood q5/q6/q7 retrieval pattern:
# top-1 around 0.65-0.70, all top-3 < 0.65 mean. This MUST trip both gates.
_LOW_REL_KB = [
    {
        "id": "phen-low-1",
        "name": "Bus differential protection",
        "domain": "engineering",
        "type_id": "Misc",
        "description": "Electrical relay protecting busbar by summing inflows.",
        "score": 0.70,
    },
    {
        "id": "phen-low-2",
        "name": "Routine activity criminology",
        "domain": "sociology",
        "type_id": "Misc",
        "description": "Crime as convergence of motivated offender + target + lack of guardian.",
        "score": 0.55,
    },
    {
        "id": "phen-low-3",
        "name": "Hall-Petch grain size",
        "domain": "materials",
        "type_id": "Misc",
        "description": "Strength scales with inverse sqrt of grain size.",
        "score": 0.54,
    },
]

# Borderline KB where top-1 is fine but top-3 mean barely fails — exercises
# the "top-3 mean" gate independently of the top-1 gate. Per dogfood q5
# (top-1=0.82, top-3 mean=0.747) we expect THIS pattern to trip ONLY the
# top-3 gate (top-3 mean below 0.65 threshold).
# We craft top-1=0.82 (above 0.75) with two low siblings so mean lands < 0.65.
_TOP3_MEAN_FAIL_KB = [
    {"id": "k1", "name": "phen 1", "domain": "x", "description": "...", "score": 0.82},
    {"id": "k2", "name": "phen 2", "domain": "x", "description": "...", "score": 0.55},
    {"id": "k3", "name": "phen 3", "domain": "x", "description": "...", "score": 0.55},
]
# Mean = (0.82+0.55+0.55)/3 = 0.64 → below default 0.65

# High-relevance KB — mirrors dogfood q1 (SVB) pattern. MUST NOT trip
# the gate; we assert the in-scope prompt is used.
_HIGH_REL_KB = [
    {"id": "phen-h-1", "name": "Bank run cascade", "domain": "finance",
     "description": "Cascading deposit withdrawals.", "score": 0.94},
    {"id": "phen-h-2", "name": "Trophic collapse", "domain": "ecology",
     "description": "Network cascade in food webs.", "score": 0.82},
    {"id": "phen-h-3", "name": "Information cascade", "domain": "sociology",
     "description": "Adoption following observable signals.", "score": 0.80},
]


class _FakeSearch:
    """Drop-in for SearchService.search() returning a fixed list."""

    def __init__(self, results):
        self._results = results

    def search(self, query: str, top_k: int = 5):
        return list(self._results)[:top_k]


_MOCK_IN_SCOPE_JSON = json.dumps({
    "answer": "银行挤兑是经典的网络级联 [1]。深度足够。" + "x" * 50,
    "citations": [
        {"idx": 1, "kb_id": "phen-h-1", "label": "bank run"},
    ],
    "followups": ["q1?", "q2?", "q3?"],
}, ensure_ascii=False)


def _parse_sse(chunks):
    """Decode SSE-formatted strings into (event, payload) tuples."""
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


# --------------------------------------------------------------------------
# Layer A: code-level relevance gate
# --------------------------------------------------------------------------

class RelevanceGateTests(unittest.TestCase):
    """Pure-function tests on AskOrchestrator._evaluate_relevance."""

    def setUp(self):
        # The orchestrator constructor doesn't touch the network unless
        # stream() is awaited, so a bare instance is safe.
        self.orch = AskOrchestrator(search_service=_FakeSearch([]))

    def test_empty_cards_trips_gate(self):
        low, reason = self.orch._evaluate_relevance([])
        self.assertTrue(low)
        self.assertEqual(reason, "no_cards")

    def test_top1_below_threshold_trips_gate(self):
        """q6-style pattern: top-1 = 0.70 < 0.75 (default) → low."""
        low, reason = self.orch._evaluate_relevance(_LOW_REL_KB)
        self.assertTrue(low)
        self.assertIn("top1_below", reason)

    def test_top3_mean_below_threshold_trips_gate(self):
        """q5-style pattern: top-1 OK but top-3 mean fails."""
        low, reason = self.orch._evaluate_relevance(_TOP3_MEAN_FAIL_KB)
        self.assertTrue(low)
        # top-1=0.82 > 0.75, so top-1 gate passes; top-3 mean gate trips.
        self.assertIn("top3_mean_below", reason)

    def test_high_relevance_passes_gate(self):
        """q1-style SVB pattern: both gates pass."""
        low, reason = self.orch._evaluate_relevance(_HIGH_REL_KB)
        self.assertFalse(low)
        self.assertEqual(reason, "ok")

    def test_missing_score_field_treated_as_zero(self):
        """Defensive: search backend missing 'score' → treat as 0 → gate trips.

        Better to degrade to honest decline than confidently hallucinate.
        """
        bad_cards = [{"id": "x", "name": "n", "domain": "d", "description": ""}]
        low, reason = self.orch._evaluate_relevance(bad_cards)
        self.assertTrue(low)

    def test_non_numeric_score_treated_as_zero(self):
        """Score = 'NaN' string → treated as 0 → gate trips."""
        bad_cards = [{"id": "x", "name": "n", "domain": "d",
                      "description": "", "score": "bogus"}]
        low, reason = self.orch._evaluate_relevance(bad_cards)
        self.assertTrue(low)


# --------------------------------------------------------------------------
# Layer B: LLM prompt branching
# --------------------------------------------------------------------------

class PromptBranchingTests(unittest.TestCase):
    """Verify _build_prompt switches branches when low_relevance=True."""

    def setUp(self):
        self.orch = AskOrchestrator(search_service=_FakeSearch([]))

    def test_low_relevance_prompt_contains_out_of_scope_instruction(self):
        prompt = self.orch._build_prompt(
            "1+1=?", _LOW_REL_KB, lang="zh",
            strict_json=False, low_relevance=True,
        )
        # Out-of-scope branch must explicitly tell the model to decline.
        self.assertIn("超出", prompt)
        self.assertIn("覆盖范围", prompt)
        # Must tell the model NOT to use [n] citation markers.
        self.assertIn("不要", prompt)

    def test_low_relevance_prompt_english_branch(self):
        prompt = self.orch._build_prompt(
            "What's 1+1?", _LOW_REL_KB, lang="en",
            strict_json=False, low_relevance=True,
        )
        self.assertIn("OUTSIDE", prompt)
        self.assertIn("structural-isomorphism", prompt.lower())

    def test_in_scope_prompt_unchanged(self):
        """Regression: in-scope prompt MUST still ask for 200-400 char answer
        with [n] citations. We don't want to accidentally degrade the
        happy path."""
        prompt = self.orch._build_prompt(
            "SVB bank run?", _HIGH_REL_KB, lang="zh",
            strict_json=False, low_relevance=False,
        )
        self.assertIn("200-400", prompt)
        self.assertIn("[1] [2]", prompt)
        self.assertNotIn("超出 Structural 当前覆盖范围", prompt)

    def test_low_relevance_flag_defaults_false(self):
        """Backward compatibility: existing callers without low_relevance
        kwarg get the original in-scope prompt."""
        prompt = self.orch._build_prompt(
            "test", _HIGH_REL_KB, lang="zh", strict_json=False,
        )
        self.assertIn("200-400", prompt)


# --------------------------------------------------------------------------
# M1.3: local refusal payload builder (pure function, no LLM)
# --------------------------------------------------------------------------

class RefusalPayloadTests(unittest.TestCase):
    """Pure-function tests on AskOrchestrator._build_refusal_payload."""

    def setUp(self):
        self.orch = AskOrchestrator(search_service=_FakeSearch([]))

    def test_no_cards_reason_zh(self):
        p = self.orch._build_refusal_payload("1+1=?", [], "zh", "no_cards")
        self.assertIn("没有匹配到", p["answer"])
        self.assertEqual(len(p["followups"]), 3)

    def test_low_score_reason_zh(self):
        p = self.orch._build_refusal_payload(
            "BTC?", _LOW_REL_KB, "zh", "top1_below_0.75")
        self.assertIn("超出", p["answer"])
        self.assertIn("覆盖范围", p["answer"])
        self.assertEqual(len(p["followups"]), 3)

    def test_english_branch(self):
        p = self.orch._build_refusal_payload(
            "What's 1+1?", _LOW_REL_KB, "en", "top3_mean_below_0.65")
        self.assertIn("knowledge base", p["answer"])
        self.assertEqual(len(p["followups"]), 3)

    def test_answer_length_reasonable(self):
        """Refusal answer stays short & honest across every reason / lang."""
        for reason in ("no_cards", "top1_below_0.75", "top3_mean_below_0.65"):
            for lang in ("zh", "en"):
                p = self.orch._build_refusal_payload("q", [], lang, reason)
                self.assertGreaterEqual(len(p["answer"]), 40)
                self.assertLessEqual(len(p["answer"]), 600)

    def test_no_citation_markers_in_answer(self):
        """Refusal text must NOT contain [n] citation markers — the whole
        point is to stop pretending the weak KB hits are relevant."""
        p = self.orch._build_refusal_payload("q", _LOW_REL_KB, "zh", "no_cards")
        self.assertNotRegex(p["answer"], r"\[\d+\]")

    def test_followups_distinct_non_empty(self):
        p = self.orch._build_refusal_payload("q", [], "zh", "no_cards")
        fu = p["followups"]
        self.assertEqual(len(fu), len(set(fu)))
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in fu))


# --------------------------------------------------------------------------
# Integration: M1.3 refusal short-circuits the SSE stream without an LLM call
# --------------------------------------------------------------------------

class OutOfScopeStreamTests(unittest.TestCase):
    """End-to-end SSE behavior with the M1.3 refusal short-circuit."""

    def _run_refused(self, kb, query):
        """Run stream() with LLM-call counters. Returns (events, calls).

        Both LLM entry points are patched with counting stand-ins so a
        passing test PROVES the refusal path never touched the network —
        an AssertionError would be swallowed by stream()'s broad
        `except Exception`, so we assert call counts instead of raising.
        """
        orch = AskOrchestrator(search_service=_FakeSearch(kb))
        calls = {"once": 0, "stream": 0}

        async def _track_once(self, prompt):
            calls["once"] += 1
            return _MOCK_IN_SCOPE_JSON

        async def _track_stream(self, prompt):
            calls["stream"] += 1
            yield ("error", "should-not-be-called")

        with patch.object(AskOrchestrator, "_call_llm_once", new=_track_once), \
             patch.object(AskOrchestrator, "_call_llm_stream", new=_track_stream), \
             patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream(query, lang="zh")))
        return _parse_sse(chunks), calls

    def test_low_relevance_query_refused_without_llm(self):
        """Low-score retrieval → local refusal, ZERO LLM calls."""
        events, calls = self._run_refused(_LOW_REL_KB, "求 1+1 = ?")
        self.assertEqual(calls["once"], 0, "refusal path must not call LLM")
        self.assertEqual(calls["stream"], 0, "refusal path must not call LLM")
        answer_done = next(p for n, p in events if n == "answer_done")
        self.assertTrue(answer_done.get("out_of_scope"))
        self.assertTrue(answer_done.get("refused"))
        self.assertIsInstance(answer_done.get("scope_reason"), str)
        self.assertEqual(answer_done.get("citations"), [])
        # The streamed answer is the LOCAL refusal text — honest & short.
        self.assertIn("覆盖范围", answer_done["full_text"])
        # No LLM call → no `llm_start` event.
        self.assertNotIn("llm_start", [n for n, _ in events])

    def test_refusal_answer_chunks_reconstruct_full_text(self):
        """Typewriter answer_chunks must concatenate exactly to full_text."""
        events, _ = self._run_refused(_LOW_REL_KB, "BTC 明天涨跌?")
        answer_done = next(p for n, p in events if n == "answer_done")
        streamed = "".join(p["delta"] for n, p in events if n == "answer_chunk")
        self.assertEqual(streamed, answer_done["full_text"])

    def test_refusal_emits_three_in_scope_followups(self):
        events, _ = self._run_refused(_LOW_REL_KB, "1+1=?")
        followups = next(p for n, p in events if n == "followups")
        self.assertEqual(len(followups["questions"]), 3)

    def test_refusal_emits_empty_similar_phenomena(self):
        """Weak cards must NOT be surfaced as 'similar phenomena'."""
        events, _ = self._run_refused(_LOW_REL_KB, "1+1=?")
        similar = next(p for n, p in events if n == "similar_phenomena")
        self.assertEqual(similar["phenomena"], [])

    def test_empty_search_results_trigger_refusal(self):
        """No KB cards retrieved → refused with scope_reason=no_cards."""
        events, calls = self._run_refused([], "?? ?? ??")
        self.assertEqual(calls["once"] + calls["stream"], 0)
        answer_done = next(p for n, p in events if n == "answer_done")
        self.assertTrue(answer_done.get("refused"))
        self.assertEqual(answer_done["scope_reason"], "no_cards")

    def test_refusal_sse_sequence_well_formed(self):
        """Refusal still emits a complete, ordered SSE event sequence."""
        events, _ = self._run_refused(_LOW_REL_KB, "1+1=?")
        names = [n for n, _ in events]
        for required in ("meta", "retrieval_done", "kb_cards", "answer_done",
                         "similar_phenomena", "followups", "done"):
            self.assertIn(required, names)
        self.assertEqual(names[-1], "done", "`done` must be the last event")

    def test_high_relevance_query_not_refused(self):
        """SVB-style query: in-scope path runs the LLM, no `refused` flag,
        and M1.2 fix 4's `llm_start` event is emitted."""
        search = _FakeSearch(_HIGH_REL_KB)
        orch = AskOrchestrator(search_service=search)

        with patch.object(
            AskOrchestrator, "_call_llm_once",
            return_value=_MOCK_IN_SCOPE_JSON,
        ), patch("services.ask_orchestrator.TYPEWRITER_SLEEP_S", 0):
            chunks = asyncio.run(_collect(orch.stream("Why do banks collapse?", lang="zh")))

        events = _parse_sse(chunks)
        names = [n for n, _ in events]
        answer_done = next(p for n, p in events if n == "answer_done")
        self.assertFalse(answer_done.get("out_of_scope", False))
        self.assertFalse(answer_done.get("refused", False))
        # M1.2 fix 4: the in-scope path signals the LLM call to the frontend.
        self.assertIn("llm_start", names)


# --------------------------------------------------------------------------
# Follow-up: prod evidence (NOT a test — recorded for human follow-up)
# --------------------------------------------------------------------------
#
# These cases verify the mock path only. After this PR lands, the
# dogfooder should re-run the W4-D suite against prod with real LLM and
# verify:
#
#   q5 "女朋友为什么生气" → answer < 200 chars, no [n] markers
#   q6 "1+1=?"            → answer < 200 chars, no [n] markers
#   q7 "BTC 明天涨跌"      → answer < 200 chars, polite refusal
#
# AND that q1/q2/q3/q4 STILL get full 200-400 char isomorphism answers
# (no regression on the happy path).
#
# Real-env e2e is intentionally NOT automated here because it costs real
# OpenRouter $; track as follow-up in docs/dogfood-ask-2026-05-15.md.

if __name__ == "__main__":
    unittest.main()
