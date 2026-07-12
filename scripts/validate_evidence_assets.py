#!/usr/bin/env python3
"""Validate evidence ladder, KB vNext migration, and discovery normalization."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
LADDER = ROOT / "evaluation/research/evidence-ladder-v1.json"
KB_SCHEMA = ROOT / "evaluation/research/kb-vnext-schema-v1.json"
KB = ROOT / "data/kb-expanded.jsonl"
DISCOVERIES = ROOT / "web/data/a_discoveries_merged.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_ladder(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if value.get("schema_version") != "evidence-ladder-v1":
        errors.append("evidence ladder schema mismatch")
    levels = value.get("levels")
    expected = ["candidate", "source_backed", "analysis_recorded", "falsification_tested", "externally_reviewed", "replicated"]
    if not isinstance(levels, list) or [item.get("id") for item in levels if isinstance(item, dict)] != expected:
        errors.append("evidence ladder levels/order mismatch")
    elif [item.get("rank") for item in levels] != list(range(1, 7)):
        errors.append("evidence ladder ranks must be 1..6")
    for item in levels or []:
        if not isinstance(item, dict) or set(item) != {"id", "rank", "label_zh", "label_en", "requires"}:
            errors.append("evidence ladder level schema mismatch")
        elif not all(isinstance(item[key], str) and item[key] for key in ("label_zh", "label_en")):
            errors.append("evidence ladder labels must be bilingual")
    prohibited = value.get("prohibited_generic_labels")
    if not isinstance(prohibited, list) or not {"verified", "已验证"} <= set(prohibited):
        errors.append("generic verified labels must be prohibited")
    if isinstance(levels, list):
        source_level = next((item for item in levels if item.get("id") == "source_backed"), {})
        if "source_review" not in source_level.get("requires", []):
            errors.append("source-backed evidence requires an auditable source review")
    return errors


def migrate_legacy_kb_row(row: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    legacy_required = {"id", "name", "domain", "type_id", "description"}
    if set(row) != legacy_required or not all(isinstance(row[key], str) and row[key].strip() for key in legacy_required):
        raise ValueError("legacy KB row schema mismatch")
    defaults = schema["unknown_migration"]
    return {**row, **defaults}


def validate_kb_vnext_row(row: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    errors = []
    required = set(schema.get("required", []))
    if not required <= set(row):
        return [f"missing KB vNext fields: {sorted(required - set(row))}"]
    if row.get("language") not in schema["languages"]:
        errors.append("invalid language")
    if row.get("provenance_class") not in schema["provenance_classes"]:
        errors.append("invalid provenance_class")
    if row.get("license") not in schema["licenses"]:
        errors.append("invalid license")
    if row.get("evidence_level") not in {"candidate", "source_backed", "analysis_recorded", "falsification_tested", "externally_reviewed", "replicated"}:
        errors.append("invalid evidence_level")
    if row.get("evidence_level") != "candidate":
        locator = row.get("source", {}).get("locator") if isinstance(row.get("source"), dict) else None
        parsed_locator = urlparse(locator) if isinstance(locator, str) else None
        if not (
            isinstance(locator, str)
            and locator.strip() == locator
            and parsed_locator
            and parsed_locator.scheme == "https"
            and parsed_locator.hostname
            and parsed_locator.username is None
            and parsed_locator.password is None
            and not parsed_locator.fragment
            and re.fullmatch(r"[A-Za-z0-9.-]+", parsed_locator.hostname)
            and all(label and not label.startswith("-") and not label.endswith("-") for label in parsed_locator.hostname.split("."))
            and "." in parsed_locator.hostname
        ):
            errors.append("promoted KB row requires a source locator")
        if row.get("license") == "unknown" or row.get("provenance_class") == "unknown":
            errors.append("promoted KB row cannot retain unknown license/provenance")
        review = row.get("source_review")
        if (
            not isinstance(review, dict)
            or not isinstance(review.get("reviewer"), str)
            or not review["reviewer"].strip()
            or not isinstance(review.get("reviewed_at"), str)
            or not review["reviewed_at"].strip()
        ):
            errors.append("promoted KB row requires an auditable source review")
        elif isinstance(review, dict):
            try:
                reviewed_on = date.fromisoformat(review["reviewed_at"])
                if reviewed_on > date.today():
                    raise ValueError("future review")
            except ValueError:
                errors.append("source review date must be a non-future ISO date")
    level = row.get("evidence_level")
    ladder = read_json(LADDER)
    level_ids = [item["id"] for item in ladder["levels"]]
    if level in level_ids:
        rank = level_ids.index(level)
        requirements = {
            key
            for item in ladder["levels"][: rank + 1]
            for key in item["requires"]
        }
        already_checked = {"source", "license", "provenance_class", "source_review"}
        for key in sorted(requirements - already_checked):
            value = row.get(key)
            valid = isinstance(value, (str, dict, list)) and not isinstance(value, bool)
            if isinstance(value, str):
                valid = bool(value.strip())
            elif isinstance(value, dict):
                valid = bool(value)
            if key == "reviewer_independence":
                valid = value is True
            if key == "independent_team":
                valid = (
                    isinstance(value, dict)
                    and isinstance(value.get("team_name"), str)
                    and bool(value["team_name"].strip())
                    and isinstance(value.get("independence_statement"), str)
                    and bool(value["independence_statement"].strip())
                )
            if not valid:
                errors.append(f"{level} evidence requires valid {key}")
        for key in ("artifact_sha256", "replication_sha256"):
            if key in requirements and row.get(key) and not SHA256.fullmatch(str(row[key])):
                errors.append(f"{key} must be lowercase SHA-256")
        if "verdict" in requirements and row.get("verdict") not in ladder["allowed_verdicts"]:
            errors.append("falsification verdict is invalid")
        structured = {
            "evidence_artifact": ("locator",),
            "preregistered_rule": ("locator", "failure_condition"),
            "counter_evidence": ("search_protocol", "findings"),
            "review_record": ("locator",),
            "resolved_disputes": ("status",),
            "replication_artifact": ("locator",),
        }
        for key, fields in structured.items():
            if key not in requirements:
                continue
            value = row.get(key)
            if not isinstance(value, dict):
                errors.append(f"{key} must be a structured auditable record")
                continue
            for field in fields:
                field_value = value.get(field)
                if key == "counter_evidence" and field == "findings":
                    valid_field = isinstance(field_value, list)
                else:
                    valid_field = isinstance(field_value, str) and bool(field_value.strip())
                if not valid_field:
                    errors.append(f"{key}.{field} must have the required type and value")
        counter = row.get("counter_evidence")
        if "counter_evidence" in requirements and isinstance(counter, dict) and not isinstance(counter.get("findings"), list):
            errors.append("counter_evidence findings must be a list")
        disputes = row.get("resolved_disputes")
        if "resolved_disputes" in requirements and isinstance(disputes, dict) and disputes.get("status") not in {"none", "resolved"}:
            errors.append("resolved_disputes status must be none or resolved")
    return errors


def normalize_variable_mapping(value: Any) -> dict[str, str] | None:
    if isinstance(value, dict):
        cleaned = {
            str(left).strip(): str(right).strip()
            for left, right in value.items()
            if str(left).strip() and str(right).strip()
        }
        return cleaned or None
    if not isinstance(value, str):
        return None
    pairs: dict[str, str] = {}
    notes: list[str] = []
    for item in re.split(r"[;；]", value):
        parts = re.split(r"↔|→|=>", item, maxsplit=1)
        if len(parts) != 2 or not all(part.strip() for part in parts):
            if item.strip():
                notes.append(item.strip())
            continue
        left, right = (part.strip() for part in parts)
        if left in pairs:
            return None
        pairs[left] = right
    if pairs and notes:
        pairs["__unmapped_notes__"] = "；".join(notes)
    return pairs or None


def normalize_discovery(row: dict[str, Any]) -> dict[str, Any]:
    if isinstance(row.get("shared_equations"), list):
        equations = row["shared_equations"]
    elif isinstance(row.get("shared_equation"), str) and row["shared_equation"].strip():
        equations = [row["shared_equation"]]
    else:
        equations = row.get("equations") if isinstance(row.get("equations"), list) else []
    literature = row.get("literature_evidence")
    has_evidence = (
        isinstance(literature, list)
        and bool(literature)
        and all(
            isinstance(item, dict)
            and isinstance(item.get("source"), str)
            and item["source"].strip()
            and item.get("license") not in {None, "", "unknown"}
            and item.get("provenance_class") not in {None, "", "unknown"}
            and isinstance(item.get("source_review"), dict)
            for item in literature
        )
    )
    score = row.get("isomorphism_confidence")
    return {
        "rank": row.get("rank"),
        "shared_equations": [item for item in equations if isinstance(item, str) and item.strip()],
        "variable_mapping": normalize_variable_mapping(row.get("variable_mapping")),
        "model_score_unvalidated": float(score) if isinstance(score, (int, float)) else None,
        "evidence_level": "source_backed" if has_evidence else "candidate",
        "literature_status": row.get("literature_status") if has_evidence else "not_systematically_reviewed",
    }


def validate_repository() -> list[str]:
    errors = validate_ladder(read_json(LADDER))
    schema = read_json(KB_SCHEMA)
    rows = [json.loads(line) for line in KB.read_text(encoding="utf-8").splitlines() if line]
    for index, row in enumerate(rows):
        try:
            migrated = migrate_legacy_kb_row(row, schema)
        except ValueError as exc:
            errors.append(f"KB row {index}: {exc}")
            continue
        row_errors = validate_kb_vnext_row(migrated, schema)
        if row_errors:
            errors.extend(f"KB row {index}: {error}" for error in row_errors)
        defaults = schema["unknown_migration"]
        if any(migrated.get(key) != value for key, value in defaults.items()):
            errors.append(f"KB row {index}: legacy migration fabricated provenance")
    discoveries = read_json(DISCOVERIES).get("discoveries", [])
    normalized = [normalize_discovery(row) for row in discoveries]
    if len(normalized) != 39 or any(not row["shared_equations"] for row in normalized):
        errors.append("all 39 discoveries must normalize to non-empty shared_equations")
    if any(row["evidence_level"] != "candidate" for row in normalized):
        errors.append("discoveries without literature_evidence must remain candidate")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    errors = validate_repository()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("evidence asset contracts: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
