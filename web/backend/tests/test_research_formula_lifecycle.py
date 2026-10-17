"""Real signed HTTP -> immutable revision -> guarded child -> protected history."""
from contextlib import closing
import copy
import json
import sqlite3
import sys
from uuid import uuid4
import pytest
from .test_research_persistence import stack,post,problem,login,app
from .test_research_formula_public import draft_request,request
from api import auth
from research import ResearchStore


def formula_problem():
    data=problem();data['entry']='formula';data['formula_draft']={'input_origin':'user_provided',**draft_request(request())}
    return data


def create_formula(client,data=None):
    response=post(client,'/api/research',{'problem':data or formula_problem()})
    assert response.status_code==200,response.text
    body=response.json()['data'];return body['research']['id'],body


def check(client,rid,body,key=None,**changes):
    meta=body['current_problem']['formula_snapshot']
    payload={'input_revision':meta['revision'],'expected_research_version':body['research_version'],
        'formula_digest':meta['formula_digest'],'confirm_formula_input':True,**changes}
    return post(client,f'/api/research/{rid}/formula-checks',payload,key)


def test_actual_api_snapshot_child_receipt_and_same_ref_history(stack):
    client,path=stack;rid,body=create_formula(client)
    assert body['current_problem']['formula_snapshot']['executable'] is True
    assert 'formula_draft' not in body['current_problem']
    assert 'expression' not in json.dumps(body)
    snapshot=client.get(f'/api/research/{rid}/formula-revisions/1')
    assert snapshot.status_code==200,snapshot.text
    assert snapshot.json()['data']['formula']['left']['id']
    key=str(uuid4());response=check(client,rid,body,key)
    assert response.status_code==200,response.text
    data=response.json()['data'];assert data['state']=='returned'
    ref=data['result_ref'];saved=client.get(f'/api/research/{rid}/formula-results/{ref}')
    assert saved.status_code==200,saved.text
    result=saved.json()['data'];assert result['state']=='available'
    assert result['result']['execution_attested'] is False
    assert result['provenance']['reaped'] is True
    if sys.platform=='linux':assert result['provenance']['execution_attested'] is True
    else:
        assert result['provenance']['execution_attested'] is False
        assert {v['status'] for v in result['result']['outcomes']}=={'unsupported'}
        assert result['provenance']['resource_guard']=='not_executed'
    replay=check(client,rid,body,key)
    assert replay.status_code==200 and replay.json()['data']['result_ref']==ref
    with closing(sqlite3.connect(path)) as conn, conn:
        assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==1
        assert conn.execute('SELECT execution FROM research_tasks').fetchone()[0]=='COMPLETED'
        assert conn.execute('SELECT count(*) FROM research_provider_sessions').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0
    reopened=client.get(f'/api/research/{rid}')
    assert reopened.status_code==200,reopened.text
    assert reopened.json()['data']['formula_check']['result_ref']==ref
    assert 'expression' not in reopened.text


def test_missing_ast_remains_nonexecutable_draft_and_no_mathstatus(stack):
    client,path=stack;data=formula_problem();data['formula_draft']['left']['expression']=None
    rid,body=create_formula(client,data)
    assert body['current_problem']['formula_snapshot']['executable'] is False
    response=check(client,rid,body)
    assert response.status_code==422,response.text
    assert 'math_status' not in response.json()
    with closing(sqlite3.connect(path)) as conn, conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==0


@pytest.mark.parametrize('override',[{'owner':'bad'},{'task_id':str(uuid4())},{'callback':True},
    {'status':'COMPUTED'},{'confirm_formula_input':1},{'confirm_formula_input':False},{'formula_digest':'0'*64}])
def test_actual_api_rejects_authoritative_fields_and_wrong_confirmation(stack,override):
    client,_=stack;rid,body=create_formula(client)
    response=check(client,rid,body,**override)
    assert response.status_code in (409,422),response.text


def test_cross_owner_and_anonymous_result_access(stack):
    client,path=stack;rid,body=create_formula(client);response=check(client,rid,body)
    ref=response.json()['data']['result_ref']
    cookie=client.cookies.get('phase_session');client.cookies.clear()
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').status_code==401
    login(client,'formula-b@example.test')
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').status_code==404
    client.cookies.set('phase_session',cookie)


def _formula_read_process(cookie,rid,ref,out):
    from fastapi.testclient import TestClient
    from web.backend.tests.test_research_persistence import app
    with TestClient(app()) as client:
        client.cookies.set('phase_session',cookie)
        response=client.get(f'/api/research/{rid}/formula-results/{ref}')
        out.put((response.status_code,response.json()))


