"""Real owned TCP reception over explicitly synthetic offline budget rows.

This is not reserve/consume implementation, actual funding or a model run.
"""
from contextlib import contextmanager
import json
import pickle
import socket
import sqlite3
import threading
import time
from uuid import uuid4

import pytest

from .test_research_persistence import stack,post
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs,preview,identity
from .test_research_lifecycle import lifecycle
from research.authorization import AuthorizationGate
from research.paid_approval import packet_authority
from research.paid_control import mint_current_paid_authority,persist_offline_owned_source,mint_trusted_cost_authority
from research.paid_provider_session import OwnedProviderSession,OwnedReturnReceipt
from research.provider_evidence import read_confirmed_provider_packet
from research.provider_schemas import canonical,digest,MODEL
from research.errors import ResearchError


def response_body(**updates):
    candidate={'summary':'Offline candidate requiring a real experiment.','mechanisms':[],
        'competing_explanations':['A common shock remains possible.'],
        'validation_plan':{'measurement':'Measure the delay.','outcome':'Compare the baseline.',
            'falsification':'Reject equivalent performance.','stop_rule':'Stop at the sample limit.'},
        'gaps':['No real model or research result.']}
    result={'model':MODEL,'object':'chat.completion','id':'offline-owned-return','choices':[{'index':0,'finish_reason':'stop',
        'message':{'role':'assistant','content':json.dumps(candidate)}}],
        'usage':{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120,
            'prompt_cache_hit_tokens':10,'prompt_cache_miss_tokens':90}}
    result.update(updates)
    return canonical(result)


@contextmanager
def tcp_reply(body,*,truncated=False):
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(1);listener.settimeout(2)
    address=listener.getsockname();state={'requests':0,'body':None,'closed':False}
    def serve():
        conn=None
        try:
            conn,_=listener.accept();conn.settimeout(2);raw=b''
            while b'\r\n\r\n' not in raw:
                part=conn.recv(4096)
                if not part:raise ValueError('closed request')
                raw+=part
                if len(raw)>20000:raise ValueError('request cap')
            headers,incoming=raw.split(b'\r\n\r\n',1)
            size=int(next(line.split(b':',1)[1] for line in headers.split(b'\r\n') if line.lower().startswith(b'content-length:')))
            assert 0<size<=16384
            while len(incoming)<size:
                part=conn.recv(size-len(incoming))
                if not part:raise ValueError('closed body')
                incoming+=part
            state['body']=incoming;state['requests']+=1
            conn.sendall((f'HTTP/1.1 200 Probe\r\nContent-Type: application/json\r\nContent-Length: {len(body)+(10 if truncated else 0)}\r\nConnection: close\r\n\r\n').encode()+body)
        except (OSError,ValueError):pass
        finally:
            if conn is not None:conn.close()
            state['closed']=True
    thread=threading.Thread(target=serve);thread.start()
    try:yield lambda deadline:socket.create_connection(address,timeout=deadline.remaining()),state
    finally:
        listener.close();thread.join(3)
        assert not thread.is_alive()


