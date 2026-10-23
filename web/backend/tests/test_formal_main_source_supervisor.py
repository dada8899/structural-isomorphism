"""Actual Main integration; local primitives never deliver a public GET/body.

No admission/enabled/worker/state substitutions. The flock barrier runs only
after the actual Source task mutex has been acquired, before any send permit.
"""
import asyncio
from contextlib import contextmanager, asynccontextmanager
import fcntl
import inspect
import os
from pathlib import Path
import subprocess
import sys
import select
import signal
import json
import threading
import time

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import (BETA, envelope, login, prepared, problem, smtp)


async def ready(main, admission):
    end = time.monotonic() + 8
    while True:
        try:
            admission.require(main.app, 'source_execute')
            return admission._STATE[id(main.app)]
        except RuntimeError:
            if time.monotonic() >= end:
                raise AssertionError('actual Main Source never became available') from None
            await asyncio.sleep(.02)


async def create(client):
    response = await client.post('/api/research', json=envelope({'problem': problem()}),
        headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-create'})
    assert response.status_code == 200, response.text
    return response.json()['data']['research']['id']


async def approved_source(client, rid):
    base = '/api/research/' + rid
    query = {'input_revision': 1, 'expected_research_version': 1, 'query': 'queue variability'}
    response = await client.post(base + '/source-preview', json=envelope(query),
        headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-preview'})
    assert response.status_code == 200, response.text
    preview = response.json()['data']
    response = await client.post(base + '/source-approvals', json=envelope({**query,
        'preview_digest': preview['preview_digest'], 'confirm_external': True}),
        headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-approve'})
    assert response.status_code == 200, response.text
    return response.json()['data']['approval_ref']


@asynccontextmanager
async def published_source_retirement(main, admission):
    """A separate legitimate sub-lifetime; not a withdrawal-race control."""
    async with main.lifespan(main.app):
        binding = await ready(main, admission)
        try:
            yield binding
        finally:
            if not admission.source_closed(binding):
                deadline = binding.source_deadline or time.monotonic() + 20
                admission.close_source(binding, deadline_monotonic=deadline)


def test_actual_main_ready_same_inode_new_services_preview_and_normal_shutdown(prepared):
    main, admission, _, messages = prepared
    async def run():
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            module = admission.source_module(binding)
            from api import auth
            from research import ResearchStore, ResearchService
            other = ResearchService(ResearchStore(auth._store()))
            assert other is not binding.service and other.store is not binding.service.store
            assert module.require_available(main.app, other) is None
            alternate = __import__('web.backend.services.formal_admission', fromlist=['require'])
            assert alternate.require(main.app, 'source_execute') is None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages)
                rid = await create(client)
                view = await client.get('/api/research/' + rid)
                assert view.status_code == 200 and view.json()['data']['capabilities']['source_evidence'] is True
                assert await approved_source(client, rid)
                health = await client.get('/api/health')
                assert health.status_code == 200 and health.json()['checks']['source_execute'] == 'ready'
        assert binding.source_receipt.state == 'CLOSED'
        assert binding.source_receipt.supervisor_ref == binding.supervisor.reference
        assert not binding.supervisor._thread.is_alive()
        assert all(witness.parent_fd is None for witness in binding.witnesses)
    asyncio.run(run())


def test_real_started_handle_survives_attachment_failure_and_preserves_primary(prepared, monkeypatch):
    main, admission, _, _ = prepared
    captured = []
    def fail_attachment(app, binding, module, supervisor):
        # Failure only, after the actual Core.start return. No fake resource,
        # availability, worker, or successful attachment is supplied.
        captured.append((binding, module, supervisor))
        raise OSError('owned post-start attachment failure')
    monkeypatch.setattr(admission, 'attach_source', fail_attachment)
    async def run():
        with pytest.raises(OSError, match='owned post-start attachment failure'):
            async with main.lifespan(main.app):
                raise AssertionError('startup must not enter after attachment failure')
        assert len(captured) == 1
        binding, module, supervisor = captured[0]
        assert binding.supervisor is supervisor and binding.source_module is module
        assert admission.source_closed(binding) and not supervisor._thread.is_alive()
        assert all(witness.parent_fd is None for witness in binding.witnesses)
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(run())


def test_actual_main_withdraw_before_retire_window_is_normal_cleanup(prepared, monkeypatch):
    """A native scheduling pause, not a substituted ready or worker result."""
    main, admission, _, _ = prepared
    async def run():
        context = main.lifespan(main.app)
        await context.__aenter__()
        binding = await ready(main, admission)
        module = admission.source_module(binding)
        original = module.retire
        first = True
        def pause_before_retire(supervisor, *, deadline_monotonic):
            nonlocal first
            if first:
                first = False
                assert admission._STATE.get(id(main.app)) is None
                module.wake(supervisor)  # Real hint wakes the real idle thread.
                end = time.monotonic() + 1
                while supervisor._thread.is_alive() and time.monotonic() < end:
                    time.sleep(.01)
                print('WITHDRAW_WINDOW_FACTS:' + __import__('json').dumps({
                    'http_withdrawn': binding.retired, 'stop_before_retire': supervisor._stop.is_set(),
                    'worker_alive_before_retire': supervisor._thread.is_alive(),
                    'worker_failure_before_retire': supervisor._failure}))
            return original(supervisor, deadline_monotonic=deadline_monotonic)
        monkeypatch.setattr(module, 'retire', pause_before_retire)
        await context.__aexit__(None, None, None)
        assert binding.source_receipt.state == 'CLOSED'
    asyncio.run(run())


@pytest.mark.parametrize('action', ['cancel', 'delete'])
def test_actual_http_source_task_cancel_before_native_send(prepared, monkeypatch, action):
    main, admission, _, messages = prepared
    async def run():
        async with published_source_retirement(main, admission) as binding:
            from research import authorization
            from multiprocessing import reduction
            held, proceed = threading.Event(), threading.Event()
            handoff_attempts = []
            original_handoff = reduction.send_handle
            def no_public_capability(*args, **kwargs):
                if threading.current_thread() is binding.supervisor._thread:
                    handoff_attempts.append(True)
                    raise PermissionError('public Source send is outside this local control')
                return original_handoff(*args, **kwargs)
            monkeypatch.setattr(reduction, 'send_handle', no_public_capability)
            native = fcntl.flock
            caller_code = authorization._source_task_gate.__wrapped__.__code__
            def barrier(descriptor, operation):
                result = native(descriptor, operation)
                caller = inspect.currentframe().f_back
                if (threading.current_thread() is binding.supervisor._thread and caller.f_code is caller_code
                        and operation == fcntl.LOCK_EX | fcntl.LOCK_NB):
                    held.set()
                    if not proceed.wait(5):
                        raise TimeoutError('owned native task-lock barrier expired')
                return result
            monkeypatch.setattr(fcntl, 'flock', barrier)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                    await login(client, messages)
                    rid = await create(client)
                    approval = await approved_source(client, rid)
                    response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                        'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-task'})
                    assert response.status_code == 200, response.text
                    task = response.json()['data']['task']
                    end = time.monotonic() + 3
                    while not held.is_set() and time.monotonic() < end:
                        await asyncio.sleep(.01)
                    assert held.is_set()
                    if action == 'cancel':
                        cancelled = await client.post('/api/research/' + rid + '/cancel', json=envelope({
                            'task_id': task['id'], 'expected_task_version': task['version']}),
                            headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-cancel'})
                    else:
                        cancelled = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'Origin': BETA})
                    assert cancelled.status_code == 200, cancelled.text
                    proceed.set()
                    end = time.monotonic() + 3
                    while binding.supervisor._slot is not None and time.monotonic() < end:
                        await asyncio.sleep(.01)
                    with binding.service.store.transaction() as connection:
                        assert connection.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
                        state = connection.execute('SELECT execution FROM research_tasks WHERE id=?', (task['id'],)).fetchone()[0]
                        assert state in (('CANCELLED',) if action == 'cancel' else ('CANCELLED', 'ACCESS_REVOKED'))
                    assert not handoff_attempts
            finally:
                proceed.set()
    asyncio.run(run())


