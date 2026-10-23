"""FIN-2 real current Main/Auth/Owner/DB controls; no funding or execution issuer."""
import asyncio
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
import time
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from web.backend.tests.test_formal_main_admission import BETA,envelope,login,problem,prepared,source_ready,smtp as base_smtp
from web.backend.tests.test_research_financial_input_schemas import csv_text,preview_body,sample_rows


@pytest.fixture
def smtp(base_smtp):
    guard=sys.modules.get('main_smtp_task_guard')
    if guard is not None:guard.OWNED_MAIN_SMTP_PORTS.add(base_smtp[0])
    try:yield base_smtp
    finally:
        if guard is not None:guard.OWNED_MAIN_SMTP_PORTS.discard(base_smtp[0])


async def create(client,key='fin2-create'):
    response=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':key})
    assert response.status_code==200,response.text
    return response.json()['data']['research']['id']


async def preview(client,rid,*,version=1,revision=1,text=None):
    body=preview_body(csv_text() if text is None else text);body['data'].update(input_revision=revision,expected_research_version=version)
    response=await client.post('/api/research/'+rid+'/financial-import-preview',json=body,headers={'Origin':BETA,'Idempotency-Key':'fin2-preview'})
    assert response.status_code==200,response.text
    return body,response.json()


async def save(client,rid,body,previewed,key='fin2-save'):
    request={**body,'data':{**body['data'],'preview_digest':previewed['data']['preview_digest'],'confirmed':True}}
    response=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':key})
    return request,response


