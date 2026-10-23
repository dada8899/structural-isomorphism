"""Fixed systemd provider boundary. Import performs no secret or app work.

Only the hardened formal entry can publish the real directory witness. Shape
helpers are deliberately data-only; they cannot create a live credential.
"""
import ctypes
import hashlib
import hmac
import importlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import sys
import threading
import types

_DIRECTORY = '/run/credentials/structural-web.service'
_COMPONENTS = ('run', 'credentials', 'structural-web.service')
_PROVIDER = 'structural-deepseek-api-key'
_ROOT = Path(__file__).resolve().parents[3]
_FACTORY = object()
_ENTRIES, _KEYS, _ATTEMPTS, _UNCERTAIN = {}, {}, {}, []
_TOKEN = re.compile(rb'[A-Za-z0-9._~+/-]+={0,}\Z')


def _closed():
    family = 'web.backend.research' if __package__ == 'web.backend.services' else 'research'
    error = importlib.import_module(family + '.errors').ResearchError
    return error('FUNDING_CLOSED', 503, '真实模型凭据尚未完成受信绑定。')


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode),
            info.st_nlink, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _canonical_module(name, relative, functions=(), classes=()):
    path = _ROOT / relative
    if path.is_symlink() or not path.is_file() or path != path.resolve():
        raise _closed()
    raw = path.read_bytes()
    if len(raw) > 262144:
        raise _closed()
    module = importlib.import_module(name)
    if (type(module) is not types.ModuleType or module.__name__ != name
            or Path(module.__file__).resolve() != path):
        raise _closed()
    compiled = compile(raw, str(path), 'exec', dont_inherit=True)
    codes = {c.co_name: c for c in compiled.co_consts if isinstance(c, types.CodeType)}
    for label in functions:
        function = getattr(module, label, None)
        if (type(function) is not types.FunctionType or function.__globals__ is not vars(module)
                or function.__module__ != name or function.__code__ != codes.get(label)):
            raise _closed()
    for label in classes:
        cls = getattr(module, label, None)
        if type(cls) is not type or cls.__module__ != name or cls.__name__ != label:
            raise _closed()
    return module


def _a():
    family = 'web.backend.research' if __package__ == 'web.backend.services' else 'research'
    return _canonical_module(family + '.native_live_grant', 'web/backend/research/native_live_grant.py',
        ('credential_bootstrap_binding', 'credential_session_binding'),
        ('NativeLiveGrantWitness', 'NativeLiveFlightLease', 'NativeLiveSession'))


def _c():
    family = 'web.backend.research' if __package__ == 'web.backend.services' else 'research'
    return _canonical_module(family + '.native_plan_supervisor', 'web/backend/research/native_plan_supervisor.py',
        ('require_startup_scope', 'require_slot', 'require_lifecycle_scope'),
        ('MainStartupScope', 'NativePlanSlotLease', 'NativeLifecycleScope'))


def _formal_metadata_entry():
    # The sole helper is the one attested before Formal read its five files.
    # Never import a second package spelling or accept a caller-supplied policy.
    path = _ROOT / 'scripts/run-formal-main.py'
    module = sys.modules.get('__main__')
    if (type(module) is not types.ModuleType or getattr(module, '__file__', None) != str(path)
            or path.is_symlink() or path != path.resolve()):raise _closed()
    codes = {c.co_name:c for c in compile(path.read_bytes(), str(path), 'exec', dont_inherit=True).co_consts
             if isinstance(c, types.CodeType)}
    for name in ('_require_metadata_helper', '_capture_metadata', '_capture_consumer', '_metadata_pair'):
        function = getattr(module, name, None)
        if (type(function) is not types.FunctionType or function.__globals__ is not vars(module)
                or function.__module__ != '__main__' or function.__code__ != codes.get(name)):raise _closed()
    helper = module._require_metadata_helper()
    if helper is not sys.modules.get('systemd_credential_metadata'):raise _closed()
    return module


def _directory_snapshots(descriptors, uid):
    entry = _formal_metadata_entry()
    identities = []
    for i, fd in enumerate(descriptors):
        parent, name = (None, '/') if i == 0 else (descriptors[i-1], _COMPONENTS[i-1])
        snapshot, _ = entry._metadata_pair(parent, name, fd, uid, 'directory' if i == 3 else 'ancestor')
        identities.append(tuple(snapshot[key] for key in entry._require_metadata_helper().SNAPSHOT_FIELDS))
    return tuple(identities)


