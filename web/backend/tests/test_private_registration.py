"""Formal registration uses actual native transactions and an isolated mail sink."""
from datetime import datetime,timedelta,timezone
import json
import pickle
import sqlite3
import os
import multiprocessing
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from api import auth
from services import auth_registration as registration
from services.auth_store import AuthStore
from .test_private_runtime_bootstrap import roots

BETA='https://beta.structural.bytedance.city'
SECRET='private-registration-synthetic-7a3c95e02b18f6d4'


def register_private_user(monkeypatch,email='fixture@example.invalid',tier='free'):
    """Explicit fixture producer: actual formal HTTP mail->verify, no seeding."""
    mail=[]
    configured_secret=os.getenv('JWT_SECRET') or 'A7f9K2m4P8q1R6t3V5x0Y2z8C4d7H9j1L6n3'
    with monkeypatch.context() as setup:
        for key,value in {'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':configured_secret,
            'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid',
            'ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false',
            'AUTH_IP_EMAIL_LIMIT_PER_HOUR':'10000','AUTH_GLOBAL_EMAIL_LIMIT_PER_HOUR':'10000'}.items():setup.setenv(key,value)
        setup.setattr(auth,'_send_email',lambda _to,_subject,text:mail.append(text))
        setup.setattr(auth,'_DEFAULT_TIER',tier)
        # Fixture users may need fresh sessions repeatedly while testing replay
        # and generation boundaries; this does not alter production limits.
        setup.setattr(auth,'_RATE_LIMIT_PER_HOUR',10000)
        app=FastAPI();app.include_router(auth.router,prefix='/api')
        with TestClient(app,base_url=BETA) as client:
            assert verify(client,link(client,mail,email)).status_code==200
            token=client.cookies.get('phase_session')
            return auth._store().user(email),token


@pytest.fixture
def stack(roots,monkeypatch):
    registration.bootstrap_private_runtime()
    settings={'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':SECRET,
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid',
        'ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}
    for key,value in settings.items():monkeypatch.setenv(key,value)
    monkeypatch.setenv('STRUCTURAL_SSO_SECRET',SECRET)
    monkeypatch.setattr(auth,'_AUTH_STORES',{})
    mail=[]
    monkeypatch.setattr(auth,'_send_email',lambda to,subject,text:mail.append(text))
    app=FastAPI();app.include_router(auth.router,prefix='/api')
    with TestClient(app,base_url=BETA) as client:
        yield client,roots,mail


def link(client,mail,email='fresh@example.invalid'):
    result=client.post('/api/auth/request-link',json={'email':email},headers={'origin':BETA})
    assert result.status_code==200,result.text
    assert 'dev_token' not in result.json()
    from urllib.parse import urlsplit,parse_qs
    return parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]


def verify(client,token):
    return client.post('/api/auth/verify',json={'token':token},headers={'origin':BETA})


def test_actual_formal_request_link_new_account_login_logout(stack,monkeypatch):
    client,root,mail=stack
    token=link(client,mail)
    response=verify(client,token)
    assert response.status_code==200,response.text
    assert client.get('/api/auth/me').status_code==200
    store=auth._store();user=store.user('fresh@example.invalid')
    generation=user['session_generation']
    with store._connection() as conn:
        assert conn.execute('SELECT consumed_at FROM magic_tokens WHERE token_hash=?',(auth._token_hash(token),)).fetchone()[0]
        assert conn.execute("SELECT count(*) FROM auth_registration_receipts WHERE kind='account_finalize'").fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==1
    assert verify(client,token).status_code==400
    assert client.post('/api/auth/logout',headers={'origin':BETA}).status_code==200
    assert client.get('/api/auth/me').status_code==401
    token2=link(client,mail)
    # Existing resources and fresh sign-in must never touch the global lock.
    monkeypatch.setattr(registration,'_provision_lock',lambda *_:(_ for _ in ()).throw(AssertionError('sign-in global lock')))
    assert verify(client,token2).status_code==200
    assert store.user(user['email'])['session_generation']==generation
    with store._connection() as conn:
        assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==1


