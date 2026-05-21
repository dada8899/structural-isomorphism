"""C2 structural-lint service — Session ***REMOVED***18.

Feeds a strategy / plan document to an LLM and extracts the document's
*structural claims*: implicit assumptions, cross-domain analogies, and
causal judgments. For each claim it surfaces the underlying structure,
the failure mode that structure most commonly hits, a risk level, and a
mitigation suggestion.

The LLM is untrusted. `normalize_lint_result` is a hard guardrail: it
validates enum fields, drops malformed claims, and never lets a bad
payload through. When no API key is configured the endpoint degrades to
an explicit "llm unavailable" response (see api/struct_lint.py).
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
    }


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


async def lint_document(document: str) -> Optional[dict]:
    """Run the structural lint on a document.

    Returns the normalized {"summary", "claims"} dict, or None when the
    LLM call fails or returns an unusable payload. The caller decides how
    to surface a degraded result.
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
    return normalize_lint_result(raw)


__all__ = [
    "MAX_DOC_CHARS",
    "CLAIM_TYPES",
    "RISK_LEVELS",
    "check_doc_length",
    "normalize_lint_result",
    "lint_document",
]
