"""Structural diagnosis service (Session #18, feature F).

The product takes a free-text description of an organisation / company /
team / project situation and tells it which *structural state* it is in —
e.g. "damped convergence", "hysteresis trap", "cascade fragility",
"self-organized criticality". It does NOT predict stock prices; it gives
a structural diagnosis: which state, why, how it will evolve untouched,
which signal to watch, and 1-2 structural recommendations.

The set of structural states is a fixed whitelist defined HERE in code.
The LLM may only PICK from it — it can never invent a state. Every live field
is validated strictly before reaching the API; model self-confidence is not
part of the public contract.

After the model picks a primary state, an optional KB search can attach one
named candidate reference for comparison. Retrieval does not establish a
shared mechanism. Search is best-effort: when unavailable or empty the
diagnosis completes without a candidate reference.

LLM access goes through the generic `llm_client` wrapper. When no API key
is configured `complete_json` returns None — callers surface a clean 503.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

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

logger = get_logger("structural.diagnose")

# Hard input bounds. A situation description is a paragraph-ish; anything
# past this is abuse / accidental paste of a whole document.
SITUATION_MIN_LEN = 12
SITUATION_MAX_LEN = 1500

# Cap list-valued LLM fields — a runaway model could emit dozens.
MAX_SIGNALS = 6
MAX_RECOMMENDATIONS = 5

# --------------------------------------------------------------------------
# Structural-state whitelist.
#
# 8 states. Each aligns loosely with a universality class the KB already
# names (universality-classes.json), but is phrased for an org/team reader.
# Per-state fields:
#   - class_ref       related universality class_id (traceability only).
#   - class_hub       the class's representative cross-domain phenomenon
#                     name (from universality-classes.json hub_name). Used
#                     as a fallback reference when KB search is unavailable.
#   - structure_query a domain-neutral structural phrasing of the state,
#                     used to query the KB for a same-structure real case.
# --------------------------------------------------------------------------
STRUCTURAL_STATES: dict[str, dict[str, str]] = {
    "damped_convergence": {
        "name": "阻尼收敛（稳定）",
        "definition": "受到扰动后会自己回到平衡，波动逐渐变小，结构健康。",
        "typical_signal": "出问题后指标能自行回落，不需要持续救火。",
        "class_ref": "",
        "class_hub": "",
        "structure_query": "负反馈调节 扰动后自我回到平衡 波动衰减 稳定不动点",
    },
    "positive_feedback_runaway": {
        "name": "正反馈失控",
        "definition": "某个变量自我放大、越走越偏，没有刹车机制，会持续脱离平衡。",
        "typical_signal": "同一类问题每次都比上次更严重，干预一次顶不了多久。",
        "class_ref": "motter_lai_network_cascade",
        "class_hub": "建筑结构的渐进倒塌",
        "structure_query": "正反馈自我放大 没有抑制机制 指数级偏离 失控发散",
    },
    "hysteresis_trap": {
        "name": "滞回陷阱（改了因还卡在旧果）",
        "definition": "导致问题的原因已经去掉，但系统因为路径依赖仍停在旧状态，不会自己回弹。",
        "typical_signal": "明明已经调整了策略/换了人，旧的局面却纹丝不动。",
        "class_ref": "hysteresis_preisach",
        "class_hub": "热固性树脂凝胶点渗流相变",
        "structure_query": "滞回 路径依赖 去掉原因后系统不回弹 多稳态记忆效应",
    },
    "cascade_fragility": {
        "name": "级联脆弱（一处断全线塌）",
        "definition": "关键节点高度耦合，任意一处失效会沿链条扩散，局部故障变成全局崩溃。",
        "typical_signal": "组织高度依赖某个人/某个系统/某个客户，缺了就全停。",
        "class_ref": "motter_lai_network_cascade",
        "class_hub": "建筑结构的渐进倒塌",
        "structure_query": "级联失效 节点高度耦合 局部故障沿链条扩散 全局崩溃",
    },
    "self_organized_criticality": {
        "name": "自组织临界（看似平稳实则临界）",
        "definition": "表面运转正常，但内部张力持续累积到临界点，随时可能被一件小事引爆。",
        "typical_signal": "长期『还行』，但谁都知道某根弦绷得很紧，就差一根稻草。",
        "class_ref": "soc_threshold_cascade",
        "class_hub": "清算级联的链上流动性危机",
        "structure_query": "自组织临界 阈值压力持续累积 小扰动触发幂律级联 沙堆",
    },
    "limit_cycle_oscillation": {
        "name": "极限环震荡（周期性反复）",
        "definition": "系统在两种状态之间周期性来回，既不崩溃也不稳定，反复消耗精力。",
        "typical_signal": "扩张—收缩、放权—收权、激进—保守，每隔一段就轮回一次。",
        "class_ref": "",
        "class_hub": "",
        "structure_query": "极限环 周期性震荡 两种状态之间反复来回 捕食者猎物循环",
    },
    "regime_shift_tipping": {
        "name": "临界突变前夜（Fold 分岔）",
        "definition": "正逼近一个不可逆的转折点，越过之后会突然跳到完全不同的状态，且难以退回。",
        "typical_signal": "韧性变差、恢复变慢、波动变大——临界放缓的典型先兆。",
        "class_ref": "scheffer_fold_bifurcation",
        "class_hub": "蛋白质相分离的临界浓度阈值",
        "structure_query": "临界相变 Fold 分岔 不可逆突变 临界放缓 状态突跳",
    },
    "self_fulfilling_run": {
        "name": "自我实现挤兑（信心崩塌）",
        "definition": "结果取决于大家的预期：一旦多数人开始撤，撤离本身就让结局成真。",
        "typical_signal": "核心人员/客户/投资人开始观望，越观望越想走。",
        "class_ref": "diamond_dybvig_self_fulfilling",
        "class_hub": "银行挤兑",
        "structure_query": "自我实现预期 信心崩塌 多重均衡 挤兑 协调失败博弈",
    },
}

# Convenience: the set of legal state ids.
STATE_IDS = frozenset(STRUCTURAL_STATES.keys())


def _states_for_prompt() -> str:
    """Render the whitelist as a numbered list for the system prompt."""
    lines = []
    for sid, meta in STRUCTURAL_STATES.items():
        lines.append(
            f"- {sid}｜{meta['name']}：{meta['definition']}"
            f"（典型信号：{meta['typical_signal']}）"
        )
    return "\n".join(lines)


_SYSTEM_PROMPT = """你是一个冷静、专业的组织结构诊断师。

