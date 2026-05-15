"""Sanity tests for v4/lib/llm_guardrail.py + v4/lib/llm_schemas.py.

Pure stdlib + pytest. No real LLM calls — mocks via stateful closures.
Run from repo root:

    .venv/bin/python -m pytest v4/tests/sanity/test_llm_guardrail.py -v
"""

from __future__ import annotations

import pytest

***REMOVED*** Import the deprecated shims via their canonical `v4.lib.*` package path.
***REMOVED*** Historically these used bare `import llm_guardrail`, which required a
***REMOVED*** sys.path.insert(0, v4/lib) hack — but that prepend shadowed the
***REMOVED*** editable-installed `soc_pipeline` real package in sibling test modules.
***REMOVED*** Using the dotted path keeps shim-coverage intact without polluting sys.path.
from v4.lib.llm_guardrail import (
    state_machine_fix,
    validate_json,
    guardrailed_llm_call,
)
from v4.lib.llm_schemas import (
    Layer3CriticVerdict,
    Layer4Prediction,
    B3EnsembleReview,
)


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** Helpers: a valid baseline JSON for each schema
***REMOVED*** ---------------------------------------------------------------------------

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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 1. Valid input → parse success (for all 3 schemas)
***REMOVED*** ---------------------------------------------------------------------------


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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 2. Trailing comma
***REMOVED*** ---------------------------------------------------------------------------


def test_02_trailing_comma():
    raw = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low",'
        ' "flagged_count": 0, "reasoning": "ok",}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err
    assert inst.class_id == "x"


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 3. Single quotes
***REMOVED*** ---------------------------------------------------------------------------


def test_03_single_quotes():
    raw = (
        "{'class_id': 'x', 'review_verdict': 'KEEP', 'confidence': 'low',"
        " 'flagged_count': 0, 'reasoning': 'ok'}"
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 4. Markdown fence
***REMOVED*** ---------------------------------------------------------------------------


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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 5. C-style comments
***REMOVED*** ---------------------------------------------------------------------------


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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 6. NaN → null
***REMOVED*** ---------------------------------------------------------------------------


def test_06_nan_to_null():
    ***REMOVED*** NaN in non-required field; Layer4 lets evidence_url be null
    raw = (
        '{"class_id": "x", "target_system": "solar", "physical_quantity": "alpha", '
        '"predicted_band": [1.0, 2.0], "evidence_url": NaN, "journal_target": "ApJ"}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer4Prediction)
    assert ok, err
    assert inst.evidence_url is None


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 7. Unescaped interior quote
***REMOVED*** ---------------------------------------------------------------------------


def test_07_unescaped_interior_quote():
    ***REMOVED*** LLM emits: "reasoning": "He said "hi"."
    raw = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low",'
        ' "flagged_count": 0, "reasoning": "He said "hi"."}'
    )
    cleaned = state_machine_fix(raw)
    ok, err, inst = validate_json(cleaned, Layer3CriticVerdict)
    assert ok, err
    assert '"hi"' in inst.reasoning or "hi" in inst.reasoning


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 8. Invalid verdict value → reject
***REMOVED*** ---------------------------------------------------------------------------


def test_08_invalid_verdict():
    d = dict(VALID_L3, review_verdict="MAYBE")
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert err is not None
    assert "review_verdict" in err
    assert inst is None


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 9. Missing required field → reject
***REMOVED*** ---------------------------------------------------------------------------


def test_09_missing_required_field():
    d = {"class_id": "x"}
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert err is not None
    assert "missing" in err.lower()
    ***REMOVED*** Must name at least one missing field
    assert "review_verdict" in err
    assert inst is None


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 10. Type mismatch → reject
***REMOVED*** ---------------------------------------------------------------------------


def test_10_type_mismatch():
    d = dict(VALID_L3, flagged_count="three")
    ok, err, inst = validate_json(d, Layer3CriticVerdict)
    assert not ok
    assert err is not None
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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 11. Retry exhausted (mock LLM always returns garbage)
***REMOVED*** ---------------------------------------------------------------------------


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
    ***REMOVED*** Retry prompts should reference the previous error
    assert "Previous error" in call_log[1]
    assert "Previous error" in call_log[2]


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 12. First attempt fails, second passes (stateful mock)
***REMOVED*** ---------------------------------------------------------------------------


def test_12_first_fails_second_passes():
    call_log: list[str] = []
    responses = [
        ***REMOVED*** First: garbage
        "not json",
        ***REMOVED*** Second: valid JSON (in a fence + with a trailing comma to exercise fixer)
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
    assert len(errors) == 1  ***REMOVED*** one earlier failure
    assert len(call_log) == 2  ***REMOVED*** only two LLM calls (success on 2nd)


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 13. Extra: state-machine-fix is idempotent on already-clean JSON
***REMOVED*** ---------------------------------------------------------------------------


def test_13_fixer_idempotent_on_clean():
    clean = (
        '{"class_id": "x", "review_verdict": "KEEP", "confidence": "low", '
        '"flagged_count": 0, "reasoning": "ok"}'
    )
    fixed = state_machine_fix(clean)
    ***REMOVED*** parse both, compare
    import json

    assert json.loads(fixed) == json.loads(clean)


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 14. llm_caller raises — recorded as error, retry continues
***REMOVED*** ---------------------------------------------------------------------------


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


***REMOVED*** ---------------------------------------------------------------------------
***REMOVED*** 15. Combined drift: fences + comments + single quotes + trailing comma
***REMOVED*** ---------------------------------------------------------------------------


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
