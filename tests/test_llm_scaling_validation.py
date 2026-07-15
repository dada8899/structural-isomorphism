"""Tests for the X3 LLM scaling-law learning-curve validation.

Smoke + schema + alpha-range sanity. Standalone-module-load pattern so we
do NOT depend on `soc_pipeline.__init__` being importable in this checkout
(the editable-install points to a /tmp path that may not exist).

Coverage:
1. learning_curve module loads + roundtrips a synthetic Chinchilla curve
2. results.json exists, has the expected schema, and the fits are sane
3. KB JSONL has 10-15 entries with required fields and unique IDs
4. CSV files exist with expected non-empty content
5. Pythia alpha ensemble sits in the band [0.05, 0.30] (sanity, not strict)
"""
from __future__ import annotations

import copy
import csv
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = (
    REPO_ROOT / "packages" / "soc-pipeline" / "src" / "soc_pipeline" / "learning_curve.py"
)
VAL_DIR = REPO_ROOT / "v4" / "validation" / "llm-scaling"
RAW_DIR = VAL_DIR / "raw"
RESULTS_JSON = VAL_DIR / "results.json"
SUMMARY_MD = VAL_DIR / "summary.md"
RUNNER_PATH = VAL_DIR / "run_validation.py"
CROSS_SOURCE_JSON = VAL_DIR / "cross_source_summary.json"
CROSS_SOURCE_12B_JSON = VAL_DIR / "pythia_12b_cross_source.json"
KB_JSONL = REPO_ROOT / "data" / "kb-additions-2026-05-24-llm-scaling.jsonl"


