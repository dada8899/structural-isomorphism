"""Actual R12 formal HTTP/worker, synthetic loopback only; no external credentials."""
from contextlib import contextmanager,closing
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import sqlite3
import threading
import time
from uuid import uuid4
import pytest
from api import auth
from research import ResearchStore,ResearchRunner
from research.authorization import AuthorizationGate
from research.paid_approval import OfflineFundingResolver,request_codec_digest
from research.financial_guard import OfflineProjectRegistration
from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money,canonical,digest
from research.plan_runtime import install_fixture_funding,uninstall_fixture_funding,UPPER
from research.plan_transport import fixture_resource
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack,link,verify,BETA
from .test_research_account_bridge import configure
from .test_research_persistence import envelope,problem
from .test_research_paid_producers import identity

CANDIDATE={'summary':'A starting plan from the self observation.','candidates':[{'label':'Queue variability','mechanism_hypothesis':'Variable arrivals may accumulate work.','why_considered':'The observation concerns waiting.','method_leads':['queueing model'],'key_unknowns':['Arrival variation is unknown.']}],'query_suggestions':[{'candidate_index':0,'query':'queue variability waiting','intent':'Find a possible comparison later.'}],'gaps':['No literature or mathematics has been checked.'],'clarification_questions':[]}

@contextmanager
def provider(*,invalid_body=False,unknown_usage=False,balance='73',before_balance=None,before_post=None):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value):
            raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            calls.append(('GET',self.path,self.headers.get('X-Fixture-Incarnation')))
            if before_balance:before_balance()
            self.reply({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':balance}]})
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']));request=json.loads(raw)
            calls.append(('POST',self.path,self.headers.get('X-Fixture-Incarnation'),request))
            if before_post:before_post()
            self.reply({'id':'fixture-plan-1','model':'deepseek-flash','usage':None if unknown_usage else {'prompt_tokens':100,'completion_tokens':80,'total_tokens':180},'choices':[{'finish_reason':'stop','message':{'content':'{}' if invalid_body else json.dumps(CANDIDATE)}}]})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server,calls
    finally:server.shutdown();server.server_close();thread.join(3)


def send(client,rid,suffix,payload,key):return client.post('/api/research/'+rid+'/'+suffix,json=envelope(payload),headers={'origin':BETA,'idempotency-key':key})


def saved(stack,monkeypatch):
    client,root,mail=stack;configure(client,root,monkeypatch)
    assert verify(client,link(client,mail)).status_code==200
    data=problem();data.update(entry='phenomenon',original_input='我发现团队的到达任务变得集中时，等待时间明显增加。',confirmed=True)
    response=client.post('/api/research',json=envelope({'problem':data}),headers={'origin':BETA,'idempotency-key':'plan-create'})
    assert response.status_code==200
    rid=response.json()['data']['research']['id'];store=ResearchStore(auth._store())
    return client,root,rid,store


@contextmanager
def funded(data,server):
    client,_,rid,store=data;actor=identity(client)
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    money=lambda n:Money(currency='CNY',scale=6,amount_units=n)
    fid,binding,sid=[str(uuid4()) for _ in range(3)];now=int(time.time())
    quote=UsageUpperQuote(revision=str(uuid4()),context_bound=1048576,peak_input_miss_units_per_million=1,peak_output_units_per_million=2,local_guard=1,price_document_digest='a'*64,model_document_digest='b'*64,completion_bound_basis_digest='c'*64,final_request_code_digest=request_codec_digest(),valid_until=now+60)
    basis=BudgetBasisSnapshot(id=sid,account_id=fid,provider_binding_id=binding,funding_epoch=1,initial_prepaid=money(73_000_000),other_use_margin=money(0),cap=money(73_000_000),settled_actual=money(0),upper_booked=money(0),held=money(0),available_after_observed_consumption=money(73_000_000),price_revision=quote.revision,valid_until=now+3600)
    stamp=lambda t:datetime.fromtimestamp(t,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,cap,initial_prepaid_units,other_use_margin_units,status,snapshot_id) VALUES(?,?,'live','deepseek','CNY',73000000,73000000,0,'active',?)",(fid,binding,sid))
        conn.execute('INSERT INTO research_balance_snapshots(id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off,basis_evidence_digest) VALUES(?,?,73000000,0,0,?,?,1,1,1,?)',(sid,fid,stamp(now),stamp(now+3600),digest(canonical(basis.model_dump()))))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,?,'bounded_usage_upper_v2',?,?)",(quote.revision,fid,stamp(now+60),canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    resolver=OfflineFundingResolver(principal_id=pid,quote=quote,basis=basis,approved_upper=money(3))
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,authorized_cap=money(73_000_000),authorization_ref=str(uuid4()))
    resource=fixture_resource(server,economic_binding=binding,credential_incarnation='fixture-credential-1')
    installation=None
    try:
        installation=install_fixture_funding(store,actor,source,resource)
        yield installation
    finally:
        if installation:uninstall_fixture_funding(store,installation)
        else:resource.close()
        source.close();resolver.close()


