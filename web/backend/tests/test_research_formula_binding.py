"""Actual domain rows and original Source reader, never JSON-shaped authority."""
from contextlib import closing
from functools import partial
import json
import sqlite3
from uuid import uuid4
import pytest
from .test_research_persistence import stack,post
from .test_research_lifecycle import lifecycle
from .test_research_formula_lifecycle import create_formula,formula_problem,check,_seed_source
from .test_research_d1_integration import start_current
from web.backend.tests.source_http_fixture import source_server,get_local
from research import ResearchStore,ResearchRunner
from research.source_policy import PinnedPublicTransport
from api import auth


@pytest.mark.parametrize('damage',['task-version','task-input','task-execution','step-state','control-version','task-revision','research-id'])
def test_saved_body_requires_actual_original_domain_bindings(stack,damage):
    client,path=stack;rid,body=create_formula(client);started=check(client,rid,body)
    assert started.status_code==200,started.text
    ref=started.json()['data']['result_ref']
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').status_code==200
    target_rid=rid
    if damage=='task-revision':
        revised=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':formula_problem()})
        assert revised.status_code==200,revised.text
    if damage=='research-id':target_rid,_=create_formula(client)
    with closing(sqlite3.connect(path)) as conn,conn:
        task_id=conn.execute('SELECT task_id FROM research_formula_runs WHERE result_ref=?',(ref,)).fetchone()[0]
        if damage=='task-version':conn.execute('UPDATE research_tasks SET version=version+1 WHERE id=?',(task_id,))
        elif damage=='task-input':conn.execute('UPDATE research_tasks SET input_digest=? WHERE id=?',('0'*64,task_id))
        elif damage=='task-execution':conn.execute("UPDATE research_tasks SET execution='FAILED' WHERE id=?",(task_id,))
        elif damage=='step-state':conn.execute("UPDATE research_steps SET state='FAILED' WHERE task_id=?",(task_id,))
        elif damage=='control-version':conn.execute('UPDATE research_controls SET version=1 WHERE id=?',(rid,))
        elif damage=='task-revision':conn.execute('UPDATE research_tasks SET input_revision=2 WHERE id=?',(task_id,))
        else:conn.execute('UPDATE research_tasks SET research_id=? WHERE id=?',(target_rid,task_id))
    rejected=client.get(f'/api/research/{target_rid}/formula-results/{ref}')
    assert rejected.status_code==404,rejected.text
    assert 'formula_displays' not in rejected.text


def test_cached_typed_source_rows_without_task_and_step_are_not_read_authority(stack):
    client,path=stack;rid,_=create_formula(client);ref,_=_seed_source(path,rid)
    revised=formula_problem();revised['formula_draft']['left']['source_refs']=[ref]
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':revised})
    assert response.status_code==422,response.text


def test_original_source_pipeline_old_revision_and_stop_preserve_legitimate_read_policy(stack,monkeypatch):
    client,path=stack
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','true');monkeypatch.setenv('STRUCTURAL_D1_PUBLIC_GET_ENABLED','false')
    data=formula_problem();data['confirmed']=True;rid,_=create_formula(client,data)
    source_started=start_current(client,rid);assert source_started.status_code==200,source_started.text
    source_task=source_started.json()['data']['task']['id']
    with source_server() as (port,calls):
        runner=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        assert runner.run_once(source_task)=='COMPLETED'
        assert calls==['/discovery','/article']
    with closing(sqlite3.connect(path)) as conn,conn:
        row=conn.execute("SELECT id,payload FROM research_evidence_objects WHERE task_id=? AND kind='excerpts'",(source_task,)).fetchone()
        excerpt=json.loads(row[1]);snapshot=json.loads(conn.execute('SELECT payload FROM research_evidence_objects WHERE id=?',(excerpt['snapshot_id'],)).fetchone()[0])
        reference={'id':row[0],'revision':snapshot['source_revision'],'content_digest':snapshot['extracted_digest'],
            'provenance':'product_excerpt','locator':f"chars:{excerpt['start']}:{excerpt['end']}"}
    data=formula_problem();data['formula_draft']['left']['source_refs']=[reference]
    revised=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':data})
    assert revised.status_code==200,revised.text
    checked=check(client,rid,revised.json()['data']);assert checked.status_code==200,checked.text
    ref=checked.json()['data']['result_ref']
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').json()['data']['state']=='available'
    # Source stop alone does not introduce a new withdrawal policy. Existing
    # Source authorizer allows reading its saved evidence with current ACL.
    with closing(sqlite3.connect(path)) as conn,conn:conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(source_task,))
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').json()['data']['state']=='available'
    with closing(sqlite3.connect(path)) as conn,conn:conn.execute('DELETE FROM research_evidence_objects WHERE id=?',(snapshot['id'],))
    unavailable=client.get(f'/api/research/{rid}/formula-results/{ref}')
    assert unavailable.status_code==200 and unavailable.json()['data']['state']=='unavailable'
    assert unavailable.json()['data']['result'] is None


