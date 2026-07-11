#!/usr/bin/env python3
"""Evaluate Structural Search against the canonical bilingual gold set."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "retrieval-v1.jsonl"


def load_dataset(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    pairs: dict[str, set[str]] = defaultdict(set)
    with path.open(encoding="utf-8") as handle:
        for line_no, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"line {line_no}: invalid JSON: {exc}") from exc
            required = {"id", "pair_id", "language", "query", "labels"}
            missing = required - row.keys()
            if missing:
                raise ValueError(f"line {line_no}: missing {sorted(missing)}")
            if row["id"] in seen_ids:
                raise ValueError(f"line {line_no}: duplicate id {row['id']}")
            if row["language"] not in {"zh", "en"}:
                raise ValueError(f"line {line_no}: invalid language")
            labels = row["labels"]
            label_fields = {
                "out_of_scope", "scope_reason", "accepted_type_ids",
                "require_cross_domain", "min_relevant_at_5", "note",
            }
            if not isinstance(labels, dict) or label_fields - labels.keys():
                raise ValueError(f"line {line_no}: incomplete labels")
            if labels["out_of_scope"] and labels["accepted_type_ids"]:
                raise ValueError(f"line {line_no}: OOS row has accepted types")
            if not labels["out_of_scope"] and not labels["accepted_type_ids"]:
                raise ValueError(f"line {line_no}: in-scope row has no accepted types")
            seen_ids.add(row["id"])
            pairs[row["pair_id"]].add(row["language"])
            rows.append(row)
    if len(rows) != 100:
        raise ValueError(f"expected 100 rows, got {len(rows)}")
    broken_pairs = [pair_id for pair_id, langs in pairs.items() if langs != {"zh", "en"}]
    if len(pairs) != 50 or broken_pairs:
        raise ValueError(f"expected 50 complete bilingual pairs; broken={broken_pairs}")
    return rows


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def post_search(base_url: str, row: dict[str, Any], timeout: float) -> tuple[dict, float]:
    payload = json.dumps({
        "query": row["query"],
        "top_k": 5,
        "rewrite": False,
        "lang": row["language"],
    }).encode()
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/search",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "structural-eval/1.0"},
        method="POST",
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:300]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    return body, (time.monotonic() - started) * 1000


def evaluate(
    rows: list[dict[str, Any]],
    base_url: str,
    timeout: float,
    search_call=None,
) -> tuple[dict, list[dict]]:
    outcomes: list[dict] = []
    latencies: list[float] = []
    pair_types: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for position, row in enumerate(rows, 1):
        try:
            if search_call is None:
                body, latency_ms = post_search(base_url, row, timeout)
            else:
                started = time.monotonic()
                body = search_call(row)
                latency_ms = (time.monotonic() - started) * 1000
            error = None
        except Exception as exc:  # one failed request must not erase the report
            body, latency_ms, error = {}, 0.0, str(exc)
        latencies.append(latency_ms)
        labels = row["labels"]
        results = body.get("results") or []
        predicted_oos = bool(body.get("out_of_scope"))
        expected_types = set(labels["accepted_type_ids"])
        result_types = [str(item.get("type_id") or "") for item in results[:5]]
        relevant_ranks = [i + 1 for i, type_id in enumerate(result_types) if type_id in expected_types]
        hit_at_5 = (
            len(relevant_ranks) >= int(labels["min_relevant_at_5"])
            if not labels["out_of_scope"]
            else predicted_oos and not results
        )
        reciprocal_rank = 1 / relevant_ranks[0] if relevant_ranks else 0.0
        cross_domain_ok = (
            not labels["require_cross_domain"]
            or any(bool(item.get("cross_domain")) and str(item.get("type_id") or "") in expected_types
                   for item in results[:5])
        )
        if not labels["out_of_scope"]:
            pair_types[row["pair_id"]][row["language"]] = set(result_types)
        outcomes.append({
            "id": row["id"],
            "pair_id": row["pair_id"],
            "language": row["language"],
            "expected_oos": labels["out_of_scope"],
            "predicted_oos": predicted_oos,
            "expected_reason": labels["scope_reason"],
            "predicted_reason": body.get("scope_reason"),
            "hit_at_5": hit_at_5,
            "reciprocal_rank": reciprocal_rank,
            "cross_domain_ok": cross_domain_ok,
            "result_types": result_types,
            "top_ids": [item.get("id") for item in results[:5]],
            "latency_ms": round(latency_ms, 1),
            "error": error,
        })
        if position % 10 == 0:
            print(f"evaluated {position}/{len(rows)}", file=sys.stderr)

    def ratio(items: list[bool]) -> float:
        return sum(items) / len(items) if items else 0.0

    in_scope = [item for item in outcomes if not item["expected_oos"]]
    oos = [item for item in outcomes if item["expected_oos"]]
    predicted_positive = [item for item in outcomes if item["predicted_oos"]]
    true_positive = [item for item in oos if item["predicted_oos"]]
    bilingual_jaccard: list[float] = []
    for langs in pair_types.values():
        if "zh" not in langs or "en" not in langs:
            continue
        union = langs["zh"] | langs["en"]
        bilingual_jaccard.append(len(langs["zh"] & langs["en"]) / len(union) if union else 1.0)
    by_language = {}
    for language in ("zh", "en"):
        subset = [item for item in in_scope if item["language"] == language]
        by_language[language] = {
            "hit_at_5": round(ratio([item["hit_at_5"] for item in subset]), 4),
            "mrr_at_5": round(statistics.mean([item["reciprocal_rank"] for item in subset]), 4),
            "cross_domain_success": round(ratio([item["cross_domain_ok"] for item in subset]), 4),
        }
    metrics = {
        "dataset_rows": len(rows),
        "in_scope_rows": len(in_scope),
        "out_of_scope_rows": len(oos),
        "request_errors": sum(bool(item["error"]) for item in outcomes),
        "hit_at_5": round(ratio([item["hit_at_5"] for item in in_scope]), 4),
        "mrr_at_5": round(statistics.mean([item["reciprocal_rank"] for item in in_scope]), 4),
        "cross_domain_success": round(ratio([item["cross_domain_ok"] for item in in_scope]), 4),
        "oos_recall": round(len(true_positive) / len(oos), 4) if oos else 0.0,
        "oos_precision": round(len(true_positive) / len(predicted_positive), 4) if predicted_positive else 0.0,
        "oos_reason_accuracy": round(ratio([
            item["predicted_oos"] and item["predicted_reason"] == item["expected_reason"]
            for item in oos
        ]), 4),
        "strict_refusal_rate": round(ratio([
            item["predicted_oos"] and item["hit_at_5"] for item in oos
        ]), 4),
        "bilingual_type_jaccard_at_5": round(statistics.mean(bilingual_jaccard), 4),
        "latency_ms": {
            "p50": round(percentile(latencies, 0.50), 1),
            "p95": round(percentile(latencies, 0.95), 1),
        },
        "by_language": by_language,
    }
    return metrics, outcomes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def add_qrel_metrics(
    metrics: dict,
    outcomes: list[dict],
    qrels_path: Path,
    *,
    dataset_path: Path,
    kb_path: Path,
    frozen_results_path: Path,
) -> None:
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    expected_fingerprints = {
        "dataset_sha256": _sha256(dataset_path),
        "kb_sha256": _sha256(kb_path),
        "results_sha256": _sha256(frozen_results_path),
    }
    metadata_variants: set[tuple[str, str, str, str, str]] = set()
    for raw in qrels_path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        row = json.loads(raw)
        if row.get("schema_version") != "qrels-v1":
            raise ValueError("qrels schema_version must be qrels-v1")
        judge_model = row.get("judge_model")
        if not isinstance(judge_model, str) or not judge_model.strip():
            raise ValueError("qrels judge_model is required")
        for field, expected_hash in expected_fingerprints.items():
            if row.get(field) != expected_hash:
                raise ValueError(f"qrels {field} does not match current authoritative input")
        for field in ("target_domain", "mechanism", "reason"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"qrels {field} is required")
        metadata_variants.add((
            row["schema_version"], judge_model, row["dataset_sha256"],
            row["kb_sha256"], row["results_sha256"],
        ))
        relevance = row.get("relevance")
        if type(relevance) is not int or relevance not in {0, 1, 2, 3}:
            raise ValueError(f"invalid qrel relevance: {row}")
        query_id, doc_id = row.get("query_id"), row.get("doc_id")
        if doc_id in qrels[query_id]:
            raise ValueError(f"duplicate qrel: {(query_id, doc_id)}")
        qrels[query_id][doc_id] = relevance

    if len(metadata_variants) != 1:
        raise ValueError("qrels contains mixed schema, model, or input fingerprints")

    expected = {
        outcome["id"]: set(outcome["top_ids"][:5])
        for outcome in outcomes if not outcome["expected_oos"]
    }
    if set(qrels) != set(expected):
        missing = sorted(set(expected) - set(qrels))
        unknown = sorted(set(qrels) - set(expected))
        raise ValueError(f"qrels query coverage mismatch missing={missing[:5]} unknown={unknown[:5]}")
    for query_id, expected_docs in expected.items():
        actual_docs = set(qrels[query_id])
        if actual_docs != expected_docs:
            raise ValueError(
                f"qrels doc coverage mismatch for {query_id}: "
                f"missing={expected_docs-actual_docs} unknown={actual_docs-expected_docs}"
            )

    ndcgs: list[float] = []
    successes: list[bool] = []
    judged_queries = 0
    for outcome in outcomes:
        judgments = qrels.get(outcome["id"])
        if not judgments:
            continue
        judged_queries += 1
        gains = [judgments.get(doc_id, 0) for doc_id in outcome["top_ids"][:5]]
        dcg = sum((2**rel - 1) / math.log2(rank + 1) for rank, rel in enumerate(gains, 1))
        ideal = sorted(judgments.values(), reverse=True)[:5]
        idcg = sum((2**rel - 1) / math.log2(rank + 1) for rank, rel in enumerate(ideal, 1))
        ndcgs.append(dcg / idcg if idcg else 0.0)
        successes.append(any(rel >= 2 for rel in gains))
    metrics["qrels"] = {
        "judged_queries": judged_queries,
        "judgments": sum(len(items) for items in qrels.values()),
        "ndcg_at_5": round(statistics.mean(ndcgs), 4) if ndcgs else 0.0,
        "success_at_5": round(sum(successes) / len(successes), 4) if successes else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--base-url", help="Server root, e.g. https://beta.structural.bytedance.city")
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--direct", action="store_true", help="Run SearchService in-process using the production-v2 local artifact")
    parser.add_argument("--qrels", type=Path, help="Optional graded qrels JSONL for nDCG@5")
    parser.add_argument("--qrels-kb", type=Path, default=ROOT / "data" / "kb-expanded.jsonl")
    parser.add_argument(
        "--qrels-frozen-results",
        type=Path,
        default=ROOT / "evaluation" / "results" / "retrieval-v1-local-baseline.json",
    )
    args = parser.parse_args()
    rows = load_dataset(args.dataset)
    print(f"dataset valid: {len(rows)} rows / 50 bilingual pairs")
    if args.validate_only:
        return 0
    search_call = None
    source = args.base_url
    if args.direct:
        sys.path.insert(0, str(ROOT))
        sys.path.insert(0, str(ROOT / "web" / "backend"))
        from services.scope_guard import is_out_of_scope
        from services.search_service import SearchService

        service = SearchService(
            data_dir=str(ROOT / "data"),
            kb_file="kb-expanded.jsonl",
            model_path=str(ROOT / "models" / "structural-v2"),
            precomputed_embeddings=str(ROOT / "web" / "data" / "kb_v2_embeddings.npy.bak-session22"),
        )

        def direct_search(row):
            refused, reason = is_out_of_scope(row["query"])
            results = [] if refused else service.search(row["query"], top_k=5)
            return {"out_of_scope": refused, "scope_reason": reason, "results": results}

        search_call = direct_search
        source = "local-production-v2-4443"
    elif not args.base_url:
        parser.error("--base-url or --direct is required unless --validate-only is used")
    metrics, outcomes = evaluate(rows, args.base_url or "", args.timeout, search_call=search_call)
    if args.qrels:
        add_qrel_metrics(
            metrics, outcomes, args.qrels,
            dataset_path=args.dataset,
            kb_path=args.qrels_kb,
            frozen_results_path=args.qrels_frozen_results,
        )
    report = {"schema_version": "retrieval-eval-v1", "source": source, "metrics": metrics, "outcomes": outcomes}
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(f"report written: {args.output}")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if metrics["request_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
