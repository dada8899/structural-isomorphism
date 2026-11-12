#!/usr/bin/env python3
"""Seal and fail-closed validate a Stage 1 benchmark package.

This tool validates benchmark instrumentation. It never runs models, computes
scientific effects, or upgrades synthetic fixtures into scientific evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any


SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
TASK_ID_RE = re.compile(r"^st1_[a-z0-9_-]{3,64}$")
ARM_KINDS = {"baseline", "negative_control", "target", "ablation"}
FATAL_EVENTS = {
    "fabricated_citation", "leakage", "fatal_factual_error",
    "causal_overreach", "protocol_deviation",
}


class ValidationError(ValueError):
    pass


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise ValidationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load_json(path: Path) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs_no_duplicates)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot read JSON {path}: {exc}") from exc
    _reject_nonfinite(value, str(path))
    return value


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ValidationError(f"cannot read JSONL {path}: {exc}") from exc
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            raise ValidationError(f"blank JSONL line: {path}:{line_no}")
        try:
            row = json.loads(line, object_pairs_hook=_pairs_no_duplicates)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValidationError(f"invalid JSONL {path}:{line_no}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValidationError(f"JSONL row must be object: {path}:{line_no}")
        _reject_nonfinite(row, f"{path}:{line_no}")
        rows.append(row)
    if not rows:
        raise ValidationError(f"empty JSONL: {path}")
    return rows


def _reject_nonfinite(value: Any, where: str) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValidationError(f"non-finite number in {where}")
    if isinstance(value, dict):
        for nested in value.values():
            _reject_nonfinite(nested, where)
    elif isinstance(value, list):
        for nested in value:
            _reject_nonfinite(nested, where)


def require_keys(obj: dict[str, Any], required: set[str], allowed: set[str], where: str) -> None:
    missing = required - obj.keys()
    extra = obj.keys() - allowed
    if missing or extra:
        raise ValidationError(f"{where}: missing={sorted(missing)} extra={sorted(extra)}")


def parse_time(raw: Any, where: str) -> datetime:
    if not isinstance(raw, str) or not raw.endswith("Z"):
        raise ValidationError(f"{where}: timestamp must be UTC and end in Z")
    try:
        return datetime.fromisoformat(raw[:-1] + "+00:00")
    except ValueError as exc:
        raise ValidationError(f"{where}: invalid timestamp") from exc


def safe_artifact_path(root: Path, relative: Any) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValidationError("artifact path must be non-empty string")
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts or "\\" in relative:
        raise ValidationError(f"unsafe artifact path: {relative}")
    resolved_root = root.resolve()
    target = resolved_root / pure
    try:
        target.relative_to(resolved_root)
    except ValueError as exc:
        raise ValidationError(f"artifact escapes benchmark root: {relative}") from exc
    current = resolved_root
    for part in pure.parts:
        current = current / part
        if current.is_symlink():
            raise ValidationError(f"artifact path contains symlink: {relative}")
    if not target.is_file():
        raise ValidationError(f"artifact missing or symlinked: {relative}")
    return target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValidationError(f"cannot securely open artifact: {path}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
        after = os.fstat(handle.fileno())
    identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if identity_before != identity_after:
        raise ValidationError(f"artifact changed while hashing: {path}")
    return digest.hexdigest()


def sha256_artifact(root: Path, relative: str) -> str:
    """Hash via no-follow dirfds so parent-directory swaps cannot escape root."""
    pure = PurePosixPath(relative)
    safe_artifact_path(root, relative)
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(root.resolve(), directory_flags)
        descriptors.append(current)
        for part in pure.parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(pure.parts[-1], file_flags, dir_fd=current)
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            digest = hashlib.sha256()
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        identity_before = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
        identity_after = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
        if identity_before != identity_after:
            raise ValidationError(f"artifact changed while hashing: {relative}")
        return digest.hexdigest()
    except OSError as exc:
        raise ValidationError(f"cannot securely hash artifact: {relative}") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def manifest_digest(manifest: dict[str, Any]) -> str:
    payload = dict(manifest)
    payload.pop("immutable_digest", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_problem(row: dict[str, Any]) -> None:
    allowed = {
        "schema_version", "task_id", "evidence_class", "domain", "task_family",
        "t0", "information_boundary", "outcome_release", "contamination",
        "controls", "budget_id", "gold_status",
    }
    require_keys(row, allowed, allowed, "problem")
    if row["schema_version"] != "stage1.problem-package.v1":
        raise ValidationError("problem: unsupported schema_version")
    if not isinstance(row["task_id"], str) or not TASK_ID_RE.fullmatch(row["task_id"]):
        raise ValidationError("problem: invalid task_id")
    if row["evidence_class"] not in {"historical", "synthetic"}:
        raise ValidationError("problem: invalid evidence_class")
    if row["task_family"] not in {"prediction", "experiment_design", "mechanism_discrimination"}:
        raise ValidationError("problem: invalid task_family")
    if not isinstance(row["domain"], str) or not 2 <= len(row["domain"]) <= 80:
        raise ValidationError("problem: invalid domain")
    t0 = parse_time(row["t0"], "problem.t0")

    boundary = row["information_boundary"]
    if not isinstance(boundary, dict):
        raise ValidationError("problem.information_boundary must be object")
    boundary_keys = {"corpus_manifest_id", "latest_allowed_publication_at", "excluded_sources"}
    require_keys(boundary, boundary_keys, boundary_keys, "problem.information_boundary")
    cutoff = parse_time(boundary["latest_allowed_publication_at"], "latest_allowed_publication_at")
    if cutoff >= t0:
        raise ValidationError("information cutoff must precede t0")
    if not isinstance(boundary["corpus_manifest_id"], str) or not boundary["corpus_manifest_id"]:
        raise ValidationError("corpus_manifest_id required")
    if not isinstance(boundary["excluded_sources"], list) or not boundary["excluded_sources"]:
        raise ValidationError("excluded_sources must be non-empty list")
    if any(not isinstance(item, str) or not item for item in boundary["excluded_sources"]) or len(boundary["excluded_sources"]) != len(set(boundary["excluded_sources"])):
        raise ValidationError("excluded_sources must contain unique non-empty strings")

    outcome = row["outcome_release"]
    if not isinstance(outcome, dict):
        raise ValidationError("outcome_release must be object")
    outcome_keys = {"available_after_t0", "sealed_locator", "sealed_sha256"}
    require_keys(outcome, outcome_keys, outcome_keys, "problem.outcome_release")
    if parse_time(outcome["available_after_t0"], "available_after_t0") <= t0:
        raise ValidationError("outcome must become available after t0")
    if not isinstance(outcome["sealed_locator"], str) or not outcome["sealed_locator"]:
        raise ValidationError("sealed_locator required")
    if outcome["sealed_locator"] not in boundary["excluded_sources"]:
        raise ValidationError("sealed outcome must be explicitly excluded from available sources")
    if not isinstance(outcome["sealed_sha256"], str) or not SHA256_RE.fullmatch(outcome["sealed_sha256"]):
        raise ValidationError("invalid sealed outcome digest")

    contamination = row["contamination"]
    contamination_keys = {"near_duplicate_check", "target_revealing_text_check", "model_probe_status", "reviewed_by"}
    if not isinstance(contamination, dict):
        raise ValidationError("contamination must be object")
    require_keys(contamination, contamination_keys, contamination_keys, "problem.contamination")
    if contamination["near_duplicate_check"] != "pass" or contamination["target_revealing_text_check"] != "pass":
        raise ValidationError("problem fails mandatory contamination checks")
    if contamination["model_probe_status"] not in {"pass", "fail", "inconclusive", "not_run"}:
        raise ValidationError("invalid model_probe_status")
    if not isinstance(contamination["reviewed_by"], list) or not contamination["reviewed_by"]:
        raise ValidationError("contamination review attribution required")
    if any(not isinstance(item, str) or not item for item in contamination["reviewed_by"]) or len(contamination["reviewed_by"]) != len(set(contamination["reviewed_by"])):
        raise ValidationError("contamination reviewers must be unique non-empty strings")

    controls = row["controls"]
    control_keys = {"matched_non_isomorph", "synthetic_null", "random_candidate"}
    if not isinstance(controls, dict):
        raise ValidationError("controls must be object")
    require_keys(controls, control_keys, control_keys, "problem.controls")
    if any(type(controls[key]) is not bool for key in control_keys):
        raise ValidationError("control flags must be booleans")
    if not controls["matched_non_isomorph"]:
        raise ValidationError("matched non-isomorph is mandatory")
    if not isinstance(row["budget_id"], str) or not row["budget_id"].startswith("budget_"):
        raise ValidationError("invalid budget_id")
    if row["gold_status"] not in {"sealed", "adjudicated"}:
        raise ValidationError("invalid gold_status")


def validate_result(row: dict[str, Any], arm_ids: set[str], budgets: dict[str, dict[str, Any]], task_budget: str) -> None:
    keys = {"schema_version", "run_id", "task_id", "arm_id", "output_artifact", "budget_usage", "terminal_status", "fatal_events", "vfu"}
    require_keys(row, keys, keys, "result")
    if row["schema_version"] != "stage1.run-result.v1" or row["arm_id"] not in arm_ids:
        raise ValidationError("result: unsupported schema or unknown arm")
    if not isinstance(row["run_id"], str) or not re.fullmatch(r"run_[a-z0-9_-]{4,96}", row["run_id"]):
        raise ValidationError("result: invalid run_id")
    if not isinstance(row["task_id"], str) or not TASK_ID_RE.fullmatch(row["task_id"]):
        raise ValidationError("result: invalid task_id")
    if row["terminal_status"] not in {"completed", "abstained", "error", "budget_exceeded"}:
        raise ValidationError("result: invalid terminal status")
    if not isinstance(row["fatal_events"], list) or set(row["fatal_events"]) - FATAL_EVENTS or len(row["fatal_events"]) != len(set(row["fatal_events"])):
        raise ValidationError("result: invalid fatal events")
    artifact = row["output_artifact"]
    if not isinstance(artifact, dict):
        raise ValidationError("result: output_artifact must be object")
    require_keys(artifact, {"locator", "sha256"}, {"locator", "sha256"}, "result.output_artifact")
    if not isinstance(artifact["locator"], str) or not artifact["locator"] or not isinstance(artifact["sha256"], str) or not SHA256_RE.fullmatch(artifact["sha256"]):
        raise ValidationError("result: invalid output artifact")
    usage = row["budget_usage"]
    usage_keys = {"model_input_tokens", "model_output_tokens", "wall_seconds", "expert_active_minutes", "compute_cost_usd"}
    if not isinstance(usage, dict):
        raise ValidationError("result: budget_usage must be object")
    require_keys(usage, usage_keys, usage_keys, "result.budget_usage")
    limits = budgets[task_budget]
    for name in usage_keys:
        value = usage[name]
        expected_types = {int} if name in {"model_input_tokens", "model_output_tokens"} else {int, float}
        if type(value) not in expected_types or value < 0 or (isinstance(value, float) and not math.isfinite(value)):
            raise ValidationError(f"result: invalid usage {name}")
        if value > limits[f"{name}_max"] and row["terminal_status"] != "budget_exceeded":
            raise ValidationError(f"result: {name} exceeds budget without budget_exceeded status")
    vfu = row["vfu"]
    vfu_keys = {"falsifiable", "outcome_supported", "no_fatal_error", "novel_at_t0", "verified_useful_discovery"}
    if not isinstance(vfu, dict):
        raise ValidationError("result.vfu must be object")
    require_keys(vfu, vfu_keys, vfu_keys, "result.vfu")
    if any(type(vfu[key]) is not bool for key in vfu_keys):
        raise ValidationError("result: VFU fields must be booleans")
    expected = all(vfu[key] for key in vfu_keys - {"verified_useful_discovery"})
    if row["fatal_events"] or row["terminal_status"] != "completed":
        expected = False
    if vfu["no_fatal_error"] != (not row["fatal_events"]):
        raise ValidationError("result: no_fatal_error conflicts with fatal_events")
    if vfu["verified_useful_discovery"] != expected:
        raise ValidationError("result: VFU conjunction is inconsistent")


def validate_manifest(root: Path, manifest: dict[str, Any], formal: bool, results_path: Path | None) -> dict[str, Any]:
    keys = {"schema_version", "benchmark_id", "status", "created_at", "evidence_class", "scientific_claim_allowed", "protocol", "arms", "budgets", "negative_controls", "artifacts", "immutable_digest"}
    require_keys(manifest, keys, keys, "manifest")
    if manifest["schema_version"] != "stage1.manifest.v1":
        raise ValidationError("unsupported manifest schema")
    if manifest["status"] not in {"IMPLEMENTATION_ONLY_NOT_STARTED", "PILOT_NOT_EVIDENCE", "FORMAL_FROZEN"}:
        raise ValidationError("invalid benchmark status")
    if type(manifest["scientific_claim_allowed"]) is not bool:
        raise ValidationError("scientific_claim_allowed must be boolean")
    if manifest["status"] != "FORMAL_FROZEN" and manifest["scientific_claim_allowed"]:
        raise ValidationError("non-formal package cannot allow a scientific claim")
    parse_time(manifest["created_at"], "manifest.created_at")

    protocol = manifest["protocol"]
    required_protocol = {"primary_endpoint", "unit", "minimum_formal_design", "stage2_gate", "synthetic_counts_as_scientific_evidence"}
    if not isinstance(protocol, dict):
        raise ValidationError("protocol must be object")
    require_keys(protocol, required_protocol, required_protocol, "manifest.protocol")
    if protocol["primary_endpoint"] != "VFU" or protocol["synthetic_counts_as_scientific_evidence"] is not False:
        raise ValidationError("VFU must be primary and synthetic evidence must be prohibited")
    design = protocol["minimum_formal_design"]
    design_keys = {"domains", "tasks_per_domain", "repeat_scoring_fraction"}
    if not isinstance(design, dict):
        raise ValidationError("minimum_formal_design must be object")
    require_keys(design, design_keys, design_keys, "minimum_formal_design")
    if type(design["domains"]) is not int or design["domains"] < 3 or type(design["tasks_per_domain"]) is not int or design["tasks_per_domain"] < 30:
        raise ValidationError("formal design must include at least 3 domains and 30 tasks per domain")
    if type(design["repeat_scoring_fraction"]) not in {int, float} or not 0 < design["repeat_scoring_fraction"] <= 1:
        raise ValidationError("invalid repeat scoring fraction")
    gate = protocol["stage2_gate"]
    gate_keys = {"paired_vfu_ci_lower_gt", "matched_negative_specificity_min", "fabricated_citation_rate_max", "fatal_overclaim_rate_max", "directionally_consistent_domains_min"}
    if not isinstance(gate, dict):
        raise ValidationError("stage2_gate must be object")
    require_keys(gate, gate_keys, gate_keys, "stage2_gate")
    if gate["paired_vfu_ci_lower_gt"] != 0 or gate["fabricated_citation_rate_max"] != 0:
        raise ValidationError("Stage 2 requires positive VFU lower bound and zero fabricated citations")
    if type(gate["matched_negative_specificity_min"]) not in {int, float} or not 0.9 <= gate["matched_negative_specificity_min"] <= 1:
        raise ValidationError("invalid matched-negative specificity gate")
    if type(gate["fatal_overclaim_rate_max"]) not in {int, float} or not 0 <= gate["fatal_overclaim_rate_max"] <= 0.01:
        raise ValidationError("invalid fatal-overclaim gate")
    if type(gate["directionally_consistent_domains_min"]) is not int or gate["directionally_consistent_domains_min"] < 2:
        raise ValidationError("invalid directional-consistency gate")

    arms = manifest["arms"]
    if not isinstance(arms, list) or not arms:
        raise ValidationError("arms must be non-empty")
    arm_ids: set[str] = set()
    ablation_indices: set[int] = set()
    for arm in arms:
        allowed = {"arm_id", "kind", "ablation_index"}
        required = {"arm_id", "kind"}
        if not isinstance(arm, dict):
            raise ValidationError("arm must be object")
        require_keys(arm, required, allowed, "arm")
        if not isinstance(arm.get("arm_id"), str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,95}", arm["arm_id"]):
            raise ValidationError("invalid arm_id")
        if arm["arm_id"] in arm_ids or arm["kind"] not in ARM_KINDS:
            raise ValidationError("duplicate arm or invalid kind")
        arm_ids.add(arm["arm_id"])
        if arm["kind"] == "ablation":
            if type(arm.get("ablation_index")) is not int:
                raise ValidationError("ablation requires integer index")
            ablation_indices.add(arm["ablation_index"])
        elif "ablation_index" in arm:
            raise ValidationError("non-ablation cannot have ablation_index")
    required_arms = {"expert_usual", "general_ai_rag", "semantic_retrieval_same_model", "random_or_same_domain_candidates", "full_structure_engine"}
    ablation_count = sum(arm["kind"] == "ablation" for arm in arms)
    expected_kinds = {"expert_usual": "baseline", "general_ai_rag": "baseline", "semantic_retrieval_same_model": "baseline", "random_or_same_domain_candidates": "negative_control", "full_structure_engine": "target"}
    if not required_arms <= arm_ids or any(next(arm for arm in arms if arm["arm_id"] == arm_id)["kind"] != kind for arm_id, kind in expected_kinds.items()) or ablation_count != 8 or ablation_indices != set(range(1, 9)):
        raise ValidationError("required baselines/target and exactly eight ablations are mandatory")

    budgets: dict[str, dict[str, Any]] = {}
    budget_keys = {"budget_id", "model_input_tokens_max", "model_output_tokens_max", "wall_seconds_max", "expert_active_minutes_max", "compute_cost_usd_max"}
    if not isinstance(manifest["budgets"], list) or not manifest["budgets"]:
        raise ValidationError("budgets must be a non-empty list")
    for budget in manifest["budgets"]:
        if not isinstance(budget, dict):
            raise ValidationError("budget must be object")
        require_keys(budget, budget_keys, budget_keys, "budget")
        if not isinstance(budget["budget_id"], str) or not re.fullmatch(r"budget_[a-z0-9_-]+", budget["budget_id"]):
            raise ValidationError("invalid budget_id")
        if budget["budget_id"] in budgets:
            raise ValidationError("duplicate budget_id")
        for key in budget_keys - {"budget_id"}:
            if type(budget[key]) not in {int, float} or budget[key] <= 0:
                raise ValidationError(f"budget limit must be positive: {key}")
        budgets[budget["budget_id"]] = budget
    if not isinstance(manifest["negative_controls"], list) or any(not isinstance(item, str) for item in manifest["negative_controls"]) or len(manifest["negative_controls"]) != len(set(manifest["negative_controls"])):
        raise ValidationError("negative controls must be a unique string list")
    controls = set(manifest["negative_controls"])
    required_controls = {"matched_non_isomorph", "synthetic_null", "random_candidate", "shared_shape_different_mechanism", "insufficient_evidence_should_reject"}
    if controls != required_controls:
        raise ValidationError("negative controls must exactly match protocol set")

    artifacts = manifest["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ValidationError("artifacts must be a non-empty list")
    artifact_paths: set[str] = set()
    problem_rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValidationError("artifact entry must be object")
        require_keys(artifact, {"path", "sha256"}, {"path", "sha256"}, "artifact")
        if artifact["path"] in artifact_paths:
            raise ValidationError("duplicate artifact path")
        artifact_paths.add(artifact["path"])
        target = safe_artifact_path(root, artifact["path"])
        actual = sha256_artifact(root, artifact["path"])
        if artifact["sha256"] != actual:
            raise ValidationError(f"artifact digest mismatch: {artifact['path']}")
        if artifact["path"].endswith("problems-v1.jsonl"):
            problem_rows.extend(load_jsonl(target))
    if not problem_rows:
        raise ValidationError("manifest must seal at least one problem JSONL")
    task_ids: set[str] = set()
    task_budget: dict[str, str] = {}
    for row in problem_rows:
        validate_problem(row)
        if row["task_id"] in task_ids:
            raise ValidationError(f"duplicate task_id: {row['task_id']}")
        if row["budget_id"] not in budgets:
            raise ValidationError(f"unknown task budget: {row['budget_id']}")
        task_ids.add(row["task_id"])
        task_budget[row["task_id"]] = row["budget_id"]

    if not SHA256_RE.fullmatch(str(manifest["immutable_digest"])) or manifest["immutable_digest"] != manifest_digest(manifest):
        raise ValidationError("manifest immutable_digest mismatch")

    if formal:
        if manifest["status"] != "FORMAL_FROZEN" or manifest["evidence_class"] != "historical":
            raise ValidationError("formal validation rejects implementation/pilot/synthetic packages")
        if manifest["scientific_claim_allowed"] is not True:
            raise ValidationError("formal completed package must explicitly allow scientific analysis")
        if results_path is None:
            raise ValidationError("formal validation requires a sealed, complete results file")
        if any(row["evidence_class"] == "synthetic" for row in problem_rows):
            raise ValidationError("formal Stage 1 cannot use synthetic tasks as scientific evidence")
        if any(row["contamination"]["model_probe_status"] != "pass" for row in problem_rows):
            raise ValidationError("formal Stage 1 requires passed model contamination probes")
        domains = Counter(row["domain"] for row in problem_rows)
        if len(domains) < design["domains"] or min(domains.values()) < design["tasks_per_domain"]:
            raise ValidationError("formal Stage 1 minimum domain/task design not met")
        if any(row["gold_status"] != "sealed" for row in problem_rows):
            raise ValidationError("formal pre-run tasks must have sealed gold")

    result_count = 0
    results_target: Path | None = None
    if results_path is not None:
        if results_path.is_symlink():
            raise ValidationError("results file cannot be a symlink")
        try:
            result_relative = results_path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError as exc:
            raise ValidationError("results file must be inside benchmark root") from exc
        results_target = safe_artifact_path(root, result_relative)
        if formal and result_relative not in artifact_paths:
            raise ValidationError("formal results file must be sealed by the manifest")
        seen_pairs: set[tuple[str, str]] = set()
        seen_runs: set[str] = set()
        for row in load_jsonl(results_target):
            if row.get("task_id") not in task_ids:
                raise ValidationError(f"result references unknown task: {row.get('task_id')}")
            validate_result(row, arm_ids, budgets, task_budget[row["task_id"]])
            if row["run_id"] in seen_runs:
                raise ValidationError(f"duplicate run_id: {row['run_id']}")
            seen_runs.add(row["run_id"])
            pair = (row["task_id"], row["arm_id"])
            if pair in seen_pairs:
                raise ValidationError(f"duplicate task/arm result: {pair}")
            seen_pairs.add(pair)
            result_count += 1

        if formal:
            expected_pairs = {(task_id, arm_id) for task_id in task_ids for arm_id in arm_ids}
            missing_pairs = expected_pairs - seen_pairs
            if missing_pairs:
                raise ValidationError(f"formal results incomplete: {len(missing_pairs)} task/arm rows missing")

    return {"benchmark_id": manifest["benchmark_id"], "status": manifest["status"], "tasks": len(task_ids), "arms": len(arm_ids), "results": result_count, "scientific_evidence": bool(formal)}


def seal(manifest_path: Path) -> None:
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValidationError("manifest to seal must be a regular non-symlink file")
    manifest = load_json(manifest_path)
    root = manifest_path.parent
    for artifact in manifest.get("artifacts", []):
        artifact["sha256"] = sha256_artifact(root, artifact["path"])
    manifest["immutable_digest"] = manifest_digest(manifest)
    validate_manifest(root, manifest, formal=False, results_path=None)
    payload = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    temporary = manifest_path.with_name(f".{manifest_path.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, manifest_path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--formal", action="store_true", help="enforce formal Stage 1 design; rejects fixtures")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--seal", action="store_true", help="update artifact and canonical manifest digests")
    args = parser.parse_args()
    try:
        if args.seal:
            seal(args.manifest)
        manifest = load_json(args.manifest)
        summary = validate_manifest(args.manifest.parent, manifest, args.formal, args.results)
    except ValidationError as exc:
        print(f"STAGE1 INVALID: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"valid": True, **summary}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
