"""One canonical Main, one Source thread and one current task; no paid queue.

The registry is a lifetime witness, never a replacement for Source's native
task/owner leases, approval checks or SQL scopes. Cleanup outlives HTTP admission.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import importlib
import inspect
import math
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time
import types
from typing import Literal
from uuid import uuid4

from .errors import ResearchError

_FACTORY = object()
_REGISTRY = vars(sqlite3).setdefault('_structural_source_supervisor_v1', {})
_REGISTRY_LOCK = vars(sqlite3).setdefault('_structural_source_supervisor_lock_v1', threading.RLock())
_BATCH = 16
_POLL_SECONDS = .2


@dataclass(frozen=True, slots=True)
class SourceCleanupReceipt:
    contract: Literal['source-supervisor-cleanup-v1']
    supervisor_ref: str
    state: Literal['CLOSED', 'CLEANUP_UNCERTAIN']
    pending_task_id: str | None
    reason: Literal['CLOSED', 'DEADLINE', 'WORKER_FAILURE', 'CLOSE_UNCERTAIN', 'START_FAILED', 'RETIREMENT_UNCERTAIN']


class SourceStartFailure(RuntimeError):
    """Main must retain this actual partial handle and join its shared deadline."""
    def __init__(self, supervisor):
        super().__init__('Source supervisor start failed')
        self._supervisor = supervisor
    safe_code = 'START_FAILED'
    @property
    def supervisor(self):
        return self._supervisor


class SourceRetirementUncertain(RuntimeError):
    def __init__(self, supervisor):
        super().__init__('Source dispatch retirement uncertain')
        self._supervisor = supervisor
    safe_code = 'RETIREMENT_UNCERTAIN'
    @property
    def supervisor(self):
        return self._supervisor


def _unavailable():
    return ResearchError('FEATURE_UNAVAILABLE', 503, '来源执行监督器当前不可用；已存来源可按权限读取。')


def _admission():
    family = 'web.backend.services' if __package__ == 'web.backend.research' else 'services'
    return importlib.import_module(family + '.formal_admission')


def _code_images():
    root = Path(__file__).resolve().parent
    names = ('source_supervisor.py', 'source_workflow.py', 'source_integration.py', 'source_guard.py',
             'source_policy.py', 'source_spawn.py', 'authorization.py', 'runtime_profile.py', 'store.py',
             'service.py', 'runner.py', 'budget.py', 'paid_control.py', 'financial_guard.py',
             'evidence_repository.py', 'evidence_schemas.py', 'source_adapters/crossref_plos.py')
    result = {}
    for name in names:
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise _unavailable()
        result[path] = hashlib.sha256(path.read_bytes()).digest()
    return result


def _same_store(supervisor, store):
    from .store import ResearchStore
    if (type(store) is not ResearchStore or not store._formal_mode()
            or store.path != supervisor._path or store.storage_identity != supervisor._identity
            or store.auth_store.path != supervisor._path
            or store.auth_store.storage_identity != supervisor._identity):
        raise _unavailable()


class SourceSupervisor:
    __slots__ = ('_factory', '_origin', '_pid', '_binding', '_service', '_path', '_identity',
                 '_images', '_lock', '_event', '_state', '_thread', '_slot', '_lease',
                 '_failure', '_start_failed', '_cursor', '_stop', '_dispatch_mutex',
                 '_slot_epoch', '_deadline', '_reference', '_session', '_guard', '_errors')

    def __init__(self, service, binding, *, _factory=None):
        if _factory is not _FACTORY or inspect.currentframe().f_back.f_code is not start.__code__:
            raise TypeError('canonical Main Source start required')
        self._factory, self._origin, self._pid = _factory, __name__, os.getpid()
        self._binding, self._service = binding, service
        self._path, self._identity = service.store.path, service.store.storage_identity
        self._images = _code_images()
        self._lock, self._event = threading.RLock(), threading.Event()
        self._stop, self._dispatch_mutex = threading.Event(), threading.Lock()
        self._slot_epoch, self._deadline, self._reference = 0, {}, str(uuid4())
        self._session = self._guard = None
        self._errors = []  # Retain real exception frames/owned close handles.
        self._state, self._slot, self._lease = 'STARTING', None, None
        self._failure, self._start_failed, self._cursor = None, False, ''
        self._thread = threading.Thread(target=self._run, name='structure-source-supervisor', daemon=False)

    def __reduce__(self):
        raise TypeError('Source supervisor cannot cross processes')

    @property
    def reference(self):
        return self._reference

    def __repr__(self):
        return '<canonical Source supervisor>'

    def _run(self):
        try:
            from .runtime_profile import runtime_capability_facts
            # A new native, hook-protected schema14 snapshot in this thread.
            facts = runtime_capability_facts(self._service)
            if facts.profile.checked_pid != self._pid or facts.profile.research_schema != 14:
                raise _unavailable()
            while True:
                with self._lock:
                    if self._stop.is_set() or self._state in ('STOPPING', 'CLEANUP_UNCERTAIN'):
                        break
                    _check(self, published=True)
                    starting = self._state == 'STARTING'
                selected = _select(self._service.store, cleanup_only=starting, after=self._cursor)
                if not selected:
                    self._cursor = ''
                    if self._stop.is_set():
                        break
                    if starting:
                        # Do not publish READY while an old, lock-contended debt
                        # remains anywhere in the finite scan.
                        if not _select(self._service.store, cleanup_only=True):
                            with self._lock:
                                _check(self, published=True)
                                if self._state == 'STARTING':
                                    self._state = 'READY'
                    self._event.wait(_POLL_SECONDS)
                    self._event.clear()
                    continue
                for task_id, operation in selected:
                    self._cursor = task_id
                    with self._lock:
                        if self._stop.is_set() or self._state in ('STOPPING', 'CLEANUP_UNCERTAIN'):
                            break
                        _check(self, published=True)
                    try:
                        _execute(self, task_id, operation)
                    except ResearchError as error:
                        if error.code != 'STORE_BUSY':
                            raise
                    self._event.wait(.01)
                    self._event.clear()
        except BaseException as error:
            with self._lock:
                if not (self._stop.is_set() and self._slot is None and not self._errors
                        and isinstance(error, ResearchError) and error.code == 'FEATURE_UNAVAILABLE'):
                    self._errors.append(error)
                    self._failure = self._failure or 'WORKER_FAILURE'
                    self._state = 'CLEANUP_UNCERTAIN'
        finally:
            # A failed close retains the real slot/lease record and registry.
            # Thread exit alone is not proof that a Source sender was reaped.
            with self._lock:
                if self._failure is None and self._slot is None:
                    self._state = 'STOPPED'
                self._event.set()


def _identity_handle(supervisor):
    origin = sys.modules.get(supervisor._origin)
    if (origin is None or type(supervisor) is not getattr(origin, 'SourceSupervisor', None)
            or supervisor._factory is not origin._FACTORY or supervisor._pid != os.getpid()
            or _REGISTRY.get(id(supervisor._binding.app)) is not supervisor):
        raise _unavailable()


def _check(supervisor, *, published=False):
    _identity_handle(supervisor)
    if supervisor._images != _code_images():
        raise _unavailable()
    _same_store(supervisor, supervisor._service.store)
    if published:
        if supervisor._stop.is_set():
            raise _unavailable()
        try:
            supervisor._binding.check()
        except BaseException:
            if supervisor._stop.is_set():
                raise _unavailable() from None
            raise


def start(service, main_binding) -> SourceSupervisor:
    """Called directly by actual Main lifespan, after initialize/search/publish.

    STARTING is closed to HTTP. Every post-registration failure carries its
    original handle, including an indeterminate Thread.start result.
    """
    from .service import ResearchService
    from .store import ResearchStore
    from .source_spawn import require_supported
    admission = _admission()
    if (type(service) is not ResearchService or type(service.store) is not ResearchStore
            or type(main_binding) is not admission._Binding or main_binding.service is not service):
        raise _unavailable()
    admission._producer(main_binding.app)
    main_binding.check()
    if not service.store._formal_mode():
        raise _unavailable()
    require_supported()
    with _REGISTRY_LOCK:
        # Even an uncertain, stopped thread owns its old debt; never overwrite.
        if any(handle._pid == os.getpid() for handle in _REGISTRY.values()):
            raise _unavailable()
        supervisor = SourceSupervisor(service, main_binding, _factory=_FACTORY)
        _REGISTRY[id(main_binding.app)] = supervisor
    try:
        supervisor._thread.start()
    except BaseException as error:
        with supervisor._lock:
            supervisor._errors.append(error)
            supervisor._start_failed = True
            supervisor._failure = 'START_FAILED'
        supervisor._stop.set()
        supervisor._event.set()
        raise SourceStartFailure(supervisor) from None
    return supervisor


def require_available(app, service) -> None:
    """Only supervision facts. Caller first checks its real Main binding."""
    from .service import ResearchService
    supervisor = _REGISTRY.get(id(app))
    try:
        if type(service) is not ResearchService or supervisor is None:
            raise _unavailable()
        with supervisor._lock:
            _check(supervisor)
            _same_store(supervisor, service.store)
            if (supervisor._binding.app is not app or supervisor._state != 'READY'
                    or supervisor._stop.is_set() or supervisor._failure is not None
                    or not supervisor._thread.is_alive()):
                raise _unavailable()
    except (AttributeError, RuntimeError, OSError, ValueError, TypeError):
        raise _unavailable() from None


def require_worker(supervisor, store, task_id, *, operation: Literal['send', 'cleanup']) -> None:
    """Lifetime only; the caller must still hold fresh native SQL/lease scopes."""
    with supervisor._lock:
        _check(supervisor, published=operation == 'send')
        _same_store(supervisor, store)
        if (operation not in ('send', 'cleanup') or threading.current_thread() is not supervisor._thread
                or supervisor._slot != task_id or supervisor._lease is None
                or supervisor._lease.task_id != task_id or not supervisor._lease.active):
            raise _unavailable()
        if operation == 'send':
            if supervisor._stop.is_set() or supervisor._state != 'READY' or supervisor._failure is not None:
                raise _unavailable()
        elif supervisor._state not in ('STARTING', 'READY', 'STOPPING', 'CLEANUP_UNCERTAIN'):
            raise _unavailable()


def _for_store(store):
    candidates = [handle for handle in _REGISTRY.values()
                  if handle._pid == os.getpid() and handle._path == store.path
                  and handle._identity == store.storage_identity]
    if len(candidates) != 1:
        raise _unavailable()
    return candidates[0]


def _require_store_worker(store, *, operation):
    supervisor = _for_store(store)
    require_worker(supervisor, store, supervisor._slot, operation=operation)
    return supervisor


def wake(supervisor) -> None:
    _check(supervisor)
    supervisor._event.set()  # Hints may be lost; periodic scanning is authority.


def _deadline(supervisor, value):
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError('absolute monotonic deadline required')
    # One atomic CPython dict operation fixes the common Main budget even if
    # two shutdown callers arrive together. No extra lock or I/O precedes G.
    fixed = supervisor._deadline.setdefault('absolute', value)
    if value != fixed:
        raise ValueError('Main cleanup deadline cannot be extended or reset')
    return max(0., value - time.monotonic())


def retire(supervisor, *, deadline_monotonic: float) -> None:
    # No DB/Main/owner/task lock here: dispatch retirement must not reverse
    # the sender's task -> owner -> finished transaction -> dispatch order.
    _identity_handle(supervisor)
    remaining = _deadline(supervisor, deadline_monotonic)
    supervisor._stop.set()
    supervisor._event.set()
    if not supervisor._dispatch_mutex.acquire(timeout=remaining):
        supervisor._state = 'CLEANUP_UNCERTAIN'
        supervisor._failure = 'RETIREMENT_UNCERTAIN'
        raise SourceRetirementUncertain(supervisor)
    try:
        supervisor._slot_epoch += 1
        if supervisor._state not in ('STOPPED', 'CLEANUP_UNCERTAIN'):
            supervisor._state = 'STOPPING'
    finally:
        supervisor._dispatch_mutex.release()


def join(supervisor, *, deadline_monotonic: float) -> SourceCleanupReceipt:
    _identity_handle(supervisor)
    _deadline(supervisor, deadline_monotonic)
    try:
        retire(supervisor, deadline_monotonic=deadline_monotonic)
    except SourceRetirementUncertain:
        return SourceCleanupReceipt('source-supervisor-cleanup-v1', supervisor.reference,
                                    'CLEANUP_UNCERTAIN', supervisor._slot, 'RETIREMENT_UNCERTAIN')
    if threading.current_thread() is supervisor._thread:
        raise RuntimeError('Main must join its Source thread')
    try:
        if supervisor._thread.ident is not None:
            supervisor._thread.join(max(0., deadline_monotonic - time.monotonic()))
    except BaseException as error:
        supervisor._errors.append(error)
        supervisor._failure = 'CLOSE_UNCERTAIN'
    if not supervisor._lock.acquire(timeout=max(0., deadline_monotonic - time.monotonic())):
        supervisor._state = 'CLEANUP_UNCERTAIN'
        return SourceCleanupReceipt('source-supervisor-cleanup-v1', supervisor.reference,
                                    'CLEANUP_UNCERTAIN', supervisor._slot, 'DEADLINE')
    try:
        if (not supervisor._thread.is_alive() and supervisor._state == 'STOPPED'
                and supervisor._slot is None and supervisor._failure is None):
            with _REGISTRY_LOCK:
                if _REGISTRY.get(id(supervisor._binding.app)) is supervisor:
                    del _REGISTRY[id(supervisor._binding.app)]
            return SourceCleanupReceipt('source-supervisor-cleanup-v1', supervisor.reference, 'CLOSED', None, 'CLOSED')
        reason = supervisor._failure or ('DEADLINE' if supervisor._thread.is_alive() else 'CLOSE_UNCERTAIN')
        supervisor._state = 'CLEANUP_UNCERTAIN'
        return SourceCleanupReceipt('source-supervisor-cleanup-v1', supervisor.reference,
                                    'CLEANUP_UNCERTAIN', supervisor._slot, reason)
    finally:
        supervisor._lock.release()


def _select(store, *, cleanup_only=False, after=''):
    """No active/ACL join can hide a terminal or deleted task's old debt."""
    with store.transaction() as conn:
        if conn.execute('SELECT version FROM research_schema').fetchone()[0] != 14:
            raise _unavailable()
        rows = conn.execute("""SELECT t.id,r.started,t.execution,
            EXISTS(SELECT 1 FROM research_source_requests q WHERE q.task_id=t.id
                   AND q.outcome IN ('SENDING','UNKNOWN') AND q.execution_closed=0) AS debt
            FROM research_tasks t JOIN research_source_runs r ON r.task_id=t.id
            JOIN research_source_resources s ON s.task_id=t.id
            WHERE t.policy_revision='d1-source-only-v1' AND t.id>?
            AND ((r.started=1 AND t.execution NOT IN ('COMPLETED','FAILED','CANCELLED','ACCESS_REVOKED'))
                OR EXISTS(SELECT 1 FROM research_source_requests q WHERE q.task_id=t.id
                   AND q.outcome IN ('SENDING','UNKNOWN') AND q.execution_closed=0)
                OR (?=0 AND r.started=0 AND t.execution='QUEUED' AND t.stop_requested=0
                    AND s.state='admitted' AND s.admission_json IS NOT NULL))
            ORDER BY t.id LIMIT ?""", (after, int(cleanup_only), _BATCH)).fetchall()
        return [(row['id'], 'cleanup' if row['started'] or row['debt'] else 'send') for row in rows]


