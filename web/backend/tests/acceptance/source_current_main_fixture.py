"""Explicit Source acceptance support; importing this module starts nothing.

The recovery subprocess receives only synthetic runtime settings over stdin.
It opens the existing fresh-15 specimen, never bootstraps/seeds/migrates it.
Neither phase installs a Source worker, resolver, provider TLS context or receipt.
"""
import asyncio
from contextlib import contextmanager
import hashlib
import importlib
import json
import os
from pathlib import Path
import signal
import sys

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA, login, smtp as native_smtp


KINDS = ('sources', 'excerpts', 'claims', 'reports')
SCIENCE_GUARD_SHA256 = 'e2ac612dfd5cc3e029ab7037d7035ea9184afd674823ebb398d4aa03f722cf98'
SETTING_KEYS = (
    'STRUCTURAL_ENV', 'AUTH_ENABLED', 'AUTH_SITE_ROLE', 'AUTH_LINK_BASE_URL',
    'AUTH_DATA_DIR', 'STRUCTURAL_SSO_DATA_DIR', 'AUTH_TRUSTED_PROXY_IPS',
    'JWT_SECRET', 'STRUCTURAL_SSO_SECRET', 'STRUCTURAL_PRIVACY_HMAC_KEY',
    'STRUCTURAL_SHARE_TOKEN_SECRET', 'AUTH_DEV_MODE', 'SSL_CERT_FILE',
)


@contextmanager
def owned_smtp():
    guard = sys.modules.get('main_smtp_task_guard')
    assert guard is not None
    assert hashlib.sha256(Path(guard.__file__).read_bytes()).hexdigest() == SCIENCE_GUARD_SHA256
    mail = native_smtp.__wrapped__()
    port = None
    try:
        port, messages = next(mail)
        native = mail.gi_frame.f_locals
        assert native['server'].socket.getsockname() == ('127.0.0.1', port)
        assert native['thread'].is_alive() and guard.owned_fixture_port(port)
        guard.OWNED_MAIN_SMTP_PORTS.add(port)
        yield port, messages
    finally:
        if port is not None:
            guard.OWNED_MAIN_SMTP_PORTS.discard(port)
        mail.close()


@pytest.fixture
def smtp():
    with owned_smtp() as value:
        yield value


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True,
                     separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def require_ok(response):
    # Do not include response bodies, cookies, headers or mail tokens in logs.
    assert response.status_code == 200, 'owned HTTP operation did not return 200'
    return response.json()


def stored_facts(rid, tid, *, include_records=True):
    """SELECT-only observation through the actual AuthStore connection."""
    from api import auth
    with auth._store()._connection() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 15
        task = conn.execute('SELECT execution,policy_revision,execution_mode FROM research_tasks WHERE id=? AND research_id=?', (tid, rid)).fetchone()
        assert task is not None
        requests = [dict(row) for row in conn.execute(
            'SELECT id,ordinal,semantic,target_digest,outcome,http_status,execution_closed,started_at,ended_at FROM research_source_requests WHERE task_id=? ORDER BY ordinal', (tid,))]
        rows = conn.execute('SELECT id,kind,payload,payload_digest,raw,extracted,discovery FROM research_evidence_objects WHERE research_id=? AND task_id=? ORDER BY kind,id', (rid, tid)).fetchall() if include_records else ()
        records = []
        for row in rows:
            payload = json.loads(row['payload'])
            assert hashlib.sha256(row['payload'].encode()).hexdigest() == row['payload_digest']
            item = {'id': row['id'], 'kind': row['kind'], 'payload_digest': row['payload_digest']}
            if row['kind'] == 'snapshots':
                assert payload['origin'] == 'live'
                assert type(row['raw']) is bytes and type(row['extracted']) is str and type(row['discovery']) is bytes
                for column, field in (('raw', 'raw_digest'), ('extracted', 'extracted_digest'), ('discovery', 'discovery_digest')):
                    value = row[column].encode() if column == 'extracted' else row[column]
                    assert hashlib.sha256(value).hexdigest() == payload[field]
                    item[field] = payload[field]
                item.update(doi=payload['doi'], source_id=payload['source_id'], source_revision=payload['source_revision'],
                            acquired_at=payload['acquired_at'], information_cutoff=payload['information_cutoff'])
            records.append(item)
        # No paid/native task or funding row is needed for this free Source run.
        assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0] == 0
        assert conn.execute('SELECT count(*) FROM research_tasks WHERE research_id=?', (rid,)).fetchone()[0] == 1
        assert task['policy_revision'] == 'd1-source-only-v1' and task['execution_mode'] == 'live'
        return {'task': dict(task), 'requests': requests, 'records': records}


