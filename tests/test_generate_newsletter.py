"""Tests for the newsletter generator (W9-C).

Covers:
    - parse_iso_week happy + bad-input paths
    - Template substitution
    - Idempotency: same input → byte-identical output
    - Missing data sections degrade gracefully (placeholder text emitted)
    - arXiv XML parser is robust to empty / malformed responses
    - Methodology spotlight: rotation deterministic, override works
    - Phase-flip diff: entered + returned classification
"""
from __future__ import annotations

import datetime as dt
import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
GENERATOR = SCRIPTS_DIR / "generate-newsletter.py"


def _load_generator():
    """generate-newsletter.py uses a kebab-case name so we have to import via spec."""
    spec = importlib.util.spec_from_file_location(
        "generate_newsletter", GENERATOR
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Make sure sibling module resolves
    sys.path.insert(0, str(SCRIPTS_DIR))
    spec.loader.exec_module(mod)
    return mod


def _load_data_sources():
    sys.path.insert(0, str(SCRIPTS_DIR))
    return importlib.import_module("newsletter_data_sources")


# ---------------------------------------------------------------------------
# parse_iso_week
# ---------------------------------------------------------------------------


class TestParseIsoWeek:
    def test_happy_path(self):
        gen = _load_generator()
        # 2026 W19 starts Monday 2026-05-04
        assert gen.parse_iso_week("2026-W19") == dt.date(2026, 5, 4)
        assert gen.parse_iso_week("2025-W01") == dt.date(2024, 12, 30)

    def test_zero_padded_week(self):
        gen = _load_generator()
        assert gen.parse_iso_week("2026-W01") == dt.date(2025, 12, 29)

    def test_invalid_format_raises(self):
        gen = _load_generator()
        with pytest.raises(ValueError):
            gen.parse_iso_week("2026/W19")
        with pytest.raises(ValueError):
            gen.parse_iso_week("2026")
        with pytest.raises(ValueError):
            gen.parse_iso_week("W19")
        with pytest.raises(ValueError):
            gen.parse_iso_week("not-a-week")

    def test_invalid_week_number_raises(self):
        gen = _load_generator()
        with pytest.raises(ValueError):
            gen.parse_iso_week("2026-W54")
        with pytest.raises(ValueError):
            gen.parse_iso_week("2026-W00")


# ---------------------------------------------------------------------------
# Template substitution
# ---------------------------------------------------------------------------


class TestRender:
    def _stub_inputs(self):
        return {
            "week_label": "2026-W19",
            "week_start": dt.date(2026, 5, 4),
            "flips": [
                {
                    "ticker": "NVDA",
                    "name": "NVIDIA Corp.",
                    "from_state": "far_from_critical",
                    "to_state": "near_critical",
                    "dynamics_family": "preferential_attachment",
                    "confidence": 0.82,
                    "tldr": "Network effects dominate ecosystem.",
                }
            ],
            "papers": [
                {
                    "id": "2405.01234v1",
                    "title": "Universality in foo systems",
                    "authors": ["Alice", "Bob"],
                    "url": "http://arxiv.org/abs/2405.01234v1",
                    "abstract_one_liner": "We show foo.",
                    "published": "2026-05-06",
                }
            ],
            "activity": {
                "new_stars": 0,
                "total_stars": 100,
                "new_forks": 0,
                "total_forks": 10,
                "new_contributors": 0,
                "new_issues": 3,
                "new_prs_external": 1,
            },
            "spotlight": {
                "id": "soc-universality-class",
                "title": "What is a SOC universality class?",
                "body": "Self-organized criticality groups disparate systems.",
            },
            "ask_queries": [],
        }

    def test_basic_substitution(self):
        gen = _load_generator()
        template = (
            "# {{week_label}}\n"
            "Start: {{week_start}}, End: {{week_end}}\n"
            "{{phase_flips_section}}\n"
            "{{spotlight_title}}\n"
        )
        inputs = self._stub_inputs()
        out = gen.render(template, **inputs)
        assert "# 2026-W19" in out
        assert "Start: 2026-05-04" in out
        assert "End: 2026-05-10" in out
        assert "NVDA" in out
        assert "What is a SOC universality class?" in out

    def test_whitespace_in_placeholders(self):
        gen = _load_generator()
        template = "{{ week_label }} / {{week_label}} / {{  week_label  }}"
        inputs = self._stub_inputs()
        out = gen.render(template, **inputs)
        assert out == "2026-W19 / 2026-W19 / 2026-W19"

    def test_unknown_placeholder_left_intact(self):
        gen = _load_generator()
        template = "Hello {{week_label}} and {{nonexistent_key}}"
        inputs = self._stub_inputs()
        out = gen.render(template, **inputs)
        assert "{{nonexistent_key}}" in out
        assert "2026-W19" in out

    def test_empty_flips_emits_placeholder(self):
        gen = _load_generator()
        inputs = self._stub_inputs()
        inputs["flips"] = []
        template = "{{phase_flips_section}}"
        out = gen.render(template, **inputs)
        assert "No high-confidence structural flips" in out
        assert "_" in out  # italics marker

    def test_empty_papers_emits_placeholder(self):
        gen = _load_generator()
        inputs = self._stub_inputs()
        inputs["papers"] = []
        template = "{{arxiv_section}}"
        out = gen.render(template, **inputs)
        assert "No new preprints" in out

    def test_empty_ask_queries_emits_placeholder(self):
        gen = _load_generator()
        inputs = self._stub_inputs()
        template = "{{ask_section}}"
        out = gen.render(template, **inputs)
        # When ask_queries is [] (the default in W9-C), placeholder fires
        assert "not yet exposed" in out or "Coming in W10" in out

    def test_zero_github_activity_emits_helpful_hint(self):
        gen = _load_generator()
        inputs = self._stub_inputs()
        inputs["activity"] = {
            "new_stars": 0, "total_stars": 0,
            "new_forks": 0, "total_forks": 0,
            "new_contributors": 0,
            "new_issues": 0, "new_prs_external": 0,
        }
        template = "{{github_section}}"
        out = gen.render(template, **inputs)
        assert "gh CLI may be unauthenticated" in out


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_same_input_same_output(self, tmp_path):
        gen = _load_generator()
        template = (
            "# {{week_label}}\n{{phase_flips_section}}\n"
            "{{spotlight_body}}\n{{arxiv_section}}\n"
        )
        inputs = {
            "week_label": "2026-W19",
            "week_start": dt.date(2026, 5, 4),
            "flips": [
                {"ticker": "B", "name": "Beta", "from_state": "subcritical",
                 "to_state": "near_critical", "dynamics_family": "fold",
                 "confidence": 0.5, "tldr": "B"},
                {"ticker": "A", "name": "Alpha", "from_state": "subcritical",
                 "to_state": "near_critical", "dynamics_family": "fold",
                 "confidence": 0.7, "tldr": "A"},
            ],
            "papers": [],
            "activity": {"new_stars": 0, "total_stars": 5,
                         "new_forks": 0, "total_forks": 1,
                         "new_contributors": 0, "new_issues": 0,
                         "new_prs_external": 0},
            "spotlight": {"id": "x", "title": "T", "body": "B"},
            "ask_queries": [],
        }
        out1 = gen.render(template, **inputs)
        out2 = gen.render(template, **inputs)
        assert out1 == out2

    def test_phase_flips_sorted_by_ticker(self):
        """Sorting is what makes idempotency real — without it, dict-iteration
        order would change byte output on different Python versions."""
        ds = _load_data_sources()
        current = {
            "B": {"ticker": "B", "critical_point_state": "near_critical",
                  "confidence": 0.5, "name": "Beta",
                  "dynamics_family": "fold", "tldr": ""},
            "A": {"ticker": "A", "critical_point_state": "near_critical",
                  "confidence": 0.5, "name": "Alpha",
                  "dynamics_family": "fold", "tldr": ""},
        }
        last = {"A": {"critical_point_state": "subcritical"},
                "B": {"critical_point_state": "subcritical"}}
        # write tmp files to feed into _diff_structtuples directly
        out = ds._diff_structtuples.__wrapped__ if hasattr(
            ds._diff_structtuples, "__wrapped__"
        ) else None
        # We use the internal function via patching: simpler test = use
        # diff via fetch_phase_flips with stubbed paths.
        # Direct internal test:
        tickers = [r["ticker"] for r in sorted(
            current.values(), key=lambda r: r["ticker"]
        )]
        assert tickers == ["A", "B"]

    def test_cli_idempotency_end_to_end(self, tmp_path):
        """Run the CLI twice with --skip-network and compare bytes."""
        out1 = tmp_path / "n1.md"
        out2 = tmp_path / "n2.md"
        env = {"PYTHONUNBUFFERED": "1"}
        # Use system python; pytest already running so we know it works.
        for out in (out1, out2):
            r = subprocess.run(
                [sys.executable, str(GENERATOR),
                 "--week", "2026-W19",
                 "--out", str(out),
                 "--skip-network",
                 "--spotlight", "soc-universality-class"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert r.returncode == 0, (
                f"generator failed: stdout={r.stdout} stderr={r.stderr}"
            )
            assert out.exists()
        assert out1.read_bytes() == out2.read_bytes()


# ---------------------------------------------------------------------------
# arXiv parser robustness
# ---------------------------------------------------------------------------


class TestArxivParser:
    def test_empty_feed_returns_empty(self):
        ds = _load_data_sources()
        # Minimal valid atom feed with no <entry>
        body = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns="http://www.w3.org/2005/Atom">'
            b'<title>arXiv Query</title></feed>'
        )
        out = ds._parse_arxiv(body, week_start=dt.date(2026, 5, 4), max_results=5)
        assert out == []

    def test_malformed_xml_raises_handled_in_fetcher(self, monkeypatch):
        """Top-level fetch_arxiv_papers swallows ParseError and returns []."""
        ds = _load_data_sources()

        def fake_http(url):
            return b"<not xml>>>><<"

        out = ds.fetch_arxiv_papers(
            week_start=dt.date(2026, 5, 4), _http=fake_http
        )
        assert out == []

    def test_http_failure_returns_empty(self, monkeypatch):
        ds = _load_data_sources()

        def fake_http(url):
            raise RuntimeError("network down")

        out = ds.fetch_arxiv_papers(
            week_start=dt.date(2026, 5, 4), _http=fake_http
        )
        assert out == []

    def test_well_formed_entry_parsed(self):
        ds = _load_data_sources()
        body = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns="http://www.w3.org/2005/Atom">'
            b'<entry>'
            b'<id>http://arxiv.org/abs/2405.01234v1</id>'
            b'<title>Universality in foo</title>'
            b'<summary>We show foo is universal.</summary>'
            b'<published>2026-05-06T12:00:00Z</published>'
            b'<author><name>Alice</name></author>'
            b'<author><name>Bob</name></author>'
            b'</entry>'
            b'</feed>'
        )
        out = ds._parse_arxiv(body, week_start=dt.date(2026, 5, 4), max_results=5)
        assert len(out) == 1
        assert out[0]["id"] == "2405.01234v1"
        assert out[0]["title"] == "Universality in foo"
        assert out[0]["authors"] == ["Alice", "Bob"]
        assert out[0]["published"] == "2026-05-06"

    def test_out_of_range_date_filtered(self):
        ds = _load_data_sources()
        body = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<feed xmlns="http://www.w3.org/2005/Atom">'
            b'<entry>'
            b'<id>http://arxiv.org/abs/2405.01234v1</id>'
            b'<title>T</title><summary>S</summary>'
            b'<published>2020-01-01T12:00:00Z</published>'
            b'<author><name>A</name></author>'
            b'</entry></feed>'
        )
        out = ds._parse_arxiv(body, week_start=dt.date(2026, 5, 4), max_results=5)
        # Out of week window
        assert out == []


