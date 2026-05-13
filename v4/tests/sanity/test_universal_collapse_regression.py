"""A3 universal collapse — cross-system rescaling sanity."""
from __future__ import annotations

import pytest

from sanity_helpers import RESULTS_DIR, load_json_or_skip


RESULTS_FILE = RESULTS_DIR / "A3_universal_collapse.json"


@pytest.mark.sanity
def test_universal_collapse_min_systems():
    """At least 6 systems must have ok status."""
    d = load_json_or_skip(RESULTS_FILE)
    ok = [k for k, v in d.items() if isinstance(v, dict) and v.get("status") == "ok"]
    assert len(ok) >= 6, f"only {len(ok)} systems ok: {ok}"


@pytest.mark.sanity
def test_universal_collapse_alpha_ranges():
    """Every system's alpha_known must be in plausible (1.0, 5.0)."""
    d = load_json_or_skip(RESULTS_FILE)
    for k, v in d.items():
        if not isinstance(v, dict):
            continue
        if v.get("status") != "ok":
            continue
        alpha = v.get("alpha_known")
        assert isinstance(alpha, (int, float)), f"{k} alpha_known missing: {v}"
        assert 1.0 < alpha < 5.0, f"{k} alpha out of plausible range: {alpha}"


@pytest.mark.sanity
def test_universal_collapse_s_star_positive():
    """Every system's s_star_99pctl must be > 0."""
    d = load_json_or_skip(RESULTS_FILE)
    for k, v in d.items():
        if not isinstance(v, dict) or v.get("status") != "ok":
            continue
        s_star = v.get("s_star_99pctl")
        assert isinstance(s_star, (int, float)), f"{k} s_star missing: {v}"
        assert s_star > 0, f"{k} s_star non-positive: {s_star}"