def test_actual_withdraw_active_native_slot_never_delivers_send_capability(prepared, monkeypatch):
    main, admission, _, messages = prepared
    async def run():
        context = main.lifespan(main.app)
        await context.__aenter__()
        binding = await ready(main, admission)
        from research import authorization
        from multiprocessing import reduction
        held, release = threading.Event(), threading.Event()
        native_flock, native_handoff = fcntl.flock, reduction.send_handle
        task_code = authorization._source_task_gate.__wrapped__.__code__
        attempts = []
        def barrier(descriptor, operation):
            result = native_flock(descriptor, operation)
            if (threading.current_thread() is binding.supervisor._thread
                    and inspect.currentframe().f_back.f_code is task_code
                    and operation == fcntl.LOCK_EX | fcntl.LOCK_NB):
                held.set()
                if not release.wait(5): raise TimeoutError('owned active-slot primitive expired')
            return result
        def no_delivery(*args, **kwargs):
            if threading.current_thread() is binding.supervisor._thread:
                attempts.append(True); raise PermissionError('public Source send is not authorized here')
            return native_handoff(*args, **kwargs)
        monkeypatch.setattr(fcntl, 'flock', barrier)
        monkeypatch.setattr(reduction, 'send_handle', no_delivery)
        observer = None
        exited = False
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages); rid = await create(client)
                approval = await approved_source(client, rid)
                response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'main-active-slot-before-stop'})
                assert response.status_code == 200
                tid = response.json()['data']['task']['id']
                end = time.monotonic() + 3
                while not held.is_set() and time.monotonic() < end: await asyncio.sleep(.01)
                assert held.is_set()
            withdrawn = []
            def after_real_withdraw():
                end = time.monotonic() + 3
                while admission._STATE.get(id(main.app)) is not None and time.monotonic() < end:
                    time.sleep(.005)
                withdrawn.append(admission._STATE.get(id(main.app)) is None)
                release.set()
            observer = threading.Thread(target=after_real_withdraw, name='owned-main-withdraw-observer')
            observer.start()
            await context.__aexit__(None, None, None)
            exited = True
            observer.join(3)
            assert withdrawn == [True] and not observer.is_alive()
            assert admission.source_closed(binding) and attempts == []
            assert all(witness.parent_fd is None for witness in binding.witnesses)
            with binding.service.store.transaction() as connection:
                assert connection.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
                assert connection.execute('SELECT started FROM research_source_runs WHERE task_id=?', (tid,)).fetchone()[0] == 0
                assert connection.execute('SELECT execution FROM research_tasks WHERE id=?', (tid,)).fetchone()[0] == 'QUEUED'
        finally:
            release.set()
            if observer is not None: observer.join(3)
            if not exited:
                primary = sys.exc_info()[1]
                try:
                    await context.__aexit__(type(primary) if primary is not None else None, primary,
                                            primary.__traceback__ if primary is not None else None)
                except BaseException as cleanup:
                    if primary is None: raise
                    primary.add_note('owned active-slot cleanup uncertain: ' + type(cleanup).__name__)
    asyncio.run(run())


@pytest.mark.parametrize('point', ['before', 'after'])
def test_partial_thread_start_preserves_actual_handle_and_body_primary(request, tmp_path, monkeypatch, point):
    # Run this retained-uncertainty control in its own test process. A second
    # lifetime must not overwrite this genuine Core registry/debt owner.
    if os.environ.get('FORMAL_MAIN_PARTIAL_TEST_CHILD') != 'yes':
        owned = tmp_path / 'partial-child'; owned.mkdir(mode=0o700)
        home = owned / 'home'; home.mkdir(mode=0o700)
        root = Path(__file__).resolve().parents[3]
        paths = [str(root / 'web/backend'), str(root)]
        audit = sys.modules.get('audit_bootstrap')
        if audit is not None:
            paths.insert(0, str(Path(audit.__file__).resolve().parent))
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'TMPDIR': str(owned),
            'A006_AUDIT_ROOT': str(owned), 'REVIEW_SOURCE_ROOT': str(root), 'PYTHONPATH': os.pathsep.join(paths),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            'STRUCTURAL_ENV': 'test', 'AUTH_ENABLED': 'false', 'AUTH_DATA_DIR': str(owned / 'auth'),
            'STRUCTURAL_LOG_FILE': str(owned / 'bootstrap.jsonl'), 'HF_HUB_OFFLINE': '1',
            'TRANSFORMERS_OFFLINE': '1', 'FORMAL_MAIN_PARTIAL_TEST_CHILD': 'yes'}
        target = str(Path(__file__).resolve()) + '::test_partial_thread_start_preserves_actual_handle_and_body_primary[' + point + ']'
        result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-s', '-p', 'no:cacheprovider',
            '-p', 'no:logging', '--basetemp=' + str(owned / 'cases'), target], cwd=owned,
            env=environment, capture_output=True, timeout=30)
        (owned / 'result.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, 'isolated partial-start control failed; retain owned log'
        assert b'PARTIAL_NATIVE_HANDLE_FACTS:' in result.stdout
        return
    prepared = request.getfixturevalue('prepared')
    main, admission, _, messages = prepared
    original = threading.Thread.start
    def fail_source(thread, *args, **kwargs):
        if thread.name == 'structure-source-supervisor':
            if point == 'after':
                original(thread, *args, **kwargs)
            raise OSError('owned native thread-start failure')
        return original(thread, *args, **kwargs)
    monkeypatch.setattr(threading.Thread, 'start', fail_source)
    class BodyFailure(Exception):
        pass
    binding = None
    async def run():
        nonlocal binding
        async with main.lifespan(main.app):
            binding = admission._STATE[id(main.app)]
            assert admission.require(main.app, 'research_basic') is None
            assert admission.safe_status(main.app)['source_execute'] == 'unavailable'
            assert type(binding.supervisor) is binding.source_module.SourceSupervisor
            assert (binding.supervisor._thread.ident is not None) == (point == 'after')
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages)
                assert await create(client)
            raise BodyFailure('owned primary')
    with pytest.raises(BodyFailure) as error:
        asyncio.run(run())
    assert any('retirement uncertain' in note for note in error.value.__notes__)
    assert admission._STATE.get(id(main.app)) is None
    assert binding.source_receipt.state == 'CLEANUP_UNCERTAIN'
    assert binding.source_receipt.reason == 'START_FAILED'
    assert any(witness.parent_fd is not None for witness in binding.witnesses)
    print('PARTIAL_NATIVE_HANDLE_FACTS:' + __import__('json').dumps({
        'http_withdrawn': True, 'receipt': binding.source_receipt.state, 'reason': binding.source_receipt.reason,
        'fault_point': point,
        'source_thread_started': binding.supervisor._thread.ident is not None,
        'shared_witnesses_retained': sum(witness.parent_fd is not None for witness in binding.witnesses),
        'original_body_preserved': True}))