@contextmanager
def owned_probe(data,body=None,*,truncated=False,stale=None,change_after_connect=False):
    client,_,store,_,pid,_,_=data;actor=identity(client);service,draft=preview(data)
    result=service.confirm(actor,draft['preview_ref'],draft['preview_digest'],'owned-reception')
    with tcp_reply(response_body() if body is None else body,truncated=truncated) as (factory,state):
        with AuthorizationGate(store).owner_gate(pid) as lease:
            with store.transaction(write=True) as conn:
                packet=read_confirmed_provider_packet(conn,store,actor,packet_authority(conn,store,actor,lease,result['approval_ref']))
                row=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(result['approval_ref'],)).fetchone()
                funding=json.loads(row['payload_json'])['funding']
                admission=mint_current_paid_authority(conn,store=store,lease=lease,identity=actor,context=packet.context,
                    step_id=result['step_id'],expected_task_version=1,expected_step_version=1,operation='reserve',approval_ref=row['id']).require(conn,'reserve')
                reservation,permit,dispatch=str(uuid4()),str(uuid4()),str(uuid4())
                # Isolated synthetic already-consumed preconditions only.
                conn.execute("INSERT INTO research_reservations(id,account_id,task_id,step_id,operation_key,price_revision,funding_epoch,max_cost,status,policy_revision,principal_id,auth_scope_digest,outbound_fingerprint) VALUES(?,?,?,?,?,?,1,3,'SENT','bounded_usage_upper_v2',?,?,?)",
                    (reservation,row['account_id'],result['task_id'],result['step_id'],str(uuid4()),funding['quote']['revision'],pid,admission.auth_scope_digest,admission.outbound_fingerprint))
                conn.execute("INSERT INTO research_dispatch_permits(id,step_id,reservation_id,dispatch_id,input_digest,state,expires_at,policy_revision,request_digest,evidence_digest,price_digest,budget_basis_digest,authorization_context_digest,authorized_task_version,authorized_step_version,paid_approval_ref,admitted_at,gate_identity_json) VALUES(?,?,?,?,?,'consumed','2033-01-01T00:00:00.000000Z','bounded_usage_upper_v2',?,?,?,?,?,1,1,?,?,?)",
                    (permit,result['step_id'],reservation,dispatch,packet.context.input_digest,result['request_digest'],result['evidence_digest'],digest(canonical(funding['quote'])),digest(canonical(funding['basis'])),digest(canonical(packet.context.model_dump())),row['id'],int(time.time()),canonical(lease.identity).decode()))
                conn.execute('UPDATE research_funding_accounts SET held=3 WHERE id=?',(row['account_id'],))
                if stale:conn.execute('UPDATE research_dispatch_permits SET '+stale+'=99 WHERE id=?',(permit,))
            def connect(deadline):
                sock=factory(deadline)
                if change_after_connect:
                    with store.transaction(write=True) as conn:conn.execute('UPDATE research_tasks SET version=version+1 WHERE id=?',(result['task_id'],))
                return sock
            session=OwnedProviderSession.offline_probe(store,actor,lease,result['approval_ref'],permit,connection_factory=connect)
        try:yield session,result,state
        finally:session.close()


def saved(store):
    with store.transaction() as conn:
        row=dict(conn.execute('SELECT * FROM research_provider_sessions').fetchone())
        assert tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone())==(3,0,0)
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        return row


def test_real_owned_finish_first_return_and_idempotent_replay(approved_inputs):
    store=approved_inputs[2]
    with owned_probe(approved_inputs) as (session,result,state):
        receipt=session.receive()
        with store.transaction(write=True) as conn:
            first=persist_offline_owned_source(conn,receipt)
            assert persist_offline_owned_source(conn,receipt)==first
        row=saved(store);financial=json.loads(row['financial_return_json'])
        assert row['state']=='received' and row['candidate_json']
        assert financial['transport']['usage']['total_tokens']==120
        assert financial['actual_charge'] is None and financial['model_analysis_ran'] is False
        assert financial['financial_consumer_enabled'] is False and first['execution_mode']=='offline_probe'
        assert 'candidate' not in financial['transport'] and 'context' not in financial['transport']
        assert 'Offline candidate' not in row['financial_return_json']
        assert financial['binding']['request_digest']==digest(state['body']) and state['requests']==1
        assert 'cost' not in financial['transport']
        assert financial['binding']['reserved_upper']==3 and financial['binding']['output_bound']==4096
        with pytest.raises(PermissionError):session.receive()
        with pytest.raises(TypeError):pickle.dumps(receipt)
        with pytest.raises(TypeError):receipt._value=None
        with pytest.raises(TypeError):session.connection=None
        assert session.connection.sock.fileno()==-1
        with store.transaction(write=True) as conn:
            conn.execute('UPDATE research_provider_sessions SET candidate_json=NULL WHERE id=?',(session.id,))
            assert persist_offline_owned_source(conn,receipt)==first
        assert saved(store)['candidate_json'] is None


