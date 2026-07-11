import json
from pathlib import Path

import pytest

from scripts.english_review_tool import (
    JUDGMENT_SCHEMA,
    atomic_json,
    build_bundle,
    merge_judgments,
    validate_bundle,
    validate_judgments,
    weighted_kappa,
)

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "evaluation/english-candidate-pool-v1.jsonl"
KB = ROOT / "data/kb-expanded.jsonl"
SEED = ROOT / "evaluation/qrels-v1.jsonl"


@pytest.fixture(scope="module")
def bundle():
    return build_bundle(POOL, KB, SEED)


def judgment(task, fingerprint, reviewer="human-a", relevance=2):
    return {
        "schema_version": JUDGMENT_SCHEMA, "task_id": task["task_id"],
        "query_id": task["query_id"], "doc_id": task["doc_id"],
        "bundle_fingerprint": fingerprint, "reviewer_id": reviewer,
        "relevance": relevance, "same_domain": False, "evidence_present": True,
        "reject_reason": "not_relevant" if relevance == 0 else "none",
        "confidence": "high", "note": "",
    }


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_bundle_is_deterministic_complete_and_blinded(bundle):
    assert bundle == build_bundle(POOL, KB, SEED)
    assert bundle["task_count"] == 594
    assert len({task["task_id"] for task in bundle["tasks"]}) == 594
    forbidden = {"rank", "source", "provenance", "model", "relevance", "judgment"}
    assert all(not (set(task) & forbidden) for task in bundle["tasks"])
    assert len(validate_bundle(bundle, POOL, KB, SEED)) == 594


def test_bundle_rejects_missing_duplicate_and_fingerprint_drift(bundle):
    changed = json.loads(json.dumps(bundle))
    changed["metadata"]["candidate_pool_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        validate_bundle(changed, POOL, KB, SEED)
    missing = json.loads(json.dumps(bundle)); missing["tasks"].pop(); missing["task_count"] -= 1
    with pytest.raises(ValueError, match="missing 1 tasks"):
        validate_bundle(missing, POOL, KB, SEED)
    duplicate = json.loads(json.dumps(bundle)); duplicate["tasks"][1] = duplicate["tasks"][0]
    with pytest.raises(ValueError, match="duplicate bundle task"):
        validate_bundle(duplicate, POOL, KB, SEED)
    content_drift = json.loads(json.dumps(bundle)); content_drift["tasks"][0]["query"] = "changed"
    with pytest.raises(ValueError, match="content drift"):
        validate_bundle(content_drift, POOL, KB, SEED)


def test_judgment_validator_is_strict_and_supports_partial(bundle):
    task = bundle["tasks"][0]; fingerprint = bundle["metadata"]["candidate_pool_sha256"]
    row = judgment(task, fingerprint)
    assert validate_judgments([row], bundle, require_complete=False) == [row]
    with pytest.raises(ValueError, match="missing 593"):
        validate_judgments([row], bundle)
    wrong = {**row, "doc_id": "not-allowed"}
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_judgments([wrong], bundle, require_complete=False)
    duplicate = [row, row]
    with pytest.raises(ValueError, match="duplicate"):
        validate_judgments(duplicate, bundle, require_complete=False)
    invalid = {**row, "relevance": 0, "reject_reason": "none"}
    with pytest.raises(ValueError, match="requires reject_reason"):
        validate_judgments([invalid], bundle, require_complete=False)
    extra = {**row, "untrusted": True}
    with pytest.raises(ValueError, match="strict schema"):
        validate_judgments([extra], bundle, require_complete=False)


def test_merge_reports_agreement_and_disputes(bundle, tmp_path):
    tasks = bundle["tasks"][:3]; fingerprint = bundle["metadata"]["candidate_pool_sha256"]
    first = [judgment(task, fingerprint, "human-a", relevance) for task, relevance in zip(tasks, [3, 2, 0])]
    second = [judgment(task, fingerprint, "human-b", relevance) for task, relevance in zip(tasks, [3, 0, 0])]
    one, two = tmp_path / "a.jsonl", tmp_path / "b.jsonl"
    write_jsonl(one, first); write_jsonl(two, second)
    merged, report, disputes = merge_judgments([one, two], bundle)
    assert len(merged) == 594
    assert report["reviewers"] == ["human-a", "human-b"]
    assert report["pairwise"][0]["overlap"] == 3
    assert isinstance(report["pairwise"][0]["quadratic_weighted_kappa"], float)
    assert report["pairwise"][0]["exact_agreement"] == pytest.approx(2 / 3)
    disputed_ids = {row["task_id"] for row in disputes}
    assert tasks[1]["task_id"] in disputed_ids
    assert tasks[0]["task_id"] not in disputed_ids
    assert all(row["needs_adjudication"] for row in disputes)


def test_weighted_kappa_known_edges():
    assert weighted_kappa({"x": 3}, {"x": 3}, {"x"}) == 1.0
    assert weighted_kappa({}, {}, set()) is None


def test_atomic_json_and_jsonl_leave_no_temporary_file(tmp_path):
    output = tmp_path / "nested" / "rows.jsonl"
    atomic_json(output, [{"a": 1}, {"a": 2}], jsonl=True)
    assert [json.loads(line) for line in output.read_text().splitlines()] == [{"a": 1}, {"a": 2}]
    assert not list(output.parent.glob(f".{output.name}.*"))
