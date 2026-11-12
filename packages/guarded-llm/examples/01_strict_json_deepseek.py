"""Example 01: strict JSON output from DeepSeek with a Pydantic schema.

Set DEEPSEEK_API_KEY in your env before running:

    export DEEPSEEK_API_KEY="sk-..."
    python 01_strict_json_deepseek.py
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from guarded_llm import GuardedLLM, RetryPolicy


class Verdict(BaseModel):
    """The shape we want the model to return."""

    verdict: str = Field(description="One of KEEP / REJECT / SPLIT")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


def main() -> None:
    llm = GuardedLLM(
        provider="deepseek",
        model="deepseek-v4-flash",
        schema=Verdict,
        retry=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
        max_tokens=512,
    )

    prompt = (
        "You are a scientific reviewer. Reply with a JSON object that has "
        "exactly the fields: verdict (KEEP|REJECT|SPLIT), confidence (0-1), "
        "reasoning (string). Question: 'Is gravity a self-organized criticality "
        "system?'"
    )

    result: Verdict = llm.call(prompt)
    print(f"verdict:    {result.verdict}")
    print(f"confidence: {result.confidence}")
    print(f"reasoning:  {result.reasoning}")
    print(f"---")
    print(f"attempts: {llm.last_stats.attempts}")
    print(f"cost:     ${llm.last_stats.cost_usd:.6f}")


if __name__ == "__main__":
    main()