def test_result_recorded_timestamp_is_saved_once_and_replayed_without_now(stack):
    client,path=stack;rid,body=create_formula(client);key=str(uuid4());checked=check(client,rid,body,key)
    original=checked.json()['data']['formula_result_recorded_at'];assert original
    ref=checked.json()['data']['result_ref']
    replay=check(client,rid,body,key);assert replay.json()['data']['formula_result_recorded_at']==original
    result=client.get(f'/api/research/{rid}/formula-results/{ref}').json()['data']
    assert result['metadata']['formula_result_recorded_at']==original
    with closing(sqlite3.connect(path)) as conn,conn:
        assert json.loads(conn.execute('SELECT commit_json FROM research_formula_runs').fetchone()[0])['recorded_at']==original


def test_recursive_triggers_off_cannot_replace_saved_formula_rows_even_with_forged_udf(stack):
    client,path=stack;rid,body=create_formula(client);checked=check(client,rid,body)
    ref=checked.json()['data']['result_ref']
    with closing(sqlite3.connect(path)) as conn,conn:
        conn.execute('PRAGMA recursive_triggers=OFF')
        # This is an adversarial missing-authorizer connection, not a writer
        # capability or proof. The row-level no-replace guards must still win.
        conn.create_function('research_formula_write_allowed',2,lambda *args:1)
        for table in ('research_formula_revisions','research_formula_runs'):
            row=conn.execute('SELECT rowid,* FROM '+table).fetchone()
            columns=[column[1] for column in conn.execute('PRAGMA table_info('+table+')')]
            sql='INSERT OR REPLACE INTO '+table+' (rowid,'+','.join(columns)+') VALUES('+','.join('?' for _ in row)+')'
            with pytest.raises(sqlite3.IntegrityError):conn.execute(sql,row)
            with pytest.raises(sqlite3.IntegrityError):conn.execute('UPDATE OR REPLACE '+table+' SET rowid=rowid+1')
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').status_code==200


def test_saved_draft_without_formula_task_uses_authenticated_erase_origin(lifecycle):
    client,path,_=lifecycle;rid,_=create_formula(client)
    from research import ResearchService
    from research.errors import ResearchError
    from .test_research_paid_producers import identity
    service=ResearchService(ResearchStore(auth._store()));actor=identity(client)
    principal=service._principal(actor)
    with service.authorization.owner_gate(principal) as lease:
        with service.store.transaction() as conn:gate_id=conn.execute('SELECT gate_id FROM research_principals WHERE id=?',(principal,)).fetchone()[0]
        with pytest.raises(ResearchError) as denied:
            service.begin_account_deletion_locked(actor.email,actor.generation,gate_id,auth._account_cleanup_binding(actor.email),owner_lease=lease,request_source=None)
        assert denied.value.code=='AUTHORIZATION_STALE'
    response=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
    assert response.status_code==200,response.text
    with closing(sqlite3.connect(path)) as conn,conn:
        assert conn.execute('SELECT count(*) FROM research_formula_revisions').fetchone()[0]==0
        assert conn.execute('SELECT origin_version FROM auth_deletion_jobs').fetchone()[0]=='authenticated-delete-v1'
