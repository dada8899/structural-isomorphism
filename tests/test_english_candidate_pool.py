import json
from pathlib import Path

import pytest

from scripts.build_english_candidate_pool import (
    atomic_write_jsonl,
    build_pool,
    validate_pool,
)


FINGERPRINTS = {
    "dataset_sha256": "dataset", "kb_sha256": "kb", "model_sha256": "model",
    "embeddings_sha256": "embed", "code_sha256": "code", "code_git_sha": "git",
    "artifact_id": "artifact",
}


def fixtures():
    dataset, kb = [], []
    for number in range(1, 41):
        pair = f"pair-{number:02d}"
        labels = {"out_of_scope": False}
        dataset.extend([
            {"id": f"en-{number:02d}", "pair_id": pair, "language": "en", "query": f"en query {number}", "labels": labels},
            {"id": f"zh-{number:02d}", "pair_id": pair, "language": "zh", "query": f"zh query {number}", "labels": labels},
        ])
    for number in range(1, 13):
        kb.append({"id": f"doc-{number:02d}", "name": f"Doc {number}", "domain": "test", "description": "valid"})
    return dataset, kb


def ranker(query):
    if query.startswith("en"):
        return [f"doc-{number:02d}" for number in range(1, 11)]
    return [f"doc-{number:02d}" for number in range(3, 13)]


def test_build_pool_deduplicates_and_preserves_both_ranks():
    dataset, kb = fixtures()
    rows = build_pool(dataset, kb, ranker, FINGERPRINTS)
    assert len(rows) == 40
    assert all(row["candidate_count"] == 12 for row in rows)
    shared = next(candidate for candidate in rows[0]["candidates"] if candidate["doc_id"] == "doc-03")
    assert shared["provenance"] == [
        {"source": "original_english", "rank": 3},
        {"source": "reference_chinese", "rank": 1},
    ]


def test_build_pool_is_deterministic():
    dataset, kb = fixtures()
    first = build_pool(dataset, kb, ranker, FINGERPRINTS)
    second = build_pool(list(reversed(dataset)), kb, ranker, FINGERPRINTS)
    assert first == second


def test_unknown_candidate_fails_allowlist():
    dataset, kb = fixtures()
    def bad_ranker(query):
        return ranker(query)[:9] + ["invented"]
    with pytest.raises(ValueError, match="unknown KB ids"):
        build_pool(dataset, kb, bad_ranker, FINGERPRINTS)


def test_schema_rejects_incomplete_provenance():
    dataset, kb = fixtures()
    rows = build_pool(dataset, kb, ranker, FINGERPRINTS)
    rows[0]["candidates"][0]["provenance"] = []
    with pytest.raises(ValueError, match="provenance is required"):
        validate_pool(rows, {row["id"] for row in kb}, FINGERPRINTS, top_k=10)


def test_atomic_output_is_valid_jsonl(tmp_path: Path):
    dataset, kb = fixtures()
    rows = build_pool(dataset, kb, ranker, FINGERPRINTS)
    output = tmp_path / "nested" / "pool.jsonl"
    atomic_write_jsonl(output, rows)
    loaded = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert loaded == rows
    assert not list(output.parent.glob(f".{output.name}.*"))
