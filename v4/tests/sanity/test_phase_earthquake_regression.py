"""Phase 1 — Earthquake (Gutenberg-Richter): regression on b-value + n_above_Mc."""
from __future__ import annotations

from pathlib import Path

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, deep_find_alpha


RESULTS_FILE = VALIDATION_DIR / "soc-earthquake" / "gr_results.json"


@pytest.mark.sanity
def test_earthquake_b_value_band():
    """b ∈ [1.05, 1.12] on the canonical 2020-2025 USGS pull."""
    d = load_json_or_skip(RESULTS_FILE)
    b = d.get("b_value")
    assert isinstance(b, (int, float)), f"b_value missing/non-numeric: {b}"
    assert 1.05 <= b <= 1.12, f"b-value out of expected band: {b}"


@pytest.mark.sanity
def test_earthquake_n_above_Mc():
    """At least 30,000 events above Mc."""
    d = load_json_or_skip(RESULTS_FILE)
    n = d.get("n_above_Mc")
    assert isinstance(n, int), f"n_above_Mc missing/non-int: {n}"
    assert n > 30000, f"n_above_Mc too small: {n}"


@pytest.mark.sanity
def test_earthquake_verdict_not_failed():
    """verdict should not be a rejection."""
    d = load_json_or_skip(RESULTS_FILE)
    verdict = d.get("verdict", "")
    assert isinstance(verdict, str)
    assert verdict.lower() not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"


@pytest.mark.sanity
def test_earthquake_clauset_alpha_present():
    """A nested clauset_powerlaw_fit.alpha must be discoverable and finite."""
    d = load_json_or_skip(RESULTS_FILE)
    alpha = deep_find_alpha(d)
    assert alpha is not None, "no alpha found anywhere in earthquake results"
    assert 1.0 < alpha < 5.0, f"alpha out of plausible range: {alpha}"
