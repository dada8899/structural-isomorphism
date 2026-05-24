"""Tests for the W7-D weekly signals newsletter pipeline (2026-05-24).

Three scenarios per the mini-brief:
  1. generate: real-data path picks 6 near_critical companies, writes file
  2. buttondown mock: no API key → returns ok with mode=mock, no HTTP
  3. empty-data fallback: zero near_critical companies → graceful empty doc

Run:
    cd /Users/dadamini/Projects/structural-isomorphism
    .venv/bin/python3 -m pytest tests/test_generate_weekly_signals.py -v
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    """Load a module from an explicit .py path (scripts/ isn't a package)."""
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gen_mod():
    return _load(
        "generate_weekly_signals",
        REPO_ROOT / "scripts" / "generate_weekly_signals.py",
    )


@pytest.fixture(scope="module")
def send_mod():
    return _load(
        "send_to_buttondown",
        REPO_ROOT / "scripts" / "send_to_buttondown.py",
    )


***REMOVED*** ---------- 1. generate ----------

def test_generate_picks_6_near_critical(tmp_path, monkeypatch, gen_mod):
    """Real-shaped data → exactly 6 picks, highest-confidence first, output file written."""
    data = [
        {"ticker": f"T{i:02d}", "name": f"Co {i}", "phase": "near_critical",
         "confidence": 0.50 + i * 0.03, "dynamics_family": "bistable",
         "delta_signal": (i - 4) * 0.1, "primary_quote": f"q{i}"}
        for i in range(10)
    ] + [
        {"ticker": "S01", "name": "Stable", "phase": "stable",
         "confidence": 0.99, "dynamics_family": "stationary"},
    ]
    data_file = tmp_path / "data" / "phase-detector" / "latest.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text(json.dumps(data), encoding="utf-8")

    monkeypatch.setattr(gen_mod, "_PHASE_DATA_CANDIDATES", [data_file])

    out_md = tmp_path / "issue.md"
    rc = gen_mod.main([
        "--week", "2026-05-25",
        "--out", str(out_md),
        "--no-llm",       ***REMOVED*** avoid network
        "--no-chart",     ***REMOVED*** avoid matplotlib dep in CI
    ])
    assert rc == 0
    assert out_md.exists()

    text = out_md.read_text(encoding="utf-8")
    ***REMOVED*** 6 picks, highest-confidence first → T09, T08, T07, T06, T05, T04
    assert "| `T09` |" in text
    assert "| `T08` |" in text
    assert "| `T04` |" in text
    ***REMOVED*** Lowest confidence rows NOT in (T00..T03)
    assert "| `T03` |" not in text
    ***REMOVED*** Header / footer markers present
    assert "Structural Signals — week of 2026-05-25" in text
    assert "Data source: **real**" in text
    assert "Not financial advice" in text


***REMOVED*** ---------- 2. buttondown mock ----------

def test_send_to_buttondown_mock_mode(tmp_path, send_mod):
    """No API key → mock mode, no HTTP, ok=True."""
    md = tmp_path / "issue.md"
    md.write_text("***REMOVED*** My subject line\n\nbody text\n", encoding="utf-8")

    result = send_mod.send(md_path=md, api_key=None)
    assert result["ok"] is True
    assert result["mode"] == "mock"
    assert result["subject"] == "My subject line"
    assert result["status"] == "draft"
    assert result["response"] is None


def test_send_to_buttondown_dry_run_skips_http(tmp_path, send_mod):
    """API key present but --dry-run → no HTTP, mode=dry-run."""
    md = tmp_path / "issue.md"
    md.write_text("***REMOVED*** Subject\n\nbody\n", encoding="utf-8")

    result = send_mod.send(
        md_path=md, api_key="btn_pat_fake", dry_run=True,
    )
    assert result["ok"] is True
    assert result["mode"] == "dry-run"


def test_send_to_buttondown_uses_h1_as_subject(tmp_path, send_mod):
    md = tmp_path / "issue.md"
    md.write_text(
        "Some preamble\n***REMOVED*** The real subject\nmore text\n", encoding="utf-8",
    )
    result = send_mod.send(md_path=md, api_key=None)
    assert result["subject"] == "The real subject"


***REMOVED*** ---------- 3. empty-data fallback ----------

def test_empty_data_emits_graceful_doc(tmp_path, monkeypatch, gen_mod):
    """Zero near_critical companies → file is still written with empty-state copy."""
    data_file = tmp_path / "data" / "phase-detector" / "latest.json"
    data_file.parent.mkdir(parents=True, exist_ok=True)
    data_file.write_text(json.dumps([
        {"ticker": "STBL", "phase": "stable", "confidence": 0.9},
    ]), encoding="utf-8")

    monkeypatch.setattr(gen_mod, "_PHASE_DATA_CANDIDATES", [data_file])

    out_md = tmp_path / "issue-empty.md"
    rc = gen_mod.main([
        "--week", "2026-05-25",
        "--out", str(out_md),
        "--no-llm", "--no-chart",
    ])
    assert rc == 0
    assert out_md.exists()
    text = out_md.read_text(encoding="utf-8")
    assert "No near-critical structural signals this week" in text
    assert "null weeks are real signal" in text


def test_monday_of_iso_week(gen_mod):
    """Sanity: 2026-05-25 is itself a Monday."""
    monday = gen_mod.monday_of_iso_week(dt.date(2026, 5, 28))
    assert monday == dt.date(2026, 5, 25)
    ***REMOVED*** Already Monday → stays
    assert gen_mod.monday_of_iso_week(dt.date(2026, 5, 25)) == dt.date(2026, 5, 25)
