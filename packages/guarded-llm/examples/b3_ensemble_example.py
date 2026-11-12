"""b3_ensemble_example.py — N-model ensemble vote pattern.

This mirrors the structural-isomorphism V4 Layer 3.5 "B3 ensemble pass":
ask N independent models the same question, validate each response against
B3EnsembleReview, then majority-vote the verdicts.

It's a real production pattern for taxonomy refinement — see the
structural-isomorphism B3 taxonomy v2 (session #2).
"""

from __future__ import annotations

import os
from collections import Counter

from guarded_llm import (
    guardrailed_llm_call,
    B3EnsembleReview,
    GuardrailError,
)


# (provider, model, env_key) tuples for the ensemble
ENSEMBLE = [
    ("deepseek", "deepseek-v4-flash", "DEEPSEEK_API_KEY"),
    ("kimi", "kimi-k2.5", "KIMI_API_KEY"),
    ("anthropic", "claude-sonnet-4.5", "ANTHROPIC_API_KEY"),
]


def prompt_for(class_id: str, question: str) -> list[dict]:
    return [
        {
            "role": "user",
            "content": (
                f"You are reviewing taxonomy class '{class_id}'. {question}\n\n"
                "Output JSON exactly: {class_id, model_id, verdict (KEEP/REJECT/UNCLEAR), "
                "confidence (0-1 float), rationale (1 sentence)}."
            ),
        }
    ]


def ensemble_vote(class_id: str, question: str) -> tuple[str | None, list[dict]]:
    """Run the question past every available model. Return (winning_verdict, raw_reviews)."""
    reviews: list = []
    for provider, model, env_key in ENSEMBLE:
        if not os.getenv(env_key):
            print(f"[skip] {provider}: {env_key} unset")
            continue
        try:
            result = guardrailed_llm_call(
                provider=provider,
                model=model,
                messages=prompt_for(class_id, question),
                schema=B3EnsembleReview,
                max_retries=2,
                budget_cap_usd=0.05,
            )
        except GuardrailError as e:
            print(f"[fail] {provider}: {e}")
            continue
        if not result.ok:
            print(f"[fail] {provider}: {result.errors}")
            continue
        review = result.parsed
        # Override model_id with our actual model name (some LLMs hallucinate it)
        review.model_id = f"{provider}/{model}"
        reviews.append(review)
        print(f"[ ok ] {provider}: verdict={review.verdict}, conf={review.confidence:.2f}")

    if not reviews:
        return None, []

    # Confidence-weighted majority vote
    weighted: Counter[str] = Counter()
    for r in reviews:
        weighted[r.verdict] += r.confidence
    winner, score = weighted.most_common(1)[0]
    return winner, reviews


def main() -> None:
    verdict, reviews = ensemble_vote(
        class_id="soc_neural_avalanches",
        question=(
            "Should this class be KEPT in the SOC taxonomy? "
            "Reference: criticality in neural avalanches has been replicated "
            "but power-law exponent is contested."
        ),
    )
    print(f"\nEnsemble verdict for soc_neural_avalanches: {verdict}")
    print(f"Total models voting: {len(reviews)}")


if __name__ == "__main__":
    main()
