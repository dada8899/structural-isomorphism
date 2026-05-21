"""A1 method-search service — Session ***REMOVED***18.

Reverse direction of the engine: the user gives a *method* (an algorithm /
model / technique) and we find KB phenomena whose underlying *structure*
matches what the method exploits.

Pipeline:
  1. extract_signature()  — LLM extracts a structural signature of the
     method: which underlying structure it leverages. Degrades to a
     trivial signature (the raw method text) when the LLM is unavailable.
  2. SearchService.search() — use the signature text as the query to find
     structurally similar phenomena in the KB.
  3. annotate_matches()   — for the top matches, LLM writes one sentence on
     *why* the method transfers / *how* to apply it. Degrades to no note.

All LLM output is schema-validated here (never trusted): types coerced,
strings length-capped, lists trimmed. Any LLM failure → graceful degrade,
never an exception.
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("structural.method_search")

***REMOVED*** --- input / output bounds (guardrails) --------------------------------------
MAX_METHOD_LEN = 1000
MIN_METHOD_LEN = 4
MAX_SIGNATURE_LEN = 600
MAX_QUERY_LEN = 400          ***REMOVED*** SearchService query is capped at 500
MAX_NOTE_LEN = 240
DEFAULT_TOP_N = 8
MAX_TOP_N = 20
MAX_KEYWORDS = 6
MAX_KEYWORD_LEN = 30


***REMOVED*** --- structural signature -----------------------------------------------------

_SIGNATURE_SYSTEM = (
    "你是一个跨学科结构分析专家。用户会给你一个方法/算法/模型。"
    "你的任务：剥离它的领域外衣，提炼出它在结构层面利用的底层机制——"
    "它假设了什么样的结构、靠什么动力学起作用。"
    '严格只输出 JSON，形如 {"signature": "...", "keywords": ["...", "..."]}。'
    "signature 是一句话的结构描述（不超过 80 字，不要提原方法的名字），"
    "keywords 是 3-6 个描述这个结构的关键词（中文，每个不超过 12 字）。"
    "示例：梯度下降 → signature: 在带噪声的局部反馈下沿可微地形迭代逼近极值；"
    'keywords: ["迭代逼近", "局部信息", "噪声反馈", "极值搜索"]。'
)


def _coerce_signature(raw: Optional[dict], method_text: str) -> dict:
    """Validate / coerce the LLM signature payload into a safe shape.

    Always returns {"signature": str, "keywords": list[str], "llm": bool}.
    A None or malformed payload falls back to the raw method text.
    """
    fallback = {
        "signature": method_text[:MAX_SIGNATURE_LEN],
        "keywords": [],
        "llm": False,
    }
    if not isinstance(raw, dict):
        return fallback

    sig = raw.get("signature")
    if not isinstance(sig, str) or not sig.strip():
        return fallback
    sig = sig.strip()[:MAX_SIGNATURE_LEN]

    kws_raw = raw.get("keywords")
    keywords: list[str] = []
    if isinstance(kws_raw, list):
        for k in kws_raw:
            if not isinstance(k, str):
                continue
            k = k.strip()[:MAX_KEYWORD_LEN]
            if k and k not in keywords:
                keywords.append(k)
            if len(keywords) >= MAX_KEYWORDS:
                break

    return {"signature": sig, "keywords": keywords, "llm": True}


async def extract_signature(method_text: str) -> dict:
    """Extract the structural signature of a method via the LLM.

    Returns the coerced shape from `_coerce_signature`. Never raises.
    """
    from services import llm_client

    method_text = (method_text or "").strip()
    if not llm_client.llm_available():
        logger.info("extract_signature: no LLM, degrading to raw text")
        return _coerce_signature(None, method_text)
    try:
        raw = await llm_client.complete_json(
            system=_SIGNATURE_SYSTEM,
            user=f"方法描述：\n{method_text}",
            temperature=0.3,
            max_tokens=600,
        )
    except Exception as e:  ***REMOVED*** noqa: BLE001 — defensive; client already guards
        logger.error("extract_signature LLM call failed: %s", e)
        raw = None
    return _coerce_signature(raw, method_text)


def build_query(signature: dict) -> str:
    """Build the SearchService query text from a signature payload.

    Combine the signature sentence with its keywords so BM25 has lexical
    anchors and the embedding has the full structural sentence.
    """
    parts = [signature.get("signature", "")]
    kws = signature.get("keywords") or []
    if kws:
        parts.append(" ".join(kws))
    query = " ".join(p for p in parts if p).strip()
    return query[:MAX_QUERY_LEN]


***REMOVED*** --- applicability notes ------------------------------------------------------

_NOTE_SYSTEM = (
    "你是一个跨学科迁移顾问。用户给你一个方法的结构签名，以及若干个来自"
    "不同领域的现象。对每个现象，写一句话说明：这个方法为什么能套用在这个"
    "现象上、具体怎么套（不超过 60 字，要具体、不空泛）。"
    '严格只输出 JSON，形如 {"notes": {"现象id": "套用说明", ...}}。'
    "只为给定的现象 id 写说明，不要编造 id。"
)


def _coerce_notes(raw: Optional[dict], valid_ids: set[str]) -> dict[str, str]:
    """Validate the LLM notes payload — drop unknown ids, cap lengths."""
    if not isinstance(raw, dict):
        return {}
    notes_obj = raw.get("notes")
    if not isinstance(notes_obj, dict):
        return {}
    out: dict[str, str] = {}
    for pid, note in notes_obj.items():
        if pid not in valid_ids:
            continue  ***REMOVED*** never trust an LLM-invented id
        if not isinstance(note, str):
            continue
        note = note.strip()[:MAX_NOTE_LEN]
        if note:
            out[pid] = note
    return out


async def annotate_matches(signature: dict, matches: list[dict]) -> dict[str, str]:
    """Ask the LLM for a one-line applicability note per match.

    Returns {phenomenon_id: note}. Empty dict when the LLM is unavailable
    or returns nothing usable — callers must treat notes as optional.
    """
    from services import llm_client

    if not matches or not llm_client.llm_available():
        return {}

    valid_ids = {m["id"] for m in matches if m.get("id")}
    if not valid_ids:
        return {}

    lines = [f"结构签名：{signature.get('signature', '')}", "", "现象列表："]
    for m in matches:
        lines.append(
            f"- id={m.get('id')} | 领域={m.get('domain')} | "
            f"{m.get('name')}：{(m.get('description') or '')[:160]}"
        )
    try:
        raw = await llm_client.complete_json(
            system=_NOTE_SYSTEM,
            user="\n".join(lines),
            temperature=0.4,
            max_tokens=1400,
        )
    except Exception as e:  ***REMOVED*** noqa: BLE001
        logger.error("annotate_matches LLM call failed: %s", e)
        raw = None
    return _coerce_notes(raw, valid_ids)


***REMOVED*** --- ranking ------------------------------------------------------------------

def rank_matches(results: list[dict], notes: dict[str, str], top_n: int) -> list[dict]:
    """Shape + rank the final match list.

    SearchService already returns results ranked by fused score; we keep
    that order, attach the applicability note, and trim to top_n. Each
    output item is a small, frontend-ready dict.
    """
    out: list[dict] = []
    for r in results:
        rid = r.get("id")
        if not rid:
            continue
        out.append({
            "id": rid,
            "name": r.get("name", ""),
            "domain": r.get("domain", ""),
            "type_id": r.get("type_id", ""),
            "description": r.get("description", ""),
            "relevance": float(r.get("relevance", 0.0) or 0.0),
            "score": float(r.get("score", 0.0) or 0.0),
            "apply_note": notes.get(rid, ""),
        })
        if len(out) >= top_n:
            break
    return out


***REMOVED*** --- orchestration ------------------------------------------------------------

def normalize_top_n(value: Optional[int]) -> int:
    """Clamp a requested top_n into [1, MAX_TOP_N]."""
    if not isinstance(value, int):
        return DEFAULT_TOP_N
    return max(1, min(value, MAX_TOP_N))


async def run_method_search(method_text: str, search_svc, top_n: int) -> dict:
    """Full A1 pipeline. `search_svc` is the live SearchService instance.

    Returns a dict ready to serialise:
      {method, signature, keywords, llm_used, count, matches: [...]}
    Never raises for LLM reasons — degrades gracefully.
    """
    method_text = (method_text or "").strip()
    top_n = normalize_top_n(top_n)

    sig = await extract_signature(method_text)
    query = build_query(sig)

    ***REMOVED*** Search a slightly larger pool than top_n so ranking has headroom.
    results = search_svc.search(query, top_k=min(top_n * 2, 30)) if query else []

    ***REMOVED*** Annotate only the slice we will actually return.
    head = rank_matches(results, {}, top_n)
    notes = await annotate_matches(sig, head)
    matches = rank_matches(results, notes, top_n)

    return {
        "method": method_text,
        "signature": sig["signature"],
        "keywords": sig["keywords"],
        "llm_used": sig["llm"],
        "count": len(matches),
        "matches": matches,
    }
