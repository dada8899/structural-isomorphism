"""Null controls — pipeline must REJECT power-law on synthetic non-SOC data."""
from __future__ import annotations

import pytest

from sanity_helpers import VALIDATION_DIR, load_json_or_skip


RESULTS_FILE = VALIDATION_DIR / "null-controls" / "null_results.json"

# Datasets that should be rejected as power-law
REJECT_DATASETS = ("gaussian_walk", "exponential", "poisson_iat")


@pytest.mark.sanity
def test_null_pipeline_robustness_passed():
    """top-level pipeline_robustness must equal PASSED."""
    d = load_json_or_skip(RESULTS_FILE)
    assert d.get("pipeline_robustness") == "PASSED", (
        f"null-controls regression failed: {d.get('pipeline_robustness')}"
    )


@pytest.mark.sanity
def test_null_all_three_size_dists_rejected():
    """`all_three_size_dists_rejected_power_law` must be True."""
    d = load_json_or_skip(RESULTS_FILE)
    assert d.get("all_three_size_dists_rejected_power_law") is True


@pytest.mark.sanity
@pytest.mark.parametrize("ds", REJECT_DATASETS)
def test_null_each_synthetic_rejected(ds):
    """Each of the 3 synthetic non-SOC datasets must individually be rejected."""
    d = load_json_or_skip(RESULTS_FILE)
    results = d.get("results") or {}
    if ds not in results:
        pytest.skip(f"dataset {ds} missing from null results")
    rejects = results[ds].get("rejects_power_law")
    assert rejects is True, f"{ds} not rejected as power-law: {results[ds]}"
