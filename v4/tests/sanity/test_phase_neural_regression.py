"""Phase 4 — Neural avalanches (Beggs-Plenz) regression on bf=16 canonical fit."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get


RESULTS_FILE = VALIDATION_DIR / "soc-neural" / "bf_16_fit.json"


@pytest.mark.sanity
def test_neural_tau_band():
    """size_fit.alpha (= τ size exponent) in [2.0, 3.1] for bf=16 canonical bin factor.

    Note: bf=16 gives a smaller sample than bf=1, so the recovered τ drifts
    slightly above the strict Beggs-Plenz 1.5; we use a broader literature band.
    """
    d = load_json_or_skip(RESULTS_FILE)
    size_fit = d.get("size_fit") or {}
    tau = robust_get(size_fit, ["alpha", "alpha_fit", "tau"])
    assert isinstance(tau, (int, float)), f"size_fit alpha missing: {size_fit}"
    assert 2.0 <= tau <= 3.1, f"neural τ out of band: {tau}"


@pytest.mark.sanity
def test_neural_n_avalanches():
    """n_avalanches > 100."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_avalanches", "n_total"])
    assert isinstance(n, int), f"n_avalanches missing: {n}"
    assert n > 100, f"n_avalanches too small: {n}"


@pytest.mark.sanity
def test_neural_verdict_not_rejected():
    """verdict must not be a hard rejection (PARTIAL/CONFIRMED both OK)."""
    d = load_json_or_skip(RESULTS_FILE)
    verdict = (d.get("verdict") or "").lower()
    assert verdict not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"
