"""Real offline budget lifecycle. No synthetic consumed rows or real fees."""
from contextlib import contextmanager
from uuid import uuid4
import multiprocessing
from pathlib import Path
import sqlite3
import os

import pytest

from .test_research_persistence import stack,post
from web.backend.tests.research_process_fixture import _observe_child, _reserve_child, _die_after_committed_consumption
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api,make_preview,confirm_data
from .test_research_paid_producers import identity
from .test_research_owned_return import tcp_reply,response_body
from .test_research_lifecycle import lifecycle
from research.authorization import AuthorizationGate
from research.financial_guard import OfflineProjectRegistration
from research.provider_schemas import Money
from research.paid_provider_session import BudgetedOwnedSession,persist_budget_return
from research import paid_budget as ledger
from research import ResearchStore,BudgetLedger
from research.errors import ResearchError


@contextmanager
def execution(data,*,body=None,cap=10):
    client,_,store,rid,_,resolver=data
    actor=identity(client)
    draft=make_preview(data)
    response=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'real-budget-confirm')
    assert response.status_code==200,response.text
    confirmation=response.json()['data']
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=cap),authorization_ref=str(uuid4()))
    session=None
    try:
        with tcp_reply(response_body() if body is None else body) as (factory,state):
            def preconnect(deadline):
                with store.transaction() as conn:
                    assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='HELD'
                    assert conn.execute('SELECT state FROM research_dispatch_permits').fetchone()[0]=='prepared'
                    assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==0
                return factory(deadline)
            session=BudgetedOwnedSession.offline_start(store,actor,source,confirmation['approval_ref'],connection_factory=preconnect)
            yield session,confirmation,state,pid
    finally:
        if session is not None:session.close()
        source.close()


def test_actual_reserve_consume_owned_finish_persist_observe_once(paid_api):
    store=paid_api[2]
    with execution(paid_api) as (session,confirmation,state,pid):
        with store.transaction() as conn:
            assert conn.execute('SELECT state FROM research_dispatch_permits').fetchone()[0]=='consumed'
            assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==1
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            result=ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)
            assert result['reserved_upper']==3 and result['booked_upper']==2 and result['released_reserve_difference']==1
            assert result['actual_charge'] is None
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)==result
            assert persist_budget_return(conn,store=store,lease=lease,receipt=receipt)==ref
        assert state['requests']==1
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,2,0)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
            assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]