def digest(value):
    from research.financial_policy import canonical
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def test_actual_main15_save_private_public_mapping_replay_and_default_result_closed(prepared,tmp_path):
    main,admission,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                body,p=await preview(client,rid)
                request,saved=await save(client,rid,body,p);assert saved.status_code==200,saved.text
                result=saved.json();m=result['data']['metadata'];ref=m['registry_ref']['id']
                assert m['research_version_before']==1 and m['research_version_after']==2
                assert result['data']['current']=={'input_revision':1,'research_version':2} and result['data']['is_historical'] is False
                opened=await client.get('/api/research/'+rid+'/financial-registries/'+ref)
                assert opened.status_code==200,opened.text
                data=opened.json()['data'];projection=data['projection'];registry=projection['registry']
                assert projection['csv_text']==csv_text() and data['public_projection_digest']==digest(projection)
                assert 'received_ref' not in registry['receipt'] and 'native' not in data
                mapping={v['key']:v['registered_id'] for v in registry['key_map']}
                assert registry['records'][1]['source_refs']==[mapping['statement']]
                assert registry['records'][1]['value']=='1e+02' and registry['records'][2]['declared_basis']=='media_estimate'
                assert m['request_digest']==digest(request) and m['preview_digest']==p['data']['preview_digest']
                again=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert again.status_code==200 and again.json()==result
                from api import auth
                from research import ResearchStore
                from research.financial_input_guard import REGISTRIES,RESULTS,statement_allowed
                with ResearchStore(auth._store()).transaction() as conn:
                    assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
                    assert conn.execute('SELECT count(*) FROM '+REGISTRIES).fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM '+RESULTS).fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
                    cached=json.loads(conn.execute("SELECT result_json FROM research_idempotency WHERE operation='financial-registry-save'").fetchone()[0]);assert cached=={'registry_ref':ref}
                    private=conn.execute('SELECT * FROM '+REGISTRIES).fetchone()
                    assert digest(json.loads(private['registry_json']))==m['registry_ref']['digest']
                    assert private['received_ref'] not in json.dumps(projection)
                    assert conn.execute("SELECT research_financial_input_allowed('research_financial_results','INSERT','[]')").fetchone()[0]==0
                    assert statement_allowed(conn,sqlite3.SQLITE_INSERT,RESULTS,None) is False
                listed=await client.get('/api/research/'+rid+'/financial-registries')
                assert listed.status_code==200 and listed.json()['data']['items'][0]['registry_ref']==m['registry_ref']
                health=(await client.get('/api/health')).json();assert health['checks']['native_planner']=='FUNDING_CLOSED'
                calculation_routes={(route.path,tuple(sorted(route.methods)),route.endpoint.__name__)
                                    for route in main.app.routes if 'calculat' in route.path or '/financial-results' in route.path}
                assert calculation_routes=={
                    ('/api/research/{research_id}/financial-calculations',('POST',),'calculate_research_financial'),
                    ('/api/research/{research_id}/financial-results',('GET',),'list_research_financial_results'),
                    ('/api/research/{research_id}/financial-results/{result_ref}',('GET',),'read_research_financial_result')}
                (tmp_path/'confirmation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
                (tmp_path/'read.json').write_text(json.dumps(opened.json(),ensure_ascii=False,indent=2))
                print('FIN2_MAIN:'+json.dumps({'actual_main':True,'schema':15,'no_funding_or_tasks':True,'result_insert_closed':True,'registry_ref':ref,'public_projection_digest':data['public_projection_digest']}))
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(run())


def test_actual_main15_Source_READY_same_inode_request_store_and_native_retirement(prepared):
    main,admission,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            await source_ready(main,admission)
            binding=admission._STATE[id(main.app)];supervisor=binding.supervisor
            from api import auth
            from research import ResearchStore,ResearchService,source_supervisor as control
            store=ResearchStore(auth._store());service=ResearchService(store)
            assert service is not binding.service and store is not binding.service.store
            control.require_available(main.app,service)
            assert service.runtime_capability_facts().profile.research_schema==15
            assert control._select(store)==[] and control._select(store,cleanup_only=True)==[]
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                receipt=await asyncio.to_thread(admission.close_source,binding,deadline_monotonic=time.monotonic()+20)
                assert receipt.state==receipt.reason=='CLOSED' and receipt.pending_task_id is None
                assert receipt.supervisor_ref==supervisor.reference and not supervisor._thread.is_alive()
                with pytest.raises(Exception):control.require_available(main.app,service)
                assert (await client.get('/api/research/'+rid)).status_code==200
                body,p=await preview(client,rid);_,saved=await save(client,rid,body,p)
                assert saved.status_code==200,saved.text
        assert admission._STATE.get(id(main.app)) is None and not supervisor._thread.is_alive()
    asyncio.run(run())


def test_actual_multiple_same_problem_history_cursor_original_P_and_historical_replay(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                body,p=await preview(client,rid);request,first=await save(client,rid,body,p);assert first.status_code==200,first.text
                first=first.json()['data'];old_ref=first['metadata']['registry_ref']['id']
                rows=sample_rows();rows[1]['value']='101'
                body2,p2=await preview(client,rid,version=2,text=csv_text(rows));_,second=await save(client,rid,body2,p2,key='fin2-second')
                assert second.status_code==200,second.text
                second=second.json()['data'];assert second['metadata']['registry_ref']['id']!=old_ref
                page=await client.get('/api/research/'+rid+'/financial-registries?limit=1');assert page.status_code==200,page.text
                page=page.json()['data'];assert len(page['items'])==1 and page['items'][0]['is_historical'] is False and page['next_cursor']
                next_page=await client.get('/api/research/'+rid+'/financial-registries',params={'limit':'1','cursor':page['next_cursor']})
                assert next_page.status_code==200,next_page.text
                assert next_page.json()['data']['items'][0]['registry_ref']['id']!=page['items'][0]['registry_ref']['id']
                assert next_page.json()['data']['next_cursor'] is None
                old=(await client.get('/api/research/'+rid+'/financial-registries/'+old_ref)).json()['data']
                assert old['is_historical'] is False and old['current']['research_version']==3
                assert old['metadata']==first['metadata'] and old['public_projection_digest']==first['public_projection_digest']
                changed={**request,'data':{**request['data'],'csv_text':csv_text(rows)}}
                conflict=await client.post('/api/research/'+rid+'/financial-registries',json=changed,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert conflict.status_code==409 and conflict.json()['error']['code']=='IDEMPOTENCY_CONFLICT'
                updated=problem();updated['original_input']+=' 我补充了服务时间变化这一观察。'
                revise=await client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':1,'problem':updated}),headers={'Origin':BETA,'Idempotency-Key':'fin2-revision'})
                assert revise.status_code==200,revise.text
                replay=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert replay.status_code==200,replay.text
                replay=replay.json()['data'];assert replay['metadata']==first['metadata'] and replay['is_historical'] is True
                assert replay['current']=={'input_revision':2,'research_version':4}
                forbidden=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-old-revision-new-key'})
                assert forbidden.status_code==409 and forbidden.json()['error']['code']=='REVISION_CONFLICT'
                body3,p3=await preview(client,rid,revision=2,version=4);_,third=await save(client,rid,body3,p3,key='fin2-new-revision')
                assert third.status_code==200,third.text
                assert third.json()['data']['metadata']['registry_ref']['id'] not in (old_ref,second['metadata']['registry_ref']['id'])
                history=(await client.get('/api/research/'+rid+'/financial-registries')).json()['data']
                assert len(history['items'])==3 and sum(item['is_historical'] for item in history['items'])==2
                for query in ('limit=01','limit=21','limit=1&limit=2','unknown=x','cursor=','cursor=not-a-uuid'):
                    assert (await client.get('/api/research/'+rid+'/financial-registries?'+query)).status_code==422
                other=await create(client,key='fin2-other-root')
                bad=await client.get('/api/research/'+other+'/financial-registries',params={'cursor':old_ref})
                assert bad.status_code==409 and bad.json()['error']['code']=='REVISION_CONFLICT'
    asyncio.run(run())


def test_actual_scope_rejections_and_B_only_account_delete_no_late_replay(prepared,monkeypatch):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            transport=httpx.ASGITransport(app=main.app)
            async with httpx.AsyncClient(transport=transport,base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body,p=await preview(client,rid)
                from research import paid_control,ResearchStore,ResearchService
                from research import financial_input as inputs,financial_input_guard as guard
                from api import auth
                captured=[];issue=paid_control.issue_authenticated_action
                def observe(request,**kwargs):
                    source=issue(request,**kwargs)
                    if kwargs['action']=='financial-registry-save':captured.append(source)
                    return source
                monkeypatch.setattr(paid_control,'issue_authenticated_action',observe)
                request,response=await save(client,rid,body,p);assert response.status_code==200,response.text
                ref=response.json()['data']['metadata']['registry_ref']['id'];source=captured[-1]
                assert source.active is False
                parsed=inputs.types.decode_financial_registry_confirmation(json.dumps(request).encode()).data
                store=ResearchStore(auth._store());service=ResearchService(store)
                for fake in (source,SimpleNamespace(**{k:getattr(source,k) for k in source.__slots__})):
                    with pytest.raises(PermissionError):inputs.save_registry(service,source.identity,rid,parsed,'fin2-save',fake)
                pid=service._principal(source.identity)
                with service.authorization.owner_gate(pid) as lease,store.transaction(write=True) as conn:
                    row=conn.execute('SELECT * FROM '+guard.REGISTRIES+' WHERE registry_ref=?',(ref,)).fetchone()
                    values=tuple(row[k] for k in guard.REGISTRY_COLUMNS)
                    with pytest.raises(PermissionError):
                        with guard._write_scope(conn,service,lease,guard.REGISTRIES,'INSERT',values,identity=source.identity,source=source,key='fin2-save',request=parsed):pass
                    for sql,args in (("UPDATE research_financial_registries SET received_at=received_at",()),
                                     ("DELETE FROM research_financial_registries",()),
                                     ('INSERT OR REPLACE INTO research_financial_registries('+','.join(guard.REGISTRY_COLUMNS)+') VALUES('+','.join('?' for _ in values)+')',values)):
                        with pytest.raises(sqlite3.Error):conn.execute(sql,args)
                    assert conn.execute('SELECT count(*) FROM '+guard.REGISTRIES).fetchone()[0]==1
                    # Disable only the compilation authorizer to independently
                    # exercise the installed SQL/UDF guard. This is negative:
                    # no writer frame, action, or result producer is installed.
                    scope=paid_control._current_scope(conn)
                    conn.set_authorizer(None)
                    try:
                        sql='INSERT INTO '+guard.REGISTRIES+'('+','.join(guard.REGISTRY_COLUMNS)+') VALUES('+','.join('?' for _ in values)+')'
                        distinct={**dict(row),'registry_ref':str(uuid4()),'received_ref':str(uuid4())}
                        no_duplicate=tuple(distinct[k] for k in guard.REGISTRY_COLUMNS)
                        for _ in range(2):
                            with pytest.raises(sqlite3.Error):conn.execute(sql,no_duplicate)
                        common={k:row[k] for k in guard.COMMON_COLUMNS}
                        fake={**common,'result_ref':ref,'result_type':'financial_scenario_v2','registry_ref':ref,'registry_revision':1,'registry_digest':row['registry_digest'],
                              'run_id':ref,'recorded_at':row['received_at'],'policy_revision':'not-an-execution','producer_revision':'not-a-producer',
                              'execution_code_digest':'0'*64,'execution_status':'completed','operations_used':0,
                              'operation_json':'{}','expectation_json':'{}','execution_receipt_json':'{}','snapshot_json':'{}','snapshot_digest':'0'*64}
                        result_values=tuple(fake[k] for k in guard.RESULT_COLUMNS)
                        for keyword in ('INSERT','INSERT OR REPLACE','INSERT OR IGNORE'):
                            with pytest.raises(sqlite3.Error):conn.execute(keyword+' INTO '+guard.RESULTS+'('+','.join(guard.RESULT_COLUMNS)+') VALUES('+','.join('?' for _ in result_values)+')',result_values)
                        assert conn.execute('SELECT count(*) FROM '+guard.RESULTS).fetchone()[0]==0
                    finally:scope.refresh_authorizer()
                async with httpx.AsyncClient(transport=transport,base_url=BETA) as other:
                    await login(other,messages,email='fin2-other@example.invalid')
                    assert (await other.get('/api/research/'+rid+'/financial-registries/'+ref)).status_code==404
                    assert (await save(other,rid,body,p,key='other-actor'))[1].status_code==404
                with store.transaction(write=True) as conn:
                    scopes=conn.execute('SELECT scopes FROM research_grants WHERE research_id=?',(rid,)).fetchone()[0]
                    conn.execute("UPDATE research_grants SET scopes='[\"read\"]' WHERE research_id=?",(rid,))
                assert (await client.get('/api/research/'+rid+'/financial-registries/'+ref)).status_code==200
                assert (await save(client,rid,body,p))[1].status_code==404
                with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=?",(rid,))
                assert (await client.get('/api/research/'+rid+'/financial-registries/'+ref)).status_code==404
                assert (await client.get('/api/research/'+rid+'/financial-registries')).status_code==404
                with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET scopes=?,status='active' WHERE research_id=?",(scopes,rid))
                deleted=await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})
                assert deleted.status_code==200,deleted.text
                with store.transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM '+guard.REGISTRIES).fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM '+guard.RESULTS).fetchone()[0]==0
                    assert conn.execute("SELECT count(*) FROM research_idempotency WHERE operation='financial-registry-save'").fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
                assert (await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})).status_code in (401,404)
    asyncio.run(run())


