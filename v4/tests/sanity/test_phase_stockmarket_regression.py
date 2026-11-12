"""Phase 2 — Stock market (S&P 500 daily returns) regression."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get, deep_find_alpha


RESULTS_FILE = VALIDATION_DIR / "soc-stockmarket" / "gr_results.json"


@pytest.mark.sanity
def test_stockmarket_alpha_band():
    """alpha ∈ [2.8, 3.1]."""
    d = load_json_or_skip(RESULTS_FILE)
    alpha = deep_find_alpha(d)
    assert alpha is not None, "no alpha found in stockmarket results"
    assert 2.8 <= alpha <= 3.1, f"alpha out of band: {alpha}"


@pytest.mark.sanity
def test_stockmarket_n_returns():
    """n_returns > 9000."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_returns", "n_total"])
    assert isinstance(n, int), f"n missing: {n}"
    assert n > 9000, f"n_returns too small: {n}"


@pytest.mark.sanity
def test_stockmarket_within_prediction_flag():
    """If `alpha_within_prediction` exists it must be True."""
    d = load_json_or_skip(RESULTS_FILE)
    flag = d.get("alpha_within_prediction")
    if flag is None:
        pytest.skip("alpha_within_prediction not present")
    assert flag is True, "stockmarket alpha not within prediction"