用户会给你一段对某个组织 / 公司 / 团队 / 项目处境的自然语言描述。你的\
任务【不是预测业绩、不是给鸡汤】，而是对它现在的结构状态做一次诊断：\
判断它处于下面哪一种结构状态，为什么，不干预会怎样演化，该盯哪个信号。

你只能从下面这份固定的结构状态清单里选，禁止自创状态：

{states}

工作步骤：
1. 通读用户描述，找出其中真实存在的结构特征（反馈回路、耦合方式、\
路径依赖、临界迹象、震荡周期等），不要被表面情绪带跑。
2. 判定它最接近清单里的哪一种状态（primary），并选一个次可能状态\
（secondary，必须与 primary 不同）。
3. 给出判定理由：基于描述里的哪些结构特征得出这个判断，要具体引用\
描述中的事实，不要套话。
4. 给出演化预测：如果不做结构性干预，这个状态接下来大概会怎么走。
5. 指出该盯的关键信号 / 拐点：必须是【具体、可观测、可量化】的指标或\
拐点，结合用户描述里的真实情况。每条信号要写清楚「盯什么指标 + 朝哪个\
方向变 + 大致到什么程度就该警觉」。禁止写「关注团队氛围」「留意风险」\
这类无法落地的空泛话。
6. 给 1-2 条结构性建议：针对的是结构本身（反馈回路、耦合、路径依赖），\
不是头痛医头的战术动作。

