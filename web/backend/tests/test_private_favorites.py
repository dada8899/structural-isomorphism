"""Private Favorites ownership, native JSONL transactions and signed SSO."""
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import parse_qs, urlsplit
import asyncio
import copy
import hashlib
import importlib
import json
import os
import sqlite3
import time
import concurrent.futures

import jwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from api import auth, favorites, sso, report, report_account
from services import runtime_paths as paths
from services.auth_store import AuthStore
from services.report_store import ReportStore
from errors import install_problem_handlers
from .test_private_sso_store import private, native, shared_assets, SECRET
from .test_private_registration import register_private_user

ALICE = 'alice@example.invalid'
BOB = 'bob@example.invalid'
BETA = 'https://beta.structural.bytedance.city'
PHASE = 'https://phase.bytedance.city'


@pytest.fixture
def stack(private, monkeypatch):
    shared_assets(private, monkeypatch)
    state = private.parent
    for email in (ALICE, BOB):register_private_user(monkeypatch,email,'pro')
    for name in ('favorites.jsonl', 'favorites.lock', 'account_deletion_audit.jsonl'):
        (state / name).write_bytes(b'')
        (state / name).chmod(0o600)
    settings = {'AUTH_ENABLED': 'true', 'AUTH_DEV_MODE': 'false',
        'AUTH_SITE_ROLE': 'beta', 'AUTH_LINK_BASE_URL': BETA, 'JWT_SECRET': SECRET,
        'SMTP_HOST': 'fixture.invalid', 'SMTP_PORT': '587', 'SMTP_FROM_EMAIL': 'sender@example.invalid',
        'ADMIN_NOTIFICATION_EMAIL': 'admin@example.invalid', 'AUTH_TRUSTED_PROXY_IPS': '127.0.0.1', 'STRUCTURAL_HISTORY_DB': str(state / 'history.db')}
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv('STRUCTURAL_FAVORITES_PATH', raising=False)
    monkeypatch.setattr(favorites, '_legacy_data_file', lambda: state / 'unowned-legacy.jsonl')
    app = FastAPI()
    for router in (auth.router, favorites.router, sso.router):
        app.include_router(router, prefix='/api')
    install_problem_handlers(app)
    with TestClient(app, base_url=BETA) as client:
        token = private_session(ALICE)
        client.cookies.set('phase_session', token)
        yield client, state, app


def favorite_bytes(state):
    return (state / 'favorites.jsonl').read_bytes()


def records(state):
    return [json.loads(line) for line in favorite_bytes(state).splitlines() if line]


def request_for(token, *, sso_cookie=False):
    name = 'structural_beta_session' if sso_cookie else 'phase_session'
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'scheme': 'https',
        'server': ('beta.structural.bytedance.city', 443),
        'headers': [(b'host', b'beta.structural.bytedance.city'), (b'cookie', (name + '=' + token).encode())]})


def private_session(email,tier='pro'):
    with pytest.MonkeyPatch.context() as patch:
        return register_private_user(patch,email,tier)[1]


def retire_auth_incarnation(email):
    """Real protected delete, deliberately retaining separate fixture assets.

    These tests model leftover old Favorites/SSO material, so the explicit
    fixture registry includes only authentication. No Auth capability is faked.
    """
    from services.account_data_registry import AccountDataRegistry
    original=auth._account_registry
    def auth_only(**kwargs):
        registry=original(**kwargs)
        return AccountDataRegistry([asset for asset in registry.assets if asset.name=='authentication'])
    token=private_session(email)
    app=FastAPI();app.include_router(auth.router,prefix='/api')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(auth,'_account_registry',auth_only)
        with TestClient(app,base_url=BETA) as client:
            client.cookies.set('phase_session',token)
            response=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})
            assert response.status_code==200,response.text


def deletion_request_source(email):
    from research.paid_control import issue_authenticated_action
    token=private_session(email)
    request=Request({'type':'http','method':'POST','path':'/api/me/delete','scheme':'https',
        'server':('beta.structural.bytedance.city',443),'headers':[(b'host',b'beta.structural.bytedance.city'),
            (b'origin',BETA.encode()),(b'cookie',('phase_session='+token).encode())]})
    return issue_authenticated_action(request,action='account-delete')


@contextmanager
def deletion_context(email=ALICE):
    service = auth._account_deletion_service()
    generation = auth._store().user(email)['session_generation']
    source=deletion_request_source(email)
    try:
        with auth.account_owner_transaction(email) as lease:
            job_id = service.begin_account_deletion_locked(email, generation,
                auth._store().owner_gate_id(email), auth._account_cleanup_binding(email), owner_lease=lease,request_source=source)
            with auth._favorites_authority(email, generation, lease, service=service, job_id=job_id) as authority:
                yield service, job_id, authority
    finally:source.close()


def exchange_material(stack, monkeypatch):
    client, state, app = stack
    # The actual production issuer and consumer use their distinct origins
    # with the same synthetic authoritative AuthStore, not a copied DTO.
    with TestClient(app, base_url=PHASE) as phase:
        token = private_session(ALICE)
        phase.cookies.set('phase_session', token)
        started = client.get('/api/sso/start', follow_redirects=False)
        assert started.status_code == 303
        query = parse_qs(urlsplit(started.headers['location']).query)
        with monkeypatch.context() as issuer:
            issuer.setenv('AUTH_SITE_ROLE', 'phase')
            issuer.setenv('AUTH_LINK_BASE_URL', PHASE)
            issued = phase.post('/api/sso/issue', headers={'Origin': PHASE}, json={
                'audience': 'structural-beta', 'state': query['state'][0], 'nonce': query['nonce'][0]})
        assert issued.status_code == 200, issued.text
    code = issued.json()['code']
    claims = jwt.decode(code, SECRET, algorithms=['HS256'], audience='structural-beta', issuer=PHASE)
    client.cookies.delete('phase_session')
    return client, code, query['state'][0], claims


