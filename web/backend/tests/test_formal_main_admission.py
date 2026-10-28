"""Actual Main lifecycle and native resources; no admission/enable/facts spies."""
import asyncio
from contextlib import closing,contextmanager
from email import policy
from email.parser import BytesParser
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

from web.backend.tests.acceptance.owned_smtp_tls import owned_smtp_tls, StartTLSHandler

BETA = 'https://beta.structural.bytedance.city'


@pytest.fixture
def smtp():
    messages = []
    class Handler(StartTLSHandler):
        timeout = 3
        def handle(self):
            self.wfile.write(b'220 owned SMTP\r\n')
            while True:
                line = self.rfile.readline(8192)
                if not line: return
                verb = line.split(None, 1)[0].upper()
                if self.smtp_tls_command(verb):
                    if self.smtp_tls_failed:return
                    continue
                if verb == b'DATA':
                    self.wfile.write(b'354 send message\r\n'); raw = bytearray()
                    while True:
                        part = self.rfile.readline(8192)
                        if part == b'.\r\n': break
                        if not part or len(raw) + len(part) > 65536: return
                        raw.extend(part)
                    messages.append(BytesParser(policy=policy.default).parsebytes(bytes(raw)))
                    self.wfile.write(b'250 stored\r\n')
                elif verb == b'QUIT':
                    self.wfile.write(b'221 done\r\n'); return
                else: self.wfile.write(b'250 ok\r\n')
    with owned_smtp_tls() as (tls_context,ca_file):
        server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        server.smtp_tls_context = tls_context
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try: yield server.server_address[1], messages
        finally:
            server.shutdown(); server.server_close(); thread.join(4)
            assert not thread.is_alive()


@pytest.fixture
def prepared(tmp_path, monkeypatch, smtp):
    port, messages = smtp
    root = tmp_path.resolve()
    settings = {'STRUCTURAL_ENV': 'prod', 'AUTH_ENABLED': 'true', 'AUTH_SITE_ROLE': 'beta',
        'AUTH_LINK_BASE_URL': BETA, 'AUTH_DATA_DIR': str(root / 'state'),
        'STRUCTURAL_SSO_DATA_DIR': str(root / 'state'), 'AUTH_TRUSTED_PROXY_IPS': '127.0.0.1',
        'JWT_SECRET': secrets.token_urlsafe(48), 'STRUCTURAL_SSO_SECRET': secrets.token_urlsafe(48),
        'STRUCTURAL_PRIVACY_HMAC_KEY': secrets.token_hex(32), 'STRUCTURAL_SHARE_TOKEN_SECRET': secrets.token_urlsafe(48),
        'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': str(port), 'SMTP_FROM_EMAIL': 'sender@example.invalid',
        'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid', 'SMTP_STARTTLS': 'true', 'SMTP_USE_SSL': 'false',
        'SMTP_TIMEOUT_SECONDS': '2', 'AUTH_DEV_MODE': 'false'}
    for key, value in settings.items(): monkeypatch.setenv(key, value)
    for key in ('STRUCTURAL_HISTORY_DB', 'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_DATA_DIR', 'STRUCTURAL_MODEL_PATH',
                'STRUCTURAL_PRECOMPUTED_EMBEDDINGS', 'STRUCTURAL_ARTIFACT_MANIFEST', 'SMTP_USERNAME', 'SMTP_PASSWORD',
                'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY', 'SENTRY_DSN'):
        monkeypatch.delenv(key, raising=False)
    from services import runtime_paths as paths
    monkeypatch.setattr(paths, 'STATE_ROOT', root / 'state')
    monkeypatch.setattr(paths, 'CACHE_ROOT', root / 'cache')
    monkeypatch.setattr(paths, 'LOG_ROOT', root / 'state/logs')
    from services.auth_registration import bootstrap_private_runtime
    assert bootstrap_private_runtime()['research_schema'] == 15
    environment_get = os.environ.get
    def no_provider_read(key, default=None):
        if key in ('OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY'):
            raise AssertionError('basic Main must not inspect provider credentials')
        return environment_get(key, default)
    monkeypatch.setattr(os.environ, 'get', no_provider_read)
    main = importlib.import_module('main')
    from services import formal_admission
    assert main._IS_PROD and main._LAUNCH_FORMAL
    yield main, formal_admission, paths, messages
    formal_admission.retire(main.app)


async def login(client, messages, email='owned-main@example.invalid'):
    at = len(messages)
    response = await client.post('/api/auth/request-link', json={'email': email}, headers={'Origin': BETA})
    assert response.status_code == 200 and 'dev_token' not in response.json()
    assert len(messages) > at
    mail = next(m for m in reversed(messages) if m['To'] == email)
    text = mail.get_body(preferencelist=('plain',)).get_content()
    token = parse_qs(urlsplit(text.strip().split()[-1]).query)['token'][0]
    verified = await client.post('/api/auth/verify', json={'token': token}, headers={'Origin': BETA})
    assert verified.status_code == 200


def envelope(data):
    return {'schema_version': 'structure-research-v1', 'contract_revision': 'b1-candidate-01', 'data': data}


def problem():
    return {'entry': 'phenomenon', 'original_input': '我发现任务集中到达时等待时间明显增加。',
        'objective': '减少等待', 'summary': '受控自述的排队现象', 'variables': [], 'constraints': [], 'unknowns': [], 'confirmed': True}


async def source_ready(main, admission):
    end = time.monotonic() + 8
    while True:
        try:
            admission.require(main.app, 'source_execute')
            return
        except RuntimeError:
            if time.monotonic() >= end:
                raise AssertionError('actual Source supervisor unavailable') from None
            await asyncio.sleep(.02)


