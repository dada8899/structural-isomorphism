"""Tests for X3 Wave 3 Directed Percolation (DP) validation (2026-05-24)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "dp-contact-process"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADD = REPO_ROOT / "data" / "kb-additions-2026-05-24-dp.jsonl"
SESSION = REPO_ROOT / "docs" / "sessions" / "X3-wave3-dp-validation-2026-05-24.md"

THETA_BAND = (0.12, 0.20)


@pytest.fixture(scope="module")
def results() -> dict:
    if not RESULTS.exists():
        pytest.skip(f"missing {RESULTS}; run runner first")
    with RESULTS.open() as f:
        return json.load(f)


@pytest.mark.sanity
def test_outputs_exist():
    assert RESULTS.exists()
    assert VERDICT.exists()
    assert KB_ADD.exists()
    assert SESSION.exists()


@pytest.mark.sanity
def test_results_schema(results):
    assert results["predicted_class"] == "directed_percolation_1plus1d"
    assert "SYNTHETIC" in results["data_provenance"]
    s = results["summary"]
    for k in ("theta_measured", "theta_predicted", "theta_band",
              "monotone_phase_diagram", "in_dp_band", "overall_verdict"):
        assert k in s
    for label in ("below", "critical", "above"):
        assert label in results["per_p"]


@pytest.mark.sanity
def test_kb_jsonl_schema():
    lines = KB_ADD.read_text().strip().split("\n")
    assert len(lines) >= 5
    seen = set()
    for ln in lines:
        rec = json.loads(ln)
        for k in ("id", "name", "domain", "type_id", "description"):
            assert k in rec
        assert rec["id"].startswith("dp-x3-")
        assert rec["id"] not in seen
        seen.add(rec["id"])


@pytest.mark.sanity
def test_theta_in_dp_band(results):
    theta = results["summary"]["theta_measured"]
    assert theta is not None
    lo, hi = THETA_BAND
    assert lo <= theta <= hi, \
        f"theta={theta:.3f} OUTSIDE [{lo},{hi}] (DP-1+1d predicted 0.159)"


@pytest.mark.sanity
def test_phase_diagram_monotone(results):
    assert results["summary"]["monotone_phase_diagram"] is True, \
        "ρ_below < ρ_critical < ρ_above must hold for valid absorbing-state transition"


@pytest.mark.sanity
def test_verdict_confirmed(results):
    assert results["summary"]["overall_verdict"] in ("CONFIRMED", "PARTIAL")
