"""basic_usage.py — minimal happy-path call.

Set DEEPSEEK_API_KEY in your env before running:

    export DEEPSEEK_API_KEY=sk-...
    python examples/basic_usage.py
"""

from __future__ import annotations

from guarded_llm import guardrailed_llm_call, LLMSchema


def main() -> None:
    schema = LLMSchema(
        {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["KEEP", "REJECT", "SPLIT", "MERGE"],
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["verdict", "confidence"],
        }
    )

    result = guardrailed_llm_call(
        provider="deepseek",
        model="deepseek-v4-flash",
        messages=[
            {
                "role": "user",
                "content": (
                    "Is gravity a self-organized criticality (SOC) system? "
                    "Output JSON: {verdict, confidence}."
                ),
            }
        ],
        schema=schema,
        max_retries=3,
        budget_cap_usd=0.05,
    )

    if result.ok:
        print(f"parsed: {result.parsed}")
        print(f"cost_usd: ${result.cost_usd:.6f}")
        print(f"attempts: {result.attempts}")
    else:
        print("All retries failed:")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
