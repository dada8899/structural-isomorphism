"""Tests for the guardrail core: state-machine fixer + retry loop.

Mirrors the V4 sanity tests at v4/tests/sanity/test_llm_guardrail.py,
adapted to the new package import path.
"""

from __future__ import annotations

import json

import pytest

from guarded_llm import (
    state_machine_fix,
    validate_json,
    guardrailed_llm_call,
    GuardrailResult,
    Layer3CriticVerdict,
    Layer4Prediction,
    B3EnsembleReview,
)


VALID_L3 = {
    "class_id": "soc_earthquake",
    "review_verdict": "KEEP",
    "confidence": "high",
    "flagged_count": 0,
    "reasoning": "Clauset alpha 2.1 in tail; ND not rejected.",
}

VALID_L4 = {
    "class_id": "soc_solar",
    "target_system": "solar_flares",
    "physical_quantity": "alpha",
    "predicted_band": [1.8, 2.3],
    "evidence_url": "https://example.org/x",
    "journal_target": "ApJ",
}

VALID_B3 = {
    "class_id": "soc_neural",
    "model_id": "claude-sonnet-4.5",
    "verdict": "KEEP",
    "confidence": 0.85,
    "rationale": "Avalanche stats match.",
}


# -----------------------------------------------------------------------
# 1. Valid input → parse success
# -----------------------------------------------------------------------


def test_01_valid_layer3_passes():
    ok, err, inst = validate_json(VALID_L3, Layer3CriticVerdict)
    assert ok, err
    assert err is None
    assert inst.class_id == "soc_earthquake"
    assert inst.review_verdict == "KEEP"


def test_01b_valid_layer4_passes():
    ok, err, inst = validate_json(VALID_L4, Layer4Prediction)
    assert ok, err
    assert inst.predicted_band == [1.8, 2.3]


def test_01c_valid_b3_passes():
    ok, err, inst = validate_json(VALID_B3, B3EnsembleReview)
    assert ok, err
    assert inst.confidence == pytest.approx(0.85)


def test_01d_merge_with_verdict_passes():
    d = dict(VALID_L3, review_verdict="MERGE_WITH(soc_solar)")
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert ok, err
    assert inst.review_verdict == "MERGE_WITH(soc_solar)"


# -----------------------------------------------------------------------
# 2. Trailing comma
# -----------------------------------------------------------------------


def test_02_trailing_comma():
    raw = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low",'
        ' "flagged_count": 0, "reasoning": "ok",}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err
    assert inst.class_id == "x"


# -----------------------------------------------------------------------
# 3. Single quotes
# -----------------------------------------------------------------------


