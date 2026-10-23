"""Canonical native-plan transport with separate controlled/live lifetimes.

Import performs no credential, CA, DNS or connection work. Live construction
requires genuine A/C bootstrap resources; network operations additionally need
an executable session and the current actual C slot. Missing ports stay closed.
"""
from decimal import Decimal, InvalidOperation
import errno
import _thread
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import select
import socket
import ssl
import stat
import sys
import threading
import time
from uuid import uuid4

__all__ = ('open_plan_resource', 'NativePlanResource', 'OwnedBalanceReceipt', 'OwnedNativeReturn')
_FACTORY = object()
_RESOURCES, _CREDENTIALS, _PENDING, _BALANCES, _RETURNS, _CHANNELS = ({}, {}, {}, {}, {}, {})
_WALL = 8.0
_HEAD_LIMIT, _BODY_LIMIT = 16384, 65536
_PAST_RESOURCES = {}
_LIVE_WIRE_BODY_LIMIT = 393216 + 65536
_TLS_SERVER_NAME = 'api.deepseek.com'
_REF = re.compile(r'[a-zA-Z0-9._:-]{1,100}\Z')


def _core():
    family = 'web.backend.research' if __package__ == 'web.backend.services' else 'research'
    return (importlib.import_module(family + '.plan_native'),
            importlib.import_module(family + '.plan_native_runtime'),
            importlib.import_module(family + '.errors').ResearchError)


def _uncertain():
    return _core()[2]('CLEANUP_UNCERTAIN', 503, '传输权限已退休，原生连接关闭仍待核对。')


def _identity(sock):
    info = os.fstat(sock.fileno())
    return info.st_dev, info.st_ino


class _Sealed:
    __slots__ = ()

    def __setattr__(self, name, value):
        if hasattr(self, name):
            raise TypeError('native transport resource immutable')
        object.__setattr__(self, name, value)

    def __reduce__(self):
        raise TypeError('native transport resource cannot be serialized')


def _close_socket(sock):
    sock.close()