def preview(client,rid,key='plan-preview'):
    response=send(client,rid,'plan-previews',{'input_revision':1,'expected_research_version':1,'observation_source':'own_observation','declaration_status':'self_declared'},key)
    assert response.status_code==200,response.json().get('error')
    return response.json()['data']


def confirm(client,rid,preview,key='plan-confirm'):
    value={k:preview[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};value['confirm_outbound']=True
    response=send(client,rid,'plan-approvals',value,key)
    assert response.status_code==200,response.json().get('error')
    return response.json()['data'],value


def test_closed_current12_keeps_auth_save_formula_and_refuses_paid(stack,monkeypatch):
    client,root,rid,store=saved(stack,monkeypatch)
    denied=send(client,rid,'plan-previews',{'input_revision':1,'expected_research_version':1,'observation_source':'own_observation','declaration_status':'self_declared'},'closed-preview')
    assert denied.status_code==503 and denied.json()['error']['code']=='FUNDING_CLOSED'
    assert client.get('/api/research/'+rid).status_code==200
    from .test_research_formula_lifecycle import formula_problem
    formula=client.post('/api/research',json=envelope({'problem':formula_problem()}),headers={'origin':BETA,'idempotency-key':'closed-formula-save'})
    assert formula.status_code==200
    formula_rid=formula.json()['data']['research']['id']
    assert client.get('/api/research/'+formula_rid+'/formula-revisions/1').status_code==200
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==12
        assert conn.execute('SELECT count(*) FROM research_plan_dispatches').fetchone()[0]==0


def test_actual_plan_http_confirm_worker_return_read_same_ref_and_history(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        draft=preview(client,rid);assert draft['exact_input']=='我发现团队的到达任务变得集中时，等待时间明显增加。'
        admitted,body=confirm(client,rid,draft)
        replay=send(client,rid,'plan-approvals',body,'plan-confirm');assert replay.json()['data']==admitted
        actual=ResearchRunner(store).run_once(admitted['task_id'])['data'];assert actual['state']=='saved'
        assert [c[0] for c in calls]==['GET','POST'] and calls[0][2]==calls[1][2]=='fixture-credential-1'
        request=calls[1][3];assert request['max_tokens']==4096 and request['stream'] is False and request['tool_choice']=='none' and request['thinking']=={'type':'disabled'}
        path='/api/research/'+rid+'/plan-results/'+admitted['result_ref']
        first=client.get(path);assert first.status_code==200,first.json().get('error')
        content=first.json()['data']['content'];assert content['proposal']==CANDIDATE and content['real_model_executed'] is False
        assert content['query_state']=='draft_only' and content['automatically_created_sources']==0
        assert client.get(path).json()==first.json()
        assert ResearchRunner(store).run_once(admitted['task_id'])['data']['result_ref']==admitted['result_ref']
        assert len(calls)==2
        history=client.get('/api/research/'+rid);assert history.status_code==200 and history.json()['data']['plan_history'][0]['result_ref']==admitted['result_ref']
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,UPPER,0)
            assert conn.execute('SELECT count(*) FROM research_source_runs').fetchone()[0]==0
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_plan_new_process_read_keeps_exact_ref_content_time_without_funding(stack,monkeypatch,tmp_path):
    import multiprocessing
    from .plan_process_fixture import read_plan
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));ResearchRunner(store).run_once(admitted['task_id'])
        original=client.get('/api/research/'+rid+'/plan-results/'+admitted['result_ref']).json()
    output=tmp_path/'reopened.json';child=multiprocessing.get_context('spawn').Process(target=read_plan,args=(str(store.path),rid,admitted['result_ref'],client.cookies.get('phase_session'),str(output)))
    try:
        child.start();child.join(12)
        assert not child.is_alive() and child.exitcode==0
        assert json.loads(output.read_text())==original
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()


