"""Actual v17 lifecycle must not seek any external material without proof."""
import asyncio

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,prepared,problem,smtp


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
                assert (await client.post(base+'/confirm',json=body,headers=headers)).status_code==503
                assert calls==['GET','POST']*(1 if unknown else 2)
    with provider() as (server,provider_calls,_):asyncio.run(verify(server));assert provider_calls==[]