@pytest.mark.parametrize('body',[response_body(usage=None),b'{',response_body(usage={'prompt_tokens':True})],ids=['missing','bad-json','bool-usage'])
def test_unknown_usage_preserves_entire_hold_and_never_resends(paid_api,body):
    store=paid_api[2]
    with execution(paid_api,body=body) as (session,_,state,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['kind']=='unknown'
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        assert state['requests']==1


def test_bad_candidate_with_complete_usage_books_upper_independently(paid_api):
    store=paid_api[2]
    with execution(paid_api,body=response_body(choices=[])) as (session,_,state,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
            assert conn.execute('SELECT candidate_json FROM research_provider_sessions').fetchone()[0] is None
        assert state['requests']==1


@pytest.mark.parametrize('ending',['cancel','revoke','delete'])
@pytest.mark.parametrize('before_receive',[True,False])
def test_financial_late_return_never_reads_erased_private_approval_or_revives_content(paid_api,lifecycle,ending,before_receive):
    client,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,result,state,pid):
        receipt=None if before_receive else session.receive()
        if ending=='delete':
            response=lifecycle[0].post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
            assert response.status_code==200,response.text
        else:
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                if ending!='cancel':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
            if ending=='cancel':
                response=post(client,f'/api/research/{paid_api[3]}/cancel',{'task_id':result['task_id'],'expected_task_version':2},'late-real-http-cancel')
                assert response.status_code==200,response.text
        receipt=receipt or session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
            assert conn.execute('SELECT candidate_json FROM research_provider_sessions').fetchone()[0] is None
            assert conn.execute('SELECT execution FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()[0]!='RUNNING'
            if ending=='delete':assert conn.execute('SELECT payload_json FROM research_paid_approvals').fetchone()[0] is None
        assert state['requests']==1




def test_two_fresh_processes_observe_durable_return_once_without_owned_memory(paid_api):
    _,path,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,state,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        session.close()
        ctx=multiprocessing.get_context('spawn');ready,result=ctx.Queue(),ctx.Queue();go=ctx.Event()
        workers=[ctx.Process(target=_observe_child,args=(str(path),pid,ref,ready,go,result)) for _ in range(2)]
        try:
            for worker in workers:worker.start()
            assert ready.get(timeout=15) and ready.get(timeout=15);go.set()
            values=[result.get(timeout=15),result.get(timeout=15)]
            assert values[0]==values[1] and values[0][1]==2
            for worker in workers:worker.join(10);assert worker.exitcode==0
        finally:
            for worker in workers:
                if worker.is_alive():worker.terminate();worker.join(3)
                worker.close()
            for queue in (ready,result):queue.close();queue.join_thread()
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(0,2,0)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
        assert state['requests']==1


def test_missing_first_durable_return_stays_unknown_and_cannot_mint(paid_api):
    store=paid_api[2]
    with execution(paid_api) as (session,_,_,pid):
        session.receive();session.close()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):ledger.mint_cost_from_return(conn,store=store,lease=lease,return_ref=session.id)
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==3


def test_old_c0_cannot_settle_or_release_v2_reservation(paid_api,monkeypatch):
    monkeypatch.setenv('STRUCTURAL_C0_ENABLED','true');store=paid_api[2]
    with execution(paid_api) as (session,result,_,pid):
        with store.transaction(write=True) as conn:
            step=conn.execute('SELECT * FROM research_steps WHERE id=?',(session.snapshot.dispatch.step_id,)).fetchone()
            task=conn.execute('SELECT * FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()
            for action in (lambda:BudgetLedger.reserve_in(conn,task,step),lambda:BudgetLedger.dispatch_in(conn,step),lambda:BudgetLedger.unknown_in(conn,step['id'])):
                with pytest.raises(ResearchError):action()
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==3


@pytest.mark.parametrize('marker',[
    'INSERT INTO research_reservations(', 'INSERT INTO research_dispatch_permits(', 'INSERT INTO research_provider_sessions(',
    "UPDATE research_dispatch_permits SET state='consumed'", "UPDATE research_reservations SET status='SENT'",
    "UPDATE research_paid_approvals SET state='consumed'",'INSERT INTO research_financial_admissions'])
def test_real_reserve_consume_sql_faults_never_send_or_partially_admit(paid_api,monkeypatch,marker):
    connect=sqlite3.connect;hits=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            value=super().execute(sql,*args,**kwargs)
            if sql.startswith(marker) and not hits:hits.append(True);raise sqlite3.OperationalError('owned budget boundary fault')
            return value
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
        with pytest.raises(ResearchError):
            with execution(paid_api):pytest.fail('faulted consumption sent')
    with paid_api[2].transaction() as conn:
        assert hits and conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        if marker.startswith('INSERT INTO research_') and 'financial_admissions' not in marker:
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==0
        else:
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==3
            assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='HELD'


def test_real_commit_with_lost_ack_has_no_begin_and_stays_full_held(paid_api,monkeypatch):
    connect=sqlite3.connect;hit=[]
    class AckLoss(sqlite3.Connection):
        consumed=False
        def execute(self,sql,*args,**kwargs):
            value=super().execute(sql,*args,**kwargs)
            if sql.startswith("UPDATE research_paid_approvals SET state='consumed'"):self.consumed=True
            return value
        def commit(self):
            value=super().commit()
            if self.consumed and not hit:hit.append(True);raise sqlite3.OperationalError('owned commit ack loss')
            return value
    begins=[]
    from research.provider_adapter import OfflineOwnedTransport
    original=OfflineOwnedTransport.begin
    def count_begin(*args,**kwargs):begins.append(True);return original(*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=AckLoss,**k))
        patch.setattr(OfflineOwnedTransport,'begin',count_begin)
        with pytest.raises(ResearchError):
            with execution(paid_api):pytest.fail('unknown commit acknowledgment sent')
    with paid_api[2].transaction() as conn:
        assert hit and begins==[]
        assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==1
        assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
        assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==3
        assert conn.execute('SELECT financial_return_json FROM research_provider_sessions').fetchone()[0] is None


@pytest.mark.parametrize('marker',['INSERT INTO research_cost_observations',"UPDATE research_reservations SET status='UPPER_BOOKED'",'UPDATE research_funding_accounts SET held=held-'])
def test_observe_fault_rolls_back_entire_reestimate_and_retry_uses_same_return(paid_api,monkeypatch,marker):
    store=paid_api[2];connect=sqlite3.connect;hits=[]
    class Fault(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            value=super().execute(sql,*args,**kwargs)
            if sql.startswith(marker) and not hits:hits.append(True);raise sqlite3.OperationalError('owned observe fault')
            return value
    with execution(paid_api) as (session,_,state,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        with AuthorizationGate(store).owner_gate(pid) as lease:
            with monkeypatch.context() as patch:
                patch.setattr(sqlite3,'connect',lambda *a,**k:connect(*a,**k) if 'factory' in k else connect(*a,factory=Fault,**k))
                with pytest.raises(ResearchError):
                    with store.transaction(write=True) as conn:ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)
            with store.transaction(write=True) as conn:
                assert hits and tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(3,0)
                assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
                assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
        assert state['requests']==1


def test_cached_sql_and_plain_rows_do_not_gain_financial_write_permission(paid_api):
    store=paid_api[2]
    with execution(paid_api) as (session,_,_,pid):
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            r=conn.execute('SELECT * FROM research_reservations').fetchone()
            ledger.unknown_in(conn,r['id'],store=store,lease=lease)
            # Exact previously authorized SQL must be recompiled with the
            # same transaction observer after the private write scope exits.
            sql="UPDATE research_reservations SET status='UNKNOWN',version=version+1 WHERE id=? AND status='SENT' AND version=?"
            with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,(r['id'],r['version']))
            with pytest.raises(sqlite3.DatabaseError):conn.execute("UPDATE research_dispatch_permits SET state='prepared'")
            with pytest.raises(TypeError):ledger.BudgetPreparation()
            with pytest.raises(PermissionError):ledger.consume_in(conn,{},lease)
        with store.auth_store._connection() as raw:
            with pytest.raises(sqlite3.DatabaseError):raw.execute("UPDATE research_dispatch_permits SET state='prepared'")




def test_two_processes_different_tasks_share_project_limit_without_new_allowances(paid_api):
    from functools import partial
    from web.backend.tests.source_http_fixture import source_server,get_local,ARTICLE,TITLE
    from .test_research_d1_integration import start
    from .test_research_persistence import problem
    from research import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    client,_,store,rid,excerpt,resolver=paid_api
    actor=identity(client)
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    data=problem('second actual source research');data['confirmed']=True
    second=post(client,'/api/research',{'problem':data},'second-budget-research').json()['data']['research']['id']
    task=start(client,second)
    article=ARTICLE.replace(('Citation: '+TITLE).encode(),('Citation: Example A, Example B (2026) '+TITLE).encode())
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(task)=='COMPLETED'
        assert len(calls)==2
    with store.transaction() as conn:second_excerpt=conn.execute("SELECT id FROM research_evidence_objects WHERE research_id=? AND kind='excerpts'",(second,)).fetchone()[0]
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=3),authorization_ref=str(uuid4()))
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ledger.activate_offline_in(conn,store=store,actor=actor,lease=lease,source=source)
        ctx=multiprocessing.get_context('spawn');ready,results=ctx.Queue(),ctx.Queue();go=ctx.Event()
        workers=[ctx.Process(target=_reserve_child,args=(client.cookies.get('phase_session'),research,ref,pid,
            resolver._quote.model_dump(),resolver._basis.model_dump(),source._reference,3,ready,go,results)) for research,ref in ((rid,excerpt),(second,second_excerpt))]
        try:
            for worker in workers:worker.start()
            assert ready.get(timeout=15) and ready.get(timeout=15);go.set()
            observed=[results.get(timeout=15),results.get(timeout=15)]
            assert sorted(item[0] for item in observed)==['BUDGET_EXHAUSTED','held']
            for worker in workers:worker.join(10);assert worker.exitcode==0
        finally:
            for worker in workers:
                if worker.is_alive():worker.terminate();worker.join(3)
                worker.close()
            for queue in (ready,results):queue.close();queue.join_thread()
        with store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==1
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
            assert conn.execute('SELECT count(*) FROM research_dispatch_permits WHERE state=\'consumed\'').fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM research_project_budgets').fetchone()[0]==1
    finally:source.close()