def test_direct_and_export_private_generation_never_enters_public_dto(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL', headers={'Origin': BETA}).status_code == 201
    listed = client.get('/api/favorites')
    assert listed.status_code == 200 and listed.json()['tickers'] == ['AAPL']
    stored = records(state)[0]
    assert stored['_favorites_owner']['generation'] == auth._store().user(ALICE)['session_generation']
    exported = client.get('/api/me/export')
    assert exported.status_code == 200, exported.text
    assert exported.json()['data']['favorites']['tickers'] == ['AAPL']
    for response in (listed, exported, client.get('/api/auth/me')):
        assert '_verified_generation' not in response.text and '_favorites_owner' not in response.text
        assert stored['_favorites_owner']['generation'] not in response.text


def test_formal_old_email_records_remain_unowned_and_opaque(stack, native):
    client, state, _ = stack
    legacy = {'email': ALICE, 'tickers': ['LEGACY'], 'future': {'raw': [None, {'x': 1}]}}
    (state / 'favorites.jsonl').write_text(json.dumps(legacy) + '\n')
    assert client.get('/api/favorites').json()['tickers'] == []
    assert client.post('/api/favorites/MSFT').status_code == 201
    assert client.get('/api/favorites').json()['tickers'] == ['MSFT']
    assert records(state)[0] == legacy
    deleted = client.post('/api/me/delete', json={'confirmation': 'DELETE'})
    assert deleted.status_code == 200, deleted.text
    assert records(state)[0] == legacy
    assert b'LEGACY' in favorite_bytes(state)


def test_new_exchange_signs_same_verified_generation_and_uses_favorites(stack, native, monkeypatch):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    generation = auth._store().user(ALICE)['session_generation']
    assert claims['gen'] == generation
    response = client.post('/api/sso/exchange', json={'code': code, 'state': state})
    assert response.status_code == 200, response.text
    token = client.cookies.get('structural_beta_session')
    session = jwt.decode(token, SECRET, algorithms=['HS256'], audience='structural-beta-session', issuer=BETA)
    assert session['gen'] == generation
    assert client.post('/api/favorites/AAPL').status_code == 201
    assert client.get('/api/favorites').json()['tickers'] == ['AAPL']
    assert client.get('/api/me/export').json()['data']['favorites']['tickers'] == ['AAPL']


@pytest.mark.parametrize('bad', [None, '', 0, True, [], {}, 'G' * 32, 'a' * 31])
def test_present_invalid_code_generation_never_consumes(stack, native, monkeypatch, bad):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    claims['gen'] = bad
    tampered = jwt.encode(claims, SECRET, algorithm='HS256')
    result = client.post('/api/sso/exchange', json={'code': tampered, 'state': state})
    assert result.status_code == 401
    assert sso.get_replay_store().lookup_issued(claims['jti']) is not None
    assert not result.headers.get('set-cookie')


def test_missing_generation_code_retired_and_new_generation_code_cannot_be_upgraded(stack, native, monkeypatch):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    old = dict(claims);old.pop('gen')
    assert client.post('/api/sso/exchange', json={'code': jwt.encode(old, SECRET, algorithm='HS256'), 'state': state}).status_code == 401
    # A real account erase/re-registration changes the persisted generation.
    retire_auth_incarnation(ALICE)
    private_session(ALICE)
    assert auth._store().user(ALICE)['session_generation'] != claims['gen']
    assert client.post('/api/sso/exchange', json={'code': code, 'state': state}).status_code == 401
    assert sso.get_replay_store().lookup_issued(claims['jti']) is not None


def test_wrong_nonce_and_existing_other_cookie_do_not_consume(stack, native, monkeypatch):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    wrong = dict(claims);wrong['nonce'] = 'other-nonce'
    assert client.post('/api/sso/exchange', json={'code': jwt.encode(wrong, SECRET, algorithm='HS256'), 'state': state}).status_code == 400
    token = private_session(BOB);client.cookies.set('phase_session', token)
    assert client.post('/api/sso/exchange', json={'code': code, 'state': state}).status_code == 409
    assert sso.get_replay_store().lookup_issued(claims['jti']) is not None


def test_snapshot_delete_restore_is_single_use_and_preserves_unknown_record_fields(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    raw = records(state);raw[0]['unknown'] = {'values': [1, None, {'x': 'future'}]}
    (state / 'favorites.jsonl').write_text(''.join(json.dumps(v) + '\n' for v in raw))
    with deletion_context() as (_, _, authority):
        registry = auth._account_registry(favorites_authority=authority)
        item = registry.assets[0]
        snapshot = item.snapshot(ALICE)
        removed = item.delete(ALICE)
        assert removed == {'records': 1, 'tickers': 1, 'bookmarks': 0}
        assert all('email' not in v for v in records(state))
        item.restore(ALICE, snapshot, removed)
        assert records(state)[0]['unknown'] == raw[0]['unknown']
        assert records(state)[0]['_favorites_owner']['revision'] != raw[0]['_favorites_owner']['revision']
        before = favorite_bytes(state)
        with pytest.raises(PermissionError):item.restore(ALICE, snapshot, removed)
        assert favorite_bytes(state) == before


def test_snapshot_or_receipt_without_live_job_lease_never_authorizes_restore(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    with deletion_context() as (_, _, authority):
        registry = auth._account_registry(favorites_authority=authority)
        item = registry.assets[0];snapshot = item.snapshot(ALICE);removed = item.delete(ALICE)
    before = favorite_bytes(state)
    with pytest.raises(PermissionError):item.restore(ALICE, snapshot, removed)
    with pytest.raises(PermissionError):favorites.restore_account_favorites(ALICE, snapshot, removed)
    assert favorite_bytes(state) == before


@pytest.mark.parametrize('bad', [None, '', 0, True, [], {}, 'G' * 32, 'a' * 31])
@pytest.mark.parametrize('profile', ['dev', 'prod'])
def test_present_bad_session_generation_rejected_in_every_profile(stack, native, monkeypatch, bad, profile):
    _, _, _ = stack
    ledger = sso.get_replay_store();subject = sso._subject_id(ALICE)
    ledger.issue('session-link', subject, 'pro', int(time.time()) + 300, email=ALICE)
    claims = {'iss': BETA, 'aud': 'structural-beta-session', 'sub': subject,
        'iat': int(time.time()), 'exp': int(time.time()) + 300, 'issued_ns': time.time_ns(), 'gen': bad}
    token = jwt.encode(claims, SECRET, algorithm='HS256')
    monkeypatch.setenv('STRUCTURAL_ENV', profile)
    assert sso.resolve_beta_user(request_for(token, sso_cookie=True))[1] == 'invalid'


def test_only_absent_dev_generation_has_legacy_compatibility_never_formal(stack, native, monkeypatch):
    client, _, _ = stack
    ledger = sso.get_replay_store();subject = sso._subject_id(ALICE)
    ledger.issue('old-session-link', subject, 'pro', int(time.time()) + 300, email=ALICE)
    claims = {'iss': BETA, 'aud': 'structural-beta-session', 'sub': subject,
        'iat': int(time.time()), 'exp': int(time.time()) + 300, 'issued_ns': time.time_ns()}
    token = jwt.encode(claims, SECRET, algorithm='HS256')
    client.cookies.delete('phase_session');client.cookies.set('structural_beta_session', token)
    retired = client.get('/api/favorites')
    assert retired.status_code == 401 and 'retired' in retired.text and 'sign in again' in retired.text
    exported = client.get('/api/me/export')
    assert exported.status_code == 401 and 'retired' in exported.text
    with monkeypatch.context() as dev:
        dev.setenv('STRUCTURAL_ENV', 'dev')
        user, status = sso.resolve_beta_user(request_for(token, sso_cookie=True))
        assert status == 'valid' and '_verified_generation' not in user
    assert sso.resolve_beta_user(request_for(token, sso_cookie=True))[1] == 'retired'


@pytest.mark.parametrize('fault', ['missing', 'lock-missing', 'bad-json', 'utf8', 'unfinished', 'duplicate-owner', 'duplicate-key', 'symlink', 'hardlink', 'mode', 'lock-mode', 'open-denied'])
def test_private_missing_or_unsafe_storage_never_becomes_empty_or_overwritten(stack, native, monkeypatch, fault):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    target = state / 'favorites.jsonl'
    if fault == 'missing':
        (state / 'unowned-legacy.jsonl').write_bytes(target.read_bytes())
        target.unlink()
    elif fault == 'lock-missing':(state / 'favorites.lock').unlink()
    elif fault == 'bad-json':target.write_bytes(b'not-json\n')
    elif fault == 'utf8':target.write_bytes(b'\xff\n')
    elif fault == 'unfinished':target.write_bytes(target.read_bytes().rstrip(b'\n'))
    elif fault == 'duplicate-owner':target.write_bytes(target.read_bytes() * 2)
    elif fault == 'duplicate-key':target.write_bytes(b'{"email":"alice@example.invalid","email":"bob@example.invalid"}\n')
    elif fault == 'symlink':
        kept = state / 'kept.jsonl';target.rename(kept);target.symlink_to(kept)
    elif fault == 'hardlink':os.link(target, state / 'alias.jsonl')
    elif fault == 'mode':target.chmod(0o644)
    elif fault == 'lock-mode':(state / 'favorites.lock').chmod(0o644)
    elif fault == 'open-denied':
        original_open = os.open
        def denied(name, flags, *args, **kwargs):
            if name == 'favorites.jsonl':raise PermissionError('synthetic file ACL denies reading')
            return original_open(name, flags, *args, **kwargs)
        monkeypatch.setattr(paths.os, 'open', denied)
    before = target.read_bytes() if target.exists() else None
    listed = client.get('/api/favorites')
    written = client.post('/api/favorites/MSFT')
    assert listed.status_code == written.status_code == 503
    assert (target.read_bytes() if target.exists() else None) == before
    assert list(state.glob('.favorites-*.jsonl.tmp')) == []
    with pytest.raises((paths.RuntimePathError, FileNotFoundError)):
        favorites._migrate_legacy_file(target)


def test_formal_api_key_without_verified_generation_is_rejected(stack, native):
    from auth.api_key import APIKey
    client, state, _ = stack
    client.cookies.clear()
    key = APIKey(key='fixture-unused', tier='pro', owner_email=ALICE, created_at='2026-10-17T00:00:00+00:00')
    with pytest.raises(Exception) as denied:
        favorites._resolve_user(request_for(''), key)
    assert getattr(denied.value, 'status', None) == 401
    assert favorite_bytes(state) == b''


@pytest.mark.parametrize('fault', ['write', 'partial-write', 'short-write', 'file-fsync', 'replace-before', 'replace-after', 'directory-fsync'])
def test_write_failures_distinguish_unchanged_and_unknown_result(stack, native, monkeypatch, fault):
    import stat
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    before = favorite_bytes(state);replace = os.replace;write = os.write;fsync = os.fsync
    if fault in {'write', 'partial-write', 'short-write'}:
        written_once = []
        def broken(fd, payload):
            if fault == 'partial-write' and not written_once:
                written_once.append(True)
                return write(fd, payload[:5])
            if fault == 'short-write':
                return write(fd, payload[:max(1, len(payload) // 3)])
            raise OSError('synthetic write failure')
        monkeypatch.setattr(paths.os, 'write', broken)
    elif fault in {'file-fsync', 'directory-fsync'}:
        def broken(fd):
            is_directory = stat.S_ISDIR(os.fstat(fd).st_mode)
            if is_directory == (fault == 'directory-fsync'):
                raise OSError('synthetic fsync failure')
            return fsync(fd)
        monkeypatch.setattr(paths.os, 'fsync', broken)
    else:
        def broken(*args, **kwargs):
            if fault == 'replace-after':replace(*args, **kwargs)
            raise OSError('synthetic replace failure')
        monkeypatch.setattr(paths.os, 'replace', broken)
    result = client.post('/api/favorites/MSFT')
    if fault == 'short-write':
        assert result.status_code == 201
        assert client.get('/api/favorites').json()['tickers'] == ['AAPL', 'MSFT']
    else:
        assert result.status_code == 503
        if fault in {'replace-after', 'directory-fsync'}:
            assert 'favorites_storage_result_unknown' in result.text
            assert [v for v in records(state) if '_favorites_owner' in v][0]['tickers'] == ['AAPL', 'MSFT']
        else:
            assert favorite_bytes(state) == before
    assert list(state.glob('.favorites-*.jsonl.tmp')) == []


def test_delete_lost_replace_receipt_reconciles_before_generic_compensation(stack, native, monkeypatch):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    replace = os.replace;events = []
    with deletion_context() as (_, _, authority):
        registry = auth._account_registry(favorites_authority=authority)
        item = registry.assets[0];snapshot = item.snapshot(ALICE)
        def lost(*args, **kwargs):
            replace(*args, **kwargs);events.append('committed-replace')
            raise OSError('lost rename receipt')
        with monkeypatch.context() as fault:
            fault.setattr(paths.os, 'replace', lost)
            result = item.delete(ALICE)
        assert result['records'] == 1 and events == ['committed-replace']
        assert records(state)[0]['_favorites_tombstone']['operation_id'] == snapshot['operation_id']
        item.restore(ALICE, snapshot, result)
        assert records(state)[0]['tickers'] == ['AAPL']


def test_unknown_delete_durability_stays_pending_without_blind_restore(stack, native, monkeypatch):
    import stat
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    with deletion_context() as (service, job_id, authority):
        registry = auth._account_registry(favorites_authority=authority)
        fsync = os.fsync
        def failed(fd):
            if stat.S_ISDIR(os.fstat(fd).st_mode):raise OSError('persistent directory durability failure')
            return fsync(fd)
        with monkeypatch.context() as fault:
            fault.setattr(paths.os, 'fsync', failed)
            with pytest.raises(paths.FavoritesWriteUnknown):registry.delete_all(ALICE)
        current = records(state)
        assert len(current) == 1 and '_favorites_tombstone' in current[0]
        assert service.deletion_job(job_id)['state'] == 'pending'
        assert auth._store().user(ALICE)['lifecycle'] == 'deleting'
        # A fresh registry can observe absence, but cannot invent the lost
        # snapshot, remove the marker, or automatically restore old contents.
        retry = auth._account_registry(favorites_authority=authority).assets[0]
        observed = retry.snapshot(ALICE)
        assert observed['exists'] is False and retry.delete(ALICE)['records'] == 0
        assert records(state) == current


def test_full_formal_delete_recovery_keeps_other_owner_and_new_incarnation_separate(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    old_token = client.cookies.get('phase_session')
    alice_record = copy.deepcopy(records(state)[0])
    bob_token = private_session(BOB);client.cookies.set('phase_session', bob_token)
    assert client.post('/api/favorites/MSFT').status_code == 201
    bob_before = next(v for v in records(state) if v.get('email') == BOB)
    client.cookies.set('phase_session', old_token)
    with deletion_context() as (service, job_id, authority):
        result = auth._run_account_deletion_locked(service, job_id, owner_lease=authority.lease)
        assert result['removed']['favorites']['records'] == 1
    assert auth.resume_account_deletion(job_id) == result
    assert client.get('/api/favorites').status_code == 401
    private_session(ALICE)
    new_token = private_session(ALICE);client.cookies.set('phase_session', new_token)
    assert client.get('/api/favorites').json()['tickers'] == []
    assert client.post('/api/favorites/GOOG').status_code == 201
    assert not any('_favorites_tombstone' in v and v['_favorites_tombstone']['owner_key'] == alice_record['_favorites_owner']['owner_key'] for v in records(state))
    assert next(v for v in records(state) if v.get('email') == BOB) == bob_before
    assert next(v for v in records(state) if v.get('email') == ALICE)['_favorites_owner']['generation'] != alice_record['_favorites_owner']['generation']


def test_snapshot_revision_cas_and_repeat_delete_prevent_old_restore(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    with deletion_context() as (_, _, authority):
        registry = auth._account_registry(favorites_authority=authority);item = registry.assets[0]
        first = item.snapshot(ALICE);removed = item.delete(ALICE);item.restore(ALICE, first, removed)
        # Restore returns the same content with a new revision. The old
        # snapshot cannot delete this ABA incarnation of the record.
        before = favorite_bytes(state)
        with pytest.raises(PermissionError):favorites._delete_private_favorites(ALICE, first)
        assert favorite_bytes(state) == before
        second = item.snapshot(ALICE);item.delete(ALICE)
        current = favorite_bytes(state)
        with pytest.raises(PermissionError):favorites.restore_account_favorites(ALICE, first, removed)
        assert favorite_bytes(state) == current
        item.restore(ALICE, second, removed)


def test_generic_compensation_only_restores_its_confirmed_favorites_operation(stack, native, monkeypatch):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    # A real native auth-store failure happens after Favorites was confirmed
    # and after report deletion; original registry compensation is exercised.
    original = AuthStore.delete_account_data
    def failed(self, email, **kwargs):
        raise OSError('synthetic later auth-store failure')
    with monkeypatch.context() as fault:
        fault.setattr(AuthStore, 'delete_account_data', failed)
        result = client.post('/api/me/delete', json={'confirmation': 'DELETE'})
    assert result.status_code == 500 and result.json()['deletion_state'] == 'cleanup_pending'
    assert records(state)[0]['tickers'] == ['AAPL']
    assert client.get('/api/favorites').status_code == 401
    job_id = auth.pending_account_deletions()[0]
    result = auth.resume_account_deletion(job_id)
    assert result['removed']['favorites']['count_status'] == 'unknown_after_interruption'
    assert not any('_favorites_owner' in v and v.get('email') == ALICE for v in records(state))
    assert auth.resume_account_deletion(job_id) == result


def test_only_this_registry_snapshot_and_target_owner_can_compensate(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    with deletion_context() as (_, _, authority):
        item = auth._account_registry(favorites_authority=authority).assets[0]
        snapshot = item.snapshot(ALICE);removed = item.delete(ALICE)
        before = favorite_bytes(state)
        with pytest.raises(PermissionError):item.restore(ALICE, copy.deepcopy(snapshot), removed)
        with pytest.raises(PermissionError):item.restore(BOB, snapshot, removed)
        with pytest.raises(PermissionError):item.delete(BOB)
        assert favorite_bytes(state) == before
        item.restore(ALICE, snapshot, removed)


_FAVORITES_CHILD = r'''
import sys,os,json,sqlite3,socket,time,asyncio
from pathlib import Path
from contextlib import contextmanager
from urllib.parse import urlsplit,unquote
owned=Path(os.environ['TMPDIR']).resolve();fdpaths={};connections=[]
real_open,real_close=os.open,os.close

def location(value,dir_fd=None):
 if isinstance(value,int):return fdpaths.get(value)
 p=Path(os.fsdecode(value))
 if not p.is_absolute():
  if dir_fd is not None and dir_fd>=0:
   assert dir_fd in fdpaths,'unknown dir fd';p=fdpaths[dir_fd]/p
  else:p=Path.cwd()/p
 return p

def own(p):return p is not None and (p==owned or p.is_relative_to(owned))
def opened(value,flags,*args,**kw):
 fd=real_open(value,flags,*args,**kw);fdpaths[fd]=location(value,kw.get('dir_fd'));return fd
def closed(fd):
 try:return real_close(fd)
 finally:fdpaths.pop(fd,None)
os.open=opened;os.close=closed

def audit(event,args):
 if event=='open':
  value,mode,flags=args;p=location(value);text=str(p).lower()
  assert not any(v in text for v in ('/models/','/huggingface/','/.ssh/','1password'))
  assert not text.endswith(('.env','.env.runtime','.bin','.safetensors','.pt','.ckpt'))
  writing=(isinstance(mode,str) and any(v in mode for v in 'wax+')) or (isinstance(flags,int) and flags&(os.O_CREAT|os.O_WRONLY|os.O_RDWR|os.O_APPEND|os.O_TRUNC))
  # An os.open relative path is checked at the wrapper below using its dirfd.
  if writing and not own(p):
   frame=sys._getframe().f_back
   assert frame.f_code.co_name=='opened' and own(location(value,frame.f_locals.get('kw',{}).get('dir_fd'))),'outside write'
 elif event in ('os.mkdir','os.remove','os.rmdir','os.chmod'):
  assert own(location(args[0],args[-1] if isinstance(args[-1],int) else None)),'outside mutation'
 elif event in ('os.rename','os.link'):
  assert own(location(args[0],args[2])) and own(location(args[1],args[3])),'outside rename'
 elif event=='sqlite3.connect':
  v=str(args[0]);parsed=urlsplit(v) if v.startswith('file:') else None
  assert v==':memory:' or own(location(unquote(parsed.path) if parsed else v)),'outside sqlite'
 elif event=='socket.__new__':assert args[1] not in (socket.AF_INET,socket.AF_INET6),'network'
 elif event in ('socket.connect','socket.getaddrinfo'):raise AssertionError('network')
 elif event=='import':assert args[0].split('.')[0] not in ('torch','transformers','sentence_transformers','huggingface_hub'),'model'
sys.addaudithook(audit)
root,state,mode,token,ticker,ready,go=sys.argv[1:8];state=Path(state)
sys.path[:0]=[str(Path(root)/'web/backend'),root]
from services import runtime_paths as paths
paths.STATE_ROOT=state;paths.CACHE_ROOT=state.parent/'cache';paths.LOG_ROOT=state/'logs'
real_connect=sqlite3.connect
def observed(*a,**kw):
 c=real_connect(*a,**kw);connections.append(c);return c
sqlite3.connect=observed
from api import auth,favorites
from starlette.requests import Request
if mode=='crash-lock':
 with paths.private_favorites_transaction():os._exit(0)
if mode=='missing':
 try:paths.PrivateFavoritesFile().acquire()
 except (FileNotFoundError,paths.RuntimePathError):pass
 else:raise AssertionError('missing accepted')
 assert not (state/'favorites.jsonl').exists() and not connections
 result=503
elif mode=='resume':
 result=auth.resume_account_deletion(token)['removed']['favorites']['count_status']
else:
 if mode=='queued-write':
  original=favorites.account_owner_transaction
  @contextmanager
  def waiting(owner):
   Path(ready).write_text('ready')
   end=time.monotonic()+8
   while not Path(go).exists():
    assert time.monotonic()<end;time.sleep(.01)
   with original(owner) as lease:yield lease
  favorites.account_owner_transaction=waiting
 else:
  Path(ready).write_text('ready')
  end=time.monotonic()+8
  while not Path(go).exists():
   assert time.monotonic()<end;time.sleep(.01)
 request=Request({'type':'http','method':'POST','path':'/api/favorites/'+ticker,'scheme':'https',
  'server':('beta.structural.bytedance.city',443),'headers':[(b'host',b'beta.structural.bytedance.city'),(b'cookie',('phase_session='+token).encode())]})
 try:
  response=asyncio.run(favorites.add_favorite(ticker,request,None));result=getattr(response,'status_code',201)
 except Exception as exc:
  if getattr(exc,'status',None) is None:raise
  result=exc.status
  # Only bounded identifiers and code locations; never exception text,
  # filenames, arguments, locals, headers, bodies or credential values.
  import re as _diagnostic_re
  def _identifier(value):
   return value if type(value) is str and _diagnostic_re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}',value) else None
  def _safe_exception(error,relation):
   slug=getattr(error,'type_slug',None);code=getattr(error,'code',None)
   frames=[];trace=error.__traceback__
   while trace is not None:
    frames.append({'function':_identifier(trace.tb_frame.f_code.co_name) or 'module','line':trace.tb_lineno})
    trace=trace.tb_next
   sqlname=getattr(error,'sqlite_errorname',None)
   return {'relation':relation,'class':_identifier(type(error).__name__),
    'type_slug':slug if type(slug) is str and slug in {'favorites_storage_unavailable','favorites_storage_result_unknown','upstream_unavailable','unauthenticated','forbidden','credential_conflict'} else None,
    'code':code if type(code) is str and code in {'STORE_BUSY','STORE_UNAVAILABLE','SCHEMA_UNSUPPORTED','AUTH_REQUIRED','AUTHORIZATION_STALE'} else None,
    'sqlite_errorname':_identifier(sqlname) if type(sqlname) is str and sqlname.startswith('SQLITE_') else None,
    'frames':frames[-12:]}
  _safe_error=[];_pending_errors=[('exception',exc)];_seen_errors=set()
  while _pending_errors and len(_safe_error)<6:
   _relation,_error=_pending_errors.pop(0)
   if _error is None or id(_error) in _seen_errors:continue
   _seen_errors.add(id(_error));_safe_error.append(_safe_exception(_error,_relation))
   _pending_errors.extend([('cause',_error.__cause__),('context',_error.__context__)])
closed_count=0
for conn in connections:
 try:conn.execute('SELECT 1')
 except sqlite3.ProgrammingError:closed_count+=1
 else:raise AssertionError('native handle leaked in creating thread')
for fd in list(fdpaths):
 try:os.fstat(fd)
 except OSError:fdpaths.pop(fd,None)
assert not fdpaths,'descriptor leaked'
print('FAVORITES_CHILD:'+json.dumps({'status':result,'native':len(connections),'closed':closed_count,'fd':0,**({'safe_error':_safe_error} if '_safe_error' in locals() else {})}))
'''


def child_command(state, mode, token='', ticker='AAPL', ready=None, go=None):
    import sys
    root = Path(__file__).resolve().parents[3]
    return [sys.executable, '-B', '-c', _FAVORITES_CHILD, str(root), str(state), mode, token, ticker,
        str(ready or state.parent / 'unused-ready'), str(go or state.parent / 'unused-go')]


def child_env(state):
    keys = ('AUTH_ENABLED', 'AUTH_SITE_ROLE', 'AUTH_LINK_BASE_URL', 'JWT_SECRET', 'STRUCTURAL_SSO_SECRET',
        'STRUCTURAL_PRIVACY_HMAC_KEY', 'STRUCTURAL_SHARE_TOKEN_SECRET', 'SMTP_HOST', 'SMTP_PORT',
        'SMTP_FROM_EMAIL', 'ADMIN_NOTIFICATION_EMAIL', 'AUTH_TRUSTED_PROXY_IPS')
    result = {key: os.environ[key] for key in keys}
    owned = str(state.parent.resolve())
    result.update(PATH='/usr/bin:/bin:/opt/homebrew/bin', HOME=owned, TMPDIR=owned,
        PYTHONDONTWRITEBYTECODE='1', STRUCTURAL_ENV='prod', AUTH_DATA_DIR=str(state),
        STRUCTURAL_SSO_DATA_DIR=str(state), STRUCTURAL_HISTORY_DB=str(state / 'history.db'))
    return result


def finish_child(process):
    try:
        output, error = process.communicate(timeout=20)
        assert process.returncode == 0, error[-4000:]
        return json.loads(next(line.split(':', 1)[1] for line in output.splitlines() if line.startswith('FAVORITES_CHILD:')))
    finally:
        if process.poll() is None:
            process.kill();process.communicate(timeout=5)


def await_ready(processes, markers):
    deadline = time.monotonic() + 8
    while not all(path.exists() for path in markers):
        assert all(p.poll() is None for p in processes), 'child exited before rendezvous'
        assert time.monotonic() < deadline, 'child rendezvous timed out'
        time.sleep(0.01)


def test_two_real_processes_rewrite_whole_file_without_lost_other_owner(stack, native):
    import subprocess
    client, state, _ = stack
    go = state.parent / 'go'
    tokens = [client.cookies.get('phase_session'), private_session(BOB)]
    ready = [state.parent / ('ready-' + str(index)) for index in range(2)]
    processes = []
    try:
        for index, ticker in enumerate(('AAPL', 'MSFT')):
            processes.append(subprocess.Popen(child_command(state, 'write', tokens[index], ticker, ready[index], go),
                env=child_env(state), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE))
        await_ready(processes, ready);go.write_text('go')
        results = [finish_child(process) for process in processes]
        print('FAVORITES_PROCESS_RESULTS:' + json.dumps(results))
        assert [r['status'] for r in results] == [201, 201]
        assert all(r['native'] == r['closed'] and r['fd'] == 0 for r in results)
        assert {v['email']: v['tickers'] for v in records(state)} == {ALICE: ['AAPL'], BOB: ['MSFT']}
        assert list(state.glob('.favorites-*.jsonl.tmp')) == []
    finally:
        for process in processes:
            if process.poll() is None:process.kill();process.communicate(timeout=5)


def test_queued_real_process_write_revalidates_after_account_delete(stack, native):
    import subprocess
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    ready, go = state.parent / 'queued-ready', state.parent / 'queued-go'
    process = None
    try:
        with auth.account_owner_transaction(ALICE) as lease:
            process = subprocess.Popen(child_command(state, 'queued-write', client.cookies.get('phase_session'), 'MSFT', ready, go),
                env=child_env(state), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            await_ready([process], [ready]);go.write_text('go')
            service = auth._account_deletion_service()
            job_id = service.begin_account_deletion_locked(ALICE, auth._store().user(ALICE)['session_generation'],
                auth._store().owner_gate_id(ALICE), auth._account_cleanup_binding(ALICE), owner_lease=lease)
            auth._run_account_deletion_locked(service, job_id, owner_lease=lease)
        result = finish_child(process)
        print('FAVORITES_QUEUED_RESULT:' + json.dumps(result))
        assert result['status'] == 401 and result['native'] == result['closed']
        assert not any('_favorites_owner' in v and v.get('email') == ALICE for v in records(state))
    finally:
        if process is not None and process.poll() is None:process.kill();process.communicate(timeout=5)


def test_crashed_process_releases_stable_lock_and_new_process_missing_file_does_not_create(stack, native):
    import subprocess
    client, state, _ = stack
    result = subprocess.run(child_command(state, 'crash-lock'), env=child_env(state), text=True, capture_output=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert client.post('/api/favorites/AAPL').status_code == 201
    (state / 'favorites.jsonl').unlink()
    process = subprocess.Popen(child_command(state, 'missing'), env=child_env(state), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    observed = finish_child(process)
    print('FAVORITES_MISSING_PROCESS_RESULT:' + json.dumps(observed))
    assert observed['native'] == 0 and observed['status'] == 503 and not (state / 'favorites.jsonl').exists()


def test_both_namespaces_share_lock_and_real_thread_writes_close_native_on_creator(stack, native, monkeypatch):
    import threading
    client, state, _ = stack
    other_paths = importlib.import_module('web.backend.services.runtime_paths')
    other = importlib.import_module('web.backend.api.favorites')
    for name in ('STATE_ROOT', 'CACHE_ROOT', 'LOG_ROOT'):
        monkeypatch.setattr(other_paths, name, getattr(paths, name))
    assert other_paths.FAVORITES_LOCK is paths.FAVORITES_LOCK
    assert other_paths.FAVORITES_IO is paths.FAVORITES_IO
    original = sqlite3.connect;local = threading.local();local.handles = []
    def observed(*args, **kwargs):
        conn = original(*args, **kwargs)
        local.handles.append(conn)
        return conn
    monkeypatch.setattr(sqlite3, 'connect', observed)
    tokens = [client.cookies.get('phase_session'), private_session(BOB)]
    def work(index):
        local.handles = []
        module = (favorites, other)[index]
        result = asyncio.run(module.add_favorite(('AAPL', 'MSFT')[index], request_for(tokens[index]), None))
        for conn in local.handles:
            with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')
        return getattr(result, 'status_code', 201), len(local.handles)
    # token issuance happened on the creating parent thread too.
    local.handles = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        result = list(executor.map(work, (0, 1)))
    print('FAVORITES_CREATING_THREAD_CLOSE_CHECKS:' + json.dumps(result))
    assert [r[0] for r in result] == [201, 201] and all(r[1] > 0 for r in result)
    assert {v['email']: v['tickers'] for v in records(state)} == {ALICE: ['AAPL'], BOB: ['MSFT']}


def test_same_email_reregistration_cannot_read_or_replace_leftover_old_generation(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    old = copy.deepcopy(records(state)[0]);old_token = client.cookies.get('phase_session')
    # Deliberately leave the separately stored Favorites material in place.
    retire_auth_incarnation(ALICE)
    private_session(ALICE)
    new_token = private_session(ALICE);client.cookies.set('phase_session', new_token)
    assert client.get('/api/favorites').json()['tickers'] == []
    assert client.get('/api/me/export').json()['data']['favorites']['exists'] is False
    assert client.post('/api/favorites/MSFT').status_code == 201
    assert records(state)[0] == old
    assert len(records(state)) == 2
    assert client.get('/api/favorites').json()['tickers'] == ['MSFT']
    client.cookies.set('phase_session', old_token)
    before = favorite_bytes(state)
    assert client.get('/api/favorites').status_code == 401
    assert client.post('/api/favorites/GOOG').status_code == 401
    assert favorite_bytes(state) == before


def test_new_sso_session_old_generation_poison_cannot_fallback_to_fresh_direct_cookie(stack, native, monkeypatch):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    assert client.post('/api/sso/exchange', json={'code': code, 'state': state}).status_code == 200
    old_sso = client.cookies.get('structural_beta_session')
    retire_auth_incarnation(ALICE)
    private_session(ALICE)
    fresh = private_session(ALICE);client.cookies.set('phase_session', fresh)
    assert auth.resolve_account_user(request_for(fresh))[1] == 'valid'
    assert client.get('/api/favorites').status_code == 401
    assert sso.resolve_beta_user(request_for(old_sso, sso_cookie=True))[1] == 'invalid'
    client.cookies.delete('structural_beta_session')
    assert client.get('/api/favorites').status_code == 200


def test_typed_and_ticker_producers_all_share_private_owner_envelope(stack, native):
    client, state, _ = stack
    payload = {'kind': 'structural_analysis', 'title': 'Synthetic mechanism',
        'query': 'How does a queue transfer?', 'source_id': 'fixture-source', 'target_id': 'fixture-target'}
    merged = client.post('/api/favorites/merge', json={'tickers': ['AAPL'], 'bookmarks': [payload]})
    assert merged.status_code == 200, merged.text
    bookmark_id = merged.json()['confirmed_bookmark_ids'][0]
    second = dict(payload, target_id='other-fixture-target')
    added = client.post('/api/favorites/bookmarks', json=second)
    assert added.status_code == 201
    assert client.delete('/api/favorites/bookmarks/' + bookmark_id).status_code == 204
    assert client.post('/api/favorites/MSFT').status_code == 201
    assert client.delete('/api/favorites/AAPL').status_code == 204
    result = client.get('/api/favorites').json()
    assert result['tickers'] == ['MSFT'] and len(result['bookmarks']) == 2
    assert len(records(state)) == 1
    assert records(state)[0]['_favorites_owner']['generation'] == auth._store().user(ALICE)['session_generation']


def test_delete_close_receipt_loss_reconciles_without_second_replace(stack, native, monkeypatch):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    replace, close = os.replace, os.close
    replaces, target, failed = [], [], []
    with deletion_context() as (_, _, authority):
        item = auth._account_registry(favorites_authority=authority).assets[0]
        snapshot = item.snapshot(ALICE)
        def committed(*args, **kwargs):
            result = replace(*args, **kwargs)
            replaces.append(True);target[:] = [paths.FAVORITES_IO.get().parent_fd]
            return result
        def lost(fd):
            close(fd)
            if target and fd == target[0] and not failed:
                failed.append(True)
                raise OSError('synthetic lost parent close receipt')
        with monkeypatch.context() as fault:
            fault.setattr(paths.os, 'replace', committed);fault.setattr(paths.os, 'close', lost)
            removed = item.delete(ALICE)
        assert removed['records'] == 1 and len(replaces) == len(failed) == 1
        assert records(state)[0]['_favorites_tombstone']['operation_id'] == snapshot['operation_id']
        item.restore(ALICE, snapshot, removed)
        assert records(state)[0]['tickers'] == ['AAPL']


def test_real_job_rejects_forged_lease_and_wrong_owner_gate(stack, native):
    from types import SimpleNamespace
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    with deletion_context() as (service, job_id, authority):
        before = favorite_bytes(state)
        fake = SimpleNamespace(identity=authority.lease.identity)
        with pytest.raises(PermissionError):
            with auth._favorites_authority(ALICE, authority.generation, fake, service=service, job_id=job_id):pass
        with auth.account_owner_transaction(BOB) as bob_lease:
            with pytest.raises(PermissionError):
                with auth._favorites_authority(ALICE, authority.generation, bob_lease, service=service, job_id=job_id):pass
        assert favorite_bytes(state) == before


def test_stable_lock_inode_is_never_replaced_and_substitution_is_rejected(stack, native):
    client, state, _ = stack
    lock = state / 'favorites.lock';before = lock.stat().st_ino
    for ticker in ('AAPL', 'MSFT'):
        assert client.post('/api/favorites/' + ticker).status_code == 201
        assert lock.stat().st_ino == before
    content = favorite_bytes(state)
    with paths.private_favorites_transaction() as io:
        lock.rename(state / 'old-lock')
        lock.write_bytes(b'');lock.chmod(0o600)
        with pytest.raises(paths.RuntimePathError):io.read()
    assert favorite_bytes(state) == content


@pytest.mark.parametrize('configured', ['', 'relative/favorites.jsonl', 'file:/tmp/favorites.jsonl', '../favorites.jsonl'])
def test_formal_config_cannot_fallback_or_escape(private, native, monkeypatch, configured):
    monkeypatch.setenv('STRUCTURAL_FAVORITES_PATH', configured)
    with pytest.raises(paths.RuntimePathError):favorites._data_file()
    assert not native and not (private.parent / 'favorites.jsonl').exists()


def test_exchange_queued_behind_real_deletion_rechecks_before_consume(stack, native, monkeypatch):
    import threading
    client, code, state, claims = exchange_material(stack, monkeypatch)
    waiting = threading.Event();original_gate = sso.account_owner_transaction
    original_consume = sso.SsoReplayStore.consume_issued;consumed = []
    original_connect = sqlite3.connect;local = threading.local();local.handles = []
    def observed(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        local.handles.append(connection)
        return connection
    monkeypatch.setattr(sqlite3, 'connect', observed)
    @contextmanager
    def announced(owner):
        waiting.set()
        with original_gate(owner) as lease:yield lease
    def consume(self, jti):
        consumed.append(jti);return original_consume(self, jti)
    monkeypatch.setattr(sso, 'account_owner_transaction', announced)
    monkeypatch.setattr(sso.SsoReplayStore, 'consume_issued', consume)
    binding = client.cookies.get('structural_sso_state')
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/sso/exchange', 'scheme': 'https',
        'server': ('beta.structural.bytedance.city', 443),
        'headers': [(b'host', b'beta.structural.bytedance.city'),
                    (b'cookie', ('structural_sso_state=' + binding).encode())]})
    def exchange():
        local.handles = []
        response = asyncio.run(sso.exchange_code(sso.ExchangeBody(code=code, state=state), request))
        for connection in local.handles:
            with pytest.raises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
        return response
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        with auth.account_owner_transaction(ALICE) as lease:
            future = executor.submit(exchange)
            assert waiting.wait(timeout=5)
            service = auth._account_deletion_service()
            job_id = service.begin_account_deletion_locked(ALICE, auth._store().user(ALICE)['session_generation'],
                auth._store().owner_gate_id(ALICE), auth._account_cleanup_binding(ALICE), owner_lease=lease)
            auth._run_account_deletion_locked(service, job_id, owner_lease=lease)
        response = future.result(timeout=10)
    assert response.status_code == 409 and consumed == []
    assert 'set-cookie' not in response.headers
    assert auth._store().user(ALICE) is None


def test_unicode_nonce_mismatch_is_rejected_without_consumption(stack, native, monkeypatch):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    claims['nonce'] = '错误nonce' * 8
    response = client.post('/api/sso/exchange', json={
        'code': jwt.encode(claims, SECRET, algorithm='HS256'), 'state': state})
    assert response.status_code == 400
    assert sso.get_replay_store().lookup_issued(claims['jti']) is not None


@pytest.mark.parametrize('bad', [None, '', False])
def test_present_invalid_code_gen_does_not_enter_absent_dev_compatibility(stack, native, monkeypatch, bad):
    client, code, state, claims = exchange_material(stack, monkeypatch)
    claims['gen'] = bad
    monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
    response = client.post('/api/sso/exchange', json={
        'code': jwt.encode(claims, SECRET, algorithm='HS256'), 'state': state})
    assert response.status_code == 401
    assert sso.get_replay_store().lookup_issued(claims['jti']) is not None


def test_formal_operation_cannot_downgrade_to_development_path_mid_write(stack, native, monkeypatch):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    before = favorite_bytes(state);escape = state.parent / 'unapproved-favorites.jsonl'
    original = favorites._atomic_write_all
    def downgrade(records):
        monkeypatch.setenv('STRUCTURAL_ENV', 'dev')
        monkeypatch.setenv('STRUCTURAL_FAVORITES_PATH', str(escape))
        return original(records)
    monkeypatch.setattr(favorites, '_atomic_write_all', downgrade)
    response = client.post('/api/favorites/MSFT')
    assert response.status_code == 503 and not escape.exists()
    assert favorite_bytes(state) == before


def test_preexisting_old_generation_does_not_block_current_snapshot_compensation(stack, native):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    previous_incarnation = copy.deepcopy(records(state)[0])
    retire_auth_incarnation(ALICE)
    private_session(ALICE)
    current_token = private_session(ALICE)
    client.cookies.set('phase_session', current_token)
    assert client.get('/api/favorites').json()['tickers'] == []
    assert client.post('/api/favorites/MSFT').status_code == 201
    current_incarnation = copy.deepcopy(records(state)[1])
    assert current_incarnation['_favorites_owner']['generation'] != previous_incarnation['_favorites_owner']['generation']
    with deletion_context() as (_, _, authority):
        item = auth._account_registry(favorites_authority=authority).assets[0]
        snapshot = item.snapshot(ALICE)
        removed = item.delete(ALICE)
        assert removed == {'records': 1, 'tickers': 1, 'bookmarks': 0}
        assert records(state)[0] == previous_incarnation
        item.restore(ALICE, snapshot, removed)
        restored = records(state)
        assert len(restored) == 2 and restored[0] == previous_incarnation
        assert restored[1]['tickers'] == ['MSFT']
        assert restored[1]['_favorites_owner']['generation'] == current_incarnation['_favorites_owner']['generation']
        assert restored[1]['_favorites_owner']['record_id'] == current_incarnation['_favorites_owner']['record_id']
        assert restored[1]['_favorites_owner']['revision'] != current_incarnation['_favorites_owner']['revision']
        before_replay = favorite_bytes(state)
        with pytest.raises(PermissionError):item.restore(ALICE, snapshot, removed)
        assert favorite_bytes(state) == before_replay


def test_real_next_generation_writer_atomically_invalidates_prior_deletion_marker(stack, native, monkeypatch):
    client, state, _ = stack
    assert client.post('/api/favorites/AAPL').status_code == 201
    original_record = copy.deepcopy(records(state)[0])
    old_generation = original_record['_favorites_owner']['generation']
    with deletion_context() as (service, job_id, authority):
        item = auth._account_registry(favorites_authority=authority).assets[0]
        snapshot = item.snapshot(ALICE)
        removed = item.delete(ALICE)
        mark = copy.deepcopy(records(state)[0]['_favorites_tombstone'])
        assert mark['operation_id'] == snapshot['operation_id']
        # Finish the real persisted job before a new incarnation may register.
        result = auth._run_account_deletion_locked(service, job_id, owner_lease=authority.lease)
        assert service.deletion_job(job_id)['state'] == 'completed'
    assert auth.resume_account_deletion(job_id) == result
    assert records(state)[0]['_favorites_tombstone'] == mark
    private_session(ALICE)
    token = private_session(ALICE);client.cookies.set('phase_session', token)
    new_generation = auth._store().user(ALICE)['session_generation']
    assert new_generation != old_generation
    assert client.get('/api/favorites').json()['tickers'] == []
    assert records(state)[0]['_favorites_tombstone'] == mark
    original_replace = os.replace
    images = []
    def observe_replace(source, destination, *args, **kwargs):
        if destination != 'favorites.jsonl':
            return original_replace(source, destination, *args, **kwargs)
        before = copy.deepcopy(records(state))
        returned = original_replace(source, destination, *args, **kwargs)
        images.append((before, copy.deepcopy(records(state))))
        return returned
    # Observe the actual supported HTTP writer and its actual OS replace;
    # never remove/edit a marker or substitute an in-memory records mapping.
    monkeypatch.setattr(paths.os, 'replace', observe_replace)
    written = client.post('/api/favorites/MSFT')
    assert written.status_code == 201
    assert len(images) == 1
    before, after = images[0]
    assert before == [{'_favorites_tombstone': mark}]
    assert len(after) == 1 and '_favorites_tombstone' not in after[0]
    assert after[0]['tickers'] == ['MSFT']
    assert after[0]['_favorites_owner']['generation'] == new_generation
    assert after[0]['_favorites_owner']['record_id'] != original_record['_favorites_owner']['record_id']
    persisted = favorite_bytes(state)
    with pytest.raises(PermissionError):item.restore(ALICE, snapshot, removed)
    # Even a newly held correct owner gate cannot reactivate a completed job
    # or use its old-generation snapshot against the current incarnation.
    with auth.account_owner_transaction(ALICE) as fresh_lease:
        with pytest.raises(PermissionError):
            with auth._favorites_authority(ALICE, old_generation, fresh_lease,
                    service=service, job_id=job_id):
                favorites.restore_account_favorites(ALICE, snapshot, removed)
    assert favorite_bytes(state) == persisted and len(images) == 1