def test_normal_withdraw_fact_never_masks_intrinsic_config_damage(prepared, monkeypatch):
    main, admission, _, _ = prepared
    async def run():
        async with published_source_retirement(main, admission) as binding:
            admission.close_source(binding, deadline_monotonic=time.monotonic() + 20)
            assert admission.withdraw(main.app) is binding
            with pytest.raises(admission.FormalAdmissionWithdrawn) as normal:
                binding.check()
            assert admission.validate_withdrawal(normal.value, binding) is None
            assert normal.value.binding is binding and normal.value.reference == binding.reference
            with pytest.raises(TypeError):
                admission.FormalAdmissionWithdrawn(binding, _factory=admission._WITHDRAW_FACTORY)
            with pytest.raises(RuntimeError):
                admission.validate_withdrawal(RuntimeError('not a normal withdrawal'), binding)
            with monkeypatch.context() as damaged:
                damaged.setenv('AUTH_SITE_ROLE', 'phase')
                with pytest.raises(RuntimeError) as error:
                    binding.check()
                assert type(error.value) is not admission.FormalAdmissionWithdrawn
            with pytest.raises(admission.FormalAdmissionWithdrawn):
                binding.check()
    asyncio.run(run())


def test_actual_controller_source_closed_sublifetime_keeps_history_and_original_deadline(tmp_path):
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService
    service = FormalMainBrowserService(tmp_path / 'controller-source-lifetime')
    with service:
        end = time.monotonic() + 8
        while service.source_status() != 'ready' and time.monotonic() < end:
            time.sleep(.02)
        assert service.source_status() == 'ready'
        status, _ = service.client.request('POST', '/api/auth/request-link', {'email': service.seed.email})
        assert status == 200
        token = service.take_latest_magic_token()
        try:
            status, _ = service.client.request('POST', '/api/auth/verify', {'token': token})
        finally:
            token = None
        assert status == 200
        from urllib.parse import urlencode
        path = '/api/research/' + service.seed.research_id + '/records?' + urlencode({
            'task_id': service.seed.source_task_id, 'kind': 'excerpts'})
        status, before = service.client.request('GET', path)
        assert status == 200 and before['data']['items']
        status, initial = service.client.request('GET', '/api/research/' + service.seed.research_id)
        assert status == 200 and initial['data']['capabilities']['source_evidence'] is True
        assert service.retire_source() == 'unavailable'
        from services import formal_admission as admission
        binding = admission._STATE[id(service.app)]
        receipt, deadline = binding.source_receipt, binding.source_deadline
        assert admission.source_closed(binding) and receipt.supervisor_ref == binding.supervisor.reference
        assert service.retire_source() == 'unavailable'
        assert binding.source_receipt is receipt and binding.source_deadline == deadline
        status, after = service.client.request('GET', path)
        assert status == 200 and after == before
        status, current = service.client.request('GET', '/api/research/' + service.seed.research_id)
        assert status == 200 and current['data']['capabilities']['source_evidence'] is False
        blocked = {'schema_version': 'structure-research-v1', 'contract_revision': 'b1-candidate-01',
            'data': {'input_revision': 1, 'expected_research_version': current['data']['research_version'], 'query': 'queue variability'}}
        status, denied = service.client.request('POST', '/api/research/' + service.seed.research_id + '/source-preview',
            blocked, key='closed-real-source-must-reject-post')
        assert status == 503 and denied['error']['code'] == 'FEATURE_UNAVAILABLE'
        status, health = service.client.request('GET', '/api/health')
        assert status == 200 and health['checks']['base'] == 'ready' and health['checks']['source_execute'] == 'unavailable'
    assert not service.root.exists()


def test_running_bad_resource_is_not_normal_withdrawal_and_retains_uncertainty(request, tmp_path, monkeypatch):
    if os.environ.get('FORMAL_MAIN_BAD_RESOURCE_CHILD') != 'yes':
        owned = tmp_path / 'bad-resource-child'; owned.mkdir(mode=0o700)
        (owned / 'home').mkdir(mode=0o700)
        root = Path(__file__).resolve().parents[3]
        paths = [str(root / 'web/backend'), str(root)]
        audit = sys.modules.get('audit_bootstrap')
        if audit is not None: paths.insert(0, str(Path(audit.__file__).resolve().parent))
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(owned / 'home'), 'TMPDIR': str(owned),
            'A006_AUDIT_ROOT': str(owned), 'REVIEW_SOURCE_ROOT': str(root), 'PYTHONPATH': os.pathsep.join(paths),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'STRUCTURAL_ENV': 'test',
            'AUTH_ENABLED': 'false', 'AUTH_DATA_DIR': str(owned / 'auth'), 'STRUCTURAL_LOG_FILE': str(owned / 'bootstrap.jsonl'),
            'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1', 'FORMAL_MAIN_BAD_RESOURCE_CHILD': 'yes'}
        target = str(Path(__file__).resolve()) + '::test_running_bad_resource_is_not_normal_withdrawal_and_retains_uncertainty'
        result = subprocess.run([sys.executable, '-B', '-m', 'pytest', '-q', '-s', '-p', 'no:cacheprovider',
            '-p', 'no:logging', '--basetemp=' + str(owned / 'cases'), target], cwd=owned,
            env=environment, capture_output=True, timeout=30)
        (owned / 'result.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, 'isolated bad-resource control failed; retain owned log'
        assert b'BAD_RESOURCE_NATIVE_FACTS:' in result.stdout
        return
    main, admission, paths, _ = request.getfixturevalue('prepared')
    async def run():
        with pytest.raises(RuntimeError):
            async with main.lifespan(main.app):
                binding = await ready(main, admission)
                database = paths.STATE_ROOT / 'auth.sqlite3'
                try:
                    database.chmod(0o644)  # Real invariant damage; no DB FD copy/close.
                    with pytest.raises(RuntimeError) as error:
                        binding.check()
                    assert type(error.value) is not admission.FormalAdmissionWithdrawn
                    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                        assert (await client.get('/api/health')).status_code == 503
                    end = time.monotonic() + 3
                    while binding.supervisor._thread.is_alive() and time.monotonic() < end:
                        await asyncio.sleep(.02)
                    assert binding.supervisor._failure is not None
                finally:
                    database.chmod(0o600)
        assert binding.source_receipt.state == 'CLEANUP_UNCERTAIN'
        assert any(witness.parent_fd is not None for witness in binding.witnesses)
        print('BAD_RESOURCE_NATIVE_FACTS:' + json.dumps({'base_rejected': True, 'not_normal_withdrawal': True,
            'source_receipt': binding.source_receipt.state, 'worker_failure': binding.supervisor._failure,
            'witnesses_retained': sum(w.parent_fd is not None for w in binding.witnesses)}))
    asyncio.run(run())


def test_actual_main_restarts_real_interrupted_source_debt_without_fetch(prepared, tmp_path, monkeypatch):
    main, admission, paths, _ = prepared
    from multiprocessing import reduction
    from api import auth
    from research import ResearchStore
    from services import runtime_paths
    root = Path(__file__).resolve().parents[3]
    owned = tmp_path / 'crash-probe'; owned.mkdir(mode=0o700)
    home = owned / 'home'; home.mkdir(mode=0o700)
    read, write = os.pipe()
    environment = {key: os.environ[key] for key in (
        'JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY', 'STRUCTURAL_SHARE_TOKEN_SECRET',
        'AUTH_DATA_DIR', 'STRUCTURAL_SSO_DATA_DIR', 'AUTH_LINK_BASE_URL', 'AUTH_SITE_ROLE',
        'AUTH_TRUSTED_PROXY_IPS', 'AUTH_ENABLED', 'AUTH_DEV_MODE', 'STRUCTURAL_ENV')}
    pythonpath = [str(root / 'web/backend'), str(root)]
    audit = sys.modules.get('audit_bootstrap')
    if audit is not None: pythonpath.insert(0, str(Path(audit.__file__).resolve().parent))
    # The shared synthetic state belongs to the original task root; do not
    # narrow the child guard to a directory that excludes that state.
    task_root = os.environ.get('TMPDIR', str(tmp_path))
    environment.update(PATH='/usr/bin:/bin', HOME=str(home), TMPDIR=task_root, A006_AUDIT_ROOT=task_root,
        REVIEW_SOURCE_ROOT=str(root), PYTHONPATH=os.pathsep.join(pythonpath), PYTHONDONTWRITEBYTECODE='1',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', FORMAL_SOURCE_PROBE_FD=str(write),
        STRUCTURAL_LOG_FILE=str(owned / 'bootstrap.jsonl'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    process = None
    try:
        with (owned / 'probe.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--interrupted-source-probe'],
                cwd=owned, env=environment, pass_fds=(write,), close_fds=True, stdout=log, stderr=subprocess.STDOUT,
                start_new_session=True)
            os.close(write); write = None
            readable, _, _ = select.select([read], [], [], 25)
            assert readable, 'owned crash probe never reached real pre-handoff point'
            frame = json.loads(os.read(read, 2048))
            assert frame['probe_pid'] == process.pid and frame['phase'] == 'before_real_fd_handoff'
            (owned / 'safe-process-frame.json').write_text(json.dumps(frame, sort_keys=True) + '\n')
            os.killpg(process.pid, signal.SIGKILL)
            assert process.wait(timeout=5) == -signal.SIGKILL
        store = ResearchStore(auth._store())
        with store.transaction() as connection:
            before = connection.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=?',
                                        (frame['task_id'],)).fetchone()
            assert tuple(before) == ('SENDING', 0)
            assert connection.execute('SELECT started FROM research_source_runs WHERE task_id=?',
                                      (frame['task_id'],)).fetchone()[0] == 1
        attempts = []; original = reduction.send_handle
        def no_refetch(*args, **kwargs):
            attempts.append(True)
            raise PermissionError('restart control never grants a public source capability')
        monkeypatch.setattr(reduction, 'send_handle', no_refetch)
        async def recover():
            async with published_source_retirement(main, admission) as binding:
                with binding.service.store.transaction() as connection:
                    after = connection.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=?',
                                               (frame['task_id'],)).fetchone()
                    assert tuple(after) == ('UNKNOWN', 1)
                    assert connection.execute('SELECT execution FROM research_tasks WHERE id=?',
                                              (frame['task_id'],)).fetchone()[0] == 'FAILED'
                    assert connection.execute("SELECT count(*) FROM research_evidence_objects WHERE kind IN ('snapshots','reports')").fetchone()[0] == 0
                assert attempts == []
                (owned / 'safe-recovery-facts.json').write_text(json.dumps({
                    'same_auth_inode': binding.service.store.storage_identity == store.storage_identity,
                    'before': ['SENDING', 0], 'after': ['UNKNOWN', 1],
                    'task': 'FAILED', 'source_body_records': 0, 'new_capability_handoffs': len(attempts),
                    'producer': 'actual_Main_HTTP_and_real_pre_SCM_primitive',
                    'recovery': 'actual_Main_fresh_native_cleanup_before_READY'}) + '\n')
        asyncio.run(recover())
    finally:
        if write is not None: os.close(write)
        os.close(read)
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)


