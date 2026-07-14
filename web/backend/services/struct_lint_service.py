"""C2 structural-lint service — Session #18.

Feeds a strategy / plan document to an LLM and extracts the document's
*structural claims*: implicit assumptions, cross-domain analogies, and
causal judgments. For each claim it surfaces the underlying structure,
the failure mode that structure most commonly hits, a risk level, and a
mitigation suggestion.

After the LLM extracts claims, each structural description may query the KB
for a candidate reference. Retrieval does not prove shared mechanism and
never rewrites the model-generated failure mode.

The LLM is untrusted. The live path uses `validate_lint_result`, rejects the
whole payload on any malformed claim, and binds every quote to the submitted
document. When search is unavailable, references remain null.
"""
from __future__ import annotations

import hashlib
from typing import Any, AsyncIterator, Optional

if __package__ == "web.backend.services":
    from . import llm_client
    from .input_limits import normalize_research_text
    from .search_synthesis import validate_candidate_public_texts
    from .secondary_tool_contracts import (
        internal_screen_evidence,
        kb_candidate_evidence,
    )
    from ..logging_config import get_logger, new_incident_id
else:
    from services import llm_client
    from services.input_limits import normalize_research_text
    from services.search_synthesis import validate_candidate_public_texts
    from services.secondary_tool_contracts import (
        internal_screen_evidence,
        kb_candidate_evidence,
    )
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.struct_lint")

# Hard cap on input length. Longer documents are rejected with HTTP 400
# rather than silently truncated — a truncated doc produces a misleading
# "structural risk" report on a fragment the user didn't intend to send.
MAX_DOC_CHARS = 20000

# Enum whitelists — anything outside these is malformed LLM output.
CLAIM_TYPES = {"assumption", "analogy", "causal_judgment"}
RISK_LEVELS = {"high", "medium", "low"}

# Defensive cap on how many claims we keep, so a runaway LLM reply can't
# bloat the response payload.
MAX_CLAIMS = 30

# How many KB phenomena to fetch per claim. We display at most one candidate;
# the second is only a fallback for malformed retrieval rows.
ISOMORPH_TOP_K = 2

# Only claims at/above this many chars of structure text are worth a KB
# query — a near-empty structure string yields noise matches.
_MIN_STRUCTURE_FOR_SEARCH = 6

_SYSTEM_PROMPT = """你是一个"结构 lint"工具，像代码审查工具审查代码一样审查策略/方案文档。

你的任务：从文档里找出**结构性主张**——那些文档作者隐含依赖、但没有明说、一旦不成立整个方案就会出问题的东西。三类：
1. assumption（隐含假设）：方案默认成立、但其实需要被验证的前提。
2. analogy（跨域类比）：把另一个领域/案例的逻辑搬过来用的地方。
3. causal_judgment（因果判断）："做 A 就会得到 B" 这种因果断言。

对每一条主张，你要：
- 引用原文片段（quote，尽量是原文里的一句话或短语，不要改写）
- 判断它属于哪一类（claim_type）
- 描述它的底层结构（structure，用结构化语言：这是个什么形状的逻辑）
- 指出这个结构最常见的失效模式（failure_mode：什么条件下它会崩，历史上同类结构怎么失败的）
- 给一个风险等级（risk_level：high/medium/low）
- 给一条具体的对冲建议（suggestion）

最后给整个文档一个 summary：这份方案最大的结构性风险是什么。

只输出 JSON，格式严格如下：
{
  "summary": "整个文档最大的结构性风险，2-4 句话",
  "claims": [
    {
      "quote": "原文片段",
      "claim_type": "assumption | analogy | causal_judgment",
      "structure": "底层结构描述",
      "failure_mode": "这个结构最常见的失效模式",
      "risk_level": "high | medium | low",
      "suggestion": "具体对冲建议"
    }
  ]
}

要求：claim_type 和 risk_level 必须是上面列出的英文枚举值之一。其余字段用中文。
如果文档里找不到任何结构性主张，claims 返回空数组，summary 说明原因。"""


