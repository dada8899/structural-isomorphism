"""Voting strategies + disagreement metrics for ensemble verdicts.

Public surface:

  - majority_vote(verdicts, priority=None, fallback="UNCLEAR")
      → (consensus, disagreement_bool)
  - unanimous(verdicts, fallback="UNCLEAR")
      → (consensus, disagreement_bool)
  - agreement_pct(verdicts, consensus)
      → fraction of critics whose kind == consensus
  - krippendorff_alpha(verdicts, metric="nominal")
      → α coefficient in [-1, 1]; None if fewer than 2 valid verdicts
  - VOTING_STRATEGIES dict for name-based lookup.

Krippendorff's α implementation:
  Treats critics as raters and labels as nominal data. Computes α via the
  coincidence-matrix formulation (Krippendorff 2011, "Computing Krippendorff's
  Alpha-Reliability"). For our setup (one query, N critics, one label each),
  the formula simplifies considerably:

    α = 1 - D_observed / D_expected

  where D_observed = sum over pairs of critics where labels differ,
        D_expected = sum over pairs where labels would differ by chance,
                     given the marginal label distribution.

  α = 1.0 → all critics agree
  α = 0.0 → agreement equal to chance
  α < 0.0 → systematic disagreement (worse than chance)
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Callable

from .verdict import Verdict

VotingStrategy = Callable[[list[Verdict]], tuple[str, bool]]


def _valid(verdicts: Iterable[Verdict]) -> list[Verdict]:
    """Return non-errored verdicts."""
    return [v for v in verdicts if v.error is None]


def _label_counts(verdicts: Iterable[Verdict]) -> dict[str, int]:
    """Count valid verdicts by kind."""
    counts: dict[str, int] = {}
    for v in verdicts:
        if v.error is not None:
            continue
        counts[v.kind] = counts.get(v.kind, 0) + 1
    return counts


def majority_vote(
    verdicts: list[Verdict],
    *,
    priority: list[str] | None = None,
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Majority vote: most common label wins.

    Args:
        verdicts: per-critic verdicts.
        priority: tiebreaker order — labels earlier in the list win ties.
        fallback: returned if no valid verdicts.

    Returns:
        (consensus_label, disagreement_bool)
    """
    counts = _label_counts(verdicts)
    if not counts:
        return fallback, False
    labels = {v.kind for v in verdicts if v.error is None}
    disagree = len(labels) > 1
    max_count = max(counts.values())
    tied = [label for label, c in counts.items() if c == max_count]
    if len(tied) == 1:
        return tied[0], disagree
    if priority:
        for p in priority:
            if p in tied:
                return p, disagree
    # else preserve insertion order
    seen: list[str] = []
    for v in verdicts:
        if v.error is None and v.kind in tied and v.kind not in seen:
            seen.append(v.kind)
    return (seen[0] if seen else tied[0]), disagree


def unanimous(
    verdicts: list[Verdict],
    *,
    fallback: str = "UNCLEAR",
) -> tuple[str, bool]:
    """Unanimous vote: return label only if all critics agree.

    Args:
        verdicts: per-critic verdicts.
        fallback: returned on any disagreement.

    Returns:
        (consensus_label, disagreement_bool)
    """
    labels = {v.kind for v in verdicts if v.error is None}
    if len(labels) == 1:
        return labels.pop(), False
    return fallback, True


def agreement_pct(verdicts: list[Verdict], consensus: str) -> float:
    """Fraction of valid critics whose kind == consensus.

    Returns:
        float in [0.0, 1.0]. 0.0 if no valid verdicts.
    """
    valid = _valid(verdicts)
    if not valid:
        return 0.0
    matching = sum(1 for v in valid if v.kind == consensus)
    return matching / len(valid)


def krippendorff_alpha(verdicts: list[Verdict]) -> float | None:
    """Krippendorff's α for nominal data.

    Treats each critic as a rater and each label as nominal.

    For the single-item, N-rater case:
        α = 1 - (D_observed / D_expected)

    where:
        D_observed = number of disagreeing pairs of critics
        D_expected = sum over (cat_i, cat_j) of n_i * n_j (i != j) / (N-1)
                     where n_i is the count of critics that voted cat_i,
                     N is the total number of critics.

    The (N-1) divisor in D_expected is the standard small-sample correction
    (Krippendorff 2011 eq. 4).

    Returns:
        α in [-1.0, 1.0]. None if fewer than 2 valid verdicts.
        1.0  → perfect agreement
        0.0  → agreement equal to chance
        <0.0 → systematic disagreement
    """
    valid = _valid(verdicts)
    n = len(valid)
    if n < 2:
        return None

    counts = _label_counts(valid)
    total = n

    # D_observed: count of disagreeing pairs out of C(N,2)
    # For each pair of critics (i, j), if their labels differ → +1
    # Equivalently: D_obs = C(N,2) - sum_c C(n_c, 2)
    total_pairs = n * (n - 1) // 2
    same_pairs = sum(c * (c - 1) // 2 for c in counts.values())
    disagreeing_pairs = total_pairs - same_pairs

    if total_pairs == 0:
        return None

    # D_observed normalized to per-pair rate
    d_observed = disagreeing_pairs / total_pairs

    # D_expected: probability two randomly chosen labels differ given marginals
    # = 1 - sum_c (n_c / N) * ((n_c - 1) / (N - 1))   (sampling without replacement)
    if total == 1:
        return None
    same_chance = sum((c / total) * ((c - 1) / (total - 1)) for c in counts.values())
    d_expected = 1.0 - same_chance

    if d_expected == 0.0:
        # All critics had to agree by structure (e.g. only 1 label observed)
        return 1.0 if d_observed == 0.0 else 0.0

    alpha = 1.0 - (d_observed / d_expected)
    # Clamp to [-1, 1] for numerical safety; α can go slightly negative for
    # systematic disagreement but should never exceed 1.0.
    return max(-1.0, min(1.0, alpha))


VOTING_STRATEGIES: dict[str, VotingStrategy] = {
    "majority": majority_vote,
    "unanimous": unanimous,
}


def get_voting_strategy(name_or_fn: str | VotingStrategy) -> VotingStrategy:
    """Resolve a voting strategy by name or pass through if already callable."""
    if callable(name_or_fn):
        return name_or_fn  # type: ignore[return-value]
    key = str(name_or_fn).lower()
    if key not in VOTING_STRATEGIES:
        raise KeyError(
            f"Unknown voting strategy '{name_or_fn}'. Known: {sorted(VOTING_STRATEGIES)}."
        )
    return VOTING_STRATEGIES[key]
