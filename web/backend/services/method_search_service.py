"""A1 method-search service — Session #18.

Reverse direction of the engine: the user gives a *method* (an algorithm /
model / technique) and we find KB phenomena whose underlying *structure*
matches what the method exploits.

Pipeline:
  1. extract_signature()  — LLM extracts a structural signature of the
     method: which underlying structure it leverages. Degrades to a
     trivial signature (the raw method text) when the LLM is unavailable.
  2. SearchService.search() — use the signature text as the query to find
     structurally similar phenomena in the KB.
  3. annotate_matches()   — for the top matches, LLM writes one candidate
     comparison note and a falsifiable boundary. Degrades to no note.

All LLM output is schema-validated here (never trusted): types coerced,
strings length-capped, lists trimmed. Any LLM failure → graceful degrade,
never an exception.
"""
from __future__ import annotations

import asyncio
import math
import time
from typing import Any, Optional

if __package__ == "web.backend.services":
    from . import llm_client
    from .candidate_origin import normalize_candidate_identifier
    from .input_limits import normalize_research_text
    from .search_synthesis import validate_candidate_public_texts
    from .secondary_tool_contracts import kb_candidate_evidence
    from ..logging_config import get_logger, new_incident_id
else:
    from services import llm_client
    from services.candidate_origin import normalize_candidate_identifier
    from services.input_limits import normalize_research_text
    from services.search_synthesis import validate_candidate_public_texts
    from services.secondary_tool_contracts import kb_candidate_evidence
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.method_search")

# --- input / output bounds (guardrails) --------------------------------------
MAX_METHOD_LEN = 1000
MIN_METHOD_LEN = 4
MAX_SIGNATURE_LEN = 600
MAX_QUERY_LEN = 400          # SearchService query is capped at 500
MAX_NOTE_LEN = 240
DEFAULT_TOP_N = 8
MAX_TOP_N = 20
MAX_KEYWORDS = 6
MAX_KEYWORD_LEN = 30
METHOD_SEARCH_TOTAL_BUDGET_SECONDS = 7.5
SIGNATURE_TIMEOUT_SECONDS = 3.0
ANNOTATION_TIMEOUT_SECONDS = 2.0


# --- structural signature -----------------------------------------------------

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


def _validate_signature_strict(raw: Any, method_text: str) -> dict:
    """Validate the complete signature payload or use an explicit fallback."""
    fallback = _coerce_signature(None, method_text)
    if not isinstance(raw, dict) or set(raw) != {"signature", "keywords"}:
        return fallback
    if not isinstance(raw.get("keywords"), list):
        return fallback
    try:
        signature = normalize_research_text(
            raw.get("signature"),
            max_chars=MAX_SIGNATURE_LEN,
            allow_layout=False,
            field_name="signature",
        )
        keywords = [
            normalize_research_text(
                item,
                max_chars=MAX_KEYWORD_LEN,
                allow_layout=False,
                field_name="keyword",
            )
            for item in raw["keywords"]
        ]
        if not 1 <= len(keywords) <= MAX_KEYWORDS or len(keywords) != len(set(keywords)):
            return fallback
        validate_candidate_public_texts([signature])
    except (TypeError, ValueError):
        return fallback
    return {"signature": signature, "keywords": keywords, "llm": True}


