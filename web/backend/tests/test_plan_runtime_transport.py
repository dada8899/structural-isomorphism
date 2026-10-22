"""Fixed Runtime resource over actual owned HTTP; TLS tests are components only."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib
import json
import os
from pathlib import Path
import pickle
import shutil
import socket
import ssl
import sys
import subprocess
import threading
import time

import pytest
from fastapi import FastAPI, APIRouter
from fastapi.testclient import TestClient
from .test_private_registration import BETA
from .test_private_runtime_bootstrap import roots
from .test_research_funded_plan import CANDIDATE
from .test_research_native_plan import admitted
from .test_research_paid_producers import identity
from research import plan_native as native, plan_native_runtime as flow, ResearchRunner
from services import plan_runtime_transport as transport


class _ActualMainResponse:
    """Data-only HTTP result adapter; never a native resource or receipt."""
    def __init__(self, status, value):
        self.status_code, self._value = status, value
    def json(self):
        return self._value
    @property
    def text(self):
        return json.dumps(self._value, ensure_ascii=False)


class _ActualCookieView:
    def __init__(self, client):
        self.client = client
    def get(self, name):
        return next((cookie.value for cookie in self.client.cookies if cookie.name == name), None)


class _ActualMainClient:
    """Preserve old test call shapes over real canonical TLS/cookies only."""
    def __init__(self, service, store, actor):
        self.service, self.store, self.actor = service, store, actor
        self.cookies, self.app = _ActualCookieView(service.client), service.app
        self._delete_attempted = False
    def _request(self, method, path, *, json=None, headers=None, params=None):
        from urllib.parse import urlencode
        headers = headers or {}
        assert headers.get('origin', headers.get('Origin', BETA)) == BETA
        if params: path += ('&' if '?' in path else '?') + urlencode(params)
        key = headers.get('idempotency-key', headers.get('Idempotency-Key'))
        if method == 'POST' and path == '/api/me/delete':
            assert json == {'confirmation': 'DELETE'} and key is None
            return self._delete_after_owned_return()
        status, value = self.service.client.request(method, path, json, key=key)
        return _ActualMainResponse(status, value)
    def _delete_after_owned_return(self):
        # This one legacy case used in-process TestClient. Its real HTTPS
        # observation may wait 10s once, after an actual OwnedReturn only;
        # Native/Source/Main and the test's wait/join budgets stay unchanged.
        import urllib.request
        import urllib.error
        assert not self._delete_attempted
        provision, resource = native.installation(self.store)
        assert type(resource) is transport.NativePlanResource
        assert provision.authority.store is self.store and provision.authority.identity == self.actor
        returns = [value for value in tuple(transport._RETURNS.values()) if value.resource is resource]
        assert len(returns) == 1
        owned = returns[0]
        assert type(owned) is transport.OwnedNativeReturn
        owned.require(resource, owned.dispatch, owned.nonce, owned.admission_digest, owned.producer_digest)
        self._delete_attempted = True
        request = urllib.request.Request(self.service.origin + '/api/me/delete',
            data=b'{"confirmation":"DELETE"}', method='POST',
            headers={'Origin': BETA, 'Content-Type': 'application/json'})
        try:
            response = self.service.client.opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            body = response.read(524289)
            assert len(body) <= 524288
            return _ActualMainResponse(response.status, json.loads(body) if body else None)
    def post(self, path, **kwargs):
        return self._request('POST', path, **kwargs)
    def get(self, path, **kwargs):
        return self._request('GET', path, **kwargs)


@pytest.fixture
def stack(tmp_path):
    from .test_research_evidence_method_plan import actual
    with actual(tmp_path) as (service, _, store, actor):
        yield _ActualMainClient(service, store, actor), service.root, []


def saved(stack, monkeypatch):
    from .test_formal_main_admission import problem, envelope
    client, root, _ = stack
    response = client.post('/api/research', json=envelope({'problem': problem()}),
        headers={'origin': BETA, 'idempotency-key': 'runtime-local-current-create'})
    assert response.status_code == 200
    return client, root, response.json()['data']['research']['id'], client.store


@contextmanager
def full_namespace_on_actual_main(client, monkeypatch):
    """Fixed test-only router deployment; the real Main binding stays owned."""
    short_paths = importlib.import_module('services.runtime_paths')
    full_paths = importlib.import_module('web.backend.services.runtime_paths')
    for name in ('STATE_ROOT', 'CACHE_ROOT', 'LOG_ROOT'):
        monkeypatch.setattr(full_paths, name, getattr(short_paths, name))
    auth = importlib.import_module('web.backend.api.auth')
    api = importlib.import_module('web.backend.api.research')
    router = APIRouter()
    router.include_router(auth.router, prefix='/api')
    router.include_router(api.router, prefix='/api')
    paths = {route.path for route in router.routes}
    original = list(client.app.router.routes)
    client.app.router.routes[:] = list(router.routes) + [route for route in original if getattr(route, 'path', None) not in paths]
    try:
        service = client.service
        response = client.post('/api/auth/request-link', json={'email': service.seed.email}, headers={'origin': BETA})
        assert response.status_code == 200
        token = service.take_latest_magic_token()
        try: response = client.post('/api/auth/verify', json={'token': token}, headers={'origin': BETA})
        finally: token = None
        assert response.status_code == 200
        package = importlib.import_module('web.backend.research')
        store = package.ResearchStore(auth._store())
        claims = auth._decode_jwt(client.cookies.get('phase_session'))
        actor = importlib.import_module('web.backend.research.authorization').AccountIdentity(
            claims['sub'], claims['gen'], claims['jti'], claims['exp'])
        claims = None
        yield store, actor
    finally:
        client.app.router.routes[:] = original


@contextmanager
def installed_evidence_runtime(store, actor, server):
    authority = native.create_controlled_runtime_evidence_method_fixture_authority(
        store, actor, server, approved_cap_units=41_000_000, risk_margin_units=1_000_000)
    provision = native.issue_native_provision(store, authority)
    permit = native.mint_runtime_permit(provision)
    resource = native.open_plan_resource(permit)
    assert type(resource) is transport.NativePlanResource
    try:
        native.install_native_funding(store, provision, resource)
        yield resource
    finally:
        native.retire_installation(store)


def test_evidence_runtime_actual_main_full_request_owned_return_save_and_read(tmp_path, monkeypatch):
    from .test_research_evidence_method_plan import actual, preview, approve
    from .test_research_evidence_method_native import example
    from .test_research_funded_plan import provider as evidence_provider
    observed = []
    original = transport._Pending.write_first
    def actual_first(pending, capability):
        assert pending.first_write_syscall_entered is False
        result = original(pending, capability)
        assert capability.used and type(capability.inspected) is flow.EvidenceMethodPayload
        assert pending.first_write_syscall_entered is True
        observed.append(pending)
        return result
    monkeypatch.setattr(transport._Pending, 'write_first', actual_first)
    with actual(tmp_path) as (service, client, store, actor), evidence_provider(
            choices=[{'finish_reason': 'stop', 'message': {'content': json.dumps(example())}}]
            ) as (server, calls), installed_evidence_runtime(store, actor, server) as resource:
        status, shown = preview(service, client)
        assert status == 200 and shown['data']['can_confirm'] is True
        (status, confirmed), _ = approve(service, client, shown['data'])
        assert status == 200
        result = flow.run_once(store, confirmed['data']['task_id'])['data']
        assert result['state'] == 'saved' and result['cleanup_state'] == 'clean'
        assert len(observed) == 1
        assert [call[0] for call in calls] == ['GET', 'POST']
        from research.provider_schemas import canonical, digest
        assert digest(canonical(calls[1][3])) == shown['data']['request_digest']
        status, saved_value = client.request('GET', '/api/research/' + service.seed.research_id
            + '/evidence-method-plans/' + confirmed['data']['result_ref'])
        assert status == 200 and saved_value['data']['metadata']['state'] == 'saved'
        status, reopened = client.request('GET', '/api/research/' + service.seed.research_id
            + '/evidence-method-plans/' + confirmed['data']['result_ref'])
        assert status == 200 and reopened == saved_value
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()) == (0, flow.UPPER)
        flow.run_once(store, confirmed['data']['task_id'])
        assert [call[0] for call in calls] == ['GET', 'POST']


@contextmanager
def actual_evidence_runtime_case(tmp_path):
    from .test_research_evidence_method_plan import actual, preview, approve
    from .test_research_evidence_method_native import example
    from .test_research_funded_plan import provider as evidence_provider
    with actual(tmp_path) as (service, client, store, actor), evidence_provider(
            choices=[{'finish_reason': 'stop', 'message': {'content': json.dumps(example())}}]
            ) as (server, calls), installed_evidence_runtime(store, actor, server) as resource:
        status, shown = preview(service, client)
        assert status == 200 and shown['data']['can_confirm'] is True
        (status, confirmed), _ = approve(service, client, shown['data'])
        assert status == 200
        yield service, client, store, actor, resource, calls, confirmed['data'], server


def assert_consumed_unknown_hold(store, calls, pending):
    assert [call[0] for call in calls] == ['GET']
    with store.transaction() as conn:
        row = conn.execute('SELECT * FROM research_plan_native_runs').fetchone()
        assert (row['state'], row['cost_state'], row['cleanup_state']) == ('unknown', 'unknown', 'clean')
        assert row['receipt_json'] is None and row['result_json'] is None
        assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()) == (flow.UPPER, 0)
    assert not pending.first_write_syscall_entered


@pytest.mark.parametrize('fault', ['raw', 'schema', 'purpose', 'handle'])
def test_evidence_runtime_fixed_decoder_rejects_before_consume_and_first_write(tmp_path, monkeypatch, fault):
    from dataclasses import replace
    inspected, pendings = [], []
    original_inspect, original_write = flow.NativePlanSendLease.inspect_payload, transport._Pending.write_first
    def tampered_data(capability, resource):
        descriptor = original_inspect(capability, resource)
        inspected.append(capability)
        if fault == 'raw':
            raw = descriptor.raw + b'\n'
        else:
            request = json.loads(descriptor.raw)
            user = json.loads(request['messages'][1]['content'])
            if fault == 'schema': user['candidate_schema'] = 'PhenomenonPlanCandidate-v2'
            elif fault == 'purpose': user['purpose'] = 'phenomenon_plan_v1'
            else: user['input']['handles'][0]['handle'] = 'E2'
            request['messages'][1]['content'] = json.dumps(user, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
            raw = json.dumps(request, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        return replace(descriptor, raw=raw)
    def capture_pending(pending, capability):
        pendings.append(pending)
        return original_write(pending, capability)
    monkeypatch.setattr(flow.NativePlanSendLease, 'inspect_payload', tampered_data)
    monkeypatch.setattr(transport._Pending, 'write_first', capture_pending)
    with actual_evidence_runtime_case(tmp_path) as (_, _, store, _, _, calls, confirmation, _):
        with pytest.raises((PermissionError, ValueError, TypeError)):
            flow.run_once(store, confirmation['task_id'])
        assert len(inspected) == len(pendings) == 1 and not inspected[0].used
        assert_consumed_unknown_hold(store, calls, pendings[0])
        flow.run_once(store, confirmation['task_id'])
        assert [call[0] for call in calls] == ['GET']


@pytest.mark.parametrize('fault', ['source-revoked', 'consume-binding', 'cross-resource'])
def test_evidence_runtime_actual_recheck_rejects_before_first_write(tmp_path, monkeypatch, fault):
    from .test_research_evidence_method_native import _reader_grants
    original_inspect, original_consume = flow.NativePlanSendLease.inspect_payload, flow.NativePlanSendLease.consume
    original_write = transport._Pending.write_first
    pendings, withdrawn, consumed = [], [], []
    other = []
    with actual_evidence_runtime_case(tmp_path) as (service, _, store, actor, resource, calls, confirmation, server):
        if fault == 'cross-resource':
            # A second genuine resource has the same sealed money domain but
            # a distinct registered object; do not create/reset an account.
            other.append(native.open_plan_resource(resource.permit))
        def observed_inspect(capability, resource):
            if fault == 'cross-resource': return original_inspect(capability, other[0])
            descriptor = original_inspect(capability, resource)
            if fault == 'source-revoked':
                withdrawn.extend(_reader_grants(store, service.seed.research_id, held_owner=capability.lease))
            return descriptor
        def changed_consume(capability, resource):
            consumed.append(capability)
            if fault == 'consume-binding': object.__setattr__(capability, 'raw', capability.raw + b'\n')
            return original_consume(capability, resource)
        def capture_pending(pending, capability):
            pendings.append(pending)
            return original_write(pending, capability)
        monkeypatch.setattr(flow.NativePlanSendLease, 'inspect_payload', observed_inspect)
        monkeypatch.setattr(flow.NativePlanSendLease, 'consume', changed_consume)
        monkeypatch.setattr(transport._Pending, 'write_first', capture_pending)
        try:
            with pytest.raises((PermissionError, ValueError, TypeError, __import__('research.errors', fromlist=['ResearchError']).ResearchError)):
                flow.run_once(store, confirmation['task_id'])
            assert len(pendings) == 1
            assert_consumed_unknown_hold(store, calls, pendings[0])
            if fault != 'cross-resource': assert len(consumed) == 1 and not consumed[0].used
            flow.run_once(store, confirmation['task_id'])
            assert [call[0] for call in calls] == ['GET']
        finally:
            if withdrawn: _reader_grants(store, service.seed.research_id, restore=withdrawn)
            if other: assert not native.retire_attempts(*other)


@pytest.mark.parametrize('fault', ['want-read', 'want-write', 'failure', 'partial', 'pre-syscall'])
def test_evidence_runtime_first_socket_entry_is_recorded_once_and_never_refunded(tmp_path, monkeypatch, fault):
    original_send, original_write = socket.socket.send, transport._Pending.write_first
    original_first = transport._Channel.send_first
    pendings, entries = [], []
    def capture_pending(pending, capability):
        pendings.append(pending)
        return original_write(pending, capability)
    def first_socket_send(sock, data, *args, **kwargs):
        frame = sys._getframe(1)
        if frame.f_code is transport._Channel.send_first.__code__ and pendings and sock is pendings[-1].channel.sock:
            assert pendings[-1].first_write_syscall_entered is True
            entries.append(True)
            if fault == 'want-read': raise ssl.SSLWantReadError('owned first-send entry requires read')
            if fault == 'want-write': raise ssl.SSLWantWriteError('owned first-send entry requires write')
            if fault == 'failure': raise OSError('owned first-send syscall failure')
            return original_send(sock, data[:7], *args, **kwargs)
        return original_send(sock, data, *args, **kwargs)
    monkeypatch.setattr(transport._Pending, 'write_first', capture_pending)
    monkeypatch.setattr(socket.socket, 'send', first_socket_send)
    if fault == 'pre-syscall':
        def expire_before_entry(channel, data):
            channel.deadline = time.monotonic() - 1
            return original_first(channel, data)
        monkeypatch.setattr(transport._Channel, 'send_first', expire_before_entry)
    with actual_evidence_runtime_case(tmp_path) as (_, _, store, _, _, calls, confirmation, _):
        if fault == 'partial':
            assert flow.run_once(store, confirmation['task_id'])['data']['state'] == 'saved'
            assert [call[0] for call in calls] == ['GET', 'POST']
        else:
            with pytest.raises((ssl.SSLWantReadError, ssl.SSLWantWriteError, OSError, TimeoutError)):
                flow.run_once(store, confirmation['task_id'])
            assert [call[0] for call in calls] == ['GET']
            with store.transaction() as conn:
                assert tuple(conn.execute('SELECT state,cost_state FROM research_plan_native_runs').fetchone()) == ('unknown', 'unknown')
                assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()) == (flow.UPPER, 0)
            flow.run_once(store, confirmation['task_id'])
            assert [call[0] for call in calls] == ['GET']
        assert len(pendings) == 1
        assert len(entries) == (0 if fault == 'pre-syscall' else 1)
        assert pendings[0].first_write_syscall_entered is (fault != 'pre-syscall')


def test_existing_self_runtime_actual_main_original_contract_still_saves(tmp_path):
    from .test_research_evidence_method_plan import actual
    from .test_formal_main_admission import problem, envelope
    with actual(tmp_path) as (service, client, store, actor), provider() as (server, calls, _):
        status, created = client.request('POST', '/api/research', envelope({'problem': problem()}), key='runtime-self-original-problem')
        assert status == 200
        rid = created['data']['research']['id']
        with installed((client, service.root, rid, store), server, actor=actor):
            def old_send(suffix, data, key):
                return client.request('POST', '/api/research/' + rid + '/' + suffix,
                    {'schema_version': 'structure-research-v1', 'contract_revision': 'funded-plan-v2', 'data': data}, key=key)
            status, shown = old_send('plan-previews', {
                'input_revision': 1, 'expected_research_version': 1,
                'observation_source': 'own_observation', 'declaration_status': 'self_declared'}, 'runtime-self-preview')
            assert status == 200 and shown['data']['can_confirm']
            confirmed = {key: shown['data'][key] for key in ('preview_ref', 'preview_digest', 'request_digest',
                'expected_research_version', 'approved_upper_units')}
            confirmed['confirm_outbound'] = True
            status, queued = old_send('plan-approvals', confirmed, 'runtime-self-approve')
            assert status == 200
            outcome = flow.run_once(store, queued['data']['task_id'])['data']
            assert outcome['state'] == 'saved'
            assert [value[0] for value in calls] == ['GET', 'POST']
            status, saved_value = client.request('GET', '/api/research/' + rid + '/plan-results/' + queued['data']['result_ref'])
            assert status == 200 and saved_value['data']['content']['proposal'] == CANDIDATE
            flow.run_once(store, queued['data']['task_id'])
            assert [value[0] for value in calls] == ['GET', 'POST']


@contextmanager
def provider(*, before_balance=None, unknown_usage=False, tls=None, truncated=False, truncated_get=False):
    calls = []
    state = {'balance': '73'}
    class Handler(BaseHTTPRequestHandler):
        timeout = 3
        def log_message(self, *args): pass
        def reply(self, value):
            raw = json.dumps(value).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(raw) + (10 if (truncated and self.command == 'POST') or (truncated_get and self.command == 'GET') else 0)))
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError, ssl.SSLError): pass
        def note(self):
            calls.append((self.command, self.path, self.headers.get('X-Fixture-Incarnation'), self.headers.get('X-Fixture-Credential-Instance')))
        def do_GET(self):
            self.note()
            if before_balance: before_balance()
            self.reply({'is_available': True, 'balance_infos': [{'currency': 'CNY', 'total_balance': state['balance']}]})
        def do_POST(self):
            raw = self.rfile.read(int(self.headers['Content-Length']))
            assert json.loads(raw)['model'] == 'deepseek-flash'
            self.note()
            self.reply({'model': 'deepseek-flash', 'usage': None if unknown_usage else {'prompt_tokens': 100, 'completion_tokens': 80, 'total_tokens': 180},
                        'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(CANDIDATE)}}]})
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    if tls is not None:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, calls, state
    finally:
        server.shutdown(); server.server_close(); thread.join(4)
        assert not thread.is_alive()


@contextmanager
def installed(data, server, *, core=native, runtime=transport, actor=None, allow_uncertain=False):
    client, _, _, store = data
    authority = provision = permit = resource = None
    bound = False
    try:
        authority = core.create_controlled_runtime_fixture_authority(store, actor or identity(client), server, approved_cap_units=41_000_000, risk_margin_units=1_000_000)
        provision = core.issue_native_provision(store, authority)
        permit = core.mint_runtime_permit(provision)
        resource = core.open_plan_resource(permit)
        assert type(resource) is runtime.NativePlanResource
        core.install_native_funding(store, provision, resource)
        bound = True
        yield resource
    finally:
        try:
            if bound:
                core.retire_installation(store)
            else:
                assert not core.retire_attempts(resource, permit, provision, authority)
        except Exception as error:
            if not allow_uncertain or getattr(error, 'code', None) != 'CLEANUP_UNCERTAIN': raise
        assert not [v for reg in (runtime._RESOURCES, runtime._PENDING, runtime._BALANCES, runtime._RETURNS, runtime._CREDENTIALS, runtime._CHANNELS) for v in reg.values() if getattr(v, 'active', False)]
        assert not runtime._CHANNELS, 'owned native FDs remain after fixture retirement'


@pytest.mark.parametrize('family', ['research', 'web.backend.research'])
def test_actual_canonical_http_worker_same_credential_native_commit_and_saved_history(stack, monkeypatch, family):
    data = saved(stack, monkeypatch)
    client, root, rid, store = data
    extra = None
    if family.startswith('web.'):
        extra = full_namespace_on_actual_main(client, monkeypatch)
        store, actor = extra.__enter__()
        data = client, root, rid, store
    else:
        actor = identity(client)
    core = importlib.import_module(family + '.plan_native')
    worker = importlib.import_module(family).ResearchRunner
    runtime = importlib.import_module(('web.backend.services' if family.startswith('web.') else 'services') + '.plan_runtime_transport')
    phase = []
    prepare, write = runtime.NativePlanResource.prepare_post, runtime._Pending.write_first
    gate = importlib.import_module(family + '.authorization').AuthorizationGate(store)
    def before_prepare(value):
        with store.transaction() as conn:
            row = conn.execute('SELECT state FROM research_plan_native_runs').fetchone()
            assert row[0] == 'reserved'
            principal = conn.execute('SELECT principal_id FROM research_plan_native_runs JOIN research_tasks ON task_id=research_tasks.id').fetchone()[0]
        with gate.owner_gate(principal, timeout=.1): phase.append('prepare_owner_free')
        return prepare(value)
    def first_write(pending, cap):
        with store.transaction() as conn:
            assert conn.execute('SELECT state FROM research_plan_native_runs').fetchone()[0] == 'consumed'
            principal = conn.execute('SELECT principal_id FROM research_tasks').fetchone()[0]
        with pytest.raises(Exception) as held:
            with gate.owner_gate(principal, timeout=.03): raise AssertionError('Owner was not held')
        assert getattr(held.value, 'code', None) == 'STORE_BUSY'
        write(pending, cap)
        with pytest.raises(PermissionError): cap.consume(pending.resource)
        phase.append('actual_consumed_owner_first_write')
    monkeypatch.setattr(runtime.NativePlanResource, 'prepare_post', before_prepare)
    monkeypatch.setattr(runtime._Pending, 'write_first', first_write)
    try:
        with provider() as (server, calls, _), installed(data, server, core=core, runtime=runtime, actor=actor) as resource:
            result = admitted(client, rid)
            outcome = worker(store).run_once(result['task_id'])['data']
            assert outcome['state'] == 'saved' and outcome['cleanup_state'] == 'clean' and not outcome['real_model_executed']
            assert [v[0] for v in calls] == ['GET', 'POST']
            assert calls[0][2:] == calls[1][2:] and calls[0][3] == resource._credential.reference
            assert resource.economic_binding == resource.permit.data()['economic_binding']
            response = client.get('/api/research/' + rid + '/plan-results/' + result['result_ref'])
            assert response.status_code == 200
            content = response.json()['data']['content']
            assert content['proposal'] == CANDIDATE and content['producer'] == 'owned-native-plan-runtime-v1'
            assert content['execution_mode'] == 'controlled_fixture' and not content['real_model_executed']
            assert client.get('/api/research/' + rid + '/plan-results/' + result['result_ref']).json() == response.json()
            worker(store).run_once(result['task_id']); assert len(calls) == 2
            with store.transaction() as conn:
                assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (0, flow.UPPER)
            assert phase == ['prepare_owner_free', 'actual_consumed_owner_first_write']
    finally:
        if extra is not None: extra.__exit__(None, None, None)


def test_import_and_forged_permits_caps_are_closed_before_transport(stack, monkeypatch):
    data = saved(stack, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('unapproved socket or DNS')
    class Forged:
        def data(self): raise AssertionError('ducktype was called')
    with monkeypatch.context() as denied:
        denied.setattr(socket, 'socket', forbidden); denied.setattr(socket, 'getaddrinfo', forbidden)
        for value in (None, {}, Forged()):
            with pytest.raises((PermissionError, TypeError)): transport.open_plan_resource(value)
        with pytest.raises(Exception) as closed: native.bootstrap_native_owner_authority(data[3])
        assert closed.value.code == 'FUNDING_CLOSED'
    with provider() as (server, calls, _), installed(data, server) as resource:
        with pytest.raises(PermissionError): resource.balance(Forged())
        with pytest.raises(PermissionError): resource.prepare_post()
        assert resource._credential is None and calls == []
        for value in (resource, resource.permit):
            with pytest.raises(TypeError): pickle.dumps(value)
        resource.permit.close()
        with pytest.raises(PermissionError): resource.require()
        with pytest.raises(PermissionError): transport.open_plan_resource(resource.permit)
        assert calls == []


@pytest.mark.parametrize('family', ['services', 'web.backend.services'])
def test_fresh_module_and_unapproved_factory_do_not_touch_credential_sqlite_or_network(family, tmp_path):
    code = r'''
import importlib,json,os,socket,sqlite3,sys
hits=[]
def audit(event,args):
 if event=='sqlite3.connect' or event in ('socket.getaddrinfo','socket.connect') or (event=='socket.__new__' and args[1] in (socket.AF_INET,socket.AF_INET6)):
  hits.append(event);raise AssertionError('unapproved native IO')
 if event=='open' and isinstance(args[0],str) and ('structural-deepseek-api-key' in args[0] or args[0].endswith(('.env','.env.runtime'))):
  hits.append('credential-file');raise AssertionError('unapproved credential')
sys.addaudithook(audit)
module=importlib.import_module(sys.argv[1]+'.plan_runtime_transport')
for value in (None,{}, {'mode':'native_live','credential_ref':'structural-deepseek-api-key'}):
 try:module.open_plan_resource(value)
 except PermissionError:pass
 else:raise AssertionError('factory admitted data')
assert not hits
print(json.dumps({'native_io':hits,'default_closed':True}))
'''
    result = subprocess.run([__import__('sys').executable, '-B', '-c', code, family], capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout.splitlines()[-1]) == {'native_io': [], 'default_closed': True}


@pytest.mark.parametrize('failure', [ssl.SSLWantReadError, ssl.SSLWantWriteError])
def test_first_write_want_is_unknown_no_retry_and_holds_original_cost(stack, monkeypatch, failure):
    data = saved(stack, monkeypatch); client, _, rid, store = data
    def want(channel, raw): raise failure('owned nonblocking boundary')
    monkeypatch.setattr(transport._Channel, 'send_first', want)
    with provider() as (server, calls, _), installed(data, server):
        result = admitted(client, rid)
        with pytest.raises(failure): ResearchRunner(store).run_once(result['task_id'])
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:] == ('unknown', 'unknown', 'clean')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (flow.UPPER, 0)
        ResearchRunner(store).run_once(result['task_id']); assert [v[0] for v in calls] == ['GET']


def test_actual_partial_first_write_completes_same_request_once(stack, monkeypatch):
    data = saved(stack, monkeypatch); client, _, rid, store = data
    original = transport._Channel.send_first
    monkeypatch.setattr(transport._Channel, 'send_first', lambda channel, raw: original(channel, raw[:7]))
    with provider() as (server, calls, _), installed(data, server):
        result = admitted(client, rid)
        assert ResearchRunner(store).run_once(result['task_id'])['data']['state'] == 'saved'
        assert [v[0] for v in calls] == ['GET', 'POST']


@pytest.mark.parametrize('kind', ['unknown_usage', 'truncated'])
def test_real_unusable_return_keeps_unknown_cost_and_never_resends(stack, monkeypatch, kind):
    data = saved(stack, monkeypatch); client, _, rid, store = data
    with provider(**{kind: True}) as (server, calls, _), installed(data, server):
        result = admitted(client, rid)
        if kind == 'truncated':
            with pytest.raises(ValueError): ResearchRunner(store).run_once(result['task_id'])
        else:
            assert ResearchRunner(store).run_once(result['task_id'])['data']['state'] == 'pending_reconciliation'
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (flow.UPPER, 0)
        ResearchRunner(store).run_once(result['task_id']); assert [v[0] for v in calls] == ['GET', 'POST']


@pytest.mark.parametrize('target', ['pending', 'return'])
def test_close_fault_after_owned_handoff_preserves_booked_result_and_retires_all(stack, monkeypatch, target):
    data = saved(stack, monkeypatch); client, _, rid, store = data
    cls = transport._Pending if target == 'pending' else transport.OwnedNativeReturn
    original = cls.close; fired = []
    def close(value):
        original(value)
        if not fired: fired.append(True); raise OSError('owned after-close fault')
    monkeypatch.setattr(cls, 'close', close)
    with provider() as (server, calls, _), installed(data, server) as resource:
        result = admitted(client, rid)
        with pytest.raises(Exception) as failed: ResearchRunner(store).run_once(result['task_id'])
        assert failed.value.code == 'CLEANUP_UNCERTAIN'
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:] == ('returned', 'upper_booked', 'uncertain')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (0, flow.UPPER)
        assert not [v for v in transport._RETURNS.values() if v.active]
        assert resource.flight.acquire(blocking=False); resource.flight.release()
        assert client.get('/api/research/' + rid + '/plan-results/' + result['result_ref']).json()['data']['content']['proposal'] == CANDIDATE
        assert [v[0] for v in calls] == ['GET', 'POST']


@pytest.mark.parametrize('phase', ['balance', 'balance-read', 'prepare'])
def test_preowned_socket_close_failure_must_not_be_clean(stack, monkeypatch, record_property, phase):
    data = saved(stack, monkeypatch); client, _, rid, store = data
    native_close = transport._close_socket; fired = []
    def close(sock):
        native_close(sock)
        fired.append(True)
        if len(fired) == (2 if phase == 'prepare' else 1): raise OSError('owned pre-handoff close fault')
    monkeypatch.setattr(transport, '_close_socket', close)
    if phase == 'prepare':
        def prepare_failed(*args, **kwargs): raise OSError('owned failure after actual preconnection')
        monkeypatch.setattr(transport, '_Pending', prepare_failed)
    with provider(truncated_get=phase == 'balance-read') as (server, calls, _), installed(data, server, allow_uncertain=True) as resource:
        result = admitted(client, rid)
        with pytest.raises(Exception) as primary_failure: ResearchRunner(store).run_once(result['task_id'])
        if phase == 'balance-read': assert type(primary_failure.value) is ValueError
        with store.transaction() as conn:
            state = conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]
            money = conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]
        frames = []; trace = primary_failure.value.__traceback__
        while trace is not None:
            frames.append({'function': trace.tb_frame.f_code.co_name, 'line': trace.tb_lineno}); trace = trace.tb_next
        record_property('preowned_cleanup_fact', json.dumps({'run': state, 'money': money, 'runtime_unknown': resource._cleanup_unknown,
            'channels': len(resource._channels), 'owned_balance': len(transport._BALANCES), 'owned_return': len(transport._RETURNS),
            'primary_class': type(primary_failure.value).__name__, 'primary_frames': frames[-10:], 'close_calls': len(fired), 'requests': [v[0] for v in calls]}))
        assert fired and resource._cleanup_unknown and [v[0] for v in calls] == ['GET']
        assert state[2] == 'uncertain'


def test_insufficient_balance_is_not_resource_retirement_and_next_explicit_task_can_run(stack, monkeypatch):
    from .test_research_persistence import problem, envelope
    data = saved(stack, monkeypatch); client, _, rid, store = data
    with provider() as (server, calls, state), installed(data, server) as resource:
        state['balance'] = '0'
        first = admitted(client, rid)
        with pytest.raises(Exception) as denied: ResearchRunner(store).run_once(first['task_id'])
        assert denied.value.code == 'BUDGET_EXHAUSTED'
        resource.require()
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:] == ('closed', 'unreserved', 'clean')
        state['balance'] = '73'
        value = problem(); value['confirmed'] = True
        made = client.post('/api/research', json=envelope({'problem': value}), headers={'origin': BETA, 'idempotency-key': 'new-after-insufficient'})
        assert made.status_code == 200
        second = admitted(client, made.json()['data']['research']['id'])
        assert ResearchRunner(store).run_once(second['task_id'])['data']['state'] == 'saved'
        assert [v[0] for v in calls] == ['GET', 'GET', 'POST']
        assert len({v[3] for v in calls}) == 1


@pytest.mark.parametrize('fault', [False, True])
def test_retire_unhanded_is_io_only_and_uncertainty_is_sticky(stack, monkeypatch, fault):
    data = saved(stack, monkeypatch)
    with provider() as (server, calls, _), installed(data, server, allow_uncertain=fault) as resource:
        sock, peer = socket.socketpair()
        channel = transport._Channel(sock, time.monotonic() + 3, resource, _factory=transport._FACTORY)
        original_close = transport._close_socket
        def failed_close(value): original_close(value); raise OSError('owned unhanded close uncertainty')
        assert resource.flight.acquire(blocking=False)
        try:
            if fault:
                monkeypatch.setattr(transport, '_close_socket', failed_close)
                with pytest.raises(Exception) as unknown: resource.retire_unhanded()
                assert unknown.value.code == 'CLEANUP_UNCERTAIN'
                assert resource._uncertain_channels[channel.reference] is channel and channel.closed
                with pytest.raises(Exception): resource.retire_unhanded()
            else:
                assert resource.retire_unhanded() is None
                resource.require()
            assert resource.active and resource.permit.active and resource.permit.provision.active
            resource.permit.require()
            assert not resource.flight.acquire(blocking=False)
            assert calls == [] and channel.closed and not resource._channels
        finally:
            resource.flight.release(); peer.close()


def test_cancel_during_actual_balance_get_invalidates_cas_without_post(stack, monkeypatch):
    from .test_research_funded_plan import send
    data = saved(stack, monkeypatch); client, _, rid, store = data
    selected = {}
    def cancel():
        result = send(client, rid, 'cancel', {'task_id': selected['task_id'], 'expected_task_version': 1}, 'stop-during-balance')
        assert result.status_code == 200
    with provider(before_balance=cancel) as (server, calls, _), installed(data, server) as resource:
        selected.update(admitted(client, rid))
        with pytest.raises(Exception): ResearchRunner(store).run_once(selected['task_id'])
        assert [v[0] for v in calls] == ['GET']
        resource.require()
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (0, 0)


@pytest.mark.parametrize('action', ['cancel', 'delete'])
def test_actual_late_return_original_credential_books_fee_without_restoring_body(stack, monkeypatch, action):
    from .test_research_funded_plan import send
    data = saved(stack, monkeypatch); client, _, rid, store = data
    ready, go = threading.Event(), threading.Event(); errors = []; original = flow._commit_return
    def delayed(*args):
        ready.set(); assert go.wait(5)
        return original(*args)
    monkeypatch.setattr(flow, '_commit_return', delayed)
    with provider() as (server, calls, _), installed(data, server):
        result = admitted(client, rid)
        def run():
            try: ResearchRunner(store).run_once(result['task_id'])
            except BaseException as error: errors.append(type(error).__name__)
        thread = threading.Thread(target=run); thread.start()
        try:
            assert ready.wait(5)
            stopped = (send(client, rid, 'cancel', {'task_id': result['task_id'], 'expected_task_version': 2}, 'late-stop')
                if action == 'cancel' else client.post('/api/me/delete', json={'confirmation': 'DELETE'}, headers={'origin': BETA}))
            assert stopped.status_code == 200
        finally: go.set(); thread.join(7)
        assert not thread.is_alive() and errors == []
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state,result_json FROM research_plan_native_runs').fetchone()[:] == ('closed', 'upper_booked', 'clean', None)
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:] == (0, flow.UPPER)
        assert [v[0] for v in calls] == ['GET', 'POST']


@pytest.mark.parametrize('raw', [b'HTTP/1.0 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx',
    b'HTTP/1.0 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
    b'HTTP/1.0 200 OK\r\nContent-Length: 3\r\n\r\nx', b'HTTP/1.0 200 OK\r\n\r\n' + b'x' * 65537])
def test_http_bounds_and_ambiguous_headers_rejected(raw):
    with pytest.raises(ValueError): transport._parse_response(raw)


def test_native_channel_deadline_does_not_wait_or_write():
    sock, peer = socket.socketpair()
    channel = transport._Channel(sock, time.monotonic() - 1, _factory=transport._FACTORY)
    try:
        with pytest.raises(TimeoutError): channel.send_first(b'owned')
        with pytest.raises(TimeoutError): channel.receive()
        peer.setblocking(False)
        with pytest.raises(BlockingIOError): peer.recv(10)
    finally: channel.close(); peer.close()
    assert channel.closed


def test_receive_retries_same_recv_after_wantwrite_ready(monkeypatch, record_property):
    client, peer = socket.socketpair(); client.setblocking(False)
    channel = transport._Channel(client, time.monotonic() + .5, _factory=transport._FACTORY)
    native_recv = socket.socket.recv; calls = []; retry = threading.Event(); stop = threading.Event()
    outcome = None; error = None
    def receive(sock, size, *args, **kwargs):
        if sock is client:
            calls.append('recv')
            if len(calls) == 1:
                assert native_recv(sock, size, *args, **kwargs) == b'handshake-record'
                raise ssl.SSLWantWriteError('owned recv needs writable progress')
            retry.set()
        return native_recv(sock, size, *args, **kwargs)
    def serve():
        peer.sendall(b'handshake-record')
        if retry.wait(1.5) and not stop.is_set():
            peer.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok')
            peer.shutdown(socket.SHUT_WR)
    thread = threading.Thread(target=serve); thread.start()
    monkeypatch.setattr(socket.socket, 'recv', receive)
    try:
        try: outcome = channel.receive()
        except Exception as exc: error = type(exc).__name__
        record_property('recv_continuation', json.dumps({'error': error, 'recv_calls': len(calls),
            'retried_after_writable': retry.is_set(), 'actual_HTTP_body': outcome == (200, b'ok'),
            'scope': 'actual socketpair/control bytes; explicitly injected SSLWantWrite, not natural TLS/provider'}))
        assert error is None and outcome == (200, b'ok')
        assert retry.is_set() and len(calls) >= 2
    finally:
        stop.set(); retry.set(); thread.join(2); channel.close(); peer.close()
        assert not thread.is_alive()


def test_remainder_send_retries_same_send_after_wantread_ready(monkeypatch, record_property):
    client, peer = socket.socketpair(); client.setblocking(False); peer.setblocking(False)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    channel = transport._Channel(client, time.monotonic() + .5, _factory=transport._FACTORY)
    native_send, native_recv = socket.socket.send, socket.socket.recv
    calls = []; fill = []; error = None; payload = b'owned-current-request-tail'
    def send(sock, data, *args, **kwargs):
        if sock is client:
            calls.append('send')
            if len(calls) == 1:
                while True:
                    try: fill.append(native_send(sock, b'x' * 4096))
                    except BlockingIOError: break
                assert sum(fill) > 0
                assert native_send(peer, b'read-control') == len(b'read-control')
                raise ssl.SSLWantReadError('owned remainder needs readable progress')
            if len(calls) == 2:
                assert native_recv(client, 100) == b'read-control'
                drained = bytearray()
                while True:
                    try: drained.extend(native_recv(peer, 16384))
                    except BlockingIOError: break
                assert drained == b'x' * sum(fill)
        return native_send(sock, data, *args, **kwargs)
    monkeypatch.setattr(socket.socket, 'send', send)
    try:
        try: channel.send_remaining(payload)
        except Exception as exc: error = type(exc).__name__
        record_property('send_continuation', json.dumps({'error': error, 'send_calls': len(calls),
            'retried_after_readable': len(calls) >= 2, 'scope': 'actual filled socket/control bytes plus injected SSLWantRead; remainder only'}))
        assert error is None and len(calls) >= 2
        assert native_recv(peer, 4096) == payload
    finally: channel.close(); peer.close()


@pytest.mark.parametrize('fault', ['detached', 'no-close'])
def test_native_close_needs_actual_fd_proof_and_preserves_unknown(monkeypatch, fault):
    sock, peer = socket.socketpair()
    channel = transport._Channel(sock, time.monotonic() + 3, _factory=transport._FACTORY)
    detached = None
    try:
        with monkeypatch.context() as failure:
            if fault == 'detached': detached = sock.detach()
            else: failure.setattr(transport, '_close_socket', lambda _: None)
            with pytest.raises(Exception) as unknown: channel.close()
            assert unknown.value.code == 'CLEANUP_UNCERTAIN'
            assert not channel.closed and transport._CHANNELS[channel.reference] is channel
        if detached is not None: os.close(detached); detached = None
        with pytest.raises(Exception) as retired: channel.close()
        assert retired.value.code == 'CLEANUP_UNCERTAIN' and channel.closed
        assert channel.reference not in transport._CHANNELS
    finally:
        if detached is not None: os.close(detached)
        sock.close(); peer.close()


def certificate(tmp_path, hostname):
    key, cert, config = tmp_path / 'server.key', tmp_path / 'server.pem', tmp_path / 'openssl.cnf'
    config.write_text('[req]\nprompt=no\ndistinguished_name=dn\nx509_extensions=ext\n[dn]\nCN=' + hostname + '\n[ext]\nsubjectAltName=DNS:' + hostname + '\nbasicConstraints=critical,CA:TRUE\nkeyUsage=digitalSignature,keyEncipherment,keyCertSign\nextendedKeyUsage=serverAuth\n')
    command = [shutil.which('openssl'), 'req', '-x509', '-newkey', 'rsa:2048', '-sha256', '-nodes', '-days', '1', '-keyout', str(key), '-out', str(cert), '-config', str(config)]
    subprocess.run(command, check=True, capture_output=True, timeout=10)
    key.chmod(0o600)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); server.load_cert_chain(cert, key)
    return server, cert


@pytest.mark.parametrize('kind', ['trusted', 'untrusted', 'wrong-host'])
def test_actual_owned_tls_component_verifies_chain_and_fixed_hostname(tmp_path, kind):
    server_context, cert = certificate(tmp_path, 'wrong.invalid' if kind == 'wrong-host' else 'api.deepseek.com')
    with provider(tls=server_context) as (server, calls, _):
        sock = socket.create_connection(('127.0.0.1', server.server_port), timeout=2); sock.setblocking(False)
        channel = transport._Channel(sock, time.monotonic() + 4, _factory=transport._FACTORY)
        context = ssl.create_default_context(cafile=str(cert)) if kind != 'untrusted' else ssl.create_default_context()
        try:
            if kind != 'trusted':
                with pytest.raises(ssl.SSLCertVerificationError): transport._upgrade_tls(channel, context)
                assert calls == []
            else:
                transport._upgrade_tls(channel, context)
                channel.send_remaining(b'GET /user/balance HTTP/1.0\r\nHost: api.deepseek.com\r\n\r\n')
                status, body = channel.receive()
                assert status == 200 and json.loads(body)['is_available'] and len(calls) == 1
        finally: channel.close()
        assert channel.closed
