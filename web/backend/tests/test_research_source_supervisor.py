"""Core components, not evidence of formal Main/READY admission.

Real HTTP-queued legacy14 tasks exercise runner/leases/GET/closure; the current
supervisor selector must reject that legacy profile. Current15 selection and
Main-thread execution are separate actual-Main controls. Private in-memory
handles exercise G/retirement without changing any production admission check.
Only tests replace the registry with a local dictionary; no install bypass is
provided in production and public start/availability remain closed to these.
"""
from contextlib import contextmanager
from functools import partial
import os
import gc
import fcntl
import stat
import sqlite3
from pathlib import Path
import hashlib
import json
import pickle
import threading
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI

from research import ResearchRunner, ResearchService, ResearchStore
from research import source_supervisor as control, source_workflow
from research.authorization import AuthorizationGate
from research.errors import ResearchError
from research.source_policy import PinnedPublicTransport
from .test_research_source_terminal14 import current14, start as new_task, cancel
from .source_http_fixture import source_server, get_local, drop_after_response
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack


@pytest.fixture
def component(current14, monkeypatch):
    _, store, _ = current14
    # Test-only memory specimen. It has no real Main binding and cannot pass
    # _same_store(), public start(), require_available() or formal require_worker.
    supervisor = object.__new__(control.SourceSupervisor)
    binding=SimpleNamespace(app=FastAPI(),reference=str(uuid4()),pid=os.getpid())
    values = dict(_factory=control._FACTORY, _origin=control.__name__, _pid=os.getpid(),
        _binding=binding, _binding_reference=binding.reference, _main_stop_intent=None, _source_stop_intent=None, _stop_intents={}, _main_stop_entry=None,
        _service=ResearchService(store),
        _path=store.path, _identity=store.storage_identity, _images=control._code_images(),
        _lock=threading.RLock(), _dispatch_mutex=threading.Lock(), _stop=threading.Event(),
        _event=threading.Event(), _state='READY', _thread=threading.current_thread(),
        _slot=str(uuid4()), _lease=None, _failure=None, _start_failed=False, _cursor='',
        _slot_epoch=1, _deadline={}, _reference=str(uuid4()), _session=None, _guard=None, _errors=[])
    for key, value in values.items():
        setattr(supervisor, key, value)
    monkeypatch.setattr(control, '_REGISTRY', {id(supervisor._binding.app): supervisor})
    session = object.__new__(source_workflow.SourceSession)
    session.store, session.task_id, session.transport = store, supervisor._slot, PinnedPublicTransport()
    guard = object.__new__(control.SourceDispatchGuard)
    for key, value in dict(_supervisor=supervisor, _session=session, _task_id=session.task_id,
        _epoch=1, _pid=os.getpid(), _thread=threading.current_thread(),
        _transport=session.transport, _factory=control._FACTORY).items():
        setattr(guard, key, value)
    supervisor._session, supervisor._guard = session, guard
    yield supervisor, session, guard
    supervisor._stop.set()
    assert not supervisor._dispatch_mutex.locked()
    assert supervisor._thread is threading.current_thread() or not supervisor._thread.is_alive()


def test_public_ports_reject_fake_binding_legacy_store_and_env_promotion(current14, component, monkeypatch):
    _, store, _ = current14
    supervisor, session, _ = component
    service = ResearchService(store)
    for action in (
        lambda: control.SourceSupervisor(service, object()),
        lambda: control.SourceDispatchGuard(supervisor, session),
        lambda: control.start(service, SimpleNamespace(service=service)),
        lambda: control.require_available(supervisor._binding.app, service),
        lambda: control.require_worker(supervisor, store, session.task_id, operation='send'),
        lambda: pickle.dumps(supervisor),
    ):
        with pytest.raises((ResearchError, TypeError, RuntimeError)):
            action()
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    with pytest.raises((ResearchError, RuntimeError)):
        control.require_available(supervisor._binding.app, service)
    assert store._private_auth is False


def _assert_current_selector_rejects_legacy14(store):
    assert store._formal_mode() is False
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 14
        ResearchStore._check_v14(conn)
    for cleanup_only in (False, True):
        with pytest.raises(ResearchError) as rejected:
            control._select(store, cleanup_only=cleanup_only)
        assert rejected.value.code == 'FEATURE_UNAVAILABLE' and rejected.value.status == 503


