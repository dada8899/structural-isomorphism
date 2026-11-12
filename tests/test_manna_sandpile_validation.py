"""Tests for X3 Wave 3 Manna sandpile validation (2026-05-25)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "manna-sandpile"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADD = REPO_ROOT / "data" / "kb-additions-2026-05-25-manna-sandpile.jsonl"
SESSION = REPO_ROOT / "docs" / "sessions" / "X3-wave3-manna-validation-2026-05-25.md"

# Sanity band: per spec τ ∈ [1.1, 1.5]; Manna asymptotic is 1.27 and
# finite-L parallel-update typically lands 1.3-1.45 at L≥128.
TAU_SANITY_BAND = (1.1, 1.5)


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
    assert results["predicted_class"] == "manna_stochastic_soc"
    assert "SYNTHETIC" in results["data_provenance"]
    s = results["summary"]
    for k in (
        "tau_size_measured",
        "tau_size_predicted",
        "in_manna_band",
        "overall_verdict",
        "powerlaw_fit",
        "iso_distance",
        "L",
        "n_nonzero",
    ):
        assert k in s, f"missing summary key {k}"
    assert s["n_nonzero"] >= 10000, "need enough avalanches for stable α fit"


@pytest.mark.sanity
def test_iso_distance_schema(results):
    iso = results["summary"]["iso_distance"]
    for k in ("to_manna", "to_btw", "to_oslo", "nearest_class"):
        assert k in iso, f"missing iso_distance key {k}"
    assert iso["nearest_class"] in ("manna", "btw", "oslo")
    # All distances must be non-negative numbers
    for k in ("to_manna", "to_btw", "to_oslo"):
        assert isinstance(iso[k], (int, float))
        assert iso[k] >= 0


@pytest.mark.sanity
def test_kb_jsonl():
    lines = KB_ADD.read_text().strip().split("\n")
    assert len(lines) >= 5, f"expected ≥5 KB entries, got {len(lines)}"
    assert len(lines) <= 10, f"expected ≤10 KB entries, got {len(lines)}"
    seen_ids = set()
    for ln in lines:
        rec = json.loads(ln)
        for k in ("id", "name", "domain", "type_id", "description"):
            assert k in rec, f"missing field {k} in {rec.get('id', '?')}"
        assert rec["id"].startswith("manna-x3-")
        assert rec["id"] not in seen_ids, f"duplicate id {rec['id']}"
        seen_ids.add(rec["id"])


@pytest.mark.sanity
def test_tau_in_sanity_band(results):
    """τ must land inside the spec-required sanity band [1.1, 1.5]."""
    tau = results["summary"]["tau_size_measured"]
    assert tau is not None
    lo, hi = TAU_SANITY_BAND
    assert lo <= tau <= hi, (
        f"tau={tau:.3f} OUTSIDE sanity band [{lo}, {hi}] (Manna predicted ~1.27)"
    )


@pytest.mark.sanity
def test_in_manna_band(results):
    """Validation's own finite-L band [1.15, 1.70] must be satisfied."""
    assert results["summary"]["in_manna_band"] is True


@pytest.mark.sanity
def test_verdict(results):
    assert results["summary"]["overall_verdict"] in ("CONFIRMED", "PARTIAL")


@pytest.mark.sanity
def test_predicted_class_distinct():
    """Ensure Manna class id is distinct from BTW/Oslo."""
    with RESULTS.open() as f:
        r = json.load(f)
    cls = r["predicted_class"]
    assert cls == "manna_stochastic_soc"
    assert cls != "btw"
    assert cls != "oslo_rice_pile"