@contextmanager
def _native_activity(monkeypatch):
    """Observe real method entries, delegate once, and restore before retirement."""
    from functools import wraps
    from research import plan_native as native
    from services import plan_runtime_transport as runtime
    counts={'balance':0,'prepare':0,'send':0}
    targets=((native.ControlledNativeResource,'balance','balance'),
        (native.ControlledNativeResource,'prepare_post','prepare'),
        (native.ControlledNativePending,'write_first','send'),
        (runtime.NativePlanResource,'balance','balance'),
        (runtime.NativePlanResource,'prepare_post','prepare'),
        (runtime._Pending,'write_first','send'),(runtime._Channel,'send_first','send'),
        (runtime._Channel,'send_remaining','send'))
    with monkeypatch.context() as observe:
        for owner,name,label in targets:
            original=getattr(owner,name)
            def instrument(original,label):
                @wraps(original)
                def entered(*args,**kwargs):
                    counts[label]+=1
                    return original(*args,**kwargs)
                return entered
            entered=instrument(original,label)
            observe.setattr(owner,name,entered)
            assert getattr(owner,name) is entered and entered.__wrapped__ is original
        yield counts


def _native_state_snapshot(store):
    from research.plan_native_financial import NAMES
    tables=(*NAMES,'research_tasks','research_steps','research_funding_accounts',
        'research_project_budgets','research_reservations','research_plan_dispatches')
    with store.transaction() as conn:
        return {name:[dict(row) for row in conn.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in tables}


def test_actual_main_lifespan_register_save_reopen_funding_closed_and_shutdown(prepared,monkeypatch):
    main, admission, paths, messages = prepared
    async def run():
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
            assert (await client.get('/api/research')).status_code == 503
            main.app.state.runtime_admitted = True
            main.app_state['runtime_admitted'] = True
            from research.runtime_profile import FormalResearchProfileFacts
            main.app.state.profile = FormalResearchProfileFacts('core-formal-profile-v1', 'auth-provision-v1', 14, (7, 8, 9), 9, True, True, True, os.getpid())
            with pytest.raises(RuntimeError): admission._Binding(main.app, _factory=admission._FACTORY)
            with pytest.raises(RuntimeError): admission.initialize(main.app)
            assert (await client.get('/api/research')).status_code == 503
            async with main.lifespan(main.app):
                await source_ready(main, admission)
                assert admission.require(main.app, 'research_basic') is None
                alternate = importlib.import_module('web.backend.services.formal_admission')
                assert alternate.require(main.app, 'research_basic') is None
                await login(client, messages)
                favorite = await client.post('/api/favorites/AAPL', headers={'Origin': BETA})
                assert favorite.status_code == 201
                assert (await client.get('/api/favorites')).json()['tickers'] == ['AAPL']
                assert admission.require(main.app, 'research_basic') is None
                reports = await client.get('/api/me/reports')
                assert reports.status_code == 200 and reports.json()['items'] == []
                made = await client.post('/api/research', json=envelope({'problem': problem()}), headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-create'})
                assert made.status_code == 200, made.text
                rid = made.json()['data']['research']['id']
                saved = await client.get('/api/research/' + rid)
                assert saved.status_code == 200
                assert admission.require(main.app, 'source_history') is None
                # The original reader still needs its actual stored task/kind.
                # A missing context is not an empty successful history page.
                absent = await client.get('/api/research/' + rid + '/records')
                assert absent.status_code == 404 and absent.json()['error']['code'] == 'NOT_FOUND'
                blocked = await client.post('/api/research/' + rid + '/source-preview', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'query': 'queue variability'}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-source-closed'})
                assert blocked.status_code == 200  # Preview is not a GET/approval/task.
                with _native_activity(monkeypatch) as activity:
                    quote = await client.post('/api/research/' + rid + '/plan-previews', json={
                        'schema_version': 'structure-research-v1', 'contract_revision': 'funded-plan-v2',
                        'data': {'input_revision': 1, 'expected_research_version': 1, 'observation_source': 'own_observation', 'declaration_status': 'self_declared'}},
                        headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-closed-plan'})
                    assert quote.status_code == 200, quote.text
                    assert quote.json()['data']['can_confirm'] is False and quote.json()['data']['funding_reason'] == 'FUNDING_CLOSED'
                    from api import auth
                    from research import ResearchStore
                    assert quote.json()['data']['cash_evidence']=='not_observed'
                    store=ResearchStore(auth._store());before=_native_state_snapshot(store)
                    confirmation={key:quote.json()['data'][key] for key in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')}
                    confirmation['confirm_outbound']=True
                    rejected=await client.post('/api/research/'+rid+'/plan-approvals',json={
                        'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':confirmation},
                        headers={'Origin':BETA,'Idempotency-Key':'actual-main-closed-confirm'})
                    assert rejected.status_code==503 and rejected.json()['error']['code']=='FUNDING_CLOSED'
                    assert _native_state_snapshot(store)==before
                    assert (await client.get('/api/research/'+rid)).json()==saved.json()
                    assert activity=={'balance':0,'prepare':0,'send':0}
                revised_problem = problem(); revised_problem['original_input'] = '我补充确认任务到达更集中时，等待时间和积压都增加。'
                revised = await client.post('/api/research/' + rid + '/revisions', json=envelope({
                    'expected_revision': 1, 'problem': revised_problem}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-revision'})
                assert revised.status_code == 200, revised.text
                saved = await client.get('/api/research/' + rid)
                assert saved.json()['data']['current_problem']['revision'] == 2
                health = await client.get('/api/health')
                assert health.status_code == 200 and health.json()['status'] == 'limited'
                assert health.json()['checks']['native_planner'] == 'FUNDING_CLOSED'
                assert (await client.get('/api/health?deep=1')).status_code == 503
                assert (await client.get('/api/search?q=owned')).status_code == 503
                assert (await client.post('/api/ask', json={'query': 'owned'})).status_code == 503
                assert admission.require(main.app, 'source_execute') is None
                from api import auth
                with auth._store()._connection() as conn:
                    assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0] == 0
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0] == 0
                async with httpx.AsyncClient(transport=transport, base_url=BETA) as other:
                    assert (await other.get('/api/research/' + rid)).status_code == 401
                    await login(other, messages, 'other-main@example.invalid')
                    assert (await other.get('/api/research/' + rid)).status_code == 404
            assert (await client.get('/api/research/' + rid)).status_code == 503
            async with main.lifespan(main.app):
                assert (await client.get('/api/research/' + rid)).json() == saved.json()
                assert (await client.get('/api/favorites')).json()['tickers'] == ['AAPL']
                deleted = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'Origin': BETA})
                assert deleted.status_code == 200, deleted.text
                assert (await client.get('/api/research/' + rid)).status_code == 401
                await login(client, messages)
                assert (await client.get('/api/research/' + rid)).status_code == 404
                assert (await client.get('/api/favorites')).json()['tickers'] == []
    asyncio.run(run())


def test_registered_user_research_favorites_sso_delete_and_no_inheritance(prepared):
    """The complete registration chain uses the admitted Main and SMTP sink."""
    main, admission, paths, messages = prepared
    from api import auth, sso
    from .test_research_persistence import problem, envelope
    import jwt
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages, 'fresh@example.invalid')
                user = auth._store().user('fresh@example.invalid'); oldgen = user['session_generation']
                oldcookie = client.cookies.get('phase_session')
                response = await client.post('/api/research', json=envelope({'problem': problem()}), headers={'origin': BETA, 'idempotency-key': 'registration-save'})
                assert response.status_code == 200, response.text
                rid = response.json()['data']['research']['id']
                assert (await client.get('/api/research/' + rid)).status_code == 200
                assert (await client.post('/api/favorites/AAPL', headers={'origin': BETA})).status_code == 201
                assert (await client.get('/api/favorites')).json()['tickers'] == ['AAPL']
                start = await client.get('/api/sso/start', follow_redirects=False)
                assert start.status_code == 303, start.text
                binding = jwt.decode(start.cookies.get(sso._STATE_COOKIE), os.environ['STRUCTURAL_SSO_SECRET'], algorithms=['HS256'], audience='structural-beta-start', issuer=BETA)
                issued = await client.post('/api/sso/issue', json={'audience': 'structural-beta', 'state': binding['state'], 'nonce': binding['nonce']}, headers={'origin': BETA})
                assert issued.status_code == 200, issued.text
                code = issued.json()['code']
                exchanged = await client.post('/api/sso/exchange', json={'code': code, 'state': binding['state']}, headers={'origin': BETA})
                assert exchanged.status_code == 200, exchanged.text
                assert (await client.post('/api/sso/exchange', json={'code': code, 'state': binding['state']}, headers={'origin': BETA})).status_code == 400
                deleted = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'origin': BETA})
                assert deleted.status_code == 200, deleted.text
                assert auth._store().user(user['email']) is None
                await login(client, messages, 'fresh@example.invalid')
                assert auth._store().user(user['email'])['session_generation'] != oldgen
                assert (await client.get('/api/research/' + rid)).status_code == 404
                assert (await client.get('/api/favorites')).json()['tickers'] == []
                exported = auth._store().export_account_data(user['email'])
                assert all(row['kind'] == 'new_account' for row in exported['registration_events'])
                serialized = json.dumps(exported)
                for private in ('token_hash', 'gate_id', 'lock_ino', 'database_binding', oldgen):
                    assert private not in serialized
    asyncio.run(run())


