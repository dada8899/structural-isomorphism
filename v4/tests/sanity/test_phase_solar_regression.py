"""Phase 11 — NOAA GOES solar flare X-ray (Lu-Hamilton SOC) regression."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get


RESULTS_FILE = VALIDATION_DIR / "soc-solar" / "solar_results.json"


@pytest.mark.sanity
def test_solar_alpha_band():
    """peak_flux alpha ∈ [2.1, 2.3]."""
    d = load_json_or_skip(RESULTS_FILE)
    pl = d.get("powerlaw_fit_peak_flux") or d.get("powerlaw_fit") or {}
    alpha = robust_get(pl, ["alpha", "alpha_fit"])
    assert isinstance(alpha, (int, float)), f"alpha missing: {pl}"
    assert 2.1 <= alpha <= 2.3, f"solar alpha out of band: {alpha}"


@pytest.mark.sanity
def test_solar_n_flares():
    """n_total_flares > 25000."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_total_flares", "n_total"])
    assert isinstance(n, int), f"n_total_flares missing: {n}"
    assert n > 25000, f"n_total_flares too small: {n}"


@pytest.mark.sanity
def test_solar_verdict_not_rejected():
    d = load_json_or_skip(RESULTS_FILE)
    verdict = (d.get("verdict") or "").lower()
    assert verdict not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"