def test_actual_CAS_rollback_and_response_failure_preserve_key_and_original_preview(prepared,monkeypatch):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body,p=await preview(client,rid)
                from api import auth,research as api
                from research import ResearchStore,ResearchService,financial_input as inputs
                from research.errors import ResearchError
                store=ResearchStore(auth._store())
                def facts():
                    with store.transaction() as conn:
                        return (conn.execute('SELECT version FROM research_controls WHERE id=?',(rid,)).fetchone()[0],
                                conn.execute('SELECT count(*) FROM research_financial_registries').fetchone()[0],
                                conn.execute("SELECT count(*) FROM research_idempotency WHERE operation='financial-registry-save'").fetchone()[0])
                original_cap=inputs._response_cap
                def reject_read_admission(result,**kwargs):
                    if type(result) is inputs.types.FinancialRegistryReadResponse:raise ResearchError('PAYLOAD_LIMIT',413,'synthetic bounded response rejection')
                    return original_cap(result,**kwargs)
                with monkeypatch.context() as fault:
                    fault.setattr(inputs,'_response_cap',reject_read_admission)
                    _,denied=await save(client,rid,body,p,key='bounded-reject');assert denied.status_code==413,denied.text
                assert facts()==(1,0,0)
                remember=ResearchService._remember
                def fail_after_actual_remember(self,*args,**kwargs):
                    result=remember(*args,**kwargs)
                    if args[2]=='financial-registry-save':raise OSError('synthetic failure after ref cache insertion')
                    return result
                with monkeypatch.context() as fault:
                    fault.setattr(ResearchService,'_remember',fail_after_actual_remember)
                    _,failed=await save(client,rid,body,p,key='atomic-key');assert failed.status_code==503,failed.text
                assert facts()==(1,0,0)
                project=api.projection_bytes
                def fail_final_projection(result):
                    if result.get('contract_revision')=='financial-input-v2' and result.get('data',{}).get('persisted') is True:raise ValueError('synthetic response failure after commit')
                    return project(result)
                with monkeypatch.context() as fault:
                    fault.setattr(api,'projection_bytes',fail_final_projection)
                    request,failed=await save(client,rid,body,p,key='atomic-key')
                    assert failed.status_code==503 and failed.json()['error']['code']=='RESPONSE_UNAVAILABLE',failed.text
                    assert '可能已保存' in failed.json()['error']['message']
                assert facts()==(2,1,1)
                replay=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'atomic-key'})
                assert replay.status_code==200 and replay.json()['data']['metadata']['preview_digest']==p['data']['preview_digest']
                assert facts()==(2,1,1)
                # Two actual requests race on one saved version. SQLite/OwnerGate
                # must preserve one immutable baseline and reject the stale peer.
                body2,p2=await preview(client,rid,version=2)
                answers=await asyncio.gather(save(client,rid,body2,p2,key='race-a'),save(client,rid,body2,p2,key='race-b'))
                assert sorted(answer.status_code for _,answer in answers)==[200,409]
                assert facts()==(3,2,2)
                body3,p3=await preview(client,rid,version=3)
                transaction=ResearchStore.transaction
                @contextmanager
                def lose_commit_ack(self,*,write=False):
                    with transaction(self,write=write) as conn:yield conn
                    if write:raise OSError('synthetic lost acknowledgement after actual commit/close')
                with monkeypatch.context() as fault:
                    fault.setattr(ResearchStore,'transaction',lose_commit_ack)
                    request3,unknown=await save(client,rid,body3,p3,key='commit-unknown')
                    assert unknown.status_code==503 and unknown.json()['error']['code']=='RESPONSE_UNAVAILABLE',unknown.text
                    assert '可能已保存' in unknown.json()['error']['message']
                assert facts()==(4,3,3)
                replay=await client.post('/api/research/'+rid+'/financial-registries',json=request3,headers={'Origin':BETA,'Idempotency-Key':'commit-unknown'})
                assert replay.status_code==200 and replay.json()['data']['metadata']['research_version_after']==4,replay.text
                assert facts()==(4,3,3)
    asyncio.run(run())