@pytest.mark.parametrize('ending',['stop','cancel','revoke','scope','delete'])
@pytest.mark.parametrize('before_receive',[False,True])
def test_late_financial_provenance_never_restores_ended_content(approved_inputs,lifecycle,ending,before_receive):
    client,_,store,rid,_,_,_=approved_inputs
    with owned_probe(approved_inputs) as (session,result,_):
        receipt=None if before_receive else session.receive()
        if ending=='delete':
            response=lifecycle[0].post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
            assert response.status_code==200,response.text
        elif ending=='cancel':
            response=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':1})
            assert response.status_code==200,response.text
        else:
            with store.transaction(write=True) as conn:
                if ending=='stop':conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(result['task_id'],))
                elif ending=='revoke':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
                else:conn.execute("UPDATE research_grants SET scopes='[\"execute\"]' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
        receipt=receipt or session.receive()
        with store.transaction(write=True) as conn:persist_offline_owned_source(conn,receipt)
        row=saved(store)
        assert row['state']=='received' and row['candidate_json'] is None
        assert json.loads(row['financial_return_json'])['transport']['usage']['total_tokens']==120
        with store.transaction() as conn:
            task=conn.execute('SELECT execution,stop_requested FROM research_tasks WHERE id=?',(result['task_id'],)).fetchone()
            assert not task or task['execution']!='COMPLETED'


@pytest.mark.parametrize('body,truncated,code',[(response_body(usage=None),False,'usage_unknown'),
    (b'{',False,'response_unknown'),(response_body(),True,'response_unknown'),
    (b'x'*131073,False,'response_limit')],ids=['missing-usage','invalid-json','truncated','over-cap'])
def test_missing_or_incomplete_receive_stays_unknown_and_closes(approved_inputs,body,truncated,code):
    store=approved_inputs[2]
    with owned_probe(approved_inputs,body,truncated=truncated) as (session,_,_):
        receipt=session.receive()
        with store.transaction(write=True) as conn:persist_offline_owned_source(conn,receipt)
        row=saved(store);transport=json.loads(row['financial_return_json'])['transport']
        assert row['state']=='unknown' and row['candidate_json'] is None
        assert transport['safe_code']==code and transport['usage'] is None
        assert session.connection.sock.fileno()==-1


def test_no_public_or_dto_source_and_retired_owner_rejected(approved_inputs):
    store=approved_inputs[2]
    with pytest.raises(TypeError):OwnedProviderSession()
    with pytest.raises(ResearchError) as err:OwnedProviderSession.register()
    assert err.value.status==503
    with owned_probe(approved_inputs) as (session,_,_):
        with pytest.raises(TypeError):OwnedReturnReceipt(session,{})
        receipt=session.receive()
        with store.transaction(write=True) as conn:
            for obj in (True,{},receipt._value):
                with pytest.raises(PermissionError):persist_offline_owned_source(conn,obj)
            with pytest.raises(PermissionError):mint_trusted_cost_authority(conn,observation=receipt)
        with sqlite3.connect(store.path) as conn:
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        session.close()
        with store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        assert saved(store)['financial_return_json'] is None


def test_replaced_return_and_changed_persistent_binding_rejected(approved_inputs):
    store=approved_inputs[2]
    with owned_probe(approved_inputs) as (session,_,_):
        receipt=session.receive();original=receipt._value
        object.__setattr__(receipt,'_value',original.model_copy())
        with store.transaction(write=True) as conn:
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        object.__setattr__(receipt,'_value',original)
        with store.transaction(write=True) as conn:
            conn.execute('UPDATE research_provider_sessions SET binding_digest=? WHERE id=?',('0'*64,session.id))
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        assert saved(store)['financial_return_json'] is None


def test_no_receive_close_preserves_unknown_without_financial_return(approved_inputs):
    with owned_probe(approved_inputs) as (session,_,_):
        session.close()
        row=saved(approved_inputs[2])
        assert row['state']=='unknown' and row['financial_return_json'] is None
        assert session.connection.sock.fileno()==-1
        with pytest.raises(PermissionError):session.receive()


def test_duplicate_session_registration_never_sends_again(approved_inputs):
    client,_,store,_,pid,_,_=approved_inputs
    with owned_probe(approved_inputs) as (session,result,state):
        with AuthorizationGate(store).owner_gate(pid) as lease:
            with pytest.raises(sqlite3.IntegrityError):
                OwnedProviderSession.offline_probe(store,identity(client),lease,result['approval_ref'],session.binding.permit_id,
                    connection_factory=lambda _:pytest.fail('duplicate registration connected'))
        receipt=session.receive()
        with store.transaction(write=True) as conn:persist_offline_owned_source(conn,receipt)
        assert saved(store)['state']=='received' and state['requests']==1


@pytest.mark.parametrize('field',['request_digest','evidence_digest','admitted_at','authorized_task_version'])
def test_changed_consumed_ticket_rejects_persistence(approved_inputs,field):
    store=approved_inputs[2]
    with owned_probe(approved_inputs) as (session,_,_):
        receipt=session.receive()
        with store.transaction(write=True) as conn:
            value='0'*64 if field.endswith('digest') else 99
            conn.execute('UPDATE research_dispatch_permits SET '+field+'=? WHERE id=?',(value,session.binding.permit_id))
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        assert saved(store)['financial_return_json'] is None


@pytest.mark.parametrize('field',['authorized_task_version','authorized_step_version'])
def test_stale_consumed_version_rejected_before_registration(approved_inputs,field):
    with pytest.raises(PermissionError):
        with owned_probe(approved_inputs,stale=field):pytest.fail('stale probe sent')
    with approved_inputs[2].transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0]==0


