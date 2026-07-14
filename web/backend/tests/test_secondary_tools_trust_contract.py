"""Adversarial contract tests for the four secondary product journeys."""
from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError

from services import diagnose_service, method_search_service, stress_test_service
from services.secondary_tool_contracts import (
    CandidateReference,
    MethodApplyResponse,
    internal_screen_evidence,
    kb_candidate_evidence,
    secondary_scope_guard,
)
from services.struct_lint_service import build_reference_candidate, validate_lint_result


def _stress_raw() -> dict:
    return {
        "source": "受延迟反馈控制的系统",
        "target": "当前团队",
        "structural_correspondences": [
            {
                "claim": "反馈存在时滞",
                "stress_result": "时滞尚未测量，当前对应可能断裂。",
                "holds": False,
            }
        ],
        "weakest_link": "反馈时滞尚未测量",
        "verdict": "CONDITIONAL",
        "verdict_reason": "需要先测量反馈时滞和干预后的恢复轨迹。",
    }


def test_stress_live_validator_is_complete_and_candidate_only() -> None:
    result = stress_test_service.validate_screen_result(_stress_raw())
    assert result is not None
    assert result["screening_outcome"] == "condition_dependent"
    assert "verdict" not in result and "confidence" not in result
    assert result["structural_correspondences"][0]["screening_outcome"] == "breaks"


def test_secondary_scope_guard_closes_trivial_suffix_bypass() -> None:
    assert secondary_scope_guard("2 + 2 等于多少，请直接告诉我答案") == (
        True, "arithmetic"
    )
    assert secondary_scope_guard(
        "团队按 2 + 2 人拆组后，反馈延迟反而上升，请分析机制"
    ) == (False, "ok")
    assert secondary_scope_guard("法国首都是哪里，请直接告诉我答案") == (
        True, "trivia"
    )


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update(extra="poison"),
        lambda raw: raw.update(verdict="MAYBE"),
        lambda raw: raw["structural_correspondences"][0].update(holds="false"),
        lambda raw: raw["structural_correspondences"][0].pop("stress_result"),
        lambda raw: raw.update(verdict_reason="成功率为 90%"),
    ],
)
def test_stress_live_validator_rejects_partial_or_overclaim_payloads(mutation) -> None:
    raw = _stress_raw()
    mutation(raw)
    assert stress_test_service.validate_screen_result(raw) is None


def _diagnosis_raw() -> dict:
    return {
        "primary_state": {"state_id": "hysteresis_trap"},
        "secondary_state": {"state_id": "cascade_fragility"},
        "reasoning": "流程改变后旧的协作模式仍然延续。",
        "evolution": "若反馈条件不变，旧模式可能继续维持。",
        "signals_to_watch": ["改流程后决策时长是否连续两周下降"],
        "recommendations": ["先记录干预前后的决策时长基线。"],
    }


def test_diagnosis_drops_model_self_confidence_from_live_contract() -> None:
    result = diagnose_service.validate_diagnosis_result(_diagnosis_raw())
    assert result is not None
    assert set(result["primary_state"]) == {
        "state_id", "name", "definition", "typical_signal"
    }
    assert "confidence" not in result["primary_state"]


def test_diagnosis_rejects_confidence_extra_and_duplicate_state() -> None:
    with_confidence = _diagnosis_raw()
    with_confidence["primary_state"]["confidence"] = 0.9
    assert diagnose_service.validate_diagnosis_result(with_confidence) is None
    duplicate = _diagnosis_raw()
    duplicate["secondary_state"] = {"state_id": "hysteresis_trap"}
    assert diagnose_service.validate_diagnosis_result(duplicate) is None


def test_method_notes_fail_as_a_unit_on_unknown_id_or_overclaim() -> None:
    assert method_search_service._validate_notes_strict(
        {"notes": {"kb-1": "值得核查边界条件。"}}, {"kb-1"}
    ) == {"kb-1": "值得核查边界条件。"}
    assert method_search_service._validate_notes_strict(
        {"notes": {"kb-1": "待核查。", "invented": "伪造"}}, {"kb-1"}
    ) == {}
    assert method_search_service._validate_notes_strict(
        {"notes": {"kb-1": "置信度为 90%，可以直接套用。"}}, {"kb-1"}
    ) == {}


