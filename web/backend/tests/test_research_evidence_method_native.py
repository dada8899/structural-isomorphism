"""Actual F9 producer stages with the fixed new-purpose controlled resource."""
from contextlib import contextmanager
import json
import pytest
from research import plan_native as native,plan_native_runtime as flow
from research import evidence_method_plan_codec as codec
from research.errors import ResearchError
from .test_research_evidence_method_plan import actual,preview,approve,send
from .test_research_funded_plan import provider


@contextmanager
def installed(store,actor,server,*,old=False):
    factory=native.create_controlled_fixture_authority if old else native.create_controlled_evidence_method_fixture_authority
    authority=factory(store,actor,server,approved_cap_units=41_000_000,risk_margin_units=1_000_000)
    provision=native.issue_native_provision(store,authority);permit=native.mint_runtime_permit(provision);resource=native.open_controlled_fixture_resource(permit)
    try:
        native.install_native_funding(store,provision,resource);yield resource
    finally:native.retire_installation(store)


def example():return codec.strict_json(codec.PROTOCOL_BYTES,8192)['example']


def test_actual_http_new_purpose_confirm_controlled_return_save_read_and_replay(tmp_path):
    with actual(tmp_path) as (service,client,store,actor),provider(choices=[{'finish_reason':'stop','message':{'content':json.dumps(example())}}]) as (server,calls),installed(store,actor,server):
        status,response=preview(service,client);assert status==200,response
        assert response['data']['can_confirm'] is True
        (status,confirmation),body=approve(service,client,response['data']);assert status==200,confirmation
        tid=confirmation['data']['task_id'];ref=confirmation['data']['result_ref'];rid=service.seed.research_id
        replay=send(client,rid,'evidence-method-plan-approvals',body,'evidence-confirm');assert replay==(status,confirmation)
        with store.transaction() as conn:
            assert json.loads(conn.execute("SELECT scopes FROM research_grants WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(tid,)).fetchone()[0])==['execute','provider_outbound']
            assert calls==[] and conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==0
        outcome=flow.run_once(store,tid)['data'];assert outcome['state']=='saved',outcome
        assert [call[0] for call in calls]==['GET','POST']
        status,saved=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref);assert status==200,saved
        result=saved['data']['content'];assert saved['data']['content_state']=='available'
        assert result['candidate']==example() and result['real_model_executed'] is False
        assert result['maturity_status']=='candidate_unverified' and result['mathematics_status']=='not_checked'
        assert client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref)==(status,saved)
        assert client.request('GET','/api/research/'+rid+'/plan-results/'+ref)[0]==404
        root=client.request('GET','/api/research/'+rid)[1]['data'];assert root['native_plan_history']==[] and 'native_plan' not in root
        listing=client.request('GET','/api/research/'+rid+'/evidence-method-plans')[1]['data'];assert listing['items']==[saved['data']['metadata']]
        assert flow.run_once(store,tid)['data']['result_ref']==ref and len(calls)==2
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER,0)
            cached=json.loads(conn.execute("SELECT result_json FROM research_idempotency WHERE operation='evidence-method-confirm'").fetchone()[0]);assert set(cached)=={'dispatch_id','task_id','result_ref'}
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('old',[True,False])
def test_actual_sealed_factory_purpose_domains_are_mutually_exclusive(tmp_path,old):
    with actual(tmp_path) as (service,client,store,actor),provider() as (server,calls),installed(store,actor,server,old=old) as resource:
        own='phenomenon_plan_v1' if old else 'evidence_method_plan_v1';other='evidence_method_plan_v1' if old else 'phenomenon_plan_v1'
        assert native.require_purpose(store,own) is resource
        with pytest.raises(ResearchError) as error:native.require_purpose(store,other)
        assert error.value.code=='FUNDING_CLOSED' and calls==[]
        with pytest.raises(PermissionError):native._fixture_authority(store,actor,server,41_000_000,1_000_000,native._module_digest(),_evidence=True)
        with pytest.raises(TypeError):flow.NativePlanSendLease(store,resource,None,'fake',b'{}',1,1,_factory=object())
        with pytest.raises((TypeError,PermissionError)):native.issue_native_provision(store,{'purpose':other,'owner':True})
        from research import evidence_method_plan as plan
        from research.authorization import AuthorizationGate
        with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(service.seed.research_id,)).fetchone()[0]
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction() as conn:
            with pytest.raises(PermissionError):plan.issue_evidence_task_scope_in(conn,store,lease,'ffffffff-ffff-4fff-bfff-ffffffffffff','balance')
        with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_plan_native_runs').fetchone()[0]==0


def test_actual_main_existing_self_declared_chain_stays_separate_and_works(tmp_path):
    with actual(tmp_path) as (service,client,store,actor),provider() as (server,calls),installed(store,actor,server,old=True):
        from .test_formal_main_admission import problem,envelope
        status,created=client.request('POST','/api/research',envelope({'problem':problem()}),key='separate-own-observation')
        assert status==200,created;rid=created['data']['research']['id']
        def old_send(suffix,data,key):
            return client.request('POST','/api/research/'+rid+'/'+suffix,{'schema_version':'structure-research-v1','contract_revision':'funded-plan-v2','data':data},key=key)
        status,response=old_send('plan-previews',dict(input_revision=1,expected_research_version=1,observation_source='own_observation',declaration_status='self_declared'),'self-preview')
        assert status==200,response;value=response['data'];assert value['can_confirm'] is True
        body={k:value[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};body['confirm_outbound']=True
        status,response=old_send('plan-approvals',body,'self-confirm');assert status==200,response
        ref=response['data']['result_ref'];tid=response['data']['task_id']
        result=flow.run_once(store,tid)['data'];assert result['state']=='saved'
        assert [c[0] for c in calls]==['GET','POST']
        assert client.request('GET','/api/research/'+rid+'/plan-results/'+ref)[0]==200
        assert client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref)[0]==404
        assert client.request('GET','/api/research/'+rid+'/evidence-method-plans')[1]['data']['items']==[]
