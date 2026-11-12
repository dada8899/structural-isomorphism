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
        from research.provider_schemas import canonical,digest
        assert digest(canonical(calls[1][3]))==response['data']['request_digest']
        status,saved=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref);assert status==200,saved
        result=saved['data']['content'];assert saved['data']['content_state']=='available'
        assert result['candidate']==example() and result['real_model_executed'] is False
        assert result['maturity_status']=='candidate_unverified' and result['mathematics_status']=='not_checked'
        assert client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref)==(status,saved)
        assert client.request('GET','/api/research/'+rid+'/plan-results/'+ref)[0]==404
        root=client.request('GET','/api/research/'+rid)[1]['data'];assert root['native_plan_history']==[] and 'native_plan' not in root
        listing=client.request('GET','/api/research/'+rid+'/evidence-method-plans')[1]['data'];assert listing['items']==[saved['data']['metadata']]
        assert flow.run_once(store,tid)['data']['result_ref']==ref and len(calls)==2
        from .test_formal_main_admission import problem,envelope
        updated=problem();updated['original_input']='我新增观察到服务时间变化，同时保留原方法候选作为历史记录。'
        status,revised=client.request('POST','/api/research/'+rid+'/revisions',envelope({'expected_revision':1,'problem':updated}),key='a-current-revision')
        assert status==200,revised
        status,historical=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref);assert status==200,historical
        assert historical['data']['metadata']['is_historical'] is True and historical['data']['content']==result
        assert historical['data']['metadata']['recorded_at']==saved['data']['metadata']['recorded_at']
        assert send(client,rid,'evidence-method-plan-approvals',body,'evidence-confirm')==(200,confirmation)
        assert send(client,rid,'evidence-method-plan-approvals',body,'fresh-key-old-preview')[0]==409
        assert len(calls)==2
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


def _choices(value=None):
    return [{'finish_reason':'stop','message':{'content':json.dumps(example() if value is None else value)}}]


def _reader_grants(store,rid,*,restore=None,held_owner=None):
    from contextlib import nullcontext
    from research.authorization import AuthorizationGate
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    with (nullcontext(held_owner) if held_owner is not None else AuthorizationGate(store).owner_gate(pid)) as lease,store.transaction(write=True) as conn:
        lease.identity
        if restore is not None:
            for key,status in restore:conn.execute('UPDATE research_grants SET status=? WHERE id=?',(status,key))
            return
        rows=conn.execute("SELECT id,status FROM research_grants WHERE research_id=? AND status='active' AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(rid,)).fetchall()
        assert rows
        for key,status in rows:conn.execute("UPDATE research_grants SET status='revoked' WHERE id=?",(key,))
        return [tuple(r) for r in rows]


@pytest.mark.parametrize('phase',['before_balance','balance_claim','after_balance','after_prepare','after_inspect'])
def test_actual_source_withdrawal_at_each_native_stage_never_sends_or_refunds_consumed(tmp_path,monkeypatch,phase):
    with actual(tmp_path) as (service,client,store,actor):
        rid=service.seed.research_id;withdrawn=[]
        def withdraw():withdrawn.extend(_reader_grants(store,rid))
        with provider(choices=_choices(),before_balance=withdraw if phase=='after_balance' else None) as (server,calls),installed(store,actor,server):
            status,response=preview(service,client);assert status==200,response
            (status,confirmed),body=approve(service,client,response['data']);assert status==200,confirmed
            if phase=='before_balance':withdraw()
            elif phase=='balance_claim':
                original=native.ControlledNativeResource.balance
                def after_claim(resource,cap):
                    with store.transaction() as conn:
                        assert conn.execute('SELECT balance_claim FROM research_plan_native_funding').fetchone()[0] is not None
                        assert conn.execute('SELECT admission_json FROM research_plan_native_runs').fetchone()[0] is None
                    withdraw();return original(resource,cap)
                monkeypatch.setattr(native.ControlledNativeResource,'balance',after_claim)
            elif phase=='after_prepare':
                original=native.ControlledNativeResource.prepare_post
                def after_prepare(resource):
                    pending=original(resource);withdraw();return pending
                monkeypatch.setattr(native.ControlledNativeResource,'prepare_post',after_prepare)
            elif phase=='after_inspect':
                original=flow.NativePlanSendLease.inspect_payload
                def after_inspect(cap,resource):
                    descriptor=original(cap,resource)
                    withdrawn.extend(_reader_grants(store,rid,held_owner=cap.lease))
                    return descriptor
                monkeypatch.setattr(flow.NativePlanSendLease,'inspect_payload',after_inspect)
            with pytest.raises((PermissionError,ResearchError)):flow.run_once(store,confirmed['data']['task_id'])
            assert [c[0] for c in calls]==([] if phase in ('before_balance','balance_claim') else ['GET'])
            with store.transaction() as conn:
                run=conn.execute('SELECT * FROM research_plan_native_runs').fetchone();money=conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()
                assert run['state']==('unknown' if phase=='after_inspect' else 'closed')
                assert run['cost_state']==('unknown' if phase=='after_inspect' else 'unreserved')
                assert tuple(money)==((flow.UPPER,0) if phase=='after_inspect' else (0,0))
                assert run['cleanup_state']=='clean' and run['receipt_json'] is None and run['result_json'] is None
            flow.run_once(store,confirmed['data']['task_id']);assert len(calls)==(0 if phase in ('before_balance','balance_claim') else 1)
            _reader_grants(store,rid,restore=withdrawn)
            status,read=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+confirmed['data']['result_ref']);assert status==200,read
            assert read['data']['metadata']['state']==('pending_reconciliation' if phase=='after_inspect' else 'failed_insufficient')