def test_real_legacy14_component_completed_task_never_replays(current14, monkeypatch):
    client, store, rid = current14
    queued = []
    actual_post = client.post
    def observed_post(url, *args, **kwargs):
        response = actual_post(url, *args, **kwargs)
        if url == f'/api/research/{rid}/source-tasks':
            queued.append((url, kwargs['json'], dict(kwargs['headers'])))
        return response
    monkeypatch.setattr(client, 'post', observed_post)
    tid = new_task(client, rid)
    _assert_current_selector_rejects_legacy14(store)
    # This component explicitly runs the actual HTTP-created task. It does not
    # claim current15 periodic selection or use a wake hint as authority.
    with source_server() as (port, calls):
        runner = ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(get_local, port)))
        assert runner.run_once(tid) == 'COMPLETED'
        assert calls == ['/discovery', '/article']
        url, body, headers = queued[0]
        replay = actual_post(url, json=body, headers=headers)
        assert replay.status_code == 200 and replay.json()['data']['task']['id'] == tid
        assert runner.run_once(tid) == 'COMPLETED'
        assert calls == ['/discovery', '/article']
    with store.transaction() as conn:
        assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM research_tasks WHERE policy_revision!='d1-source-only-v1'").fetchone()[0] == 0


def test_real_legacy14_component_terminal_unknown_closes_under_fresh_leases_without_get(current14, monkeypatch):
    client, store, rid = current14
    tid = new_task(client, rid)
    with source_server() as (port, calls):
        with monkeypatch.context() as fault:
            def interrupted(*args):
                raise OSError('component closure interruption')
            fault.setattr(source_workflow, 'close_interrupted', interrupted)
            with pytest.raises(OSError, match='component closure interruption'):
                ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(drop_after_response, port))).run_once(tid)
        cancel(client, rid, tid)
        with store.transaction() as conn:
            before = dict(conn.execute('SELECT * FROM research_source_requests WHERE task_id=?', (tid,)).fetchone())
        assert (before['outcome'], before['execution_closed']) == ('UNKNOWN', 0)
        _assert_current_selector_rejects_legacy14(store)
        gate = AuthorizationGate(store)
        with gate.source_task_gate(tid) as lease:
            assert lease.cleanup is True
            source_workflow.close_interrupted(store, tid, lease)
        assert calls == ['/discovery']
        with store.transaction() as conn:
            after = dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?', (before['id'],)).fetchone())
            assert (after['outcome'], after['execution_closed']) == ('UNKNOWN', 1)
            assert after['closure_ref'] and after['closure_proof']
            assert (after['started_at'], after['ended_at']) == (before['started_at'], before['ended_at'])
            assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0] == 1


def test_real_legacy14_component_two_workers_same_task_send_only_once(current14, monkeypatch):
    from research import source_guard
    client, store, rid = current14
    tid = new_task(client, rid)
    _assert_current_selector_rejects_legacy14(store)
    outcomes, failures = [], []
    go = threading.Barrier(2)
    first_read = threading.Barrier(2)
    seen, seen_lock = set(), threading.Lock()
    actual_resource = source_guard.resource
    def observed_resource(conn, task_id):
        row = actual_resource(conn, task_id)
        name = threading.current_thread().name
        with seen_lock:
            pause = name.startswith('source-birth-worker-') and name not in seen and row['task_gate_identity'] is None
            if pause: seen.add(name)
        if pause: first_read.wait(3)
        return row  # Real row unchanged; both workers observed pre-birth state.
    monkeypatch.setattr(source_guard, 'resource', observed_resource)
    with source_server() as (port, calls):
        def run():
            try:
                go.wait(3)
                outcomes.append(ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(get_local, port))).run_once(tid))
            except BaseException as error:
                failures.append((type(error).__name__, str(error)))
        workers = [threading.Thread(target=run, name='source-birth-worker-' + str(index)) for index in range(2)]
        try:
            for worker in workers: worker.start()
            for worker in workers: worker.join(8)
            assert not any(worker.is_alive() for worker in workers)
            assert outcomes == ['COMPLETED'] and failures == [('PermissionError', 'Source birth is no longer available')], (outcomes, failures)
            assert calls == ['/discovery', '/article']
            with store.transaction() as conn:
                assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0] == 2
        finally:
            for worker in workers: worker.join(13)


def test_real_legacy14_component_sender_close_uncertainty_preserves_unknown_debt(current14, monkeypatch):
    from research.source_spawn import SourceSpawnProcess, SourceCleanupUncertain
    client, store, rid = current14
    tid = new_task(client, rid)
    actual_close = SourceSpawnProcess.close
    with source_server() as (port, calls):
        with monkeypatch.context() as fault:
            def uncertain(process):
                actual_close(process)
                raise SourceCleanupUncertain('component acknowledged close uncertainty')
            fault.setattr(SourceSpawnProcess, 'close', uncertain)
            with pytest.raises(SourceCleanupUncertain):
                ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(get_local, port))).run_once(tid)
        assert calls == ['/discovery']
        with store.transaction() as conn:
            before = dict(conn.execute('SELECT * FROM research_source_requests WHERE task_id=?', (tid,)).fetchone())
        assert (before['outcome'], before['execution_closed']) == ('UNKNOWN', 0)
        _assert_current_selector_rejects_legacy14(store)
        with AuthorizationGate(store).source_task_gate(tid) as lease:
            # The original close-uncertain run has not become terminal. This
            # is a fresh native task lease, not a fabricated cleanup-only one.
            assert lease.cleanup is False
            source_workflow.close_interrupted(store, tid, lease)
        assert calls == ['/discovery']
        with store.transaction() as conn:
            after = dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?', (before['id'],)).fetchone())
            assert (after['outcome'], after['execution_closed']) == ('UNKNOWN', 1)
            assert after['closure_ref'] and after['closure_proof']
            assert (after['started_at'], after['ended_at']) == (before['started_at'], before['ended_at'])
            assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0] == 1