def _provider_snapshot(fd, directory, uid):
    entry = _formal_metadata_entry();helper = entry._require_metadata_helper()
    directory_snapshot = entry._capture_metadata(directory)
    directory_shape = helper.validate_snapshot(directory_snapshot, 'directory', uid, os.getegid())
    snapshot, shape = entry._metadata_pair(directory, _PROVIDER, fd, uid, 'file')
    if (shape != directory_shape or snapshot['mount_id'] != directory_snapshot['mount_id']
            or not 1 <= snapshot['size'] <= 4096):raise _closed()
    return tuple(snapshot[key] for key in helper.SNAPSHOT_FIELDS)


def _runtime_boundary(*, single=False):
    uid = os.geteuid()
    if sys.platform != 'linux' or os.name != 'posix' or uid <= 0 or os.getuid() != uid:
        raise _closed()
    if resource.getrlimit(resource.RLIMIT_CORE) != (0, 0):
        raise _closed()
    call = ctypes.CDLL(None, use_errno=True).prctl
    call.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
    call.restype = ctypes.c_int
    if call(3, 0, 0, 0, 0) != 0:
        raise _closed()
    if single and (threading.current_thread() is not threading.main_thread() or threading.active_count() != 1):
        raise _closed()
    entry = _formal_metadata_entry()
    if entry._CONSUMER is None or entry._capture_consumer() != entry._CONSUMER:raise _closed()
    return uid


def _entry_caller(label):
    path = _ROOT / 'scripts/run-formal-main.py'
    frame = sys._getframe(2)
    try:
        module = sys.modules.get('__main__')
        if (module is None or frame.f_globals is not vars(module) or module.__file__ != str(path)
                or path.is_symlink() or path != path.resolve() or not sys.flags.isolated
                or not sys.flags.dont_write_bytecode):
            raise _closed()
        function = getattr(module, label, None)
        code = next((c for c in compile(path.read_bytes(), str(path), 'exec', dont_inherit=True).co_consts
                     if isinstance(c, types.CodeType) and c.co_name == label), None)
        if (type(function) is not types.FunctionType or frame.f_code is not function.__code__
                or function.__code__ != code):
            raise _closed()
        return frame.f_locals.get('descriptors')
    finally:
        del frame


def _directory_metadata(info, uid, final):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != (uid if final else 0)
            or (stat.S_IMODE(info.st_mode) != 0o500 if final else bool(info.st_mode & 0o022))):
        raise _closed()
    return info.st_dev, info.st_ino, info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode)


def _check_directories(descriptors, identities, uid):
    if len(descriptors) != 4 or len(identities) != 4:
        raise _closed()
    current = _directory_snapshots(descriptors, uid)
    if current != tuple(identities):
        raise _closed()
    if any(os.get_inheritable(fd) for fd in descriptors):raise _closed()


class _Sealed:
    __slots__ = ()
    def __setattr__(self, name, value):
        if hasattr(self, name):
            raise TypeError('native credential resource is immutable')
        object.__setattr__(self, name, value)
    def __reduce__(self):
        raise TypeError('native credential resource cannot be serialized')


class NativeCredentialStartFailure(RuntimeError):
    __slots__ = ('_handle', '_resources', '_uncertain')
    def __init__(self, handle, resources, *, _factory=None):
        frame = sys._getframe(1)
        if (_factory is not _FACTORY or frame.f_globals is not globals()
                or frame.f_code not in (_publish_entry_directory.__code__, _read_provider.__code__, load_native_live_credential.__code__)
                or type(handle) is not _CredentialFDHandle or type(resources) is not tuple or resources != (handle,)
                or handle.pid != os.getpid() or not handle.uncertain):
            raise _closed()
        RuntimeError.__init__(self, 'native credential birth retirement uncertain')
        object.__setattr__(self, '_handle', handle)
        object.__setattr__(self, '_resources', resources)
        object.__setattr__(self, '_uncertain', True)
    @property
    def handle(self):return self._handle
    @property
    def resources(self):return self._resources
    @property
    def uncertain(self):return self._uncertain
    def __setattr__(self, name, value):
        if name in ('_handle','_resources','_uncertain','handle','resources','uncertain'):
            raise TypeError('native start failure is immutable')
        BaseException.__setattr__(self,name,value)
    def __reduce__(self):raise TypeError('native start failure cannot be serialized')
    def __repr__(self):return '<NativeCredentialStartFailure redacted>'


