"""Native13 minimum real HTTP/worker contract, controlled transport only."""
from contextlib import contextmanager,closing
import json,sqlite3
import pytest
from research import ResearchRunner
from research import plan_native as native,plan_native_runtime as flow
from research.errors import ResearchError
from .test_research_funded_plan import saved,provider,CANDIDATE
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack,BETA
from .test_research_paid_producers import identity


def post(client,rid,suffix,data,key):
    return client.post('/api/research/'+rid+'/'+suffix,json={'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':data},headers={'origin':BETA,'idempotency-key':key})


@contextmanager
def installed(data,server):
    client,_,rid,store=data
    authority=native.create_controlled_fixture_authority(store,identity(client),server,approved_cap_units=41_000_000,risk_margin_units=1_000_000)
    provision=native.issue_native_provision(store,authority);permit=native.mint_runtime_permit(provision);resource=native.open_controlled_fixture_resource(permit)
    try:
        native.install_native_funding(store,provision,resource)
        yield resource
    finally:native.retire_installation(store)


def preview(client,rid):
    value=post(client,rid,'plan-previews',dict(input_revision=1,expected_research_version=1,observation_source='own_observation',declaration_status='self_declared'),'native-preview')
    assert value.status_code==200,value.json().get('error')
    return value.json()['data']


def admitted(client,rid):
    value=preview(client,rid)
    body={key:value[key] for key in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};body['confirm_outbound']=True
    response=post(client,rid,'plan-approvals',body,'native-confirm')
    assert response.status_code==200,response.json().get('error')
    return response.json()['data']


def test_native_closed_allows_cost_preview_without_cash_or_funding_and_keeps_saved_question(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    value=preview(client,rid)
    assert value['cash_evidence']=='not_observed' and value['can_confirm'] is False and value['funding_reason']=='FUNDING_CLOSED'
    with pytest.raises(ResearchError) as closed:native.bootstrap_native_owner_authority(store)
    assert closed.value.code=='FUNDING_CLOSED'
    assert client.get('/api/research/'+rid).status_code==200
    with store.transaction() as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==13
        assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0


def test_native_actual_http_worker_single_requests_typed_saved_ref_no_cap_as_cash(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),installed(data,server):
        result=admitted(client,rid)
        assert result['cash_evidence']=='not_observed'
        with store.transaction() as conn:
            account=conn.execute('SELECT * FROM research_funding_accounts').fetchone()
            assert account['cap']==0 and account['initial_prepaid_units'] is None and account['other_use_margin_units'] is None
            assert account['held']==0
        outcome=ResearchRunner(store).run_once(result['task_id'])['data']
        assert outcome['state']=='saved' and outcome['cleanup_state']=='clean' and outcome['real_model_executed'] is False
        assert [call[0] for call in calls]==['GET','POST']
        path='/api/research/'+rid+'/plan-results/'+result['result_ref']
        response=client.get(path);assert response.status_code==200,response.json().get('error')
        content=response.json()['data']['content'];assert content['proposal']==CANDIDATE and content['execution_mode']=='controlled_fixture' and content['real_model_executed'] is False
        assert content['automatically_created_sources']==0
        assert client.get(path).json()==response.json()
        ResearchRunner(store).run_once(result['task_id']);assert len(calls)==2
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER,0)
            assert conn.execute('SELECT cap,initial_prepaid_units FROM research_funding_accounts').fetchone()[:]==(0,None)
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_native_preconnect_failure_is_before_consume_releases_reserved_hold(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    def fail(_):raise OSError('synthetic prepare failure')
    monkeypatch.setattr(native.ControlledNativeResource,'prepare_post',fail)
    with provider() as (server,calls),installed(data,server):
        result=admitted(client,rid)
        with pytest.raises(OSError):ResearchRunner(store).run_once(result['task_id'])
        assert [c[0] for c in calls]==['GET']
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('closed','unreserved','clean')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,0)
        ResearchRunner(store).run_once(result['task_id']);assert len(calls)==1


def test_native_json_authority_and_foreign_types_cannot_install(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with pytest.raises((TypeError,PermissionError)):native.issue_native_provision(store,{'approved':True,'owner':identity(client).email})
    with pytest.raises(TypeError):native.OwnerFundingAuthorityLease(_factory=object())
    with pytest.raises((TypeError,PermissionError)):native.open_plan_resource({'mode':'native_live','runtime_digest':'a'*64})
    with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_funding').fetchone()[0]==0


@pytest.mark.parametrize('native_connection',['ordinary','private'])
def test_native13_rows_and_shared_ledger_default_deny_without_scope(stack,monkeypatch,native_connection):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),installed(data,server):
        admitted(client,rid)
        context=closing(sqlite3.connect(store.path,isolation_level=None)) if native_connection=='ordinary' else store.auth_store._connection()
        with context as conn:
            conn.execute('BEGIN IMMEDIATE')
            for sql in ("UPDATE research_plan_native_funding SET state='blocked'","UPDATE research_plan_native_runs SET state='consumed'","UPDATE research_funding_accounts SET held=3"):
                with pytest.raises(sqlite3.Error):conn.execute(sql)
            conn.rollback()
        assert calls==[]


