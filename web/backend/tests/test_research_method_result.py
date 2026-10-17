"""Actual B transport, actual authenticated HTTP commit/read; synthetic funds."""
import json
import multiprocessing
import importlib
import os
import sqlite3
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest

from .test_research_persistence import stack,post,app
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api
from .test_research_paid_budget_loop import execution
from .test_research_lifecycle import lifecycle,delete,login
from .test_research_owned_return import response_body
from .test_research_paid_producers import identity
from research.authorization import AuthorizationGate
from research.paid_provider_session import persist_budget_return
from research import ResearchService
from research import ResearchStore,ResearchRunner
from research import method_result
from research.errors import ResearchError


def _new_process_get(cookie,rid,tid,out):
    from fastapi.testclient import TestClient
    from research.paid_provider_session import _B_SESSIONS,_OWNED
    from research.paid_approval import _SOURCES
    assert not _B_SESSIONS and not _OWNED and not _SOURCES
    with TestClient(app()) as client:
        client.cookies.set('phase_session',cookie)
        response=client.get(f'/api/research/{rid}',params={'task_id':tid})
        out.put((response.status_code,response.json()))


def test_actual_b_first_fact_authenticated_typed_commit_and_fresh_process_read(paid_api,monkeypatch):
    client,_,store,rid,_,resolver=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        assert receipt._value.candidate is not None,receipt._value.safe_code
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            assert conn.execute('SELECT body_origin_state FROM research_provider_sessions').fetchone()[0]=='fresh'
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            row=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
            assert row['body_origin_state']=='present' and row['method_commit_json'] is None
            envelope=json.loads(row['candidate_json'])
            assert envelope['header']['result_ref']==ref and envelope['candidate_digest']==row['body_candidate_digest']
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'typed-real')
        assert response.status_code==200,response.text
        view=response.json()['data'];report=view['method_result']
        assert report['result_ref']==ref and report['received_at']==receipt._time
        assert report['status']=='qualified_report' and report['evidence']=='INSUFFICIENT'
        assert report['model_analysis_ran'] is False and view['execution']=='COMPLETED'
        assert post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'typed-real').json()==response.json()
        with store.transaction() as conn:
            cached=conn.execute("SELECT result_json FROM research_idempotency WHERE operation='reconcile'").fetchone()[0]
            assert json.loads(cached)=={'_method_result_replay':1,'task_id':result['task_id']}
            assert 'Offline candidate' not in cached and 'candidate_json' not in cached
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
            with pytest.raises(PermissionError):method_result.read_source(conn,store=store,lease=True,identity=identity(client),rid=rid,task_id=result['task_id'],request_source=None)
        assert 'method_result' not in ResearchService(store).view(identity(client),rid,result['task_id'])['data']
        resolver.close()
        from web.backend.tests.test_research_method_result import _new_process_get as target
        ctx=multiprocessing.get_context('spawn');out=ctx.Queue();child=ctx.Process(target=target,args=(client.cookies.get('phase_session'),rid,result['task_id'],out))
        try:
            child.start();status,reopened=out.get(timeout=20);child.join(10)
            assert child.exitcode==0 and status==200,reopened
            assert reopened['data']['method_result']==report
        finally:
            if child.is_alive():child.terminate();child.join(3)
            child.close();out.close();out.join_thread()
        assert wire['requests']==1


@pytest.mark.parametrize('body',[response_body(choices=[]),response_body(usage=None)])
def test_first_bad_body_or_usage_never_becomes_typed_result(paid_api,body):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api,body=body) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'bad-typed')
        assert response.status_code==200,response.text
        current=client.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
        assert current.status_code==200,current.text
        assert current.json()['data']['method_result'] is None
        with store.transaction() as conn:
            assert conn.execute('SELECT method_commit_json FROM research_provider_sessions').fetchone()[0] is None
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]==('UNKNOWN' if receipt._value.usage is None else 'UPPER_BOOKED')
        assert wire['requests']==1


def test_actual_delete_before_first_fact_late_fee_stays_closed_and_cannot_refill(paid_api,lifecycle):
    _,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,wire,pid):
        receipt=session.receive()
        response=delete(lifecycle[0]);assert response.status_code==200,response.text
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            assert conn.execute('SELECT body_origin_state,financial_return_json FROM research_provider_sessions').fetchone()[:]==('closed',None)
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            from research.paid_budget import observe_in
            observe_in(conn,store=store,lease=lease,return_ref=session.id)
            row=conn.execute('SELECT candidate_json,body_origin_state,body_candidate_digest,body_envelope_digest,method_commit_json FROM research_provider_sessions').fetchone()
            assert row[:]==(None,'closed',None,None,None)
        assert wire['requests']==1


