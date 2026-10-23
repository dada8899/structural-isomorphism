"""Optional, existing-only SEC resource owned by the actual Source lifetime.

This module grants no request authority. The current transport has no DOC
target/profile decoder, so begin_request always refuses a request. In particular,
holding a flock or observing a pacing state never enables a public GET.
"""
from __future__ import annotations

import fcntl
import inspect
import math
import os
import stat
import threading
import time

_FACTORY = object()
_NAME = 'source-sec-access.lock'
_INTERVAL = 1.0


class _Cadence:
    """Pure timing state; contains neither native resources nor send authority."""
    __slots__ = ('next_due', 'flight', 'uncertain')

    def __init__(self):
        self.next_due, self.flight, self.uncertain = None, None, False

    def cleared(self, now):
        if self.next_due is not None or self.flight is not None or self.uncertain:
            raise RuntimeError('cleanup checkpoint already consumed')
        self.next_due = now + _INTERVAL

    def delay(self, now):
        if self.next_due is None or self.flight is not None or self.uncertain:
            raise PermissionError('SEC cadence is not clear')
        return max(0., self.next_due - now)

    def begin(self, now):
        if self.delay(now) != 0:
            raise PermissionError('SEC cadence is cooling down')
        self.flight = object()
        return self.flight

    def finished(self, token, now):
        # Pure mechanism only. The native finish_request port below never
        # accepts this token as evidence of actual transport retirement.
        if token is not self.flight or self.flight is None or self.uncertain:
            raise PermissionError('SEC cadence flight did not retire')
        self.flight, self.next_due = None, now + _INTERVAL

    def unknown(self, token):
        if token is not self.flight or self.flight is None:
            raise PermissionError('SEC cadence flight identity changed')
        self.uncertain = True


class _Governor:
    __slots__ = ('supervisor', 'binding', 'reference', 'context', 'pid', 'factory',
                 'fd', 'identity', 'state', 'reason', 'errors', 'cadence', 'retired')

    def __init__(self, supervisor, *, _factory=None):
        frame = inspect.currentframe().f_back
        if _factory is not _FACTORY or frame.f_globals is not globals() or frame.f_code is not attach.__code__:
            raise TypeError('canonical Source SEC attachment required')
        self.supervisor, self.binding = supervisor, supervisor._binding
        self.reference, self.context = self.binding.reference, self.binding.native_context
        self.pid, self.factory = os.getpid(), _factory
        self.fd = self.identity = None
        self.state, self.reason = 'UNBOUND', None
        self.errors, self.cadence, self.retired = [], _Cadence(), False

    def __repr__(self):
        return '<optional native Source SEC resource>'

    def __reduce__(self):
        raise TypeError('Source SEC resource cannot cross processes')


def _source():
    from . import source_supervisor
    return source_supervisor


def _identity(governor):
    source = _source()
    if type(governor) is not _Governor or governor.factory is not _FACTORY or governor.pid != os.getpid():
        raise RuntimeError('actual Source SEC resource required')
    supervisor, binding = governor.supervisor, governor.binding
    source._identity_handle(supervisor)
    source._binding_module(supervisor)
    source._same_store(supervisor, supervisor._service.store)
    if (getattr(supervisor, '_sec_access', None) is not governor or supervisor._binding is not binding
            or binding.reference != governor.reference or binding.native_context is not governor.context
            or binding.service is not supervisor._service):
        raise RuntimeError('Source SEC binding identity changed')
    from . import native_plan_supervisor as native
    native._scope_identity(governor.context, supervisor._service.store)
    return supervisor


def _parent(governor):
    binding = governor.binding
    if binding.roots != (binding.paths.STATE_ROOT, binding.paths.CACHE_ROOT, binding.paths.LOG_ROOT):
        raise RuntimeError('Source SEC private roots changed')
    witness = binding.witnesses[0]
    if (type(witness) is not binding.paths.PrivateAuthFile
            or witness.path != binding.roots[0] / 'auth.sqlite3'
            or witness.file_identity != governor.supervisor._identity):
        raise RuntimeError('Source SEC requires the original Auth witness')
    witness.check()  # Checks the named directory and original Auth inode.
    return witness.parent_fd


def _regular(info):
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
        raise RuntimeError('Source SEC lock metadata invalid')
    return info.st_dev, info.st_ino


def _held(governor):
    parent = _parent(governor)
    if governor.fd is None or governor.identity is None:
        raise RuntimeError('Source SEC lock not held')
    if (_regular(os.fstat(governor.fd)) != governor.identity
            or _regular(os.stat(_NAME, dir_fd=parent, follow_symlinks=False)) != governor.identity):
        raise RuntimeError('Source SEC lock pathname changed')


def _uncertain(governor, error):
    governor.errors.append(error)
    governor.state, governor.reason = 'CLEANUP_UNCERTAIN', 'CLOSE_UNCERTAIN'


def _close_owned(governor):
    # Retain the actual descriptor number on an indeterminate close. Never
    # retry it: an interrupted close could have released and reused that number.
    if governor.fd is not None:
        try:
            os.close(governor.fd)
        except BaseException as error:
            _uncertain(governor, error)
            return False
        governor.fd = None
    return True


