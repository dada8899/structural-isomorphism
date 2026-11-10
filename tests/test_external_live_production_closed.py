"""Actual v17 lifecycle must not seek any external material without proof."""
import asyncio

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp


def test_fresh_main_defers_jwt_and_preserves_the_original_token_library(tmp_path):
    import os,subprocess,sys
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    code='''
import importlib,sys
from pathlib import Path
root=Path(sys.argv[1]);sys.path[:0]=[str(root/'web/backend'),str(root)]
assert 'jwt' not in sys.modules and 'cryptography' not in sys.modules
import main
from api import auth,sso
assert 'jwt' not in sys.modules and 'cryptography' not in sys.modules
assert auth.jwt is sso.jwt
try:getattr(auth.jwt,'not_a_token_library_operation')
except AttributeError:pass
else:raise AssertionError('unsupported delegation')
assert 'jwt' not in sys.modules
secret='public-synthetic-token-secret-for-isolated-test'
token=auth.jwt.encode({'sub':'public-synthetic-owner'},secret,algorithm='HS256')
assert sso.jwt.decode(token,secret,algorithms=['HS256'])=={'sub':'public-synthetic-owner'}
library=importlib.import_module('jwt')
assert auth.jwt.encode is library.encode and auth.jwt.decode is library.decode
assert sso.jwt.PyJWTError is library.PyJWTError
try:sso.jwt.decode(token,'another-public-synthetic-secret',algorithms=['HS256'])
except sso.jwt.PyJWTError:pass
else:raise AssertionError('invalid signature accepted')
print('DEFERRED_JWT_PUBLIC_FLOW_VERIFIED')
'''
    env={name:os.environ[name] for name in ('PATH','HOME','TMPDIR') if name in os.environ}
    env.update(LANG='C',LC_ALL='C',TZ='UTC',STRUCTURAL_ENV='test',AUTH_ENABLED='false',
        AUTH_DATA_DIR=str(tmp_path/'auth'),STRUCTURAL_SSO_DATA_DIR=str(tmp_path/'sso'),
        STRUCTURAL_HISTORY_DB=str(tmp_path/'history.sqlite3'),STRUCTURAL_FAVORITES_PATH=str(tmp_path/'favorites.jsonl'),
        STRUCTURAL_LOG_FILE=str(tmp_path/'app.jsonl'),PYTHONDONTWRITEBYTECODE='1')
    result=subprocess.run([sys.executable,'-I','-B','-c',code,str(root)],env=env,capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    assert result.stdout.strip()==b'DEFERRED_JWT_PUBLIC_FLOW_VERIFIED'


@pytest.mark.parametrize("pin",[False,True],ids=["no-source-pin","pin-without-entry-witness"])
def test_actual_main_defaults_closed_without_credential_or_crypto_lookup(prepared,monkeypatch,pin):
    main,admission,paths,messages=prepared
    from research.external_first_answer_catalog import provision_isolated_v17
    from research.external_first_answer_file_writer import approve_isolated_file
    from research.first_answer import provision_first_answers_v16
    from services import external_live_production as production
    path=paths.private_auth_path()
    provision_first_answers_v16(path)
    marker=path.with_name("STRUCTURE-EXTERNAL-LEDGER-FIXTURE")
    marker.write_bytes(b"isolated external ledger candidate, no provider\n");marker.chmod(0o600)
    provision_isolated_v17(approve_isolated_file(path))
    def forbidden(*_):
        pytest.fail("no credential, approval file or verifier access before entry witness")
    monkeypatch.setattr(production,"_load_credential",forbidden)
    monkeypatch.setattr(production,"_fixed_file",forbidden)
    monkeypatch.setattr(production,"_verify_runtime_files",forbidden)
    monkeypatch.setenv("STRUCTURAL_EXTERNAL_FIRST_ANSWER_ENABLED","true")
    if pin:
        monkeypatch.setattr(production,"_PINNED_POLICY",production.PinnedTargetPolicy("0"*64,"0"*64,"/no","/no",()))

    async def verify():
        async with main.lifespan(main.app):
            assert admission.safe_status(main.app)["base"]=="ready"
            assert not production._LIVE and not production._ENTRIES
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                made=await client.post("/api/research",json=envelope({"problem":problem()}),
                    headers={"Origin":BETA,"Idempotency-Key":"external-live-closed-fixture"})
                assert made.status_code==200
                data=made.json()["data"];rid=data["research"]["id"]
                assert data["capabilities"]["external_first_answer"]=="status_only"
                answer=await client.post(f"/api/research/{rid}/revisions/1/external-first-answer/preview",
                    json={"research_version":data["research_version"],"problem_digest":data["current_problem"]["digest"]},
                    headers={"Origin":BETA})
                assert answer.status_code==503
        assert not production._LIVE and admission._STATE.get(id(main.app)) is None
    asyncio.run(verify())


@pytest.mark.parametrize('unknown',[False,True],ids=['returned','unknown-held'])
def test_saved_question_policy_real_main_auth_shared_ledger_and_once_sender(prepared,monkeypatch,tmp_path,unknown):
    """Synthetic handle/transport seam only: no issuer, key, socket or real provider."""
    from contextlib import contextmanager
    import json,os,time
    from types import SimpleNamespace as NS
    from uuid import uuid4
    from web.backend.tests.test_plan_runtime_transport import provider
    main,admission,paths,messages=prepared
    from api import auth
    from research import first_answer,plan_native
    from research.external_first_answer_catalog import provision_isolated_v17
    from research.external_first_answer_file_writer import approve_isolated_file
    from research.external_first_answer_issuer_contract import StartupBinding
    from research.store import ResearchStore
    from web.backend.tests.test_research_first_answer import identity
    from services import external_live_operations as operations,external_live_production as live,external_live_sender as transport
    path=paths.private_auth_path();first_answer.provision_first_answers_v16(path)
    origin={'Origin':BETA};calls=[]
    candidate={'status':'candidate','explanation':'这是公开合成问题的待核查回答。','assumptions':['仅用于隔离验证。'],
        'next_check':'检查原问题与持久状态。','evidence_status':'not_checked'}
    class FakeSocket:
        def settimeout(self,*_):pass
        def connect(self,*_):pass
        def close(self):pass
        def sendall(self,wire):
            method=wire.split(b' ',1)[0].decode();calls.append(method)
            body=({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'400'}]} if method=='GET' else
                  {'id':'synthetic-receipt','model':'deepseek-flash','usage':None if unknown else {'prompt_tokens':100,'completion_tokens':20,'total_tokens':120},
                   'choices':[{'finish_reason':'stop','message':{'content':json.dumps(candidate,ensure_ascii=False)}}]})
            raw=json.dumps(body,ensure_ascii=False).encode();self.reply=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw
        def recv(self,size):raw=self.reply[:size];self.reply=self.reply[size:];return raw
    tls=NS(wrap_socket=lambda sock,**_:sock)
    receipts=tmp_path/'operation-receipts';receipts.mkdir(mode=0o700)
    @contextmanager
    def synthetic_receipts(_):
        fd=os.open(receipts,os.O_RDONLY|os.O_DIRECTORY)
        try:yield fd
        finally:os.close(fd)

    async def verify(server):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            async with main.lifespan(main.app):
                await login(client,messages)
                made=await client.post('/api/research',json=envelope({'problem':problem()}),headers=origin|{'Idempotency-Key':'general-policy-seed'})
                assert made.status_code==200,made.text
                store=ResearchStore(auth._store());actor=identity(client)
                authority=plan_native.create_controlled_runtime_fixture_authority(store,actor,server,approved_cap_units=300_000_000,risk_margin_units=2_129_920)
                provision=plan_native.issue_native_provision(store,authority);permit=plan_native.mint_runtime_permit(provision);resource=plan_native.open_plan_resource(permit)
                try:plan_native.install_native_funding(store,provision,resource)
                finally:plan_native.retire_installation(store)
            marker=path.with_name('STRUCTURE-EXTERNAL-LEDGER-FIXTURE');marker.write_bytes(b'isolated external ledger candidate, no provider\n');marker.chmod(0o600)
            provision_isolated_v17(approve_isolated_file(path))
            async with main.lifespan(main.app):
                binding=admission._STATE[id(main.app)];service=binding.service
                with service.store.transaction() as conn:
                    row=conn.execute('''SELECT f.account_id,f.economic_binding,f.credential_incarnation,f.principal_id,f.generation,
                     f.owner_gate_id,a.funding_epoch,p.epoch FROM research_plan_native_funding f JOIN research_funding_accounts a ON a.id=f.account_id
                     JOIN research_principals p ON p.id=f.principal_id WHERE f.id=1''').fetchone()
                policy=transport.EndpointPolicy('1.1.1.1','a'*64,'b'*64,'c'*64,2_129_920,request_mode='saved-question')
                expected=StartupBinding(startup_id=str(uuid4()),source_commit='a'*40,source_manifest_digest='b'*64,runtime_closure_digest='c'*64,
                    unit_digest='d'*64,database_dev=service.store.storage_identity[0],database_ino=service.store.storage_identity[1],
                    receipts_dev=1,receipts_ino=1,schema_version=17,runtime_uid=981,runtime_gid=976,owner_principal=row[3],owner_generation=row[4],
                    owner_epoch=row[7],owner_gate_id=row[5],account_id=row[0],economic_binding=row[1],funding_epoch=row[6],credential_incarnation=row[2],
                    ledger_policy_digest='e'*64,endpoint_policy_digest=policy.wire_digest())
                # Real Main/owner/account attestation remains active; only the
                # absent production startup loader is replaced by a test-local resource.
                resource=live._LiveCredential(bytearray(b'PUBLIC-SYNTHETIC-NOT-A-KEY'),factory=live._FACTORY_LIVE)
                handle=live._LiveHandle(main.app,binding,expected,resource,NS(require_runtime=lambda:None),factory=live._FACTORY_LIVE)
                with monkeypatch.context() as patch:
                    patch.setitem(live._LIVE,id(main.app),handle)
                    patch.setattr(transport,'_PINNED_ENDPOINT',policy)
                    patch.setattr(transport,'_trust',lambda *_,**__: (tls,int(time.time())+60,1_000_000))
                    patch.setattr(transport,'socket',NS(AF_INET=2,AF_INET6=10,SOCK_STREAM=1,socket=lambda *_:FakeSocket()))
                    patch.setattr(live,'_receipt_directory',synthetic_receipts)
                    previews=[]
                    prior_data=None
                    persisted=None
                    for n in range(2):
                        public_problem=problem()|{'original_input':f'公开合成问题{n}：为什么反馈延迟可能造成超调？'}
                        if n==0:
                            made=await client.post('/api/research',json=envelope({'problem':public_problem}),headers=origin|{'Idempotency-Key':f'general-policy-public-{n}'})
                        else:
                            made=await client.post(f"/api/research/{prior_data['research']['id']}/revisions",json=envelope({'expected_revision':1,'problem':public_problem}),headers=origin|{'Idempotency-Key':'general-policy-revision-two'})
                        assert made.status_code==200,made.text
                        data=made.json()['data'];prior_data=data;rid=data['research']['id'];base=f'/api/research/{rid}/revisions/{n+1}/external-first-answer'
                        if not unknown and n==1:
                            original_scope=operations._authorized_saved_revision
                            @contextmanager
                            def exhausted_scope(*args,**kwargs):
                                with original_scope(*args,**kwargs) as (conn,scope,raw):
                                    class ReadOnlyAccountFault:
                                        def execute(self,sql,*params):
                                            if sql.startswith('SELECT settled,held,upper_booked FROM research_funding_accounts'):
                                                return NS(fetchone=lambda:(300_000_000,0,0))
                                            return conn.execute(sql,*params)
                                    yield ReadOnlyAccountFault(),scope,raw
                            with monkeypatch.context() as empty_budget:
                                empty_budget.setattr(operations,'_authorized_saved_revision',exhausted_scope)
                                exhausted=await client.post(base+'/preview',json={'research_version':data['research_version'],'problem_digest':data['current_problem']['digest']},headers=origin)
                            assert exhausted.status_code==409 and calls==['GET','POST']
                        offered=await client.post(base+'/preview',json={'research_version':data['research_version'],'problem_digest':data['current_problem']['digest']},headers=origin)
                        if unknown and n==1:
                            assert offered.status_code==409 and calls==['GET','POST'];break
                        assert offered.status_code==200,offered.text
                        preview=offered.json();key=preview['operation_key'];assert key not in previews;previews.append(key)
                        body={k:preview[k] for k in ('preview_digest','request_digest','upper_units')};body.update(purpose='external-first-answer-question-v1',confirm_exact_question=True,confirm_maximum_cost=True,declares_right_to_send=True)
                        wrong=await client.post(base+'/confirm',json=body,headers=origin|{'Idempotency-Key':str(uuid4())})
                        assert wrong.status_code==409 and len(calls)==2*n
                        headers=origin|{'Idempotency-Key':key}
                        response=await client.post(base+'/confirm',json=body,headers=headers)
                        assert response.status_code==200,response.text
                        assert response.json()['status']==('unknown' if unknown else 'completed'),response.text
                        assert calls==['GET','POST']*(n+1)
                        current_view=await client.get('/api/research/'+rid)
                        assert current_view.status_code==200,current_view.text
                        assert current_view.json()['data']['external_first_answer_recovery']==response.json()
                        assert calls==['GET','POST']*(n+1)
                        persisted=(base,dict(headers),dict(body),response.json())
                        assert (await client.post(base+'/confirm',json=body,headers=headers)).json()==response.json()
                        duplicate=await client.post(base+'/preview',json={'research_version':data['research_version'],'problem_digest':data['current_problem']['digest']},headers=origin)
                        assert duplicate.status_code==409 and calls==['GET','POST']*(n+1)
                    assert not (receipts/live._P1_SPENT).exists()
                    assert len(list(receipts.glob('spent-operation-*')))==(1 if unknown else 2)
                    with service.store.transaction() as conn:
                        money=conn.execute('SELECT held,upper_booked FROM research_funding_accounts WHERE id=?',(expected.account_id,)).fetchone()
                        assert tuple(money)==((2_129_920,0) if unknown else (0,2*2_129_920))
                    changed=live._LiveHandle(main.app,binding,expected.model_copy(update={'owner_generation':'0'*32}),resource,NS(require_runtime=lambda:None),factory=live._FACTORY_LIVE)
                    with monkeypatch.context() as generation:
                        generation.setitem(live._LIVE,id(main.app),changed)
                        assert operations.current(main.app,service,actor) is None
                    live.retire(main.app,handle)
                assert live._PINNED_POLICY is None
            async with main.lifespan(main.app):
                base,headers,body,original=persisted
                reopened=await client.get(base+'/status',headers=headers)
                assert reopened.status_code==200 and reopened.json()==original
                # A new page has no sessionStorage operation key. The owner
                # view must locate the same durable operation without sending.
                rid=base.split('/')[3]
                located=await client.get('/api/research/'+rid)
                assert located.status_code==200,located.text
                recovered=located.json()['data'].get('external_first_answer_recovery')
                if unknown:
                    # The loop saved a newer revision after the uncertain send.
                    # Its view must not attach the old revision's operation.
                    assert recovered is None
                    recovered=original
                else:
                    assert recovered==original
                    assert recovered['metadata']['research_version']<=located.json()['data']['research_version']
                assert calls==['GET','POST']*(1 if unknown else 2)
                recovered_headers={'Idempotency-Key':recovered['operation_key']}
                assert (await client.get(base+'/status',headers=recovered_headers)).json()==original
                if not unknown:
                    saved=await client.get(base+'/result',headers=recovered_headers)
                    assert saved.status_code==200 and saved.json()['candidate']==candidate
                else:
                    assert (await client.get(base+'/result',headers=recovered_headers)).status_code==404
                assert (await client.post(base+'/confirm',json=body,headers=headers)).status_code==503
                assert calls==['GET','POST']*(1 if unknown else 2)
    with provider() as (server,provider_calls,_):asyncio.run(verify(server));assert provider_calls==[]


