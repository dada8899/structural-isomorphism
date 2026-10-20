"""Actual Main lifecycle and native resources; no admission/enable/facts spies."""
import asyncio
from email import policy
from email.parser import BytesParser
import hashlib
import importlib
import json
import os
from pathlib import Path
import secrets
import socketserver
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest

BETA = 'https://beta.structural.bytedance.city'


@pytest.fixture
def smtp():
    messages = []
    class Handler(socketserver.StreamRequestHandler):
        timeout = 3
        def handle(self):
            self.wfile.write(b'220 owned SMTP\r\n')
            while True:
                line = self.rfile.readline(8192)
                if not line: return
                verb = line.split(None, 1)[0].upper()
                if verb in (b'EHLO', b'HELO'):
                    self.wfile.write(b'250-owned\r\n250 SIZE 65536\r\n')
                elif verb == b'DATA':
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
    server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
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
        'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid', 'SMTP_STARTTLS': 'false', 'SMTP_USE_SSL': 'false',
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
    assert bootstrap_private_runtime()['research_schema'] == 14
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


def test_actual_main_lifespan_register_save_reopen_funding_closed_and_shutdown(prepared):
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
                quote = await client.post('/api/research/' + rid + '/plan-previews', json={
                    'schema_version': 'structure-research-v1', 'contract_revision': 'funded-plan-v2',
                    'data': {'input_revision': 1, 'expected_research_version': 1, 'observation_source': 'own_observation', 'declaration_status': 'self_declared'}},
                    headers={'Origin': BETA, 'Idempotency-Key': 'actual-main-closed-plan'})
                assert quote.status_code == 200, quote.text
                assert quote.json()['data']['can_confirm'] is False and quote.json()['data']['funding_reason'] == 'FUNDING_CLOSED'
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


def test_shutdown_attempts_all_directory_retirements_even_after_one_close_error(prepared, monkeypatch):
    main, admission, paths, _ = prepared
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
            'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid', 'SMTP_STARTTLS': 'false',
            'SMTP_USE_SSL': 'false', 'SMTP_TIMEOUT_SECONDS': '2'}
        for key, value in settings.items(): monkeypatch.setenv(key, value)
        for key in ('STRUCTURAL_HISTORY_DB', 'STRUCTURAL_FAVORITES_PATH', 'STRUCTURAL_DATA_DIR',
                    'STRUCTURAL_MODEL_PATH', 'STRUCTURAL_PRECOMPUTED_EMBEDDINGS', 'STRUCTURAL_ARTIFACT_MANIFEST',
                    'SMTP_USERNAME', 'SMTP_PASSWORD', 'OPENROUTER_API_KEY', 'DEEPSEEK_API_KEY', 'SENTRY_DSN'):
            monkeypatch.delenv(key, raising=False)
        main = importlib.import_module('main')
        from services import formal_admission as admission
        assert main._IS_PROD and seed.schema_version == 14
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