@pytest.mark.parametrize('kind',['invalid','oversize','unknown_usage'])
def test_actual_owned_bad_candidate_keeps_usage_and_unknown_usage_keeps_hold(tmp_path,kind):
    data=example()
    if kind=='oversize':data['summary']='x'*17000
    with actual(tmp_path) as (service,client,store,actor),provider(invalid_body=kind=='invalid',unknown_usage=kind=='unknown_usage',choices=None if kind=='invalid' else _choices(data)) as (server,calls),installed(store,actor,server):
        status,response=preview(service,client);assert status==200,response
        (status,confirmed),_=approve(service,client,response['data']);assert status==200,confirmed
        outcome=flow.run_once(store,confirmed['data']['task_id'])['data'];unknown=kind=='unknown_usage'
        assert outcome['state']==('pending_reconciliation' if unknown else 'failed_insufficient')
        assert [c[0] for c in calls]==['GET','POST']
        with store.transaction() as conn:
            value=conn.execute('SELECT * FROM research_plan_native_runs').fetchone()
            assert value['result_json'] is None and value['receipt_json'] is not None and value['commit_json'] is not None
            assert value['cost_state']==('unknown' if unknown else 'upper_booked')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==((flow.UPPER,0) if unknown else (0,flow.UPPER))
            assert json.loads(value['commit_json'])['result_digest'] is None
        rid=service.seed.research_id;ref=confirmed['data']['result_ref']
        status,read=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+ref);assert status==200,read
        assert read['data']['content_state']=='none' and read['data']['content'] is None
        flow.run_once(store,confirmed['data']['task_id']);assert len(calls)==2


def test_actual_owned_return_after_read_withdrawal_books_fee_only_and_never_revives_body(tmp_path):
    with actual(tmp_path) as (service,client,store,actor):
        rid=service.seed.research_id;withdrawn=[]
        def withdraw():withdrawn.extend(_reader_grants(store,rid))
        with provider(choices=_choices(),before_post=withdraw) as (server,calls),installed(store,actor,server):
            status,response=preview(service,client);assert status==200,response
            (status,confirmed),_=approve(service,client,response['data']);assert status==200,confirmed
            result=flow.run_once(store,confirmed['data']['task_id'])['data'];assert result['state']=='failed_insufficient'
            assert [c[0] for c in calls]==['GET','POST']
            with store.transaction() as conn:
                assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
                assert conn.execute('SELECT result_json FROM research_plan_native_runs').fetchone()[0] is None
            _reader_grants(store,rid,restore=withdrawn)
            status,read=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+confirmed['data']['result_ref']);assert status==200,read
            assert read['data']['content_state']=='none' and read['data']['metadata']['cost_state']=='upper_booked'
            flow.run_once(store,confirmed['data']['task_id']);assert len(calls)==2


