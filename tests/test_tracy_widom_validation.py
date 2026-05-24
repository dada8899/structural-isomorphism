"""Tests for X3 Wave 3 Tracy-Widom GUE validation (2026-05-24)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "tracy-widom-gue"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADD = REPO_ROOT / "data" / "kb-additions-2026-05-24-tracy-widom.jsonl"
SESSION = REPO_ROOT / "docs" / "sessions" / "X3-wave3-tracy-widom-validation-2026-05-24.md"

# TW GUE reference (Bornemann 2010 / Prähofer-Spohn 2004)
TW_MEAN = -1.7710868074
TW_VAR = 0.81319479
TW_SKEW = 0.2240842
TW_KURT = 0.0934480


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
    assert results["predicted_class"] == "tracy_widom_gue_beta2"
    assert "SYNTHETIC" in results["data_provenance"]
    s = results["summary"]
    for k in ("empirical", "tw_gue_reference", "deviations_from_tw",
              "in_tw_band", "overall_verdict"):
        assert k in s
    for moment in ("mean", "var", "skew", "excess_kurt"):
        assert moment in s["empirical"]


@pytest.mark.sanity
def test_kb_jsonl():
    lines = KB_ADD.read_text().strip().split("\n")
    assert len(lines) >= 5
    for ln in lines:
        rec = json.loads(ln)
        for k in ("id", "name", "domain", "type_id", "description"):
            assert k in rec
        assert rec["id"].startswith("tw-x3-")


@pytest.mark.sanity
def test_mean_in_band(results):
    m = results["summary"]["empirical"]["mean"]
    assert abs(m - TW_MEAN) < 0.15, \
        f"mean={m:.3f} deviates >0.15 from TW={TW_MEAN:.3f}"


@pytest.mark.sanity
def test_var_in_band(results):
    v = results["summary"]["empirical"]["var"]
    assert abs(v - TW_VAR) < 0.15, \
        f"var={v:.3f} deviates >0.15 from TW={TW_VAR:.3f}"


@pytest.mark.sanity
def test_skew_in_band(results):
    sk = results["summary"]["empirical"]["skew"]
    assert sk is not None
    assert abs(sk - TW_SKEW) < 0.15, \
        f"skew={sk:.3f} deviates >0.15 from TW={TW_SKEW:.3f}"


@pytest.mark.sanity
def test_verdict(results):
    assert results["summary"]["overall_verdict"] in ("CONFIRMED", "PARTIAL")