def test_protected_body_is_not_writable_by_ordinary_sql_or_missing_hook(paid_api):
    _,path,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        for hook in (True,False):
            with sqlite3.connect(path) as conn:
                if hook:
                    from research.financial_guard import install_default_hook
                    install_default_hook(conn)
                for sql in ["UPDATE research_provider_sessions SET candidate_json=NULL", "UPDATE research_provider_sessions SET body_origin_state='closed',candidate_json=NULL,body_candidate_digest=NULL,body_envelope_digest=NULL",'DELETE FROM research_provider_sessions']:
                    with pytest.raises(sqlite3.DatabaseError):conn.execute(sql)


def test_finance_runner_or_identity_dto_never_mints_typed_result(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        ResearchRunner(store).reconcile(result['task_id'])
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction() as conn:
            assert conn.execute('SELECT method_commit_json FROM research_provider_sessions').fetchone()[0] is None
            with pytest.raises(PermissionError):method_result.read_source(conn,store=store,lease=lease,identity=identity(client),rid=rid,task_id=result['task_id'],request_source=identity(client))
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'after-finance-only')
        assert response.status_code==200,response.text
        assert response.json()['data']['method_result']['result_ref']==session.id
        assert wire['requests']==1


@pytest.mark.parametrize('cached',['stable-ref','legacy-full-response'])
@pytest.mark.parametrize('withdraw',['paid-grant','excerpt'])
def test_cached_replay_rechecks_paid_grant_and_does_not_rollback_late_cost(paid_api,cached,withdraw):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        body={'task_id':result['task_id'],'expected_task_version':2}
        first=post(client,f'/api/research/{rid}/reconcile',body,'fresh-read-every-replay')
        assert first.status_code==200 and first.json()['data']['method_result']
        with store.transaction(write=True) as conn:
            if cached=='legacy-full-response':conn.execute("UPDATE research_idempotency SET result_json=? WHERE operation='reconcile'",(json.dumps(first.json()),))
            if withdraw=='paid-grant':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
            else:conn.execute("DELETE FROM research_evidence_objects WHERE id=? AND kind='excerpts'",(paid_api[4],))
        replay=post(client,f'/api/research/{rid}/reconcile',body,'fresh-read-every-replay')
        assert replay.status_code==200,replay.text
        assert replay.json()['data']['method_result'] is None and 'Offline candidate' not in replay.text
        assert client.get(f'/api/research/{rid}',params={'task_id':result['task_id']}).status_code==404
        with store.transaction() as conn:
            assert conn.execute('SELECT upper_booked,held FROM research_funding_accounts').fetchone()[:]==(2,0)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
        assert wire['requests']==1


def test_revoked_grant_before_typed_commit_preserves_valid_financial_reconciliation(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'financial-independent')
        assert response.status_code==200 and response.json()['data']['method_result'] is None,response.text
        with store.transaction() as conn:
            assert conn.execute('SELECT upper_booked,held FROM research_funding_accounts').fetchone()[:]==(2,0)
            assert conn.execute('SELECT method_commit_json FROM research_provider_sessions').fetchone()[0] is None
        assert wire['requests']==1


def test_two_actual_reconcile_requests_commit_one_result_and_event(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        body={'task_id':result['task_id'],'expected_task_version':2}
        with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:post(client,f'/api/research/{rid}/reconcile',body,'race-one-commit'),range(2)))
        assert all(r.status_code==200 for r in responses),[r.text for r in responses]
        assert responses[0].json()==responses[1].json()
        with store.transaction() as conn:
            assert conn.execute('SELECT version,execution FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[:]==(3,'COMPLETED')
            assert conn.execute("SELECT count(*) FROM research_task_events WHERE task_id=? AND kind='terminal'",(result['task_id'],)).fetchone()[0]==1
        assert wire['requests']==1


def test_delete_after_typed_commit_erases_only_body_and_never_refills_on_old_receipt(paid_api,lifecycle):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'before-delete')
        assert response.status_code==200 and response.json()['data']['method_result']
        assert delete(lifecycle[0]).status_code==200
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert conn.execute('SELECT candidate_json,body_origin_state,body_candidate_digest,body_envelope_digest,method_commit_json FROM research_provider_sessions').fetchone()[:]==(None,'closed',None,None,None)
            assert conn.execute('SELECT upper_booked,held FROM research_funding_accounts').fetchone()[:]==(2,0)
        client.cookies.clear();login(client)
        assert client.get(f'/api/research/{rid}',params={'task_id':result['task_id']}).status_code==404
        assert wire['requests']==1


