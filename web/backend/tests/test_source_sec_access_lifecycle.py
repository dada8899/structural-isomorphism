"""Actual Main15 native consumers; only owned files and negative fault controls.

No registry/factory/permit/availability replacement. SEC and all public Source
GETs remain forbidden. The wait scheduling shim runs the real negative pacing
port on the real idle Source worker, before it owns a slot or transaction.
"""
import asyncio
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import (BETA, envelope, login, prepared, problem, smtp)
from web.backend.tests.test_formal_main_source_supervisor import ready, create, approved_source, _actual_main15_debt_recovery


def provision_lock(paths):
    lock = paths.STATE_ROOT / 'source-sec-access.lock'
    lock.touch(mode=0o600)
    return lock


def test_actual_main_missing_optional_file_keeps_basic_history_and_paper(prepared):
    main, admission, paths, messages = prepared
    async def run():
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            governor = binding.supervisor._sec_access
            assert governor.state == 'UNBOUND' and governor.fd is None
            for capability in ('research_basic', 'source_history', 'source_execute'):
                assert admission.require(main.app, capability) is None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages)
                rid = await create(client)
                assert await approved_source(client, rid)
                assert (await client.get('/api/research/' + rid)).status_code == 200
        assert binding.source_receipt.state == 'CLOSED'
        assert governor.state == 'CLOSED' and not (paths.STATE_ROOT / 'source-sec-access.lock').exists()
    asyncio.run(run())


def test_actual_main_native_birth_rechecks_and_closes_own_fd_only(prepared):
    main, admission, paths, _ = prepared
    lock = provision_lock(paths)
    async def run():
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            source = binding.source_module
            sec = __import__(source.__package__ + '.source_sec_access', fromlist=['attach'])
            governor = binding.supervisor._sec_access
            assert governor.context is binding.native_context and governor.binding is binding
            assert governor.state == 'COOLDOWN' and governor.cadence.next_due is not None
            assert os.fstat(governor.fd).st_ino == lock.stat().st_ino
            assert not os.get_inheritable(governor.fd)
            fd = governor.fd
            assert sec._held(governor) is None
            with pytest.raises(RuntimeError): sec.cleanup_completed(governor)
            with pytest.raises(PermissionError): sec.wait_before_claim(governor)
            with pytest.raises(PermissionError): sec.begin_request(governor, None, None)
            with pytest.raises(PermissionError): sec.finish_request(object(), True)
            with pytest.raises(TypeError): sec.attach(binding.supervisor)
        assert binding.source_receipt.state == 'CLOSED'
        assert governor.state == 'CLOSED' and governor.fd is None
        with pytest.raises(OSError): os.fstat(fd)
        assert all(w.parent_fd is None for w in binding.witnesses)
        print('SEC_NATIVE_LIFECYCLE:' + json.dumps({'bound_to_actual_main': True,
            'own_fd_closed': True, 'auth_parent_closed_by_main': True, 'get_count': 0}))
    asyncio.run(run())


@pytest.mark.parametrize('bad', ['symlink', 'hardlink', 'mode'])
def test_actual_main_optional_bad_metadata_never_disables_paper(prepared, bad):
    main, admission, paths, _ = prepared
    lock = provision_lock(paths)
    if bad == 'mode': lock.chmod(0o640)
    elif bad == 'hardlink': os.link(lock, lock.with_name('owned-link'))
    else:
        target = lock.with_name('owned-target'); lock.rename(target); lock.symlink_to(target)
    async def run():
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            governor = binding.supervisor._sec_access
            assert governor.state == 'UNBOUND' and governor.fd is None
            assert admission.require(main.app, 'source_execute') is None
        assert binding.source_receipt.state == 'CLOSED'
    asyncio.run(run())


def test_actual_main_flock_excludes_second_independent_process(prepared):
    main, admission, paths, _ = prepared
    lock = provision_lock(paths)
    # The peer only opens this test's owned fixed file. Its result is a real
    # kernel flock, never a synthesized native governor or Main context.
    peer = """import fcntl,os,sys
fd=os.open(sys.argv[1],os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
try:
 try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:print('CONTENDED')
 else:print('ACQUIRED')
finally:os.close(fd)
"""
    def observe():
        return subprocess.run([sys.executable, '-B', '-c', peer, str(lock)],
            capture_output=True, text=True, check=True, timeout=5).stdout.strip()
    async def run():
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            assert binding.supervisor._sec_access.fd is not None
            assert observe() == 'CONTENDED'
        assert binding.source_receipt.state == 'CLOSED'
        assert observe() == 'ACQUIRED'
    asyncio.run(run())


