"""Authenticated historical result consumers; offline local transport only."""
import json
import multiprocessing
import sqlite3
from uuid import uuid4

import pytest

from .test_research_persistence import stack,post,problem
from .test_research_d1_integration import source_stack,start_current
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api
from .test_research_paid_budget_loop import execution
from .test_research_paid_producers import identity
from research.authorization import AuthorizationGate
from research.paid_provider_session import persist_budget_return
from research.paid_provider_session import BudgetedOwnedSession
from .test_research_paid_api import make_preview,confirm_data
from .test_research_owned_return import tcp_reply,response_body
from .test_research_lifecycle import lifecycle,delete,login


def complete(data):
    client,_,store,rid,_,_=data
    with execution(data) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'history-complete')
        assert response.status_code==200,response.text
        report=response.json()['data']['method_result'];assert report
        with store.transaction() as conn:original=conn.execute('SELECT method_commit_json FROM research_provider_sessions WHERE id=?',(report['result_ref'],)).fetchone()[0]
        assert wire['requests']==1
        return result['task_id'],report,original


def test_actual_completed_result_survives_revision_as_explicit_read_only_history(paid_api):
    client,_,store,rid,_,_=paid_api
    task,original,commit=complete(paid_api)
    changed=problem('A distinct later question');changed['confirmed']=True
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':changed},'history-revise')
    assert response.status_code==200,response.text
    current=client.get(f'/api/research/{rid}')
    assert current.status_code==200 and current.json()['data'].get('method_result') is None
    assert task in [item['task_id'] for item in current.json()['data']['task_history']]
    read=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert read.status_code==200,read.text
    view=read.json()['data'];report=view['method_result']
    assert view['is_historical'] is report['is_historical'] is True
    assert view['current_problem']['revision']==1 and report['input_revision']==1
    assert {k:v for k,v in report.items() if k!='is_historical'}=={k:v for k,v in original.items() if k!='is_historical'}
    write=post(client,f'/api/research/{rid}/reconcile',{'task_id':task,'expected_task_version':3},'history-is-not-writer')
    assert write.status_code==200 and write.json()['data']['method_result'] is None,write.text
    with store.transaction() as conn:
        assert conn.execute('SELECT method_commit_json FROM research_provider_sessions WHERE id=?',(report['result_ref'],)).fetchone()[0]==commit
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1


def test_global_control_version_growth_does_not_invalidate_original_commit(paid_api):
    client,_,store,rid,_,_=paid_api;task,report,commit=complete(paid_api)
    with store.transaction(write=True) as conn:conn.execute('UPDATE research_controls SET version=version+1 WHERE id=?',(rid,))
    read=client.get(f'/api/research/{rid}')
    assert read.status_code==200,read.text
    assert read.json()['data']['method_result']==report
    with store.transaction() as conn:assert conn.execute('SELECT method_commit_json FROM research_provider_sessions WHERE id=?',(report['result_ref'],)).fetchone()[0]==commit


@pytest.mark.parametrize('damage',['control-before-commit','task-version','step-version','step-state','future-input'])
def test_original_commit_versions_are_exact_and_never_a_future_revision(paid_api,damage):
    client,_,store,rid,_,_=paid_api;task,_,commit=complete(paid_api);meta=json.loads(commit)
    with store.transaction(write=True) as conn:
        if damage=='control-before-commit':conn.execute('UPDATE research_controls SET version=? WHERE id=?',(meta['research_before'],rid))
        elif damage=='task-version':conn.execute('UPDATE research_tasks SET version=version+1 WHERE id=?',(task,))
        elif damage=='step-version':conn.execute('UPDATE research_steps SET version=version+1 WHERE id=?',(meta['step_id'],))
        elif damage=='step-state':conn.execute("UPDATE research_steps SET state='FAILED' WHERE id=?",(meta['step_id'],))
        else:conn.execute('UPDATE research_tasks SET input_revision=input_revision+1 WHERE id=?',(task,))
    response=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert response.status_code==200,response.text
    assert response.json()['data']['method_result'] is None and response.json()['data']['method_result_state']=='unavailable'