def _interrupted_source_probe():
    """Owned subprocess only: actual Main produces debt, never an external GET."""
    import smtplib
    from multiprocessing import reduction
    from services import runtime_paths
    from web.backend.tests.acceptance.formal_main_browser_service import _MailSink
    runtime_paths.STATE_ROOT = Path(os.environ['AUTH_DATA_DIR'])
    runtime_paths.CACHE_ROOT = runtime_paths.STATE_ROOT.parent / 'cache'
    runtime_paths.LOG_ROOT = runtime_paths.STATE_ROOT / 'logs'
    sink = _MailSink(); sink.start()
    os.environ.update(SMTP_HOST='127.0.0.1', SMTP_PORT=str(sink.port), SMTP_FROM_EMAIL='sender@example.invalid',
        ADMIN_NOTIFICATION_EMAIL='admin@example.invalid', SMTP_STARTTLS='false', SMTP_USE_SSL='false', SMTP_TIMEOUT_SECONDS='2')
    native_smtp = smtplib.SMTP
    def local_mail(host, port, *args, **kwargs):
        assert (host, port) == ('127.0.0.1', sink.port)
        kwargs.setdefault('local_hostname', 'fixture.invalid')
        return native_smtp(host, port, *args, **kwargs)
    smtplib.SMTP = local_mail  # Actual protocol; only deterministic local EHLO.
    import main
    from services import formal_admission as admission
    fd = int(os.environ['FORMAL_SOURCE_PROBE_FD'])
    native_handoff = reduction.send_handle
    binding = None
    def hold_before_capability(connection, handle, destination_pid):
        if binding is not None and threading.current_thread() is binding.supervisor._thread:
            os.write(fd, json.dumps({'phase': 'before_real_fd_handoff', 'probe_pid': os.getpid(),
                'sender_pid': destination_pid, 'task_id': binding.supervisor._slot}).encode())
            threading.Event().wait(25)
            raise PermissionError('owned pre-handoff control expired without granting capability')
        return native_handoff(connection, handle, destination_pid)
    reduction.send_handle = hold_before_capability
    async def run():
        nonlocal binding
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                response = await client.post('/api/auth/request-link', json={'email': 'interrupted-source@example.invalid'}, headers={'Origin': BETA})
                assert response.status_code == 200
                token = sink.take_latest_magic_token()
                try: response = await client.post('/api/auth/verify', json={'token': token}, headers={'Origin': BETA})
                finally: token = None
                assert response.status_code == 200
                rid = await create(client); approval = await approved_source(client, rid)
                response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'real-interrupted-source-task'})
                assert response.status_code == 200
                await asyncio.sleep(28)
    try:
        asyncio.run(run())
    finally:
        sink.close(); os.close(fd)