class _Channel:
    """One owned native FD; no TLS shutdown wait and no retrying requests."""
    def __init__(self, sock, deadline, owner=None, *, _factory=None):
        if _factory is not _FACTORY or not isinstance(sock, socket.socket):
            raise TypeError('owned native socket required')
        self.sock, self.deadline, self.owner = sock, deadline, owner
        self.pid, self.reference, self.identity, self.fd = os.getpid(), str(uuid4()), None, sock.fileno()
        self.active, self.closed, self.close_error = True, False, False
        self.slot_scope = getattr(owner, '_slot_scope', None)
        _CHANNELS[self.reference] = self
        if owner is not None:
            owner._channels[self.reference] = self
        try:
            self.identity = _identity(sock)
        except BaseException:
            self.active = False
            self.close_error = True
            if owner is not None:
                object.__setattr__(owner, '_cleanup_unknown', True)
                owner._uncertain_channels[self.reference] = self
            raise

    def require(self):
        if (not self.active or self.pid != os.getpid() or _CHANNELS.get(self.reference) is not self
                or self.sock.fileno() != self.fd or _identity(self.sock) != self.identity):
            raise PermissionError('native channel lifetime ended')
        if time.monotonic() >= self.deadline:
            raise TimeoutError('bounded native transport deadline')
        if self.owner is not None and self.owner.mode == 'native_live':
            self.owner._require_live_execute(self.slot_scope)
            if time.monotonic() >= self.deadline:
                raise TimeoutError('bounded native transport deadline')

    def wait(self, *, read=False):
        self.require()
        if self.owner is not None and self.owner.mode == 'native_live':
            stop = self.owner._stop_fd(self.slot_scope)
            if select.select([stop], [], [], 0)[0]:raise InterruptedError('native live slot stopped')
        if read and isinstance(self.sock, ssl.SSLSocket) and self.sock.pending():
            return
        remaining = self.deadline - time.monotonic()
        stop = self.owner._stop_fd(self.slot_scope) if self.owner is not None and self.owner.mode == 'native_live' else None
        readers = ([self.sock] if read else []) + ([stop] if stop is not None else [])
        r, w, failed = select.select(readers, [] if read else [self.sock], [self.sock], max(0, remaining))
        if stop is not None and stop in r:
            raise InterruptedError('native live slot stopped')
        if failed or not (r if read else w):
            raise TimeoutError('bounded native transport deadline')

    def send_first(self, data):
        self.require()
        # Exactly one nonblocking syscall. SSLWant*/EAGAIN propagate as an
        # ambiguous consumed send; waiting/retrying here would hold Owner.
        # Only the actual registered Pending path may mark this observation.
        # Validate before marking, then enter send even if it wants TLS I/O,
        # raises, returns zero or writes only part of the request.
        frame = sys._getframe(1)
        try:
            for _ in range(8):
                if frame is None:
                    break
                if frame.f_code is _PENDING_FIRST_WRITE_CODE and frame.f_globals is globals():
                    pending = frame.f_locals.get('self')
                    capability = frame.f_locals.get('capability')
                    _, flow, _ = _core()
                    if (type(pending) is _Pending and _PENDING.get(pending.reference) is pending
                            and pending.channel is self and pending.active and pending.pid == os.getpid()
                            and pending.attempted and type(capability) is flow.NativePlanSendLease and capability.used):
                        object.__setattr__(pending, 'first_write_syscall_entered', True)
                    break
                frame = frame.f_back
        finally:
            del frame
        sent = self.sock.send(data)
        if sent <= 0:
            raise OSError('native first write interrupted')
        return sent

    def send_remaining(self, data):
        pending = memoryview(data)
        read_ready = False
        while pending:
            self.wait(read=read_ready)
            try:
                sent = self.sock.send(pending)
            except ssl.SSLWantReadError:
                read_ready = True
                continue
            except (ssl.SSLWantWriteError, BlockingIOError):
                read_ready = False
                continue
            if sent <= 0:
                raise OSError('native remainder interrupted')
            pending = pending[sent:]
            read_ready = False

    def receive(self):
        if self.owner is not None and self.owner.mode == 'native_live':
            self.owner._require_live_execute(self.slot_scope)
            parser = _LiveHTTPParser(self.owner._body_limit())
            read_ready = True
            while not parser.done:
                self.wait(read=read_ready)
                try:chunk = self.sock.recv(16384)
                except ssl.SSLWantWriteError:read_ready = False;continue
                except (ssl.SSLWantReadError, BlockingIOError):read_ready = True;continue
                if not chunk:return parser.finish()
                parser.feed(chunk);read_ready = True
            return parser.finish()
        raw = bytearray()
        read_ready = True
        while True:
            self.wait(read=read_ready)
            try:
                chunk = self.sock.recv(16384)
            except ssl.SSLWantWriteError:
                read_ready = False
                continue
            except (ssl.SSLWantReadError, BlockingIOError):
                read_ready = True
                continue
            if not chunk:
                break
            raw.extend(chunk)
            read_ready = True
            if len(raw) > _HEAD_LIMIT + _BODY_LIMIT:
                raise ValueError('native HTTP response bound')
            if b'\r\n\r\n' not in raw and len(raw) > _HEAD_LIMIT:
                raise ValueError('native HTTP header bound')
        return _parse_response(bytes(raw))

    def close(self):
        self.active = False
        def proved_closed():
            if self.sock.fileno() >= 0:
                return False
            try:
                os.fstat(self.fd)
            except OSError as error:
                return error.errno == errno.EBADF
            return False
        if not self.closed:
            try:
                if self.sock.fileno() >= 0:
                    if self.pid != os.getpid() or self.sock.fileno() != self.fd or _identity(self.sock) != self.identity:
                        raise PermissionError('cannot close an unknown native FD')
                    _close_socket(self.sock)
                    if self.sock.fileno() >= 0:
                        raise OSError('native close not confirmed')
                else:
                    # A detached socket is not proof that its FD was closed.
                    try:
                        os.fstat(self.fd)
                    except OSError as error:
                        if error.errno != errno.EBADF:
                            raise
                    else:
                        raise PermissionError('detached native FD remains unknown')
            except BaseException:
                self.close_error = True
                if self.owner is not None:
                    object.__setattr__(self.owner, '_cleanup_unknown', True)
                    self.owner._uncertain_channels[self.reference] = self
                raise _uncertain() from None
            finally:
                if proved_closed():
                    self.closed = True
                    _CHANNELS.pop(self.reference, None)
                    if self.owner is not None:
                        self.owner._channels.pop(self.reference, None)
        if self.close_error:
            raise _uncertain()


def _upgrade_tls(channel, context):
    """Fixed-host TLS over an owned socket, with no DNS or secret here.

    Controlled components may supply their owned test CA. The gated live
    caller constructs the default CA context; verification stays enabled.
    """
    channel.require()
    if type(context) is not ssl.SSLContext or not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise PermissionError('verified TLS context required')
    wrapped = context.wrap_socket(channel.sock, server_hostname=_TLS_SERVER_NAME, do_handshake_on_connect=False)
    channel.sock = wrapped
    wrapped.setblocking(False)
    while True:
        channel.require()
        try:
            wrapped.do_handshake()
            return channel
        except ssl.SSLWantReadError:
            channel.wait(read=True)
        except ssl.SSLWantWriteError:
            channel.wait()