@pytest.mark.parametrize('target',['id','dispatch_id','permit_id','rowid','insert-rowid'])
@pytest.mark.parametrize('hook',[True,False])
def test_actual_protected_body_survives_all_real_unique_replace_constraints(paid_api,target,hook):
    _,path,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        legacy=str(uuid4())
        # Unsigned shape is only a negative SQL fixture, never a source proof.
        # Dedicated default body hook, no financial permit, FK-off raw SQLite.
        with sqlite3.connect(path) as seed:
            seed.row_factory=sqlite3.Row;method_result.install_hook(seed)
            original=dict(seed.execute('SELECT rowid AS stored_rowid,* FROM research_provider_sessions').fetchone())
            seed.execute("INSERT INTO research_provider_sessions(id,approval_id,dispatch_id,permit_id,mode,binding_digest,state) VALUES(?,?,?,?,'offline_probe',?,'created')",
                (legacy,original['approval_id'],str(uuid4()),str(uuid4()),'a'*64))
        try:
            with sqlite3.connect(path) as conn:
                conn.row_factory=sqlite3.Row
                if hook:method_result.install_hook(conn)
                assert conn.execute('PRAGMA recursive_triggers').fetchone()[0]==0
                if target=='insert-rowid':
                    sql="INSERT OR REPLACE INTO research_provider_sessions(rowid,id,approval_id,dispatch_id,permit_id,mode,binding_digest,state) VALUES(?,?,?,?,?,'offline_probe',?,'created')"
                    args=(original['stored_rowid'],str(uuid4()),original['approval_id'],str(uuid4()),str(uuid4()),'b'*64)
                else:
                    sql='UPDATE OR REPLACE research_provider_sessions SET '+target+'=? WHERE id=?'
                    args=(original['stored_rowid'] if target=='rowid' else original[target],legacy)
                with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,args)
                assert dict(conn.execute('SELECT rowid AS stored_rowid,* FROM research_provider_sessions WHERE id=?',(session.id,)).fetchone())==original
        finally:
            with sqlite3.connect(path) as clean:clean.execute('DELETE FROM research_provider_sessions WHERE id=?',(legacy,))


def test_financial_write_scope_never_grants_body_erase_or_commit(paid_api):
    _,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            from research.paid_budget import _write
            with pytest.raises(sqlite3.DatabaseError):_write(conn,lease,'return',session.id,'research_provider_sessions',session.id,
                "UPDATE research_provider_sessions SET candidate_json=NULL,body_origin_state='closed',body_candidate_digest=NULL,body_envelope_digest=NULL WHERE id=?",(session.id,))
            assert conn.execute('SELECT body_origin_state FROM research_provider_sessions').fetchone()[0]=='present'


def test_ordinary_callback_and_owner_id_cannot_mint_receipt_body_scope(paid_api):
    from types import SimpleNamespace
    _,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            fake=SimpleNamespace(_owner=SimpleNamespace(id=session.id))
            values=method_result._values(method_result._row(conn,session.id),candidate_json=None,body_origin_state='closed',body_candidate_digest=None,body_envelope_digest=None,method_commit_json=None)
            with pytest.raises(PermissionError):
                with method_result.receipt_scope(conn,store=store,lease=lease,receipt=fake,values=values,decision=lambda:None):
                    conn.execute("UPDATE research_provider_sessions SET candidate_json=NULL,body_origin_state='closed',body_candidate_digest=NULL,body_envelope_digest=NULL,method_commit_json=NULL WHERE id=?",(session.id,))