async def extract_signature(
    method_text: str,
    *,
    timeout_seconds: float = SIGNATURE_TIMEOUT_SECONDS,
) -> dict:
    """Extract the structural signature of a method via the LLM.

    Returns the coerced shape from `_coerce_signature`. Never raises.
    """
    method_text = (method_text or "").strip()
    if not llm_client.llm_available():
        logger.info("retrieval.method_signature_llm_unavailable")
        return _coerce_signature(None, method_text)
    try:
        raw = await llm_client.complete_json(
            system=_SIGNATURE_SYSTEM,
            user=f"方法描述：\n{method_text}",
            temperature=0.3,
            max_tokens=600,
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001 — defensive; client already guards
        logger.error(
            "retrieval.method_signature_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raw = None
    return _validate_signature_strict(raw, method_text)


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


# --- applicability notes ------------------------------------------------------

_NOTE_SYSTEM = (
    "你是一个跨学科候选筛查员。用户给你一个方法的结构签名，以及若干条内部"
    "知识库检索记录。对每条记录写一句话：为什么值得进一步测试，以及哪个条件"
    "不满足时应当放弃迁移。检索命中不证明方法适用。"
    '严格只输出 JSON，形如 {"notes": {"现象id": "待验证说明", ...}}。'
    "只为给定的现象 id 写说明，不要编造 id。"
    "不得写成功概率、置信度、已经同构、确认适用或可以直接套用。"
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
            continue  # never trust an LLM-invented id
        if not isinstance(note, str):
            continue
        note = note.strip()[:MAX_NOTE_LEN]
        if note:
            out[pid] = note
    return out


def _validate_notes_strict(raw: Any, valid_ids: set[str]) -> dict[str, str]:
    """Accept a complete, source-bound note map or reject it as a unit."""
    if not isinstance(raw, dict) or set(raw) != {"notes"}:
        return {}
    notes = raw.get("notes")
    if not isinstance(notes, dict) or not set(notes).issubset(valid_ids):
        return {}
    out: dict[str, str] = {}
    try:
        for pid, note in notes.items():
            clean = normalize_research_text(
                note,
                max_chars=MAX_NOTE_LEN,
                allow_layout=False,
                field_name="candidate_note",
            )
            out[pid] = clean
        validate_candidate_public_texts(out.values())
    except (TypeError, ValueError):
        return {}
    return out


async def annotate_matches(
    signature: dict,
    matches: list[dict],
    *,
    timeout_seconds: float = ANNOTATION_TIMEOUT_SECONDS,
) -> dict[str, str]:
    """Ask the LLM for one candidate-comparison note per match.

    Returns {phenomenon_id: note}. Empty dict when the LLM is unavailable
    or returns nothing usable — callers must treat notes as optional.
    """
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
            timeout=timeout_seconds,
        )
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "retrieval.method_annotation_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raw = None
    return _validate_notes_strict(raw, valid_ids)


# --- ranking ------------------------------------------------------------------

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


def rank_candidates(
    results: Any, notes: dict[str, str], top_n: int
) -> list[dict[str, Any]]:
    """Shape retrieval rows without publishing score-as-probability fields."""
    if not isinstance(results, list):
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in results:
        if not isinstance(row, dict):
            continue
        rid = normalize_candidate_identifier(row.get("id"))
        name = row.get("name")
        if rid is None or rid in seen or not isinstance(name, str) or not name.strip():
            continue
        relevance = row.get("relevance", row.get("score"))
        if isinstance(relevance, bool) or not isinstance(relevance, (int, float)):
            relevance = None
        elif not math.isfinite(float(relevance)):
            relevance = None
        evidence_row = dict(row)
        evidence_row["name"] = name.strip()[:200]
        evidence_row["relevance"] = relevance
        candidates.append({
            "id": rid,
            "name": name.strip()[:200],
            "domain": row.get("domain", "").strip()[:120]
            if isinstance(row.get("domain", ""), str) else "",
            "type_id": row.get("type_id", "").strip()[:120]
            if isinstance(row.get("type_id", ""), str) else "",
            "description": row.get("description", "").strip()[:600]
            if isinstance(row.get("description", ""), str) else "",
            "retrieval_rank": len(candidates) + 1,
            "candidate_note": notes.get(rid),
            "evidence": kb_candidate_evidence(
                evidence_row,
                counterexample="需要在目标领域验证方法假设、观测量和边界条件。",
            ),
        })
        seen.add(rid)
        if len(candidates) >= top_n:
            break
    return candidates


# --- orchestration ------------------------------------------------------------

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
    started = time.monotonic()

    signature_budget = min(
        SIGNATURE_TIMEOUT_SECONDS,
        METHOD_SEARCH_TOTAL_BUDGET_SECONDS,
    )
    try:
        sig = await asyncio.wait_for(
            extract_signature(method_text, timeout_seconds=signature_budget),
            timeout=signature_budget,
        )
    except TimeoutError as exc:
        logger.warning(
            "retrieval.method_signature_timeout",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        sig = _coerce_signature(None, method_text)
    query = build_query(sig)

    # Search a slightly larger pool than top_n so ranking has headroom.
    results = search_svc.search(query, top_k=min(top_n * 2, 30)) if query else []

    # Annotate only the slice we will actually return.
    head = rank_matches(results, {}, top_n)
    remaining = METHOD_SEARCH_TOTAL_BUDGET_SECONDS - (time.monotonic() - started)
    annotation_budget = min(ANNOTATION_TIMEOUT_SECONDS, max(0.0, remaining))
    notes: dict[str, str] = {}
    if annotation_budget > 0:
        try:
            notes = await asyncio.wait_for(
                annotate_matches(
                    sig,
                    head,
                    timeout_seconds=annotation_budget,
                ),
                timeout=annotation_budget,
            )
        except TimeoutError as exc:
            logger.warning(
                "retrieval.method_annotation_timeout",
                count=len(head),
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
    else:
        logger.warning(
            "retrieval.method_annotation_skipped",
            count=len(head),
        )
    candidates = rank_candidates(results, notes, top_n)

    return {
        "method": method_text,
        "signature": sig["signature"],
        "signature_origin": "model_generated" if sig["llm"] else "input_fallback",
        "keywords": sig["keywords"],
        "count": len(candidates),
        "candidates": candidates,
    }
