"""multi_provider.py — fallback chain across providers.

Demonstrates how to route through DeepSeek → Kimi → Anthropic when one is
rate-limited or returns persistently invalid output. Pure standard-library
fallback — no external orchestration library required.

Run with whatever provider keys you have available:

    export DEEPSEEK_API_KEY=...
    export KIMI_API_KEY=...
    export ANTHROPIC_API_KEY=...
    python examples/multi_provider.py
"""

from __future__ import annotations

import os

from guarded_llm import (
    guardrailed_llm_call,
    LLMSchema,
    GuardrailResult,
    GuardrailError,
)


SCHEMA = LLMSchema(
    {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "minLength": 10},
            "topics": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        },
        "required": ["summary", "topics"],
    }
)


PROVIDERS = [
    ("deepseek", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    ("kimi", "kimi-k2.5", "KIMI_API_KEY"),
    ("anthropic", "claude-sonnet-4.5", "ANTHROPIC_API_KEY"),
]


def call_with_fallback(messages: list[dict]) -> GuardrailResult:
    last_result: GuardrailResult | None = None
    for provider, model, env_key in PROVIDERS:
        if not os.getenv(env_key):
            print(f"[skip] {provider}: {env_key} not set")
            continue
        try:
            print(f"[try ] {provider} / {model}")
            result = guardrailed_llm_call(
                provider=provider,
                model=model,
                messages=messages,
                schema=SCHEMA,
                max_retries=2,
                budget_cap_usd=0.1,
            )
        except GuardrailError as e:
            print(f"[fail] {provider}: {e}")
            continue
        if result.ok:
            print(f"[ ok ] {provider}: ${result.cost_usd:.6f}, {result.attempts} attempt(s)")
            return result
        last_result = result
        print(f"[fail] {provider}: {result.errors}")
    return last_result or GuardrailResult(parsed=None, errors=["no providers configured"])


def main() -> None:
    result = call_with_fallback(
        [
            {
                "role": "user",
                "content": (
                    "Summarize the concept of self-organized criticality in 2 sentences, "
                    "then list 3 example systems. Output JSON: {summary, topics}."
                ),
            }
        ]
    )
    if result.ok:
        print(f"\nFinal: {result.parsed}")
    else:
        print(f"\nAll providers failed: {result.errors}")


if __name__ == "__main__":
    main()
