#!/usr/bin/env python3
"""Build the frozen English/reference-Chinese candidate union for judging.

This is an offline evidence builder. It does not translate queries, call an
external API, or alter production retrieval. Each English in-scope query is
paired with its human-authored Chinese reference and both rankings contribute
Top-K documents to a deduplicated, provenance-preserving pool.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "evaluation/retrieval-v1.jsonl"
KB = ROOT / "data/kb-expanded.jsonl"
MANIFEST = ROOT / "artifacts/production-v2-4443.json"
EMBEDDINGS = ROOT / "web/data/kb_v2_embeddings.npy.bak-session22"
MODEL = ROOT / "models/structural-v2"
SEARCH_SERVICE = ROOT / "web/backend/services/search_service.py"
OUTPUT = ROOT / "evaluation/english-candidate-pool-v1.jsonl"
SCHEMA_VERSION = "english-candidate-pool-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{number}: row must be an object")
        rows.append(value)
    return rows


def model_fingerprint(manifest: dict[str, Any], model_dir: Path) -> str:
    required = manifest.get("model", {}).get("required_files")
    if not isinstance(required, dict) or not required:
        raise ValueError("manifest model.required_files must be a non-empty object")
    verified: dict[str, str] = {}
    for filename, expected in sorted(required.items()):
        if not isinstance(filename, str) or not isinstance(expected, str):
            raise ValueError("invalid model required_files entry")
        actual = sha256(model_dir / filename)
        if actual != expected:
            raise ValueError(f"model fingerprint mismatch: {filename}")
        verified[filename] = actual
    canonical = json.dumps(verified, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def input_fingerprints(
    dataset: Path, kb: Path, manifest_path: Path, embeddings: Path,
    model_dir: Path, code_paths: list[Path], git_sha: str,
) -> dict[str, str]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_kb = manifest.get("kb", {}).get("sha256")
    expected_embeddings = manifest.get("embeddings", {}).get("sha256")
    kb_hash, embeddings_hash = sha256(kb), sha256(embeddings)
    if kb_hash != expected_kb or embeddings_hash != expected_embeddings:
        raise ValueError("KB or embeddings do not match the production manifest")
    code_hashes = {str(path.relative_to(ROOT)): sha256(path) for path in sorted(code_paths)}
    code_hash = hashlib.sha256(
        json.dumps(code_hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "dataset_sha256": sha256(dataset),
        "kb_sha256": kb_hash,
        "model_sha256": model_fingerprint(manifest, model_dir),
        "embeddings_sha256": embeddings_hash,
        "code_sha256": code_hash,
        "code_git_sha": git_sha,
        "artifact_id": manifest["artifact_id"],
    }


def build_pool(
    dataset_rows: list[dict[str, Any]],
    kb_rows: list[dict[str, Any]],
    ranker: Callable[[str], list[str]],
    fingerprints: dict[str, str],
    *,
    top_k: int = 10,
) -> list[dict[str, Any]]:
    if type(top_k) is not int or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    required_fingerprints = {
        "dataset_sha256", "kb_sha256", "model_sha256", "embeddings_sha256",
        "code_sha256", "code_git_sha", "artifact_id",
    }
    if set(fingerprints) != required_fingerprints or any(
        not isinstance(value, str) or not value for value in fingerprints.values()
    ):
        raise ValueError("fingerprints have invalid schema")
    kb_by_id = {row.get("id"): row for row in kb_rows}
    if None in kb_by_id or len(kb_by_id) != len(kb_rows):
        raise ValueError("KB ids must be present and unique")
    pairs: dict[str, dict[str, dict[str, Any]]] = {}
    for row in dataset_rows:
        pair_id, language = row.get("pair_id"), row.get("language")
        if not isinstance(pair_id, str) or language not in {"en", "zh"}:
            raise ValueError("dataset pair_id/language schema is invalid")
        bucket = pairs.setdefault(pair_id, {})
        if language in bucket:
            raise ValueError(f"duplicate {language} row for {pair_id}")
        bucket[language] = row
    english = sorted(
        (row for row in dataset_rows if row.get("language") == "en"
         and row.get("labels", {}).get("out_of_scope") is False),
        key=lambda row: row["id"],
    )
    if len(english) != 40:
        raise ValueError(f"expected 40 English in-scope queries, got {len(english)}")
    output = []
    for en_row in english:
        pair = pairs.get(en_row["pair_id"], {})
        zh_row = pair.get("zh")
        if not zh_row or zh_row.get("labels", {}).get("out_of_scope") is not False:
            raise ValueError(f"missing in-scope Chinese reference for {en_row['id']}")
        rankings = {
            "original_english": ranker(en_row["query"])[:top_k],
            "reference_chinese": ranker(zh_row["query"])[:top_k],
        }
        if any(len(ids) != top_k or len(set(ids)) != top_k for ids in rankings.values()):
            raise ValueError(f"{en_row['id']}: each ranking must have {top_k} unique ids")
        unknown = set(rankings["original_english"] + rankings["reference_chinese"]) - set(kb_by_id)
        if unknown:
            raise ValueError(f"{en_row['id']}: ranking contains unknown KB ids: {sorted(unknown)[:3]}")
        provenance: dict[str, list[dict[str, Any]]] = {}
        order: list[str] = []
        for source in ("original_english", "reference_chinese"):
            for rank, doc_id in enumerate(rankings[source], 1):
                if doc_id not in provenance:
                    provenance[doc_id] = []
                    order.append(doc_id)
                provenance[doc_id].append({"source": source, "rank": rank})
        candidates = []
        for doc_id in order:
            item = kb_by_id[doc_id]
            candidates.append({
                "doc_id": doc_id,
                "name": str(item.get("name", "")),
                "domain": str(item.get("domain", "")),
                "description": str(item.get("description", ""))[:900],
                "provenance": provenance[doc_id],
            })
        output.append({
            "schema_version": SCHEMA_VERSION,
            **fingerprints,
            "query_id": en_row["id"],
            "pair_id": en_row["pair_id"],
            "query": en_row["query"],
            "reference_query_id": zh_row["id"],
            "reference_query": zh_row["query"],
            "top_k_per_source": top_k,
            "candidate_count": len(candidates),
            "candidates": candidates,
        })
    validate_pool(output, set(kb_by_id), fingerprints, top_k=top_k)
    return output


def validate_pool(rows: list[dict[str, Any]], allowed_doc_ids: set[str], fingerprints: dict[str, str], *, top_k: int) -> None:
    if len(rows) != 40 or len({row.get("query_id") for row in rows}) != 40:
        raise ValueError("candidate pool must contain 40 unique queries")
    for row in rows:
        if row.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("candidate pool schema mismatch")
        if any(row.get(key) != value for key, value in fingerprints.items()):
            raise ValueError("candidate pool fingerprint mismatch")
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or row.get("candidate_count") != len(candidates):
            raise ValueError("candidate count mismatch")
        ids = [candidate.get("doc_id") for candidate in candidates]
        if len(ids) != len(set(ids)) or not set(ids) <= allowed_doc_ids:
            raise ValueError("candidate ids violate the KB allowlist")
        coverage = {"original_english": set(), "reference_chinese": set()}
        for candidate in candidates:
            provenance = candidate.get("provenance")
            if not isinstance(provenance, list) or not provenance:
                raise ValueError("candidate provenance is required")
            for source_rank in provenance:
                source, rank = source_rank.get("source"), source_rank.get("rank")
                if source not in coverage or type(rank) is not int or not 1 <= rank <= top_k:
                    raise ValueError("invalid candidate provenance")
                if rank in coverage[source]:
                    raise ValueError("duplicate rank within source")
                coverage[source].add(rank)
        if any(ranks != set(range(1, top_k + 1)) for ranks in coverage.values()):
            raise ValueError("candidate provenance does not cover both complete rankings")


def atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--top-k", type=int, default=10)
    args = parser.parse_args()
    git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    fingerprints = input_fingerprints(
        DATASET, KB, MANIFEST, EMBEDDINGS, MODEL,
        [Path(__file__).resolve(), SEARCH_SERVICE], git_sha,
    )
    sys.path[:0] = [str(ROOT), str(ROOT / "web/backend")]
    from services.search_service import SearchService
    import numpy as np
    service = SearchService(
        data_dir=str(ROOT / "data"), kb_file=KB.name, model_path=str(MODEL),
        precomputed_embeddings=str(EMBEDDINGS),
    )
    def rank(query: str) -> list[str]:
        indices = np.argsort(service._fused_scores(query), kind="stable")[::-1]
        return [service.kb[int(index)]["id"] for index in indices]
    rows = build_pool(read_jsonl(DATASET), read_jsonl(KB), rank, fingerprints, top_k=args.top_k)
    atomic_write_jsonl(args.output, rows)
    total = sum(row["candidate_count"] for row in rows)
    print(f"wrote {len(rows)} queries / {total} candidate judgments to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