@pytest.mark.parametrize('cut',['before-begin','after-receive'])
def test_actual_process_death_after_commit_without_return_cannot_restore_receipt_or_send(paid_api,cut):
    client,path,store,rid,excerpt,resolver=paid_api
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    worker=multiprocessing.get_context('spawn').Process(target=_die_after_committed_consumption,
        args=(client.cookies.get('phase_session'),rid,excerpt,pid,resolver._quote.model_dump(),resolver._basis.model_dump(),cut))
    worker.start()
    try:worker.join(15);assert not worker.is_alive() and worker.exitcode==(73 if cut=='before-begin' else 74)
    finally:
        if worker.is_alive():worker.terminate();worker.join(3)
        worker.close()
    reopened=ResearchStore(store.auth_store)
    with AuthorizationGate(reopened).owner_gate(pid) as lease,reopened.transaction(write=True) as conn:
        ref=conn.execute('SELECT session_id FROM research_financial_admissions').fetchone()[0]
        assert conn.execute('SELECT financial_return_json FROM research_provider_sessions').fetchone()[0] is None
        assert ledger.observe_in(conn,store=reopened,lease=lease,return_ref=ref)['kind']=='unknown'
        assert conn.execute('SELECT status FROM research_reservations').fetchone()[0]=='UNKNOWN'
        assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0