async def public_facts(client, rid, tid):
    result = {}
    for kind in KINDS:
        cursor = None
        items = []
        for _ in range(4):
            query = {'task_id': tid, 'kind': kind}
            if cursor is not None:
                query['cursor'] = cursor
            data = require_ok(await client.get('/api/research/' + rid + '/records', params=query))['data']
            assert data['kind'] == kind and type(data['items']) is list
            items.extend(data['items'])
            cursor = data['next_cursor']
            if cursor is None:
                break
        assert cursor is None, 'bounded evidence page allowance exceeded'
        result[kind] = {'count': len(items), 'items_digest': digest(items)}
        if kind == 'sources':
            assert 1 <= len(items) <= 3, 'no licensed current-live source was saved'
            assert all(item['execution_mode'] == 'live' and item['read_scope'] == 'author_narrative_subset' for item in items)
            result[kind]['refs'] = [{'id': item['id'], 'revision': item['revision'],
                'content_digest': item['content_digest'], 'accessed_at': item['accessed_at']} for item in items]
    assert result['excerpts']['count'] >= 1 and result['reports']['count'] == 1
    return result


async def recover(frame):
    assert set(frame) == {'settings', 'rid', 'tid', 'stored', 'public', 'parent_pid'}
    assert set(frame['settings']) == set(SETTING_KEYS)
    assert os.getpid() != frame['parent_pid']
    settings = frame['settings']
    assert settings['STRUCTURAL_ENV'] == 'prod' and settings['AUTH_ENABLED'] == 'true'
    assert settings['AUTH_DATA_DIR'] == settings['STRUCTURAL_SSO_DATA_DIR']
    state = Path(settings['AUTH_DATA_DIR'])
    assert state.is_absolute() and (state / 'auth.sqlite3').is_file()
    os.environ.update(settings)
    from services import runtime_paths
    runtime_paths.STATE_ROOT = state
    runtime_paths.CACHE_ROOT = state.parent / 'cache'
    runtime_paths.LOG_ROOT = state / 'logs'
    # Reuse only the owned SMTP protocol fixture; no old Source/history seed.
    mail = owned_smtp()
    port, messages = mail.__enter__()
    os.environ.update(SMTP_HOST='127.0.0.1', SMTP_PORT=str(port), SMTP_FROM_EMAIL='sender@example.invalid',
        ADMIN_NOTIFICATION_EMAIL='admin@example.invalid', SMTP_STARTTLS='true', SMTP_USE_SSL='false', SMTP_TIMEOUT_SECONDS='2')
    try:
        main = importlib.import_module('main')
        from services import formal_admission as admission
        assert main._IS_PROD and main._LAUNCH_FORMAL
        # Refuse unexpected unfinished work before allowing a new supervisor.
        before = stored_facts(frame['rid'], frame['tid'])
        assert before == frame['stored'] and before['task']['execution'] == 'COMPLETED'
        assert all(row['outcome'] == 'SUCCEEDED' for row in before['requests'])
        loop = asyncio.get_running_loop()
        operation = asyncio.current_task()
        loop.add_signal_handler(signal.SIGTERM, operation.cancel)
        binding = None
        try:
            async with main.lifespan(main.app):
                admission.require(main.app, 'source_history')
                binding = admission._STATE[id(main.app)]
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA, timeout=10) as client:
                    await login(client, messages)
                    assert await public_facts(client, frame['rid'], frame['tid']) == frame['public']
                    assert stored_facts(frame['rid'], frame['tid']) == before
            assert binding.source_receipt.state == 'CLOSED'
            assert not binding.supervisor._thread.is_alive()
            assert all(witness.parent_fd is None for witness in binding.witnesses)
        finally:
            loop.remove_signal_handler(signal.SIGTERM)
        return {'phase': 'new-process-authenticated-readback', 'pid': os.getpid(),
                'same_ref_hash_time': True, 'additional_source_requests': 0,
                'source_closed': True, 'witness_fds_closed': True}
    finally:
        mail.__exit__(None, None, None)


if __name__ == '__main__':
    assert sys.argv[1:] == ['--recover-existing-store']
    # The launcher exposes only its owned, byte-verified original Science guard.
    # This is a test-process boundary, never a Source worker/trust replacement.
    import audit_bootstrap
    import main_smtp_guard
    assert hashlib.sha256(Path(main_smtp_guard.__file__).read_bytes()).hexdigest() == SCIENCE_GUARD_SHA256
    sys.modules['main_smtp_task_guard'] = main_smtp_guard
    main_smtp_guard.install()
    raw = sys.stdin.buffer.read(65537)
    assert len(raw) <= 65536
    receipt = asyncio.run(recover(json.loads(raw)))
    print('SOURCE15_RECOVERY:' + json.dumps(receipt, sort_keys=True))