def test_real_source_wait_is_outside_locks_stop_wakes_and_claims_nothing(prepared, monkeypatch):
    main, admission, paths, _ = prepared
    provision_lock(paths)
    entered = threading.Event()
    facts = []
    original_wait = threading.Event.wait
    used = False
    def schedule_wait(event, timeout=None):
        nonlocal used
        binding = admission._STATE.get(id(main.app))
        supervisor = binding.supervisor if binding is not None else None
        # The genuine worker's idle wait, after its real empty cleanup scan.
        if (not used and supervisor is not None and event is supervisor._event
                and threading.current_thread() is supervisor._thread
                and supervisor._state == 'READY' and supervisor._sec_access.state == 'COOLDOWN'):
            used = True
            sec = __import__(supervisor.__class__.__module__.rsplit('.', 1)[0] + '.source_sec_access', fromlist=['wait_before_claim'])
            facts.append((supervisor._slot, supervisor._lease, supervisor._lock._is_owned()))
            entered.set()
            return sec.wait_before_claim(supervisor._sec_access)
        return original_wait(event, timeout)
    monkeypatch.setattr(threading.Event, 'wait', schedule_wait)
    async def run():
        context = main.lifespan(main.app)
        await context.__aenter__()
        binding = admission._STATE[id(main.app)]
        try:
            end = time.monotonic() + 4
            while not entered.is_set() and time.monotonic() < end: await asyncio.sleep(.01)
            assert entered.is_set() and facts == [(None, None, False)]
            started = time.monotonic()
        finally:
            await context.__aexit__(None, None, None)
        assert time.monotonic()-started < 2
        assert binding.source_receipt.state == 'CLOSED'
        assert binding.supervisor._slot is None
        with binding.service.store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
        print('SEC_STOP_WAIT:' + json.dumps({'actual_worker': True, 'locks_owned': False,
            'claimed': 0, 'requests': 0, 'public_gets': 0, 'closed': True}))
    asyncio.run(run())


def test_real_terminal_debt_blocks_cooldown_until_native_cleanup_finishes(prepared, tmp_path, monkeypatch):
    main, admission, paths, _ = prepared
    provision_lock(paths)
    from research import authorization
    native_flock = fcntl.flock
    task_code = authorization._source_task_gate.__wrapped__.__code__
    held, release = threading.Event(), threading.Event()
    observed, released_at, errors = [], [], []
    def hold_actual_cleanup(descriptor, operation):
        result = native_flock(descriptor, operation)
        source = __import__('research.source_supervisor', fromlist=['_REGISTRY'])
        supervisor = source._REGISTRY.get(id(main.app))
        # The reused recovery helper has its own transparent flock observer.
        # Locate the original gate below both observers rather than requiring
        # this observer to be directly adjacent to the kernel primitive.
        frame = sys._getframe(1)
        task_gate = False
        while frame is not None:
            if frame.f_code is task_code:
                task_gate = True
                break
            frame = frame.f_back
        del frame
        if (not observed and supervisor is not None and threading.current_thread() is supervisor._thread
                and task_gate and supervisor._state == 'STARTING'
                and operation == fcntl.LOCK_EX | fcntl.LOCK_NB):
            governor = supervisor._sec_access
            assert governor.state == 'HELD_CLEANUP' and governor.cadence.next_due is None
            observed.append(governor); held.set()
            if not release.wait(4): raise TimeoutError('owned cleanup observation expired')
        return result
    def observer():
        try:
            assert held.wait(25)
            governor = observed[0]
            time.sleep(1.05)  # Longer than cadence; debt closure, not age, starts it.
            assert governor.state == 'HELD_CLEANUP' and governor.cadence.next_due is None
        except BaseException as error: errors.append(error)
        finally:
            released_at.append(time.monotonic()); release.set()
    monkeypatch.setattr(fcntl, 'flock', hold_actual_cleanup)
    thread = threading.Thread(target=observer, name='owned-sec-cleanup-observer')
    thread.start()
    try:
        # Original actual Main15 producer leaves genuine terminal UNKNOWN debt
        # before SCM, and its fresh Main proves task/Owner closure and no refetch.
        _actual_main15_debt_recovery(prepared, tmp_path, monkeypatch, 'terminal-unknown')
        assert observed and not errors
        governor = observed[0]
        assert governor.cadence.next_due >= released_at[0] + 1.
        assert governor.state == 'CLOSED' and governor.fd is None
        print('SEC_REAL_DEBT:' + json.dumps({'terminal_unknown': True,
            'actual_native_cleanup': True, 'no_cooldown_while_debt_held': True,
            'cooldown_after_real_closure_seconds': 1., 'get_count': 0}))
    finally:
        release.set(); thread.join(26)
        assert not thread.is_alive()