def _source_arena_fds():
    """Observe current process FDs only; never close or alter an arena."""
    directory = Path('/proc/self/fd') if Path('/proc/self/fd').is_dir() else Path('/dev/fd')
    found = set()
    for name in os.listdir(directory):
        if not name.isdecimal():continue
        fd = int(name)
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_size != 4194304:continue
            try:path = os.readlink(directory / name)
            except OSError:
                path = fcntl.fcntl(fd, fcntl.F_GETPATH, b'\0' * 1024).split(b'\0', 1)[0].decode()
        except (OSError, AttributeError):continue
        if '/pymp-' in path:found.add((fd, info.st_dev, info.st_ino))
    return found


@pytest.mark.parametrize('outcome', ['completed', 'lost-ack', 'sender-exec-failure'])
def test_handled_source_return_releases_own_arena_without_gc(current14, monkeypatch, outcome):
    from research import source_spawn
    client, store, rid = current14
    tid = new_task(client, rid)
    if outcome == 'sender-exec-failure':
        execute = source_spawn._exec
        def fail_sender(command, descriptors):
            if len(descriptors) > 1:raise OSError('synthetic sender exec failure')
            return execute(command, descriptors)
        monkeypatch.setattr(source_spawn, '_exec', fail_sender)
    gc.collect();enabled = gc.isenabled();gc.disable()
    before = _source_arena_fds()
    try:
        with source_server() as (port, calls):
            worker = drop_after_response if outcome == 'lost-ack' else get_local
            result = ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(worker, port))).run_once(tid)
            after_return = _source_arena_fds()
            with store.transaction() as conn:
                requests = [tuple(row) for row in conn.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=? ORDER BY ordinal', (tid,))]
            if outcome == 'completed':
                assert result == 'COMPLETED' and calls == ['/discovery', '/article']
                assert requests == [('SUCCEEDED', 0), ('SUCCEEDED', 0)]
            else:
                assert result == 'FAILED' and requests == [('UNKNOWN', 1)]
                assert calls == (['/discovery'] if outcome == 'lost-ack' else [])
            assert after_return == before, 'handled Source return retained its own arena FD until GC'
    finally:
        if enabled:gc.enable()
        gc.collect()  # Restore ordinary test cleanup, never production retirement.


def test_uncertain_source_close_keeps_own_buffer_and_original_handle_evidence(current14, monkeypatch):
    from research.source_spawn import SourceSpawnProcess, SourceCleanupUncertain
    from multiprocessing.heap import Arena, BufferWrapper
    import sys
    client, store, rid = current14
    tid = new_task(client, rid)
    actual_close = SourceSpawnProcess.close
    gc.collect();enabled = gc.isenabled();gc.disable()
    observed = {};failure = frame = shared = view = process = wrapper = arena = None
    try:
        with source_server() as (port, calls):
            with monkeypatch.context() as fault:
                def uncertain(process):
                    caller = sys._getframe(1)
                    assert caller.f_code is PinnedPublicTransport.get.__code__
                    assert caller.f_globals is PinnedPublicTransport.get.__globals__
                    shared = caller.f_locals['shared'];view = caller.f_locals['view']
                    wrapper = shared._wrapper
                    assert type(wrapper) is BufferWrapper
                    (arena, start, stop), size = wrapper._state
                    assert type(arena) is Arena and type(arena.fd) is int
                    info = os.fstat(arena.fd)
                    assert stat.S_ISREG(info.st_mode) and not observed
                    observed.update(shared=id(shared), view=id(view), process=id(process),
                                    wrapper=id(wrapper), arena=id(arena), fd=arena.fd,
                                    fd_identity=(info.st_dev, info.st_ino, info.st_mode, info.st_size),
                                    block=(start, stop, size), arena_size=arena.size)
                    # Only primitive identity evidence survives this callback;
                    # extra subject references must not retain the buffer.
                    del caller, shared, view, wrapper, arena
                    actual_close(process)
                    raise SourceCleanupUncertain('synthetic post-close observation uncertainty')
                fault.setattr(SourceSpawnProcess, 'close', uncertain)
                with pytest.raises(SourceCleanupUncertain) as failure:
                    ResearchRunner(store, source_transport=PinnedPublicTransport(_worker=partial(get_local, port))).run_once(tid)
            traceback = failure.value.__traceback__
            while traceback is not None:
                if traceback.tb_frame.f_code is PinnedPublicTransport.get.__code__:frame = traceback.tb_frame
                traceback = traceback.tb_next
            assert frame is not None and frame.f_locals['shared'] is not None
            assert frame.f_locals['view'] is not None and frame.f_locals['process'] is not None
            shared = frame.f_locals['shared'];view = frame.f_locals['view'];process = frame.f_locals['process']
            assert (id(shared), id(view), id(process)) == (observed['shared'], observed['view'], observed['process'])
            wrapper = shared._wrapper
            (arena, start, stop), size = wrapper._state
            assert type(wrapper) is BufferWrapper and type(arena) is Arena
            assert (id(wrapper), id(arena), arena.fd) == (observed['wrapper'], observed['arena'], observed['fd'])
            assert (start, stop, size) == observed['block'] and arena.size == observed['arena_size']
            assert view.obj is shared and view.nbytes == len(shared) == size
            assert 0 <= start < stop <= arena.size and stop - start >= size
            info = os.fstat(arena.fd)
            assert (info.st_dev, info.st_ino, info.st_mode, info.st_size) == observed['fd_identity']
            assert calls == ['/discovery']
            with store.transaction() as conn:
                assert tuple(conn.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=?', (tid,)).fetchone()) == ('UNKNOWN', 0)
            with AuthorizationGate(store).source_task_gate(tid) as lease:
                source_workflow.close_interrupted(store, tid, lease)
            assert calls == ['/discovery']
    finally:
        # The fault performed real physical retirement; fresh DB closure above
        # is separate from the intentionally uncertain caller observation.
        # Release test-owned exception references only, then ordinary GC.
        failure = frame = shared = view = process = wrapper = arena = None
        if enabled:gc.enable()
        gc.collect()


@pytest.mark.parametrize('policy', ['native', 'funded'])
def test_core_paid_preview_requires_genuine_http_source(stack, policy):
    # This proves the producer boundary only. A real queued native/funded
    # side-task selector control is deferred to 07's actual Main composition.
    from api import auth
    from .test_private_registration import link, verify
    from .test_research_paid_producers import identity
    from .test_research_persistence import problem
    from research.schemas import CreateResearchRequest
    from research.plan_schemas import PlanPreviewRequest
    from research import plan_native_runtime, plan_runtime
    client, _, mail = stack
    assert verify(client, link(client, mail)).status_code == 200
    actor = identity(client)
    store = ResearchStore(auth._store());service = ResearchService(store)
    value = problem();value['confirmed'] = True
    made = service.create(actor, CreateResearchRequest.model_validate({'problem': value}), 'source-core-save')
    rid = made['data']['research']['id']
    request = PlanPreviewRequest(input_revision=1, expected_research_version=1,
                                observation_source='own_observation', declaration_status='self_declared')
    runtime = plan_native_runtime if policy == 'native' else plan_runtime
    with pytest.raises(PermissionError, match='verified action source missing or stale'):
        runtime.preview(service, actor, rid, request, 'no-invented-http-source', None)
    with store.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0] == 0


def test_retire_after_last_auth_before_g_prevents_handoff(component):
    supervisor, session, guard = component
    # This is the memory/G component after original ACL has already returned.
    control.retire(supervisor, deadline_monotonic=time.monotonic() + 1)
    calls = []
    with pytest.raises(PermissionError):
        with guard.handoff_scope(session, session.transport, deadline_monotonic=time.monotonic() + 1):
            calls.append('handoff')
    assert calls == [] and supervisor._state == 'STOPPING'


def test_handoff_in_g_retirement_waits_for_exit(component):
    supervisor, session, guard = component
    entered, release, retired = threading.Event(), threading.Event(), threading.Event()
    failures = []
    def sender():
        try:
            with guard.handoff_scope(session, session.transport, deadline_monotonic=time.monotonic() + 2):
                entered.set()
                assert release.wait(2)
        except BaseException as error:
            failures.append(type(error).__name__)
    worker = threading.Thread(target=sender)
    supervisor._thread = guard._thread = worker
    worker.start()
    assert entered.wait(1)
    def stopping():
        try:
            control.retire(supervisor, deadline_monotonic=time.monotonic() + 1)
            retired.set()
        except BaseException as error:
            failures.append(type(error).__name__)
    stopper = threading.Thread(target=stopping)
    try:
        stopper.start()
        assert supervisor._stop.wait(1)
        assert not retired.wait(.04)
        release.set()
        stopper.join(1)
        worker.join(1)
        assert retired.is_set() and failures == [] and supervisor._state == 'STOPPING'
    finally:
        release.set()
        worker.join(2)
        stopper.join(2)


def test_blocked_handoff_deadline_preserves_actual_handle_and_uncertainty(component):
    supervisor, session, guard = component
    entered, release = threading.Event(), threading.Event()
    failures = []
    def sender():
        try:
            with guard.handoff_scope(session, session.transport, deadline_monotonic=time.monotonic() + 2):
                entered.set()
                release.wait(2)
        except BaseException as error:
            failures.append(type(error).__name__)
    worker = threading.Thread(target=sender)
    supervisor._thread = guard._thread = worker
    worker.start()
    deadline = time.monotonic() + .08
    try:
        assert entered.wait(1)
        with pytest.raises(control.SourceRetirementUncertain) as outcome:
            control.retire(supervisor, deadline_monotonic=deadline)
        assert outcome.value.supervisor is supervisor
        receipt = control.join(supervisor, deadline_monotonic=deadline)
        assert receipt.state == 'CLEANUP_UNCERTAIN' and receipt.pending_task_id == session.task_id
        assert receipt.supervisor_ref == supervisor.reference
        assert control._REGISTRY[id(supervisor._binding.app)] is supervisor
        assert worker.is_alive() and not failures
    finally:
        release.set()
        worker.join(2)


@pytest.mark.parametrize('fault', ['pid', 'thread', 'task', 'epoch', 'session', 'transport', 'registry'])
def test_old_or_wrong_slot_guard_cannot_handoff(component, fault):
    supervisor, session, guard = component
    if fault == 'pid': guard._pid = -1
    if fault == 'thread': guard._thread = threading.Thread()
    if fault == 'task': guard._task_id = str(uuid4())
    if fault == 'epoch': supervisor._slot_epoch += 1
    if fault == 'session': supervisor._session = object()
    if fault == 'transport': session.transport = PinnedPublicTransport()
    if fault == 'registry': control._REGISTRY.clear()
    called = []
    with pytest.raises(PermissionError):
        with guard.handoff_scope(session, session.transport, deadline_monotonic=time.monotonic() + 1):
            called.append(True)
    assert called == []


def test_callback_and_dto_cannot_replace_formal_session(monkeypatch):
    monkeypatch.setenv('STRUCTURAL_ENV', 'prod')
    def callback():
        raise AssertionError('identity anchor must never be called inside G')
    for candidate in (callback, SimpleNamespace(still_authorized=callback)):
        with pytest.raises(PermissionError):
            with control.send_handoff_scope(candidate, deadline_monotonic=time.monotonic() + 1):
                raise AssertionError('formal dispatch must stay closed')


@pytest.mark.parametrize('deadline', [True, False, float('nan'), float('inf'), -1, 0])
def test_absolute_deadline_rejects_invalid_and_bool(component, deadline):
    supervisor, _, _ = component
    with pytest.raises(ValueError):
        control.retire(supervisor, deadline_monotonic=deadline)
    assert not supervisor._stop.is_set()


def test_cleanup_deadline_cannot_be_reset_or_extended(component):
    supervisor, _, _ = component
    deadline = time.monotonic() + 1
    control.retire(supervisor, deadline_monotonic=deadline)
    with pytest.raises(ValueError, match='cannot be extended'):
        control.join(supervisor, deadline_monotonic=deadline + 20)


def test_exited_thread_and_unknown_close_are_not_closed_receipt(component):
    supervisor, _, _ = component
    worker = threading.Thread(target=lambda: None)
    supervisor._thread = worker
    worker.start();worker.join(1)
    supervisor._failure = 'CLOSE_UNCERTAIN'
    receipt = control.join(supervisor, deadline_monotonic=time.monotonic() + 1)
    assert receipt.state == 'CLEANUP_UNCERTAIN' and receipt.reason == 'CLOSE_UNCERTAIN'
    assert control._REGISTRY[id(supervisor._binding.app)] is supervisor


def test_source10_plan12_and_both_old13_reconstruct_from_no_git_closure(tmp_path):
    from . import source_v10_reference, plan_v12_reference, method_v13_reference
    root = Path(__file__).resolve().parents[3]
    shallow = tmp_path / 'shallow'
    required = {'web/backend/tests/reference/method_v13/deltas.json'}
    for family in ('source_v10', 'plan_v12', 'method_v13'):
        directory = 'web/backend/tests/reference/' + family
        reference = root / directory
        required.update(path.relative_to(root).as_posix() for path in reference.rglob('*') if path.is_file())
        manifest = json.loads((reference / 'manifest.json').read_text())
        groups = manifest['cases'].values() if family == 'method_v13' else (manifest,)
        for group in groups:
            required.update(name for name, entry in group['files'].items()
                            if family == 'method_v13' or entry['source'] == 'current_exact')
    for name in required:
        source, destination = root / name, shallow / name
        assert source.is_file() and not source.is_symlink()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())
    for family, loader in (('source_v10', source_v10_reference), ('plan_v12', plan_v12_reference)):
        package, _, manifest_path = loader.reconstruct(shallow, tmp_path / family)
        manifest = json.loads(manifest_path.read_text())['files']
        assert {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in manifest} == {name: entry['sha256'] for name, entry in manifest.items()}
    for mode in ('native', 'fixture'):
        package, manifest_path = method_v13_reference.reconstruct(shallow, tmp_path / ('old13-' + mode), mode)
        manifest = json.loads(manifest_path.read_text())['cases'][mode]['files']
        assert {name: hashlib.sha256((package / name).read_bytes()).hexdigest() for name in manifest} == {name: entry['sha256'] for name, entry in manifest.items()}
    assert not (shallow / '.git').exists()


