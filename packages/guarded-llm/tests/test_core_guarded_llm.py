"""Tests for the high-level GuardedLLM class.

Uses a stub provider so no real network calls are made.
"""

from __future__ import annotations

import pytest

pydantic = pytest.importorskip("pydantic")
from pydantic import BaseModel, Field  # noqa: E402

from guarded_llm import (
    GuardedLLM,
    Budget,
    BudgetExceeded,
    RetryPolicy,
    RetryExhausted,
    BaseProvider,
    register_provider,
    GuardrailResult,
)


class Verdict(BaseModel):
    verdict: str
    confidence: float = Field(ge=0.0, le=1.0)


# --- Stub provider --------------------------------------------------------


class _StubProvider(BaseProvider):
    """Scriptable stub. Set _StubProvider.responses (list[dict or Exception])."""

    responses: list = []
    _i: int = 0
    name = "stub_core"

    def call(self, messages, model, max_tokens, schema=None, **kwargs):
        if _StubProvider._i >= len(_StubProvider.responses):
            raise RuntimeError("stub exhausted")
        resp = _StubProvider.responses[_StubProvider._i]
        _StubProvider._i += 1
        if isinstance(resp, Exception):
            raise resp
        return resp


register_provider("stub_core", _StubProvider)


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubProvider.responses = []
    _StubProvider._i = 0
    yield


# --- Tests ----------------------------------------------------------------


def test_guarded_llm_call_returns_pydantic_instance():
    _StubProvider.responses = [
        {"text": '{"verdict": "KEEP", "confidence": 0.9}', "cost_usd": 0.001}
    ]
    llm = GuardedLLM(provider="stub_core", model="m", schema=Verdict)
    out = llm.call("test prompt")
    assert isinstance(out, Verdict)
    assert out.verdict == "KEEP"
    assert llm.last_stats.attempts == 1
    assert llm.last_stats.cost_usd == pytest.approx(0.001)


def test_guarded_llm_call_with_dict_schema():
    """A plain dict schema is auto-wrapped in LLMSchema."""
    _StubProvider.responses = [
        {"text": '{"verdict": "REJECT", "confidence": 0.2}', "cost_usd": 0.001}
    ]
    schema = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string"},
            "confidence": {"type": "number"},
        },
        "required": ["verdict", "confidence"],
    }
    llm = GuardedLLM(provider="stub_core", model="m", schema=schema)
    out = llm.call("test")
    assert isinstance(out, dict)
    assert out["verdict"] == "REJECT"


def test_guarded_llm_recovers_on_retry():
    _StubProvider.responses = [
        {"text": "garbage not json", "cost_usd": 0.0005},
        {"text": '{"verdict": "KEEP", "confidence": 0.7}', "cost_usd": 0.0005},
    ]
    llm = GuardedLLM(
        provider="stub_core",
        model="m",
        schema=Verdict,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
    )
    out = llm.call("test")
    assert out.confidence == pytest.approx(0.7)
    assert llm.last_stats.attempts == 2
    assert len(llm.last_stats.errors) == 1


def test_guarded_llm_retry_exhausted_raises():
    _StubProvider.responses = [
        {"text": "g1", "cost_usd": 0.0001},
        {"text": "g2", "cost_usd": 0.0001},
        {"text": "g3", "cost_usd": 0.0001},
    ]
    llm = GuardedLLM(
        provider="stub_core",
        model="m",
        schema=Verdict,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=0.0),
    )
    with pytest.raises(RetryExhausted) as exc:
        llm.call("test")
    assert len(exc.value.attempts) == 3
    assert exc.value.last_raw == "g3"


def test_guarded_llm_budget_enforced():
    _StubProvider.responses = [
        {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.20},
    ]
    budget = Budget(usd_total=0.10, usd_per_call=0.10)
    llm = GuardedLLM(
        provider="stub_core",
        model="m",
        schema=Verdict,
        budget=budget,
    )
    with pytest.raises(BudgetExceeded):
        llm.call("test")


def test_guarded_llm_budget_consumed_across_calls():
    """Budget should persist across multiple .call() invocations on same instance."""
    _StubProvider.responses = [
        {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.03},
        {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.03},
        {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.03},
    ]
    budget = Budget(usd_total=0.05)
    llm = GuardedLLM(
        provider="stub_core",
        model="m",
        schema=Verdict,
        budget=budget,
    )
    llm.call("test1")  # OK, spent 0.03
    with pytest.raises(BudgetExceeded):
        llm.call("test2")  # would push to 0.06 > 0.05


def test_call_as_result_returns_result_on_failure():
    _StubProvider.responses = [
        {"text": "garbage", "cost_usd": 0.0001},
        {"text": "garbage", "cost_usd": 0.0001},
    ]
    llm = GuardedLLM(
        provider="stub_core",
        model="m",
        schema=Verdict,
        retry=RetryPolicy(max_attempts=2, backoff_seconds=0.0),
    )
    result = llm.call_as_result("test")
    assert isinstance(result, GuardrailResult)
    assert not result.ok
    assert result.parsed is None
    assert result.attempts == 2


def test_call_as_result_returns_result_on_success():
    _StubProvider.responses = [
        {"text": '{"verdict": "KEEP", "confidence": 0.6}', "cost_usd": 0.001},
    ]
    llm = GuardedLLM(provider="stub_core", model="m", schema=Verdict)
    result = llm.call_as_result("test")
    assert result.ok
    assert result.parsed.verdict == "KEEP"


def test_init_validation():
    with pytest.raises(ValueError):
        GuardedLLM(provider="", model="m", schema=Verdict)
    with pytest.raises(ValueError):
        GuardedLLM(provider="stub_core", model="", schema=Verdict)
    with pytest.raises(ValueError):
        GuardedLLM(provider="stub_core", model="m", schema=None)
    with pytest.raises(TypeError):
        GuardedLLM(
            provider="stub_core",
            model="m",
            schema=Verdict,
            budget="cheap",  # type: ignore[arg-type]
        )


def test_system_prompt_prepended_as_first_message():
    seen = []

    class _Spy(BaseProvider):
        name = "spy_sys"

        def call(self, messages, model, max_tokens, schema=None, **kwargs):
            seen.append([dict(m) for m in messages])
            return {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.0}

    register_provider("spy_sys", _Spy)
    llm = GuardedLLM(provider="spy_sys", model="m", schema=Verdict)
    llm.call("user prompt", system="be terse")
    assert seen[0][0]["role"] == "system"
    assert seen[0][0]["content"] == "be terse"
    assert seen[0][1]["role"] == "user"


def test_provider_kwargs_forwarded():
    seen_kwargs = []

    class _Spy(BaseProvider):
        name = "spy_kw"

        def call(self, messages, model, max_tokens, schema=None, **kwargs):
            seen_kwargs.append(kwargs)
            return {"text": '{"verdict": "KEEP", "confidence": 0.5}', "cost_usd": 0.0}

    register_provider("spy_kw", _Spy)
    llm = GuardedLLM(
        provider="spy_kw", model="m", schema=Verdict, api_key="constructor-key"
    )
    llm.call("test", temperature=0.7)
    assert seen_kwargs[0].get("api_key") == "constructor-key"
    assert seen_kwargs[0].get("temperature") == 0.7
