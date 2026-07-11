#!/usr/bin/env python3
"""Build, validate, and merge blinded human judgments for the English pool.

No model judgment is produced here. Review bundles omit retrieval provenance,
rank, model names, and seed labels; exports remain bound to the frozen pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.judge_english_candidate_pool import load_pool, output_metadata, read_jsonl

DEFAULT_POOL = ROOT / "evaluation/english-candidate-pool-v1.jsonl"
DEFAULT_KB = ROOT / "data/kb-expanded.jsonl"
DEFAULT_SEED = ROOT / "evaluation/qrels-v1.jsonl"
DEFAULT_BUNDLE = ROOT / "evaluation/review/english-review-bundle-v1.json"
BUNDLE_SCHEMA = "english-human-review-bundle-v1"
JUDGMENT_SCHEMA = "english-human-judgment-v1"
MERGED_SCHEMA = "english-human-adjudication-v1"
DECISIONS = {0, 1, 2, 3}
CONFIDENCES = {"low", "medium", "high"}
REJECT_REASONS = {
    "none", "not_relevant", "same_domain_only", "weak_evidence",
    "wrong_mechanism", "insufficient_information", "other",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: Any, *, jsonl: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            if jsonl:
                for row in value:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            else:
                json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def task_id(pool_hash: str, query_id: str, doc_id: str) -> str:
    value = f"{pool_hash}\0{query_id}\0{doc_id}".encode()
    return "ert_" + hashlib.sha256(value).hexdigest()[:24]


def seed_keys(seed_path: Path | None, pool: list[dict[str, Any]], metadata: dict[str, str]) -> set[tuple[str, str]]:
    if seed_path is None:
        return set()
    allowed = {(q["query_id"], c["doc_id"]) for q in pool for c in q["candidates"]}
    found: set[tuple[str, str]] = set()
    for row in read_jsonl(seed_path):
        key = (row.get("query_id"), row.get("doc_id"))
        if key not in allowed:
            continue
        if row.get("schema_version") != "qrels-v1":
            raise ValueError(f"seed schema mismatch: {key}")
        if row.get("dataset_sha256") != metadata["dataset_sha256"] or row.get("kb_sha256") != metadata["kb_sha256"]:
            raise ValueError(f"seed fingerprint mismatch: {key}")
        if key in found:
            raise ValueError(f"duplicate seed key: {key}")
        found.add(key)  # labels are deliberately not copied into the bundle
    return found


def build_bundle(pool_path: Path, kb_path: Path, seed_path: Path | None = DEFAULT_SEED) -> dict[str, Any]:
    pool, fingerprints = load_pool(pool_path, kb_path)
    metadata = output_metadata(pool_path, fingerprints)
    seeded = seed_keys(seed_path, pool, metadata)
    tasks = []
    for query in pool:
        for candidate in query["candidates"]:
            key = (query["query_id"], candidate["doc_id"])
            if key in seeded:
                continue
            tasks.append({
                "task_id": task_id(metadata["candidate_pool_sha256"], *key),
                "query_id": key[0], "doc_id": key[1], "query": query["query"],
                "candidate_name": candidate["name"], "candidate_domain": candidate["domain"],
                "candidate_description": candidate["description"],
            })
    rng = random.Random(int(metadata["candidate_pool_sha256"][:16], 16))
    rng.shuffle(tasks)
    bundle = {
        "schema_version": BUNDLE_SCHEMA, "metadata": metadata,
        "rubric": {
            "relevance": {"0": "irrelevant", "1": "weak", "2": "relevant", "3": "strong"},
            "confidence": sorted(CONFIDENCES), "reject_reasons": sorted(REJECT_REASONS),
        },
        "task_count": len(tasks), "tasks": tasks,
    }
    validate_bundle(bundle, pool_path, kb_path, seed_path)
    return bundle


def validate_bundle(bundle: dict[str, Any], pool_path: Path, kb_path: Path, seed_path: Path | None = DEFAULT_SEED) -> dict[str, dict[str, Any]]:
    pool, fingerprints = load_pool(pool_path, kb_path)
    metadata = output_metadata(pool_path, fingerprints)
    if bundle.get("schema_version") != BUNDLE_SCHEMA or bundle.get("metadata") != metadata:
        raise ValueError("bundle schema or fingerprint mismatch")
    expected_seed = seed_keys(seed_path, pool, metadata)
    allowed = {(q["query_id"], c["doc_id"]) for q in pool for c in q["candidates"]} - expected_seed
    expected_content = {
        (query["query_id"], candidate["doc_id"]): {
            "query": query["query"], "candidate_name": candidate["name"],
            "candidate_domain": candidate["domain"],
            "candidate_description": candidate["description"],
        }
        for query in pool for candidate in query["candidates"]
        if (query["query_id"], candidate["doc_id"]) not in expected_seed
    }
    tasks = bundle.get("tasks")
    if not isinstance(tasks, list) or bundle.get("task_count") != len(tasks):
        raise ValueError("bundle task_count mismatch")
    by_id: dict[str, dict[str, Any]] = {}
    seen_keys = set()
    forbidden = {"provenance", "rank", "source", "model", "relevance", "judgment"}
    for task in tasks:
        if not isinstance(task, dict) or forbidden & set(task):
            raise ValueError("bundle leaks blinded fields")
        key = (task.get("query_id"), task.get("doc_id"))
        expected_id = task_id(metadata["candidate_pool_sha256"], *key) if all(isinstance(v, str) for v in key) else ""
        if key not in allowed or task.get("task_id") != expected_id:
            raise ValueError(f"bundle violates task allowlist: {key}")
        if key in seen_keys or expected_id in by_id:
            raise ValueError(f"duplicate bundle task: {key}")
        for field in ("query", "candidate_name", "candidate_domain", "candidate_description"):
            if task.get(field) != expected_content[key][field]:
                raise ValueError(f"bundle content drift in {field}: {key}")
        seen_keys.add(key)
        by_id[expected_id] = task
    if seen_keys != allowed:
        raise ValueError(f"bundle missing {len(allowed - seen_keys)} tasks")
    return by_id


def validate_judgments(rows: list[dict[str, Any]], bundle: dict[str, Any], *, require_complete: bool = True) -> list[dict[str, Any]]:
    tasks = {task["task_id"]: task for task in bundle["tasks"]}
    metadata = bundle["metadata"]
    clean, seen = [], set()
    expected_fields = {
        "schema_version", "task_id", "query_id", "doc_id", "bundle_fingerprint",
        "reviewer_id", "relevance", "same_domain", "evidence_present",
        "reject_reason", "confidence", "note",
    }
    for row in rows:
        if not isinstance(row, dict) or row.get("schema_version") != JUDGMENT_SCHEMA:
            raise ValueError("judgment schema mismatch")
        if set(row) != expected_fields:
            raise ValueError("judgment fields do not match the strict schema")
        tid = row.get("task_id")
        if tid not in tasks or tid in seen:
            raise ValueError(f"unknown or duplicate task_id: {tid}")
        if row.get("bundle_fingerprint") != metadata["candidate_pool_sha256"]:
            raise ValueError(f"judgment fingerprint mismatch: {tid}")
        reviewer = row.get("reviewer_id")
        relevance = row.get("relevance")
        if not isinstance(reviewer, str) or not reviewer.strip() or len(reviewer) > 80:
            raise ValueError(f"invalid reviewer_id: {tid}")
        if type(relevance) is not int or relevance not in DECISIONS:
            raise ValueError(f"invalid relevance: {tid}")
        if type(row.get("same_domain")) is not bool or type(row.get("evidence_present")) is not bool:
            raise ValueError(f"invalid boolean fields: {tid}")
        if row.get("reject_reason") not in REJECT_REASONS or row.get("confidence") not in CONFIDENCES:
            raise ValueError(f"invalid reject/confidence: {tid}")
        note = row.get("note", "")
        if not isinstance(note, str) or len(note) > 1000:
            raise ValueError(f"invalid note: {tid}")
        if relevance == 0 and row["reject_reason"] == "none":
            raise ValueError(f"relevance 0 requires reject_reason: {tid}")
        if relevance > 0 and row["reject_reason"] not in {"none", "same_domain_only", "weak_evidence"}:
            raise ValueError(f"positive relevance has incompatible reject_reason: {tid}")
        expected = tasks[tid]
        if row.get("query_id") != expected["query_id"] or row.get("doc_id") != expected["doc_id"]:
            raise ValueError(f"judgment task identity mismatch: {tid}")
        seen.add(tid)
        clean.append(row)
    if clean and len({row["reviewer_id"] for row in clean}) != 1:
        raise ValueError("one file must contain exactly one reviewer_id")
    if require_complete and seen != set(tasks):
        raise ValueError(f"judgments missing {len(set(tasks) - seen)} tasks")
    return sorted(clean, key=lambda row: row["task_id"])


def weighted_kappa(a: dict[str, int], b: dict[str, int], task_ids: set[str]) -> float | None:
    ids = sorted(task_ids & set(a) & set(b))
    if not ids:
        return None
    matrix = [[0] * 4 for _ in range(4)]
    for tid in ids:
        matrix[a[tid]][b[tid]] += 1
    n = len(ids)
    weights = [[((i - j) / 3) ** 2 for j in range(4)] for i in range(4)]
    observed = sum(weights[i][j] * matrix[i][j] for i in range(4) for j in range(4)) / n
    left = [sum(matrix[i]) for i in range(4)]
    right = [sum(matrix[i][j] for i in range(4)) for j in range(4)]
    expected = sum(weights[i][j] * left[i] * right[j] for i in range(4) for j in range(4)) / (n * n)
    return 1.0 if expected == 0 and observed == 0 else (None if expected == 0 else 1 - observed / expected)


def pair_agreement(a: dict[str, int], b: dict[str, int]) -> dict[str, Any]:
    overlap = sorted(set(a) & set(b))
    if not overlap:
        return {"overlap": 0, "exact_agreement": None, "within_one_agreement": None,
                "quadratic_weighted_kappa": None}
    return {
        "overlap": len(overlap),
        "exact_agreement": sum(a[tid] == b[tid] for tid in overlap) / len(overlap),
        "within_one_agreement": sum(abs(a[tid] - b[tid]) <= 1 for tid in overlap) / len(overlap),
        "quadratic_weighted_kappa": weighted_kappa(a, b, set(overlap)),
    }


def merge_judgments(files: Iterable[Path], bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reviewers: dict[str, dict[str, int]] = {}
    for path in files:
        rows = validate_judgments(read_jsonl(path), bundle, require_complete=False)
        if not rows:
            raise ValueError(f"empty review file: {path}")
        reviewer = rows[0]["reviewer_id"]
        if reviewer in reviewers:
            raise ValueError(f"duplicate reviewer file: {reviewer}")
        reviewers[reviewer] = {row["task_id"]: row["relevance"] for row in rows}
        for row in rows:
            by_task[row["task_id"]].append(row)
    task_map = {task["task_id"]: task for task in bundle["tasks"]}
    merged, disputes = [], []
    for tid in sorted(task_map):
        votes = by_task.get(tid, [])
        counts = Counter(row["relevance"] for row in votes)
        top = counts.most_common()
        consensus = top[0][0] if top and (len(top) == 1 or top[0][1] > top[1][1]) else None
        needs_adjudication = len(votes) < 2 or consensus is None or (votes and max(counts) - min(counts) >= 2)
        item = {
            "schema_version": MERGED_SCHEMA, "task_id": tid,
            "query_id": task_map[tid]["query_id"], "doc_id": task_map[tid]["doc_id"],
            "bundle_fingerprint": bundle["metadata"]["candidate_pool_sha256"],
            "review_count": len(votes), "vote_counts": {str(i): counts[i] for i in range(4)},
            "consensus_relevance": consensus, "needs_adjudication": needs_adjudication,
        }
        merged.append(item)
        if needs_adjudication:
            disputes.append({**item, "query": task_map[tid]["query"], "candidate_name": task_map[tid]["candidate_name"],
                             "candidate_domain": task_map[tid]["candidate_domain"],
                             "votes": [{k: row[k] for k in ("reviewer_id", "relevance", "same_domain", "evidence_present", "reject_reason", "confidence", "note")} for row in votes]})
    pairwise = []
    names = sorted(reviewers)
    for index, first in enumerate(names):
        for second in names[index + 1:]:
            pairwise.append({"reviewer_a": first, "reviewer_b": second,
                             **pair_agreement(reviewers[first], reviewers[second])})
    kappas = [row["quadratic_weighted_kappa"] for row in pairwise if row["quadratic_weighted_kappa"] is not None]
    report = {"reviewers": names, "task_count": len(task_map), "judged_task_count": len(by_task),
              "adjudication_count": len(disputes), "pairwise": pairwise,
              "mean_quadratic_weighted_kappa": sum(kappas) / len(kappas) if kappas else None}
    return merged, report, disputes


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--pool", type=Path, default=DEFAULT_POOL); build.add_argument("--kb", type=Path, default=DEFAULT_KB)
    build.add_argument("--seed", type=Path, default=DEFAULT_SEED); build.add_argument("--output", type=Path, default=DEFAULT_BUNDLE)
    validate = sub.add_parser("validate")
    validate.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE); validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--allow-partial", action="store_true")
    merge = sub.add_parser("merge")
    merge.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE); merge.add_argument("--input", type=Path, nargs="+", required=True)
    merge.add_argument("--output", type=Path, required=True); merge.add_argument("--report", type=Path, required=True); merge.add_argument("--disputes", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        bundle = build_bundle(args.pool, args.kb, args.seed); atomic_json(args.output, bundle)
        print(f"wrote {bundle['task_count']} blinded tasks to {args.output}")
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        validate_bundle(bundle, DEFAULT_POOL, DEFAULT_KB, DEFAULT_SEED)
        if args.command == "validate":
            rows = validate_judgments(read_jsonl(args.input), bundle, require_complete=not args.allow_partial)
            print(f"valid: {len(rows)} human judgments")
        else:
            merged, report, disputes = merge_judgments(args.input, bundle)
            atomic_json(args.output, merged, jsonl=True); atomic_json(args.report, report); atomic_json(args.disputes, disputes, jsonl=True)
            print(f"merged {report['judged_task_count']} tasks; {len(disputes)} need adjudication")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
