"""High-level `GuardedLLM` class — the headline public API.

This is the object-oriented entry point most users will see. It wraps the
lower-level `guardrailed_llm_call()` so the same instance can be re-used
across many calls with a shared `Budget` and `RetryPolicy`.

Example::

    from pydantic import BaseModel
    from guarded_llm import GuardedLLM, Budget, RetryPolicy

    class Verdict(BaseModel):
        verdict: str
        confidence: float

    llm = GuardedLLM(
        provider="deepseek",
        model="deepseek-v4-flash",
        schema=Verdict,
        budget=Budget(usd_total=0.50, usd_per_call=0.05),
        retry=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
    )

    out = llm.call("Is gravity a self-organized criticality system?")
    print(out.verdict, out.confidence)         # real Pydantic instance
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .budget import Budget
from .exceptions import BudgetExceededError, LLMCallError
from .guardrail import GuardrailResult, state_machine_fix, validate_json
from .retry import RetryExhausted, RetryPolicy
from .schemas import LLMSchema
from .validator import SchemaValidator, _HAS_PYDANTIC, BaseModel


@dataclass
class GuardedCallStats:
    """Per-call metadata returned alongside the parsed instance via `.last_stats`.

    Useful for cost dashboards / debugging without changing the return type
    of `.call()` (which by default returns the parsed instance directly).
    """

    attempts: int = 0
    cost_usd: float = 0.0
    errors: list[str] = field(default_factory=list)
    raw_outputs: list[str] = field(default_factory=list)


def _coerce_schema(schema: Any) -> Any:
    """Accept Pydantic BaseModel class, LLMSchema, dict, or legacy schema class.

    Returns an object with a `.validate(d)` method that the lower-level
    `validate_json` understands.
    """
    # Pydantic BaseModel subclass → wrap in SchemaValidator
    if _HAS_PYDANTIC and isinstance(schema, type) and issubclass(schema, BaseModel):
        return SchemaValidator(schema)
    # Raw dict treated as JSON Schema
    if isinstance(schema, dict):
        return LLMSchema(schema)
    # Anything else passed through unchanged (must already expose .validate)
    return schema


class GuardedLLM:
    """Reusable strict-JSON LLM caller with budget + retry + multi-vendor support.

    Args:
        provider: registered provider name (`"anthropic"`, `"deepseek"`,
            `"openai"`, `"kimi"`, `"glm"`, or any custom registered provider).
        model: vendor-specific model id (e.g. `"claude-sonnet-4.5"`,
            `"deepseek-v4-flash"`, `"kimi-k2.5"`, `"glm-4.6"`).
        schema: how to validate LLM output. One of:
            * a `pydantic.BaseModel` subclass (returns typed instance)
            * a `dict` (treated as a JSON Schema)
            * an `LLMSchema` instance
            * a class exposing `.validate(d) -> (ok, err, instance)`
        budget: optional `Budget` for cumulative cost cap.
        retry: optional `RetryPolicy` (defaults to 3 attempts, 1s backoff).
        max_tokens: max tokens per LLM call (default 2048).
        provider_kwargs: extra kwargs forwarded to the provider on every call
            (e.g. `api_key=`, `base_url=`, `temperature=`).

    Public API::

        llm = GuardedLLM(provider, model, schema, budget=..., retry=...)
        out = llm.call("prompt")            # returns validated instance
        llm.last_stats.cost_usd             # cost of the last call
        llm.budget.spent_usd                # cumulative spend
    """

    def __init__(
        self,
        provider: str,
        model: str,
        schema: Any,
        budget: Budget | None = None,
        retry: RetryPolicy | None = None,
        max_tokens: int = 2048,
        **provider_kwargs: Any,
    ):
        if not isinstance(provider, str) or not provider:
            raise ValueError("provider must be a non-empty string")
        if not isinstance(model, str) or not model:
            raise ValueError("model must be a non-empty string")
        if schema is None:
            raise ValueError("schema is required")
        if budget is not None and not isinstance(budget, Budget):
            raise TypeError("budget must be a Budget instance or None")
        if retry is not None and not isinstance(retry, RetryPolicy):
            raise TypeError("retry must be a RetryPolicy instance or None")

        self.provider = provider
        self.model = model
        self.schema = _coerce_schema(schema)
        self.budget = budget
        self.retry = retry or RetryPolicy()
        self.max_tokens = max_tokens
        self.provider_kwargs = dict(provider_kwargs)
        self.last_stats: GuardedCallStats = GuardedCallStats()

    # ------------------------------------------------------------------ call

    def call(
        self,
        prompt: str,
        *,
        system: str | None = None,
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> Any:
        """Run an LLM call and return the validated instance.

        Args:
            prompt: user prompt string (ignored if `messages=` is passed).
            system: optional system prompt prepended as the first message.
            messages: optional fully-formed messages list (overrides `prompt`).
            **kwargs: forwarded to the provider (e.g. `api_key=`, `temperature=`).

        Returns:
            The validated instance (Pydantic model instance, dict, or legacy
            dataclass instance — whatever the schema returns).

        Raises:
            BudgetExceededError: if cumulative cost exceeds the Budget cap.
            RetryExhausted: if all attempts fail validation.
            LLMCallError: if the provider itself fails (network, auth, etc.)
                and all retries are exhausted.
        """
        from .providers import get_provider

        if messages is None:
            messages = []
            if system:
                messages.append({"role": "system", "content": system})
            messages.append({"role": "user", "content": prompt})

        prov = get_provider(self.provider)
        merged_kwargs = {**self.provider_kwargs, **kwargs}

        stats = GuardedCallStats()
        last_err: str | None = None

        for attempt in range(self.retry.max_attempts):
            if attempt > 0:
                sleep_s = self.retry.sleep_seconds(attempt)
                if sleep_s > 0:
                    time.sleep(sleep_s)

            attempt_messages = list(messages)
            if last_err is not None and attempt_messages:
                hint = (
                    f"\n\nPrevious output failed validation: {last_err}\n"
                    "Output valid JSON only — no prose, no markdown fences."
                )
                last = dict(attempt_messages[-1])
                if last.get("role") == "user":
                    last["content"] = last.get("content", "") + hint
                    attempt_messages[-1] = last
                else:
                    attempt_messages.append({"role": "user", "content": hint.strip()})

            stats.attempts += 1
            try:
                call_out = prov.call(
                    messages=attempt_messages,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    schema=self.schema,
                    **merged_kwargs,
                )
            except Exception as exc:
                err = f"attempt {attempt + 1}: provider {self.provider!r} raised: {exc}"
                stats.errors.append(err)
                last_err = err
                continue

            raw = (
                call_out.get("text", "") if isinstance(call_out, dict) else str(call_out)
            )
            cost = (
                float(call_out.get("cost_usd", 0.0))
                if isinstance(call_out, dict)
                else 0.0
            )
            stats.raw_outputs.append(raw)
            stats.cost_usd += cost

            # Charge the budget BEFORE checking schema, so a runaway loop
            # can't keep burning money on a bad prompt.
            if self.budget is not None:
                # Budget.consume() raises BudgetExceeded if we'd exceed any cap.
                # Reset stats first so caller can inspect partial spend.
                self.last_stats = stats
                self.budget.consume(cost)

            cleaned = state_machine_fix(raw)
            ok, err, parsed = validate_json(cleaned, self.schema)
            if ok:
                self.last_stats = stats
                return parsed
            err_msg = f"attempt {attempt + 1}: {err}"
            stats.errors.append(err_msg)
            last_err = err

        self.last_stats = stats
        raise RetryExhausted(
            f"all {self.retry.max_attempts} attempts failed validation",
            attempts=stats.errors,
            last_raw=stats.raw_outputs[-1] if stats.raw_outputs else None,
        )

    # -------------------------------------------------------------- as_result

    def call_as_result(
        self,
        prompt: str,
        *,
        system: str | None = None,
        messages: list[dict] | None = None,
        **kwargs: Any,
    ) -> GuardrailResult:
        """Like `.call()` but returns a `GuardrailResult` (never raises on
        validation failure — errors are accumulated in the result)."""
        try:
            parsed = self.call(prompt, system=system, messages=messages, **kwargs)
        except RetryExhausted:
            return GuardrailResult(
                parsed=None,
                errors=list(self.last_stats.errors),
                attempts=self.last_stats.attempts,
                cost_usd=self.last_stats.cost_usd,
                raw_outputs=list(self.last_stats.raw_outputs),
            )
        except BudgetExceededError:
            # Re-raise — budget is a hard stop, not a soft validation failure.
            raise
        return GuardrailResult(
            parsed=parsed,
            errors=list(self.last_stats.errors),
            attempts=self.last_stats.attempts,
            cost_usd=self.last_stats.cost_usd,
            raw_outputs=list(self.last_stats.raw_outputs),
        )


__all__ = ["GuardedLLM", "GuardedCallStats"]
