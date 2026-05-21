"""Structural diagnosis service (Session ***REMOVED***18, feature F).

The product takes a free-text description of an organisation / company /
team / project situation and tells it which *structural state* it is in —
e.g. "damped convergence", "hysteresis trap", "cascade fragility",
"self-organized criticality". It does NOT predict stock prices; it gives
a structural diagnosis: which state, why, how it will evolve untouched,
which signal to watch, and 1-2 structural recommendations.

The set of structural states is a fixed whitelist defined HERE in code.
The LLM may only PICK from it — it can never invent a state. Every field
the LLM returns is treated as untrusted: schema, types, the state_id enum
and the confidence range are validated / coerced before reaching the API.

LLM access goes through the generic `llm_client` wrapper. When no API key
is configured `complete_json` returns None — callers surface a clean 503.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services import llm_client

logger = logging.getLogger("structural.diagnose")

***REMOVED*** Hard input bounds. A situation description is a paragraph-ish; anything
***REMOVED*** past this is abuse / accidental paste of a whole document.
SITUATION_MIN_LEN = 12
SITUATION_MAX_LEN = 1500

***REMOVED*** Cap list-valued LLM fields — a runaway model could emit dozens.
MAX_SIGNALS = 6
MAX_RECOMMENDATIONS = 5

***REMOVED*** --------------------------------------------------------------------------
***REMOVED*** Structural-state whitelist.
***REMOVED***
***REMOVED*** 8 states. Each aligns loosely with a universality class the KB already
***REMOVED*** names (universality-classes.json), but is phrased for an org/team reader.
***REMOVED*** `class_ref` records the related class_id purely for traceability — it is
***REMOVED*** NOT surfaced as a hard claim.
***REMOVED*** --------------------------------------------------------------------------
STRUCTURAL_STATES: dict[str, dict[str, str]] = {
    "damped_convergence": {
        "name": "阻尼收敛（稳定）",
        "definition": "受到扰动后会自己回到平衡，波动逐渐变小，结构健康。",
        "typical_signal": "出问题后指标能自行回落，不需要持续救火。",
        "class_ref": "",
    },
    "positive_feedback_runaway": {
        "name": "正反馈失控",
        "definition": "某个变量自我放大、越走越偏，没有刹车机制，会持续脱离平衡。",
        "typical_signal": "同一类问题每次都比上次更严重，干预一次顶不了多久。",
        "class_ref": "motter_lai_network_cascade",
    },
    "hysteresis_trap": {
        "name": "滞回陷阱（改了因还卡在旧果）",
        "definition": "导致问题的原因已经去掉，但系统因为路径依赖仍停在旧状态，不会自己回弹。",
        "typical_signal": "明明已经调整了策略/换了人，旧的局面却纹丝不动。",
        "class_ref": "hysteresis_preisach",
    },
    "cascade_fragility": {
        "name": "级联脆弱（一处断全线塌）",
        "definition": "关键节点高度耦合，任意一处失效会沿链条扩散，局部故障变成全局崩溃。",
        "typical_signal": "组织高度依赖某个人/某个系统/某个客户，缺了就全停。",
        "class_ref": "motter_lai_network_cascade",
    },
    "self_organized_criticality": {
        "name": "自组织临界（看似平稳实则临界）",
        "definition": "表面运转正常，但内部张力持续累积到临界点，随时可能被一件小事引爆。",
        "typical_signal": "长期『还行』，但谁都知道某根弦绷得很紧，就差一根稻草。",
        "class_ref": "soc_threshold_cascade",
    },
    "limit_cycle_oscillation": {
        "name": "极限环震荡（周期性反复）",
        "definition": "系统在两种状态之间周期性来回，既不崩溃也不稳定，反复消耗精力。",
        "typical_signal": "扩张—收缩、放权—收权、激进—保守，每隔一段就轮回一次。",
        "class_ref": "",
    },
    "regime_shift_tipping": {
        "name": "临界突变前夜（Fold 分岔）",
        "definition": "正逼近一个不可逆的转折点，越过之后会突然跳到完全不同的状态，且难以退回。",
        "typical_signal": "韧性变差、恢复变慢、波动变大——临界放缓的典型先兆。",
        "class_ref": "scheffer_fold_bifurcation",
    },
    "self_fulfilling_run": {
        "name": "自我实现挤兑（信心崩塌）",
        "definition": "结果取决于大家的预期：一旦多数人开始撤，撤离本身就让结局成真。",
        "typical_signal": "核心人员/客户/投资人开始观望，越观望越想走。",
        "class_ref": "diamond_dybvig_self_fulfilling",
    },
}

***REMOVED*** Convenience: the set of legal state ids.
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
5. 指出该盯的关键信号 / 拐点：哪些可观测的迹象能最早告诉用户状态在\
恶化或好转。
6. 给 1-2 条结构性建议：针对的是结构本身（反馈回路、耦合、路径依赖），\
不是头痛医头的战术动作。

严格要求：
- primary_state.state_id 和 secondary_state.state_id 必须是上面清单里\
出现过的英文 id，原样照抄，不得改写、翻译或自创。
- confidence 是 0 到 1 之间的小数，表示对 primary 判定的把握。
- 诊断要基于结构，不要基于行业八卦或情绪。

只输出 JSON，结构如下：
{{
  "primary_state": {{ "state_id": "清单里的英文 id", "confidence": 0.0 }},
  "secondary_state": {{ "state_id": "清单里另一个英文 id" }},
  "reasoning": "判定理由，基于描述里的结构特征，3-5 句",
  "evolution": "不干预会如何演化，2-4 句",
  "signals_to_watch": ["该盯的关键信号 / 拐点，每条一句"],
  "recommendations": ["结构性建议，每条一句"]
}}"""


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
    ***REMOVED*** Direct id match (case-insensitive).
    low = norm.lower()
    for sid in STATE_IDS:
        if sid.lower() == low:
            return sid
    ***REMOVED*** The LLM sometimes returns the Chinese name — map it back.
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
    if val != val:  ***REMOVED*** NaN
        return 0.5
    if val > 1.0:
        ***REMOVED*** Likely a percentage like 80 → 0.8.
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
        ***REMOVED*** No legal primary state — nothing trustworthy to show.
        return None
    confidence = _coerce_confidence(primary_in.get("confidence"))

    ***REMOVED*** Secondary is optional. Drop it when illegal or identical to primary.
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


async def run_diagnosis(situation: str) -> Optional[dict]:
    """Run the full structural diagnosis for one situation description.

    Returns the coerced result dict, or None when the LLM is unavailable /
    failed / returned unrecoverable garbage. Never raises on LLM problems.
    """
    system = _SYSTEM_PROMPT.format(states=_states_for_prompt())
    user_prompt = f"请对下面这个组织/团队的处境做结构状态诊断：\n\n{situation}"
    raw = await llm_client.complete_json(
        system=system,
        user=user_prompt,
        temperature=0.3,  ***REMOVED*** low — we want consistent, structural reasoning
        max_tokens=2400,
    )
    if raw is None:
        logger.warning("run_diagnosis: LLM returned None")
        return None
    coerced = coerce_result(raw)
    if coerced is None:
        logger.warning("run_diagnosis: LLM output failed schema coercion")
    return coerced


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
    "run_diagnosis",
    "list_states",
]
