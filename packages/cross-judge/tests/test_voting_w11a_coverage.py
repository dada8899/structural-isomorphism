"""W11-A coverage gap fillers for voting.py.

Targets uncovered branches in `cross_judge.voting`:
- majority_vote insertion-order tiebreaker (no priority list): lines 86-90
- krippendorff_alpha total_pairs == 0 fallthrough: line 165
- krippendorff_alpha total == 1 sentinel: line 173
- get_voting_strategy callable passthrough: line 195
- agreement_pct empty-input zero return
- unanimous fallback when all errored
"""
from __future__ import annotations

from cross_judge import Verdict
from cross_judge.voting import (
    VOTING_STRATEGIES,
    agreement_pct,
    get_voting_strategy,
    krippendorff_alpha,
    majority_vote,
    unanimous,
)


def _v(name: str, kind: str, conf: float = 1.0, error: str | None = None) -> Verdict:
    return Verdict(critic_id=name, kind=kind, confidence=conf, reasoning="", error=error)


# --- majority_vote insertion-order tiebreaker (lines 86-90) ------------------


def test_majority_vote_tie_no_priority_uses_insertion_order():
    """Tie with no priority list → first label by insertion order wins."""
    vs = [_v("a", "REJECT"), _v("b", "KEEP")]
    label, disagree = majority_vote(vs)
    # Both have count 1. With no priority, the first verdict's kind ("REJECT") wins.
    assert label == "REJECT"
    assert disagree is True


def test_majority_vote_tie_priority_missing_label_falls_back_to_insertion():
    """Priority list exists but contains none of the tied labels → falls
    through to insertion-order branch (lines 86-90)."""
    vs = [_v("a", "FOO"), _v("b", "BAR")]
    label, disagree = majority_vote(vs, priority=["BAZ", "QUX"])  # none tied
    assert label in ("FOO", "BAR")
    assert disagree is True
    # Insertion order means FOO comes first
    assert label == "FOO"


def test_majority_vote_three_way_tie_no_priority():
    vs = [_v("a", "X"), _v("b", "Y"), _v("c", "Z")]
    label, _ = majority_vote(vs)
    assert label == "X"  # first by insertion


def test_majority_vote_all_errored_returns_fallback():
    vs = [_v("a", "K", error="oops"), _v("b", "K", error="oops")]
    label, disagree = majority_vote(vs, fallback="UNKNOWN")
    assert label == "UNKNOWN"
    assert disagree is False


# --- unanimous ---------------------------------------------------------------


def test_unanimous_all_errored_returns_fallback_disagree_true():
    vs = [_v("a", "K", error="x"), _v("b", "K", error="x")]
    label, disagree = unanimous(vs, fallback="UNCLEAR")
    # No valid labels → labels set is empty, len(labels) != 1 → fallback path
    assert label == "UNCLEAR"
    assert disagree is True


def test_unanimous_single_valid_critic():
    vs = [_v("a", "KEEP")]
    label, disagree = unanimous(vs)
    assert label == "KEEP"
    assert disagree is False


def test_unanimous_disagree():
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    label, disagree = unanimous(vs)
    assert disagree is True


# --- agreement_pct -----------------------------------------------------------


def test_agreement_pct_no_valid_returns_zero():
    vs = [_v("a", "K", error="x")]
    assert agreement_pct(vs, "K") == 0.0


def test_agreement_pct_empty_returns_zero():
    assert agreement_pct([], "K") == 0.0


def test_agreement_pct_partial():
    vs = [_v("a", "K"), _v("b", "K"), _v("c", "R"), _v("d", "K", error="x")]
    # 3 valid, 2 match "K"
    assert agreement_pct(vs, "K") == 2 / 3


# --- krippendorff_alpha edge cases ------------------------------------------


def test_krippendorff_alpha_fewer_than_two_returns_none():
    assert krippendorff_alpha([]) is None
    assert krippendorff_alpha([_v("a", "K")]) is None


def test_krippendorff_alpha_all_errored_returns_none():
    vs = [_v("a", "K", error="x"), _v("b", "R", error="x")]
    assert krippendorff_alpha(vs) is None


def test_krippendorff_alpha_unanimous_returns_one():
    vs = [_v("a", "K"), _v("b", "K"), _v("c", "K")]
    a = krippendorff_alpha(vs)
    assert a == 1.0


def test_krippendorff_alpha_perfect_disagreement_two_critics():
    vs = [_v("a", "K"), _v("b", "R")]
    a = krippendorff_alpha(vs)
    assert a is not None
    # 2 critics, 2 different labels: D_obs=1, D_exp=1.0 → α=0
    assert a == 0.0


def test_krippendorff_alpha_clamped_to_minus_one():
    """Systematic disagreement scenario, but α floor is -1.0."""
    # 4 critics, all 4 different labels: max disagreement on 4 raters
    vs = [_v("a", "W"), _v("b", "X"), _v("c", "Y"), _v("d", "Z")]
    a = krippendorff_alpha(vs)
    assert a is not None
    assert -1.0 <= a <= 1.0


def test_krippendorff_alpha_three_critic_mix():
    """3 critics: K, K, R — partial agreement."""
    vs = [_v("a", "K"), _v("b", "K"), _v("c", "R")]
    a = krippendorff_alpha(vs)
    assert a is not None
    # Some positive (one pair agrees) but well below 1.0
    assert 0 < a < 1.0


# --- get_voting_strategy + VOTING_STRATEGIES --------------------------------


def test_get_voting_strategy_by_name():
    assert get_voting_strategy("majority") is majority_vote
    assert get_voting_strategy("unanimous") is unanimous


def test_get_voting_strategy_case_insensitive():
    assert get_voting_strategy("MAJORITY") is majority_vote
    assert get_voting_strategy("Unanimous") is unanimous


def test_get_voting_strategy_unknown_raises_keyerror():
    import pytest

    with pytest.raises(KeyError) as exc:
        get_voting_strategy("nonexistent_strategy_xyz")
    assert "Unknown voting strategy" in str(exc.value)


def test_get_voting_strategy_callable_passthrough():
    """Line 195: passing a callable returns it unchanged."""

    def custom(verdicts):
        return ("CUSTOM", False)

    fn = get_voting_strategy(custom)
    assert fn is custom


def test_voting_strategies_dict_has_expected_keys():
    assert "majority" in VOTING_STRATEGIES
    assert "unanimous" in VOTING_STRATEGIES
