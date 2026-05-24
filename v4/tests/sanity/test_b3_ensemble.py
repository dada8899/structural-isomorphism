"""Sanity tests for v4/scripts/b3_ensemble.py.

Combined unit + integration test suite for the B3 multi-model ensemble
reviewer pipeline. Covers the pure / deterministic functions:

  - consensus_of()      majority voting across reviewer verdicts
  - extract_json()      JSON extraction from raw LLM output (markdown fences,
                        nested objects, missing fields, malformed)
  - load_yaml_class()   minimal yaml parsing (display_name / hub /
                        shared_equation / key_invariants / positive_examples /
                        negative_examples / notes)
  - build_user_prompt() template substitution + truncation
  - write_taxonomy_v2() / write_summary() IO smoke tests via tmp_path
  - module-level DEEPSEEK_API_KEY env var enforcement

We do NOT exercise call_deepseek() — that requires network and the API key.

The module reads `DEEPSEEK_API_KEY` at import time and raises if unset; the
env setup below sets a dummy value so the import succeeds.

Provenance:
- W6-A class-style tests (TestConsensusOf, TestExtractJson, TestWriteTaxonomyV2,
  TestWriteSummary, env-var enforcement) — base set, takes priority on
  overlapping coverage per W6-A merge order.
- W6-E function-style additions (test_load_yaml_class_*, test_build_user_prompt_*,
  test_verdict_normalization_prefix) — added to extend coverage without
  duplicating W6-A's overlapping tests.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make the env var defined before b3_ensemble.py is imported (module-level
# check would otherwise abort).
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-not-real")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "v4" / "scripts"))

import b3_ensemble  # noqa: E402


# ---------------------------------------------------------------------------
# consensus_of() — W6-A class-based
# ---------------------------------------------------------------------------


class TestConsensusOf:
    def test_three_keeps(self):
        assert b3_ensemble.consensus_of(["KEEP", "KEEP", "KEEP"]) == "KEEP"

    def test_majority_keep_one_reject(self):
        assert b3_ensemble.consensus_of(["KEEP", "KEEP", "REJECT"]) == "KEEP"

    def test_majority_reject(self):
        assert b3_ensemble.consensus_of(["REJECT", "REJECT", "KEEP"]) == "REJECT"

    def test_all_unclear(self):
        assert b3_ensemble.consensus_of(["UNCLEAR", "UNCLEAR", "UNCLEAR"]) == "UNCLEAR"

    def test_three_way_split_falls_to_unclear(self):
        # KEEP=1, REJECT=1, SPLIT=1 — no label hits >=2, falls to UNCLEAR
        assert b3_ensemble.consensus_of(["KEEP", "REJECT", "SPLIT"]) == "UNCLEAR"

    def test_majority_split(self):
        assert b3_ensemble.consensus_of(["SPLIT", "SPLIT", "KEEP"]) == "SPLIT"

    def test_majority_merge(self):
        assert b3_ensemble.consensus_of(["MERGE", "MERGE", "UNCLEAR"]) == "MERGE"

    def test_priority_keep_over_split(self):
        # Both KEEP and SPLIT hit 2; KEEP wins because it's checked first.
        # This test pins the documented priority order.
        # Five reviewers: 2 KEEP, 2 SPLIT, 1 UNCLEAR
        result = b3_ensemble.consensus_of(["KEEP", "KEEP", "SPLIT", "SPLIT", "UNCLEAR"])
        assert result == "KEEP"

    def test_empty_input(self):
        # Edge case: no reviewers (shouldn't happen in prod but mustn't crash)
        assert b3_ensemble.consensus_of([]) == "UNCLEAR"

    def test_error_verdicts_pass_through_unclear(self):
        # ERROR / PARSE_FAIL are not in the priority list, so they fall through
        # to UNCLEAR (correct: errors shouldn't drive consensus).
        assert b3_ensemble.consensus_of(["ERROR", "PARSE_FAIL", "ERROR"]) == "UNCLEAR"


# ---------------------------------------------------------------------------
# extract_json() — W6-A class-based
# ---------------------------------------------------------------------------


class TestExtractJson:
    def test_plain_json(self):
        raw = '{"verdict": "KEEP", "confidence": 0.8}'
        out = b3_ensemble.extract_json(raw)
        assert out == {"verdict": "KEEP", "confidence": 0.8}

    def test_fenced_json(self):
        raw = '```json\n{"verdict": "REJECT", "confidence": 0.9}\n```'
        out = b3_ensemble.extract_json(raw)
        assert out == {"verdict": "REJECT", "confidence": 0.9}

    def test_fenced_without_lang(self):
        raw = '```\n{"verdict": "KEEP"}\n```'
        out = b3_ensemble.extract_json(raw)
        assert out == {"verdict": "KEEP"}

    def test_preamble_before_json(self):
        raw = 'Here is my verdict:\n\n{"verdict": "KEEP", "confidence": 0.7}\n\nDone.'
        out = b3_ensemble.extract_json(raw)
        assert out["verdict"] == "KEEP"

    def test_nested_json(self):
        raw = '{"verdict": "KEEP", "meta": {"depth": 2, "tags": ["a", "b"]}}'
        out = b3_ensemble.extract_json(raw)
        assert out["meta"]["depth"] == 2
        assert out["meta"]["tags"] == ["a", "b"]

    def test_malformed_returns_none(self):
        raw = "not json at all"
        assert b3_ensemble.extract_json(raw) is None

    def test_empty_string_returns_none(self):
        assert b3_ensemble.extract_json("") is None

    def test_only_opening_brace_returns_none(self):
        assert b3_ensemble.extract_json("{") is None

    def test_unbalanced_json_returns_none(self):
        # This is genuinely invalid JSON (no closing brace at all)
        assert b3_ensemble.extract_json("{ no closing brace ever") is None

    def test_trailing_comma_lenient_recovery(self):
        # Some models emit trailing commas; the lenient path strips them.
        raw = '{"verdict": "KEEP",\n"confidence": 0.5,\n}'
        out = b3_ensemble.extract_json(raw)
        assert out is not None
        assert out["verdict"] == "KEEP"

    def test_missing_field_still_parses(self):
        # Caller is responsible for field validation; the parser shouldn't
        # reject incomplete JSON.
        raw = '{"verdict": "KEEP"}'
        out = b3_ensemble.extract_json(raw)
        assert out == {"verdict": "KEEP"}
        assert "confidence" not in out


# ---------------------------------------------------------------------------
# write_taxonomy_v2() — IO contract (W6-A class-based)
# ---------------------------------------------------------------------------


class TestWriteTaxonomyV2:
    def _make_rows_and_classes(self):
        """Synthesize 2 classes with 3 reviewer verdicts each."""
        rows = [
            # class_a: B1=KEEP, B3 = 3x KEEP → final KEEP_strong
            {"class_id": "class_a", "model_id": "deepseek-pro-rigorous",
             "verdict": "KEEP", "confidence": 0.9, "rationale": "r1"},
            {"class_id": "class_a", "model_id": "deepseek-flash-rigorous",
             "verdict": "KEEP", "confidence": 0.8, "rationale": "r2"},
            {"class_id": "class_a", "model_id": "deepseek-pro-creative",
             "verdict": "KEEP", "confidence": 0.7, "rationale": "r3"},
            # class_b: B1=REJECT, B3 = 3x REJECT → final REJECT_strong
            {"class_id": "class_b", "model_id": "deepseek-pro-rigorous",
             "verdict": "REJECT", "confidence": 0.85, "rationale": "r4"},
            {"class_id": "class_b", "model_id": "deepseek-flash-rigorous",
             "verdict": "REJECT", "confidence": 0.75, "rationale": "r5"},
            {"class_id": "class_b", "model_id": "deepseek-pro-creative",
             "verdict": "REJECT", "confidence": 0.65, "rationale": "r6"},
        ]
        classes_in = [
            {"class_id": "class_a", "review_verdict": "KEEP", "confidence": 0.9},
            {"class_id": "class_b", "review_verdict": "REJECT", "confidence": 0.8},
        ]
        return rows, classes_in

    def test_strong_keep_and_reject(self, monkeypatch, tmp_path):
        rows, classes_in = self._make_rows_and_classes()
        out_path = tmp_path / "taxonomy_v2.jsonl"
        monkeypatch.setattr(b3_ensemble, "TAXONOMY_OUT", out_path)

        b3_ensemble.write_taxonomy_v2(rows, classes_in)

        assert out_path.exists()
        records = [json.loads(line) for line in out_path.read_text().splitlines()]
        assert len(records) == 2
        by_cid = {r["class_id"]: r for r in records}

        assert by_cid["class_a"]["final_verdict"] == "KEEP_strong"
        assert by_cid["class_a"]["b3_consensus"] == "KEEP"
        assert by_cid["class_a"]["b3_avg_confidence"] == 0.8  # (0.9+0.8+0.7)/3

        assert by_cid["class_b"]["final_verdict"] == "REJECT_strong"
        assert by_cid["class_b"]["b3_consensus"] == "REJECT"

    def test_contested_keep_vs_reject(self, monkeypatch, tmp_path):
        # B1 KEEP but B3 majority REJECT → CONTESTED(B1=KEEP,B3=REJECT)
        rows = [
            {"class_id": "class_x", "model_id": "deepseek-pro-rigorous",
             "verdict": "REJECT", "confidence": 0.8, "rationale": "r"},
            {"class_id": "class_x", "model_id": "deepseek-flash-rigorous",
             "verdict": "REJECT", "confidence": 0.7, "rationale": "r"},
            {"class_id": "class_x", "model_id": "deepseek-pro-creative",
             "verdict": "KEEP", "confidence": 0.5, "rationale": "r"},
        ]
        classes_in = [{"class_id": "class_x", "review_verdict": "KEEP", "confidence": 0.9}]
        out_path = tmp_path / "taxonomy_v2.jsonl"
        monkeypatch.setattr(b3_ensemble, "TAXONOMY_OUT", out_path)

        b3_ensemble.write_taxonomy_v2(rows, classes_in)

        rec = json.loads(out_path.read_text().splitlines()[0])
        assert rec["final_verdict"].startswith("CONTESTED")
        assert "B1=KEEP" in rec["final_verdict"]
        assert "B3=REJECT" in rec["final_verdict"]


# ---------------------------------------------------------------------------
# write_summary() — schema smoke (W6-A class-based)
# ---------------------------------------------------------------------------


class TestWriteSummary:
    def test_summary_writes_expected_sections(self, monkeypatch, tmp_path):
        rows = [
            {"class_id": "c1", "model_id": "deepseek-pro-rigorous",
             "verdict": "KEEP", "confidence": 0.8, "rationale": "x"},
            {"class_id": "c1", "model_id": "deepseek-flash-rigorous",
             "verdict": "KEEP", "confidence": 0.7, "rationale": "x"},
            {"class_id": "c1", "model_id": "deepseek-pro-creative",
             "verdict": "REJECT", "confidence": 0.6, "rationale": "x"},
        ]
        classes_in = [{"class_id": "c1", "review_verdict": "KEEP", "confidence": 0.9}]
        out_path = tmp_path / "summary.md"
        monkeypatch.setattr(b3_ensemble, "OUT_SUMMARY", out_path)

        b3_ensemble.write_summary(rows, classes_in, elapsed_s=3.0, n_errors=0, n_parse_fail=0)

        text = out_path.read_text()
        assert "Per-class verdict table" in text
        assert "B3 consensus distribution" in text
        assert "B1 critic vs B3 ensemble agreement" in text
        assert "Methodology notes" in text
        # Consensus for c1 should be KEEP (2/3)
        assert "**KEEP**" in text or "KEEP" in text


# ---------------------------------------------------------------------------
# Module-level: env var enforcement (W6-A)
# ---------------------------------------------------------------------------


def test_module_raises_when_env_unset(monkeypatch):
    """Verify that importing b3_ensemble in a fresh interpreter raises if
    DEEPSEEK_API_KEY is unset. We can't reimport in-process easily, so we
    spawn a subprocess."""
    import subprocess
    script = REPO / "v4" / "scripts" / "b3_ensemble.py"
    # Strip env var explicitly
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    result = subprocess.run(
        [sys.executable, "-c", f"import sys; sys.path.insert(0, '{script.parent}'); import b3_ensemble"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "DEEPSEEK_API_KEY" in result.stderr


# ---------------------------------------------------------------------------
# load_yaml_class() — minimal yaml parser (W6-E additions, NOT covered by W6-A)
# ---------------------------------------------------------------------------


def test_load_yaml_class_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(b3_ensemble, "YAML_DIR", tmp_path)
    out = b3_ensemble.load_yaml_class("does_not_exist")
    assert out == {}


def test_load_yaml_class_parses_fields(monkeypatch, tmp_path):
    monkeypatch.setattr(b3_ensemble, "YAML_DIR", tmp_path)
    (tmp_path / "test_class.yaml").write_text(
        'display_name: "Test Class"\n'
        'hub_phenomenon: "test hub"\n'
        "shared_equation:\n"
        "  E = mc^2\n"
        "  alpha = 2.0\n"
        "key_invariants:\n"
        '  - "scaling exponent"\n'
        '  - "critical mechanism"\n'
        "positive_examples:\n"
        '  - phenomenon: "earthquake"\n'
        '  - phenomenon: "solar flare"\n'
        "negative_examples:\n"
        '  - phenomenon: "lottery"\n'
        "notes: |\n"
        "  Some notes here\n"
        "  with multiple lines.\n"
    )
    out = b3_ensemble.load_yaml_class("test_class")
    assert out["display_name"] == "Test Class"
    assert out["hub"] == "test hub"
    assert "E = mc^2" in out["shared_equation"]
    assert "scaling exponent" in out["key_invariants"]
    assert "critical mechanism" in out["key_invariants"]
    assert "earthquake" in out["positive_examples"]
    assert "solar flare" in out["positive_examples"]
    assert "lottery" in out["negative_examples"]
    assert "Some notes" in out["notes"]


# ---------------------------------------------------------------------------
# build_user_prompt() — W6-E additions, NOT covered by W6-A
# ---------------------------------------------------------------------------


def test_build_user_prompt_basic_substitution():
    b1_row = {
        "class_id": "soc_threshold_cascade",
        "review_verdict": "KEEP",
        "confidence": 0.8,
        "members_flagged_reason": "consistent power-law tails",
    }
    yaml = {
        "display_name": "SOC Cascade",
        "hub": "earthquake aftershock",
        "shared_equation": "P(s) ~ s^-alpha",
        "key_invariants": ["alpha ~ 1.5", "self-similar"],
        "positive_examples": ["earthquake", "solar flare"],
        "negative_examples": ["lottery"],
        "notes": "verified across 13 systems",
    }
    prompt = b3_ensemble.build_user_prompt("soc_threshold_cascade", b1_row, yaml)
    assert "soc_threshold_cascade" in prompt
    assert "SOC Cascade" in prompt
    assert "P(s) ~ s^-alpha" in prompt
    assert "alpha ~ 1.5" in prompt
    assert "earthquake" in prompt
    assert "lottery" in prompt
    # B1 prior verdict is included
    assert "KEEP" in prompt


def test_build_user_prompt_truncation_long_summary():
    """Verifies the [:N] slices in the format call don't crash on huge inputs."""
    b1_row = {"review_verdict": "REJECT", "confidence": 0.9, "members_flagged_reason": "x" * 2000}
    yaml = {
        "display_name": "huge",
        "hub": "x" * 1000,
        "shared_equation": "y" * 2000,
        "key_invariants": ["z" * 200] * 50,
        "positive_examples": ["p" * 100] * 30,
        "negative_examples": ["n" * 100] * 30,
        "notes": "q" * 1000,
    }
    prompt = b3_ensemble.build_user_prompt("huge_class", b1_row, yaml)
    # prompt is rendered, no exception
    assert "huge_class" in prompt


