#!/usr/bin/env python3
"""Generate or verify the committed OpenAPI artifact deterministically."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import ModuleType


SCRIPT_PATH = Path(__file__).resolve()
PROJECT_ROOT = SCRIPT_PATH.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "web" / "backend"
DEFAULT_ARTIFACT = PROJECT_ROOT / "docs" / "api" / "openapi.json"
BACKEND_REQUIREMENTS = BACKEND_ROOT / "requirements.txt"
SCHEMA_RUNTIME_PACKAGES = ("fastapi", "pydantic", "starlette")
STABLE_HASH_SEED = "0"
STABLE_PROCESS_SENTINEL = "STRUCTURAL_OPENAPI_STABLE_PROCESS"


def _emit(event: str, **context: object) -> None:
    """Write a single structured diagnostic without leaking environment data."""
    print(json.dumps({"event": event, **context}, sort_keys=True), file=sys.stderr)


def _ensure_stable_hash_seed() -> None:
    """Re-exec before imports so set-backed FastAPI methods have stable order."""
    if (
        os.environ.get(STABLE_PROCESS_SENTINEL) == "1"
        and os.environ.get("PYTHONHASHSEED") == STABLE_HASH_SEED
    ):
        return
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = STABLE_HASH_SEED
    env[STABLE_PROCESS_SENTINEL] = "1"
    os.execve(
        sys.executable,
        [sys.executable, str(SCRIPT_PATH), *sys.argv[1:]],
        env,
    )


def _prepend_current_sources() -> None:
    """Put this checkout ahead of editable installs from another worktree."""
    source_roots = (
        PROJECT_ROOT,
        BACKEND_ROOT,
        PROJECT_ROOT / "packages" / "guarded-llm" / "src",
        PROJECT_ROOT / "packages" / "cross-judge" / "src",
        PROJECT_ROOT / "packages" / "reject-aware-critic" / "src",
        PROJECT_ROOT / "packages" / "soc-pipeline" / "src",
    )
    for source_root in reversed(source_roots):
        source = str(source_root)
        while source in sys.path:
            sys.path.remove(source)
        sys.path.insert(0, source)


def _locked_schema_runtime_versions() -> dict[str, str]:
    """Read exact schema-library pins from the production requirements."""
    requirements = BACKEND_REQUIREMENTS.read_text(encoding="utf-8")
    locked: dict[str, str] = {}
    for package in SCHEMA_RUNTIME_PACKAGES:
        pattern = re.compile(
            rf"^{re.escape(package)}(?:\[[^]]+\])?==([^\s#]+)\s*(?:#.*)?$",
            re.MULTILINE | re.IGNORECASE,
        )
        match = pattern.search(requirements)
        if match is None:
            raise RuntimeError(
                f"{BACKEND_REQUIREMENTS} must exactly pin {package} with =="
            )
        locked[package] = match.group(1)
    return locked


def _assert_schema_runtime_matches_release_target() -> None:
    """Reject artifacts generated outside the declared release dependency lock."""
    locked = _locked_schema_runtime_versions()
    mismatches: list[str] = []
    for package, expected in locked.items():
        try:
            actual = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            actual = "not-installed"
        if actual != expected:
            mismatches.append(f"{package}=={actual} (expected {expected})")
    if mismatches:
        raise RuntimeError(
            "OpenAPI schema runtime differs from the release target requirements: "
            + ", ".join(mismatches)
            + "; install web/backend/requirements.txt in the generator environment"
        )


def _module_file(module: ModuleType) -> Path | None:
    raw_path = getattr(module, "__file__", None)
    return Path(raw_path).resolve() if raw_path else None


def _assert_current_worktree_imports(main_module: ModuleType) -> None:
    """Fail if the generator accidentally imported a sibling checkout."""
    expected_main = (BACKEND_ROOT / "main.py").resolve()
    if _module_file(main_module) != expected_main:
        raise RuntimeError(
            f"main import escaped current worktree: {_module_file(main_module)}"
        )

    allowed_prefixes = {
        "api": (BACKEND_ROOT / "api").resolve(),
        "services": (BACKEND_ROOT / "services").resolve(),
        "structural_isomorphism": (PROJECT_ROOT / "structural_isomorphism").resolve(),
    }
    for name, module in tuple(sys.modules.items()):
        prefix = next(
            (
                candidate
                for candidate in allowed_prefixes
                if name == candidate or name.startswith(f"{candidate}.")
            ),
            None,
        )
        if prefix is None or module is None:
            continue
        module_path = _module_file(module)
        if module_path is not None and not module_path.is_relative_to(
            allowed_prefixes[prefix]
        ):
            raise RuntimeError(
                f"{name} import escaped current worktree: {module_path}"
            )


def _canonical_openapi_bytes() -> bytes:
    _prepend_current_sources()
    _assert_schema_runtime_matches_release_target()
    os.environ["STRUCTURAL_PROJECT_ROOT"] = str(PROJECT_ROOT)
    os.environ["STRUCTURAL_ENV"] = "dev"
    os.environ["AUTH_ENABLED"] = "false"

    import main as main_module

    _assert_current_worktree_imports(main_module)
    main_module.app.openapi_schema = None
    schema = main_module.app.openapi()
    if not isinstance(schema, dict) or not isinstance(schema.get("paths"), dict):
        raise RuntimeError("app.openapi() did not return a schema with paths")
    if not schema["paths"]:
        raise RuntimeError("app.openapi() returned an empty paths object")
    schemas = schema.get("components", {}).get("schemas")
    if not isinstance(schemas, dict) or not schemas:
        raise RuntimeError("app.openapi() returned no component schemas")

    operation_ids: dict[str, list[str]] = {}
    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if not isinstance(operation, dict) or "operationId" not in operation:
                continue
            operation_ids.setdefault(operation["operationId"], []).append(
                f"{method.upper()} {path}"
            )
    duplicates = {
        operation_id: locations
        for operation_id, locations in operation_ids.items()
        if len(locations) > 1
    }
    if duplicates:
        raise RuntimeError(f"duplicate OpenAPI operationId values: {duplicates}")

    serialized = json.dumps(
        schema,
        allow_nan=False,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    return f"{serialized}\n".encode("utf-8")


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write_artifact(path: Path, generated: bytes) -> int:
    temporary: Path | None = None
    file_descriptor = -1
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temporary = Path(temporary_name)
        with os.fdopen(file_descriptor, "wb") as handle:
            file_descriptor = -1
            handle.write(generated)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_fd = os.open(path.parent, directory_flags)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except OSError as exc:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        _emit("openapi.write_failed", artifact=str(path), error=str(exc))
        return 2
    _emit(
        "openapi.written",
        artifact=str(path),
        bytes=len(generated),
        sha256=_sha256(generated),
    )
    return 0


def _write_stdout(generated: bytes) -> int:
    try:
        sys.stdout.buffer.write(generated)
        sys.stdout.buffer.flush()
    except OSError as exc:
        _emit("openapi.stdout_failed", error=str(exc))
        return 2
    _emit(
        "openapi.stdout_written",
        bytes=len(generated),
        sha256=_sha256(generated),
    )
    return 0


def _assert_canonical_write_target(path: Path) -> None:
    if path != DEFAULT_ARTIFACT:
        raise RuntimeError("OpenAPI writes are restricted to the canonical artifact")
    for directory in (PROJECT_ROOT / "docs", DEFAULT_ARTIFACT.parent):
        if directory.is_symlink() or directory.resolve(strict=True) != directory:
            raise RuntimeError("canonical OpenAPI parent must not be a symlink")


def _check_artifact(path: Path, generated: bytes) -> int:
    try:
        committed = path.read_bytes()
    except OSError as exc:
        _emit("openapi.read_failed", artifact=str(path), error=str(exc))
        return 2
    if committed != generated:
        _emit(
            "openapi.out_of_sync",
            artifact=str(path),
            committed_bytes=len(committed),
            committed_sha256=_sha256(committed),
            generated_bytes=len(generated),
            generated_sha256=_sha256(generated),
        )
        return 1
    _emit(
        "openapi.in_sync",
        artifact=str(path),
        bytes=len(generated),
        sha256=_sha256(generated),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true", help="replace the artifact")
    action.add_argument("--check", action="store_true", help="require an exact match")
    action.add_argument("--stdout", action="store_true", help="emit generated JSON")
    parser.add_argument("--artifact", type=Path)
    args = parser.parse_args()

    _ensure_stable_hash_seed()
    artifact = (
        args.artifact.expanduser().resolve()
        if args.artifact is not None
        else DEFAULT_ARTIFACT
    )
    if args.stdout and args.artifact is not None:
        _emit("openapi.invalid_target", error="--stdout does not accept --artifact")
        return 2
    if args.write and artifact != DEFAULT_ARTIFACT:
        _emit(
            "openapi.invalid_target",
            artifact=str(artifact),
            error="--write is restricted to the canonical repository artifact",
        )
        return 2
    if args.write:
        try:
            _assert_canonical_write_target(artifact)
        except (OSError, RuntimeError) as exc:
            _emit("openapi.invalid_target", artifact=str(artifact), error=str(exc))
            return 2
    try:
        generated = _canonical_openapi_bytes()
    except Exception as exc:
        _emit(
            "openapi.generation_failed",
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return 2
    if args.write:
        return _write_artifact(artifact, generated)
    if args.stdout:
        return _write_stdout(generated)
    return _check_artifact(artifact, generated)


if __name__ == "__main__":
    raise SystemExit(main())