def test_original_unicode_revision_is_preserved_and_control_cannot_rewind_before_it(paid_api):
    from functools import partial
    from .source_http_fixture import source_server,get_local,ARTICLE,TITLE
    from research import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    client,path,store,rid,_,resolver=paid_api
    unicode_problem=problem('Original e\u0301 plus 😀 must remain exact');unicode_problem['confirmed']=True
    revised=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':unicode_problem},'unicode-original-revision')
    assert revised.status_code==200,revised.text
    source=start_current(client,rid,'unicode historical evidence').json()['data']['task']['id']
    article=ARTICLE.replace(('Citation: '+TITLE).encode(),('Citation: Example A, Example B (2026) '+TITLE).encode())
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(source)=='COMPLETED'
        assert len(calls)==2
    with store.transaction() as conn:excerpt=conn.execute("SELECT id FROM research_evidence_objects WHERE task_id=? AND kind='excerpts'",(source,)).fetchone()[0]
    task,report,_=complete((client,path,store,rid,excerpt,resolver))
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':2,'problem':problem('Later third revision')},'unicode-later-revision').status_code==200
    read=client.get(f'/api/research/{rid}',params={'task_id':task});assert read.status_code==200,read.text
    assert read.json()['data']['current_problem']['original_input']==unicode_problem['original_input']
    assert read.json()['data']['method_result']['input_revision']==2
    assert read.json()['data']['method_result']['citations']==report['citations']
    with store.transaction(write=True) as conn:conn.execute('UPDATE research_controls SET current_revision=1 WHERE id=?',(rid,))
    refused=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert refused.status_code==200 and refused.json()['data']['method_result'] is None,refused.text


def test_same_revision_new_completed_task_keeps_previous_result_as_explicit_history(paid_api):
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (first,first_result,wire,pid):
        receipt=first.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':first_result['task_id'],'expected_task_version':2},'first-same-revision')
        assert response.status_code==200 and response.json()['data']['method_result']
        old=response.json()['data']['method_result']
        draft=make_preview(paid_api,'second-same-revision-preview')
        confirmed=post(client,f'/api/research/{rid}/paid-approvals',confirm_data(draft),'second-same-revision-confirm')
        assert confirmed.status_code==200,confirmed.text
        with tcp_reply(response_body()) as (factory,second_wire):
            with BudgetedOwnedSession.offline_start(store,identity(client),first.proof.source,confirmed.json()['data']['approval_ref'],connection_factory=factory) as second:
                receipt2=second.receive()
                with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt2)
                result2=post(client,f'/api/research/{rid}/reconcile',{'task_id':confirmed.json()['data']['task_id'],'expected_task_version':2},'second-same-revision-result')
                assert result2.status_code==200,result2.text
                assert client.get(f'/api/research/{rid}').json()['data']['method_result']['result_ref']==second.id
                previous=client.get(f'/api/research/{rid}',params={'task_id':first_result['task_id']})
                assert previous.status_code==200,previous.text
                value=previous.json()['data'];assert value['is_historical'] is value['method_result']['is_historical'] is True
                assert value['method_result']['result_ref']==old['result_ref'] and value['method_result']['received_at']==old['received_at']
                assert second_wire['requests']==1
        assert wire['requests']==1


