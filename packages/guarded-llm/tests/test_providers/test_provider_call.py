"""Tests for the provider-style guardrailed_llm_call orchestrator.

Uses a stub provider so no real network calls are made.
"""

from __future__ import annotations

import pytest

from guarded_llm import (
    LLMSchema,
    BaseProvider,
    GuardrailResult,
    guardrailed_llm_call,
    register_provider,
    BudgetExceededError,
    LLMCallError,
)


# --- Stub provider ---------------------------------------------------------


class _StubProvider(BaseProvider):
    """A scriptable stub for tests. Set `_StubProvider.responses` and reset _i."""

    responses: list[dict] = []
    _i: int = 0
    cost_per_call: float = 0.001

    name = "stub"

    def call(self, messages, model, max_tokens, schema=None, **kwargs):
        if _StubProvider._i >= len(_StubProvider.responses):
            raise RuntimeError("stub exhausted")
        resp = _StubProvider.responses[_StubProvider._i]
        _StubProvider._i += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


register_provider("stub", _StubProvider)


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubProvider.responses = []
    _StubProvider._i = 0
    yield


@pytest.fixture
def schema():
    return LLMSchema(
        {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["KEEP", "REJECT"]},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["verdict", "confidence"],
        }
    )


# --- Tests -----------------------------------------------------------------


def test_provider_call_success_first_try(schema):
    _StubProvider.responses = [
        {"text": '{"verdict": "KEEP", "confidence": 0.9}', "cost_usd": 0.001}
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=schema,
    )
    assert isinstance(result, GuardrailResult)
    assert result.ok
    assert result.parsed == {"verdict": "KEEP", "confidence": 0.9}
    assert result.attempts == 1
    assert result.cost_usd == pytest.approx(0.001)
    assert result.errors == []


def test_provider_call_recovers_via_retry(schema):
    _StubProvider.responses = [
        {"text": "garbage not json", "cost_usd": 0.0005},
        {"text": '{"verdict": "REJECT", "confidence": 0.2}', "cost_usd": 0.0005},
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=schema,
        max_retries=3,
    )
    assert result.ok
    assert result.parsed["verdict"] == "REJECT"
    assert result.attempts == 2
    assert len(result.errors) == 1
    assert result.cost_usd == pytest.approx(0.001)


def test_provider_call_exhausts_retries(schema):
    _StubProvider.responses = [
        {"text": "garbage", "cost_usd": 0.0005},
        {"text": "still garbage", "cost_usd": 0.0005},
        {"text": "more garbage", "cost_usd": 0.0005},
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=schema,
        max_retries=3,
    )
    assert not result.ok
    assert result.parsed is None
    assert result.attempts == 3
    assert len(result.errors) == 3
    assert len(result.raw_outputs) == 3


def test_provider_call_budget_exceeded(schema):
    _StubProvider.responses = [
        {"text": "garbage", "cost_usd": 0.5},  # already over cap
    ]
    with pytest.raises(BudgetExceededError) as exc:
        guardrailed_llm_call(
            provider="stub",
            model="m",
            messages=[{"role": "user", "content": "hi"}],
            schema=schema,
            max_retries=3,
            budget_cap_usd=0.1,
        )
    assert exc.value.spent_usd > exc.value.cap_usd


def test_provider_call_handles_provider_exception(schema):
    _StubProvider.responses = [
        LLMCallError("network down"),
        {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.001},
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=schema,
        max_retries=3,
    )
    assert result.ok
    assert "network down" in result.errors[0]
    assert result.attempts == 2


def test_provider_call_retry_hint_injected(schema):
    """Verify that on retry, the previous error is appended to the last user message."""
    seen_messages: list[list[dict]] = []

    class _SpyProvider(BaseProvider):
        name = "spy"

        def call(self, messages, model, max_tokens, schema=None, **kwargs):
            seen_messages.append([dict(m) for m in messages])
            if len(seen_messages) == 1:
                return {"text": "garbage", "cost_usd": 0.0}
            return {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.0}

    register_provider("spy", _SpyProvider)
    result = guardrailed_llm_call(
        provider="spy",
        model="m",
        messages=[{"role": "user", "content": "original prompt"}],
        schema=schema,
        max_retries=3,
    )
    assert result.ok
    assert len(seen_messages) == 2
    # First call: original prompt only
    assert "Previous output failed" not in seen_messages[0][-1]["content"]
    # Second call: retry hint appended
    assert "Previous output failed" in seen_messages[1][-1]["content"]


def test_provider_call_missing_args_raises():
    with pytest.raises(ValueError, match="provider-style call requires"):
        guardrailed_llm_call(provider="stub", model="m")  # missing messages, schema


def test_provider_call_with_dataclass_schema():
    from guarded_llm import Layer3CriticVerdict

    _StubProvider.responses = [
        {
            "text": (
                '{"class_id": "soc_x", "review_verdict": "KEEP", '
                '"confidence": "high", "flagged_count": 1, "reasoning": "ok"}'
            ),
            "cost_usd": 0.001,
        }
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=Layer3CriticVerdict,
    )
    assert result.ok
    assert result.parsed.class_id == "soc_x"
    assert result.parsed.flagged_count == 1


def test_provider_call_strips_fences_from_response(schema):
    _StubProvider.responses = [
        {
            "text": (
                "Sure, here you go:\n"
                "```json\n"
                '{"verdict": "KEEP", "confidence": 0.7,}\n'
                "```"
            ),
            "cost_usd": 0.0,
        }
    ]
    result = guardrailed_llm_call(
        provider="stub",
        model="m",
        messages=[{"role": "user", "content": "hi"}],
        schema=schema,
    )
    assert result.ok
    assert result.parsed["verdict"] == "KEEP"
