"""Structural stress-test service (Session ***REMOVED***18, feature E).

The product takes ONE business analogy / strategic claim and ONLY tries to
falsify it. It never flatters, never agrees for the sake of agreeing. It
decomposes the analogy into source / target, lists the structural
correspondences the user implicitly assumes, red-teams each one, names the
weakest link, and gives a hard verdict (PASS / FAIL / CONDITIONAL).

LLM access goes through the generic `llm_client` wrapper. When no API key is
configured `complete_json` returns None — callers must surface a clean 503.
Everything the LLM returns is treated as untrusted: schema, types and the
verdict enum are validated / coerced before reaching the API layer.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services import llm_client

logger = logging.getLogger("structural.stress_test")

***REMOVED*** Verdict enum — the only three values the API will ever emit.
VERDICTS = ("PASS", "FAIL", "CONDITIONAL")

***REMOVED*** Hard input bounds. A claim is one sentence-ish; anything past this is abuse.
CLAIM_MIN_LEN = 4
CLAIM_MAX_LEN = 600

***REMOVED*** Cap how many correspondences we keep — a runaway LLM could emit dozens.
MAX_CORRESPONDENCES = 12

_SYSTEM_PROMPT = """你是一个冷静、严苛的结构红队分析师（red team）。

用户会给你一个商业类比或战略判断（例如"我们是中国版的 Notion"、\
"这次 AI 泡沫和 2000 年互联网泡沫一样"）。

你的唯一任务是【证伪】——不夸奖、不顺着说、不给鼓励性废话。专门检查这个\
类比在结构上到底成不成立、最可能从哪一环崩。

工作步骤：
1. 把类比拆成 source（被类比的对象/先例）和 target（用户自己的对象）。
2. 列出用户隐含主张的结构对应关系——即用户假设 source 和 target 在哪些\
环节上是同构的（机制、增长飞轮、护城河、用户行为、单位经济、监管环境等）。
3. 对每一条对应关系做对抗性压力测试：这一环到底成不成立？在什么条件下会崩？\
找出 source 成立但 target 不成立的差异点。
4. 指出最薄弱的一环（weakest link）——整个类比最先崩的地方。
5. 给一个明确结论 verdict，三选一：
   - PASS：结构对应基本成立，类比站得住
   - FAIL：关键环节不同构，类比误导
   - CONDITIONAL：部分成立，依赖明确的前提条件

严格要求：
- 立场是证伪，不是平衡报道。如果类比有问题，直说。
- 每条 stress_result 要具体，点出真实的结构差异，不要套话。
- holds 字段只在该环节确实成立时才为 true。

