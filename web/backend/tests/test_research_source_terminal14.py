"""Current14 legacy-dev components; never Main/C3 execution admission."""
from contextlib import closing,contextmanager
from functools import partial
import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from api import auth
from research import ResearchStore,ResearchRunner,source_workflow
from research.authorization import AuthorizationGate,OwnerGateLease
from research.errors import ResearchError
from research.runtime_profile import require_formal_application
from research.source_policy import PinnedPublicTransport
from .test_research_persistence import app,login,problem,post
from .source_http_fixture import source_server,get_local,drop_after_response


@pytest.fixture
def current14(tmp_path,monkeypatch):
    for name,value in {
        'STRUCTURAL_ENV':'test','AUTH_ENABLED':'true','AUTH_DEV_MODE':'true',
        'AUTH_DATA_DIR':str(tmp_path/'legacy-dev-auth'),'AUTH_LINK_BASE_URL':'http://testserver',
        'JWT_SECRET':'terminal14-synthetic-auth-secret-32-characters',
        'STRUCTURAL_SSO_SECRET':'terminal14-synthetic-sso-secret-32-characters',
        'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'STRUCTURAL_SSO_DATA_DIR':str(tmp_path/'sso'),'STRUCTURAL_SSO_BETA_ORIGIN':'http://testserver',
        'STRUCTURAL_SSO_PHASE_ORIGIN':'http://phase.test','ADMIN_NOTIFICATION_EMAIL':'',
        'STRUCTURAL_FAVORITES_PATH':str(tmp_path/'favorites.jsonl'),
        'STRUCTURAL_RESEARCH_ENABLED':'true','STRUCTURAL_D1_SOURCES_ENABLED':'true',
        'STRUCTURAL_D1_PUBLIC_GET_ENABLED':'false','STRUCTURAL_LOG_FILE':str(tmp_path/'events.jsonl'),
    }.items():monkeypatch.setenv(name,value)
    # New legacy-dev paths are supported without altering captured private paths,
    # app.state, enabled functions, constructors or the fixed Main admission.
    with TestClient(app()) as client:
        login(client,'terminal14@example.test')
        saved=problem();saved['confirmed']=True
        created=post(client,'/api/research',{'problem':saved})
        assert created.status_code==200,created.text
        rid=created.json()['data']['research']['id'];store=ResearchStore(auth._store())
        assert store._formal_mode() is False and store.auth_store._private_auth is False
        with store.transaction() as conn:
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==14
        yield client,store,rid


def start(client,rid):
    data=client.get(f'/api/research/{rid}').json()['data']
    request={'input_revision':data['current_problem']['revision'],'expected_research_version':data['research_version'],'query':'queue theory'}
    preview=post(client,f'/api/research/{rid}/source-preview',request)
    assert preview.status_code==200,preview.text
    approval=post(client,f'/api/research/{rid}/source-approvals',{**request,'preview_digest':preview.json()['data']['preview_digest'],'confirm_external':True})
    assert approval.status_code==200,approval.text
    task=post(client,f'/api/research/{rid}/source-tasks',{'input_revision':request['input_revision'],'expected_research_version':request['expected_research_version'],'approval_ref':approval.json()['data']['approval_ref']})
    assert task.status_code==200,task.text
    return task.json()['data']['task']['id']


def cancel(client,rid,tid):
    data=client.get(f'/api/research/{rid}').json()['data']
    response=post(client,f'/api/research/{rid}/cancel',{'task_id':tid,'expected_task_version':data['task_version']})
    assert response.status_code==200 and response.json()['data']['execution']=='CANCELLED'


def image(path):
    with closing(sqlite3.connect(path)) as conn:return tuple(conn.iterdump())