def test_native_cleanup_attempts_every_resource_and_never_masks_retirement_failure():
    calls=[]
    class Resource:
        def __init__(self,name,fail=False):self.name,self.fail=name,fail
        def close(self):
            calls.append(self.name)
            if self.fail:raise OSError('synthetic close failure')
    class Flight:
        def release(self):calls.append('flight')
    errors=native.retire_attempts(Resource('pending',True),Resource('owned',True),Resource('balance'),flight=Flight())
    assert errors==('OSError','OSError') and calls==['pending','owned','balance','flight']


@pytest.mark.parametrize('action',['cancel','delete'])
def test_native_actual_owned_late_return_books_cost_without_reviving_body(stack,monkeypatch,action):
    import threading
    from .test_research_funded_plan import send
    data=saved(stack,monkeypatch);client,_,rid,store=data
    ready=threading.Event();go=threading.Event();errors=[];original=flow._commit_return
    def delayed(*args):
        ready.set();assert go.wait(5)
        return original(*args)
    monkeypatch.setattr(flow,'_commit_return',delayed)
    with provider() as (server,calls),installed(data,server):
        result=admitted(client,rid)
        def work():
            try:ResearchRunner(store).run_once(result['task_id'])
            except BaseException as error:errors.append(type(error).__name__)
        thread=threading.Thread(target=work);thread.start()
        try:
            assert ready.wait(5)
            stopped=(send(client,rid,'cancel',{'task_id':result['task_id'],'expected_task_version':2},'native-late-stop') if action=='cancel' else client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA}))
            assert stopped.status_code==200,stopped.json().get('error')
        finally:go.set();thread.join(7)
        assert not thread.is_alive() and not errors,errors
        with store.transaction() as conn:
            value=conn.execute('SELECT * FROM research_plan_native_runs').fetchone()
            assert value['state']=='closed' and value['result_json'] is None and value['cleanup_state']=='clean'
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
            if action=='delete':assert value['consent_json'] is None and value['admission_json'] is None
        assert [call[0] for call in calls]==['GET','POST']


def test_native_owned_close_failure_keeps_booked_result_and_quarantines_resource(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    original=native.OwnedNativeReturn.close
    def close(value):original(value);raise OSError('synthetic actual return retirement failure')
    monkeypatch.setattr(native.OwnedNativeReturn,'close',close)
    with provider() as (server,calls),installed(data,server) as resource:
        result=admitted(client,rid)
        with pytest.raises(ResearchError) as failed:ResearchRunner(store).run_once(result['task_id'])
        assert failed.value.code=='CLEANUP_UNCERTAIN'
        assert resource.flight.acquire(blocking=False)
        resource.flight.release()
        with pytest.raises(PermissionError):resource.require()
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state,cleanup_state FROM research_plan_native_runs').fetchone()[:]==('returned','upper_booked','uncertain')
            assert conn.execute('SELECT state FROM research_plan_native_funding').fetchone()[0]=='blocked'
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
        response=client.get('/api/research/'+rid+'/plan-results/'+result['result_ref'])
        assert response.status_code==200 and response.json()['data']['content']['proposal']==CANDIDATE
        ResearchRunner(store).run_once(result['task_id']);assert len(calls)==2


def test_native_first_write_ambiguous_never_retries_and_keeps_held(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    def failed(pending,cap):
        cap.consume(pending.resource)
        raise OSError('synthetic post-consume first-write ambiguity')
    monkeypatch.setattr(native.ControlledNativePending,'write_first',failed)
    with provider() as (server,calls),installed(data,server):
        result=admitted(client,rid)
        with pytest.raises(OSError):ResearchRunner(store).run_once(result['task_id'])
        with store.transaction() as conn:
            assert conn.execute('SELECT state,cost_state FROM research_plan_native_runs').fetchone()[:]==('unknown','unknown')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(flow.UPPER,0)
        ResearchRunner(store).run_once(result['task_id']);assert [c[0] for c in calls]==['GET']



def test_native_public_response_and_actual_http_contract_are_strict():
    import importlib.util
    from pathlib import Path
    from research import plan_native_schemas as runtime
    path=Path(__file__).resolve().parents[1]/'schemas.py'
    spec=importlib.util.spec_from_file_location('native_public_shapes',path);public=importlib.util.module_from_spec(spec);spec.loader.exec_module(public)
    for name in ('NativePlanQuote','NativePlanPreviewEnvelope','NativePlanConfirmationEnvelope','NativePlanResult','NativePlanPreviewResponse','NativePlanConfirmationResponse','NativePlanReadResponse'):
        assert getattr(runtime,name).model_json_schema()==getattr(public,name).model_json_schema(),name
    from api.research import router
    from fastapi import FastAPI
    app=FastAPI();app.include_router(router,prefix='/api');schema=app.openapi()
    for suffix in ('plan-previews','plan-approvals'):
        method=schema['paths']['/api/research/{research_id}/'+suffix]['post']
        assert len(method['requestBody']['content']['application/json']['schema']['oneOf'])==2
        assert len(method['responses']['200']['content']['application/json']['schema']['anyOf'])==2



def test_native_retired_runtime_permit_cannot_retain_resource_sending_authority(stack,monkeypatch):
    data=saved(stack,monkeypatch);client,_,rid,store=data
    with provider() as (server,calls),installed(data,server) as resource:
        result=admitted(client,rid);resource.permit.close()
        with pytest.raises(PermissionError):resource.require()
        with pytest.raises(PermissionError):ResearchRunner(store).run_once(result['task_id'])
        assert calls==[]
        assert resource.flight.acquire(blocking=False);resource.flight.release()
