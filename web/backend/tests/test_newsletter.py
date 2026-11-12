"""Closed-release subscription contract; replaces the earlier capture contract.

There is deliberately no signup-success fixture or production data access.
"""
from __future__ import annotations

import asyncio
import builtins
import importlib
import inspect
import json
import os
from pathlib import Path
import sqlite3
import sys

import pytest
from fastapi import FastAPI

@pytest.fixture(autouse=True)
def restore_main_imports():
    missing = object()
    saved = {name: sys.modules.get(name, missing) for name in ('main', 'web.backend.main')}
    yield
    for name, module in saved.items():
        if module is missing:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module


CANARY = 'SUBSCRIPTION-PRIVATE-CANARY@example.invalid'
BODY_CASES = {
    'json': json.dumps({'email': CANARY, 'token': 'PRIVATE-TOKEN-CANARY'}).encode(),
    'invalid-json': ('{"email":"' + CANARY).encode(),
    'large-stream': (CANARY.encode() + b':') * 100000,
    'form': ('email=' + CANARY + '&token=PRIVATE-TOKEN-CANARY').encode(),
}
POST_PATHS = ('/api/newsletter/subscribe', '/api/waitlist', '/phase/api/waitlist')
COUNT_PATHS = ('/api/newsletter/count', '/api/waitlist/count')


async def probe(app, path, *, method='POST', payload=b'', spec='2.3', content_type=b'application/json'):
    messages = [];received = []
    chunks = [payload[:17], payload[17:]]
    async def receive():
        received.append(True)
        if chunks:
            body = chunks.pop(0)
            return {'type': 'http.request', 'body': body, 'more_body': bool(chunks)}
        return {'type': 'http.disconnect'}
    async def send(message):
        messages.append(message)
    scope = {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': spec},
        'http_version': '1.1', 'method': method, 'scheme': 'http',
        'path': path, 'raw_path': path.encode(),
        'query_string': ('email=' + CANARY + '&token=PRIVATE-TOKEN-CANARY').encode(),
        'root_path': '', 'client': ('127.0.0.1', 32123), 'server': ('testserver', 80),
        'headers': [(b'host', b'testserver'), (b'content-type', content_type),
                    (b'content-length', str(len(payload)).encode())]}
    await app(scope, receive, send)
    start = next(m for m in messages if m['type'] == 'http.response.start')
    body = b''.join(m.get('body', b'') for m in messages if m['type'] == 'http.response.body')
    return start, body, received


def assert_closed(result, *, specific=True):
    start, body, received = result
    assert start['status'] == 503 and received == []
    assert dict(start['headers']).get(b'cache-control') == b'no-store'
    assert CANARY.encode() not in body and b'PRIVATE-TOKEN-CANARY' not in body
    value = json.loads(body)
    if specific:
        assert value['ok'] is False and value['created'] is False
        assert value['error'] in {'newsletter_unavailable', 'waitlist_unavailable'}
        assert 'count' not in value and 'email' not in value


def forbid_storage(monkeypatch):
    attempted = []
    def denied(*args, **kwargs):
        attempted.append(True)
        raise AssertionError('closed request touched storage or sending')
    for name in ('api.newsletter', 'web.backend.api.newsletter'):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, '_data_file', denied)
            monkeypatch.setattr(module, '_is_duplicate', denied)
    for name in ('api.waitlist', 'web.backend.api.waitlist'):
        module = sys.modules.get(name)
        if module is not None:
            monkeypatch.setattr(module, '_data_file', denied)
            monkeypatch.setattr(module, '_connect', denied)
            monkeypatch.setattr(module, '_check_rate_limit', denied)
    monkeypatch.setattr(builtins, 'open', denied)
    monkeypatch.setattr(os, 'open', denied)
    monkeypatch.setattr(os, 'mkdir', denied)
    monkeypatch.setattr(sqlite3, 'connect', denied)
    return attempted


