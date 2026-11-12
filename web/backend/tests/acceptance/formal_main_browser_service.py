"""Owned test HTTPS/SMTP for the actual Main, never a production control API.

Prepare historical data first, retain its synthetic signing environment, then
let Uvicorn run the canonical Main lifespan. No readiness, routes, sender,
feature predicates, credentials or funding installations are substituted.
"""
from __future__ import annotations

import argparse
import asyncio
import _thread
from contextlib import AbstractContextManager
from email import policy
from email.parser import BytesParser
from http.cookiejar import CookieJar
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import sqlite3
import sys
import threading
import time
import types
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlsplit

ROOT = Path(__file__).resolve().parents[4]
for _source in (ROOT, ROOT / 'web/backend'):
    if str(_source) not in sys.path:
        sys.path.insert(0, str(_source))

from web.backend.tests.acceptance.plan_browser_service import (  # noqa: E402
    CanonicalBrowserBridge, _certificates, _OwnedHTTPSHandler,
)
from web.backend.tests.acceptance.source_history_fixture import prepared_source_history  # noqa: E402

ORIGIN = 'https://beta.structural.bytedance.city'
HOST = 'beta.structural.bytedance.city'
PREFIX = 'formal-main-browser-'
_FOREIGN_SECRETS = ('JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY',
                    'STRUCTURAL_SHARE_TOKEN_SECRET', 'SMTP_USERNAME', 'SMTP_PASSWORD',
                    'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY', 'SENTRY_DSN')
_FOREIGN_INPUTS = ('STRUCTURAL_HISTORY_DB', 'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_DATA_DIR',
                   'STRUCTURAL_MODEL_PATH', 'STRUCTURAL_PRECOMPUTED_EMBEDDINGS',
                   'STRUCTURAL_ARTIFACT_MANIFEST', 'STRUCTURAL_KB_FILE')

# Only these literal names can leave the owned startup observer. In particular,
# a basename or a syntactically valid Python identifier is not an allowlist.
_STARTUP_REPO_FRAMES = {
    'web/backend/main.py': ('lifespan',),
    'web/backend/services/formal_admission.py': (
        'initialize', 'publish', 'check', '_producer', '_modules', '_config',
        '_digest', 'pin_source_module', 'attach_source', 'retire', 'release'),
    'web/backend/services/runtime_paths.py': (
        'inspect_formal', '_directory_fd', '_validated_directory_fd',
        '_validate_directory', '_check_current_parent', '_repository_roots',
        'acquire', '_acquire_locked', 'check', '_sidecars', '_sidecar_entry',
        '_require_private_file', 'formal_favorites', 'private_favorites_path'),
    'web/backend/api/auth.py': ('_validate_production_config', '_store'),
    'web/backend/research/runtime_profile.py': (),
    'web/backend/research/store.py': ('__init__',),
    'web/backend/research/service.py': ('__init__', 'runtime_capability_facts'),
}
_STARTUP_DEPENDENCY_FRAMES = {
    'starlette.routing': ('starlette/routing.py', ('lifespan',)),
    'uvicorn.lifespan.on': ('uvicorn/lifespan/on.py', ('main', 'send', 'startup')),
    'contextlib': ('stdlib/contextlib.py', ('__aenter__', '__aexit__')),
}
_STARTUP_ERROR_TYPES = (RuntimeError, PermissionError, OSError, ValueError,
    TypeError, AssertionError, ImportError, ModuleNotFoundError, TimeoutError,
    RecursionError, FileNotFoundError, FileExistsError, BlockingIOError,
    BrokenPipeError, ConnectionError, sqlite3.OperationalError,
    sqlite3.ProgrammingError, sqlite3.IntegrityError, sqlite3.DatabaseError,
    asyncio.CancelledError, GeneratorExit, SystemExit, Exception, BaseException)


def _safe_startup_error(error):
    """Copy bounded coordinates only; never retain or render the exception."""
    files = {str(ROOT / relative): (relative, functions)
             for relative, functions in _STARTUP_REPO_FRAMES.items()}
    for module_name, (relative, functions) in _STARTUP_DEPENDENCY_FRAMES.items():
        module = sys.modules.get(module_name)
        filename = vars(module).get('__file__') if module is not None else None
        if type(filename) is str:
            files[filename] = (relative, functions)
    error_type = next((kind.__name__ for kind in _STARTUP_ERROR_TYPES
                       if type(error) is kind), 'OTHER')
    frames = []
    traceback = error.__traceback__
    for _ in range(256):
        if traceback is None:
            break
        code = traceback.tb_frame.f_code
        filename, functions = files.get(code.co_filename, ('OTHER', ()))
        function = code.co_name if code.co_name in functions else 'OTHER'
        line = traceback.tb_lineno
        frames.append({'file': filename, 'function': function,
                       'line': line if type(line) is int and 0 < line <= 1000000 else 0})
        traceback = traceback.tb_next
    return {'type': error_type, 'frames': frames[-8:]}


def _safe_lifespan_errors(error):
    """Keep a small cause/context chain using the same literal coordinate policy."""
    errors, seen = [], set()
    for _ in range(4):
        if not isinstance(error, BaseException) or id(error) in seen:
            break
        seen.add(id(error))
        errors.append(_safe_startup_error(error))
        error = error.__cause__ if error.__cause__ is not None else error.__context__
    return errors


# Retirement observation is test evidence, never a Core closure predicate.
_RETIREMENT_LIMIT = 16384
_RETIREMENT_STATES = frozenset(('STARTING', 'READY', 'STOPPING', 'STOPPED',
    'CLOSED', 'CLEANUP_UNCERTAIN', 'UNBOUND', 'HELD_CLEANUP', 'COOLDOWN',
    'RECHECK_REQUIRED', 'RETIRED'))
_RETIREMENT_REASONS = frozenset(('CLOSED', 'DEADLINE', 'WORKER_FAILURE',
    'CLOSE_UNCERTAIN', 'START_FAILED', 'RETIREMENT_UNCERTAIN', 'BUDGET_FAILURE',
    'CLEANUP_UNCERTAIN', 'FileNotFoundError', 'PermissionError', 'OSError',
    'BlockingIOError', 'RuntimeError'))
