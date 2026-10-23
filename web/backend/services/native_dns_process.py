"""Fixed owned DNS exec. No credential, configurable host or app import at top.

The public operation requires the canonical transport's current executable C
slot before socket/process birth. Child IPC contains only fixed DNS metadata.
"""
import errno
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import time

_HOST = 'api.deepseek.com'
_LIMIT = 4096
_MAX_ADDRESSES = 16
_UNCERTAIN = []


def validate_addresses(values):
    """Pure result validation, not permission to resolve or connect."""
    if type(values) is not list or not 1 <= len(values) <= _MAX_ADDRESSES:
        raise ValueError('bounded DNS result required')
    result = []
    for value in values:
        if type(value) is not str or not 1 <= len(value) <= 45 or '%' in value:
            raise ValueError('numeric public peer required')
        address = ipaddress.ip_address(value)
        if (not address.is_global or address.is_reserved or address.is_multicast or address.is_unspecified
                or getattr(address, 'ipv4_mapped', None) is not None or str(address) != value):
            raise ValueError('nonpublic DNS answer rejected')
        if value in result:
            raise ValueError('duplicate DNS answer')
        result.append(value)
    return tuple(result)


def decode_result(raw, pid, nonce):
    if type(raw) is not bytes or not 1 <= len(raw) <= _LIMIT:
        raise ValueError('bounded DNS frame required')
    value = json.loads(raw)
    if (type(value) is not list or len(value) != 4 or value[0] != 'native-dns-result-v1'
            or type(value[1]) is not int or value[1] != pid or value[2] != nonce):
        raise ValueError('owned DNS child/result mismatch')
    encoded = json.dumps(value, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    if encoded != raw:
        raise ValueError('exact DNS frame required')
    return validate_addresses(value[3])


def _deadline(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= time.monotonic():
        raise TimeoutError('native DNS deadline ended')
    return value


def _wait(sock, stop_fd, deadline, *, write=False):
    remaining = max(0., deadline - time.monotonic())
    if not remaining:
        raise TimeoutError('native DNS deadline ended')
    ready, writable, bad = select.select([stop_fd] + ([] if write else [sock]), [sock] if write else [], [sock], remaining)
    if stop_fd in ready:
        raise InterruptedError('native DNS stopped')
    if bad or not (writable if write else ready):
        raise TimeoutError('native DNS deadline ended')


def _write_frame(sock, raw, stop_fd, deadline):
    pending = memoryview(struct.pack('!I', len(raw)) + raw)
    while pending:
        _wait(sock, stop_fd, deadline, write=True)
        try:
            n = sock.send(pending)
        except BlockingIOError:
            continue
        if n <= 0:
            raise OSError('native DNS IPC ended')
        pending = pending[n:]


def _read_frame(sock, stop_fd, deadline):
    raw = bytearray()
    expected = None
    while True:
        _wait(sock, stop_fd, deadline)
        try:
            data = sock.recv(4096)
        except BlockingIOError:
            continue
        if not data:
            raise OSError('native DNS IPC ended')
        raw.extend(data)
        if expected is None and len(raw) >= 4:
            expected = struct.unpack('!I', raw[:4])[0]
            if not 1 <= expected <= _LIMIT:
                raise ValueError('native DNS IPC bound')
        if len(raw) > _LIMIT + 4 or (expected is not None and len(raw) > expected + 4):
            raise ValueError('native DNS IPC trailing bytes')
        if expected is not None and len(raw) == expected + 4:
            return bytes(raw[4:])


class _OwnedDNS:
    """Actual child/IPC ownership; a failed reap remains sticky evidence."""
    def __init__(self, resource, scope, deadline):
        self.resource, self.scope, self.deadline = resource, scope, deadline
        self.pid, self.reference = os.getpid(), object()
        self.parent = self.child = self.process = None
        self.socket_records = {}
        self.uncertain, self.closed = False, False
        resource._dns_processes[self.reference] = self
    def remember_socket(self, sock):
        record = {'fd':sock.fileno(), 'identity':None, 'closed':False}
        self.socket_records[id(sock)] = record
        info = os.fstat(record['fd']);record['identity'] = (info.st_dev, info.st_ino)
    def close_socket(self, sock):
        record = self.socket_records.get(id(sock))
        if record is None:
            # The socketpair itself was born before a subsequent fstat failed.
            self.remember_socket(sock);record = self.socket_records[id(sock)]
        if record['closed']:return
        if sock.fileno() >= 0:
            info = os.fstat(sock.fileno())
            if sock.fileno() != record['fd'] or (info.st_dev,info.st_ino) != record['identity']:
                raise PermissionError('DNS socket identity changed')
            sock.close()
        if sock.fileno() != -1:raise OSError('DNS socket close unproved')
        try:os.fstat(record['fd'])
        except OSError as error:
            if error.errno != errno.EBADF:raise
        else:raise OSError('DNS original FD retirement unknown')
        record['closed'] = True
    def close(self):
        if self.pid != os.getpid():
            raise PermissionError('native DNS belongs to its actual parent')
        errors = []
        for sock in (self.child, self.parent):
            if sock is not None:
                try:
                    self.close_socket(sock)
                except BaseException as error:
                    errors.append(type(error).__name__)
        p = self.process
        if p is not None and getattr(p, '_child_created', False):
            try:
                if p.poll() is None:
                    if type(p.pid) is not int or os.getpgid(p.pid) != p.pid:
                        raise PermissionError('native DNS child identity differs')
                    p.terminate()
                    try:
                        p.wait(timeout=max(0., min(.15, self.deadline - time.monotonic())))
                    except subprocess.TimeoutExpired:
                        p.kill()
                        p.wait(timeout=max(0., self.deadline - time.monotonic()))
                if p.returncode is None:
                    raise OSError('native DNS child not reaped')
            except BaseException as error:
                errors.append(type(error).__name__)
        if errors or self.uncertain:
            self.uncertain = True
            self.resource._mark_cleanup_uncertain()
            if self not in _UNCERTAIN:
                _UNCERTAIN.append(self)
            raise OSError('native DNS retirement uncertain')
        self.closed = True
        self.resource._dns_processes.pop(self.reference, None)


def resolve_native_host(resource, scope, *, deadline):
    # This fixed check rejects a dictionary/callback before any socket or exec.
    from . import native_live_credentials as credentials
    transport = credentials._canonical_module(__package__ + '.plan_runtime_transport',
        'web/backend/services/plan_runtime_transport.py', (), ('NativePlanResource',))
    if type(resource) is not transport.NativePlanResource:
        raise credentials._closed()
    resource._require_live_execute(scope)
    stop_fd = resource._stop_fd(scope)
    deadline = _deadline(deadline)
    if sys.platform != 'linux' or not sys.flags.dont_write_bytecode:
        raise credentials._closed()
    owned = _OwnedDNS(resource, scope, deadline)
    primary = None
    try:
        owned.parent, owned.child = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        owned.remember_socket(owned.parent);owned.remember_socket(owned.child)
        owned.parent.setblocking(False)
        for s in (owned.parent, owned.child):
            s.set_inheritable(False)
        child_fd = owned.child.fileno()
        command = [sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--owned-dns-child', str(child_fd)]
        # Keep the actual object even if Popen.__init__ fails after child birth.
        p = subprocess.Popen.__new__(subprocess.Popen)
        owned.process = p
        subprocess.Popen.__init__(p, command, executable=sys.executable,
            env={'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'}, pass_fds=(child_fd,), close_fds=True,
            start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        owned.close_socket(owned.child)
        resource._require_live_execute(scope)
        nonce = os.urandom(16).hex()
        # Reserve part of the same phase budget for actual reaping, not extra time.
        work_deadline = min(deadline - .5, time.monotonic() + 9.5)
        _deadline(work_deadline)
        arm = json.dumps(['native-dns-arm-v1', os.getpid(), nonce, int(work_deadline * 1_000_000_000)], separators=(',', ':')).encode()
        _write_frame(owned.parent, arm, stop_fd, work_deadline)
        raw = _read_frame(owned.parent, stop_fd, work_deadline)
        resource._require_live_execute(scope)
        return decode_result(raw, p.pid, nonce)
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            owned.close()
        except BaseException:
            if primary is None:
                raise
            # Preserve the original failure and the actual retained owned handle.
            resource._mark_cleanup_uncertain()


def _child_read(sock):
    data = bytearray()
    while len(data) < 4:
        part = sock.recv(4 - len(data))
        if not part:
            raise ValueError('closed DNS arm')
        data.extend(part)
    size = struct.unpack('!I', data)[0]
    if not 1 <= size <= 256:
        raise ValueError('bounded DNS arm required')
    data.clear()
    while len(data) < size:
        part = sock.recv(size - len(data))
        if not part:
            raise ValueError('closed DNS arm')
        data.extend(part)
    return json.loads(data)


def _child_main():
    # Nonpublic fixed self-exec target. Not a callable/host/credential service.
    if (sys.platform != 'linux' or not sys.flags.isolated or not sys.flags.dont_write_bytecode
            or os.geteuid() <= 0 or len(sys.argv) != 3 or sys.argv[1] != '--owned-dns-child'
            or re.fullmatch(r'[0-9]{1,10}', sys.argv[2]) is None):
        return 78
    sock = socket.socket(fileno=int(sys.argv[2]))
    try:
        if sock.family != socket.AF_UNIX or sock.type != socket.SOCK_STREAM:
            return 78
        peer_pid, peer_uid, _ = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if peer_pid != os.getppid() or peer_uid != os.geteuid():
            return 78
        sock.settimeout(1)
        arm = _child_read(sock)
        if (type(arm) is not list or len(arm) != 4 or arm[0] != 'native-dns-arm-v1'
                or type(arm[1]) is not int or arm[1] != peer_pid or type(arm[2]) is not str
                or re.fullmatch(r'[0-9a-f]{32}', arm[2]) is None or type(arm[3]) is not int):
            return 78
        remaining = arm[3] / 1_000_000_000 - time.monotonic()
        if not 0 < remaining <= 10:
            return 78
        signal.signal(signal.SIGALRM, signal.SIG_DFL)
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGALRM})
        signal.setitimer(signal.ITIMER_REAL, remaining)
        answers = socket.getaddrinfo(_HOST, 443, type=socket.SOCK_STREAM)
        values = []
        for family, kind, protocol, _, address in answers:
            if family not in (socket.AF_INET, socket.AF_INET6) or kind != socket.SOCK_STREAM:
                return 78
            if address[0] not in values:
                values.append(address[0])
            if len(values) > _MAX_ADDRESSES:
                return 78
        values = list(validate_addresses(values))
        raw = json.dumps(['native-dns-result-v1', os.getpid(), arm[2], values], separators=(',', ':')).encode()
        if len(raw) > _LIMIT or time.monotonic() >= arm[3] / 1_000_000_000:
            return 78
        sock.sendall(struct.pack('!I', len(raw)) + raw)
        return 0
    except BaseException:
        return 78
    finally:
        sock.close()


if __name__ == '__main__':
    raise SystemExit(_child_main())