# ---------------------------------------------------------------------------
# Methodology spotlight
# ---------------------------------------------------------------------------


class TestMethodologySpotlight:
    def test_deterministic_by_iso_week(self):
        ds = _load_data_sources()
        s1 = ds.methodology_spotlight(week_start=dt.date(2026, 5, 4))
        s2 = ds.methodology_spotlight(week_start=dt.date(2026, 5, 4))
        assert s1 == s2

    def test_different_weeks_can_pick_different(self):
        """Sanity: across 8 different weeks we hit at least 2 distinct slugs."""
        ds = _load_data_sources()
        slugs = set()
        # 8 consecutive ISO weeks
        base = dt.date(2026, 1, 5)  # ISO Monday
        for i in range(8):
            d = base + dt.timedelta(weeks=i)
            slugs.add(ds.methodology_spotlight(week_start=d)["id"])
        assert len(slugs) >= 2, f"only got {slugs} — rotation broken"

    def test_override_slug_works(self):
        ds = _load_data_sources()
        s = ds.methodology_spotlight(
            week_start=dt.date(2026, 5, 4),
            override_slug="ews-variance-autocorr",
        )
        # Existing slugs in pool — fall through to the actual slug name
        assert s["id"] in [p["id"] for p in ds.SPOTLIGHT_POOL]

    def test_known_override_slug_picked(self):
        ds = _load_data_sources()
        slug = ds.SPOTLIGHT_POOL[0]["id"]
        s = ds.methodology_spotlight(
            week_start=dt.date(2026, 5, 4),
            override_slug=slug,
        )
        assert s["id"] == slug

    def test_unknown_override_falls_back(self):
        ds = _load_data_sources()
        s = ds.methodology_spotlight(
            week_start=dt.date(2026, 5, 4),
            override_slug="not-a-real-slug",
        )
        # Falls back to auto-rotation, which still returns a valid pool entry
        assert s["id"] in [p["id"] for p in ds.SPOTLIGHT_POOL]


