"""X2 quick wins (2026-05-24) — unified retrieval pipeline.

Combines W2 (LLM query expansion) + W3 (EN→ZH translation) + structured
retrieval logging into a single async entry point used by /api/ask.

Flow:
    user_query
      ├─ detect_lang
      │    ├─ 'en'   → translate_en_to_zh (LLM, cached) → zh_for_embedding
      │    └─ 'zh'/'mixed' → pass through
      ├─ expand_query (LLM, cached) → up to 4 query variants
      ├─ parallel SearchService.search() over all variants
      ├─ fuse_results (union-by-id, max-score)
      └─ structured log line → web/backend/logs/retrieval.jsonl

Failure modes are all soft — every external call has a timeout + fallback
back to the original query, so retrieval never blocks on LLM availability.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional

from services import query_expansion as qe
from services.search_service import _detect_lang

logger = logging.getLogger("structural.retrieval_pipeline")


***REMOVED*** --- Retrieval log sink -----------------------------------------------------

***REMOVED*** Independent jsonl so a future "1 week from now, quantify expansion lift"
***REMOVED*** pass can read just this file. Living under web/backend/logs/ next to the
***REMOVED*** existing server.jsonl. The directory is created on first write.
_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "logs" / "retrieval.jsonl"
)


def _write_retrieval_log(payload: Dict) -> None:
    """Append one JSON line. Never raises — log failure must not break ask."""
    try:
        _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception as e:  ***REMOVED*** noqa: BLE001
        logger.warning("retrieval log write failed: %s", e)


def _hash_query(query: str) -> str:
    """SHA-256 truncated — for log correlation without leaking content."""
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


***REMOVED*** --- Pipeline entrypoint ----------------------------------------------------


async def retrieve_with_expansion(
    query: str,
    *,
    search_fn: Callable[..., List[Dict]],
    top_k: int = 12,
    enable_expansion: bool = True,
    enable_translation: bool = True,
    expansion_timeout: float = 5.0,
    translation_timeout: float = 5.0,
    llm_complete_json: Optional[Callable[..., Awaitable[dict]]] = None,
) -> Dict:
    """Run the full expansion + parallel search pipeline.

    Args:
      query: raw user query.
      search_fn: callable matching SearchService.search() signature —
        `search_fn(query: str, top_k: int) -> List[Dict]`. Injected for
        testability (tests pass a fake).
      top_k: final fused result count.
      enable_expansion: feature flag — disable to A/B against baseline.
      enable_translation: feature flag for EN→ZH path.
      expansion_timeout / translation_timeout: per-LLM-call budgets.
      llm_complete_json: dependency-injected LLM call. None = use prod
        services.llm_client.

    Returns:
      A dict with:
        results: List[Dict]   — fused top_k
        expansion_used: bool
        translation_used: bool
        lang_detected: str    — 'zh' | 'en' | 'mixed'
        candidate_queries: List[str] — queries actually issued
        total_recall: int     — raw count before top_k cut

    The function ALSO appends one row to web/backend/logs/retrieval.jsonl
    with hashed query (no raw text), top-5 KB ids, scores, and timing.
    Privacy: the raw query never leaves this function.
    """
    started = time.monotonic()
    lang = _detect_lang(query)

    ***REMOVED*** --- W3 translation -----------------------------------------------------
    zh_query: Optional[str] = None
    translation_used = False
    if enable_translation and lang == "en":
        zh_query = await qe.translate_en_to_zh(
            query,
            llm_complete_json=llm_complete_json,
            timeout=translation_timeout,
        )
        translation_used = bool(zh_query)

    ***REMOVED*** Build the seed query set we'll expand from. EN query stays in for
    ***REMOVED*** BM25 (KB descriptions occasionally contain English terms); translated
    ***REMOVED*** ZH is added as a parallel seed for embedding-side strength.
    seeds = [query]
    if zh_query and zh_query != query:
        seeds.append(zh_query)

    ***REMOVED*** --- W2 expansion -------------------------------------------------------
    candidate_queries: List[str] = list(seeds)
    expansion_used = False
    if enable_expansion:
        ***REMOVED*** We expand ONCE — off the primary query (ZH if translated, else
        ***REMOVED*** original). Expanding both seeds doubles LLM cost for marginal lift.
        primary_for_expansion = zh_query or query
        expansions = await qe.expand_query(
            primary_for_expansion,
            llm_complete_json=llm_complete_json,
            timeout=expansion_timeout,
        )
        ***REMOVED*** expand_query returns [primary, *rest]; we already have primary in
        ***REMOVED*** seeds (as either original or translated), so only append the rest.
        added = 0
        seen_lower = {s.lower() for s in candidate_queries}
        for e in expansions[1:]:
            if e.lower() in seen_lower:
                continue
            candidate_queries.append(e)
            seen_lower.add(e.lower())
            added += 1
        expansion_used = added > 0

    ***REMOVED*** --- Parallel search ---------------------------------------------------
    async def _run_one(q: str) -> List[Dict]:
        try:
            ***REMOVED*** search_fn is sync (SearchService.search). Run it in the
            ***REMOVED*** default thread pool so 4 queries truly run in parallel
            ***REMOVED*** rather than serialising the python work.
            return await asyncio.to_thread(search_fn, q, top_k)
        except Exception as e:  ***REMOVED*** noqa: BLE001
            logger.warning("retrieval search failed for one expansion: %s", e)
            return []

    per_query = await asyncio.gather(*[_run_one(q) for q in candidate_queries])
    total_recall = sum(len(r or []) for r in per_query)

    fused = qe.fuse_results(per_query, top_k=top_k)

    elapsed_ms = int((time.monotonic() - started) * 1000)

    ***REMOVED*** --- Structured log ----------------------------------------------------
    log_payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": "ask.retrieval",
        "query_hash": _hash_query(query),
        "query_len": len(query),
        "lang_detected": lang,
        "expansion_used": expansion_used,
        "translation_used": translation_used,
        "candidate_count": len(candidate_queries),
        "total_recall": total_recall,
        "fused_count": len(fused),
        "top_5_kb_ids": [r.get("id", "") for r in fused[:5]],
        "top_5_scores": [round(float(r.get("score") or 0.0), 4) for r in fused[:5]],
        "elapsed_ms": elapsed_ms,
    }
    _write_retrieval_log(log_payload)

    return {
        "results": fused,
        "expansion_used": expansion_used,
        "translation_used": translation_used,
        "lang_detected": lang,
        "candidate_queries": candidate_queries,
        "total_recall": total_recall,
        "elapsed_ms": elapsed_ms,
    }


***REMOVED*** --- Test helpers -----------------------------------------------------------


def _log_path_for_tests() -> Path:
    """Expose the log path so tests can read/clean it deterministically."""
    return _LOG_PATH
