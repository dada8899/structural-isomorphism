"""W11-A coverage gap fillers for v4.lib.multitest_correction.

Targets uncovered branches:
- bonferroni([]) empty-input early return (line 87)
- benjamini_hochberg([]) empty-input early return (line 155)
- apply_corrections wrapper (returns dict of three results)
- CorrectionResult.to_dict roundtrip
- NaN / clipping in _clean_pvalues
"""
from __future__ import annotations

import math

import numpy as np
import pytest

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v4.lib.multitest_correction import (  # noqa: E402
    CorrectionResult,
    apply_corrections,
    benjamini_hochberg,
    bonferroni,
    bonferroni_holm,
)


# --- empty-input early returns ----------------------------------------------


def test_bonferroni_empty_input_returns_zero_rows():
    r = bonferroni([])
    assert r.n_tests == 0
    assert r.p_adjusted == []
    assert r.reject == []
    assert r.p_raw == []
    assert r.method == "bonferroni"


def test_benjamini_hochberg_empty_input_returns_zero_rows():
    r = benjamini_hochberg([])
    assert r.n_tests == 0
    assert r.p_adjusted == []
    assert r.reject == []
    assert r.method == "benjamini-hochberg"


def test_bonferroni_holm_empty_input_returns_zero_rows():
    r = bonferroni_holm([])
    assert r.n_tests == 0
    assert r.method == "bonferroni-holm"


# --- apply_corrections wrapper -----------------------------------------------


def test_apply_corrections_returns_three_methods():
    pvalues = [0.001, 0.04, 0.5, 0.9]
    results = apply_corrections(pvalues, alpha=0.05)
    assert "bonferroni" in results
    assert "bonferroni-holm" in results
    assert "benjamini-hochberg" in results
    for v in results.values():
        assert isinstance(v, CorrectionResult)
        assert v.n_tests == 4


def test_apply_corrections_empty_input():
    results = apply_corrections([])
    assert all(v.n_tests == 0 for v in results.values())


# --- CorrectionResult.to_dict -----------------------------------------------


def test_correction_result_to_dict_roundtrip():
    r = bonferroni_holm([0.01, 0.03, 0.5])
    d = r.to_dict()
    assert d["method"] == "bonferroni-holm"
    assert d["n_tests"] == 3
    assert len(d["p_raw"]) == 3
    assert len(d["p_adjusted"]) == 3
    assert len(d["reject"]) == 3
    # Mutating returned lists should not mutate the dataclass
    d["p_raw"].append(0.99)
    assert len(r.p_raw) == 3


# --- _clean_pvalues edge cases -----------------------------------------------


def test_bonferroni_handles_nan():
    """NaN inputs become 1.0 (never reject)."""
    r = bonferroni([float("nan"), 0.01])
    assert r.reject[0] is False or r.reject[0] == False  # NaN→1.0→stays at 1.0
    # 0.01 * 2 = 0.02 ≤ 0.05 → True
    assert r.reject[1] is True


def test_bonferroni_clips_above_one():
    """p > 1 gets clipped to 1.0."""
    r = bonferroni([1.5, 0.01])
    assert r.p_raw[0] == 1.0  # clipped


def test_bonferroni_clips_below_zero():
    r = bonferroni([-0.5, 0.01])
    assert r.p_raw[0] == 0.0


def test_bh_handles_unsorted_input():
    """BH preserves output order matching input order."""
    pvals = [0.5, 0.01, 0.04]
    r = benjamini_hochberg(pvals, alpha=0.05)
    # Adjusted values should map back to input positions
    assert len(r.p_adjusted) == 3
    # The 0.01 (smallest, index 1) should give smallest adjusted
    assert r.p_adjusted[1] <= r.p_adjusted[0]
    assert r.p_adjusted[1] <= r.p_adjusted[2]


def test_bonferroni_holm_monotone_step_down():
    """Holm enforces monotone non-decreasing adjusted p-values when sorted."""
    pvals = [0.001, 0.01, 0.02, 0.03, 0.5]
    r = bonferroni_holm(pvals, alpha=0.05)
    # Sort by input
    order = np.argsort(pvals)
    sorted_adj = [r.p_adjusted[i] for i in order]
    for i in range(1, len(sorted_adj)):
        assert sorted_adj[i] >= sorted_adj[i - 1] - 1e-9


def test_bonferroni_strict_dominates_holm_when_significant():
    """Bonferroni adjusted >= Holm adjusted (Holm is uniformly more powerful)."""
    pvals = [0.001, 0.01, 0.02, 0.04, 0.5]
    bonf = bonferroni(pvals)
    holm = bonferroni_holm(pvals)
    for b, h in zip(bonf.p_adjusted, holm.p_adjusted):
        assert b >= h - 1e-9


def test_bh_more_powerful_than_holm():
    """In typical cases, BH rejects at least as many as Holm."""
    pvals = [0.001, 0.005, 0.01, 0.02, 0.04, 0.5]
    bh = benjamini_hochberg(pvals)
    holm = bonferroni_holm(pvals)
    assert sum(bh.reject) >= sum(holm.reject)


def test_all_zeros_all_reject():
    pvals = [0.0, 0.0, 0.0]
    bonf = bonferroni(pvals, alpha=0.05)
    assert all(bonf.reject)
    holm = bonferroni_holm(pvals, alpha=0.05)
    assert all(holm.reject)
    bh = benjamini_hochberg(pvals, alpha=0.05)
    assert all(bh.reject)


def test_all_ones_no_reject():
    pvals = [1.0, 1.0, 1.0]
    for fn in (bonferroni, bonferroni_holm, benjamini_hochberg):
        r = fn(pvals, alpha=0.05)
        assert not any(r.reject)


def test_single_pvalue_each_method():
    for fn, name in (
        (bonferroni, "bonferroni"),
        (bonferroni_holm, "bonferroni-holm"),
        (benjamini_hochberg, "benjamini-hochberg"),
    ):
        r = fn([0.04], alpha=0.05)
        assert r.method == name
        assert r.n_tests == 1
        assert r.reject == [True]