严格要求：
- primary_state.state_id 和 secondary_state.state_id 必须是上面清单里\
出现过的英文 id，原样照抄，不得改写、翻译或自创。
- 这只是基于用户描述的候选结构状态，不输出概率、置信度或确定性结论。
- 诊断要基于结构，不要基于行业八卦或情绪。
- signals_to_watch 的每条都必须可量化 / 可观测，结合用户处境里的具体\
对象（某个指标、某段流程、某类人员），不要泛泛而谈。

只输出 JSON，结构如下：
{{
  "primary_state": {{ "state_id": "清单里的英文 id" }},
  "secondary_state": {{ "state_id": "清单里另一个英文 id" }},
  "reasoning": "判定理由，基于描述里的结构特征，3-5 句",
  "evolution": "不干预会如何演化，2-4 句",
  "signals_to_watch": ["具体可量化的信号，含指标+方向+阈值感，每条一句"],
  "recommendations": ["结构性建议，每条一句"]
}}"""


class _StrictStateChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    state_id: str = Field(min_length=1, max_length=64)


class _StrictDiagnosisResult(BaseModel):
    """Complete model payload accepted by the live diagnosis path."""

    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    primary_state: _StrictStateChoice
    secondary_state: _StrictStateChoice
    reasoning: str = Field(min_length=1, max_length=1_500)
    evolution: str = Field(min_length=1, max_length=1_200)
    signals_to_watch: list[str] = Field(min_length=1, max_length=MAX_SIGNALS)
    recommendations: list[str] = Field(min_length=1, max_length=MAX_RECOMMENDATIONS)

    @field_validator("reasoning", "evolution", mode="before")
    @classmethod
    def normalize_narrative(cls, value: Any, info: Any) -> str:
        limit = 1_500 if info.field_name == "reasoning" else 1_200
        return normalize_research_text(
            value, max_chars=limit, allow_layout=False, field_name=info.field_name
        )

    @field_validator("signals_to_watch", "recommendations", mode="before")
    @classmethod
    def normalize_lists(cls, value: Any, info: Any) -> Any:
        if not isinstance(value, list):
            return value
        limit = 500 if info.field_name == "signals_to_watch" else 800
        return [
            normalize_research_text(
                item,
                max_chars=limit,
                allow_layout=False,
                field_name=info.field_name,
            )
            for item in value
        ]

    @model_validator(mode="after")
    def state_choices_are_valid(self) -> "_StrictDiagnosisResult":
        if self.primary_state.state_id not in STATE_IDS:
            raise ValueError("primary state is not allowlisted")
        if (
            self.secondary_state.state_id not in STATE_IDS
            or self.secondary_state.state_id == self.primary_state.state_id
        ):
            raise ValueError("secondary state is invalid")
        return self


class _StrictReferenceNote(BaseModel):
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


def validate_situation(text: Any) -> str:
    """Validate + normalise the incoming situation description.

    Raises ValueError on empty / non-str / too-short / too-long input.
    Returns the stripped text on success.
    """
    if not isinstance(text, str):
        raise ValueError("处境描述必须是文本")
    stripped = text.strip()
    if len(stripped) < SITUATION_MIN_LEN:
        raise ValueError("描述太短，请把组织/团队的处境说得更完整一些")
    if len(stripped) > SITUATION_MAX_LEN:
        raise ValueError(f"描述过长（上限 {SITUATION_MAX_LEN} 字）")
    return stripped


def _coerce_state_id(raw: Any) -> Optional[str]:
    """Normalise an LLM-supplied state id to the whitelist, or None.

    Accepts the id directly, case-insensitively, and also tolerates the
    LLM returning the Chinese display name instead of the id. Returns None
    when nothing in the whitelist matches — the caller decides to degrade.
    """
    if not isinstance(raw, str):
        return None
    norm = raw.strip()
    if not norm:
        return None
    # Direct id match (case-insensitive).
    low = norm.lower()
    for sid in STATE_IDS:
        if sid.lower() == low:
            return sid
    # The LLM sometimes returns the Chinese name — map it back.
    for sid, meta in STRUCTURAL_STATES.items():
        if meta["name"] == norm:
            return sid
    return None


def _coerce_confidence(raw: Any) -> float:
    """Clamp an LLM-supplied confidence into [0, 1].

    Non-numeric / missing → 0.5 (a neutral default). Values given as a
    percentage (e.g. 80) are scaled down. Always returns a legal float.
    """
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 0.5
    if val != val:  # NaN
        return 0.5
    if val > 1.0:
        # Likely a percentage like 80 → 0.8.
        val = val / 100.0
    if val < 0.0:
        return 0.0
    if val > 1.0:
        return 1.0
    return round(val, 2)


def _state_block(sid: str, *, with_confidence: Optional[float] = None) -> dict:
    """Build the API-facing state block for a whitelisted state id."""
    meta = STRUCTURAL_STATES[sid]
    block = {
        "state_id": sid,
        "name": meta["name"],
        "definition": meta["definition"],
        "typical_signal": meta["typical_signal"],
    }
    if with_confidence is not None:
        block["confidence"] = with_confidence
    return block


def _clean_str_list(raw: Any, *, limit: int) -> list[str]:
    """Coerce an LLM list field into a clean, capped list of strings."""
    out: list[str] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        if len(out) >= limit:
            break
    return out


def coerce_result(raw: Any) -> Optional[dict]:
    """Validate + coerce the raw LLM JSON into the API response shape.

    Returns a clean dict, or None when the payload has no recoverable
    primary state (not a dict, or no legal state_id). The caller treats
    None as a degraded LLM failure. Guardrails:
      - primary state_id MUST be in the whitelist, else None;
      - secondary is dropped if illegal or equal to primary;
      - confidence is clamped to [0, 1];
      - reasoning / evolution fall back to a placeholder if missing;
      - signals / recommendations are capped and string-filtered.
    """
    if not isinstance(raw, dict):
        return None

    primary_in = raw.get("primary_state")
    if not isinstance(primary_in, dict):
        return None
    primary_id = _coerce_state_id(primary_in.get("state_id"))
    if primary_id is None:
        # No legal primary state — nothing trustworthy to show.
        return None
    confidence = _coerce_confidence(primary_in.get("confidence"))

    # Secondary is optional. Drop it when illegal or identical to primary.
    secondary_block: Optional[dict] = None
    secondary_in = raw.get("secondary_state")
    if isinstance(secondary_in, dict):
        secondary_id = _coerce_state_id(secondary_in.get("state_id"))
        if secondary_id is not None and secondary_id != primary_id:
            secondary_block = _state_block(secondary_id)

    reasoning = raw.get("reasoning")
    reasoning_str = (
        reasoning.strip()
        if isinstance(reasoning, str) and reasoning.strip()
        else "（模型未给出判定理由）"
    )

    evolution = raw.get("evolution")
    evolution_str = (
        evolution.strip()
        if isinstance(evolution, str) and evolution.strip()
        else "（模型未给出演化预测）"
    )

    signals = _clean_str_list(raw.get("signals_to_watch"), limit=MAX_SIGNALS)
    recommendations = _clean_str_list(
        raw.get("recommendations"), limit=MAX_RECOMMENDATIONS
    )

    return {
        "primary_state": _state_block(primary_id, with_confidence=confidence),
        "secondary_state": secondary_block,
        "reasoning": reasoning_str,
        "evolution": evolution_str,
        "signals_to_watch": signals,
        "recommendations": recommendations,
    }


def validate_diagnosis_result(raw: Any) -> Optional[dict]:
    """Fail closed on any partial, extra, or semantically unsafe model field."""
    try:
        parsed = _StrictDiagnosisResult.model_validate(raw)
        # Quantified watch signals may legitimately contain percentages. The
        # semantic candidate guard is applied to explanatory model prose, while
        # the signal strings still receive strict Unicode/length validation.
        validate_candidate_public_texts(
            [parsed.reasoning, parsed.evolution, *parsed.recommendations]
        )
    except (ValidationError, ValueError, TypeError):
        return None
    return {
        "assessment_kind": "structural_state_hypothesis",
        "primary_state": _state_block(parsed.primary_state.state_id),
        "secondary_state": _state_block(parsed.secondary_state.state_id),
        "reasoning": parsed.reasoning,
        "evolution": parsed.evolution,
        "signals_to_watch": parsed.signals_to_watch,
        "recommendations": parsed.recommendations,
        "candidate_reference": None,
    }


# --------------------------------------------------------------------------
# Reference case — anchor the diagnosis to a real KB phenomenon.
#
# The product's moat is the KB (4443 cross-domain phenomena). A diagnosis
# that just says "you are cascade-fragile" is an LLM opinion; a diagnosis
# that adds "your structure matches a real, named phenomenon" is evidence.
# --------------------------------------------------------------------------

# How many KB hits to ask SearchService for — we only keep the best one
# but a small pool lets us prefer a cross-domain hit over a same-domain one.
_REFERENCE_TOP_K = 6

# A reference is only worth showing above this unified relevance. Below it
# the "same structure" claim is too weak to stand behind.
_REFERENCE_MIN_RELEVANCE = 0.55

# Words pulled out of the user's situation that would just re-surface the
# user's own domain — we want a STRUCTURAL match, not a topical one. Kept
# tiny on purpose: the structure_query already dominates the query.
_SITUATION_QUERY_CHARS = 120


def build_reference_query(state_id: str, situation: str) -> str:
    """Construct the KB search query for a state's reference case.

    The structural phrasing of the state leads (so the search keys on
    STRUCTURE, not on the user's industry), with a short slice of the
    user's own words appended for mild grounding. Returns "" for an
    unknown state id so the caller can skip the lookup.
    """
    meta = STRUCTURAL_STATES.get(state_id)
    if meta is None:
        return ""
    structure = meta.get("structure_query", "").strip()
    tail = (situation or "").strip().replace("\n", " ")[:_SITUATION_QUERY_CHARS]
    if structure and tail:
        return f"{structure} {tail}"
    return structure or tail


def _coerce_reference_case(hit: Any) -> Optional[dict]:
    """Coerce one raw SearchService hit into the API reference_case shape.

    Untrusted-input discipline: the search layer is in-house, but we still
    validate types and require a usable id+name before surfacing a "real
    case" claim. Returns None when the hit is unusable.
    """
    if not isinstance(hit, dict):
        return None
    pid = hit.get("id")
    name = hit.get("name")
    if not isinstance(pid, str) or not pid.strip():
        return None
    if not isinstance(name, str) or not name.strip():
        return None
    relevance = hit.get("relevance")
    try:
        rel = float(relevance)
    except (TypeError, ValueError):
        rel = 0.0
    if rel != rel:  # NaN
        rel = 0.0
    rel = max(0.0, min(1.0, rel))
    domain = hit.get("domain")
    desc = hit.get("description")
    return {
        "id": pid.strip(),
        "name": name.strip(),
        "domain": domain.strip() if isinstance(domain, str) else "",
        "description": desc.strip() if isinstance(desc, str) else "",
        "relevance": round(rel, 4),
        "source": "kb_search",
    }


def _fallback_reference_case(state_id: str) -> Optional[dict]:
    """Fallback reference when KB search is unavailable / returns nothing.

    Uses the representative phenomenon (hub_name) of the universality
    class this state is aligned with. Has no KB id — the frontend renders
    it without a deep link. Returns None when the state has no class hub.
    """
    meta = STRUCTURAL_STATES.get(state_id)
    if meta is None:
        return None
    hub = meta.get("class_hub", "").strip()
    if not hub:
        return None
    return {
        "id": "",
        "name": hub,
        "domain": "",
        "description": "",
        "relevance": None,
        "source": "class_hub",
    }


def fetch_reference_case(
    state_id: str, situation: str, search_svc: Any
) -> Optional[dict]:
    """Find a real KB phenomenon that shares the diagnosed structure.

    Best-effort: searches the KB via SearchService, prefers a cross-domain
    hit that clears the relevance bar, and falls back to the state's
    universality-class hub when search is unavailable or finds nothing.
    Never raises — any failure degrades to the fallback or to None.
    """
    if state_id not in STATE_IDS:
        return None

    hits: list = []
    if search_svc is not None:
        query = build_reference_query(state_id, situation)
        if query:
            try:
                raw_hits = search_svc.search(query, top_k=_REFERENCE_TOP_K)
                if isinstance(raw_hits, list):
                    hits = raw_hits
            except Exception as exc:  # noqa: BLE001 — search must never break F
                logger.warning(
                    "structural.diagnose_reference_search_failed",
                    error_type=type(exc).__name__,
                    incident_id=new_incident_id(),
                )

    # Coerce + relevance-gate, keeping order (search already ranked them).
    candidates: list[dict] = []
    for hit in hits:
        case = _coerce_reference_case(hit)
        if case is not None and case["relevance"] >= _REFERENCE_MIN_RELEVANCE:
            candidates.append((case, bool(hit.get("cross_domain"))))

    if candidates:
        # Prefer a cross-domain hit (the product's whole point), else the
        # top-ranked one.
        for case, is_cross in candidates:
            if is_cross:
                return case
        return candidates[0][0]

    # No usable search hit — fall back to the class hub.
    return _fallback_reference_case(state_id)


# Prompt for the optional second LLM call that explains how the real
# reference case evolved — strictly grounded on the phenomenon we pass in.
_REFERENCE_NOTE_PROMPT = """你是一个结构分析师。下面给你一个真实的跨领域\
现象，以及一位用户当前组织/团队所处的结构状态。

真实现象：『{domain}』领域的「{name}」
现象描述：{description}

用户当前的结构状态：{state_name}——{state_def}

请用 1-2 句话说明：这个真实现象在【同一种结构】下，是怎样演化的（怎么\
失稳、怎么崩、或怎么稳住的）。要求：
- 只基于上面给的现象描述，不要编造现象里没有的细节；
- 讲的是这个真实现象本身的演化，不是给用户的建议；
- 平实、具体，不堆术语。

只输出 JSON：{{"note": "1-2 句话"}}"""


async def _build_reference_note(
    case: dict, state_id: str
) -> Optional[str]:
    """Optionally enrich a KB reference case with a one-line evolution note.

    Only attempted for real KB hits (source == kb_search) that carry a
    description — there is nothing real to ground on otherwise. Best-effort:
    any LLM failure simply yields None and the case ships without a note.
    """
    if case.get("source") != "kb_search":
        return None
    description = (case.get("description") or "").strip()
    if not description:
        return None
    meta = STRUCTURAL_STATES.get(state_id)
    if meta is None:
        return None
    prompt = _REFERENCE_NOTE_PROMPT.format(
        domain=case.get("domain") or "未知",
        name=case.get("name", ""),
        description=description[:600],
        state_name=meta["name"],
        state_def=meta["definition"],
    )
    try:
        raw = await llm_client.complete_json(
            system="你只输出严格的 JSON。",
            user=prompt,
            temperature=0.3,
            max_tokens=400,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "structural.diagnose_reference_note_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return None
    if not isinstance(raw, dict):
        return None
    note = raw.get("note")
    if isinstance(note, str) and note.strip():
        return note.strip()
    return None


_CANDIDATE_REFERENCE_PROMPT = """你会看到一个组织状态候选和一条内部知识库检索记录。
检索记录只是待核查参照，不是现实证据，也不证明两个对象同构。

请用 1-2 句话说明：为什么这条记录值得比较，以及用户需要观察哪个变量关系来
推翻或保留这个候选参照。不得写概率、置信度、真实先例、已经同构或直接适用。
只输出 JSON：{"candidate_note": "待核查说明"}"""


async def _build_candidate_note(case: dict, state_id: str) -> Optional[str]:
    """Return a cautious annotation bound to one retrieved KB candidate."""
    description = case.get("description")
    meta = STRUCTURAL_STATES.get(state_id)
    if (
        case.get("source") != "kb_search"
        or not isinstance(description, str)
        or not description.strip()
        or meta is None
    ):
        return None
    user_prompt = (
        f"候选结构状态：{meta['name']}——{meta['definition']}\n"
        f"知识库候选：{case.get('name', '')}\n"
        f"领域：{case.get('domain', '')}\n"
        f"记录描述：{description[:600]}"
    )
    try:
        raw = await llm_client.complete_json(
            system=_CANDIDATE_REFERENCE_PROMPT,
            user=user_prompt,
            temperature=0.3,
            max_tokens=400,
        )
        note = _StrictReferenceNote.model_validate(raw).candidate_note
        validate_candidate_public_texts([note])
        return note
    except Exception as exc:  # optional annotation must never break diagnosis
        logger.warning(
            "structural.diagnose_candidate_note_rejected",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return None


async def build_candidate_reference(case: Any, state_id: str) -> Optional[dict]:
    """Shape one search hit as a candidate-only, source-bound reference."""
    if not isinstance(case, dict) or case.get("source") != "kb_search":
        return None
    pid = case.get("id")
    name = case.get("name")
    if not isinstance(pid, str) or not pid.strip() or not isinstance(name, str) or not name.strip():
        return None
    domain = case.get("domain") if isinstance(case.get("domain"), str) else ""
    description = (
        case.get("description") if isinstance(case.get("description"), str) else ""
    )
    note = await _build_candidate_note(case, state_id)
    return {
        "id": pid.strip(),
        "name": name.strip()[:200],
        "domain": domain.strip()[:120],
        "description": description.strip()[:600],
        "retrieval_rank": 1,
        "candidate_note": note,
        "evidence": kb_candidate_evidence(
            case,
            counterexample="需要核查状态变量、时间尺度和干预边界是否一致。",
        ),
    }


async def run_diagnosis(
    situation: str, search_svc: Any = None
) -> Optional[dict]:
    """Run the full structural diagnosis for one situation description.

    After the LLM picks a structural state we anchor the result to a real
    KB phenomenon of the same structure (reference_case). The reference
    lookup is best-effort: when `search_svc` is None / unavailable or
    finds nothing the diagnosis still completes with reference_case set to
    a class-hub fallback or None.

    Returns the coerced result dict, or None when the LLM is unavailable /
    failed / returned unrecoverable garbage. Never raises on LLM problems.
    """
    system = _SYSTEM_PROMPT.format(states=_states_for_prompt())
    user_prompt = f"请对下面这个组织/团队的处境做结构状态诊断：\n\n{situation}"
    raw = await llm_client.complete_json(
        system=system,
        user=user_prompt,
        temperature=0.3,  # low — we want consistent, structural reasoning
        max_tokens=2400,
    )
    if raw is None:
        logger.warning("structural.diagnose_payload_missing")
        return None
    validated = validate_diagnosis_result(raw)
    if validated is None:
        logger.warning("structural.diagnose_payload_rejected")
        return None

    # Anchor to a real KB phenomenon of the same structure. All failures
    # here degrade gracefully — the core diagnosis is already done.
    primary_id = validated["primary_state"]["state_id"]
    reference_case: Optional[dict] = None
    try:
        reference_case = fetch_reference_case(primary_id, situation, search_svc)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "structural.diagnose_reference_lookup_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        reference_case = None

    validated["candidate_reference"] = await build_candidate_reference(
        reference_case, primary_id
    )
    return validated


def list_states() -> list[dict]:
    """Return the public structural-state catalogue (for the frontend)."""
    return [
        {
            "state_id": sid,
            "name": meta["name"],
            "definition": meta["definition"],
            "typical_signal": meta["typical_signal"],
        }
        for sid, meta in STRUCTURAL_STATES.items()
    ]


__all__ = [
    "STRUCTURAL_STATES",
    "STATE_IDS",
    "SITUATION_MIN_LEN",
    "SITUATION_MAX_LEN",
    "validate_situation",
    "coerce_result",
    "validate_diagnosis_result",
    "build_reference_query",
    "fetch_reference_case",
    "build_candidate_reference",
    "run_diagnosis",
    "list_states",
]