def _stop_signal_specimen(supervisor):
    """Unit metadata specimen only; never an issued Main withdrawal/READY."""
    signal = control._SourceStopping.__new__(control._SourceStopping)
    ResearchError.__init__(signal, 'FEATURE_UNAVAILABLE', 503, 'unit stop specimen')
    signal._factory, signal._supervisor = control._FACTORY, supervisor
    signal._intent, signal._pid = supervisor._source_stop_intent, os.getpid()
    signal._thread, signal._slot = threading.current_thread(), supervisor._slot
    return signal


def test_native_source_retire_intent_is_distinct_from_event_or_main_withdraw(component):
    supervisor, _, _ = component
    supervisor._stop.set()
    assert supervisor._source_stop_intent is supervisor._main_stop_intent is None
    assert not control._controlled_stopping(ResearchError('FEATURE_UNAVAILABLE',503,'ordinary'),supervisor)
    deadline=time.monotonic()+1
    control.retire(supervisor,deadline_monotonic=deadline)
    intent=supervisor._source_stop_intent
    assert control._matching_intent(supervisor,intent,'source-retire')
    assert supervisor._main_stop_intent is None
    control.retire(supervisor,deadline_monotonic=deadline)
    assert supervisor._source_stop_intent is intent
    with pytest.raises(TypeError):intent.kind='main-withdraw'
    with pytest.raises(TypeError):pickle.dumps(intent)
    with pytest.raises(TypeError):control._StopIntent(supervisor,'main-withdraw',_factory=control._FACTORY)