def test_actual_request_reader_binds_route_task_action_key_pid_and_lifetime(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api
    from research.paid_control import require_authenticated_action
    captured=[];original=method_result.read_source
    def checked(conn,**kwargs):
        source=kwargs['request_source'];captured.append(source)
        valid=dict(identity=kwargs['identity'],action=source.action,research_id=rid,task_id=source.task_id)
        for changes in ({'action':'cancel'},{'research_id':str(uuid4())},{'task_id':str(uuid4())},{'key':'wrong-body-operation-key'},{'body_digest':'f'*64}):
            with pytest.raises(PermissionError):require_authenticated_action(source,**dict(valid,**changes))
        for fake in (None,True,{},kwargs['identity']):
            with pytest.raises(PermissionError):original(conn,**dict(kwargs,request_source=fake))
        pid=source.pid
        try:
            object.__setattr__(source,'pid',-1)
            with pytest.raises(PermissionError):original(conn,**kwargs)
        finally:object.__setattr__(source,'pid',pid)
        return original(conn,**kwargs)
    with execution(paid_api) as (session,result,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        monkeypatch.setattr(method_result,'read_source',checked)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'provenance-typed')
        assert response.status_code==200,response.text
        response=client.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
        assert response.status_code==200,response.text
        assert captured and all(not source.active for source in captured)
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction() as conn:
            with pytest.raises(PermissionError):original(conn,store=store,lease=lease,identity=identity(client),rid=rid,task_id=result['task_id'],request_source=captured[-1])
        assert client.get(f'/api/research/{rid}',params=[('task_id',result['task_id']),('task_id',result['task_id'])]).status_code==422
        assert client.get(f'/api/research/{rid}',params={'unexpected':'read-all'}).status_code==422


def test_first_closed_permission_cannot_be_refilled_when_fixture_permission_returns(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            grant=conn.execute('SELECT grant_id FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[0]
            conn.execute("UPDATE research_grants SET status='revoked' WHERE id=?",(grant,))
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert conn.execute('SELECT body_origin_state,candidate_json FROM research_provider_sessions').fetchone()[:]==('closed',None)
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            conn.execute("UPDATE research_grants SET status='active' WHERE id=?",(grant,))
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert conn.execute('SELECT body_origin_state,candidate_json FROM research_provider_sessions').fetchone()[:]==('closed',None)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'closed-never-refill')
        assert response.status_code==200 and response.json()['data']['method_result'] is None
        assert wire['requests']==1


@pytest.mark.parametrize('prefix',['api','web.backend.api'])
def test_both_actual_api_namespaces_read_and_commit_the_same_protected_body(paid_api,prefix):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    client,_,store,rid,_,_=paid_api
    module=importlib.import_module(prefix+'.research')
    application=FastAPI();application.include_router(module.router,prefix='/api')
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        with TestClient(application) as incoming:
            incoming.cookies.update(client.cookies)
            response=post(incoming,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'namespace-typed')
            assert response.status_code==200,response.text
            report=response.json()['data']['method_result'];assert report['result_ref']==session.id
            read=incoming.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
            assert read.status_code==200 and read.json()['data']['method_result']==report,read.text
        assert wire['requests']==1


def _body_crash(cookie,rid,excerpt,principal,quote,basis,cut):
    from fastapi.testclient import TestClient
    from research.paid_approval import OfflineFundingResolver
    from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money
    from api import auth
    resolver=OfflineFundingResolver(principal_id=principal,quote=UsageUpperQuote.model_validate(quote),
        basis=BudgetBasisSnapshot.model_validate(basis),approved_upper=Money(currency='CNY',scale=6,amount_units=3))
    application=app();application.state.research_paid_resolver=resolver
    with TestClient(application) as client:
        client.cookies.set('phase_session',cookie);store=ResearchStore(auth._store())
        with execution((client,store.path,store,rid,excerpt,resolver)) as (session,_,_,pid):
            receipt=session.receive();assert receipt._value.candidate is not None
            connect=sqlite3.connect;pending=[]
            class Crash(sqlite3.Connection):
                def execute(self,sql,*a,**k):
                    value=super().execute(sql,*a,**k)
                    if sql.startswith('UPDATE research_provider_sessions SET state=?,version=version+1,financial_return_json='):
                        pending.append(True)
                        if cut=='body-sql':os._exit(71)
                    return value
                def commit(self):
                    super().commit()
                    if pending and cut=='after-commit':os._exit(72)
            sqlite3.connect=lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Crash,**k)
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)


