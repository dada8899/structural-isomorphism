"""Sanity tests for v4/scripts/b3_ensemble.py.

These tests cover the pure-function pieces of b3_ensemble.py — `consensus_of`,
`extract_json`, and the IO helpers (`write_taxonomy_v2`, `write_summary`) —
without ever calling DeepSeek. Network is mocked at the urllib layer when
needed.

The module reads `DEEPSEEK_API_KEY` at import time and raises if unset; the
fixture below sets a dummy value so the import succeeds.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Make the env var defined before b3_ensemble.py is imported (module-level
# check would otherwise abort).
os.environ.setdefault("DEEPSEEK_API_KEY", "sk-test-dummy-not-real")

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "v4" / "scripts"))

import b3_ensemble  # noqa: E402


# ---------------------------------------------------------------------------
# consensus_of()
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
# extract_json()
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
# write_taxonomy_v2() — IO contract
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
# write_summary() — schema smoke
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
# Module-level: env var enforcement
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
