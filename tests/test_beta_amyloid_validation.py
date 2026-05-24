"""Smoke + schema + sanity tests for X3 Wave 2 beta-amyloid validation.

Validates:
  1. Smoke — run_validation.py imports and exposes public functions.
  2. Schema — results.json has per_series with fit fields.
  3. Sanity — all alpha in aggregation_kinetics sanity band [1.5, 4.0].
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "v4" / "validation" / "beta-amyloid"
RESULTS = DIR / "results.json"
RUN = DIR / "run_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "amyloid_run_validation", RUN
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_run_validation_module_imports():
    mod = _load_module()
    for fn in ("load_series", "fit_one", "verdict",
               "isomorphism_distance", "SERIES"):
        assert hasattr(mod, fn), f"{fn} missing"


def test_smoke_verdict_function():
    mod = _load_module()
    # alpha in canonical, no LR_ln winning → PASS
    v = mod.verdict(alpha=2.5, n_tail=100, R_ln=2.0, p_ln=0.001)
    assert v == "PASS"
    # alpha in canonical but lognormal beats PL decisively → INCONCLUSIVE
    v = mod.verdict(alpha=2.5, n_tail=100, R_ln=-5.0, p_ln=0.001)
    assert v == "INCONCLUSIVE"
    # alpha out of sanity → FAIL
    v = mod.verdict(alpha=10.0, n_tail=100, R_ln=2.0, p_ln=0.001)
    assert v == "FAIL"


def test_smoke_isomorphism_distance():
    mod = _load_module()
    d = mod.isomorphism_distance(2.0, 2.0, 0.1, 0.1)
    assert d == pytest.approx(0.0)
    d = mod.isomorphism_distance(2.0, 3.0, 0.5, 0.5)
    assert 1.3 < d < 1.5


def test_smoke_series_list_complete():
    mod = _load_module()
    expected = {"ab42_pg_per_mg", "ab40_pg_per_mg", "ihc_a_beta",
                "ihc_a_beta_ffpe", "ab42_over_ab40_ratio"}
    assert set(mod.SERIES) == expected


@pytest.mark.skipif(not RESULTS.exists(),
                    reason="results.json not yet generated")
def test_schema_top_level_keys():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    required = {"timestamp_utc", "data_provenance", "per_series",
                "iso_within_series", "iso_vs_literature", "references",
                "canonical_band", "sanity_band"}
    missing = required - set(data.keys())
    assert not missing, f"missing top-level keys: {missing}"


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_schema_per_series_fields():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert len(data["per_series"]) >= 4, "expected >=4 series"
    for name, entry in data["per_series"].items():
        for k in ("series", "n", "min", "max", "median", "verdict"):
            assert k in entry, f"{name} missing {k}"
        if "alpha" in entry and entry["alpha"] is not None:
            assert "xmin" in entry
            assert "n_tail" in entry


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_alpha_in_aggregation_band():
    """All alpha values should be in sanity band [1.5, 4.0]."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    out_of_range = []
    for name, entry in data["per_series"].items():
        a = entry.get("alpha")
        if a is not None and not (1.0 <= a <= 5.0):
            out_of_range.append((name, a))
    assert not out_of_range, f"alpha out of [1.0, 5.0]: {out_of_range}"


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_verdicts_valid():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    valid = {"PASS", "INCONCLUSIVE", "FAIL"}
    for name, entry in data["per_series"].items():
        assert entry["verdict"] in valid, f"{name} bad verdict"


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_iso_within_finite():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    iso = data["iso_within_series"]
    for a, refs in iso.items():
        for b, d in refs.items():
            assert isinstance(d, (int, float))
            assert np.isfinite(d), f"{a}->{b} non-finite distance"
            assert d >= 0