def test_history_navigation_uses_inclusive_anchor_lookahead_without_gaps_or_loops(source_stack):
    client,_,rid=source_stack;expected=[]
    for i in range(43):
        started=start_current(client,rid,'history navigation '+chr(65+i//26)+chr(65+i%26));assert started.status_code==200,started.text
        task=started.json()['data']['task'];expected.append(task['id'])
        cancelled=post(client,f'/api/research/{rid}/cancel',{'task_id':task['id'],'expected_task_version':task['version']},'history-cancel-'+str(i))
        assert cancelled.status_code==200,cancelled.text
    cursor=None;seen=[];pages=[]
    while True:
        response=client.get(f'/api/research/{rid}',params={'task_id':cursor} if cursor else {})
        assert response.status_code==200,response.text
        view=response.json()['data'];page=view['task_history'];pages.append(page)
        assert 0<len(page)<=20
        if cursor:assert page[0]['task_id']==cursor
        assert all(set(item)=={'task_id','input_revision','input_digest','start_version','execution','is_historical','received_at','result_status'} for item in page)
        seen.extend(item['task_id'] for item in page)
        cursor=view['next_task_id']
        if cursor is None:break
        assert cursor not in seen
    assert [len(page) for page in pages]==[20,20,3]
    assert seen==list(reversed(expected)) and len(set(seen))==43


def _history_get(cookie,rid,task,out):
    from fastapi.testclient import TestClient
    from .test_research_persistence import app
    with TestClient(app()) as client:
        client.cookies.set('phase_session',cookie)
        response=client.get(f'/api/research/{rid}',params={'task_id':task})
        out.put((response.status_code,response.json()))


def test_historical_result_reopens_in_new_process_under_current_authorization(paid_api):
    client,_,_,rid,_,_=paid_api;task,report,_=complete(paid_api)
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':problem('new historical problem')},'history-process-revision')
    assert response.status_code==200,response.text
    from web.backend.tests.test_research_method_history import _history_get as target
    ctx=multiprocessing.get_context('spawn');out=ctx.Queue();child=ctx.Process(target=target,args=(client.cookies.get('phase_session'),rid,task,out))
    try:
        child.start();status,value=out.get(timeout=20);child.join(5)
        assert child.exitcode==0 and status==200,value
        assert value['data']['method_result']['result_ref']==report['result_ref'] and value['data']['method_result']['received_at']==report['received_at']
        assert value['data']['method_result']['is_historical'] is True
    finally:
        if child.is_alive():child.terminate();child.join(3)
        child.close();out.close();out.join_thread()


def test_publication_size_failure_cannot_rollback_trusted_financial_observation(paid_api,monkeypatch):
    from research import method_result
    client,_,store,rid,_,_=paid_api
    with execution(paid_api) as (session,result,wire,pid):
        receipt=session.receive()
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
        original=method_result.result_view
        def oversized(*args,**kwargs):
            value=original(*args,**kwargs)
            if value is not None:value=dict(value,synthetic_size_fault='X'*(512*1024))
            return value
        with monkeypatch.context() as fault:
            fault.setattr(method_result,'result_view',oversized)
            response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'publication-limit')
        assert response.status_code==413,response.text
        with store.transaction() as conn:
            assert conn.execute('SELECT held,upper_booked FROM research_funding_accounts').fetchone()[:]==(0,2)
            assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==1
            assert conn.execute('SELECT method_commit_json IS NOT NULL FROM research_provider_sessions').fetchone()[0]==1
        replay=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'publication-limit')
        assert replay.status_code==200 and replay.json()['data']['method_result']['result_ref']==session.id,replay.text
        assert wire['requests']==1


@pytest.mark.parametrize('withdraw',['paid-grant','grant-epoch','stop','source-display','source-hash','source-snapshot'])
def test_historical_body_rechecks_original_permission_and_current_source(paid_api,withdraw,monkeypatch):
    client,_,store,rid,excerpt,_=paid_api;task,report,_=complete(paid_api)
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':problem('Later private question')},'withdraw-revise').status_code==200
    with store.transaction(write=True) as conn:
        if withdraw=='paid-grant':conn.execute("UPDATE research_grants SET status='revoked' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(task,))
        elif withdraw=='grant-epoch':conn.execute('UPDATE research_grants SET version=version+1 WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)',(task,))
        elif withdraw=='stop':conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(task,))
        elif withdraw=='source-display':
            # Source rows are immutable. Inject only the reader's permission
            # failure; do not bypass its SQL protections to fake a revocation.
            from research.evidence_repository import EvidenceRepository
            def denied(*args,**kwargs):raise PermissionError('synthetic Source display policy failure')
            monkeypatch.setattr(EvidenceRepository,'_permissions',denied)
        elif withdraw=='source-hash':
            from research import evidence_repository
            extracted=conn.execute("SELECT extracted FROM research_evidence_objects WHERE kind='snapshots' AND research_id=?",(rid,)).fetchone()[0]
            original=evidence_repository.sha256
            monkeypatch.setattr(evidence_repository,'sha256',lambda value:'f'*64 if value==extracted.encode() else original(value))
        else:conn.execute("DELETE FROM research_evidence_objects WHERE kind='snapshots' AND research_id=?",(rid,))
    read=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert read.status_code==200,read.text
    value=read.json()['data']
    assert value['method_result'] is None and value['method_result_state']=='unavailable'
    assert value['is_historical'] and value['current_problem']['revision']==1 and value['task_history']
    assert report['sections']['summary'] not in read.text


