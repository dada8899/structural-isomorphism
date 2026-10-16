"""Internal CP2 against real auth, saved v2 sources and same DB; offline only."""
from functools import partial
import json
import sqlite3
import time
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from .test_research_persistence import stack,app,login,problem,post
from .test_research_d1_integration import source_stack,start
from .source_http_fixture import ARTICLE,TITLE,source_server,get_local
from .test_research_paid_producers import identity
from .test_research_lifecycle import lifecycle
from research import ResearchStore,ResearchRunner
from research.authorization import AuthorizationGate
from research.source_policy import PinnedPublicTransport
from research.provider_schemas import UsageUpperQuote,Money,BudgetBasisSnapshot,canonical,digest
from research.paid_approval import PaidApprovalService,OfflineFundingResolver,packet_authority,_checked,request_codec_digest
from research.paid_control import mint_current_paid_authority,CurrentPaidAuthority
from research.provider_evidence import read_confirmed_provider_packet
from research.errors import ResearchError
from api import auth


@pytest.fixture
def approved_inputs(source_stack,request):
    client,path,rid=source_stack;store=ResearchStore(auth._store());tid=start(client,rid)
    article=ARTICLE.replace(('Citation: '+TITLE).encode(),('Citation: Example A, Example B (2026) '+TITLE).encode()) if getattr(request,'param',True) else ARTICLE
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=='COMPLETED'
        assert len(calls)==2
    with store.transaction() as conn:
        pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
        ref=conn.execute("SELECT id FROM research_evidence_objects WHERE kind='excerpts'").fetchone()[0]
    quote=UsageUpperQuote(revision=str(uuid4()),peak_input_miss_units_per_million=1,peak_output_units_per_million=2,context_bound=1048576,local_guard=1,
        price_document_digest='a'*64,model_document_digest='b'*64,completion_bound_basis_digest='c'*64,final_request_code_digest=request_codec_digest(),valid_until=int(time.time())+60)
    fid,binding,snapshot=str(uuid4()),str(uuid4()),str(uuid4())
    money=lambda value:Money(currency='CNY',scale=6,amount_units=value)
    basis=BudgetBasisSnapshot(id=snapshot,account_id=fid,provider_binding_id=binding,funding_epoch=1,initial_prepaid=money(1000000),other_use_margin=money(0),cap=money(1000000),settled_actual=money(0),upper_booked=money(0),held=money(0),available_after_observed_consumption=money(1000000),price_revision=quote.revision,valid_until=2000000000)
    # Explicit simulation fixture, not a provision API or real funding evidence.
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,cap,initial_prepaid_units,other_use_margin_units,status,snapshot_id) VALUES(?,?,'live','deepseek','CNY',1000000,1000000,0,'active',?)",(fid,binding,snapshot))
        conn.execute("INSERT INTO research_balance_snapshots(id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off,basis_evidence_digest) VALUES(?,?,1000000,0,0,'2026-10-17T00:00:00.000000Z','2033-01-01T00:00:00.000000Z',1,1,1,?)",(snapshot,fid,digest(canonical(basis.model_dump()))))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,'2033-01-01T00:00:00.000000Z','bounded_usage_upper_v2',?,?)",(quote.revision,fid,canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    resolver=OfflineFundingResolver(principal_id=pid,quote=quote,basis=basis,approved_upper=money(3))
    try:yield client,path,store,rid,pid,ref,resolver
    finally:resolver.close()


def preview(data):
    client,_,store,rid,_,ref,resolver=data
    view=client.get('/api/research/'+rid).json()['data']
    service=PaidApprovalService(store,funding_resolver=resolver)
    return service,service.preview(identity(client),rid,view['current_problem']['revision'],view['research_version'],(ref,))


def test_default_unverified_source_rejects_even_with_synthetic_active_rows(approved_inputs):
    data=approved_inputs;client,_,store,rid,_,ref,_=data
    with pytest.raises(ResearchError) as error:PaidApprovalService(store).preview(identity(client),rid,1,3,(ref,))
    assert error.value.code=='FEATURE_UNAVAILABLE'
    with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_paid_approvals').fetchone()[0]==0


