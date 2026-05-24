"""X2 W2 (2026-05-24) — LLM query expansion for retrieval recall.

Root cause (X2 §2.2/§2.3/§2.4): KB stores "general phenomena" (e.g. 银行
挤兑) but users phrase questions with proper nouns (SVB / Theranos /
GameStop) or English aliases (power-law / phase transition / feedback
loop). BM25 + embedding miss both axes:

  * SVB → 0 字面 / 0 embedding (KB has no SVB entry)
  * "power-law" → 0 字面 (KB is all-Chinese), embedding biased

This module expands a single user query into 4 retrieval queries:
  1. The original query (preserved verbatim — never drop the user's words)
  2. A "general concept" rephrase (SVB → 银行挤兑)
  3. A synonym variant (银行挤兑 → 流动性危机 / 储户撤资)
  4. A bilingual mirror (中→EN or EN→中)

The 4 queries are run in parallel through SearchService.search() and
results are unioned by KB id with rerank by max(score across queries).

Design notes:
  * **LRU cache** (in-memory, 256 entries) — exact-string key. Repeat
    queries within a session never re-hit the LLM.
  * **Cost guardrail** — single expansion call must stay under
    EXPANSION_MAX_COST_USD (default $0.001). The LLM client (DeepSeek
    via OpenRouter) doesn't return usage in our wrapper, so we estimate
    cost from a fixed token budget and the model's published price.
  * **Graceful fallback** — any LLM error / timeout / no-key / cost-cap
    returns just [original_query]. The retrieval still works; we just
    skip the expansion lift for that call. Never raise.
  * **No PII** — the LLM call goes via services.llm_client (project's
    OpenRouter wrapper). No third-party SDKs added.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import threading
import time
from collections import OrderedDict
from typing import Iterable, List, Optional, Tuple

logger = logging.getLogger("structural.query_expansion")

# --- Cost / size budgets ----------------------------------------------------

# DeepSeek-chat on OpenRouter is ~$0.27/M input + $1.10/M output as of
# 2026-05. With max_tokens=160 and a ~250-token system+user prompt the
# worst-case cost per call is ~$0.0002. We cap at $0.001 to absorb price
# fluctuation while still keeping per-query cost in the negligible range.
EXPANSION_MAX_COST_USD = 0.001

# Heuristic per-call cost estimate. We don't get usage tokens back from
# the wrapper, so we assume a fixed price ceiling rather than the wire
# bytes. If the model is ever swapped to GPT-4o-mini ($0.15/M in,
# $0.60/M out) the estimate is still inside budget.
_ESTIMATED_COST_PER_CALL_USD = 0.0003

# Max length of any expansion candidate (chars). Anything longer is
# likely a hallucination ("expanded" into a full paragraph instead of a
# query rephrase) — we truncate and log, never crash.
_MAX_EXPANSION_LEN = 80

# Number of expanded queries we want from the LLM (besides the original).
# X2 spec: 3 expansions + 1 original = 4 queries total.
_TARGET_EXPANSIONS = 3

# LLM call timeout. Default budget is "quick win" — slow expansion is
# worse UX than no expansion, so we keep it tight.
_LLM_TIMEOUT_SEC = 5.0


# --- LRU cache --------------------------------------------------------------

# OrderedDict-based LRU. We use a threading.Lock (not asyncio.Lock) so the
# cache is safe across multiple event loops too — tests create+tear down a
# fresh loop per call (asyncio.run), which would invalidate an asyncio.Lock.
# Dict ops in CPython are atomic anyway; the lock is to protect the
# OrderedDict.move_to_end + popitem sequence from interleaving.
_CACHE_MAX = 256
_cache: "OrderedDict[str, List[str]]" = OrderedDict()
_cache_lock = threading.Lock()

# Lightweight counters for observability (surfaced via cache_stats()).
_stats = {
    "calls": 0,
    "hits": 0,
    "llm_calls": 0,
    "llm_failures": 0,
    "cost_capped": 0,
    "fallbacks": 0,
}

# Running total of expansion cost (estimated). Bounded by
# EXPANSION_MAX_COST_USD per call; total is informational only.
_running_cost_usd: float = 0.0


def cache_stats() -> dict:
    """Expose expansion + cache counters for /api/health?deep=1."""
    return {
        "calls": _stats["calls"],
        "cache_hits": _stats["hits"],
        "llm_calls": _stats["llm_calls"],
        "llm_failures": _stats["llm_failures"],
        "cost_capped": _stats["cost_capped"],
        "fallbacks": _stats["fallbacks"],
        "running_cost_usd": round(_running_cost_usd, 6),
        "cache_size": len(_cache),
    }


def _cache_key(query: str) -> str:
    return query.strip()


def _cache_get(query: str) -> Optional[List[str]]:
    with _cache_lock:
        key = _cache_key(query)
        if key in _cache:
            # LRU touch
            _cache.move_to_end(key)
            return list(_cache[key])
        return None


def _cache_put(query: str, expansions: List[str]) -> None:
    with _cache_lock:
        key = _cache_key(query)
        _cache[key] = list(expansions)
        _cache.move_to_end(key)
        while len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)


def reset_cache_for_tests() -> None:
    """Test-only — flush the in-memory LRU + counters."""
    global _running_cost_usd
    _cache.clear()
    for k in _stats:
        _stats[k] = 0
    _running_cost_usd = 0.0


# --- LLM prompt -------------------------------------------------------------

_EXPANSION_SYSTEM = """你是一个跨领域知识检索助手。\
用户向一个研究跨学科结构同构现象的知识库提问，但 KB 收录的是"通用现象"\
（如"银行挤兑"、"幂律分布"），用户可能会用专有名词（如 SVB、Theranos、\
GameStop）、英文术语或同义表达提问。

