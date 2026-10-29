"""Synthetic actual R12 producer; runs only in exact offline reference closure."""
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


from contextlib import contextmanager,closing
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import sqlite3
import threading
import time
from uuid import uuid4
from api import auth
from research import ResearchStore,ResearchRunner
from research.authorization import AuthorizationGate
from research.paid_approval import OfflineFundingResolver,request_codec_digest
from research.financial_guard import OfflineProjectRegistration
from research.provider_schemas import UsageUpperQuote,BudgetBasisSnapshot,Money,canonical,digest
from research.plan_runtime import install_fixture_funding,uninstall_fixture_funding,UPPER
from research.plan_transport import fixture_resource
CANDIDATE={'summary':'A starting plan from the self observation.','candidates':[{'label':'Queue variability','mechanism_hypothesis':'Variable arrivals may accumulate work.','why_considered':'The observation concerns waiting.','method_leads':['queueing model'],'key_unknowns':['Arrival variation is unknown.']}],'query_suggestions':[{'candidate_index':0,'query':'queue variability waiting','intent':'Find a possible comparison later.'}],'gaps':['No literature or mathematics has been checked.'],'clarification_questions':[]}
@contextmanager
def provider(*,invalid_body=False,unknown_usage=False,balance='73',before_balance=None,before_post=None,choices=None):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def reply(self,value):
            raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            calls.append(('GET',self.path,self.headers.get('X-Fixture-Incarnation')))
            if before_balance:before_balance()
            self.reply({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':balance}]})
        def do_POST(self):
            raw=self.rfile.read(int(self.headers['Content-Length']));request=json.loads(raw)
            calls.append(('POST',self.path,self.headers.get('X-Fixture-Incarnation'),request))
            if before_post:before_post()
            self.reply({'id':'fixture-plan-1','model':'deepseek-flash','usage':None if unknown_usage else {'prompt_tokens':100,'completion_tokens':80,'total_tokens':180},'choices':choices if choices is not None else [{'finish_reason':'stop','message':{'content':'{}' if invalid_body else json.dumps(CANDIDATE)}}]})
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server,calls
    finally:server.shutdown();server.server_close();thread.join(3)
@contextmanager
def funded(data,server):
    client,_,rid,store=data;actor=identity(client)
    with store.transaction() as conn:pid=conn.execute('SELECT owner_id FROM research_controls WHERE id=?',(rid,)).fetchone()[0]
    money=lambda n:Money(currency='CNY',scale=6,amount_units=n)
    fid,binding,sid=[str(uuid4()) for _ in range(3)];now=int(time.time())
    quote=UsageUpperQuote(revision=str(uuid4()),context_bound=1048576,peak_input_miss_units_per_million=1,peak_output_units_per_million=2,local_guard=1,price_document_digest='a'*64,model_document_digest='b'*64,completion_bound_basis_digest='c'*64,final_request_code_digest=request_codec_digest(),valid_until=now+60)
    basis=BudgetBasisSnapshot(id=sid,account_id=fid,provider_binding_id=binding,funding_epoch=1,initial_prepaid=money(73_000_000),other_use_margin=money(0),cap=money(73_000_000),settled_actual=money(0),upper_booked=money(0),held=money(0),available_after_observed_consumption=money(73_000_000),price_revision=quote.revision,valid_until=now+3600)
    stamp=lambda t:datetime.fromtimestamp(t,timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    with store.transaction(write=True) as conn:
        conn.execute("INSERT INTO research_funding_accounts(id,binding_id,mode,provider,currency,cap,initial_prepaid_units,other_use_margin_units,status,snapshot_id) VALUES(?,?,'live','deepseek','CNY',73000000,73000000,0,'active',?)",(fid,binding,sid))
        conn.execute('INSERT INTO research_balance_snapshots(id,account_id,balance,settled_at_observation,local_settlement_cursor,observed_at,expires_at,hard_prepaid,auto_topup_off,postpaid_off,basis_evidence_digest) VALUES(?,?,73000000,0,0,?,?,1,1,1,?)',(sid,fid,stamp(now),stamp(now+3600),digest(canonical(basis.model_dump()))))
        conn.execute("INSERT INTO research_price_revisions(id,account_id,operation,currency,scale,expires_at,policy_revision,quote_json,quote_digest) VALUES(?,?,'model_report','CNY',6,?,'bounded_usage_upper_v2',?,?)",(quote.revision,fid,stamp(now+60),canonical(quote.model_dump()).decode(),digest(canonical(quote.model_dump()))))
    resolver=OfflineFundingResolver(principal_id=pid,quote=quote,basis=basis,approved_upper=money(3))
    source=OfflineProjectRegistration(store=store,identity=actor,principal_id=pid,funding_resolver=resolver,authorized_cap=money(73_000_000),authorization_ref=str(uuid4()))
    resource=fixture_resource(server,economic_binding=binding,credential_incarnation='fixture-credential-1')
    installation=None
    try:
        installation=install_fixture_funding(store,actor,source,resource)
        yield installation
    finally:
        if installation:uninstall_fixture_funding(store,installation)
        else:resource.close()
        source.close();resolver.close()
from research.authorization import AccountIdentity

def identity(client):
    claims=auth._decode_jwt(client.cookies.get('phase_session'))
    return AccountIdentity(claims['sub'],claims['gen'],claims['jti'],claims['exp'])


def main():
    root=Path(os.environ['PLAN12_ROOT']).resolve()
    manifest=json.loads(Path(os.environ['PLAN12_MANIFEST']).read_text())['files'] if os.getenv('PLAN12_MANIFEST') else None
    loaded(root,manifest)
    state=Path(sys.argv[1]).resolve();output=Path(sys.argv[2])
    from services import runtime_paths as paths
    paths.STATE_ROOT=state;paths.CACHE_ROOT=state.parent/'cache';paths.LOG_ROOT=state/'logs'
    beta='https://beta.structural.bytedance.city'
    os.environ.update({'STRUCTURAL_ENV':'prod','AUTH_DATA_DIR':str(state),'STRUCTURAL_SSO_DATA_DIR':str(state),'STRUCTURAL_PRIVACY_HMAC_KEY':'0123456789abcdef'*4,
      'AUTH_ENABLED':'true','AUTH_SITE_ROLE':'beta','AUTH_LINK_BASE_URL':beta,'JWT_SECRET':'native13-history-synthetic-secret-0123456789','STRUCTURAL_SSO_SECRET':'native13-history-synthetic-secret-0123456789',
      'SMTP_HOST':'fixture.invalid','SMTP_PORT':'587','SMTP_FROM_EMAIL':'sender@example.invalid','ADMIN_NOTIFICATION_EMAIL':'admin@example.invalid','AUTH_TRUSTED_PROXY_IPS':'127.0.0.1','AUTH_DEV_MODE':'false'})
    from services.auth_registration import bootstrap_private_runtime
    assert bootstrap_private_runtime()['research_schema']==12
    from api import research
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    mail=[];auth._send_email=lambda to,subject,text:mail.append(text);research.enabled=lambda:True
    app=FastAPI();app.include_router(auth.router,prefix='/api');app.include_router(research.router,prefix='/api')
    problem=json.loads(Path(sys.argv[3]).read_text());problem.pop('formula_draft',None)
    problem.update(entry='phenomenon',original_input='我发现团队的到达任务变得集中时，等待时间明显增加。',confirmed=True)
    def envelope(data):return {'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':data}
    def post(client,rid,suffix,data,key):
        response=client.post('/api/research/'+rid+'/'+suffix,json=envelope(data),headers={'origin':beta,'idempotency-key':key})
        assert response.status_code==200,response.text
        return response.json()['data']
    loaded(root,manifest)
    with TestClient(app,base_url=beta) as client:
        response=client.post('/api/auth/request-link',json={'email':'fresh@example.invalid'},headers={'origin':beta});assert response.status_code==200,response.text
        token=parse_qs(urlsplit(mail[-1].strip().split()[-1]).query)['token'][0]
        response=client.post('/api/auth/verify',json={'token':token},headers={'origin':beta});assert response.status_code==200,response.text
        response=client.post('/api/research',json=envelope({'problem':problem}),headers={'origin':beta,'idempotency-key':'old12-create'});assert response.status_code==200,response.text
        rid=response.json()['data']['research']['id'];store=ResearchStore(auth._store())
        with provider() as (server,calls),funded((client,state,rid,store),server):
            preview=post(client,rid,'plan-previews',{'input_revision':1,'expected_research_version':1,'observation_source':'own_observation','declaration_status':'self_declared'},'old12-preview')
            confirmation={k:preview[k] for k in ('preview_ref','preview_digest','request_digest','expected_research_version','approved_upper_units')};confirmation['confirm_outbound']=True
            admitted=post(client,rid,'plan-approvals',confirmation,'old12-confirm')
            assert ResearchRunner(store).run_once(admitted['task_id'])['data']['state']=='saved'
            assert [call[0] for call in calls]==['GET','POST']
            response=client.get('/api/research/'+rid+'/plan-results/'+admitted['result_ref']);assert response.status_code==200,response.text
            result=response.json()
        files,modules=loaded(root,manifest)
        output.write_text(json.dumps({'rid':rid,'ref':admitted['result_ref'],'result':result,'source_files':files,'loaded_modules':modules}))

if __name__=='__main__':main()