def test_independent_confirmation_packet_and_current_authority_are_offline(approved_inputs):
    client,path,store,rid,pid,ref,resolver=approved_inputs
    service,draft=preview(approved_inputs)
    assert draft['may_send'] is False and draft['excerpts'][0]['may_send_to_provider'] is False
    with store.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'confirm-one')
    assert result['mode']=='offline_probe' and result['may_send'] is False
    assert service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'confirm-one')==result
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        source=packet_authority(conn,store,identity(client),lease,result['approval_ref'])
        packet=read_confirmed_provider_packet(conn,store,identity(client),source)
        assert packet.handles[0].may_send_to_provider and 'Example A, Example B (2026)' in packet.handles[0].attribution
        assert packet.handles[0].quote in packet.handles[0].extracted_text
        assert 'extracted_text' not in json.dumps(packet.outbound())
        cap=mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=1,operation='reserve',approval_ref=result['approval_ref'])
        assert type(cap) is CurrentPaidAuthority and cap.require(conn,'reserve').execution_mode=='offline_probe'
        with pytest.raises(PermissionError):cap.require(conn,'consume')
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_confirmation_packet_port_rejects_plain_objects_and_draft(approved_inputs):
    client,_,store,_,pid,_,_=approved_inputs;service,draft=preview(approved_inputs)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        for obj in (True,{},None):
            with pytest.raises(PermissionError):read_confirmed_provider_packet(conn,store,identity(client),obj)
        with pytest.raises(PermissionError):packet_authority(conn,store,identity(client),lease,draft['preview_ref'])
    with pytest.raises(ResearchError) as error:service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'wrong-version',expected_preview_version=2)
    assert error.value.code=='REVISION_CONFLICT'


@pytest.mark.parametrize('change',['revision','source_retired','quote_mismatch','grant_revoked','other_user'])
def test_stale_or_unprivileged_confirm_does_not_create_paid_grant(approved_inputs,change):
    client,_,store,rid,_,_,resolver=approved_inputs;service,draft=preview(approved_inputs)
    actor=identity(client)
    if change=='revision':
        p=problem();p.update(confirmed=True,summary='修改后必须重新核付费完整输入')
        assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':p}).status_code==200
    elif change=='source_retired':resolver.close()
    elif change=='quote_mismatch':
        with store.transaction(write=True) as conn:conn.execute("UPDATE research_funding_accounts SET status='blocked'")
    elif change=='grant_revoked':
        with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=?",(rid,))
    else:
        with TestClient(app()) as other:login(other,'paid-other@example.test');actor=identity(other)
    with pytest.raises((ResearchError,PermissionError)):service.confirm(actor,draft['preview_ref'],draft['preview_digest'],'reject')
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM research_grants WHERE scopes LIKE '%execute_paid%'").fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0


def test_two_concurrent_confirm_calls_create_only_one_task_and_grant(approved_inputs):
    client,_,store,_,_,_,_=approved_inputs;service,draft=preview(approved_inputs);actor=identity(client)
    def confirm(_):return service.confirm(actor,draft['preview_ref'],draft['preview_digest'],'same-key')
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(confirm,range(2)))
    assert results[0]==results[1]
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM research_tasks WHERE policy_revision='bounded_usage_upper_v2'").fetchone()[0]==1
        assert conn.execute("SELECT count(*) FROM research_grants WHERE scopes LIKE '%execute_paid%'").fetchone()[0]==1


def test_confirmation_failure_rolls_back_whole_paid_creation(approved_inputs):
    client,_,store,_,_,_,_=approved_inputs;service,draft=preview(approved_inputs)
    with store.transaction(write=True) as conn:
        conn.execute("CREATE TRIGGER owned_paid_fault BEFORE UPDATE OF state ON research_paid_approvals WHEN NEW.state='confirmed' BEGIN SELECT RAISE(ABORT,'owned confirmation fault'); END")
    with pytest.raises(sqlite3.IntegrityError):service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'retry-key')
    with store.transaction(write=True) as conn:
        assert conn.execute("SELECT count(*) FROM research_tasks WHERE policy_revision='bounded_usage_upper_v2'").fetchone()[0]==0
        assert conn.execute("SELECT count(*) FROM research_grants WHERE scopes LIKE '%execute_paid%'").fetchone()[0]==0
        assert conn.execute('SELECT state FROM research_paid_approvals').fetchone()[0]=='draft'
        conn.execute('DROP TRIGGER owned_paid_fault')
    assert service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'retry-key')['mode']=='offline_probe'


@pytest.mark.parametrize('approved_inputs',[False],indirect=True)
def test_missing_creator_credit_cannot_be_supplied_by_user_consent(approved_inputs):
    client,_,store,_,_,_,_=approved_inputs
    with pytest.raises(ResearchError) as error:preview(approved_inputs)
    assert error.value.code=='SOURCE_PERMISSION_UNAVAILABLE'
    with pytest.raises(ResearchError):PaidApprovalService(store).confirm(identity(client),str(uuid4()),'a'*64,'bad-credit')
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM research_grants WHERE scopes LIKE '%execute_paid%'").fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_paid_approvals').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0


