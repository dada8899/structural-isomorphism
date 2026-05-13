"""Phase 10 — NIFC wildfire (Drossel-Schwabl forest-fire) regression."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get


RESULTS_FILE = VALIDATION_DIR / "soc-wildfire" / "wildfire_results.json"


@pytest.mark.sanity
def test_wildfire_alpha_band():
    """alpha ∈ [1.3, 1.9]."""
    d = load_json_or_skip(RESULTS_FILE)
    pl = d.get("powerlaw_fit") or {}
    alpha = robust_get(pl, ["alpha", "alpha_fit"])
    assert isinstance(alpha, (int, float)), f"alpha missing: {pl}"
    assert 1.3 <= alpha <= 1.9, f"wildfire alpha out of band: {alpha}"


@pytest.mark.sanity
def test_wildfire_n_fires():
    """n_total_fires > 20000."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_total_fires", "n_total"])
    assert isinstance(n, int), f"n_total_fires missing: {n}"
    assert n > 20000, f"n_total_fires too small: {n}"


@pytest.mark.sanity
def test_wildfire_verdict_not_rejected():
    d = load_json_or_skip(RESULTS_FILE)
    verdict = (d.get("verdict") or "").lower()
    assert verdict not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"