class _CredentialFDHandle(_Sealed):
    __slots__ = ('pid', '_records', 'uncertain')
    def __init__(self, *, _factory=None):
        frame = sys._getframe(1)
        if (_factory is not _FACTORY or frame.f_globals is not globals()
                or frame.f_code not in (_publish_entry_directory.__code__, _read_provider.__code__)):
            raise _closed()
        self.pid, self._records, self.uncertain = os.getpid(), [], False
    def __repr__(self):return '<CredentialFDHandle redacted>'
    def record(self, fd):
        record = [fd, None, False]
        self._records.append(record)
        info = os.fstat(fd)
        record[1] = (info.st_dev, info.st_ino)
    def close(self):
        if self.pid != os.getpid():raise _closed()
        errors = []
        for record in reversed(self._records):
            fd, identity, closed = record
            if closed:continue
            try:
                if identity is None:raise OSError('native descriptor birth identity unknown')
                info = os.fstat(fd)
                if (info.st_dev,info.st_ino) != identity:raise OSError('native descriptor identity changed')
                os.close(fd)
                try:os.fstat(fd)
                except OSError as error:
                    if error.errno != 9:raise
                else:raise OSError('native descriptor close unproved')
                record[2] = True
            except BaseException as error:
                # If close raised after retiring its FD, never close a reused
                # number later. The observed uncertainty still remains sticky.
                try:os.fstat(fd)
                except OSError as gone:
                    if gone.errno == 9:record[2] = True
                errors.append(type(error).__name__)
        if errors or self.uncertain:
            object.__setattr__(self,'uncertain',True)
            if self not in _UNCERTAIN:_UNCERTAIN.append(self)
            raise _closed()


class EntryCredentialDirectoryWitness(_Sealed):
    __slots__ = ('pid', 'uid', 'reference', 'fds', 'identities', 'closed', 'uncertain', '_io')
    def __init__(self, descriptors, identities, uid, io, *, _factory=None):
        frame = sys._getframe(1)
        if _factory is not _FACTORY or frame.f_code is not _publish_entry_directory.__code__ or frame.f_globals is not globals():
            raise _closed()
        self.pid, self.uid, self.reference = os.getpid(), uid, object()
        self.fds, self.identities, self.closed, self.uncertain = tuple(descriptors), tuple(identities), False, False
        self._io = io
        _ENTRIES[self.reference] = self
    def __repr__(self):
        return '<EntryCredentialDirectoryWitness redacted>'
    def require_runtime(self):
        if (self.closed or self.uncertain or self.pid != os.getpid() or self.uid != _runtime_boundary()
                or _ENTRIES.get(self.reference) is not self):
            raise _closed()
        _check_directories(self.fds, self.identities, self.uid)
    def close(self):
        if self.closed:
            if self.uncertain:
                raise _closed()
            return
        errors = []
        for key in tuple(_KEYS.values()):
            if key.entry is self:
                try:
                    key.close()
                except BaseException as error:
                    errors.append(type(error).__name__)
        try:
            self._io.close()
        except BaseException as error:
            errors.append(type(error).__name__)
        object.__setattr__(self, 'closed', True)
        if errors:
            object.__setattr__(self, 'uncertain', True)
            raise _closed()
        _ENTRIES.pop(self.reference, None)


def _publish_entry_directory(descriptors):
    if __package__ != 'services':raise _closed()
    actual = _entry_caller('main')
    uid = _runtime_boundary(single=True)
    if actual is not descriptors or type(descriptors) is not list or len(descriptors) != 4 or _ENTRIES:
        raise _closed()
    identities = _directory_snapshots(descriptors, uid)
    _check_directories(descriptors, identities, uid)
    duplicated = []
    io = _CredentialFDHandle(_factory=_FACTORY)
    try:
        for fd in descriptors:
            copy = os.dup(fd)
            duplicated.append(copy)
            io.record(copy)
            os.set_inheritable(copy, False)
        _check_directories(duplicated, identities, uid)
        return EntryCredentialDirectoryWitness(duplicated, identities, uid, io, _factory=_FACTORY)
    except BaseException:
        try:io.close()
        except BaseException:raise NativeCredentialStartFailure(io,(io,),_factory=_FACTORY) from None
        raise


def _require_entry_for_serve(witness):
    _entry_caller('_serve')
    if type(witness) is not EntryCredentialDirectoryWitness:
        raise _closed()
    witness.require_runtime()
    _runtime_boundary(single=True)


def _require_entry_preimport(witness):
    _entry_caller('_code_paths')
    if type(witness) is not EntryCredentialDirectoryWitness:
        raise _closed()
    witness.require_runtime()
    _runtime_boundary(single=True)


