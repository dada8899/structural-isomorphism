#!/bin/bash -p
# Install or verify the forced-command deployment route without trusting PATH.
set -euo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset BASH_ENV ENV CDPATH GLOBIGNORE

MODE=install
if [[ "${1:-}" == "--check" && "$#" -eq 1 ]]; then
  MODE=check
elif [[ "$#" -ne 0 ]]; then
  echo "usage: install-deploy-dispatcher.sh [--check]" >&2
  exit 2
fi

SCRIPT_PATH="${BASH_SOURCE[0]}"
[[ "$SCRIPT_PATH" == /* && "$SCRIPT_PATH" == */* ]] || {
  echo "[dispatcher-install] ERROR: installer must use an absolute path" >&2
  exit 1
}

SOURCE_DIR="${SCRIPT_PATH%/*}"
INSTALL_DIR="${STRUCTURAL_DEPLOY_INSTALL_DIR:-/root/scripts}"
AUTHORIZED_KEYS="${STRUCTURAL_DEPLOY_AUTHORIZED_KEYS:-/root/.ssh/authorized_keys}"
PUBLIC_KEY_FILE="${STRUCTURAL_DEPLOY_PUBLIC_KEY_FILE:-}"
[[ -n "$PUBLIC_KEY_FILE" ]] || {
  echo "[dispatcher-install] ERROR: STRUCTURAL_DEPLOY_PUBLIC_KEY_FILE is required" >&2
  exit 2
}

exec /usr/bin/python3 -I - "$MODE" "$SOURCE_DIR" "$INSTALL_DIR" \
  "$AUTHORIZED_KEYS" "$PUBLIC_KEY_FILE" <<'PY'
from __future__ import annotations

import base64
import binascii
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


mode, source_raw, install_raw, authorized_raw, public_key_raw = sys.argv[1:]
source_dir = Path(source_raw)
install_dir = Path(install_raw)
authorized_keys = Path(authorized_raw)
public_key_file = Path(public_key_raw)
safe_absolute = re.compile(r"^/[A-Za-z0-9._/-]+$")


def fail(message: str) -> "NoReturn":
    raise SystemExit(f"[dispatcher-install] ERROR: {message}")


def require_safe_path(path: Path, *, leaf_may_be_missing: bool = False) -> None:
    if not path.is_absolute() or not safe_absolute.fullmatch(str(path)):
        fail(f"unsafe absolute path: {path}")
    current = Path(path.anchor)
    parts = path.parts[1:]
    for index, part in enumerate(parts):
        current /= part
        is_leaf = index == len(parts) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            if is_leaf and leaf_may_be_missing:
                return
            fail(f"path component is missing: {current}")
        if stat.S_ISLNK(info.st_mode):
            fail(f"symlink path component is forbidden: {current}")


def read_public_key() -> tuple[str, str]:
    require_safe_path(public_key_file)
    info = public_key_file.lstat()
    if not stat.S_ISREG(info.st_mode):
        fail("public key input must be a regular file")
    lines = [line.strip() for line in public_key_file.read_text().splitlines() if line.strip()]
    if len(lines) != 1:
        fail("public key input must contain exactly one non-empty line")
    fields = lines[0].split()
    allowed = {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"}
    if len(fields) < 2 or fields[0] not in allowed:
        fail("unsupported or malformed public key")
    try:
        decoded = base64.b64decode(fields[1] + "=" * (-len(fields[1]) % 4), validate=True)
    except (binascii.Error, ValueError):
        fail("public key payload is not canonical base64")
    if len(decoded) < 16:
        fail("public key payload is too short")
    try:
        validation = subprocess.run(
            ["/usr/bin/ssh-keygen", "-l", "-f", str(public_key_file)],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin"},
        )
    except OSError:
        fail("system ssh-keygen is unavailable")
    if validation.returncode != 0:
        fail("public key input is not accepted by ssh-keygen")
    return fields[0], fields[1]


def stage_write(path: Path, payload: bytes, permissions: int) -> Path:
    descriptor, temporary_raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_raw)
    try:
        os.fchmod(descriptor, permissions)
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        return temporary
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise


def commit_stage(temporary: Path, target: Path) -> None:
    if target.is_symlink() or (target.exists() and not target.is_file()):
        fail(f"refusing to replace unsafe target: {target}")
    os.replace(temporary, target)


def fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def key_identity(line: str) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    try:
        fields = shlex.split(stripped, posix=True)
    except ValueError:
        fail("authorized_keys contains malformed quoting")
    for index, field in enumerate(fields[:-1]):
        if field in {"ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256"}:
            return field, fields[index + 1]
    return None