def _source_main15_debt_probe(mode):
    """Two fixed owned fault specimens; neither delivers an SCM capability."""
    if mode not in ('terminal-unknown', 'sender-close-uncertainty'):
        raise SystemExit('fixed Main15 debt specimen required')
    import smtplib
    import stat
    from multiprocessing import reduction
    from research import authorization, source_spawn
    from services import runtime_paths
    from web.backend.tests.acceptance.formal_main_browser_service import _MailSink
    runtime_paths.STATE_ROOT = Path(os.environ['AUTH_DATA_DIR'])
    runtime_paths.CACHE_ROOT = runtime_paths.STATE_ROOT.parent / 'cache'
    runtime_paths.LOG_ROOT = runtime_paths.STATE_ROOT / 'logs'
    sink = _MailSink(); sink.start()
    os.environ.update(SMTP_HOST='127.0.0.1', SMTP_PORT=str(sink.port),
        SMTP_FROM_EMAIL='sender@example.invalid', ADMIN_NOTIFICATION_EMAIL='admin@example.invalid',
        SMTP_STARTTLS='false', SMTP_USE_SSL='false', SMTP_TIMEOUT_SECONDS='2')
    native_smtp = smtplib.SMTP
    def local_mail(host, port, *args, **kwargs):
        assert (host, port) == ('127.0.0.1', sink.port)
        kwargs.setdefault('local_hostname', 'fixture.invalid')
        return native_smtp(host, port, *args, **kwargs)
    smtplib.SMTP = local_mail
    import main
    from services import formal_admission as admission
    fd = int(os.environ['FORMAL_SOURCE_PROBE_FD'])
    native_handoff, native_close = reduction.send_handle, os.close
    native_sender_close = source_spawn.SourceSpawnProcess.close
    owner_code = authorization.AuthorizationGate.owner_gate_id.__wrapped__.__code__
    denied, owner_released = threading.Event(), threading.Event()
    owner_pause = threading.Event()
    handoffs, closed_senders, injected = [], [], []
    binding = None
    owner_fd_observation = []

    def reject_before_scm(connection, handle, destination_pid):
        if binding is not None and threading.current_thread() is binding.supervisor._thread:
            handoffs.append(destination_pid)
            denied.set()
            raise PermissionError('owned Main15 armed sender receives no capability')
        return native_handoff(connection, handle, destination_pid)

    def after_real_sender_close(process):
        own = binding is not None and threading.current_thread() is binding.supervisor._thread
        if not own:
            return native_sender_close(process)
        pid, popen = process.pid, process._popen
        sender, tracker = popen.sender, popen.tracker.process
        result = native_sender_close(process)
        assert handoffs == [pid] and process._closed
        assert sender.poll() is not None and tracker.poll() is not None
        closed_senders.append(process)
        if mode == 'sender-close-uncertainty' and not injected:
            injected.append(True)
            raise source_spawn.SourceCleanupUncertain('owned Main15 post-close acknowledgement uncertain')
        return result

    def after_real_owner_close(descriptor):
        watch = (mode == 'terminal-unknown' and binding is not None
            and threading.current_thread() is binding.supervisor._thread
            and sys._getframe(1).f_code is owner_code and denied.is_set()
            and not owner_released.is_set())
        old = os.fstat(descriptor) if watch else None
        result = native_close(descriptor)
        if watch and stat.S_ISREG(old.st_mode):
            # A reused number is not evidence that the old description survived.
            try:
                current = os.fstat(descriptor)
                fd_state = ('reused_other_identity' if (current.st_dev, current.st_ino) !=
                            (old.st_dev, old.st_ino) else 'present_same_identity_unclassified')
            except OSError:
                fd_state = 'absent'
            with binding.service.store.transaction() as conn:
                row = conn.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=?',
                                   (binding.supervisor._slot,)).fetchone()
            if row is not None and tuple(row) == ('UNKNOWN', 0):
                owner_fd_observation.append(fd_state)
                owner_released.set()
                if not owner_pause.wait(3):
                    raise TimeoutError('owned Main15 post-owner-close observation expired')
        return result

    reduction.send_handle = reject_before_scm
    source_spawn.SourceSpawnProcess.close = after_real_sender_close
    os.close = after_real_owner_close

    async def run():
        nonlocal binding
        async with main.lifespan(main.app):
            binding = await ready(main, admission)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                response = await client.post('/api/auth/request-link', json={'email': 'main15-debt@example.invalid'},
                                             headers={'Origin': BETA})
                assert response.status_code == 200
                token = sink.take_latest_magic_token()
                try: response = await client.post('/api/auth/verify', json={'token': token}, headers={'Origin': BETA})
                finally: token = None
                assert response.status_code == 200
                rid = await create(client); approval = await approved_source(client, rid)
                response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'main15-debt-task'})
                assert response.status_code == 200
                tid = response.json()['data']['task']['id']
                deadline = time.monotonic() + 3
                if mode == 'terminal-unknown':
                    while not owner_released.is_set() and time.monotonic() < deadline:
                        await asyncio.sleep(.01)
                    assert owner_released.is_set() and len(closed_senders) == 1
                    with binding.service.store.transaction() as conn:
                        version = conn.execute('SELECT version FROM research_tasks WHERE id=?', (tid,)).fetchone()[0]
                    cancelled = await client.post('/api/research/' + rid + '/cancel', json=envelope({
                        'task_id': tid, 'expected_task_version': version}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'main15-terminal-cancel'})
                    assert cancelled.status_code == 200
                else:
                    while binding.supervisor._thread.is_alive() and time.monotonic() < deadline:
                        await asyncio.sleep(.01)
                    assert not binding.supervisor._thread.is_alive() and injected == [True]
                    assert binding.supervisor._state == 'CLEANUP_UNCERTAIN'
                    assert binding.supervisor._slot == tid and binding.supervisor._lease is not None
                    assert binding.supervisor._session.task_id == tid
                    assert binding.supervisor._guard._session is binding.supervisor._session
                    assert len(closed_senders) == 1 and closed_senders[0]._closed
                    assert any(getattr(error, '_source_cleanup_uncertainty', ())
                               for error in binding.supervisor._errors)
                with binding.service.store.transaction() as conn:
                    task = conn.execute('SELECT execution FROM research_tasks WHERE id=?', (tid,)).fetchone()[0]
                    row = conn.execute('SELECT outcome,execution_closed FROM research_source_requests WHERE task_id=?', (tid,)).fetchone()
                    assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 15
                assert tuple(row) == ('UNKNOWN', 0)
                assert task == ('CANCELLED' if mode == 'terminal-unknown' else 'RUNNING')
                assert binding.source_module._select(binding.service.store, cleanup_only=True) == [(tid, 'cleanup')]
                assert len(handoffs) == 1
                print('MAIN15_DEBT_NATIVE_FACTS:' + json.dumps({
                    'mode': mode, 'real_sender_closed': all(item._closed for item in closed_senders),
                    'typed_close_uncertainty_injected_once': injected == [True],
                    'owner_fd_after_real_close': owner_fd_observation,
                    'terminal_unknown_open': task == 'CANCELLED' and tuple(row) == ('UNKNOWN', 0)}), flush=True)
                os.write(fd, json.dumps({'mode': mode, 'phase': 'main15-debt-open',
                    'probe_pid': os.getpid(), 'sender_pid': handoffs[0], 'task_id': tid}).encode())
                await asyncio.sleep(3)
                raise AssertionError('owned parent did not interrupt the fixed debt specimen')
    try:
        asyncio.run(run())
    finally:
        owner_pause.set()
        os.close = native_close
        reduction.send_handle = native_handoff
        source_spawn.SourceSpawnProcess.close = native_sender_close
        sink.close(); os.close(fd)


