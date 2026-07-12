#!/usr/bin/env python3
"""Validate and aggregate evidence-bound simulated-user judgments.

The default mode is offline. This script never calls a model provider and never
reads application data; provider adapters must produce the same frozen JSONL
contract in a separate, explicitly authorised step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STAGES = ("input", "processing", "result", "action", "recovery")
VERDICTS = {"pass", "fail", "abstain"}
REQUIRED_LISTS = ("positive_value", "negative_value", "applicability", "failure_conditions")
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
LOCATOR_PATTERN = re.compile(r"^artifact://[A-Za-z0-9._/-]+#[A-Za-z0-9._:-]+$")


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _loads(raw: str, label: str) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_no_duplicate_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {value}")),
        )
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is invalid JSON: {exc.msg}") from exc


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _nonempty_strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in value):
        raise ValueError(f"{label} contains an invalid string")
    return value


def load_json(path: Path) -> dict[str, Any]:
    return _object(_loads(path.read_text(encoding="utf-8"), str(path)), str(path))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(_object(_loads(line, f"line {line_number}"), f"line {line_number}"))
        except ValueError as exc:
            raise ValueError(f"line {line_number}: {exc}") from exc
    if not rows:
        raise ValueError("judgment file is empty")
    return rows


def validate_config(config: dict[str, Any]) -> None:
    if config.get("schema_version") != "journey-eval-config-v1":
        raise ValueError("config schema mismatch")
    weights = _object(config.get("stage_weights"), "stage_weights")
    if set(weights) != set(STAGES) or any(
        type(v) not in (int, float) or not math.isfinite(v) or v <= 0 for v in weights.values()
    ):
        raise ValueError("stage_weights must contain five positive numeric weights")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("stage_weights must sum to 1")
    for field in ("roles", "tasks"):
        values = config.get(field)
        if not isinstance(values, list) or not values:
            raise ValueError(f"{field} must be a non-empty list")
        ids = [item.get("id") for item in values if isinstance(item, dict)]
        if len(ids) != len(values) or any(not isinstance(item, str) or not ID_PATTERN.fullmatch(item) for item in ids) or len(set(ids)) != len(ids):
            raise ValueError(f"{field} ids must be unique non-empty strings")
    for role in config["roles"]:
        if set(role) != {"id", "label"} or not isinstance(role["label"], str) or not role["label"].strip():
            raise ValueError("roles require exactly id and label")
    for task in config["tasks"]:
        if set(task) != {"id", "prompt", "success_conditions", "failure_conditions"}:
            raise ValueError("tasks have invalid fields")
        if not isinstance(task["prompt"], str) or not task["prompt"].strip() or len(task["prompt"]) > 4000:
            raise ValueError("task prompt is invalid")
        _nonempty_strings(task["success_conditions"], "task.success_conditions")
        _nonempty_strings(task["failure_conditions"], "task.failure_conditions")
    if type(config.get("required_models")) is not int or config["required_models"] < 2:
        raise ValueError("required_models must be at least 2")
    if type(config.get("minimum_stage_score")) is not int or not 0 <= config["minimum_stage_score"] <= 100:
        raise ValueError("minimum_stage_score must be an integer in [0,100]")
    if type(config.get("require_distinct_model_families")) is not bool:
        raise ValueError("require_distinct_model_families must be boolean")
    models = config.get("allowed_models")
    if not isinstance(models, list) or len(models) != config["required_models"]:
        raise ValueError("allowed_models must register exactly required_models judges")
    identities = set()
    for model in models:
        model = _object(model, "allowed_models item")
        if set(model) != {"provider", "family", "name"}:
            raise ValueError("allowed_models entries require provider, family, and name")
        if any(not isinstance(value, str) or not ID_PATTERN.fullmatch(value) for value in model.values()):
            raise ValueError("allowed_models contains an invalid identifier")
        identity = (model["provider"], model["family"], model["name"])
        if identity in identities:
            raise ValueError("allowed_models contains a duplicate")
        identities.add(identity)


def validate_row(row: dict[str, Any], config: dict[str, Any]) -> None:
    allowed = {"schema_version", "run_id", "task_id", "role_id", "model", "stages", *REQUIRED_LISTS, "verdict"}
    if set(row) != allowed:
        raise ValueError(f"judgment fields mismatch: missing={sorted(allowed-set(row))}, extra={sorted(set(row)-allowed)}")
    if row["schema_version"] != "journey-judgment-v1":
        raise ValueError("judgment schema mismatch")
    for field in ("run_id", "task_id", "role_id"):
        if not isinstance(row[field], str) or not ID_PATTERN.fullmatch(row[field]):
            raise ValueError(f"{field} is required")
    if row["task_id"] not in {item["id"] for item in config["tasks"]}:
        raise ValueError(f"unknown task_id: {row['task_id']}")
    if row["role_id"] not in {item["id"] for item in config["roles"]}:
        raise ValueError(f"unknown role_id: {row['role_id']}")
    model = _object(row["model"], "model")
    if set(model) != {"provider", "family", "name"} or any(not isinstance(v, str) or not ID_PATTERN.fullmatch(v) for v in model.values()):
        raise ValueError("model requires provider, family, and name")
    if model not in config["allowed_models"]:
        raise ValueError("model is not in the frozen allowed_models registry")
    stages = _object(row["stages"], "stages")
    if set(stages) != set(STAGES):
        raise ValueError("stages must contain exactly the five journey stages")
    for stage_name, stage in stages.items():
        stage = _object(stage, stage_name)
        if set(stage) != {"score", "evidence"}:
            raise ValueError(f"{stage_name} fields mismatch")
        if type(stage["score"]) is not int or not 0 <= stage["score"] <= 100:
            raise ValueError(f"{stage_name}.score must be an integer in [0,100]")
        evidence = _nonempty_strings(stage["evidence"], f"{stage_name}.evidence")
        if any(not LOCATOR_PATTERN.fullmatch(item) or ".." in item for item in evidence):
            raise ValueError(f"{stage_name}.evidence must use a safe artifact locator with fragment")
    for field in REQUIRED_LISTS:
        _nonempty_strings(row[field], field)
    if row["verdict"] not in VERDICTS:
        raise ValueError("verdict must be pass, fail, or abstain")
    if row["verdict"] == "pass" and any(stage["score"] < config["minimum_stage_score"] for stage in stages.values()):
        raise ValueError("pass verdict conflicts with a stage below the configured floor")


def aggregate(rows: list[dict[str, Any]], config: dict[str, Any], *, require_complete: bool = True) -> dict[str, Any]:
    for row in rows:
        validate_row(row, config)
    keys: set[tuple[str, str, str]] = set()
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        model_id = f"{row['model']['provider']}:{row['model']['name']}"
        key = (row["task_id"], row["role_id"], model_id)
        if key in keys:
            raise ValueError(f"duplicate judgment: {key}")
        keys.add(key)
        grouped.setdefault((row["task_id"], row["role_id"]), []).append(row)
    if len({row["run_id"] for row in rows}) != 1:
        raise ValueError("judgments must belong to exactly one run_id")
    expected = {(task["id"], role["id"]) for task in config["tasks"] for role in config["roles"]}
    if require_complete and set(grouped) != expected:
        missing = sorted(expected - set(grouped))
        raise ValueError(f"incomplete role/task matrix: missing={missing}")
    required_panel = {
        (model["provider"], model["family"], model["name"]) for model in config["allowed_models"]
    }
    reports = []
    for (task_id, role_id), judgments in sorted(grouped.items()):
        if len(judgments) < config["required_models"]:
            raise ValueError(f"insufficient models for {(task_id, role_id)}")
        panel = {(row["model"]["provider"], row["model"]["family"], row["model"]["name"]) for row in judgments}
        if panel != required_panel:
            raise ValueError(f"judge panel mismatch for {(task_id, role_id)}")
        families = {row["model"]["family"] for row in judgments}
        if config.get("require_distinct_model_families") and len(families) < 2:
            raise ValueError(f"model families are not heterogeneous for {(task_id, role_id)}")
        stage_report = {}
        for stage in STAGES:
            scores = [row["stages"][stage]["score"] for row in judgments]
            stage_report[stage] = {
                "mean": round(statistics.mean(scores), 2),
                "variance": round(statistics.pvariance(scores), 2),
                "range": max(scores) - min(scores),
            }
        weighted = sum(stage_report[s]["mean"] * config["stage_weights"][s] for s in STAGES)
        verdicts = [row["verdict"] for row in judgments]
        majority_count = max(verdicts.count(v) for v in set(verdicts))
        hard_fail = any(stage_report[s]["mean"] < config["minimum_stage_score"] for s in STAGES)
        reports.append({
            "task_id": task_id, "role_id": role_id, "model_families": sorted(families),
            "stage_scores": stage_report, "weighted_score": round(weighted, 2),
            "verdict_agreement": round(majority_count / len(verdicts), 3),
            "status": "fail" if hard_fail or any(verdict != "pass" for verdict in verdicts) else "pass",
        })
    config_digest = hashlib.sha256(
        json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "journey-eval-report-v1",
        "run_id": rows[0]["run_id"],
        "config_sha256": config_digest,
        "groups": reports,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "evaluation/journeys/config-v1.json")
    parser.add_argument("--judgments", type=Path, default=ROOT / "evaluation/journeys/offline-fixture-v1.jsonl")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--allow-partial", action="store_true", help="Contract debugging only; never a release gate")
    args = parser.parse_args()
    config = load_json(args.config)
    validate_config(config)
    report = aggregate(load_jsonl(args.judgments), config, require_complete=not args.allow_partial)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
