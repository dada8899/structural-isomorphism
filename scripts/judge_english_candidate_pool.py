#!/usr/bin/env python3
"""Judge the frozen English/reference candidate pool with guarded resume.

Existing qrels may seed candidates already judged in the old Top-5 pool. Only
missing candidates are sent to the provider. All persisted rows bind to the
candidate-pool hash and its upstream artifact fingerprints.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.judge_retrieval_qrels import (  # noqa: E402
    DEFAULT_MODEL,
    call_provider,
    read_jsonl,
    validate_batch,
)


DEFAULT_POOL = ROOT / "evaluation/english-candidate-pool-v1.jsonl"
DEFAULT_SEED = ROOT / "evaluation/qrels-v1.jsonl"
DEFAULT_KB = ROOT / "data/kb-expanded.jsonl"
DEFAULT_OUTPUT = ROOT / "evaluation/english-qrels-v1.jsonl"
POOL_SCHEMA = "english-candidate-pool-v1"
OUTPUT_SCHEMA = "english-qrels-v1"
UPSTREAM_FIELDS = (
    "dataset_sha256", "kb_sha256", "model_sha256", "embeddings_sha256",
    "code_sha256", "code_git_sha", "artifact_id",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_pool(path: Path, kb_path: Path) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows = read_jsonl(path)
    if len(rows) != 40 or len({row.get("query_id") for row in rows}) != 40:
        raise ValueError("candidate pool must contain exactly 40 unique queries")
    kb_ids = {row.get("id") for row in read_jsonl(kb_path)}
    if None in kb_ids:
        raise ValueError("KB contains a missing id")
    fingerprints = {field: rows[0].get(field) for field in UPSTREAM_FIELDS}
    if any(not isinstance(value, str) or not value for value in fingerprints.values()):
        raise ValueError("candidate pool has missing upstream fingerprints")
    seen_pairs: set[tuple[str, str]] = set()
    for row in rows:
        if row.get("schema_version") != POOL_SCHEMA:
            raise ValueError("candidate pool schema mismatch")
        if any(row.get(field) != value for field, value in fingerprints.items()):
            raise ValueError("candidate pool has mixed upstream fingerprints")
        candidates = row.get("candidates")
        if not isinstance(candidates, list) or row.get("candidate_count") != len(candidates):
            raise ValueError("candidate pool candidate_count mismatch")
        local_ids: set[str] = set()
        for candidate in candidates:
            doc_id = candidate.get("doc_id") if isinstance(candidate, dict) else None
            key = (row["query_id"], doc_id)
            if not isinstance(doc_id, str) or doc_id not in kb_ids:
                raise ValueError(f"candidate violates KB allowlist: {key}")
            if doc_id in local_ids or key in seen_pairs:
                raise ValueError(f"duplicate candidate key: {key}")
            for field in ("name", "domain", "description"):
                if not isinstance(candidate.get(field), str):
                    raise ValueError(f"candidate {key} has invalid {field}")
            local_ids.add(doc_id)
            seen_pairs.add(key)
    return sorted(rows, key=lambda row: row["query_id"]), fingerprints


def output_metadata(pool_path: Path, fingerprints: dict[str, str]) -> dict[str, str]:
    return {"candidate_pool_sha256": sha256(pool_path), **fingerprints}


def validate_judgment_row(
    row: dict[str, Any], allowed: set[tuple[str, str]], metadata: dict[str, str],
) -> tuple[str, str]:
    key = (row.get("query_id"), row.get("doc_id"))
    if key not in allowed:
        raise ValueError(f"judgment has unknown key: {key}")
    if row.get("schema_version") != OUTPUT_SCHEMA:
        raise ValueError(f"judgment has invalid schema: {key}")
    if any(row.get(field) != value for field, value in metadata.items()):
        raise ValueError(f"judgment input fingerprint mismatch: {key}")
    if not isinstance(row.get("judge_model"), str) or not row["judge_model"]:
        raise ValueError(f"judgment judge_model is required: {key}")
    if row.get("judgment_source") not in {"seed_qrels", "provider"}:
        raise ValueError(f"judgment source is invalid: {key}")
    if type(row.get("relevance")) is not int or row["relevance"] not in {0, 1, 2, 3}:
        raise ValueError(f"judgment relevance is invalid: {key}")
    for field in ("target_domain", "mechanism", "reason"):
        value = row.get(field)
        if not isinstance(value, str) or not value.strip() or len(value) > 500:
            raise ValueError(f"judgment {field} is invalid: {key}")
    return key  # type: ignore[return-value]


def load_seed(
    path: Path | None, allowed: set[tuple[str, str]], metadata: dict[str, str],
) -> dict[tuple[str, str], dict[str, Any]]:
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    if path is None:
        return completed
    for row in read_jsonl(path):
        key = (row.get("query_id"), row.get("doc_id"))
        if key not in allowed:
            continue
        if key in completed:
            raise ValueError(f"seed qrels duplicate candidate: {key}")
        if row.get("schema_version") != "qrels-v1":
            raise ValueError(f"seed qrels schema mismatch: {key}")
        if row.get("dataset_sha256") != metadata["dataset_sha256"] or row.get("kb_sha256") != metadata["kb_sha256"]:
            raise ValueError(f"seed qrels upstream fingerprint mismatch: {key}")
        clean = {
            "query_id": key[0], "doc_id": key[1], "relevance": row.get("relevance"),
            "target_domain": row.get("target_domain"), "mechanism": row.get("mechanism"),
            "reason": row.get("reason"), "judge_model": row.get("judge_model"),
            "judgment_source": "seed_qrels", "schema_version": OUTPUT_SCHEMA, **metadata,
        }
        validate_judgment_row(clean, allowed, metadata)
        completed[key] = clean
    return completed


def load_resume(
    path: Path, allowed: set[tuple[str, str]], metadata: dict[str, str], provider_model: str,
) -> dict[tuple[str, str], dict[str, Any]]:
    completed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in read_jsonl(path):
        key = validate_judgment_row(row, allowed, metadata)
        if key in completed:
            raise ValueError(f"resume has duplicate candidate: {key}")
        if row["judgment_source"] == "provider" and row["judge_model"] != provider_model:
            raise ValueError(f"resume provider model mismatch: {key}")
        completed[key] = row
    return completed


def atomic_write(path: Path, rows: list[dict[str, Any]]) -> None:
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


def judge_pool(
    pool: list[dict[str, Any]], metadata: dict[str, str], completed: dict[tuple[str, str], dict[str, Any]],
    *, model: str, provider: Callable[[list[dict[str, Any]]], dict[str, Any]],
    output: Path, retries: int = 3, sleep: Callable[[float], None] = time.sleep,
) -> dict[tuple[str, str], dict[str, Any]]:
    allowed = {(query["query_id"], candidate["doc_id"]) for query in pool for candidate in query["candidates"]}
    if not set(completed) <= allowed:
        raise ValueError("completed judgments violate candidate allowlist")
    for query in pool:  # batch-size is deliberately one query
        missing = [candidate for candidate in query["candidates"] if (query["query_id"], candidate["doc_id"]) not in completed]
        if not missing:
            continue
        batch = [{
            "query_id": query["query_id"], "language": "en", "query": query["query"],
            "candidates": missing,
        }]
        for attempt in range(1, retries + 1):
            try:
                clean = validate_batch(provider(batch), batch)
                for row in clean:
                    enriched = {
                        **row, "judge_model": model, "judgment_source": "provider",
                        "schema_version": OUTPUT_SCHEMA, **metadata,
                    }
                    key = validate_judgment_row(enriched, allowed, metadata)
                    completed[key] = enriched
                break
            except Exception as exc:
                if attempt == retries:
                    raise RuntimeError(f"query {query['query_id']} failed after {retries} attempts: {exc}") from exc
                sleep(attempt * 2)
        atomic_write(output, sorted(completed.values(), key=lambda row: (row["query_id"], row["doc_id"])))
    missing_all = allowed - set(completed)
    if missing_all:
        raise ValueError(f"output is missing {len(missing_all)} judgments")
    return completed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", type=Path, default=DEFAULT_POOL)
    parser.add_argument("--kb", type=Path, default=DEFAULT_KB)
    parser.add_argument("--seed-qrels", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-base", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.batch_size != 1:
        parser.error("--batch-size must be 1 so each request contains one query")
    pool, fingerprints = load_pool(args.pool, args.kb)
    metadata = output_metadata(args.pool, fingerprints)
    allowed = {(query["query_id"], candidate["doc_id"]) for query in pool for candidate in query["candidates"]}
    completed = load_seed(args.seed_qrels, allowed, metadata)
    if args.resume and args.output.exists():
        resumed = load_resume(args.output, allowed, metadata, args.model)
        for key, row in resumed.items():
            if key in completed and completed[key] != row:
                raise ValueError(f"resume conflicts with seed qrels: {key}")
            completed[key] = row
    api_key = os.getenv(args.api_key_env)
    if len(completed) < len(allowed) and not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")
    def provider(batch: list[dict[str, Any]]) -> dict[str, Any]:
        return call_provider(api_key, args.model, batch, args.timeout, args.api_base)  # type: ignore[arg-type]
    judge_pool(pool, metadata, completed, model=args.model, provider=provider, output=args.output)
    print(f"wrote {len(completed)} qrels to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
