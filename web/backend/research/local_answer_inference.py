"""Fixed Unix-only llama-server adapter for the private answer gateway."""
import errno
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import threading

from .local_answer_gateway import Gateway, GatewayUnavailable, _linux_peer_uid, private_listener
from .local_answer_transport import _MAX_OUTPUT
from .provider_schemas import ProviderFailure, canonical, strict_json

_INFERENCE_SOCKET = Path("/run/structural-first-answer/inference.sock")
_MODEL_ALIAS = "structure-first-answer"
_MAX_TOKENS = 480
_MAX_HEADER = 8192
_MAX_BODY = 128 * 1024
_POLL_SECONDS = 0.05
_STATUS = re.compile(rb"HTTP/1\.[01] ([1-5][0-9][0-9])(?: [ -~]*)?")
_HEADER_NAME = re.compile(rb"[a-zA-Z0-9!#$%&'*+.^_`|~-]+")


def _wait(sock, request, *, writable):
    while True:
        timeout = min(_POLL_SECONDS, request.check())
        reads, writes, errors = select.select([] if writable else [sock],
                                               [sock] if writable else [], [sock], timeout)
        if errors:
            raise GatewayUnavailable("inference_socket_error")
        if reads or writes:
            return


def _send(sock, request, payload):
    remaining = memoryview(payload)
    while remaining:
        _wait(sock, request, writable=True)
        try:
            sent = sock.send(remaining, getattr(socket, "MSG_NOSIGNAL", 0))
        except BlockingIOError:
            continue
        if sent <= 0:
            raise GatewayUnavailable("inference_send_incomplete")
        remaining = remaining[sent:]


def _recv(sock, request, count):
    while True:
        _wait(sock, request, writable=False)
        try:
            data = sock.recv(count)
        except BlockingIOError:
            continue
        if not data:
            raise GatewayUnavailable("inference_response_incomplete")
        return data


def _response(sock, request):
    # Non-streaming server answers use a bounded Content-Length. Transfer
    # encoding or connection-close framing is not accepted for this endpoint.
    frame = bytearray()
    boundary = -1
    while boundary < 0:
        frame.extend(_recv(sock, request, min(4096, _MAX_HEADER + 4 - len(frame))))
        boundary = frame.find(b"\r\n\r\n")
        if (boundary < 0 and len(frame) >= _MAX_HEADER + 4) or boundary > _MAX_HEADER:
            raise GatewayUnavailable("inference_header_limit")
    lines = bytes(frame[:boundary]).split(b"\r\n")
    match = _STATUS.fullmatch(lines[0])
    if not match:
        raise GatewayUnavailable("inference_status_invalid")
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(b":")
        name = name.lower()
        if not sep or not _HEADER_NAME.fullmatch(name) or name in headers:
            raise GatewayUnavailable("inference_header_invalid")
        headers[name] = value.strip()
    if b"transfer-encoding" in headers or not re.fullmatch(rb"[0-9]{1,6}", headers.get(b"content-length", b"")):
        raise GatewayUnavailable("inference_framing_unavailable")
    length = int(headers[b"content-length"])
    body = frame[boundary + 4:]
    if not 0 <= len(body) <= length <= _MAX_BODY:
        raise GatewayUnavailable("inference_response_limit")
    while len(body) < length:
        body.extend(_recv(sock, request, min(4096, length - len(body))))
    return int(match[1]), headers, bytes(body)


def _post_body(messages):
    return canonical({"messages": messages, "model": _MODEL_ALIAS, "temperature": 0, "stream": False,
                      "cache_prompt": False, "max_tokens": _MAX_TOKENS,
                      "response_format": {"type": "json_object"}})


def _post(sock, messages, request):
    body = _post_body(messages)
    header = (b"POST /v1/chat/completions HTTP/1.1\r\nHost: localhost\r\n"
              b"Content-Type: application/json\r\nAccept: application/json\r\nConnection: close\r\nContent-Length: "
              + str(len(body)).encode() + b"\r\n\r\n")
    _send(sock, request, header + body)
    return _response(sock, request)


def _extract(status, headers, raw):
    if status != 200 or headers.get(b"content-type", b"").split(b";", 1)[0].strip().lower() != b"application/json":
        raise GatewayUnavailable("inference_not_ready")
    try:
        envelope = strict_json(raw, _MAX_BODY)
        choices = envelope.get("choices") if type(envelope) is dict else None
        if type(choices) is not list or len(choices) != 1:
            raise ValueError()
        choice = choices[0]
        if type(choice) is not dict or choice.get("finish_reason") != "stop":
            raise ValueError()
        message = choice.get("message")
        if (type(message) is not dict or message.get("role") != "assistant"
                or type(message.get("content")) is not str or message.get("tool_calls")):
            raise ValueError()
        data = message["content"].encode("utf-8")
        if not 1 <= len(data) <= _MAX_OUTPUT:
            raise ValueError()
    except (ProviderFailure, UnicodeError, ValueError, TypeError):
        raise GatewayUnavailable("inference_candidate_invalid") from None
    return data


def _open_private(sock, request, path, uid):
    entry = os.lstat(path)
    if (not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != uid or entry.st_mode & 0o077 or entry.st_nlink != 1):
        raise GatewayUnavailable("inference_socket_unavailable")
    sock.setblocking(False)
    err = sock.connect_ex(str(path))
    if err in (errno.EINPROGRESS, errno.EALREADY, errno.EWOULDBLOCK):
        _wait(sock, request, writable=True)
        err = sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR)
    if err or _linux_peer_uid(sock) != uid:
        raise GatewayUnavailable("inference_identity_unavailable")


class LlamaUnixBackend:
    """Never re-use an inference slot after an incomplete upstream receipt."""

    def __init__(self):
        self._quarantined = False

    def __call__(self, messages, request):
        if self._quarantined:
            raise GatewayUnavailable("inference_unavailable")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            _open_private(sock, request, _INFERENCE_SOCKET, os.geteuid())
            try:
                status, headers, raw = _post(sock, messages, request)
            except (GatewayUnavailable, OSError):
                # Closing HTTP cancels the gateway side. Until inference exit
                # or idle is proved out-of-band, never send another request.
                self._quarantined = True
                raise GatewayUnavailable("inference_receipt_unconfirmed") from None
        return _extract(status, headers, raw)


def main():
    stopping = threading.Event()
    for name in (signal.SIGTERM, signal.SIGINT):
        signal.signal(name, lambda *_: stopping.set())
    try:
        with private_listener() as listener:
            Gateway(LlamaUnixBackend()).serve(listener, stopping)
    except (GatewayUnavailable, OSError, ValueError, KeyError):
        # No raw exception (which could include user data) in unit logs.
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
