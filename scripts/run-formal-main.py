"""Fixed beta Main entry: final interpreter hardening, then systemd credentials.

Invoke the approved absolute release Python with -I -B and this physical file.
No credential/command/module argument, provider secret, exec, or UID transition.
The five files and final directory must match the frozen v255 target contract;
this code does not establish that the target metadata has been verified.
"""
import os
import stat
import sys

CREDENTIAL_DIRECTORY = '/run/credentials/structural-web.service'
CREDENTIAL_IDS = (
    ('structural-jwt-secret', 'JWT_SECRET'),
    ('structural-sso-secret', 'STRUCTURAL_SSO_SECRET'),
    ('structural-privacy-hmac-key', 'STRUCTURAL_PRIVACY_HMAC_KEY'),
    ('structural-share-token-secret', 'STRUCTURAL_SHARE_TOKEN_SECRET'),
    ('structural-smtp-password', 'SMTP_PASSWORD'),
)
PROFILE = {'STRUCTURAL_ENV': 'prod', 'AUTH_ENABLED': 'true', 'AUTH_DEV_MODE': 'false',
           'AUTH_SITE_ROLE': 'beta', 'AUTH_LINK_BASE_URL': 'https://beta.structural.bytedance.city'}
_KNOWN_SENSITIVE = frozenset(('AZURE_OPENAI_KEY', 'ANTHROPIC_AUTH_TOKEN', 'GOOGLE_APPLICATION_CREDENTIALS',
    'AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN', 'HF_TOKEN', 'HUGGING_FACE_HUB_TOKEN'))
_CODE_OVERRIDES = frozenset(('STRUCTURAL_PROJECT_ROOT', 'PYTHONPATH', 'PYTHONHOME', 'PYTHONINSPECT'))
_UNCERTAIN_FDS = []
_METADATA_HELPER = None
_CONSUMER = None
_GROUP_METADATA = ()
_CODES = frozenset(('ENTRY_ARGUMENTS', 'INTERPRETER_FLAGS', 'INHERITED_SECRET', 'CODE_OVERRIDE',
    'PROFILE_INVALID', 'SMTP_AUTH_REQUIRED', 'CREDENTIAL_DIRECTORY_INVALID', 'UNSUPPORTED_PLATFORM',
    'SERVICE_IDENTITY_INVALID', 'CORE_HARDENING_FAILED', 'DUMP_HARDENING_FAILED', 'BOUNDARY_CHANGED',
    'CREDENTIAL_METADATA_INVALID', 'CREDENTIAL_CHANGED', 'CREDENTIAL_SIZE_INVALID',
    'CREDENTIAL_ENCODING_INVALID', 'CREDENTIAL_FORMAT_INVALID', 'CREDENTIAL_IO_FAILED',
    'FD_CLOSE_FAILED', 'ENV_INSTALL_FAILED', 'CODE_IDENTITY_INVALID', 'APP_IMPORT_FAILED', 'SERVER_FAILED'))


class EntryFailure(RuntimeError):
    def __init__(self, code):
        self.code = code if code in _CODES else 'SERVER_FAILED'
        super().__init__(self.code)


def _initial_environment():
    # Examine names first; never read, adopt or overwrite an inherited secret.
    targets = {target for _, target in CREDENTIAL_IDS}
    for name in os.environ:
        if name in targets or name in _KNOWN_SENSITIVE or name.startswith('OP_') or name.endswith('_API_KEY'):
            raise EntryFailure('INHERITED_SECRET')
    if any(name in os.environ for name in _CODE_OVERRIDES):
        raise EntryFailure('CODE_OVERRIDE')
    if os.environ.get('CREDENTIALS_DIRECTORY') != CREDENTIAL_DIRECTORY:
        raise EntryFailure('CREDENTIAL_DIRECTORY_INVALID')
    if any(name in os.environ and os.environ[name] != value for name, value in PROFILE.items()):
        raise EntryFailure('PROFILE_INVALID')
    if not os.environ.get('SMTP_USERNAME', '').strip():
        raise EntryFailure('SMTP_AUTH_REQUIRED')


def _core_state(value):
    if type(value) is not tuple or len(value) != 2 or any(type(item) is not int for item in value) or value != (0, 0):
        raise EntryFailure('CORE_HARDENING_FAILED')


def _dump_state(value):
    if type(value) is not int or value != 0:
        raise EntryFailure('DUMP_HARDENING_FAILED')


