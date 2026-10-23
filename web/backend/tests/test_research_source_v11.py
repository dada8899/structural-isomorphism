"""Real legacy-auth Source components; formal private contracts live in Main tests."""
from contextlib import closing
from functools import partial
import json,multiprocessing,sqlite3
from pathlib import Path
import pytest
from api import auth
from research import ResearchStore,ResearchRunner,source_integration
from research.source_policy import PinnedPublicTransport
from .test_private_runtime_bootstrap import roots
from .research_component_fixture import stack,BETA,after_native_commit
from .test_research_persistence import envelope,problem
from web.backend.tests.source_http_fixture import source_server,get_local
from web.backend.tests.research_component_process_fixture import reopen


def send(client,rid,suffix,payload,key=None):
    return client.post('/api/research/'+rid+'/'+suffix,json=envelope(payload),headers={'origin':BETA,'idempotency-key':key or 'source11-'+suffix})


def admitted(stack,monkeypatch):
    client,root,_=stack
    monkeypatch.setenv('STRUCTURAL_D1_PUBLIC_GET_ENABLED','false')
    data=problem();data['confirmed']=True
    created=client.post('/api/research',json=envelope({'problem':data}),headers={'origin':BETA,'idempotency-key':'source11-create'})
    assert created.status_code==200,created.text
    rid=created.json()['data']['research']['id'];payload={'input_revision':1,'expected_research_version':1,'query':'queue theory'}
    preview=send(client,rid,'source-preview',payload);assert preview.status_code==200,preview.text
    approved=send(client,rid,'source-approvals',{**payload,'confirm_external':True,'preview_digest':preview.json()['data']['preview_digest']})
    assert approved.status_code==200,approved.text
    started=send(client,rid,'source-tasks',{'input_revision':1,'expected_research_version':1,'approval_ref':approved.json()['data']['approval_ref']})
    assert started.status_code==200,started.text
    tid=started.json()['data']['task']['id']
    return client,root,rid,tid,ResearchStore(auth._store())


def test_component_actual_source_worker_and_new_process_keep_same_task_inode(stack,monkeypatch,tmp_path):
    client,root,rid,tid,store=admitted(stack,monkeypatch)
    with source_server() as (port,calls):
        transport=PinnedPublicTransport(_worker=partial(get_local,port))
        assert ResearchRunner(store,source_transport=transport).run_once(tid)=='COMPLETED'
        assert calls==['/discovery','/article']
    task_file=root/'research-locks'/('source-'+tid+'.lock')
    assert task_file.exists() and not (root/'research-locks'/(tid+'.lock')).exists()
    with store.transaction() as conn:
        row=conn.execute('SELECT * FROM research_source_resources WHERE task_id=?',(tid,)).fetchone()
        identity=json.loads(row['task_gate_identity'])
        assert identity[:2]==[task_file.stat().st_dev,task_file.stat().st_ino]
        assert conn.execute('SELECT started,task_gate_identity FROM research_source_runs').fetchone()[:]==(1,row['task_gate_identity'])
        assert conn.execute('SELECT count(*) FROM research_evidence_objects WHERE kind=\'snapshots\'').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM research_source_requests WHERE outcome=\'SUCCEEDED\'').fetchone()[0]==2
    output=tmp_path/'reopened.json';child=multiprocessing.get_context('spawn').Process(target=reopen,args=(str(store.path),tid,str(output)))
    try:
        child.start();child.join(10)
        assert not child.is_alive() and child.exitcode==0
        value=json.loads(output.read_text());assert value=={'state':'COMPLETED','identity':identity}
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()
    assert client.get('/api/research/'+rid).status_code==200


