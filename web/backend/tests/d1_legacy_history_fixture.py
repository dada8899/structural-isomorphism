"""Stopped-service R10 history followed by real maintenance and an R14 reader.

The child owns a fresh, never-captured development store. Only that old,
unprotected schema receives the supported historical fingerprint fixture.
Current R14 only reads this history; no Main or new Source sender is admitted.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from uuid import uuid4


def _old_history(root, state, manifest_path, current, mode, output):
    from functools import partial
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    manifest = json.loads(manifest_path.read_text())['files']
    loaded = runpy.run_path(str(current/'web/backend/tests/source_v10_history_producer.py'),
                           run_name='history_source_observer')['loaded']
    loaded(root, manifest)
    # The wire fixture uses stdlib only; no current production module enters
    # the frozen application's import closure.
    wire_path = current/'web/backend/tests/source_http_fixture.py'
    # A normal fixed-path import remains resolvable by the real spawn sender.
    # Only this checkout's test directory is exposed, not its production root.
    sys.path.append(str(wire_path.parent))
    import source_http_fixture as wire
    assert Path(wire.__file__).resolve()==wire_path
    from api import auth, research
    auth._send_email=lambda *_args:None
    from research.runner import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    from research.store import ResearchStore
    os.environ.update({'STRUCTURAL_ENV':'test','AUTH_DATA_DIR':str(state),
        'AUTH_ENABLED':'true','AUTH_DEV_MODE':'true','AUTH_LINK_BASE_URL':'http://testserver',
        'JWT_SECRET':'research-synthetic-auth-secret-32-characters',
        'STRUCTURAL_SSO_SECRET':'research-synthetic-sso-secret-32-characters',
        'STRUCTURAL_RESEARCH_ENABLED':'true','STRUCTURAL_D1_SOURCES_ENABLED':'true',
        'STRUCTURAL_D1_PUBLIC_GET_ENABLED':'false','ADMIN_NOTIFICATION_EMAIL':'',
        'STRUCTURAL_SSO_DATA_DIR':str(state),'STRUCTURAL_SSO_BETA_ORIGIN':'http://testserver',
        'STRUCTURAL_SSO_PHASE_ORIGIN':'http://phase.test',
        'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4})
    application = FastAPI();application.include_router(auth.router,prefix='/api')
    application.include_router(research.router,prefix='/api')
    def post(client, path, data):
        return client.post(path,json={'schema_version':'structure-research-v1',
            'contract_revision':'b1-candidate-01','data':data},
            headers={'Origin':'http://testserver','Idempotency-Key':str(uuid4())})
    def start(client, rid, expected=200):
        view=client.get('/api/research/'+rid).json()['data']
        payload={'input_revision':view['current_problem']['revision'],
            'expected_research_version':view['research_version'],'query':'queue theory'}
        preview=post(client,f'/api/research/{rid}/source-preview',payload)
        assert preview.status_code==200,preview.text
        approved=post(client,f'/api/research/{rid}/source-approvals',{
            **payload,'preview_digest':preview.json()['data']['preview_digest'],'confirm_external':True})
        assert approved.status_code==200,approved.text
        response=post(client,f'/api/research/{rid}/source-tasks',{
            **{key:payload[key] for key in ('input_revision','expected_research_version')},
            'approval_ref':approved.json()['data']['approval_ref']})
        assert response.status_code==expected,response.text
        return response.json()['data']['task']['id'] if expected==200 else response
    problem={'entry':'phenomenon','original_input':'合成排队问题：午间等待时间为什么增加？',
        'objective':'缩短合成等待时间','summary':'合成排队现象与等待时间的结构描述',
        'variables':[],'constraints':['仅为离线测试'],'unknowns':['到达规律尚未确认'],'confirmed':True}
    loaded(root, manifest)
    with TestClient(application) as client:
        requested=client.post('/api/auth/request-link',json={'email':'research-a@example.test'},headers={'Origin':'http://testserver'})
        assert requested.status_code==200,requested.text
        verified=client.post('/api/auth/verify',json={'token':requested.json()['dev_token']},headers={'Origin':'http://testserver'})
        assert verified.status_code==200,verified.text
        created=post(client,'/api/research',{'problem':problem})
        assert created.status_code==200,created.text
        rid=created.json()['data']['research']['id'];first=start(client,rid)
        metadata=json.loads(wire.METADATA)
        if mode=='unknown':metadata['message']['items']=[]
        with wire.source_server(metadata=json.dumps(metadata).encode()) as (port, first_calls):
            result=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(wire.get_local,port))).run_once(first)
            assert result=='COMPLETED'
            assert len(first_calls)==(2 if mode=='quota' else 1)
        changed=dict(problem,summary=('历史候选链模拟：仅本地摘要变化而查询不变' if mode=='quota' else '旧候选第二条链：同一实际查询，仅本地摘要不同'))
        assert post(client,f'/api/research/{rid}/revisions',{'expected_revision':1,'problem':changed}).status_code==200
        second=start(client,rid)
        with wire.source_server() as (port, second_calls):
            result=ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(wire.get_local if mode=='quota' else wire.drop_after_response,port))).run_once(second)
            assert result==('COMPLETED' if mode=='quota' else 'FAILED')
            assert second_calls==(['/discovery','/article'] if mode=='quota' else ['/discovery'])
    path=state/'auth.sqlite3'
    with ResearchStore(auth._store()).transaction(write=True) as conn:
        assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==10
        ResearchStore._check_v10(conn)
        chosen=conn.execute('SELECT chain_id FROM research_source_runs WHERE task_id=?',(first,)).fetchone()[0]
        other=str(uuid4()) if mode=='quota' else 'ffffffff-ffff-4fff-bfff-ffffffffffff'
        if mode=='unknown':assert chosen<other
        observed={row['id']:dict(row) for row in conn.execute('SELECT * FROM research_source_requests')}
        # Exact supported old persisted shape, before Source write guards exist.
        for index,tid in enumerate((first,second)):
            approval=conn.execute('SELECT a.* FROM research_source_approvals a JOIN research_source_runs r ON r.approval_id=a.id WHERE r.task_id=?',(tid,)).fetchone()
            legacy=hashlib.sha256(json.dumps({'problem_digest':approval['problem_digest'],'query':'queue theory',
                'operation_family':'crossref-plos-method-get'},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            chain_id=chosen if index==0 else other;used=2 if mode=='quota' else 1
            if index==0:conn.execute('UPDATE research_source_chains SET fingerprint=?,used=? WHERE id=?',(legacy,used,chain_id))
            else:
                conn.execute('INSERT INTO research_source_chains VALUES(?,?,?,?,?)',(chain_id,approval['principal_id'],rid,legacy,used))
                conn.execute('UPDATE research_source_requests SET chain_id=?,ordinal=ordinal-? WHERE task_id=?',(chain_id,used,tid))
            conn.execute('UPDATE research_source_runs SET fingerprint=?,chain_id=? WHERE task_id=?',(legacy,chain_id,tid))
            conn.execute('UPDATE research_source_approvals SET fingerprint=? WHERE id=?',(legacy,approval['id']))
        unknown=dict(conn.execute('SELECT * FROM research_source_requests WHERE task_id=?',(second,)).fetchone()) if mode=='unknown' else None
        if unknown:assert unknown['outcome']=='UNKNOWN' and unknown['execution_closed']==1
        for row in conn.execute('SELECT * FROM research_source_requests'):
            # Only chain/ordinal define the old supported grouping shape;
            # no actual outcome, time, closure, dispatch or identity is edited.
            assert {key:row[key] for key in row.keys() if key not in ('chain_id','ordinal')}=={
                key:value for key,value in observed[row['id']].items() if key not in ('chain_id','ordinal')}
    third=None;third_calls=[]
    with TestClient(application) as continuation:
        continuation.cookies.update(client.cookies)
        view=continuation.get('/api/research/'+rid).json()['data']
        assert view['source_quota']['used']==(4 if mode=='quota' else 2)
        if mode=='quota':
            refused=start(continuation,rid,expected=429)
            assert refused.status_code==429 and len(first_calls)+len(second_calls)==4,refused.text
        else:
            third=start(continuation,rid)
            with wire.source_server() as (port,third_calls):
                assert ResearchRunner(ResearchStore(auth._store()),source_transport=PinnedPublicTransport(_worker=partial(wire.get_local,port))).run_once(third)=='COMPLETED'
                assert second_calls+third_calls==['/discovery','/discovery','/article']
            with ResearchStore(auth._store()).transaction() as conn:
                request=conn.execute("SELECT chain_id,prior_dispatch_id,started_at FROM research_source_requests WHERE task_id=? AND semantic='discover_sources'",(third,)).fetchone()
                assert request['chain_id']==chosen and unknown['chain_id']==other
                assert request['prior_dispatch_id']==unknown['dispatch_id'] and request['started_at']>unknown['started_at']
                assert dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?',(unknown['id'],)).fetchone())==unknown
                assert conn.execute('SELECT sum(used) FROM research_source_chains').fetchone()[0]==4
            view=continuation.get('/api/research/'+rid).json()['data']
            assert view['source_quota']['used']==4 and view['source_quota']['unknown_closed']==1
    with ResearchStore(auth._store()).transaction() as conn:
        user=dict(conn.execute('SELECT * FROM auth_users').fetchone())
        principal=dict(conn.execute('SELECT * FROM research_principals').fetchone())
        owners=[dict(row) for row in conn.execute('SELECT * FROM auth_owner_gates')]
        evidence=[]
        for row in conn.execute('SELECT * FROM research_evidence_objects ORDER BY id'):
            evidence.append({key:row[key] for key in ('id','kind','task_id','payload','payload_digest')}|{
                'cache_digests':{key:hashlib.sha256(row[key].encode() if type(row[key]) is str else row[key]).hexdigest()
                    if row[key] is not None else None for key in ('raw','extracted','discovery')}})
        persisted={table:[dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY '+('task_id' if table=='research_source_runs' else 'id'))]
            for table in ('research_source_approvals','research_source_chains','research_source_runs','research_source_requests')}
        assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
    files,modules=loaded(root,manifest)
    Path(output).write_text(json.dumps({'rid':rid,'first':first,'second':second,'chosen':chosen,'other':other,
        'unknown':unknown,'user':user,'principal':principal,'owners':owners,'evidence':evidence,'persisted':persisted,'first_calls':first_calls,
        'second_calls':second_calls,'third':third,'third_calls':third_calls,'source_files':files,'loaded_modules':modules,
        'wire_sha256':hashlib.sha256(wire_path.read_bytes()).hexdigest(),'pid':os.getpid()}))


@contextmanager
def legacy_source_history(tmp_path, monkeypatch, mode):
    from .source_v10_reference import reconstruct
    from .test_private_registration import register_private_user
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api import auth
    from services import runtime_paths as paths
    from services.auth_store import AuthStore
    from services.auth_registration import migrate_private_auth_registration,admit_private_gate
    from research.source_guard import provision_source_v11
    from research.plan_financial import provision_plan_v12
    from research.plan_native_financial import provision_native_v13
    from research.method_draft import provision_method_drafts_v14
    from research.store import ResearchStore
    current=Path(__file__).resolve().parents[3];state=tmp_path/'auth'
    package,_,manifest_path=reconstruct(current,tmp_path/'frozen-source10')
    expected=json.loads(manifest_path.read_text())
    worker_reference=current/'web/backend/tests/reference/source_v10_worker'
    worker_manifest=json.loads((worker_reference/'manifest.json').read_text())
    assert worker_manifest['source_commit']=='10b0919d7e784da9d66ff80ef1d69606457b94b1'
    assert set(worker_manifest['files'])=={'web/backend/research/source_workflow.py',
        'web/backend/research/source_adapters/__init__.py','web/backend/research/source_adapters/crossref_plos.py'}
    for relative,entry in worker_manifest['files'].items():
        source=worker_reference/relative;target=package/relative
        assert source.is_file() and not source.is_symlink() and not target.exists()
        content=source.read_bytes();assert hashlib.sha256(content).hexdigest()==entry['sha256']
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content)
        assert relative not in expected['files'];expected['files'][relative]=entry
    assert len(expected['files'])==49
    manifest_path=tmp_path/'combined-r10-manifest.json';manifest_path.write_text(json.dumps(expected))
    output=tmp_path/'old-history.json';log=tmp_path/'old-history.log'
    environment={**os.environ,'PYTHONPATH':str(package/'web/backend')+os.pathsep+str(package),
        'STRUCTURAL_ENV':'test','AUTH_DATA_DIR':str(state)}
    guard=sys.modules.get('audit_bootstrap')
    if guard is not None:
        environment['REVIEW_SOURCE_ROOT']=str(package)
        environment['PYTHONPATH']=str(Path(guard.__file__).parent)+os.pathsep+environment['PYTHONPATH']
    with log.open('wb') as stream:
        result=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),str(package),str(state),str(manifest_path),str(current),mode,str(output)],
            cwd=package,env=environment,stdout=stream,stderr=subprocess.STDOUT,timeout=20)
    assert result.returncode==0,log.read_text()
    history=json.loads(output.read_text());manifest=json.loads(manifest_path.read_text())['files']
    assert history['source_files'] and all(manifest[name]['sha256']==digest for name,digest in history['source_files'].items())
    assert history['loaded_modules'] and all(name in history['source_files'] for name in history['loaded_modules'].values())
    assert history['wire_sha256']==hashlib.sha256((current/'web/backend/tests/source_http_fixture.py').read_bytes()).hexdigest()
    path=state/'auth.sqlite3';identity=(path.stat().st_dev,path.stat().st_ino)
    # Explicit stopped-service permission staging; no database copy or schema
    # edits. The old factory already created its real owner/task lock files.
    for folder in (state,tmp_path/'cache',state/'logs'):
        folder.mkdir(mode=0o700,exist_ok=True);folder.chmod(0o700)
    for entry in state.iterdir():
        if entry.is_file():entry.chmod(0o600)
    lock_root=state/'research-locks';lock_root.chmod(0o700)
    for entry in lock_root.iterdir():
        assert entry.is_file() and not entry.is_symlink();entry.chmod(0o600)
    gate_identity={row['gate_id']:(lock_root/(row['gate_id']+'.lock')).stat().st_ino for row in history['owners']}
    for name,value in [('STATE_ROOT',state),('CACHE_ROOT',tmp_path/'cache'),('LOG_ROOT',state/'logs')]:monkeypatch.setattr(paths,name,value)
    for name,value in {'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
        'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,'JWT_SECRET':'research-synthetic-auth-secret-32-characters',
        'STRUCTURAL_SSO_SECRET':'research-synthetic-sso-secret-32-characters'}.items():monkeypatch.setenv(name,value)
    assert migrate_private_auth_registration()=={'contract':'auth-provision-v1','research_schema':10,'migrated':True}
    assert provision_source_v11(path)['schema_version']==11
    for row in history['owners']:admit_private_gate(row['owner_key'])
    for operation,version in ((provision_plan_v12,12),(provision_native_v13,13),(provision_method_drafts_v14,14)):
        assert operation(path)['schema_version']==version
    auth_store=AuthStore(path);store=ResearchStore(auth_store)
    with store.transaction() as conn:
        ResearchStore._check_v14(conn)
        assert conn.execute('PRAGMA foreign_key_check').fetchall()==[]
        assert dict(conn.execute('SELECT * FROM auth_users').fetchone())==history['user']
        assert dict(conn.execute('SELECT * FROM research_principals').fetchone())==history['principal']
        assert [dict(row) for row in conn.execute('SELECT * FROM auth_owner_gates')]==history['owners']
        for table,before in history['persisted'].items():
            after=[dict(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY '+('task_id' if table=='research_source_runs' else 'id'))]
            if table=='research_source_approvals':
                for row in after:
                    assert row.pop('consent_origin') is None and row.pop('consent_digest') is None
            assert after==before,'maintenance changed historical observations: '+table
        assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
        if history['unknown']:
            assert dict(conn.execute('SELECT * FROM research_source_requests WHERE id=?',(history['unknown']['id'],)).fetchone())==history['unknown']
    assert (path.stat().st_dev,path.stat().st_ino)==identity
    assert gate_identity=={row['gate_id']:(lock_root/(row['gate_id']+'.lock')).stat().st_ino for row in history['owners']}
    monkeypatch.setattr(auth,'_store',lambda:auth_store)
    user,token=register_private_user(monkeypatch,'research-a@example.test')
    assert user==history['user']
    application=FastAPI();application.include_router(auth.router,prefix='/api')
    with monkeypatch.context() as configured:
        from .test_private_registration import BETA
        for name,value in {'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,
            'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid',
            'ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}.items():configured.setenv(name,value)
        with TestClient(application,base_url=BETA) as client:
            client.cookies.set(auth._COOKIE_NAME,token)
            identity=_authenticated_identity(client,token,user['email'])
            before=execution_snapshot()
            read_history(store,identity,history)
            assert execution_snapshot()==before
            # A second actual account/session never acquires the old ACL.
            other,other_token=register_private_user(monkeypatch,'other-history@example.test')
            with TestClient(application,base_url=BETA) as visitor:
                visitor.cookies.set(auth._COOKIE_NAME,other_token)
                other_identity=_authenticated_identity(visitor,other_token,other['email'])
                import pytest
                from research.errors import ResearchError
                with pytest.raises(ResearchError,match='NOT_FOUND'):
                    read_history(store,other_identity,history)
            assert execution_snapshot()==before
            yield store,path,history,identity


def _authenticated_identity(client,token,email):
    from api import auth
    from research.authorization import AccountIdentity
    response=client.get('/api/auth/me')
    assert response.status_code==200,response.text
    assert response.json()['user']['email']==email
    claims=auth._decode_jwt(token)
    assert claims and claims['sub']==email
    # Signature/expiry and the real HTTP resolver precede this data carrier.
    return AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])


def read_history(store,identity,history):
    """Current native reader rechecks actual account/ACL on every get."""
    from research.evidence_repository import EvidenceRepository
    from research.evidence_schemas import encode
    from research.source_integration import authorizer,context_for
    with store.transaction() as conn:
        repository=EvidenceRepository(conn,authorizer(store,identity=identity))
        assert history['evidence']
        for original in history['evidence']:
            context=context_for(conn,original['task_id'])
            record=repository.get(context,original['kind'],original['id'])
            assert encode(record)==original['payload']
            assert hashlib.sha256(encode(record).encode()).hexdigest()==original['payload_digest']
            row=conn.execute('SELECT raw,extracted,discovery FROM research_evidence_objects WHERE id=?',(original['id'],)).fetchone()
            assert {key:hashlib.sha256(row[key].encode() if type(row[key]) is str else row[key]).hexdigest()
                if row[key] is not None else None for key in ('raw','extracted','discovery')}==original['cache_digests']
            if original['kind']=='excerpts':
                details=repository.excerpt_details(context,record.id)
                snapshot=repository.get(context,'snapshots',record.snapshot_id)
                assert details['quote']==record.quote and (details['start'],details['end'])==(record.start,record.end)
                assert details['source_revision']==snapshot.source_revision and details['content_digest']==snapshot.extracted_digest
                assert snapshot.origin=='offline_probe' and snapshot.licence.display_excerpt


def execution_snapshot():
    """Actual current durable execution/budget rows around a refused request."""
    from api import auth
    tables=('research_tasks','research_source_chains','research_source_runs','research_source_requests',
        'research_source_resources','research_funding_accounts','research_balance_snapshots',
        'research_price_revisions','research_reservations','research_dispatch_permits',
        'research_project_budgets','research_financial_admissions')
    with auth._store()._connection() as conn:
        conn.execute('BEGIN')
        return {table:[tuple(row) for row in conn.execute('SELECT * FROM '+table+' ORDER BY 1')] for table in tables}


if __name__=='__main__':
    _old_history(*(Path(value) if index!=4 else value for index,value in enumerate(sys.argv[1:])))