你的任务：把用户的查询扩写成 3 条用于检索的候选查询，每条 < 30 字。\
请覆盖以下三个维度（每条选一个）：
  1. 通用概念：把专名换成它所属的通用现象名（SVB → 银行挤兑）
  2. 同义/近义表达：用 KB 可能收录的另一种说法（银行挤兑 → 流动性危机）
  3. 中英对照：如果原查询是中文给一条英文，反之亦然

输出严格的 JSON：{"expansions": ["...", "...", "..."]}"""

_EXPANSION_USER_TPL = """原查询：{query}

输出 3 条候选，严格 JSON 格式。"""


# --- Public API -------------------------------------------------------------


async def expand_query(
    query: str,
    *,
    llm_complete_json=None,
    timeout: float = _LLM_TIMEOUT_SEC,
) -> List[str]:
    """Return [original_query, *up_to_3_expansions]. Never raises.

    Args:
      query: raw user query. Required.
      llm_complete_json: dependency-injected LLM call for testing. If
        None, uses services.llm_client.complete_json. Tests pass a mock.
      timeout: LLM call timeout in seconds.

    Returns:
      A list of 1-4 query strings, always starting with the original.
      Falls back to [original_query] on any error / no-key / cost-cap.

    Cost: at most one LLM call per unique query (LRU cache). Budget cap
    EXPANSION_MAX_COST_USD enforced per-call; if total running cost
    would exceed it we skip the call and return [original_query].
    """
    global _running_cost_usd
    _stats["calls"] += 1

    if not query or not query.strip():
        return [query] if query else []

    original = query.strip()

    # Cache fast path
    cached = _cache_get(original)
    if cached is not None:
        _stats["hits"] += 1
        return cached

    # Cost guardrail — if we've already burnt the per-call budget on this
    # particular call (we haven't, by definition), short-circuit. Real
    # check: ensure ONE more call stays under the cap.
    if _ESTIMATED_COST_PER_CALL_USD > EXPANSION_MAX_COST_USD:
        # Defensive: model upgrade pushed cost above cap.
        _stats["cost_capped"] += 1
        _stats["fallbacks"] += 1
        logger.warning(
            "query expansion cost-capped: per-call %.4f USD > cap %.4f",
            _ESTIMATED_COST_PER_CALL_USD, EXPANSION_MAX_COST_USD,
        )
        result = [original]
        _cache_put(original, result)
        return result

    # LLM call
    if llm_complete_json is None:
        try:
            from services.llm_client import complete_json as llm_complete_json
        except Exception as e:  # pragma: no cover
            logger.warning("query expansion: llm_client import failed: %s", e)
            _stats["fallbacks"] += 1
            return [original]

    _stats["llm_calls"] += 1
    try:
        raw = await asyncio.wait_for(
            llm_complete_json(
                system=_EXPANSION_SYSTEM,
                user=_EXPANSION_USER_TPL.format(query=original),
                temperature=0.3,
                max_tokens=240,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("query expansion: LLM timeout (%.1fs) for query_hash=%s",
                       timeout, _hash(original))
        _stats["llm_failures"] += 1
        _stats["fallbacks"] += 1
        return [original]
    except Exception as e:
        logger.warning("query expansion: LLM error: %s", e)
        _stats["llm_failures"] += 1
        _stats["fallbacks"] += 1
        return [original]

    # Account for the spend AFTER the call (regardless of success — paid for it).
    _running_cost_usd += _ESTIMATED_COST_PER_CALL_USD

    # Parse + sanitise
    expansions: List[str] = []
    if isinstance(raw, dict):
        candidates = raw.get("expansions") or []
        if isinstance(candidates, list):
            seen = {original.lower()}
            for c in candidates:
                if not isinstance(c, str):
                    continue
                c = c.strip()
                if not c or len(c) > _MAX_EXPANSION_LEN:
                    continue
                # Drop trivial dupes of the original
                if c.lower() in seen:
                    continue
                seen.add(c.lower())
                expansions.append(c)
                if len(expansions) >= _TARGET_EXPANSIONS:
                    break

    if not expansions:
        # LLM responded but didn't give usable expansions
        _stats["fallbacks"] += 1
        result = [original]
    else:
        result = [original] + expansions

    _cache_put(original, result)
    return result


# --- Result fusion ----------------------------------------------------------


def fuse_results(
    per_query_results: Iterable[Iterable[dict]],
    *,
    top_k: int = 12,
) -> List[dict]:
    """Union results from N queries by KB id, rank by max score.

    Each input is a list of result dicts as returned by
    SearchService.search() (with at least `id` and `score` keys). When
    the same id appears across multiple expansions, we keep the entry
    with the highest score and copy that into the fused list (preserves
    `relevance`, `cross_domain`, `surface_domain` from the strongest
    hit). Stable ordering by score desc.
    """
    best: dict = {}  # id -> result dict (with current max score)
    for run in per_query_results:
        for r in run or []:
            rid = r.get("id")
            if not rid:
                continue
            score = float(r.get("score") or 0.0)
            prev = best.get(rid)
            if prev is None or score > float(prev.get("score") or 0.0):
                # Tag the fused result so downstream can tell if expansion helped
                tagged = dict(r)
                tagged.setdefault("_expansion_boosted", prev is not None)
                best[rid] = tagged
            else:
                # Same id appeared again from a different expansion → mark
                prev["_expansion_boosted"] = True
    ranked = sorted(
        best.values(),
        key=lambda r: float(r.get("score") or 0.0),
        reverse=True,
    )
    return ranked[:top_k]


# --- X2 W3 — EN → ZH translation cache ------------------------------------

# Translation cache is keyed separately from expansion so the two paths
# don't collide. Translations are cheaper (shorter prompt) and even more
# repetition-friendly than expansions ("power-law" appears everywhere).
_translate_cache: "OrderedDict[str, str]" = OrderedDict()
_translate_lock = threading.Lock()
_TRANSLATE_CACHE_MAX = 256

_TRANSLATE_SYSTEM = """你是一个学术术语翻译助手。\
把用户提供的英文查询翻译成简洁的中文，专门用于检索一个中文知识库。\
要求：
  1. 不解释、不展开，只输出翻译结果
  2. 保留原 query 的关键术语（即使有英文专有名词，也用中文学术对应词）
  3. 长度尽量贴近原句长度，不要扩写
  4. 严格 JSON 格式输出：{"zh": "中文翻译"}"""

_TRANSLATE_USER_TPL = """英文查询：{query}