async def _exchange_main_sso(client):
    import jwt
    from api import sso
    started = await client.get('/api/sso/start', follow_redirects=False)
    assert started.status_code == 303, started.text
    state = jwt.decode(started.cookies.get(sso._STATE_COOKIE), os.environ['STRUCTURAL_SSO_SECRET'], algorithms=['HS256'], audience='structural-beta-start', issuer=BETA)
    issued = await client.post('/api/sso/issue', json={'audience': 'structural-beta', 'state': state['state'], 'nonce': state['nonce']}, headers={'origin': BETA})
    assert issued.status_code == 200, issued.text
    exchanged = await client.post('/api/sso/exchange', json={'code': issued.json()['code'], 'state': state['state']}, headers={'origin': BETA})
    assert exchanged.status_code == 200, exchanged.text
    assert not client.cookies.get('phase_session')
    return client.cookies.get(sso._BETA_SESSION_COOKIE)


@pytest.mark.parametrize('resources', ['none', 'question', 'draft', 'formula'])
def test_actual_formal_delete_protects_every_job_and_erases_registration_in_research_txn(prepared, monkeypatch, resources):
    main, _, _, messages = prepared
    from api import auth
    from .test_research_formula_lifecycle import formula_problem

    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages, 'fresh@example.invalid')
                old_cookie = client.cookies.get('phase_session')
                user = auth._store().user('fresh@example.invalid')
                rid = None
                if resources != 'none':
                    data = formula_problem()
                    if resources == 'question':
                        data.pop('formula_draft')
                    result = await client.post('/api/research', json=envelope({'problem': data}), headers={'origin': BETA, 'idempotency-key': 'account-bridge-create'})
                    assert result.status_code == 200, result.text
                    body = result.json()['data']
                    rid = body['research']['id']
                    if resources == 'formula':
                        snapshot = body['current_problem']['formula_snapshot']
                        checked = await client.post(f'/api/research/{rid}/formula-checks', json=envelope({'input_revision': 1, 'expected_research_version': body['research_version'], 'formula_digest': snapshot['formula_digest'], 'confirm_formula_input': True}), headers={'origin': BETA, 'idempotency-key': 'account-bridge-check'})
                        assert checked.status_code == 200, checked.text
                from research.service import ResearchService
                original = ResearchService.erase_research_locked
                observed = []

                def erase(service, job_id, **kwargs):
                    result = original(service, job_id, **kwargs)
                    with service.store.transaction() as conn:
                        job = conn.execute('SELECT * FROM auth_deletion_jobs WHERE id=?', (job_id,)).fetchone()
                        rows = conn.execute('SELECT * FROM auth_registration_operations WHERE owner_key=?', (job['owner_key'],)).fetchall()
                        assert job['origin_version'] == 'authenticated-delete-v1'
                        assert rows and all((row['state'] == 'closed' and row['target_generation'] is None and (row['token_hash'] is None) for row in rows))
                        assert conn.execute('SELECT lifecycle FROM auth_users WHERE email=?', (user['email'],)).fetchone()[0] == 'deleting'
                    observed.append(True)
                    return result
                monkeypatch.setattr(ResearchService, 'erase_research_locked', erase)
                deleted = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'origin': BETA})
                assert deleted.status_code == 200, deleted.text
                assert observed == [True] and auth._store().user(user['email']) is None
                with auth._store()._connection() as conn:
                    assert conn.execute('SELECT origin_version,state FROM auth_deletion_jobs').fetchone()[:] == ('authenticated-delete-v1', 'completed')
                    assert conn.execute('SELECT count(*) FROM research_formula_revisions').fetchone()[0] == 0
                await login(client, messages, 'fresh@example.invalid')
                assert auth._store().user(user['email'])['session_generation'] != user['session_generation']
                if rid:
                    assert (await client.get('/api/research/' + rid)).status_code == 404
                client.cookies.clear()
                client.cookies.set('phase_session', old_cookie, domain='beta.structural.bytedance.city', path='/')
                assert (await client.get('/api/auth/me')).status_code == 401
    asyncio.run(run())


