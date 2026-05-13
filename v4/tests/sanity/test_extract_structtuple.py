"""Unit tests for v4/product/d1_phase_detector/extract_structtuple.py.

Covers:
  - StructTuple.validate() — full schema validation, all required/optional
    fields, enum checks, range checks, length checks, type coercion
  - StructTuple.to_dict() — round-trip
  - make_prompt() — prompt template substitution + sector/market_cap handling

We do NOT exercise call_deepseek() / extract_one() — those require network.
We do exercise the parse-fail edge case through validate() since the same
validation feeds the guardrail loop.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
EX_PATH = REPO / "v4" / "product" / "d1_phase_detector" / "extract_structtuple.py"


@pytest.fixture(scope="module")
def ex():
    # Wire v4/lib into sys.path BEFORE loading the module (module itself does
    # this when imported normally, but we're path-loading via spec).
    sys.path.insert(0, str(REPO / "v4" / "lib"))
    spec = importlib.util.spec_from_file_location("extract_structtuple", EX_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # Register in sys.modules BEFORE exec — dataclasses look up cls.__module__
    # in sys.modules at decoration time.
    sys.modules["extract_structtuple"] = mod
    spec.loader.exec_module(mod)
    return mod


def _good_record() -> dict:
    return {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "as_of_date": "2026-05-13",
        "dynamics_family": "preferential_attachment",
        "critical_point_state": "far_from_critical",
        "structural_summary": "Network effect mega-cap with stable mean reversion.",
        "confidence": 0.85,
        "evidence_anchors": [
            {"fact": "$3.5T market cap", "source": "Bloomberg 2026-05-12"},
            {"fact": "Services 25% of revenue", "source": "10-K FY24"},
        ],
        "early_warning_indicators": {
            "ar1_trend": "stable",
            "variance_trend": "stable",
            "tail_exponent_drift": "stable",
        },
        "v4_class_alignment": {"preferential_attachment": 0.9},
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_validate_happy_path(ex):
    ok, err, inst = ex.StructTuple.validate(_good_record())
    assert ok is True
    assert err is None
    assert inst is not None
    assert inst.ticker == "AAPL"
    assert inst.confidence == 0.85
    assert len(inst.evidence_anchors) == 2
    assert inst.early_warning_indicators is not None


def test_validate_minimal_record(ex):
    """Only required fields; optional fields omitted."""
    rec = {
        "ticker": "X",
        "as_of_date": "2026-05-13",
        "dynamics_family": "linear_quasi_equilibrium",
        "critical_point_state": "far_from_critical",
        "structural_summary": "Mature utility.",
        "confidence": 0.7,
        "evidence_anchors": [
            {"fact": "P/E ratio 15", "source": "yfinance"},
            {"fact": "Dividend stable 5y", "source": "10-K"},
        ],
    }
    ok, err, inst = ex.StructTuple.validate(rec)
    assert ok is True
    assert inst is not None
    assert inst.company_name is None
    assert inst.early_warning_indicators is None


def test_to_dict_round_trip(ex):
    ok, _, inst = ex.StructTuple.validate(_good_record())
    assert ok and inst is not None
    d = inst.to_dict()
    assert d["ticker"] == "AAPL"
    assert d["evidence_anchors"][0]["fact"].startswith("$3.5T")
    # Re-validate the round-trip
    ok2, _, inst2 = ex.StructTuple.validate(d)
    assert ok2 is True


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_validate_rejects_non_dict(ex):
    ok, err, _ = ex.StructTuple.validate("not a dict")
    assert ok is False
    assert "expected object" in err


def test_validate_missing_required_field(ex):
    rec = _good_record()
    del rec["ticker"]
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "missing required field" in err
    assert "ticker" in err


def test_validate_bad_dynamics_family(ex):
    rec = _good_record()
    rec["dynamics_family"] = "not_a_real_family"
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "dynamics_family" in err


def test_validate_bad_critical_state(ex):
    rec = _good_record()
    rec["critical_point_state"] = "exploding"
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "critical_point_state" in err


def test_validate_bad_date_format(ex):
    rec = _good_record()
    rec["as_of_date"] = "2026/5/13"
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "YYYY-MM-DD" in err


def test_validate_summary_too_long(ex):
    rec = _good_record()
    rec["structural_summary"] = "x" * 700
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "too long" in err


def test_validate_confidence_out_of_range(ex):
    rec = _good_record()
    rec["confidence"] = 1.5
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "out of [0,1]" in err


def test_validate_confidence_not_numeric(ex):
    rec = _good_record()
    rec["confidence"] = "high"
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "not coercible" in err


def test_validate_evidence_anchors_too_few(ex):
    rec = _good_record()
    rec["evidence_anchors"] = [{"fact": "x", "source": "y"}]
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "evidence_anchors length 1" in err


def test_validate_evidence_anchors_too_many(ex):
    rec = _good_record()
    rec["evidence_anchors"] = [{"fact": f"f{i}", "source": "s"} for i in range(6)]
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "evidence_anchors length 6" in err


def test_validate_anchor_missing_source(ex):
    rec = _good_record()
    rec["evidence_anchors"] = [
        {"fact": "x"},
        {"fact": "y", "source": "z"},
    ]
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "missing fact/source" in err


def test_validate_empty_ticker(ex):
    rec = _good_record()
    rec["ticker"] = "   "
    ok, err, _ = ex.StructTuple.validate(rec)
    assert ok is False
    assert "non-empty string" in err


def test_validate_alignment_filters_non_numeric(ex):
    """v4_class_alignment with non-numeric values should be silently filtered."""
    rec = _good_record()
    rec["v4_class_alignment"] = {
        "preferential_attachment": 0.9,
        "soc": "high",  # not numeric -> dropped
        "fold": 0.3,
    }
    ok, _, inst = ex.StructTuple.validate(rec)
    assert ok is True
    assert "preferential_attachment" in inst.v4_class_alignment
    assert "fold" in inst.v4_class_alignment
    assert "soc" not in inst.v4_class_alignment


# ---------------------------------------------------------------------------
# make_prompt()
# ---------------------------------------------------------------------------


def test_make_prompt_with_market_cap(ex):
    company = {
        "ticker": "AAPL",
        "company_name": "Apple Inc.",
        "sector": "tech_hardware",
        "market_cap_bn_usd": 3500,
    }
    p = ex.make_prompt(company, as_of="2026-05-13")
    assert "AAPL" in p
    assert "Apple Inc." in p
    assert "tech_hardware" in p
    assert "$3500B" in p
    assert "2026-05-13" in p


def test_make_prompt_without_market_cap(ex):
    company = {"ticker": "XYZ", "sector": "misc"}
    p = ex.make_prompt(company)
    assert "XYZ" in p
    assert "market cap unknown" in p


def test_make_prompt_enums_present(ex):
    """Sanity check: prompt mentions all 9 dynamics_family enums."""
    company = {"ticker": "T", "sector": "x"}
    p = ex.make_prompt(company)
    for fam in ex.DYNAMICS_FAMILIES:
        if fam != "mixed_or_unclear":
            assert fam in p


# ---------------------------------------------------------------------------
# Enum coverage
# ---------------------------------------------------------------------------


def test_all_dynamics_families_accepted(ex):
    rec = _good_record()
    for fam in ex.DYNAMICS_FAMILIES:
        rec["dynamics_family"] = fam
        ok, err, _ = ex.StructTuple.validate(rec)
        assert ok is True, f"family {fam} failed: {err}"


def test_all_critical_states_accepted(ex):
    rec = _good_record()
    for st in ex.CRITICAL_STATES:
        rec["critical_point_state"] = st
        ok, err, _ = ex.StructTuple.validate(rec)
        assert ok is True, f"state {st} failed: {err}"
