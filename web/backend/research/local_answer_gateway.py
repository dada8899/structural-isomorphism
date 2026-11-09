"""Same-host first-answer worker boundary; no TCP and no prompt logging.

The worker receives one bounded request to write-EOF and returns a single
candidate to EOF. A backend is a cooperative callable (messages, request)
that must bound its own work and check request.check() while blocked.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import os
from pathlib import Path
import pwd
import re
import socket
import stat
import struct
import sys
import threading
import time

from .local_answer_transport import _MAX_INPUT, _MAX_OUTPUT, _SOCKET, _WORKER
from .local_first_answer_contract import (
    CONTRACT, MAX_EXCERPT_CHARS, MAX_PROMPT_BYTES, MAX_QUESTION_CHARS, MAX_SOURCES, _SYSTEM,
)
from .provider_schemas import ProviderFailure, strict_json
from .schemas import bounded_text

MAIN_UID = 981
DEADLINE_SECONDS = 11.0  # Main's client closes after 12 seconds.
_IO_SLICE = 0.1
_FRAME_TOKEN = re.compile(r"[<>]|\[/?(?:INST|SYSTEM_PROMPT)\]")


class GatewayUnavailable(Exception):
    """Only fixed error codes; never includes input, output or transport text."""


def _linux_peer_uid(connection):
    if sys.platform != "linux":
        raise GatewayUnavailable("peer_credentials_unavailable")
    pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    if pid <= 0 or uid < 0:
        raise GatewayUnavailable("peer_credentials_unavailable")
    return uid


def decode_messages(payload):
    """Accept only the fixed system instruction and prepared user-data shape."""
    try:
        envelope = strict_json(payload, _MAX_INPUT)
        if type(envelope) is not dict or set(envelope) != {"messages"}:
            raise ValueError()
        messages = envelope["messages"]
        if type(messages) is not list or len(messages) != 2:
            raise ValueError()
        for message, role in zip(messages, ("system", "user")):
            if (type(message) is not dict or set(message) != {"role", "content"}
                    or message["role"] != role or type(message["content"]) is not str):
                raise ValueError()
        system, user = (message["content"] for message in messages)
        user_bytes = user.encode()
        if system != _SYSTEM or len(system.encode()) + len(user_bytes) > MAX_PROMPT_BYTES or _FRAME_TOKEN.search(user):
            raise ValueError()
        data = strict_json(user_bytes, MAX_PROMPT_BYTES)
        if type(data) is not dict or set(data) != {"contract", "question", "sources"} or data["contract"] != CONTRACT:
            raise ValueError()
        question = bounded_text(data["question"], MAX_QUESTION_CHARS, 1, normalize=False)
        sources = data["sources"]
        if not question.strip() or type(sources) is not list or len(sources) > MAX_SOURCES:
            raise ValueError()
        for number, source in enumerate(sources, 1):
            if (type(source) is not dict or set(source) != {"number", "label", "excerpt"}
                    or type(source["number"]) is not int or source["number"] != number
                    or not bounded_text(source["label"], 240, 1).strip()
                    or not bounded_text(source["excerpt"], MAX_EXCERPT_CHARS, 1).strip()):
                raise ValueError()
    except (ProviderFailure, ValueError, UnicodeError, TypeError, OverflowError, RecursionError, KeyError):
        raise GatewayUnavailable("invalid_messages") from None
    return tuple(messages)


@dataclass(frozen=True, slots=True, repr=False)
class RequestDeadline:
    _connection: socket.socket
    _end: float
    _stopping: threading.Event

    def check(self):
        """Return remaining absolute budget or fail if stopped/disconnected."""
        remaining = self._end - time.monotonic()
        if self._stopping.is_set():
            raise GatewayUnavailable("worker_stopping")
        if remaining <= 0:
            raise GatewayUnavailable("deadline")
        # A read-EOF is normal; a zero-byte write probes the other direction
        # without adding data to the frame or mistaking half-close for loss.
        try:
            self._connection.send(b"", getattr(socket, "MSG_NOSIGNAL", 0))
        except BlockingIOError:
            pass
        except OSError:
            raise GatewayUnavailable("client_disconnected") from None
        return remaining


def _read_frame(connection, request):
    data = bytearray()
    while True:
        connection.setblocking(False)
        connection.settimeout(min(_IO_SLICE, request.check()))
        try:
            chunk = connection.recv(min(4096, _MAX_INPUT + 1 - len(data)))
        except TimeoutError:
            continue
        if not chunk:
            return bytes(data)
        data.extend(chunk)
        if len(data) > _MAX_INPUT:
            raise GatewayUnavailable("request_limit")


class Gateway:
    """An authenticated Unix peer can occupy at most one inference slot."""

    def __init__(self, backend, *, main_uid=MAIN_UID, peer_uid=_linux_peer_uid, timeout=DEADLINE_SECONDS):
        if (type(main_uid) is not int or main_uid <= 0 or type(timeout) not in (float, int)
                or not 0 < timeout <= DEADLINE_SECONDS or not callable(backend) or not callable(peer_uid)):
            raise ValueError("invalid worker boundary")
        self._main_uid = main_uid
        self._peer_uid = peer_uid
        self._timeout = timeout
        self._backend = backend
        self._slot = threading.BoundedSemaphore(1)

    def _claimed(self, connection, stopping, end):
        try:
            with connection:
                if connection.family != socket.AF_UNIX or self._peer_uid(connection) != self._main_uid:
                    return False
                request = RequestDeadline(connection, end, stopping)
                messages = decode_messages(_read_frame(connection, request))
                connection.setblocking(False)
                request.check()
                try:
                    result = self._backend(messages, request)
                except Exception:
                    # Never let model/backend exceptions or output enter stderr.
                    return False
                request.check()
                if type(result) is not bytes or not 1 <= len(result) <= _MAX_OUTPUT:
                    return False
                if type(strict_json(result, _MAX_OUTPUT)) is not dict:
                    return False
                connection.settimeout(request.check())
                connection.sendall(result)
                return True
        except (GatewayUnavailable, ProviderFailure, OSError, struct.error):
            return False
        finally:
            self._slot.release()

    def handle(self, connection, stopping=None):
        """Synchronous single-connection handler, also used with socketpairs."""
        if not self._slot.acquire(blocking=False):
            connection.close()
            return False
        return self._claimed(connection, stopping or threading.Event(), time.monotonic() + self._timeout)

    def serve(self, listener, stopping):
        """Accept continuously so a concurrent peer never waits for the slot."""
        listener.settimeout(_IO_SLICE)
        active = None
        try:
            while not stopping.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                if not self._slot.acquire(blocking=False):
                    connection.close()
                    continue
                if active is not None:
                    active.join()
                active = threading.Thread(
                    target=self._claimed, args=(connection, stopping, time.monotonic() + self._timeout),
                    name="local-first-answer-request", daemon=True,
                )
                try:
                    active.start()
                except BaseException:
                    if active.ident is None:
                        connection.close()
                        self._slot.release()
                    raise
        finally:
            stopping.set()
            if active is not None and active.ident is not None:
                active.join(self._timeout + _IO_SLICE)
                if active.is_alive():
                    raise GatewayUnavailable("backend_stop_unconfirmed")


def _listener_parent(path, uid, gid):
    parent = os.lstat(path.parent)
    if (not stat.S_ISDIR(parent.st_mode) or parent.st_uid != uid or parent.st_gid != gid
            or stat.S_IMODE(parent.st_mode) != 0o750):
        raise GatewayUnavailable("worker_socket_directory_unavailable")
    return parent.st_dev, parent.st_ino


def _socket_identity(path, uid, gid):
    item = os.lstat(path)
    if (not stat.S_ISSOCK(item.st_mode) or item.st_uid != uid or item.st_gid != gid
            or stat.S_IMODE(item.st_mode) != 0o660 or item.st_nlink != 1):
        raise GatewayUnavailable("worker_socket_unavailable")
    return item.st_dev, item.st_ino


@contextmanager
def private_listener():
    """Bind the exact runtime path, without replacing any existing file."""
    if sys.platform != "linux":
        raise GatewayUnavailable("worker_platform_unavailable")
    account = pwd.getpwnam(_WORKER)
    uid, gid = os.geteuid(), os.getegid()
    if uid <= 0 or uid != os.getuid() or uid != account.pw_uid or uid == MAIN_UID:
        raise GatewayUnavailable("worker_identity_unavailable")
    path = Path(_SOCKET)
    parent = _listener_parent(path, uid, gid)
    identity = None
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
            # The process is still single-threaded. Restrict permissions at
            # creation; never briefly expose a wider socket and then chmod.
            old = os.umask(0o117)
            try:
                listener.bind(str(path))
            finally:
                os.umask(old)
            identity = _socket_identity(path, uid, gid)
            if _listener_parent(path, uid, gid) != parent:
                raise GatewayUnavailable("worker_socket_directory_changed")
            listener.listen(4)
            yield listener
    finally:
        if identity is not None:
            try:
                if _listener_parent(path, uid, gid) == parent and _socket_identity(path, uid, gid) == identity:
                    path.unlink()
            except (OSError, GatewayUnavailable):
                pass