@pytest.mark.parametrize('floor',['cash-cap','balance'])
def test_fresh_cash_and_balance_floors_are_independent_of_larger_project_cap(paid_api,monkeypatch,floor):
    import time
    from datetime import datetime,timezone
    from research.paid_approval import OfflineFundingResolver
    from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,canonical,digest
    from research.usage_upper import preview_bound
    client,_,store,_,_,original=paid_api;now=int(time.time())
    quote=UsageUpperQuote.model_validate(original._quote.model_dump()|{'revision':str(uuid4()),'valid_until':now+60,
        'peak_input_miss_units_per_million':1000000 if floor=='cash-cap' else 1})
    value=original._basis.model_dump();sid=str(uuid4());value.update(id=sid,price_revision=quote.revision)
    if floor=='balance':value['available_after_observed_consumption']['amount_units']=1
    basis=BudgetBasisSnapshot.model_validate(value)
    expires=datetime.fromtimestamp(now+3600,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO research_balance_snapshots(id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off,basis_evidence_digest) VALUES(?,?,?,0,0,?,?,1,1,1,?)",
            (sid,basis.account_id,1 if floor=='balance' else 1000000,datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),expires,digest(canonical(basis.model_dump()))))
        conn.execute('UPDATE research_funding_accounts SET snapshot_id=? WHERE id=?',(sid,basis.account_id))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,?,'bounded_usage_upper_v2',?,?)",
            (quote.revision,basis.account_id,expires,canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    resolver=OfflineFundingResolver(principal_id=original._pid,quote=quote,basis=basis,approved_upper=preview_bound(quote,now=now).upper_bound)
    monkeypatch.setattr(client.app.state,'research_paid_resolver',resolver)
    data=(*paid_api[:5],resolver)
    try:
        with pytest.raises(ResearchError) as caught:
            with execution(data,cap=5000000):pytest.fail('funding floor bypassed')
        assert caught.value.code=='BUDGET_EXHAUSTED'
        with store.transaction() as conn:
            assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==0
    finally:resolver.close()


def _another_confirmed_paid_research(data,label):
    from functools import partial
    from web.backend.tests.source_http_fixture import source_server,get_local,ARTICLE,TITLE
    from .test_research_d1_integration import start
    from .test_research_persistence import problem
    from research import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    client,_,store,_,_,resolver=data
    body=problem(label);body.update(confirmed=True,summary='另一个已确认的合成研究问题')
    rid=post(client,'/api/research',{'problem':body},label+'-create').json()['data']['research']['id']
    task=start(client,rid)
    article=ARTICLE.replace(('Citation: '+TITLE).encode(),('Citation: Example A, Example B (2026) '+TITLE).encode())
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(task)=='COMPLETED'
        assert calls==['/discovery','/article']
    with store.transaction() as conn:excerpt=conn.execute("SELECT id FROM research_evidence_objects WHERE research_id=? AND kind='excerpts'",(rid,)).fetchone()[0]
    new_data=(client,data[1],store,rid,excerpt,resolver)
    draft=make_preview(new_data,label+'-preview')
    result=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),label+'-confirm')
    assert result.status_code==200,result.text
    return result.json()['data']


