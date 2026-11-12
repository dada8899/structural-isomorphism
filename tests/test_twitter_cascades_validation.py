"""Smoke + schema + sanity tests for X3 Wave 2 Twitter cascade validation.

Validates:
  1. Smoke — run_validation.py module imports and exposes public functions.
  2. Schema — results.json contains expected fit + verdict + isomorphism keys.
  3. Sanity — alpha falls within preferential_attachment sanity band [1.5, 3.5].

If results.json is missing (validation not yet run), schema and sanity tests
are skipped with a clear message. Smoke always runs.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "v4" / "validation" / "twitter-cascades"
RESULTS = DIR / "results.json"
RUN = DIR / "run_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "twitter_run_validation", RUN
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_run_validation_module_imports():
    """run_validation.py imports and exposes public functions."""
    mod = _load_module()
    for fn in ("load_cascade_sizes", "fit_and_compare",
               "omori_probe", "verdict", "isomorphism_distance"):
        assert hasattr(mod, fn), f"{fn}() missing"


def test_smoke_verdict_function():
    """verdict() returns 'PASS' for canonical-band alpha + good LR signs."""
    mod = _load_module()
    v = mod.verdict(alpha=2.1, n_tail=10000,
                    R_ln=2.0, p_ln=0.001,
                    R_exp=20.0, p_exp=0.0)
    assert v == "PASS"
    # alpha out of sanity band → FAIL
    v = mod.verdict(alpha=5.0, n_tail=10000,
                    R_ln=2.0, p_ln=0.001,
                    R_exp=20.0, p_exp=0.0)
    assert v == "FAIL"
    # n_tail too small → INCONCLUSIVE
    v = mod.verdict(alpha=2.1, n_tail=10,
                    R_ln=None, p_ln=None,
                    R_exp=None, p_exp=None)
    assert v == "INCONCLUSIVE"


def test_smoke_isomorphism_distance():
    mod = _load_module()
    # Identical with same SE → distance 0
    d = mod.isomorphism_distance(2.0, 2.0, 0.1, 0.1)
    assert d == pytest.approx(0.0)
    # 1 unit apart, both SE=0.5 → pooled SE ~0.707, distance ~1.414
    d = mod.isomorphism_distance(2.0, 3.0, 0.5, 0.5)
    assert 1.3 < d < 1.5


@pytest.mark.skipif(not RESULTS.exists(),
                    reason="results.json not yet generated; "
                           "run v4/validation/twitter-cascades/run_validation.py first")
def test_schema_top_level_keys():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    required = {"timestamp_utc", "data_provenance", "n_cascades", "fit",
                "references", "isomorphism_distances",
                "canonical_band", "sanity_band", "verdict"}
    missing = required - set(data.keys())
    assert not missing, f"missing top-level keys: {missing}"


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_schema_fit_fields():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    fit = data["fit"]
    for k in ("alpha", "alpha_se", "xmin", "n_tail", "ks"):
        assert k in fit, f"fit missing {k}"


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_alpha_in_pref_attach_band():
    """alpha should land in preferential_attachment sanity band [1.5, 3.5]."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    alpha = data["fit"].get("alpha")
    assert alpha is not None
    assert 1.5 <= alpha <= 3.5, (
        f"alpha={alpha:.3f} outside preferential_attachment sanity band"
    )


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_verdict_value():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert data["verdict"] in ("PASS", "INCONCLUSIVE", "FAIL")


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_n_cascades_large():
    """SNAP Higgs Twitter has 41K origins; ensure full data ingested."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert data["n_cascades"] >= 10000, (
        f"only {data['n_cascades']} cascades loaded — likely truncated"
    )


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_isomorphism_distances_finite():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    iso = data["isomorphism_distances"]
    assert iso, "isomorphism_distances empty"
    for ref, d in iso.items():
        assert isinstance(d, (int, float))
        assert np.isfinite(d), f"{ref} distance not finite"
        assert d >= 0