def test_cancel_delete_and_source_retirement_do_not_restore_paid_body(approved_inputs,lifecycle):
    client,path,store,rid,pid,_,resolver=approved_inputs;service,draft=preview(approved_inputs)
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'one')
    actor=identity(client)
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        consent=packet_authority(conn,store,actor,lease,result['approval_ref'])
        packet=read_confirmed_provider_packet(conn,store,actor,consent)
        cap=mint_current_paid_authority(conn,store=store,lease=lease,identity=actor,context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=1,operation='reserve',approval_ref=result['approval_ref'])
        conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(result['task_id'],))
        with pytest.raises((PermissionError,ResearchError)):cap.require(conn,'reserve')
    deleting,_,_=lifecycle
    response=deleting.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
    assert response.status_code==200,response.text
    with store.transaction() as conn:
        row=conn.execute('SELECT * FROM research_paid_approvals').fetchone()
        assert row['state']=='revoked' and row['payload_json'] is None and row['research_id'] is None
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0


def test_old_policy_unknown_held_blocks_new_paid_confirmation_without_reclassification(approved_inputs):
    client,_,store,rid,_,_,_=approved_inputs;service,draft=preview(approved_inputs)
    fid,price,reservation=str(uuid4()),str(uuid4()),str(uuid4())
    with store.transaction(write=True) as conn:
        task=conn.execute("SELECT id FROM research_tasks WHERE research_id=? AND policy_revision='d1-source-only-v1'",(rid,)).fetchone()[0]
        step=conn.execute('SELECT id FROM research_steps WHERE task_id=? ORDER BY position LIMIT 1',(task,)).fetchone()[0]
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,fixture_port,mode,currency,cap,status) VALUES(?,?,12345,'fixture','USD',10000,'active')",(fid,str(uuid4())))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at) VALUES(?,?,'discover_sources','USD',6,'2099')",(price,fid))
        conn.execute("INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status) VALUES(?,?,?,?,?,?,1,1,'UNKNOWN')",(reservation,fid,task,step,str(uuid4()),price))
        conn.execute('UPDATE research_funding_accounts SET held=1 WHERE id=?',(fid,))
    with pytest.raises(ResearchError) as error:service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'unknown-old')
    assert error.value.code=='RECONCILIATION_REQUIRED'
    with store.transaction() as conn:
        row=conn.execute('SELECT status,policy_revision,max_cost,settled_cost FROM research_reservations WHERE id=?',(reservation,)).fetchone()
        assert tuple(row)==('UNKNOWN','c0-fixture-v1',1,None)
        assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts WHERE id=?',(fid,)).fetchone()[:]==(1,0)
        assert conn.execute("SELECT count(*) FROM research_grants WHERE scopes LIKE '%execute_paid%'").fetchone()[0]==0


@pytest.mark.parametrize('operation',['authorize','consume'])
def test_current_held_permit_authority_checks_db_total_without_double_counting_this_ticket(approved_inputs,operation):
    client,_,store,_,pid,_,_=approved_inputs;service,draft=preview(approved_inputs)
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'prepared')
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        consent=packet_authority(conn,store,identity(client),lease,result['approval_ref'])
        packet=read_confirmed_provider_packet(conn,store,identity(client),consent)
        row=conn.execute('SELECT * FROM research_paid_approvals').fetchone();payload=json.loads(row['payload_json']);funding=payload['funding']
        admission=mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=1,operation='reserve',approval_ref=row['id']).require(conn,'reserve')
        reservation,permit,dispatch=str(uuid4()),str(uuid4()),str(uuid4())
        # Synthetic existing budget preconditions only. No production reserve,
        # consume, F or provider send is implemented by this fixture.
        conn.execute("INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint) VALUES(?,?,?,?,?,?,1,3,'HELD','bounded_usage_upper_v2',?,?,?)",(reservation,row['account_id'],result['task_id'],result['step_id'],str(uuid4()),funding['quote']['revision'],pid,admission.auth_scope_digest,admission.outbound_fingerprint))
        conn.execute("INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,input_digest,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,authorization_context_digest,authorized_task_version,authorized_step_version,paid_approval_ref,admitted_at) VALUES(?,?,?,?,?,'prepared','2033-01-01T00:00:00.000000Z','bounded_usage_upper_v2',?,?,?,?,?,1,2,?,?)",(permit,result['step_id'],reservation,dispatch,packet.context.input_digest,result['request_digest'],result['evidence_digest'],digest(canonical(funding['quote'])),digest(canonical(funding['basis'])),digest(canonical(packet.context.model_dump())),row['id'],int(time.time())))
        conn.execute("UPDATE research_steps SET state='PREPARED',version=2 WHERE id=?",(result['step_id'],))
        conn.execute('UPDATE research_funding_accounts SET held=cap WHERE id=?',(row['account_id'],))
        cap=mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=2,operation=operation,approval_ref=row['id'])
        assert cap.require(conn,operation).execution_mode=='offline_probe'
        conn.execute("UPDATE research_dispatch_permits SET state='consumed' WHERE id=?",(permit,))
        with pytest.raises(PermissionError):cap.require(conn,operation)


