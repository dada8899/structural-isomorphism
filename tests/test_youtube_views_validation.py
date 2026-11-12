"""Smoke + schema + sanity tests for X3 Wave 2 YouTube view-count validation.

Validates:
  1. Smoke — run_validation.py imports and exposes public functions.
  2. Schema — results.json has fit + verdict + isomorphism fields.
  3. Sanity — alpha in preferential_attachment sanity band [1.5, 3.5].
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
DIR = REPO / "v4" / "validation" / "youtube-views"
RESULTS = DIR / "results.json"
RUN = DIR / "run_validation.py"


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "youtube_run_validation", RUN
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_smoke_run_validation_module_imports():
    mod = _load_module()
    for fn in ("load_view_counts", "fit_and_compare",
               "verdict", "isomorphism_distance"):
        assert hasattr(mod, fn), f"{fn}() missing"


def test_smoke_verdict_function():
    mod = _load_module()
    v = mod.verdict(alpha=2.1, n_tail=500, R_ln=1.0, p_ln=0.5)
    assert v == "PASS"
    # alpha out of canonical, in sanity → INCONCLUSIVE
    v = mod.verdict(alpha=1.6, n_tail=500, R_ln=1.0, p_ln=0.5)
    assert v == "INCONCLUSIVE"
    # alpha out of sanity → FAIL
    v = mod.verdict(alpha=5.0, n_tail=500, R_ln=1.0, p_ln=0.5)
    assert v == "FAIL"
    # n_tail too small → INCONCLUSIVE
    v = mod.verdict(alpha=2.1, n_tail=20, R_ln=None, p_ln=None)
    assert v == "INCONCLUSIVE"


def test_smoke_isomorphism_distance():
    mod = _load_module()
    d = mod.isomorphism_distance(2.0, 2.0, 0.1, 0.1)
    assert d == pytest.approx(0.0)
    d = mod.isomorphism_distance(2.1, 2.2, 0.05, 0.10)
    assert 0.5 < d < 1.2


@pytest.mark.skipif(not RESULTS.exists(),
                    reason="results.json not yet generated; run "
                           "v4/validation/youtube-views/run_validation.py first")
def test_schema_top_level_keys():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    required = {"timestamp_utc", "data_provenance", "n_videos", "max_views",
                "median_views", "fit", "references", "isomorphism_distances",
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
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    alpha = data["fit"].get("alpha")
    assert alpha is not None
    assert 1.5 <= alpha <= 3.5, (
        f"alpha={alpha:.3f} outside preferential_attachment sanity band"
    )


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_n_videos_large():
    """Kaggle YouTube Trending US has ~6000 distinct videos; ensure full data."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert data["n_videos"] >= 5000, (
        f"only {data['n_videos']} videos — likely truncated dataset"
    )


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_verdict_value():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    assert data["verdict"] in ("PASS", "INCONCLUSIVE", "FAIL")


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_iso_distances_finite():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    iso = data["isomorphism_distances"]
    assert iso, "isomorphism_distances empty"
    for ref, d in iso.items():
        assert np.isfinite(d), f"{ref} not finite"
        assert d >= 0


@pytest.mark.skipif(not RESULTS.exists(), reason="results.json missing")
def test_sanity_crane_sornette_isomorphism_close():
    """Cross-domain match to Crane-Sornette 2008 YouTube should be < 2σ."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    d = data["isomorphism_distances"].get("crane_sornette_2008_yt")
    assert d is not None
    assert d < 2.0, (
        f"distance to Crane-Sornette 2008 = {d:.2f}σ exceeds 2σ "
        "— possibly different sub-class"
    )
