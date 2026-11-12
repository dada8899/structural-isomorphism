"""Real R13 HTTP/worker producer in an independently reconstructed exact package."""
import hashlib,json,os,sys
from pathlib import Path
from urllib.parse import parse_qs,urlsplit
from functools import partial


def loaded(root,manifest):
    files={};modules={}
    for name,module in tuple(sys.modules.items()):
        file=getattr(module,'__file__',None)
        if not file:continue
        path=Path(file).resolve();core=name.split('.')[0] in ('api','research','services') or name.startswith('web.backend')
        if core and not path.is_relative_to(root):raise AssertionError('mixed old producer: '+name)
        if not path.is_relative_to(root) or path.suffix!='.py':continue
        relative=path.relative_to(root).as_posix();sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if manifest is not None:assert manifest['files'][relative]['sha256']==sha
        files[relative]=sha;modules[name]=relative
    return files,modules


def main():
    root=Path(os.environ['METHOD13_ROOT']).resolve();manifest=json.loads(Path(os.environ['METHOD13_MANIFEST']).read_text())['cases'][sys.argv[3]] if os.getenv('METHOD13_MANIFEST') else None
    loaded(root,manifest)
    state=Path(sys.argv[1]).resolve();output=Path(sys.argv[2]);mode=sys.argv[3]
    from services import runtime_paths as paths
    paths.STATE_ROOT=state;paths.CACHE_ROOT=state.parent/'cache';paths.LOG_ROOT=state/'logs'
    beta='https://beta.structural.bytedance.city'
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
        'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':beta,'JWT_SECRET':'method14-history-synthetic-secret-0123456789','STRUCTURAL_SSO_SECRET':'method14-history-synthetic-secret-0123456789',
        'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'})
    from services.auth_registration import bootstrap_private_runtime
    assert bootstrap_private_runtime()['research_schema']==13
    from api import auth,research
    from research import ResearchStore,ResearchRunner,source_integration,plan_native as native
    from research.source_policy import PinnedPublicTransport
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from web.backend.tests.source_http_fixture import source_server,get_local
    from web.backend.tests.plan_v12_history_producer import provider,funded,identity
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text);research.enabled=lambda:True;source_integration.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    def post(client,rid,suffix,data,key,contract='b1-candidate-01'):
        path='/api/research'+('/'+rid+'/'+suffix if rid else '')
        response=client.post(path,json={'schema_version':'structure-research-v1','contract_revision':contract,'data':data},headers={'origin':beta,'idempotency-key':key})
        assert response.status_code==200,response.text
        return response.json()['data']
    problem={'entry':'phenomenon','original_input':'A synthetic observation of waiting when work arrivals vary.','objective':'Measure waiting','summary':'A synthetic queue observation.','variables':[],'constraints':['Synthetic offline fixture'],'unknowns':['Arrival process is unknown.'],'confirmed':True}
    loaded(root,manifest)
    with TestClient(app,base_url=beta) as client:
        assert client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':beta}).status_code==200
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        assert client.post('/api/auth/verify',json={'token':token},headers={'origin':beta}).status_code==200
        formula_problem=json.loads((Path(__file__).parent/'reference/plan_v12/problem.json').read_text())
        made=post(client,None,None,{'problem':formula_problem},'old13-create');rid=made['research']['id'];store=ResearchStore(auth._store())
        checked=post(client,rid,'formula-checks',{'input_revision':1,'expected_research_version':made['research_version'],'formula_digest':made['current_problem']['formula_snapshot']['formula_digest'],'confirm_formula_input':True},'old13-formula-check')
        formula_ref=checked['result_ref'];formula=client.get(f'/api/research/{rid}/formula-results/{formula_ref}');assert formula.status_code==200,formula.text
        query={'input_revision':1,'expected_research_version':client.get('/api/research/'+rid).json()['data']['research_version'],'query':'queue theory'}
        preview=post(client,rid,'source-preview',query,'old13-source-preview')
        approval=post(client,rid,'source-approvals',{**query,'confirm_external':True,'preview_digest':preview['preview_digest']},'old13-source-approve')
        task=post(client,rid,'source-tasks',{'input_revision':1,'expected_research_version':query['expected_research_version'],'approval_ref':approval['approval_ref']},'old13-source-start')['task']['id']
        with source_server() as (port,calls):
            assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(task)=='COMPLETED'
            assert calls==['/discovery','/article']
        post(client,rid,'revisions',{'expected_revision':1,'problem':problem},'old13-own-observation')
        results=[]
        unknown=[False]
        class UnknownUsage:
            def __bool__(self):return unknown[0]
        with provider(unknown_usage=UnknownUsage()) as (server,calls):
            installation=provision=permit=resource=authority=None
            try:
                if mode=='native':
                    authority=native.create_controlled_fixture_authority(store,identity(client),server,approved_cap_units=41_000_000,risk_margin_units=1_000_000)
                    provision=native.issue_native_provision(store,authority);permit=native.mint_runtime_permit(provision);resource=native.open_controlled_fixture_resource(permit)
                    native.install_native_funding(store,provision,resource)
                    installation=True
                else:
                    installation=funded((client,state,rid,store),server);installation.__enter__()
                contract='funded-plan-v2' if mode=='native' else 'b1-candidate-01'
                for number in range(2):
                    if number:rid2=post(client,None,None,{'problem':problem},'old13-other')['research']['id']
                    else:rid2=rid
                    version=client.get('/api/research/'+rid2).json()['data']['research_version']
                    preview=post(client,rid2,'plan-previews',{'input_revision':1 if number else 2,'expected_research_version':version,'observation_source':'own_observation','declaration_status':'self_declared'},'old13-preview-'+str(number),contract)
                    confirmation={k:preview[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};confirmation['confirm_outbound']=True
                    approved=post(client,rid2,'plan-approvals',confirmation,'old13-confirm-'+str(number),contract)
                    unknown[0]=bool(number)
                    outcome=ResearchRunner(store).run_once(approved['task_id'])['data']
                    assert outcome['state']==('pending_reconciliation' if number else 'saved')
                    response=client.get('/api/research/'+rid2+'/plan-results/'+approved['result_ref']);assert response.status_code==200,response.text
                    results.append({'rid':rid2,'ref':approved['result_ref'],'result':response.json()})
            finally:
                if mode=='native':
                    native.retire_installation(store)
                    for cap in (resource,permit,provision,authority):
                        if cap is not None:cap.close()
                elif installation:installation.__exit__(None,None,None)
        with store.transaction() as conn:
            table='research_plan_native_runs' if mode=='native' else 'research_plan_dispatches'
            assert conn.execute('SELECT state,cost_state FROM '+table+' ORDER BY rowid DESC LIMIT 1').fetchone()[:]==('unknown','unknown')
            money=tuple(conn.execute('SELECT held,upper_booked,settled FROM research_funding_accounts').fetchone());assert money[0]>0 and money[1]>0
        files,modules=loaded(root,manifest)
        output.write_text(json.dumps({'results':results,'source_task':task,'formula_ref':formula_ref,'formula_result':formula.json(),'money':money,'source_files':files,'loaded_modules':modules}))

if __name__=='__main__':main()
