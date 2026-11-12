"""Tests for X3 Wave 3 RFIM/Barkhausen validation (2026-05-24)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "rfim-barkhausen"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADD = REPO_ROOT / "data" / "kb-additions-2026-05-24-rfim.jsonl"
SESSION = REPO_ROOT / "docs" / "sessions" / "X3-wave3-rfim-validation-2026-05-24.md"

TAU_BAND = (1.30, 1.70)
GAMMA_BAND = (1.5, 2.5)


@pytest.fixture(scope="module")
def results() -> dict:
    if not RESULTS.exists():
        pytest.skip(f"missing {RESULTS}")
    with RESULTS.open() as f:
        return json.load(f)


@pytest.mark.sanity
def test_outputs_exist():
    for p in (RESULTS, VERDICT, KB_ADD, SESSION):
        assert p.exists(), f"missing {p}"


@pytest.mark.sanity
def test_results_schema(results):
    assert results["predicted_class"] == "rfim_barkhausen_avalanche"
    assert "SYNTHETIC" in results["data_provenance"]
    s = results["summary"]
    for k in ("tau_size_measured", "tau_size_predicted", "gamma_measured",
              "gamma_predicted", "in_rfim_band", "overall_verdict"):
        assert k in s


@pytest.mark.sanity
def test_kb_jsonl():
    lines = KB_ADD.read_text().strip().split("\n")
    assert len(lines) >= 5
    for ln in lines:
        rec = json.loads(ln)
        for k in ("id", "name", "domain", "type_id", "description"):
            assert k in rec
        assert rec["id"].startswith("rfim-x3-")


@pytest.mark.sanity
def test_tau_size_in_rfim_band(results):
    tau = results["summary"]["tau_size_measured"]
    assert tau is not None
    lo, hi = TAU_BAND
    assert lo <= tau <= hi, f"tau_size={tau:.3f} OUTSIDE [{lo},{hi}] (MF RFIM predicted 1.5)"


@pytest.mark.sanity
def test_gamma_in_rfim_band(results):
    gamma = results["summary"]["gamma_measured"]
    assert gamma is not None
    lo, hi = GAMMA_BAND
    assert lo <= gamma <= hi, f"gamma={gamma:.3f} OUTSIDE [{lo},{hi}] (MF RFIM predicted 2)"


@pytest.mark.sanity
def test_verdict(results):
    assert results["summary"]["overall_verdict"] in ("CONFIRMED", "PARTIAL")
