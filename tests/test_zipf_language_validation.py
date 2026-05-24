"""Smoke + schema + sanity tests for X3 Zipf multi-language validation.

Validates:
  1. Smoke — run_validation.py module imports and exposes the public functions.
  2. Schema — zipf_results.json contains expected per-language and summary keys.
  3. Sanity — every reported Zipf exponent s_rank falls in [0.5, 2.0].

If zipf_results.json is missing (validation not yet run), schema and sanity
checks are skipped with a clear message. Smoke always runs.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ZIPF_DIR = REPO / "v4" / "validation" / "zipf-language"
RESULTS = ZIPF_DIR / "zipf_results.json"


def test_smoke_run_validation_module_imports():
    """run_validation.py should import and expose tokenize() + fit functions."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "zipf_run_validation", ZIPF_DIR / "run_validation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert hasattr(mod, "tokenize"), "tokenize() missing"
    assert hasattr(mod, "rank_freq"), "rank_freq() missing"
    assert hasattr(mod, "fit_zipf_loglog"), "fit_zipf_loglog() missing"
    assert hasattr(mod, "fit_alpha_clauset"), "fit_alpha_clauset() missing"
    assert hasattr(mod, "chi_square_homogeneity"), "chi_square_homogeneity() missing"
    assert hasattr(mod, "isomorphism_distance"), "isomorphism_distance() missing"


def test_smoke_tokenize_basic():
    """Tokenize one short string per supported language; ensure non-empty."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "zipf_run_validation", ZIPF_DIR / "run_validation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.tokenize("The cat sat on the mat.", "en") == [
        "the", "cat", "sat", "on", "the", "mat"
    ]
    es = mod.tokenize("El gato está en la silla.", "es")
    assert len(es) >= 5
    hi = mod.tokenize("यह एक परीक्षण है।", "hi")
    assert len(hi) >= 3
    ar = mod.tokenize("هذا اختبار بسيط.", "ar")
    assert len(ar) >= 2


def test_smoke_fit_synthetic_zipf():
    """Generate synthetic Zipf with s=1 and recover s close to 1."""
    import importlib.util
    import numpy as np

    spec = importlib.util.spec_from_file_location(
        "zipf_run_validation", ZIPF_DIR / "run_validation.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    rng = np.random.default_rng(42)
    # Construct a synthetic vocabulary with rank-frequency exactly f(r) = C/r^s
    # for s=1.0, then realize integer counts via Poisson sampling.
    n_vocab = 5000
    s_true = 1.0
    ranks_true = np.arange(1, n_vocab + 1, dtype=float)
    expected_freq = 1e5 / (ranks_true ** s_true)
    counts = rng.poisson(expected_freq)
    freqs = np.array(sorted(counts.tolist(), reverse=True), dtype=float)
    freqs = freqs[freqs > 0]
    ranks = np.arange(1, len(freqs) + 1, dtype=float)
    fit = mod.fit_zipf_loglog(ranks, freqs, rank_lo=10, rank_hi=1000)
    assert "s_rank" in fit
    assert 0.85 <= fit["s_rank"] <= 1.15, f"synthetic s={fit['s_rank']:.3f}"


@pytest.mark.skipif(not RESULTS.exists(),
                    reason="zipf_results.json not yet generated; run "
                           "v4/validation/zipf-language/run_validation.py first")
def test_schema_results_top_level_keys():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    required = {"timestamp", "per_language", "cross_language_chi2",
                "references", "isomorphism_distances", "expected_band",
                "verdict_per_lang"}
    missing = required - set(data.keys())
    assert not missing, f"missing top-level keys: {missing}"
    assert isinstance(data["per_language"], dict)
    assert len(data["per_language"]) >= 1, "no per-language entries"


@pytest.mark.skipif(not RESULTS.exists(), reason="zipf_results.json missing")
def test_schema_per_language_fields():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    for label, entry in data["per_language"].items():
        assert "language" in entry, f"{label}: language missing"
        assert "n_tokens" in entry, f"{label}: n_tokens missing"
        assert "vocab_size" in entry, f"{label}: vocab_size missing"
        assert "fit" in entry, f"{label}: fit missing"
        fit = entry["fit"]
        if "error" not in fit:
            for k in ("s_rank", "log_c", "r2", "resid_std",
                      "rank_lo", "rank_hi_used", "n_points"):
                assert k in fit, f"{label}.fit missing {k}"


@pytest.mark.skipif(not RESULTS.exists(), reason="zipf_results.json missing")
def test_sanity_s_in_plausible_range():
    """Every reported s_rank should be in [0.5, 2.0] — sanity range for any
    natural-language Zipf exponent (Mandelbrot, Piantadosi 2014 reviews give
    0.9-1.2 typical; we widen to 0.5-2.0 to also catch undersampled corpora)."""
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    out_of_range = []
    for label, entry in data["per_language"].items():
        s = entry["fit"].get("s_rank")
        if s is None:
            continue
        if not (0.5 <= s <= 2.0):
            out_of_range.append((label, s))
    assert not out_of_range, f"s_rank out of [0.5, 2.0]: {out_of_range}"


@pytest.mark.skipif(not RESULTS.exists(), reason="zipf_results.json missing")
def test_sanity_brown_canonical():
    """The Brown corpus is the canonical Zipf benchmark; s should be ~1.0.

    Mandatory check because Brown is offline and largest by ~80x; if Brown
    drifts the whole pipeline is suspect.
    """
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    brown = data["per_language"].get("brown_en")
    if brown is None:
        pytest.skip("brown_en not in results")
    s = brown["fit"].get("s_rank")
    assert s is not None
    assert 0.85 <= s <= 1.15, f"Brown s_rank={s:.3f} outside canonical band"


@pytest.mark.skipif(not RESULTS.exists(), reason="zipf_results.json missing")
def test_isomorphism_distance_present():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    iso = data["isomorphism_distances"]
    assert iso, "isomorphism_distances empty"
    for label, refs in iso.items():
        for ref_name in ("pareto_wealth_rank_s", "city_size_zipf",
                         "zipf_classical"):
            assert ref_name in refs, f"{label} missing ref {ref_name}"
            d = refs[ref_name]
            assert isinstance(d, (int, float))
            assert d >= 0, f"{label}.{ref_name} distance negative"


@pytest.mark.skipif(not RESULTS.exists(), reason="zipf_results.json missing")
def test_verdict_values_valid():
    data = json.loads(RESULTS.read_text(encoding="utf-8"))
    valid = {"PASS", "INCONCLUSIVE", "FAIL"}
    for label, v in data["verdict_per_lang"].items():
        assert v in valid, f"{label}: invalid verdict {v}"