@pytest.mark.parametrize('fault', ['replace', 'close-before', 'close-after', 'checkpoint-mode', 'checkpoint-event'])
def test_actual_main_uncertain_owned_fd_never_returns_closed(request, tmp_path, monkeypatch, fault):
    # Each uncertainty control owns a fresh process. Logical uncertain records
    # are deliberately retained until that process exits; no registry reset or
    # false CLOSED is used to make another Main lifetime possible.
    if os.environ.get('SEC_LIFECYCLE_FAULT_CHILD') != fault:
        owned = tmp_path / fault; owned.mkdir(mode=0o700)
        home = owned / 'home'; home.mkdir(mode=0o700)
        guard = sys.modules.get('main_smtp_task_guard')
        assert guard is not None, 'run this control with the approved owned Main guard'
        packet = Path(guard.__file__).resolve().parent
        environment = {name: os.environ[name] for name in ('PATH', 'PYTHONPATH', 'REVIEW_SOURCE_ROOT')}
        environment.update(HOME=str(home), TMPDIR=str(owned), A006_AUDIT_ROOT=str(owned),
            PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',
            STRUCTURAL_ENV='test', AUTH_ENABLED='false', AUTH_DATA_DIR=str(owned/'auth'),
            STRUCTURAL_LOG_FILE=str(owned/'bootstrap.jsonl'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
            SEC_LIFECYCLE_FAULT_CHILD=fault)
        target = str(Path(__file__).resolve()) + '::test_actual_main_uncertain_owned_fd_never_returns_closed[' + fault + ']'
        result = subprocess.run([sys.executable, '-B', str(packet/'run_tests.py'),
            '-p', 'controller_mail_observer', '-p', 'a_evidence_resource_observer',
            target, '--basetemp='+str(owned/'cases'), '--junitxml='+str(owned/'result.xml')],
            cwd=owned, env=environment, capture_output=True, timeout=25)
        (owned/'result.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode == 0, 'owned uncertainty child failed; retain result.log'
        assert b'SEC_UNCERTAIN_RESOURCE:' in result.stdout
        return
    prepared = request.getfixturevalue('prepared')
    main, admission, paths, _ = prepared
    lock = provision_lock(paths)
    original_close = os.close
    captured, failures = [], []
    old_trace = threading.gettrace()
    if fault in ('checkpoint-mode', 'checkpoint-event'):
        sourcepath = Path(main.__file__).parent / 'research/source_supervisor.py'
        checkpoint_line = next(i for i, line in enumerate(sourcepath.read_text().splitlines(), 1)
            if 'cleanup_completed(self._sec_access)' in line)
        def damage_at_real_checkpoint(frame, event, argument):
            if (not failures and event == 'line' and frame.f_code.co_filename == str(sourcepath)
                    and frame.f_lineno == checkpoint_line):
                supervisor = frame.f_locals['self']
                assert not supervisor._stop.is_set() and supervisor._slot is None
                if fault == 'checkpoint-mode':
                    lock.chmod(0o640)  # Owned physical failure, no logical substitution.
                else:
                    # Negative fault: the actual Event is not sealed native
                    # stop provenance and must remain WORKER_FAILURE.
                    supervisor._stop.set()
                failures.append(True)
            return damage_at_real_checkpoint
        threading.settrace(damage_at_real_checkpoint)
    async def run():
        context = main.lifespan(main.app)
        await context.__aenter__()
        if fault in ('checkpoint-mode', 'checkpoint-event'):
            binding = admission._STATE[id(main.app)]
            end = time.monotonic() + 4
            while binding.supervisor._thread.is_alive() and time.monotonic() < end: await asyncio.sleep(.01)
            assert failures and not binding.supervisor._thread.is_alive()
            assert binding.supervisor._stop.is_set() == (fault == 'checkpoint-event')
            assert binding.supervisor._failure == 'WORKER_FAILURE'
        else:
            binding = await ready(main, admission)
        governor = binding.supervisor._sec_access
        descriptor = governor.fd
        captured.extend([binding, governor, descriptor])
        if fault == 'replace':
            lock.rename(lock.with_name('owned-original-lock')); provision_lock(paths)
        elif fault not in ('checkpoint-mode', 'checkpoint-event'):
            def fail_close(fd):
                if fd == descriptor and not failures:
                    failures.append(True)
                    if fault == 'close-after': original_close(fd)
                    raise OSError('owned indeterminate SEC close')
                return original_close(fd)
            monkeypatch.setattr(os, 'close', fail_close)
        # Main correctly reports incomplete resource retirement as an error.
        with pytest.raises(RuntimeError): await context.__aexit__(None, None, None)
        assert binding.source_receipt.state == 'CLEANUP_UNCERTAIN'
        assert governor.state == ('RETIRED' if fault == 'checkpoint-event' else 'CLEANUP_UNCERTAIN')
        assert governor.fd == descriptor
        assert not binding.supervisor._thread.is_alive()
        assert any(w.parent_fd is not None for w in binding.witnesses)
        if fault != 'close-after': assert os.fstat(descriptor).st_ino == governor.identity[1]
        else:
            with pytest.raises(OSError): os.fstat(descriptor)
        print('SEC_UNCERTAIN_RESOURCE:' + json.dumps({'fault': fault, 'actual_handle_retained': True,
            'join': binding.source_receipt.state, 'worker_stopped': True,
            'physical_fd_still_open': fault != 'close-after', 'uncertain_close_not_retried': True}))
    try: asyncio.run(run())
    finally:
        # Explicit physical test teardown only; no forged logical CLOSED.
        threading.settrace(old_trace)
        monkeypatch.setattr(os, 'close', original_close)
        if captured:
            binding, governor, descriptor = captured
            if fault != 'close-after': original_close(descriptor)
            for witness in binding.witnesses:
                if witness.parent_fd is not None: witness.close()


def test_actual_main_stop_between_cleanup_check_and_checkpoint_is_clean(prepared):
    """Native trace barrier reproduces DOC-GOV-STOP-01 without a fake stop."""
    main, admission, paths, _ = prepared
    provision_lock(paths)
    entered, released = threading.Event(), threading.Event()
    seen, observer_errors, captured = [], [], []
    sourcepath = Path(main.__file__).parent / 'research/source_supervisor.py'
    checkpoint_line = next(i for i, line in enumerate(sourcepath.read_text().splitlines(), 1)
        if 'cleanup_completed(self._sec_access)' in line)
    def trace(frame, event, argument):
        if (not seen and event == 'line' and frame.f_code.co_filename == str(sourcepath)
                and frame.f_lineno == checkpoint_line):
            seen.append(frame.f_locals['self']); entered.set()
            if not released.wait(5): raise TimeoutError('owned checkpoint barrier expired')
        return trace
    def release_after_native_stop():
        try:
            assert entered.wait(5)
            assert seen[0]._stop.wait(5)
        except BaseException as error: observer_errors.append(error)
        finally: released.set()
    old_trace = threading.gettrace(); threading.settrace(trace)
    observer = threading.Thread(target=release_after_native_stop, name='owned-sec-checkpoint-stop-observer')
    observer.start()
    async def run():
        context = main.lifespan(main.app); await context.__aenter__()
        binding = admission._STATE[id(main.app)]; captured.append(binding)
        end = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < end: await asyncio.sleep(.01)
        assert entered.is_set()
        await context.__aexit__(None, None, None)
        assert binding.source_receipt.state == 'CLOSED' and binding.supervisor._failure is None
        assert not binding.supervisor._thread.is_alive() and binding.supervisor._slot is None
        assert binding.supervisor._sec_access.fd is None
        assert not observer_errors
        print('SEC_CHECKPOINT_STOP:' + json.dumps({'receipt': 'CLOSED', 'worker_failure': None,
            'slot': None, 'public_gets': 0, 'actual_main_withdrawal': True}))
    try: asyncio.run(run())
    finally:
        released.set(); threading.settrace(old_trace); observer.join(6)
        assert not observer.is_alive()
        # Physical teardown if a future regression fails; never forge CLOSED.
        for binding in captured:
            assert not binding.supervisor._thread.is_alive()
            if binding.supervisor._sec_access.fd is not None: os.close(binding.supervisor._sec_access.fd)
            for witness in binding.witnesses:
                if witness.parent_fd is not None: witness.close()
