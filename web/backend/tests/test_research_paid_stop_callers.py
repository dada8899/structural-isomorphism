"""Real HTTP sources and same-auth-DB stopping; no actual paid dispatch."""
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest

from .test_research_persistence import stack,post
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api,make_preview,confirm_data
from .test_research_paid_budget_loop import execution
from .test_research_paid_producers import identity
from research import paid_budget as ledger,ResearchService,ResearchStore
from research.financial_guard import OfflineProjectRegistration
from research.authorization import AuthorizationGate
from research.provider_schemas import Money
from research.schemas import TaskVersionRequest
from research.errors import ResearchError
from .test_research_lifecycle import lifecycle,delete,login
from .test_research_owned_return import response_body
from research.paid_provider_session import persist_budget_return
from api import auth
import sqlite3
import multiprocessing
from research import paid_control
from research.provider_schemas import canonical,digest
from services.auth_store import AuthStore
from .test_research_lifecycle import _resume_in_new_process


def test_real_http_cancel_of_consumed_v2_keeps_hold_and_single_task_version(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,state,pid):
        body={'task_id':result['task_id'],'expected_task_version':2}
        response=post(client,f'/api/research/{rid}/cancel',body,'actual-http-cancel')
        assert response.status_code==200,response.text
        assert response.json()['data']['execution']=='CANCELLED'
        assert response.json()['data']['task_version']==3
        assert post(client,f'/api/research/{rid}/cancel',body,'actual-http-cancel').json()==response.json()
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(3,0)
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
            assert conn.execute("SELECT count(*) FROM research_task_events WHERE task_id=? AND kind='stop_requested'",(result['task_id'],)).fetchone()[0]==1


def test_real_http_cancel_held_v2_releases_once_but_plain_identity_cannot(paid_api):
    client,_,store,rid,_,resolver=paid_api;actor=identity(client)
    draft=make_preview(paid_api)
    result=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'held-confirm').json()['data']
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=10),authorization_ref=str(uuid4()))
    proof=None
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ledger.activate_offline_in(conn,store=store,actor=actor,lease=lease,source=source)
            proof=ledger.reserve_in(conn,store=store,actor=actor,lease=lease,source=source,approval_ref=result['approval_ref'])
            with pytest.raises(PermissionError):ledger.cancel_in(conn,store=store,actor=actor,lease=lease,task_id=result['task_id'],expected_task_version=1)
        request=TaskVersionRequest(task_id=result['task_id'],expected_task_version=1)
        with pytest.raises(PermissionError):ResearchService(store).task_action(actor,rid,request,'direct-dto','cancel')
        body=request.model_dump(mode='json')
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses=list(pool.map(lambda _:post(client,f'/api/research/{rid}/cancel',body,'held-http-cancel'),range(2)))
        assert all(response.status_code==200 for response in responses),[response.text for response in responses]
        assert responses[0].json()==responses[1].json()
        assert responses[0].json()['data']['task_version']==2
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(0,0)
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='RELEASED'
            assert conn.execute('SELECT state FROM research_dispatch_permits').fetchone()[0]=='revoked'
    finally:
        if proof:ledger._PREPARED.pop(proof.session,None);object.__setattr__(proof,'_active',False)
        source.close()