def test_formal_old_callers_and_ordinary_sql_default_deny(stack,monkeypatch):
    client,root,mail=stack
    store=auth._store()
    for call in (lambda:store.ensure_user_and_notification('bad@example.invalid','free','synthetic'),
        lambda:store.ensure_user_from_token('bad@example.invalid','free','synthetic','synthetic'),
        lambda:store.consume_token('bad','synthetic'),lambda:auth._issue_jwt('bad@example.invalid','free')):
        with pytest.raises(PermissionError):call()
    monkeypatch.setenv('STRUCTURAL_ENV','dev')
    with pytest.raises(PermissionError):store.ensure_user_and_notification('bad@example.invalid','free','synthetic')
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.Error):conn.execute("INSERT INTO auth_users VALUES('bad@example.invalid','free','synthetic','0123456789abcdef0123456789abcdef','active')")
    assert store.user('bad@example.invalid') is None


def test_fabricated_request_is_not_actual_token_or_verify_producer(stack):
    client,root,mail=stack;store=auth._store()
    scope={'type':'http','method':'POST','scheme':'https','query_string':b'',
        'server':('beta.structural.bytedance.city',443),'headers':[(b'origin',BETA.encode())]}
    request=Request(dict(scope,path='/api/auth/request-link'))
    now=datetime.now(timezone.utc)
    with pytest.raises(PermissionError):store.add_token('f'*64,'forged@example.invalid',now.isoformat(),(now+timedelta(minutes=10)).isoformat(),request=request)
    with pytest.raises(PermissionError):
        with registration.verify_request(Request(dict(scope,path='/api/auth/verify')),store):pass
    with store._connection() as conn:assert conn.execute('SELECT count(*) FROM magic_tokens').fetchone()[0]==0


def test_failure_before_finalize_does_not_consume(stack,monkeypatch):
    client,root,mail=stack
    token=link(client,mail)
    def fail(*_a,**_k):raise PermissionError('owned failure before finalize')
    monkeypatch.setattr(registration,'_finalize',fail)
    assert verify(client,token).status_code==503
    with auth._store()._connection() as conn:
        assert conn.execute('SELECT consumed_at FROM magic_tokens').fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0


@pytest.mark.parametrize('fault',[1,2,3,4,5])
def test_finalize_each_sql_failure_is_atomic(stack,monkeypatch,fault):
    client,root,mail=stack;token=link(client,mail)
    from services.sqlite_utils import PrivateAuthConnection
    original=PrivateAuthConnection.execute
    n=[0]
    def execute(self,sql,*a,**k):
        if sql.startswith(('UPDATE magic_tokens SET consumed_at','INSERT INTO auth_users','INSERT INTO auth_notification_outbox','INSERT INTO auth_registration_receipts','UPDATE auth_registration_operations SET state=\'finalized\'')):
            if not (sql.startswith('INSERT INTO auth_registration_receipts') and a and a[0][2]=='gate_resource'):
                n[0]+=1
                if n[0]==fault:raise sqlite3.OperationalError('owned SQL cut')
        return original(self,sql,*a,**k)
    monkeypatch.setattr(PrivateAuthConnection,'execute',execute)
    assert verify(client,token).status_code==503
    with auth._store()._connection() as conn:
        assert conn.execute('SELECT consumed_at FROM magic_tokens').fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM auth_registration_receipts WHERE kind='account_finalize'").fetchone()[0]==0


def test_commit_ack_unknown_cannot_issue_and_new_link_works(stack,monkeypatch):
    client,root,mail=stack;token=link(client,mail)
    from services.sqlite_utils import PrivateAuthConnection
    original=PrivateAuthConnection.commit
    def commit(self):
        finalized=self.execute("SELECT 1 FROM auth_registration_operations WHERE state='finalized'").fetchone()
        original(self)
        if finalized:raise sqlite3.OperationalError('owned lost commit ACK')
    with monkeypatch.context() as cut:
        cut.setattr(PrivateAuthConnection,'commit',commit)
        result=verify(client,token)
        assert result.status_code==503 and 'phase_session' not in result.cookies
    assert verify(client,token).status_code==400
    assert client.get('/api/auth/me').status_code==401
    token2=link(client,mail)
    assert verify(client,token2).status_code==200