def entry_directory_witness(main_context):
    if __package__ != 'services':raise _closed()
    module = _c()
    if type(main_context) is not module.MainStartupScope:
        raise _closed()
    store = getattr(main_context, 'store', None)
    if module.require_startup_scope(main_context, store) is not None:
        raise _closed()
    if len(_ENTRIES) != 1:
        raise _closed()
    witness = next(iter(_ENTRIES.values()))
    witness.require_runtime()
    return witness


def validate_provider_bytes(raw):
    """Data-only strict header grammar; no resource, file or authority born."""
    if type(raw) is not bytes or not 1 <= len(raw) <= 4096 or _TOKEN.fullmatch(raw) is None:
        raise ValueError('bounded ASCII bearer token required')
    return raw


def validate_provider_metadata(info, uid):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != uid or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o400 or not 1 <= info.st_size <= 4096):
        raise ValueError('provider credential metadata invalid')
    return _identity(info)


def _read_provider(directory, uid, *, _entry=None, _grant=None, _flight=None, _context=None):
    """Real directory reads require the fixed load caller and A/C binding.

    Bare synthetic helper calls are limited to a private0700 current-UID test
    directory, which cannot be the frozen0500 systemd credential directory.
    They return data/owned FD only, never a witness or live key object.
    """
    if type(uid) is not int or uid != os.geteuid():raise ValueError('actual credential UID required')
    if _entry is None:
        info = os.fstat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('synthetic directory cannot select real systemd credentials')
    else:
        frame = sys._getframe(1)
        if (frame.f_globals is not globals() or frame.f_code is not load_native_live_credential.__code__
                or type(_entry) is not EntryCredentialDirectoryWitness):raise _closed()
        _bootstrap_binding(_grant,_flight,_context)
        _entry.require_runtime()
        if directory != _entry.fds[-1] or uid != _entry.uid:raise _closed()
    io = _CredentialFDHandle(_factory=_FACTORY)
    fd = os.open(_PROVIDER, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
    try:
        io.record(fd)
        before = validate_provider_metadata(os.fstat(fd), uid) if _entry is None else _provider_snapshot(fd, directory, uid)
        raw = os.read(fd, 4097)
        os.lseek(fd, 0, os.SEEK_SET)
        again = os.read(fd, 4097)
        current = validate_provider_metadata(os.fstat(fd), uid) if _entry is None else _provider_snapshot(fd, directory, uid)
        named = validate_provider_metadata(os.stat(_PROVIDER, dir_fd=directory, follow_symlinks=False), uid) if _entry is None else current
        if (before != current or before != named or len(raw) != before[6] or raw != again):
            raise ValueError('provider credential changed')
        validate_provider_bytes(raw)
        return bytearray(raw), fd, before, io
    except BaseException:
        try:io.close()
        except BaseException:raise NativeCredentialStartFailure(io,(io,),_factory=_FACTORY) from None
        raise


def _bootstrap_binding(grant, flight, main_context):
    module = _a()
    if type(grant) is not module.NativeLiveGrantWitness or type(flight) is not module.NativeLiveFlightLease:
        raise _closed()
    store, message = module.credential_bootstrap_binding(grant, flight, main_context=main_context)
    c = _c()
    if type(main_context) is not c.MainStartupScope or c.require_startup_scope(main_context, store) is not None:
        raise _closed()
    if type(message) is not bytes or not 1 <= len(message) <= 16512:
        raise _closed()
    data = json.loads(message)
    if type(data) is not list or len(data) != 2 or data[0] != 'native-live-credential-v1' or type(data[1]) is not dict:
        raise _closed()
    encoded = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()
    if encoded != message:
        raise _closed()
    return store, message


class NativeLiveCredential(_Sealed):
    __slots__ = ('entry', 'grant', 'flight', 'store', 'message', 'pid', 'uid', 'reference', '_key',
                 'fd', 'metadata', 'closed', 'uncertain', '_io')
    def __init__(self, entry, grant, flight, store, message, key, fd, metadata, io, *, _factory=None):
        frame = sys._getframe(1)
        if (_factory is not _FACTORY or frame.f_code is not load_native_live_credential.__code__
                or frame.f_globals is not globals()):
            raise _closed()
        self.entry, self.grant, self.flight, self.store, self.message = entry, grant, flight, store, message
        self.pid, self.uid, self.reference = os.getpid(), os.geteuid(), object()
        self._key, self.fd, self.metadata, self.closed, self.uncertain = key, fd, metadata, False, False
        self._io = io
        _KEYS[self.reference] = self
    def __repr__(self):
        return '<NativeLiveCredential redacted>'
    def _birth(self, *, past=False):
        if (self.pid != os.getpid() or self.uid != _runtime_boundary()
                or _KEYS.get(self.reference) is not self or self.uncertain or (self.closed and not past)):
            raise _closed()
    def _current_file(self):
        self._birth()
        self.entry.require_runtime()
        if self.metadata != _provider_snapshot(self.fd, self.entry.fds[-1], self.uid):
            raise _closed()
    def require_bootstrap(self, grant, flight, *, main_context):
        if grant is not self.grant or flight is not self.flight:
            raise _closed()
        store, message = _bootstrap_binding(grant, flight, main_context)
        if store is not self.store or message != self.message:
            raise _closed()
        self._current_file()
    def continuity_for_grant(self, grant, flight, *, main_context):
        self.require_bootstrap(grant, flight, main_context=main_context)
        return hmac.new(self._key, self.message, hashlib.sha256).hexdigest()
    def _session(self, session):
        module = _a()
        if (type(session) is not module.NativeLiveSession or module.credential_session_binding(session, self) is not True
                or session.grant is not self.grant or session.flight is not self.flight):
            raise _closed()
    def require_current(self, session):
        self._session(session)
        self._current_file()
    def require_past(self, session, lifecycle_scope):
        self._session(session)
        self._birth(past=True)
        c = _c()
        if type(lifecycle_scope) is c.NativePlanSlotLease:
            if c.require_slot(lifecycle_scope, self.store, session, task_id=lifecycle_scope.task_id,
                              purpose=lifecycle_scope.purpose, mode='cleanup') is not None:
                raise _closed()
        elif type(lifecycle_scope) is c.NativeLifecycleScope:
            action = lifecycle_scope.action
            if action not in ('revoke', 'retire', 'recover') or c.require_lifecycle_scope(
                    lifecycle_scope, self.store, session, action=action) is not None:
                raise _closed()
        else:
            raise _closed()
        # No active grant/key reread here; a closed key retains birth proof only.
    def _authorization(self, session, resource, slot_scope):
        transport = _canonical_module(__package__ + '.plan_runtime_transport', 'web/backend/services/plan_runtime_transport.py', (), ('NativePlanResource',))
        frame = sys._getframe(1)
        try:
            if (type(resource) is not transport.NativePlanResource or frame.f_code is not transport.NativePlanResource._request.__code__
                    or frame.f_globals is not vars(transport) or frame.f_locals.get('self') is not resource):
                raise _closed()
        finally:
            del frame
        resource._require_live_execute(slot_scope)
        self.require_current(session)
        return b'Bearer ' + bytes(self._key)
    def close(self):
        if self.closed:
            if self.uncertain:
                raise _closed()
            return
        if self.pid != os.getpid():
            raise _closed()
        self._key[:] = b'\0' * len(self._key)
        self._key.clear()
        object.__setattr__(self, 'closed', True)
        try:
            self._io.close()
        except BaseException:
            object.__setattr__(self, 'uncertain', True)
            raise
        # Exact registered tombstone is only for old cleanup scopes, never send.


def load_native_live_credential(entry_witness, grant, flight, *, main_context):
    # A/C/exact pairing is checked before the first provider-file open.
    if __package__ != 'services':raise _closed()
    store, message = _bootstrap_binding(grant, flight, main_context)
    if type(entry_witness) is not EntryCredentialDirectoryWitness:
        raise _closed()
    entry_witness.require_runtime()
    attempt = (entry_witness.reference, id(grant), id(flight))
    if attempt in _ATTEMPTS:
        raise _closed()
    _ATTEMPTS[attempt] = None
    key, fd, metadata, io = _read_provider(entry_witness.fds[-1], entry_witness.uid,
        _entry=entry_witness,_grant=grant,_flight=flight,_context=main_context)
    try:
        entry_witness.require_runtime()
        again_store, again_message = _bootstrap_binding(grant, flight, main_context)
        if again_store is not store or again_message != message:
            raise _closed()
        value = NativeLiveCredential(entry_witness, grant, flight, store, message, key, fd, metadata, io, _factory=_FACTORY)
        _ATTEMPTS[attempt] = value
        return value
    except BaseException:
        key[:] = b'\0' * len(key)
        key.clear()
        try:io.close()
        except BaseException:raise NativeCredentialStartFailure(io,(io,),_factory=_FACTORY) from None
        raise