@pytest.mark.parametrize('first_unknown',[False,True])
def test_account_unknown_blocks_a_different_research_before_any_second_connection(paid_api,first_unknown):
    from contextlib import nullcontext
    store=paid_api[2]
    with execution(paid_api,body=response_body(usage=None) if first_unknown else response_body(),cap=10) as (first,_,wire,pid):
        receipt=first.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['kind']==('unknown' if first_unknown else 'estimated_upper')
        second=_another_confirmed_paid_research(paid_api,'independent-after-first')
        with tcp_reply(response_body()) as (factory,second_wire):
            connects=[]
            def count(deadline):connects.append(True);return factory(deadline)
            expectation=pytest.raises(ResearchError,match='RECONCILIATION_REQUIRED') if first_unknown else nullcontext()
            with expectation:
                with BudgetedOwnedSession.offline_start(store,identity(paid_api[0]),first.proof.source,second['approval_ref'],connection_factory=count) as session:
                    receipt=session.receive()
                    with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                        ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
                        assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
            assert len(connects)==(0 if first_unknown else 1) and second_wire['requests']==(0 if first_unknown else 1)
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==((3,0) if first_unknown else (0,4))
        assert wire['requests']==1


def test_already_reserved_task_cannot_authorize_or_consume_after_account_becomes_unknown_but_late_observe_works(paid_api):
    client,_,store,_,_,_=paid_api
    with execution(paid_api,cap=10) as (first,_,wire,pid):
        receipt=first.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        second=_another_confirmed_paid_research(paid_api,'reserved-before-unknown')
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            proof=ledger.reserve_in(conn,store=store,actor=identity(client),lease=lease,source=first.proof.source,approval_ref=second['approval_ref'])
            assert conn.execute('SELECT held FROM research_funding_accounts').fetchone()[0]==6
            ledger.unknown_in(conn,first.proof.reservation,store=store,lease=lease)
        try:
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                for method in (ledger.authorize_in,ledger.consume_in):
                    with pytest.raises(ResearchError,match='RECONCILIATION_REQUIRED'):method(conn,proof,lease)
                assert conn.execute('SELECT state FROM research_dispatch_permits WHERE id=?',(proof.permit,)).fetchone()[0]=='prepared'
                assert conn.execute('SELECT count(*) FROM research_financial_admissions').fetchone()[0]==1
            # The original durable valid return may still be financially
            # observed late without reopening admission for another send.
            with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
                assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
                assert ledger.authorize_in(conn,proof,lease)
                assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(3,2)
        finally:
            ledger._PREPARED.pop(proof.session,None);object.__setattr__(proof,'_active',False)
        assert wire['requests']==1


@pytest.mark.parametrize('status',['active','blocked','closed'])
def test_registered_project_pause_keeps_real_tickets_and_cached_writes_protected_and_allows_late_financial_observe(paid_api,status):
    store=paid_api[2]
    with execution(paid_api) as (session,_,wire,pid):
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            project=conn.execute('SELECT * FROM research_project_budgets').fetchone()
            ledger._write(conn,lease,'project-update','','research_project_budgets',1,
                'UPDATE research_project_budgets SET status=?,version=version+1 WHERE id=1 AND version=?',(status,project['version']))
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            sql='UPDATE research_dispatch_permits SET state=state WHERE id=?'
            ledger._write(conn,lease,'ticket-noop',session.proof.permit,'research_dispatch_permits',session.proof.permit,sql,(session.proof.permit,))
            with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,(session.proof.permit,))
            with pytest.raises(sqlite3.DatabaseError):conn.execute("UPDATE research_dispatch_permits SET state='prepared' WHERE id=?",(session.proof.permit,))
            assert conn.execute('SELECT state FROM research_dispatch_permits').fetchone()[0]=='consumed'
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
        assert wire['requests']==1