def _prctl():
    import ctypes
    try:
        function = ctypes.CDLL(None, use_errno=True).prctl
        function.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong)
        function.restype = ctypes.c_int
        return function
    except Exception:
        raise EntryFailure('DUMP_HARDENING_FAILED') from None


def _single_process(pid, uid):
    import threading
    if (sys.platform != 'linux' or os.name != 'posix' or os.getpid() != pid
            or uid <= 0 or os.getuid() != uid or os.geteuid() != uid
            or threading.current_thread() is not threading.main_thread() or threading.active_count() != 1):
        raise EntryFailure('BOUNDARY_CHANGED')


def _harden_current_process():
    if sys.platform != 'linux' or os.name != 'posix':
        raise EntryFailure('UNSUPPORTED_PLATFORM')
    pid, uid = os.getpid(), os.geteuid()
    if uid <= 0 or os.getuid() != uid:
        raise EntryFailure('SERVICE_IDENTITY_INVALID')
    _single_process(pid, uid)
    import resource
    try:
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        _core_state(resource.getrlimit(resource.RLIMIT_CORE))
    except Exception:
        raise EntryFailure('CORE_HARDENING_FAILED') from None
    call = _prctl()
    try:
        if call(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE
            raise EntryFailure('DUMP_HARDENING_FAILED')
        _dump_state(call(3, 0, 0, 0, 0))  # PR_GET_DUMPABLE
    except Exception:
        raise EntryFailure('DUMP_HARDENING_FAILED') from None
    _check_boundary(pid, uid)
    return pid, uid


def _check_boundary(pid, uid):
    _single_process(pid, uid)
    import resource
    try:
        _core_state(resource.getrlimit(resource.RLIMIT_CORE))
        _dump_state(_prctl()(3, 0, 0, 0, 0))
    except EntryFailure:
        raise
    except Exception:
        raise EntryFailure('BOUNDARY_CHANGED') from None


def _identity(info):
    return (info.st_dev, info.st_ino, info.st_uid, info.st_gid, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _directory_metadata(info, uid, *, final):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != (uid if final else 0)
            or (stat.S_IMODE(info.st_mode) != 0o500 if final else bool(info.st_mode & 0o022))):
        raise EntryFailure('CREDENTIAL_METADATA_INVALID')


def _close_all(descriptors):
    failed = []
    for descriptor in reversed(tuple(descriptors)):
        try:
            os.close(descriptor)
        except BaseException:
            failed.append(descriptor)
    descriptors[:] = list(reversed(failed))
    if failed:
        # Retain failed native handles; a later numeric FD reuse is not proof
        # that this retirement succeeded, and must not trigger a blind retry.
        _UNCERTAIN_FDS.append(tuple(failed))
        raise EntryFailure('FD_CLOSE_FAILED')


def _read_proc(path, limit):
    descriptors = []
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(descriptor)
        raw = os.read(descriptor, limit + 1)
        if not 0 < len(raw) <= limit:
            raise EntryFailure('CREDENTIAL_METADATA_INVALID')
        return raw
    finally:
        _close_all(descriptors)


def _source_bytes(path):
    # Root-managed source and every physical ancestor must be non-writable by
    # the service. Mode group bits include a POSIX ACL's effective mask.
    from pathlib import Path
    descriptors = []
    try:
        parts = Path(path).parts
        descriptor = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        descriptors.append(descriptor)
        root_info = os.fstat(descriptor)
        if root_info.st_uid != 0 or root_info.st_mode & 0o022:raise EntryFailure('CODE_IDENTITY_INVALID')
        for component in parts[1:]:
            parent = descriptors[-1]
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            if component != parts[-1]:flags |= os.O_DIRECTORY
            descriptor = os.open(component, flags, dir_fd=parent)
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            named = os.stat(component, dir_fd=parent, follow_symlinks=False)
            if (info.st_uid != 0 or info.st_mode & 0o022 or _identity(info) != _identity(named)
                    or not (stat.S_ISREG(info.st_mode) if component == parts[-1] else stat.S_ISDIR(info.st_mode))):
                raise EntryFailure('CODE_IDENTITY_INVALID')
        before = os.fstat(descriptor)
        if before.st_nlink != 1 or not 0 < before.st_size <= 65536:
            raise EntryFailure('CODE_IDENTITY_INVALID')
        raw = os.read(descriptor, 65537)
        if len(raw) != before.st_size or _identity(before) != _identity(os.fstat(descriptor)):
            raise EntryFailure('CODE_IDENTITY_INVALID')
        return raw
    finally:
        _close_all(descriptors)


def _require_metadata_helper():
    import types
    from pathlib import Path
    path = Path(__file__).absolute().parent.parent / 'web/backend/systemd_credential_metadata.py'
    module = _METADATA_HELPER
    if (type(module) is not types.ModuleType or sys.modules.get('systemd_credential_metadata') is not module
            or module.__name__ != 'systemd_credential_metadata' or module.__file__ != str(path)):
        raise EntryFailure('CODE_IDENTITY_INVALID')
    raw = _source_bytes(path)
    expected = {'__name__': module.__name__, '__file__': str(path)}
    exec(compile(raw, str(path), 'exec', dont_inherit=True), expected)
    names = {key for key in expected if not key.startswith('__')}
    if {key for key in vars(module) if not key.startswith('__')} != names:
        raise EntryFailure('CODE_IDENTITY_INVALID')
    for name in names:
        actual, original = vars(module)[name], expected[name]
        if type(original) is types.FunctionType:
            if (type(actual) is not types.FunctionType or actual.__globals__ is not vars(module)
                    or actual.__module__ != module.__name__ or actual.__code__ != original.__code__
                    or actual.__defaults__ != original.__defaults__ or actual.__kwdefaults__ != original.__kwdefaults__):
                raise EntryFailure('CODE_IDENTITY_INVALID')
        elif type(actual) is not type(original) or (actual is not original if isinstance(original, types.ModuleType) else actual != original):
            raise EntryFailure('CODE_IDENTITY_INVALID')
    if _source_bytes(path) != raw:
        raise EntryFailure('CODE_IDENTITY_INVALID')
    return module


def _load_metadata_helper(backend):
    global _METADATA_HELPER
    import importlib
    path = backend / 'systemd_credential_metadata.py'
    if _METADATA_HELPER is not None or 'systemd_credential_metadata' in sys.modules:
        raise EntryFailure('CODE_IDENTITY_INVALID')
    before = _source_bytes(path)
    sys.path.insert(0, str(backend))
    _METADATA_HELPER = importlib.import_module('systemd_credential_metadata')
    module = _require_metadata_helper()
    if _source_bytes(path) != before:
        raise EntryFailure('CODE_IDENTITY_INVALID')
    return module


def _capture_metadata(descriptor):
    module = _require_metadata_helper()
    if _CONSUMER is None or _capture_consumer() != _CONSUMER:raise EntryFailure('BOUNDARY_CHANGED')
    before = _identity(os.fstat(descriptor))
    snapshot = module.capture_fd(descriptor, _read_proc('/proc/self/fdinfo/' + str(descriptor), 4096), _read_proc('/proc/thread-self/mountinfo', 262144))
    if before != _identity(os.fstat(descriptor)):raise EntryFailure('CREDENTIAL_CHANGED')
    if _capture_consumer() != _CONSUMER:raise EntryFailure('BOUNDARY_CHANGED')
    return snapshot


def _capture_consumer():
    import threading
    thread_id = threading.get_native_id()
    module = _require_metadata_helper()
    user = os.stat('/proc/thread-self/ns/user');mount = os.stat('/proc/thread-self/ns/mnt')
    before = (user.st_dev, user.st_ino), (mount.st_dev, mount.st_ino)
    value = module.parse_consumer(_read_proc('/proc/thread-self/status', 65536), _read_proc('/proc/thread-self/uid_map', 65536),
        _read_proc('/proc/thread-self/gid_map', 65536), _read_proc('/proc/self/stat', 65536), os.getpid(), *before)
    user = os.stat('/proc/thread-self/ns/user');mount = os.stat('/proc/thread-self/ns/mnt')
    if (threading.get_native_id() != thread_id
            or before != ((user.st_dev, user.st_ino), (mount.st_dev, mount.st_ino))
            or value['uid'] != os.geteuid() or value['gid'] != os.getegid()
            or os.getresuid() != (value['uid'],) * 3 or os.getresgid() != (value['gid'],) * 3):
        raise EntryFailure('BOUNDARY_CHANGED')
    return value


def _metadata_pair(parent, name, descriptor, uid, role):
    descriptors = []
    module = _METADATA_HELPER
    try:
        held = _capture_metadata(descriptor)
        flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        if role != 'file':flags |= os.O_DIRECTORY
        named = os.open(name, flags, dir_fd=parent) if parent is not None else os.open('/', flags)
        descriptors.append(named)
        current = _capture_metadata(named)
        if not module.same_snapshot(held, current):raise EntryFailure('CREDENTIAL_CHANGED')
        shape = module.validate_snapshot(held, role, uid, os.getegid())
        return held, shape
    except ValueError:
        raise EntryFailure('CREDENTIAL_METADATA_INVALID') from None
    finally:
        _close_all(descriptors)


def _credential_directory(uid):
    descriptors = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptors.append(os.open('/', flags))
        _metadata_pair(None, '/', descriptors[-1], uid, 'ancestor')
        for component in ('run', 'credentials', 'structural-web.service'):
            parent = descriptors[-1]
            before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            final = component == 'structural-web.service'
            if not stat.S_ISDIR(before.st_mode):raise EntryFailure('CREDENTIAL_METADATA_INVALID')
            descriptor = os.open(component, flags, dir_fd=parent)
            descriptors.append(descriptor)
            after = os.fstat(descriptor)
            _metadata_pair(parent, component, descriptor, uid, 'directory' if final else 'ancestor')
            if _identity(before) != _identity(after):
                raise EntryFailure('CREDENTIAL_CHANGED')
        return descriptors
    except BaseException:
        _close_all(descriptors)
        raise


def _check_directories(descriptors, uid):
    _metadata_pair(None, '/', descriptors[0], uid, 'ancestor')
    for parent, descriptor, component in zip(descriptors, descriptors[1:], ('run', 'credentials', 'structural-web.service')):
        _metadata_pair(parent, component, descriptor, uid, 'directory' if component == 'structural-web.service' else 'ancestor')
    if _CONSUMER is None or _capture_consumer() != _CONSUMER:
        raise EntryFailure('BOUNDARY_CHANGED')


def _validate_value(target, raw):
    try:
        value = raw.decode('utf-8', errors='strict')
    except UnicodeError:
        raise EntryFailure('CREDENTIAL_ENCODING_INVALID') from None
    if not value or any(character in value for character in ('\0', '\r', '\n')):
        raise EntryFailure('CREDENTIAL_FORMAT_INVALID')
    # Match the existing consumers, including their predicate-only strip.
    if target in ('JWT_SECRET', 'STRUCTURAL_SSO_SECRET'):
        markers = (('replace', 'change-me', 'changeme', 'example', 'test-secret', 'dev-jwt')
                   if target == 'JWT_SECRET' else ('replace', 'change-me', 'example', 'test-secret', 'dev-'))
        if len(value) < 32 or len(set(value)) < 12 or any(marker in value.strip().lower() for marker in markers):
            raise EntryFailure('CREDENTIAL_FORMAT_INVALID')
    if target == 'STRUCTURAL_PRIVACY_HMAC_KEY':
        if len(value) != 64 or any(character not in '0123456789abcdef' for character in value) or len(set(value)) < 12:
            raise EntryFailure('CREDENTIAL_FORMAT_INVALID')
    # Share and SMTP consumers require nonempty UTF-8; do not invent a length.
    return value


def _read_group(directory, uid):
    """Internal FD helper; tests may supply only their owned synthetic directory.

    Formal entry obtains this FD exclusively through the fixed directory walk.
    Nothing here is a Main readiness, funding, or secret-loader authority port.
    """
    global _GROUP_METADATA
    _GROUP_METADATA = ()
    values, descriptors, fingerprints, total = {}, [], [], 0
    try:
        directory_snapshot = _capture_metadata(directory)
        directory_shape = _METADATA_HELPER.validate_snapshot(directory_snapshot, 'directory', uid, os.getegid())
        for credential, target in CREDENTIAL_IDS:
            descriptor = os.open(credential, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 dir_fd=directory)
            descriptors.append(descriptor)
            before = os.fstat(descriptor)
            initial, shape = _metadata_pair(directory, credential, descriptor, uid, 'file')
            if shape != directory_shape or initial['mount_id'] != directory_snapshot['mount_id']:
                raise EntryFailure('CREDENTIAL_METADATA_INVALID')
            if not 1 <= before.st_size <= 4096 or total + before.st_size > 20480:
                raise EntryFailure('CREDENTIAL_SIZE_INVALID')
            raw = os.read(descriptor, 4097)
            after = os.fstat(descriptor)
            named = os.stat(credential, dir_fd=directory, follow_symlinks=False)
            if (_identity(before) != _identity(after) or _identity(after) != _identity(named)
                    or len(raw) != before.st_size):
                raise EntryFailure('CREDENTIAL_CHANGED')
            current, _ = _metadata_pair(directory, credential, descriptor, uid, 'file')
            if not _METADATA_HELPER.same_snapshot(initial, current):raise EntryFailure('CREDENTIAL_CHANGED')
            total += len(raw)
            values[target] = _validate_value(target, raw)
            fingerprints.append((credential, descriptor, _identity(after), initial))
        if not _METADATA_HELPER.same_snapshot(directory_snapshot, _capture_metadata(directory)):
            raise EntryFailure('CREDENTIAL_CHANGED')
        for credential, descriptor, fingerprint, initial in fingerprints:
            if (fingerprint != _identity(os.fstat(descriptor))
                    or fingerprint != _identity(os.stat(credential, dir_fd=directory, follow_symlinks=False))):
                raise EntryFailure('CREDENTIAL_CHANGED')
            current, _ = _metadata_pair(directory, credential, descriptor, uid, 'file')
            if not _METADATA_HELPER.same_snapshot(initial, current):raise EntryFailure('CREDENTIAL_CHANGED')
        _GROUP_METADATA = tuple((credential, initial) for credential, _, _, initial in fingerprints)
        return values
    except EntryFailure:
        values.clear()
        raise
    except Exception:
        values.clear()
        raise EntryFailure('CREDENTIAL_IO_FAILED') from None
    finally:
        _close_all(descriptors)


def _check_group(directory, uid):
    descriptors = []
    if tuple(name for name, _ in _GROUP_METADATA) != tuple(name for name, _ in CREDENTIAL_IDS):
        raise EntryFailure('CREDENTIAL_CHANGED')
    try:
        for name, expected in _GROUP_METADATA:
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC, dir_fd=directory)
            descriptors.append(fd)
            current, _ = _metadata_pair(directory, name, fd, uid, 'file')
            if not _METADATA_HELPER.same_snapshot(current, expected):raise EntryFailure('CREDENTIAL_CHANGED')
    finally:
        _close_all(descriptors)


