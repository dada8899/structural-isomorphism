#!/usr/bin/env python3
"""Validate pilot sourcing slots and create answer-blind expert packet drafts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "evaluation/stage1/pilot-sourcing-queue-v1.json"
CHECKLIST = ROOT / "evaluation/stage1/contamination-checklist-v1.json"
EXPECTED_BASELINES = {"expert_usual", "expert_plus_general_ai_rag", "same_model_semantic_rag"}
EXPECTED_DOMAINS = {"earth_systems", "biomedical_systems", "networked_infrastructure", "collective_behavior"}
EXPECTED_FAMILIES = {"prediction", "experiment_design", "mechanism_discrimination"}
EXPECTED_CHECKS = {
    "corpus_cutoff", "answer_absence", "near_duplicate", "target_revealing_text",
    "model_training_risk", "developer_exposure", "search_cache", "packet_redaction",
    "independent_signoff",
}
EXPECTED_CONTROL_BY_FAMILY = {
    "prediction": "matched_non_isomorph",
    "experiment_design": "random_candidate",
    "mechanism_discrimination": "same_domain_candidate",
}
EXPECTED_EXPERTISE = {
    "earth_systems": "earth-system observation and inference",
    "biomedical_systems": "biomedical experimental design and statistics",
    "networked_infrastructure": "network resilience and cascading failures",
    "collective_behavior": "collective behavior and causal inference",
}
EXPECTED_CHECK_QUESTIONS = {
    "corpus_cutoff": "Are every corpus, cache and retrieval snapshot dated no later than the frozen cutoff?",
    "answer_absence": "Is the outcome answer absent from the repository, prompts, fixtures, caches and model-visible packet?",
    "near_duplicate": "Did a reviewer inspect lexical and semantic near-duplicate candidates without exposing the answer?",
    "target_revealing_text": "Did a reviewer check titles, abstracts, filenames and metadata for target-revealing text?",
    "model_training_risk": "Is model pretraining or post-training exposure assessed and recorded rather than assumed absent?",
    "developer_exposure": "Are developers who saw the answer excluded from task selection, execution and primary scoring?",
    "search_cache": "Are external search results frozen at t0 and checked for post-t0 snippets?",
    "packet_redaction": "Does the expert packet omit answer locator, digest, outcome and adjudication fields?",
    "independent_signoff": "Did an independent reviewer sign the completed scan before dispatch?",
}
SLOT_KEYS = {
    "slot_id", "status", "domain", "task_family", "expert_role", "budget",
    "baselines", "negative_control", "time_split", "answer_source",
    "contamination_scan", "formal_evidence_allowed",
}


class PilotValidationError(ValueError):
    pass


def _no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PilotValidationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def _open_parent_dirfd(path: Path) -> tuple[int, str]:
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    current = os.open(parts[0], directory_flags)
    try:
        for part in parts[1:-1]:
            next_fd = os.open(part, directory_flags, dir_fd=current)
            os.close(current)
            current = next_fd
        return current, parts[-1]
    except Exception:
        os.close(current)
        raise


def load_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise PilotValidationError(f"JSON input must be a regular non-symlink file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    parent_fd: int | None = None
    try:
        parent_fd, filename = _open_parent_dirfd(path)
        descriptor = os.open(filename, flags, dir_fd=parent_fd)
    except OSError as exc:
        raise PilotValidationError(f"cannot securely open JSON input: {path}") from exc
    finally:
        if parent_fd is not None:
            os.close(parent_fd)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise PilotValidationError(f"JSON input changed while reading: {path}")
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_no_duplicate_keys,
        parse_constant=lambda token: (_ for _ in ()).throw(PilotValidationError(f"non-finite number: {token}")),
    )


def canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise PilotValidationError("value is not canonical finite JSON") from exc
    return hashlib.sha256(payload).hexdigest()


def validate_checklist(value: dict[str, Any]) -> None:
    if set(value) != {"schema_version", "checklist_id", "status", "checks", "result_states", "dispatch_rule"}:
        raise PilotValidationError("contamination checklist schema mismatch")
    if value.get("schema_version") != "stage1-contamination-v1" or value.get("status") != "TEMPLATE_NOT_RUN":
        raise PilotValidationError("contamination checklist must remain an unrun template")
    checks = value.get("checks")
    if not isinstance(checks, list) or len(checks) != 9:
        raise PilotValidationError("contamination checklist is incomplete")
    ids: list[str] = []
    for item in checks:
        if not isinstance(item, dict) or set(item) != {"id", "question"} or not isinstance(item["id"], str) or not re.fullmatch(r"[a-z][a-z0-9_]{2,63}", item["id"]) or not isinstance(item["question"], str) or not item["question"].strip():
            raise PilotValidationError("contamination checklist item schema mismatch")
        ids.append(item["id"])
    if len(ids) != len(set(ids)):
        raise PilotValidationError("contamination checklist IDs must be unique")
    if set(ids) != EXPECTED_CHECKS:
        raise PilotValidationError("contamination checklist lacks the exact nine leakage checks")
    if {item["id"]: item["question"] for item in checks} != EXPECTED_CHECK_QUESTIONS:
        raise PilotValidationError("contamination checklist questions drifted")
    if value["result_states"] != ["PASS", "FAIL", "UNRESOLVED"]:
        raise PilotValidationError("contamination result states mismatch")
    expected_rule = "Every check must be PASS; any FAIL, UNRESOLVED or NOT_RUN blocks dispatch and formal evidence."
    if value["dispatch_rule"] != expected_rule:
        raise PilotValidationError("contamination dispatch rule mismatch")


def validate_slot(slot: dict[str, Any]) -> None:
    if set(slot) != SLOT_KEYS:
        raise PilotValidationError(f"{slot.get('slot_id', 'unknown')}: slot schema mismatch")
    if slot["status"] != "SOURCING_PLACEHOLDER" or slot["formal_evidence_allowed"] is not False:
        raise PilotValidationError(f"{slot['slot_id']}: placeholder cannot become formal evidence")
    if not all(isinstance(slot[key], str) and slot[key] for key in ("slot_id", "domain", "task_family")):
        raise PilotValidationError("slot identity fields must be non-empty")
    if not re.fullmatch(r"pilot-[0-9]{2}", slot["slot_id"]):
        raise PilotValidationError("slot_id format mismatch")
    if slot["task_family"] not in {"prediction", "experiment_design", "mechanism_discrimination"}:
        raise PilotValidationError(f"{slot['slot_id']}: unsupported task family")
    expert = slot["expert_role"]
    if set(expert) != {"domain_expertise", "independent_of_engine", "assigned_expert_id"}:
        raise PilotValidationError(f"{slot['slot_id']}: expert role schema mismatch")
    if expert["independent_of_engine"] is not True or expert["assigned_expert_id"] is not None:
        raise PilotValidationError(f"{slot['slot_id']}: pilot placeholder must await independent expert assignment")
    if not isinstance(expert["domain_expertise"], str) or not expert["domain_expertise"].strip():
        raise PilotValidationError(f"{slot['slot_id']}: domain expertise must be explicit")
    if slot["domain"] not in EXPECTED_EXPERTISE or expert["domain_expertise"] != EXPECTED_EXPERTISE[slot["domain"]]:
        raise PilotValidationError(f"{slot['slot_id']}: expert role does not match the frozen domain stratum")
    budget = slot["budget"]
    if set(budget) != {"expert_minutes_max", "wall_minutes_max", "compute_usd_max"} or any(
        not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0 for value in budget.values()
    ):
        raise PilotValidationError(f"{slot['slot_id']}: positive complete budget required")
    if type(budget["expert_minutes_max"]) is not int or type(budget["wall_minutes_max"]) is not int:
        raise PilotValidationError(f"{slot['slot_id']}: minute budgets must be integers")
    if not isinstance(slot["baselines"], list) or any(not isinstance(item, str) for item in slot["baselines"]):
        raise PilotValidationError(f"{slot['slot_id']}: baselines must be a string list")
    if set(slot["baselines"]) != EXPECTED_BASELINES or len(slot["baselines"]) != len(EXPECTED_BASELINES):
        raise PilotValidationError(f"{slot['slot_id']}: all strong baselines are required")
    control = slot["negative_control"]
    if set(control) != {"kind", "frozen"} or control["frozen"] is not False:
        raise PilotValidationError(f"{slot['slot_id']}: negative control is not yet frozen")
    if control["kind"] not in {"matched_non_isomorph", "random_candidate", "same_domain_candidate"}:
        raise PilotValidationError(f"{slot['slot_id']}: unsupported negative control")
    if control["kind"] != EXPECTED_CONTROL_BY_FAMILY[slot["task_family"]]:
        raise PilotValidationError(f"{slot['slot_id']}: negative control does not match frozen task-family design")
    split = slot["time_split"]
    if set(split) != {"t0", "latest_accessible_material_at", "outcome_available_after_t0"} or any(
        value is not None for value in split.values()
    ):
        raise PilotValidationError(f"{slot['slot_id']}: placeholder must not fabricate a time split")
    answer = slot["answer_source"]
    if answer != {"state": "NOT_IMPORTED", "locator": None, "digest": None, "imported_into_repository": False}:
        raise PilotValidationError(f"{slot['slot_id']}: outcome answer must remain unimported and undisclosed")
    scan = slot["contamination_scan"]
    if scan != {"checklist_id": "stage1-contamination-v1", "state": "NOT_RUN", "completed_by": None, "completed_at": None}:
        raise PilotValidationError(f"{slot['slot_id']}: contamination scan must remain NOT_RUN")


def validate_queue(queue: dict[str, Any], checklist: dict[str, Any]) -> dict[str, Any]:
    validate_checklist(checklist)
    if set(queue) != {"schema_version", "status", "pilot_target", "slots"}:
        raise PilotValidationError("pilot queue schema mismatch")
    if queue.get("schema_version") != "stage1-pilot-sourcing-queue-v1":
        raise PilotValidationError("pilot queue schema mismatch")
    if queue.get("status") != "PILOT_SOURCING_ONLY_FORMAL_NO_GO":
        raise PilotValidationError("formal benchmark must remain NO-GO")
    slots = queue.get("slots")
    if not isinstance(slots, list) or len(slots) != 12 or queue.get("pilot_target") != 12:
        raise PilotValidationError("pilot queue must contain exactly 12 explicit slots")
    for slot in slots:
        if not isinstance(slot, dict):
            raise PilotValidationError("pilot slot must be an object")
        validate_slot(slot)
    ids = [slot["slot_id"] for slot in slots]
    if len(ids) != len(set(ids)):
        raise PilotValidationError("pilot slot IDs must be unique")
    if set(ids) != {f"pilot-{index:02d}" for index in range(1, 13)}:
        raise PilotValidationError("pilot slot IDs must be exactly pilot-01 through pilot-12")
    domains = {slot["domain"] for slot in slots}
    families = {slot["task_family"] for slot in slots}
    matrix = {(slot["domain"], slot["task_family"]) for slot in slots}
    if domains != EXPECTED_DOMAINS or families != EXPECTED_FAMILIES or matrix != {(domain, family) for domain in EXPECTED_DOMAINS for family in EXPECTED_FAMILIES}:
        raise PilotValidationError("pilot queue must contain exactly one slot for every 4-domain x 3-family cell")
    budgets = {canonical_sha256(slot["budget"]) for slot in slots}
    if len(budgets) != 1:
        raise PilotValidationError("all pilot slots must use one equal frozen budget")
    return {"slots": len(slots), "domains": len(domains), "formal_evidence": False, "dispatch_ready": False}


def expert_packet(slot: dict[str, Any], checklist: dict[str, Any]) -> dict[str, Any]:
    validate_slot(slot)
    validate_checklist(checklist)
    packet = {
        "schema_version": "stage1-pilot-expert-packet-v1",
        "status": "DRAFT_NOT_DISPATCH_READY",
        "slot_id": slot["slot_id"],
        "domain": slot["domain"],
        "task_family": slot["task_family"],
        "expert_role": slot["expert_role"],
        "budget": slot["budget"],
        "baselines": slot["baselines"],
        "negative_control": slot["negative_control"],
        "time_split": slot["time_split"],
        "answer_source_state": "NOT_IMPORTED",
        "contamination_questions": [{"id": item["id"], "question": item["question"], "result": "NOT_RUN"} for item in checklist["checks"]],
        "formal_evidence_allowed": False,
    }
    packet["packet_sha256"] = canonical_sha256(packet)
    return packet


def write_packets(queue: dict[str, Any], checklist: dict[str, Any], output_dir: Path) -> None:
    validate_queue(queue, checklist)
    if output_dir.is_symlink():
        raise PilotValidationError("output directory cannot be a symlink")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    parent_fd, directory_name = _open_parent_dirfd(output_dir)
    try:
        os.mkdir(directory_name, 0o700, dir_fd=parent_fd)
        directory_fd = os.open(directory_name, directory_flags, dir_fd=parent_fd)
    finally:
        os.close(parent_fd)
    try:
        for slot in queue["slots"]:
            filename = f"{slot['slot_id']}.expert-packet.json"
            payload = (json.dumps(expert_packet(slot, checklist), ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode()
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=directory_fd)
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, default=QUEUE)
    parser.add_argument("--checklist", type=Path, default=CHECKLIST)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--dispatch-ready", action="store_true")
    args = parser.parse_args()
    queue, checklist = load_json(args.queue), load_json(args.checklist)
    summary = validate_queue(queue, checklist)
    if args.dispatch_ready:
        raise PilotValidationError("pilot placeholders are not dispatch-ready; expert assignment, time split, outcome custody and contamination signoff are missing")
    if args.output_dir:
        write_packets(queue, checklist, args.output_dir)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PilotValidationError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        raise SystemExit(1)
