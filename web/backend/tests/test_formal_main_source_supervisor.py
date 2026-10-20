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
                assert await approved_source(client, rid)
                health = await client.get('/api/health')
                assert health.status_code == 200 and health.json()['checks']['source_execute'] == 'ready'
        assert binding.source_receipt.state == 'CLOSED'
        assert binding.source_receipt.supervisor_ref == binding.supervisor.reference
        assert not binding.supervisor._thread.is_alive()
        assert all(witness.parent_fd is None for witness in binding.witnesses)
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
        assert service.retire_source() == 'unavailable'
        from services import formal_admission as admission
        binding = admission._STATE[id(service.app)]
        receipt, deadline = binding.source_receipt, binding.source_deadline
        assert admission.source_closed(binding) and receipt.supervisor_ref == binding.supervisor.reference
        assert service.retire_source() == 'unavailable'
        assert binding.source_receipt is receipt and binding.source_deadline == deadline
        status, after = service.client.request('GET', path)
        assert status == 200 and after == before
        status, health = service.client.request('GET', '/api/health')
        assert status == 200 and health['checks']['base'] == 'ready' and health['checks']['source_execute'] == 'unavailable'
    assert not service.root.exists()


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


if __name__ == '__main__':
    if sys.argv[1:] != ['--interrupted-source-probe']:
        raise SystemExit('owned test probe only')
    _interrupted_source_probe()


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