@pytest.mark.parametrize('native',['ordinary','auth_factory'])
def test_source11_native_sql_cannot_reinterpret_admission_or_reset_counters(stack,monkeypatch,native):
    _,root,_,tid,store=admitted(stack,monkeypatch)
    context=closing(sqlite3.connect(store.path,isolation_level=None)) if native=='ordinary' else store.auth_store._connection()
    with context as conn:
        conn.execute('BEGIN IMMEDIATE')
        statements=[('UPDATE research_source_runs SET started=1,task_gate_identity=? WHERE task_id=?',('[1,2,3,384,1]',tid)),
            ("UPDATE research_source_approvals SET query='forged',plan_json='{}'",()),
            ('UPDATE research_source_chains SET used=1',()),
            ("UPDATE research_source_resources SET admission_json='{}' WHERE task_id=?",(tid,))]
        for sql,args in statements:
            with pytest.raises(sqlite3.Error):conn.execute(sql,args)
        conn.rollback()
    with store.transaction() as conn:
        assert conn.execute('SELECT started,task_gate_identity FROM research_source_runs').fetchone()[:]==(0,None)
        assert conn.execute('SELECT used FROM research_source_chains').fetchone()[0]==0


def test_component_source_delete_erases_private_admission_and_retains_only_closure_binding(stack,monkeypatch):
    client,root,rid,tid,store=admitted(stack,monkeypatch)
    from research.authorization import AuthorizationGate,TaskGateLease
    with AuthorizationGate(store).source_task_gate(tid) as lease:
        identity=lease.identity
        with pytest.raises(TypeError):lease.epoch=900
        assert not hasattr(lease,'handoff')
        with pytest.raises(TypeError):TaskGateLease(None,{},False)
    removed=client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'origin':BETA})
    assert removed.status_code==200,removed.text
    with store.transaction() as conn:
        resource=conn.execute('SELECT * FROM research_source_resources WHERE task_id=?',(tid,)).fetchone()
        assert resource['admission_json'] is None and resource['state']=='closed'
        assert json.loads(resource['task_gate_identity'])==list(identity)
        assert resource['write_epoch']==2
        assert conn.execute('SELECT count(*) FROM research_source_approvals').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_evidence_objects').fetchone()[0]==0
        assert conn.execute('SELECT approval_id,fingerprint FROM research_source_runs').fetchone()[:]==(None,None)
    # Deletion does not invent execution-reaped evidence or remove the mutex.
    assert (root/'research-locks'/('source-'+tid+'.lock')).exists()
    assert client.get('/api/research/'+rid).status_code==401