def test_orphan_requires_explicit_same_operation_offline_admission(stack,monkeypatch):
    client,root,mail=stack;token=link(client,mail)
    with monkeypatch.context() as cut:
        cut.setattr(registration,'_mark_ready',lambda *_a,**_k:(_ for _ in ()).throw(PermissionError('owned birth before receipt')))
        assert verify(client,token).status_code==503
    store=auth._store();email='fresh@example.invalid';owner=store.owner_key(email)
    with store._connection() as conn:
        op=conn.execute('SELECT * FROM auth_registration_operations').fetchone()
        assert op['state']=='closed'
        assert conn.execute('SELECT consumed_at FROM magic_tokens').fetchone()[0] is None
    with pytest.raises(PermissionError):registration.admit_private_gate(owner)
    assert registration.admit_private_gate(owner,operation_id=op['id'])=={'admitted':True}
    with store._connection() as conn:
        assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM auth_registration_receipts WHERE kind='account_finalize'").fetchone()[0]==0
        offline=conn.execute("SELECT * FROM auth_registration_operations WHERE kind='offline_gate_admission'").fetchone()
        assert offline['state']=='closed' and offline['closed_reason']=='admitted'
    assert verify(client,token).status_code==400
    assert verify(client,link(client,mail)).status_code==200


def test_sealed_authority_single_use_original_request_only(stack,monkeypatch):
    client,root,mail=stack;token=link(client,mail);captured=[]
    original=auth._issue_jwt
    def issue(*a,**k):
        cap=k['authority'];captured.append(cap)
        with pytest.raises(TypeError):cap.user['email']='other@example.invalid'
        with pytest.raises(TypeError):cap.used=False
        with pytest.raises(TypeError):pickle.dumps(cap)
        result=original(*a,**k)
        with pytest.raises(PermissionError):original(authority=cap)
        return result
    monkeypatch.setattr(auth,'_issue_jwt',issue)
    assert verify(client,token).status_code==200
    with pytest.raises(PermissionError):original(authority=captured[0])
    assert not registration._SESSIONS


def test_registered_user_research_favorites_sso_delete_and_no_inheritance(stack,monkeypatch):
    """Isolated admitted routers; Main/formal admission remains closed."""
    client,root,mail=stack
    from api import research,favorites,sso,report_account,report
    from errors import install_problem_handlers
    from .test_research_persistence import problem,envelope
    monkeypatch.setattr(research,'enabled',lambda:True)
    monkeypatch.setattr(sso,'_REPLAY_STORES',{})
    monkeypatch.setattr(report_account,'_store',None);monkeypatch.setattr(report,'_store',None)
    monkeypatch.setattr(favorites,'_legacy_data_file',lambda:root/'absent-legacy-favorites.jsonl')
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB',str(root/'history.db'))
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET','synthetic-share-secret')
    app=client.app
    for router in (research.router,favorites.router,sso.router,report.router,report_account.router):app.include_router(router,prefix='/api')
    install_problem_handlers(app)
    assert verify(client,link(client,mail)).status_code==200
    user=auth._store().user('fresh@example.invalid');oldgen=user['session_generation']
    oldcookie=client.cookies.get('phase_session')
    response=client.post('/api/research',json=envelope({'problem':problem()}),headers={'origin':BETA,'idempotency-key':'registration-save'})
    assert response.status_code==200,response.text
    rid=response.json()['data']['research']['id']
    assert client.get('/api/research/'+rid).status_code==200
    assert client.post('/api/favorites/AAPL',headers={'origin':BETA}).status_code==201
    assert client.get('/api/favorites').json()['tickers']==['AAPL']
    import jwt
    start=client.get('/api/sso/start',follow_redirects=False)
    assert start.status_code==303,start.text
    binding=jwt.decode(start.cookies.get(sso._STATE_COOKIE),SECRET,algorithms=['HS256'],audience='structural-beta-start',issuer=BETA)
    issued=client.post('/api/sso/issue',json={'audience':'structural-beta','state':binding['state'],'nonce':binding['nonce']},headers={'origin':BETA})
    assert issued.status_code==200,issued.text
    code=issued.json()['code']
    exchanged=client.post('/api/sso/exchange',json={'code':code,'state':binding['state']},headers={'origin':BETA})
    assert exchanged.status_code==200,exchanged.text
    assert client.post('/api/sso/exchange',json={'code':code,'state':binding['state']},headers={'origin':BETA}).status_code==400
    deleted=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert deleted.status_code==200,deleted.text
    assert auth._store().user(user['email']) is None
    assert verify(client,link(client,mail)).status_code==200
    assert auth._store().user(user['email'])['session_generation']!=oldgen
    assert client.get('/api/research/'+rid).status_code==404
    assert client.get('/api/favorites').json()['tickers']==[]
    exported=auth._store().export_account_data(user['email'])
    assert all(row['kind']=='new_account' for row in exported['registration_events'])
    serialized=json.dumps(exported)
    for private in ('token_hash','gate_id','lock_ino','database_binding',oldgen):assert private not in serialized


