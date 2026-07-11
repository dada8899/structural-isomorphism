#!/usr/bin/env python3
"""Offline multilingual dense-retrieval experiment on frozen evaluation assets.

Only model artifacts may be downloaded when explicitly enabled. Queries and KB
documents are read locally and passed only to the local SentenceTransformer.
Full-corpus retrieval is diagnostic; qrel metrics are restricted to the exact
five-document pools judged for the frozen production baseline.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Protocol

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/retrieval-v1.jsonl"
QRELS = ROOT / "evaluation/qrels-v1.jsonl"
BASELINE = ROOT / "evaluation/results/retrieval-v1-local-baseline.json"
KB = ROOT / "data/kb-expanded.jsonl"
MANIFEST = ROOT / "artifacts/production-v2-4443.json"
DEFAULT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class Encoder(Protocol):
    def encode(self, sentences: list[str], **kwargs: Any) -> np.ndarray: ...


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def package_version(distribution: str) -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def dcg(relevances: Iterable[int]) -> float:
    return sum((2**rel - 1) / math.log2(rank + 1) for rank, rel in enumerate(relevances, 1))


def load_frozen_inputs(
    dataset_path: Path = DATASET,
    qrels_path: Path = QRELS,
    baseline_path: Path = BASELINE,
    kb_path: Path = KB,
) -> tuple[list[dict], list[dict], dict[str, dict[str, int]], dict[str, dict]]:
    queries = load_jsonl(dataset_path)
    kb = load_jsonl(kb_path)
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    outcomes = {row["id"]: row for row in baseline["outcomes"]}
    expected = {
        "dataset_sha256": sha256(dataset_path),
        "kb_sha256": sha256(kb_path),
        "results_sha256": sha256(baseline_path),
    }
    qrels: dict[str, dict[str, int]] = defaultdict(dict)
    for row in load_jsonl(qrels_path):
        for field, value in expected.items():
            if row.get(field) != value:
                raise ValueError(f"qrels {field} does not match frozen input")
        query_id, doc_id = row["query_id"], row["doc_id"]
        if doc_id in qrels[query_id] or row.get("relevance") not in {0, 1, 2, 3}:
            raise ValueError(f"invalid or duplicate qrel: {(query_id, doc_id)}")
        qrels[query_id][doc_id] = row["relevance"]

    pairs: dict[str, set[str]] = defaultdict(set)
    for row in queries:
        pairs[row["pair_id"]].add(row["language"])
    if len(queries) != 100 or len(pairs) != 50 or any(languages != {"en", "zh"} for languages in pairs.values()):
        raise ValueError("expected exactly 100 queries in 50 complete English/Chinese pairs")
    if len(kb) != 4443 or len({row["id"] for row in kb}) != 4443:
        raise ValueError("expected exactly 4443 uniquely identified KB documents")
    judged_ids = {row["id"] for row in queries if not row["labels"]["out_of_scope"]}
    if set(qrels) != judged_ids or any(len(qrels[query_id]) != 5 for query_id in judged_ids):
        raise ValueError("qrels must cover every in-scope query with exactly five documents")
    if any(set(outcomes[qid]["top_ids"]) != set(qrels[qid]) for qid in judged_ids):
        raise ValueError("qrels are not the frozen production-baseline candidate pools")
    return queries, kb, dict(qrels), outcomes


def normalize(matrix: np.ndarray) -> np.ndarray:
    values = np.asarray(matrix, dtype=np.float32)
    if values.ndim != 2 or not np.all(np.isfinite(values)):
        raise ValueError("encoder output must be a finite two-dimensional matrix")
    norms = np.linalg.norm(values, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("encoder output contains a zero vector")
    return values / norms


def encode_normalized(model: Encoder, texts: list[str], batch_size: int) -> np.ndarray:
    encoded = model.encode(
        texts,
        batch_size=batch_size,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    )
    if len(encoded) != len(texts):
        raise ValueError("encoder returned an unexpected row count")
    return normalize(encoded)


def rank_all(query_vector: np.ndarray, doc_vectors: np.ndarray, doc_ids: list[str]) -> list[int]:
    if doc_vectors.shape[0] != len(doc_ids) or query_vector.shape != (doc_vectors.shape[1],):
        raise ValueError("query, document vectors, and document IDs have incompatible shapes")
    scores = doc_vectors @ query_vector
    # Explicit secondary key makes ties deterministic across BLAS implementations.
    return sorted(range(len(doc_ids)), key=lambda i: (-float(scores[i]), doc_ids[i]))


def judged_pool_metrics(rankings: dict[str, list[str]], qrels: dict[str, dict[str, int]]) -> dict[str, Any]:
    ndcgs, mrrs, top1s = [], [], []
    for query_id in sorted(rankings):
        ranking, judgments = rankings[query_id], qrels[query_id]
        if len(ranking) != 5 or len(set(ranking)) != 5 or set(ranking) != set(judgments):
            raise ValueError(f"{query_id}: ranking must contain the exact fixed judged pool")
        gains = [judgments[doc_id] for doc_id in ranking]
        ideal_dcg = dcg(sorted(judgments.values(), reverse=True))
        ndcgs.append(dcg(gains) / ideal_dcg if ideal_dcg else 0.0)
        relevant = [rank for rank, relevance in enumerate(gains, 1) if relevance >= 2]
        mrrs.append(1 / relevant[0] if relevant else 0.0)
        top1s.append(gains[0] >= 2)
    return {
        "queries": len(rankings),
        "ndcg_at_5_fixed_judged_pool": round(float(np.mean(ndcgs)), 6),
        "mrr_fixed_judged_pool": round(float(np.mean(mrrs)), 6),
        "top1_success_fixed_judged_pool": round(float(np.mean(top1s)), 6),
    }


def fingerprint_tree(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"model cache path does not exist: {path}")
    files = []
    for item in sorted((p for p in path.rglob("*") if p.is_file()), key=lambda p: p.relative_to(path).as_posix()):
        files.append({"path": item.relative_to(path).as_posix(), "size": item.stat().st_size, "sha256": sha256(item)})
    if not files:
        raise ValueError(f"model cache path contains no files: {path}")
    digest = hashlib.sha256()
    for item in files:
        digest.update(json.dumps(item, sort_keys=True, separators=(",", ":")).encode())
    return {"path": str(path.resolve()), "file_count": len(files), "tree_sha256": digest.hexdigest(), "files": files}


def resolved_model_path(
    model: Any,
    requested: str,
    *,
    cache_dir: Path | None = None,
    revision: str | None = None,
) -> Path:
    first_module = next(iter(getattr(model, "_modules", {}).values()), None)
    auto_model = getattr(first_module, "auto_model", None)
    tokenizer = getattr(first_module, "tokenizer", None)
    candidates = [
        getattr(first_module, "model_name_or_path", None),
        getattr(getattr(auto_model, "config", None), "_name_or_path", None),
        getattr(tokenizer, "name_or_path", None),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and Path(candidate).is_dir():
            return Path(candidate)
    if Path(requested).is_dir():
        return Path(requested)

    cache_root = cache_dir
    if cache_root is None:
        hub_cache = os.environ.get("HUGGINGFACE_HUB_CACHE")
        hf_home = os.environ.get("HF_HOME")
        cache_root = Path(hub_cache) if hub_cache else Path(hf_home or Path.home() / ".cache/huggingface") / "hub"
    repository = cache_root / ("models--" + requested.replace("/", "--"))
    snapshots = repository / "snapshots"
    revision_name = revision
    if revision_name and (repository / "refs" / revision_name).is_file():
        revision_name = (repository / "refs" / revision_name).read_text(encoding="utf-8").strip()
    if not revision_name and (repository / "refs/main").is_file():
        revision_name = (repository / "refs/main").read_text(encoding="utf-8").strip()
    if revision_name and (snapshots / revision_name).is_dir():
        return snapshots / revision_name
    available = sorted(path for path in snapshots.glob("*") if path.is_dir())
    if len(available) == 1:
        return available[0]
    raise ValueError(
        "cannot unambiguously resolve model cache directory for fingerprinting; "
        "pass --model as a local snapshot path or pin --revision"
    )


def build_report(
    model: Encoder,
    model_path: Path,
    *,
    model_id: str,
    requested_revision: str | None,
    batch_size: int,
    candidate_k: int,
    dataset_path: Path = DATASET,
    qrels_path: Path = QRELS,
    baseline_path: Path = BASELINE,
    kb_path: Path = KB,
    manifest_path: Path = MANIFEST,
) -> dict[str, Any]:
    queries, kb, qrels, outcomes = load_frozen_inputs(dataset_path, qrels_path, baseline_path, kb_path)
    doc_ids = [row["id"] for row in kb]
    descriptions = [row["description"] for row in kb]
    doc_vectors = encode_normalized(model, descriptions, batch_size)
    query_vectors = encode_normalized(model, [row["query"] for row in queries], batch_size)
    if query_vectors.shape[1] != doc_vectors.shape[1]:
        raise ValueError("query and document embedding dimensions differ")

    full_rankings = {
        row["id"]: [doc_ids[i] for i in rank_all(query_vectors[index], doc_vectors, doc_ids)]
        for index, row in enumerate(queries)
    }
    by_pair: dict[str, dict[str, dict]] = defaultdict(dict)
    for row in queries:
        by_pair[row["pair_id"]][row["language"]] = row
    pair_diagnostics = []
    for pair_id in sorted(by_pair):
        en_id, zh_id = by_pair[pair_id]["en"]["id"], by_pair[pair_id]["zh"]["id"]
        en_top, zh_top = full_rankings[en_id][:candidate_k], full_rankings[zh_id][:candidate_k]
        union = set(en_top) | set(zh_top)
        judged = set(qrels.get(en_id, {})) | set(qrels.get(zh_id, {}))
        top5_intersection = set(en_top[:5]) & set(zh_top[:5])
        top5_union = set(en_top[:5]) | set(zh_top[:5])
        pair_diagnostics.append({
            "pair_id": pair_id,
            "out_of_scope": bool(by_pair[pair_id]["en"]["labels"]["out_of_scope"]),
            "top5_intersection": len(top5_intersection),
            "top5_jaccard": round(len(top5_intersection) / len(top5_union), 6),
            "candidate_union_size": len(union),
            "judged_in_union": len(union & judged),
            "unjudged_in_union": len(union - judged),
        })

    english_ids = sorted(
        row["id"] for row in queries if row["language"] == "en" and not row["labels"]["out_of_scope"]
    )
    baseline_rankings = {query_id: outcomes[query_id]["top_ids"] for query_id in english_ids}
    dense_rerankings = {
        query_id: [doc_id for doc_id in full_rankings[query_id] if doc_id in qrels[query_id]]
        for query_id in english_ids
    }
    average = lambda key: round(float(np.mean([row[key] for row in pair_diagnostics])), 6)
    model_fingerprint = fingerprint_tree(model_path)
    resolved_revision = None
    for marker in (model_path, *model_path.parents):
        if marker.parent.name == "snapshots":
            resolved_revision = marker.name
            break
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    script_path = Path(__file__).resolve()
    return {
        "schema_version": "multilingual-embedding-experiment-v1",
        "frozen_inputs": {
            "dataset_sha256": sha256(dataset_path), "qrels_sha256": sha256(qrels_path),
            "baseline_sha256": sha256(baseline_path), "kb_sha256": sha256(kb_path),
            "manifest_sha256": sha256(manifest_path), "artifact_id": manifest["artifact_id"],
            "query_count": len(queries), "paired_query_count": len(by_pair), "kb_rows": len(kb),
        },
        "model": {
            "requested_id": model_id, "requested_revision": requested_revision,
            "resolved_cache_revision": resolved_revision, "cache": model_fingerprint,
        },
        "runtime": {
            "python": platform.python_version(), "numpy": np.__version__,
            "sentence_transformers": package_version("sentence-transformers"),
            "torch": package_version("torch"),
            "platform": platform.platform(), "embedding_dimension": int(doc_vectors.shape[1]),
            "batch_size": batch_size, "candidate_k": candidate_k,
            "device": str(getattr(model, "device", "unknown")),
            "determinism": "model.eval; normalized float32 embeddings; deterministic doc-id tie break",
        },
        "reproduction": {
            "script_sha256": sha256(script_path),
            "command": (
                f".venv/bin/python scripts/{script_path.name} --batch-size {batch_size} "
                f"--candidate-k {candidate_k} --output evaluation/results/multilingual-minilm-l12-v2.json"
            ),
            "network_requirement": "none after the fingerprinted model snapshot is cached",
        },
        "methodology": {
            "document_text": "description only", "retrieval": "normalized dense embeddings; pure cosine; deterministic doc-id tie break",
            "privacy": "queries and KB documents are encoded locally and are never sent to an API",
            "pair_consistency_scope": "all 50 English/Chinese query pairs, including 10 out-of-scope pairs",
            "rerank_scope": "the exact old five-document judged pool for 40 in-scope English queries",
        },
        "paired_top5": {
            "mean_jaccard_all_50_pairs": average("top5_jaccard"),
            "mean_intersection_all_50_pairs": average("top5_intersection"),
            "per_pair": pair_diagnostics,
        },
        "fixed_old_english_judged_pool": {
            "production_baseline_order": judged_pool_metrics(baseline_rankings, qrels),
            "multilingual_dense_rerank": judged_pool_metrics(dense_rerankings, qrels),
        },
        "candidate_union_diagnostics": {
            "candidate_k_per_language": candidate_k,
            "mean_union_size": average("candidate_union_size"),
            "mean_judged_in_union": average("judged_in_union"),
            "mean_unjudged_in_union": average("unjudged_in_union"),
        },
        "comparability_boundaries": {
            "valid": "dense versus production ordering only as a reranker over each identical fixed old English judged pool",
            "not_valid": "full-corpus dense Top-5 is not endpoint-comparable to production fused retrieval, diversification, thresholds, or filters",
            "recall": "candidate-union documents outside the old pool are unjudged and cannot establish recall gains or losses",
            "dataset": "the old judged pool is a development set and does not independently validate generalization",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--revision")
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--candidate-k", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.batch_size < 1 or args.candidate_k < 5:
        parser.error("--batch-size must be positive and --candidate-k must be at least 5")
    from sentence_transformers import SentenceTransformer

    kwargs: dict[str, Any] = {"local_files_only": not args.allow_model_download}
    if args.revision:
        kwargs["revision"] = args.revision
    if args.cache_dir:
        kwargs["cache_folder"] = str(args.cache_dir)
    model = SentenceTransformer(args.model, **kwargs)
    model_path = resolved_model_path(model, args.model, cache_dir=args.cache_dir, revision=args.revision)
    report = build_report(
        model, model_path, model_id=args.model, requested_revision=args.revision,
        batch_size=args.batch_size, candidate_k=args.candidate_k,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["fixed_old_english_judged_pool"], ensure_ascii=False, indent=2, sort_keys=True))
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
