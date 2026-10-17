"""Fail-closed validation for the production KB/model artifact bundle."""

from __future__ import annotations

import hashlib
import io
import os
import stat
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
    if formal:
        with open_formal_artifact_bundle(
            manifest_path, kb_path=kb_path, embeddings_path=embeddings_path, model_path=model_path
        ) as snapshot:
            return dict(snapshot.metadata)
    manifest_file = Path(manifest_path)
    kb_file = Path(kb_path)
    embeddings_file = Path(embeddings_path)
    model_dir = Path(model_path)
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

    with kb_file.open("rb") as handle:
        prefix = handle.read(160)
    if prefix.startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ArtifactValidationError(f"knowledge base is a Git LFS pointer: {kb_file}")

    kb_spec = manifest.get("kb") or {}
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
    for relative_name, expected_hash in (model_spec.get("required_files") or {}).items():
        relative_path = Path(relative_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ArtifactValidationError(f"unsafe model file path: {relative_name}")
        model_file = model_dir / relative_path
        _require_file(model_file, f"model file {relative_name}")
        _validate_hash(model_file, expected_hash, f"model file {relative_name}")

    result = {
        "artifact_id": manifest["artifact_id"],
        "schema_version": manifest["schema_version"],
        "kb_size": row_count,
        "embedding_shape": list(embeddings.shape),
        "model_id": model_spec.get("id", "unknown"),
    }
    return result


# This profile deliberately supports only the approved structural-v2 layout.
# Read-only mounts still require the deployment contract to close writable
# aliases/project producers. These checks do not claim to defend against root.
FORMAL_MODEL_FILES = frozenset({
    "1_Pooling/config.json", "README.md", "config.json",
    "config_sentence_transformers.json", "model.safetensors", "modules.json",
    "sentence_bert_config.json", "tokenizer.json", "tokenizer_config.json",
})
FORMAL_PAYLOAD_FILES = frozenset({
    "manifest.json", "kb-expanded.jsonl", "kb_v2_embeddings.npy",
    "kb_v2_embeddings_ids.json",
}) | frozenset("structural-v2/" + name for name in FORMAL_MODEL_FILES)


def _strict_json(data: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ArtifactValidationError("duplicate JSON key")
            result[key] = value
        return result

    def invalid(_value):
        raise ArtifactValidationError("nonfinite JSON value")

    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def _digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def _readonly_fd(fd):
    # fstatvfs checks the opened mount, not a replaceable pathname.
    if not os.fstatvfs(fd).f_flag & os.ST_RDONLY:
        raise ArtifactValidationError("formal artifacts require a read-only filesystem")


def _open_directory(path):
    path = Path(path)
    if not path.is_absolute() or ".." in path.parts:
        raise ArtifactValidationError("formal artifact path must be absolute and canonical")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def _read_member(root_fd, name, spec, *, retain=True):
    parts = Path(name).parts
    if not parts or Path(name).is_absolute() or any(p in (".", "..") for p in parts):
        raise ArtifactValidationError("unsafe formal member")
    parent = os.dup(root_fd)
    fd = None
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ArtifactValidationError("formal members must be regular files without hard links")
        _readonly_fd(fd)
        if info.st_size != spec["bytes"]:
            raise ArtifactValidationError("formal member size mismatch")
        digest = hashlib.sha256()
        chunks = []
        size = 0
        while chunk := os.read(fd, 1024 * 1024):
            size += len(chunk)
            if size > spec["bytes"]:
                raise ArtifactValidationError("formal member changed while reading")
            digest.update(chunk)
            if retain:
                chunks.append(chunk)
        after = os.fstat(fd)
        if (size != spec["bytes"] or digest.hexdigest() != spec["sha256"]
                or (after.st_size, after.st_mtime_ns, after.st_ctime_ns, after.st_nlink)
                != (info.st_size, info.st_mtime_ns, info.st_ctime_ns, 1)):
            raise ArtifactValidationError("formal member checksum or identity mismatch")
        return b"".join(chunks) if retain else None
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent)


def _members(root_fd, prefix=""):
    result = set()
    for name in os.listdir(root_fd):
        info = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        relative = prefix + name
        if stat.S_ISDIR(info.st_mode):
            # Only these two directories belong to the closed payload.
            if relative not in ("structural-v2", "structural-v2/1_Pooling"):
                raise ArtifactValidationError("extra formal artifact directory")
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=root_fd)
            try:
                _readonly_fd(child)
                result.update(_members(child, relative + "/"))
            finally:
                os.close(child)
        elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
            result.add(relative)
        else:
            raise ArtifactValidationError("nonregular or linked formal artifact member")
    return result


