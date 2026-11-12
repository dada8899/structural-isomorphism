"""Current15 reads authentic controlled13 history; no current Source execution."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from urllib.parse import urlencode

import pytest

ROOT = Path(__file__).resolve().parents[4]
for source in (ROOT, ROOT / 'web/backend'):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from research import ResearchStore
from research.financial_input import provision_financial_inputs_v15
from research.financial_input_guard import REGISTRIES, RESULTS, statement_allowed
from research.method_draft import provision_method_drafts_v14
from services.auth_store import AuthStore
from web.backend.tests.acceptance.source_history_fixture import (
    _KEY_NAMES, _rows_digest, prepared_source_history,
)
from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService


def _snapshot(path):
    info = path.stat()
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                isolation_level=None)) as conn:
        return {'version': conn.execute('SELECT version FROM research_schema').fetchone()[0],
                'identity': [info.st_dev, info.st_ino], 'rows_digest': _rows_digest(conn)}


def _assert_empty_financial_and_closed_results(conn):
    ResearchStore._check_v15(conn)
    assert conn.execute('SELECT count(*) FROM ' + REGISTRIES).fetchone()[0] == 0
    assert conn.execute('SELECT count(*) FROM ' + RESULTS).fetchone()[0] == 0
    assert conn.execute("SELECT research_financial_input_allowed('research_financial_results','INSERT','[]')").fetchone()[0] == 0
    assert statement_allowed(conn, sqlite3.SQLITE_INSERT, RESULTS, None) is False
    assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM research_tasks WHERE policy_revision!='d1-source-only-v1'").fetchone()[0] == 0


@pytest.mark.parametrize('target_revision', [False, True])
def test_old13_real14_real15_preserves_history_and_empty_financial_tables(tmp_path, target_revision):
    owned = tmp_path / 'history'
    events = []
    original_profile = sys.getprofile()
    original_environment = {name: os.environ.get(name) for name in _KEY_NAMES}
    codes = {provision_method_drafts_v14.__code__: 'method14',
             provision_financial_inputs_v15.__code__: 'financial15'}

    def observe(frame, event, result):
        phase = codes.get(frame.f_code)
        if phase is None:
            return
        if event == 'call':
            events.append({'phase': phase, 'before': _snapshot(owned / 'state/auth.sqlite3')})
        elif event == 'return' and type(result) is dict:
            # Provision receipts contain only fixed protocols and native inode.
            events[-1]['receipt'] = dict(result)

    sys.setprofile(observe)
    try:
        with prepared_source_history(ROOT, owned, target_revision=target_revision) as seed:
            sys.setprofile(original_profile)
            assert [event['phase'] for event in events] == ['method14', 'financial15', 'financial15']
            assert [event['before']['version'] for event in events] == [13, 14, 15]
            identity = events[0]['before']['identity']
            assert all(event['before']['identity'] == identity for event in events)
            assert all(event['before']['rows_digest'] == seed.original_source_rows_digest for event in events)
            receipt = events[1]['receipt']
            assert receipt == events[2]['receipt'] == {
                'schema_version': 15, 'financial_protocol': 9, 'financial_input_protocol': 2,
                'journal_mode': 'wal', 'database_identity': identity,
                'backup_scope': 'in_memory_algorithm_recovery_only'}
            assert seed.schema_version == 15 and seed.source_input_revision == 1
            assert seed.current_input_revision == (2 if target_revision else 1)
            assert seed.mode == 'offline_probe' and seed.excerpt_refs and seed.acquired_at
            manifest = ROOT / 'web/backend/tests/reference/method_v13/manifest.json'
            assert seed.original_source_code_manifest_sha256 == hashlib.sha256(manifest.read_bytes()).hexdigest()
            assert len(seed.original_loaded_modules_sha256) == 64
            with ResearchStore(AuthStore(seed.state_root / 'auth.sqlite3')).transaction() as conn:
                _assert_empty_financial_and_closed_results(conn)
                assert _rows_digest(conn) == seed.original_source_rows_digest
                assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 2
            (tmp_path / 'history-contract.json').write_text(json.dumps({
                'target_revision': target_revision, 'migration_events': events,
                'schema': seed.schema_version, 'old_source_version': 13,
                'refs_time_permission_checked_by_current_reader': True,
                'old_producer_loopback_gets': 2, 'current_source_requests_created': 0,
                'new_financial_tables_empty': True, 'result_writer_closed': True}))
    finally:
        sys.setprofile(original_profile)
    restored = all(os.environ.get(name) == value for name, value in original_environment.items())
    assert restored and not owned.exists()


def test_actual_main15_https_smtp_login_and_original_history_read(tmp_path):
    owned = tmp_path / 'actual-main'
    original_environment = {name: os.environ.get(name) for name in _KEY_NAMES}
    with FormalMainBrowserService(owned) as service:
        seed = service.seed
        assert seed.schema_version == 15
        client = service.client
        query = urlencode({'task_id': seed.source_task_id, 'kind': 'excerpts'})
        path = '/api/research/' + seed.research_id + '/records?' + query
        status, _ = client.request('GET', path)
        assert status == 401
        status, _ = client.request('POST', '/api/auth/request-link', {'email': seed.email})
        assert status == 200
        token = service.take_latest_magic_token()
        try:
            status, _ = client.request('POST', '/api/auth/verify', {'token': token})
        finally:
            token = None
        assert status == 200
        cookies = [cookie for cookie in client.cookies if cookie.name == 'phase_session']
        assert len(cookies) == 1 and cookies[0].secure and 'HttpOnly' in cookies[0]._rest
        status, records = client.request('GET', path)
        assert status == 200
        expected = {ref['excerpt_id']: ref for ref in seed.excerpt_refs}
        assert len(records['data']['items']) == len(expected)
        for item in records['data']['items']:
            ref = expected[item['id']]
            assert (item['source_revision'], item['text_digest'], item['start'], item['end']) == (
                ref['source_revision'], ref['content_digest'], ref['start'], ref['end'])
        status, health = client.request('GET', '/api/health')
        assert status == 200 and health['checks']['native_planner'] == 'FUNDING_CLOSED'
        with ResearchStore(AuthStore(seed.state_root / 'auth.sqlite3')).transaction() as conn:
            _assert_empty_financial_and_closed_results(conn)
            assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 2
            assert _rows_digest(conn) == seed.original_source_rows_digest
        facts = {'schema': seed.schema_version, 'actual_https': True,
                 'actual_smtp_login': True, 'unauthenticated_history_rejected': True,
                 'old_producer_loopback_gets': 2, 'current_source_requests_created': 0,
                 'funding': 'closed', 'ports': [service.port, service._smtp.port]}
    restored = all(os.environ.get(name) == value for name, value in original_environment.items())
    assert restored and not owned.exists() and not service.server_thread.is_alive()
    assert not service._smtp.thread.is_alive()
    (tmp_path / 'actual-main-history.json').write_text(json.dumps(facts))