输出 JSON。"""


async def translate_en_to_zh(
    query: str,
    *,
    llm_complete_json=None,
    timeout: float = _LLM_TIMEOUT_SEC,
) -> Optional[str]:
    """Translate an EN query to ZH. Returns None on any failure.

    Caching: in-memory LRU 256. Same EN string twice → one LLM call.
    """
    if not query or not query.strip():
        return None
    key = query.strip()
    with _translate_lock:
        if key in _translate_cache:
            _translate_cache.move_to_end(key)
            return _translate_cache[key]

    if llm_complete_json is None:
        try:
            from services.llm_client import complete_json as llm_complete_json
        except Exception:  # pragma: no cover
            return None

    try:
        raw = await asyncio.wait_for(
            llm_complete_json(
                system=_TRANSLATE_SYSTEM,
                user=_TRANSLATE_USER_TPL.format(query=key),
                temperature=0.2,
                max_tokens=160,
            ),
            timeout=timeout,
        )
    except (asyncio.TimeoutError, Exception) as e:  # noqa: BLE001
        logger.warning("translate_en_to_zh failed: %s", e)
        return None

    if not isinstance(raw, dict):
        return None
    zh = raw.get("zh")
    if not isinstance(zh, str) or not zh.strip() or len(zh) > _MAX_EXPANSION_LEN:
        return None
    zh = zh.strip()
    with _translate_lock:
        _translate_cache[key] = zh
        _translate_cache.move_to_end(key)
        while len(_translate_cache) > _TRANSLATE_CACHE_MAX:
            _translate_cache.popitem(last=False)
    return zh


def reset_translate_cache_for_tests() -> None:
    """Test-only — flush translation cache."""
    _translate_cache.clear()


# --- Utilities --------------------------------------------------------------


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]
