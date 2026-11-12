"""Supervise the one approved llama child and the private gateway in one unit."""
from dataclasses import dataclass
import grp
import hashlib
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import stat
import struct
import subprocess
import sys
import threading
import time

from .local_answer_gateway import Gateway, GatewayUnavailable, MAIN_UID, _listener_parent, private_listener
from .local_answer_inference import (
    LlamaUnixBackend, _INFERENCE_SOCKET, _MODEL_ALIAS, _open_private, _response, _send,
)
from .local_answer_transport import _WORKER
from .provider_schemas import ProviderFailure, strict_json

_BUNDLE = Path("/opt/structural-first-answer/artifacts")
_PIN = Path("/opt/structural-first-answer/release/first-answer-artifact.sha256")
_READY_SECONDS = 75.0
_MANIFEST_CAP = 32768
_MODEL_CAP = 6 * 1024**3
_MEMBER_CAP = 256 * 1024**2
_HASH = re.compile(r"[a-f0-9]{64}")
_MEMBER = re.compile(r"bin/(?:llama-server|lib[A-Za-z0-9._-]+\.so(?:\.[0-9]+)*)|model/model\.gguf")
_ENV = {
    "PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LANG": "C.UTF-8",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
}


@dataclass(frozen=True, slots=True)
class Artifacts:
    engine: Path
    model: Path


def _trusted_dir(path, owner):
    entry = os.lstat(path)
    if not stat.S_ISDIR(entry.st_mode) or entry.st_uid != owner or entry.st_mode & 0o022:
        raise GatewayUnavailable("unsafe_artifact_directory")