def _parse_response(raw):
    head, separator, body = raw.partition(b'\r\n\r\n')
    if not separator or len(head) > _HEAD_LIMIT or len(body) > _BODY_LIMIT:
        raise ValueError('bounded complete HTTP response required')
    lines = head.split(b'\r\n')
    status = re.fullmatch(rb'HTTP/1\.[01] ([1-5][0-9]{2})(?: [\x20-\x7e]*)?', lines[0])
    if status is None:
        raise ValueError('native HTTP status invalid')
    headers = {}
    for line in lines[1:]:
        key, colon, value = line.partition(b':')
        key = key.lower()
        if (not colon or re.fullmatch(rb"[!#$%&'*+.^_`|~0-9a-z-]+", key) is None
                or key in headers or any(c < 32 and c != 9 for c in value) or b'\x7f' in value):
            raise ValueError('native HTTP headers ambiguous')
        headers[key] = value.strip()
    if b'transfer-encoding' in headers or headers.get(b'content-encoding', b'identity') != b'identity':
        raise ValueError('native encoded response unsupported')
    length = headers.get(b'content-length')
    if length is not None and (not length.isdigit() or len(length) > 6 or int(length) != len(body)):
        raise ValueError('native HTTP response incomplete')
    return int(status[1]), body


class _LiveHTTPParser:
    """Pure incremental strict framing, with no credential or network port."""
    def __init__(self, body_limit):
        if type(body_limit) is not int or body_limit not in (65536, 393216):
            raise ValueError('fixed live response limit required')
        self.limit, self.buffer, self.body = body_limit, bytearray(), bytearray()
        self.status, self.mode, self.remaining = None, 'headers', None
        self.chunks, self.wire, self.header_size, self.done = 0, 0, 0, False
    def _body(self, data):
        if len(self.body) + len(data) > self.limit:
            raise ValueError('native decoded response bound')
        self.body.extend(data)
    def feed(self, data):
        if type(data) is not bytes or (self.done and data):
            raise ValueError('native response trailing bytes')
        self.wire += len(data)
        if self.wire > _HEAD_LIMIT + _LIVE_WIRE_BODY_LIMIT:
            raise ValueError('native wire response bound')
        if self.header_size and self.wire - self.header_size > _LIVE_WIRE_BODY_LIMIT:
            raise ValueError('native wire body bound')
        self.buffer.extend(data)
        while not self.done:
            if self.mode == 'headers':
                end = self.buffer.find(b'\r\n\r\n')
                if end < 0:
                    if len(self.buffer) > _HEAD_LIMIT:raise ValueError('native response header bound')
                    return
                self.header_size = end + 4
                if self.wire - self.header_size > _LIVE_WIRE_BODY_LIMIT:raise ValueError('native wire body bound')
                if self.header_size > _HEAD_LIMIT:raise ValueError('native response header bound')
                lines = bytes(self.buffer[:end]).split(b'\r\n');del self.buffer[:end + 4]
                status = re.fullmatch(rb'HTTP/1\.[01] ([1-5][0-9]{2})(?: [\x20-\x7e]*)?', lines[0])
                if status is None:raise ValueError('native HTTP status invalid')
                self.status = int(status[1])
                if self.status < 200 or 300 <= self.status < 400:raise ValueError('native HTTP redirect/information refused')
                headers = {}
                for line in lines[1:]:
                    key, colon, value = line.partition(b':');key = key.lower()
                    if (not colon or re.fullmatch(rb"[!#$%&'*+.^_`|~0-9a-z-]+", key) is None or key in headers
                            or any(c < 32 and c != 9 for c in value) or b'\x7f' in value):
                        raise ValueError('native HTTP headers ambiguous')
                    headers[key] = value.strip()
                if headers.get(b'content-encoding', b'identity').lower() != b'identity':raise ValueError('native compression refused')
                transfer, length = headers.get(b'transfer-encoding'), headers.get(b'content-length')
                if transfer is not None:
                    if length is not None or transfer.lower() != b'chunked':raise ValueError('native HTTP framing conflict')
                    self.mode = 'chunk-size'
                elif length is not None:
                    if re.fullmatch(rb'[0-9]{1,9}', length) is None or int(length) > self.limit:raise ValueError('native HTTP length invalid')
                    self.remaining, self.mode = int(length), 'length'
                else:self.mode = 'eof'
            elif self.mode == 'length':
                count = min(len(self.buffer), self.remaining)
                self._body(self.buffer[:count]);del self.buffer[:count];self.remaining -= count
                if self.remaining:return
                self.done = True
            elif self.mode == 'eof':
                self._body(self.buffer);self.buffer.clear();return
            elif self.mode == 'chunk-size':
                end = self.buffer.find(b'\r\n')
                if end < 0:
                    if len(self.buffer) > 128:raise ValueError('native chunk line bound')
                    return
                line = bytes(self.buffer[:end]);del self.buffer[:end + 2]
                if len(line) > 128 or re.fullmatch(rb'[0-9a-fA-F]{1,8}', line) is None:raise ValueError('native chunk syntax')
                self.chunks += 1
                if self.chunks > 1024:raise ValueError('native chunk count bound')
                self.remaining = int(line, 16)
                if self.remaining > self.limit - len(self.body):raise ValueError('native decoded response bound')
                self.mode = 'chunk-data' if self.remaining else 'chunk-end'
            elif self.mode == 'chunk-data':
                count = min(len(self.buffer), self.remaining)
                self._body(self.buffer[:count]);del self.buffer[:count];self.remaining -= count
                if self.remaining:return
                self.mode = 'chunk-crlf'
            elif self.mode == 'chunk-crlf':
                if len(self.buffer) < 2:return
                if self.buffer[:2] != b'\r\n':raise ValueError('native chunk separator invalid')
                del self.buffer[:2];self.mode = 'chunk-size'
            elif self.mode == 'chunk-end':
                if len(self.buffer) < 2:return
                if self.buffer[:2] != b'\r\n':raise ValueError('native trailers refused')
                del self.buffer[:2];self.done = True
        if self.buffer:raise ValueError('native response trailing bytes')
        if self.wire - self.header_size > _LIVE_WIRE_BODY_LIMIT:raise ValueError('native wire body bound')
    def finish(self):
        if self.mode == 'eof':self.done = True
        if not self.done or self.buffer:raise ValueError('native response incomplete')
        return self.status, bytes(self.body)