class FormalArtifactSnapshot:
    """Validated in-memory data plus live FDs anchoring the read-only model."""

    def __init__(self):
        self.root_fd = None
        self.model_fd = None

    @property
    def model_path(self):
        return f"/proc/self/fd/{self.model_fd}"

    def check_model(self):
        _readonly_fd(self.root_fd)
        _readonly_fd(self.model_fd)
        if _members(self.root_fd) != FORMAL_PAYLOAD_FILES:
            raise ArtifactValidationError("formal artifact member set changed")
        # Additional integrity check; read-only publication and closed writable
        # aliases provide the immutability boundary, not repeated hashing.
        for name in FORMAL_MODEL_FILES:
            _read_member(self.model_fd, name, self.specs["structural-v2/" + name], retain=False)

    def close(self):
        for name in ("model_fd", "root_fd"):
            fd = getattr(self, name)
            if fd is not None:
                setattr(self, name, None)
                os.close(fd)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def open_formal_artifact_bundle(manifest_path, *, kb_path, embeddings_path, model_path):
    """Read each data input once; never return references to mutable source paths."""
    snapshot = FormalArtifactSnapshot()
    manifest_parent = None
    try:
        kb_path, embeddings_path, model_path, manifest_path = map(
            Path, (kb_path, embeddings_path, model_path, manifest_path)
        )
        root = kb_path.parent
        if (kb_path.name != "kb-expanded.jsonl"
                or embeddings_path != root / "kb_v2_embeddings.npy"
                or model_path != root / "structural-v2"
                or not manifest_path.is_absolute() or manifest_path.is_relative_to(root)):
            raise ArtifactValidationError("formal artifact paths do not match the closed layout")
        snapshot.root_fd = _open_directory(root)
        _readonly_fd(snapshot.root_fd)
        manifest_parent = _open_directory(manifest_path.parent)
        # A manifest is outside the payload to avoid self-reference. Read it
        # through a no-follow FD; only the bytes parsed below determine policy.
        fd = os.open(manifest_path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=manifest_parent)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > 1024 * 1024:
                raise ArtifactValidationError("invalid formal manifest file")
            _readonly_fd(fd)
            with os.fdopen(fd, "rb", closefd=False) as stream:
                manifest = _strict_json(stream.read())
        finally:
            os.close(fd)
        if (not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int
                or manifest["schema_version"] != 2
                or not isinstance(manifest.get("artifact_id"), str)
                or not manifest["artifact_id"].strip()):
            raise ArtifactValidationError("formal artifacts require schema v2 identity")
        payload = manifest["payload"]
        files = payload["files"]
        if (not isinstance(files, list) or payload.get("exact_members") is not True
                or len(files) != 13):
            raise ArtifactValidationError("formal payload must contain exactly thirteen members")
        specs = {}
        for spec in files:
            name = spec["path"]
            if (not isinstance(name, str) or name not in FORMAL_PAYLOAD_FILES or name in specs
                    or type(spec.get("bytes")) is not int or spec["bytes"] <= 0
                    or not _digest(spec.get("sha256"))):
                raise ArtifactValidationError("invalid or duplicate formal payload member")
            specs[name] = spec
        if (set(specs) != FORMAL_PAYLOAD_FILES
                or type(payload.get("total_bytes")) is not int
                or payload["total_bytes"] != sum(s["bytes"] for s in specs.values())
                or _members(snapshot.root_fd) != FORMAL_PAYLOAD_FILES):
            raise ArtifactValidationError("formal payload member or size set mismatch")
        snapshot.specs = specs
        model = manifest["model"]
        required = model["required_files"]
        binding = manifest["source_binding"]
        if (not isinstance(model.get("id"), str) or not model["id"].strip()
                or set(required) != FORMAL_MODEL_FILES
                or any(required[n] != specs["structural-v2/" + n]["sha256"] for n in required)
                or type(binding.get("payload_files")) is not int or binding["payload_files"] != 13
                or type(binding.get("model_files")) is not int or binding["model_files"] != 9
                or binding.get("legacy_production_manifest_sha256") != specs["manifest.json"]["sha256"]
                or not _digest(binding.get("transfer_manifest_sha256"))):
            raise ArtifactValidationError("formal model/source binding is incomplete")
        captured = {}
        for name, spec in specs.items():
            # Model weights stay on the read-only filesystem; no second 400MB
            # Python copy. All other input parsing uses these verified bytes.
            data = _read_member(snapshot.root_fd, name, spec, retain=not name.endswith("model.safetensors"))
            if data is not None:
                captured[name] = data
        kb_spec, vector_spec = manifest["kb"], manifest["embeddings"]
        if (kb_spec.get("filename") != kb_path.name
                or vector_spec.get("filename") != embeddings_path.name
                or kb_spec.get("sha256") != specs[kb_path.name]["sha256"]
                or vector_spec.get("sha256") != specs[embeddings_path.name]["sha256"]):
            raise ArtifactValidationError("formal data specs disagree with payload")
        legacy = _strict_json(captured["manifest.json"])
        if (legacy.get("schema_version") != 1 or legacy.get("artifact_id") != manifest["artifact_id"]
                or any(legacy.get(k) != manifest.get(k) for k in ("kb", "embeddings", "generation"))
                or legacy.get("model", {}).get("id") != model["id"]
                or not all(required.get(k) == v for k, v in legacy["model"]["required_files"].items())):
            raise ArtifactValidationError("formal manifest differs from its bound legacy source")
        transfer = {"artifact_id": manifest["artifact_id"], "files": files,
                    "schema_version": 1, "total_bytes": payload["total_bytes"]}
        transfer_bytes = (json.dumps(transfer, sort_keys=True, separators=(",", ":")) + "\n").encode()
        if hashlib.sha256(transfer_bytes).hexdigest() != binding["transfer_manifest_sha256"]:
            raise ArtifactValidationError("formal transfer source binding mismatch")
        rows = []
        for line in captured[kb_path.name].splitlines():
            if not line.strip() or line.lstrip().startswith(b"//"):
                continue
            row = _strict_json(line)
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]
                    or not isinstance(row.get("description"), str) or not row["description"].strip()):
                raise ArtifactValidationError("invalid formal knowledge base row")
            rows.append(row)
        ids = [row["id"] for row in rows]
        if (type(kb_spec.get("row_count")) is not int or kb_spec["row_count"] <= 0
                or type(kb_spec.get("unique_id_count")) is not int
                or len(rows) != kb_spec["row_count"] or len(set(ids)) != kb_spec["unique_id_count"]
                or kb_spec["unique_id_count"] != kb_spec["row_count"]
                or _strict_json(captured["kb_v2_embeddings_ids.json"]) != ids):
            raise ArtifactValidationError("formal ordered knowledge base IDs mismatch")
        matrix = np.load(io.BytesIO(captured[embeddings_path.name]), allow_pickle=False)
        shape = vector_spec.get("shape")
        if (not isinstance(shape, list) or len(shape) != 2
                or any(type(n) is not int or n <= 0 for n in shape)
                or matrix.ndim != 2 or list(matrix.shape) != shape or matrix.shape[0] != len(rows)
                or not np.issubdtype(matrix.dtype, np.floating) or not np.isfinite(matrix).all()
                or str(matrix.dtype) != vector_spec.get("dtype")):
            raise ArtifactValidationError("invalid formal embeddings matrix")
        matrix.flags.writeable = False
        snapshot.rows, snapshot.embeddings = rows, matrix
        _validate_model_references(captured)
        snapshot.model_fd = os.open("structural-v2", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                    dir_fd=snapshot.root_fd)
        _readonly_fd(snapshot.model_fd)
        snapshot.metadata = {
            "artifact_id": manifest["artifact_id"], "schema_version": 2,
            "kb_size": len(rows), "embedding_shape": list(matrix.shape),
            "embedding_dtype": str(matrix.dtype), "model_id": model["id"],
        }
        return snapshot
    except BaseException:
        snapshot.close()
        raise
    finally:
        if manifest_parent is not None:
            os.close(manifest_parent)