def _execute(supervisor, task_id, operation):
    from .authorization import AuthorizationGate
    from .source_workflow import close_interrupted, run_source_once
    from .source_policy import PinnedPublicTransport
    store = supervisor._service.store
    if operation == 'send':
        # Eligibility is checked before task-lock birth/CAS, then again by the
        # original native task/owner scopes. Never apply this filter to debt.
        from .source_integration import check_approval
        from .source_guard import check_active
        try:
            with store.transaction() as conn:
                task = conn.execute('SELECT * FROM research_tasks WHERE id=?', (task_id,)).fetchone()
                if not task or task['execution'] != 'QUEUED':
                    return
                AuthorizationGate(store).check_task(conn, task)
                run, _ = check_approval(conn, task)
                check_active(store, conn, task_id)
                if run['started'] or run['origin'] != 'live':
                    return
        except (ResearchError, PermissionError):
            return
    with supervisor._lock:
        if supervisor._stop.is_set() or supervisor._state == 'STOPPING':
            return
        if supervisor._slot is not None:
            raise _unavailable()
        supervisor._slot = task_id
        supervisor._slot_epoch += 1
    clean = False
    try:
        with AuthorizationGate(store).source_task_gate(task_id, timeout=.1) as lease:
            supervisor._lease = lease
            if operation == 'cleanup':
                require_worker(supervisor, store, task_id, operation='cleanup')
                close_interrupted(store, task_id, lease)
            else:
                if not supervisor._stop.is_set():
                    require_worker(supervisor, store, task_id, operation='send')
                    try:
                        run_source_once(store, task_id, lease, PinnedPublicTransport())
                    except ResearchError as error:
                        if error.code != 'FEATURE_UNAVAILABLE' or not supervisor._stop.is_set():
                            raise
                        # Retirement can win between the last precheck and the
                        # original run_source_once entry. Prove no claim/send.
                        with store.transaction() as conn:
                            row = conn.execute('SELECT started FROM research_source_runs WHERE task_id=?', (task_id,)).fetchone()
                            sent = conn.execute('SELECT 1 FROM research_source_requests WHERE task_id=?', (task_id,)).fetchone()
                            if not row or row[0] != 0 or sent:
                                raise
        clean = True
    except ResearchError as error:
        if error.code == 'STORE_BUSY' and supervisor._lease is None:
            clean = True  # No native slot was acquired; the DB debt remains.
        raise
    except BaseException as error:
        supervisor._errors.append(error)
        raise
    finally:
        with supervisor._lock:
            if clean:
                supervisor._slot = supervisor._lease = None
                supervisor._session = supervisor._guard = None
            else:
                supervisor._failure = 'CLOSE_UNCERTAIN'
                supervisor._state = 'CLEANUP_UNCERTAIN'