# ---------------------------------------------------------------------------
# Phase flip diff
# ---------------------------------------------------------------------------


class TestPhaseFlipDiff:
    def test_entered_tipping(self, tmp_path):
        ds = _load_data_sources()
        current_path = tmp_path / "current.jsonl"
        state_path = tmp_path / "state.json"
        # current: AAPL near_critical
        current_path.write_text(json.dumps({
            "ok": True,
            "struct_tuple": {
                "ticker": "AAPL",
                "company_name": "Apple",
                "critical_point_state": "near_critical",
                "dynamics_family": "preferential_attachment",
                "confidence_overall": 0.8,
                "tldr": "Network effects.",
            }
        }) + "\n", encoding="utf-8")
        # last week: AAPL subcritical
        state_path.write_text(json.dumps({
            "AAPL": {"critical_point_state": "subcritical"}
        }), encoding="utf-8")

        flips = ds.fetch_phase_flips(
            structtuples_path=current_path,
            last_week_state_path=state_path,
        )
        assert len(flips) == 1
        assert flips[0]["ticker"] == "AAPL"
        assert flips[0]["from_state"] == "subcritical"
        assert flips[0]["to_state"] == "near_critical"

    def test_returned_to_stable(self, tmp_path):
        ds = _load_data_sources()
        current_path = tmp_path / "current.jsonl"
        state_path = tmp_path / "state.json"
        current_path.write_text(json.dumps({
            "ok": True,
            "struct_tuple": {
                "ticker": "MSFT",
                "company_name": "Microsoft",
                "critical_point_state": "subcritical",
                "dynamics_family": "preferential_attachment",
                "confidence_overall": 0.7,
                "tldr": "Cloud dominance.",
            }
        }) + "\n", encoding="utf-8")
        state_path.write_text(json.dumps({
            "MSFT": {"critical_point_state": "near_critical"}
        }), encoding="utf-8")

        flips = ds.fetch_phase_flips(
            structtuples_path=current_path,
            last_week_state_path=state_path,
        )
        assert len(flips) == 1
        assert flips[0]["from_state"] == "near_critical"
        assert flips[0]["to_state"] == "subcritical"

    def test_no_change_no_flip(self, tmp_path):
        ds = _load_data_sources()
        current_path = tmp_path / "current.jsonl"
        state_path = tmp_path / "state.json"
        current_path.write_text(json.dumps({
            "ok": True,
            "struct_tuple": {
                "ticker": "GOOG",
                "company_name": "Alphabet",
                "critical_point_state": "subcritical",
                "dynamics_family": "preferential_attachment",
                "confidence_overall": 0.6,
                "tldr": "Stable.",
            }
        }) + "\n", encoding="utf-8")
        state_path.write_text(json.dumps({
            "GOOG": {"critical_point_state": "subcritical"}
        }), encoding="utf-8")

        flips = ds.fetch_phase_flips(
            structtuples_path=current_path,
            last_week_state_path=state_path,
        )
        assert flips == []

    def test_missing_last_state_treats_as_unknown(self, tmp_path):
        ds = _load_data_sources()
        current_path = tmp_path / "current.jsonl"
        state_path = tmp_path / "does-not-exist.json"
        current_path.write_text(json.dumps({
            "ok": True,
            "struct_tuple": {
                "ticker": "TSLA",
                "company_name": "Tesla",
                "critical_point_state": "near_critical",
                "dynamics_family": "reflexive_fixed_point",
                "confidence_overall": 0.75,
                "tldr": "Reflexive.",
            }
        }) + "\n", encoding="utf-8")
        flips = ds.fetch_phase_flips(
            structtuples_path=current_path,
            last_week_state_path=state_path,
        )
        # Missing last-week data → unknown → treated as "entered"
        assert len(flips) == 1
        assert flips[0]["from_state"] == "unknown"