def test_first_closed_registration_protects_rows_in_the_same_existing_transaction(paid_api):
    from research.financial_guard import register_closed_project
    client,_,store,rid,_,resolver=paid_api
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    source=OfflineProjectRegistration(store=store,identity=identity(client),principal_id=pid,funding_resolver=resolver,
        authorized_cap=Money(currency='CNY',scale=6,amount_units=10),authorization_ref=str(uuid4()))
    try:
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            assert not conn.execute('SELECT 1 FROM research_project_budgets').fetchone()
            # Compile an innocuous empty-table write before registration.
            sql="UPDATE research_dispatch_permits SET state='prepared'"
            conn.execute(sql)
            register_closed_project(conn,store=store,identity=identity(client),lease=lease,source=source)
            with pytest.raises(sqlite3.DatabaseError):conn.execute(sql)
        with store.transaction(write=True) as conn:
            with pytest.raises(sqlite3.DatabaseError):conn.execute("UPDATE research_dispatch_permits SET state='prepared'")
    finally:source.close()


@pytest.mark.parametrize('status',['active','blocked','closed'])
def test_free_source_workflow_coexists_after_project_registration_without_touching_money(paid_api,status):
    from functools import partial
    from web.backend.tests.source_http_fixture import source_server,get_local
    from .test_research_persistence import problem
    from .test_research_d1_integration import start
    from research import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    client,_,store,_,_,_=paid_api
    with execution(paid_api) as (session,_,paid_wire,pid):
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            version=conn.execute('SELECT version FROM research_project_budgets').fetchone()[0]
            ledger._write(conn,lease,'project-update','','research_project_budgets',1,
                'UPDATE research_project_budgets SET status=?,version=version+1 WHERE id=1 AND version=?',(status,version))
            money=tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())
            assert money==(3,0,0)
        data=problem('free Source independent of registered paid budget');data['confirmed']=True
        created=post(client,'/api/research',{'problem':data},'coexist-create')
        assert created.status_code==200,created.text
        rid=created.json()['data']['research']['id'];task=start(client,rid)
        with source_server() as (port,calls):
            runner=ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
            assert runner.run_once(task)=='COMPLETED'
            assert runner.run_once(task)=='COMPLETED'
            assert calls==['/discovery','/article']
        with store.transaction() as conn:
            assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==money
            assert conn.execute('SELECT count(*) FROM research_reservations WHERE task_id=?',(task,)).fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM research_dispatch_permits p JOIN research_steps s ON p.step_id=s.id WHERE s.task_id=?',(task,)).fetchone()[0]==0
            assert conn.execute("SELECT count(*) FROM research_source_requests WHERE task_id=? AND outcome='SUCCEEDED'",(task,)).fetchone()[0]==2
        view=client.get(f'/api/research/{rid}').json()['data']
        assert view['source_quota']['used']==2 and view['evidence']=='INSUFFICIENT' and view['model_analysis_ran'] is False
        for kind in ('sources','excerpts','claims','reports'):
            response=client.get(f'/api/research/{rid}/records',params={'task_id':task,'kind':kind})
            assert response.status_code==200 and len(response.json()['data']['items'])==1
        assert paid_wire['requests']==1


@pytest.mark.parametrize('status',['blocked','closed'])
def test_paused_execution_cannot_be_automatically_reactivated_by_original_offline_source(paid_api,status):
    store=paid_api[2]
    with execution(paid_api) as (first,_,wire,pid):
        receipt=first.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            ref=persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            assert ledger.observe_in(conn,store=store,lease=lease,return_ref=ref)['booked_upper']==2
            version=conn.execute('SELECT version FROM research_project_budgets').fetchone()[0]
            ledger._write(conn,lease,'project-update','','research_project_budgets',1,
                'UPDATE research_project_budgets SET status=?,version=version+1 WHERE id=1 AND version=?',(status,version))
        second=_another_confirmed_paid_research(paid_api,'after-project-pause')
        connections=[]
        def forbidden(deadline):connections.append(True);pytest.fail('paused project connected')
        with pytest.raises(PermissionError):BudgetedOwnedSession.offline_start(store,identity(paid_api[0]),first.proof.source,
            second['approval_ref'],connection_factory=forbidden)
        with store.transaction() as conn:
            assert conn.execute('SELECT status FROM research_project_budgets').fetchone()[0]==status
            assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==1
            assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone())==(0,2)
        assert connections==[] and wire['requests']==1