def _bind_session(session):
    from .source_workflow import SourceSession
    if type(session) is not SourceSession or inspect.currentframe().f_back.f_code is not SourceSession.__init__.__code__:
        raise PermissionError('canonical Source session birth required')
    supervisor = _require_store_worker(session.store, operation='send')
    if supervisor._session is not None or supervisor._guard is not None:
        raise PermissionError('Source slot session already bound')
    supervisor._session = session
    supervisor._guard = SourceDispatchGuard(supervisor, session, _factory=_FACTORY)


@contextmanager
def send_handoff_scope(still_authorized, *, deadline_monotonic):
    from .source_workflow import SourceSession
    from .runtime_profile import formal_request_required
    canonical = (type(still_authorized) is types.MethodType
                 and still_authorized.__func__ is SourceSession.still_authorized
                 and type(still_authorized.__self__) is SourceSession)
    if not canonical:
        if formal_request_required() or any(handle._pid == os.getpid() for handle in _REGISTRY.values()):
            raise PermissionError('formal Source requires canonical session authority')
        yield  # Legacy nonformal transport probes grant no C3 authority.
        return
    session = still_authorized.__self__
    if not session.store._formal_mode():
        yield
        return
    from .source_policy import PinnedPublicTransport
    caller = inspect.currentframe().f_back.f_back
    transport = caller.f_locals.get('self')
    if (caller.f_code is not PinnedPublicTransport.get.__code__
            or type(transport) is not PinnedPublicTransport or transport is not session.transport):
        raise PermissionError('canonical Source transport caller required')
    supervisor = _require_store_worker(session.store, operation='send')
    guard = supervisor._guard
    if type(guard) is not SourceDispatchGuard or supervisor._session is not session:
        raise PermissionError('actual supervised Source session required')
    with guard.handoff_scope(session, transport, deadline_monotonic=deadline_monotonic):
        yield


