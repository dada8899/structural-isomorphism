"""Example 02: budget enforcement — fail fast before you torch your wallet.

Demonstrates both per-call and cumulative caps. Will catch `BudgetExceeded`
and report partial spend.

    export DEEPSEEK_API_KEY="sk-..."
    python 02_budget_enforcement.py
"""

from __future__ import annotations

from pydantic import BaseModel

from guarded_llm import GuardedLLM, Budget, BudgetExceeded


class TinyAnswer(BaseModel):
    answer: str


def main() -> None:
    # 50 cents lifetime, 5 cents per individual call.
    budget = Budget(usd_total=0.50, usd_per_call=0.05)

    llm = GuardedLLM(
        provider="deepseek",
        model="deepseek-v4-flash",
        schema=TinyAnswer,
        budget=budget,
        max_tokens=200,
    )

    questions = [
        "What is 2 + 2? Answer in JSON: {answer: '...'}",
        "What is the capital of France? Answer in JSON: {answer: '...'}",
        "What year was the Eiffel Tower built? JSON: {answer: '...'}",
        # Many more rounds — eventually hits cumulative cap
    ] * 30

    for i, q in enumerate(questions, 1):
        try:
            out = llm.call(q)
            print(f"[{i:02d}] {out.answer!r:<40s}  spent=${budget.spent_usd:.4f}")
        except BudgetExceeded as e:
            print(f"[{i:02d}] BUDGET HIT: {e}")
            print(f"     final spent: ${budget.spent_usd:.4f}")
            print(f"     remaining:   ${budget.remaining_usd:.4f}")
            break


if __name__ == "__main__":
    main()
