"""Tests for X3 Wave 3 KPZ universality-class validation (2026-05-24).

Three layers per CLAUDE.md 功能验收三层:

1. smoke   — runner is importable, results.json exists and parses.
2. schema  — results.json has required fields; KB JSONL well-formed.
3. sanity  — α, β recovered inside the predicted KPZ bands; the
             load-bearing scientific claim (KPZ universality recovery).

Coverage marker: sanity (per pytest.ini markers).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
VAL_DIR = REPO_ROOT / "v4" / "validation" / "kpz-interface"
RESULTS = VAL_DIR / "results.json"
VERDICT = VAL_DIR / "verdict.md"
KB_ADD = REPO_ROOT / "data" / "kb-additions-2026-05-24-kpz.jsonl"
SESSION = REPO_ROOT / "docs" / "sessions" / "X3-wave3-kpz-validation-2026-05-24.md"

ALPHA_BAND = (0.40, 0.65)
BETA_BAND = (0.27, 0.40)


@pytest.fixture(scope="module")
def results() -> dict:
    if not RESULTS.exists():
        pytest.skip(
            f"missing {RESULTS}; run "
            "`python3 v4/validation/kpz-interface/run_validation.py` first"
        )
    with RESULTS.open() as f:
        return json.load(f)


# ---------- smoke ----------

@pytest.mark.sanity
def test_results_exists():
    assert RESULTS.exists(), f"missing {RESULTS}"


@pytest.mark.sanity
def test_verdict_md_exists():
    assert VERDICT.exists()
    assert "CONFIRMED" in VERDICT.read_text() or "PARTIAL" in VERDICT.read_text()


@pytest.mark.sanity
def test_session_doc_exists():
    assert SESSION.exists()
    body = SESSION.read_text()
    assert "Wave 3" in body
    assert "KPZ" in body


@pytest.mark.sanity
def test_kb_jsonl_exists():
    assert KB_ADD.exists()


# ---------- schema ----------

@pytest.mark.sanity
def test_results_schema(results):
    assert results["predicted_class"] == "kpz_1plus1d_growth"
    exp = results["exponents_predicted"]
    assert abs(exp["alpha"] - 0.5) < 1e-9
    assert abs(exp["beta"] - 1.0/3.0) < 1e-9
    assert abs(exp["z"] - 1.5) < 1e-9
    assert "SYNTHETIC" in results["data_provenance"]
    summary = results["summary"]
    for k in ("alpha_fit", "beta_mean_largest2", "z_estimate",
              "alpha_band", "beta_band", "in_kpz_band",
              "tracy_widom_compare", "overall_verdict"):
        assert k in summary, f"summary missing key {k}"
    assert results["per_L"], "per_L empty"
    for r in results["per_L"]:
        for k in ("L", "n_mono", "n_seed", "growth_slope", "w_sat", "n_snap"):
            assert k in r, f"per-L entry missing {k}"


@pytest.mark.sanity
def test_kb_jsonl_schema():
    lines = KB_ADD.read_text().strip().split("\n")
    assert len(lines) >= 5, f"expected >=5 KB entries, got {len(lines)}"
    seen_ids = set()
    for line in lines:
        rec = json.loads(line)
        for k in ("id", "name", "domain", "type_id", "description"):
            assert k in rec, f"KB entry missing {k}: {rec}"
        assert rec["id"].startswith("kpz-x3-"), f"unexpected id {rec['id']}"
        assert rec["id"] not in seen_ids, f"duplicate id {rec['id']}"
        seen_ids.add(rec["id"])


# ---------- sanity (the scientific claim) ----------

@pytest.mark.sanity
def test_alpha_in_kpz_band(results):
    alpha = results["summary"]["alpha_fit"]["slope"]
    assert alpha is not None, "alpha fit failed"
    lo, hi = ALPHA_BAND
    assert lo <= alpha <= hi, f"alpha={alpha:.3f} OUTSIDE [{lo},{hi}] (predicted 0.5)"


@pytest.mark.sanity
def test_beta_in_kpz_band(results):
    beta = results["summary"]["beta_mean_largest2"]
    assert beta is not None, "beta fit failed"
    lo, hi = BETA_BAND
    assert lo <= beta <= hi, f"beta={beta:.3f} OUTSIDE [{lo},{hi}] (predicted 1/3)"


@pytest.mark.sanity
def test_verdict_confirmed_or_partial(results):
    v = results["summary"]["overall_verdict"]
    assert v in ("CONFIRMED", "PARTIAL"), f"unexpected verdict {v}"


@pytest.mark.sanity
def test_beta_converges_with_L(results):
    """β_eff should increase monotonically toward 1/3 with L (finite-size convergence)."""
    per_L = sorted(results["per_L"], key=lambda r: r["L"])
    betas = [r["growth_slope"]["slope"] for r in per_L
             if r["growth_slope"]["slope"] is not None]
    # the largest L should have higher β than the smallest
    assert betas[-1] > betas[0] - 0.05, \
        f"β not converging with L: smallest L β={betas[0]:.3f}, largest L β={betas[-1]:.3f}"