def test_sso_delete_proof_does_not_grant_formula_or_paid_direct_session_access(prepared, monkeypatch):
    main, _, _, messages = prepared
    from api import auth
    from .test_research_formula_lifecycle import formula_problem

    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                await login(client, messages, 'fresh@example.invalid')
                response = await client.post('/api/research', json=envelope({'problem': formula_problem()}), headers={'origin': BETA, 'idempotency-key': 'direct-only-create'})
                assert response.status_code == 200, response.text
                body = response.json()['data']
                rid = body['research']['id']
                snapshot = body['current_problem']['formula_snapshot']
                await _exchange_main_sso(client)
                assert (await client.get('/api/auth/me')).status_code == 200
                assert (await client.get('/api/research/' + rid)).status_code == 401
                for path, data in [('formula-checks', {'input_revision': 1, 'expected_research_version': body['research_version'], 'formula_digest': snapshot['formula_digest'], 'confirm_formula_input': True}), ('paid-previews', {})]:
                    refused = await client.post(f'/api/research/{rid}/{path}', json=envelope(data), headers={'origin': BETA, 'idempotency-key': 'sso-direct-only'})
                    assert refused.status_code == 401, refused.text
                with auth._store()._connection() as conn:
                    assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0] == 0
                    assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0] == 0
    asyncio.run(run())


def test_registration_erase_fault_rolls_back_with_research_then_same_job_resumes(prepared, monkeypatch):
    main, _, _, messages = prepared
    from api import auth
    from research import ResearchStore
    from .test_research_formula_lifecycle import formula_problem
    import sqlite3

    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                from services import auth_registration as registration
                from research import ResearchService
                await login(client, messages, 'fresh@example.invalid')
                response = await client.post('/api/research', json=envelope({'problem': formula_problem()}), headers={'origin': BETA, 'idempotency-key': 'atomic-erase-create'})
                assert response.status_code == 200, response.text
                rid = response.json()['data']['research']['id']
                original = registration.erase_registration_for_job
                observed = []

                def fail(conn, **kwargs):
                    original(conn, **kwargs)
                    assert conn.execute("SELECT count(*) FROM auth_registration_operations WHERE state='closed'").fetchone()[0] == 1
                    observed.append(True)
                    raise sqlite3.OperationalError('owned after-registration-erase fault')
                with monkeypatch.context() as fault:
                    fault.setattr(registration, 'erase_registration_for_job', fail)
                    result = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'origin': BETA})
                    assert result.status_code == 503, result.text
                assert observed == [True]
                store = ResearchStore(auth._store())
                service = ResearchService(store)
                with store.transaction() as conn:
                    job = dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())
                    assert job['state'] == 'pending' and job['research_erased'] == 0 and (job['origin_version'] == 'authenticated-delete-v1')
                    assert conn.execute("SELECT state,target_generation FROM auth_registration_operations WHERE kind='new_account'").fetchone()[:] == ('finalized', job['session_generation'])
                    assert conn.execute('SELECT research_id FROM research_formula_revisions').fetchone()[0] == rid
                    assert conn.execute('SELECT lifecycle FROM auth_users').fetchone()[0] == 'deleting'
                with service.authorization.owner_gate_id(job['gate_id']) as lease:
                    resumed = auth._run_account_deletion_locked(service, job['id'], owner_lease=lease)
                    assert resumed['removed']['research']['researches'] == 1
                assert auth._store().user('fresh@example.invalid') is None
    asyncio.run(run())