@pytest.mark.parametrize('invalid_body,unknown_usage',[(True,False),(False,True)])
def test_invalid_body_retains_cost_unknown_usage_retains_hold_and_never_retries(stack,monkeypatch,invalid_body,unknown_usage):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider(invalid_body=invalid_body,unknown_usage=unknown_usage) as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));result=ResearchRunner(store).run_once(admitted['task_id'])['data']
        assert result['state']==('pending_reconciliation' if unknown_usage else 'failed_insufficient')
        assert result['financial_state']==('unknown' if unknown_usage else 'upper_booked')
        assert client.get('/api/research/'+rid+'/plan-results/'+admitted['result_ref']).json()['data']['content'] is None
        ResearchRunner(store).run_once(admitted['task_id']);assert len(calls)==2
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==((UPPER,0,0) if unknown_usage else (0,UPPER,0))
        if unknown_usage:
            response=send(client,rid,'plan-previews',{'input_revision':1,'expected_research_version':2,'observation_source':'own_observation','declaration_status':'self_declared'},'blocked-before-credential')
            assert response.status_code==409 and response.json()['error']['code']=='RECONCILIATION_REQUIRED'
            assert len(calls)==2


def test_low_fresh_balance_refuses_model_without_zero_cost_claim(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider(balance='0.001') as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        from research.errors import ResearchError
        with pytest.raises(ResearchError) as failure:ResearchRunner(store).run_once(admitted['task_id'])
        assert failure.value.code=='BUDGET_EXHAUSTED' and [v[0] for v in calls]==['GET']
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,0,0)
            assert conn.execute('SELECT state FROM research_plan_dispatches').fetchone()[0]=='closed'