class _FixtureCredential(_Sealed):
    __slots__ = ('resource', 'economic_binding', 'incarnation', 'reference', 'pid', 'active')

    def __init__(self, resource, *, _factory=None):
        if _factory is not _FACTORY or type(resource) is not NativePlanResource or _RESOURCES.get(resource.reference) is not resource:
            raise TypeError('actual controlled credential factory required')
        self.resource, self.economic_binding, self.incarnation = resource, resource.economic_binding, resource.credential_incarnation
        self.reference, self.pid, self.active = str(uuid4()), os.getpid(), True
        _CREDENTIALS[self.reference] = self

    def require(self, resource):
        if (not self.active or self.pid != os.getpid() or _CREDENTIALS.get(self.reference) is not self
                or self.resource is not resource or resource._credential is not self
                or (self.economic_binding, self.incarnation) != (resource.economic_binding, resource.credential_incarnation)):
            raise PermissionError('same controlled credential lifetime required')

    def close(self):
        object.__setattr__(self, 'active', False)
        _CREDENTIALS.pop(self.reference, None)


class NativePlanResource(_Sealed):
    __slots__ = ('permit', 'mode', 'producer', 'economic_binding', 'credential_incarnation', 'flight',
                 'pid', 'reference', 'active', '_runtime_digest', '_credential', '_balance', '_deadline',
                 '_endpoint', '_channels', '_uncertain_channels', '_cleanup_unknown', '_live_session', '_slot_scope', '_dns_processes')

    def __init__(self, permit, *, startup_scope=None, _factory=None):
        core, _, error = _core()
        if _factory is not _FACTORY or type(permit) is not core.NativeRuntimePermit:
            raise PermissionError('fixed Core runtime permit required')
        live = getattr(permit.provision.authority, 'live_session', None)
        if live is not None:
            from . import native_live_credentials as credentials
            a = credentials._a()
            if type(live) is not a.NativeLiveSession:
                raise error('FUNDING_CLOSED', 503, '真实模型会话未绑定。')
            permit.require_bootstrap(startup_scope)
            live.require_bootstrap(startup_scope)
            facts = permit.data_bootstrap(startup_scope)
            if (facts['mode'] != 'native_live' or type(live.credential) is not credentials.NativeLiveCredential
                    or type(live.thread_flight) is not _thread.LockType):
                raise error('FUNDING_CLOSED', 503, '实际凭据和共享线程锁尚未绑定。')
            live.credential.require_bootstrap(live.grant, live.flight, main_context=startup_scope)
        else:
            facts = permit.data()
            if facts['mode'] != 'controlled_fixture':
                raise error('FUNDING_CLOSED', 503, '真实凭据和原生资金资源尚未绑定。')
        if (Path(__file__).is_symlink() or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != facts['runtime_digest']
                or any(type(facts[k]) is not str or _REF.fullmatch(facts[k]) is None for k in ('economic_binding', 'credential_incarnation'))):
            raise PermissionError('fixed Runtime code and controlled identity required')
        self.permit, self.mode, self.producer = permit, facts['mode'], 'owned-native-plan-runtime-v1'
        self.economic_binding, self.credential_incarnation = facts['economic_binding'], facts['credential_incarnation']
        self.flight, self.pid, self.reference, self.active = (live.thread_flight if live is not None else threading.Lock()), os.getpid(), str(uuid4()), True
        self._runtime_digest, self._credential, self._balance, self._deadline = facts['runtime_digest'], None, None, None
        self._endpoint, self._channels, self._cleanup_unknown = None, {}, False
        self._uncertain_channels = {}
        self._live_session, self._slot_scope, self._dns_processes = live, None, {}
        if live is not None:
            object.__setattr__(self, '_credential', live.credential)
        _RESOURCES[self.reference] = self
        if live is not None:_PAST_RESOURCES[self.reference] = self

    def require(self, *, current=True):
        if self.mode == 'native_live':
            if current:self._require_live_current()
            else:self._require_live_past(self._slot_scope)
            return
        if not self.active or self.pid != os.getpid() or _RESOURCES.get(self.reference) is not self:
            raise PermissionError('native Runtime resource retired')
        if self._cleanup_unknown:
            raise _uncertain()
        facts = self.permit.data(current=current)
        if (facts['mode'], facts['economic_binding'], facts['credential_incarnation'], facts['runtime_digest']) != (
                self.mode, self.economic_binding, self.credential_incarnation, self._runtime_digest):
            raise PermissionError('native Runtime binding changed')
        if Path(__file__).is_symlink() or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != self._runtime_digest:
            raise PermissionError('native Runtime code changed')

    def require_bootstrap(self, startup_scope):
        if self.mode != 'native_live':
            self.require()
            return
        self._live_birth()
        self.permit.require_bootstrap(startup_scope)
        session = self._live_session
        session.require_bootstrap(startup_scope)
        if (self.permit.provision.authority.live_session is not session
                or self.flight is not session.thread_flight or self._credential is not session.credential):
            raise PermissionError('actual bootstrap resource/session pairing required')
        self._credential.require_bootstrap(session.grant, session.flight, main_context=startup_scope)

    def _mark_cleanup_uncertain(self):
        object.__setattr__(self, '_cleanup_unknown', True)

    def _live_birth(self, *, past=False):
        registry = _PAST_RESOURCES if past else _RESOURCES
        if (self.pid != os.getpid() or registry.get(self.reference) is not self or self.mode != 'native_live'
                or self._cleanup_unknown or (not self.active and not past)
                or hashlib.sha256(Path(__file__).read_bytes()).hexdigest() != self._runtime_digest):
            raise _core()[2]('FUNDING_CLOSED', 503, '实际原生资源当前关闭。')

    def _require_live_current(self):
        # Presence/preview/confirmation is not permission to begin IO. It may
        # precede slot birth, but still needs the real executable A/B pairing.
        self._live_birth()
        from . import native_live_credentials as credentials
        a = credentials._a()
        session = self._live_session
        if (type(session) is not a.NativeLiveSession or type(self._credential) is not credentials.NativeLiveCredential
                or a.credential_session_binding(session, self._credential) is not True
                or self.permit.provision.authority.live_session is not session
                or self._credential is not session.credential or self.flight is not session.thread_flight
                or type(self.flight) is not _thread.LockType):
            raise credentials._closed()
        session.require()  # Native starting/cleanup-only states remain closed.
        self._credential.require_current(session)
        facts = self.permit.data()
        if (facts['mode'], facts['economic_binding'], facts['credential_incarnation'], facts['runtime_digest']) != (
                self.mode, self.economic_binding, self.credential_incarnation, self._runtime_digest):
            raise credentials._closed()
        _core()[0].purpose_scope(self)

    def _require_live_execute(self, scope):
        self._live_birth()
        from . import native_live_credentials as credentials
        c = credentials._c()
        if type(scope) is not c.NativePlanSlotLease or scope is not self._slot_scope:
            raise credentials._closed()
        session = self._live_session
        if (c.require_slot(scope, session.store, session, task_id=scope.task_id,
                purpose=_core()[0].purpose_scope(self), mode='execute') is not None):
            raise credentials._closed()
        self._require_live_current()

    def _require_live_past(self, scope):
        self._live_birth(past=True)
        self.permit.require(current=False, past_scope=scope)
        self._credential.require_past(self._live_session, scope)

    def _stop_fd(self, scope):
        self._require_live_execute(scope)
        import fcntl
        fd, identity = scope.stop_fd, scope.stop_fd_identity
        if (type(fd) is not int or fd < 0 or type(identity) is not tuple or len(identity) != 2
                or any(type(v) is not int or v < 0 for v in identity)):
            raise PermissionError('actual slot stop FD required')
        info = os.fstat(fd)
        if (not stat.S_ISFIFO(info.st_mode) or (info.st_dev, info.st_ino) != identity
                or not fcntl.fcntl(fd, fcntl.F_GETFL) & os.O_NONBLOCK or os.get_inheritable(fd)):
            raise PermissionError('original nonblocking slot stop FD required')
        return fd

    def _body_limit(self):
        return 393216 if _core()[0].purpose_scope(self) == 'evidence_method_plan_v1' else 65536

    def _connect_live(self):
        self._require_live_execute(self._slot_scope)
        if any(name in os.environ for name in ('SSL_CERT_FILE','SSL_CERT_DIR','SSLKEYLOGFILE')):
            raise PermissionError('native CA/keylog override refused')
        from . import native_dns_process
        addresses = native_dns_process.resolve_native_host(self, self._slot_scope, deadline=self._deadline)
        address = addresses[0]
        import ipaddress
        family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
        sock = socket.socket(family, socket.SOCK_STREAM)
        channel = _Channel(sock, self._deadline, self, _factory=_FACTORY)
        try:
            sock.setblocking(False)
            target = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
            self._require_live_execute(self._slot_scope)
            result = sock.connect_ex(target)
            if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):raise OSError('native TLS connection unavailable')
            channel.wait()
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) or ipaddress.ip_address(sock.getpeername()[0]) != ipaddress.ip_address(address):
                raise PermissionError('native numeric peer differs')
            context = ssl.create_default_context()
            if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED or context.keylog_filename is not None:
                raise PermissionError('fixed verified default TLS context required')
            return _upgrade_tls(channel, context)
        except BaseException:
            try:channel.close()
            except BaseException:self._mark_cleanup_uncertain()
            raise

    def _connect(self):
        if self.mode == 'native_live':return self._connect_live()
        self.require()
        endpoint = self.permit.controlled_endpoint()
        if (type(endpoint) is not tuple or len(endpoint) != 2 or endpoint[0] != '127.0.0.1'
                or type(endpoint[1]) is not int or not 1 <= endpoint[1] <= 65535):
            raise PermissionError('owned controlled endpoint required')
        if self._endpoint is not None and endpoint != self._endpoint:
            raise PermissionError('controlled endpoint changed')
        object.__setattr__(self, '_endpoint', endpoint)
        self._credential.require(self)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        channel = _Channel(sock, self._deadline, self, _factory=_FACTORY)
        try:
            sock.setblocking(False)
            outcome = sock.connect_ex(endpoint)
            if outcome not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY):
                raise OSError('controlled connection unavailable')
            channel.wait()
            if sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                raise OSError('controlled connection unavailable')
            return channel
        except BaseException:
            try:
                channel.close()
            except BaseException:
                pass  # sticky resource UNKNOWN is exposed by resource.close.
            raise

    def _request(self, method, path, raw):
        if self.mode == 'native_live':
            self._require_live_execute(self._slot_scope)
            if type(raw) is not bytes or (method,path) not in (('GET','/user/balance'),('POST','/chat/completions')):
                raise PermissionError('fixed live HTTP operation required')
            authorization = self._credential._authorization(self._live_session, self, self._slot_scope)
            return (method + ' ' + path + ' HTTP/1.1\r\nHost: api.deepseek.com\r\nConnection: close\r\nContent-Type: application/json\r\nAccept-Encoding: identity\r\nAuthorization: ').encode('ascii') + authorization + ('\r\nContent-Length: ' + str(len(raw)) + '\r\n\r\n').encode('ascii') + raw
        self._credential.require(self)
        if type(raw) is not bytes or (method, path) not in (('GET', '/user/balance'), ('POST', '/chat/completions')):
            raise PermissionError('fixed controlled HTTP operation required')
        return (method + ' ' + path + ' HTTP/1.0\r\nHost: 127.0.0.1\r\nConnection: close\r\nContent-Type: application/json\r\n'
                'X-Fixture-Incarnation: ' + self.credential_incarnation + '\r\nX-Fixture-Credential-Instance: ' + self._credential.reference
                + '\r\nContent-Length: ' + str(len(raw)) + '\r\n\r\n').encode('ascii') + raw

    def balance(self, capability):
        _, flow, error = _core()
        if type(capability) is not flow.NativeBalanceLease:
            raise PermissionError('actual pre-GET balance lease required')
        if self.mode == 'native_live':
            scope = getattr(capability, 'slot_scope', None)
            object.__setattr__(self, '_slot_scope', scope)
            self._require_live_execute(scope)
        claim = capability.consume(self)
        self.require()
        object.__setattr__(self, '_balance', None)
        object.__setattr__(self, '_deadline', time.monotonic() + (10.0 if self.mode == 'native_live' else _WALL))
        if self._credential is None:
            object.__setattr__(self, '_credential', _FixtureCredential(self, _factory=_FACTORY))
        channel = self._connect()
        primary = None
        try:
            channel.send_remaining(self._request('GET', '/user/balance', b''))
            status, raw = channel.receive()
        except BaseException as exc:
            primary = exc
            raise
        finally:
            try:
                channel.close()
            except BaseException:
                if primary is None:
                    raise
        data = flow.strict_json(raw, _BODY_LIMIT)
        if status != 200 or type(data) is not dict or data.get('is_available') is not True:
            raise error('BUDGET_UNVERIFIED', 503, '当前受控余额不可核对。')
        infos = data.get('balance_infos')
        if type(infos) is not list or len(infos) != 1 or type(infos[0]) is not dict or infos[0].get('currency') != 'CNY':
            raise ValueError('one exact controlled CNY balance required')
        text = infos[0].get('total_balance')
        if type(text) is not str or not 1 <= len(text) <= 32 or re.fullmatch(r'[0-9]+(?:\.[0-9]{1,6})?', text) is None:
            raise ValueError('bounded native cash required')
        try:
            units = Decimal(text) * 1000000
        except InvalidOperation:
            raise ValueError('bounded native cash required') from None
        if not units.is_finite() or units < 0 or units > 9223372036854775807 or units != units.to_integral_value():
            raise ValueError('native CNY units required')
        receipt = OwnedBalanceReceipt(self, claim, int(units), hashlib.sha256(raw).hexdigest(), _factory=_FACTORY)
        object.__setattr__(self, '_balance', receipt)
        return receipt

    def prepare_post(self):
        self.require()
        if self.mode == 'native_live':self._require_live_execute(self._slot_scope)
        if self._credential is None or self._balance is None:
            raise PermissionError('same credential must complete balance first')
        self._balance.require(self, self._balance.claim)
        if any(p.resource is self and p.active for p in _PENDING.values()):
            raise PermissionError('one pending POST per controlled resource')
        if self.mode == 'native_live':object.__setattr__(self, '_deadline', time.monotonic() + 10.0)
        channel = self._connect()
        try:
            return _Pending(self, channel, self._balance.claim, self._credential, _factory=_FACTORY)
        except BaseException:
            try:
                channel.close()
            except BaseException:
                pass
            raise

    def retire_unhanded(self):
        """Drain only this PID/resource's IO, never retire a business grant.

        Closed-but-uncertain socket objects remain retained as evidence. The
        error is sticky even if a later attempt proves physical closure.
        """
        if self.pid != os.getpid():
            raise PermissionError('only this native resource PID can retire IO')
        errors = []
        for process in tuple(self._dns_processes.values()):
            try:process.close()
            except BaseException as error:errors.append(type(error).__name__)
        channels = {**self._uncertain_channels, **self._channels}
        for channel in tuple(channels.values()):
            try:
                channel.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        if errors or self._cleanup_unknown:
            object.__setattr__(self, '_cleanup_unknown', True)
            raise _uncertain()
        return None

    def close(self):
        object.__setattr__(self, 'active', False)
        _RESOURCES.pop(self.reference, None)
        errors = []
        values = [p for p in tuple(_PENDING.values()) if p.resource is self]
        values += [v for registry in (_BALANCES, _RETURNS) for v in tuple(registry.values()) if v.resource is self]
        values += list({**self._uncertain_channels, **self._channels}.values()) + ([self._credential] if self._credential and self.mode != 'native_live' else [])
        values += list(self._dns_processes.values())
        for value in values:
            try:
                value.close()
            except BaseException as exc:
                errors.append(type(exc).__name__)
        if errors or self._cleanup_unknown:
            object.__setattr__(self, '_cleanup_unknown', True)
            raise _uncertain()


