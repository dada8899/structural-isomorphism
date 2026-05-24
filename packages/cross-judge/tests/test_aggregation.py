"""Aggregation strategy tests (pure functions, no LLM)."""
from __future__ import annotations

import pytest

from cross_judge import Verdict, first_disagreement, majority, unanimous, weighted
from cross_judge.aggregation import avg_confidence, get_strategy


def _v(rid: str, verdict: str, conf: float = 1.0, error: str | None = None) -> Verdict:
    return Verdict(reviewer_id=rid, verdict=verdict, confidence=conf, rationale="", error=error)


# --- majority -----------------------------------------------------------------


def test_majority_clear_winner():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "REJECT")]
    label, disagree = majority(vs)
    assert label == "KEEP"
    assert disagree is True


def test_majority_unanimous():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "KEEP")]
    label, disagree = majority(vs)
    assert label == "KEEP"
    assert disagree is False


def test_majority_tie_priority():
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    label, _ = majority(vs, priority=["REJECT", "KEEP"])
    assert label == "REJECT"


def test_majority_tie_first_seen():
    vs = [_v("a", "KEEP"), _v("b", "REJECT")]
    label, _ = majority(vs)
    assert label == "KEEP"  # first verdict's label wins on tie when no priority given


def test_majority_no_valid_verdicts():
    vs = [_v("a", "x", error="boom"), _v("b", "y", error="boom")]
    label, disagree = majority(vs, fallback="NO_DATA")
    assert label == "NO_DATA"
    assert disagree is False


def test_majority_ignores_errored_verdicts():
    vs = [_v("a", "KEEP"), _v("b", "KEEP"), _v("c", "REJECT", error="net")]
    label, disagree = majority(vs)
    assert label == "KEEP"
    assert disagree is False  # only valid verdicts compared


# --- unanimous ----------------------------------------------------------------


def test_unanimous_all_agree():
    vs = [_v("a", "PASS"), _v("b", "PASS")]
    label, disagree = unanimous(vs)
    assert label == "PASS"
    assert disagree is False


def test_unanimous_disagreement():
    vs = [_v("a", "PASS"), _v("b", "FAIL")]
    label, disagree = unanimous(vs, fallback="MIXED")
    assert label == "MIXED"
    assert disagree is True


# --- weighted -----------------------------------------------------------------


def test_weighted_confidence_breaks_tie():
    vs = [_v("a", "KEEP", conf=0.9), _v("b", "REJECT", conf=0.4)]
    label, _ = weighted(vs)
    assert label == "KEEP"


def test_weighted_explicit_weights():
    # equal confidence, but b has 10x weight
    vs = [_v("a", "KEEP", conf=0.9), _v("b", "REJECT", conf=0.9)]
    label, _ = weighted(vs, weights={"a": 1.0, "b": 10.0})
    assert label == "REJECT"


def test_weighted_no_confidence_flag():
    # if use_confidence=False, weights override
    vs = [_v("a", "KEEP", conf=0.1), _v("b", "REJECT", conf=0.99)]
    label, _ = weighted(vs, weights={"a": 5.0, "b": 1.0}, use_confidence=False)
    assert label == "KEEP"


# --- first_disagreement -------------------------------------------------------


def test_first_disagreement_all_agree():
    vs = [_v("a", "X"), _v("b", "X"), _v("c", "X")]
    label, disagree = first_disagreement(vs)
    assert label == "X"
    assert disagree is False


def test_first_disagreement_diff():
    vs = [_v("a", "X"), _v("b", "Y")]
    label, disagree = first_disagreement(vs, disagree_label="MIXED")
    assert label == "MIXED"
    assert disagree is True


# --- avg_confidence -----------------------------------------------------------


def test_avg_confidence():
    vs = [_v("a", "X", 0.8), _v("b", "X", 0.6), _v("c", "X", 0.0, error="boom")]
    # errored excluded
    assert abs(avg_confidence(vs) - 0.7) < 1e-9


def test_avg_confidence_empty():
    assert avg_confidence([]) == 0.0


# --- registry -----------------------------------------------------------------


def test_get_strategy_by_name():
    assert get_strategy("majority") is majority
    assert get_strategy("MAJORITY") is majority


def test_get_strategy_passes_through_callable():
    assert get_strategy(majority) is majority


def test_get_strategy_unknown_raises():
    with pytest.raises(KeyError):
        get_strategy("not-a-strategy")
