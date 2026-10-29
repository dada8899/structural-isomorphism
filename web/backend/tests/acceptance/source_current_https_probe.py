"""Explicit opt-in acceptance specimen: THIS FILE MAKES PUBLIC SOURCE GETs.

Not named test_*, never part of ordinary discovery/CI. Preparation/collection
does not start Main, SMTP or a network connection. Execution requires separate
approval of this exact code and owned launcher. No automatic retry or resume.
"""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import httpx

from web.backend.tests.test_formal_main_admission import (
    BETA, envelope, login, prepared, problem, source_ready,
)
from web.backend.tests.acceptance.source_current_main_fixture import (
    SETTING_KEYS, SCIENCE_GUARD_SHA256, digest, public_facts, require_ok, smtp, stored_facts,
)


QUERY = 'queue variability'
USER_AGENT = 'StructureMethodEvidence/1'
HOSTS = ('api.crossref.org', 'journals.plos.org')
MAX_GETS = 4
GET_WALL_SECONDS = 12.0
# This is only the observer budget; it does not alter any production deadline.
OBSERVATION_SECONDS = MAX_GETS * GET_WALL_SECONDS + 12
RETAINED_RECOVERY_HANDLES = []


def specification():
    from research.source_policy import discovery_target
    return {'problem': problem(), 'query': QUERY, 'user_agent': USER_AGENT,
        'hosts': list(HOSTS), 'discovery_path': discovery_target(QUERY).path,
        'article_path_template': '/plosone/article?id=10.1371/journal.pone.[0-9]{7}',
        'max_gets': MAX_GETS, 'per_get_wall_seconds': GET_WALL_SECONDS,
        'transport': 'unmodified default PinnedPublicTransport; public DNS/TCP443/default CA/SNI',
        'retries': 0, 'models': 0, 'fees': 0}


