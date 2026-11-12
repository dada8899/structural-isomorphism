"""Protected recorded Source origin remains readable, never live authority."""
from pathlib import Path
import os
import json
import copy
import hashlib
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
for source in (ROOT, ROOT / 'web/backend'):
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))

from research import ResearchStore, source_guard, source_integration
from services.auth_store import AuthStore
from web.backend.tests.acceptance.source_history_fixture import prepared_source_history, _rows_digest


def test_authentic_offline13_history_is_checked_under_current_formal_live_mode(tmp_path):
    with prepared_source_history(ROOT, tmp_path / 'history') as seed:
        assert seed.schema_version == 15 and source_integration.origin() == 'live'
        store = ResearchStore(AuthStore(seed.state_root / 'auth.sqlite3'))
        assert store._formal_mode() is True
        identity = store.storage_identity
        with store.transaction() as conn:
            before = _rows_digest(conn)
            task = conn.execute('SELECT * FROM research_tasks WHERE id=?', (seed.source_task_id,)).fetchone()
            run = conn.execute('SELECT * FROM research_source_runs WHERE task_id=?', (seed.source_task_id,)).fetchone()
            approval = conn.execute('SELECT * FROM research_source_approvals WHERE id=?', (run['approval_id'],)).fetchone()
            assert (task['execution_mode'], run['origin'], approval['execution_mode']) == ('offline_probe',) * 3
            row = source_guard.check_origin(store, conn, seed.source_task_id)
            assert row['task_id'] == seed.source_task_id
            recorded, mode = source_guard._recorded_admission(row)
            assert mode == 'offline_probe'
            principal = conn.execute('SELECT * FROM research_principals WHERE id=?', (task['principal_id'],)).fetchone()
            grant = conn.execute('SELECT * FROM research_grants WHERE id=?', (task['grant_id'],)).fetchone()
            revision = conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=?',
                                    (task['research_id'], task['input_revision'])).fetchone()[0]
            actual = source_guard._admission_fields(task, run, approval, principal, grant, revision)
            source_guard._check_recorded_fields(actual, recorded, row['owner_gate_id'])
            # Pure negative inputs are copies of real protected records, never
            # database rows, fabricated runtime bindings or execution permits.
            for field, key in (('task', 'input_digest'), ('task', 'input_revision'),
                               ('run', 'plan_id'), ('run', 'origin'), ('approval', 'id'),
                               ('approval', 'auth_generation'), ('principal', 'session_generation'),
                               ('grant', 'research_id')):
                damaged = copy.deepcopy(actual)
                value = damaged[field][key]
                damaged[field][key] = value + 1 if type(value) is int else 'mismatched-original'
                with pytest.raises(PermissionError):
                    source_guard._check_recorded_fields(damaged, recorded, row['owner_gate_id'])
            damaged = copy.deepcopy(actual); damaged['revision_digest'] = '0' * 64
            with pytest.raises(PermissionError):
                source_guard._check_recorded_fields(damaged, recorded, row['owner_gate_id'])
            with pytest.raises(PermissionError):
                source_guard._check_recorded_fields(actual, recorded, 'another-owner-gate')
            retired = copy.deepcopy(actual)
            retired['principal']['epoch'] += 1
            retired['grant']['scopes'] = '[]'
            source_guard._check_recorded_fields(retired, recorded, row['owner_gate_id'])
            bad = dict(row); bad['admission_digest'] = '0' * 64
            with pytest.raises(PermissionError): source_guard._recorded_admission(bad)
            bad = dict(row); bad['admission_json'] = None
            with pytest.raises(PermissionError): source_guard._recorded_admission(bad)
            for bad_mode in (True, None, 0, '', 'history'):
                damaged = copy.deepcopy(recorded); damaged['task']['execution_mode'] = bad_mode
                encoded = source_guard.canonical(damaged)
                bad = dict(row); bad.update(admission_json=encoded, admission_digest=source_guard.sha256(encoded.encode()))
                with pytest.raises(PermissionError): source_guard._recorded_admission(bad)
                with pytest.raises(PermissionError):
                    source_integration._canonical_draft(approval['problem_digest'], approval['query'], bad_mode)
            for field, key in (('run', 'origin'), ('approval', 'execution_mode')):
                damaged = copy.deepcopy(recorded); damaged[field][key] = 'live'
                encoded = source_guard.canonical(damaged)
                bad = dict(row); bad.update(admission_json=encoded, admission_digest=source_guard.sha256(encoded.encode()))
                with pytest.raises(PermissionError): source_guard._recorded_admission(bad)
            with pytest.raises(PermissionError): source_integration.check_approval(conn, task)
            with pytest.raises(PermissionError): source_guard.snapshot(conn, seed.source_task_id)
            with pytest.raises(PermissionError): source_guard.check_active(store, conn, seed.source_task_id)
            assert _rows_digest(conn) == before == seed.original_source_rows_digest
            assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0] == 2
        assert store.storage_identity == identity


