"""Example 03: multi-vendor failover.

Try DeepSeek first (cheapest); on any error, fall back to Kimi; on a second
error, fall back to GLM. This is the canonical pattern for production
LLM-in-the-loop pipelines where vendor availability is unreliable (regional
blocks, rate limits, transient 5xx).

    export DEEPSEEK_API_KEY="sk-..."
    export KIMI_API_KEY="..."
    export GLM_API_KEY="..."
    python 03_multi_vendor_failover.py
"""

from __future__ import annotations

from pydantic import BaseModel

from guarded_llm import (
    GuardedLLM,
    Budget,
    RetryPolicy,
    RetryExhausted,
    BudgetExceeded,
    GuardrailError,
)


class Answer(BaseModel):
    answer: str
    confidence: float


# Ordered fallback chain: cheapest first, most expensive last.
FAILOVER = [
    ("deepseek", "deepseek-v4-flash"),
    ("kimi", "kimi-k2.5"),
    ("glm", "glm-4.6"),
]


def ask_with_failover(prompt: str, budget: Budget) -> Answer:
    """Try each vendor in order; return the first successful parse."""
    last_err: Exception | None = None
    for provider, model in FAILOVER:
        llm = GuardedLLM(
            provider=provider,
            model=model,
            schema=Answer,
            budget=budget,
            retry=RetryPolicy(max_attempts=2, backoff_seconds=1.0),
            max_tokens=256,
        )
        try:
            out = llm.call(prompt)
            print(f"  succeeded with {provider}/{model} (cost ${llm.last_stats.cost_usd:.4f})")
            return out
        except BudgetExceeded:
            # Budget is a hard stop — don't retry on another vendor.
            raise
        except (RetryExhausted, GuardrailError) as e:
            print(f"  {provider}/{model} failed: {type(e).__name__}: {e}")
            last_err = e
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  {provider}/{model} crashed: {type(e).__name__}: {e}")
            last_err = e
            continue
    raise RuntimeError(f"All vendors failed; last error: {last_err}")


def main() -> None:
    budget = Budget(usd_total=1.00)
    prompt = (
        "What is the boiling point of water at sea level in Celsius? "
        "Reply with JSON: {answer: '...', confidence: 0-1}."
    )

    out = ask_with_failover(prompt, budget)
    print(f"\nFinal answer: {out.answer} (confidence {out.confidence})")
    print(f"Total spent:  ${budget.spent_usd:.4f}")


if __name__ == "__main__":
    main()
