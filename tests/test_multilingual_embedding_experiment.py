from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/experiment_multilingual_embedding.py"
SPEC = importlib.util.spec_from_file_location("multilingual_embedding_experiment", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class FakeEncoder:
    """Deterministic local test double; no model import, network, or download."""

    def encode(self, sentences, **kwargs):
        assert kwargs["normalize_embeddings"] is False
        return np.asarray([
            [sum(map(ord, text)) % 17 + 1, len(text) + 1, text.count("?") + 1]
            for text in sentences
        ], dtype=np.float32)


def test_authoritative_inputs_are_complete_and_frozen():
    queries, kb, qrels, outcomes = MODULE.load_frozen_inputs()
    assert len(queries) == 100
    assert len({row["pair_id"] for row in queries}) == 50
    assert len(kb) == len({row["id"] for row in kb}) == 4443
    assert len(qrels) == 80
    assert all(len(pool) == 5 for pool in qrels.values())
    assert all(set(outcomes[query_id]["top_ids"]) == set(pool) for query_id, pool in qrels.items())


def test_normalization_and_ranking_are_guarded_and_deterministic():
    vectors = MODULE.normalize(np.asarray([[3, 4], [1, 0]], dtype=np.float32))
    np.testing.assert_allclose(np.linalg.norm(vectors, axis=1), [1, 1])
    assert MODULE.rank_all(np.asarray([1, 0]), np.asarray([[1, 0], [1, 0], [0, 1]]), ["b", "a", "c"]) == [1, 0, 2]
    with pytest.raises(ValueError, match="zero vector"):
        MODULE.normalize(np.asarray([[0, 0]], dtype=np.float32))


def test_fixed_pool_metrics_reject_candidate_substitution():
    qrels = {"q": {"a": 3, "b": 2, "c": 1, "d": 0, "e": 0}}
    metrics = MODULE.judged_pool_metrics({"q": ["a", "b", "c", "d", "e"]}, qrels)
    assert metrics["ndcg_at_5_fixed_judged_pool"] == 1.0
    assert metrics["mrr_fixed_judged_pool"] == 1.0
    assert metrics["top1_success_fixed_judged_pool"] == 1.0
    with pytest.raises(ValueError, match="exact fixed judged pool"):
        MODULE.judged_pool_metrics({"q": ["a", "b", "c", "d", "x"]}, qrels)


def test_model_tree_fingerprint_is_content_addressed(tmp_path):
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    nested = tmp_path / "1_Pooling"
    nested.mkdir()
    (nested / "config.json").write_text('{"mode":"mean"}', encoding="utf-8")
    first = MODULE.fingerprint_tree(tmp_path)
    second = MODULE.fingerprint_tree(tmp_path)
    assert first == second
    assert first["file_count"] == 2
    assert [row["path"] for row in first["files"]] == ["1_Pooling/config.json", "config.json"]


def test_huggingface_cache_revision_is_resolved_without_network(tmp_path):
    repository = tmp_path / "models--sentence-transformers--example"
    snapshot = repository / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    (repository / "refs").mkdir()
    (repository / "refs" / "main").write_text("abc123\n", encoding="utf-8")
    assert MODULE.resolved_model_path(
        object(), "sentence-transformers/example", cache_dir=tmp_path
    ) == snapshot


def test_fake_encoder_never_downloads_and_json_is_deterministic(tmp_path):
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    (model_dir / "config.json").write_text("{}", encoding="utf-8")
    kwargs = dict(
        model_id=MODULE.DEFAULT_MODEL, requested_revision="test-revision",
        batch_size=1000, candidate_k=5,
    )
    first = MODULE.build_report(FakeEncoder(), model_dir, **kwargs)
    second = MODULE.build_report(FakeEncoder(), model_dir, **kwargs)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["frozen_inputs"]["query_count"] == 100
    assert len(first["paired_top5"]["per_pair"]) == 50
    assert first["fixed_old_english_judged_pool"]["multilingual_dense_rerank"]["queries"] == 40
    assert "not endpoint-comparable" in first["comparability_boundaries"]["not_valid"]
