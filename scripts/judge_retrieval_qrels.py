#!/usr/bin/env python3
"""Create guarded graded qrels for a frozen retrieval result pool.

This script never accepts free-form model output into the benchmark. Every
judgment is checked against the exact query/document allow-list and a strict
0..3 relevance scale before being written.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evaluation" / "retrieval-v1.jsonl"
DEFAULT_RESULTS = ROOT / "evaluation" / "results" / "retrieval-v1-local-baseline.json"
DEFAULT_OUTPUT = ROOT / "evaluation" / "qrels-v1.jsonl"
DEFAULT_MODEL = "anthropic/claude-opus-4.8"

SYSTEM = """You are an independent retrieval relevance assessor for a cross-domain
structural analogy search engine. Judge whether each candidate document shares
the query's causal or mathematical structure, not merely words or topic.

Relevance scale:
3 = strong transferable structural match; same mechanism/equations and useful
2 = meaningful partial structural match; defensible transfer with caveats
1 = topical or surface analogy only; not enough for a transfer recommendation
0 = irrelevant, contradictory, or forced

Return strict JSON only: {"judgments":[{"query_id":"...","doc_id":"...",
"relevance":0,"target_domain":"...","mechanism":"...","reason":"..."}]}.
Do not invent query_id or doc_id. Keep reason under 35 words."""


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_pool(dataset: Path, results: Path, kb_path: Path) -> list[dict[str, Any]]:
    rows = {row["id"]: row for row in read_jsonl(dataset)}
    report = json.loads(results.read_text(encoding="utf-8"))
    kb = {item["id"]: item for item in read_jsonl(kb_path)}
    pool: list[dict[str, Any]] = []
    for outcome in report["outcomes"]:
        row = rows[outcome["id"]]
        if row["labels"]["out_of_scope"]:
            continue
        candidates = []
        for doc_id in outcome["top_ids"]:
            item = kb.get(doc_id)
            if not item:
                raise ValueError(f"unknown KB id in result pool: {doc_id}")
            candidates.append({
                "doc_id": doc_id,
                "name": item.get("name", ""),
                "domain": item.get("domain", ""),
                "description": item.get("description", "")[:900],
            })
        pool.append({
            "query_id": row["id"],
            "language": row["language"],
            "query": row["query"],
            "candidates": candidates,
        })
    return pool


def call_provider(api_key: str, model: str, batch: list[dict], timeout: float, api_base: str) -> dict:
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps({"queries": batch}, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
    }).encode()
    request = urllib.request.Request(
        f"{api_base.rstrip('/')}/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"provider HTTP {exc.code}: {detail}") from exc
    content = body.get("choices", [{}])[0].get("message", {}).get("content")
    if not isinstance(content, str):
        raise ValueError("model response has no text content")
    return json.loads(content)


def validate_batch(raw: dict, batch: list[dict]) -> list[dict]:
    allowed = {
        (query["query_id"], candidate["doc_id"])
        for query in batch
        for candidate in query["candidates"]
    }
    judgments = raw.get("judgments") if isinstance(raw, dict) else None
    if not isinstance(judgments, list):
        raise ValueError("judgments must be a list")
    seen: set[tuple[str, str]] = set()
    clean: list[dict] = []
    for item in judgments:
        if not isinstance(item, dict):
            raise ValueError("judgment must be an object")
        key = (item.get("query_id"), item.get("doc_id"))
        if key not in allowed or key in seen:
            raise ValueError(f"unknown or duplicate judgment key: {key}")
        relevance = item.get("relevance")
        if type(relevance) is not int or relevance not in {0, 1, 2, 3}:
            raise ValueError(f"invalid relevance for {key}")
        for field in ("target_domain", "mechanism", "reason"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 500:
                raise ValueError(f"invalid {field} for {key}")
        clean.append({
            "query_id": key[0],
            "doc_id": key[1],
            "relevance": relevance,
            "target_domain": item["target_domain"].strip(),
            "mechanism": item["mechanism"].strip(),
            "reason": item["reason"].strip(),
        })
        seen.add(key)
    missing = allowed - seen
    if missing:
        raise ValueError(f"missing {len(missing)} judgments")
    return sorted(clean, key=lambda row: (row["query_id"], row["doc_id"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--kb", type=Path, default=ROOT / "data" / "kb-expanded.jsonl")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-base", default="https://openrouter.ai/api/v1")
    parser.add_argument("--api-key-env", default="OPENROUTER_API_KEY")
    parser.add_argument("--batch-size", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=180.0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--start-index", type=int, default=0)
    parser.add_argument("--end-index", type=int)
    args = parser.parse_args()
    api_key = os.getenv(args.api_key_env)
    if not api_key:
        raise SystemExit(f"{args.api_key_env} is not set")
    full_pool = build_pool(args.dataset, args.results, args.kb)
    end_index = len(full_pool) if args.end_index is None else args.end_index
    if args.start_index < 0 or end_index > len(full_pool) or args.start_index >= end_index:
        raise ValueError("invalid pool slice")
    pool = full_pool[args.start_index:end_index]
    fingerprints = {
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "results_sha256": hashlib.sha256(args.results.read_bytes()).hexdigest(),
        "kb_sha256": hashlib.sha256(args.kb.read_bytes()).hexdigest(),
    }
    allowed_all = {
        (query["query_id"], candidate["doc_id"])
        for query in pool for candidate in query["candidates"]
    }
    completed: dict[tuple[str, str], dict] = {}
    if args.resume and args.output.exists():
        for row in read_jsonl(args.output):
            key = (row.get("query_id"), row.get("doc_id"))
            if key not in allowed_all or key in completed:
                raise ValueError(f"resume file has unknown or duplicate key: {key}")
            if row.get("judge_model") != args.model or any(
                row.get(name) != value for name, value in fingerprints.items()
            ):
                raise ValueError("resume file model or input fingerprint mismatch")
            if row.get("schema_version") != "qrels-v1":
                raise ValueError(f"resume file has invalid schema version: {key}")
            if type(row.get("relevance")) is not int or row["relevance"] not in {0, 1, 2, 3}:
                raise ValueError(f"resume file has invalid relevance: {key}")
            for field in ("target_domain", "mechanism", "reason"):
                value = row.get(field)
                if not isinstance(value, str) or not value.strip() or len(value) > 500:
                    raise ValueError(f"resume file has invalid {field}: {key}")
            completed[key] = row
    for start in range(0, len(pool), args.batch_size):
        batch = pool[start:start + args.batch_size]
        needed = {
            (query["query_id"], candidate["doc_id"])
            for query in batch for candidate in query["candidates"]
        }
        if needed and needed <= completed.keys():
            continue
        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                clean = validate_batch(
                    call_provider(api_key, args.model, batch, args.timeout, args.api_base), batch
                )
                for row in clean:
                    row["judge_model"] = args.model
                    row["schema_version"] = "qrels-v1"
                    row.update(fingerprints)
                    completed[(row["query_id"], row["doc_id"])] = row
                break
            except Exception as exc:
                last_error = exc
                if attempt == 3:
                    raise RuntimeError(f"batch {start} failed after 3 attempts: {exc}") from exc
                time.sleep(attempt * 2)
        assert last_error is None or needed <= completed.keys()
        ordered = sorted(completed.values(), key=lambda row: (row["query_id"], row["doc_id"]))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(
            "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in ordered),
            encoding="utf-8",
        )
        temporary.replace(args.output)
        print(
            f"judged {args.start_index + min(start + len(batch), len(pool))}/"
            f"{args.start_index + len(pool)} queries"
        )
    print(f"wrote {len(completed)} qrels to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
