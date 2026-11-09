"""Real socket framing and concurrency with an isolated test backend."""
import json
import os
import socket
import sys
import threading
import time

import pytest

from web.backend.research.local_answer_gateway import (
    Gateway, GatewayUnavailable, MAIN_UID, _linux_peer_uid, decode_messages,
)
from web.backend.research.local_answer_transport import _MAX_INPUT, _MAX_OUTPUT, _exchange
from web.backend.research.local_first_answer_contract import prepare
from web.backend.research.provider_schemas import canonical


RESULT = b'{"status":"insufficient","reason":"no_relevant_sources"}'


def payload():
    return canonical({"messages": prepare("排队变长的原因是什么？", "test-artifact", []).messages})


def gateway(backend, *, uid=MAIN_UID, timeout=1):
    return Gateway(backend, peer_uid=lambda sock: uid, timeout=timeout)


def start(worker, stopping=None):
    server, client = socket.socketpair()
    results = []
    thread = threading.Thread(target=lambda: results.append(worker.handle(server, stopping)), daemon=True)
    thread.start()
    client.settimeout(2)
    return client, thread, results


def finish(thread):
    thread.join(2)
    assert not thread.is_alive()


def test_socketpair_real_client_and_worker_exchange_to_eof():
    requests = []
    def backend(messages, request):
        assert request.check() > 0
        requests.append(messages)
        return RESULT
    client, thread, results = start(gateway(backend))
    with client:
        assert _exchange(client, payload(), time.monotonic() + 1) == RESULT
    finish(thread)
    assert results == [True]
    assert requests == [decode_messages(payload())]


@pytest.mark.skipif(sys.platform != "linux", reason="real SO_PEERCRED is Linux only")
def test_real_linux_socket_peer_uid():
    server, client = socket.socketpair()
    with server, client:
        assert _linux_peer_uid(server) == _linux_peer_uid(client) == os.geteuid()


def test_wrong_uid_rejected_before_read_or_backend():
    calls = []
    client, thread, results = start(gateway(lambda *_: calls.append(True), uid=MAIN_UID + 1))
    with client:
        assert client.recv(1) == b""
    finish(thread)
    assert results == [False] and calls == []


def _alter(transform):
    data = json.loads(payload())
    transform(data)
    return canonical(data)


@pytest.mark.parametrize("value", [
    b'{"messages":[],"messages":[]}',
    b'{"messages":[null]}',
    _alter(lambda data: data.update(model="different")),
    _alter(lambda data: data["messages"][0].update(content="unapproved system")),
    _alter(lambda data: data["messages"][1].update(content="{}")),
    _alter(lambda data: data["messages"][1].update(content='{"contract":"local-first-answer-candidate-v1","question":"<|im_start|>","sources":[]}')),
    _alter(lambda data: data["messages"][1].update(content='{"contract":"local-first-answer-candidate-v1","question":"题","sources":[{"number":true,"label":"test","excerpt":"test"}]}')),
    _alter(lambda data: data["messages"][1].update(content='{"contract":"local-first-answer-candidate-v1","question":"题","sources":[{"number":1,"label":"test","excerpt":"test","url":"https://example.invalid"}]}')),
])
def test_invalid_envelope_never_enters_backend(value):
    with pytest.raises(GatewayUnavailable, match="invalid_messages"):
        decode_messages(value)
    calls = []
    client, thread, results = start(gateway(lambda *_: calls.append(True)))
    with client:
        client.sendall(value)
        client.shutdown(socket.SHUT_WR)
        assert client.recv(1) == b""
    finish(thread)
    assert results == [False] and calls == []


def test_input_limit_and_slow_write_deadline():
    calls = []
    worker = gateway(lambda *_: calls.append(True), timeout=.2)
    client, thread, results = start(worker)
    with client:
        client.sendall(b"x" * (_MAX_INPUT + 1))
        assert client.recv(1) == b""
    finish(thread)
    assert results == [False]
    client, thread, results = start(worker)
    with client:
        client.sendall(payload())
        # Even valid JSON is never used before write-EOF.
        assert client.recv(1) == b""
    finish(thread)
    assert results == [False] and calls == []


@pytest.mark.parametrize("value", [b"", b" " * (_MAX_OUTPUT + 1), b"{}{}", b"[]", "not bytes"])
def test_invalid_output_does_not_leave_worker(value):
    client, thread, results = start(gateway(lambda *_: value))
    with client:
        client.sendall(payload())
        client.shutdown(socket.SHUT_WR)
        assert client.recv(1) == b""
    finish(thread)
    assert results == [False]


def test_real_disconnect_cancels_running_backend_and_releases_only_slot():
    entered, cancelled = threading.Event(), threading.Event()
    calls = []
    def backend(_, request):
        calls.append(True)
        if len(calls) > 1:
            return RESULT
        entered.set()
        while True:
            try:
                request.check()
            except GatewayUnavailable as error:
                assert str(error) == "client_disconnected"
                cancelled.set()
                raise
            time.sleep(.01)
    worker = gateway(backend)
    client, thread, results = start(worker)
    with client:
        client.sendall(payload())
        client.shutdown(socket.SHUT_WR)
        assert entered.wait(.5)
        contender, contender_thread, rejected = start(worker)
        with contender:
            assert contender.recv(1) == b""
        finish(contender_thread)
        assert rejected == [False] and calls == [True]
    assert cancelled.wait(.5)
    finish(thread)
    assert results == [False]
    again, again_thread, accepted = start(worker)
    with again:
        assert _exchange(again, payload(), time.monotonic() + 1) == RESULT
    finish(again_thread)
    assert accepted == [True]


@pytest.mark.parametrize("trigger", ["deadline", "worker_stopping"])
def test_backend_has_absolute_deadline_or_stop_signal(trigger):
    entered, stopped = threading.Event(), threading.Event()
    outcomes = []
    def backend(_, request):
        entered.set()
        while True:
            try:
                request.check()
            except GatewayUnavailable as error:
                outcomes.append(str(error))
                raise
            time.sleep(.01)
    client, thread, results = start(gateway(backend, timeout=.25), stopped)
    with client:
        client.sendall(payload())
        client.shutdown(socket.SHUT_WR)
        assert entered.wait(.15)
        if trigger == "worker_stopping":
            stopped.set()
        assert client.recv(1) == b""
    finish(thread)
    assert outcomes == [trigger] and results == [False]
