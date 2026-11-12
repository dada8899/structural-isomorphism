"""Actual HTTP manual drafts, original Source rights and immutable persistence."""
from contextlib import closing,contextmanager
from functools import partial
import copy,json,sqlite3
from uuid import uuid4
import pytest
from api import auth
from research import ResearchStore,ResearchRunner
from research.source_policy import PinnedPublicTransport
from .test_private_runtime_bootstrap import roots
from .test_private_registration import link,verify,BETA
from .test_research_source_v11 import admitted
from .test_research_persistence import problem,envelope
from web.backend.tests.source_http_fixture import source_server,get_local


@contextmanager
def _draft_history_stack(tmp_path,monkeypatch):
    import hashlib,importlib,secrets
    from pathlib import Path
    from .method_v13_reference import produce
    from .test_research_method_draft_migration import snapshot,check
    from .test_private_registration import SECRET
    from research.method_draft import provision_method_drafts_v14
    from research.financial_input import provision_financial_inputs_v15
    from fastapi.testclient import TestClient
    state=tmp_path/'state'
    for namespace in ('services.runtime_paths','web.backend.services.runtime_paths'):
        paths=importlib.import_module(namespace)
        monkeypatch.setattr(paths,'STATE_ROOT',state);monkeypatch.setattr(paths,'CACHE_ROOT',tmp_path/'cache');monkeypatch.setattr(paths,'LOG_ROOT',state/'logs')
    settings={'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':SECRET,'STRUCTURAL_SSO_SECRET':SECRET,
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
        'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false','STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'STRUCTURAL_SHARE_TOKEN_SECRET':secrets.token_urlsafe(48)}
    for key,value in settings.items():monkeypatch.setenv(key,value)
    for key in ('STRUCTURAL_DATA_DIR','STRUCTURAL_MODEL_PATH','STRUCTURAL_PRECOMPUTED_EMBEDDINGS',
        'STRUCTURAL_ARTIFACT_MANIFEST','STRUCTURAL_HISTORY_DB','STRUCTURAL_FAVORITES_PATH'):
        monkeypatch.delenv(key,raising=False)
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'old13',state,tmp_path/'original.json',mode='native')
    path=state/'auth.sqlite3';inode=(path.stat().st_dev,path.stat().st_ino)
    before13=snapshot(path);check(path,13,before13)
    assert provision_method_drafts_v14(path)['schema_version']==14
    check(path,14,before13);before14=snapshot(path)
    assert provision_financial_inputs_v15(path)['schema_version']==15
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    after15=snapshot(path);assert {name:after15[name] for name in before14}==before14
    import main
    from services import formal_admission
    mail=[];monkeypatch.setattr(auth,'_send_email',lambda to,subject,text:mail.append(text))
    assert main._IS_PROD and main.auth_api is auth
    history={'research_id':original['results'][0]['rid'],'source_task_id':original['source_task'],
        'plan_result_ref':original['results'][0]['ref'],
        'plan_result_sha256':hashlib.sha256(json.dumps(original['results'][0]['result'],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()}
    with TestClient(main.app,base_url=BETA) as client:
        assert formal_admission.require(main.app,'research_basic') is None
        assert verify(client,link(client,mail)).status_code==200
        with ResearchStore(auth._store()).transaction() as conn:ResearchStore._check_v15(conn)
        yield client,state,mail,history
    assert (path.stat().st_dev,path.stat().st_ino)==inode


@pytest.fixture
def stack(tmp_path,monkeypatch):
    with _draft_history_stack(tmp_path,monkeypatch) as value:yield value


def prepared(stack,monkeypatch):
    client,root,_mail,history=stack
    rid=history['research_id'];tid=history['source_task_id'];store=ResearchStore(auth._store())
    with store.transaction() as conn:
        task=conn.execute('SELECT research_id,input_revision FROM research_tasks WHERE id=?',(tid,)).fetchone()
        assert tuple(task)==(rid,1)
        row=conn.execute("SELECT payload FROM research_evidence_objects WHERE kind='excerpts' AND task_id=?",(tid,)).fetchone()
        excerpt=json.loads(row[0]);snapshot=json.loads(conn.execute('SELECT payload FROM research_evidence_objects WHERE id=?',(excerpt['snapshot_id'],)).fetchone()[0])
    current=client.get('/api/research/'+rid);assert current.status_code==200,current.text
    assert current.json()['data']['current_problem']['revision']==2
    version=current.json()['data']['research_version']
    ref={'excerpt_id':excerpt['id'],'source_revision':snapshot['source_revision'],'content_digest':snapshot['extracted_digest'],'start':excerpt['start'],'end':excerpt['end']}
    data={'input_revision':2,'expected_research_version':version,'excerpt_refs':[ref],
            'origin':{'kind':'user_proposed','label':'Queue observation','description':'A proposed measurement method, not a verified technique.'},
            'method':'Compare inflow and time in process.','mapping':['Requests correspond to work items.'],
            'nontransferable':['The two systems do not share a physical mechanism.'],'competing_explanations':['A changing arrival rate may explain the apparent delay.'],
            'test_plan':{'question':'Does the delay persist at a fixed arrival rate?','measurement':'Record counts and timestamps.','primary_outcome':'Median wait.','falsification':'No increase at the same arrival rate.','stop_rule':'Stop if timestamps are incomplete.'}}
    return client,root,rid,tid,store,data


def post(client,rid,data,key='method-save'):
    return client.post('/api/research/'+rid+'/method-drafts',json={'schema_version':'structure-research-v1','contract_revision':'method-draft-v1','data':data},headers={'origin':BETA,'idempotency-key':key})


def test_old_source_current_manual_draft_actual_api_save_reopen_and_ref_only_cache(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    value=saved.json()['data'];ref=value['metadata']['draft_ref']
    assert value['metadata']['input_revision']==2 and value['metadata']['validation_status']=='unverified'
    assert value['metadata']['execution_status']=='not_executed'
    assert value['content']['sources'][0]['input_revision']==1 and value['content']['sources'][0]['task_id']==tid
    assert value['content']['origin']['mode']=='user_proposed'
    assert client.get(f'/api/research/{rid}/method-drafts/{ref}').json()==saved.json()
    assert post(client,rid,data).json()==saved.json()
    assert client.get(f'/api/research/{rid}/method-drafts').json()['data']['items']==[value['metadata']]
    with ResearchStore(auth._store()).transaction() as conn:
        cached=json.loads(conn.execute("SELECT result_json FROM research_idempotency WHERE operation='method-draft'").fetchone()[0])
        assert cached=={'draft_ref':ref}
        assert conn.execute('SELECT count(*) FROM research_method_drafts').fetchone()[0]==1
    assert post(client,rid,{**data,'method':'Different body'}).status_code==409
    assert post(client,rid,data,'new-key-stale-version').status_code==409


@pytest.mark.parametrize('change',['hash','offset','snapshot_revision','foreign_excerpt','extra_authority','duplicate','kb_unavailable','fake_plan'])
def test_invalid_dependency_origin_or_authority_cannot_commit(stack,monkeypatch,change):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    if change=='hash':data['excerpt_refs'][0]['content_digest']='0'*64
    elif change=='offset':data['excerpt_refs'][0]['start']+=1
    elif change=='snapshot_revision':data['excerpt_refs'][0]['source_revision']+=1
    elif change=='foreign_excerpt':data['excerpt_refs'][0]['excerpt_id']=str(uuid4())
    elif change=='extra_authority':data['owner']=str(uuid4())
    elif change=='duplicate':data['excerpt_refs']*=2
    elif change=='kb_unavailable':data['origin']={'kind':'kb_record','artifact_id':'missing','record_id':'missing','record_digest':'0'*64}
    else:data['origin']={'kind':'plan_lead','plan_contract':'funded-plan-v2','result_ref':str(uuid4()),'candidate_index':0,'lead_index':0}
    response=post(client,rid,data)
    assert response.status_code in (404,409,422,503),response.text
    if change=='kb_unavailable':assert response.json()['error']['code']=='CATALOG_UNAVAILABLE'
    with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_method_drafts').fetchone()[0]==0


def test_history_and_same_key_replay_recheck_current_read_permission(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    ref=saved.json()['data']['metadata']['draft_ref']
    # Stop affects execution, not already persisted read rights.
    with store.transaction(write=True) as conn:conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(tid,))
    assert client.get(f'/api/research/{rid}/method-drafts/{ref}').status_code==200
    with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(rid,))
    for response in (client.get(f'/api/research/{rid}/method-drafts/{ref}'),client.get(f'/api/research/{rid}/method-drafts'),post(client,rid,data)):
        assert response.status_code==404,response.text
        assert 'Compare inflow' not in response.text


def test_draft_native_writes_rowid_replace_and_fake_action_are_denied(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    for connection in (lambda:closing(sqlite3.connect(store.path,isolation_level=None)),store.auth_store._connection):
        with connection() as conn:
            conn.execute('PRAGMA recursive_triggers=OFF');conn.execute('BEGIN IMMEDIATE')
            for sql in ("UPDATE research_method_drafts SET content_digest='"+'0'*64+"'",'DELETE FROM research_method_drafts','INSERT OR REPLACE INTO research_method_drafts SELECT * FROM research_method_drafts','INSERT OR REPLACE INTO research_method_drafts SELECT rowid,* FROM research_method_drafts'):
                with pytest.raises(sqlite3.Error):conn.execute(sql)
            conn.rollback()
            conn.create_function('research_method_draft_allowed',2,lambda *_:1)
            conn.execute('BEGIN IMMEDIATE')
            columns=[r[1] for r in conn.execute('PRAGMA table_info(research_method_drafts)')]
            projection=','.join("'"+str(uuid4())+"'" if column=='draft_ref' else column for column in columns)
            with pytest.raises(sqlite3.Error):conn.execute('INSERT OR REPLACE INTO research_method_drafts(rowid,'+','.join(columns)+') SELECT rowid,'+projection+' FROM research_method_drafts')
            conn.rollback()
    from research.method_draft import save
    from research.method_draft_schemas import MethodDraftRequest
    from research.service import ResearchService
    from .test_research_paid_producers import identity
    with pytest.raises(PermissionError):save(ResearchService(store),identity(client),rid,MethodDraftRequest.model_validate(data),'forged',None)
    assert client.get(f"/api/research/{rid}/method-drafts/{saved.json()['data']['metadata']['draft_ref']}").status_code==200


def test_actual_native_plan_lead_is_bound_without_promoting_literature_or_formula(stack,monkeypatch):
    from .test_research_funded_plan import provider
    from .test_research_native_plan import installed,post as native_post
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    # Explicitly confirm the current observation, preserving the original Source.
    observation=problem('A self observation about changing request arrival and waiting.');observation['confirmed']=True
    revised=client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':2,'problem':observation}),headers={'origin':BETA,'idempotency-key':'method-plan-observation'})
    assert revised.status_code==200,revised.text
    version=revised.json()['data']['research_version']
    with provider() as (server,calls),installed((client,root,rid,store),server):
        preview=native_post(client,rid,'plan-previews',{'input_revision':3,'expected_research_version':version,'observation_source':'own_observation','declaration_status':'self_declared'},'method-plan-preview')
        assert preview.status_code==200,preview.text
        approved={key:preview.json()['data'][key] for key in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};approved['confirm_outbound']=True
        confirmed=native_post(client,rid,'plan-approvals',approved,'method-plan-confirm');assert confirmed.status_code==200,confirmed.text
        plan_ref=confirmed.json()['data']['result_ref'];ResearchRunner(store).run_once(confirmed.json()['data']['task_id'])
        assert [call[0] for call in calls]==['GET','POST']
        version=client.get('/api/research/'+rid).json()['data']['research_version']
        data.update(input_revision=3,expected_research_version=version,origin={'kind':'plan_lead','plan_contract':'funded-plan-v2','result_ref':plan_ref,'candidate_index':0,'lead_index':0})
        saved=post(client,rid,data);assert saved.status_code==200,saved.text
        origin=saved.json()['data']['content']['origin']
        assert origin['mode']=='controlled_fixture' and origin['producer']=='core-controlled-native-v1'
        assert origin['lead']=='queueing model' and origin['verification']=='unverified'
        assert saved.json()['data']['metadata']['validation_status']=='unverified'
        assert len(calls)==2
        data['origin']['lead_index']=1
        data['expected_research_version']+=1
        assert post(client,rid,data,'method-out-of-range-lead').status_code==422
        assert len(calls)==2


def test_formula_link_preserves_original_check_status_and_avoids_ast_copy(stack,monkeypatch):
    from .test_research_formula_lifecycle import formula_problem
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    revised=client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':2,'problem':formula_problem()}),headers={'origin':BETA,'idempotency-key':'method-formula-observation'})
    assert revised.status_code==200,revised.text
    value=revised.json()['data'];snapshot=value['current_problem']['formula_snapshot']
    checked=client.post(f'/api/research/{rid}/formula-checks',json=envelope({'input_revision':3,'expected_research_version':value['research_version'],'formula_digest':snapshot['formula_digest'],'confirm_formula_input':True}),headers={'origin':BETA,'idempotency-key':'method-formula-check'})
    assert checked.status_code==200,checked.text
    ref=checked.json()['data']['result_ref'];original=client.get(f'/api/research/{rid}/formula-results/{ref}').json()['data']
    data.update(input_revision=3,expected_research_version=client.get('/api/research/'+rid).json()['data']['research_version'],formula_result_ref=ref)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    body=saved.json()['data'];assert body['metadata']['validation_status']=='unverified'
    assert body['content']['formula']['outcomes']==[{key:item[key] for key in ('check_kind','status','relation')} for item in original['result']['outcomes']]
    assert 'checked_AST' not in json.dumps(body['content']['formula'])
    assert body['content']['formula']['metadata']['formula_result_recorded_at']==original['metadata']['formula_result_recorded_at']


def test_actual_account_delete_erases_draft_and_old_ref_cannot_return_after_reregister(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    ref=saved.json()['data']['metadata']['draft_ref']
    deleted=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert deleted.status_code==200,deleted.text
    with closing(sqlite3.connect(store.path)) as conn:assert conn.execute('SELECT count(*) FROM research_method_drafts').fetchone()[0]==0
    assert verify(client,link(client,stack[2])).status_code==200
    assert client.get(f'/api/research/{rid}/method-drafts/{ref}').status_code==404


def _fresh_draft_history_probe(tmp_path):
    import importlib,multiprocessing,os,secrets
    from pathlib import Path
    from .method_v13_reference import produce
    from .test_research_method_draft_migration import snapshot,check
    from .method_draft_process_fixture import read_draft
    from .test_private_registration import SECRET
    from research.method_draft import provision_method_drafts_v14
    from research.financial_input import provision_financial_inputs_v15
    from fastapi.testclient import TestClient
    tmp_path=Path(tmp_path)
    state=tmp_path/'state'
    for namespace in ('services.runtime_paths','web.backend.services.runtime_paths'):
        paths=importlib.import_module(namespace)
        paths.STATE_ROOT=state;paths.CACHE_ROOT=tmp_path/'cache';paths.LOG_ROOT=state/'logs'
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':SECRET,'STRUCTURAL_SSO_SECRET':SECRET,
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
        'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false','STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'STRUCTURAL_SHARE_TOKEN_SECRET':secrets.token_urlsafe(48)})
    for key in ('STRUCTURAL_DATA_DIR','STRUCTURAL_MODEL_PATH','STRUCTURAL_PRECOMPUTED_EMBEDDINGS',
        'STRUCTURAL_ARTIFACT_MANIFEST','STRUCTURAL_HISTORY_DB','STRUCTURAL_FAVORITES_PATH'):
        os.environ.pop(key,None)
    original=produce(Path(__file__).resolve().parents[3],tmp_path/'old13',state,tmp_path/'original.json',mode='native')
    path=state/'auth.sqlite3';inode=(path.stat().st_dev,path.stat().st_ino)
    before13=snapshot(path);check(path,13,before13)
    assert provision_method_drafts_v14(path)['schema_version']==14
    check(path,14,before13);before14=snapshot(path)
    assert provision_financial_inputs_v15(path)['schema_version']==15
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    after15=snapshot(path)
    assert {name:after15[name] for name in before14}==before14
    import main
    from services import formal_admission
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text)
    assert main._IS_PROD and main.auth_api is auth
    with TestClient(main.app,base_url=BETA) as client:
        assert formal_admission.require(main.app,'research_basic') is None
        assert verify(client,link(client,mail)).status_code==200
        rid=original['results'][0]['rid'];tid=original['source_task'];root=state
        store=ResearchStore(auth._store())
        with store.transaction() as conn:
            ResearchStore._check_v15(conn)
            task=conn.execute('SELECT research_id,input_revision FROM research_tasks WHERE id=?',(tid,)).fetchone()
            assert tuple(task)==(rid,1)
            assert conn.execute('SELECT current_revision FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==2
            row=conn.execute("SELECT payload FROM research_evidence_objects WHERE kind='excerpts' AND task_id=?",(tid,)).fetchone()
            excerpt=json.loads(row[0]);snapshot_value=json.loads(conn.execute('SELECT payload FROM research_evidence_objects WHERE id=?',(excerpt['snapshot_id'],)).fetchone()[0])
        current=client.get('/api/research/'+rid);assert current.status_code==200,current.text
        assert current.json()['data']['current_problem']['revision']==2
        version=current.json()['data']['research_version']
        ref={'excerpt_id':excerpt['id'],'source_revision':snapshot_value['source_revision'],'content_digest':snapshot_value['extracted_digest'],'start':excerpt['start'],'end':excerpt['end']}
        data={'input_revision':2,'expected_research_version':version,'excerpt_refs':[ref],
                'origin':{'kind':'user_proposed','label':'Queue observation','description':'A proposed measurement method, not a verified technique.'},
                'method':'Compare inflow and time in process.','mapping':['Requests correspond to work items.'],
                'nontransferable':['The two systems do not share a physical mechanism.'],'competing_explanations':['A changing arrival rate may explain the apparent delay.'],
                'test_plan':{'question':'Does the delay persist at a fixed arrival rate?','measurement':'Record counts and timestamps.','primary_outcome':'Median wait.','falsification':'No increase at the same arrival rate.','stop_rule':'Stop if timestamps are incomplete.'}}
        saved=post(client,rid,data);assert saved.status_code==200,saved.text
        ref=saved.json()['data']['metadata']['draft_ref']
        revised=client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':2,'problem':problem('A further observation kept separate from the old draft.')}),headers={'origin':BETA,'idempotency-key':'method-further-revision'})
        assert revised.status_code==200,revised.text
        expected=client.get(f'/api/research/{rid}/method-drafts/{ref}').json()
        assert expected['data']['metadata']['is_historical'] is True
        assert expected['data']['content']==saved.json()['data']['content']
        assert expected['data']['metadata']['created_at']==saved.json()['data']['metadata']['created_at']
    assert (path.stat().st_dev,path.stat().st_ino)==inode
    output=tmp_path/'reopened.json';child=multiprocessing.get_context('spawn').Process(target=read_draft,args=(str(store.path),rid,ref,str(output)))
    try:
        child.start();child.join(15);assert not child.is_alive() and child.exitcode==0
        assert json.loads(output.read_text())==expected
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()


def test_fresh_process_reopens_original_draft_ref_time_and_historical_body(tmp_path):
    from pathlib import Path
    from .research_process_fixture import _run_owned_probe
    source=Path(__file__).resolve().parents[3]
    program=("import sys\nfrom pathlib import Path\n"
        +"sys.path[:0]="+repr([str(source/'web/backend'),str(source)])+"\n"
        +"from web.backend.tests.test_research_method_drafts import _fresh_draft_history_probe\n"
        +"_fresh_draft_history_probe(Path("+repr(str(tmp_path))+"))\n")
    result=_run_owned_probe(program,cwd=tmp_path)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('damage',['raw_hash','licence','missing_snapshot'])
def test_saved_body_and_ref_only_replay_cannot_resurrect_corrupt_or_unreadable_source(stack,monkeypatch,damage):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    ref=saved.json()['data']['metadata']['draft_ref']
    from research.evidence_schemas import sha256
    # Explicit offline corruption, restoring every exact guard before reads.
    # Ordinary SQL denial remains covered separately; no success authority is minted.
    with closing(sqlite3.connect(store.path,isolation_level=None)) as conn:
        rows=conn.execute("SELECT name,sql FROM sqlite_schema WHERE type='trigger' AND tbl_name='research_evidence_objects'").fetchall()
        conn.execute('BEGIN IMMEDIATE')
        try:
            for name,_ in rows:conn.execute('DROP TRIGGER "'+name+'"')
            snapshot=conn.execute("SELECT id,payload FROM research_evidence_objects WHERE task_id=? AND kind='snapshots'",(tid,)).fetchone()
            if damage=='raw_hash':conn.execute('UPDATE research_evidence_objects SET raw=? WHERE id=?',(b'changed original bytes',snapshot[0]))
            elif damage=='missing_snapshot':conn.execute('DELETE FROM research_evidence_objects WHERE id=?',(snapshot[0],))
            else:
                value=json.loads(snapshot[1]);value['licence']={'status':'denied','private_cache':False,'display_excerpt':False,'export_excerpt':False,'basis':'Permission withdrawn in this synthetic fault.'}
                encoded=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
                conn.execute('UPDATE research_evidence_objects SET payload=?,payload_digest=? WHERE id=?',(encoded,sha256(encoded.encode()),snapshot[0]))
            for _,sql in rows:conn.execute(sql)
            conn.commit()
        except BaseException:conn.rollback();raise
    for response in (client.get(f'/api/research/{rid}/method-drafts/{ref}'),client.get(f'/api/research/{rid}/method-drafts'),post(client,rid,data)):
        assert response.status_code in (404,409),response.text
        assert 'Compare inflow' not in response.text and 'Waiting time depends' not in response.text


def test_cross_research_and_other_registered_account_cannot_reuse_selected_source_or_ref(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    ref=saved.json()['data']['metadata']['draft_ref']
    made=client.post('/api/research',json=envelope({'problem':problem('Another separate research question.')}),headers={'origin':BETA,'idempotency-key':'method-other-research'})
    assert made.status_code==200,made.text
    other=made.json()['data']['research']['id']
    assert post(client,other,{**data,'input_revision':1,'expected_research_version':1},'method-foreign-source').status_code==409
    assert client.get(f'/api/research/{other}/method-drafts/{ref}').status_code==404
    assert verify(client,link(client,stack[2],'other@example.invalid')).status_code==200
    for response in (client.get(f'/api/research/{rid}/method-drafts/{ref}'),client.get(f'/api/research/{rid}/method-drafts'),post(client,rid,data)):
        assert response.status_code==404,response.text


def test_expired_actual_owner_lease_cannot_commit_a_draft(stack,monkeypatch):
    from contextlib import contextmanager
    from research.authorization import AuthorizationGate
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    original=AuthorizationGate.owner_gate
    @contextmanager
    def expired(gate,pid):
        with original(gate,pid) as lease:
            lease._deactivate()
            yield lease
    monkeypatch.setattr(AuthorizationGate,'owner_gate',expired)
    response=post(client,rid,data)
    assert response.status_code==409,response.text
    with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_method_drafts').fetchone()[0]==0


def test_new_refs_supersede_without_mutating_body_and_history_pages_are_bounded(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    first=post(client,rid,data);assert first.status_code==200,first.text
    ref=first.json()['data']['metadata']['draft_ref']
    second=post(client,rid,{**data,'expected_research_version':data['expected_research_version']+1,'supersedes_ref':ref,'method':'A second explicit manual proposal.'},'method-save-next')
    assert second.status_code==200,second.text
    next_ref=second.json()['data']['metadata']['draft_ref'];assert next_ref!=ref
    assert client.get(f'/api/research/{rid}/method-drafts/{ref}').json()==first.json()
    page=client.get(f'/api/research/{rid}/method-drafts',params={'limit':1});assert page.status_code==200
    page=page.json()['data'];assert len(page['items'])==1 and page['next_cursor']
    rest=client.get(f'/api/research/{rid}/method-drafts',params={'limit':1,'cursor':page['next_cursor']}).json()['data']
    assert len(rest['items'])==1 and rest['next_cursor'] is None
    assert {page['items'][0]['draft_ref'],rest['items'][0]['draft_ref']}=={ref,next_ref}
    assert client.get(f'/api/research/{rid}/method-drafts',params={'limit':21}).status_code==422
    assert client.get(f'/api/research/{rid}/method-drafts',params={'cursor':str(uuid4())}).status_code==404


def test_method_draft_public_models_exactly_match_runtime_contract():
    import schemas
    from research import method_draft_schemas
    for name in ('MethodDraftEnvelope','MethodDraftResponse','MethodDraftHistoryResponse'):
        assert getattr(schemas,name).model_json_schema()==getattr(method_draft_schemas,name).model_json_schema()


def test_reader_rejects_current_control_rollback_instead_of_trusting_self_consistent_body(stack,monkeypatch):
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    saved=post(client,rid,data);assert saved.status_code==200,saved.text
    ref=saved.json()['data']['metadata']['draft_ref']
    with store.transaction(write=True) as conn:conn.execute('UPDATE research_controls SET version=? WHERE id=?',(data['expected_research_version'],rid))
    response=client.get(f'/api/research/{rid}/method-drafts/{ref}')
    assert response.status_code==404 and 'Compare inflow' not in response.text


def _accepted_receipt_history_probe(tmp_path):
    from pathlib import Path
    from research.authorization import AuthorizationGate
    from fastapi.testclient import TestClient
    from services import formal_admission
    with pytest.MonkeyPatch.context() as monkeypatch:
        with _draft_history_stack(Path(tmp_path),monkeypatch) as stack:
            client,root,rid,tid,store,data=prepared(stack,monkeypatch)
            cookie=client.cookies.get('phase_session')
        with closing(sqlite3.connect(store.path.as_uri()+'?mode=ro',uri=True)) as conn:before=conn.serialize()
        inode=(store.path.stat().st_dev,store.path.stat().st_ino);opened=[];native=sqlite3.connect
        with monkeypatch.context() as observe:
            def connect(*args,**kwargs):
                conn=native(*args,**kwargs);opened.append((args,kwargs,conn));return conn
            observe.setattr(sqlite3,'connect',connect)
            gate=store.auth_store.owner_gate_id('fresh@example.invalid')
            expected=store.auth_store.expected_owner_gate_identity(gate)
            with AuthorizationGate(store).owner_gate_id(gate) as lease:assert lease.identity[:2]==expected
            assert opened and all(args[0]==store.path.as_uri()+'?mode=ro' and kwargs.get('uri') is True for args,kwargs,_ in opened)
            for _,_,conn in opened:
                with pytest.raises(sqlite3.ProgrammingError):conn.execute('SELECT 1')
        with closing(native(store.path.as_uri()+'?mode=ro',uri=True)) as conn:assert conn.serialize()==before
        assert (store.path.stat().st_dev,store.path.stat().st_ino)==inode
        import main
        with TestClient(main.app,base_url=BETA) as client:
            assert formal_admission.require(main.app,'research_basic') is None
            client.cookies.set('phase_session',cookie)
            saved=post(client,rid,data);assert saved.status_code==200,saved.text
            assert client.get(f"/api/research/{rid}/method-drafts/{saved.json()['data']['metadata']['draft_ref']}").json()==saved.json()


def test_current14_accepted_receipt_helper_is_native_readonly_and_draft_still_saves(tmp_path):
    from pathlib import Path
    from .research_process_fixture import _run_owned_probe
    source=Path(__file__).resolve().parents[3]
    program=("import sys\nfrom pathlib import Path\n"
        +"sys.path[:0]="+repr([str(source/'web/backend'),str(source)])+"\n"
        +"from web.backend.tests.test_research_method_drafts import _accepted_receipt_history_probe\n"
        +"_accepted_receipt_history_probe(Path("+repr(str(tmp_path))+"))\n")
    result=_run_owned_probe(program,cwd=tmp_path)
    assert result.returncode==0,result.stderr


def test_stored_native_plan_lead_consumption_preserves_provenance_and_current_read_permission(stack,monkeypatch):
    import hashlib
    from research.provider_schemas import canonical,digest
    from research.plan_native_financial import NAMES
    client,root,rid,tid,store,data=prepared(stack,monkeypatch)
    plan_ref=stack[3]['plan_result_ref'];path='/api/research/'+rid+'/plan-results/'+plan_ref
    original=client.get(path);assert original.status_code==200,original.text
    assert hashlib.sha256(json.dumps(original.json(),sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()==stack[3]['plan_result_sha256']
    content=original.json()['data']['content'];candidate=content['proposal']['candidates'][0]
    assert len(candidate['method_leads'])==1
    tables=('research_funding_accounts','research_project_budgets','research_reservations','research_plan_dispatches',*NAMES,'research_tasks')
    def ledger():
        with store.transaction() as conn:
            return {name:[tuple(row) for row in conn.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in tables}
    before=ledger()
    data['origin']={'kind':'plan_lead','plan_contract':'funded-plan-v2','result_ref':plan_ref,'candidate_index':0,'lead_index':0}
    saved=post(client,rid,data,'stored-native-lead');assert saved.status_code==200,saved.text
    value=saved.json()['data'];origin=value['content']['origin']
    assert origin['result_ref']==plan_ref and origin['lead']==candidate['method_leads'][0]
    assert origin['result_digest']==digest(canonical(content)) and origin['input_revision']==content['input_revision']
    assert origin['mode']=='controlled_fixture' and origin['producer']=='core-controlled-native-v1'
    assert origin['verification']=='unverified' and value['metadata']['validation_status']=='unverified'
    assert value['metadata']['execution_status']=='not_executed'
    draft_ref=value['metadata']['draft_ref']
    assert client.get(f'/api/research/{rid}/method-drafts/{draft_ref}').json()==saved.json()
    assert post(client,rid,data,'stored-native-lead').json()==saved.json()
    invalid={**data,'expected_research_version':client.get('/api/research/'+rid).json()['data']['research_version'],
        'origin':{**data['origin'],'lead_index':1}}
    assert post(client,rid,invalid,'stored-native-lead-out-of-range').status_code==422
    assert verify(client,link(client,stack[2],'other@example.invalid')).status_code==200
    assert client.get(path).status_code==404
    assert post(client,rid,data,'stored-native-lead').status_code==404
    assert verify(client,link(client,stack[2])).status_code==200
    with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(rid,))
    for response in (client.get(path),client.get(f'/api/research/{rid}/method-drafts/{draft_ref}'),post(client,rid,data,'stored-native-lead')):
        assert response.status_code==404,response.text
        assert 'queueing model' not in response.text and 'Compare inflow' not in response.text
    assert ledger()==before