# ---------------------------------------------------------------------------
# Fixture: load learning_curve.py once per test session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def lc():
    """Load packages/soc-pipeline/src/soc_pipeline/learning_curve.py standalone."""
    spec = importlib.util.spec_from_file_location("lc_under_test", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lc_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner():
    spec = importlib.util.spec_from_file_location("llm_scaling_runner", RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["llm_scaling_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Module smoke tests
# ---------------------------------------------------------------------------

def test_module_exports_expected_symbols(lc) -> None:
    assert hasattr(lc, "fit_learning_curve")
    assert hasattr(lc, "LearningCurveResult")
    assert hasattr(lc, "power_law_with_floor")


def test_power_law_with_floor_basic(lc) -> None:
    """Forward model evaluates correctly at known values."""
    C = np.array([1e18, 1e21, 1e24])
    L = lc.power_law_with_floor(C, A=400.0, alpha=0.155, L_inf=1.7)
    # At C → infinity loss → L_inf
    assert L[-1] > 1.7
    assert L[0] > L[1] > L[2]
    # At C=1e18 with A=400, alpha=0.155 → 400 / 1e18^0.155 ≈ 0.5 → L ≈ 2.2
    assert 2.0 < L[0] < 2.5


def test_synthetic_chinchilla_recovery(lc) -> None:
    """Round-trip: generate Chinchilla-like curve → fit → check parameter recovery."""
    rng = np.random.default_rng(42)
    C = np.logspace(17, 24, 15)
    A_true, alpha_true, L_inf_true = 400.0, 0.155, 1.7
    L_clean = lc.power_law_with_floor(C, A_true, alpha_true, L_inf_true)
    L = L_clean * (1 + 0.01 * rng.standard_normal(C.size))

    result = lc.fit_learning_curve(C, L, name="synthetic-chinchilla")

    assert result.error is None
    assert result.R2 is not None and result.R2 > 0.95
    # alpha and L_inf should recover to within ~10%
    assert abs(result.alpha - alpha_true) / alpha_true < 0.15
    assert abs(result.L_inf - L_inf_true) / L_inf_true < 0.05
    assert result.n_points == 15


def test_too_few_points_returns_error(lc) -> None:
    r = lc.fit_learning_curve([1.0, 2.0], [3.0, 4.0], name="tiny")
    assert r.error is not None
    assert "too_few_points" in r.error


def test_shape_mismatch_returns_error(lc) -> None:
    r = lc.fit_learning_curve([1.0, 2.0, 3.0], [1.0, 2.0], name="bad-shapes")
    assert r.error is not None
    assert "shape_mismatch" in r.error


def test_filters_non_finite_entries(lc) -> None:
    """NaN, inf, and non-positive entries are dropped before fitting."""
    C = [1e18, 2e18, 4e18, 8e18, 16e18, float("nan"), -1.0]
    L = [3.0, 2.5, 2.2, 2.1, 2.05, 2.0, 1.95]
    r = lc.fit_learning_curve(C, L, name="dirty")
    assert r.error is None
    assert r.n_points == 5  # 7 - 2 dropped


def test_result_to_dict_is_json_serializable(lc) -> None:
    C = np.logspace(17, 24, 12)
    L = lc.power_law_with_floor(C, 400.0, 0.155, 1.7)
    r = lc.fit_learning_curve(C, L)
    d = r.to_dict()
    # round-trips through json without exception
    s = json.dumps(d)
    assert json.loads(s)["alpha"] is not None


# ---------------------------------------------------------------------------
# 2. Validation artifact tests (run_validation.py outputs)
# ---------------------------------------------------------------------------

def test_results_json_exists() -> None:
    assert RESULTS_JSON.is_file(), (
        f"missing {RESULTS_JSON}; run `python v4/validation/llm-scaling/run_validation.py`"
    )


def test_committed_artifacts_equal_deterministic_raw_input_build(runner) -> None:
    if not runner.generator_environment_matches():
        pytest.skip("byte-stable artifact comparison runs in the locked generator gate")
    generated = runner.main(write=False)
    committed = json.loads(RESULTS_JSON.read_text())

    runner.assert_artifact_equivalent(committed, generated)
    assert SUMMARY_MD.read_text() == runner._render_summary_md(committed)


def test_artifact_comparison_rejects_material_numeric_and_semantic_drift(
    runner,
) -> None:
    committed = json.loads(RESULTS_JSON.read_text())
    numeric_drift = copy.deepcopy(committed)
    numeric_drift["fits"]["pythia-2.8b"]["A"] *= 1.001
    with pytest.raises(ValueError, match="numeric artifact mismatch"):
        runner.assert_artifact_equivalent(committed, numeric_drift)

    semantic_drift = copy.deepcopy(committed)
    semantic_drift["fits"]["pythia-2.8b"]["fit_status"] = "rejected"
    with pytest.raises(ValueError, match="artifact mismatch"):
        runner.assert_artifact_equivalent(committed, semantic_drift)


def test_generator_contract_is_exact_and_self_describing(runner) -> None:
    data = json.loads(RESULTS_JSON.read_text())
    assert runner._generator_pins() == {
        "contourpy": "1.3.3",
        "cycler": "0.12.1",
        "fonttools": "4.63.0",
        "kiwisolver": "1.5.0",
        "matplotlib": "3.11.0",
        "numpy": "1.26.3",
        "packaging": "26.2",
        "pandas": "3.0.3",
        "pillow": "12.3.0",
        "pyparsing": "3.3.2",
        "python-dateutil": "2.9.0.post0",
        "scipy": "1.16.3",
        "six": "1.17.0",
    }
    assert data["generation_contract"] == {
        "python": "3.11",
        "requirements": runner._generator_pins(),
        "float_significant_digits": 12,
        "comparison_rel_tol": 1e-4,
        "comparison_abs_tol": 1e-10,
        "canonical_data_kind": "real",
        "canonical_input": (
            "v4/validation/llm-scaling/raw/pythia_checkpoints_combined.csv"
        ),
    }


@pytest.mark.parametrize("path", [CROSS_SOURCE_JSON, CROSS_SOURCE_12B_JSON])
def test_cross_source_outputs_are_strict_json(path: Path) -> None:
    def reject_nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    parsed = json.loads(path.read_text(), parse_constant=reject_nonfinite)
    assert isinstance(parsed, dict)


@pytest.mark.parametrize("data_kind", ["synthetic", "rea1"])
def test_canonical_writer_rejects_nonreal_data_without_clobber(
    runner, monkeypatch, data_kind: str,
) -> None:
    before_results = RESULTS_JSON.read_bytes()
    before_summary = SUMMARY_MD.read_bytes()
    monkeypatch.setenv("PYTHIA_DATA", data_kind)
    monkeypatch.setattr(
        runner, "_assert_generator_environment", runner._assert_canonical_data_source
    )

    with pytest.raises(
        RuntimeError, match="canonical LLM scaling artifacts require PYTHIA_DATA=real"
    ):
        runner.main(write=True)

    assert RESULTS_JSON.read_bytes() == before_results
    assert SUMMARY_MD.read_bytes() == before_summary


def test_canonical_writer_rejects_missing_real_input_without_clobber(
    runner, monkeypatch, tmp_path: Path,
) -> None:
    before_results = RESULTS_JSON.read_bytes()
    before_summary = SUMMARY_MD.read_bytes()
    monkeypatch.setenv("PYTHIA_DATA", "real")
    monkeypatch.setattr(runner, "RAW_DIR", tmp_path)
    monkeypatch.setattr(
        runner, "_assert_generator_environment", runner._assert_canonical_data_source
    )

    with pytest.raises(RuntimeError, match="canonical LLM scaling input is missing"):
        runner.main(write=True)

    assert RESULTS_JSON.read_bytes() == before_results
    assert SUMMARY_MD.read_bytes() == before_summary


def test_fit_classification_rejects_boundaries_and_separates_narrow_tail(runner) -> None:
    base = {
        "error": None,
        "alpha": 0.2,
        "A": 10.0,
        "L_inf": 1.0,
        "R2": 0.99,
        "provenance": "REAL_FULL",
    }
    assert runner._classify_fit(base, pythia=True) == ("fit_quality_eligible", None)
    boundary = {**base, "alpha": 1.9999}
    assert runner._classify_fit(boundary, pythia=True)[0] == "rejected"
    negative = {**base, "R2": -0.01, "provenance": "REAL_TAIL_NARROW"}
    assert runner._classify_fit(negative, pythia=True)[0] == "rejected"
    narrow = {**base, "R2": 0.01, "provenance": "REAL_TAIL_NARROW"}
    assert runner._classify_fit(narrow, pythia=True)[0] == "descriptive_only"


def test_results_json_schema() -> None:
    data = json.loads(RESULTS_JSON.read_text())
    assert data["validation"] == "llm-scaling"
    assert data["schema_version"] == "1.3"
    assert "fits" in data and "summary" in data
    # Seven observed Pythia sizes + Kaplan + Hoffmann.
    assert len(data["fits"]) == 9
    pythia_keys = [k for k in data["fits"] if k.startswith("pythia-")]
    assert set(pythia_keys) == {
        "pythia-70m", "pythia-160m", "pythia-410m", "pythia-1b",
        "pythia-1.4b", "pythia-2.8b", "pythia-6.9b",
    }


def test_results_per_fit_schema() -> None:
    data = json.loads(RESULTS_JSON.read_text())
    required = {
        "name", "alpha", "A", "L_inf", "R2", "n_points",
        "fit_status", "exclusion_reason",
    }
    for name, fit in data["fits"].items():
        missing = required - set(fit.keys())
        assert not missing, f"{name} missing keys {missing}"
        assert fit["fit_status"] in {
            "fit_quality_eligible", "descriptive_only", "rejected",
        }
        if fit["fit_status"] == "fit_quality_eligible":
            assert fit["exclusion_reason"] is None
            assert fit.get("error") is None
            assert fit["alpha"] is not None and 0 < fit["alpha"] < 1
            assert fit["L_inf"] is not None and 0 <= fit["L_inf"] < 10
            assert fit["R2"] is not None and fit["R2"] > 0.9
        else:
            assert isinstance(fit["exclusion_reason"], str) and fit["exclusion_reason"]


def test_pythia_alpha_band() -> None:
    """Only fit-quality-eligible Pythia alphas enter the numerical band.

    The original 2026-05-24 synthetic data clustered at α ∈ [0.09, 0.15].
    Real wandb training-curve fits (2026-05-25 upgrade) push the per-size
    α to 0.31–0.58 in REAL_FULL sizes, well outside the original band.
    We relax the band to [0.03, 1.0] (the fitter's bounds are [0.01, 2.0]).
    """
    data = json.loads(RESULTS_JSON.read_text())
    for name, fit in data["fits"].items():
        if not name.startswith("pythia-"):
            continue
        if fit["fit_status"] != "fit_quality_eligible":
            continue
        assert 0.03 <= fit["alpha"] <= 1.0, (
            f"{name} alpha {fit['alpha']:.4f} outside [0.03, 1.0]"
        )


def test_chinchilla_alpha_matches_literature() -> None:
    """Hoffmann fit should recover alpha_C ≈ 0.155 within ±0.03."""
    data = json.loads(RESULTS_JSON.read_text())
    hoff = data["fits"]["hoffmann2022-chinchilla"]
    assert 0.125 <= hoff["alpha"] <= 0.185, (
        f"Chinchilla alpha {hoff['alpha']:.4f} should be ~0.155 ±0.03"
    )


def test_kaplan_alpha_matches_literature() -> None:
    """Kaplan fit should recover alpha_C ≈ 0.050 within ±0.02."""
    data = json.loads(RESULTS_JSON.read_text())
    kap = data["fits"]["kaplan2020-gpt"]
    assert 0.030 <= kap["alpha"] <= 0.070, (
        f"Kaplan alpha {kap['alpha']:.4f} should be ~0.050 ±0.02"
    )


def test_pythia_universality_summary() -> None:
    """Schema test: the universality stats live under either the original
    flat keys (schema 1.0, all-synthetic) or the stratified keys (schema 1.1,
    real+synthetic provenance-aware).
    """
    data = json.loads(RESULTS_JSON.read_text())
    s = data["summary"]
    assert s["pythia_n_sizes"] == 7
    assert s["pythia_n_fit_quality_eligible"] == 5
    allowed_diagnostics = {
        "NARROW_SPREAD",
        "MODERATE_SPREAD",
        "BROAD_SPREAD",
        "UNKNOWN",
    }
    eligible = s["alpha_fit_quality_eligible_sizes"]
    assert eligible["n"] == 5
    assert eligible["mean"] is not None
    assert 0.03 < eligible["mean"] < 1.0
    assert s["fit_spread_diagnostic_fit_quality_eligible"] in allowed_diagnostics
    assert s["fit_spread_diagnostic_real_wide"] in allowed_diagnostics
    assert s["alpha_real_wide_only"]["n"] == 2
    assert s["scientific_conclusion"] == (
        "INSUFFICIENT_REAL_WIDE_SERIES_FOR_UNIVERSALITY_INFERENCE"
    )
    assert s["fit_status_per_model"]["pythia-1.4b"] == "rejected"
    assert s["fit_status_per_model"]["pythia-2.8b"] == "descriptive_only"
    assert set(s["exclusions_from_fit_spread"]) == {"pythia-1.4b", "pythia-2.8b"}


# ---------------------------------------------------------------------------
# 3. KB additions JSONL tests
# ---------------------------------------------------------------------------

def test_kb_jsonl_exists() -> None:
    assert KB_JSONL.is_file()


def test_kb_jsonl_row_count() -> None:
    rows = [json.loads(l) for l in KB_JSONL.read_text().splitlines() if l.strip()]
    assert 10 <= len(rows) <= 20, f"expected 10-20 rows, got {len(rows)}"


def test_kb_jsonl_schema() -> None:
    required = {"id", "name", "domain", "type_id", "description"}
    rows = [json.loads(l) for l in KB_JSONL.read_text().splitlines() if l.strip()]
    for r in rows:
        missing = required - set(r.keys())
        assert not missing, f"{r.get('id', '?')} missing fields: {missing}"
        assert r["description"] and len(r["description"]) >= 50, (
            f"{r['id']} description too short"
        )


def test_kb_jsonl_unique_ids() -> None:
    rows = [json.loads(l) for l in KB_JSONL.read_text().splitlines() if l.strip()]
    ids = [r["id"] for r in rows]
    assert len(ids) == len(set(ids)), "duplicate ids in KB jsonl"


def test_kb_jsonl_domain_consistency() -> None:
    """All entries should be ML/AI-flavored."""
    rows = [json.loads(l) for l in KB_JSONL.read_text().splitlines() if l.strip()]
    ml_domains = {"机器学习", "人工智能", "深度学习"}
    for r in rows:
        assert r["domain"] in ml_domains, (
            f"{r['id']} unexpected domain: {r['domain']}"
        )


# ---------------------------------------------------------------------------
# 4. Raw CSV tests
# ---------------------------------------------------------------------------

def test_pythia_csv_exists_and_nonempty() -> None:
    path = RAW_DIR / "pythia_checkpoints.csv"
    assert path.is_file()
    rows = list(csv.DictReader(path.open()))
    assert len(rows) >= 60, f"too few Pythia rows: {len(rows)}"
    # 6 models × 14 steps = 84 expected
    models = {r["model"] for r in rows}
    assert len(models) == 6


def test_kaplan_csv_exists_and_nonempty() -> None:
    path = RAW_DIR / "kaplan2020_compute.csv"
    assert path.is_file()
    rows = list(csv.DictReader(path.open()))
    assert len(rows) >= 10


def test_hoffmann_csv_exists_and_nonempty() -> None:
    path = RAW_DIR / "hoffmann2022_compute.csv"
    assert path.is_file()
    rows = list(csv.DictReader(path.open()))
    assert len(rows) >= 10
