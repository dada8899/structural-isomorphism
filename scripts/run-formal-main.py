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
    return (info.st_dev, info.st_ino, info.st_uid, info.st_mode, info.st_nlink, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _directory_metadata(info, uid, *, final):
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != (uid if final else 0)
            or (stat.S_IMODE(info.st_mode) != 0o500 if final else bool(info.st_mode & 0o022))):
        raise EntryFailure('CREDENTIAL_METADATA_INVALID')


def _close_all(descriptors):
    failed = False
    for descriptor in reversed(descriptors):
        try:
            os.close(descriptor)
        except BaseException:
            failed = True
    descriptors.clear()
    if failed:
        raise EntryFailure('FD_CLOSE_FAILED')


def _credential_directory(uid):
    descriptors = []
    try:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        descriptors.append(os.open('/', flags))
        _directory_metadata(os.fstat(descriptors[-1]), uid, final=False)
        for component in ('run', 'credentials', 'structural-web.service'):
            parent = descriptors[-1]
            before = os.stat(component, dir_fd=parent, follow_symlinks=False)
            final = component == 'structural-web.service'
            _directory_metadata(before, uid, final=final)
            descriptor = os.open(component, flags, dir_fd=parent)
            descriptors.append(descriptor)
            after = os.fstat(descriptor)
            _directory_metadata(after, uid, final=final)
            if _identity(before) != _identity(after):
                raise EntryFailure('CREDENTIAL_CHANGED')
        return descriptors
    except BaseException:
        _close_all(descriptors)
        raise


def _check_directories(descriptors, uid):
    _directory_metadata(os.fstat(descriptors[0]), uid, final=False)
    for parent, descriptor, component in zip(descriptors, descriptors[1:], ('run', 'credentials', 'structural-web.service')):
        held = os.fstat(descriptor)
        named = os.stat(component, dir_fd=parent, follow_symlinks=False)
        final = component == 'structural-web.service'
        _directory_metadata(held, uid, final=final)
        _directory_metadata(named, uid, final=final)
        if (held.st_dev, held.st_ino, held.st_uid, held.st_mode, held.st_nlink) != (
                named.st_dev, named.st_ino, named.st_uid, named.st_mode, named.st_nlink):
            raise EntryFailure('CREDENTIAL_CHANGED')


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
    values, descriptors, fingerprints, total = {}, [], [], 0
    try:
        _directory_metadata(os.fstat(directory), uid, final=True)
        for credential, target in CREDENTIAL_IDS:
            descriptor = os.open(credential, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                                 dir_fd=directory)
            descriptors.append(descriptor)
            before = os.fstat(descriptor)
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_uid != uid
                    or stat.S_IMODE(before.st_mode) != 0o400):
                raise EntryFailure('CREDENTIAL_METADATA_INVALID')
            if not 1 <= before.st_size <= 4096 or total + before.st_size > 20480:
                raise EntryFailure('CREDENTIAL_SIZE_INVALID')
            raw = os.read(descriptor, 4097)
            after = os.fstat(descriptor)
            named = os.stat(credential, dir_fd=directory, follow_symlinks=False)
            if (_identity(before) != _identity(after) or _identity(after) != _identity(named)
                    or len(raw) != before.st_size):
                raise EntryFailure('CREDENTIAL_CHANGED')
            total += len(raw)
            values[target] = _validate_value(target, raw)
            fingerprints.append((credential, descriptor, _identity(after)))
        _directory_metadata(os.fstat(directory), uid, final=True)
        for credential, descriptor, fingerprint in fingerprints:
            if (fingerprint != _identity(os.fstat(descriptor))
                    or fingerprint != _identity(os.stat(credential, dir_fd=directory, follow_symlinks=False))):
                raise EntryFailure('CREDENTIAL_CHANGED')
        return values
    except EntryFailure:
        values.clear()
        raise
    except Exception:
        values.clear()
        raise EntryFailure('CREDENTIAL_IO_FAILED') from None
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


def _code_paths():
    from pathlib import Path
    script = Path(__file__).absolute()
    if script != script.resolve(strict=True) or script.name != 'run-formal-main.py' or script.parent.name != 'scripts':
        raise EntryFailure('CODE_IDENTITY_INVALID')
    root = script.parent.parent
    backend = root / 'web/backend'
    source = backend / 'main.py'
    if (source.is_symlink() or not source.is_file() or backend != backend.resolve()
            or any(name == 'main' or name.startswith(('api.', 'services.', 'research.', 'web.backend'))
                   or name in ('api', 'services', 'research') for name in sys.modules)):
        raise EntryFailure('CODE_IDENTITY_INVALID')
    return root, backend, source


def _serve(pid, uid):
    from pathlib import Path
    import importlib
    root, backend, source = _code_paths()
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
    values, descriptors, installed = {}, [], False
    try:
        if len(sys.argv) != 1:
            raise EntryFailure('ENTRY_ARGUMENTS')
        if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
            raise EntryFailure('INTERPRETER_FLAGS')
        _initial_environment()
        pid, uid = _harden_current_process()
        _code_paths()
        _check_boundary(pid, uid)
        descriptors = _credential_directory(uid)
        try:
            values = _read_group(descriptors[-1], uid)
            _check_directories(descriptors, uid)
        finally:
            _close_all(descriptors)
        _check_boundary(pid, uid)
        _publish_environment(values)
        installed = True
        _serve(pid, uid)
        return 0
    except BaseException as error:
        code = error.code if isinstance(error, EntryFailure) else 'CREDENTIAL_IO_FAILED'
        os.write(2, ('FORMAL_ENTRY:' + code + '\n').encode('ascii'))
        return 78
    finally:
        # Python strings cannot be promised erased. Never emit or persist them.
        for _, target in CREDENTIAL_IDS:
            if installed and target in values:
                os.environ.pop(target, None)
        values.clear()


if __name__ == '__main__':
    raise SystemExit(main())