def _publish_environment(values):
    if set(values) != {target for _, target in CREDENTIAL_IDS}:
        raise EntryFailure('ENV_INSTALL_FAILED')
    if any(target in os.environ for target in values):
        raise EntryFailure('INHERITED_SECRET')
    prior_profile = {name: os.environ.get(name) for name in PROFILE}
    try:
        # One single-threaded logical batch, not an OS-atomic transaction.
        os.environ.update({**PROFILE, **values})
    except BaseException:
        for target in values:
            os.environ.pop(target, None)
        for name, prior in prior_profile.items():
            if prior is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = prior
        raise EntryFailure('ENV_INSTALL_FAILED') from None


def _code_paths(*, entry_module=None, entry_witness=None):
    from pathlib import Path
    script = Path(__file__).absolute()
    if script != script.resolve(strict=True) or script.name != 'run-formal-main.py' or script.parent.name != 'scripts':
        raise EntryFailure('CODE_IDENTITY_INVALID')
    root = script.parent.parent
    backend = root / 'web/backend'
    source = backend / 'main.py'
    allowed = set()
    if _METADATA_HELPER is not None:
        _require_metadata_helper()
        allowed.add('systemd_credential_metadata')
    if entry_module is not None:
        _validate_entry_module(entry_module, root)
        entry_module._require_entry_preimport(entry_witness)
        allowed.update(('services', 'services.native_live_credentials'))
    elif entry_witness is not None:
        raise EntryFailure('CODE_IDENTITY_INVALID')
    if (source.is_symlink() or not source.is_file() or backend != backend.resolve()
            or any((name == 'main' or name.startswith(('api.', 'services.', 'research.', 'web.backend'))
                    or name in ('api', 'services', 'research', 'systemd_credential_metadata')) and name not in allowed for name in sys.modules)):
        raise EntryFailure('CODE_IDENTITY_INVALID')
    return root, backend, source