def test_retire_observer_can_call_original_native_controller_without_minting_itself(component,monkeypatch):
    from types import FunctionType
    supervisor, _, _ = component;original=control.retire;observed=[];deadline=time.monotonic()+1
    clone=FunctionType(original.__code__,dict(original.__globals__))
    with pytest.raises(TypeError):clone(supervisor,deadline_monotonic=deadline)
    assert supervisor._source_stop_intent is None and not supervisor._stop.is_set()
    def observer(value,*,deadline_monotonic):
        observed.append(value)
        with pytest.raises(TypeError):control._StopIntent(value,'source-retire',_factory=control._FACTORY)
        return original(value,deadline_monotonic=deadline_monotonic)
    monkeypatch.setattr(control,'retire',observer)
    control.retire(supervisor,deadline_monotonic=deadline)
    assert observed==[supervisor] and control._matching_intent(supervisor,supervisor._source_stop_intent,'source-retire')


@pytest.mark.parametrize('fault',['caller','binding','pid','reference'])
def test_request_main_stop_cannot_be_called_from_component_or_foreign_binding(component,fault):
    supervisor, _, _ = component;binding=supervisor._binding
    if fault=='binding':binding=SimpleNamespace(app=binding.app,reference=binding.reference)
    if fault=='pid':supervisor._pid=-1
    if fault=='reference':supervisor._binding_reference='different'
    with pytest.raises((RuntimeError,ResearchError)):
        control.request_main_stop(supervisor,binding)
    assert not supervisor._stop.is_set() and supervisor._main_stop_intent is None


