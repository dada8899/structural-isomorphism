"""Structural stress-test service (Session #18, feature E).

The product takes ONE business analogy / strategic claim and ONLY tries to
falsify it. It never flatters or agrees for the sake of agreeing. It
decomposes the analogy into source / target, lists the structural
correspondences the user implicitly assumes, and red-teams each one. The model
uses a three-way internal screen; the public contract maps it to neutral,
candidate-level outcomes and never presents it as empirical validation.

LLM access goes through the generic `llm_client` wrapper. When no API key is
configured `complete_json` returns None — callers must surface a clean 503.
Everything the LLM returns is treated as untrusted: schema, types and the
verdict enum are validated / coerced before reaching the API layer.
"""
from __future__ import annotations

import math
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

if __package__ == "web.backend.services":
    from . import llm_client
    from .input_limits import normalize_research_text
    from .search_synthesis import validate_candidate_public_texts
    from .secondary_tool_contracts import kb_candidate_evidence
    from ..logging_config import get_logger, new_incident_id
else:
    from services import llm_client
    from services.input_limits import normalize_research_text
    from services.search_synthesis import validate_candidate_public_texts
    from services.secondary_tool_contracts import kb_candidate_evidence
    from logging_config import get_logger, new_incident_id

logger = get_logger("structural.stress_test")

# Verdict enum — the only three values the API will ever emit.
VERDICTS = ("PASS", "FAIL", "CONDITIONAL")

# Hard input bounds. A claim is one sentence-ish; anything past this is abuse.
CLAIM_MIN_LEN = 4
CLAIM_MAX_LEN = 600

# Cap how many correspondences we keep — a runaway LLM could emit dozens.
MAX_CORRESPONDENCES = 12

# Candidate search — how many KB rows to pull, and the internal retrieval floor
# below which a hit is too weak even to display as a candidate reference.
PRECEDENT_TOP_K = 6
PRECEDENT_MIN_RELEVANCE = 0.55

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


# Candidate-reference note — second LLM call. It may explain what to compare
# and what would falsify the reference, but cannot promote retrieval to proof.
_PRECEDENT_SYSTEM_PROMPT = """你是结构红队分析师。下面给你一个商业类比里\
【最薄弱的一环】，以及一个从知识库里检索到的候选参照记录。

这个记录来自其他领域（物理、生态、金融、社会系统等）。检索命中只说明它\
值得继续比较，不证明它与用户类比共享机制，也不代表方法可以直接迁移。

你的任务：说明这个候选记录为什么值得核查，并明确指出要验证哪个变量关系、\
什么观察会推翻这次参照。只把它写成待验证线索。

严格要求：
- 必须紧扣给你的候选记录，不要泛泛而谈、不要编造记录里没有的细节。
- 不得写成真实先例、证据、已经同构、确认适用或成功概率。
- 简洁，2-4 句，必须包含一个可证伪检查。

只输出 JSON：
{
  "candidate_note": "为什么值得核查，以及什么观察会推翻这次参照，2-4 句"
}"""