@pytest.mark.parametrize('profile', ['PROD', ' prod '])
def test_noncanonical_formal_launcher_refuses_before_dotenv(prepared, profile):
    main, _, _, _ = prepared
    environment = dict(os.environ, STRUCTURAL_ENV=profile)
    environment['PYTHONPATH'] = os.pathsep.join((str(Path(main.__file__).parent), environment.get('PYTHONPATH', '')))
    result = subprocess.run([sys.executable, '-B', '-c', 'import main'], env=environment,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert 'formal Main requires canonical production profile' in result.stderr


@pytest.mark.parametrize('fault', ['env', 'inode', 'pid'])
def test_real_main_binding_rejects_late_profile_resource_and_pid_changes(prepared, monkeypatch, fault):
    main, admission, paths, _ = prepared
    async def run():
        async with main.lifespan(main.app):
            assert admission.require(main.app, 'research_basic') is None
            # This existing test isolates base-profile drift. Retire Source
            # through its real native lifecycle; no flag/admission override.
            binding = admission._STATE[id(main.app)]
            admission.close_source(binding, deadline_monotonic=time.monotonic() + 20)
            assert admission.source_closed(binding)
            with monkeypatch.context() as drift:
                if fault == 'env': drift.setenv('STRUCTURAL_ENV', 'dev')
                elif fault == 'pid':
                    actual = os.getpid(); drift.setattr(os, 'getpid', lambda: actual + 100000)
                else:
                    db = paths.STATE_ROOT / 'auth.sqlite3'; replacement = db.with_suffix('.replacement')
                    replacement.write_bytes(db.read_bytes()); replacement.chmod(0o600); replacement.replace(db)
                with pytest.raises(RuntimeError): admission.require(main.app, 'research_basic')
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA) as client:
                    assert (await client.get('/api/research')).status_code == 503
    asyncio.run(run())


@pytest.mark.parametrize('fault', ['missing', 'hook', 'partial-search', 'auth-config', 'sso-secret', 'share-secret'])
def test_actual_startup_failure_never_publishes_or_keeps_directory_fds(prepared, monkeypatch, fault):
    main, admission, paths, _ = prepared
    if fault == 'missing': (paths.STATE_ROOT / 'sso_replay.sqlite3').unlink()
    elif fault == 'hook':
        from services import auth_registration
        monkeypatch.setattr(auth_registration, 'install_hook', lambda conn: None)
    elif fault == 'partial-search': monkeypatch.setenv('STRUCTURAL_MODEL_PATH', str(paths.CACHE_ROOT / 'not-an-artifact'))
    elif fault == 'sso-secret': monkeypatch.delenv('STRUCTURAL_SSO_SECRET')
    elif fault == 'share-secret': monkeypatch.delenv('STRUCTURAL_SHARE_TOKEN_SECRET')
    else: monkeypatch.delenv('SMTP_HOST')
    async def run():
        entered = False
        with pytest.raises(Exception):
            async with main.lifespan(main.app): entered = True
        assert not entered
        with pytest.raises(RuntimeError): admission.require(main.app, 'research_basic')
    asyncio.run(run())


def test_uninitialized_actual_main_http_and_websocket_do_not_receive_body(prepared):
    main, _, _, _ = prepared
    async def run():
        async def receive(): raise AssertionError('unadmitted body was read')
        for kind in ('http', 'websocket'):
            messages = []
            async def send(value): messages.append(value)
            scope = {'type': kind, 'path': '/api/research', 'raw_path': b'/api/research', 'root_path': '',
                'method': 'POST', 'headers': [], 'query_string': b'', 'scheme': 'https',
                'server': ('beta.structural.bytedance.city', 443), 'client': ('127.0.0.1', 1),
                'http_version': '1.1', 'subprotocols': []}
            await main.app(scope, receive, send)
            if kind == 'http':
                assert messages[0]['status'] == 503
                assert (b'cache-control', b'no-store') in messages[0]['headers']
            else: assert messages == [{'type': 'websocket.close', 'code': 1013}]
    asyncio.run(run())


def _shutdown_directory_retirement_fault_probe(owned_root):
    from pathlib import Path
    with pytest.MonkeyPatch.context() as monkeypatch:
        smtp_fixture=smtp.__wrapped__()
        try:
            actual_smtp=next(smtp_fixture)
            prepared_fixture=prepared.__wrapped__(Path(owned_root),monkeypatch,actual_smtp)
            try:
                prepared_value=next(prepared_fixture)
                main, admission, paths, _ = prepared_value
                close = paths.PrivateAuthFile.close; closed = []
                held = []
                async def run():
                    with pytest.raises(RuntimeError):
                        async with main.lifespan(main.app):
                            held.extend(admission._STATE[id(main.app)].witnesses)
                            def failure(value):
                                close(value)
                                if value in held:
                                    closed.append(True)
                                    raise OSError('owned close-after-retirement fault')
                            monkeypatch.setattr(paths.PrivateAuthFile, 'close', failure)
                    with pytest.raises(RuntimeError): admission.require(main.app, 'research_basic')
                asyncio.run(run())
                assert closed and held and all(w.parent_fd is None for w in held)
            finally:
                with pytest.raises(StopIteration):next(prepared_fixture)
            from research import native_plan_supervisor
            scope=native_plan_supervisor._CONTEXTS.get(id(prepared_value[0].app))
            assert type(scope) is native_plan_supervisor.MainStartupScope and scope.binding.app is prepared_value[0].app
        finally:
            with pytest.raises(StopIteration):next(smtp_fixture)