def _login_actual(service, client, email):
    status, _ = client.request('POST', '/api/auth/request-link', {'email': email})
    assert status == 200
    token = service.take_latest_magic_token()
    try: status, _ = client.request('POST', '/api/auth/verify', {'token': token})
    finally: token = None
    assert status == 200


def test_recorded_origin_is_not_a_current_reader_or_execution_grant(tmp_path):
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService, _HttpsClient
    from web.backend.tests.test_formal_main_admission import envelope, problem
    from urllib.parse import urlencode
    with FormalMainBrowserService(tmp_path / 'main') as service:
        seed = service.seed
        store = ResearchStore(AuthStore(seed.state_root / 'auth.sqlite3'))
        client = service.client
        _login_actual(service, client, seed.email)
        query = urlencode({'task_id': seed.source_task_id, 'kind': 'excerpts'})
        path = '/api/research/' + seed.research_id + '/records?' + query
        status, original = client.request('GET', path)
        assert status == 200
        with store.transaction() as conn:
            source_guard.check_origin(store, conn, seed.source_task_id)
        # Retiring only the old execution scope does not revoke a real reader.
        with store.transaction(write=True) as conn:
            conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?', (seed.source_task_id,))
            conn.execute("UPDATE research_grants SET status='revoked',scopes='[]' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)", (seed.source_task_id,))
        with store.transaction() as conn:
            source_guard.check_origin(store, conn, seed.source_task_id)
            with pytest.raises(PermissionError): source_guard.check_active(store, conn, seed.source_task_id)
        status, reopened = client.request('GET', path)
        assert status == 200 and reopened == original
        status, _ = client.request('POST', '/api/auth/logout')
        assert status == 200
        # The old execution/reader JTI cannot serve as present read authority.
        with store.transaction() as conn: source_guard.check_origin(store, conn, seed.source_task_id)
        status, _ = client.request('GET', path)
        assert status == 401
        _login_actual(service, client, seed.email)
        status, _ = client.request('POST', '/api/research/' + seed.research_id + '/revisions',
                                   envelope({'expected_revision': 1, 'problem': problem()}), key='origin-history-new-revision')
        assert status == 200
        with store.transaction() as conn: source_guard.check_origin(store, conn, seed.source_task_id)
        status, reopened = client.request('GET', path)
        assert status == 200 and reopened['data']['items'] == original['data']['items']
        assert reopened['data']['research_version'] == original['data']['research_version'] + 1
        other = _HttpsClient(service.port, service.certificate)
        _login_actual(service, other, 'other-origin-history@example.invalid')
        status, _ = other.request('GET', path)
        assert status == 404
        with store.transaction(write=True) as conn:
            conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')", (seed.research_id,))
        with store.transaction() as conn: source_guard.check_origin(store, conn, seed.source_task_id)
        status, _ = client.request('GET', path)
        assert status == 404
        status, _ = client.request('POST', '/api/me/delete', {'confirmation': 'DELETE'})
        assert status == 200
        with store.transaction() as conn:
            with pytest.raises(PermissionError): source_guard.check_origin(store, conn, seed.source_task_id)
        _login_actual(service, client, seed.email)
        status, _ = client.request('GET', path)
        assert status == 404
        with store.transaction() as conn:
            with pytest.raises(PermissionError): source_guard.check_origin(store, conn, seed.source_task_id)


def test_exact_old13_source_bytes_reconstruct_without_git(tmp_path):
    from web.backend.tests.method_v13_reference import historical_bytes
    relative = Path('web/backend/tests/reference/method_v13/deltas.json')
    entries = json.loads((ROOT / relative).read_text())
    destination = tmp_path / 'no-git'; (destination / relative).parent.mkdir(parents=True)
    shutil.copyfile(ROOT / relative, destination / relative)
    for name in ('web/backend/research/source_guard.py', 'web/backend/research/source_integration.py'):
        target = destination / name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
        raw = historical_bytes(destination, name, entries[name]['original_sha256'])
        assert hashlib.sha256(raw).hexdigest() == entries[name]['original_sha256']
    assert not (destination / '.git').exists()
