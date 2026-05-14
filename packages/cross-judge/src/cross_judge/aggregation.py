"""Consensus aggregation strategies for multi-reviewer ensemble verdicts.

A strategy takes a list of Verdict objects and returns a tuple of
(consensus_label, disagreement_bool). Disagreement = True whenever not all
reviewers produced the same label.

Built-in strategies:
  - majority: most common label; tiebreaker = first label encountered in priority order
  - unanimous: returns label only if all reviewers agree; else returns "UNCLEAR" (configurable)
  - weighted: weighted vote by reviewer.weight * verdict.confidence
  - first_disagreement: returns "DISAGREE" as soon as any two reviewers differ; else the agreed label
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .schema import Verdict

AggregationStrategy = Callable[[list[Verdict]], tuple[str, bool]]


def _label_counts(verdicts: Iterable[Verdict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for v in verdicts:
        if v.error is not None:
            # Errored verdicts don't count toward consensus; tracked separately.
            continue
        counts[v.verdict] = counts.get(v.verdict, 0) + 1
    return counts


def _any_disagreement(verdicts: Iterable[Verdict]) -> bool:
    labels = {v.verdict for v in verdicts if v.error is None}
    return len(labels) > 1


def majority(
    verdicts: list[Verdict],
    *,
    priority: list[str] | None = None,
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Most common label wins. Ties broken by `priority` order (if given),
    else by first-seen order.

    Args:
        verdicts: per-reviewer verdicts.
        priority: tiebreaker order (labels earlier in the list win ties).
        fallback: label to return if no valid verdicts exist.
    """
    counts = _label_counts(verdicts)
    if not counts:
        return fallback, False
    disagree = _any_disagreement(verdicts)
    max_count = max(counts.values())
    tied = [label for label, c in counts.items() if c == max_count]
    if len(tied) == 1:
        return tied[0], disagree
    # tiebreaker
    if priority:
        for p in priority:
            if p in tied:
                return p, disagree
    # else preserve insertion order from `verdicts`
    seen_order: list[str] = []
    for v in verdicts:
        if v.error is None and v.verdict in tied and v.verdict not in seen_order:
            seen_order.append(v.verdict)
    return (seen_order[0] if seen_order else tied[0]), disagree


def unanimous(
    verdicts: list[Verdict],
    *,
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Return label only if all reviewers agree; else return fallback."""
    labels = {v.verdict for v in verdicts if v.error is None}
    if len(labels) == 1:
        return labels.pop(), False
    return fallback, True


def weighted(
    verdicts: list[Verdict],
    *,
    weights: dict[str, float] | None = None,
    use_confidence: bool = True,
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Weighted vote: each verdict contributes weight = (reviewer_weight × confidence).

    Args:
        verdicts: per-reviewer verdicts.
        weights: optional per-reviewer weight overrides keyed by reviewer_id.
                 Reviewers not in the dict default to weight=1.0.
        use_confidence: if True, multiply weight by verdict.confidence.
        fallback: returned if no valid verdicts.
    """
    weights = weights or {}
    scores: dict[str, float] = {}
    for v in verdicts:
        if v.error is not None:
            continue
        w = float(weights.get(v.reviewer_id, 1.0))
        if use_confidence:
            w *= max(0.0, min(1.0, v.confidence))
        scores[v.verdict] = scores.get(v.verdict, 0.0) + w
    if not scores:
        return fallback, False
    disagree = _any_disagreement(verdicts)
    best = max(scores.items(), key=lambda kv: kv[1])
    return best[0], disagree


def first_disagreement(
    verdicts: list[Verdict],
    *,
    disagree_label: str = "DISAGREE",
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Returns `disagree_label` if any pair of reviewers differ; else the agreed label."""
    labels = {v.verdict for v in verdicts if v.error is None}
    if not labels:
        return fallback, False
    if len(labels) == 1:
        return labels.pop(), False
    return disagree_label, True


STRATEGIES: dict[str, AggregationStrategy] = {
    "majority": majority,
    "unanimous": unanimous,
    "weighted": weighted,
    "first_disagreement": first_disagreement,
}


def get_strategy(name_or_fn: str | AggregationStrategy) -> AggregationStrategy:
    """Resolve a strategy by name (string) or pass through if already a callable."""
    if callable(name_or_fn):
        return name_or_fn  # type: ignore[return-value]
    key = str(name_or_fn).lower()
    if key not in STRATEGIES:
        raise KeyError(f"Unknown strategy '{name_or_fn}'. Known: {sorted(STRATEGIES)}.")
    return STRATEGIES[key]


def avg_confidence(verdicts: list[Verdict]) -> float:
    """Average confidence across valid (non-errored) verdicts."""
    valid = [v.confidence for v in verdicts if v.error is None]
    if not valid:
        return 0.0
    return sum(valid) / len(valid)