# Real schema18 migration + actual Main/Auth/Owner/local queue. No provider or
# permissive profile stub: Core's canonical catalog admission stays in use.
from tests.test_external_funding_v18 import existing_v17

@pytest.mark.parametrize("pin",[False,True],ids=["v18-no-pin","v18-pin-no-witness"])
def test_actual_main18_local_answer_owner_history_and_closed_legacy_execution(existing_v17,prepared,monkeypatch,pin):
    from tests.test_external_funding_v18 import migrate
    from web.backend.tests.test_research_first_answer import candidate,identity
    from research import first_answer,first_answer_queue,plan_native,native_plan_supervisor,source_supervisor
    from research.errors import ResearchError
    from services import external_live_production as production
    path,record,_=existing_v17
    migrate(path,record)
    (path.parent/first_answer_queue.LOCK_NAME).touch(mode=0o600,exist_ok=False)
    main,admission,paths,messages=prepared
    calls=[]
    def forbidden(*args,**kwargs):
        calls.append('unexpected')
        raise AssertionError('schema18 must not enter legacy Source/Native or seek credential without entry witness')
    for module,names in ((plan_native,('live_session','installation')),(native_plan_supervisor,('prepare_main_context','start')),(source_supervisor,('start',)),(production,('_load_credential','_fixed_file','_verify_runtime_files'))):
        for name in names:monkeypatch.setattr(module,name,forbidden)
    monkeypatch.setenv('STRUCTURAL_EXTERNAL_FIRST_ANSWER_ENABLED','true')
    if pin:monkeypatch.setattr(production,'_PINNED_POLICY',production.PinnedTargetPolicy('0'*64,'0'*64,'/no','/no',()))
    origin={'Origin':BETA};saved={}
    async def run():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)];service=binding.service
            assert binding.facts.profile.research_schema==18
            assert binding.native_context is binding.supervisor is None
            status=admission.safe_status(main.app)
            assert status['native_planner']=='FUNDING_CLOSED' and status['source_execute']=='unavailable'
            assert status['external_first_answer']=='ISSUER_UNBOUND'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                response=await client.post('/api/research',json=envelope({'problem':problem()}),headers=origin|{'Idempotency-Key':'v18-app-local-public'})
                assert response.status_code==200,response.text
                view=response.json()['data'];rid=view['research']['id'];owner=identity(client)
                assert view['capabilities']['external_first_answer']=='status_only'
                args={'input_revision':1,'problem_digest':view['current_problem']['digest'],'research_version':view['research_version']}
                queued=first_answer_queue.enqueue(service,owner,rid,**args)
                assert queued['status']=='queued'
                with first_answer_queue.worker_session(service) as runner:
                    job,raw=runner.claim_next();assert job.research_id==rid
                    completed=runner.finish(job,answer=candidate())
                    assert completed['status']=='completed'
                answer=first_answer.read(service,owner,rid,1)
                reopened=await client.get('/api/research/'+rid)
                assert reopened.status_code==200
                reopened_answer=await client.get(f'/api/research/{rid}/revisions/1/first-answer')
                assert reopened_answer.status_code==200 and reopened_answer.json()==answer
                history=await client.get('/api/research')
                assert history.status_code==200 and any(row['research_id']==rid for row in history.json()['data']['items'])
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as foreign:
                    await login(foreign,messages,'v18-foreign@example.invalid')
                    assert (await foreign.get('/api/research/'+rid)).status_code==404
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as anonymous:
                    assert (await anonymous.get('/api/research/'+rid)).status_code==401
                with pytest.raises(ResearchError):first_answer.save(service,owner,rid,input_revision=1,problem_digest=args['problem_digest'],research_version=args['research_version'],key='not-the-legacy-writer',answer=candidate())
                with service.store.transaction() as conn:
                    money_before=[tuple(row) for row in conn.execute('SELECT id,settled,held,upper_booked FROM research_funding_accounts ORDER BY id')]
                deleted=await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers=origin)
                assert deleted.status_code==200,deleted.text
                from research.external_funding_v18 import read_binding
                with service.store.transaction() as conn:
                    retained=read_binding(conn)
                    assert retained['status']=='retired' and retained['version']==2
                    assert retained['owner_principal'] is retained['owner_generation'] is retained['owner_gate_id'] is None
                    assert [tuple(row) for row in conn.execute('SELECT id,settled,held,upper_booked FROM research_funding_accounts ORDER BY id')]==money_before
                    assert conn.execute('SELECT count(*) FROM research_first_answers WHERE research_id=?',(rid,)).fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_first_answer_jobs WHERE research_id=?',(rid,)).fetchone()[0]==0
                saved.update(rid=rid)
        assert admission._STATE.get(id(main.app)) is None and not production._LIVE
    asyncio.run(run())
    assert calls==[] and saved