def test_actual_v2_delete_of_held_ticket_releases_once_and_preserves_protected_origin(paid_api,lifecycle):
    client,_,store,rid,_,resolver=paid_api;actor=identity(client)
    draft=make_preview(paid_api);result=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'delete-held-confirm').json()['data']
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=10),authorization_ref=str(uuid4()))
    proof=None
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ledger.activate_offline_in(conn,store=store,actor=actor,lease=lease,source=source)
            proof=ledger.reserve_in(conn,store=store,actor=actor,lease=lease,source=source,approval_ref=result['approval_ref'])
        response=delete(lifecycle[0]);assert response.status_code==200,response.text
        with store.transaction() as conn:
            job=conn.execute('SELECT * FROM auth_deletion_jobs').fetchone()
            assert job['state']=='completed' and job['origin_version']=='authenticated-delete-v1'
            assert job['owner_email'] is job['session_generation'] is None
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(0,0)
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='RELEASED'
            assert conn.execute('SELECT execution,version FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[:]==('ACCESS_REVOKED',2)
            assert conn.execute("SELECT count(*) FROM research_task_events WHERE task_id=? AND kind='authorization_changed'",(result['task_id'],)).fetchone()[0]<=1
    finally:
        if proof:ledger._PREPARED.pop(proof.session,None);object.__setattr__(proof,'_active',False)
        source.close()


@pytest.mark.parametrize('phase',['sent','unknown','upper'])
def test_real_v2_delete_preserves_possible_fee_and_never_rebooks(paid_api,lifecycle,phase):
    store=paid_api[2]
    with execution(paid_api,body=response_body(usage=None) if phase=='unknown' else response_body()) as (session,result,wire,pid):
        if phase!='sent':
            receipt=session.receive()
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
                ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)
        response=delete(lifecycle[0]);assert response.status_code==200,response.text
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==((0,2) if phase=='upper' else (3,0))
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==(1 if phase=='upper' else 0)
            assert conn.execute('SELECT candidate_json FROM research_provider_sessions').fetchone()[0] is None
            job=dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())
        # Server control returns the persisted result, not a new cleanup pass.
        first=auth.resume_account_deletion(job['id']);second=auth.resume_account_deletion(job['id']);assert first==second
        assert wire['requests']==1


def _resume_scrubbing_child(job_id,result):
    from api import auth
    result.put(auth.resume_account_deletion(job_id))


def test_new_process_finishes_scrubbing_without_old_cookie_email_generation_or_new_incarnation(paid_api,lifecycle,monkeypatch):
    client,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,_,pid):
        def fail(self):raise ResearchError('STORE_BUSY',503,'owned checkpoint fault')
        with monkeypatch.context() as fault:
            fault.setattr(ResearchStore,'checkpoint_erasure',fail)
            response=delete(lifecycle[0]);assert response.status_code==503,response.text
        with store.transaction() as conn:
            job=dict(conn.execute("SELECT * FROM auth_deletion_jobs WHERE state='scrubbing'").fetchone())
            assert job['owner_email'] is job['session_generation'] is None
            assert job['origin_digest']
        ctx=multiprocessing.get_context('spawn');result=ctx.Queue();worker=ctx.Process(target=_resume_scrubbing_child,args=(job['id'],result))
        try:
            worker.start();completed=result.get(timeout=20);worker.join(10);assert worker.exitcode==0
        finally:
            if worker.is_alive():worker.terminate();worker.join(3)
            worker.close();result.close();result.join_thread()
        assert completed['removed']['research']['revisions']>=1
        login(client)
        with store.transaction() as conn:
            fresh=conn.execute("SELECT session_generation FROM auth_users WHERE email='research-a@example.test'").fetchone()[0]
            assert conn.execute('SELECT state FROM auth_deletion_jobs WHERE id=?',(job['id'],)).fetchone()[0]=='completed'
        assert auth.resume_account_deletion(job['id'])==completed
        with store.transaction() as conn:assert conn.execute("SELECT session_generation FROM auth_users WHERE email='research-a@example.test'").fetchone()[0]==fresh