class OwnedBalanceReceipt(_Sealed):
    __slots__ = ('resource', 'claim', 'balance_units', 'response_digest', 'observed_at', 'credential_incarnation', 'reference', 'pid', 'active', 'slot_scope')

    def __init__(self, resource, claim, units, response_digest, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('owned actual balance factory required')
        self.resource, self.claim, self.balance_units, self.response_digest = resource, claim, units, response_digest
        self.observed_at, self.credential_incarnation = int(time.time()), resource.credential_incarnation
        self.slot_scope = resource._slot_scope
        self.reference, self.pid, self.active = str(uuid4()), os.getpid(), True
        _BALANCES[self.reference] = self

    def require(self, resource, claim):
        if (not self.active or self.pid != os.getpid() or _BALANCES.get(self.reference) is not self
                or self.resource is not resource or self.claim != claim or self.credential_incarnation != resource.credential_incarnation):
            raise PermissionError('owned current balance claim required')
        if resource.mode == 'native_live':
            if self.slot_scope is not resource._slot_scope:raise PermissionError('original live balance slot required')
            resource._require_live_execute(self.slot_scope)
        else:resource.require()

    def audit(self):
        self.require(self.resource, self.claim)
        return dict(protocol='owned-balance-v1', mode=self.resource.mode, balance_units=self.balance_units, currency='CNY',
                    observed_at=self.observed_at, response_digest=self.response_digest, credential_incarnation=self.credential_incarnation)

    def close(self):
        object.__setattr__(self, 'active', False)
        _BALANCES.pop(self.reference, None)


class _Pending(_Sealed):
    __slots__ = ('resource', 'channel', 'claim', 'credential', 'reference', 'pid', 'active', 'attempted', 'first_write_syscall_entered', 'grant', 'remaining', 'received', 'slot_scope')

    def __init__(self, resource, channel, claim, credential, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('actual owned pending required')
        self.resource, self.channel, self.claim, self.credential = resource, channel, claim, credential
        self.reference, self.pid, self.active, self.attempted = str(uuid4()), os.getpid(), True, False
        self.first_write_syscall_entered = False
        self.slot_scope = resource._slot_scope
        self.grant, self.remaining, self.received = None, None, False
        _PENDING[self.reference] = self

    def require(self):
        if not self.active or self.pid != os.getpid() or _PENDING.get(self.reference) is not self:
            raise PermissionError('native pending retired')
        self.channel.require()
        self.resource.require(current=False)
        if self.resource.mode == 'native_live':
            self.resource._require_live_execute(self.slot_scope)
            self.credential.require_current(self.resource._live_session)
        else:self.credential.require(self.resource)

    def write_first(self, capability):
        ports, flow, _ = _core()
        self.require()
        if self.attempted or type(capability) is not flow.NativePlanSendLease:
            raise PermissionError('actual once-only native send lease required')
        if self.resource.mode == 'native_live' and getattr(capability, 'slot_scope', None) is not self.slot_scope:
            raise PermissionError('original live send slot required')
        object.__setattr__(self, 'attempted', True)
        if ports.purpose_scope(self.resource) == 'evidence_method_plan_v1':
            descriptor = capability.inspect_payload(self.resource)
            if type(descriptor) is not flow.EvidenceMethodPayload:
                raise TypeError('canonical evidence payload data required')
            codec = importlib.import_module(flow.__package__ + '.evidence_method_plan_codec')
            codec.decode_request(descriptor.raw, descriptor.domain, descriptor.exact_input, descriptor.selection_manifest)
            consumed = capability.consume(self.resource)
            if type(consumed) is not flow.EvidenceMethodPayload or consumed != descriptor:
                raise PermissionError('inspected evidence payload changed before consume')
            raw, dispatch, nonce, admission, producer = (consumed.raw, consumed.dispatch_id,
                consumed.nonce, consumed.admission_digest, consumed.producer_digest)
        else:
            raw, dispatch, nonce, admission, producer = capability.consume(self.resource)
        if (dispatch, nonce) != self.claim:
            raise PermissionError('balance and send claims differ')
        request = self.resource._request('POST', '/chat/completions', raw)
        entered = time.monotonic()
        sent = self.channel.send_first(request)
        if self.resource.mode == 'native_live':self.channel.deadline = entered + 180.0
        object.__setattr__(self, 'grant', (dispatch, nonce, admission, producer))
        object.__setattr__(self, 'remaining', request[sent:])

    def receive(self):
        self.require()
        if self.grant is None or self.received:
            raise PermissionError('one actual first write and return required')
        object.__setattr__(self, 'received', True)
        self.channel.send_remaining(self.remaining)
        if self.resource.mode == 'native_live':object.__setattr__(self, 'remaining', b'')
        status, body = self.channel.receive()
        # Ownership transfers before any fallible close. Core commits the
        # financial return before independently attempting pending.close().
        return OwnedNativeReturn(self.resource, self.grant, status, body, slot_scope=self.slot_scope, _factory=_FACTORY)

    def close(self):
        object.__setattr__(self, 'active', False)
        _PENDING.pop(self.reference, None)
        if self.resource.mode == 'native_live':object.__setattr__(self, 'remaining', b'')
        self.channel.close()


_PENDING_FIRST_WRITE_CODE = _Pending.write_first.__code__


class OwnedNativeReturn(_Sealed):
    __slots__ = ('resource', 'dispatch', 'nonce', 'admission_digest', 'producer_digest', 'status', 'body', 'mode', 'reference', 'pid', 'active', 'slot_scope')

    def __init__(self, resource, grant, status, body, *, slot_scope=None, _factory=None):
        if _factory is not _FACTORY or type(body) is not bytes or len(body) > (resource._body_limit() if resource.mode == 'native_live' else _BODY_LIMIT):
            raise TypeError('actual bounded native return required')
        self.resource = resource
        self.slot_scope = slot_scope
        self.dispatch, self.nonce, self.admission_digest, self.producer_digest = grant
        self.status, self.body, self.mode = status, body, resource.mode
        self.reference, self.pid, self.active = str(uuid4()), os.getpid(), True
        _RETURNS[self.reference] = self

    def require(self, resource, dispatch, nonce, admission_digest, producer_digest):
        if (not self.active or self.pid != os.getpid() or _RETURNS.get(self.reference) is not self or self.resource is not resource
                or (self.dispatch, self.nonce, self.admission_digest, self.producer_digest) != (dispatch, nonce, admission_digest, producer_digest)
                or self.mode != resource.mode):
            raise PermissionError('original owned native return required')
        if resource.mode == 'native_live':resource._require_live_past(self.slot_scope)
        else:resource.require(current=False)

    def close(self):
        object.__setattr__(self, 'active', False)
        _RETURNS.pop(self.reference, None)


def open_plan_resource(permit, *, startup_scope=None):
    core, _, _ = _core()
    if type(permit) is not core.NativeRuntimePermit:
        raise PermissionError('fixed Core runtime permit required')
    if getattr(permit.provision.authority, 'live_session', None) is not None:permit.require_bootstrap(startup_scope)
    else:permit.require()
    return NativePlanResource(permit, startup_scope=startup_scope, _factory=_FACTORY)