def test_confirmation_cannot_change_raw_template_upper_or_reuse_preview(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        draft=preview(client,rid)
        body={k:draft[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};body.update(confirm_outbound=True,approved_upper_units=UPPER+1)
        assert send(client,rid,'plan-approvals',body,'wrong-upper').status_code==422
        body['approved_upper_units']=UPPER;body['request_digest']='f'*64
        assert send(client,rid,'plan-approvals',body,'wrong-bytes').status_code==409
        assert calls==[]
        admitted,valid=confirm(client,rid,draft)
        assert send(client,rid,'plan-approvals',valid,'different-confirm-key').status_code==409
        assert calls==[]


@pytest.mark.parametrize('native',['ordinary','private'])
def test_f8_native_sql_default_deny_and_rowid_replace_never_rewrites_consent(stack,monkeypatch,native):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        context=closing(sqlite3.connect(store.path,isolation_level=None)) if native=='ordinary' else store.auth_store._connection()
        with context as conn:
            conn.row_factory=sqlite3.Row;conn.execute('BEGIN IMMEDIATE')
            with pytest.raises(sqlite3.Error):conn.execute("UPDATE research_plan_dispatches SET state='returned'")
            with pytest.raises(sqlite3.Error):conn.execute("UPDATE research_plan_previews SET request_digest=?",('0'*64,))
            conn.rollback()
        with closing(sqlite3.connect(store.path,isolation_level=None)) as conn:
            conn.row_factory=sqlite3.Row;conn.create_function('research_plan_write_allowed',4,lambda *args:1);conn.execute('PRAGMA recursive_triggers=0');conn.execute('BEGIN IMMEDIATE')
            value=conn.execute('SELECT rowid,* FROM research_plan_dispatches').fetchone();columns=value.keys();values=list(value);values[columns.index('id')]=str(uuid4())
            with pytest.raises(sqlite3.Error):conn.execute('INSERT OR REPLACE INTO research_plan_dispatches('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',values)
            conn.rollback()
        assert calls==[]


def test_real_http_cancel_closes_queued_plan_no_get_no_post(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        cancelled=send(client,rid,'cancel',{'task_id':admitted['task_id'],'expected_task_version':1},'cancel-plan')
        assert cancelled.status_code==200,cancelled.json().get('error')
        assert ResearchRunner(store).run_once(admitted['task_id'])['data']['state']=='cancelled'
        assert calls==[]


def test_real_http_delete_erases_plan_raw_and_revokes_funding_incarnation(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        result=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
        assert result.status_code==200,result.json().get('error')
        with store.transaction() as conn:
            assert conn.execute('SELECT admission_json,result_json,commit_json,state FROM research_plan_dispatches').fetchone()[:]==(None,None,None,'closed')
            assert conn.execute('SELECT payload_json,research_id,state FROM research_plan_previews').fetchone()[:]==(None,None,'closed')
            assert conn.execute('SELECT status,principal_id,generation FROM research_plan_funding').fetchone()[:]==('retired',None,None)
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert calls==[]


def test_get_baseline_is_before_observation_ledger_change_refuses_post_no_second_get(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    def change_ledger():
        from research.plan_runtime import _money
        with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            account=conn.execute('SELECT * FROM research_funding_accounts').fetchone()
            _money(conn,lease,account,booked_delta=1) # Explicit concurrent synthetic financial writer.
    with provider(before_balance=change_ledger) as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        from research.errors import ResearchError
        with pytest.raises(ResearchError) as failure:ResearchRunner(store).run_once(admitted['task_id'])
        assert failure.value.code=='FUNDING_STALE' and [c[0] for c in calls]==['GET']
        ResearchRunner(store).run_once(admitted['task_id']);assert [c[0] for c in calls]==['GET']
        with store.transaction() as conn:assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,1)


def test_unknown_plan_blocks_legacy_phase_same_economic_ledger_before_network(stack,monkeypatch):
    from research.paid_budget import _limits
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider(unknown_usage=True) as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));ResearchRunner(store).run_once(admitted['task_id'])
        with store.transaction() as conn:
            account=conn.execute('SELECT * FROM research_funding_accounts').fetchone();project=conn.execute('SELECT * FROM research_project_budgets').fetchone()
            with pytest.raises(ResearchError) as failure:_limits(conn,project,account,1)
            assert failure.value.code=='RECONCILIATION_REQUIRED'
        assert len(calls)==2


def test_expired_quote_requires_new_preview_never_gets_balance_or_model(stack,monkeypatch):
    from research import plan_runtime
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        current=time.time();monkeypatch.setattr(plan_runtime.time,'time',lambda:current+61)
        with pytest.raises(ResearchError) as failure:ResearchRunner(store).run_once(admitted['task_id'])
        assert failure.value.code=='PREVIEW_EXPIRED' and calls==[]


@pytest.mark.parametrize('action',['cancel','delete'])
def test_actual_owned_return_after_http_stop_never_restores_plan_body(stack,monkeypatch,action):
    from research import plan_runtime
    data=saved(stack,monkeypatch);client,_,rid,store=data
    ready=threading.Event();go=threading.Event();errors=[];original=plan_runtime._commit_return
    def delayed(*args):
        ready.set()
        assert go.wait(5)
        return original(*args)
    monkeypatch.setattr(plan_runtime,'_commit_return',delayed)
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        def work():
            try:ResearchRunner(store).run_once(admitted['task_id'])
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=work);thread.start()
        try:
            assert ready.wait(5)
            if action=='cancel':
                stopped=send(client,rid,'cancel',{'task_id':admitted['task_id'],'expected_task_version':2},'late-plan-stop')
            else:stopped=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
            assert stopped.status_code==200,stopped.json().get('error')
        finally:go.set();thread.join(6)
        assert not thread.is_alive() and not errors
        with store.transaction() as conn:
            value=conn.execute('SELECT * FROM research_plan_dispatches').fetchone()
            assert value['state']=='closed' and value['result_json'] is None
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,UPPER,0)
            if action=='delete':assert value['admission_json'] is None
        assert [c[0] for c in calls]==['GET','POST']


@pytest.mark.parametrize('cut',['consume','return'])
def test_actual_native_commit_ack_loss_keeps_ref_and_never_repeats_model(stack,monkeypatch,cut):
    from services.sqlite_utils import PrivateAuthConnection
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));original=PrivateAuthConnection.commit;lost=[]
        def commit(conn):
            result=original(conn)
            if not lost:
                value=conn.execute('SELECT state FROM research_plan_dispatches').fetchone()
                if value and value[0]==('consumed' if cut=='consume' else 'returned'):
                    lost.append(True);raise sqlite3.OperationalError('synthetic committed ACK lost')
            return result
        monkeypatch.setattr(PrivateAuthConnection,'commit',commit)
        with pytest.raises(ResearchError):ResearchRunner(store).run_once(admitted['task_id'])
        assert lost==[True]
        read=client.get('/api/research/'+rid+'/plan-results/'+admitted['result_ref'])
        assert read.status_code==200 and read.json()['data']['result_ref']==admitted['result_ref']
        if cut=='consume':
            assert read.json()['data']['state']=='pending_reconciliation' and read.json()['data']['content'] is None
            assert [c[0] for c in calls]==['GET']
        else:
            assert read.json()['data']['state']=='saved' and read.json()['data']['content']['proposal']==CANDIDATE
            assert [c[0] for c in calls]==['GET','POST']
        before=len(calls);ResearchRunner(store).run_once(admitted['task_id']);assert len(calls)==before


def test_owned_transport_rejects_json_pid_receipt_and_wrong_cap_before_socket(stack,monkeypatch):
    from research.plan_transport import OwnedPlanReturn
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server) as installed:
        with pytest.raises(PermissionError):installed.resource.post({'pid':123,'admission_digest':'a'*64})
        with pytest.raises(TypeError):OwnedPlanReturn(_factory=object(),status=200,body=b'{}')
        assert calls==[]