@pytest.mark.parametrize('fault',['factory','pid','thread','slot','intent','supervisor','missing'])
def test_stop_signal_metadata_cannot_launder_wrong_actor_slot_or_intent(component,fault):
    supervisor, _, _ = component
    control.retire(supervisor,deadline_monotonic=time.monotonic()+1)
    signal=_stop_signal_specimen(supervisor)
    # Metadata classification only: the specimen has no real Main admission.
    assert control._controlled_stopping(signal,supervisor)
    if fault=='factory':signal._factory=object()
    if fault=='pid':signal._pid=-1
    if fault=='thread':signal._thread=threading.Thread()
    if fault=='slot':signal._slot=str(uuid4())
    if fault=='intent':signal._intent={'kind':'source-retire'}
    if fault=='supervisor':signal._supervisor=object()
    if fault=='missing':del signal._pid
    assert not control._controlled_stopping(signal,supervisor)
    with pytest.raises(TypeError):control._SourceStopping(supervisor,supervisor._source_stop_intent,_factory=control._FACTORY)


@pytest.mark.parametrize('native_intent',[False,True])
@pytest.mark.parametrize('kind',['ordinary-feature','config','source','inode','state-missing'])
def test_worker_does_not_hide_ordinary_failure_even_after_stop(component,monkeypatch,native_intent,kind):
    from research import runtime_profile
    supervisor, _, _ = component;supervisor._slot=None
    if native_intent:control.retire(supervisor,deadline_monotonic=time.monotonic()+1)
    else:supervisor._stop.set()
    error=ResearchError('FEATURE_UNAVAILABLE',503,'ordinary') if kind=='ordinary-feature' else RuntimeError('unit '+kind)
    monkeypatch.setattr(runtime_profile,'runtime_capability_facts',lambda service:SimpleNamespace(profile=SimpleNamespace(checked_pid=os.getpid(),research_schema=15)))
    def fail(*args,**kwargs):raise error
    monkeypatch.setattr(control,'_check',fail)
    # Only the error branch is run; this never installs/passes formal READY.
    supervisor._run()
    assert supervisor._state=='CLEANUP_UNCERTAIN' and supervisor._failure=='WORKER_FAILURE'
    assert supervisor._errors[-1] is error