@pytest.mark.parametrize('withdraw',['read-grant','owner','account'])
def test_historical_metadata_also_requires_current_research_owner(paid_api,withdraw):
    client,_,store,rid,_,_=paid_api;task,_,_=complete(paid_api)
    with store.transaction(write=True) as conn:
        if withdraw=='read-grant':conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND scopes LIKE '%read%'",(rid,))
        elif withdraw=='owner':conn.execute('UPDATE research_controls SET owner_epoch=owner_epoch+1 WHERE id=?',(rid,))
        else:conn.execute('UPDATE auth_users SET session_generation=?',(str(uuid4()),))
    read=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert read.status_code==(401 if withdraw=='account' else 404),read.text
    assert 'task_history' not in read.text and 'Offline candidate' not in read.text


def test_historical_delete_and_same_email_new_account_never_recover_metadata_or_body(paid_api,lifecycle):
    client,_,store,rid,_,_=paid_api;task,_,_=complete(paid_api)
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':problem('After completed result')},'delete-history-revise').status_code==200
    assert delete(lifecycle[0]).status_code==200
    assert client.get(f'/api/research/{rid}',params={'task_id':task}).status_code==401
    client.cookies.clear();login(client)
    assert client.get(f'/api/research/{rid}',params={'task_id':task}).status_code==404
    with store.transaction() as conn:
        assert conn.execute('SELECT candidate_json,method_commit_json,body_origin_state FROM research_provider_sessions').fetchone()[:]==(None,None,'closed')


@pytest.mark.parametrize('mutation',['extra','research_before','research_after','task_before','task_after','step_before','step_after','float','negative','overflow','nonincrement','ref','revision','revision-bool','revision-float','revision-zero','digest'])
def test_corrupt_original_commit_metadata_never_renders_a_historical_body(paid_api,monkeypatch,mutation):
    from research import method_result
    client,_,_,rid,_,_=paid_api;task,_,_=complete(paid_api)
    assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':problem('Historical metadata input')},'metadata-revise').status_code==200
    original=method_result._row
    def damaged(*args,**kwargs):
        row=original(*args,**kwargs);meta=json.loads(row['method_commit_json'])
        if mutation=='extra':meta['historical_authorized']=True
        elif mutation=='ref':meta['result_ref']=str(uuid4())
        elif mutation=='revision':meta['input_revision']+=1
        elif mutation=='revision-bool':meta['input_revision']=True
        elif mutation=='revision-float':meta['input_revision']=float(meta['input_revision'])
        elif mutation=='revision-zero':meta['input_revision']=0
        elif mutation=='digest':meta['input_digest']='f'*64
        elif mutation=='float':meta['task_before']=float(meta['task_before'])
        elif mutation=='negative':meta.update(step_before=-1,step_after=0)
        elif mutation=='overflow':meta.update(research_before=2147483647,research_after=2147483648)
        elif mutation=='nonincrement':meta['research_before']=meta['research_after']
        else:meta[mutation]=True
        return dict(row,method_commit_json=json.dumps(meta))
    monkeypatch.setattr(method_result,'_row',damaged)
    response=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert response.status_code==200,response.text
    assert response.json()['data']['method_result'] is None and response.json()['data']['method_result_state']=='unavailable'