@pytest.mark.parametrize('namespace', ['api', 'web.backend.api'])
@pytest.mark.parametrize('profile', ['dev', 'prod', ' PROD '])
def test_router_requests_never_consume_body_or_access_storage(namespace, profile, monkeypatch, capsys):
    monkeypatch.setenv('STRUCTURAL_ENV', profile)
    newsletter = importlib.import_module(namespace + '.newsletter')
    waitlist = importlib.import_module(namespace + '.waitlist')
    app = FastAPI();app.include_router(newsletter.router, prefix='/api');app.include_router(waitlist.router, prefix='/api')
    assert list(inspect.signature(newsletter.subscribe).parameters) == ['request']
    assert list(inspect.signature(waitlist.waitlist).parameters) == ['request']
    with monkeypatch.context() as request_guard:
        attempted = forbid_storage(request_guard)
        for path in POST_PATHS[:2]:
            for kind, payload in BODY_CASES.items():
                content_type = b'application/x-www-form-urlencoded' if kind == 'form' else b'application/json'
                assert_closed(asyncio.run(probe(app, path, payload=payload, content_type=content_type)))
        for path in COUNT_PATHS:
            assert_closed(asyncio.run(probe(app, path, method='GET')))
        assert attempted == []
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err and 'PRIVATE-TOKEN-CANARY' not in captured.out + captured.err


@pytest.mark.parametrize('namespace', ['main', 'web.backend.main'])
@pytest.mark.parametrize('profile', ['dev', 'prod'])
def test_actual_main_middleware_keeps_three_local_collectors_bodyless(namespace, profile, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv('STRUCTURAL_ENV', profile)
    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.setenv('STRUCTURAL_LOG_FILE', str(tmp_path / 'app.jsonl'))
    monkeypatch.delitem(sys.modules, namespace, raising=False)
    module = importlib.import_module(namespace)
    # The autouse fixture restores the original object or original absence.
    assert len(inspect.signature(module.phase_api_waitlist).parameters) == 1
    materials = []
    for name in ('newsletter-subscribers.jsonl', 'waitlist.db', 'phase-waitlist.jsonl'):
        path = tmp_path / name;path.write_bytes(b'preserved private material\n');materials.append((path, path.read_bytes()))
    with monkeypatch.context() as request_guard:
        attempted = forbid_storage(request_guard)
        for spec in ('2.0', '2.3', '2.4'):
            for path in POST_PATHS:
                for kind, payload in BODY_CASES.items():
                    content_type = b'application/x-www-form-urlencoded' if kind == 'form' else b'application/json'
                    assert_closed(asyncio.run(probe(module.app, path, payload=payload, spec=spec, content_type=content_type)), specific=profile != 'prod')
            for path in COUNT_PATHS:
                assert_closed(asyncio.run(probe(module.app, path, method='GET', spec=spec)), specific=profile != 'prod')
        assert attempted == []
    assert all(path.read_bytes() == original for path, original in materials)
    captured = capsys.readouterr()
    assert CANARY not in captured.out + captured.err and 'PRIVATE-TOKEN-CANARY' not in captured.out + captured.err
    log = tmp_path / 'app.jsonl'
    if log.exists():
        assert CANARY.encode() not in log.read_bytes() and b'PRIVATE-TOKEN-CANARY' not in log.read_bytes()


def test_openapi_describes_closed_endpoints_without_body_or_success_contract():
    from api import newsletter, waitlist
    app = FastAPI();app.include_router(newsletter.router, prefix='/api');app.include_router(waitlist.router, prefix='/api')
    schema = app.openapi()
    for path, method in [(p, 'post') for p in POST_PATHS[:2]] + [(p, 'get') for p in COUNT_PATHS]:
        operation = schema['paths'][path][method]
        assert set(operation['responses']) == {'503'}
        assert 'requestBody' not in operation and not operation.get('parameters')
        response = operation['responses']['503']['content']['application/json']['schema']
        assert response['$ref'].endswith('/SubscriptionUnavailableResponse')
