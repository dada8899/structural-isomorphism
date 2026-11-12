#!/usr/bin/env python3
"""Generate the committed TypeScript API surface without a shell command hop."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = PROJECT_ROOT / "web" / "backend" / "schemas.py"
TOOL_ROOT = PROJECT_ROOT / "scripts" / "types-generator"
LOCKFILE = TOOL_ROOT / "package-lock.json"
DECLARATION_FLOOR = 15
JSON2TS_VERSION = "15.0.4"
JSON2TS_CLI_SHA256 = "9c9a24bc47f7b45ecfaa7baf3b3c83a89a19d65f815bce8c4ad20a024a55fc30"
EXECUTABLE_MAGICS = (
    b"\x7fELF",
    b"\xcf\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object: {path}")
    return value


def _verified_json2ts() -> Path:
    declared = _read_json(TOOL_ROOT / "package.json")
    locked = _read_json(LOCKFILE)
    installed_path = TOOL_ROOT / "node_modules" / "json-schema-to-typescript"
    installed = _read_json(installed_path / "package.json")
    lock_packages = locked.get("packages")
    if not isinstance(lock_packages, dict):
        raise RuntimeError("package-lock.json has no packages inventory")
    root_lock = lock_packages.get("")
    package_lock = lock_packages.get("node_modules/json-schema-to-typescript")
    expected = {"json-schema-to-typescript": JSON2TS_VERSION}
    if declared.get("dependencies") != expected:
        raise RuntimeError("types-generator package.json dependency drift")
    if not isinstance(root_lock, dict) or root_lock.get("dependencies") != expected:
        raise RuntimeError("types-generator root lock dependency drift")
    if not isinstance(package_lock, dict) or package_lock.get("version") != JSON2TS_VERSION:
        raise RuntimeError("json-schema-to-typescript lock version drift")
    if installed.get("version") != JSON2TS_VERSION:
        raise RuntimeError("installed json-schema-to-typescript version drift")
    binary_map = installed.get("bin")
    if not isinstance(binary_map, dict) or set(binary_map) != {"json2ts"}:
        raise RuntimeError("json2ts executable declaration drift")
    if installed_path.is_symlink():
        raise RuntimeError("installed json2ts package must not be a symlink")
    package_root = installed_path.resolve(strict=True)
    declared_binary = installed_path / binary_map["json2ts"]
    if declared_binary.is_symlink() or not declared_binary.is_file():
        raise RuntimeError("json2ts package entrypoint must be a regular file")
    expected_binary = declared_binary.resolve(strict=True)
    if not expected_binary.is_relative_to(package_root):
        raise RuntimeError("json2ts package entrypoint escaped its package")
    linked_binary = (TOOL_ROOT / "node_modules" / ".bin" / "json2ts").resolve(
        strict=True
    )
    if linked_binary != expected_binary or not os.access(linked_binary, os.X_OK):
        raise RuntimeError("json2ts executable is not bound to the locked package")
    if hashlib.sha256(expected_binary.read_bytes()).hexdigest() != JSON2TS_CLI_SHA256:
        raise RuntimeError("json2ts package entrypoint content drift")
    return linked_binary


def _verified_node() -> Path:
    candidate = shutil.which("node")
    if not candidate:
        raise RuntimeError("node is not available")
    node = Path(candidate).resolve(strict=True)
    if not node.is_file() or not os.access(node, os.X_OK):
        raise RuntimeError("node must resolve to an executable regular file")
    with node.open("rb") as handle:
        executable_magic = handle.read(4)
    if not executable_magic.startswith(EXECUTABLE_MAGICS):
        raise RuntimeError("node must be a native executable, not a wrapper script")
    safe_env = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    version = subprocess.run(
        [str(node), "--version"], capture_output=True, text=True,
        timeout=10, check=False, env=safe_env,
    )
    match = re.fullmatch(r"v([0-9]+)\.[0-9]+\.[0-9]+\n?", version.stdout)
    if version.returncode != 0 or match is None or int(match.group(1)) < 20:
        raise RuntimeError("node version is outside the supported runtime contract")
    identity = subprocess.run(
        [str(node), "-p", "process.execPath"], capture_output=True, text=True,
        timeout=10, check=False, env=safe_env,
    )
    if identity.returncode != 0 or Path(identity.stdout.strip()).resolve() != node:
        raise RuntimeError("node runtime identity does not match its executable")
    return node


def _schema_json() -> str:
    from pydantic2ts.cli import script as pydantic_generator

    module = pydantic_generator._import_module(str(SCHEMAS))
    models = pydantic_generator._extract_pydantic_models(module)
    if not models:
        raise RuntimeError("no Pydantic models found")
    return pydantic_generator._generate_json_schema(models)


def _clean_output(path: Path) -> bytes:
    from pydantic2ts.cli import script as pydantic_generator

    pydantic_generator._clean_output_file(str(path))
    content = path.read_bytes()
    declarations = sum(
        line.startswith((b"export interface ", b"export type "))
        for line in content.splitlines()
    )
    if declarations < DECLARATION_FLOOR:
        raise RuntimeError(f"generated only {declarations} TypeScript declarations")
    return content


def _atomic_replace(path: Path, content: bytes) -> None:
    parent = path.parent.resolve(strict=True)
    temporary: Path | None = None
    descriptor = -1
    try:
        descriptor, name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=parent
        )
        temporary = Path(name)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except OSError:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        raise


def generate(output: Path) -> None:
    json2ts = _verified_json2ts()
    node = _verified_node()
    output = output.expanduser().absolute()
    with tempfile.TemporaryDirectory(prefix="structural-types-") as workspace:
        workdir = Path(workspace)
        schema_path = workdir / "schema.json"
        generated_path = workdir / "generated.ts"
        schema_path.write_text(_schema_json(), encoding="utf-8")
        completed = subprocess.run(
            [
                str(node), str(json2ts), "-i", str(schema_path),
                "-o", str(generated_path),
                "--bannerComment", "",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        )
        if completed.returncode != 0:
            raise RuntimeError(f"json2ts failed with exit code {completed.returncode}")
        _atomic_replace(output, _clean_output(generated_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        generate(args.output)
    except Exception as exc:
        print(
            json.dumps(
                {"event": "types.generation_failed", "error": str(exc)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps({"event": "types.generated", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
