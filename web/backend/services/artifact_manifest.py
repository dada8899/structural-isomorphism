"""Fail-closed validation for the production KB/model artifact bundle."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


class ArtifactValidationError(RuntimeError):
    """Raised when a production artifact does not match its manifest."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ArtifactValidationError(f"{label} missing: {path}")


def _validate_hash(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ArtifactValidationError(
            f"{label} checksum mismatch: expected {expected}, got {actual}"
        )


def validate_artifact_bundle(
    manifest_path: str | Path,
    *,
    kb_path: str | Path,
    embeddings_path: str | Path,
    model_path: str | Path,
    formal: bool = False,
) -> dict[str, Any]:
    """Validate all production artifacts and return safe metadata."""
    manifest_file = Path(manifest_path)
    kb_file = Path(kb_path)
    embeddings_file = Path(embeddings_path)
    model_dir = Path(model_path)
    if formal:
        if any(not path.is_absolute() for path in (manifest_file, kb_file, embeddings_file, model_dir)):
            raise ArtifactValidationError("formal artifact paths must be absolute")
    _require_file(manifest_file, "artifact manifest")
    _require_file(kb_file, "knowledge base")
    _require_file(embeddings_file, "embeddings")
    if not model_dir.is_dir():
        raise ArtifactValidationError(f"model directory missing: {model_dir}")

    try:
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"invalid artifact manifest: {exc}") from exc
    if manifest.get("schema_version") != 1 or not manifest.get("artifact_id"):
        raise ArtifactValidationError("unsupported or missing artifact manifest schema")
    if formal and (
        type(manifest["schema_version"]) is not int
        or not isinstance(manifest["artifact_id"], str)
        or not manifest["artifact_id"].strip()
    ):
        raise ArtifactValidationError("formal artifact identity is invalid")

    with kb_file.open("rb") as handle:
        prefix = handle.read(160)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ArtifactValidationError(f"knowledge base is a Git LFS pointer: {kb_file}")

    kb_spec = manifest.get("kb") or {}
    if formal and (
        type(kb_spec.get("row_count")) is not int or kb_spec["row_count"] <= 0
        or type(kb_spec.get("unique_id_count")) is not int
        or kb_spec["unique_id_count"] != kb_spec["row_count"]
    ):
        raise ArtifactValidationError("formal knowledge base requires nonempty unique rows")
    ids: set[str] = set()
    row_count = 0
    try:
        with kb_file.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip() or line.lstrip().startswith("//"):
                    continue
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ArtifactValidationError("knowledge base row is not an object")
                record_id = record.get("id")
                if not isinstance(record_id, str) or not record_id:
                    raise ArtifactValidationError(
                        f"knowledge base row {line_number} has no valid id"
                    )
                ids.add(record_id)
                row_count += 1
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"invalid knowledge base JSONL: {exc}") from exc
    if row_count != kb_spec.get("row_count"):
        raise ArtifactValidationError(
            f"knowledge base row count mismatch: expected {kb_spec.get('row_count')}, got {row_count}"
        )
    if len(ids) != kb_spec.get("unique_id_count"):
        raise ArtifactValidationError(
            "knowledge base unique id count mismatch: "
            f"expected {kb_spec.get('unique_id_count')}, got {len(ids)}"
        )
    _validate_hash(kb_file, kb_spec.get("sha256", ""), "knowledge base")

    embedding_spec = manifest.get("embeddings") or {}
    try:
        embeddings = np.load(embeddings_file, mmap_mode="r", allow_pickle=False)
    except Exception as exc:
        raise ArtifactValidationError(f"invalid embeddings file: {exc}") from exc
    expected_shape = tuple(embedding_spec.get("shape") or [])
    if formal and (
        len(expected_shape) != 2
        or any(type(size) is not int or size <= 0 for size in expected_shape)
        or embeddings.ndim != 2
        or not np.issubdtype(embeddings.dtype, np.floating)
        or not np.isfinite(embeddings).all()
    ):
        raise ArtifactValidationError("formal embeddings require a finite floating matrix")
    if embeddings.shape != expected_shape or embeddings.shape[0] != row_count:
        raise ArtifactValidationError(
            f"embeddings shape mismatch: expected {expected_shape}, got {embeddings.shape}"
        )
    if str(embeddings.dtype) != embedding_spec.get("dtype"):
        raise ArtifactValidationError(
            f"embeddings dtype mismatch: expected {embedding_spec.get('dtype')}, got {embeddings.dtype}"
        )
    _validate_hash(embeddings_file, embedding_spec.get("sha256", ""), "embeddings")

    model_spec = manifest.get("model") or {}
    if formal and (
        not isinstance(model_spec.get("id"), str) or not model_spec["id"]
        or not isinstance(model_spec.get("required_files"), dict)
        or not model_spec["required_files"]
    ):
        raise ArtifactValidationError("formal model identity and file hashes are required")
    for relative_name, expected_hash in (model_spec.get("required_files") or {}).items():
        relative_path = Path(relative_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ArtifactValidationError(f"unsafe model file path: {relative_name}")
        model_file = model_dir / relative_path
        if formal and not model_file.resolve().is_relative_to(model_dir.resolve()):
            raise ArtifactValidationError("formal model file escaped its model directory")
        _require_file(model_file, f"model file {relative_name}")
        _validate_hash(model_file, expected_hash, f"model file {relative_name}")

    result = {
        "artifact_id": manifest["artifact_id"],
        "schema_version": manifest["schema_version"],
        "kb_size": row_count,
        "embedding_shape": list(embeddings.shape),
        "model_id": model_spec.get("id", "unknown"),
    }
    if formal:
        result["embedding_dtype"] = str(embeddings.dtype)
    return result