def _validate_entry_module(module, root):
    import types
    path = root / 'web/backend/services/native_live_credentials.py'
    package = sys.modules.get('services')
    parent = root / 'web/backend/services/__init__.py'
    if (type(module) is not types.ModuleType or sys.modules.get('services.native_live_credentials') is not module
            or module.__name__ != 'services.native_live_credentials' or module.__file__ != str(path)
            or path.is_symlink() or path != path.resolve() or len(path.read_bytes()) > 262144
            or type(package) is not types.ModuleType or package.__file__ != str(parent)
            or parent.is_symlink() or parent != parent.resolve()):
        raise EntryFailure('CODE_IDENTITY_INVALID')
    codes = {value.co_name:value for value in compile(path.read_bytes(), str(path), 'exec', dont_inherit=True).co_consts
             if isinstance(value, types.CodeType)}
    for name in ('_publish_entry_directory', '_require_entry_preimport', '_require_entry_for_serve'):
        function = getattr(module, name, None)
        if (type(function) is not types.FunctionType or function.__globals__ is not vars(module)
                or function.__module__ != module.__name__ or function.__code__ != codes.get(name)):
            raise EntryFailure('CODE_IDENTITY_INVALID')


def _serve(pid, uid, *, entry_module=None, entry_witness=None):
    from pathlib import Path
    import importlib
    if entry_module is not None:
        _validate_entry_module(entry_module, Path(__file__).absolute().parent.parent)
        entry_module._require_entry_for_serve(entry_witness)
    root, backend, source = _code_paths(entry_module=entry_module, entry_witness=entry_witness)
    sys.path[:0] = [str(backend), str(root)]
    try:
        main = importlib.import_module('main')
        if Path(main.__file__).resolve() != source or not main._IS_PROD or not main._LAUNCH_FORMAL:
            raise EntryFailure('CODE_IDENTITY_INVALID')
        import uvicorn
        config = uvicorn.Config(main.app, host='127.0.0.1', port=5004, workers=1, reload=False,
                                lifespan='on', access_log=False, log_config=None, timeout_graceful_shutdown=5)
        server = uvicorn.Server(config)
    except EntryFailure:
        raise
    except BaseException:
        raise EntryFailure('APP_IMPORT_FAILED') from None
    # Importing code may change process properties. Recheck immediately before
    # the actual server; no exec, UID switch or worker wrapper follows this.
    _check_boundary(pid, uid)
    try:
        server.run()
        if not server.started or server.lifespan.error_occured or server.lifespan.startup_failed or server.lifespan.shutdown_failed:
            raise EntryFailure('SERVER_FAILED')
    except BaseException:
        raise EntryFailure('SERVER_FAILED') from None


