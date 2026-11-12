import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.judge_english_candidate_pool import (
    OUTPUT_SCHEMA,
    atomic_write,
    judge_pool,
    load_pool,
    load_resume,
    load_seed,
)


META = {
    "candidate_pool_sha256": "pool", "dataset_sha256": "dataset", "kb_sha256": "kb",
    "model_sha256": "model", "embeddings_sha256": "embed", "code_sha256": "code",
    "code_git_sha": "git", "artifact_id": "artifact",
}


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def pool_fixture():
    return [{
        "query_id": f"q-{number:02d}", "query": f"query {number}",
        "candidates": [{"doc_id": "d1", "name": "one", "domain": "x", "description": "a"},
                       {"doc_id": "d2", "name": "two", "domain": "y", "description": "b"}],
    } for number in range(40)]


def verdict(batch):
    return {"judgments": [{
        "query_id": batch[0]["query_id"], "doc_id": candidate["doc_id"], "relevance": 2,
        "target_domain": candidate["domain"], "mechanism": "shared", "reason": "valid",
    } for candidate in batch[0]["candidates"]]}


def test_seed_is_reused_and_provider_only_sees_missing(tmp_path):
    pool = pool_fixture()
    allowed = {(q["query_id"], c["doc_id"]) for q in pool for c in q["candidates"]}
    seed_path = tmp_path / "seed.jsonl"
    write_jsonl(seed_path, [{
        "schema_version": "qrels-v1", "query_id": q["query_id"], "doc_id": "d1",
        "relevance": 3, "target_domain": "x", "mechanism": "seed", "reason": "old",
        "judge_model": "seed-model", "dataset_sha256": "dataset", "kb_sha256": "kb",
    } for q in pool])
    completed = load_seed(seed_path, allowed, META)
    seen = []
    def provider(batch):
        seen.append(batch)
        return verdict(batch)
    result = judge_pool(pool, META, completed, model="new-model", provider=provider, output=tmp_path / "out.jsonl", sleep=lambda _: None)
    assert len(result) == 80
    assert len(seen) == 40
    assert all([c["doc_id"] for c in batch[0]["candidates"]] == ["d2"] for batch in seen)
    assert result[("q-00", "d1")]["judgment_source"] == "seed_qrels"


def test_resume_rejects_fingerprint_drift(tmp_path):
    path = tmp_path / "resume.jsonl"
    row = {
        "schema_version": OUTPUT_SCHEMA, "query_id": "q-00", "doc_id": "d1", "relevance": 2,
        "target_domain": "x", "mechanism": "m", "reason": "r", "judge_model": "model",
        "judgment_source": "provider", **META,
    }
    row["candidate_pool_sha256"] = "changed"
    write_jsonl(path, [row])
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_resume(path, {("q-00", "d1")}, META, "model")


def test_load_pool_rejects_candidate_outside_kb(tmp_path):
    kb = tmp_path / "kb.jsonl"
    write_jsonl(kb, [{"id": "d1"}])
    rows = []
    upstream = {key: value for key, value in META.items() if key != "candidate_pool_sha256"}
    for number in range(40):
        rows.append({
            "schema_version": "english-candidate-pool-v1", **upstream, "query_id": f"q-{number}",
            "candidate_count": 1, "candidates": [{"doc_id": "bad", "name": "n", "domain": "d", "description": "x"}],
        })
    pool_path = tmp_path / "pool.jsonl"
    write_jsonl(pool_path, rows)
    with pytest.raises(ValueError, match="allowlist"):
        load_pool(pool_path, kb)


def test_missing_provider_judgment_fails_without_partial_output(tmp_path):
    pool = pool_fixture()[:1]
    output = tmp_path / "out.jsonl"
    with pytest.raises(RuntimeError, match="failed after 3 attempts"):
        judge_pool(pool, META, {}, model="m", provider=lambda batch: {"judgments": []}, output=output, sleep=lambda _: None)
    assert not output.exists()


def test_atomic_output_replaces_complete_jsonl(tmp_path):
    output = tmp_path / "nested" / "out.jsonl"
    rows = [{"a": 1}, {"a": 2}]
    atomic_write(output, rows)
    assert [json.loads(line) for line in output.read_text().splitlines()] == rows
    assert not list(output.parent.glob(f".{output.name}.*"))


def test_cli_help_runs_from_repository_root():
    script = Path(__file__).resolve().parents[1] / "scripts/judge_english_candidate_pool.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