@pytest.mark.parametrize('cut',['body-sql','after-commit'])
def test_process_death_during_first_body_write_or_after_commit_recovers_without_owned_cache(paid_api,cut):
    client,_,store,rid,excerpt,resolver=paid_api
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    from web.backend.tests.test_research_method_result import _body_crash as target
    child=multiprocessing.get_context('spawn').Process(target=target,args=(client.cookies.get('phase_session'),rid,excerpt,pid,resolver._quote.model_dump(),resolver._basis.model_dump(),cut))
    try:
        child.start();child.join(25);assert not child.is_alive() and child.exitcode==(71 if cut=='body-sql' else 72)
    finally:
        if child.is_alive():child.terminate();child.join(3)
        child.close()
    with store.transaction() as conn:
        row=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
        task=conn.execute("SELECT * FROM research_tasks WHERE policy_revision='bounded_usage_upper_v2'").fetchone()
    assert row['body_origin_state']==('fresh' if cut=='body-sql' else 'present')
    assert (row['financial_return_json'] is None)==(cut=='body-sql')
    response=post(client,f'/api/research/{rid}/reconcile',{'task_id':task['id'],'expected_task_version':2},'recover-body-process')
    assert response.status_code==200,response.text
    report=response.json()['data']['method_result']
    if cut=='body-sql':
        assert report is None
        with store.transaction() as conn:assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(3,0)
    else:
        assert report['result_ref']==row['id'] and report['received_at']==row['received_at']
        with store.transaction() as conn:assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
    assert client.get(f'/api/research/{rid}',params={'task_id':task['id']}).json()['data']['method_result']==report


@pytest.fixture
def v8_origin_profile(monkeypatch):
    with monkeypatch.context() as profile:
        profile.setattr(ResearchStore,'_migrate_v9',lambda self:None)
        yield profile


def test_real_old_v8_session_is_never_retroactively_signed(v8_origin_profile,paid_api):
    from api import auth
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            original=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
            assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==8
            assert original['candidate_json']
        v8_origin_profile.undo();ResearchStore(auth._store())
        with store.transaction(write=True) as conn:
            current=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
            assert {key:current[key] for key in original}==original
            assert current['body_origin_state']=='legacy_unproved' and current['body_candidate_digest'] is current['body_envelope_digest'] is current['method_commit_json'] is None
            with pytest.raises(sqlite3.DatabaseError):conn.execute("UPDATE research_provider_sessions SET body_origin_state='fresh',candidate_json=NULL")
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'legacy-not-body-source')
        assert response.status_code==200 and response.json()['data']['method_result'] is None,response.text
        assert wire['requests']==1


@pytest.mark.parametrize('point',['sql','commit-before','commit-lost-ack'])
def test_actual_first_fact_fault_or_lost_ack_never_leaves_half_body_or_duplicates(paid_api,monkeypatch,point):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive();connect=sqlite3.connect;hit=[];saw=[]
        class Fault(sqlite3.Connection):
            def execute(self,sql,*a,**k):
                if sql.startswith('UPDATE research_provider_sessions SET state=?,version=version+1,financial_return_json='):
                    saw.append(True)
                    if point=='sql':hit.append(True);raise sqlite3.OperationalError('owned body/fact SQL fault')
                return super().execute(sql,*a,**k)
            def commit(self):
                if saw and point=='commit-before':hit.append(True);raise sqlite3.OperationalError('owned body commit fault')
                super().commit()
                if saw and point=='commit-lost-ack':hit.append(True);raise sqlite3.OperationalError('owned body ack lost')
        with monkeypatch.context() as fault:
            fault.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
            with AuthorizationGate(store).owner_gate(pid) as lease:
                with pytest.raises(ResearchError):
                    with store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        assert hit
        # Reconcile the actual durable outcome before same-receipt replay.
        with store.transaction() as conn:
            row=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
            assert row['body_origin_state']==('present' if point=='commit-lost-ack' else 'fresh')
            assert (row['financial_return_json'] is not None)==(point=='commit-lost-ack')
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'body-fault-recovered')
        assert response.status_code==200 and response.json()['data']['method_result']['received_at']==receipt._time,response.text
        with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
        assert wire['requests']==1


