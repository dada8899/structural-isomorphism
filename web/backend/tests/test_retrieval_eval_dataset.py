"""Contract tests for the canonical product retrieval benchmark."""

from __future__ import annotations

import importlib.util
import copy
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "evaluate_retrieval_v1.py"
SPEC = importlib.util.spec_from_file_location("evaluate_retrieval_v1", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_retrieval_eval_v1_contract():
    rows = MODULE.load_dataset(ROOT / "evaluation" / "retrieval-v1.jsonl")
    assert len(rows) == 100
    assert sum(row["language"] == "zh" for row in rows) == 50
    assert sum(row["language"] == "en" for row in rows) == 50
    assert sum(row["labels"]["out_of_scope"] for row in rows) == 20

    ids = {row["id"] for row in rows}
    assert len(ids) == len(rows)
    for row in rows:
        assert set(row) == {"id", "pair_id", "language", "query", "labels"}
        assert isinstance(row["id"], str) and row["id"]
        assert isinstance(row["pair_id"], str) and row["pair_id"]
        assert row["language"] in {"zh", "en"}
        assert isinstance(row["query"], str)
        labels = row["labels"]
        assert set(labels) == {
            "out_of_scope",
            "scope_reason",
            "accepted_type_ids",
            "require_cross_domain",
            "min_relevant_at_5",
            "note",
        }
        assert type(labels["out_of_scope"]) is bool
        assert type(labels["require_cross_domain"]) is bool
        assert type(labels["min_relevant_at_5"]) is int
        assert isinstance(labels["accepted_type_ids"], list)
        assert all(isinstance(type_id, str) and type_id for type_id in labels["accepted_type_ids"])


def test_retrieval_eval_generator_is_deterministic():
    before = (ROOT / "evaluation" / "retrieval-v1.jsonl").read_bytes()
    spec = importlib.util.spec_from_file_location(
        "build_retrieval_eval", ROOT / "scripts" / "build_retrieval_eval.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.main()
    assert (ROOT / "evaluation" / "retrieval-v1.jsonl").read_bytes() == before


def test_retrieval_eval_jsonl_is_canonically_serialized():
    path = ROOT / "evaluation" / "retrieval-v1.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines
    assert all(line == json.dumps(json.loads(line), ensure_ascii=False, sort_keys=True) for line in lines)


def test_all_gold_oos_cases_are_refused_by_shared_guard():
    from services.scope_guard import is_out_of_scope

    rows = MODULE.load_dataset(ROOT / "evaluation" / "retrieval-v1.jsonl")
    for row in rows:
        if not row["labels"]["out_of_scope"]:
            continue
        refused, reason = is_out_of_scope(row["query"])
        assert refused, row["id"]
        assert reason == row["labels"]["scope_reason"], row["id"]


def test_all_gold_in_scope_cases_pass_shared_guard():
    from services.scope_guard import is_out_of_scope

    rows = MODULE.load_dataset(ROOT / "evaluation" / "retrieval-v1.jsonl")
    for row in rows:
        if row["labels"]["out_of_scope"]:
            continue
        refused, reason = is_out_of_scope(row["query"])
        assert not refused, f"{row['id']}: {reason}"
        assert reason == "ok", row["id"]


def test_qrels_fail_closed_when_dataset_content_changes(tmp_path):
    report = json.loads(
        (ROOT / "evaluation" / "results" / "retrieval-v1-local-baseline.json").read_text()
    )
    dataset = tmp_path / "retrieval-v1.jsonl"
    rows = MODULE.load_dataset(ROOT / "evaluation" / "retrieval-v1.jsonl")
    changed = copy.deepcopy(rows)
    changed[0]["query"] += " changed"
    dataset.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in changed),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="dataset_sha256"):
        MODULE.add_qrel_metrics(
            {}, report["outcomes"], ROOT / "evaluation" / "qrels-v1.jsonl",
            dataset_path=dataset,
            kb_path=ROOT / "data" / "kb-expanded.jsonl",
            frozen_results_path=ROOT / "evaluation" / "results" / "retrieval-v1-local-baseline.json",
        )
