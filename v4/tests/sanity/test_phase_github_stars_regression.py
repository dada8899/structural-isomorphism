"""Phase 6 — GitHub stargazers (Barabási-Albert preferential attachment) regression."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip, robust_get


RESULTS_FILE = VALIDATION_DIR / "soc-github-stars" / "github_results.json"


@pytest.mark.sanity
def test_github_alpha_band():
    """alpha ∈ [2.7, 3.1]."""
    d = load_json_or_skip(RESULTS_FILE)
    pl = d.get("powerlaw_fit") or {}
    alpha = robust_get(pl, ["alpha", "alpha_fit"])
    assert isinstance(alpha, (int, float)), f"alpha missing: {pl}"
    assert 2.7 <= alpha <= 3.1, f"github alpha out of band: {alpha}"


@pytest.mark.sanity
def test_github_n_repos():
    """n_repos > 8000."""
    d = load_json_or_skip(RESULTS_FILE)
    n = robust_get(d, ["n_repos", "n_total"])
    assert isinstance(n, int), f"n_repos missing: {n}"
    assert n > 8000, f"n_repos too small: {n}"


@pytest.mark.sanity
def test_github_verdict_not_rejected():
    d = load_json_or_skip(RESULTS_FILE)
    verdict = (d.get("verdict") or "").lower()
    assert verdict not in ("fail", "rejected", "failed"), f"bad verdict: {verdict}"