def test_confirmation_replay_reads_original_task_current_view_not_newer_task(approved_inputs):
    client,_,store,rid,_,_,_=approved_inputs;service,draft=preview(approved_inputs)
    first=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'original')
    assert first['execution']=='QUEUED' and first['status']=='queued'
    stopped=post(client,'/api/research/'+rid+'/cancel',{'task_id':first['task_id'],'expected_task_version':first['task_version']})
    assert stopped.status_code==200,stopped.text
    _,again=preview(approved_inputs)
    second=service.confirm(identity(client),again['preview_ref'],again['preview_digest'],'next')
    assert second['task_id']!=first['task_id'] and second['execution']=='QUEUED'
    replay=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'original')
    assert replay['task_id']==first['task_id'] and replay['approval_ref']==first['approval_ref']
    assert replay['execution']=='CANCELLED' and replay['status']=='cancelled'


@pytest.mark.parametrize('operation',['authorize','consume'])
@pytest.mark.parametrize('changed',['authorized_task_version','authorized_step_version'])
def test_stale_persisted_permit_versions_reject_current_caller_versions(approved_inputs,operation,changed):
    client,_,store,_,pid,_,_=approved_inputs;service,draft=preview(approved_inputs)
    result=service.confirm(identity(client),draft['preview_ref'],draft['preview_digest'],'prepared-version')
    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
        consent=packet_authority(conn,store,identity(client),lease,result['approval_ref'])
        packet=read_confirmed_provider_packet(conn,store,identity(client),consent)
        row=conn.execute('SELECT * FROM research_paid_approvals').fetchone();funding=json.loads(row['payload_json'])['funding']
        admission=mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=1,operation='reserve',approval_ref=row['id']).require(conn,'reserve')
        reservation,permit,dispatch=str(uuid4()),str(uuid4()),str(uuid4())
        conn.execute("INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint) VALUES(?,?,?,?,?,?,1,3,'HELD','bounded_usage_upper_v2',?,?,?)",(reservation,row['account_id'],result['task_id'],result['step_id'],str(uuid4()),funding['quote']['revision'],pid,admission.auth_scope_digest,admission.outbound_fingerprint))
        conn.execute("INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,input_digest,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,authorization_context_digest,authorized_task_version,authorized_step_version,paid_approval_ref,admitted_at) VALUES(?,?,?,?,?,'prepared','2033-01-01T00:00:00.000000Z','bounded_usage_upper_v2',?,?,?,?,?,1,2,?,?)",(permit,result['step_id'],reservation,dispatch,packet.context.input_digest,result['request_digest'],result['evidence_digest'],digest(canonical(funding['quote'])),digest(canonical(funding['basis'])),digest(canonical(packet.context.model_dump())),row['id'],int(time.time())))
        conn.execute("UPDATE research_steps SET state='PREPARED',version=2 WHERE id=?",(result['step_id'],))
        conn.execute('UPDATE research_funding_accounts SET held=cap WHERE id=?',(row['account_id'],))
        def mint():return mint_current_paid_authority(conn,store=store,lease=lease,identity=identity(client),context=packet.context,step_id=result['step_id'],expected_task_version=1,expected_step_version=2,operation=operation,approval_ref=row['id'])
        cap=mint();assert cap.require(conn,operation)
        conn.execute('UPDATE research_dispatch_permits SET '+changed+'=99 WHERE id=?',(permit,))
        with pytest.raises(PermissionError):cap.require(conn,operation)
        with pytest.raises(PermissionError):mint()