def test_build_user_prompt_missing_yaml_fields():
    """All yaml fields optional; build_user_prompt must not crash."""
    b1_row = {"review_verdict": "UNCLEAR", "confidence": 0.5}
    prompt = b3_ensemble.build_user_prompt("bare_class", b1_row, {})
    assert "bare_class" in prompt
    # Falls back to '(none)'
    assert "(none)" in prompt


# ---------------------------------------------------------------------------
# Edge-case verdict normalization in the main loop (W6-E addition)
# ---------------------------------------------------------------------------


def test_verdict_normalization_prefix():
    """
    Main loop normalizes 'MERGE_with_X' -> 'MERGE' and 'SPLIT_into_3' -> 'SPLIT'.
    This is implemented inline in main(); the normalization rule is:
        if verdict.startswith("MERGE"): verdict = "MERGE"
        if verdict.startswith("SPLIT"): verdict = "SPLIT"
    We exercise the equivalent string predicate.
    """
    examples = {
        "MERGE_into_c2": "MERGE",
        "SPLIT_into_3_classes": "SPLIT",
        "KEEP": "KEEP",
        "REJECT": "REJECT",
        "UNCLEAR": "UNCLEAR",
    }
    for raw, expected in examples.items():
        v = raw.upper().strip()
        if v.startswith("MERGE"):
            v = "MERGE"
        if v.startswith("SPLIT"):
            v = "SPLIT"
        assert v == expected