_RETIREMENT_CODES = frozenset(('FEATURE_UNAVAILABLE', 'FUNDING_CLOSED',
    'STORE_BUSY', 'CLEANUP_UNCERTAIN', 'SCHEMA_UNSUPPORTED', 'RECONCILIATION_REQUIRED'))
_RETIREMENT_SQLITE_TYPES = (
    (sqlite3.Error, 'Error'), (sqlite3.Warning, 'Warning'),
    (sqlite3.InterfaceError, 'InterfaceError'), (sqlite3.DatabaseError, 'DatabaseError'),
    (sqlite3.DataError, 'DataError'), (sqlite3.OperationalError, 'OperationalError'),
    (sqlite3.IntegrityError, 'IntegrityError'), (sqlite3.InternalError, 'InternalError'),
    (sqlite3.ProgrammingError, 'ProgrammingError'), (sqlite3.NotSupportedError, 'NotSupportedError'),
)
_RETIREMENT_SQLITE_PRIMARY = frozenset((1, 2, 3, 4, 5, 6, 7, 8, 9, 10,
    11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28))
_RETIREMENT_SQLITE_NAMES = frozenset((
    'SQLITE_ERROR', 'SQLITE_INTERNAL', 'SQLITE_PERM', 'SQLITE_ABORT',
    'SQLITE_BUSY', 'SQLITE_LOCKED', 'SQLITE_NOMEM', 'SQLITE_READONLY',
    'SQLITE_INTERRUPT', 'SQLITE_IOERR', 'SQLITE_CORRUPT', 'SQLITE_NOTFOUND',
    'SQLITE_FULL', 'SQLITE_CANTOPEN', 'SQLITE_PROTOCOL', 'SQLITE_EMPTY',
    'SQLITE_SCHEMA', 'SQLITE_TOOBIG', 'SQLITE_CONSTRAINT', 'SQLITE_MISMATCH',
    'SQLITE_MISUSE', 'SQLITE_NOLFS', 'SQLITE_AUTH', 'SQLITE_FORMAT',
    'SQLITE_RANGE', 'SQLITE_NOTADB', 'SQLITE_NOTICE', 'SQLITE_WARNING',
    'SQLITE_ERROR_MISSING_COLLSEQ', 'SQLITE_ERROR_RETRY', 'SQLITE_ERROR_SNAPSHOT',
    'SQLITE_ABORT_ROLLBACK', 'SQLITE_BUSY_RECOVERY', 'SQLITE_BUSY_SNAPSHOT',
    'SQLITE_BUSY_TIMEOUT', 'SQLITE_LOCKED_SHAREDCACHE', 'SQLITE_LOCKED_VTAB',
    'SQLITE_READONLY_RECOVERY', 'SQLITE_READONLY_CANTLOCK',
    'SQLITE_READONLY_ROLLBACK', 'SQLITE_READONLY_DBMOVED',
    'SQLITE_READONLY_CANTINIT', 'SQLITE_READONLY_DIRECTORY',
    'SQLITE_IOERR_READ', 'SQLITE_IOERR_SHORT_READ', 'SQLITE_IOERR_WRITE',
    'SQLITE_IOERR_FSYNC', 'SQLITE_IOERR_DIR_FSYNC', 'SQLITE_IOERR_TRUNCATE',
    'SQLITE_IOERR_FSTAT', 'SQLITE_IOERR_UNLOCK', 'SQLITE_IOERR_RDLOCK',
    'SQLITE_IOERR_DELETE', 'SQLITE_IOERR_BLOCKED', 'SQLITE_IOERR_NOMEM',
    'SQLITE_IOERR_ACCESS', 'SQLITE_IOERR_CHECKRESERVEDLOCK', 'SQLITE_IOERR_LOCK',
    'SQLITE_IOERR_CLOSE', 'SQLITE_IOERR_DIR_CLOSE', 'SQLITE_IOERR_SHMOPEN',
    'SQLITE_IOERR_SHMSIZE', 'SQLITE_IOERR_SHMLOCK', 'SQLITE_IOERR_SHMMAP',
    'SQLITE_IOERR_SEEK', 'SQLITE_IOERR_DELETE_NOENT', 'SQLITE_IOERR_MMAP',
    'SQLITE_IOERR_GETTEMPPATH', 'SQLITE_IOERR_CONVPATH', 'SQLITE_IOERR_VNODE',
    'SQLITE_IOERR_AUTH', 'SQLITE_IOERR_BEGIN_ATOMIC', 'SQLITE_IOERR_COMMIT_ATOMIC',
    'SQLITE_IOERR_ROLLBACK_ATOMIC', 'SQLITE_IOERR_DATA', 'SQLITE_IOERR_CORRUPTFS',
    'SQLITE_CONSTRAINT_CHECK', 'SQLITE_CONSTRAINT_COMMITHOOK',
    'SQLITE_CONSTRAINT_FOREIGNKEY', 'SQLITE_CONSTRAINT_FUNCTION',
    'SQLITE_CONSTRAINT_NOTNULL', 'SQLITE_CONSTRAINT_PRIMARYKEY',
    'SQLITE_CONSTRAINT_TRIGGER', 'SQLITE_CONSTRAINT_UNIQUE',
    'SQLITE_CONSTRAINT_VTAB', 'SQLITE_CONSTRAINT_ROWID',
    'SQLITE_CONSTRAINT_PINNED', 'SQLITE_CONSTRAINT_DATATYPE',
))
_RETIREMENT_MODULES = (
    ('services.formal_admission', 'web/backend/services/formal_admission.py'),
    ('web.backend.services.formal_admission', 'web/backend/services/formal_admission.py'),
    ('research.source_supervisor', 'web/backend/research/source_supervisor.py'),
    ('web.backend.research.source_supervisor', 'web/backend/research/source_supervisor.py'),
    ('research.source_sec_access', 'web/backend/research/source_sec_access.py'),
    ('web.backend.research.source_sec_access', 'web/backend/research/source_sec_access.py'),
    ('research.native_plan_supervisor', 'web/backend/research/native_plan_supervisor.py'),
    ('web.backend.research.native_plan_supervisor', 'web/backend/research/native_plan_supervisor.py'),
    ('research.errors', 'web/backend/research/errors.py'),
    ('web.backend.research.errors', 'web/backend/research/errors.py'),
    ('research.store', 'web/backend/research/store.py'),
    ('web.backend.research.store', 'web/backend/research/store.py'),
    ('services.sqlite_utils', 'web/backend/services/sqlite_utils.py'),
    ('web.backend.services.sqlite_utils', 'web/backend/services/sqlite_utils.py'),
    ('services.runtime_paths', 'web/backend/services/runtime_paths.py'),
    ('web.backend.services.runtime_paths', 'web/backend/services/runtime_paths.py'),
)
_RETIREMENT_FUNCTIONS = {
    'web/backend/services/formal_admission.py': ('withdraw', 'close_source',
        'source_closed', 'close_native', 'native_closed', 'release',
        'preserve_retirement_uncertainty', '_owned', '_Binding.check',
        '_history_worker_current', 'reserve_history_resource',
        'begin_history_resource_close'),
    'web/backend/research/store.py': ('ResearchStore._formal_mode',
        'ResearchStore._connect', 'ResearchStore.transaction.__wrapped__'),
    'web/backend/services/sqlite_utils.py': ('connect_private_auth',
        'native_thread_budget'),
    'web/backend/services/runtime_paths.py': ('private_auth_path',
        '_open_runtime_directory', '_close_runtime_fd', '_attach_history_parent',
        '_validated_directory_fd', '_check_current_parent', 'PrivateAuthFile.check'),
    'web/backend/research/source_supervisor.py': ('_check', '_identity_handle',
        '_same_store', '_binding_module', '_main_stop_entry', '_matching_intent',
        '_controlled_stopping', '_select', '_execute', 'request_main_stop',
        'retire', 'join', '_deadline', 'SourceSupervisor._run',
        'SourceSupervisor._run_with_budget'),
    'web/backend/research/source_sec_access.py': ('_identity', '_parent',
        '_regular', '_held', '_uncertain', '_close_owned', 'attach',
        'cleanup_completed', 'wait_before_claim', 'retire', 'close'),
    'web/backend/research/native_plan_supervisor.py': ('_scope_identity',
        '_full_context', '_supervisor_memory', '_supervisor_identity',
        '_select', '_worker_main', 'request_main_stop', 'request_session_stop',
        'retire', 'join', 'closed', 'release_main_context', 'shrink_main_deadline',
        '_ThreadBudget.__enter__', '_ThreadBudget.__exit__'),
}
_RETIREMENT_ERROR_CLASSES = {
    'web/backend/research/errors.py': ('ResearchError',),
    'web/backend/research/source_supervisor.py': ('_SourceStopping',
        'SourceStartFailure', 'SourceRetirementUncertain'),
    'web/backend/research/native_plan_supervisor.py': ('NativePlanStartFailure',),
    'web/backend/services/formal_admission.py': ('FormalAdmissionWithdrawn',
        'HistoryReadUnavailable'),
    'web/backend/services/runtime_paths.py': ('RuntimePathError',),
}
_MISSING_RETIREMENT_FIELD = object()