def test_actual_archived10_formula_survives11_with_same_ref_time_and_typed_body(roots,monkeypatch,tmp_path):
    import os,subprocess,sys
    from research.source_guard import provision_source_v11
    from research.errors import ResearchError
    from services.auth_store import AuthStore
    from .source_v10_reference import reconstruct
    project=Path(__file__).resolve().parents[3]
    archive,problem_path,manifest_path=reconstruct(project,tmp_path/'source10')
    assert not (archive/'.git').exists()
    output=tmp_path/'old10-result.json';environment={**os.environ,'SOURCE10_ROOT':str(archive),'SOURCE10_MANIFEST':str(manifest_path),'PYTHONPATH':str(archive/'web/backend')+os.pathsep+str(archive)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:
        environment['REVIEW_SOURCE_ROOT']=str(archive)
        environment['PYTHONPATH']=str(Path(guard.__file__).resolve().parent)+os.pathsep+environment['PYTHONPATH']
    producer=Path(__file__).with_name('source_v10_history_producer.py')
    with (tmp_path/'old10-producer.log').open('wb') as log:
        made=subprocess.run([sys.executable,str(producer),str(roots),str(output),str(problem_path)],cwd=archive,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=20)
    assert made.returncode==0,(tmp_path/'old10-producer.log').read_text()
    original=json.loads(output.read_text());manifest=json.loads(manifest_path.read_text())
    assert original['source_files']=={name:entry['sha256'] for name,entry in manifest['files'].items()}
    assert original['loaded_modules']==manifest['loaded_modules']
    path=roots/'auth.sqlite3';inode=path.stat().st_ino
    with pytest.raises((RuntimeError,ResearchError)):AuthStore(path)
    upgraded=provision_source_v11(path);assert upgraded['schema_version']==11 and path.stat().st_ino==inode
    from research.plan_financial import provision_plan_v12
    assert provision_plan_v12(path)['schema_version']==12 and path.stat().st_ino==inode
    from web.backend.tests.research_component_process_fixture import archived_formula_read
    consumed=archived_formula_read(project,tmp_path,path,output)
    assert consumed['reopened']==original['result']
    assert consumed['history']['formula_check']['result_ref']==original['ref']
    assert consumed['history']['formula_check']['formula_result_recorded_at']==original['result']['metadata']['formula_result_recorded_at']
    assert consumed['refused_status']==409 and consumed['refused_code']=='SOURCE_PERMISSION_UNAVAILABLE'
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        assert conn.execute('SELECT count(*) FROM research_formula_runs').fetchone()[0]==1
        assert conn.execute('SELECT count(*) FROM research_source_resources').fetchone()[0]==0



def test_real_worker_claim_crash_reopens_same_inode_and_closes_without_refetch(stack,monkeypatch,tmp_path):
    from web.backend.tests.research_component_process_fixture import crash_after_claim
    client,root,rid,tid,store=admitted(stack,monkeypatch)
    proof=tmp_path/'claim-proof.json'
    child=multiprocessing.get_context('spawn').Process(target=crash_after_claim,args=(str(store.path),tid,str(proof)))
    try:
        child.start();child.join(10);assert not child.is_alive() and child.exitcode==81
    finally:
        if child.is_alive():child.kill();child.join(2)
        child.close()
    hit=json.loads(proof.read_text());assert hit['hits']==1 and hit['persisted']==[1]
    assert hit['pid']!=__import__('os').getpid() and hit['task_parameters']==[tid]
    with store.transaction() as conn:assert conn.execute('SELECT started FROM research_source_runs WHERE task_id=?',(tid,)).fetchone()[0]==1
    path=root/'research-locks'/('source-'+tid+'.lock');inode=path.stat().st_ino
    output=tmp_path/'closed.json';worker=multiprocessing.get_context('spawn').Process(target=reopen,args=(str(store.path),tid,str(output)))
    try:
        worker.start();worker.join(10);assert not worker.is_alive() and worker.exitcode==0
    finally:
        if worker.is_alive():worker.kill();worker.join(2)
        worker.close()
    assert json.loads(output.read_text())['state']=='FAILED' and path.stat().st_ino==inode
    with store.transaction() as conn:
        state=conn.execute('SELECT state,admission_json,write_epoch FROM research_source_resources').fetchone()
        assert state['state']=='closed' and state['admission_json'] is not None and state['write_epoch']==2
        assert conn.execute('SELECT count(*) FROM research_source_requests').fetchone()[0]==0
        assert conn.execute('SELECT stop_requested FROM research_tasks').fetchone()[0]==1


@pytest.mark.parametrize('fault',['orphan','replacement','symlink','hardlink'])
def test_task_resource_never_adopts_or_replaces_unknown_inode(stack,monkeypatch,fault):
    import os
    from research.authorization import AuthorizationGate
    _,root,_,tid,store=admitted(stack,monkeypatch)
    gate=AuthorizationGate(store);path=root/'research-locks'/('source-'+tid+'.lock')
    if fault!='orphan':
        with gate.source_task_gate(tid) as lease:original=lease.identity
        saved=path.with_suffix('.original');path.rename(saved)
    if fault=='symlink':path.symlink_to(saved)
    elif fault=='hardlink':os.link(saved,path)
    else:path.write_bytes(b'');path.chmod(0o600)
    try:
        with pytest.raises((PermissionError,OSError)):
            with gate.source_task_gate(tid):pytest.fail('unadmitted Source task resource was adopted')
        with store.transaction() as conn:
            binding=conn.execute('SELECT task_gate_identity FROM research_source_resources').fetchone()[0]
            assert binding is None if fault=='orphan' else json.loads(binding)==list(original)
            assert conn.execute('SELECT started FROM research_source_runs').fetchone()[0]==0
    finally:
        path.unlink()
        if fault!='orphan':saved.rename(path)


def test_birth_lost_commit_ack_reads_protected_binding_and_does_not_rebirth(stack,monkeypatch,tmp_path):
    from research.authorization import AuthorizationGate,_source_task_gate
    _,root,_,tid,store=admitted(stack,monkeypatch)
    with after_native_commit(store,caller=_source_task_gate.__wrapped__.__code__,
            query='SELECT task_gate_identity IS NOT NULL FROM research_source_resources WHERE task_id=?',
            parameters=(tid,),expected=(1,),proof_path=tmp_path/'birth-proof.json') as hits:
        with AuthorizationGate(store).source_task_gate(tid) as lease:identity=lease.identity
    lost=[True for hit in hits]
    assert lost==[True]
    with AuthorizationGate(store).source_task_gate(tid) as lease:assert lease.identity==identity
    assert len(list((root/'research-locks').glob('source-'+tid+'.lock')))==1


def test_native_rowid_or_unique_replace_cannot_overwrite_source_binding_even_with_forged_udf(stack,monkeypatch):
    _,_,_,tid,store=admitted(stack,monkeypatch)
    with closing(sqlite3.connect(store.path,isolation_level=None)) as conn:
        conn.execute('PRAGMA recursive_triggers=OFF')
        conn.create_function('research_source_write_allowed',4,lambda *args:1)
        for table in ('research_source_approvals','research_source_chains','research_source_runs','research_source_resources'):
            row=conn.execute('SELECT rowid,* FROM '+table).fetchone()
            columns=[r[1] for r in conn.execute('PRAGMA table_info('+table+')')]
            sql='INSERT OR REPLACE INTO '+table+'(rowid,'+','.join(columns)+') VALUES('+','.join('?' for _ in row)+')'
            with pytest.raises(sqlite3.Error):conn.execute(sql,row)
            with pytest.raises(sqlite3.Error):conn.execute('UPDATE OR REPLACE '+table+' SET rowid=rowid+1')


def test_cancel_does_not_wait_for_task_mutex_and_old_lease_cannot_publish(stack,monkeypatch):
    from research.authorization import AuthorizationGate
    from research.source_guard import worker_scope
    client,root,rid,tid,store=admitted(stack,monkeypatch)
    with AuthorizationGate(store).source_task_gate(tid) as lease:
        with store.transaction(write=True) as conn,worker_scope(conn,store,lease):
            conn.execute('UPDATE research_source_runs SET started=1 WHERE task_id=?',(tid,))
            conn.execute("UPDATE research_source_resources SET state='running' WHERE task_id=?",(tid,))
        result=send(client,rid,'cancel',{'task_id':tid,'expected_task_version':1},'source11-cancel')
        assert result.status_code==200 and result.json()['data']['execution']=='CANCELLED',result.text
        with store.transaction() as conn:
            state=conn.execute('SELECT state,admission_json,write_epoch FROM research_source_resources').fetchone()
            assert state['state']=='closed' and state['admission_json'] is not None and state['write_epoch']==2
            with pytest.raises(PermissionError):lease.require(store,conn)
        with pytest.raises(PermissionError):
            with store.transaction(write=True) as conn,worker_scope(conn,store,lease):pytest.fail('late Source write scope resurrected')
    assert (root/'research-locks'/('source-'+tid+'.lock')).exists()
    assert ResearchRunner(store).run_once(tid)=='CANCELLED'


def test_task_mutex_alone_is_neither_owner_handoff_nor_execution_closure_authority(stack,monkeypatch):
    from research.authorization import AuthorizationGate
    from research.source_guard import worker_scope
    _,_,_,tid,store=admitted(stack,monkeypatch)
    with AuthorizationGate(store).source_task_gate(tid) as task_lease:
        with pytest.raises(PermissionError):
            with store.transaction(write=True) as conn,worker_scope(conn,store,task_lease,close=True):pytest.fail('task mutex minted owner closure proof')
        with pytest.raises(AttributeError):task_lease.handoff(None,1,0)
        from research.source_guard import _scope
        with store.transaction(write=True) as conn:
            with pytest.raises(PermissionError,match='unsupported Source write operation'):
                with _scope(conn,store,'arbitrary-close',lease=task_lease,task_id=tid):pytest.fail('unknown Source operation was accepted')


def test_origin_integrity_preserves_stopped_source_read_and_older_revision_with_current_read_acl(stack,monkeypatch):
    from .test_research_paid_producers import identity
    from research.provider_evidence import read_provider_eligibility
    from research.source_guard import check_origin
    from research.errors import ResearchError
    client,root,rid,tid,store=admitted(stack,monkeypatch)
    with source_server() as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=='COMPLETED'
    with store.transaction() as conn:
        ref=conn.execute("SELECT id FROM research_evidence_objects WHERE kind='excerpts'").fetchone()[0]
        version=conn.execute('SELECT version FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    original=read_provider_eligibility(store,identity(client),rid,1,version,(ref,))
    assert original.may_send_to_provider is False
    with store.transaction(write=True) as conn:
        conn.execute('UPDATE research_tasks SET stop_requested=1 WHERE id=?',(tid,))
        conn.execute("UPDATE research_grants SET status='revoked',scopes='[]' WHERE id=(SELECT grant_id FROM research_tasks WHERE id=?)",(tid,))
    assert read_provider_eligibility(store,identity(client),rid,1,version,(ref,))==original
    assert client.get(f'/api/research/{rid}/records',params={'task_id':tid,'kind':'sources'}).status_code==200
    data=problem('new question revision');data['confirmed']=True
    revised=client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':1,'problem':data}),headers={'origin':BETA,'idempotency-key':'source11-new-question'})
    assert revised.status_code==200,revised.text
    with store.transaction() as conn:check_origin(store,conn,tid)
    assert client.get(f'/api/research/{rid}/records',params={'task_id':tid,'kind':'sources'}).status_code==200
    with store.transaction(write=True) as conn:
        conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='read')",(rid,))
    with pytest.raises(ResearchError):read_provider_eligibility(store,identity(client),rid,1,version,(ref,))
    assert client.get(f'/api/research/{rid}/records',params={'task_id':tid,'kind':'sources'}).status_code==404


@pytest.mark.parametrize('cut',['journal','consent','resource','marker','before-commit','after-commit'])
def test_source11_real_migration_death_recovers_complete10_or11_and_preserves_formula_bytes(roots,monkeypatch,tmp_path,cut):
    from .source_v10_reference import produce
    from web.backend.tests.source_v11_process_fixture import schema_kill
    from research.formula_runtime import recover_formula_journal
    from research.source_guard import provision_source_v11
    from services.auth_store import AuthStore
    from research.errors import ResearchError
    project=Path(__file__).resolve().parents[3]
    original=produce(project,tmp_path/'old-package',roots,tmp_path/'original.json')
    path=roots/'auth.sqlite3';identity=(path.stat().st_dev,path.stat().st_ino)
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        before=conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs').fetchone()
    worker=multiprocessing.get_context('spawn').Process(target=schema_kill,args=(str(path),cut))
    try:
        worker.start();worker.join(10);assert not worker.is_alive() and worker.exitcode==(82 if cut=='after-commit' else 81)
    finally:
        if worker.is_alive():worker.kill();worker.join(2)
        worker.close()
    recovered=recover_formula_journal(path)
    assert recovered['schema_version']==(11 if cut=='after-commit' else 10)
    assert recovered['current_app_compatible'] is False # Complete10/11 remain offline historical profiles.
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    if cut!='after-commit':
        with pytest.raises((RuntimeError,ResearchError)):AuthStore(path)
        provision_source_v11(path)
    from research.plan_financial import provision_plan_v12
    assert provision_plan_v12(path)['schema_version']==12
    # Historical12 is an offline profile, so inspect its native readonly image
    # without asking the current private Auth factory to admit it as Main15.
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,isolation_level=None)) as conn:
        conn.row_factory=sqlite3.Row;conn.execute('BEGIN')
        ResearchStore._check_v12(conn)
        assert tuple(conn.execute('SELECT result_ref,admission_json,receipt_json,result_json,commit_json FROM research_formula_runs').fetchone())==before
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert not conn.execute('PRAGMA foreign_key_check').fetchall()
        assert conn.execute('SELECT count(*) FROM research_source_resources').fetchone()[0]==0
        assert conn.execute('SELECT consent_origin,consent_digest FROM research_source_approvals').fetchone()[:]==(None,None)
    assert before[0]==original['ref']


def test_eleven_keeps_financial_default_deny_on_auth_factory_connections_without_scope(stack,monkeypatch):
    _,_,_,_,store=admitted(stack,monkeypatch)
    with store.auth_store._connection() as conn:
        conn.execute('BEGIN IMMEDIATE')
        with pytest.raises(sqlite3.DatabaseError):conn.execute('DELETE FROM research_cost_observations')
        conn.rollback()
