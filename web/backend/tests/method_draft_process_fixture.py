"""Owned current reads and native migration crash points for draft acceptance."""
import json,os,sqlite3
from pathlib import Path


def read_draft(path,rid,ref,output):
    from urllib.parse import parse_qs,urlsplit
    from .source_v11_process_fixture import configure
    from .test_private_registration import SECRET,BETA
    path=configure(path)
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(path.parent),'STRUCTURAL_SSO_DATA_DIR':str(path.parent),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':BETA,'JWT_SECRET':SECRET,'STRUCTURAL_SSO_SECRET':SECRET,
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
        'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false','STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4})
    from api import auth,research
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text);research.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    with TestClient(app,base_url=BETA) as client:
        response=client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':BETA});assert response.status_code==200
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        response=client.post('/api/auth/verify',json={'token':token},headers={'origin':BETA});assert response.status_code==200
        value=client.get(f'/api/research/{rid}/method-drafts/{ref}');assert value.status_code==200,value.text
        Path(output).write_text(json.dumps(value.json()))


def kill_upgrade(path,cut):
    from .source_v11_process_fixture import configure
    configure(path)
    from research.method_draft import provision_method_drafts_v14
    native=sqlite3.connect
    targets={'journal':'PRAGMA journal_mode=DELETE','table':'CREATE TABLE research_method_drafts','guard':'CREATE TRIGGER research_method_draft_insert','marker':'UPDATE research_schema SET version=14'}
    class Crash(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            result=super().execute(sql,*args,**kwargs)
            if cut in targets and sql.startswith(targets[cut]):os._exit(81)
            return result
        def commit(self):
            try:version=super().execute('SELECT version FROM research_schema').fetchone()[0]
            except sqlite3.Error:version=None
            if version==14 and cut=='before-commit':os._exit(81)
            result=super().commit()
            if version==14 and cut=='after-commit':os._exit(82)
            return result
    sqlite3.connect=lambda *args,**kwargs:native(*args,**kwargs) if 'factory' in kwargs else native(*args,factory=Crash,**kwargs)
    provision_method_drafts_v14(Path(path))
    raise AssertionError('draft migration boundary not reached')


def read_migrated(path,original,output):
    import secrets
    from urllib.parse import parse_qs,urlsplit
    from .source_v11_process_fixture import configure
    path=configure(path);beta='https://beta.structural.bytedance.city'
    inode=(path.stat().st_dev,path.stat().st_ino)
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(path.parent),'STRUCTURAL_SSO_DATA_DIR':str(path.parent),
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':beta,'JWT_SECRET':'method14-history-synthetic-secret-0123456789','STRUCTURAL_SSO_SECRET':'method14-history-synthetic-secret-0123456789',
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid',
        'AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false','STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'STRUCTURAL_SHARE_TOKEN_SECRET':secrets.token_urlsafe(48)})
    for key in ('STRUCTURAL_DATA_DIR','STRUCTURAL_MODEL_PATH','STRUCTURAL_PRECOMPUTED_EMBEDDINGS',
        'STRUCTURAL_ARTIFACT_MANIFEST','STRUCTURAL_HISTORY_DB','STRUCTURAL_FAVORITES_PATH'):
        os.environ.pop(key,None)
    from api import auth
    import main
    from services import formal_admission
    from fastapi.testclient import TestClient
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text)
    assert main._IS_PROD and main.auth_api is auth
    with TestClient(main.app,base_url=beta) as client:
        assert formal_admission.require(main.app,'research_basic') is None
        assert client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':beta}).status_code==200
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        assert client.post('/api/auth/verify',json={'token':token},headers={'origin':beta}).status_code==200
        for item in original['results']:
            value=client.get('/api/research/'+item['rid']+'/plan-results/'+item['ref'])
            assert value.status_code==200,value.text
            assert value.json()==item['result']
        rid=original['results'][0]['rid']
        formula=client.get('/api/research/'+rid+'/formula-results/'+original['formula_ref'])
        assert formula.status_code==200 and formula.json()==original['formula_result']
        from research import ResearchStore
        from research.authorization import AccountIdentity
        from research.evidence_repository import EvidenceRepository
        from research.source_integration import context_for,authorizer
        claims=auth._decode_jwt(client.cookies.get('phase_session'))
        identity=AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp']);store=ResearchStore(auth._store())
        with store.transaction() as conn:
            context=context_for(conn,original['source_task']);repository=EvidenceRepository(conn,authorizer(store,identity=identity))
            refs=conn.execute("SELECT id FROM research_evidence_objects WHERE task_id=? AND kind='excerpts'",(original['source_task'],)).fetchall()
            assert refs
            for ref in refs:assert repository.excerpt_details(context,ref[0])['input_revision']==1
        Path(output).write_text(json.dumps({'plan_results_unchanged':True,'formula_result_unchanged':True,'original_source_readable':True}))
    assert (path.stat().st_dev,path.stat().st_ino)==inode