def test_sql_database_failure_is_not_relabelled_as_unavailable_body(paid_api,monkeypatch):
    from research import method_result
    client,_,_,rid,_,_=paid_api;task,_,_=complete(paid_api)
    def failed(*args,**kwargs):raise sqlite3.OperationalError('synthetic read failure')
    monkeypatch.setattr(method_result,'result_view',failed)
    response=client.get(f'/api/research/{rid}',params={'task_id':task})
    assert response.status_code==503 and response.json()['error']['code']=='STORE_UNAVAILABLE'
    assert 'method_result_state' not in response.text


def test_pagination_anchor_survives_new_insert_and_rejects_cross_research(source_stack):
    client,_,rid=source_stack;expected=[]
    for i in range(22):
        result=start_current(client,rid,'anchor query '+chr(65+i)).json()['data']['task'];expected.append(result['id'])
        assert post(client,f'/api/research/{rid}/cancel',{'task_id':result['id'],'expected_task_version':result['version']}).status_code==200
    first=client.get(f'/api/research/{rid}').json()['data'];anchor=first['next_task_id'];assert anchor
    newer=start_current(client,rid,'new insert query').json()['data']['task']
    assert post(client,f'/api/research/{rid}/cancel',{'task_id':newer['id'],'expected_task_version':newer['version']}).status_code==200
    second=client.get(f'/api/research/{rid}',params={'task_id':anchor}).json()['data']
    assert [v['task_id'] for v in first['task_history']+second['task_history']]==list(reversed(expected))
    assert second['next_task_id'] is None
    other=post(client,'/api/research',{'problem':problem('Different research')}).json()['data']['research']['id']
    assert client.get(f'/api/research/{other}',params={'task_id':anchor}).status_code==404
    assert client.get(f'/api/research/{rid}',params={'task_id':anchor,'is_historical':'true'}).status_code==422


def test_large_real_received_body_does_not_block_later_problem_navigation(paid_api):
    from .test_research_revision_budget import maximum_problem
    from research.provider_schemas import canonical
    client,_,store,rid,_,_=paid_api
    candidate=dict(summary='😀'*1000,mechanisms=[dict(label='Large offline example',mechanism='😀'*1200,
        variable_map=[dict(source='😀'*120,target='😀'*120,rationale='😀'*400) for _ in range(8)],
        conditions=[],nontransferable=[],evidence_handles=['e1'])],competing_explanations=[],
        validation_plan=dict(measurement='m',outcome='o',falsification='f',stop_rule='s'),gaps=['Synthetic reception only'])
    body=json.loads(response_body());body['choices'][0]['message']['content']=canonical(candidate).decode()
    with execution(paid_api,body=canonical(body)) as (session,result,wire,pid):
        receipt=session.receive()
        assert receipt._value.candidate is not None,receipt._value.safe_code
        with AuthorizationGate(store).owner_gate(pid) as lease,store.transaction(write=True) as conn:
            persist_budget_return(conn,store=store,lease=lease,receipt=receipt)
            saved=conn.execute('SELECT candidate_json FROM research_provider_sessions WHERE id=?',(session.id,)).fetchone()[0]
            assert 30000<len(saved.encode())<=32768
        response=post(client,f'/api/research/{rid}/reconcile',{'task_id':result['task_id'],'expected_task_version':2},'large-real-result')
        assert response.status_code==200 and response.json()['data']['method_result']['sections']==candidate,response.text[:200]
        maximum=maximum_problem()
        for revision in range(1,6):
            saved=post(client,f'/api/research/{rid}/revisions',{'expected_revision':revision,'problem':maximum},'large-body-revise-'+str(revision))
            assert saved.status_code==200,saved.text[:200]
        current=client.get(f'/api/research/{rid}');assert current.status_code==200,current.text[:200]
        assert current.json()['data'].get('method_result') is None and len(current.json()['data']['revisions'])==6
        history=client.get(f'/api/research/{rid}',params={'task_id':result['task_id']})
        assert history.status_code==200,history.text[:200]
        assert history.json()['data']['method_result']['sections']==candidate and len(history.content)<=512*1024
        assert wire['requests']==1 and wire['body'] is not None and len(wire['body'])<=16384
