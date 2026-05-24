"""X2 W3 (2026-05-24) — language detection + EN→ZH translation (3 tests per spec).

Spec-mandated coverage:
  1. 中文 query 直走 — _detect_lang('zh'), no translation invoked
  2. EN query 翻译路径 — _detect_lang('en'), LLM translation called,
     translated ZH appears as a parallel embedding seed, original EN kept
     for BM25
  3. 混合双语 query 兜底 — _detect_lang('mixed'), translation skipped
     (mixed already has ZH content for embedding)
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
_ROOT = _BACKEND.parent.parent
for p in (_BACKEND, _ROOT):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from services.search_service import _detect_lang  ***REMOVED*** noqa: E402
from services import query_expansion as qe  ***REMOVED*** noqa: E402
from services import retrieval_pipeline as rp  ***REMOVED*** noqa: E402


@pytest.fixture(autouse=True)
def _reset(tmp_path, monkeypatch):
    qe.reset_cache_for_tests()
    qe.reset_translate_cache_for_tests()
    monkeypatch.setattr(rp, "_LOG_PATH", tmp_path / "retrieval.jsonl")
    yield
    qe.reset_cache_for_tests()
    qe.reset_translate_cache_for_tests()


def _async(coro):
    return asyncio.run(coro)


***REMOVED*** --- 1. 中文 query 直走 -----------------------------------------------------


def test_chinese_query_skips_translation():
    """ZH-only query → lang='zh', translation_used=False."""
    assert _detect_lang("硅谷银行挤兑后市场反应剧烈的原因") == "zh"

    translate_calls = []
    async def mock_llm(*, system, user, **kwargs):
        translate_calls.append(system[:20])
        return {"expansions": ["a", "b", "c"]}  ***REMOVED*** only expansion is called

    def search_fn(q, top_k):
        return [{"id": "k1", "score": 0.8}]

    out = _async(rp.retrieve_with_expansion(
        "硅谷银行挤兑后市场反应剧烈的原因",
        search_fn=search_fn,
        llm_complete_json=mock_llm,
    ))
    assert out["lang_detected"] == "zh"
    assert out["translation_used"] is False
    ***REMOVED*** No call should hit the translation system prompt
    assert not any("翻译" in s for s in translate_calls)


***REMOVED*** --- 2. EN query 走翻译路径 -----------------------------------------------


def test_english_query_triggers_translation_and_parallel_seed():
    """EN query → translation invoked; both EN (BM25) and ZH (embed) issued."""
    assert _detect_lang("power-law distribution in social networks") == "en"

    async def mock_llm(*, system, user, **kwargs):
        if "翻译助手" in system or "翻译成简洁的中文" in system:
            return {"zh": "幂律分布"}
        return {"expansions": ["幂律", "重尾", "Pareto"]}

    by_query = {
        "power-law distribution in social networks": [{"id": "k1", "score": 0.40}],
        "幂律分布": [{"id": "k2", "score": 0.85}],
        "幂律":   [{"id": "k3", "score": 0.80}],
        "重尾":   [{"id": "k4", "score": 0.75}],
        "Pareto": [{"id": "k5", "score": 0.50}],
    }

    def search_fn(q, top_k):
        return by_query.get(q, [])

    out = _async(rp.retrieve_with_expansion(
        "power-law distribution in social networks",
        search_fn=search_fn,
        llm_complete_json=mock_llm,
    ))
    assert out["lang_detected"] == "en"
    assert out["translation_used"] is True
    ***REMOVED*** Both EN original (BM25 lane) and ZH translation (embedding lane) issued
    assert "power-law distribution in social networks" in out["candidate_queries"]
    assert "幂律分布" in out["candidate_queries"]
    ***REMOVED*** Translated ZH yielded the top hit (k2 with 0.85)
    assert out["results"][0]["id"] == "k2"


***REMOVED*** --- 3. 混合双语 query 兜底 ------------------------------------------------


def test_mixed_lang_query_falls_through_without_translation():
    """Mixed CJK + ASCII query → 'mixed', translation skipped (already has ZH)."""
    ***REMOVED*** CJK=4 (挤兑现象) + ASCII letters=14 (power+law+and) → ratio > 0.3 → mixed
    assert _detect_lang("挤兑现象 and power law") == "mixed"

    translate_calls = []
    async def mock_llm(*, system, user, **kwargs):
        if "翻译助手" in system or "翻译成简洁的中文" in system:
            translate_calls.append(True)
            return {"zh": "should not be called"}
        return {"expansions": ["a", "b", "c"]}

    def search_fn(q, top_k):
        return [{"id": "k1", "score": 0.7}]

    out = _async(rp.retrieve_with_expansion(
        "挤兑现象 and power law",
        search_fn=search_fn,
        llm_complete_json=mock_llm,
    ))
    assert out["lang_detected"] == "mixed"
    assert out["translation_used"] is False
    assert len(translate_calls) == 0, \
        "Translation must not be invoked for mixed queries"
