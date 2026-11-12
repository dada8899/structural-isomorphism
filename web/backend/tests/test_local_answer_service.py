"""Root-pinned bundle, reviewed unit shape, and actual isolated child lifecycle."""
from configparser import ConfigParser
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shlex
import socket
import stat
import sys
import tempfile
import threading
import time

import pytest

from web.backend.research import local_answer_inference as inference, local_answer_service as service
from web.backend.research.local_answer_gateway import Gateway, MAIN_UID
from web.backend.research.local_first_answer_contract import prepare
from web.backend.research.provider_schemas import canonical
from web.backend.research.local_answer_gateway import GatewayUnavailable


def _bundle(base):
    root, release = base / "artifacts", base / "release"
    (root / "bin").mkdir(parents=True)
    (root / "model").mkdir()
    release.mkdir()
    files = {
        "bin/llama-server": b"synthetic executable\n",
        "bin/libllama.so.0": b"synthetic library\n",
        "model/model.gguf": b"synthetic model\n",
    }
    manifest = {"schema_version": 1, "files": {}}
    for name, value in files.items():
        path = root / name
        path.write_bytes(value)
        path.chmod(0o755 if name == "bin/llama-server" else 0o644)
        manifest["files"][name] = {"size": len(value), "sha256": hashlib.sha256(value).hexdigest()}
    raw = json.dumps(manifest).encode()
    (root / "manifest.json").write_bytes(raw)
    pin = release / "first-answer-artifact.sha256"
    pin.write_text(hashlib.sha256(raw).hexdigest() + "\n")
    return root, pin


def test_exact_root_pinned_artifact_closure(tmp_path):
    root, pin = _bundle(tmp_path)
    result = service.verify_artifacts(root, pin, owner=os.geteuid())
    assert result == service.Artifacts(root / "bin/llama-server", root / "model/model.gguf")
    extra = root / "bin/libunknown.so"
    extra.write_bytes(b"unreviewed")
    with pytest.raises(GatewayUnavailable, match="artifact_members_mismatch"):
        service.verify_artifacts(root, pin, owner=os.geteuid())
    extra.unlink()
    result.model.write_bytes(b"modified model!!\n")
    with pytest.raises(GatewayUnavailable, match="artifact_member_mismatch"):
        service.verify_artifacts(root, pin, owner=os.geteuid())


def test_symlink_writable_bundle_and_unpinned_manifest_are_refused(tmp_path):
    root, pin = _bundle(tmp_path)
    engine = root / "bin/llama-server"
    engine.chmod(0o775)
    with pytest.raises(GatewayUnavailable, match="unsafe_artifact_file"):
        service.verify_artifacts(root, pin, owner=os.geteuid())
    engine.chmod(0o755)
    pin.write_text("0" * 64)
    with pytest.raises(GatewayUnavailable, match="artifact_manifest_mismatch"):
        service.verify_artifacts(root, pin, owner=os.geteuid())
    original = root / "manifest.json"
    raw = original.read_bytes()
    pin.write_text(hashlib.sha256(raw).hexdigest())
    alias = tmp_path / "manifest-alias.json"
    original.rename(alias)
    original.symlink_to(alias)
    with pytest.raises(OSError):
        service.verify_artifacts(root, pin, owner=os.geteuid())


def test_reviewed_unit_has_one_launcher_and_private_boundaries():
    unit = Path(__file__).resolve().parents[3] / "docs/deployment/structural-first-answer.service"
    parsed = ConfigParser(interpolation=None, strict=True)
    assert parsed.read(unit)
    section = parsed["Service"]
    assert section["User"] == "structural-answer" and section["Group"] == "structural"
    assert shlex.split(section["ExecStart"])[1:3] == ["-I", "-B"]
    assert section["PrivateNetwork"] == "yes" and section["RestrictAddressFamilies"] == "AF_UNIX"
    assert section["TemporaryFileSystem"] == "/run:ro /var:ro /opt:ro /etc:ro"
    assert section["BindReadOnlyPaths"].split() == ["/opt/structural-first-answer", "/etc/passwd", "/etc/group", "/etc/nsswitch.conf", "-/etc/ld.so.cache"]
    assert section["BindPaths"] == "/run/structural-first-answer"
    assert section["RuntimeDirectoryMode"] == "0750" and section["RuntimeDirectoryPreserve"] == "no"
    assert section["MemoryMax"] == "6G" and section["CPUQuota"] == "400%"
    assert section["KillMode"] == "control-group" and section["StandardError"] == "null"
    assert not {"environmentfile", "loadcredential", "loadcredentialencrypted"} & set(section.keys())
    assert section["Restart"] == "on-failure" and section["RestartSec"] == "10s"
    assert parsed["Unit"]["StartLimitBurst"] == "2"