def _retirement_modules():
    result = []
    for name, relative in _RETIREMENT_MODULES:
        module = sys.modules.get(name)
        filename = vars(module).get('__file__') if type(module) is types.ModuleType else None
        if type(filename) is str and filename == str(ROOT / relative):
            result.append((module, relative))
    return result


def _retirement_type(value, class_name, relative):
    for module, path in _retirement_modules():
        if path == relative and type(value) is vars(module).get(class_name):
            return module
    return None


def _retirement_read(value, name):
    try:
        # Bypass caller properties/getattribute and inspect only native slots
        # or a small plain instance dictionary. No arbitrary descriptor runs.
        hierarchy = type.__getattribute__(type(value), '__mro__')[:16]
        for cls in hierarchy:
            fields = type.__getattribute__(cls, '__dict__')
            descriptor = fields.get(name)
            if type(descriptor) is types.MemberDescriptorType:
                return descriptor.__get__(value, type(value))
        for cls in hierarchy:
            descriptor = type.__getattribute__(cls, '__dict__').get('__dict__')
            if type(descriptor) is types.GetSetDescriptorType:
                fields = descriptor.__get__(value, type(value))
                if type(fields) is dict and len(fields) <= 32:
                    for key, item in dict.items(fields):
                        if type(key) is str and key == name:
                            return item
                break
    except BaseException:
        pass
    return _MISSING_RETIREMENT_FIELD


def _retirement_enum(value, allowed):
    return value if type(value) is str and len(value) <= 64 and value in allowed else None if value is None else 'OTHER'


def _retirement_sqlite_fields(error):
    if not any(type(error) is kind for kind, _ in _RETIREMENT_SQLITE_TYPES):
        return {}
    value = _retirement_read(error, 'sqlite_errorcode')
    primary = value & 255 if type(value) is int and 0 <= value <= 65535 else None
    if primary not in _RETIREMENT_SQLITE_PRIMARY:
        primary = None
    name = _retirement_read(error, 'sqlite_errorname')
    return {'sqlite_primary_code': primary,
        'sqlite_errorname': name if type(name) is str and len(name) <= 64
            and name in _RETIREMENT_SQLITE_NAMES else None}


def _retirement_frames(error):
    codes = []
    for module, relative in _retirement_modules():
        for literal in _RETIREMENT_FUNCTIONS.get(relative, ()):
            parts = literal.split('.')
            function = vars(module).get(parts[0])
            if len(parts) in (2, 3):
                function = vars(function).get(parts[1]) if type(function) is type else None
            if len(parts) == 3:
                # Only this canonical contextmanager's original generator is
                # observable; do not follow arbitrary wrappers or descriptors.
                wrapped = vars(function).get('__wrapped__') if type(function) is types.FunctionType else None
                closure = function.__closure__ if type(function) is types.FunctionType else None
                function = wrapped if (
                    literal == 'ResearchStore.transaction.__wrapped__'
                    and type(wrapped) is types.FunctionType
                    and wrapped.__globals__ is vars(module)
                    and wrapped.__qualname__ == 'ResearchStore.transaction'
                    and wrapped.__code__.co_filename == str(ROOT / relative)
                    and wrapped.__code__.co_flags & 0x20
                    and type(closure) is tuple and len(closure) == 1
                    and closure[0].cell_contents is wrapped
                ) else None
            if type(function) is types.FunctionType:
                codes.append((function.__code__, relative, literal))
    frames = []
    traceback = BaseException.__traceback__.__get__(error)
    for _ in range(64):
        if traceback is None:
            break
        coordinate = next(((relative, literal) for code, relative, literal in codes
                           if code is traceback.tb_frame.f_code), None)
        if coordinate is not None:
            frames.append({'file': coordinate[0], 'function': coordinate[1],
                           'line': min(1000000, max(0, traceback.tb_lineno))})
        traceback = traceback.tb_next
    return frames[-4:]


