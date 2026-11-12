"""Phase 8 — FDIC bank failures regression."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get


RESULTS_FILE = VALIDATION_DIR / "soc-bank-failures" / "bank_results.json"


@pytest.mark.sanity
def test_bank_alpha_band():
    """alpha ∈ [1.7, 2.1]."""
    d = load_json_or_skip(RESULTS_FILE)
    pl = d.get("powerlaw_fit_assets") or d.get("powerlaw_fit") or {}
    alpha = robust_get(pl, ["alpha", "alpha_fit"])
    assert isinstance(alpha, (int, float)), f"alpha missing: {pl}"
    assert 1.7 <= alpha <= 2.1, f"bank alpha out of band: {alpha}"


@pytest.mark.sanity
def test_bank_n_failures():
    """n_failures > 3500."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_failures", "n_total"])
    assert isinstance(n, int), f"n_failures missing: {n}"
    assert n > 3500, f"n_failures too small: {n}"


@pytest.mark.sanity
def test_bank_verdict_not_rejected():
    d = load_json_or_skip(RESULTS_FILE)
    verdict = (d.get("verdict") or "").lower()
    assert verdict not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"