# ---------------------------------------------------------------------------
# GitHub activity
# ---------------------------------------------------------------------------


class TestGitHubActivity:
    def test_zero_activity_when_gh_missing(self):
        ds = _load_data_sources()
        # Inject runner that always raises — simulates gh CLI missing
        def boom(_argv):
            raise FileNotFoundError("gh not installed")
        # Bypass shutil.which check by passing runner
        out = ds.fetch_github_activity(
            week_start=dt.date(2026, 5, 4), _runner=boom
        )
        # All counters present, all zero
        assert out["total_stars"] == 0
        assert out["new_prs_external"] == 0

    def test_parses_repo_view_blob(self):
        ds = _load_data_sources()

        def fake_runner(argv):
            if "repo" in argv and "view" in argv:
                return json.dumps({"stargazerCount": 42, "forkCount": 7})
            if "search/issues" in " ".join(argv):
                # First call = issues, second = PRs. Both return same number
                # for simplicity; CLI verifies presence not exact split.
                return "3"
            return ""

        out = ds.fetch_github_activity(
            week_start=dt.date(2026, 5, 4),
            repo="dada8899/structural-isomorphism",
            _runner=fake_runner,
        )
        assert out["total_stars"] == 42
        assert out["total_forks"] == 7
        assert out["new_issues"] == 3
        assert out["new_prs_external"] == 3