def _retirement_error_chain(error):
    chain, seen = [], set()
    for _ in range(2):
        if not issubclass(type(error), BaseException) or id(error) in seen:
            break
        seen.add(id(error))
        kind = next((kind.__name__ for kind in _STARTUP_ERROR_TYPES
                     if type(error) is kind), 'OTHER')
        kind = next((name for actual, name in _RETIREMENT_SQLITE_TYPES
                     if type(error) is actual), kind)
        research = False
        for module, relative in _retirement_modules():
            for name in _RETIREMENT_ERROR_CLASSES.get(relative, ()):
                if type(error) is vars(module).get(name):
                    kind = name
                    research = name in ('ResearchError', '_SourceStopping')
        code = _retirement_enum(_retirement_read(error, 'code'), _RETIREMENT_CODES) if research else None
        number = OSError.errno.__get__(error) if issubclass(type(error), OSError) else None
        record = {'type': kind, 'code': code,
            'errno': number if type(number) is int and 0 < number < 256 else None,
            'frames': _retirement_frames(error)}
        record.update(_retirement_sqlite_fields(error))
        chain.append(record)
        cause = BaseException.__cause__.__get__(error)
        error = cause if cause is not None else BaseException.__context__.__get__(error)
    return chain or [{'type': 'OTHER', 'code': None, 'errno': None, 'frames': []}]


def _retirement_errors(values):
    if type(values) not in (tuple, list):
        return {'valid': False, 'truncated': False, 'items': []}
    return {'valid': True, 'truncated': len(values) > 2,
            'items': [_retirement_error_chain(error) for error in values[:2]]}


def _retirement_thread(thread):
    if thread is None:
        return {'known': True, 'alive': False}
    if type(thread) is not threading.Thread:
        return {'known': False, 'alive': False}
    # Read native lock state without dispatching caller-overridable methods.
    stopped = _retirement_read(thread, '_is_stopped')
    event = _retirement_read(thread, '_started')
    flag = _retirement_read(event, '_flag') if type(event) is threading.Event else None
    lock = _retirement_read(thread, '_tstate_lock')
    if type(stopped) is not bool or type(flag) is not bool or (lock is not None and type(lock) is not _thread.LockType):
        return {'known': False, 'alive': False}
    return {'known': True, 'alive': flag and not stopped and lock is not None and _thread.LockType.locked(lock)}


def _retirement_receipt(receipt, class_name, relative):
    if receipt is None:
        return {'present': False, 'valid': True}
    if _retirement_type(receipt, class_name, relative) is None:
        return {'present': True, 'valid': False}
    state = _retirement_enum(_retirement_read(receipt, 'state'), frozenset(('CLOSED', 'CLEANUP_UNCERTAIN')))
    reason = _retirement_enum(_retirement_read(receipt, 'reason'), _RETIREMENT_REASONS)
    pending = _retirement_read(receipt, 'pending_task_id')
    valid = state not in (None, 'OTHER') and reason not in (None, 'OTHER') and (
        pending is None or type(pending) is str and len(pending) <= 128)
    return {'present': True, 'valid': valid, 'state': state, 'reason': reason,
            'pending': pending is not None}


def _retirement_binding_module(binding, app):
    module = _retirement_type(binding, '_Binding', 'web/backend/services/formal_admission.py')
    if (module is None or _retirement_read(binding, 'app') is not app
            or _retirement_read(binding, 'factory') is not vars(module).get('_FACTORY')
            or type(_retirement_read(binding, 'pid')) is not int
            or _retirement_read(binding, 'pid') != os.getpid()):
        return None
    return module


def _safe_retirement_snapshot(binding, app):
    admission = _retirement_binding_module(binding, app)
    if admission is None:
        return {'observation': 'UNAVAILABLE'}
    source_path = 'web/backend/research/source_supervisor.py'
    native_path = 'web/backend/research/native_plan_supervisor.py'
    source = _retirement_read(binding, 'supervisor')
    native = _retirement_read(binding, 'native_supervisor')
    source_known = (_retirement_type(source, 'SourceSupervisor', source_path) is not None
                    and _retirement_read(source, '_binding') is binding)
    native_known = (_retirement_type(native, 'NativePlanSupervisor', native_path) is not None
                    and _retirement_read(native, 'binding') is binding)
    def supervisor(value, known, *, native=False):
        if not known:
            return {'present': value is not None, 'known': False}
        return {'present': True, 'known': True,
            'state': _retirement_enum(_retirement_read(value, '_state'), _RETIREMENT_STATES),
            'failure': None if native else _retirement_enum(_retirement_read(value, '_failure'), _RETIREMENT_REASONS),
            'slot_retained': _retirement_read(value, '_slot') is not None,
            'lease_retained': _retirement_read(value, 'worker' if native else '_lease') is not None,
            'thread': _retirement_thread(_retirement_read(value, '_thread')),
            'errors': _retirement_errors(_retirement_read(value, '_errors'))}
    governor = _retirement_read(source, '_sec_access') if source_known else None
    gov_known = (_retirement_type(governor, '_Governor', 'web/backend/research/source_sec_access.py') is not None
                 and _retirement_read(governor, 'supervisor') is source
                 and _retirement_read(governor, 'binding') is binding)
    gov = {'present': governor is not None, 'known': gov_known}
    if gov_known:
        descriptor = _retirement_read(governor, 'fd')
        gov.update(state=_retirement_enum(_retirement_read(governor, 'state'), _RETIREMENT_STATES),
            reason=_retirement_enum(_retirement_read(governor, 'reason'), _RETIREMENT_REASONS),
            fd_known=descriptor is None or type(descriptor) is int and descriptor >= 0,
            fd_retained=descriptor is not None,
            errors=_retirement_errors(_retirement_read(governor, 'errors')))
    return {'observation': 'OBSERVED',
        'source': {'receipt': _retirement_receipt(_retirement_read(binding, 'source_receipt'), 'SourceCleanupReceipt', source_path),
            'errors': _retirement_errors(_retirement_read(binding, 'source_errors')),
            'supervisor': supervisor(source, source_known), 'governor': gov},
        'native': {'receipt': _retirement_receipt(_retirement_read(binding, 'native_receipt'), 'NativePlanCleanupReceipt', native_path),
            'errors': _retirement_errors(_retirement_read(binding, 'native_errors')),
            'supervisor': supervisor(native, native_known, native=True)}}