def test_current_task_version_rechecked_after_connect_before_send(approved_inputs):
    with pytest.raises(PermissionError):
        with owned_probe(approved_inputs,change_after_connect=True):pytest.fail('changed probe sent')
    row=saved(approved_inputs[2])
    assert row['state']=='unknown' and row['financial_return_json'] is None


def test_changed_session_version_rejects_first_return(approved_inputs):
    with owned_probe(approved_inputs) as (session,_,_):
        receipt=session.receive()
        with approved_inputs[2].transaction(write=True) as conn:
            conn.execute('UPDATE research_provider_sessions SET version=99 WHERE id=?',(session.id,))
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        assert saved(approved_inputs[2])['financial_return_json'] is None


def test_bad_candidate_keeps_usage_without_treating_it_as_free(approved_inputs):
    with owned_probe(approved_inputs,response_body(choices=[])) as (session,_,_):
        receipt=session.receive()
        with approved_inputs[2].transaction(write=True) as conn:persist_offline_owned_source(conn,receipt)
        row=saved(approved_inputs[2]);transport=json.loads(row['financial_return_json'])['transport']
        assert row['state']=='received' and row['candidate_json'] is None
        assert transport['usage']['total_tokens']==120 and transport['safe_code']=='body_invalid'


def test_conflicting_receipt_cannot_overwrite_first_financial_fact(approved_inputs):
    with owned_probe(approved_inputs) as (session,_,_):
        receipt=session.receive()
        with approved_inputs[2].transaction(write=True) as conn:persist_offline_owned_source(conn,receipt)
        before=saved(approved_inputs[2])
        # Simulate in-process memory corruption; ordinary assignment is sealed.
        object.__setattr__(receipt,'_received_at','2030-01-01T00:00:00.000000Z')
        with approved_inputs[2].transaction(write=True) as conn:
            with pytest.raises(PermissionError):persist_offline_owned_source(conn,receipt)
        assert saved(approved_inputs[2])==before


def _corrupt_consumed_financial_facts(store,approval_ref,permit_id,change):
    """Fault injection in synthetic consumed rows, never the approved source."""
    with store.transaction(write=True) as conn:
        approval=conn.execute('SELECT * FROM research_paid_approvals WHERE id=?',(approval_ref,)).fetchone()
        permit=conn.execute('SELECT * FROM research_dispatch_permits WHERE id=?',(permit_id,)).fetchone()
        reservation=permit['reservation_id']
        if change=='other_account':
            other=str(uuid4())
            conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,cap,initial_prepaid_units,other_use_margin_units,held,status) VALUES(?,?,'live','deepseek','CNY',1000000,1000000,0,3,'active')",(other,str(uuid4())))
            conn.execute('UPDATE research_reservations SET account_id=? WHERE id=?',(other,reservation))
        elif change=='basis':conn.execute('UPDATE research_dispatch_permits SET budget_basis_digest=? WHERE id=?',('0'*64,permit_id))
        elif change in ('admitted_future','admitted_negative','before_confirmation'):
            stamp={'admitted_future':int(time.time())+600,'admitted_negative':-1,'before_confirmation':approval['confirmed_at']-1}[change]
            conn.execute('UPDATE research_dispatch_permits SET admitted_at=? WHERE id=?',(stamp,permit_id))
        elif change=='epoch':conn.execute('UPDATE research_reservations SET funding_epoch=funding_epoch+1 WHERE id=?',(reservation,))
        elif change in ('under_reserved','over_reserved'):
            amount=1 if change=='under_reserved' else 4
            conn.execute('UPDATE research_reservations SET max_cost=? WHERE id=?',(amount,reservation))
            conn.execute('UPDATE research_funding_accounts SET held=? WHERE id=?',(amount,approval['account_id']))
        elif change in ('auth_scope_digest','outbound_fingerprint'):
            conn.execute('UPDATE research_reservations SET '+change+'=? WHERE id=?',('0'*64,reservation))
        else:raise AssertionError('unknown synthetic fault')