# Legacy note prompt retained for compatibility-only helpers below. The live
# v2 path attaches a retrieval candidate without rewriting the failure mode.
_ANCHOR_SYSTEM_PROMPT = """你是一个"结构 lint"工具的候选参照分析模块。

你会收到：一条策略文档里的结构性主张，以及一个内部知识库检索候选。
检索候选只用于后续核查，不证明两者同构，也不是现实证据。

你的任务：说明为什么值得比较，以及哪个观察会推翻这个参照。不得把候选改写成
真实先例、已经同构、确认适用、证据或成功概率。

只输出 JSON，格式严格如下：
{
  "candidate_note": "待核查说明，1-2 句话"
}

全部用中文。"""


def check_doc_length(document: str) -> Optional[str]:
    """Validate raw document input.

    Returns an error message string when the input is unusable (empty or
    over the length cap), or None when it is fine to process.
    """
    if document is None or not document.strip():
        return "empty_document"
    if len(document) > MAX_DOC_CHARS:
        return "document_too_long"
    return None


def _coerce_str(value, default: str = "") -> str:
    """Best-effort string coercion for an untrusted LLM field."""
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def _normalize_claim(raw) -> Optional[dict]:
    """Validate one raw claim object from the LLM.

    Returns a clean claim dict, or None if the claim is malformed beyond
    repair (not a dict, missing quote, or an out-of-range enum we can't
    safely keep). Enum violations drop the claim rather than guessing.
    """
    if not isinstance(raw, dict):
        return None

    quote = _coerce_str(raw.get("quote"))
    if not quote:
        # A claim with no source quote is unverifiable — drop it.
        return None

    claim_type = _coerce_str(raw.get("claim_type")).lower()
    if claim_type not in CLAIM_TYPES:
        # Out-of-enum claim_type — we can't trust the categorization, drop.
        return None

    risk_level = _coerce_str(raw.get("risk_level")).lower()
    if risk_level not in RISK_LEVELS:
        # Unknown risk level — normalize to "medium" rather than drop, so
        # the claim (which has a valid quote + type) is still surfaced.
        risk_level = "medium"

    return {
        "quote": quote[:600],
        "claim_type": claim_type,
        "structure": _coerce_str(raw.get("structure"))[:800] or "未提供结构描述",
        "failure_mode": _coerce_str(raw.get("failure_mode"))[:800] or "未提供失效模式",
        "risk_level": risk_level,
        "suggestion": _coerce_str(raw.get("suggestion"))[:800] or "未提供建议",
        # Filled in by the KB isomorphism pass; None when search is
        # unavailable or finds nothing. Keep the key present always so the
        # frontend can rely on its existence.
        "isomorph": None,
    }


def build_isomorph_query(claim: dict) -> str:
    """Build a KB search query from a normalized claim.

    The query is the claim's *structural* description — that is what we
    want a cross-domain structural match on, not the surface wording of
    the quote. We append the structure twice-weighted by also including
    the failure_mode hint, since structurally similar phenomena tend to
    share failure shapes.

    Returns an empty string when the claim has no usable structure text;
    the caller then skips the KB lookup for this claim.
    """
    if not isinstance(claim, dict):
        return ""
    structure = _coerce_str(claim.get("structure"))
    if structure in ("", "未提供结构描述") or len(structure) < _MIN_STRUCTURE_FOR_SEARCH:
        return ""
    failure = _coerce_str(claim.get("failure_mode"))
    if failure and failure != "未提供失效模式":
        return f"{structure}。失效特征：{failure}"
    return structure


def normalize_isomorph(raw) -> Optional[dict]:
    """Validate one KB search result into a compact isomorph anchor.

    Returns {id, name, domain, relevance, description} or None when the
    result is unusable (not a dict, or has no id). Untrusted in the sense
    that search results are produced by an external service — we coerce
    types and never let a malformed entry through.
    """
    if not isinstance(raw, dict):
        return None
    pid = _coerce_str(raw.get("id"))
    if not pid:
        return None
    # relevance is a [0,1] float; clamp defensively.
    try:
        relevance = float(raw.get("relevance", 0.0))
    except (TypeError, ValueError):
        relevance = 0.0
    relevance = max(0.0, min(1.0, relevance))
    return {
        "id": pid,
        "name": _coerce_str(raw.get("name"))[:200] or pid,
        "domain": _coerce_str(raw.get("domain"))[:120],
        "relevance": round(relevance, 4),
        "description": _coerce_str(raw.get("description"))[:400],
    }