def _retirement_json(binding, app):
    try:
        value = json.dumps(_safe_retirement_snapshot(binding, app), sort_keys=True, separators=(',', ':'))
        return value if len(value.encode('ascii')) <= _RETIREMENT_LIMIT else '{"observation":"LIMIT"}'
    except BaseException:
        return '{"observation":"ERROR"}'


class _StartupErrorObserver:
    """Observe before the original logger's level check, without changing it."""
    def __init__(self, logger, capture):
        self._logger, self._capture = logger, capture

    def __getattr__(self, name):
        return getattr(self._logger, name)

    def error(self, *args, **kwargs):
        explicit = kwargs.get('exc_info')
        error = (explicit if isinstance(explicit, BaseException) else
                 explicit[1] if type(explicit) is tuple and len(explicit) == 3 else
                 sys.exc_info()[1])
        if isinstance(error, BaseException):
            self._capture(error)
        return self._logger.error(*args, **kwargs)


def _observe_owned_startup(config, capture):
    """Keep the real LifespanOn instance and its original ASGI control flow."""
    missing = object()
    prior_load = vars(config).get('load', missing)
    original_load = config.load
    installed = []
    owned = []
    retired = False

    def install():
        if installed:
            return
        original_class = config.lifespan_class

        def construct(actual_config):
            lifespan = original_class(actual_config)
            logger = lifespan.logger
            lifespan.logger = _StartupErrorObserver(logger, capture)
            owned.append((lifespan, logger))
            return lifespan

        config.lifespan_class = construct
        installed.append(original_class)

    def load(*args, **kwargs):
        # Server.serve calls this at its original running-loop position. Never
        # preload configuration merely to install a diagnostic observer.
        result = original_load(*args, **kwargs)
        install()
        return result

    config.load = load
    if config.loaded:
        install()

    def retire():
        nonlocal retired
        if retired:
            return
        retired = True
        if prior_load is missing:
            del config.load
        else:
            config.load = prior_load
        if installed:
            config.lifespan_class = installed[0]
        for lifespan, logger in owned:
            lifespan.logger = logger
        owned.clear()

    return retire


from web.backend.tests.acceptance.owned_smtp_tls import owned_smtp_tls, StartTLSHandler


class _MailHandler(StartTLSHandler):
    timeout = 3

    def smtp_socket_upgraded(self,old,new):
        with self.server.owner.lock:
            self.server.owner.sockets.discard(old);self.server.owner.sockets.add(new)

    def smtp_socket_closed(self,connection):
        with self.server.owner.lock:self.server.owner.sockets.discard(connection)

    def handle(self):
        deadline = time.monotonic() + 5
        recipients = []

        def line():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned SMTP deadline')
            self.request.settimeout(min(3, remaining))
            data = self.rfile.readline(8193)
            if len(data) > 8192:
                raise ValueError('owned SMTP line limit')
            return data

        self.wfile.write(b'220 fixture.invalid owned SMTP\r\n')
        while True:
            command = line()
            if not command:
                return
            verb = command.split(None, 1)[0].upper()
            if self.smtp_tls_command(verb):
                if self.smtp_tls_failed:return
                continue
            if verb == b'MAIL':
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'RCPT':
                address = command.partition(b':')[2].strip().strip(b'<>')
                if re.fullmatch(rb'[A-Za-z0-9._+\-]+@example\.invalid', address):
                    recipients.append(address.decode('ascii'))
                    self.wfile.write(b'250 ok\r\n')
                else:
                    self.wfile.write(b'553 synthetic recipient required\r\n')
            elif verb == b'DATA' and recipients:
                self.wfile.write(b'354 send message\r\n')
                raw = bytearray()
                while True:
                    part = line()
                    if part == b'.\r\n':
                        break
                    if not part or len(raw) + len(part) > 65536:
                        raise ValueError('owned SMTP message limit')
                    raw.extend(part[1:] if part.startswith(b'..') else part)
                message = BytesParser(policy=policy.default).parsebytes(bytes(raw))
                if message['To'] not in recipients:
                    raise ValueError('owned SMTP recipient mismatch')
                with self.server.owner.lock:
                    self.server.owner.messages.append(message)
                recipients.clear()
                self.wfile.write(b'250 stored\r\n')
            elif verb == b'RSET':
                recipients.clear()
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'NOOP':
                self.wfile.write(b'250 ok\r\n')
            elif verb == b'QUIT':
                self.wfile.write(b'221 done\r\n')
                return
            else:
                self.wfile.write(b'500 unsupported command\r\n')


class _MailServer(socketserver.ThreadingTCPServer):
    block_on_close = False
    request_queue_size = 8

    def process_request(self, request, address):
        worker = threading.Thread(target=self._owned_request, args=(request, address),
                                  name=PREFIX + 'smtp-connection')
        with self.owner.lock:
            self.owner.workers.append(worker)
            self.owner.sockets.add(request)
        try:
            worker.start()
        except BaseException:
            self.shutdown_request(request)
            with self.owner.lock:
                self.owner.sockets.discard(request)
            raise

    def _owned_request(self, request, address):
        try:
            self.process_request_thread(request, address)
        finally:
            with self.owner.lock:
                self.owner.sockets.discard(request)

    def handle_error(self, request, address):
        with self.owner.lock:
            self.owner.failures.append('SMTP_HANDLER_FAILED')


