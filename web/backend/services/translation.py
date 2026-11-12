"""Read-only, source-bound public KB translations. A miss returns original
text; neither a key nor a language request can start paid translation. The old
batch sender is explicitly denied for direct consumers as well.
"""
from __future__ import annotations

if __package__ == "web.backend.services":
    from ..errors import deny_legacy_paid
else:
    from errors import deny_legacy_paid


import asyncio
import json
import os
from typing import Dict, Iterable, List, Optional

if __package__ == "web.backend.services":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

if __package__ == "web.backend.services":
    from .llm_service import OPENROUTER_URL, _get_http_client
else:
    from services.llm_service import OPENROUTER_URL, _get_http_client

logger = get_logger("structural.translation")

# Process-local cache: id -> translated dict (at minimum name/domain/description)
_TRANSLATE_CACHE: Dict[str, dict] = {}
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
    deny_legacy_paid()
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
    except Exception as exc:
        logger.warning(
            "llm.translation_batch_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return []


def _public_cached_translation(item):
    import hashlib
    key = item.get("id")
    cached = _TRANSLATE_CACHE.get(key) if isinstance(key, str) and key and not key.startswith("__") else None
    payload = {k: item.get(k) for k in ("id", "name", "domain", "description", "type_id")}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if (isinstance(cached, dict) and cached.get("schema_version") == "legacy-public-translation-v1"
            and cached.get("source_digest") == digest and isinstance(cached.get("translation"), dict)
            and set(cached["translation"]) <= {"name", "domain", "description"}
            and all(isinstance(v, str) and len(v) <= 8000 for v in cached["translation"].values())):
        return _merge_translation(item, cached["translation"])
    return item  # Original language, never fabricated translated text.


async def translate_kb_item(item: Optional[Dict], lang: str) -> Optional[Dict]:
    """Read a source-bound public translation or unchanged original; no model."""
    if not item or (lang or "zh").lower() != "en":
        return item
    return _public_cached_translation(item)


async def translate_kb_items(items: Iterable[Dict], lang: str) -> List[Dict]:
    """Read-only bulk translation cache; a miss never dispatches generation."""
    return [await translate_kb_item(item, lang) for item in items or []]


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