def _trusted_file(path, owner, cap, *, executable=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
    try:
        entry = os.fstat(fd)
        if (not stat.S_ISREG(entry.st_mode) or entry.st_uid != owner or entry.st_mode & 0o7022
                or entry.st_nlink != 1 or not 1 <= entry.st_size <= cap
                or (executable and not entry.st_mode & 0o111)):
            raise GatewayUnavailable("unsafe_artifact_file")
        return os.fdopen(fd, "rb"), entry
    except BaseException:
        os.close(fd)
        raise


def verify_artifacts(root, pin, *, owner=0):
    """Verify one operator-pinned manifest and every regular bundle member."""
    for directory in (root.parent, root, root / "bin", root / "model", pin.parent):
        _trusted_dir(directory, owner)
    pin_file, _ = _trusted_file(pin, owner, 65)
    with pin_file:
        pinned = pin_file.read(66).decode("ascii").strip()
    if not _HASH.fullmatch(pinned):
        raise GatewayUnavailable("artifact_pin_invalid")
    manifest_file, _ = _trusted_file(root / "manifest.json", owner, _MANIFEST_CAP)
    with manifest_file:
        raw = manifest_file.read(_MANIFEST_CAP + 1)
    if hashlib.sha256(raw).hexdigest() != pinned:
        raise GatewayUnavailable("artifact_manifest_mismatch")
    try:
        manifest = strict_json(raw, _MANIFEST_CAP)
    except ProviderFailure:
        raise GatewayUnavailable("artifact_manifest_invalid") from None
    if (type(manifest) is not dict or set(manifest) != {"schema_version", "files"}
            or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
            or type(manifest["files"]) is not dict or not 2 <= len(manifest["files"]) <= 64):
        raise GatewayUnavailable("artifact_manifest_invalid")
    files = manifest["files"]
    if (not {"bin/llama-server", "model/model.gguf"}.issubset(files)
            or set(os.listdir(root)) != {"bin", "model", "manifest.json"}
            or set(files) != {f"{name}/{item}" for name in ("bin", "model") for item in os.listdir(root / name)}):
        raise GatewayUnavailable("artifact_members_mismatch")
    for name, spec in files.items():
        if (not _MEMBER.fullmatch(name) or type(spec) is not dict or set(spec) != {"sha256", "size"}
                or type(spec["sha256"]) is not str or not _HASH.fullmatch(spec["sha256"])
                or type(spec["size"]) is not int):
            raise GatewayUnavailable("artifact_member_invalid")
        cap = _MODEL_CAP if name.startswith("model/") else _MEMBER_CAP
        file, entry = _trusted_file(root / name, owner, cap, executable=name == "bin/llama-server")
        with file:
            if spec["size"] != entry.st_size or hashlib.file_digest(file, "sha256").hexdigest() != spec["sha256"]:
                raise GatewayUnavailable("artifact_member_mismatch")
    return Artifacts(root / "bin/llama-server", root / "model/model.gguf")


def _argv(artifacts, endpoint):
    return [str(artifacts.engine), "-m", str(artifacts.model), "--host", str(endpoint), "--alias", _MODEL_ALIAS,
            "-ngl", "0", "-t", "4", "-tb", "4", "-c", "4096", "-np", "1", "--no-context-shift",
            "--reasoning-budget", "0", "--chat-template-kwargs", '{"enable_thinking":false}',
            "--no-webui", "--no-slots", "--no-cache-prompt", "--cache-ram", "0", "--log-disable"]


def _socket_inode(path, uid):
    entry = os.lstat(path)
    if (not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != uid or entry.st_nlink != 1
            or stat.S_IMODE(entry.st_mode) != 0o600):
        raise GatewayUnavailable("inference_socket_mode_invalid")
    return entry.st_dev, entry.st_ino


@dataclass(frozen=True, slots=True)
class _BootDeadline:
    end: float
    stopping: threading.Event

    def check(self):
        remain = self.end - time.monotonic()
        if self.stopping.is_set() or remain <= 0:
            raise GatewayUnavailable("inference_readiness_expired")
        return remain


def _health(endpoint, uid, pid, deadline, remember):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        _open_private(conn, deadline, endpoint, uid, expected_pid=pid)
        remember(_socket_inode(endpoint, uid))
        _send(conn, deadline, b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        status, headers, raw = _response(conn, deadline)
    if status != 200 or headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
        return False
    try:
        result = strict_json(raw, 1024)
    except ProviderFailure:
        return False
    return type(result) is dict and result.get("status") == "ok"


def _wait_ready(proc, endpoint, uid, stopping, timeout, remember):
    end = time.monotonic() + timeout
    deadline = _BootDeadline(end, stopping)
    while True:
        deadline.check()
        if proc.poll() is not None:
            raise GatewayUnavailable("inference_process_exited")
        try:
            identity = _socket_inode(endpoint, uid)
        except FileNotFoundError:
            stopping.wait(.1)
            continue
        try:
            probe = _BootDeadline(min(end, time.monotonic() + .5), stopping)
            ready = _health(endpoint, uid, proc.pid, probe, remember)
        except (GatewayUnavailable, OSError, struct.error):
            ready = False
        if ready and identity == _socket_inode(endpoint, uid):
            return identity
        stopping.wait(.1)


def _stop(proc):
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def run(artifacts, stopping, *, endpoint=_INFERENCE_SOCKET, timeout=_READY_SECONDS, listener=private_listener):
    """Exactly one child, with a narrow environment and no inherited I/O."""
    uid, gid = os.geteuid(), os.getegid()
    parent = _listener_parent(endpoint, uid, gid)
    if os.path.lexists(endpoint):
        raise GatewayUnavailable("inference_socket_already_exists")
    environment = {**_ENV, "LD_LIBRARY_PATH": str(artifacts.engine.parent)}
    proc = subprocess.Popen(_argv(artifacts, endpoint), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL, close_fds=True, env=environment, cwd=artifacts.engine.parent,
                            umask=0o177)
    identity = None
    watcher = None
    died = threading.Event()
    def remember(observed):
        nonlocal identity
        if identity is not None and identity != observed:
            raise GatewayUnavailable("inference_socket_replaced")
        identity = observed
    try:
        _wait_ready(proc, endpoint, uid, stopping, timeout, remember)
        def watch():
            proc.wait()
            if not stopping.is_set():
                died.set()
            stopping.set()
        watcher = threading.Thread(target=watch, name="first-answer-inference-watch", daemon=True)
        watcher.start()
        backend = LlamaUnixBackend(stopping.set, expected_pid=proc.pid)
        with listener() as sock:
            Gateway(backend).serve(sock, stopping)
        return 1 if died.is_set() or backend.quarantined else 0
    finally:
        stopping.set()
        try:
            _stop(proc)
        finally:
            if watcher is not None and watcher.ident is not None:
                watcher.join(1)
            if identity is not None:
                try:
                    if _listener_parent(endpoint, uid, gid) == parent and _socket_inode(endpoint, uid) == identity:
                        endpoint.unlink()
                except (OSError, GatewayUnavailable):
                    pass


def main():
    if sys.platform != "linux":
        return 1
    stopping = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stopping.set())
    try:
        worker = pwd.getpwnam(_WORKER)
        gid = grp.getgrnam("structural").gr_gid
        if (os.geteuid() <= 0 or os.getuid() != os.geteuid() or os.geteuid() != worker.pw_uid
                or worker.pw_uid == MAIN_UID or os.getegid() != gid or any(group != gid for group in os.getgroups())):
            return 1
        return run(verify_artifacts(_BUNDLE, _PIN), stopping)
    except (GatewayUnavailable, OSError, KeyError, ValueError, struct.error, subprocess.SubprocessError):
        return 1