class _MailSink:
    def __init__(self):
        self.lock = threading.Lock()
        self.messages, self.workers, self.failures = [], [], []
        self.sockets = set()
        self._smtp_tls_scope=None;self._smtp_tls_active=False
        self.server = _MailServer(('127.0.0.1', 0), _MailHandler)
        self.server.owner = self
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': .05}, name=PREFIX + 'smtp')

    @property
    def port(self):
        return self.server.server_address[1]

    def start(self):
        self._smtp_tls_scope=owned_smtp_tls()
        context,_=self._smtp_tls_scope.__enter__();self._smtp_tls_active=True
        self.server.smtp_tls_context=context
        self.thread.start()

    def take_latest_magic_token(self):
        with self.lock:
            for position in range(len(self.messages) - 1, -1, -1):
                message = self.messages[position]
                body = message.get_body(preferencelist=('plain',))
                if body is None:
                    continue
                words = body.get_content().strip().split()
                if not words:
                    continue
                parsed = urlsplit(words[-1])
                query = parse_qs(parsed.query)
                if (parsed.scheme == 'https' and parsed.netloc == HOST and parsed.path == '/auth/verify'
                        and not parsed.fragment and set(query) == {'token'} and len(query['token']) == 1
                        and 0 < len(query['token'][0]) <= 8192):
                    self.messages.pop(position)
                    return query['token'][0]
        raise RuntimeError('no pending canonical synthetic login mail')

    def close(self):
        errors = []
        if self.thread.is_alive():
            try:
                self.server.shutdown()
            except BaseException as error:
                errors.append(type(error).__name__)
        with self.lock:
            sockets, workers = list(self.sockets), list(self.workers)
        for connection in sockets:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                connection.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        try:
            self.server.server_close()
        except BaseException as error:
            errors.append(type(error).__name__)
        deadline = time.monotonic() + 5
        for worker in (self.thread, *workers):
            if worker.ident is not None:
                try:
                    worker.join(max(0, deadline - time.monotonic()))
                except BaseException as error:
                    errors.append(type(error).__name__)
            if worker.is_alive():
                errors.append('SMTP_THREAD_UNREAPED')
        with self.lock:
            self.messages.clear()
            errors.extend(self.failures)
        if self._smtp_tls_active:
            self._smtp_tls_scope.__exit__(None,None,None);self._smtp_tls_active=False
        if errors:
            raise RuntimeError('owned SMTP cleanup uncertain: ' + ','.join(errors))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise PermissionError('owned Main client does not follow redirects')


class _HttpsClient:
    """Actual verified TLS and an initially empty, server-populated CookieJar."""
    def __init__(self, port, certificate):
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            _OwnedHTTPSHandler(port, certificate), urllib.request.HTTPCookieProcessor(self.cookies), _NoRedirect())

    def request(self, method, path, data=None, *, key=None):
        parsed = urlsplit(path)
        if (method not in ('GET', 'HEAD', 'POST') or not path.startswith('/api/')
                or len(path) > 8192 or parsed.scheme or parsed.netloc or parsed.fragment):
            raise ValueError('fixed canonical Main API required')
        headers = {'Origin': ORIGIN}
        raw = None if data is None else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        if raw is not None:
            if len(raw) > 65536:
                raise ValueError('owned Main request limit')
            headers['Content-Type'] = 'application/json'
        if key is not None:
            headers['Idempotency-Key'] = key
        request = urllib.request.Request(ORIGIN + path, data=raw, method=method, headers=headers)
        try:
            response = self.opener.open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(524289)
            if len(body) > 524288:
                raise ValueError('owned Main response limit')
            return response.status, json.loads(body) if body else None