def _search_isomorph(search_svc, query: str) -> Optional[dict]:
    """Run one KB search for a claim and return the top isomorph anchor.

    Degrades to None on any failure — no search service, search raising,
    or empty hits. C2 must still produce a basic lint without this.
    """
    if search_svc is None or not query:
        return None
    try:
        hits = search_svc.search(query, top_k=ISOMORPH_TOP_K)
    except Exception as exc:
        logger.warning(
            "structural.struct_lint_search_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return None
    if not isinstance(hits, list) or not hits:
        return None
    for hit in hits:
        anchor = normalize_isomorph(hit)
        if anchor is not None:
            return anchor
    return None


async def _anchor_failure_mode(claim: dict, isomorph: dict) -> None:
    """Re-ground a claim's failure_mode/suggestion on a real KB anchor.

    Mutates `claim` in place. A best-effort second LLM pass: on any
    failure (no key, bad JSON, empty fields) the claim keeps its original
    free-form failure_mode — we never make the result worse than before.
    """
    user_prompt = (
        f"主张原文：{claim.get('quote', '')}\n"
        f"主张类型：{claim.get('claim_type', '')}\n"
        f"它的底层结构：{claim.get('structure', '')}\n\n"
        f"结构同构的真实现象（来自知识库）：\n"
        f"- 名称：{isomorph.get('name', '')}\n"
        f"- 所属领域：{isomorph.get('domain', '')}\n"
        f"- 描述：{isomorph.get('description', '')}\n\n"
        f"请基于这个真实现象重新给出失效模式和对冲建议。"
    )
    try:
        raw = await llm_client.complete_json(
            system=_ANCHOR_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.3,
            max_tokens=600,
        )
    except Exception as exc:
        logger.warning(
            "structural.struct_lint_anchor_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return
    if not isinstance(raw, dict):
        return
    anchored_fm = _coerce_str(raw.get("failure_mode"))
    anchored_sug = _coerce_str(raw.get("suggestion"))
    # Only overwrite when the anchored output is non-empty — a blank
    # second pass must not wipe a usable first-pass failure mode.
    if anchored_fm:
        claim["failure_mode"] = anchored_fm[:800]
    if anchored_sug:
        claim["suggestion"] = anchored_sug[:800]


def normalize_lint_result(raw) -> Optional[dict]:
    """Guardrail over the raw LLM JSON reply.

    Returns a clean {"summary": str, "claims": [...]} dict, or None when
    the payload is unusable (not a dict). Malformed individual claims are
    silently filtered out — a partially-bad reply still yields the good
    claims rather than failing the whole request.
    """
    if not isinstance(raw, dict):
        return None

    claims_raw = raw.get("claims")
    if not isinstance(claims_raw, list):
        claims_raw = []

    claims = []
    for item in claims_raw:
        clean = _normalize_claim(item)
        if clean is not None:
            claims.append(clean)
        if len(claims) >= MAX_CLAIMS:
            break

    summary = _coerce_str(raw.get("summary"))
    if not summary:
        summary = (
            "未能从文档中识别出明确的结构性风险摘要。"
            if claims
            else "未在文档中识别到结构性主张。"
        )

    return {"summary": summary[:1200], "claims": claims}


def validate_lint_result(raw: Any, document: str) -> Optional[dict]:
    """Strict execution-path validator with verbatim source-quote binding."""
    if not isinstance(raw, dict) or set(raw) != {"summary", "claims"}:
        return None
    claims_raw = raw.get("claims")
    if not isinstance(claims_raw, list) or len(claims_raw) > MAX_CLAIMS:
        return None
    try:
        normalized_document = normalize_research_text(
            document,
            max_chars=MAX_DOC_CHARS,
            allow_layout=True,
            field_name="document",
        )
        summary = normalize_research_text(
            raw.get("summary"),
            max_chars=1_200,
            allow_layout=False,
            field_name="summary",
        )
        claims: list[dict[str, Any]] = []
        for index, item in enumerate(claims_raw):
            if not isinstance(item, dict) or set(item) != {
                "quote",
                "claim_type",
                "structure",
                "failure_mode",
                "risk_level",
                "suggestion",
            }:
                return None
            quote = normalize_research_text(
                item.get("quote"),
                max_chars=600,
                allow_layout=True,
                field_name="quote",
            )
            if quote not in normalized_document:
                return None
            claim_type = item.get("claim_type")
            review_priority = item.get("risk_level")
            if claim_type not in CLAIM_TYPES or review_priority not in RISK_LEVELS:
                return None
            structure = normalize_research_text(
                item.get("structure"),
                max_chars=800,
                allow_layout=False,
                field_name="structure",
            )
            failure_mode = normalize_research_text(
                item.get("failure_mode"),
                max_chars=800,
                allow_layout=False,
                field_name="failure_mode",
            )
            suggestion = normalize_research_text(
                item.get("suggestion"),
                max_chars=800,
                allow_layout=False,
                field_name="suggestion",
            )
            claim_id = "lint-" + hashlib.sha256(
                f"{normalized_document}\x1f{index}\x1f{quote}".encode("utf-8")
            ).hexdigest()[:16]
            claims.append({
                "claim_id": claim_id,
                "quote": quote,
                "claim_type": claim_type,
                "structure": structure,
                "failure_mode": failure_mode,
                "review_priority": review_priority,
                "suggestion": suggestion,
                "reference_candidate": None,
                "evidence": internal_screen_evidence(
                    kind="document_claim_screen", label=quote
                ),
            })
        validate_candidate_public_texts(
            [
                summary,
                *(
                    text
                    for claim in claims
                    for text in (
                        claim["structure"],
                        claim["failure_mode"],
                        claim["suggestion"],
                    )
                ),
            ]
        )
    except (TypeError, ValueError):
        return None
    return {"summary": summary, "claims": claims}


def build_reference_candidate(raw: Any, retrieval_rank: int = 1) -> Optional[dict]:
    """Bind a public candidate reference to one exact SearchService row."""
    normalized = normalize_isomorph(raw)
    if normalized is None:
        return None
    name = normalized["name"]
    if not name:
        return None
    return {
        "id": normalized["id"],
        "name": name,
        "domain": normalized["domain"],
        "description": normalized["description"],
        "retrieval_rank": retrieval_rank,
        "candidate_note": None,
        "evidence": kb_candidate_evidence(
            raw,
            counterexample="需要核查原文主张与候选记录的机制、尺度和失效边界。",
        ),
    }


def _search_reference_candidate(search_svc: Any, query: str) -> Optional[dict]:
    """Retrieve, bind and return the first valid candidate row."""
    if search_svc is None or not query:
        return None
    try:
        hits = search_svc.search(query, top_k=ISOMORPH_TOP_K)
    except Exception as exc:
        logger.warning(
            "structural.struct_lint_candidate_search_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return None
    if not isinstance(hits, list):
        return None
    for index, hit in enumerate(hits, start=1):
        candidate = build_reference_candidate(hit, retrieval_rank=index)
        if candidate is not None:
            return candidate
    return None


def _attach_reference_candidates(claims: list[dict], search_svc: Any) -> None:
    """Attach retrieval candidates without allowing them to rewrite claims."""
    if search_svc is None:
        return
    for claim in claims:
        query = build_isomorph_query(claim)
        claim["reference_candidate"] = _search_reference_candidate(search_svc, query)


async def _attach_isomorphs(claims: list, search_svc) -> None:
    """For each claim, find a structurally isomorphic real KB phenomenon
    and re-ground its failure mode on that anchor. Mutates `claims`.

    Degrades cleanly: when search_svc is None every claim simply keeps
    isomorph=None and its original LLM-generated failure mode.
    """
    if search_svc is None:
        return
    for claim in claims:
        query = build_isomorph_query(claim)
        anchor = _search_isomorph(search_svc, query)
        if anchor is None:
            continue
        claim["isomorph"] = anchor
        # Anchor found — re-ground the failure mode on this real phenomenon.
        await _anchor_failure_mode(claim, anchor)


async def lint_document(document: str, search_svc=None) -> Optional[dict]:
    """Run the structural lint on a document.

    Returns the normalized {"summary", "claims"} dict, or None when the
    first LLM call fails or returns an unusable payload. The caller
    decides how to surface a degraded result.

    `search_svc` is the running SearchService instance. When provided, each
    claim may receive one untested KB candidate reference. When absent, the
    strict document screen still returns with references set to null.
    """
    user_prompt = f"请对下面这份策略/方案文档做结构 lint：\n\n{document}"
    raw = await llm_client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.3,
        max_tokens=3200,
    )
    if raw is None:
        logger.warning("structural.struct_lint_payload_missing")
        return None
    result = validate_lint_result(raw, document)
    if result is None:
        return None
    # Candidate retrieval is optional and cannot alter the primary screen.
    try:
        _attach_reference_candidates(result["claims"], search_svc)
    except Exception as exc:
        logger.warning(
            "structural.struct_lint_isomorph_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
    return result


async def lint_document_streamed(
    document: str, search_svc=None
) -> AsyncIterator[dict]:
    """Run the structural lint, yielding progress events as it goes.

    Same pipeline as lint_document(), but instead of blocking 36-165s on a
    single return value it yields dict events the SSE endpoint can forward:

      {"type": "progress", "stage": "extract",  "message": ...}
      {"type": "progress", "stage": "claims",   "claim_count": N}
      {"type": "progress", "stage": "candidate_reference", "current": i, "total": N,
                            "message": ...}
      {"type": "done",     "result": {"summary", "claims": [...]}}
      {"type": "error",    "message": ...}

    The result payload is byte-identical to lint_document()'s return value,
    so the frontend renders it the same way. On any LLM failure it yields a
    single `error` event and stops — never raises.
    """
    # --- Stage 1: extract structural claims (the long blocking LLM call) ---
    yield {
        "type": "progress",
        "stage": "extract",
        "message": "正在逐条抽取文档里的结构性主张……",
    }
    user_prompt = f"请对下面这份策略/方案文档做结构 lint：\n\n{document}"
    raw = await llm_client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.3,
        max_tokens=3200,
    )
    if raw is None:
        logger.warning("structural.struct_lint_payload_missing")
        yield {"type": "error", "message": "结构 lint 生成失败，请稍后重试。"}
        return
    result = validate_lint_result(raw, document)
    if result is None:
        yield {"type": "error", "message": "结构 lint 生成失败，请稍后重试。"}
        return

    claims = result["claims"]
    yield {
        "type": "progress",
        "stage": "claims",
        "claim_count": len(claims),
        "message": f"已抽取 {len(claims)} 条结构性主张，正在比对失效模式……",
    }

    # --- Stage 2: per-claim KB candidate retrieval. No second model is allowed
    # to rewrite the extracted claim or make the retrieval row sound proven. ---
    if search_svc is not None and claims:
        total = len(claims)
        for i, claim in enumerate(claims, start=1):
            yield {
                "type": "progress",
                "stage": "candidate_reference",
                "current": i,
                "total": total,
                "message": f"正在为第 {i}/{total} 条主张检索候选参照……",
            }
            try:
                query = build_isomorph_query(claim)
                claim["reference_candidate"] = _search_reference_candidate(
                    search_svc, query
                )
            except Exception as exc:
                logger.warning(
                    "structural.struct_lint_isomorph_failed",
                    error_type=type(exc).__name__,
                    incident_id=new_incident_id(),
                )

    yield {"type": "done", "result": result}


__all__ = [
    "MAX_DOC_CHARS",
    "CLAIM_TYPES",
    "RISK_LEVELS",
    "ISOMORPH_TOP_K",
    "check_doc_length",
    "normalize_lint_result",
    "validate_lint_result",
    "build_isomorph_query",
    "normalize_isomorph",
    "build_reference_candidate",
    "lint_document",
    "lint_document_streamed",
]
