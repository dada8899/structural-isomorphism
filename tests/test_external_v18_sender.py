"""Real v18 Main/Auth/ledger with synthetic TLS only; no key or provider."""
import asyncio
from contextlib import contextmanager
import json
import os
import time
from types import SimpleNamespace as NS
from uuid import uuid4

import httpx
import pytest

from tests.test_external_funding_v18 import existing_v17, migrate
from web.backend.tests.test_formal_main_admission import BETA, envelope, login, prepared, problem, smtp


@pytest.mark.parametrize('unknown', [False, True], ids=['known-return', 'unknown-held'])
@pytest.mark.parametrize('price_changed',[False,True],ids=['fresh-price','expired-before-post'])
def test_owner_key18_uses_independent_account_and_reopens_without_resending(prepared, existing_v17, monkeypatch, tmp_path, unknown,price_changed):
    from research.external_first_answer_issuer_contract import OwnerKeyStartupBinding
    from research.external_funding_v18 import read_binding, project_usage
    from services import external_live_production as live, external_live_sender as sender
    main,admission,_,messages=prepared
    path,registration,old_account=existing_v17
    migrate(path,registration)
    unknown=unknown or price_changed
    calls=[]
    candidate={'status':'candidate','explanation':'反馈延迟可能让调整发生在状态变化之后。',
        'assumptions':['仅为公开合成问题。'],'next_check':'对照实际反馈间隔。','evidence_status':'not_checked'}
    class Socket:
        def settimeout(self,*_):pass
        def connect(self,*_):pass
        def close(self):pass
        def sendall(self,wire):
            method=wire.split(b' ',1)[0].decode();calls.append(method)
            body=({'is_available':True,'balance_infos':[{'currency':'CNY','total_balance':'400'}]} if method=='GET' else
                {'id':'synthetic-owner-key18-receipt','model':'deepseek-flash',
                 'usage':None if unknown else {'prompt_tokens':100,'completion_tokens':20,'total_tokens':120},
                 'choices':[{'finish_reason':'stop','message':{'content':json.dumps(candidate,ensure_ascii=False)}}]})
            raw=json.dumps(body,ensure_ascii=False).encode()
            self.reply=b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(raw)).encode()+b'\r\n\r\n'+raw
        def recv(self,size):raw=self.reply[:size];self.reply=self.reply[size:];return raw
    receipts=tmp_path/'owned-operation-receipts';receipts.mkdir(mode=0o700)
    @contextmanager
    def receipt_directory(_):
        fd=os.open(receipts,os.O_RDONLY|os.O_DIRECTORY)
        try:yield fd
        finally:os.close(fd)

    async def verify():
        async with main.lifespan(main.app):
            binding=admission._STATE[id(main.app)];service=binding.service
            assert binding.facts.profile.research_schema==18
            with service.store.transaction() as conn:
                funding=read_binding(conn)
                epoch=conn.execute('SELECT epoch FROM research_principals WHERE id=?',(funding['owner_principal'],)).fetchone()[0]
            policy=sender.EndpointPolicy('1.1.1.1','a'*64,'b'*64,'c'*64,2_129_920,request_mode='saved-question')
            expected=OwnerKeyStartupBinding(startup_id=str(uuid4()),source_commit='a'*40,source_manifest_digest='b'*64,
                runtime_closure_digest='c'*64,unit_digest='d'*64,database_dev=service.store.storage_identity[0],
                database_ino=service.store.storage_identity[1],receipts_dev=1,receipts_ino=1,schema_version=18,
                runtime_uid=981,runtime_gid=976,owner_principal=funding['owner_principal'],owner_generation=funding['owner_generation'],
                owner_epoch=epoch,owner_gate_id=funding['owner_gate_id'],account_id=funding['account_id'],
                economic_binding=funding['local_binding_ref'],funding_epoch=funding['funding_epoch'],
                credential_incarnation=funding['credential_incarnation'],ledger_policy_digest='e'*64,
                endpoint_policy_digest=policy.wire_digest(),credential_source='owner_supplied',
                authorization_event_ref=funding['authorization_event_ref'],payer_identity_status='unknown',payer_id=None)
            resource=live._LiveCredential(bytearray(b'PUBLIC-SYNTHETIC-NOT-A-KEY'),factory=live._FACTORY_LIVE)
            handle=live._LiveHandle(main.app,binding,expected,resource,NS(require_runtime=lambda:None),factory=live._FACTORY_LIVE)
            with monkeypatch.context() as patch:
                patch.setitem(live._LIVE,id(main.app),handle)
                patch.setattr(sender,'_PINNED_ENDPOINT',policy)
                patch.setattr(sender,'_trust',lambda *_,**__: (NS(wrap_socket=lambda sock,**_:sock),int(time.time())+60,1_000_000))
                price_calls=[]
                def fresh_price(*args,**kwargs):
                    price_calls.append(1)
                    if price_changed and len(price_calls)>1:
                        from research.external_first_answer_contract import ContractError
                        raise ContractError('external_price_basis_unbound')
                    return {'valid_until':int(time.time())+60,'max_prompt_tokens':1000000}
                patch.setattr(sender,'_price_window',fresh_price)
                patch.setattr(sender,'socket',NS(AF_INET=2,AF_INET6=10,SOCK_STREAM=1,socket=lambda *_:Socket()))
                patch.setattr(live,'_receipt_directory',receipt_directory)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                    await login(client,messages)
                    origin={'Origin':BETA}
                    made=await client.post('/api/research',json=envelope({'problem':problem()}),
                        headers=origin|{'Idempotency-Key':'owner-key18-public-question'})
                    assert made.status_code==200,made.text
                    data=made.json()['data'];rid=data['research']['id'];base=f'/api/research/{rid}/revisions/1/external-first-answer'
                    quote=await client.post(base+'/preview',json={'research_version':data['research_version'],
                        'problem_digest':data['current_problem']['digest']},headers=origin)
                    assert quote.status_code==200,quote.text
                    offered=quote.json();headers=origin|{'Idempotency-Key':offered['operation_key']}
                    body={k:offered[k] for k in ('preview_digest','request_digest','upper_units')}
                    body.update(purpose='external-first-answer-question-v1',confirm_exact_question=True,
                        confirm_maximum_cost=True,declares_right_to_send=True)
                    response=await client.post(base+'/confirm',json=body,headers=headers)
                    assert response.status_code==200,response.text
                    assert response.json()['status']==('unknown' if unknown else 'completed')
                    assert calls==(['GET'] if price_changed else ['GET','POST'])
                    assert (await client.post(base+'/confirm',json=body,headers=headers)).json()==response.json()
                    located=await client.get('/api/research/'+rid)
                    assert located.status_code==200,located.text
                    recovery=located.json()['data']['external_first_answer_recovery']
                    assert recovery==response.json()
                    assert (await client.get(base+'/status',headers={'Idempotency-Key':recovery['operation_key']})).json()==recovery
                    with service.store.transaction() as conn:
                        assert tuple(conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(old_account[0],)).fetchone())==old_account
                        assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts WHERE id=?',
                            (registration.account_id,)).fetchone())==((2_129_920,0) if unknown else (0,2_129_920))
                        assert project_usage(conn)==2_129_920
                    assert calls==(['GET'] if price_changed else ['GET','POST'])
                    deleted=await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers=origin)
                    assert deleted.status_code==(503 if unknown else 200),deleted.text
                    with service.store.transaction() as conn:
                        retained=read_binding(conn)
                        assert retained['status']==('active' if unknown else 'retired')
                        assert retained['version']==(1 if unknown else 2)
                        if unknown:
                            assert retained['owner_principal']==registration.owner_principal
                            assert conn.execute('SELECT state FROM research_external_first_answer_runs WHERE id=?',
                                (offered['operation_key'],)).fetchone()[0]=='unknown'
                        else:
                            assert retained['owner_principal'] is retained['owner_generation'] is retained['owner_gate_id'] is None
                            assert conn.execute('SELECT count(*) FROM research_external_first_answer_runs').fetchone()[0]==0
                        assert tuple(conn.execute('SELECT * FROM research_funding_accounts WHERE id=?',(old_account[0],)).fetchone())==old_account
                        assert tuple(conn.execute('SELECT held,upper_booked FROM research_funding_accounts WHERE id=?',
                            (registration.account_id,)).fetchone())==((2_129_920,0) if unknown else (0,2_129_920))
                    assert (await client.get('/api/research/'+rid)).status_code==(200 if unknown else 401)
                    assert calls==(['GET'] if price_changed else ['GET','POST'])
                live.retire(main.app,handle)
    asyncio.run(verify())