def _validate_model_references(captured):
    def model_json(name):
        return _strict_json(captured["structural-v2/" + name])

    modules = model_json("modules.json")
    # The approved saved model has only the standard local transformer and
    # pooling modules. No dynamic module/file loading or extra module kwargs.
    if (not isinstance(modules, list) or len(modules) != 2
            or modules[0] != {"idx": 0, "name": "0", "path": "", "type": "sentence_transformers.base.modules.transformer.Transformer"}
            or modules[1] != {"idx": 1, "name": "1", "path": "1_Pooling", "type": "sentence_transformers.sentence_transformer.modules.pooling.Pooling"}):
        raise ArtifactValidationError("unapproved formal sentence-transformer modules")
    for name in FORMAL_MODEL_FILES - {"README.md", "model.safetensors", "modules.json"}:
        config = model_json(name)
        if not isinstance(config, dict):
            raise ArtifactValidationError("invalid formal model configuration")
        if any(config.get(k) is not None for k in ("auto_map", "custom_pipelines", "transformer_model_name",
                                      "tokenizer_name_or_path", "model_name_or_path", "tokenizer_file",
                                      "vocab_file", "merges_file", "special_tokens_map_file",
                                      "added_tokens_file", "model_args", "config_args", "tokenizer_args")):
            raise ArtifactValidationError("unbound formal model reference")
    config = model_json("config.json")
    tokenizer = model_json("tokenizer_config.json")
    if (config.get("model_type") != "bert" or config.get("architectures") != ["BertModel"]
            or tokenizer.get("tokenizer_class") not in (None, "BertTokenizer", "BertTokenizerFast")):
        raise ArtifactValidationError("unapproved formal model or tokenizer type")
