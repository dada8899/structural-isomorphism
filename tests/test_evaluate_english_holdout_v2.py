import json
from pathlib import Path

import pytest

from scripts.evaluate_english_holdout_v2 import (
    HOLDOUT, PROTOCOL, REVIEW_SCHEMA, RUN_SCHEMA, cluster_bootstrap, evaluate,
    paired_permutation_pvalue, read_jsonl, sha256, wilson,
)


def write_jsonl(path: Path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def complete_inputs(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    holdout = read_jsonl(HOLDOUT); digest = sha256(HOLDOUT)
    protocol = json.loads(PROTOCOL.read_text())
    common_ids = ["good", "weak", "bad1", "bad2", "bad3"] + [f"pool-{i:02d}" for i in range(45)]
    systems = []
    code_artifact = tmp_path / "code.bin"; code_artifact.write_bytes(b"code")
    kb_artifact = tmp_path / "kb.bin"; kb_artifact.write_bytes(b"kb")
    for system_id in protocol["candidate_pool"]["systems_required"]:
        output = tmp_path / f"{system_id}.jsonl"
        model_artifact = tmp_path / f"model-{system_id}.bin"; model_artifact.write_text(system_id)
        code, model, kb = sha256(code_artifact), sha256(model_artifact), sha256(kb_artifact)
        ordering = list(common_ids)
        if system_id == "production_endpoint":
            ordering = ["bad1", "bad2", "bad3", "weak", "good"] + common_ids[5:]
        write_jsonl(output, [{"schema_version": "english-candidate-system-run-v2",
            "system_id": system_id, "query_id": row["id"], "holdout_sha256": digest,
            "code_sha256": code, "model_fingerprint": model, "kb_sha256": kb,
            "top_ids": ordering} for row in holdout])
        systems.append({"system_id": system_id, "output_path": output.name,
            "output_sha256": sha256(output), "code_path": code_artifact.name, "code_sha256": code,
            "code_commit": "a" * 40, "model_path": model_artifact.name,
            "model_fingerprint": model, "kb_path": kb_artifact.name,
            "kb_sha256": kb, "holdout_sha256": digest,
            "top_k": 50, "evaluation_k": 5})
    common_path = tmp_path / "common.jsonl"
    write_jsonl(common_path, [{"query_id": row["id"], "doc_ids": common_ids} for row in holdout])
    candidate = tmp_path / "candidate.json"
    candidate.write_text(json.dumps({"schema_version": "english-holdout-candidate-pool-v2",
        "status": "FROZEN_COMPLETE", "holdout_sha256": digest, "systems": systems,
        "common_pool": {"path": common_path.name, "sha256": sha256(common_path)}}))
    candidate_sha = sha256(candidate)
    reviews, baseline, challenger = [], [], []
    for row in holdout:
        in_scope = row["expected_scope"] == "in_scope"
        for reviewer in ("reviewer-a", "reviewer-b", "reviewer-c"):
            for doc_id in common_ids:
                reviews.append({"schema_version": REVIEW_SCHEMA, "holdout_sha256": digest,
                    "candidate_pool_sha256": candidate_sha, "query_id": row["id"], "doc_id": doc_id,
                    "reviewer_id": reviewer,
                    "scope_decision": not in_scope,
                    "relevance": (3 if doc_id == "good" else 1 if doc_id == "weak" else 0)})
        def run_common(system_id):
            system = next(item for item in systems if item["system_id"] == system_id)
            return {"schema_version": RUN_SCHEMA, "holdout_sha256": digest,
                "candidate_manifest_sha256": candidate_sha, "system_id": system_id,
                "system_output_sha256": system["output_sha256"], "code_sha256": system["code_sha256"],
                "model_fingerprint": system["model_fingerprint"], "kb_sha256": system["kb_sha256"],
                "query_id": row["id"], "request_success": True}
        baseline.append({**run_common("production_endpoint"), "ranking": common_ids[2:5] + ["weak", "good"],
                         "predicted_oos": not in_scope, "latency_ms": 100})
        challenger.append({**run_common("multilingual_dense"), "ranking": common_ids[:5],
                           "predicted_oos": not in_scope, "latency_ms": 150})
    paths = [candidate] + [tmp_path / name for name in ("reviews.jsonl", "adjudications.jsonl", "baseline.jsonl", "challenger.jsonl")]
    for path, values in zip((paths[1], paths[3], paths[4]), (reviews, baseline, challenger)):
        write_jsonl(path, values)
    write_jsonl(paths[2], [])
    source_qrels = Path("evaluation/qrels-v1.jsonl")
    qrels_copy = tmp_path / "qrels.jsonl"; qrels_copy.write_bytes(source_qrels.read_bytes())
    qrels = read_jsonl(qrels_copy); zh_ids = sorted({row["query_id"] for row in qrels if row["query_id"].endswith("-zh")})
    by_query = {qid: [row["doc_id"] for row in qrels if row["query_id"] == qid] for qid in zh_ids}
    def chinese_run(system_id, filename):
        system = next(item for item in systems if item["system_id"] == system_id)
        output = tmp_path / filename
        write_jsonl(output, [{"schema_version": "english-chinese-control-run-v2", "query_id": qid,
            "system_id": system_id, "candidate_manifest_sha256": candidate_sha,
            "code_sha256": system["code_sha256"], "model_fingerprint": system["model_fingerprint"],
            "kb_sha256": system["kb_sha256"], "ranking": by_query[qid]} for qid in zh_ids])
        return {"path": output.name, "sha256": sha256(output)}
    chinese = tmp_path / "chinese.json"
    chinese.write_text(json.dumps({"schema_version": "english-holdout-chinese-control-v2",
        "qrels_path": qrels_copy.name, "qrels_sha256": sha256(qrels_copy),
        "production_run": chinese_run("production_endpoint", "zh-prod.jsonl"),
        "challenger_run": chinese_run("multilingual_dense", "zh-new.jsonl")}))
    return [paths[0], paths[1], paths[2], paths[3], paths[4], chinese], reviews


def test_missing_or_incomplete_labels_fail_closed(tmp_path):
    paths, reviews = complete_inputs(tmp_path)
    with pytest.raises(ValueError, match="reviews are missing"):
        evaluate(paths[0], tmp_path / "absent.jsonl", paths[2], paths[3], paths[4], paths[5])
    paths, reviews = complete_inputs(tmp_path / "incomplete")
    write_jsonl(paths[1], reviews[:-1])
    with pytest.raises(ValueError, match="three distinct raw reviewers"):
        evaluate(*paths)


def test_unfrozen_candidate_pool_and_missing_review_report_fail_closed(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    candidate = json.loads(paths[0].read_text()); candidate["status"] = "NOT_BUILT"
    paths[0].write_text(json.dumps(candidate))
    with pytest.raises(ValueError, match="not frozen complete"):
        evaluate(*paths)
    paths, _ = complete_inputs(tmp_path / "second")
    paths[1].unlink()
    with pytest.raises(ValueError, match="reviews are missing"):
        evaluate(*paths)


def test_complete_strong_challenger_reaches_go(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    report = evaluate(*paths)
    assert report["decision"] == "GO"
    assert all(report["checks"].values())
    assert report["metrics"]["dangerous_false_accepts"] == 0


def test_safety_failure_forces_no_go(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    rows = read_jsonl(paths[4])
    dangerous = next(row for row in read_jsonl(HOLDOUT) if row["dangerous"])
    next(item for item in rows if item["query_id"] == dangerous["id"])["predicted_oos"] = False
    write_jsonl(paths[4], rows)
    report = evaluate(*paths)
    assert report["decision"] == "NO-GO"
    assert report["checks"]["dangerous"] is False


def test_five_doc_pool_and_duplicate_system_top50_are_rejected(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    manifest = json.loads(paths[0].read_text())
    common = paths[0].parent / manifest["common_pool"]["path"]
    rows = read_jsonl(common)
    for row in rows:
        row["doc_ids"] = row["doc_ids"][:5]
    write_jsonl(common, rows); manifest["common_pool"]["sha256"] = sha256(common)
    paths[0].write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="common pool query coverage"):
        evaluate(*paths)

    paths, _ = complete_inputs(tmp_path / "duplicate")
    manifest = json.loads(paths[0].read_text()); system = manifest["systems"][0]
    output = paths[0].parent / system["output_path"]
    rows = read_jsonl(output); rows[0]["top_ids"][-1] = rows[0]["top_ids"][0]
    write_jsonl(output, rows); system["output_sha256"] = sha256(output)
    paths[0].write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unique complete Top-50"):
        evaluate(*paths)


def test_raw_dispute_requires_bound_adjudication_and_run_binding(tmp_path):
    paths, reviews = complete_inputs(tmp_path)
    target = reviews[0]
    same_task = [row for row in reviews if row["query_id"] == target["query_id"] and row["doc_id"] == target["doc_id"]]
    for row, score in zip(same_task, (0, 1, 3)):
        row["relevance"] = score
    write_jsonl(paths[1], reviews)
    with pytest.raises(ValueError, match="bound adjudication"):
        evaluate(*paths)

    paths, _ = complete_inputs(tmp_path / "binding")
    runs = read_jsonl(paths[3]); runs[0]["code_sha256"] = "forged"
    write_jsonl(paths[3], runs)
    with pytest.raises(ValueError, match="not bound"):
        evaluate(*paths)


def test_baseline_request_failure_invalidates_pairing(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    runs = read_jsonl(paths[3]); runs[0]["request_success"] = False
    write_jsonl(paths[3], runs)
    with pytest.raises(ValueError, match="baseline request failure"):
        evaluate(*paths)


def test_reordered_run_with_unchanged_fingerprints_is_rejected(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    runs = read_jsonl(paths[3]); runs[0]["ranking"][0], runs[0]["ranking"][1] = runs[0]["ranking"][1], runs[0]["ranking"][0]
    write_jsonl(paths[3], runs)
    with pytest.raises(ValueError, match="differs from the frozen system output prefix"):
        evaluate(*paths)


def test_forged_hash_and_wrong_chinese_system_are_rejected(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    manifest = json.loads(paths[0].read_text()); manifest["systems"][0]["code_sha256"] = "forged"
    paths[0].write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="fingerprint values"):
        evaluate(*paths)

    paths, _ = complete_inputs(tmp_path / "chinese")
    control = json.loads(paths[5].read_text()); run_path = paths[5].parent / control["challenger_run"]["path"]
    rows = read_jsonl(run_path); rows[0]["system_id"] = "production_endpoint"
    write_jsonl(run_path, rows); control["challenger_run"]["sha256"] = sha256(run_path)
    paths[5].write_text(json.dumps(control))
    with pytest.raises(ValueError, match="not bound to the candidate system"):
        evaluate(*paths)


def test_chinese_repeated_best_doc_is_rejected_even_with_updated_sha(tmp_path):
    paths, _ = complete_inputs(tmp_path)
    control = json.loads(paths[5].read_text())
    run_path = paths[5].parent / control["challenger_run"]["path"]
    rows = read_jsonl(run_path)
    rows[0]["ranking"] = [rows[0]["ranking"][0]] * 5
    write_jsonl(run_path, rows)
    control["challenger_run"]["sha256"] = sha256(run_path)
    paths[5].write_text(json.dumps(control))
    with pytest.raises(ValueError, match="Chinese control ranking is invalid"):
        evaluate(*paths)


def test_statistical_helpers_are_deterministic_and_bounded():
    low, high = wilson(100, 100)
    assert 0.95 < low < high <= 1
    deltas = {f"q{i}": 0.1 + i / 1000 for i in range(20)}
    clusters = {f"q{i}": f"c{i % 5}" for i in range(20)}
    assert cluster_bootstrap(deltas, clusters) == cluster_bootstrap(deltas, clusters)
    assert paired_permutation_pvalue(list(deltas.values())) < 0.01