def test_current14_cancel_before_birth_is_readonly_and_never_gets(current14,monkeypatch):
    client,store,rid=current14;tid=start(client,rid);cancel(client,rid,tid);before=image(store.path)
    original=store.transaction;runner=ResearchRunner(store)
    @contextmanager
    def readonly(*args,**kwargs):
        assert not kwargs.get('write',False)
        with original(*args,**kwargs) as conn:yield conn
    def no_birth(*args,**kwargs):raise AssertionError('read-only terminal state must not birth a sender')
    monkeypatch.setattr(store,'transaction',readonly)
    monkeypatch.setattr(runner.gate,'source_task_gate',no_birth)
    with source_server() as (port,calls):
        runner.source_transport=PinnedPublicTransport(_worker=partial(get_local,port))
        assert runner.run_once(tid)=='CANCELLED' and calls==[]
    assert image(store.path)==before
    assert not (store.path.parent/'research-locks'/('source-'+tid+'.lock')).exists()


def observe_real_locks(monkeypatch):
    tasks=[];owners=[];original_task=AuthorizationGate.source_task_gate;original_owner=AuthorizationGate.owner_gate_id
    @contextmanager
    def task(self,tid,**kwargs):
        with original_task(self,tid,**kwargs) as lease:
            tasks.append((tid,lease.identity,lease.cleanup));yield lease
    @contextmanager
    def owner(self,oid,**kwargs):
        with original_owner(self,oid,**kwargs) as lease:
            assert type(lease) is OwnerGateLease
            owners.append((oid,lease.identity));yield lease
    monkeypatch.setattr(AuthorizationGate,'source_task_gate',task)
    monkeypatch.setattr(AuthorizationGate,'owner_gate_id',owner)
    return tasks,owners


def test_current14_cancelled_unknown_debt_requires_actual_fresh_closure(current14,monkeypatch):
    client,store,rid=current14;tid=start(client,rid)
    # Fault after the real worker GET/outcome, before the existing closure. No
    # native SQL fabricates a request, outcome, source or permission here.
    with source_server() as (port,calls):
        with monkeypatch.context() as fault:
            def interrupted(*args):raise OSError('synthetic parent closure interruption')
            fault.setattr(source_workflow,'close_interrupted',interrupted)
            with pytest.raises(OSError,match='closure interruption'):
                ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(drop_after_response,port))).run_once(tid)
        assert calls==['/discovery']
        with store.transaction() as conn:
            before=dict(conn.execute('SELECT * FROM research_source_requests WHERE task_id=?',(tid,)).fetchone())
            assert (before['outcome'],before['execution_closed'],before['closure_ref'])==('UNKNOWN',0,None)
            assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?',(tid,)).fetchone()[0]==1
        cancel(client,rid,tid)
        tasks,owners=observe_real_locks(monkeypatch)
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=='CANCELLED'
        assert calls==['/discovery'] and len(tasks)==len(owners)==1 and tasks[0][2] is True
        with store.transaction() as conn:
            after=dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?',(before['id'],)).fetchone())
            assert (after['outcome'],after['execution_closed'])==('UNKNOWN',1) and after['closure_ref']
            import json
            proof=json.loads(after['closure_proof'])
            assert tuple(proof['task_gate'])==tasks[0][1] and tuple(proof['owner_gate'])==owners[0][1]
            assert proof['retired_write_epoch']==before['write_epoch'] and proof['proof_version']==1
            assert after['started_at']==before['started_at'] and after['ended_at']==before['ended_at']
            assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0]==1


def test_current14_completed_started_run_retains_lock_path_without_new_get(current14,monkeypatch):
    client,store,rid=current14;tid=start(client,rid)
    with source_server() as (port,calls):
        runner=ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        assert runner.run_once(tid)=='COMPLETED' and calls==['/discovery','/article']
        before=image(store.path);tasks,owners=observe_real_locks(monkeypatch)
        assert runner.run_once(tid)=='COMPLETED' and calls==['/discovery','/article']
        assert len(tasks)==len(owners)==1 and tasks[0][2] is True
        assert image(store.path)==before
        with store.transaction() as conn:
            assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0]==2


def test_unbound_application_source_execution_stays_closed():
    with pytest.raises(ResearchError) as failure:require_formal_application(FastAPI(),'source_execute')
    assert failure.value.code=='FEATURE_UNAVAILABLE'
