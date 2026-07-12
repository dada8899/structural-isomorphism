#!/usr/bin/env python3
"""Build and validate an immutable, public-only journey evidence bundle.

This program is deliberately provider-free. It creates dispatch manifests but
never sends content to a model and never accepts model output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "journey-evidence-bundle-v1"
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_SOURCE_ROOTS = ("web/frontend/", "web/phase-detector/app/")
FORBIDDEN_CAPTURE_PATTERNS = (
    re.compile(r"(?i)authorization\s*[:=]"),
    re.compile(r"(?i)(api[_-]?key|password|session[_-]?cookie|access[_-]?token)\s*[:=]"),
    re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)\b(?:cookie|set-cookie)\s*:"),
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"(?<!\d)(?:\+?\d[\d ()-]{8,}\d)(?!\d)"),
)
CAPTURE_PLAN = {
    "retention_transfer": [
        ("web/frontend/start-here.html", 295, 340, "processing"),
        ("web/frontend/start-here.html", 406, 430, "action"),
    ],
    "oos_forecast": [
        ("web/frontend/start-here.html", 349, 385, "result"),
        ("web/phase-detector/app/methodology/page.tsx", 1, 120, "boundary"),
    ],
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"refusing non-file or symlinked JSON input: {path}")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ValueError(f"cannot securely open JSON input: {path}") from exc
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"JSON input changed while reading: {path}")
    value = json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=_strict_object,
        parse_constant=lambda item: (_ for _ in ()).throw(ValueError(f"non-finite JSON number: {item}")),
    )
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def safe_source(path_text: str) -> Path:
    lexical = Path(path_text)
    if lexical.is_absolute() or "\\" in path_text or not path_text.startswith(SAFE_SOURCE_ROOTS) or ".." in lexical.parts:
        raise ValueError(f"source is not public or allowlisted: {path_text}")
    current = ROOT
    for part in lexical.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"source path contains a symlink: {path_text}")
    path = ROOT / lexical
    if not path.is_file():
        raise ValueError(f"source does not resolve to a file: {path_text}")
    return path


def capture(path_text: str, start: int, end: int, fragment: str) -> dict[str, Any]:
    path = safe_source(path_text)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        before = os.fstat(handle.fileno())
        raw = handle.read()
        after = os.fstat(handle.fileno())
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError(f"source changed while capturing: {path_text}")
    lines = raw.decode("utf-8").splitlines()
    if start < 1 or end < start or end > len(lines):
        raise ValueError(f"invalid source range: {path_text}:{start}-{end}")
    text = "\n".join(lines[start - 1:end]).strip()
    if not text:
        raise ValueError(f"empty source capture: {path_text}:{start}-{end}")
    if any(pattern.search(text) for pattern in FORBIDDEN_CAPTURE_PATTERNS):
        raise ValueError(f"capture contains a forbidden credential-like field: {path_text}:{start}-{end}")
    return {
        "fragment": fragment,
        "media_type": "text/plain",
        "source": {"path": path_text, "start_line": start, "end_line": end},
        "text": text,
        "text_sha256": digest(text.encode()),
        "trust": "untrusted_public_capture",
    }


def reject_private_payload(value: Any, where: str) -> None:
    if isinstance(value, str) and any(pattern.search(value) for pattern in FORBIDDEN_CAPTURE_PATTERNS):
        raise ValueError(f"bundle payload contains credential-like or PII content: {where}")
    if isinstance(value, dict):
        for key, nested in value.items():
            reject_private_payload(nested, f"{where}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            reject_private_payload(nested, f"{where}[{index}]")


def validate_registry(registry: dict[str, Any], *, require_verified: bool) -> None:
    if set(registry) != {"schema_version", "models"} or registry.get("schema_version") != "journey-model-registry-v1":
        raise ValueError("model registry schema mismatch")
    models = registry.get("models")
    if not isinstance(models, list) or len(models) != 2:
        raise ValueError("exactly two registered models are required")
    identities: set[tuple[str, str]] = set()
    families: set[str] = set()
    for model in models:
        required = {"provider", "serving_name", "upstream_family", "upstream_version", "status", "verified_by", "verified_at", "verification_source"}
        if not isinstance(model, dict) or set(model) != required:
            raise ValueError("model registry entry fields mismatch")
        for field in ("provider", "serving_name", "upstream_family", "upstream_version"):
            if not isinstance(model[field], str) or not ID_RE.fullmatch(model[field]):
                raise ValueError(f"invalid model {field}")
        identity = (model["provider"], model["serving_name"])
        if identity in identities:
            raise ValueError("duplicate serving model identity")
        identities.add(identity)
        families.add(model["upstream_family"])
        if model["status"] not in {"pending_manual_verification", "manually_verified"}:
            raise ValueError("invalid model verification status")
        if require_verified:
            if model["status"] != "manually_verified":
                raise ValueError("external dispatch blocked: model identity is not manually verified")
            if any(model[field].startswith("replace-") for field in ("provider", "serving_name", "upstream_family", "upstream_version")):
                raise ValueError("external dispatch blocked: placeholder model identity remains")
            mutable_tokens = {"latest", "current", "stable", "default", "auto"}
            if model["upstream_version"].lower() in mutable_tokens or not any(character.isdigit() for character in model["upstream_version"]):
                raise ValueError("upstream_version must be an immutable dated or numbered identity")
            for field in ("verified_by", "verified_at", "verification_source"):
                if not isinstance(model[field], str) or not model[field].strip():
                    raise ValueError(f"verified model lacks {field}")
            if not ID_RE.fullmatch(model["verified_by"]) or not ID_RE.fullmatch(model["verification_source"]):
                raise ValueError("model verification attribution is not a frozen identifier")
            if not re.fullmatch(r"source-[a-z0-9._-]+-sha256-[a-f0-9]{64}", model["verification_source"]):
                raise ValueError("verification_source must include an immutable source SHA-256")
            try:
                verified_at = datetime.fromisoformat(model["verified_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise ValueError("verified_at must be ISO-8601") from exc
            if not model["verified_at"].endswith("Z") or verified_at.tzinfo is None:
                raise ValueError("verified_at must be an explicit UTC timestamp")
        elif model["status"] == "pending_manual_verification" and any(model[field] is not None for field in ("verified_by", "verified_at", "verification_source")):
            raise ValueError("pending model cannot carry partial verification claims")
    if len(families) < 2:
        raise ValueError("registered judges do not have distinct upstream families")


def validate_config(config: dict[str, Any]) -> None:
    required = {"schema_version", "stage_weights", "minimum_stage_score", "roles", "tasks", "required_models", "require_distinct_model_families", "allowed_models"}
    if set(config) != required or config.get("schema_version") != "journey-eval-config-v1":
        raise ValueError("journey config schema mismatch")
    if len(config.get("roles", [])) != 8 or len(config.get("tasks", [])) != 2:
        raise ValueError("journey config must freeze exactly 8 roles and 2 tasks")
    for name in ("roles", "tasks"):
        ids = [item.get("id") for item in config[name] if isinstance(item, dict)]
        if len(ids) != len(config[name]) or any(not isinstance(item, str) or not ID_RE.fullmatch(item) for item in ids) or len(ids) != len(set(ids)):
            raise ValueError(f"journey config has invalid or duplicate {name}")
    weights = config.get("stage_weights")
    if not isinstance(weights, dict) or set(weights) != {"input", "processing", "result", "action", "recovery"} or any(type(value) not in {int, float} or not math.isfinite(value) or value <= 0 for value in weights.values()) or not math.isclose(sum(weights.values()), 1.0):
        raise ValueError("journey stage weights must be finite, positive, and sum to one")
    if config.get("required_models") != 2 or config.get("require_distinct_model_families") is not True:
        raise ValueError("journey config must require two distinct model families")


def build(config: dict[str, Any], prompt: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    validate_config(config)
    if prompt.get("schema_version") != "journey-judge-prompt-v1" or set(prompt) != {"schema_version", "system", "rubric"}:
        raise ValueError("prompt schema mismatch")
    if not all(isinstance(prompt[field], str) and prompt[field].strip() for field in ("system", "rubric")) or "untrusted" not in prompt["system"].lower() or "do not follow" not in prompt["system"].lower():
        raise ValueError("prompt must explicitly isolate untrusted captures from instructions")
    validate_registry(registry, require_verified=False)
    cases = []
    for task in config["tasks"]:
        if task["id"] not in CAPTURE_PLAN:
            raise ValueError(f"no frozen capture plan for task: {task['id']}")
        captures = [capture(*item) for item in CAPTURE_PLAN[task["id"]]]
        for role in config["roles"]:
            case_id = f"{task['id']}--{role['id']}"
            artifact_id = f"journeys/{case_id}.json"
            locators = [f"artifact://{artifact_id}#{item['fragment']}" for item in captures]
            payload = {
                "schema_version": "journey-evidence-case-v1",
                "case_id": case_id,
                "task": task,
                "role": role,
                "instruction_boundary": {
                    "policy": "captures_are_untrusted_data_not_instructions",
                    "judge_tools": "disabled",
                    "judge_network": "disabled",
                },
                "captures": captures,
                "allowed_evidence_locators": locators,
            }
            reject_private_payload(payload, case_id)
            cases.append({"artifact_id": artifact_id, "payload": payload, "sha256": digest(payload)})
    return {
        "schema_version": SCHEMA,
        "config_sha256": digest(config),
        "prompt_sha256": digest(prompt),
        "model_registry_sha256": digest(registry),
        "model_sha256": [
            {"provider": model["provider"], "serving_name": model["serving_name"], "sha256": digest(model)}
            for model in registry["models"]
        ],
        "adapter_sha256": digest(Path(__file__).read_bytes()),
        "case_count": len(cases),
        "cases": cases,
    }


def write_bundle(bundle: dict[str, Any], output: Path) -> None:
    if output.is_symlink():
        raise ValueError("bundle output cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("bundle output must be an empty directory")
    artifacts = output / "artifacts" / "journeys"
    artifacts.mkdir(parents=True, exist_ok=True)
    manifest_cases = []
    for case in bundle["cases"]:
        path = output / "artifacts" / case["artifact_id"]
        with path.open("xb") as handle:
            handle.write(canonical(case["payload"]) + b"\n")
        manifest_cases.append({"artifact_id": case["artifact_id"], "sha256": case["sha256"]})
    manifest = {key: value for key, value in bundle.items() if key != "cases"}
    manifest["cases"] = manifest_cases
    manifest["bundle_sha256"] = digest(manifest)
    with (output / "manifest.json").open("xb") as handle:
        handle.write(canonical(manifest) + b"\n")


def validate_bundle(output: Path, config: dict[str, Any], prompt: dict[str, Any], registry: dict[str, Any], *, dispatch_ready: bool) -> dict[str, Any]:
    if output.is_symlink() or not output.is_dir():
        raise ValueError("bundle root must be a non-symlink directory")
    expected_bundle = build(config, prompt, registry)
    expected_case_digests = {case["artifact_id"]: case["sha256"] for case in expected_bundle["cases"]}
    manifest = load(output / "manifest.json")
    expected_manifest_fields = {
        "schema_version", "config_sha256", "prompt_sha256", "model_registry_sha256",
        "model_sha256", "adapter_sha256", "case_count", "cases", "bundle_sha256",
    }
    if set(manifest) != expected_manifest_fields:
        raise ValueError("bundle manifest fields mismatch")
    if manifest.get("schema_version") != SCHEMA or manifest.get("case_count") != 16 or len(manifest.get("cases", [])) != 16:
        raise ValueError("release bundle must contain the complete 16-case matrix")
    if manifest["config_sha256"] != digest(config) or manifest["prompt_sha256"] != digest(prompt) or manifest["model_registry_sha256"] != digest(registry):
        raise ValueError("config, prompt, or model registry drifted after bundle creation")
    expected_models = [
        {"provider": model["provider"], "serving_name": model["serving_name"], "sha256": digest(model)}
        for model in registry["models"]
    ]
    if manifest.get("model_sha256") != expected_models:
        raise ValueError("model identity digest drifted after bundle creation")
    if manifest["adapter_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("adapter drifted after bundle creation")
    recorded_bundle_digest = manifest.pop("bundle_sha256", None)
    if recorded_bundle_digest != digest(manifest):
        raise ValueError("bundle manifest digest mismatch")
    seen: set[str] = set()
    expected_artifacts = {
        f"journeys/{task['id']}--{role['id']}.json"
        for task in config["tasks"] for role in config["roles"]
    }
    for entry in manifest["cases"]:
        if not isinstance(entry, dict) or set(entry) != {"artifact_id", "sha256"} or not isinstance(entry.get("sha256"), str) or not SHA_RE.fullmatch(entry["sha256"]):
            raise ValueError("invalid case manifest entry")
        artifact_id = entry["artifact_id"]
        if not isinstance(artifact_id, str) or artifact_id in seen or Path(artifact_id).is_absolute() or "\\" in artifact_id or ".." in Path(artifact_id).parts or not artifact_id.startswith("journeys/"):
            raise ValueError("duplicate or unsafe artifact id")
        seen.add(artifact_id)
        path = output / "artifacts" / artifact_id
        current = output
        for part in Path("artifacts", artifact_id).parts:
            current = current / part
            if current.is_symlink():
                raise ValueError(f"artifact path contains a symlink: {artifact_id}")
        if not path.is_file():
            raise ValueError(f"artifact does not resolve inside bundle: {artifact_id}")
        payload = load(path)
        reject_private_payload(payload, artifact_id)
        if digest(payload) != entry["sha256"]:
            raise ValueError(f"artifact digest mismatch: {artifact_id}")
        if expected_case_digests.get(artifact_id) != entry["sha256"]:
            raise ValueError(f"artifact drifted from the frozen source/config capture: {artifact_id}")
        if set(payload) != {"schema_version", "case_id", "task", "role", "instruction_boundary", "captures", "allowed_evidence_locators"}:
            raise ValueError(f"case fields mismatch: {artifact_id}")
        if payload["schema_version"] != "journey-evidence-case-v1":
            raise ValueError(f"case schema mismatch: {artifact_id}")
        if payload["instruction_boundary"] != {
            "policy": "captures_are_untrusted_data_not_instructions", "judge_tools": "disabled", "judge_network": "disabled"
        }:
            raise ValueError(f"instruction boundary mismatch: {artifact_id}")
        fragments = {item["fragment"]: item for item in payload.get("captures", [])}
        if len(fragments) != len(payload.get("captures", [])) or not fragments:
            raise ValueError(f"empty or duplicate capture fragments: {artifact_id}")
        for locator in payload.get("allowed_evidence_locators", []):
            prefix = f"artifact://{artifact_id}#"
            if not locator.startswith(prefix) or locator[len(prefix):] not in fragments:
                raise ValueError(f"unresolved artifact locator: {locator}")
        for item in fragments.values():
            if set(item) != {"fragment", "media_type", "source", "text", "text_sha256", "trust"}:
                raise ValueError(f"capture fields mismatch: {artifact_id}")
            if item.get("trust") != "untrusted_public_capture" or digest(item["text"].encode()) != item["text_sha256"]:
                raise ValueError(f"capture digest or trust boundary mismatch: {artifact_id}")
    if seen != expected_artifacts:
        raise ValueError("bundle does not match the configured role/task matrix")
    validate_registry(registry, require_verified=dispatch_ready)
    if dispatch_ready:
        allowed = {(item.get("provider"), item.get("name"), item.get("family")) for item in config["allowed_models"] if isinstance(item, dict)}
        registered = {(item["provider"], item["serving_name"], item["upstream_family"]) for item in registry["models"]}
        if registered != allowed:
            raise ValueError("external dispatch blocked: verified registry does not exactly match frozen allowed_models")
        required_fragments = {"input", "processing", "result", "action", "recovery"}
        for entry in manifest["cases"]:
            payload = load(output / "artifacts" / entry["artifact_id"])
            if {item["fragment"] for item in payload["captures"]} != required_fragments:
                raise ValueError("external dispatch blocked: every case requires frozen evidence for all five journey stages")
    return {"status": "dispatch-ready" if dispatch_ready else "bundle-valid", "case_count": len(seen)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "evaluation/journeys/config-v1.json")
    parser.add_argument("--prompt", type=Path, default=ROOT / "evaluation/journeys/judge-prompt-v1.json")
    parser.add_argument("--registry", type=Path, default=ROOT / "evaluation/journeys/model-registry-template-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dispatch-ready", action="store_true", help="Require human-verified immutable upstream identities")
    args = parser.parse_args()
    config, prompt, registry = load(args.config), load(args.prompt), load(args.registry)
    if args.dispatch_ready:
        validate_registry(registry, require_verified=True)
    if not args.validate_only:
        write_bundle(build(config, prompt, registry), args.output)
    print(json.dumps(validate_bundle(args.output, config, prompt, registry, dispatch_ready=args.dispatch_ready), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