def test_same_result_ref_can_be_read_in_actual_fresh_process(stack):
    client,path=stack;rid,body=create_formula(client);response=check(client,rid,body)
    ref=response.json()['data']['result_ref'];expected=client.get(f'/api/research/{rid}/formula-results/{ref}').json()
    import multiprocessing
    from web.backend.tests.test_research_formula_lifecycle import _formula_read_process as target
    context=multiprocessing.get_context('spawn');out=context.Queue();child=context.Process(target=target,args=(client.cookies.get('phase_session'),rid,ref,out))
    try:
        child.start();status,reopened=out.get(timeout=10);child.join(5)
        assert status==200 and child.exitcode==0 and reopened==expected
    finally:
        if child.is_alive():child.terminate();child.join(2)
        child.close();out.close();out.join_thread()


def test_actual_delete_erases_formula_snapshots_and_closes_saved_body(stack,monkeypatch):
    client,path=stack;rid,body=create_formula(client);response=check(client,rid,body)
    ref=response.json()['data']['result_ref']
    # The app's existing real delete route handles its normal cleanup adapter.
    response=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
    assert response.status_code==200,response.text
    with closing(sqlite3.connect(path)) as conn, conn:
        assert conn.execute('SELECT count(*) FROM research_formula_revisions').fetchone()[0]==0
        run=conn.execute('SELECT state,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs').fetchone()
        assert run==('closed',None,None,None,None)
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
    assert client.get(f'/api/research/{rid}/formula-results/{ref}').status_code==401


def test_real_owned_child_cancel_closes_claim_reaps_and_cannot_fill_late_result(stack,monkeypatch):
    client,path=stack;rid,body=create_formula(client)
    import threading,os
    from concurrent.futures import ThreadPoolExecutor
    from research import formula_check,formula_result
    ready=threading.Event();pids=[];captured=[]
    launch=formula_check._launch
    class Capture(formula_check._OwnedCapture):
        def __setattr__(self,name,value):
            object.__setattr__(self,name,value)
            if name=='child_pid' and value:pids.append(value);ready.set()
    def wall_probe(payload,authorization,operation='calculate',wall=formula_check.WALL_SECONDS,*,_owned=None):
        result=launch(payload,authorization,'probe_wall',wall,_owned=_owned)
        captured.append((_owned.child_pid,_owned.reaped,result[0]));return result
    monkeypatch.setattr(formula_check,'_OwnedCapture',Capture)
    monkeypatch.setattr(formula_check,'_launch',wall_probe)
    with ThreadPoolExecutor(1) as pool:
        future=pool.submit(check,client,rid,body)
        assert ready.wait(3)
        current=client.get(f'/api/research/{rid}').json()['data']
        response=post(client,f'/api/research/{rid}/cancel',{'task_id':current['task']['id'],'expected_task_version':current['task']['version']})
        assert response.status_code==200,response.text
        ended=future.result(timeout=4)
        assert ended.status_code==200,ended.text
        assert ended.json()['data']['state']=='closed'
    assert captured and captured[0][1] and captured[0][2]=='revoked'
    for pid in pids:
        with pytest.raises(ProcessLookupError):os.kill(pid,0)
    assert not formula_result._EXECUTIONS and not formula_check._OWNED_RETURNS
    with closing(sqlite3.connect(path)) as conn, conn:
        assert conn.execute('SELECT state,result_json,receipt_json FROM research_formula_runs').fetchone()==('closed',None,None)
        assert conn.execute('SELECT execution FROM research_tasks').fetchone()[0]=='CANCELLED'


def _seed_source(path,rid):
    """Synthetic typed old-source records, no transport or real-source claim."""
    from research.evidence_schemas import DataSnapshot,EvidenceExcerpt,Licence,encode,sha256
    task=str(uuid4());snapid=str(uuid4());excerptid=str(uuid4());text='Synthetic source says conditions matter.';raw=b'<p>'+text.encode()+b'</p>'
    with closing(sqlite3.connect(path)) as conn, conn:
        revision=conn.execute('SELECT digest FROM research_revisions WHERE research_id=? AND revision=1',(rid,)).fetchone()[0]
        binding=dict(research_id=rid,input_revision=1,task_id=task,attempt=1,input_digest=revision)
        snapshot=DataSnapshot(**binding,id=snapid,source_id=str(uuid4()),source_revision=1,title='Synthetic local source',
            doi='10.1371/journal.pone.0015032',canonical_url='https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0015032',
            query_digest='a'*64,discovery_digest=sha256(b'{}'),acquired_at='2026-10-17T00:00:00Z',information_cutoff='2026-10-17T00:00:00Z',
            raw_digest=sha256(raw),extracted_digest=sha256(text.encode()),parser_version='plos-html-text-v1',
            licence=Licence(status='verified',private_cache=True,display_excerpt=True,basis='Synthetic test permission.'),origin='offline_probe')
        excerpt=EvidenceExcerpt(**binding,id=excerptid,snapshot_id=snapid,extracted_digest=snapshot.extracted_digest,start=0,end=len(text),quote=text)
        for kind,record in (('snapshots',snapshot),('excerpts',excerpt)):
            payload=encode(record)
            conn.execute('INSERT INTO research_evidence_objects VALUES(?,?,?,?,?,?,?,?,?,?,?)',(record.id,kind,rid,1,task,1,payload,sha256(payload.encode()),raw if kind=='snapshots' else None,text if kind=='snapshots' else None,b'{}' if kind=='snapshots' else None))
    return {'id':excerptid,'revision':1,'content_digest':snapshot.extracted_digest,'provenance':'product_excerpt','locator':f'chars:0:{len(text)}'},snapid


