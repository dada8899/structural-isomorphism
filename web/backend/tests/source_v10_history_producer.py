"""Synthetic HTTP producer executed only in the reconstructed real R10 package."""
import hashlib,json,os,sys
from pathlib import Path
from urllib.parse import parse_qs,urlsplit


def loaded(root,expected=None):
    files={};modules={}
    for name,module in tuple(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve()
        core=name.split('.')[0] in ('api','services','research') or name.startswith('web.backend')
        if core and not path.is_relative_to(root):raise AssertionError('mixed historical source: '+name)
        if not path.is_relative_to(root) or path.suffix!='.py':continue
        relative=path.relative_to(root).as_posix();digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if expected is not None and (relative not in expected or expected[relative]['sha256']!=digest):raise AssertionError('historical source digest differs: '+relative)
        files[relative]=digest;modules[name]=relative
    return files,modules


def main():
    root=Path(os.environ['SOURCE10_ROOT']).resolve()
    manifest=json.loads(Path(os.environ['SOURCE10_MANIFEST']).read_text())['files'] if os.getenv('SOURCE10_MANIFEST') else None
    loaded(root,manifest)  # Includes modules eagerly imported by startup guards.
    state=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]);problem=json.loads(Path(sys.argv[3]).read_text())
    from services import runtime_paths as paths
    paths.STATE_ROOT=state;paths.CACHE_ROOT=state.parent/'cache';paths.LOG_ROOT=state/'logs'
    settings={'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),
      'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta',
      'AUTH_LINK_BASE_URL':'https://beta.structural.bytedance.city','JWT_SECRET':'source11-history-synthetic-secret-0123456789',
      'STRUCTURAL_SSO_SECRET':'source11-history-synthetic-secret-0123456789','SMTP_HOST':'fixture.invalid','SMTP_PORT':'587',
      'SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'}
    os.environ.update(settings)
    from services.auth_registration import bootstrap_private_runtime
    assert bootstrap_private_runtime()['research_schema']==10
    from api import auth,research
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from research import source_integration
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text)
    research.enabled=lambda:True;source_integration.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    beta=settings['AUTH_LINK_BASE_URL']
    def envelope(value):return {'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':value}
    loaded(root,manifest)  # Verify the actual old producer before any HTTP write.
    with TestClient(app,base_url=beta) as client:
        requested=client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':beta})
        assert requested.status_code==200,requested.text
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        verified=client.post('/api/auth/verify',json={'token':token},headers={'origin':beta})
        assert verified.status_code==200,verified.text
        made=client.post('/api/research',json=envelope({'problem':problem}),headers={'origin':beta,'idempotency-key':'old10-formula'})
        assert made.status_code==200,made.text
        body=made.json()['data'];rid=body['research']['id'];meta=body['current_problem']['formula_snapshot']
        checked=client.post(f'/api/research/{rid}/formula-checks',json=envelope({'input_revision':1,'expected_research_version':body['research_version'],'formula_digest':meta['formula_digest'],'confirm_formula_input':True}),headers={'origin':beta,'idempotency-key':'old10-check'})
        assert checked.status_code==200,checked.text
        ref=checked.json()['data']['result_ref'];saved=client.get(f'/api/research/{rid}/formula-results/{ref}')
        assert saved.status_code==200,saved.text
        version=client.get('/api/research/'+rid).json()['data']['research_version']
        payload={'input_revision':1,'expected_research_version':version,'query':'queue theory'}
        preview=client.post(f'/api/research/{rid}/source-preview',json=envelope(payload),headers={'origin':beta,'idempotency-key':'old10-preview'})
        assert preview.status_code==200,preview.text
        approved=client.post(f'/api/research/{rid}/source-approvals',json=envelope({**payload,'preview_digest':preview.json()['data']['preview_digest'],'confirm_external':True}),headers={'origin':beta,'idempotency-key':'old10-approval'})
        assert approved.status_code==200,approved.text
        files,modules=loaded(root,manifest)
        output.write_text(json.dumps({'rid':rid,'ref':ref,'result':saved.json()['data'],'old_approval':approved.json()['data']['approval_ref'],'research_version':version,'source_files':files,'loaded_modules':modules}))


if __name__=='__main__':main()
