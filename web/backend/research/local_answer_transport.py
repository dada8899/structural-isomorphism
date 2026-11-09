"""Bounded private transport for the optional same-host answer worker.

The worker cannot be selected by a request and this client has no TCP mode.
The worker must accept one UTF-8 request to EOF and return one result to EOF.
"""
import os
import pwd
import socket
import stat
import struct
import sys
import threading
import time

_SOCKET = "/run/structural-first-answer/worker.sock"
_WORKER = "structural-answer"
_MAX_INPUT = 64 * 1024
_MAX_OUTPUT = 16 * 1024
_DEADLINE_SECONDS = 12.0
_SLOT = threading.BoundedSemaphore(1)


class LocalAnswerUnavailable(Exception):
    """No worker output is safe to consume."""


def _timeout(connection, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise LocalAnswerUnavailable("local answer deadline")
    connection.settimeout(remaining)


def _exchange(connection, payload, deadline):
    _timeout(connection, deadline)
    connection.sendall(payload)
    connection.shutdown(socket.SHUT_WR)
    data = bytearray()
    while True:
        _timeout(connection, deadline)
        chunk = connection.recv(min(4096, _MAX_OUTPUT + 1 - len(data)))
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > _MAX_OUTPUT:
            raise LocalAnswerUnavailable("local answer response limit")
    if not data:
        raise LocalAnswerUnavailable("local answer response missing")
    return bytes(data)


def worker_present():
    """Fast availability hint; complete() independently checks peer identity."""
    if sys.platform != "linux":
        return False
    try:
        return stat.S_ISSOCK(os.lstat(_SOCKET).st_mode)
    except OSError:
        return False


def complete(payload):
    """Submit approved prompt bytes to the fixed local worker; never retry."""
    if type(payload) is not bytes or not 1 <= len(payload) <= _MAX_INPUT:
        raise LocalAnswerUnavailable("local answer request limit")
    if sys.platform != "linux" or not _SLOT.acquire(blocking=False):
        raise LocalAnswerUnavailable("local answer worker unavailable")
    try:
        deadline = time.monotonic() + _DEADLINE_SECONDS
        account = pwd.getpwnam(_WORKER)
        entry = os.lstat(_SOCKET)
        if not stat.S_ISSOCK(entry.st_mode) or entry.st_uid != account.pw_uid or entry.st_mode & 0o007:
            raise LocalAnswerUnavailable("local answer worker socket unavailable")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            _timeout(connection, deadline)
            connection.connect(_SOCKET)
            _pid, uid, _gid = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid != account.pw_uid:
                raise LocalAnswerUnavailable("local answer worker identity mismatch")
            return _exchange(connection, payload, deadline)
    except (OSError, KeyError, struct.error):
        raise LocalAnswerUnavailable("local answer worker unavailable") from None
    finally:
        _SLOT.release()
