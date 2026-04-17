"""
Lightweight KB translation helper (Chinese -> English).

Used by the web endpoints when the caller passes `lang=en`. The KB itself
is stored only in Chinese; we translate `name`, `domain`, `description`
on-the-fly via the existing LLM provider and cache the result in memory,
keyed by the phenomenon `id` so a single translation is reused across
requests.

Design notes:
- Only activates when `lang == "en"`. The zh path MUST remain unchanged.
- Cache is process-local (dict). No TTL — translations are deterministic
  enough and the process restarts frequently enough that adding disk
  persistence isn't worth the complexity right now.
- On any LLM failure we fall back to returning the original Chinese item,
  so the user is never blocked — they'll just see zh text, which is
  strictly better than a 500.
- Cache key is the phenomenon id. Items without an id (e.g. the synthetic
  `__query__` used in analyze.py query-mode) get translated per call
  without caching.

Keep this file small and dependency-light: it reuses `LLMService`'s HTTP
client indirectly so we don't open new sockets.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Dict, Iterable, List, Optional

import httpx

from services.llm_service import OPENROUTER_URL, _get_http_client

logger = logging.getLogger("structural.translation")

# Process-local cache: id -> translated dict (at minimum name/domain/description)
_TRANSLATE_CACHE: Dict[str, Dict[str, str]] = {}
# Locks to avoid duplicate concurrent translations of the same id.
_TRANSLATE_LOCKS: Dict[str, asyncio.Lock] = {}
_GLOBAL_LOCK = asyncio.Lock()

# Category enum mapping (Chinese -> English). These come from
# `assess_and_rewrite` in llm_service.py.
CATEGORY_EN = {
    "现象描述": "phenomenon description",
    "学术方向": "academic direction",
    "元问题": "meta question",
    "命令式": "command-style prompt",
    "闲聊": "small talk",
    "太抽象": "too abstract",
    "个人事务": "personal matter",
    "纯事实": "factual lookup",
}


def translate_category(zh_category: Optional[str]) -> str:
    """Return the EN label for a hard-coded ZH category enum, with passthrough."""
    if not zh_category:
        return ""
    return CATEGORY_EN.get(zh_category, zh_category)


def _get_lock(cache_key: str) -> asyncio.Lock:
    # Single-thread asyncio, so we can create locks lazily. No race here
    # because we're inside the event loop.
    lock = _TRANSLATE_LOCKS.get(cache_key)
    if lock is None:
        lock = asyncio.Lock()
        _TRANSLATE_LOCKS[cache_key] = lock
    return lock


async def _llm_translate_batch(items: List[Dict]) -> List[Dict[str, str]]:
    """Call the LLM once with a batch of items; return parallel list of
    {name, domain, description} dicts in English. On failure returns [] so
    the caller falls back to passthrough.

    Each input item must have at minimum name/domain/description (missing
    values default to empty string).
    """
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key or not items:
        return []

    # Build a compact JSON payload the model translates in-place.
    payload_in = [
        {
            "i": i,
            "name": it.get("name", "") or "",
            "domain": it.get("domain", "") or "",
            "description": it.get("description", "") or "",
        }
        for i, it in enumerate(items)
    ]

    prompt = (
        "Translate the Chinese phenomenon fields below to concise, academic "
        "English. Keep proper nouns. Preserve technical accuracy. Return "
        "ONLY a JSON object of the form {\"items\": [{\"i\": <int>, "
        "\"name\": <en>, \"domain\": <en>, \"description\": <en>}, ...]} "
        "with the same `i` indices as input. No markdown, no commentary.\n\n"
        "INPUT:\n" + json.dumps({"items": payload_in}, ensure_ascii=False)
    )

    try:
        client = _get_http_client()
        resp = await client.post(
            OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                # Use a fast + cheap model; translation doesn't need reasoning.
                "model": os.getenv("LLM_TRANSLATE_MODEL", "anthropic/claude-haiku-4.5"),
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 1500,
                "response_format": {"type": "json_object"},
            },
            timeout=20.0,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.strip("`").lstrip("json").strip()
        parsed = json.loads(content)
        out_items = parsed.get("items") or []
        # Index by i
        by_i: Dict[int, Dict[str, str]] = {}
        for rec in out_items:
            try:
                i = int(rec.get("i"))
            except (TypeError, ValueError):
                continue
            by_i[i] = {
                "name": (rec.get("name") or "").strip(),
                "domain": (rec.get("domain") or "").strip(),
                "description": (rec.get("description") or "").strip(),
            }
        result: List[Dict[str, str]] = []
        for i in range(len(items)):
            result.append(by_i.get(i, {}))
        return result
    except Exception as e:
        logger.warning(f"KB translate batch failed ({len(items)} items): {e}")
        return []


async def translate_kb_item(item: Optional[Dict], lang: str) -> Optional[Dict]:
    """Return `item` with name/domain/description translated to EN when
    `lang == 'en'`. Otherwise return `item` unchanged (the zh path).

    Uses the process-local cache keyed by item['id']. On LLM failure,
    returns the original item (passthrough).
    """
    if not item or (lang or "zh").lower() != "en":
        return item

    cache_key = item.get("id") or ""
    if cache_key and cache_key in _TRANSLATE_CACHE:
        return _merge_translation(item, _TRANSLATE_CACHE[cache_key])

    # Guard concurrent translations of the same id.
    if cache_key:
        lock = _get_lock(cache_key)
        async with lock:
            if cache_key in _TRANSLATE_CACHE:
                return _merge_translation(item, _TRANSLATE_CACHE[cache_key])
            batch = await _llm_translate_batch([item])
            if batch and batch[0]:
                _TRANSLATE_CACHE[cache_key] = batch[0]
                return _merge_translation(item, batch[0])
            # Failure: passthrough
            return item

    # No id — translate inline without caching.
    batch = await _llm_translate_batch([item])
    if batch and batch[0]:
        return _merge_translation(item, batch[0])
    return item


async def translate_kb_items(items: Iterable[Dict], lang: str) -> List[Dict]:
    """Translate a list of KB items. Batches cache-misses into one LLM call.

    Items with no `id` are translated inline (one per call) to keep the batch
    path simple; this is rare (only query-mode synthetic items).
    """
    items_list = list(items or [])
    if (lang or "zh").lower() != "en" or not items_list:
        return items_list

    # Figure out which items need translation
    to_fetch: List[Dict] = []
    to_fetch_positions: List[int] = []
    out: List[Optional[Dict]] = [None] * len(items_list)
    for i, it in enumerate(items_list):
        if not it:
            out[i] = it
            continue
        cache_key = it.get("id") or ""
        if cache_key and cache_key in _TRANSLATE_CACHE:
            out[i] = _merge_translation(it, _TRANSLATE_CACHE[cache_key])
        else:
            to_fetch.append(it)
            to_fetch_positions.append(i)

    if to_fetch:
        batch = await _llm_translate_batch(to_fetch)
        for pos_in_batch, (orig_pos, orig_item) in enumerate(
            zip(to_fetch_positions, to_fetch)
        ):
            tr = batch[pos_in_batch] if pos_in_batch < len(batch) else None
            if tr:
                cache_key = orig_item.get("id") or ""
                if cache_key:
                    _TRANSLATE_CACHE[cache_key] = tr
                out[orig_pos] = _merge_translation(orig_item, tr)
            else:
                # Fallback: passthrough Chinese
                out[orig_pos] = orig_item

    return [x for x in out]  # mypy: all populated


def _merge_translation(original: Dict, tr: Dict[str, str]) -> Dict:
    """Return a shallow copy of `original` with translated fields overlaid.

    Only overrides name/domain/description; other fields (id, type_id,
    score, etc.) pass through untouched so downstream consumers that rely
    on them keep working.
    """
    if not tr:
        return original
    merged = dict(original)
    for key in ("name", "domain", "description"):
        new_val = tr.get(key)
        if new_val:
            merged[key] = new_val
    return merged