def test_real_stored_source_ref_from_older_revision_is_checked_and_currently_unavailable_is_not_404(stack):
    client,path=stack;rid,body=create_formula(client);ref,snapshot_id=_seed_source(path,rid)
    revised=formula_problem();revised['formula_draft']['left']['source_refs']=[ref]
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':revised})
    assert response.status_code==200,response.text
    response=check(client,rid,response.json()['data']);assert response.status_code==200,response.text
    result_ref=response.json()['data']['result_ref']
    assert client.get(f'/api/research/{rid}/formula-results/{result_ref}').json()['data']['state']=='available'
    with closing(sqlite3.connect(path)) as conn, conn:conn.execute('DELETE FROM research_evidence_objects WHERE id=?',(snapshot_id,))
    unavailable=client.get(f'/api/research/{rid}/formula-results/{result_ref}')
    assert unavailable.status_code==200 and unavailable.json()['data']['state']=='unavailable'
    assert unavailable.json()['data']['result'] is None


def test_nonexistent_and_forged_source_are_rejected_with_atomic_revision(stack):
    client,path=stack;rid,body=create_formula(client)
    data=formula_problem();data['formula_draft']['left']['source_refs']=[{'id':str(uuid4()),'revision':1,'content_digest':'a'*64,'provenance':'product_excerpt','locator':'chars:0:10'}]
    response=post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':data})
    assert response.status_code==422,response.text
    with closing(sqlite3.connect(path)) as conn, conn:
        assert conn.execute('SELECT count(*) FROM research_revisions').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM research_formula_revisions').fetchone()[0]==1


def test_plain_json_pid_and_pure_results_cannot_mint_execution_or_write_authority(stack):
    from research.formula_check import OwnedFormulaReturn,owned_check,evaluate_fixed_templates
    from research.formula_result import CurrentFormulaExecution,_commit
    from research.formula_schemas import FormulaCheckInput
    client,path=stack;rid,body=create_formula(client)
    pure=evaluate_fixed_templates(FormulaCheckInput.parse(request())).data()
    for fake in (pure,{'pid':123,'result':pure,'execution_attested':True},None):
        with pytest.raises(PermissionError):_commit(None,None,fake)
        with pytest.raises(PermissionError):owned_check(request(),authority=fake)
    with pytest.raises(TypeError):OwnedFormulaReturn(reference='fake')
    with pytest.raises(TypeError):CurrentFormulaExecution(nonce='fake')
    with closing(sqlite3.connect(path)) as conn, conn:assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==0


def test_authorization_poll_real_sql_scan_is_interrupted_by_its_deadline(stack,monkeypatch):
    from research import formula_result
    client,path=stack;rid,body=create_formula(client);original=formula_result._current;observed=[]
    def scan(conn,*args,**kwargs):
        conn.execute('WITH RECURSIVE c(x) AS (VALUES(0) UNION ALL SELECT x+1 FROM c WHERE x<100000000) SELECT sum(x) FROM c').fetchone()
        return original(conn,*args,**kwargs)
    monkeypatch.setattr(formula_result,'_current',scan)
    import time
    start=time.monotonic();response=check(client,rid,body)
    assert time.monotonic()-start<1 and response.status_code==200,response.text
    assert response.json()['data']['state']=='closed'
    with closing(sqlite3.connect(path)) as conn, conn:
        assert conn.execute('SELECT result_json FROM research_formula_runs').fetchone()[0] is None


def test_generated_contract_mirrors_runtime_formula_models_exactly():
    from research import schemas as runtime
    import schemas as mirror
    for name in ('FormulaSideDraft','FormulaRevisionDraft','FormulaCheckRequest','FormulaCheckEnvelope','FormulaRunMetadata','FormulaCheckData','FormulaCheckResponse','FormulaExecutionProvenance','FormulaResultData','FormulaResultResponse'):
        assert getattr(runtime,name).model_json_schema()==getattr(mirror,name).model_json_schema(),name