def test_method_candidates_publish_rank_not_score_or_applicability() -> None:
    candidates = method_search_service.rank_candidates(
        [{
            "id": "kb-1", "name": "库存振荡", "domain": "供应链",
            "type_id": "delay", "description": "延迟反馈造成过冲",
            "relevance": 0.91, "score": 0.88,
        }],
        {"kb-1": "值得核查时滞和观测量定义。"},
        8,
    )
    assert candidates[0]["retrieval_rank"] == 1
    assert "score" not in candidates[0] and "relevance" not in candidates[0]
    assert "apply_note" not in candidates[0]
    assert candidates[0]["evidence"]["evidence_level"] == "candidate"


def _lint_raw() -> dict:
    return {
        "summary": "优先核查投入和结果之间的线性假设。",
        "claims": [{
            "quote": "预算翻倍会让增长线性放大",
            "claim_type": "causal_judgment",
            "structure": "投入与结果被假设为线性关系。",
            "failure_mode": "边际回报可能递减。",
            "risk_level": "high",
            "suggestion": "先做分段增量测试并记录响应曲线。",
        }],
    }


def test_lint_claim_is_bound_to_verbatim_input_and_uses_review_priority() -> None:
    result = validate_lint_result(
        _lint_raw(), "我们的计划假设预算翻倍会让增长线性放大。"
    )
    assert result is not None
    claim = result["claims"][0]
    assert claim["review_priority"] == "high"
    assert "risk_level" not in claim and claim["claim_id"].startswith("lint-")
    assert claim["evidence"]["evidence_level"] == "candidate"


def test_lint_rejects_invented_quote_partial_claim_and_extra_field() -> None:
    assert validate_lint_result(_lint_raw(), "文档里没有那句话。") is None
    partial = _lint_raw()
    partial["claims"][0].pop("suggestion")
    assert validate_lint_result(partial, "预算翻倍会让增长线性放大") is None
    extra = _lint_raw()
    extra["claims"][0]["confidence"] = 0.95
    assert validate_lint_result(extra, "预算翻倍会让增长线性放大") is None


def test_candidate_reference_binds_id_label_and_candidate_envelope() -> None:
    raw = {
        "id": "kb-1", "name": "库存振荡", "domain": "供应链",
        "description": "延迟反馈造成过冲", "relevance": 0.78,
    }
    candidate = build_reference_candidate(raw)
    assert candidate is not None
    assert CandidateReference.model_validate(candidate).evidence.evidence_level == "candidate"
    poisoned = copy.deepcopy(candidate)
    poisoned["evidence"]["candidate"]["label"] = "另一个记录"
    with pytest.raises(ValidationError):
        CandidateReference.model_validate(poisoned)


def test_secondary_envelopes_can_never_claim_promoted_evidence() -> None:
    screen = internal_screen_evidence(kind="screen", label="候选")
    retrieval = kb_candidate_evidence({"name": "候选", "relevance": 0.9})
    assert screen["evidence_level"] == retrieval["evidence_level"] == "candidate"
    assert screen["candidate"]["score"] is None
    assert retrieval["candidate"]["score"] is None
    assert screen["result"]["verdict"] == "INCONCLUSIVE"
    assert retrieval["result"]["verdict"] == "NOT_TESTED"


def test_secondary_envelope_rejects_cross_field_provenance_poisoning() -> None:
    poisoned = internal_screen_evidence(kind="screen", label="候选")
    poisoned["source"].update({
        "status": "recorded", "kind": "internal_kb",
        "label": "Structural KB record",
    })
    with pytest.raises(ValidationError):
        CandidateReference.model_validate({
            "id": "kb-1", "name": "候选", "domain": "", "description": "",
            "retrieval_rank": 1, "candidate_note": None, "evidence": poisoned,
        })


def test_method_response_rejects_old_score_fields() -> None:
    payload = {
        "contract_version": "secondary-tools-v2",
        "request_id": "method-1234567890",
        "method": "用局部反馈迭代寻找较优方案",
        "signature": "局部反馈迭代",
        "signature_origin": "input_fallback",
        "keywords": [],
        "count": 0,
        "candidates": [],
        "evidence": internal_screen_evidence(
            kind="method_transfer_candidate_search",
            label="用局部反馈迭代寻找较优方案",
        ),
        "score": 0.99,
    }
    with pytest.raises(ValidationError):
        MethodApplyResponse.model_validate(payload)


@pytest.mark.parametrize("relevance", [True, float("nan"), float("inf"), 1.1])
def test_stress_candidate_picker_rejects_non_numeric_or_unbounded_scores(relevance) -> None:
    assert stress_test_service._pick_precedent_hit([{
        "id": "kb-1", "name": "候选", "relevance": relevance,
    }]) is None