def attach(supervisor):
    """Only canonical start, after registration, before native Thread.start."""
    source = _source()
    frame = inspect.currentframe().f_back
    if frame.f_globals is not vars(source) or frame.f_code is not source.start.__code__:
        raise TypeError('canonical Source start required')
    source._check(supervisor, published=True)
    from . import native_plan_supervisor as native
    native.require_startup_scope(supervisor._binding.native_context, supervisor._service.store)
    governor = _Governor(supervisor, _factory=_FACTORY)
    supervisor._sec_access = governor  # Publish the partial handle before open.
    try:
        _identity(governor)
        parent = _parent(governor)
        flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
        governor.fd = os.open(_NAME, flags, dir_fd=parent)
        governor.identity = _regular(os.fstat(governor.fd))
        _held(governor)
        fcntl.flock(governor.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _held(governor)
        governor.state = 'HELD_CLEANUP'
    except (OSError, RuntimeError) as error:
        # Optional absence/invalid configuration/contended flock closes only
        # our own FD. A failed close remains an owned uncertain resource.
        governor.reason = type(error).__name__
        if _close_owned(governor):
            governor.state = 'UNBOUND'
    except BaseException as error:
        _uncertain(governor, error)
    return governor


def cleanup_completed(governor):
    """The real worker's completed all-principal debt scan is the only input."""
    supervisor = _identity(governor)
    source = _source()
    frame = inspect.currentframe().f_back
    if (frame.f_globals is not vars(source) or frame.f_code is not source.SourceSupervisor._run_with_budget.__code__
            or threading.current_thread() is not supervisor._thread
            or supervisor._slot is not None or supervisor._lease is not None):
        raise RuntimeError('actual Source cleanup checkpoint required')
    # The earlier scan check can precede a real Main withdrawal. Only the
    # original check can establish sealed stopping provenance; an Event or
    # retired flag alone must never turn a resource/integrity failure normal.
    source._check(supervisor, published=True)
    if supervisor._state != 'STARTING' or supervisor._stop.is_set() or governor.retired:
        source._check(supervisor, published=True)
        raise RuntimeError('actual Source cleanup checkpoint required')
    if governor.state == 'UNBOUND':
        return
    if governor.state != 'HELD_CLEANUP':
        source._check(supervisor, published=True)
        raise RuntimeError('Source SEC cleanup unavailable')
    _held(governor)
    governor.cadence.cleared(time.monotonic())
    governor.state = 'COOLDOWN'


def wait_before_claim(governor):
    """Wait outside every Source/Owner/DB lock; stop uses the original event.

    This only rechecks a resource/cadence. DOC permission is still absent and
    must be checked by a future native DOC dispatcher after this returns.
    """
    supervisor = _identity(governor)
    if threading.current_thread() is not supervisor._thread:
        raise PermissionError('actual Source worker required')
    if supervisor._slot is not None or supervisor._lease is not None or supervisor._lock._is_owned():
        raise RuntimeError('SEC pacing must precede native slot birth')
    while True:
        _source()._check(supervisor, published=True)
        if governor.retired or governor.state not in ('COOLDOWN', 'RECHECK_REQUIRED'):
            raise PermissionError('Source SEC resource unavailable')
        _held(governor)
        delay = governor.cadence.delay(time.monotonic())
        if delay == 0:
            governor.state = 'RECHECK_REQUIRED'
            return
        supervisor._stop.wait(delay)


def begin_request(governor, actual_session, fixed_target):
    _identity(governor)
    raise PermissionError('native DOC target, access profile and transport retirement are not installed')


def finish_request(flight, actual_retirement):
    # No native flight can be minted in this engineering slice. Accepting a
    # bool/receipt here would pre-authorize a later transport integration.
    raise PermissionError('no native DOC flight exists')


def retire(governor):
    supervisor = _identity(governor)
    governor.retired = True
    supervisor._stop.set()
    if governor.state != 'CLEANUP_UNCERTAIN':
        governor.state = 'RETIRED'
    try:
        if supervisor._images != _source()._code_images():
            raise RuntimeError('Source SEC source image changed')
        if governor.fd is not None:
            _held(governor)
    except BaseException as error:
        _uncertain(governor, error)


def close(governor, original_deadline):
    supervisor = _identity(governor)
    if (type(original_deadline) not in (int, float) or not math.isfinite(original_deadline)
            or supervisor._deadline.get('absolute') != original_deadline):
        raise ValueError('original Main cleanup deadline required')
    if (not governor.retired or supervisor._thread.is_alive() or supervisor._slot is not None
            or supervisor._lease is not None or supervisor._session is not None or supervisor._guard is not None
            or governor.state == 'CLEANUP_UNCERTAIN' or governor.cadence.flight is not None
            or governor.cadence.uncertain):
        return False
    if governor.state == 'CLOSED':
        return True
    try:
        if time.monotonic() >= original_deadline:
            return False
        if governor.fd is not None:
            _held(governor)
        if not _close_owned(governor):
            return False
        governor.state = 'CLOSED'
        return True
    except BaseException as error:
        _uncertain(governor, error)
        return False