def test_actual_fixed_decoder_origin_old64k_and_registry_integrity_fail_closed(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body,p=await preview(client,rid)
                request={**body,'data':{**body['data'],'preview_digest':p['data']['preview_digest'],'confirmed':True}}
                url='/api/research/'+rid+'/financial-registries'
                # Existing Auth explicitly permits absent Origin for native
                # non-browser clients; a supplied foreign Origin stays denied.
                for headers in ({'Origin':'https://other.invalid','Idempotency-Key':'origin'}, {'Origin':BETA}):
                    response=await client.post(url,json=request,headers=headers);assert response.status_code in (403,422),response.text
                for change in ({'confirmed':1},{'preview_digest':'0'*64},{'expected_research_version':2},{'input_revision':2}):
                    response=await client.post(url,json={**request,'data':{**request['data'],**change}},headers={'Origin':BETA,'Idempotency-Key':'bad-fixed'})
                    assert response.status_code in (409,422),response.text
                raw=json.dumps(request).encode()
                for raw_bad in (raw.replace(b'"confirmed": true',b'"confirmed": true,"confirmed":true'),raw+b' '*(794625-len(raw))):
                    response=await client.post(url,content=raw_bad,headers={'Origin':BETA,'Idempotency-Key':'bad-raw','Content-Type':'application/json'})
                    assert response.status_code in (413,422),response.text
                oversized=envelope({'expected_revision':1,'problem':problem()});oversized['data']['problem']['original_input']='x'*65537
                old=await client.post('/api/research/'+rid+'/revisions',json=oversized,headers={'Origin':BETA,'Idempotency-Key':'old64'})
                assert old.status_code==413,old.text
                _,saved=await save(client,rid,body,p);assert saved.status_code==200,saved.text
                ref=saved.json()['data']['metadata']['registry_ref']['id']
                from api import auth
                from research import ResearchStore
                from research.financial_input_schemas import PublicOwnerFinancialRegistryV2
                opened=(await client.get(url+'/'+ref)).json()['data']
                registry=opened['projection']['registry']
                for mutate in ('map','domain','claim','extra','flag','version'):
                    altered=json.loads(json.dumps(registry))
                    if mutate=='map':altered['key_map'][0]['registered_id']=altered['records'][1]['id']
                    elif mutate=='domain':altered['records'][1]['source_refs']=[altered['records'][2]['id']]
                    elif mutate=='claim':altered['records'][1]['declared_basis']='missing'
                    elif mutate=='extra':altered['received_ref']='12345678-1234-4234-8234-123456789abc'
                    elif mutate=='flag':altered['records'][0]['system_verified']=0
                    else:altered['binding']['research_version_after']=9
                    with pytest.raises(ValueError):PublicOwnerFinancialRegistryV2.model_validate_json(json.dumps(altered))
                store=ResearchStore(auth._store())
                # Deliberately corrupt owned synthetic immutable data offline,
                # restoring exact DDL. The reader must not repair or skip it.
                conn=sqlite3.connect(store.path,isolation_level=None)
                try:
                    sql=conn.execute("SELECT sql FROM sqlite_schema WHERE name='research_financial_registries_immutable'").fetchone()[0]
                    conn.execute('DROP TRIGGER research_financial_registries_immutable')
                    conn.execute("UPDATE research_financial_registries SET registry_digest=? WHERE registry_ref=?",('0'*64,ref))
                    conn.execute(sql)
                finally:conn.close()
                for path in (url+'/'+ref,url):
                    denied=await client.get(path);assert denied.status_code==503 and denied.json()['error']['code']=='STORE_UNAVAILABLE',denied.text
                replay=await client.post(url,json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert replay.status_code==503 and replay.json()['error']['code']=='STORE_UNAVAILABLE',replay.text
                with store.transaction() as conn:assert conn.execute('SELECT registry_digest FROM research_financial_registries').fetchone()[0]=='0'*64
    asyncio.run(run())


def test_actual_B_only_pending_delete_resumes_under_fresh_native_owner_and_never_replays(prepared,monkeypatch):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body,p=await preview(client,rid)
                request,saved=await save(client,rid,body,p);assert saved.status_code==200,saved.text
                from api import auth
                from research import ResearchStore,financial_input as inputs
                from research.financial_input_guard import REGISTRIES,RESULTS
                erase=inputs.erase_in
                def fail_after_real_erase(*args,**kwargs):
                    erase(*args,**kwargs)
                    raise OSError('synthetic interruption before research-erased commit')
                store=ResearchStore(auth._store())
                with monkeypatch.context() as fault:
                    fault.setattr(inputs,'erase_in',fail_after_real_erase)
                    deleted=await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})
                    assert deleted.status_code==500 and deleted.json()['access_ended'] is True,deleted.text
                with store.transaction() as conn:
                    job=conn.execute('SELECT * FROM auth_deletion_jobs').fetchone();job_id=job['id']
                    assert job['state']=='pending' and job['research_erased']==0
                    assert conn.execute('SELECT count(*) FROM '+REGISTRIES).fetchone()[0]==1
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
                denied=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert denied.status_code in (401,404),denied.text
                result=await asyncio.to_thread(auth.resume_account_deletion,job_id)
                assert result['removed']['research']['financial_registries']==1
                again=await asyncio.to_thread(auth.resume_account_deletion,job_id);assert again==result
                with store.transaction() as conn:
                    assert conn.execute('SELECT state FROM auth_deletion_jobs').fetchone()[0]=='completed'
                    for table in (REGISTRIES,RESULTS,'research_idempotency'):assert conn.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
                denied=await client.post('/api/research/'+rid+'/financial-registries',json=request,headers={'Origin':BETA,'Idempotency-Key':'fin2-save'})
                assert denied.status_code in (401,404),denied.text
    asyncio.run(run())
