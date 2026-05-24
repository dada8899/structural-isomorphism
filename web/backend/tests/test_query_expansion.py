"""X2 W2 (2026-05-24) — LLM query expansion (5 tests per spec).

Spec-mandated coverage:
  1. unit test _expand_query mock LLM — original at index 0, expansions appended
  2. integration test 4 条并联召回 — fan-out + fuse_results union-by-id
  3. 缓存命中 — second call same query is free
  4. 降级路径 — LLM error returns [original_query], no crash
  5. cost 超限 — when per-call estimate > cap, no LLM call, fallback

The pipeline-level retrieval log + EN-translation integration are tested
in test_retrieval_pipeline.py and test_lang_detection.py respectively to
keep this file focused on the expansion primitive itself.
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

from services import query_expansion as qe  # noqa: E402
from services import retrieval_pipeline as rp  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_cache():
    qe.reset_cache_for_tests()
    qe.reset_translate_cache_for_tests()
    yield
    qe.reset_cache_for_tests()
    qe.reset_translate_cache_for_tests()


def _async(coro):
    """Py 3.14: asyncio.run creates a fresh loop per call."""
    return asyncio.run(coro)


# --- 1. Unit: mock LLM → original + 3 expansions -------------------------


def test_expand_query_unit_mock_llm_returns_original_plus_expansions():
    mock_llm = AsyncMock(return_value={
        "expansions": ["银行挤兑", "流动性危机", "bank run"],
    })
    result = _async(qe.expand_query(
        "硅谷银行挤兑",
        llm_complete_json=mock_llm,
    ))
    assert result[0] == "硅谷银行挤兑", "Original query must lead"
    assert len(result) == 4
    assert {"银行挤兑", "流动性危机", "bank run"}.issubset(set(result))
    mock_llm.assert_awaited_once()


# --- 2. Integration: 4 条 query 并联召回 + fusion + 隐私日志 -------------


def test_four_queries_run_in_parallel_and_fuse_by_id(tmp_path, monkeypatch):
    """Spec covers two things in one integration:
       - 4 conditions issued; search_fn called 4 times in parallel
       - retrieval.jsonl row written with HASHED query (X2 caveat: no
         raw query content stored; only sha256-16 hash for correlation)
    """
    log_path = tmp_path / "retrieval.jsonl"
    monkeypatch.setattr(rp, "_LOG_PATH", log_path)
    mock_llm = AsyncMock(return_value={
        "expansions": ["银行挤兑", "流动性危机", "bank run"],
    })

    calls = []
    by_query = {
        "硅谷银行挤兑":      [{"id": "k1", "score": 0.85}],
        "银行挤兑":         [{"id": "k1", "score": 0.92},  # overlap, higher
                            {"id": "k2", "score": 0.70}],
        "流动性危机":        [{"id": "k3", "score": 0.78}],
        "bank run":         [{"id": "k4", "score": 0.55}],
    }

    def search_fn(q, top_k):
        calls.append(q)
        return by_query.get(q, [])

    out = _async(rp.retrieve_with_expansion(
        "硅谷银行挤兑",
        search_fn=search_fn,
        llm_complete_json=mock_llm,
        top_k=10,
    ))

    # 4 candidates issued, search called 4 times
    assert len(out["candidate_queries"]) == 4
    assert len(calls) == 4
    # k1 retained the higher score 0.92 (cross-query max-fuse)
    k1 = next(r for r in out["results"] if r["id"] == "k1")
    assert k1["score"] == 0.92
    # All 4 distinct ids appear in fused result
    assert {r["id"] for r in out["results"]} == {"k1", "k2", "k3", "k4"}

    # Retrieval log written, hashed only, no raw query content leaked
    import json
    rows = log_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(rows) == 1
    row = json.loads(rows[0])
    assert len(row["query_hash"]) == 16
    assert "硅谷银行挤兑" not in json.dumps(row, ensure_ascii=False)
    assert row["expansion_used"] is True
    assert row["top_5_kb_ids"][:1] == ["k1"]


# --- 3. 缓存命中 ----------------------------------------------------------


def test_cache_hit_avoids_second_llm_call():
    mock_llm = AsyncMock(return_value={
        "expansions": ["a", "b", "c"],
    })
    q = "硅谷银行挤兑"
    r1 = _async(qe.expand_query(q, llm_complete_json=mock_llm))
    r2 = _async(qe.expand_query(q, llm_complete_json=mock_llm))
    assert r1 == r2
    assert mock_llm.await_count == 1  # cache spared the second LLM call
    stats = qe.cache_stats()
    assert stats["cache_hits"] == 1


# --- 4. 降级路径 -----------------------------------------------------------


def test_llm_failure_falls_back_to_original_only():
    mock_llm = AsyncMock(side_effect=RuntimeError("network down"))
    result = _async(qe.expand_query("test query", llm_complete_json=mock_llm))
    assert result == ["test query"]
    stats = qe.cache_stats()
    assert stats["llm_failures"] >= 1
    assert stats["fallbacks"] >= 1


# --- 5. cost 超限 ----------------------------------------------------------


def test_cost_cap_blocks_llm_call(monkeypatch):
    """Per-call estimate above EXPANSION_MAX_COST_USD → no LLM call."""
    monkeypatch.setattr(qe, "_ESTIMATED_COST_PER_CALL_USD", 0.005)  # > 0.001 cap
    mock_llm = AsyncMock(return_value={"expansions": ["x", "y", "z"]})
    result = _async(qe.expand_query("expensive query", llm_complete_json=mock_llm))
    assert result == ["expensive query"]
    mock_llm.assert_not_awaited()
    assert qe.cache_stats()["cost_capped"] >= 1