class SourceDispatchGuard:
    """Typed, unpickleable current-slot witness; G contains no authority I/O."""
    __slots__ = ('_supervisor', '_session', '_task_id', '_epoch', '_pid', '_thread', '_transport', '_factory')

    def __init__(self, supervisor, session, *, _factory=None):
        if _factory is not _FACTORY or inspect.currentframe().f_back.f_code is not _bind_session.__code__:
            raise TypeError('current supervised Source slot required')
        require_worker(supervisor, session.store, session.task_id, operation='send')
        self._supervisor, self._session = supervisor, session
        self._task_id, self._epoch = session.task_id, supervisor._slot_epoch
        self._pid, self._thread, self._factory = os.getpid(), threading.current_thread(), _factory
        self._transport = session.transport

    def __reduce__(self):
        raise TypeError('Source dispatch guard cannot cross processes')

    @contextmanager
    def handoff_scope(self, session, transport, *, deadline_monotonic):
        supervisor = self._supervisor
        remaining = max(0., deadline_monotonic - time.monotonic())
        if not supervisor._dispatch_mutex.acquire(timeout=remaining):
            raise PermissionError('Source dispatch deadline ended')
        try:
            # IN-MEMORY ONLY. Original ACL/lease checks finished before G.
            origin = sys.modules.get(supervisor._origin)
            if (type(self) is not SourceDispatchGuard or self._factory is not _FACTORY
                    or origin is None or type(supervisor) is not origin.SourceSupervisor
                    or supervisor._factory is not origin._FACTORY or supervisor._pid != os.getpid()
                    or self._pid != os.getpid() or self._thread is not threading.current_thread()
                    or self._thread is not supervisor._thread or supervisor._slot != self._task_id
                    or supervisor._slot_epoch != self._epoch or self._session is not session
                    or supervisor._session is not session or supervisor._guard is not self
                    or self._transport is not transport or transport is not session.transport
                    or session.task_id != self._task_id
                    or session.store is not supervisor._service.store
                    or _REGISTRY.get(id(supervisor._binding.app)) is not supervisor
                    or supervisor._stop.is_set() or supervisor._state != 'READY'
                    or supervisor._failure is not None):
                raise PermissionError('Source dispatch authority retired')
            yield
        finally:
            supervisor._dispatch_mutex.release()
