from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/experiment_english_retrieval.py"
SPEC = importlib.util.spec_from_file_location("english_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_frozen_inputs_are_complete_and_fingerprinted():
    rows, qrels, outcomes = MODULE.load_frozen_inputs()
    english_ids = {
        row["id"] for row in rows
        if row["language"] == "en" and not row["labels"]["out_of_scope"]
    }
    assert len(english_ids) == 40
    assert set(qrels) >= english_ids
    assert set(outcomes) >= english_ids
    assert all(set(outcomes[query_id]["top_ids"]) == set(qrels[query_id]) for query_id in english_ids)


def test_metrics_require_exact_fixed_judged_pool():
    qrels = {"q": {"a": 3, "b": 2, "c": 1, "d": 0, "e": 0}}
    perfect = MODULE.judged_pool_metrics({"q": ["a", "b", "c", "d", "e"]}, qrels)
    assert perfect["ndcg_at_5_fixed_judged_pool"] == 1.0
    assert perfect["top1_success_fixed_judged_pool"] == 1.0
    assert perfect["mrr_fixed_judged_pool"] == 1.0
    with pytest.raises(ValueError, match="exactly once"):
        MODULE.judged_pool_metrics({"q": ["a", "b", "c", "d", "x"]}, qrels)


def test_rank_subset_rejects_missing_judged_docs():
    assert MODULE.rank_subset(["x", "b", "a", "c"], {"a", "b", "c"}) == ["b", "a", "c"]
    with pytest.raises(ValueError, match="cover every judged"):
        MODULE.rank_subset(["a", "b", "x"], {"a", "b", "c"})


def test_rrf_is_deterministic_and_rewards_consensus():
    first = MODULE.reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    second = MODULE.reciprocal_rank_fusion([["a", "b", "c"], ["b", "a", "d"]])
    assert first == second
    assert first[:2] == ["a", "b"]


def test_paired_bootstrap_is_deterministic_and_requires_data():
    first = MODULE.paired_bootstrap_ci([0.1, 0.2, -0.1, 0.0], samples=500)
    second = MODULE.paired_bootstrap_ci([0.1, 0.2, -0.1, 0.0], samples=500)
    assert first == second
    assert first[0] <= 0.05 <= first[1]
    with pytest.raises(ValueError, match="required"):
        MODULE.paired_bootstrap_ci([])