只输出 JSON，结构如下：
{
  "source": "被类比的对象，一句话",
  "target": "用户自己的对象，一句话",
  "structural_correspondences": [
    {
      "claim": "用户隐含假设的某条结构对应（一句话）",
      "stress_result": "对这条做对抗性压力测试的结论，指出会不会崩、什么条件下崩",
      "holds": true
    }
  ],
  "weakest_link": "整个类比最薄弱、最先崩的一环",
  "verdict": "PASS | FAIL | CONDITIONAL",
  "verdict_reason": "给出该裁决的核心理由，2-3 句"
}"""


def validate_claim(claim: Any) -> str:
    """Validate + normalise the incoming claim text.

    Raises ValueError on empty / non-str / too-long input. Returns the
    stripped claim on success.
    """
    if not isinstance(claim, str):
        raise ValueError("claim 必须是文本")
    stripped = claim.strip()
    if len(stripped) < CLAIM_MIN_LEN:
        raise ValueError("claim 太短，请输入一个完整的类比或判断")
    if len(stripped) > CLAIM_MAX_LEN:
        raise ValueError(f"claim 过长（上限 {CLAIM_MAX_LEN} 字）")
    return stripped


def _coerce_verdict(raw: Any) -> Optional[str]:
    """Normalise an LLM-supplied verdict to the enum, or None if unusable.

    Accepts case-insensitive matches and a few common synonyms. Returning
    None lets the caller decide to degrade rather than emit a bogus enum.
    """
    if not isinstance(raw, str):
        return None
    norm = raw.strip().upper()
    if norm in VERDICTS:
        return norm
    ***REMOVED*** Common synonyms an LLM might drift into.
    synonyms = {
        "PASSED": "PASS",
        "VALID": "PASS",
        "HOLDS": "PASS",
        "FAILED": "FAIL",
        "INVALID": "FAIL",
        "BROKEN": "FAIL",
        "CONDITIONALLY": "CONDITIONAL",
        "PARTIAL": "CONDITIONAL",
        "PARTIALLY": "CONDITIONAL",
        "DEPENDS": "CONDITIONAL",
    }
    return synonyms.get(norm)


def _coerce_correspondence(item: Any) -> Optional[dict]:
    """Coerce one correspondence entry; None if it has no usable claim."""
    if not isinstance(item, dict):
        return None
    claim = item.get("claim")
    if not isinstance(claim, str) or not claim.strip():
        return None
    stress = item.get("stress_result")
    stress_str = stress.strip() if isinstance(stress, str) else ""
    holds = item.get("holds")
    ***REMOVED*** holds defaults to False — an unproven correspondence is not "holds".
    holds_bool = holds is True
    return {
        "claim": claim.strip(),
        "stress_result": stress_str or "（模型未给出压力测试结论）",
        "holds": holds_bool,
    }


def coerce_result(raw: Any) -> Optional[dict]:
    """Validate + coerce the raw LLM JSON into the API response shape.

    Returns a clean dict, or None when the payload is so malformed it has
    no recoverable content (not a dict, or no correspondences AND no
    verdict). The caller treats None as a degraded LLM failure.
    """
    if not isinstance(raw, dict):
        return None

    source = raw.get("source")
    target = raw.get("target")
    source_str = source.strip() if isinstance(source, str) and source.strip() else "（未识别）"
    target_str = target.strip() if isinstance(target, str) and target.strip() else "（未识别）"

    raw_corrs = raw.get("structural_correspondences")
    correspondences: list[dict] = []
    if isinstance(raw_corrs, list):
        for item in raw_corrs:
            coerced = _coerce_correspondence(item)
            if coerced is not None:
                correspondences.append(coerced)
            if len(correspondences) >= MAX_CORRESPONDENCES:
                break

    verdict = _coerce_verdict(raw.get("verdict"))

    ***REMOVED*** If the LLM gave us neither correspondences nor a verdict, there is
    ***REMOVED*** nothing worth showing — treat as a failure.
    if not correspondences and verdict is None:
        return None

    weakest = raw.get("weakest_link")
    weakest_str = (
        weakest.strip()
        if isinstance(weakest, str) and weakest.strip()
        else "（模型未指出最薄弱环节）"
    )

    reason = raw.get("verdict_reason")
    reason_str = (
        reason.strip()
        if isinstance(reason, str) and reason.strip()
        else "（模型未给出裁决理由）"
    )

    ***REMOVED*** When verdict is missing/illegal, fall back deterministically from the
    ***REMOVED*** correspondence results rather than emitting an invalid enum.
    if verdict is None:
        if correspondences and all(c["holds"] for c in correspondences):
            verdict = "PASS"
        elif correspondences and not any(c["holds"] for c in correspondences):
            verdict = "FAIL"
        else:
            verdict = "CONDITIONAL"
        reason_str = "（模型未返回合法裁决，已根据各环节压力测试结果推导）"

    return {
        "source": source_str,
        "target": target_str,
        "structural_correspondences": correspondences,
        "weakest_link": weakest_str,
        "verdict": verdict,
        "verdict_reason": reason_str,
    }


async def run_stress_test(claim: str) -> Optional[dict]:
    """Run the full stress test for one claim.

    Returns the coerced result dict, or None when the LLM is unavailable /
    failed / returned unrecoverable garbage. Never raises on LLM problems.
    """
    user_prompt = f"请对下面这个类比/判断做结构压力测试：\n\n{claim}"
    raw = await llm_client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.3,  ***REMOVED*** low — we want consistent, critical reasoning
        max_tokens=2600,
    )
    if raw is None:
        logger.warning("run_stress_test: LLM returned None")
        return None
    coerced = coerce_result(raw)
    if coerced is None:
        logger.warning("run_stress_test: LLM output failed schema coercion")
    return coerced


__all__ = [
    "VERDICTS",
    "CLAIM_MIN_LEN",
    "CLAIM_MAX_LEN",
    "validate_claim",
    "coerce_result",
    "run_stress_test",
]