def test_post_wall_budget_does_not_extend_with_response_wait(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider(before_post=lambda:time.sleep(2.1)) as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));started=time.monotonic()
        with pytest.raises(TimeoutError):ResearchRunner(store).run_once(admitted['task_id'])
        assert time.monotonic()-started<3 and [c[0] for c in calls]==['GET','POST']
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state FROM research_plan_dispatches').fetchone()[:]==('unknown','unknown')
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==UPPER


def test_default_worker_scan_only_uses_actual_installed_plan_producer(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid));completed=ResearchRunner(store).run_once()['data']
        assert completed['result_ref']==admitted['result_ref'] and completed['state']=='saved'
        assert [c[0] for c in calls]==['GET','POST']


@pytest.mark.parametrize('phase',['balance','model'])
@pytest.mark.parametrize('action',['cancel','delete'])
def test_actual_http_stop_during_network_does_not_wait_on_owner_or_allow_late_body(stack,monkeypatch,phase,action):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    ready=threading.Event();go=threading.Event();fenced=threading.Event();errors=[];delete_results=[];actor=identity(client)
    if action=='delete':
        from research.service import ResearchService
        begin=ResearchService.begin_account_deletion_locked
        def observe_fence(self,*args,**kwargs):
            value=begin(self,*args,**kwargs)
            from research.errors import ResearchError
            with self.store.transaction() as conn:
                user=conn.execute('SELECT lifecycle FROM auth_users WHERE email=?',(actor.email,)).fetchone()
                assert user and user[0]=='deleting'
                with pytest.raises(ResearchError) as ended:AuthorizationGate.check_account(conn,actor)
                assert ended.value.code=='AUTH_REQUIRED'
            assert not go.is_set() # Actual permission commit precedes response release.
            fenced.set();return value
        monkeypatch.setattr(ResearchService,'begin_account_deletion_locked',observe_fence)
    def pause():ready.set();assert go.wait(2)
    arguments={'before_balance':pause} if phase=='balance' else {'before_post':pause}
    with provider(**arguments) as (server,calls),funded(data,server):
        admitted,_=confirm(client,rid,preview(client,rid))
        def work():
            try:ResearchRunner(store).run_once(admitted['task_id'])
            except BaseException as failure:errors.append(type(failure).__name__)
        thread=threading.Thread(target=work);thread.start()
        try:
            assert ready.wait(3)
            started=time.monotonic()
            if action=='cancel':stopped=send(client,rid,'cancel',{'task_id':admitted['task_id'],'expected_task_version':1 if phase=='balance' else 2},'network-stop')
            else:
                def remove():delete_results.append(client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA}))
                deleter=threading.Thread(target=remove);deleter.start()
                try:
                    assert fenced.wait(1.5) # Real committed permission fence, not total legacy cleanup.
                    assert time.monotonic()-started<1.5
                finally:go.set();deleter.join(6)
                assert not deleter.is_alive()
                stopped=delete_results[0]
            assert stopped.status_code==200,stopped.json().get('error')
            if action=='cancel':assert time.monotonic()-started<1.5
        finally:go.set();thread.join(6)
        assert not thread.is_alive()
        with store.transaction() as conn:
            value=conn.execute('SELECT * FROM research_plan_dispatches').fetchone()
            assert value['state']=='closed' and value['result_json'] is None
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==((0,0,0) if phase=='balance' else (0,UPPER,0))
        assert [c[0] for c in calls]==(['GET'] if phase=='balance' else ['GET','POST'])
        if phase=='model':assert errors==[]


def test_fresh_balance_keeps_prior_upper_booking_as_unsettled_exposure(stack,monkeypatch):
    from research.errors import ResearchError
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider(balance='3') as (server,calls),funded(data,server):
        first,_=confirm(client,rid,preview(client,rid));ResearchRunner(store).run_once(first['task_id'])
        response=send(client,rid,'plan-previews',{'input_revision':1,'expected_research_version':2,'observation_source':'own_observation','declaration_status':'self_declared'},'second-plan-preview')
        assert response.status_code==200
        second,_=confirm(client,rid,response.json()['data'],'second-plan-confirm')
        with pytest.raises(ResearchError) as failure:ResearchRunner(store).run_once(second['task_id'])
        assert failure.value.code=='BUDGET_EXHAUSTED'
        assert [c[0] for c in calls]==['GET','POST','GET']
        with store.transaction() as conn:assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,UPPER)