def test_shutdown_attempts_all_directory_retirements_even_after_one_close_error(tmp_path):
    from .research_process_fixture import _run_owned_probe
    source=Path(__file__).resolve().parents[3]
    program=("import sys\nfrom pathlib import Path\n"
        +"sys.path[:0]="+repr([str(source/'web/backend'),str(source)])+"\n"
        +"from web.backend.tests.test_formal_main_admission import _shutdown_directory_retirement_fault_probe\n"
        +"_shutdown_directory_retirement_fault_probe(Path("+repr(str(tmp_path))+"))\n")
    result=_run_owned_probe(program,cwd=tmp_path)
    assert result.returncode==0,result.stderr


@pytest.mark.skipif(not hasattr(os, 'fork'), reason='actual fork requires POSIX')
def test_actual_fork_cannot_reuse_parent_main_binding(prepared):
    main, admission, _, _ = prepared
    async def run():
        async with main.lifespan(main.app):
            assert admission.require(main.app, 'research_basic') is None
            pid = os.fork()
            if pid == 0:
                try:
                    admission.require(main.app, 'research_basic')
                except RuntimeError:
                    os._exit(0)
                except BaseException:
                    os._exit(3)
                os._exit(2)
            finished = False
            try:
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    actual, status = os.waitpid(pid, os.WNOHANG)
                    if actual == pid:
                        finished = True
                        assert os.waitstatus_to_exitcode(status) == 0
                        break
                    await asyncio.sleep(.01)
                assert finished
            finally:
                if not finished:
                    os.kill(pid, 9); os.waitpid(pid, 0)
            assert admission.require(main.app, 'research_basic') is None
    asyncio.run(run())


@pytest.fixture
def history_source():
    return Path(__file__).resolve().parents[3]


