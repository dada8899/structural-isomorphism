"""C2 structural-lint service — Session ***REMOVED***18.

Feeds a strategy / plan document to an LLM and extracts the document's
*structural claims*: implicit assumptions, cross-domain analogies, and
causal judgments. For each claim it surfaces the underlying structure,
the failure mode that structure most commonly hits, a risk level, and a
mitigation suggestion.

Session ***REMOVED***18 deepening — this is NOT a bare-LLM wrapper. After the LLM
extracts the claims, each claim's structural description is used to
query the KB (the cross-domain structural-isomorphism engine). When a
structurally similar *real phenomenon* is found, a second LLM pass
re-grounds the failure mode on that real anchor instead of free-form
speculation. That structural anchor is the product's moat.

The LLM is untrusted. `normalize_lint_result` is a hard guardrail: it
validates enum fields, drops malformed claims, and never lets a bad
payload through. When no API key is configured the endpoint degrades to
an explicit "llm unavailable" response (see api/struct_lint.py). When
the search service is unavailable or finds nothing, the isomorph field
degrades to None and C2 still returns a usable basic lint.
"""
from __future__ import annotations

import logging
from typing import Optional

from services import llm_client

logger = logging.getLogger("structural.struct_lint")

***REMOVED*** Hard cap on input length. Longer documents are rejected with HTTP 400
***REMOVED*** rather than silently truncated — a truncated doc produces a misleading
***REMOVED*** "structural risk" report on a fragment the user didn't intend to send.
MAX_DOC_CHARS = 20000

***REMOVED*** Enum whitelists — anything outside these is malformed LLM output.
CLAIM_TYPES = {"assumption", "analogy", "causal_judgment"}
RISK_LEVELS = {"high", "medium", "low"}

***REMOVED*** Defensive cap on how many claims we keep, so a runaway LLM reply can't
***REMOVED*** bloat the response payload.
MAX_CLAIMS = 30

***REMOVED*** How many KB phenomena to fetch per claim. We keep the top-1 as the
***REMOVED*** structural anchor; a 2nd is fetched only as a fallback candidate.
ISOMORPH_TOP_K = 2

***REMOVED*** Only claims at/above this many chars of structure text are worth a KB
***REMOVED*** query — a near-empty structure string yields noise matches.
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


***REMOVED*** Second-pass prompt — given a claim + the real KB phenomenon that is
***REMOVED*** structurally isomorphic to it, re-ground the failure mode on that real
***REMOVED*** anchor. The point is to replace free-form speculation with "this same
***REMOVED*** structure already failed THIS way in domain X".
_ANCHOR_SYSTEM_PROMPT = """你是一个"结构 lint"工具的失效模式分析模块。

你会收到：一条策略文档里的结构性主张，它的底层结构描述，以及一个**已知的、来自其他领域的真实现象**——这个真实现象的底层结构和这条主张是同构的（结构相似）。

你的任务：基于那个真实现象**已知的失效方式**，重新给出这条主张的失效模式和对冲建议。要求：
- failure_mode：明确点出"这条主张的结构和『某领域的某现象』同构；那个现象在 XX 条件下会失效，因此这条主张同样会在类似条件下崩"。要具体，不要泛泛而谈。
- suggestion：基于这个真实锚点给一条可执行的对冲建议。

只输出 JSON，格式严格如下：
{
  "failure_mode": "挂靠到真实现象的失效模式描述，2-4 句话",
  "suggestion": "基于真实锚点的对冲建议，1-2 句话"
}

全部用中文。如果那个真实现象其实和这条主张关系不大，failure_mode 里如实说明同构关系较弱，并退回到结构本身最常见的失效模式。"""


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
        ***REMOVED*** A claim with no source quote is unverifiable — drop it.
        return None

    claim_type = _coerce_str(raw.get("claim_type")).lower()
    if claim_type not in CLAIM_TYPES:
        ***REMOVED*** Out-of-enum claim_type — we can't trust the categorization, drop.
        return None

    risk_level = _coerce_str(raw.get("risk_level")).lower()
    if risk_level not in RISK_LEVELS:
        ***REMOVED*** Unknown risk level — normalize to "medium" rather than drop, so
        ***REMOVED*** the claim (which has a valid quote + type) is still surfaced.
        risk_level = "medium"

    return {
        "quote": quote[:600],
        "claim_type": claim_type,
        "structure": _coerce_str(raw.get("structure"))[:800] or "未提供结构描述",
        "failure_mode": _coerce_str(raw.get("failure_mode"))[:800] or "未提供失效模式",
        "risk_level": risk_level,
        "suggestion": _coerce_str(raw.get("suggestion"))[:800] or "未提供建议",
        ***REMOVED*** Filled in by the KB isomorphism pass; None when search is
        ***REMOVED*** unavailable or finds nothing. Keep the key present always so the
        ***REMOVED*** frontend can rely on its existence.
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
    ***REMOVED*** relevance is a [0,1] float; clamp defensively.
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
    except Exception:
        logger.warning("struct_lint: KB search failed for a claim", exc_info=True)
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
    except Exception:
        logger.warning("struct_lint: anchor LLM pass raised", exc_info=True)
        return
    if not isinstance(raw, dict):
        return
    anchored_fm = _coerce_str(raw.get("failure_mode"))
    anchored_sug = _coerce_str(raw.get("suggestion"))
    ***REMOVED*** Only overwrite when the anchored output is non-empty — a blank
    ***REMOVED*** second pass must not wipe a usable first-pass failure mode.
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
        ***REMOVED*** Anchor found — re-ground the failure mode on this real phenomenon.
        await _anchor_failure_mode(claim, anchor)


async def lint_document(document: str, search_svc=None) -> Optional[dict]:
    """Run the structural lint on a document.

    Returns the normalized {"summary", "claims"} dict, or None when the
    first LLM call fails or returns an unusable payload. The caller
    decides how to surface a degraded result.

    `search_svc` is the running SearchService instance (app_state["search"]).
    When provided, each extracted claim is matched against the KB for a
    structurally isomorphic real phenomenon, and the failure mode is
    re-grounded on that anchor. When None (search not ready), C2 still
    returns a usable basic lint with isomorph=None on every claim.
    """
    user_prompt = f"请对下面这份策略/方案文档做结构 lint：\n\n{document}"
    raw = await llm_client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.3,
        max_tokens=3200,
    )
    if raw is None:
        logger.warning("lint_document: LLM returned no payload")
        return None
    result = normalize_lint_result(raw)
    if result is None:
        return None
    ***REMOVED*** Session ***REMOVED***18 deepening — the KB isomorphism pass. Best-effort: any
    ***REMOVED*** failure here leaves claims with isomorph=None, never breaks the lint.
    try:
        await _attach_isomorphs(result["claims"], search_svc)
    except Exception:
        logger.warning("lint_document: isomorph pass failed", exc_info=True)
    return result


__all__ = [
    "MAX_DOC_CHARS",
    "CLAIM_TYPES",
    "RISK_LEVELS",
    "ISOMORPH_TOP_K",
    "check_doc_length",
    "normalize_lint_result",
    "build_isomorph_query",
    "normalize_isomorph",
    "lint_document",
]