from web.backend.tests.test_formal_model_startup import startup,encoder,synthetic_readonly_mount

def test_actual_main18_background_queue_saved_result_reopens(existing_v17,prepared,startup,encoder,monkeypatch):
    from tests.test_external_funding_v18 import migrate
    from web.backend.tests.test_research_first_answer import candidate
    from research import first_answer_queue,first_answer_supervisor
    path,record,_=existing_v17;migrate(path,record)
    (path.parent/first_answer_queue.LOCK_NAME).touch(mode=0o600,exist_ok=False)
    main,admission,paths,messages=prepared
    entered=[]
    def public_fixture(question,search,*,cancel):
        assert search.formal is True
        entered.append(True)
        return {'status':'answered','content':candidate().model_dump(mode='json',exclude_none=True)}
    monkeypatch.setattr(first_answer_supervisor,'produce_background_answer',public_fixture)
    async def run():
        async with main.lifespan(main.app):
            assert admission.safe_status(main.app)['first_answer_local']=='ready'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages)
                response=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'v18-background-public'})
                assert response.status_code==200,response.text
                row=response.json()['data'];rid=row['research']['id'];url=f'/api/research/{rid}/revisions/1/first-answer'
                request={'problem_digest':row['current_problem']['digest'],'research_version':row['research_version']}
                queued=await client.post(url,json=request,headers={'Origin':BETA})
                assert queued.status_code in (200,202),queued.text
                for _ in range(80):
                    opened=await client.get(url)
                    if opened.status_code==200 and opened.json().get('status')=='provisional':break
                    await asyncio.sleep(.05)
                assert opened.status_code==200 and opened.json()['status']=='provisional',opened.text
                assert (await client.get(url)).json()==opened.json()
        assert first_answer_supervisor.current(main.app) is None
    asyncio.run(run());assert entered==[True]