class _StrictStressCorrespondence(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    claim: str = Field(min_length=1, max_length=600)
    stress_result: str = Field(min_length=1, max_length=1_000)
    holds: bool

    @field_validator("claim", "stress_result", mode="before")
    @classmethod
    def normalize_text(cls, value: Any, info: Any) -> str:
        limit = 600 if info.field_name == "claim" else 1_000
        return normalize_research_text(
            value, max_chars=limit, allow_layout=False, field_name=info.field_name
        )


class _StrictStressResult(BaseModel):
    """Complete LLM payload accepted by the live execution path."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    source: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=400)
    structural_correspondences: list[_StrictStressCorrespondence] = Field(
        min_length=1, max_length=MAX_CORRESPONDENCES
    )
    weakest_link: str = Field(min_length=1, max_length=1_000)
    verdict: Literal["PASS", "FAIL", "CONDITIONAL"]
    verdict_reason: str = Field(min_length=1, max_length=1_200)

    @field_validator("source", "target", "weakest_link", "verdict_reason", mode="before")
    @classmethod
    def normalize_text(cls, value: Any, info: Any) -> str:
        limits = {
            "source": 400,
            "target": 400,
            "weakest_link": 1_000,
            "verdict_reason": 1_200,
        }
        return normalize_research_text(
            value,
            max_chars=limits[info.field_name],
            allow_layout=False,
            field_name=info.field_name,
        )


class _StrictCandidateNote(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    candidate_note: str = Field(min_length=1, max_length=600)

    @field_validator("candidate_note", mode="before")
    @classmethod
    def normalize_note(cls, value: Any) -> str:
        return normalize_research_text(
            value,
            max_chars=600,
            allow_layout=False,
            field_name="candidate_note",
        )


def build_precedent_query(weakest_link: Any, target: Any = None) -> Optional[str]:
    """Build a KB search query from the weakest-link description.

    The query is the structural description of the weakest link — we want
    SearchService to find phenomena that share that *structure*, not the
    surface business vocabulary. Returns None when there is no usable
    weakest-link text (e.g. the placeholder the LLM never filled in).
    """
    if not isinstance(weakest_link, str):
        return None
    stripped = weakest_link.strip()
    # The placeholder coerce_result emits when the LLM gave nothing.
    if not stripped or stripped.startswith("（"):
        return None
    parts = [stripped]
    if isinstance(target, str) and target.strip() and not target.strip().startswith("（"):
        parts.append(target.strip())
    return " ".join(parts)


def coerce_precedent(raw: Any, phenomenon: dict) -> Optional[dict]:
    """Coerce the precedent LLM output + the KB hit into the precedent shape.

    `phenomenon` is the trusted KB search result (id/name/domain/...).
    `raw` is the untrusted LLM JSON. Returns a clean precedent dict, or None
    when the LLM gave nothing usable — the caller then degrades precedent to
    null without failing the whole stress test.
    """
    if not isinstance(phenomenon, dict):
        return None
    pid = phenomenon.get("id")
    name = phenomenon.get("name")
    if not isinstance(pid, str) or not pid.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None

    failure = None
    if isinstance(raw, dict):
        fp = raw.get("failure_precedent")
        if isinstance(fp, str) and fp.strip():
            failure = fp.strip()
    if not failure:
        return None

    domain = phenomenon.get("domain")
    description = phenomenon.get("description")
    relevance = phenomenon.get("relevance")
    return {
        "phenomenon_id": pid.strip(),
        "phenomenon_name": name.strip(),
        "domain": domain.strip() if isinstance(domain, str) and domain.strip() else "（未知领域）",
        "description": description.strip() if isinstance(description, str) and description.strip() else "",
        "relevance": round(float(relevance), 4) if isinstance(relevance, (int, float)) else None,
        "failure_precedent": failure,
    }


def _pick_precedent_hit(results: Any) -> Optional[dict]:
    """Pick a well-formed candidate hit above the internal retrieval floor."""
    if not isinstance(results, list) or not results:
        return None
    usable = []
    for row in results:
        if not isinstance(row, dict):
            continue
        relevance = row.get("relevance")
        if (
            isinstance(relevance, bool)
            or not isinstance(relevance, (int, float))
            or not math.isfinite(float(relevance))
            or not PRECEDENT_MIN_RELEVANCE <= float(relevance) <= 1.0
            or not isinstance(row.get("id"), str)
            or not row["id"].strip()
            or not isinstance(row.get("name"), str)
            or not row["name"].strip()
        ):
            continue
        usable.append(row)
    if not usable:
        return None
    cross = [r for r in usable if r.get("cross_domain") is True]
    pool = cross if cross else usable
    return max(pool, key=lambda r: float(r["relevance"]))


async def enrich_with_precedent(result: dict, search_svc: Any) -> dict:
    """Legacy compatibility helper for the pre-v2 response contract.

    Uses the KB search engine to find a real phenomenon structurally
    isomorphic to the weakest link, then asks the LLM to explain how that
    real phenomenon broke. `precedent` is set to None on any failure
    (search unavailable, no hit, LLM failure) — the stress test still
    returns a full verdict. Never raises.
    """
    result.setdefault("precedent", None)
    if search_svc is None:
        return result

    query = build_precedent_query(result.get("weakest_link"), result.get("target"))
    if query is None:
        return result

    try:
        hits = search_svc.search(query, top_k=PRECEDENT_TOP_K)
    except Exception as exc:  # search must never break the stress test
        logger.warning(
            "structural.stress_precedent_search_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return result

    hit = _pick_precedent_hit(hits)
    if hit is None:
        logger.info("structural.stress_precedent_missing")
        return result

    user_prompt = (
        f"用户类比里最薄弱的一环：\n{result.get('weakest_link', '')}\n\n"
        f"知识库检索到的候选参照记录：\n"
        f"领域：{hit.get('domain', '')}\n"
        f"名称：{hit.get('name', '')}\n"
        f"描述：{hit.get('description', '')}"
    )
    try:
        raw = await llm_client.complete_json(
            system=_PRECEDENT_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.3,
            max_tokens=600,
        )
    except Exception as exc:
        logger.warning(
            "structural.stress_precedent_llm_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return result

    precedent = coerce_precedent(raw, hit)
    if precedent is None:
        logger.info("structural.stress_precedent_rejected")
        return result

    result["precedent"] = precedent
    return result


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
    # Common synonyms an LLM might drift into.
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
    # holds defaults to False — an unproven correspondence is not "holds".
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

    # If the LLM gave us neither correspondences nor a verdict, there is
    # nothing worth showing — treat as a failure.
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

    # When verdict is missing/illegal, fall back deterministically from the
    # correspondence results rather than emitting an invalid enum.
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
        # Real KB precedent backing the weakest link — filled in by
        # enrich_with_precedent(); stays None when no precedent is found.
        "precedent": None,
    }


def validate_screen_result(raw: Any) -> Optional[dict]:
    """Validate the complete model reply before any public text is exposed.

    Unlike the legacy ``coerce_result`` compatibility helper, this execution
    path does not guess missing fields, translate synonyms, or keep a partially
    valid payload. One malformed field rejects the whole screen.
    """
    try:
        parsed = _StrictStressResult.model_validate(raw)
        validate_candidate_public_texts(
            [
                parsed.weakest_link,
                parsed.verdict_reason,
                *(
                    text
                    for item in parsed.structural_correspondences
                    for text in (item.claim, item.stress_result)
                ),
            ]
        )
    except (ValidationError, ValueError, TypeError):
        return None

    outcome = {
        "PASS": "not_broken_in_screen",
        "FAIL": "breaks_in_screen",
        "CONDITIONAL": "condition_dependent",
    }[parsed.verdict]
    return {
        "screening_outcome": outcome,
        "screening_basis": "internal_ai_red_team",
        "source": parsed.source,
        "target": parsed.target,
        "structural_correspondences": [
            {
                "claim": item.claim,
                "screening_outcome": "not_broken" if item.holds else "breaks",
                "stress_result": item.stress_result,
            }
            for item in parsed.structural_correspondences
        ],
        "weakest_link": parsed.weakest_link,
        "rationale": parsed.verdict_reason,
        "candidate_reference": None,
    }


async def enrich_with_candidate_reference(result: dict, search_svc: Any) -> dict:
    """Bind one optional model note to an allowlisted KB retrieval candidate."""
    if search_svc is None:
        return result
    query = build_precedent_query(result.get("weakest_link"), result.get("target"))
    if query is None:
        return result
    try:
        hits = search_svc.search(query, top_k=PRECEDENT_TOP_K)
    except Exception as exc:
        logger.warning(
            "structural.stress_candidate_search_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return result
    hit = _pick_precedent_hit(hits)
    if hit is None:
        return result

    user_prompt = (
        f"用户类比里最薄弱的一环：\n{result.get('weakest_link', '')}\n\n"
        "知识库检索到的候选参照记录：\n"
        f"领域：{hit.get('domain', '')}\n"
        f"名称：{hit.get('name', '')}\n"
        f"描述：{hit.get('description', '')}"
    )
    try:
        raw = await llm_client.complete_json(
            system=_PRECEDENT_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=0.3,
            max_tokens=600,
        )
        note = _StrictCandidateNote.model_validate(raw).candidate_note
        validate_candidate_public_texts([note])
    except Exception as exc:
        logger.warning(
            "structural.stress_candidate_note_rejected",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return result

    pid = hit.get("id")
    name = hit.get("name")
    if not isinstance(pid, str) or not isinstance(name, str):
        return result
    reference = {
        "id": pid.strip(),
        "name": name.strip(),
        "domain": str(hit.get("domain") or "").strip()[:120],
        "description": str(hit.get("description") or "").strip()[:600],
        "retrieval_rank": 1,
        "candidate_note": note,
        "evidence": kb_candidate_evidence(
            hit,
            counterexample="候选参照需要验证变量定义、边界条件和失效触发是否一致。",
        ),
    }
    result["candidate_reference"] = reference
    return result


async def run_stress_test(claim: str, search_svc: Any = None) -> Optional[dict]:
    """Run the full stress test for one claim.

    When `search_svc` is provided, the weakest link may receive one KB
    candidate reference. That reference remains untested. Returns the strict
    public result dict, or None when the LLM response is unavailable/invalid.
    """
    user_prompt = f"请对下面这个类比/判断做结构压力测试：\n\n{claim}"
    raw = await llm_client.complete_json(
        system=_SYSTEM_PROMPT,
        user=user_prompt,
        temperature=0.3,  # low — we want consistent, critical reasoning
        max_tokens=2600,
    )
    if raw is None:
        logger.warning("structural.stress_test.payload_missing")
        return None
    validated = validate_screen_result(raw)
    if validated is None:
        logger.warning("structural.stress_test.payload_invalid")
        return None
    # Retrieval creates a candidate reference only. It is not a precedent or
    # source-backed validation and therefore remains at evidence level candidate.
    return await enrich_with_candidate_reference(validated, search_svc)


__all__ = [
    "VERDICTS",
    "CLAIM_MIN_LEN",
    "CLAIM_MAX_LEN",
    "PRECEDENT_TOP_K",
    "PRECEDENT_MIN_RELEVANCE",
    "validate_claim",
    "coerce_result",
    "validate_screen_result",
    "build_precedent_query",
    "coerce_precedent",
    "enrich_with_precedent",
    "enrich_with_candidate_reference",
    "run_stress_test",
]