def test_stop_slot_no_claim_uses_actual_task_lease_and_leaves_queued_metadata(component,current14):
    supervisor, _, _ = component;client,store,rid=current14;tid=new_task(client,rid)
    supervisor._slot=tid
    control.retire(supervisor,deadline_monotonic=time.monotonic()+1)
    signal=_stop_signal_specimen(supervisor)
    with AuthorizationGate(store).source_task_gate(tid) as lease:
        supervisor._lease=lease
        control._close_stopping_slot(supervisor,store,tid,lease,signal)
        with store.transaction() as conn:
            assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?',(tid,)).fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM research_source_requests WHERE task_id=?',(tid,)).fetchone()[0]==0
            assert conn.execute('SELECT execution FROM research_tasks WHERE id=?',(tid,)).fetchone()[0]=='QUEUED'
    assert lease.active is False
    with pytest.raises(PermissionError):control._close_stopping_slot(supervisor,store,tid,lease,signal)


def test_stop_slot_terminal_started_debt_uses_original_fresh_closure_without_get(component,current14,monkeypatch):
    supervisor, _, _ = component;client,store,rid=current14;tid=new_task(client,rid)
    with source_server() as (port,calls):
        with monkeypatch.context() as fault:
            def interrupted(*args):raise OSError('unit closure interruption')
            fault.setattr(source_workflow,'close_interrupted',interrupted)
            with pytest.raises(OSError,match='unit closure interruption'):
                ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(drop_after_response,port))).run_once(tid)
        cancel(client,rid,tid);supervisor._slot=tid
        control.retire(supervisor,deadline_monotonic=time.monotonic()+1)
        signal=_stop_signal_specimen(supervisor);operations=[]
        with AuthorizationGate(store).source_task_gate(tid) as lease:
            supervisor._lease=lease;identity=lease.identity
            def cleanup_port(given,actual_store,task_id,*,operation):
                assert given is supervisor and actual_store is store and task_id==tid and lease.active
                operations.append(operation);assert operation=='cleanup'
            # Lifetime port specimen only. Native task/owner/SQL closure below
            # remains the original implementation with actual held resources.
            monkeypatch.setattr(control,'require_worker',cleanup_port)
            control._close_stopping_slot(supervisor,store,tid,lease,signal)
        assert lease.active is False and calls==['/discovery'] and operations==['cleanup']
        with store.transaction() as conn:
            row=conn.execute('SELECT outcome,execution_closed,closure_proof FROM research_source_requests WHERE task_id=?',(tid,)).fetchone()
            assert tuple(row[:2])==('UNKNOWN',1)
            assert tuple(json.loads(row['closure_proof'])['task_gate'])==identity
            assert conn.execute('SELECT execution FROM research_tasks WHERE id=?',(tid,)).fetchone()[0]=='CANCELLED'


def test_generic_feature_or_wrong_slot_never_enters_stop_slot_database(component,monkeypatch):
    supervisor, _, _ = component;store=supervisor._service.store
    control.retire(supervisor,deadline_monotonic=time.monotonic()+1)
    def forbidden(*args,**kwargs):raise AssertionError('untrusted stop must not touch DB')
    monkeypatch.setattr(store,'transaction',forbidden)
    for error in (ResearchError('FEATURE_UNAVAILABLE',503,'ordinary'),_stop_signal_specimen(supervisor)):
        if type(error) is control._SourceStopping:error._slot=str(uuid4())
        with pytest.raises(type(error)) as raised:control._close_stopping_slot(supervisor,store,supervisor._slot,object(),error)
        assert raised.value is error