def test_actual_main_reads_migrated_source_history_and_enforces_current_actor(tmp_path, monkeypatch, smtp, history_source):
    from web.backend.tests.acceptance.source_history_fixture import prepared_source_history
    source_root = history_source
    owned_root = tmp_path / 'source-history'
    port, messages = smtp
    # This context precedes all parent signing configuration. It prepares only
    # the reviewed old13 producer and maintenance, never current Main readiness.
    with prepared_source_history(source_root, owned_root, target_revision=False) as seed:
        settings = {'STRUCTURAL_SHARE_TOKEN_SECRET': secrets.token_urlsafe(48),
            'SMTP_HOST': '127.0.0.1', 'SMTP_PORT': str(port), 'SMTP_FROM_EMAIL': 'sender@example.invalid',
            'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid', 'SMTP_STARTTLS': 'true',
            'SMTP_USE_SSL': 'false', 'SMTP_TIMEOUT_SECONDS': '2'}
        for key, value in settings.items(): monkeypatch.setenv(key, value)
        for key in ('STRUCTURAL_HISTORY_DB', 'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_DATA_DIR',
                    'STRUCTURAL_MODEL_PATH', 'STRUCTURAL_PRECOMPUTED_EMBEDDINGS', 'STRUCTURAL_ARTIFACT_MANIFEST',
                    'SMTP_USERNAME', 'SMTP_PASSWORD', 'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY', 'SENTRY_DSN'):
            monkeypatch.delenv(key, raising=False)
        main = importlib.import_module('main')
        from services import formal_admission as admission
        assert main._IS_PROD and seed.schema_version == 15
        assert seed.source_input_revision == seed.current_input_revision == 1
        async def run():
            transport = httpx.ASGITransport(app=main.app)
            path = '/api/research/' + seed.research_id
            async with httpx.AsyncClient(transport=transport, base_url=BETA) as client:
                async with main.lifespan(main.app):
                    await source_ready(main, admission)
                    await login(client, messages, seed.email)
                    assert admission.require(main.app, 'source_history') is None
                    original = {}
                    for kind in ('sources', 'excerpts', 'claims', 'reports'):
                        response = await client.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': kind})
                        assert response.status_code == 200, response.text
                        items = response.json()['data']['items']
                        assert items and all(item['input_revision'] == 1 and item['task_id'] == seed.source_task_id for item in items)
                        original[kind] = items
                    excerpts = {item['id']: item for item in original['excerpts']}
                    for ref in seed.excerpt_refs:
                        item = excerpts[ref['excerpt_id']]
                        assert (item['source_revision'], item['text_digest'], item['start'], item['end']) == (
                            ref['source_revision'], ref['content_digest'], ref['start'], ref['end'])
                        assert item['quote']
                    for item in original['sources']:
                        assert item['accessed_at'] == seed.acquired_at and item['execution_mode'] == 'offline_probe'
                        assert item['access'] == 'body_retrieved' and item['license_note']
                        assert item['revision'] == 1 and item['read_scope'] == 'author_narrative_subset'
                    report = original['reports'][0]
                    assert not report['model_analysis_ran'] and not report['statistics_ran']
                    assert report['execution_mode'] == 'offline_probe' and report['limitations']
                    assert all(ref['revision'] == 1 and ref['access'] == 'body_retrieved' for ref in report['source_revisions'])
                    revised = await client.post(path + '/revisions', json=envelope({'expected_revision': 1, 'problem': problem()}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-source-revision'})
                    assert revised.status_code == 200, revised.text
                    current = await client.get(path)
                    assert current.status_code == 200 and current.json()['data']['current_problem']['revision'] == 2
                    for kind, items in original.items():
                        reopened = await client.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': kind})
                        assert reopened.status_code == 200 and reopened.json()['data']['items'] == items
                    async with httpx.AsyncClient(transport=transport, base_url=BETA) as other:
                        await login(other, messages, 'other-source-history@example.invalid')
                        denied = await other.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': 'excerpts'})
                        assert denied.status_code == 404 and 'data' not in denied.json()
                    blocked = await client.post(path + '/source-preview', json=envelope({
                        'input_revision': 2, 'expected_research_version': current.json()['data']['research']['version'], 'query': 'queue theory'}),
                        headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-history-no-execute'})
                    assert blocked.status_code == 200
                    old_session = httpx.Cookies(client.cookies)
                    logout = await client.post('/api/auth/logout', headers={'Origin': BETA})
                    assert logout.status_code == 200
                    async with httpx.AsyncClient(transport=transport, base_url=BETA, cookies=old_session) as revoked:
                        denied = await revoked.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': 'excerpts'})
                        assert denied.status_code == 401 and 'data' not in denied.json()
                    await login(client, messages, seed.email)
                assert (await client.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': 'excerpts'})).status_code == 503
                async with main.lifespan(main.app):
                    for kind, items in original.items():
                        reopened = await client.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': kind})
                        assert reopened.status_code == 200 and reopened.json()['data']['items'] == items
                    old_session = httpx.Cookies(client.cookies)
                    deleted = await client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'Origin': BETA})
                    assert deleted.status_code == 200, deleted.text
                    async with httpx.AsyncClient(transport=transport, base_url=BETA, cookies=old_session) as revoked:
                        denied = await revoked.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': 'excerpts'})
                        assert denied.status_code == 401 and 'data' not in denied.json()
                    await login(client, messages, seed.email)
                    denied = await client.get(path + '/records', params={'task_id': seed.source_task_id, 'kind': 'excerpts'})
                    assert denied.status_code == 404 and 'data' not in denied.json()
                    assert admission.require(main.app, 'source_execute') is None
        asyncio.run(run())
        with pytest.raises(RuntimeError): admission.require(main.app, 'research_basic')
    assert not owned_root.exists()


def test_actual_current_main_native_json_authority_and_foreign_types_are_closed(prepared,monkeypatch):
    main,admission,paths,messages=prepared
    from api import auth
    from research import ResearchStore,plan_native as native
    from research.authorization import AccountIdentity
    from research.errors import ResearchError
    async def run():
        async with main.lifespan(main.app):
            assert admission.require(main.app,'research_basic') is None
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'native-json-owner-question'})
                assert made.status_code==200,made.text
                rid=made.json()['data']['research']['id']
                saved=await client.get('/api/research/'+rid);assert saved.status_code==200
                claims=auth._decode_jwt(client.cookies.get('phase_session'))
                actor=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])
                store=ResearchStore(auth._store())
                with store.transaction() as conn:
                    ResearchStore._check_v15(conn)
                    assert conn.execute('SELECT session_generation FROM auth_users WHERE email=?',(actor.email,)).fetchone()[0]==actor.generation
                before=_native_state_snapshot(store)
                with _native_activity(monkeypatch) as activity:
                    with pytest.raises(ResearchError) as closed:native.bootstrap_native_owner_authority(store)
                    assert closed.value.code=='FUNDING_CLOSED'
                    with pytest.raises((TypeError,PermissionError)):native.issue_native_provision(store,{'approved':True,'owner':actor.email})
                    with pytest.raises(TypeError):native.OwnerFundingAuthorityLease(_factory=object())
                    with pytest.raises((TypeError,PermissionError)):native.open_plan_resource({'mode':'native_live','runtime_digest':'a'*64})
                    assert activity=={'balance':0,'prepare':0,'send':0}
                assert _native_state_snapshot(store)==before
                assert (await client.get('/api/research/'+rid)).json()==saved.json()
    asyncio.run(run())


