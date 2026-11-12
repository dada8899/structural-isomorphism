#!/usr/bin/env python3
"""Reproducible English retrieval experiments on frozen retrieval-v1 assets.

The qrels judge only the five documents returned by the frozen baseline.  This
script therefore separates (a) valid reranking experiments on that fixed judged
pool from (b) exploratory candidate-union diagnostics.  Unjudged documents are
never counted as gains.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import statistics
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import sentence_transformers


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/retrieval-v1.jsonl"
QRELS = ROOT / "evaluation/qrels-v1.jsonl"
BASELINE = ROOT / "evaluation/results/retrieval-v1-local-baseline.json"
KB = ROOT / "data/kb-expanded.jsonl"
MANIFEST = ROOT / "artifacts/production-v2-4443.json"
EMBEDDINGS = ROOT / "web/data/kb_v2_embeddings.npy.bak-session22"
MODEL = ROOT / "models/structural-v2"
SEARCH_SERVICE = ROOT / "web/backend/services/search_service.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_frozen_inputs() -> tuple[list[dict], dict[str, dict[str, int]], dict[str, dict]]:
    rows = load_jsonl(DATASET)
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    outcomes = {row["id"]: row for row in baseline["outcomes"]}
    qrel_rows = load_jsonl(QRELS)
    expected = {
        "dataset_sha256": sha256(DATASET),
        "kb_sha256": sha256(KB),
        "results_sha256": sha256(BASELINE),
    }
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    seen_qrels: set[tuple[str, str]] = set()
    for row in qrel_rows:
        for key, value in expected.items():
            if row.get(key) != value:
                raise ValueError(f"qrels {key} does not match frozen input")
        key = (row["query_id"], row["doc_id"])
        if key in seen_qrels or row.get("relevance") not in {0, 1, 2, 3}:
            raise ValueError(f"invalid or duplicate qrel: {key}")
        seen_qrels.add(key)
        qrels[row["query_id"]][row["doc_id"]] = row["relevance"]
    english = [row for row in rows if row["language"] == "en" and not row["labels"]["out_of_scope"]]
    if len(english) != 40 or any(len(qrels[row["id"]]) != 5 for row in english):
        raise ValueError("expected 40 English in-scope queries with exactly five judgments each")
    if any(set(outcomes[row["id"]]["top_ids"]) != set(qrels[row["id"]]) for row in english):
        raise ValueError("qrels are not the frozen baseline candidate pools")
    return rows, qrels, outcomes


def dcg(relevances: Iterable[int]) -> float:
    return sum((2**rel - 1) / math.log2(rank + 1) for rank, rel in enumerate(relevances, 1))


def judged_pool_metrics(rankings: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> dict:
    ndcgs, top1_successes, reciprocal_ranks, pool_has_relevant = [], [], [], []
    for query_id, ranking in rankings.items():
        judgments = qrels[query_id]
        if set(ranking) != set(judgments) or len(ranking) != len(set(ranking)):
            raise ValueError(f"{query_id}: ranking must contain each judged document exactly once")
        gains = [judgments[doc_id] for doc_id in ranking]
        ideal = sorted(judgments.values(), reverse=True)
        denominator = dcg(ideal)
        ndcgs.append(dcg(gains) / denominator if denominator else 0.0)
        top1_successes.append(gains[0] >= 2)
        relevant_ranks = [rank for rank, rel in enumerate(gains, 1) if rel >= 2]
        reciprocal_ranks.append(1 / relevant_ranks[0] if relevant_ranks else 0.0)
        pool_has_relevant.append(bool(relevant_ranks))
    return {
        "queries": len(rankings),
        "ndcg_at_5_fixed_judged_pool": round(statistics.mean(ndcgs), 4),
        "top1_success_fixed_judged_pool": round(statistics.mean(top1_successes), 4),
        "mrr_fixed_judged_pool": round(statistics.mean(reciprocal_ranks), 4),
        # This is invariant under reranking and exposes the recall ceiling of
        # the frozen five-document pool; it must not be read as rerank gain.
        "candidate_pool_has_relevant": round(statistics.mean(pool_has_relevant), 4),
    }


def per_query_ndcg(rankings: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> dict[str, float]:
    values = {}
    for query_id, ranking in rankings.items():
        judgments = qrels[query_id]
        gains = [judgments[doc_id] for doc_id in ranking]
        denominator = dcg(sorted(judgments.values(), reverse=True))
        values[query_id] = dcg(gains) / denominator if denominator else 0.0
    return values


def paired_bootstrap_ci(deltas: list[float], *, samples: int = 10_000) -> tuple[float, float]:
    if not deltas:
        raise ValueError("paired deltas are required")
    rng = np.random.default_rng(20260711)
    values = np.asarray(deltas, dtype=np.float64)
    means = values[rng.integers(0, len(values), size=(samples, len(values)))].mean(axis=1)
    low, high = np.quantile(means, [0.025, 0.975])
    return round(float(low), 4), round(float(high), 4)


def rank_subset(full_ranking: list[str], judged_docs: set[str]) -> list[str]:
    ranked = [doc_id for doc_id in full_ranking if doc_id in judged_docs]
    if set(ranked) != judged_docs:
        raise ValueError("full ranking does not cover every judged document")
    return ranked


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, int] = {}
    sequence = 0
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking, 1):
            scores[doc_id] += 1.0 / (k + rank)
            if doc_id not in first_seen:
                first_seen[doc_id] = sequence
                sequence += 1
    return sorted(scores, key=lambda doc_id: (-scores[doc_id], first_seen[doc_id], doc_id))


def run(pool_size: int) -> dict:
    rows, qrels, outcomes = load_frozen_inputs()
    by_pair = defaultdict(dict)
    for row in rows:
        by_pair[row["pair_id"]][row["language"]] = row

    sys.path[:0] = [str(ROOT), str(ROOT / "web/backend")]
    from services.search_service import SearchService

    service = SearchService(
        data_dir=str(ROOT / "data"),
        kb_file="kb-expanded.jsonl",
        model_path=str(ROOT / "models/structural-v2"),
        precomputed_embeddings=str(ROOT / "web/data/kb_v2_embeddings.npy.bak-session22"),
    )
    baseline_rankings, translated_rankings, rrf_rankings = {}, {}, {}
    union_diagnostics = []
    current_ranking_drift = []
    for row in [row for row in rows if row["language"] == "en" and not row["labels"]["out_of_scope"]]:
        query_id = row["id"]
        zh_query = by_pair[row["pair_id"]]["zh"]["query"]
        judged = set(qrels[query_id])
        # Rank the complete artifact so every frozen judged document remains
        # available for a valid fixed-pool comparison, even when translation
        # pushes it below the exploratory top-N candidate window.
        original_all = [service.kb[int(i)]["id"] for i in np.argsort(service._fused_scores(row["query"]))[::-1]]
        translated_all = [service.kb[int(i)]["id"] for i in np.argsort(service._fused_scores(zh_query))[::-1]]
        original_full = original_all[:pool_size]
        translated_full = translated_all[:pool_size]
        baseline_rankings[query_id] = outcomes[query_id]["top_ids"]
        if original_all[:5] != baseline_rankings[query_id]:
            current_ranking_drift.append(query_id)
        translated_rankings[query_id] = rank_subset(translated_all, judged)
        rrf_full = reciprocal_rank_fusion([original_all, translated_all])
        rrf_rankings[query_id] = rank_subset(rrf_full, judged)
        union = set(original_full) | set(translated_full)
        union_diagnostics.append({
            "query_id": query_id,
            "candidate_union_size": len(union),
            "judged_in_union": len(union & judged),
            "unjudged_in_union": len(union - judged),
            "top5_overlap_original_vs_oracle_zh": len(set(original_full[:5]) & set(translated_full[:5])),
        })

    def average(key: str) -> float:
        return round(statistics.mean(item[key] for item in union_diagnostics), 4)

    original_metrics = judged_pool_metrics(baseline_rankings, qrels)
    oracle_metrics = judged_pool_metrics(translated_rankings, qrels)
    rrf_metrics = judged_pool_metrics(rrf_rankings, qrels)
    relative_ndcg_gain = (
        oracle_metrics["ndcg_at_5_fixed_judged_pool"]
        / original_metrics["ndcg_at_5_fixed_judged_pool"] - 1
    )
    original_per_query = per_query_ndcg(baseline_rankings, qrels)
    reference_per_query = per_query_ndcg(translated_rankings, qrels)
    paired_deltas = [
        reference_per_query[query_id] - original_per_query[query_id]
        for query_id in sorted(original_per_query)
    ]
    delta_ci = paired_bootstrap_ci(paired_deltas)
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    git_sha = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    return {
        "schema_version": "english-retrieval-experiment-v1",
        "frozen_inputs": {
            "dataset_sha256": sha256(DATASET),
            "qrels_sha256": sha256(QRELS),
            "baseline_sha256": sha256(BASELINE),
            "kb_sha256": sha256(KB),
            "manifest_sha256": sha256(MANIFEST),
            "embeddings_sha256": sha256(EMBEDDINGS),
            "model_required_files": manifest["model"]["required_files"],
            "search_service_sha256": sha256(SEARCH_SERVICE),
            "experiment_sha256": sha256(Path(__file__)),
            "code_git_sha": git_sha,
            "artifact": manifest["artifact_id"],
            "runtime": {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "sentence_transformers": sentence_transformers.__version__,
            },
        },
        "methodology": {
            "queries": 40,
            "candidate_pool": "the five frozen baseline documents judged for each English query",
            "reference_counterpart": "paired human-authored Chinese query from retrieval-v1; a diagnostic proxy, not an upper bound or production translator",
            "candidate_union": f"original English and reference-Chinese top-{pool_size}",
            "qrels_limit": "qrels cover baseline Top-5 only; unjudged union documents are not treated as gains or losses",
            "ranker_limit": "uses SearchService._fused_scores before production domain-diversification/min-score post-processing so every judged document can be reranked; this is a diagnostic, not endpoint parity",
            "judge_limit": "qrels are from one deepseek-reasoner judge and remain a development set pending independent human/heterogeneous review",
        },
        "fixed_judged_pool": {
            "original_english": original_metrics,
            "reference_chinese_rerank": oracle_metrics,
            "rrf_original_plus_reference": rrf_metrics,
        },
        "candidate_union_diagnostics": {
            "mean_union_size": average("candidate_union_size"),
            "mean_judged_in_union": average("judged_in_union"),
            "mean_unjudged_in_union": average("unjudged_in_union"),
            "mean_top5_overlap": average("top5_overlap_original_vs_oracle_zh"),
            "per_query": union_diagnostics,
            "current_top5_drift_from_frozen_baseline": current_ranking_drift,
        },
        "conclusions": {
            "reference_relative_ndcg_gain": round(relative_ndcg_gain, 4),
            "mean_paired_ndcg_delta": round(statistics.mean(paired_deltas), 4),
            "paired_ndcg_delta_bootstrap_95_ci": list(delta_ci),
            "paired_delta_counts": {
                "positive": sum(delta > 1e-12 for delta in paired_deltas),
                "zero": sum(abs(delta) <= 1e-12 for delta in paired_deltas),
                "negative": sum(delta < -1e-12 for delta in paired_deltas),
            },
            "translation_signal": "the paired Chinese reference changes ordering in a favorable direction on average inside the same judged pool; this does not isolate production translation quality",
            "fusion_result": "simple RRF underperforms the reference-Chinese ranking on this fixed pool",
            "recall_claim": "not established: most union candidates are unjudged",
        },
        "recommended_production_experiment": {
            "implementation": "translate English to Chinese before retrieval, retain original-English fallback, cache deterministic translations, and log both query forms",
            "required_next_labeling": "judge newly retrieved documents from the English/translated union before claiming recall or end-to-end gain",
            "offline_gates_after_expanded_qrels": [
                "English nDCG@5 improves at least 15% relative to the frozen English baseline",
                "English Success@5 does not regress",
                "Chinese nDCG@5 regresses by no more than 0.01 absolute",
                "all four OOS metrics remain 1.0",
                "translation failures fall back to original English retrieval and never fail the request",
                "p95 latency stays within the product SLA measured on repeated warm and cold runs",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-size", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.pool_size < 5:
        parser.error("--pool-size must be at least 5")
    report = run(args.pool_size)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["fixed_judged_pool"], ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