def _actual_main15_debt_recovery(prepared, tmp_path, monkeypatch, mode):
    """Reuse the existing owned pre-SCM process/pipe recovery protocol."""
    assert mode in ('terminal-unknown', 'sender-close-uncertainty')
    main, admission, _, _ = prepared
    from api import auth
    from multiprocessing import reduction
    from research import ResearchStore, authorization, source_workflow
    root = Path(__file__).resolve().parents[3]
    owned = tmp_path / mode; owned.mkdir(mode=0o700)
    home = owned / 'home'; home.mkdir(mode=0o700)
    read, write = os.pipe()
    environment = {name: os.environ[name] for name in (
        'JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY', 'STRUCTURAL_SHARE_TOKEN_SECRET',
        'AUTH_DATA_DIR', 'STRUCTURAL_SSO_DATA_DIR', 'AUTH_LINK_BASE_URL', 'AUTH_SITE_ROLE',
        'AUTH_TRUSTED_PROXY_IPS', 'AUTH_ENABLED', 'AUTH_DEV_MODE', 'STRUCTURAL_ENV')}
    pythonpath = [str(root / 'web/backend'), str(root)]
    audit = sys.modules.get('audit_bootstrap')
    if audit is not None: pythonpath.insert(0, str(Path(audit.__file__).resolve().parent))
    task_root = os.environ.get('TMPDIR', str(tmp_path))
    environment.update(PATH='/usr/bin:/bin', HOME=str(home), TMPDIR=task_root, A006_AUDIT_ROOT=task_root,
        REVIEW_SOURCE_ROOT=str(root), PYTHONPATH=os.pathsep.join(pythonpath), PYTHONDONTWRITEBYTECODE='1',
        PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', FORMAL_SOURCE_PROBE_FD=str(write),
        STRUCTURAL_LOG_FILE=str(owned / 'bootstrap.jsonl'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    process = None
    try:
        with (owned / 'probe.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), '--main15-debt-probe', mode],
                cwd=owned, env=environment, pass_fds=(write,), close_fds=True,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            os.close(write); write = None
            readable, _, _ = select.select([read], [], [], 25)
            assert readable, 'owned Main15 specimen did not produce its fixed debt phase'
            raw = os.read(read, 2048)
            assert raw, 'owned Main15 specimen exited before producing actual debt; retain probe log'
            frame = json.loads(raw)
            assert set(frame) == {'mode', 'phase', 'probe_pid', 'sender_pid', 'task_id'}
            assert frame['mode'] == mode and frame['phase'] == 'main15-debt-open'
            assert frame['probe_pid'] == process.pid and process.poll() is None
            assert os.getpgid(process.pid) == process.pid
            (owned / 'safe-process-frame.json').write_text(json.dumps(frame, sort_keys=True))
            os.killpg(process.pid, signal.SIGKILL)
            assert process.wait(timeout=5) == -signal.SIGKILL
        store = ResearchStore(auth._store())
        with store.transaction() as conn:
            before = dict(conn.execute('SELECT * FROM research_source_requests WHERE task_id=?', (frame['task_id'],)).fetchone())
            execution = conn.execute('SELECT execution FROM research_tasks WHERE id=?', (frame['task_id'],)).fetchone()[0]
        assert (before['outcome'], before['execution_closed']) == ('UNKNOWN', 0)
        assert execution == ('CANCELLED' if mode == 'terminal-unknown' else 'RUNNING')
        module = __import__(store.__class__.__module__.rsplit('.', 1)[0] + '.source_supervisor', fromlist=['_select'])
        assert module._select(store, cleanup_only=True) == [(frame['task_id'], 'cleanup')]
        attempts, locks, calls = [], [], []
        native_handoff, native_flock = reduction.send_handle, fcntl.flock
        old_profile = threading.getprofile()
        task_code = authorization._source_task_gate.__wrapped__.__code__
        owner_code = authorization.AuthorizationGate.owner_gate_id.__wrapped__.__code__

        def actual_worker():
            handle = module._REGISTRY.get(id(main.app))
            return (type(handle) is module.SourceSupervisor and threading.current_thread() is handle._thread)

        def observe_lock(descriptor, operation):
            result = native_flock(descriptor, operation)
            code = sys._getframe(1).f_code
            if actual_worker() and operation == fcntl.LOCK_EX | fcntl.LOCK_NB and code in (task_code, owner_code):
                info = os.fstat(descriptor)
                import stat
                locks.append({'kind': 'task' if code is task_code else 'owner',
                    'identity': [info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode), info.st_nlink]})
            return result

        def observe_cleanup(frame_in, event, result):
            if (event == 'call' and frame_in.f_code is source_workflow.close_interrupted.__code__
                    and actual_worker()):
                lease = frame_in.f_locals.get('task_lease')
                caller = frame_in.f_back
                calls.append({'pid': os.getpid(), 'actual_worker': True,
                    'task_matches': frame_in.f_locals.get('task_id') == frame['task_id'],
                    'native_task_lease': type(lease) is authorization.TaskGateLease,
                    'same_pid_lease': lease is not None and lease.pid == os.getpid(),
                    'original_cleanup_dispatch': bool(caller is not None
                        and caller.f_code is module._execute.__code__
                        and caller.f_locals.get('operation') == 'cleanup'),
                    'active_task_lease': bool(lease is not None and lease.active),
                    'cleanup_task_lease': bool(lease is not None and lease.cleanup)})

        def no_refetch(*args, **kwargs):
            if sys._getframe(1).f_code is authorization.OwnerGateLease.handoff.__code__:
                attempts.append(True)
                raise PermissionError('Main15 recovery never grants a new Source capability')
            return native_handoff(*args, **kwargs)

        monkeypatch.setattr(fcntl, 'flock', observe_lock)
        monkeypatch.setattr(reduction, 'send_handle', no_refetch)
        threading.setprofile(observe_cleanup)
        try:
            async def recover():
                async with published_source_retirement(main, admission) as binding:
                    assert binding.service.store.storage_identity == store.storage_identity
                    with binding.service.store.transaction() as conn:
                        after = dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?', (before['id'],)).fetchone())
                        state = conn.execute('SELECT execution FROM research_tasks WHERE id=?', (frame['task_id'],)).fetchone()[0]
                        assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0] == 1
                        assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 1
                        assert conn.execute("SELECT count(*) FROM research_evidence_objects WHERE kind IN ('snapshots','reports')").fetchone()[0] == 0
                    assert (after['outcome'], after['execution_closed']) == ('UNKNOWN', 1)
                    assert state == ('CANCELLED' if mode == 'terminal-unknown' else 'FAILED')
                    assert (after['started_at'], after['ended_at']) == (before['started_at'], before['ended_at'])
                    assert after['closure_ref'] and after['closure_proof']
                    proof = json.loads(after['closure_proof'])
                    assert proof['task_gate'] in [item['identity'] for item in locks if item['kind'] == 'task']
                    assert proof['owner_gate'] in [item['identity'] for item in locks if item['kind'] == 'owner']
                    assert calls == [{'pid': os.getpid(), 'actual_worker': True, 'task_matches': True,
                        'native_task_lease': True, 'same_pid_lease': True, 'original_cleanup_dispatch': True,
                        'active_task_lease': True, 'cleanup_task_lease': mode == 'terminal-unknown'}]
                    assert module._select(store) == [] and not attempts
                    (owned / 'safe-recovery-facts.json').write_text(json.dumps({
                        'mode': mode, 'schema': 15, 'before': ['UNKNOWN', 0], 'after': ['UNKNOWN', 1],
                        'before_task': execution, 'after_task': state, 'same_auth_inode': True,
                        'real_cleanup_calls': calls, 'closure_matches_actual_native_locks': True,
                        'used': 1, 'times_preserved': True, 'source_gets': 0, 'new_handoffs': 0}))
            asyncio.run(recover())
        finally:
            threading.setprofile(old_profile)
    finally:
        if write is not None: os.close(write)
        os.close(read)
        if process is not None and process.poll() is None:
            assert os.getpgid(process.pid) == process.pid
            os.killpg(process.pid, signal.SIGKILL); process.wait(timeout=5)


def test_actual_main15_terminal_unknown_debt_uses_fresh_native_cleanup(prepared, tmp_path, monkeypatch):
    _actual_main15_debt_recovery(prepared, tmp_path, monkeypatch, 'terminal-unknown')


def test_actual_main15_sender_close_uncertainty_preserves_debt_until_fresh_main(prepared, tmp_path, monkeypatch):
    _actual_main15_debt_recovery(prepared, tmp_path, monkeypatch, 'sender-close-uncertainty')


if __name__ == '__main__':
    if sys.argv[1:] == ['--interrupted-source-probe']:
        _interrupted_source_probe()
    elif len(sys.argv) == 3 and sys.argv[1] == '--main15-debt-probe':
        _source_main15_debt_probe(sys.argv[2])
    else:
        raise SystemExit('owned test probe only')


@pytest.mark.parametrize('policy', ['native', 'funded'])
def test_real_paid_queue_is_not_claimed_by_source_supervisor(prepared, policy):
    main, admission, paths, messages = prepared
    async def run():
        async with published_source_retirement(main, admission) as binding:
            from research import plan_native as native
            from web.backend.tests.test_research_funded_plan import provider, funded
            from web.backend.tests.test_research_paid_producers import identity
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages)
                rid = await create(client)
                with provider() as (server, calls):
                    @contextmanager
                    def native_installation():
                        authority = native.create_controlled_fixture_authority(binding.service.store, identity(client), server,
                            approved_cap_units=41_000_000, risk_margin_units=1_000_000)
                        provision = native.issue_native_provision(binding.service.store, authority)
                        permit = native.mint_runtime_permit(provision)
                        resource = native.open_controlled_fixture_resource(permit)
                        try:
                            native.install_native_funding(binding.service.store, provision, resource)
                            yield
                        finally:
                            native.retire_installation(binding.service.store)
                    installation = native_installation() if policy == 'native' else funded(
                        (client, paths.STATE_ROOT, rid, binding.service.store), server)
                    with installation:
                        contract = 'funded-plan-v2' if policy == 'native' else 'b1-candidate-01'
                        body = {'schema_version': 'structure-research-v1', 'contract_revision': contract,
                            'data': {'input_revision': 1, 'expected_research_version': 1,
                                'observation_source': 'own_observation', 'declaration_status': 'self_declared'}}
                        response = await client.post('/api/research/' + rid + '/plan-previews', json=body,
                            headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-paid-preview'})
                        assert response.status_code == 200, response.text
                        preview = response.json()['data']
                        confirm = {name: preview[name] for name in ('preview_ref', 'preview_digest', 'request_digest',
                            'expected_research_version', 'approved_upper_units')}
                        confirm['confirm_outbound'] = True
                        response = await client.post('/api/research/' + rid + '/plan-approvals',
                            json={**body, 'data': confirm}, headers={'Origin': BETA, 'Idempotency-Key': 'main-c3-paid-confirm'})
                        assert response.status_code == 200, response.text
                        tid = response.json()['data']['task_id']
                        await asyncio.sleep(.6)  # Several real Source periodic scans.
                        with binding.service.store.transaction() as connection:
                            row = connection.execute('SELECT policy_revision,execution FROM research_tasks WHERE id=?', (tid,)).fetchone()
                            assert row['policy_revision'] == ('native-plan-v1' if policy == 'native' else 'funded-plan-v1')
                            assert row['execution'] == 'QUEUED'
                        assert binding.source_module._select(binding.service.store) == []
                        assert binding.supervisor._slot is None and calls == []
    asyncio.run(run())


def test_actual_main15_periodic_slot_without_hint_selects_real_task_before_cancel(prepared, monkeypatch, tmp_path):
    main, admission, _, messages = prepared

    async def run():
        async with published_source_retirement(main, admission) as binding:
            from research import authorization
            from multiprocessing import reduction
            module = admission.source_module(binding)
            supervisor = binding.supervisor
            held, release = threading.Event(), threading.Event()
            dropped, slot_threads, handoffs = [], [], []
            native_set = supervisor._event.set
            native_flock = fcntl.flock
            native_handoff = reduction.send_handle
            task_code = authorization._source_task_gate.__wrapped__.__code__

            def drop_only_this_hint():
                if sys._getframe(1).f_code is module.wake.__code__:
                    dropped.append(True)
                    return
                return native_set()

            def after_real_task_lock(descriptor, operation):
                result = native_flock(descriptor, operation)
                if (threading.current_thread() is supervisor._thread
                        and sys._getframe(1).f_code is task_code
                        and operation == fcntl.LOCK_EX | fcntl.LOCK_NB):
                    slot_threads.append(threading.get_ident())
                    held.set()
                    if not release.wait(3):
                        raise TimeoutError('owned Main15 task-lock observation expired')
                return result

            def reject_public_handoff(*args, **kwargs):
                if threading.current_thread() is supervisor._thread:
                    handoffs.append(True)
                    raise PermissionError('Main15 control never delivers a Source capability')
                return native_handoff(*args, **kwargs)

            monkeypatch.setattr(supervisor._event, 'set', drop_only_this_hint)
            monkeypatch.setattr(fcntl, 'flock', after_real_task_lock)
            monkeypatch.setattr(reduction, 'send_handle', reject_public_handoff)
            try:
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                    await login(client, messages)
                    rid = await create(client)
                    approval = await approved_source(client, rid)
                    response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                        'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'main15-no-hint-task'})
                    assert response.status_code == 200, response.text
                    task = response.json()['data']['task']
                    # Exercise the genuine wake port, but lose only its hint.
                    # HTTP enqueue currently relies on the periodic scan itself.
                    module.wake(supervisor)
                    deadline = time.monotonic() + 3
                    while not held.is_set() and time.monotonic() < deadline:
                        await asyncio.sleep(.01)
                    assert dropped and held.is_set()
                    assert supervisor._slot == task['id'] and slot_threads == [supervisor._thread.ident]
                    with binding.service.store.transaction() as conn:
                        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 15
                        assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?', (task['id'],)).fetchone()[0] == 0
                    assert module._select(binding.service.store) == [(task['id'], 'send')]
                    assert module._select(binding.service.store, cleanup_only=True) == []
                    cancelled = await client.post('/api/research/' + rid + '/cancel', json=envelope({
                        'task_id': task['id'], 'expected_task_version': task['version']}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'main15-no-hint-cancel'})
                    assert cancelled.status_code == 200, cancelled.text
                    release.set()
                    deadline = time.monotonic() + 3
                    while supervisor._slot is not None and time.monotonic() < deadline:
                        await asyncio.sleep(.01)
                    assert supervisor._slot is None
                    with binding.service.store.transaction() as conn:
                        assert conn.execute('SELECT execution FROM research_tasks WHERE id=?', (task['id'],)).fetchone()[0] == 'CANCELLED'
                        assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
                    assert module._select(binding.service.store) == [] and not handoffs
                    (tmp_path / 'main15-periodic-slot.json').write_text(json.dumps({
                        'schema': 15, 'hint_dropped': True, 'actual_periodic_worker_slot': True,
                        'actual_source_select': 'send', 'actual_task_gate_acquired': True,
                        'cancelled_before_scm': True, 'source_requests': 0, 'source_gets': 0}))
            finally:
                release.set()

    asyncio.run(run())


def _source_state_stop_control(prepared, point):
    """Two real worker windows; pause scheduling, never fabricate stop authority."""
    main, admission, _, messages = prepared
    from research import source_supervisor as source
    lines = Path(source.__file__).read_text().splitlines()
    state_lines = [i for i, line in enumerate(lines, 1) if "if self._state not in ('STARTING', 'READY'):" in line]
    target = state_lines[0 if point == 'loop' else 1]
    idle_line = next(i for i, line in enumerate(lines, 1) if 'self._event.wait(_POLL_SECONDS)' in line)
    idle, idle_release = threading.Event(), threading.Event()
    entered, release = threading.Event(), threading.Event()
    seen, errors, captured = [], [], []
    def trace(frame, event, argument):
        if frame.f_code is not source.SourceSupervisor._run_with_budget.__code__:
            return None
        supervisor = source._REGISTRY.get(id(main.app))
        if (event == 'line' and supervisor is not None and threading.current_thread() is supervisor._thread
                and supervisor._state == 'READY'):
            if point == 'selected' and frame.f_lineno == idle_line and not idle.is_set():
                idle.set()
                if not idle_release.wait(10): raise TimeoutError('owned idle scheduling barrier expired')
            if frame.f_lineno == target and not seen:
                seen.append(True); entered.set()
                if not release.wait(5): raise TimeoutError('owned Source state barrier expired')
        return trace
    def release_after_actual_retire():
        try:
            assert entered.wait(10)
            end = time.monotonic() + 5
            while time.monotonic() < end:
                supervisor = source._REGISTRY.get(id(main.app))
                if supervisor is not None and supervisor._state == 'STOPPING' and supervisor._stop.is_set(): break
                time.sleep(.001)
            else: raise TimeoutError('actual Source retirement not observed')
        except BaseException as error:
            errors.append('TIMEOUT' if type(error) is TimeoutError else 'OBSERVER_FAILURE')
        finally: release.set()
    old_trace = threading.gettrace(); threading.settrace(trace)
    observer = threading.Thread(target=release_after_actual_retire, name='owned-source-state-stop-observer')
    async def run():
        context = main.lifespan(main.app); await context.__aenter__()
        binding = admission._STATE[id(main.app)]; captured.append(binding)
        if point == 'selected':
            end = time.monotonic() + 5
            while not idle.is_set() and time.monotonic() < end: await asyncio.sleep(.01)
            assert idle.is_set()
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages)
                rid = await create(client); approval = await approved_source(client, rid)
                response = await client.post('/api/research/' + rid + '/source-tasks', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'source-state-window-task'})
                assert response.status_code == 200, response.text
                task_id = response.json()['data']['task']['id']
            # The actual HTTP action/Owner admission has returned before the
            # worker takes its state lock. No response is fabricated here.
            idle_release.set(); source.wake(binding.supervisor)
        end = time.monotonic() + 5
        while not entered.is_set() and time.monotonic() < end: await asyncio.sleep(.01)
        assert entered.is_set()
        assert binding.supervisor._slot is None and binding.supervisor._lease is None
        if point == 'selected': assert binding.supervisor._cursor == task_id
        observer.start()  # Startup/HTTP preparation must not consume this observation window.
        await context.__aexit__(None, None, None)
        assert not errors and binding.source_receipt.state == 'CLOSED'
        assert binding.source_receipt.reason == 'CLOSED' and binding.supervisor._failure is None
        assert not binding.supervisor._thread.is_alive()
        assert all(witness.parent_fd is None for witness in binding.witnesses)
        with binding.service.store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
            if point == 'selected':
                assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?', (task_id,)).fetchone()[0] == 0
        print('SOURCE_STATE_NATIVE_STOP:' + json.dumps({'point': point, 'receipt': 'CLOSED',
            'worker_failure': None, 'actual_selected_http_task': point == 'selected', 'claims': 0, 'requests': 0, 'gets': 0}))
    try: asyncio.run(run())
    finally:
        idle_release.set(); release.set(); threading.settrace(old_trace)
        if observer.ident is not None: observer.join(11)
        assert not observer.is_alive()
        for binding in captured:
            assert not binding.supervisor._thread.is_alive()
            # Physical teardown only if a later regression failed; no logical
            # CLOSED/registry entry is supplied or repaired by the test.
            governor = binding.supervisor._sec_access
            if governor.fd is not None: os.close(governor.fd)
            for witness in binding.witnesses:
                if witness.parent_fd is not None: witness.close()


