"""Voting strategy + Krippendorff α tests (pure functions, no LLM)."""
from __future__ import annotations

import math

import pytest

from cross_judge import Verdict
from cross_judge.voting import (
    agreement_pct,
    get_voting_strategy,
    krippendorff_alpha,
    majority_vote,
    unanimous,
)


def _v(name: str, kind: str, conf: float = 1.0, error: str | None = None) -> Verdict:
    return Verdict(critic_id=name, kind=kind, confidence=conf, reasoning="", error=error)


# --- majority_vote ------------------------------------------------------------


def test_majority_vote_2_keep_1_reject():
    """Task spec: 3 critics, 2 KEEP + 1 REJECT → KEEP."""
    vs = [_v("a", "KEEP", 0.9), _v("b", "KEEP", 0.85), _v("c", "REJECT", 0.7)]
    label, disagree = majority_vote(vs)
    assert label == "KEEP"
    assert disagree is True


def test_majority_vote_unanimous():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "KEEP")]
    label, disagree = majority_vote(vs)
    assert label == "KEEP"
    assert disagree is False


def test_majority_vote_tie_priority():
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    label, _ = majority_vote(vs, priority=["REJECT", "KEEP"])
    assert label == "REJECT"


def test_majority_vote_fallback_no_valid():
    vs = [_v("a", "X", error="boom")]
    label, disagree = majority_vote(vs, fallback="NO_DATA")
    assert label == "NO_DATA"
    assert disagree is False


# --- unanimous ----------------------------------------------------------------


def test_unanimous_all_agree():
    vs = [_v("a", "KEEP"), _v("b", "KEEP")]
    label, disagree = unanimous(vs)
    assert label == "KEEP"
    assert disagree is False


def test_unanimous_disagreement_returns_fallback():
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    label, disagree = unanimous(vs, fallback="MIXED")
    assert label == "MIXED"
    assert disagree is True


# --- agreement_pct ------------------------------------------------------------


def test_agreement_pct_full():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "KEEP")]
    assert agreement_pct(vs, "KEEP") == 1.0


def test_agreement_pct_partial():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "REJECT")]
    assert abs(agreement_pct(vs, "KEEP") - 2 / 3) < 1e-9


def test_agreement_pct_excludes_errored():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "X", error="boom")]
    assert agreement_pct(vs, "KEEP") == 1.0  # errored excluded → 2/2


def test_agreement_pct_empty():
    assert agreement_pct([], "KEEP") == 0.0


# --- krippendorff_alpha -------------------------------------------------------


def test_krippendorff_perfect_agreement():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "KEEP")]
    alpha = krippendorff_alpha(vs)
    assert alpha == 1.0


def test_krippendorff_total_disagreement_two_critics():
    """2 critics, different labels → α = 0.0 (random chance for 2 categories of 1 each)."""
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    alpha = krippendorff_alpha(vs)
    # With 2 raters & 2 different labels, observed disagreement = 1, expected = 1
    # → α = 0.0 (chance-level)
    assert alpha is not None
    assert abs(alpha) < 1e-9


def test_krippendorff_majority_agreement_three_critics():
    """3 critics: 2 KEEP + 1 REJECT.
    Observed disagreement = 2 pairs out of 3 → 2/3.
    Expected by chance = 1 - (2/3 * 1/2 + 1/3 * 0/2) = 1 - 1/3 = 2/3.
    → α = 1 - (2/3)/(2/3) = 0.0."""
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "REJECT")]
    alpha = krippendorff_alpha(vs)
    assert alpha is not None
    assert abs(alpha) < 1e-9


def test_krippendorff_three_keep_one_reject():
    """4 critics: 3 KEEP + 1 REJECT.
    Pairs: C(4,2)=6. Disagreeing pairs: 3 (each REJECT with each KEEP).
    Same pairs: C(3,2)=3.
    D_observed = 3/6 = 0.5
    D_expected = 1 - (3/4*2/3 + 1/4*0/3) = 1 - 0.5 = 0.5
    α = 1 - 0.5/0.5 = 0.0
    """
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "KEEP"), _v("d", "REJECT")]
    alpha = krippendorff_alpha(vs)
    assert alpha is not None
    assert abs(alpha) < 1e-9


def test_krippendorff_too_few_raters():
    """α undefined for < 2 critics."""
    assert krippendorff_alpha([]) is None
    assert krippendorff_alpha([_v("a", "KEEP")]) is None


def test_krippendorff_returns_in_range():
    """α should be in [-1, 1]."""
    vs = [_v("a", "X"), _v("b", "Y"), _v("c", "Z"), _v("d", "X")]
    alpha = krippendorff_alpha(vs)
    assert alpha is not None
    assert -1.0 <= alpha <= 1.0


def test_krippendorff_excludes_errored():
    """Errored verdicts shouldn't tank α."""
    vs = [
        _v("a", "KEEP"),
        _v("b", "KEEP"),
        _v("c", "X", error="boom"),
    ]
    alpha = krippendorff_alpha(vs)
    # Only 2 valid critics, both KEEP → perfect agreement
    assert alpha == 1.0


# --- registry -----------------------------------------------------------------


def test_get_voting_strategy_by_name():
    assert get_voting_strategy("majority") is majority_vote
    assert get_voting_strategy("MAJORITY") is majority_vote
    assert get_voting_strategy("unanimous") is unanimous


def test_get_voting_strategy_passes_callable():
    assert get_voting_strategy(majority_vote) is majority_vote


def test_get_voting_strategy_unknown_raises():
    with pytest.raises(KeyError):
        get_voting_strategy("not-a-strategy")