def test_expired_link_claim_fails_without_consumption_or_mapping(stack,monkeypatch):
    client,root,mail=stack
    actual=auth._TOKEN_TTL_MIN
    monkeypatch.setattr(auth,'_TOKEN_TTL_MIN',-1)
    token=link(client,mail)
    assert verify(client,token).status_code==400
    with auth._store()._connection() as conn:
        assert conn.execute('SELECT consumed_at FROM magic_tokens').fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM auth_registration_operations').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM auth_owner_gates').fetchone()[0]==0


def _verify_process(root,token,barrier,queue):
    """Real fresh process; safety audit metadata is inherited, no store stubs."""
    from pathlib import Path
    from services import runtime_paths as paths
    paths.STATE_ROOT=Path(root);paths.CACHE_ROOT=Path(root).parent/'cache';paths.LOG_ROOT=Path(root)/'logs'
    from api import auth as child_auth
    from starlette.requests import Request
    from starlette.responses import Response
    import asyncio
    request=Request({'type':'http','method':'POST','scheme':'https','path':'/api/auth/verify',
        'query_string':b'','server':('beta.structural.bytedance.city',443),'client':('127.0.0.1',10000),
        'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',BETA.encode())]})
    barrier.wait(10)
    result=asyncio.run(child_auth.verify(child_auth.VerifyBody(token=token),request,Response()))
    leaked=[];blocked=[]
    try:
        import audit_bootstrap as audit
        blocked=list(audit.blocked)
        for conn in audit.handles:
            try:conn.execute('SELECT 1')
            except sqlite3.Error:pass
            else:leaked.append('native-open');conn.close()
    except ImportError:pass
    queue.put((result.status_code,bool(result.headers.get('set-cookie')),leaked,blocked))


@pytest.mark.parametrize('same_token',[False,True])
def test_two_fresh_processes_one_owner_single_atomic_account(stack,same_token):
    client,root,mail=stack
    first=link(client,mail)
    second=first if same_token else link(client,mail)
    ctx=multiprocessing.get_context('spawn');barrier=ctx.Barrier(2);queue=ctx.Queue()
    workers=[ctx.Process(target=_verify_process,args=(str(root),token,barrier,queue)) for token in (first,second)]
    try:
        for process in workers:process.start()
        results=[queue.get(timeout=20) for _ in workers]
        for process in workers:process.join(20);assert process.exitcode==0
        assert all(not row[2] and not row[3] for row in results),results
        assert sum(row[0]==200 for row in results) in (1,2)
        if same_token:assert sum(row[0]==200 for row in results)==1
        with auth._store()._connection() as conn:
            assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==1
            assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM auth_registration_receipts WHERE kind='gate_resource'").fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM auth_registration_operations WHERE state IN ('claimed','gate_ready')").fetchone()[0]==0
    finally:
        for process in workers:
            if process.is_alive():process.terminate();process.join(5)
            if process.pid is not None:process.close()
        queue.close();queue.join_thread()


def _die_registration_process(root,token,point):
    from pathlib import Path
    from services import runtime_paths as paths,auth_registration as child_registration
    paths.STATE_ROOT=Path(root);paths.CACHE_ROOT=Path(root).parent/'cache';paths.LOG_ROOT=Path(root)/'logs'
    if point=='birth':
        child_registration._mark_ready=lambda *_a,**_k:os._exit(77)
    elif point=='ready':
        child_registration._finalize=lambda *_a,**_k:os._exit(77)
    else:
        from services.sqlite_utils import PrivateAuthConnection
        original=PrivateAuthConnection.commit
        def commit(self):
            finalized=self.execute("SELECT 1 FROM auth_registration_operations WHERE state='finalized'").fetchone()
            original(self)
            if finalized:os._exit(77)
        PrivateAuthConnection.commit=commit
    from api import auth as child_auth
    from starlette.requests import Request
    from starlette.responses import Response
    import asyncio
    request=Request({'type':'http','method':'POST','scheme':'https','path':'/api/auth/verify',
        'query_string':b'','server':('beta.structural.bytedance.city',443),'client':('127.0.0.1',10000),
        'headers':[(b'host',b'beta.structural.bytedance.city'),(b'origin',BETA.encode())]})
    asyncio.run(child_auth.verify(child_auth.VerifyBody(token=token),request,Response()))