@pytest.fixture
def memory_withdraw_protocol(component,monkeypatch):
    """Frozen07 withdraw body, isolated memory specimens; no formal READY."""
    import sys,types
    supervisor,_,_=component
    module=types.ModuleType('unit_withdraw_protocol_'+uuid4().hex);module.__file__='<unit-memory-protocol>'
    module._STATE={};module._FACTORY=object();module._Binding=SimpleNamespace
    module._LIFETIME_LOCK=threading.RLock();module._RETIRED_UNCERTAIN={}
    # Exact withdraw body from approved read-only checkpoint 01a87df; the
    # surrounding state/record specimens cannot pass actual Main admission.
    exec('''def withdraw(app):
    """Revoke HTTP before waiting on G; keep local native witnesses alive."""
    with _LIFETIME_LOCK:
        binding = _STATE.get(id(app))
    if binding is None:
        return
    error = None
    if binding.supervisor is not None and not source_closed(binding):
        try:
            if binding.source_module.request_main_stop(binding.supervisor, binding) is not None:
                raise RuntimeError('Main stop coordination returned data')
        except BaseException as failure:
            error = failure
    with _LIFETIME_LOCK:
        if _STATE.get(id(app)) is not binding:
            return None
        binding.withdrawal = _Withdrawal(binding, _factory=_WITHDRAW_FACTORY) if error is None else None
        binding.active, binding.retired = False, True
        _STATE.pop(id(app), None)
    if error is not None:
        _RETIRED_UNCERTAIN[binding.reference] = (binding, binding.supervisor, (error,))
        raise RuntimeError('Main stop coordination uncertain') from None
    return binding
def validate_withdrawal(error,binding):
    raise AssertionError('memory request must never invoke withdrawal validator')
def source_closed(binding):
    return False
def _Withdrawal(binding,*,_factory):
    return 'unit-record-not-a-native-seal'
''',vars(module))
    module._WITHDRAW_FACTORY=object();binding=supervisor._binding
    binding.origin=module.__name__;binding.factory=module._FACTORY;binding.supervisor=supervisor
    binding.source_module=control;binding.active=True;binding.retired=False;binding.withdrawal=None
    module._STATE[id(binding.app)]=binding
    entry=object.__new__(control._MainStopEntry)
    values=dict(factory=control._FACTORY,supervisor=supervisor,supervisor_ref=supervisor.reference,
        binding=binding,reference=binding.reference,pid=os.getpid(),app=binding.app,module=module,
        module_name=module.__name__,module_file=module.__file__,binding_type=SimpleNamespace,
        binding_factory=module._FACTORY,state=module._STATE,withdraw=module.withdraw,
        withdraw_code=module.withdraw.__code__,validate=module.validate_withdrawal,
        validate_code=module.validate_withdrawal.__code__,source_identity=('unit-only',b'not-startup-authority'))
    for key,value in values.items():object.__setattr__(entry,key,value)
    supervisor._main_stop_entry=entry
    monkeypatch.setitem(sys.modules,module.__name__,module)
    return supervisor,binding,module,entry


def test_frozen_withdraw_memory_protocol_sets_intent_without_io_db_owner_or_g(memory_withdraw_protocol,monkeypatch):
    import builtins,io
    from research.authorization import AuthorizationGate
    supervisor,binding,module,entry=memory_withdraw_protocol;traps=[]
    def forbidden(*args,**kwargs):traps.append('unexpected-I/O');raise AssertionError('stop entry must be memory only')
    binding.check=forbidden
    supervisor._dispatch_mutex=SimpleNamespace(acquire=forbidden,release=forbidden,locked=lambda:False)
    with monkeypatch.context() as blocked:
        for cls,name in [(Path,'resolve'),(Path,'read_bytes'),(Path,'is_symlink'),(Path,'stat')]:blocked.setattr(cls,name,forbidden)
        for obj,name in [(builtins,'open'),(builtins,'compile'),(io,'open'),(os,'open'),(sqlite3,'connect'),
                         (os.environ,'get'),(AuthorizationGate,'owner_gate_id'),(AuthorizationGate,'source_task_gate')]:blocked.setattr(obj,name,forbidden)
        result=module.withdraw(binding.app)
    assert result is binding and traps==[] and supervisor._stop.is_set() and supervisor._event.is_set()
    assert control._matching_intent(supervisor,supervisor._main_stop_intent,'main-withdraw')
    assert supervisor._source_stop_intent is None and supervisor._state=='READY'
    assert entry.supervisor is supervisor and entry.binding is binding
    with pytest.raises(TypeError):entry.pid=-1
    with pytest.raises(TypeError):pickle.dumps(entry)
    # State is a test specimen: this asserts no normal retirement/READY proof.
    with pytest.raises(ResearchError):control.require_available(binding.app,supervisor._service)


@pytest.mark.parametrize('fault',['caller','function','reference','pid','app','registry'])
def test_frozen_stop_entry_rejects_stale_memory_identity_without_io(memory_withdraw_protocol,monkeypatch,fault):
    supervisor,binding,module,entry=memory_withdraw_protocol
    if fault=='function':module.withdraw=lambda app:None
    if fault=='reference':binding.reference='changed'
    if fault=='pid':binding.pid=-1
    if fault=='app':binding.app=FastAPI()
    if fault=='registry':control._REGISTRY.clear()
    def forbidden(*args,**kwargs):raise AssertionError('rejected stop must not read source')
    with monkeypatch.context() as blocked:
        blocked.setattr(Path,'resolve',forbidden);blocked.setattr(Path,'read_bytes',forbidden)
        with pytest.raises((RuntimeError,ResearchError)):control.request_main_stop(supervisor,binding)
    assert supervisor._main_stop_intent is None and not supervisor._stop.is_set()
