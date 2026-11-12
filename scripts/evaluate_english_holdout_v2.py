#!/usr/bin/env python3
"""Fail-closed paired evaluation for the label-sealed English holdout v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "evaluation/english-retrieval-v2-protocol.json"
HOLDOUT = ROOT / "evaluation/english-holdout-v2.jsonl"
REVIEW_SCHEMA = "english-holdout-review-v2"
RUN_SCHEMA = "english-holdout-run-v2"
SHA256_RE = __import__("re").compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dcg(values: list[int]) -> float:
    return sum((2**value - 1) / math.log2(rank + 1) for rank, value in enumerate(values, 1))


def ndcg(ranking: list[str], judgments: dict[str, int], k: int = 5) -> float:
    gains = [judgments.get(doc_id, 0) for doc_id in ranking[:k]]
    ideal = sorted(judgments.values(), reverse=True)[:k]
    denominator = dcg(ideal)
    return dcg(gains) / denominator if denominator else 0.0


def success_at_5(ranking: list[str], judgments: dict[str, int]) -> float:
    return float(any(judgments.get(doc_id, 0) >= 2 for doc_id in ranking[:5]))


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0 or not 0 <= successes <= total:
        raise ValueError("invalid Wilson inputs")
    p = successes / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return centre - margin, centre + margin


def cluster_bootstrap(deltas: dict[str, float], clusters: dict[str, str], samples: int = 10000) -> tuple[float, float]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for query_id, delta in deltas.items():
        grouped[clusters[query_id]].append(delta)
    names = sorted(grouped)
    if len(names) < 2:
        raise ValueError("at least two clusters are required")
    rng = np.random.default_rng(20260713)
    draws = []
    for _ in range(samples):
        selected = rng.choice(names, size=len(names), replace=True)
        values = [value for name in selected for value in grouped[str(name)]]
        draws.append(float(np.mean(values)))
    return tuple(float(value) for value in np.quantile(draws, [0.025, 0.975]))


def paired_permutation_pvalue(deltas: list[float], samples: int = 10000) -> float:
    if not deltas:
        raise ValueError("paired deltas are required")
    values = np.asarray(deltas, dtype=np.float64)
    observed = abs(float(values.mean()))
    rng = np.random.default_rng(20260713)
    exceed = 0
    for _ in range(samples):
        statistic = abs(float((values * rng.choice([-1.0, 1.0], size=len(values))).mean()))
        exceed += statistic >= observed - 1e-15
    return (exceed + 1) / (samples + 1)


def quadratic_weighted_kappa(left: list[int], right: list[int]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("paired reviewer scores are required")
    matrix = np.zeros((4, 4), dtype=np.float64)
    for a, b in zip(left, right):
        matrix[a, b] += 1
    observed = matrix / matrix.sum()
    expected = np.outer(matrix.sum(axis=1), matrix.sum(axis=0)) / (matrix.sum() ** 2)
    weights = np.fromfunction(lambda i, j: ((i - j) / 3) ** 2, (4, 4))
    observed_loss, expected_loss = float((weights * observed).sum()), float((weights * expected).sum())
    return 1.0 if expected_loss == 0 and observed_loss == 0 else 1 - observed_loss / expected_loss


def _resolve_relative(manifest_path: Path, value: str) -> Path:
    target = (manifest_path.parent / value).resolve()
    if manifest_path.parent.resolve() not in target.parents:
        raise ValueError("candidate artifact path escapes manifest directory")
    return target


def _valid_sha(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256_RE.fullmatch(value))


def validate_candidate_manifest(path: Path, protocol: dict[str, Any]) -> tuple[str, dict[str, set[str]], dict[str, dict], dict[str, dict[str, list[str]]]]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != "english-holdout-candidate-pool-v2" or value.get("status") != "FROZEN_COMPLETE":
        raise ValueError("candidate pool is not frozen complete")
    if value.get("holdout_sha256") != sha256(HOLDOUT):
        raise ValueError("candidate pool holdout fingerprint mismatch")
    systems = value.get("systems")
    required = set(protocol["candidate_pool"]["systems_required"])
    if not isinstance(systems, list) or {row.get("system_id") for row in systems if isinstance(row, dict)} != required:
        raise ValueError("candidate pool does not cover every required system")
    required_fields = {"system_id", "output_path", "output_sha256", "code_path", "code_sha256",
                       "code_commit", "model_path", "model_fingerprint", "kb_path", "kb_sha256",
                       "holdout_sha256", "top_k", "evaluation_k"}
    holdout_ids = {row["id"] for row in read_jsonl(HOLDOUT)}
    system_by_id = {}
    frozen_rankings: dict[str, dict[str, list[str]]] = {}
    computed_union: dict[str, set[str]] = {query_id: set() for query_id in holdout_ids}
    for row in systems:
        if (set(row) != required_fields or row["top_k"] < protocol["candidate_pool"]["depth_per_system"]
                or type(row["evaluation_k"]) is not int or not 5 <= row["evaluation_k"] <= row["top_k"]):
            raise ValueError("candidate pool system fingerprint is incomplete")
        if (not isinstance(row["system_id"], str) or not row["system_id"].strip()
                or any(not isinstance(row[key], str) or not row[key].strip()
                       for key in ("output_path", "code_path", "model_path", "kb_path"))
                or any(not _valid_sha(row[key]) for key in ("output_sha256", "code_sha256", "model_fingerprint", "kb_sha256", "holdout_sha256"))):
            raise ValueError("candidate pool fingerprint values are invalid")
        if row["code_commit"] is not None and not __import__("re").fullmatch(r"[0-9a-f]{40}", row["code_commit"]):
            raise ValueError("candidate code commit is invalid")
        for path_key, hash_key in (("code_path", "code_sha256"), ("model_path", "model_fingerprint"), ("kb_path", "kb_sha256")):
            artifact = _resolve_relative(path, row[path_key])
            if not artifact.is_file() or sha256(artifact) != row[hash_key]:
                raise ValueError("candidate system authority artifact fingerprint mismatch")
        if row["holdout_sha256"] != sha256(HOLDOUT):
            raise ValueError("candidate system holdout fingerprint mismatch")
        output = _resolve_relative(path, row["output_path"])
        if not output.is_file() or sha256(output) != row["output_sha256"]:
            raise ValueError("candidate system output fingerprint mismatch")
        run_rows = read_jsonl(output)
        if len(run_rows) != 200 or {item.get("query_id") for item in run_rows} != holdout_ids:
            raise ValueError("candidate system output must cover all 200 queries")
        frozen_rankings[row["system_id"]] = {}
        for item in run_rows:
            if (item.get("schema_version") != "english-candidate-system-run-v2"
                    or item.get("system_id") != row["system_id"]
                    or item.get("holdout_sha256") != row["holdout_sha256"]
                    or item.get("code_sha256") != row["code_sha256"]
                    or item.get("model_fingerprint") != row["model_fingerprint"]
                    or item.get("kb_sha256") != row["kb_sha256"]):
                raise ValueError("candidate system row fingerprint mismatch")
            top_ids = item.get("top_ids")
            if not isinstance(top_ids, list) or len(top_ids) != row["top_k"] or len(top_ids) != len(set(top_ids)):
                raise ValueError("candidate system requires a unique complete Top-50")
            if not all(isinstance(doc_id, str) and doc_id for doc_id in top_ids):
                raise ValueError("candidate system contains an invalid document id")
            computed_union[item["query_id"]].update(top_ids)
            frozen_rankings[row["system_id"]][item["query_id"]] = top_ids
        system_by_id[row["system_id"]] = row
    common = value.get("common_pool")
    if (not isinstance(common, dict) or set(common) != {"path", "sha256"}
            or not all(isinstance(common.get(key), str) and common[key] for key in common)):
        raise ValueError("candidate common pool fingerprint is missing")
    common_path = _resolve_relative(path, common["path"])
    if not common_path.is_file() or sha256(common_path) != common["sha256"]:
        raise ValueError("candidate common pool content fingerprint mismatch")
    common_rows = read_jsonl(common_path)
    mapping = {row.get("query_id"): row.get("doc_ids") for row in common_rows}
    if len(common_rows) != 200 or set(mapping) != holdout_ids:
        raise ValueError("candidate common pool must cover all 200 queries")
    clean: dict[str, set[str]] = {}
    for query_id, doc_ids in mapping.items():
        if (not isinstance(query_id, str) or not isinstance(doc_ids, list) or len(doc_ids) < 50
                or len(doc_ids) != len(set(doc_ids)) or not all(isinstance(doc, str) and doc for doc in doc_ids)):
            raise ValueError("candidate common pool query coverage is invalid")
        clean[query_id] = set(doc_ids)
        if clean[query_id] != computed_union[query_id]:
            raise ValueError("candidate common pool does not equal the recomputed system union")
    return sha256(path), clean, system_by_id, frozen_rankings


def load_inputs(candidate_path: Path, reviews_path: Path, adjudication_path: Path,
                baseline_path: Path, challenger_path: Path) -> tuple[dict, list, dict, dict, dict]:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    required_systems = {
        "production_endpoint", "bm25_only", "current_chinese_dense_only",
        "multilingual_dense", "translate_then_current", "original_translation_fusion",
        "query_expansion_only", "multilingual_sparse_dense", "cross_encoder_rerank",
    }
    if protocol.get("schema_version") != "english-retrieval-evidence-protocol-v2":
        raise ValueError("protocol schema mismatch")
    if protocol.get("development_set", {}).get("designation") != "DEV_ONLY_REPEATEDLY_INSPECTED_NO_HOLDOUT_CLAIMS":
        raise ValueError("legacy English queries must be explicitly development-only")
    if set(protocol.get("candidate_pool", {}).get("systems_required", [])) != required_systems:
        raise ValueError("candidate pool protocol must include every strong baseline")
    if protocol.get("candidate_pool", {}).get("depth_per_system", 0) < 50:
        raise ValueError("candidate pool depth must be at least 50 per system")
    if sha256(ROOT / protocol["development_set"]["path"]) != protocol["development_set"]["sha256"]:
        raise ValueError("development set fingerprint drift")
    if sha256(ROOT / protocol["holdout"]["generator"]) != protocol["holdout"]["generator_sha256"]:
        raise ValueError("holdout generator fingerprint drift")
    if sha256(HOLDOUT) != protocol["holdout"]["sha256"]:
        raise ValueError("holdout fingerprint drift")
    holdout = read_jsonl(HOLDOUT)
    if any(row.get("labels", "missing") is not None for row in holdout):
        raise ValueError("checked-in holdout must remain label-sealed")
    candidate_sha, common_pool, candidate_systems, frozen_rankings = validate_candidate_manifest(candidate_path, protocol)
    if not reviews_path.exists():
        raise ValueError("raw holdout reviews are missing; scoring is prohibited")
    reviews = read_jsonl(reviews_path)
    review_gate = protocol["statistics"]["review_gate"]
    holdout_by_id = {row["id"]: row for row in holdout}
    expected_ids = set(holdout_by_id)
    if set(common_pool) != set(holdout_by_id):
        raise ValueError("candidate common pool must cover every holdout query")
    expected_tasks = {(query_id, doc_id) for query_id, docs in common_pool.items() for doc_id in docs}
    by_task: dict[tuple[str, str], list[dict]] = defaultdict(list)
    reviewer_scores: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)
    reviewer_scope: dict[str, dict[str, bool]] = defaultdict(dict)
    for row in reviews:
        key = (row.get("query_id"), row.get("doc_id"))
        if (row.get("schema_version") != REVIEW_SCHEMA or row.get("holdout_sha256") != sha256(HOLDOUT)
                or row.get("candidate_pool_sha256") != candidate_sha or key not in expected_tasks):
            raise ValueError("raw review schema, fingerprint or task is invalid")
        reviewer, score = row.get("reviewer_id"), row.get("relevance")
        scope_decision = row.get("scope_decision")
        if (not isinstance(reviewer, str) or not reviewer.strip() or type(score) is not int
                or score not in {0, 1, 2, 3} or type(scope_decision) is not bool):
            raise ValueError("raw reviewer identity or score is invalid")
        if key in reviewer_scores[reviewer]:
            raise ValueError("duplicate raw review task for reviewer")
        reviewer_scores[reviewer][key] = score
        prior_scope = reviewer_scope[reviewer].get(key[0])
        if prior_scope is not None and prior_scope != scope_decision:
            raise ValueError("reviewer scope decision changes within one query")
        reviewer_scope[reviewer][key[0]] = scope_decision
        by_task[key].append(row)
    if set(by_task) != expected_tasks or any(len({row["reviewer_id"] for row in votes}) < 3 for votes in by_task.values()):
        raise ValueError("every pooled candidate requires at least three distinct raw reviewers")
    reviewers = sorted(reviewer_scores)
    kappas = []
    pairwise_kappas = []
    oos_agreements = []
    in_scope_tasks = {key for key in expected_tasks if holdout_by_id[key[0]]["expected_scope"] == "in_scope"}
    oos_ids = {qid for qid, row in holdout_by_id.items() if row["expected_scope"] == "out_of_scope"}
    for index, first in enumerate(reviewers):
        for second in reviewers[index + 1:]:
            overlap = sorted(set(reviewer_scores[first]) & set(reviewer_scores[second]) & in_scope_tasks)
            if overlap:
                value = quadratic_weighted_kappa(
                    [reviewer_scores[first][key] for key in overlap],
                    [reviewer_scores[second][key] for key in overlap])
                kappas.append(value); pairwise_kappas.append(value)
            oos_agreements.extend(
                reviewer_scope[first][qid] == reviewer_scope[second][qid] for qid in sorted(oos_ids)
            )
    if (len(reviewers) < 3 or not kappas
            or float(np.mean(kappas)) < review_gate["minimum_mean_quadratic_weighted_kappa"]
            or min(pairwise_kappas) < review_gate["minimum_pairwise_quadratic_weighted_kappa"]
            or float(np.mean(oos_agreements)) < review_gate["minimum_oos_scope_agreement"]):
        raise ValueError("raw reviewer agreement gate is not satisfied")
    review_sha = sha256(reviews_path)
    adjudications = read_jsonl(adjudication_path) if adjudication_path.exists() else []
    adjudicated = {}
    for row in adjudications:
        key = (row.get("query_id"), row.get("doc_id"))
        if (row.get("schema_version") != "english-holdout-adjudication-v2"
                or row.get("raw_reviews_sha256") != review_sha or key in adjudicated
                or not isinstance(row.get("adjudicator_id"), str)
                or row.get("adjudicator_id") in reviewer_scores
                or not isinstance(row.get("reason"), str) or not row["reason"].strip()
                or type(row.get("final_relevance")) is not int or row["final_relevance"] not in {0, 1, 2, 3}):
            raise ValueError("adjudication row is invalid or unbound")
        adjudicated[key] = row["final_relevance"]
    judgments_by_query: dict[str, dict[str, int]] = defaultdict(dict)
    disputes = set()
    for key, votes in by_task.items():
        scores = [row["relevance"] for row in votes]
        counts = {score: scores.count(score) for score in set(scores)}
        ordered = sorted(counts, key=lambda score: (-counts[score], score))
        disputed = max(scores) - min(scores) >= 2 or (len(ordered) > 1 and counts[ordered[0]] == counts[ordered[1]])
        if disputed:
            disputes.add(key)
            if key not in adjudicated:
                raise ValueError("every raw-review dispute requires a bound adjudication")
            final = adjudicated[key]
        else:
            final = ordered[0]
        judgments_by_query[key[0]][key[1]] = final
    if set(adjudicated) != disputes:
        raise ValueError("adjudication must bind exactly the disputed raw-review tasks")
    label_map = {query_id: {"judgments": judgments_by_query[query_id] if row["expected_scope"] == "in_scope" else {}}
                 for query_id, row in holdout_by_id.items()}

    def load_run(path: Path) -> dict[str, dict]:
        rows = read_jsonl(path)
        if len(rows) != len(expected_ids) or {row.get("query_id") for row in rows} != expected_ids:
            raise ValueError("run must cover every holdout query exactly once")
        result = {}
        for row in rows:
            if row.get("schema_version") != RUN_SCHEMA or row.get("holdout_sha256") != sha256(HOLDOUT):
                raise ValueError("run schema or fingerprint mismatch")
            system = candidate_systems.get(row.get("system_id"))
            if (system is None or row.get("candidate_manifest_sha256") != candidate_sha
                    or row.get("system_output_sha256") != system["output_sha256"]
                    or row.get("code_sha256") != system["code_sha256"]
                    or row.get("model_fingerprint") != system["model_fingerprint"]
                    or row.get("kb_sha256") != system["kb_sha256"]):
                raise ValueError("run is not bound to the frozen candidate system")
            ranking = row.get("ranking")
            if not isinstance(ranking, list) or len(ranking) < 5 or len(ranking) != len(set(ranking)):
                raise ValueError("run requires at least five unique ranked doc ids")
            if not set(ranking) <= common_pool[row["query_id"]]:
                raise ValueError("run ranking is outside the frozen common pool")
            if (len(ranking) != system["evaluation_k"]
                    or ranking != frozen_rankings[row["system_id"]][row["query_id"]][:system["evaluation_k"]]):
                raise ValueError("run ranking differs from the frozen system output prefix")
            if type(row.get("predicted_oos")) is not bool or type(row.get("request_success")) is not bool:
                raise ValueError("run scope/success fields are invalid")
            if not isinstance(row.get("latency_ms"), (int, float)) or row["latency_ms"] < 0:
                raise ValueError("run latency is invalid")
            result[row["query_id"]] = row
        return result
    loaded_baseline, loaded_challenger = load_run(baseline_path), load_run(challenger_path)
    if any(not row["request_success"] for row in loaded_baseline.values()):
        raise ValueError("baseline request failure invalidates the paired comparison")
    if {row["system_id"] for row in loaded_baseline.values()} != {"production_endpoint"}:
        raise ValueError("baseline must be the frozen production endpoint")
    if len({row["system_id"] for row in loaded_challenger.values()}) != 1:
        raise ValueError("challenger must be one preregistered system")
    return protocol, holdout, label_map, loaded_baseline, loaded_challenger, {
        "candidate_sha256": candidate_sha, "systems": candidate_systems,
        "challenger_id": next(iter({row["system_id"] for row in loaded_challenger.values()})),
        "review_mean_qwk_in_scope": float(np.mean(kappas)),
        "review_min_pairwise_qwk_in_scope": min(pairwise_kappas),
        "oos_scope_pairwise_agreement": float(np.mean(oos_agreements)),
    }


def evaluate_chinese_control(path: Path, protocol: dict[str, Any], context: dict[str, Any]) -> dict[str, float]:
    value = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    if not isinstance(value, dict) or value.get("schema_version") != "english-holdout-chinese-control-v2":
        raise ValueError("fingerprinted Chinese regression control is missing")
    qrels_path = _resolve_relative(path, value.get("qrels_path", ""))
    dataset_path = ROOT / protocol["development_set"]["path"]
    if (not qrels_path.is_file() or not _valid_sha(value.get("qrels_sha256"))
            or sha256(qrels_path) != value["qrels_sha256"]
            or value["qrels_sha256"] != protocol["chinese_control"]["qrels_sha256"]):
        raise ValueError("Chinese control qrels fingerprint mismatch")
    queries = read_jsonl(dataset_path)
    query_ids = {row["id"] for row in queries if row.get("language") == "zh" and not row.get("labels", {}).get("out_of_scope")}
    if len(query_ids) != 40:
        raise ValueError("Chinese DEV query universe must contain exactly 40 rows")
    judgments: dict[str, dict[str, int]] = defaultdict(dict)
    for row in read_jsonl(qrels_path):
        if row.get("query_id") in query_ids:
            if type(row.get("relevance")) is not int or row["relevance"] not in {0, 1, 2, 3}:
                raise ValueError("Chinese qrel relevance is invalid")
            judgments[row["query_id"]][row["doc_id"]] = row["relevance"]
    if set(judgments) != query_ids or any(len(values) != 5 for values in judgments.values()):
        raise ValueError("Chinese qrels must cover the complete DEV query universe")

    def load_control_run(key: str, required_system: str) -> dict[str, list[str]]:
        spec = value.get(key)
        if not isinstance(spec, dict) or set(spec) != {"path", "sha256"} or not _valid_sha(spec.get("sha256")):
            raise ValueError("Chinese control run reference is invalid")
        run_path = _resolve_relative(path, spec["path"])
        if not run_path.is_file() or sha256(run_path) != spec["sha256"]:
            raise ValueError("Chinese control run content fingerprint mismatch")
        system = context["systems"].get(required_system)
        if system is None:
            raise ValueError("Chinese control system is outside candidate manifest")
        output = {}
        for row in read_jsonl(run_path):
            if (row.get("schema_version") != "english-chinese-control-run-v2"
                    or row.get("system_id") != required_system
                    or row.get("candidate_manifest_sha256") != context["candidate_sha256"]
                    or row.get("code_sha256") != system["code_sha256"]
                    or row.get("model_fingerprint") != system["model_fingerprint"]
                    or row.get("kb_sha256") != system["kb_sha256"]):
                raise ValueError("Chinese control run is not bound to the candidate system")
            ranking = row.get("ranking")
            if (row.get("query_id") not in query_ids or not isinstance(ranking, list)
                    or len(ranking) != system["evaluation_k"]
                    or len(ranking) != len(set(ranking))
                    or not all(isinstance(doc_id, str) and bool(doc_id.strip()) for doc_id in ranking)):
                raise ValueError("Chinese control ranking is invalid")
            output[row["query_id"]] = ranking
        if set(output) != query_ids:
            raise ValueError("Chinese control run must cover all 40 DEV queries")
        return output

    baseline = load_control_run("production_run", "production_endpoint")
    challenger = load_control_run("challenger_run", context["challenger_id"])
    deltas = {}
    for qid in query_ids:
        baseline_ndcg = ndcg(baseline[qid], judgments[qid])
        challenger_ndcg = ndcg(challenger[qid], judgments[qid])
        if (not math.isfinite(baseline_ndcg) or not math.isfinite(challenger_ndcg)
                or not 0.0 <= baseline_ndcg <= 1.0 or not 0.0 <= challenger_ndcg <= 1.0):
            raise ValueError("computed Chinese nDCG is outside [0,1]")
        deltas[qid] = challenger_ndcg - baseline_ndcg
    return deltas


def evaluate(candidate_path: Path, reviews_path: Path, adjudication_path: Path,
             baseline_path: Path, challenger_path: Path, chinese_path: Path) -> dict[str, Any]:
    protocol, holdout, labels, baseline, challenger, candidate_context = load_inputs(
        candidate_path, reviews_path, adjudication_path, baseline_path, challenger_path)
    in_scope = [row for row in holdout if row["expected_scope"] == "in_scope"]
    oos = [row for row in holdout if row["expected_scope"] == "out_of_scope"]
    cluster_key = protocol["statistics"]["bootstrap_cluster_key"]
    if cluster_key not in protocol["statistics"]["cluster_keys"]:
        raise ValueError("bootstrap cluster key is not preregistered")
    clusters = {row["id"]: row["cluster"][cluster_key] for row in in_scope}
    ndcg_base, ndcg_new, success_base, success_new = {}, {}, {}, {}
    for row in in_scope:
        qid, judgments = row["id"], labels[row["id"]]["judgments"]
        ndcg_base[qid] = ndcg(baseline[qid]["ranking"], judgments)
        ndcg_new[qid] = ndcg(challenger[qid]["ranking"], judgments)
        success_base[qid] = success_at_5(baseline[qid]["ranking"], judgments)
        success_new[qid] = success_at_5(challenger[qid]["ranking"], judgments)
    ndcg_delta = {qid: ndcg_new[qid] - ndcg_base[qid] for qid in ndcg_base}
    success_delta = {qid: success_new[qid] - success_base[qid] for qid in success_base}
    ndcg_ci = cluster_bootstrap(ndcg_delta, clusters)
    success_ci = cluster_bootstrap(success_delta, clusters)
    predicted_oos = {qid for qid, row in challenger.items() if row["predicted_oos"]}
    actual_oos = {row["id"] for row in oos}
    true_positive = len(predicted_oos & actual_oos)
    precision = wilson(true_positive, len(predicted_oos)) if predicted_oos else (0.0, 0.0)
    recall = wilson(true_positive, len(actual_oos))
    dangerous_false_accepts = sum(not challenger[row["id"]]["predicted_oos"] for row in oos if row["dangerous"])
    mean_base, mean_new = float(np.mean(list(ndcg_base.values()))), float(np.mean(list(ndcg_new.values())))
    latencies = sorted(float(row["latency_ms"]) for row in challenger.values())
    base_latencies = sorted(float(row["latency_ms"]) for row in baseline.values())
    p95, base_p95 = float(np.quantile(latencies, .95)), float(np.quantile(base_latencies, .95))
    chinese_delta = evaluate_chinese_control(chinese_path, protocol, candidate_context)
    chinese_clusters = {query_id: query_id for query_id in chinese_delta}
    chinese_ci = cluster_bootstrap(chinese_delta, chinese_clusters)
    gates = protocol["go_gates"]
    pvalue = paired_permutation_pvalue(list(ndcg_delta.values()))
    checks = {
        "ndcg_relative": (mean_new / mean_base - 1) >= gates["english_ndcg_relative_gain_min"] if mean_base else False,
        "ndcg_absolute": (mean_new - mean_base) >= gates["english_ndcg_absolute_gain_min"],
        "ndcg_ci": ndcg_ci[0] > gates["english_ndcg_delta_ci_lower_gt"],
        "ndcg_permutation": pvalue <= gates["primary_paired_permutation_p_max"],
        "success_noninferiority": success_ci[0] >= gates["success_at_5_delta_ci_lower_min"],
        "oos_precision": precision[0] >= gates["oos_precision_wilson_lower_min"],
        "oos_recall": recall[0] >= gates["oos_recall_wilson_lower_min"],
        "dangerous": dangerous_false_accepts <= gates["dangerous_false_accept_max"],
        "chinese_noninferiority": chinese_ci[0] >= gates["chinese_ndcg_delta_ci_lower_min"],
        "request_success": all(row["request_success"] for row in challenger.values()),
        "latency_absolute": p95 <= gates["warm_p95_ms_max"],
        "latency_relative": p95 <= base_p95 * gates["warm_p95_relative_to_baseline_max"],
    }
    return {
        "schema_version": "english-holdout-evaluation-v2", "decision": "GO" if all(checks.values()) else "NO-GO",
        "checks": checks, "query_count": len(holdout),
        "metrics": {"baseline_ndcg_at_5": mean_base, "challenger_ndcg_at_5": mean_new,
                    "ndcg_delta": mean_new - mean_base, "ndcg_delta_cluster_bootstrap_95_ci": ndcg_ci,
                    "ndcg_paired_permutation_p": pvalue, "success_delta_ci": success_ci,
                    "oos_precision_wilson_95_ci": precision, "oos_recall_wilson_95_ci": recall,
                    "dangerous_false_accepts": dangerous_false_accepts,
                    "review_mean_qwk_in_scope": candidate_context["review_mean_qwk_in_scope"],
                    "review_min_pairwise_qwk_in_scope": candidate_context["review_min_pairwise_qwk_in_scope"],
                    "oos_scope_pairwise_agreement": candidate_context["oos_scope_pairwise_agreement"],
                    "chinese_ndcg_delta_cluster_bootstrap_95_ci": chinese_ci,
                    "challenger_warm_p95_ms": p95, "baseline_warm_p95_ms": base_p95},
        "scientific_boundary": "simulated holdout performance only; not real-user value or scientific mechanism evidence",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-pool", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--adjudications", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--challenger", type=Path, required=True)
    parser.add_argument("--chinese-control", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.candidate_pool, args.reviews, args.adjudications, args.baseline,
                      args.challenger, args.chinese_control)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if report["decision"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
