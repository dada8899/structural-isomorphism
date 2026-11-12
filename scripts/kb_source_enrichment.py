#!/usr/bin/env python3
"""Offline queue and review merge for human KB source enrichment."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KB = ROOT / "data/kb-expanded.jsonl"
BUNDLE_SCHEMA = "kb-source-enrichment-bundle-v1"
REVIEW_SCHEMA = "kb-source-review-v1"
PROVENANCE = {"real", "synthetic", "literature-derived", "manual-coded", "model-generated", "demo"}
LICENSES = {"CC-BY-4.0", "CC0-1.0", "public-domain", "MIT", "source-specific"}
REVIEW_STATUSES = {"accepted", "rejected", "insufficient"}
URL = re.compile(r"^https://[^\s]+$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REVIEWER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def description_hash(row: dict[str, Any]) -> str:
    return sha256_bytes(row["description"].strip().encode("utf-8"))


def _strict_json(value: str) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = item
        return result

    def nonfinite(value: str) -> None:
        raise ValueError(f"non-finite JSON number: {value}")

    return json.loads(value, object_pairs_hook=pairs, parse_constant=nonfinite)


def _regular_input(path: Path) -> None:
    if _has_symlink_component(path) or not path.is_file():
        raise ValueError(f"input must be a regular non-symlink file: {path}")


def _has_symlink_component(path: Path) -> bool:
    current = path.absolute()
    return any(part.is_symlink() for part in (current, *current.parents))


def read_json(path: Path) -> Any:
    _regular_input(path)
    return _strict_json(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    _regular_input(path)
    return [_strict_json(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def atomic_json(path: Path, value: Any, *, jsonl: bool = False, overwrite: bool = False) -> None:
    if _has_symlink_component(path):
        raise ValueError(f"refusing symlink output: {path}")
    if path.exists() and not overwrite:
        raise FileExistsError(f"output exists; pass --overwrite to replace: {path}")
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
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def priority_score(row: dict[str, Any]) -> int:
    text = f"{row['name']} {row['description']}"
    score = min(len(row["description"]) // 80, 3)
    score += 3 if re.search(r"\d|百分|约|大约|通常|始终|严格|证明|导致|驱动|遵循", text) else 0
    score += 2 if re.search(r"金融|医疗|军事|政策|气候|神经|生物|投资|风险", row["domain"] + text) else 0
    score += 1 if re.search(r"临界|普适|因果|预测|机制|定律", text) else 0
    return score


def task_id(kb_sha: str, row: dict[str, Any]) -> str:
    payload = f"{kb_sha}\0{row['id']}\0{description_hash(row)}".encode()
    return "kbs_" + sha256_bytes(payload)[:24]


def review_fingerprint(bundle: dict[str, Any]) -> str:
    canonical = json.dumps(
        bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return sha256_bytes(canonical)


def load_kb(path: Path) -> list[dict[str, Any]]:
    rows = read_jsonl(path)
    required = {"id", "name", "domain", "type_id", "description"}
    seen = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError(f"KB row {index} schema mismatch")
        if row["id"] in seen or not all(isinstance(row[key], str) and row[key].strip() for key in required):
            raise ValueError(f"KB row {index} invalid or duplicate")
        seen.add(row["id"])
    return rows


def build_bundle(kb_path: Path = DEFAULT_KB, *, batch_size: int = 100) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    rows = load_kb(kb_path)
    kb_sha = sha256_file(kb_path)
    ordered = sorted(rows, key=lambda row: (-priority_score(row), row["type_id"], row["domain"], row["id"]))
    selected = ordered[: min(batch_size, len(ordered))]
    tasks = [{
        "task_id": task_id(kb_sha, row), "kb_id": row["id"], "name": row["name"],
        "domain": row["domain"], "type_id": row["type_id"], "description": row["description"],
        "description_sha256": description_hash(row), "priority_score": priority_score(row),
        "required_review_fields": [
            "source_url", "citation", "license", "provenance_class", "source_review",
            "reviewer_id", "reviewed_at", "note"
        ],
    } for row in selected]
    bundle = {
        "schema_version": BUNDLE_SCHEMA,
        "metadata": {"kb_sha256": kb_sha, "kb_row_count": len(rows), "selection": "risk-priority-v1"},
        "task_count": len(tasks), "tasks": tasks,
        "instructions": {
            "no_automation": "Do not generate or infer sources. Inspect the source manually.",
            "accepted": "Accepted requires an HTTPS source URL, complete citation, license, and provenance class.",
            "insufficient": "Use insufficient with null source fields when no defensible source can be established."
        },
    }
    bundle["metadata"]["review_fingerprint"] = review_fingerprint(bundle)
    return bundle


def validate_bundle(bundle: dict[str, Any], kb_path: Path = DEFAULT_KB) -> dict[str, dict[str, Any]]:
    expected = build_bundle(kb_path, batch_size=bundle.get("task_count", 0))
    if bundle != expected:
        raise ValueError("source enrichment bundle drift or fingerprint mismatch")
    return {task["task_id"]: task for task in bundle["tasks"]}


def _valid_date(value: Any) -> bool:
    if not isinstance(value, str) or not DATE.fullmatch(value):
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed <= date.today()


def _valid_source_url(value: Any) -> bool:
    if not isinstance(value, str) or not URL.fullmatch(value):
        return False
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https" and parsed.hostname and not parsed.username
        and not parsed.password and not parsed.fragment
    )


def validate_reviews(
    rows: list[dict[str, Any]], bundle: dict[str, Any], *, require_complete: bool = False
) -> list[dict[str, Any]]:
    tasks = {task["task_id"]: task for task in bundle["tasks"]}
    expected_fields = {
        "schema_version", "task_id", "kb_id", "description_sha256", "bundle_fingerprint",
        "reviewer_id", "reviewed_at", "source_review", "source_url", "citation",
        "license", "provenance_class", "note",
    }
    clean, seen, reviewers = [], set(), set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != expected_fields or row.get("schema_version") != REVIEW_SCHEMA:
            raise ValueError("source review schema mismatch")
        task = tasks.get(row.get("task_id"))
        if task is None or row["task_id"] in seen:
            raise ValueError("unknown or duplicate source review task")
        if row.get("bundle_fingerprint") != bundle["metadata"]["review_fingerprint"]:
            raise ValueError("source review bundle fingerprint mismatch")
        if row.get("kb_id") != task["kb_id"] or row.get("description_sha256") != task["description_sha256"]:
            raise ValueError("source review content hash or identity mismatch")
        reviewer = row.get("reviewer_id")
        if not isinstance(reviewer, str) or not REVIEWER_ID.fullmatch(reviewer):
            raise ValueError("invalid reviewer_id")
        if not _valid_date(row.get("reviewed_at")):
            raise ValueError("reviewed_at must be a valid non-future YYYY-MM-DD")
        status = row.get("source_review")
        if status not in REVIEW_STATUSES:
            raise ValueError("invalid source_review")
        note = row.get("note")
        if not isinstance(note, str) or not note.strip() or len(note) > 2000:
            raise ValueError("invalid source review note")
        if status == "accepted":
            if not _valid_source_url(row.get("source_url")):
                raise ValueError("accepted source review requires an HTTPS source_url")
            if not isinstance(row.get("citation"), str) or len(row["citation"].strip()) < 20:
                raise ValueError("accepted source review requires a complete citation")
            if row.get("license") not in LICENSES or row.get("provenance_class") not in PROVENANCE:
                raise ValueError("accepted source review requires allowed license/provenance")
        else:
            if any(row.get(key) is not None for key in ("source_url", "citation", "license", "provenance_class")):
                raise ValueError("rejected/insufficient review must not retain source claims")
            if not note.strip():
                raise ValueError("rejected/insufficient review requires a reason")
        seen.add(row["task_id"]); reviewers.add(reviewer); clean.append(row)
    if len(reviewers) > 1:
        raise ValueError("one review file must contain exactly one reviewer_id")
    if require_complete and seen != set(tasks):
        raise ValueError(f"source reviews missing {len(set(tasks) - seen)} tasks")
    return sorted(clean, key=lambda row: row["task_id"])


def review_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(row.get(key) for key in (
        "source_review", "source_url", "citation", "license", "provenance_class", "note"
    ))


def merge_reviews(files: Iterable[Path], bundle: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reviewer_ids = set()
    for path in files:
        values = validate_reviews(read_jsonl(path), bundle)
        if not values:
            raise ValueError(f"empty source review file: {path}")
        reviewer = values[0]["reviewer_id"]
        if reviewer in reviewer_ids:
            raise ValueError(f"duplicate reviewer file: {reviewer}")
        reviewer_ids.add(reviewer)
        for row in values:
            by_task[row["task_id"]].append(row)
    merged, conflicts = [], []
    for task in bundle["tasks"]:
        votes = by_task.get(task["task_id"], [])
        counts = Counter(review_signature(row) for row in votes)
        consensus_signature = None
        # Evidence review is unanimous, not majority voting: any dissenting
        # status, source field or scope note keeps the task in conflict.
        if len(votes) >= 2 and len(counts) == 1:
            consensus_signature = next(iter(counts))
        accepted = consensus_signature is not None and consensus_signature[0] == "accepted"
        item = {
            "task_id": task["task_id"], "kb_id": task["kb_id"],
            "description_sha256": task["description_sha256"], "review_count": len(votes),
            "consensus": accepted, "evidence_level": "source_backed" if accepted else "candidate",
        }
        if accepted:
            item.update(dict(zip(
                ("source_review", "source_url", "citation", "license", "provenance_class", "note"),
                consensus_signature,
            )))
            item["reviewers"] = sorted(
                row["reviewer_id"] for row in votes
                if review_signature(row) == consensus_signature
            )
        merged.append(item)
        if votes and not accepted:
            conflicts.append({
                **item, "name": task["name"], "domain": task["domain"],
                "reviews": [{key: row[key] for key in (
                    "reviewer_id", "reviewed_at", "source_review", "source_url", "citation",
                    "license", "provenance_class", "note"
                )} for row in votes],
            })
    status_counts = Counter(
        "source_backed" if item["consensus"] else
        ("conflict_or_insufficient" if item["review_count"] else "unreviewed")
        for item in merged
    )
    report = {
        "schema_version": "kb-source-enrichment-progress-v1",
        "task_count": len(bundle["tasks"]), "reviewers": sorted(reviewer_ids),
        "reviewed_task_count": sum(bool(item["review_count"]) for item in merged),
        "source_backed_count": status_counts["source_backed"],
        "conflict_or_insufficient_count": status_counts["conflict_or_insufficient"],
        "unreviewed_count": status_counts["unreviewed"],
        "conflict_queue_count": len(conflicts),
    }
    return merged, conflicts, report


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--kb", type=Path, default=DEFAULT_KB)
    build.add_argument("--batch-size", type=int, default=100)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--overwrite", action="store_true")
    validate = sub.add_parser("validate")
    validate.add_argument("--kb", type=Path, default=DEFAULT_KB)
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--require-complete", action="store_true")
    merge = sub.add_parser("merge")
    merge.add_argument("--kb", type=Path, default=DEFAULT_KB)
    merge.add_argument("--bundle", type=Path, required=True)
    merge.add_argument("--input", type=Path, nargs="+", required=True)
    merge.add_argument("--output", type=Path, required=True)
    merge.add_argument("--conflicts", type=Path, required=True)
    merge.add_argument("--report", type=Path, required=True)
    merge.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    if args.command == "build":
        bundle = build_bundle(args.kb, batch_size=args.batch_size)
        atomic_json(args.output, bundle, overwrite=args.overwrite)
        print(f"wrote {bundle['task_count']} source-enrichment tasks")
        return 0
    bundle = read_json(args.bundle)
    validate_bundle(bundle, args.kb)
    if args.command == "validate":
        rows = validate_reviews(read_jsonl(args.input), bundle, require_complete=args.require_complete)
        print(f"valid: {len(rows)} source reviews")
    else:
        outputs = (args.output, args.conflicts, args.report)
        if len({path.resolve(strict=False) for path in outputs}) != len(outputs):
            raise ValueError("merge outputs must be distinct")
        for path in outputs:
            if _has_symlink_component(path):
                raise ValueError(f"refusing symlink output: {path}")
            if path.exists() and not args.overwrite:
                raise FileExistsError(f"output exists; pass --overwrite to replace: {path}")
        merged, conflicts, report = merge_reviews(args.input, bundle)
        atomic_json(args.output, merged, jsonl=True, overwrite=args.overwrite)
        atomic_json(args.conflicts, conflicts, jsonl=True, overwrite=args.overwrite)
        atomic_json(args.report, report, overwrite=args.overwrite)
        print(f"source-backed={report['source_backed_count']} conflicts={report['conflict_queue_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