@pytest.mark.parametrize('point', ['loop', 'selected'])
def test_actual_main_native_stop_between_check_and_source_state_is_closed(prepared, point):
    _source_state_stop_control(prepared, point)


@pytest.mark.parametrize('fault', ['state', 'event', 'integrity'])
def test_actual_main_unsealed_source_state_or_integrity_fault_stays_uncertain(request, tmp_path, monkeypatch, fault):
    if os.environ.get('SOURCE_STATE_FAULT_CHILD') != fault:
        owned = tmp_path / fault; owned.mkdir(mode=0o700)
        home = owned / 'home'; home.mkdir(mode=0o700)
        root = Path(__file__).resolve().parents[3]
        audit = sys.modules.get('audit_bootstrap')
        assert audit is not None, 'owned lifecycle guard required for isolated uncertainty control'
        guard = sys.modules.get('main_smtp_task_guard')
        assert guard is not None, 'approved owned Main guard required'
        packet = Path(guard.__file__).resolve().parent
        environment = {'PATH': os.environ['PATH'], 'PYTHONPATH': os.pathsep.join((str(Path(audit.__file__).resolve().parent),
            str(root / 'web/backend'), str(root), str(packet))), 'REVIEW_SOURCE_ROOT': str(root),
            'HOME': str(home), 'TMPDIR': str(owned), 'A006_AUDIT_ROOT': str(owned),
            'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1',
            'STRUCTURAL_ENV': 'test', 'AUTH_ENABLED': 'false', 'AUTH_DATA_DIR': str(owned / 'auth'),
            'STRUCTURAL_LOG_FILE': str(owned / 'bootstrap.jsonl'), 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
            'SOURCE_STATE_FAULT_CHILD': fault}
        target = str(Path(__file__).resolve()) + '::test_actual_main_unsealed_source_state_or_integrity_fault_stays_uncertain[' + fault + ']'
        result = subprocess.run([sys.executable, '-B', str(packet / 'run_tests.py'),
            '-p', 'controller_mail_observer', '-p', 'a_evidence_resource_observer', target,
            '--basetemp=' + str(owned / 'cases'), '--junitxml=' + str(owned / 'result.xml')],
            cwd=owned, env=environment, capture_output=True, timeout=25)
        (owned / 'result.log').write_bytes(result.stdout + result.stderr)
        assert result.returncode == 0, 'isolated Source state fault failed; retain owned result.log'
        assert b'SOURCE_STATE_UNCERTAINTY:' in result.stdout
        return
    prepared = request.getfixturevalue('prepared')
    main, admission, paths, _ = prepared
    from research import source_supervisor as source
    target = next(i for i, line in enumerate(Path(source.__file__).read_text().splitlines(), 1)
        if "if self._state not in ('STARTING', 'READY'):" in line)
    injected, captured = [], []
    def trace(frame, event, argument):
        if frame.f_code is not source.SourceSupervisor._run_with_budget.__code__: return None
        supervisor = source._REGISTRY.get(id(main.app))
        if (event == 'line' and frame.f_lineno == target and not injected and supervisor is not None
                and threading.current_thread() is supervisor._thread and supervisor._state == 'READY'):
            if fault == 'state': supervisor._state = 'STOPPING'
            elif fault == 'event': supervisor._stop.set()
            else: (paths.STATE_ROOT / 'history.db').chmod(0o640)
            injected.append(True)
        return trace
    old_trace = threading.gettrace(); threading.settrace(trace)
    async def run():
        context = main.lifespan(main.app); await context.__aenter__()
        binding = admission._STATE[id(main.app)]; captured.append(binding)
        end = time.monotonic() + 5
        while binding.supervisor._thread.is_alive() and time.monotonic() < end: await asyncio.sleep(.01)
        assert injected and not binding.supervisor._thread.is_alive()
        assert binding.supervisor._failure == 'WORKER_FAILURE'
        assert binding.supervisor._stop.is_set() == (fault == 'event')
        assert binding.supervisor._main_stop_intent is None and binding.supervisor._source_stop_intent is None
        assert binding.supervisor._errors and all(type(error) is not source._SourceStopping for error in binding.supervisor._errors)
        with pytest.raises(RuntimeError): await context.__aexit__(None, None, None)
        assert binding.source_receipt.state == 'CLEANUP_UNCERTAIN'
        assert binding.source_receipt.reason == 'WORKER_FAILURE'
        assert binding.supervisor._slot is None and binding.supervisor._lease is None
        assert any(witness.parent_fd is not None for witness in binding.witnesses)
        with binding.service.store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 0
        print('SOURCE_STATE_UNCERTAINTY:' + json.dumps({'fault': fault, 'receipt': 'CLEANUP_UNCERTAIN',
            'reason': 'WORKER_FAILURE', 'sealed_stop_signal': False, 'worker_alive': False, 'requests': 0, 'gets': 0}))
    try: asyncio.run(run())
    finally:
        threading.settrace(old_trace)
        for binding in captured:
            assert not binding.supervisor._thread.is_alive()
            governor = binding.supervisor._sec_access
            if governor.fd is not None: os.close(governor.fd)
            for witness in binding.witnesses:
                if witness.parent_fd is not None: witness.close()