def test_03_single_quotes():
    raw = (
        "{'class_id': 'x', 'review_verdict': 'KEEP', 'confidence': 'low',"
        " 'flagged_count': 0, 'reasoning': 'ok'}"
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err


# -----------------------------------------------------------------------
# 4. Markdown fence
# -----------------------------------------------------------------------


def test_04_markdown_fence():
    raw = (
        "Here's the verdict:\n"
        "```json\n"
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low", '
        '"flagged_count": 0, "reasoning": "ok"}\n'
        "```"
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err


# -----------------------------------------------------------------------
# 5. C-style comments
# -----------------------------------------------------------------------


def test_05_c_comments():
    raw = (
        "{\n"
        "  // this is a comment\n"
        '  "class_id": "x", /* block comment */\n'
        '  "review_verdict": "KEEP",\n'
        '  "confidence": "low",\n'
        '  "flagged_count": 0,\n'
        '  "reasoning": "ok"\n'
        "}"
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err


# -----------------------------------------------------------------------
# 6. NaN → null
# -----------------------------------------------------------------------


def test_06_nan_to_null():
    raw = (
        '{"class_id": "x", "target_system": "solar", "physical_quantity": "alpha", '
        '"predicted_band": [1.0, 2.0], "evidence_url": NaN, "journal_target": "ApJ"}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer4Prediction)
    assert ok, err
    assert inst.evidence_url is None


# -----------------------------------------------------------------------
# 7. Unescaped interior quote
# -----------------------------------------------------------------------


def test_07_unescaped_interior_quote():
    raw = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low",'
        ' "flagged_count": 0, "reasoning": "He said "hi"."}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err
    assert '"hi"' in inst.reasoning or "hi" in inst.reasoning


# -----------------------------------------------------------------------
# 8. Invalid verdict value
# -----------------------------------------------------------------------


def test_08_invalid_verdict():
    d = dict(VALID_L3, review_verdict="MAYBE")
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert "review_verdict" in err
    assert inst is None


# -----------------------------------------------------------------------
# 9. Missing required field
# -----------------------------------------------------------------------


def test_09_missing_required_field():
    d = {"class_id": "x"}
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert "missing" in err.lower()
    assert "review_verdict" in err
    assert inst is None


# -----------------------------------------------------------------------
# 10. Type mismatch
# -----------------------------------------------------------------------


def test_10_type_mismatch():
    d = dict(VALID_L3, flagged_count="three")
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert "flagged_count" in err
    assert inst is None


def test_10b_predicted_band_wrong_length():
    d = dict(VALID_L4, predicted_band=[1.0])
    ok, err, inst = validate_json(d, Layer4Prediction)
    assert not ok
    assert "predicted_band" in err


def test_10c_confidence_out_of_range():
    d = dict(VALID_B3, confidence=1.5)
    ok, err, inst = validate_json(d, B3EnsembleReview)
    assert not ok
    assert "confidence" in err


# -----------------------------------------------------------------------
# 11. Retry exhausted (legacy API)
# -----------------------------------------------------------------------


def test_11_retry_exhausted():
    call_log: list[str] = []

    def prompt_fn(last_err: str | None) -> str:
        if last_err is None:
            return "Output JSON."
        return f"Output JSON only. Previous error: {last_err}"

    def llm_caller(prompt: str) -> str:
        call_log.append(prompt)
        return "this is not json at all, just garbage"

    parsed, errors = guardrailed_llm_call(
        prompt_fn, llm_caller, Layer3CriticVerdict, max_retries=3
    )
    assert parsed is None
    assert len(errors) == 3
    assert len(call_log) == 3
    assert "Previous error" in call_log[1]
    assert "Previous error" in call_log[2]


# -----------------------------------------------------------------------
# 12. First attempt fails, second passes (legacy API)
# -----------------------------------------------------------------------


def test_12_first_fails_second_passes():
    call_log: list[str] = []
    responses = [
        "not json",
        (
            "```json\n"
            '{"class_id": "soc_earthquake", "review_verdict": "KEEP",'
            ' "confidence": "high", "flagged_count": 2,'
            ' "reasoning": "Looks good.",}\n'
            "```"
        ),
    ]
    counter = {"i": 0}

    def prompt_fn(last_err: str | None) -> str:
        return "p" if last_err is None else f"retry: {last_err}"

    def llm_caller(prompt: str) -> str:
        call_log.append(prompt)
        out = responses[counter["i"]]
        counter["i"] += 1
        return out

    parsed, errors = guardrailed_llm_call(
        prompt_fn, llm_caller, Layer3CriticVerdict, max_retries=3
    )
    assert parsed is not None
    assert parsed.class_id == "soc_earthquake"
    assert parsed.flagged_count == 2
    assert len(errors) == 1
    assert len(call_log) == 2


# -----------------------------------------------------------------------
# 13. Idempotent on clean
# -----------------------------------------------------------------------


def test_13_fixer_idempotent_on_clean():
    clean = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low", '
        '"flagged_count": 0, "reasoning": "ok"}'
    )
    fixed = state_machine_fix(clean)
    assert json.loads(fixed) == json.loads(clean)


# -----------------------------------------------------------------------
# 14. llm_caller raises (legacy)
# -----------------------------------------------------------------------


def test_14_llm_caller_exception_is_caught():
    counter = {"i": 0}

    def prompt_fn(last_err: str | None) -> str:
        return "p"

    def llm_caller(prompt: str) -> str:
        counter["i"] += 1
        if counter["i"] < 3:
            raise RuntimeError(f"network blip {counter['i']}")
        return (
            '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low",'
            ' "flagged_count": 0, "reasoning": "ok"}'
        )

    parsed, errors = guardrailed_llm_call(
        prompt_fn, llm_caller, Layer3CriticVerdict, max_retries=3
    )
    assert parsed is not None
    assert len(errors) == 2
    assert "network blip" in errors[0]


# -----------------------------------------------------------------------
# 15. Combined drift
# -----------------------------------------------------------------------


def test_15_combined_drift():
    raw = (
        "Sure, here's the verdict:\n"
        "```json\n"
        "{\n"
        "  // top-level\n"
        "  'class_id': 'soc_x',\n"
        "  'review_verdict': 'KEEP',\n"
        "  'confidence': 'medium',\n"
        "  'flagged_count': 3,\n"
        "  'reasoning': 'looks fine',\n"
        "}\n"
        "```"
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, f"cleaned was: {cleaned!r}; err: {err}"
    assert inst.class_id == "soc_x"
    assert inst.flagged_count == 3


# -----------------------------------------------------------------------
# 16. GuardrailResult shape (new API)
# -----------------------------------------------------------------------


def test_16_guardrail_result_dataclass():
    r = GuardrailResult(parsed=None, errors=["x"], attempts=2, cost_usd=0.01)
    assert r.ok is False
    r2 = GuardrailResult(parsed={"a": 1})
    assert r2.ok is True


# -----------------------------------------------------------------------
# 17. Legacy call validates input
# -----------------------------------------------------------------------


def test_17_legacy_missing_args_raises():
    with pytest.raises(ValueError):
        guardrailed_llm_call()


# -----------------------------------------------------------------------
# 18. Max retries < 1 (legacy)
# -----------------------------------------------------------------------


def test_18_max_retries_zero():
    parsed, errors = guardrailed_llm_call(
        lambda e: "p", lambda p: "{}", Layer3CriticVerdict, max_retries=0
    )
    assert parsed is None
    assert len(errors) == 1
    assert "max_retries" in errors[0]


# -----------------------------------------------------------------------
# 19. BOM-prefixed input
# -----------------------------------------------------------------------


def test_19_bom_prefix():
    raw = "﻿" + json.dumps(VALID_L3)
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err


# -----------------------------------------------------------------------
# 20. Empty raw input fails gracefully
# -----------------------------------------------------------------------


def test_20_empty_raw_input():
    cleaned = state_machine_fix("")
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert not ok
    assert err is not None
