"""Unit tests for the W5-A out-of-scope rejection guardrail.

Background — W4-D dogfood report (docs/dogfood-ask-2026-05-15.md) found
that edge queries like "我女朋友为什么生气" / "1+1=?" / "BTC 明天涨跌"
硬拗 isomorphism answers despite all retrieved KB items scoring < 0.75.
q6 burned 33s of LLM time producing 494 chars of forced analogy.

M1.3 guardrail tested here:
  - AskOrchestrator._evaluate_relevance gates on top-1 < RELEVANCE_TOP1_MIN
    OR top-3 mean < RELEVANCE_TOP3_MEAN_MIN (or empty cards).
  - Refusal payload, followups and typewriter helpers remain pure tests.
  - Retired stream() rejects before retrieval, provider, cost or SSE emission.

Pure helper checks do not claim that the retired generation stream runs.

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
# Layer B: in-scope prompt shape
# --------------------------------------------------------------------------

class PromptTests(unittest.TestCase):
    """`_build_prompt` always produces the in-scope synthesis prompt — the
    out-of-scope branch was removed in M1.3 (refusal short-circuits before
    the LLM is ever reached, so a low-relevance prompt is never built)."""

    def setUp(self):
        self.orch = AskOrchestrator(search_service=_FakeSearch([]))

    def test_in_scope_prompt_shape(self):
        """In-scope prompt asks for a 200-400 char answer with [n] citations."""
        prompt = self.orch._build_prompt(
            "SVB bank run?", _HIGH_REL_KB, lang="zh", strict_json=False,
        )
        self.assertIn("200-400", prompt)
        self.assertIn("[1] [2]", prompt)
        # The removed out-of-scope wording must not leak back in.
        self.assertNotIn("超出 Structural 当前覆盖范围", prompt)

    def test_strict_json_appends_reminder(self):
        """strict_json=True appends the JSON-only reminder block."""
        normal = self.orch._build_prompt(
            "q", _HIGH_REL_KB, lang="zh", strict_json=False,
        )
        strict = self.orch._build_prompt(
            "q", _HIGH_REL_KB, lang="zh", strict_json=True,
        )
        self.assertNotIn("严格要求", normal)
        self.assertIn("严格要求", strict)


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
# Retired runtime admission plus surviving pure refusal helpers
# --------------------------------------------------------------------------

class OutOfScopeStreamTests(unittest.TestCase):
    """Pure refusal contracts and zero-effect admission for retired generation."""

    def _assert_closed(self, kb, query):
        from errors import LegacyPaidUnavailable
        from services.cost_ledger import ledger

        search = _FakeSearch(kb)
        orch = AskOrchestrator(search_service=search)
        calls = {"search": 0, "once": 0, "stream": 0, "cost": 0}
        emitted = []

        def retrieve(*args, **kwargs):
            calls["search"] += 1
            return kb

        async def once(*args, **kwargs):
            calls["once"] += 1
            return _MOCK_IN_SCOPE_JSON

        async def stream(*args, **kwargs):
            calls["stream"] += 1
            yield ("error", "unexpected generation")

        def charge(*args, **kwargs):
            calls["cost"] += 1

        async def collect():
            async for chunk in orch.stream(query, lang="zh"):
                emitted.append(chunk)

        with patch.object(search, "search", retrieve), \
             patch.object(orch, "_call_llm_once", once), \
             patch.object(orch, "_call_llm_stream", stream), \
             patch.object(ledger, "charge", charge):
            with self.assertRaises(LegacyPaidUnavailable) as unavailable:
                asyncio.run(collect())
        self.assertEqual(unavailable.exception.status, 503)
        self.assertIs(unavailable.exception.extensions["retryable"], False)
        self.assertEqual(emitted, [])
        self.assertEqual(calls, {"search": 0, "once": 0, "stream": 0, "cost": 0})
        return orch

    def test_pure_low_relevance_refusal_and_retired_stream_without_llm(self):
        orch = self._assert_closed(_LOW_REL_KB, "求 1+1 = ?")
        refused, reason = orch._evaluate_relevance(_LOW_REL_KB)
        self.assertTrue(refused)
        self.assertTrue(reason.startswith(("top1_below_", "top3_mean_below_")))
        payload = orch._build_refusal_payload("求 1+1 = ?", _LOW_REL_KB, "zh", reason)
        self.assertIn("覆盖范围", payload["answer"])
        self.assertNotIn("citations", payload)

    def test_pure_refusal_chunks_reconstruct_full_text(self):
        orch = AskOrchestrator(search_service=None)
        payload = orch._build_refusal_payload("BTC 明天涨跌?", [], "zh", "forecasting_intent")
        chunks = orch._typewriter_chunks(payload["answer"])
        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunks), payload["answer"])

    def test_pure_refusal_has_three_distinct_in_scope_followups(self):
        from services.scope_guard import is_out_of_scope
        orch = AskOrchestrator(search_service=None)
        payload = orch._build_refusal_payload("1+1=?", _LOW_REL_KB, "zh", "off_topic_arithmetic")
        followups = payload["followups"]
        self.assertEqual(len(followups), 3)
        self.assertEqual(len(set(followups)), 3)
        self.assertTrue(all(isinstance(q, str) and q.strip() for q in followups))
        self.assertTrue(all(not is_out_of_scope(q)[0] for q in followups))

    def test_pure_empty_similar_projection_and_no_weak_card_publication(self):
        orch = self._assert_closed(_LOW_REL_KB, "1+1=?")
        self.assertEqual(orch._build_similar_phenomena([]), [])
        self.assertTrue(orch._evaluate_relevance(_LOW_REL_KB)[0])

    def test_pure_empty_search_relevance_reason_is_no_cards(self):
        orch = self._assert_closed([], "xyzzy plugh qwerty")
        self.assertEqual(orch._evaluate_relevance([]), (True, "no_cards"))
        payload = orch._build_refusal_payload("xyzzy plugh qwerty", [], "zh", "no_cards")
        self.assertTrue(payload["answer"])
        self.assertNotRegex(payload["answer"], r"\[[0-9]+\]")

    def test_pure_sse_serialization_and_retired_stream_emits_no_events(self):
        from services.ask_orchestrator import _sse
        self._assert_closed(_LOW_REL_KB, "1+1=?")
        # Encoder format remains testable; no retired runtime event sequence is promised.
        payload = {"code": "FEATURE_UNAVAILABLE", "retryable": False}
        self.assertEqual(_parse_sse([_sse("error", payload)]), [("error", payload)])

    def test_pure_high_relevance_schema_and_retired_stream_still_closed(self):
        from services.ask_schemas import AskAnswerPayload
        orch = self._assert_closed(_HIGH_REL_KB, "Why do banks collapse?")
        self.assertEqual(orch._evaluate_relevance(_HIGH_REL_KB), (False, "ok"))
        payload = AskAnswerPayload.model_validate_json(_MOCK_IN_SCOPE_JSON)
        self.assertEqual(payload.citations[0].kb_id, "phen-h-1")
        self.assertEqual(len(payload.followups), 3)
        prompt = orch._build_prompt("Why do banks collapse?", _HIGH_REL_KB, lang="zh", strict_json=False)
        self.assertIn("[1] [2]", prompt)


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

# --------------------------------------------------------------------------
# Layer C: forecasting-intent keyword gate (session #16)
# --------------------------------------------------------------------------

from services.ask_orchestrator import _is_forecasting_intent  # noqa: E402


class ForecastingIntentGateTests(unittest.TestCase):
    """Pure-function tests on _is_forecasting_intent.

    Catches the "AI 能不能预测股票" class of query that retrieves OK
    (KB has "科技泡沫" / "投资判断" with decent cosine) but whose intent
    we deterministically refuse.
    """

    # ---- positive: should trip ---------------------------------------- #

    def test_predict_crypto_zh(self):
        self.assertTrue(_is_forecasting_intent("AI 能不能预测加密货币", "zh"))

    def test_predict_stock_zh(self):
        self.assertTrue(_is_forecasting_intent("帮我预测股价走势", "zh"))

    def test_tomorrow_rise_zh(self):
        self.assertTrue(_is_forecasting_intent("BTC 明天涨吗", "zh"))

    def test_recommend_stock_zh(self):
        self.assertTrue(_is_forecasting_intent("推荐股票，下周买什么", "zh"))

    def test_price_target_zh(self):
        self.assertTrue(_is_forecasting_intent("茅台涨到多少", "zh"))

    def test_predict_crypto_en(self):
        self.assertTrue(_is_forecasting_intent("Can AI predict crypto prices", "en"))

    def test_will_rise_tomorrow_en(self):
        self.assertTrue(_is_forecasting_intent("Will Tesla rise tomorrow", "en"))

    def test_stock_pick_en(self):
        self.assertTrue(_is_forecasting_intent("Stock pick for next week", "en"))

    # ---- negative: in-scope questions must NOT trip ------------------- #

    def test_structural_question_zh_passes(self):
        """The keyword 预测 alone is OK if not paired with a financial asset."""
        self.assertFalse(
            _is_forecasting_intent("临界相变能不能提前预警", "zh")
        )

    def test_isomorphism_question_zh_passes(self):
        self.assertFalse(
            _is_forecasting_intent("银行挤兑和森林大火的级联机制是什么", "zh")
        )

    def test_cascade_question_en_passes(self):
        self.assertFalse(
            _is_forecasting_intent("How do bank runs cascade", "en")
        )

    def test_empty_query_returns_false(self):
        self.assertFalse(_is_forecasting_intent("", "zh"))
        self.assertFalse(_is_forecasting_intent("", "en"))


class ForecastingRefusalPayloadTests(unittest.TestCase):
    """Verify _build_refusal_payload emits a forecasting-specific message
    when scope_reason='forecasting_intent', not the generic 'no_cards' one."""

    def setUp(self):
        self.orch = AskOrchestrator(search_service=_FakeSearch([]))

    def test_forecasting_refusal_zh_specific_wording(self):
        payload = self.orch._build_refusal_payload(
            "AI 预测股票",
            cards=[],
            lang="zh",
            scope_reason="forecasting_intent",
        )
        ans = payload["answer"]
        # Forecasting-specific phrasing — NOT the generic out-of-scope text
        self.assertIn("预测", ans)
        # Must call out that no AI tool can do this
        self.assertTrue(
            "包括 AI" in ans or "AI" in ans,
            f"expected AI-disclaimer in answer, got: {ans[:200]}",
        )
        # Must offer a pivot (the in-scope rephrasing)
        self.assertTrue(
            "级联" in ans or "相变" in ans or "结构" in ans,
            f"expected in-scope pivot offered, got: {ans[:200]}",
        )

    def test_forecasting_refusal_en_specific_wording(self):
        payload = self.orch._build_refusal_payload(
            "Can AI predict crypto",
            cards=[],
            lang="en",
            scope_reason="forecasting_intent",
        )
        ans = payload["answer"]
        self.assertTrue("forecast" in ans.lower() or "predict" in ans.lower())
        self.assertTrue(
            "cascade" in ans.lower() or "phase transition" in ans.lower()
            or "fragility" in ans.lower(),
            f"expected in-scope pivot offered, got: {ans[:200]}",
        )

    def test_generic_refusal_still_works(self):
        """Make sure adding forecasting branch didn't break the no_cards path."""
        payload = self.orch._build_refusal_payload(
            "1+1=?",
            cards=[],
            lang="zh",
            scope_reason="no_cards",
        )
        # No_cards path — should NOT trigger forecasting-specific phrasing
        self.assertNotIn("预测涨跌", payload["answer"])
        self.assertNotIn("不预测资产价格", payload["answer"])


if __name__ == "__main__":
    unittest.main()