require_safe_path(source_dir)
require_safe_path(install_dir)
require_safe_path(authorized_keys, leaf_may_be_missing=True)
if not source_dir.is_dir() or not install_dir.is_dir() or not authorized_keys.parent.is_dir():
    fail("source, install, and authorized_keys parent directories must exist")

key_type, key_blob = read_public_key()
command_path = install_dir / "deploy-dispatcher.sh"
forced_line = f'restrict,command="{command_path}" {key_type} {key_blob} structural-deploy'
# Runtime dependencies are committed before their entrypoints, the dispatcher
# follows, and authorized_keys is last. Every intermediate state stays closed.
sources = [
    (
        install_dir / "install-nginx-privacy-vhost.sh",
        source_dir / "install-nginx-privacy-vhost.sh",
    ),
    (
        install_dir / "deploy-phase-detector-vps.sh",
        source_dir / "deploy-phase-detector-vps.sh",
    ),
    (
        install_dir / "deploy-phase-detector-entrypoint.sh",
        source_dir / "deploy-phase-detector-entrypoint.sh",
    ),
    (install_dir / "deploy-beta-backend.sh", source_dir / "deploy-beta-backend.sh"),
    (install_dir / "deploy-dispatcher.sh", source_dir / "deploy-dispatcher.sh"),
]
for target, source in sources:
    require_safe_path(source)
    if not source.is_file() or source.is_symlink():
        fail(f"unsafe source script: {source}")
    if target.is_symlink() or (target.exists() and not target.is_file()):
        fail(f"unsafe installed script: {target}")
if authorized_keys.exists() and (
    authorized_keys.is_symlink() or not authorized_keys.is_file()
):
    fail("authorized_keys must be a regular non-symlink file")

existing_lines = authorized_keys.read_text().splitlines() if authorized_keys.exists() else []
matches = [index for index, line in enumerate(existing_lines) if key_identity(line) == (key_type, key_blob)]
if len(matches) > 1:
    fail("deployment public key appears more than once in authorized_keys")

if matches:
    existing_lines[matches[0]] = forced_line
else:
    existing_lines.append(forced_line)
authorized_payload = ("\n".join(existing_lines) + "\n").encode()


def verify_installation() -> None:
    for target, source in sources:
        if (
            not target.is_file()
            or target.is_symlink()
            or target.read_bytes() != source.read_bytes()
        ):
            fail(f"installed script differs from tracked source: {target}")
        if stat.S_IMODE(target.stat().st_mode) != 0o755:
            fail(f"installed script mode is not 0755: {target}")
    if not authorized_keys.is_file() or authorized_keys.is_symlink():
        fail("authorized_keys must be a regular non-symlink file")
    if stat.S_IMODE(authorized_keys.stat().st_mode) != 0o600:
        fail("authorized_keys mode is not 0600")
    installed_lines = authorized_keys.read_text().splitlines()
    if installed_lines.count(forced_line) != 1:
        fail("forced-command key line is missing or non-canonical")
    installed_matches = [
        line for line in installed_lines
        if key_identity(line) == (key_type, key_blob)
    ]
    if installed_matches != [forced_line]:
        fail("deployment public key is not uniquely restricted")


if mode == "install":
    plans = [
        (target, source.read_bytes(), 0o755) for target, source in sources
    ] + [(authorized_keys, authorized_payload, 0o600)]
    originals = {
        path: (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
        if path.exists() else None
        for path, _payload, _permissions in plans
    }
    staged: list[tuple[Path, Path]] = []
    committed: list[Path] = []
    try:
        for path, payload, permissions in plans:
            staged.append((stage_write(path, payload, permissions), path))
        for temporary, target in staged:
            commit_stage(temporary, target)
            committed.append(target)
            fsync_parent(target)
        verify_installation()
    except BaseException:
        rollback_failed = False
        for target in reversed(committed):
            original = originals[target]
            try:
                if original is None:
                    target.unlink(missing_ok=True)
                    fsync_parent(target)
                else:
                    payload, permissions = original
                    commit_stage(stage_write(target, payload, permissions), target)
                    fsync_parent(target)
            except BaseException:
                rollback_failed = True
        if rollback_failed:
            fail("installation failed and rollback could not restore every target")
        raise
    finally:
        for temporary, _target in staged:
            temporary.unlink(missing_ok=True)
elif mode != "check":
    fail("unknown installer mode")

verify_installation()
print(f"[dispatcher-install] {mode} verified")
PY