@pytest.mark.parametrize('phase',['registration','pre_send'])
@pytest.mark.parametrize('change',['other_account','basis','admitted_future','admitted_negative',
    'before_confirmation','epoch','under_reserved','over_reserved','auth_scope_digest','outbound_fingerprint'])
def test_original_approval_binds_consumed_rows_before_any_post(approved_inputs,monkeypatch,phase,change):
    import sys
    original_factory=OwnedProviderSession.offline_probe
    original_reply=tcp_reply
    observed={'connections':0,'wire':None}
    @contextmanager
    def capture_wire(*args,**kwargs):
        with original_reply(*args,**kwargs) as (factory,state):
            observed['wire']=state
            yield factory,state
    def create(cls,store,actor,lease,approval_ref,permit_id,*,connection_factory,seconds=5):
        if phase=='registration':_corrupt_consumed_financial_facts(store,approval_ref,permit_id,change)
        def connect(deadline):
            observed['connections']+=1
            sock=connection_factory(deadline)
            try:
                if phase=='pre_send':_corrupt_consumed_financial_facts(store,approval_ref,permit_id,change)
                return sock
            except BaseException:
                sock.close()
                raise
        return original_factory(store,actor,lease,approval_ref,permit_id,connection_factory=connect,seconds=seconds)
    with monkeypatch.context() as patch:
        patch.setattr(sys.modules[__name__],'tcp_reply',capture_wire)
        patch.setattr(OwnedProviderSession,'offline_probe',classmethod(create))
        with pytest.raises((PermissionError,ResearchError)):
            with owned_probe(approved_inputs):pytest.fail('corrupted consumed probe was sent')
    assert observed['connections']==(0 if phase=='registration' else 1)
    assert observed['wire']['requests']==0 and observed['wire']['closed']
    with approved_inputs[2].transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0
        if phase=='registration':assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0]==0
        else:
            row=conn.execute('SELECT state,financial_return_json,candidate_json FROM research_provider_sessions').fetchone()
            assert tuple(row)==('unknown',None,None)


@pytest.mark.parametrize('ending',['cancel','revoke','stop','paid_scope'])
def test_replay_erases_now_disallowed_candidate_preserving_first_financial_fact(approved_inputs,ending):
    client,_,store,rid,_,_,_=approved_inputs
    with owned_probe(approved_inputs) as (session,result,state):
        receipt=session.receive()
        with store.transaction(write=True) as conn:first=persist_offline_owned_source(conn,receipt)
        original=saved(store)
        assert original['candidate_json']
        if ending=='cancel':
            response=post(client,f'/api/research/{rid}/cancel',{'task_id':result['task_id'],'expected_task_version':1})
            assert response.status_code==200,response.text
        else:
            with store.transaction(write=True) as conn:
                if ending=='stop':conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(result['task_id'],))
                elif ending=='revoke':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
                else:conn.execute("UPDATE research_grants SET scopes='[\"execute\"]' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(result['task_id'],))
        for _ in range(2):
            with store.transaction(write=True) as conn:assert persist_offline_owned_source(conn,receipt)==first
            current=saved(store)
            assert current['candidate_json'] is None
            assert {key:value for key,value in current.items() if key!='candidate_json'}=={key:value for key,value in original.items() if key!='candidate_json'}
        assert state['requests']==1
