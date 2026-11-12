"""W11-A coverage for v4/scripts/F3_apply_fwer_correction.py.

Covers the pure functions (_safe_get, _coerce_p, FwerSummary dataclass).
Main entry `main()` is integration-tested via main() roundtrip.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPTS = ROOT / "v4" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Import the script as a module via a synthetic name
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "_f3_fwer", str(SCRIPTS / "F3_apply_fwer_correction.py")
)
_f3 = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
sys.modules["_f3_fwer"] = _f3
_spec.loader.exec_module(_f3)  # type: ignore[union-attr]


# --- _safe_get ---


def test_safe_get_single_level():
    d = {"a": 1}
    assert _f3._safe_get(d, "a") == 1


def test_safe_get_nested():
    d = {"a": {"b": {"c": 42}}}
    assert _f3._safe_get(d, "a", "b", "c") == 42


def test_safe_get_missing_returns_none():
    d = {"a": 1}
    assert _f3._safe_get(d, "b") is None


def test_safe_get_intermediate_non_dict():
    d = {"a": "string_not_dict"}
    assert _f3._safe_get(d, "a", "b") is None


def test_safe_get_empty_keys():
    d = {"a": 1}
    assert _f3._safe_get(d) == d


def test_safe_get_none_value_returns_none():
    d = {"a": None}
    assert _f3._safe_get(d, "a") is None


# --- _coerce_p ---


def test_coerce_p_none():
    assert _f3._coerce_p(None) is None


def test_coerce_p_valid_float():
    assert _f3._coerce_p(0.05) == 0.05


def test_coerce_p_clips_above_one():
    assert _f3._coerce_p(1.5) == 1.0


def test_coerce_p_clips_below_zero():
    assert _f3._coerce_p(-0.5) == 0.0


def test_coerce_p_string_numeric():
    assert _f3._coerce_p("0.03") == 0.03


def test_coerce_p_string_non_numeric():
    assert _f3._coerce_p("abc") is None


def test_coerce_p_nan():
    assert _f3._coerce_p(float("nan")) is None


def test_coerce_p_infinity():
    assert _f3._coerce_p(float("inf")) is None


def test_coerce_p_zero():
    assert _f3._coerce_p(0.0) == 0.0


def test_coerce_p_one():
    assert _f3._coerce_p(1.0) == 1.0


def test_coerce_p_int():
    assert _f3._coerce_p(1) == 1.0


# --- FwerSummary dataclass ---


def test_fwer_summary_dataclass_construction():
    s = _f3.FwerSummary(
        n_tests=10,
        n_significant_raw=5,
        n_significant_bonferroni=2,
        n_significant_holm=3,
        n_significant_bh=4,
    )
    assert s.n_tests == 10
    assert s.n_significant_raw == 5


# --- harvest_pvalues with synthetic validation tree ---


def test_harvest_pvalues_empty_validation_dir(tmp_path, monkeypatch):
    """If no validation files exist, harvest returns empty list."""
    monkeypatch.setattr(_f3, "VALIDATION", tmp_path / "nope")
    out = _f3.harvest_pvalues()
    assert out == []


def test_harvest_pvalues_with_stockmarket(tmp_path, monkeypatch):
    """Synthetic validation tree with one stockmarket file."""
    validation = tmp_path / "validation"
    sm = validation / "soc-stockmarket"
    sm.mkdir(parents=True)
    (sm / "gr_results.json").write_text(json.dumps({
        "clauset_fit": {
            "vs_lognormal_p": 0.03,
            "vs_lognormal_R": -1.2,
            "vs_exponential_p": 0.01,
            "vs_exponential_R": 2.5,
            "alpha": 2.4,
            "n_tail": 1000,
            "winner": "powerlaw",
        }
    }))
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    assert len(out) == 2  # two LR tests
    systems = {r["system"] for r in out}
    assert "stockmarket" in systems
    tests = {r["test"] for r in out}
    assert "Vuong vs lognormal" in tests
    assert "Vuong vs exponential" in tests


def test_harvest_pvalues_skips_bad_json(tmp_path, monkeypatch, capsys):
    """File with unparseable JSON → skipped, no crash."""
    validation = tmp_path / "validation"
    sm = validation / "soc-stockmarket"
    sm.mkdir(parents=True)
    (sm / "gr_results.json").write_text("not valid json {{{")
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    assert out == []
    captured = capsys.readouterr()
    assert "parse error" in captured.out


def test_harvest_pvalues_dotted_path(tmp_path, monkeypatch):
    """defi_aave uses 'aave_v2.power_law' dotted path."""
    validation = tmp_path / "validation"
    defi = validation / "soc-defi"
    defi.mkdir(parents=True)
    (defi / "multiprotocol_results.json").write_text(json.dumps({
        "aave_v2": {
            "power_law": {
                "vs_lognormal_p": 0.02,
                "vs_lognormal_R": 1.0,
                "alpha": 2.0,
            }
        }
    }))
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    systems = {r["system"] for r in out}
    assert "defi_aave" in systems


def test_harvest_pvalues_scheffer_block_bootstrap(tmp_path, monkeypatch):
    """Scheffer adds 2 block-bootstrap tests when present."""
    validation = tmp_path / "validation"
    sch = validation / "scheffer-lake"
    sch.mkdir(parents=True)
    (sch / "lake_results.json").write_text(json.dumps({
        "block_bootstrap": {
            "p_block_bootstrap_ar1": 0.02,
            "p_block_bootstrap_var": 0.04,
            "n_boot": 1000,
        }
    }))
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    tests = {r["test"] for r in out}
    assert "Scheffer AR1 block-bootstrap" in tests
    assert "Scheffer Var block-bootstrap" in tests


def test_harvest_pvalues_skips_missing_key(tmp_path, monkeypatch, capsys):
    """Key path that resolves to None / missing → skip with message."""
    validation = tmp_path / "validation"
    sm = validation / "soc-stockmarket"
    sm.mkdir(parents=True)
    (sm / "gr_results.json").write_text(json.dumps({}))  # missing clauset_fit
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    captured = capsys.readouterr()
    assert "no fit dict" in captured.out


def test_harvest_pvalues_skips_when_no_p_values(tmp_path, monkeypatch):
    """fit dict exists but has no LR p-values → no rows added."""
    validation = tmp_path / "validation"
    sm = validation / "soc-stockmarket"
    sm.mkdir(parents=True)
    (sm / "gr_results.json").write_text(json.dumps({
        "clauset_fit": {"alpha": 2.5, "n_tail": 100}
    }))
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    assert out == []


def test_harvest_pvalues_compare_vs_alias(tmp_path, monkeypatch):
    """Alternative key name 'compare_vs_lognormal_p' should also be accepted."""
    validation = tmp_path / "validation"
    sm = validation / "soc-wildfire"
    sm.mkdir(parents=True)
    (sm / "wildfire_results.json").write_text(json.dumps({
        "powerlaw_fit": {
            "compare_vs_lognormal_p": 0.04,
            "compare_vs_lognormal_R": -0.5,
            "alpha": 2.3,
            "n_tail": 500,
        }
    }))
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    out = _f3.harvest_pvalues()
    assert len(out) >= 1
    assert out[0]["p_value"] == 0.04


def test_main_writes_summary_files(tmp_path, monkeypatch, capsys):
    """Full integration: main() harvests, corrects, writes JSONL + summary."""
    validation = tmp_path / "validation"
    sm = validation / "soc-stockmarket"
    sm.mkdir(parents=True)
    (sm / "gr_results.json").write_text(json.dumps({
        "clauset_fit": {
            "vs_lognormal_p": 0.001,
            "vs_lognormal_R": 1.0,
            "vs_exponential_p": 0.5,
            "vs_exponential_R": 1.0,
            "alpha": 2.5,
            "n_tail": 1000,
        }
    }))
    results = tmp_path / "results"
    results.mkdir()
    monkeypatch.setattr(_f3, "VALIDATION", validation)
    monkeypatch.setattr(_f3, "RESULTS", results)

    _f3.main()
    captured = capsys.readouterr()
    # Output files present
    out_jsonl = results / "F3_fwer_corrected.jsonl"
    out_summary = results / "F3_fwer_summary.json"
    assert out_jsonl.exists()
    assert out_summary.exists()
    summary = json.loads(out_summary.read_text())
    assert "n_tests" in summary
    assert summary["n_tests"] == 2  # ln + exp
    assert "alpha" in summary