def test_sealed_receipt_decision_rejects_changed_values_and_retired_scope(paid_api):
    from research.paid_budget import PRODUCER as financial_producer
    from research.provider_schemas import canonical,digest
    _,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            admission=conn.execute('SELECT id,snapshot_digest FROM research_financial_admissions').fetchone()
            raw=canonical(dict(record_version=financial_producer,admission_ref=admission['id'],admission_digest=admission['snapshot_digest'],
                transport=receipt._value.model_dump(exclude={'candidate','context'}),received_at=receipt._time,execution_mode='offline_probe',model_analysis_ran=False,actual_charge=None)).decode()
            values,decision=method_result.receipt_body_scope(conn,store=store,lease=lease,receipt=receipt,raw=raw,return_digest=digest(raw.encode()))
            changed=dict(values,candidate_json=None,body_origin_state='closed',body_candidate_digest=None,body_envelope_digest=None)
            with pytest.raises(PermissionError):method_result.receipt_scope(conn,store=store,lease=lease,receipt=receipt,values=changed,decision=decision)
            with pytest.raises(PermissionError):method_result.receipt_body_scope(conn,store=store,lease=lease,receipt=receipt,raw='{}',return_digest=digest(b'{}'))
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):decision.require(conn)
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)


def test_rebinding_task_to_another_valid_grant_does_not_inherit_body(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,_,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        body={'task_id':result['task_id'],'expected_task_version':2}
        response=post(client,f'/api/research/{rid}/reconcile',body,'original-grant')
        assert response.status_code==200 and response.json()['data']['method_result']
        with store.transaction(write=True) as conn:
            grant=dict(conn.execute('SELECT * FROM research_grants WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)',(result['task_id'],)).fetchone())
            grant['id']=str(uuid4())
            conn.execute('INSERT INTO research_grants('+','.join(grant)+') VALUES('+','.join('?' for _ in grant)+')',tuple(grant.values()))
            conn.execute('UPDATE research_tasks SET grant_id=? WHERE id=?',(grant['id'],result['task_id']))
        assert client.get(f'/api/research/{rid}',params={'task_id':result['task_id']}).status_code==404
        assert post(client,f'/api/research/{rid}/reconcile',body,'original-grant').json()['data']['method_result'] is None


@pytest.mark.parametrize('point',['method-meta','step','task','research','event','commit-before','commit-lost-ack'])
def test_typed_commit_cas_faults_or_lost_ack_are_atomic_and_replay_current_result(paid_api,monkeypatch,point):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        connect=sqlite3.connect;saw=[];hit=[]
        markers={'method-meta':'UPDATE research_provider_sessions SET method_commit_json=',
            'step':"UPDATE research_steps SET state='SUCCEEDED'",'task':"UPDATE research_tasks SET execution='COMPLETED',evidence=",
            'research':'UPDATE research_controls SET version=version+1 WHERE id=? AND version=?',
            'event':'INSERT INTO research_task_events'}
        class Fault(sqlite3.Connection):
            def execute(self,sql,*a,**k):
                if sql.startswith('UPDATE research_provider_sessions SET method_commit_json='):saw.append(True)
                if point in markers and sql.startswith(markers[point]):hit.append(True);raise sqlite3.OperationalError('owned typed CAS fault')
                return super().execute(sql,*a,**k)
            def commit(self):
                if saw and point=='commit-before':hit.append(True);raise sqlite3.OperationalError('owned typed commit fault')
                super().commit()
                if saw and point=='commit-lost-ack':hit.append(True);raise sqlite3.OperationalError('owned typed ack lost')
        body={'task_id':result['task_id'],'expected_task_version':2}
        with monkeypatch.context() as fault:
            fault.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
            response=post(client,f'/api/research/{rid}/reconcile',body,'typed-CAS-fault')
        assert hit and response.status_code==503,response.text
        with store.transaction() as conn:
            saved=conn.execute('SELECT method_commit_json FROM research_provider_sessions').fetchone()[0]
            assert (saved is not None)==(point=='commit-lost-ack')
            task=conn.execute('SELECT execution,version FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()
            assert task[:]==(('COMPLETED',3) if point=='commit-lost-ack' else ('WAITING_EXTERNAL',2))
        replay=post(client,f'/api/research/{rid}/reconcile',body,'typed-CAS-fault')
        assert replay.status_code==200 and replay.json()['data']['method_result']['result_ref']==session.id,replay.text
        with store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
            assert conn.execute("SELECT count(*) FROM research_task_events WHERE task_id=? AND kind='terminal'",(result['task_id'],)).fetchone()[0]==1
        assert wire['requests']==1