@pytest.mark.parametrize('point',['birth','ready','commit'])
def test_actual_process_death_no_session_replay_and_safe_recovery(stack,point):
    client,root,mail=stack;token=link(client,mail)
    ctx=multiprocessing.get_context('spawn')
    process=ctx.Process(target=_die_registration_process,args=(str(root),token,point))
    try:
        process.start();process.join(15)
        assert process.exitcode==77
        store=auth._store()
        with store._connection() as conn:
            op=conn.execute("SELECT * FROM auth_registration_operations WHERE kind!='offline_gate_admission'").fetchone()
            consumed=conn.execute('SELECT consumed_at FROM magic_tokens').fetchone()[0]
        assert client.get('/api/auth/me').status_code==401
        if point in ('birth','ready'):
            assert op['state']==('claimed' if point=='birth' else 'gate_ready') and consumed is None
            with pytest.raises(PermissionError):registration.admit_private_gate(op['owner_key'])
            result=registration.admit_private_gate(op['owner_key'],operation_id=op['id'])
            assert result['admitted'] is (point=='birth')
            with store._connection() as conn:
                assert conn.execute('SELECT state FROM auth_registration_operations WHERE id=?',(op['id'],)).fetchone()[0]=='closed'
                assert conn.execute('SELECT count(*) FROM auth_users').fetchone()[0]==0
                assert conn.execute('SELECT count(*) FROM auth_notification_outbox').fetchone()[0]==0
                assert conn.execute("SELECT count(*) FROM auth_registration_receipts WHERE kind='account_finalize'").fetchone()[0]==0
        else:
            assert op['state']=='finalized' and consumed is not None
            assert verify(client,token).status_code==400
        assert verify(client,link(client,mail)).status_code==200
    finally:
        if process.is_alive():process.terminate();process.join(5)
        if process.pid is not None:process.close()


def test_receipts_and_mapping_cannot_replace_update_delete_or_rowid_bypass(stack):
    client,root,mail=stack
    assert verify(client,link(client,mail)).status_code==200
    store=auth._store()
    with store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        op=conn.execute('SELECT * FROM auth_registration_operations').fetchone()
        gate=conn.execute('SELECT * FROM auth_owner_gates').fetchone()
        attempts=[
            ("UPDATE auth_registration_receipts SET recorded_at='forged'",()),
            ('DELETE FROM auth_registration_receipts',()),
            ('DELETE FROM auth_registration_operations',()),
            ('UPDATE auth_registration_operations SET rowid=rowid+100',()),
            ('UPDATE OR REPLACE auth_registration_operations SET state=\'claimed\',version=version+1',()),
            ('UPDATE auth_owner_gates SET gate_id=?',(str(__import__('uuid').uuid4()),)),
            ('DELETE FROM auth_owner_gates',()),
            ('UPDATE auth_users SET rowid=rowid+10',()),
            ('UPDATE auth_users SET lifecycle=\'active\'',()),
            ('UPDATE magic_tokens SET consumed_at=NULL',()),
            ("INSERT OR REPLACE INTO auth_users(email,tier,created_at,session_generation,lifecycle) SELECT email,tier,created_at,session_generation,lifecycle FROM auth_users",()),
            ('INSERT OR REPLACE INTO auth_registration_receipts SELECT * FROM auth_registration_receipts',()),
        ]
        for sql,args in attempts:
            with pytest.raises(sqlite3.Error):conn.execute(sql,args)
        assert conn.execute('SELECT state FROM auth_registration_operations').fetchone()[0]=='finalized'
        assert store.expected_owner_gate_identity(gate['gate_id'])