@pytest.mark.parametrize('action',['cancel','delete'])
def test_actual_http_stop_after_owned_return_keeps_original_fee_without_late_body(tmp_path,monkeypatch,action):
    with actual(tmp_path) as (service,client,store,actor):
        rid=service.seed.research_id;confirmed=None;actions=[]
        def stop():
            if action=='cancel':result=client.request('POST','/api/research/'+rid+'/cancel',{'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{'task_id':confirmed['task_id'],'expected_task_version':2}},key='a-late-cancel')
            else:
                # This one-shot account erasure may exceed the controller's
                # general 5s read budget. Receive already completed above;
                # retain a finite client-only 10s budget, no retry or change to
                # the native 2s, Source12s or Main shutdown deadlines.
                import urllib.request,urllib.error
                request=urllib.request.Request(service.origin+'/api/me/delete',data=b'{"confirmation":"DELETE"}',method='POST',headers={'Origin':service.origin,'Content-Type':'application/json'})
                try:reply=client.opener.open(request,timeout=10)
                except urllib.error.HTTPError as error:reply=error
                with reply:
                    raw=reply.read(4097);assert len(raw)<=4096
                    result=(reply.status,json.loads(raw))
            actions.append(result[0]);assert result[0]==200,result[1]
        original_commit=flow._commit_return
        def stop_before_original_commit(*args):
            # The real bounded receive and OwnedReturn have already completed;
            # this observed schedule does not extend the transport's deadline.
            owned=args[3]
            assert type(owned) is native.OwnedNativeReturn and owned.active
            stop();return original_commit(*args)
        monkeypatch.setattr(flow,'_commit_return',stop_before_original_commit)
        with provider(choices=_choices()) as (server,calls),installed(store,actor,server):
            status,response=preview(service,client);assert status==200,response
            (status,body),_=approve(service,client,response['data']);assert status==200,body;confirmed=body['data']
            result=flow.run_once(store,confirmed['task_id'])['data'];assert actions==[200] and result['state']=='cancelled'
            with store.transaction() as conn:
                value=conn.execute('SELECT * FROM research_plan_native_runs').fetchone()
                assert value['result_json'] is None and value['cost_state']=='upper_booked'
                assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
            assert [c[0] for c in calls]==['GET','POST']
            if action=='cancel':
                status,read=client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+confirmed['result_ref']);assert status==200,read
                assert read['data']['content_state']=='none'
            else:assert client.request('GET','/api/research/'+rid+'/evidence-method-plans/'+confirmed['result_ref'])[0] in (401,404)


def test_actual_saved_body_and_money_survive_real_close_then_uncertain_receipt(tmp_path,monkeypatch):
    with actual(tmp_path) as (service,client,store,actor),provider(choices=_choices()) as (server,calls),installed(store,actor,server):
        status,response=preview(service,client);assert status==200,response
        (status,confirmed),_=approve(service,client,response['data']);assert status==200,confirmed
        original=native.ControlledNativePending.close
        def close_then_uncertain(pending):
            original(pending)  # Real original socket/registry cleanup occurs.
            raise OSError('owned close receipt uncertainty')
        monkeypatch.setattr(native.ControlledNativePending,'close',close_then_uncertain)
        with pytest.raises(ResearchError) as error:flow.run_once(store,confirmed['data']['task_id'])
        assert error.value.code=='CLEANUP_UNCERTAIN' and [c[0] for c in calls]==['GET','POST']
        with store.transaction() as conn:
            assert conn.execute('SELECT cleanup_state,cost_state FROM research_plan_native_runs').fetchone()[:]==('uncertain','upper_booked')
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,flow.UPPER)
            assert conn.execute('SELECT state FROM research_plan_native_funding').fetchone()[0]=='blocked'
        path='/api/research/'+service.seed.research_id+'/evidence-method-plans/'+confirmed['data']['result_ref']
        status,read=client.request('GET',path);assert status==200,read
        assert read['data']['content_state']=='available' and read['data']['metadata']['cleanup_state']=='uncertain'
        assert client.request('GET',path)==(status,read)