def test_real_route_source_is_bound_to_action_target_payload_key_identity_pid_and_lifetime(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api
    draft=make_preview(paid_api);result=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'source-confirm').json()['data']
    original=ResearchService.task_action;captured=[]
    def inspect(self,actor,research_id,request,key,operation,*,request_source=None):
        captured.append(request_source)
        valid=dict(identity=actor,action='cancel',research_id=research_id,task_id=request.task_id,key=key,
            body_digest=digest(canonical(request.model_dump(mode='json'))))
        assert paid_control.require_authenticated_action(request_source,**valid)
        for change in ({'action':'account-delete'},{'research_id':str(uuid4())},{'task_id':str(uuid4())},
                       {'key':'other-key'},{'body_digest':'f'*64},{'identity':True}):
            with pytest.raises(PermissionError):paid_control.require_authenticated_action(request_source,**dict(valid,**change))
        for source in (None,True,{},actor,{'identity':actor,'action':'cancel'}):
            with pytest.raises(PermissionError):paid_control.require_authenticated_action(source,**valid)
        pid=request_source.pid
        try:
            object.__setattr__(request_source,'pid',-1)
            with pytest.raises(PermissionError):paid_control.require_authenticated_action(request_source,**valid)
        finally:object.__setattr__(request_source,'pid',pid)
        return original(self,actor,research_id,request,key,operation,request_source=request_source)
    with monkeypatch.context() as patch:
        patch.setattr(ResearchService,'task_action',inspect)
        response=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':1},'bound-cancel')
        assert response.status_code==200,response.text
    assert len(captured)==1 and not captured[0].active
    with pytest.raises(PermissionError):paid_control.require_authenticated_action(captured[0],identity=captured[0].identity,action='cancel',research_id=rid,task_id=result['task_id'])
    from starlette.requests import Request
    async def fake_endpoint():pass
    fake_endpoint.__name__='cancel_research_task'
    fake=Request({'type':'http','method':'POST','path':f'/api/research/{rid}/cancel','headers':[],
        'path_params':{'research_id':rid},'app':object(),'endpoint':fake_endpoint})
    fake._body=canonical({'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'task_id':result['task_id'],'expected_task_version':1}})
    with pytest.raises(PermissionError):paid_control.issue_authenticated_action(fake,action='cancel')


def test_v2_pending_failure_keeps_auth_fenced_and_protected_job_recovers_in_new_process(paid_api,lifecycle,monkeypatch):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (_,result,wire,pid):
        with monkeypatch.context() as fault:
            def fail(self,email,**kwargs):raise OSError('owned final-store fault')
            fault.setattr(AuthStore,'delete_account_data',fail)
            response=delete(lifecycle[0])
        assert response.status_code==500 and response.json()['access_ended'] is True
        assert client.get(f'/api/research/{rid}').status_code==401
        with store.transaction() as conn:
            job=dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())
            assert job['state']=='pending' and job['research_erased']==1 and job['legacy_attempted']==1
            assert job['owner_email']=='research-a@example.test' and job['origin_version']=='authenticated-delete-v1'
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
            assert conn.execute('SELECT execution,version FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[:]==('ACCESS_REVOKED',3)
        with store.transaction(write=True) as conn:
            for sql in ["UPDATE auth_deletion_jobs SET research_erased=0", "UPDATE auth_deletion_jobs SET owner_email='other@example.test'",
                        "UPDATE auth_deletion_jobs SET state='scrubbing',owner_email=NULL,session_generation=NULL,result_json='{}'",
                        "DELETE FROM auth_deletion_jobs"]:
                with pytest.raises(sqlite3.IntegrityError):conn.execute(sql)
        _resume_in_new_process(lifecycle[2],job['id'])
        with store.transaction() as conn:
            assert conn.execute('SELECT state,owner_email,session_generation FROM auth_deletion_jobs').fetchone()[:]==('completed',None,None)
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(3,0)
        assert wire['requests']==1


def test_plain_account_identity_and_real_lock_cannot_start_v2_account_deletion(paid_api):
    client,_,store,rid,_,_=paid_api;actor=identity(client)
    draft=make_preview(paid_api);response=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'dto-delete-confirm')
    assert response.status_code==200,response.text
    service=ResearchService(store);gate=store.auth_store.owner_gate_id(actor.email)
    with AuthorizationGate(store).owner_gate_id(gate) as lease:
        with pytest.raises(ResearchError) as rejected:
            service.begin_account_deletion_locked(actor.email,actor.generation,gate,auth._account_cleanup_binding(actor.email),owner_lease=lease)
        assert rejected.value.code=='AUTHORIZATION_STALE'
    with store.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM auth_deletion_jobs').fetchone()[0]==0
        assert conn.execute('SELECT lifecycle FROM auth_users WHERE email=?',(actor.email,)).fetchone()[0]=='active'
        assert conn.execute('SELECT status FROM research_principals').fetchone()[0]=='active'


@pytest.mark.parametrize('raw',[False,True])
def test_real_protected_job_rejects_ordinary_or_missing_hook_write_sign_replace_delete(paid_api,lifecycle,raw):
    client,path,store,_,_,_=paid_api
    with execution(paid_api):
        response=delete(lifecycle[0]);assert response.status_code==200,response.text
        with sqlite3.connect(path) as conn:
            conn.row_factory=sqlite3.Row
            if not raw:
                from research.financial_guard import install_default_hook
                install_default_hook(conn)
            job=dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone());columns=','.join(job)
            statements=[('UPDATE auth_deletion_jobs SET '+column+'=?',(value,)) for column,value in
                [('owner_key','wrong'),('gate_id',str(uuid4())),('database_binding','wrong'),('cleanup_binding','wrong'),
                 ('created_at','wrong'),('origin_version',None),('origin_digest','f'*64),('state','pending'),('owner_email','restored@example.test')]]
            statements+=[('DELETE FROM auth_deletion_jobs',()),
                ('INSERT OR REPLACE INTO auth_deletion_jobs('+columns+') VALUES('+','.join('?' for _ in job)+')',tuple(job.values()))]
            copied=dict(job,id=str(uuid4()))
            statements.append(('INSERT INTO auth_deletion_jobs('+columns+') VALUES('+','.join('?' for _ in copied)+')',tuple(copied.values())))
            for sql,args in statements:
                with pytest.raises((sqlite3.IntegrityError,sqlite3.OperationalError)) as rejected:conn.execute(sql,args)
                if isinstance(rejected.value,sqlite3.OperationalError):assert 'research_financial_write_allowed' in str(rejected.value)
            assert dict(conn.execute('SELECT * FROM auth_deletion_jobs').fetchone())==job
        # Hash/job/real gate do not make a different SQLite connection canonical.
        with AuthorizationGate(store).owner_gate_id(job['gate_id']) as lease,store.transaction() as conn:
            with pytest.raises(PermissionError):paid_control.verify_deletion_origin(conn,store=store,lease=True,job_id=job['id'])
            with sqlite3.connect(':memory:') as copied_conn:
                conn.backup(copied_conn);copied_conn.row_factory=sqlite3.Row
                with pytest.raises(PermissionError):paid_control.verify_deletion_origin(copied_conn,store=store,lease=lease,job_id=job['id'])


def test_v2_reconcile_uses_durable_owned_receipt_and_never_fixture_or_new_send(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            prior_candidate=conn.execute('SELECT candidate_json FROM research_provider_sessions').fetchone()[0]
            assert prior_candidate is not None
        response=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':2},'reconcile-cancel')
        assert response.status_code==200,response.text
        from research.transport import FixtureTransport
        from research import ResearchRunner
        def forbidden(*a,**k):pytest.fail('v2 must not use legacy fixture receipt')
        with monkeypatch.context() as patch:
            patch.setattr(FixtureTransport,'receipt',forbidden)
            response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':3},'actual-reconcile')
            assert response.status_code==200,response.text
            ResearchRunner(store).reconcile(result['task_id'])
            resume=post(client,f'/api/research/{rid}/resume',{'task_id':result['task_id'],'expected_task_version':3},'no-implicit-send')
            assert resume.status_code==503,resume.text
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
            assert conn.execute('SELECT candidate_json FROM research_provider_sessions').fetchone()[0]==prior_candidate
            assert conn.execute('SELECT execution,version FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[:]==('CANCELLED',3)
        assert wire['requests']==1