class FormalMainBrowserService(AbstractContextManager):
    """One owned real Main lifetime; a retained failure is never a fresh retry."""
    def __init__(self, owned_root, *, history_source=None):
        self.root = Path(owned_root).absolute()
        self.history_source = ROOT if history_source is None else Path(history_source).resolve()
        self.origin, self.stop = ORIGIN, threading.Event()
        self.seed = self.app = self.main = self.server = self.server_thread = None
        self.app_socket = self.certificate = self.client = self._smtp = self._history = None
        self._prior, self._bridges, self._server_errors = {}, [], []
        self._startup_diagnostics = []
        self._retirement_binding = self._retirement_diagnostics = None
        self._entered = self._closed = False

    def __repr__(self):
        return '<owned actual Main browser service>'

    def __enter__(self):
        try:
            self._start()
            return self
        except BaseException as primary:
            try:
                self._close(primary)
            except BaseException as cleanup:
                primary.add_note('owned Main startup cleanup uncertain: ' + type(cleanup).__name__)
            raise

    def _start(self):
        if self._entered or self._closed:
            raise RuntimeError('owned Main service cannot be re-entered')
        self._entered = True
        if (self.root != self.root.resolve() or self.root.exists() or self.root.is_relative_to(ROOT)
                or any(parent.is_symlink() for parent in self.root.parents)
                or not self.root.parent.is_dir()):
            raise ValueError('fresh canonical owned root outside source required')
        if any(name in os.environ for name in (*_FOREIGN_SECRETS, *_FOREIGN_INPUTS)):
            raise RuntimeError('owned Main requires an unconfigured synthetic process')
        for name in ('main', 'web.backend.main'):
            module = sys.modules.get(name)
            if module is not None:
                if (Path(module.__file__).resolve() != ROOT / 'web/backend/main.py'
                        or not module._IS_PROD or not module._LAUNCH_FORMAL):
                    raise RuntimeError('another Main profile is already imported')
                if vars(sqlite3).get('_structural_main_admission_v1', {}).get(id(module.app)) is not None:
                    raise RuntimeError('another Main lifetime is already owned')
        self._history = prepared_source_history(self.history_source, self.root, target_revision=False)
        self.seed = self._history.__enter__()
        self._smtp = _MailSink()
        self._smtp.start()
        settings = {'STRUCTURAL_SHARE_TOKEN_SECRET': secrets.token_urlsafe(48),
            'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': str(self._smtp.port),
            'SMTP_FROM_EMAIL': 'sender@example.invalid', 'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid',
            'SMTP_STARTTLS': 'true', 'SMTP_USE_SSL': 'false', 'SMTP_TIMEOUT_SECONDS': '2'}
        self._prior = {name: os.environ.get(name) for name in settings}
        os.environ.update(settings)
        self.main = importlib.import_module('main')
        if Path(self.main.__file__).resolve() != ROOT / 'web/backend/main.py' or not self.main._LAUNCH_FORMAL:
            raise RuntimeError('canonical formal Main source required')
        self.app = self.main.app
        key, self.certificate = _certificates(self.root)
        self.app_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.app_socket.bind(('127.0.0.1', 0))
        self.port = self.app_socket.getsockname()[1]
        self.app_socket.listen(16)
        import uvicorn
        config = uvicorn.Config(self.app, host='127.0.0.1', port=self.port, lifespan='on',
            ssl_keyfile=str(key), ssl_certfile=str(self.certificate), loop='asyncio', ws='none',
            log_config=None, log_level='critical', access_log=False, timeout_graceful_shutdown=5)
        self.server = uvicorn.Server(config)
        def serve():
            retire_observer = None
            try:
                retire_observer = _observe_owned_startup(config, self._capture_startup_error)
                self.server.run(sockets=[self.app_socket])
            except BaseException as error:
                self._capture_startup_error(error)
                self._server_errors.append(next((kind.__name__ for kind in _STARTUP_ERROR_TYPES
                    if type(error) is kind), 'OTHER'))
            finally:
                if retire_observer is not None:
                    retire_observer()
        self.server_thread = threading.Thread(target=serve, name=PREFIX + 'app')
        self.server_thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.server_thread.is_alive() or time.monotonic() >= deadline:
                failure = RuntimeError('actual Main HTTPS startup unavailable')
                if self._startup_diagnostics:
                    failure.add_note('owned Main startup coordinates: ' +
                        json.dumps(self._startup_diagnostics, sort_keys=True, separators=(',', ':')))
                raise failure
            time.sleep(.02)
        self.client = _HttpsClient(self.port, self.certificate)
        status, body = self.client.request('GET', '/api/health')
        if (status != 200 or body['status'] != 'limited' or body['checks']['base'] != 'ready'
                or body['checks']['source_history'] != 'CURRENT_ACL_AND_STORED_SOURCE_REQUIRED'
                or body['checks']['source_execute'] not in ('ready', 'unavailable')
                or body['checks']['native_planner'] != 'FUNDING_CLOSED'):
            raise RuntimeError('actual Main base and closed capabilities differ')
        from services import formal_admission
        formal_admission.require(self.app, 'research_basic')
        formal_admission.require(self.app, 'source_history')
        self._remember_retirement_binding(formal_admission._STATE)

    def _remember_retirement_binding(self, state):
        # Retain only this actually admitted lifetime; retirement removes STATE.
        # Both canonical module families use the same actual registry. A copy
        # supplied by a caller is not the observed admission entry.
        try:
            if type(state) is not dict:
                return
            binding = dict.get(state, id(self.app))
            module = _retirement_binding_module(binding, self.app)
            if module is not None and vars(module).get('_STATE') is state:
                self._retirement_binding = binding
        except BaseException:
            pass

    def _observe_retirement(self):
        try:
            if self._retirement_binding is not None:
                self._retirement_diagnostics = _retirement_json(self._retirement_binding, self.app)
        except BaseException:
            self._retirement_diagnostics = '{"observation":"ERROR"}'
        finally:
            self._retirement_binding = None

    def _note_retirement(self, error):
        try:
            value = self._retirement_diagnostics
            if type(value) is str and len(value.encode('ascii')) <= _RETIREMENT_LIMIT:
                BaseException.add_note(error, 'owned Main retirement snapshot: ' + value)
        except BaseException:
            pass

    def _capture_startup_error(self, error):
        if len(self._startup_diagnostics) >= 4:
            return
        try:
            self._startup_diagnostics.extend(_safe_lifespan_errors(error)[:4-len(self._startup_diagnostics)])
        except BaseException:
            # A diagnostic failure must never replace the actual startup error.
            self._startup_diagnostics.append({'type': 'OTHER', 'frames': []})

    def source_status(self):
        """Observation only: no flag, receipt or authority is accepted."""
        if self.stop.is_set() or self.app is None:
            return 'unavailable'
        from services import formal_admission
        return formal_admission.safe_status(self.app)['source_execute']

    def retire_source(self):
        """Python-only actual sub-lifetime retirement; no caller authority input.

        A CLOSED Core result completes only this Source object. Main remains
        live for history; its other resources have a later teardown lifetime.
        Uncertainty retains the original fixed deadline/handles, never extends it.
        """
        if self.stop.is_set() or self.app is None:
            raise RuntimeError('owned Main service is retired')
        from services import formal_admission
        binding = formal_admission._STATE.get(id(self.app))
        if binding is None:
            raise RuntimeError('actual Main binding unavailable')
        binding.check()
        deadline = binding.source_deadline
        if deadline is None:
            deadline = time.monotonic() + 20
        formal_admission.close_source(binding, deadline_monotonic=deadline)
        if not formal_admission.source_closed(binding):
            raise RuntimeError('actual Source sub-lifetime did not close')
        return self.source_status()

    def browser_bridge(self):
        if self.stop.is_set() or self.server_thread is None or not self.server_thread.is_alive():
            raise RuntimeError('owned Main service is retired')
        bridge = CanonicalBrowserBridge(self)
        self._bridges.append(bridge)
        return bridge

    def take_latest_magic_token(self):
        if self.stop.is_set() or self._smtp is None:
            raise RuntimeError('owned Main mail sink is retired')
        return self._smtp.take_latest_magic_token()

    def _close(self, primary=None):
        if self._closed:
            return
        self.stop.set()
        errors = []
        for bridge in self._bridges:
            try:
                bridge.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        if self.server is not None:
            self.server.should_exit = True
        if self.server_thread is not None and self.server_thread.ident is not None:
            try:
                # Candidate HTTP5 + application20 + observer margin5. This local
                # test wait is not evidence of a production unit's hard deadline.
                self.server_thread.join(30)
            except BaseException as error:
                errors.append(type(error).__name__)
            if self.server_thread.is_alive():
                errors.append('MAIN_THREAD_UNREAPED')
        if self.app_socket is not None:
            try:
                self.app_socket.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        if self._smtp is not None:
            try:
                self._smtp.close()
            except BaseException as error:
                errors.append(type(error).__name__)
        errors.extend(self._server_errors)
        lifespan = getattr(self.server, 'lifespan', None)
        if lifespan is not None and (lifespan.error_occured or lifespan.startup_failed or lifespan.shutdown_failed):
            errors.append('MAIN_LIFESPAN_FAILED')
        if self.app is not None:
            from services import formal_admission
            if formal_admission._STATE.get(id(self.app)) is not None:
                errors.append('MAIN_BINDING_NOT_RETIRED')
        # A live server/handler must retain its configuration and helper scope.
        # The outer test process owns the final kill if normal reaping fails.
        live = self.server_thread is not None and self.server_thread.is_alive()
        if self._smtp is not None:
            live = live or self._smtp.thread.is_alive() or any(t.is_alive() for t in self._smtp.workers)
        # No Core check/close/receipt mutation: observe the retained actual
        # binding after the original join, before ENV/history are restored.
        self._observe_retirement()
        if live:
            failure = RuntimeError('owned Main resources remain live; root and scope retained')
            self._note_retirement(failure)
            raise failure
        for name, value in self._prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self._prior.clear()
        failure = primary if primary is not None else RuntimeError('owned Main cleanup uncertain') if errors else None
        if self._history is not None:
            try:
                self._history.__exit__(type(failure) if failure is not None else None, failure,
                                       failure.__traceback__ if failure is not None else None)
            except BaseException as error:
                errors.append(type(error).__name__)
        self._closed = not errors
        if errors:
            failure = RuntimeError('owned Main cleanup uncertain: ' + ','.join(errors))
            if self._startup_diagnostics:
                failure.add_note('owned Main lifespan coordinates: ' +
                    json.dumps(self._startup_diagnostics, sort_keys=True, separators=(',', ':')))
            self._note_retirement(failure)
            raise failure

    def close(self):
        self._close()

    def __exit__(self, kind, error, traceback):
        try:
            self._close(error)
        except BaseException as cleanup:
            if error is None:
                raise
            error.add_note('owned Main cleanup uncertain: ' + type(cleanup).__name__)
            self._note_retirement(error)
        return False


