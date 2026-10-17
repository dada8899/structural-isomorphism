"""The release waitlist contract is closed, replacing signup/UTM persistence."""
import asyncio
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from .test_newsletter import BODY_CASES, CANARY, assert_closed, forbid_storage, probe


@pytest.mark.parametrize('namespace', ['api', 'web.backend.api'])
def test_waitlist_does_not_collect_utm_or_reactivate_with_flags(namespace, monkeypatch):
    module = importlib.import_module(namespace + '.waitlist')
    app = FastAPI();app.include_router(module.router, prefix='/api')
    for key in ('AUTH_DEV_MODE', 'NEWSLETTER_ENABLED', 'WAITLIST_ENABLED'):
        monkeypatch.setenv(key, 'true')
    with monkeypatch.context() as request_guard:
        attempted = forbid_storage(request_guard)
        for path, method in [('/api/waitlist', 'POST'), ('/api/waitlist/count', 'GET')]:
            assert_closed(asyncio.run(probe(app, path, method=method, payload=BODY_CASES['json'])))
        assert attempted == []


def test_all_three_collectors_are_closed_in_a_fresh_process(tmp_path):
    code = r'''
import sys,os,socket,sqlite3,asyncio
from pathlib import Path
root=Path(sys.argv[1]);owned=Path(sys.argv[2]);sys.path[:0]=[str(root/'web/backend'),str(root)]
def audit(event,args):
 if event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6):raise AssertionError('network forbidden')
 if event=='import' and args[0].split('.')[0] in ('torch','transformers','sentence_transformers','huggingface_hub'):raise AssertionError('model forbidden')
 if event=='sqlite3.connect':raise AssertionError('closed request opened sqlite')
sys.addaudithook(audit)
from web.backend.tests.test_newsletter import POST_PATHS,COUNT_PATHS,BODY_CASES,assert_closed,probe
import importlib
for namespace in ('main','web.backend.main'):
 module=importlib.import_module(namespace)
 for path in POST_PATHS:assert_closed(asyncio.run(probe(module.app,path,payload=BODY_CASES['large-stream'])))
 for path in COUNT_PATHS:assert_closed(asyncio.run(probe(module.app,path,method='GET')))
assert not list(owned.rglob('*.db')) and not list(owned.rglob('*.sqlite3'))
print('FRESH_SUBSCRIPTIONS_CLOSED')
'''
    root = Path(__file__).resolve().parents[3]
    env = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'HOME': str(tmp_path), 'TMPDIR': str(tmp_path),
        'PYTHONDONTWRITEBYTECODE': '1', 'STRUCTURAL_ENV': 'dev', 'AUTH_ENABLED': 'false',
        'STRUCTURAL_LOG_FILE': str(tmp_path / 'app.jsonl')}
    result = subprocess.run([sys.executable, '-B', '-c', code, str(root), str(tmp_path)], env=env,
        cwd=tmp_path, text=True, capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr[-3000:]
    assert 'FRESH_SUBSCRIPTIONS_CLOSED' in result.stdout and CANARY not in result.stdout + result.stderr