def test_actual_current15_history_native_sql_owner_and_positive_unknown_debt_guards(tmp_path,monkeypatch):
    from copy import deepcopy
    from types import SimpleNamespace
    from fastapi.testclient import TestClient
    from .test_research_method_drafts import _draft_history_stack
    from .test_private_registration import link,verify
    from .test_research_paid_producers import identity
    from research import ResearchStore,ResearchService,ResearchRunner,plan_native_financial as finance,plan_native_runtime as flow
    from research.authorization import AuthorizationGate
    from research.financial_guard import install_default_hook
    with _draft_history_stack(tmp_path,monkeypatch) as stack:
        client,root,mail,history=stack
        import main
        from api import auth
        from services import formal_admission
        assert formal_admission.require(main.app,'research_basic') is None
        store=ResearchStore(auth._store());owner=identity(client)
        with store.transaction() as conn:
            ResearchStore._check_v15(conn)
            rows=conn.execute('SELECT * FROM '+flow.RUNS+" WHERE state='unknown' AND cost_state='unknown'").fetchall()
            assert len(rows)==1
            unknown=dict(rows[0])
            account=dict(conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(unknown['account_id'],)).fetchone())
            assert account['held']>0 and account['upper_booked']>0 and unknown['upper']>0
        material_inode=(store.path.stat().st_dev,store.path.stat().st_ino)
        with _native_activity(monkeypatch) as activity:
            baseline=_native_state_snapshot(store)
            # A: both real, nonempty connection paths retain their native SQL gates.
            for connection in ('ordinary','private'):
                scope=closing(sqlite3.connect(store.path,isolation_level=None)) if connection=='ordinary' else store.auth_store._connection()
                with scope as conn:
                    conn.row_factory=sqlite3.Row;install_default_hook(conn);conn.execute('BEGIN IMMEDIATE')
                    assert conn.execute('SELECT id FROM '+finance.NAMES[0]).fetchone() is not None
                    assert conn.execute('SELECT id FROM '+flow.RUNS+' WHERE id=?',(unknown['id'],)).fetchone() is not None
                    for sql,args in (("UPDATE research_plan_native_funding SET state='blocked'",()),
                        ("UPDATE research_plan_native_runs SET state='consumed' WHERE id=?",(unknown['id'],)),
                        ("UPDATE research_funding_accounts SET held=3 WHERE id=?",(account['id'],))):
                        with pytest.raises(sqlite3.Error):conn.execute(sql,args)
                    conn.rollback()
                assert _native_state_snapshot(store)==baseline
            # B: an actual unrelated registered actor is not a funding producer.
            other=TestClient(main.app,base_url=BETA)
            try:
                assert verify(other,link(other,mail,'other-native-owner@example.invalid')).status_code==200
                made=other.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'history-other-native-owner'})
                assert made.status_code==200,made.text
                other_rid=made.json()['data']['research']['id'];other_actor=identity(other)
                for writer in ('fake','unrelated_owner','actual_owner_noop','money_wrapper_noop'):
                    actor=other_actor if writer=='unrelated_owner' else owner
                    pid=ResearchService(store)._principal(actor)
                    before=_native_state_snapshot(store)
                    with AuthorizationGate(store).owner_gate(pid) as actual,store.transaction(write=True) as conn:
                        current=conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(account['id'],)).fetchone()
                        assert current['held']>0 and current['upper_booked']>0
                        lease=SimpleNamespace(identity=(1,2,3)) if writer=='fake' else actual
                        with pytest.raises((PermissionError,TypeError)):
                            if writer=='money_wrapper_noop':flow._money(conn,lease,current,0,-flow.UPPER,lambda:None)
                            else:finance._write(conn,lease,finance.MONEY,current['id'],{'upper_booked':0,'version':current['version']+1},lambda:None,_factory=finance._FACTORY)
                        assert dict(conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(account['id'],)).fetchone())==dict(current)
                        conn.rollback()
                    assert _native_state_snapshot(store)==before
                # D: real current Owner/ref/digests, not stale or malformed confirmation.
                for actor_client,rid,label in ((client,history['research_id'],'owner'),(other,other_rid,'other')):
                    question=actor_client.get('/api/research/'+rid);assert question.status_code==200
                    body=question.json()['data']
                    preview=actor_client.post('/api/research/'+rid+'/plan-previews',json={'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':{
                        'input_revision':body['current_problem']['revision'],'expected_research_version':body['research_version'],'observation_source':'own_observation','declaration_status':'self_declared'}},headers={'Origin':BETA,'Idempotency-Key':'history-closed-preview-'+label})
                    assert preview.status_code==200,preview.text
                    quote=preview.json()['data']
                    assert quote['can_confirm'] is False and quote['funding_reason']=='FUNDING_CLOSED' and quote['cash_evidence']=='not_observed'
                    confirmation={key:quote[key] for key in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};confirmation['confirm_outbound']=True
                    before=_native_state_snapshot(store)
                    rejected=actor_client.post('/api/research/'+rid+'/plan-approvals',json={'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':confirmation},headers={'Origin':BETA,'Idempotency-Key':'history-closed-confirm-'+label})
                    assert rejected.status_code==503 and rejected.json()['error']['code']=='FUNDING_CLOSED'
                    assert _native_state_snapshot(store)==before
                    assert actor_client.get('/api/research/'+rid).json()==question.json()
                # C: genuine positive UNKNOWN debt, no retry/send, and terminal SQL constraints.
                before=_native_state_snapshot(store)
                result=ResearchRunner(store).run_once(unknown['task_id'])
                assert result['data']['state']=='pending_reconciliation'
                assert _native_state_snapshot(store)==before
                with closing(sqlite3.connect(store.path,isolation_level=None)) as conn:
                    conn.create_function('research_plan_native_write_allowed',4,lambda *_:1)
                    for assignment in ("state='consumed'","cost_state='unreserved'","upper=0","receipt_json='{}'","result_json='{}'","safe_code='saved'"):
                        with pytest.raises(sqlite3.IntegrityError):conn.execute('UPDATE '+flow.RUNS+' SET '+assignment+',version=version+1 WHERE id=?',(unknown['id'],))
                    conn.execute('UPDATE '+flow.RUNS+" SET cleanup_state='uncertain',version=version+1 WHERE id=?",(unknown['id'],))
                expected=deepcopy(before)
                for row in expected[flow.RUNS]:
                    if row['id']==unknown['id']:row['cleanup_state']='uncertain';row['version']+=1
                assert _native_state_snapshot(store)==expected
                assert ResearchRunner(store).run_once(unknown['task_id'])['data']['state']=='pending_reconciliation'
                assert _native_state_snapshot(store)==expected
                with store.transaction() as conn:
                    current=conn.execute('SELECT held,upper_booked FROM research_funding_accounts WHERE id=?',(account['id'],)).fetchone()
                    assert tuple(current)==(account['held'],account['upper_booked']) and current['held']>0 and current['upper_booked']>0
                assert activity=={'balance':0,'prepare':0,'send':0}
                print('NATIVE_HISTORY_GUARDS:'+json.dumps({'schema':15,'held_positive':True,'upper_positive':True,'A_connections':2,'B_writers':4,'C_unknown_preserved':True,'D_real_closed_actors':2,'native_balance_prepare_send':[0,0,0]}))
            finally:other.close()
        assert (store.path.stat().st_dev,store.path.stat().st_ino)==material_inode
