"""Real Unix socket adapter tests; no local model files or TCP service."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import time

import pytest

from web.backend.research import local_answer_inference as adapter
from web.backend.research.local_answer_gateway import Gateway, GatewayUnavailable, MAIN_UID, RequestDeadline
from web.backend.research.local_answer_transport import _exchange
from web.backend.research.local_first_answer_contract import prepare
from web.backend.research.provider_schemas import canonical


_MESSAGES = prepare("How might queue delay change?", "synthetic", []).messages
_CANDIDATE = b'{"status":"insufficient","reason":"no_relevant_sources"}'


def _request(stream):
    data = bytearray()
    stream.settimeout(2)
    while b"\r\n\r\n" not in data:
        chunk = stream.recv(4096)
        assert chunk
        data.extend(chunk)
    head, body = bytes(data).split(b"\r\n\r\n", 1)
    lines = head.split(b"\r\n")
    assert lines[0] == b"POST /v1/chat/completions HTTP/1.1"
    fields = dict(line.split(b": ", 1) for line in lines[1:])
    length = int(fields[b"Content-Length"])
    while len(body) < length:
        chunk = stream.recv(length - len(body))
        assert chunk
        body += chunk
    assert len(body) == length
    return json.loads(body)


def _http(data, *, reason="stop", role="assistant"):
    body = canonical({"choices": [{"finish_reason": reason, "message": {"role": role, "content": data}}]})
    return b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body


@contextmanager
def _inference_socket(monkeypatch):
    with tempfile.TemporaryDirectory(prefix="str-ans-", dir="/tmp") as directory:
        path = Path(directory) / "inference.sock"
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            listener.bind(str(path))
            path.chmod(0o700)
            listener.listen(1)
            listener.settimeout(2)
            monkeypatch.setattr(adapter, "_INFERENCE_SOCKET", path)
            if not hasattr(socket, "SO_PEERCRED"):
                # Linux CI executes the actual getsockopt; macOS still exercises
                # the filesystem and wire path, not the unsupported Linux op.
                monkeypatch.setattr(adapter, "_linux_peer_uid", lambda _: os.geteuid())
            yield listener, path


def _join(thread):
    thread.join(2)
    assert not thread.is_alive()


def test_fixed_unix_http_request_and_bounded_return_through_gateway(monkeypatch):
    received = []
    with _inference_socket(monkeypatch) as (listener, _):
        def fake_llama():
            connection, _ = listener.accept()
            with connection:
                received.append(_request(connection))
                wire = _http(_CANDIDATE.decode())
                # Header/body can arrive split at arbitrary byte offsets.
                for offset in range(0, len(wire), 17):
                    connection.sendall(wire[offset:offset + 17])
        inference = threading.Thread(target=fake_llama, daemon=True)
        inference.start()
        server, client = socket.socketpair()
        worker = Gateway(adapter.LlamaUnixBackend(), peer_uid=lambda _: MAIN_UID, timeout=1)
        gateway = threading.Thread(target=worker.handle, args=(server,), daemon=True)
        gateway.start()
        with client:
            assert _exchange(client, canonical({"messages": _MESSAGES}), time.monotonic() + 2) == _CANDIDATE
        _join(gateway)
        _join(inference)
    assert received == [{
        "messages": list(_MESSAGES), "model": "structure-first-answer", "temperature": 0,
        "stream": False, "cache_prompt": False, "max_tokens": 480,
        "response_format": {"type": "json_object"},
    }]


@pytest.mark.parametrize("wire", [
    b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}",
    b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 999999\r\n\r\n",
    b"HTTP/1.1 200 OK\r\nContent-Length: 10\r\n\r\n{}",
])
def test_rejects_ambiguous_incomplete_or_large_upstream_frame(wire):
    worker, client = socket.socketpair()
    upstream, inference = socket.socketpair()
    with worker, client, upstream, inference:
        upstream.setblocking(False)
        inference.sendall(wire)
        inference.shutdown(socket.SHUT_WR)
        deadline = RequestDeadline(worker, time.monotonic() + 1, threading.Event())
        with pytest.raises(GatewayUnavailable):
            adapter._response(upstream, deadline)


@pytest.mark.parametrize("wire", [
    _http(_CANDIDATE.decode(), reason="length"), _http(_CANDIDATE.decode(), role="tool"), _http("x" * 16385),
])
def test_rejects_truncated_wrong_role_or_oversized_candidate(wire):
    worker, client = socket.socketpair()
    upstream, inference = socket.socketpair()
    with worker, client, upstream, inference:
        upstream.setblocking(False)
        send = threading.Thread(target=inference.sendall, args=(wire,), daemon=True)
        send.start()
        deadline = RequestDeadline(worker, time.monotonic() + 1, threading.Event())
        reply = adapter._response(upstream, deadline)
        _join(send)
        with pytest.raises(GatewayUnavailable, match="inference_candidate_invalid"):
            adapter._extract(*reply)


def test_disconnect_closes_inference_and_quarantines_unknown_slot(monkeypatch):
    entered, disconnected = threading.Event(), threading.Event()
    with _inference_socket(monkeypatch) as (listener, _):
        def fake_llama():
            connection, _ = listener.accept()
            with connection:
                _request(connection)
                entered.set()
                if connection.recv(1) == b"":
                    disconnected.set()
        inference = threading.Thread(target=fake_llama, daemon=True)
        inference.start()
        backend = adapter.LlamaUnixBackend()
        server, client = socket.socketpair()
        worker = Gateway(backend, peer_uid=lambda _: MAIN_UID, timeout=1)
        gateway = threading.Thread(target=worker.handle, args=(server,), daemon=True)
        gateway.start()
        with client:
            client.sendall(canonical({"messages": _MESSAGES}))
            client.shutdown(socket.SHUT_WR)
            assert entered.wait(1)
        assert disconnected.wait(1)
        _join(gateway)
        _join(inference)

        server, client = socket.socketpair()
        with server, client:
            deadline = RequestDeadline(server, time.monotonic() + 1, threading.Event())
            with pytest.raises(GatewayUnavailable, match="inference_unavailable"):
                backend(_MESSAGES, deadline)
        listener.settimeout(.05)
        with pytest.raises(TimeoutError):
            listener.accept()


def test_private_inference_socket_rejects_group_access_before_connect(monkeypatch):
    with _inference_socket(monkeypatch) as (listener, path):
        path.chmod(0o760)
        server, client = socket.socketpair()
        with server, client:
            deadline = RequestDeadline(server, time.monotonic() + 1, threading.Event())
            with pytest.raises(GatewayUnavailable, match="inference_socket_unavailable"):
                adapter.LlamaUnixBackend()(_MESSAGES, deadline)
        listener.settimeout(.05)
        with pytest.raises(TimeoutError):
            listener.accept()