def test_real_formal_registration_both_supported_import_namespaces(stack,monkeypatch):
    client,root,mail=stack
    import importlib
    from services import runtime_paths as paths
    other_paths=importlib.import_module('web.backend.services.runtime_paths')
    for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other_paths,name,getattr(paths,name))
    other=importlib.import_module('web.backend.api.auth')
    monkeypatch.setattr(other,'_AUTH_STORES',{})
    monkeypatch.setattr(other,'_send_email',lambda _to,_subject,text:mail.append(text))
    app=FastAPI();app.include_router(other.router,prefix='/api')
    with TestClient(app,base_url=BETA) as alternative:
        result=alternative.post('/api/auth/request-link',json={'email':'namespace@example.invalid'},headers={'origin':BETA})
        assert result.status_code==200,result.text
        from urllib.parse import urlsplit,parse_qs
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        result=alternative.post('/api/auth/verify',json={'token':token},headers={'origin':BETA})
        assert result.status_code==200,result.text
        assert alternative.get('/api/auth/me').status_code==200


@pytest.mark.parametrize('namespace',['api','web.backend.api'])
@pytest.mark.parametrize('kind',['live','retired','copied','wrong_owner','subclass'])
def test_delete_mark_requires_actual_live_canonical_owner_lease(stack,monkeypatch,namespace,kind):
    """Actual deletion action and write txn; only the real held owner passes."""
    import importlib
    from contextlib import contextmanager
    from types import SimpleNamespace
    from services import runtime_paths as paths
    _client,root,mail=stack
    if namespace.startswith('web.'):
        other=importlib.import_module('web.backend.services.runtime_paths')
        for name in ('STATE_ROOT','CACHE_ROOT','LOG_ROOT'):monkeypatch.setattr(other,name,getattr(paths,name))
    api=importlib.import_module(namespace+'.auth')
    reg=importlib.import_module('web.backend.services.auth_registration' if namespace.startswith('web.') else 'services.auth_registration')
    service_type=importlib.import_module('web.backend.research.service' if namespace.startswith('web.') else 'research.service').ResearchService
    monkeypatch.setattr(api,'_AUTH_STORES',{})
    monkeypatch.setattr(api,'_send_email',lambda _to,_subject,text:mail.append(text))
    for name in ('report_account','report'):monkeypatch.setattr(importlib.import_module(namespace+'.'+name),'_store',None)
    monkeypatch.setattr(importlib.import_module(namespace+'.favorites'),'_legacy_data_file',lambda:root/'absent-legacy-favorites.jsonl')
    monkeypatch.setenv('STRUCTURAL_HISTORY_DB',str(root/'history.db'))
    monkeypatch.setenv('STRUCTURAL_SHARE_TOKEN_SECRET','synthetic-share-secret')
    app=FastAPI();app.include_router(api.router,prefix='/api')
    observed={}
    class RollBackProbe(Exception):pass
    def begin(self,email,generation,gate_id,cleanup_binding,*,owner_lease=None,request_source=None):
        assert request_source is not None and request_source.active
        try:
            with self.store.transaction(write=True) as conn:
                try:reg.mark_account_deleting(conn,store=self.store,lease=owner_lease,request_source=request_source,email=email,generation=generation)
                except PermissionError:observed['denied']=True
                else:
                    observed['denied']=False
                    assert conn.execute('SELECT lifecycle FROM auth_users WHERE email=?',(email,)).fetchone()[0]=='deleting'
                raise RollBackProbe()
        except RollBackProbe:raise RuntimeError('intentional rollback before any deletion job')
    monkeypatch.setattr(service_type,'begin_account_deletion_locked',begin)
    with TestClient(app,base_url=BETA) as client:
        if kind=='wrong_owner':assert verify(client,link(client,mail,'other@example.invalid')).status_code==200
        assert verify(client,link(client,mail)).status_code==200
        original=api.account_owner_transaction
        @contextmanager
        def lease_context(email):
            if kind=='wrong_owner':
                with original('other@example.invalid') as lease:yield lease
            elif kind=='live':
                with original(email) as lease:yield lease
            else:
                with original(email) as lease:identity=lease.identity
                if kind=='retired':yield lease
                elif kind=='copied':yield SimpleNamespace(identity=identity)
                else:
                    class FakeSubclass(type(lease)):
                        @property
                        def identity(self):return identity
                    yield object.__new__(FakeSubclass)
        monkeypatch.setattr(api,'account_owner_transaction',lease_context)
        result=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
        assert result.status_code==500,result.text
        assert observed['denied'] is (kind!='live')
        assert api._store().user('fresh@example.invalid')['lifecycle']=='active'