def self_test(owned_root):
    owned_root = Path(owned_root).absolute()
    with FormalMainBrowserService(owned_root) as service:
        client = service.client
        status, _ = client.request('POST', '/api/auth/request-link', {'email': service.seed.email})
        assert status == 200
        token = service.take_latest_magic_token()
        try:
            status, _ = client.request('POST', '/api/auth/verify', {'token': token})
        finally:
            token = None
        assert status == 200
        cookies = [cookie for cookie in client.cookies if cookie.name == 'phase_session']
        assert len(cookies) == 1 and cookies[0].secure and 'HttpOnly' in cookies[0]._rest
        query = urlencode({'task_id': service.seed.source_task_id, 'kind': 'excerpts'})
        status, result = client.request('GET', '/api/research/' + service.seed.research_id + '/records?' + query)
        assert status == 200 and result['data']['items']
        expected = {ref['excerpt_id']: ref for ref in service.seed.excerpt_refs}
        for item in result['data']['items']:
            ref = expected[item['id']]
            assert (item['source_revision'], item['text_digest'], item['start'], item['end']) == (
                ref['source_revision'], ref['content_digest'], ref['start'], ref['end'])
        # A revision containing a Source run cannot be submitted as an owned
        # observation. Save a new explicit observation through actual Main.
        problem = {'entry': 'phenomenon', 'original_input': '我观察到任务集中到达时，排队等待随积压增加。',
            'objective': '记录等待', 'summary': '合成观察自述，仅供实际Main入口测试。',
            'variables': [], 'constraints': [], 'unknowns': [], 'confirmed': True}
        revision = {'schema_version': 'structure-research-v1', 'contract_revision': 'b1-candidate-01',
                    'data': {'expected_revision': 1, 'problem': problem}}
        status, saved = client.request('POST', '/api/research/' + service.seed.research_id + '/revisions',
                                        revision, key='actual-main-https-new-observation')
        assert status == 200 and saved['data']['current_problem']['revision'] == 2
        data = {'input_revision': 2, 'expected_research_version': saved['data']['research_version'],
                'observation_source': 'own_observation', 'declaration_status': 'self_declared'}
        envelope = {'schema_version': 'structure-research-v1', 'contract_revision': 'funded-plan-v2', 'data': data}
        status, closed = client.request('POST', '/api/research/' + service.seed.research_id + '/plan-previews',
                                        envelope, key='actual-main-https-closed-preview')
        assert status == 200 and not closed['data']['can_confirm'] and closed['data']['funding_reason'] == 'FUNDING_CLOSED'
        with service.browser_bridge() as bridge:
            response = bridge.forward('GET', ORIGIN + '/assets/research.js', [])
            assert response.status == 200 and response.body == (ROOT / 'web/frontend/assets/research.js').read_bytes()
        actual_app = service.app
        source_status = service.source_status()
    from services import formal_admission
    try:
        formal_admission.require(actual_app, 'research_basic')
    except RuntimeError:
        pass
    else:
        raise AssertionError('shutdown Main binding remained usable')
    assert not owned_root.exists() and not service.server_thread.is_alive()
    return {'scope': 'actual_main_local_tls_only', 'actual_main': True, 'schema': service.seed.schema_version,
            'history_origin': 'offline_probe', 'actual_https_history': True, 'server_issued_secure_httponly_cookie': True,
            'source_execute': source_status, 'funding': 'closed', 'real_model_executed': False,
            'public_tls_verified': False, 'browser_behavior_verified': False, 'shutdown_binding': 'rejected', 'cleanup': 'closed'}


def failure_cleanup_test(owned_root):
    class BodyFailure(Exception):
        pass
    service = FormalMainBrowserService(owned_root)
    try:
        with service:
            raise BodyFailure('owned test-body failure')
    except BodyFailure:
        pass
    else:
        raise AssertionError('test-body failure was swallowed')
    assert Path(owned_root).exists() and not service.server_thread.is_alive()
    assert service._smtp is not None and not service._smtp.thread.is_alive()
    assert not any(thread.is_alive() for thread in service._smtp.workers)
    assert all(name not in os.environ for name in _FOREIGN_SECRETS[:4])
    return {'scope': 'actual_main_body_failure_cleanup', 'threads': 'closed', 'root': 'retained', 'signing_environment': 'removed'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', type=Path)
    parser.add_argument('--failure-cleanup-test', type=Path)
    args = parser.parse_args()
    if bool(args.self_test) == bool(args.failure_cleanup_test):
        parser.error('choose exactly one owned test root')
    result = self_test(args.self_test) if args.self_test else failure_cleanup_test(args.failure_cleanup_test)
    print(json.dumps(result, sort_keys=True))