def main():
    global _CONSUMER
    values, descriptors, installed = {}, [], False
    entry_module = entry_witness = None
    uncertain_entry_resources = ()
    result = 78
    try:
        if len(sys.argv) != 1:
            raise EntryFailure('ENTRY_ARGUMENTS')
        if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
            raise EntryFailure('INTERPRETER_FLAGS')
        _initial_environment()
        pid, uid = _harden_current_process()
        # Original pre-import source gate still runs before even B is imported.
        root, backend, _ = _code_paths()
        _load_metadata_helper(backend)
        _check_boundary(pid, uid)
        _CONSUMER = _capture_consumer()
        descriptors = _credential_directory(uid)
        try:
            values = _read_group(descriptors[-1], uid)
            _check_directories(descriptors, uid)
            _check_group(descriptors[-1], uid)
            import importlib
            sys.path[:0] = [str(backend), str(root)]
            entry_module = importlib.import_module('services.native_live_credentials')
            _validate_entry_module(entry_module, root)
            _check_boundary(pid, uid)
            entry_witness = entry_module._publish_entry_directory(descriptors)
        finally:
            _close_all(descriptors)
        _check_boundary(pid, uid)
        if _capture_consumer() != _CONSUMER:raise EntryFailure('BOUNDARY_CHANGED')
        entry_witness.require_runtime()
        _check_group(entry_witness.fds[-1], uid)
        _publish_environment(values)
        installed = True
        _serve(pid, uid, entry_module=entry_module, entry_witness=entry_witness)
        result = 0
    except BaseException as error:
        if entry_module is not None and type(error) is entry_module.NativeCredentialStartFailure:
            uncertain_entry_resources = error.resources
        code = error.code if isinstance(error, EntryFailure) else 'CREDENTIAL_IO_FAILED'
        os.write(2, ('FORMAL_ENTRY:' + code + '\n').encode('ascii'))
    finally:
        # Existing five ENV values retain their original consumers. Provider
        # material is never added to this batch or inherited by a DNS child.
        for handle in uncertain_entry_resources:
            try:handle.close()
            except BaseException:result = 78
        if entry_witness is not None:
            try:
                entry_witness.close()
            except BaseException:
                result = 78
                os.write(2, b'FORMAL_ENTRY:FD_CLOSE_FAILED\n')
        for _, target in CREDENTIAL_IDS:
            if installed and target in values:
                os.environ.pop(target, None)
        values.clear()
    return result


if __name__ == '__main__':
    raise SystemExit(main())