_CHILD = r"""
import json, os, pathlib, socket, sys
endpoint = pathlib.Path(sys.argv[sys.argv.index('--host')+1])
assert os.environ.get('STRUCTURE_SYNTHETIC_PRIVATE_TEST') is None
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.bind(str(endpoint)); s.listen(1)
(endpoint.parent / 'receipt.json').write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid(),
    'mode':oct(endpoint.stat().st_mode & 0o777), 'argv':sys.argv[1:], 'sid':os.getsid(0)}))
while True:
    with s.accept()[0] as c:
        data = b''
        while b'\r\n\r\n' not in data:
            block = c.recv(4096)
            if not block: break
            data += block
        if data.startswith(b'POST /v1/chat/completions '):
            head, incoming = data.split(b'\r\n\r\n', 1)
            length = int(next(line for line in head.split(b'\r\n') if line.startswith(b'Content-Length:')).split(b':',1)[1])
            while len(incoming) < length: incoming += c.recv(length - len(incoming))
            with (endpoint.parent / 'request-count').open('a') as receipt: receipt.write('1\n')
            while c.recv(4096): pass
            continue
        if not data.startswith(b'GET /health '): continue
        body = b'{"status":"ok"}'
        c.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\n\r\n'+body)
"""


@pytest.mark.parametrize("disconnect", [False, True], ids=["normal-stop", "unconfirmed-retire"])
def test_real_child_readiness_then_shutdown_and_socket_cleanup(tmp_path, monkeypatch, disconnect):
    monkeypatch.setenv("STRUCTURE_SYNTHETIC_PRIVATE_TEST", "must-not-reach-child")
    engine = tmp_path / "fake-llama-server"
    engine.write_text(f"#!{sys.executable}\n" + _CHILD)
    engine.chmod(0o755)
    model = tmp_path / "unused-model"
    model.write_bytes(b"fixture")
    with tempfile.TemporaryDirectory(prefix="str-answer-unit-", dir="/tmp") as short:
        parent = Path(short)
        os.chown(parent, -1, os.getegid())
        parent.chmod(0o750)
        endpoint, worker = parent / "inference.sock", parent / "worker.sock"
        monkeypatch.setattr(inference, "_INFERENCE_SOCKET", endpoint)
        monkeypatch.setattr(service, "Gateway", lambda backend: Gateway(backend, peer_uid=lambda _: MAIN_UID, timeout=2))
        if not hasattr(socket, "SO_PEERCRED"):
            real_open = service._open_private
            # Unix filesystem and process lifecycle are still real on macOS;
            # Linux CI takes the actual kernel peer PID/UID path.
            monkeypatch.setattr(inference, "_linux_peer_uid", lambda _: os.geteuid())
            def mac_open(conn, deadline, path, uid, *, expected_pid):
                assert expected_pid > 1
                real_open(conn, deadline, path, uid)
            monkeypatch.setattr(service, "_open_private", mac_open)
            monkeypatch.setattr(inference, "_open_private", mac_open)
        ready, stop = threading.Event(), threading.Event()
        result = []
        @contextmanager
        def listener():
            assert stat.S_IMODE(endpoint.lstat().st_mode) == 0o600
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.bind(str(worker));s.listen(1);ready.set()
                try:yield s
                finally:worker.unlink()
        def execute():
            result.append(service.run(service.Artifacts(engine, model), stop, endpoint=endpoint, timeout=3, listener=listener))
        thread = threading.Thread(target=execute, daemon=True)
        thread.start()
        try:
            assert ready.wait(4)
            receipt = json.loads((parent / "receipt.json").read_text())
            assert receipt["parent"] == os.getpid() and receipt["pid"] != os.getpid()
            assert receipt["mode"] == "0o600" and receipt["sid"] == os.getsid(0)
            assert receipt["argv"] == service._argv(service.Artifacts(engine, model), endpoint)[1:]
            assert "--no-warmup" not in receipt["argv"]
            os.kill(receipt["pid"], 0)
            if disconnect:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                    client.connect(str(worker))
                    messages = prepare("An isolated public fixture", "fixture", []).messages
                    client.sendall(canonical({"messages": messages}))
                    client.shutdown(socket.SHUT_WR)
                    deadline = time.monotonic() + 1
                    while not (parent / "request-count").exists():
                        assert time.monotonic() < deadline
                        time.sleep(.01)
                # No stop injected here: disconnect must retire both processes
                # and leave no original prompt to replay.
                thread.join(4)
                assert not thread.is_alive()
                assert (parent / "request-count").read_text() == "1\n"
        finally:
            stop.set()
            thread.join(5)
            assert not thread.is_alive()
        assert result == [int(disconnect)] and not endpoint.exists() and not worker.exists()
        with pytest.raises(ProcessLookupError):
            os.kill(receipt["pid"], 0)