def reopen_in_new_process(tmp_path, frame):
    owned = tmp_path / 'readback-process'
    owned.mkdir(mode=0o700)
    home = owned / 'home'
    home.mkdir(mode=0o700)
    source = Path(__file__).resolve().parents[4]
    pythonpath = [str(source / 'web/backend'), str(source)]
    audit = sys.modules.get('audit_bootstrap')
    assert audit is not None, 'approved startup guard must be installed by the owned launcher'
    pythonpath.insert(0, str(Path(audit.__file__).resolve().parent))
    science = sys.modules.get('main_smtp_task_guard')
    assert science is not None, 'approved owned Science guard required'
    science_path = Path(science.__file__).resolve()
    assert science_path.name == 'main_smtp_guard.py'
    assert hashlib.sha256(science_path.read_bytes()).hexdigest() == SCIENCE_GUARD_SHA256
    pythonpath.insert(1, str(science_path.parent))
    environment = {'PATH': '/usr/bin:/bin', 'HOME': str(home),
        'TMPDIR': os.environ['TMPDIR'], 'A006_AUDIT_ROOT': os.environ['A006_AUDIT_ROOT'],
        'REVIEW_SOURCE_ROOT': str(source), 'PYTHONPATH': os.pathsep.join(pythonpath),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1',
        'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'HF_HUB_OFFLINE': '1', 'TRANSFORMERS_OFFLINE': '1',
        'STRUCTURAL_LOG_FILE': str(owned / 'bootstrap.jsonl')}
    process = None
    raw = json.dumps(frame, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    assert len(raw) <= 65536
    try:
        with (owned / 'output.log').open('wb') as log:
            process = subprocess.Popen([sys.executable, '-B', str(Path(__file__).with_name('source_current_main_fixture.py')),
                '--recover-existing-store'], stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                cwd=owned, env=environment, close_fds=True)
            try:
                process.communicate(raw, timeout=60)
            except subprocess.TimeoutExpired:
                # Cooperative cancellation exits through the actual lifespan.
                # Never SIGKILL an unresolved Main and call its resources closed.
                process.send_signal(signal.SIGTERM)
                try:
                    process.communicate(timeout=25)
                except subprocess.TimeoutExpired:
                    RETAINED_RECOVERY_HANDLES.append(process)
                    raise AssertionError('recovery cleanup uncertain; retain real process handle and owned store') from None
                raise AssertionError('readback exceeded its finite observation budget') from None
        assert process.returncode == 0, 'new-process readback failed; retain private output.log'
        lines = (owned / 'output.log').read_text().splitlines()
        receipts = [json.loads(line[len('SOURCE15_RECOVERY:'):]) for line in lines if line.startswith('SOURCE15_RECOVERY:')]
        assert len(receipts) == 1 and receipts[0]['pid'] == process.pid
        assert receipts[0]['pid'] != os.getpid()
        return receipts[0]
    finally:
        # A retained uncertain handle is evidence, not a fabricated close.
        if process is not None and process.poll() is None and process not in RETAINED_RECOVERY_HANDLES:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                RETAINED_RECOVERY_HANDLES.append(process)
                raise AssertionError('recovery cleanup uncertain; retain real handle') from None


def test_current_main15_source_https_persist_and_reopen(prepared, tmp_path):
    main, admission, _, messages = prepared
    from api import auth
    from research.source_policy import WALL_SECONDS, discovery_target, article_target
    assert WALL_SECONDS == GET_WALL_SECONDS
    # Capture only fixture-generated synthetic signing settings; never log them.
    settings = {key: os.environ[key] for key in SETTING_KEYS}
    assert 'OPENROUTER_API_KEY' not in os.environ and 'DEEPSEEK_API_KEY' not in os.environ
    async def run():
        binding = None
        async with main.lifespan(main.app):
            await source_ready(main, admission)
            binding = admission._STATE[id(main.app)]
            with auth._store()._connection() as conn:
                assert conn.execute('SELECT version FROM research_schema').fetchone()[0] == 15
                assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0] == 0
                assert conn.execute('SELECT count(*) FROM research_evidence_objects').fetchone()[0] == 0
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url=BETA, timeout=10) as client:
                await login(client, messages)
                made = require_ok(await client.post('/api/research', json=envelope({'problem': problem()}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'source15-probe-create'}))
                rid = made['data']['research']['id']
                base = '/api/research/' + rid
                query = {'input_revision': 1, 'expected_research_version': 1, 'query': QUERY}
                preview = require_ok(await client.post(base + '/source-preview', json=envelope(query),
                    headers={'Origin': BETA, 'Idempotency-Key': 'source15-probe-preview'}))['data']
                approval = require_ok(await client.post(base + '/source-approvals', json=envelope({**query,
                    'preview_digest': preview['preview_digest'], 'confirm_external': True}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'source15-probe-approve'}))['data']['approval_ref']
                started = require_ok(await client.post(base + '/source-tasks', json=envelope({
                    'input_revision': 1, 'expected_research_version': 1, 'approval_ref': approval}),
                    headers={'Origin': BETA, 'Idempotency-Key': 'source15-probe-task'}))
                tid = started['data']['task']['id']
                (tmp_path / 'source15-task.json').write_text(json.dumps({'rid': rid, 'tid': tid,
                    'query': QUERY, 'retry_allowed': False, 'parent_pid': os.getpid()}, sort_keys=True) + '\n')
                deadline = time.monotonic() + OBSERVATION_SECONDS
                while True:
                    facts = stored_facts(rid, tid, include_records=False)
                    (tmp_path / 'source15-observation.json').write_text(json.dumps(facts, sort_keys=True) + '\n')
                    requests = facts['requests']
                    assert len(requests) <= MAX_GETS
                    assert all(row['semantic'] in ('discover_sources', 'fetch_source') for row in requests)
                    # UNKNOWN is never retried or treated as a received response.
                    assert not any(row['outcome'] == 'UNKNOWN' for row in requests), 'Source outcome unknown; stop and retain original task/store'
                    if facts['task']['execution'] == 'COMPLETED':
                        facts = stored_facts(rid, tid)
                        requests = facts['requests']
                        break
                    assert facts['task']['execution'] in ('QUEUED', 'RUNNING', 'WAITING_EXTERNAL'), 'Source did not complete; no fallback query or retry'
                    assert time.monotonic() < deadline, 'Source observation expired; stop through original Main cleanup'
                    await asyncio.sleep(.1)
                assert 2 <= len(requests) <= MAX_GETS
                assert all(row['outcome'] == 'SUCCEEDED' and row['http_status'] == 200 for row in requests)
                targets = [discovery_target(QUERY)] + [article_target(row['doi']) for row in facts['records'] if row['kind'] == 'snapshots']
                target_digests = {digest({'host': target.host, 'path': target.path}) for target in targets}
                assert all(target.host in HOSTS for target in targets)
                assert {row['target_digest'] for row in requests} == target_digests
                assert len(requests) == len(targets)
                public = await public_facts(client, rid, tid)
                assert 1 <= sum(row['kind'] == 'snapshots' for row in facts['records']) <= 3
                frame = {'settings': settings, 'rid': rid, 'tid': tid, 'stored': facts,
                         'public': public, 'parent_pid': os.getpid()}
        assert binding.source_receipt.state == 'CLOSED'
        assert not binding.supervisor._thread.is_alive()
        assert all(witness.parent_fd is None for witness in binding.witnesses)
        return frame
    frame = asyncio.run(run())
    recovery = reopen_in_new_process(tmp_path, frame)
    safe = {'specification': specification(), 'parent_pid': os.getpid(), 'rid': frame['rid'], 'tid': frame['tid'],
        'stored': frame['stored'], 'public': frame['public'], 'recovery': recovery,
        'tls_evidence': 'Successful bounded 200/body on unmodified default verified transport; no exported certificate/remote receipt',
        'remote_request_count': None, 'local_durable_request_count': len(frame['stored']['requests'])}
    (tmp_path / 'source15-safe-evidence.json').write_text(json.dumps(safe, ensure_ascii=False, sort_keys=True, indent=2) + '\n')
    print('SOURCE15_SAFE_RESULT:' + json.dumps({'source_count': frame['public']['sources']['count'],
        'local_durable_request_count': len(frame['stored']['requests']), 'new_process_readback': True,
        'source_closed': True, 'witness_fds_closed': True}, sort_keys=True))
