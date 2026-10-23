"""Synthetic actual Main15/auth/native producer/save/read controls. No paid I/O."""
import asyncio
from copy import deepcopy
import json
import sqlite3
from uuid import uuid4

import httpx
import pytest

from web.backend.tests.test_research_financial_registries import prepared,smtp,create,preview,save,login,BETA
from web.backend.tests.test_formal_main_admission import smtp as base_smtp
from web.backend.tests.test_research_financial_input_schemas import csv_text,CSV_HEADER
from web.backend.tests.test_research_financial_result_v2 import owner_fixture


async def setup_financial(client,rid,*,currency='CNY'):
    template,owner=owner_fixture(currency);request=template.data.request.data();rows=[]
    keys={r.id:r.key for r in owner.records}
    for record in owner.records:
        raw=record.model_dump(mode='json');row={key:raw[key] for key in CSV_HEADER if key in raw}
        for name in ('source_chain','source_refs','alternative_refs'):
            if name in row:row[name]=';'.join(keys[v] for v in row[name])
        rows.append({key:'' if value is None else value for key,value in row.items()})
    body,p=await preview(client,rid,text=csv_text(rows))
    _,saved=await save(client,rid,body,p,key='fin3-registry')
    assert saved.status_code==200,saved.text
    meta=saved.json()['data']['metadata'];ref=meta['registry_ref']
    read=await client.get(f'/api/research/{rid}/financial-registries/{ref["id"]}')
    assert read.status_code==200,read.text
    mapping={v['key']:v['registered_id'] for v in read.json()['data']['projection']['registry']['key_map']}
    request['interim_revenue_ref']=mapping[keys[request['interim_revenue_ref']]]
    request['historical_context_refs']=[mapping[keys[v]] for v in request['historical_context_refs']]
    return {'schema_version':'structure-research-v1','contract_revision':'financial-result-v2',
        'data':{'input_revision':1,'expected_research_version':2,'registry_ref':ref,'request':request}}


async def calculate(client,rid,body,key='fin3-calculate'):
    return await client.post(f'/api/research/{rid}/financial-calculations',json=body,
        headers={'Origin':BETA,'Idempotency-Key':key})


def test_actual_main15_financial_save_replay_views_and_reopen(prepared,tmp_path):
    main,admission,_,messages=prepared
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
            async with main.lifespan(main.app):
                await login(client,messages);rid=await create(client,'fin3-create');body=await setup_financial(client,rid)
                first=await calculate(client,rid,body);assert first.status_code==200,first.text
                data=first.json()['data'];meta=data['metadata'];ref=meta['result_ref']
                assert data['persisted'] is True and set(data['public_result'])=={'view','input_status','value'}
                assert meta['u2_goal_status']=='not_met' and meta['model_analysis_ran'] is False
                table=await client.get(f'/api/research/{rid}/financial-results/{ref}?view=table')
                chart=await client.get(f'/api/research/{rid}/financial-results/{ref}?view=chart')
                assert table.status_code==chart.status_code==200,(table.text,chart.text)
                values=[r['target']['revenue']['display'] for r in table.json()['data']['public_result']['value']['scenarios'][0]['years']]
                assert values==chart.json()['data']['public_result']['value']['chart_spec']['series'][0]['values']
                assert chart.json()['data']['public_result']['value']['chart_spec']['snapshot_digest']==meta['snapshot_digest']
                assert 'received_ref' not in table.text and 'execution_receipt' not in table.text
                assert (await calculate(client,rid,body)).json()==first.json()
                changed=deepcopy(body);changed['data']['request']['baseline_selection_reason']='different request'
                assert (await calculate(client,rid,changed)).status_code==409
                from api import auth
                from research import ResearchStore,financial_execution as ex,financial_input as native
                with ResearchStore(auth._store()).transaction() as conn:
                    row=conn.execute('SELECT * FROM research_financial_results WHERE result_ref=?',(ref,)).fetchone()
                    receipt=json.loads(row['execution_receipt_json']);snapshot=json.loads(row['snapshot_json'])
                    assert receipt['guard']['operations_used']==row['operations_used']==snapshot['operations_used']
                    assert receipt['producer_revision']=='owned-financial-local-v2-r1'
                    assert conn.execute("SELECT research_financial_input_allowed('research_financial_results','INSERT','[]')").fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_tasks').fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_funding_accounts').fetchone()[0]==0
                assert ex._CONTEXTS==ex._RETURNS==native._RESOLVED_OWNER=={}
                assert (await client.get('/api/health')).json()['checks']['native_planner']=='FUNDING_CLOSED'
                (tmp_path/'financial-result-metadata.json').write_text(json.dumps(meta,indent=2))
            assert admission._STATE.get(id(main.app)) is None
            async with main.lifespan(main.app):
                reopened=await client.get(f'/api/research/{rid}/financial-results/{ref}')
                assert reopened.status_code==200,reopened.text
                assert reopened.json()['data']['metadata']==meta
                assert (await calculate(client,rid,body)).json()['data']['metadata']==meta
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(run())


def test_actual_main15_financial_history_21_bad_cursor_and_safe_input(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid);refs=[]
                for i in range(21):
                    body['data']['expected_research_version']=i+2
                    response=await calculate(client,rid,body,f'fin3-history-{i}')
                    assert response.status_code==200,response.text
                    refs.append(response.json()['data']['metadata']['result_ref'])
                first=await client.get(f'/api/research/{rid}/financial-results')
                assert first.status_code==200,first.text
                data=first.json()['data'];assert len(data['items'])==20 and data['next_cursor']==data['items'][-1]['result_ref']
                second=await client.get(f'/api/research/{rid}/financial-results?cursor={data["next_cursor"]}')
                assert second.status_code==200 and len(second.json()['data']['items'])==1
                assert {v['result_ref'] for v in data['items']+second.json()['data']['items']}==set(refs)
                assert (await client.get(f'/api/research/{rid}/financial-results?cursor={uuid4()}')).status_code==409
                for suffix in ('?limit=21','?limit=2&limit=3','?cursor='):
                    assert (await client.get(f'/api/research/{rid}/financial-results'+suffix)).status_code==422
                for raw,status in ((b'{"x":NaN}',422),(b'{"secret_do_not_echo":1,"secret_do_not_echo":2}',422),(b' '*65537,413)):
                    bad=await client.post(f'/api/research/{rid}/financial-calculations',content=raw,
                        headers={'Origin':BETA,'Idempotency-Key':'fin3-bad','Content-Type':'application/json'})
                    assert bad.status_code==status and 'secret_do_not_echo' not in bad.text
    asyncio.run(run())


def test_actual_main15_result_bare_insert_and_cached_trigger_denied(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid)
                response=await calculate(client,rid,body);assert response.status_code==200,response.text
                from api import auth
                from research import ResearchStore
                from research.financial_input_guard import COLUMNS,RESULTS,install_hook
                store=ResearchStore(auth._store());columns=COLUMNS[RESULTS]
                with store.transaction() as conn:values=dict(conn.execute('SELECT * FROM '+RESULTS).fetchone())
                values.update(result_ref=str(uuid4()),run_id=str(uuid4()))
                sql='INSERT INTO '+RESULTS+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')'
                args=tuple(values[k] for k in columns)
                with store.transaction(write=True) as conn:
                    with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,args)
                    assert conn.execute("SELECT research_financial_input_allowed('research_financial_results','INSERT','[]')").fetchone()[0]==0
                # Deliberately ordinary SQLite, not a forged native positive.
                # A permissive observational authorizer cannot grant the real trigger.
                conn=sqlite3.connect(store.path,cached_statements=8)
                try:
                    install_hook(conn);compiles=[]
                    def observer(action,table,*rest):
                        if action==sqlite3.SQLITE_INSERT and table==RESULTS:compiles.append(table)
                        return sqlite3.SQLITE_OK
                    conn.set_authorizer(observer)
                    for _ in range(2):
                        with pytest.raises(sqlite3.DatabaseError):conn.execute(sql,args)
                    assert len(compiles)==1,'same prepared INSERT must be cached on second failed execution'
                    conn.rollback()
                finally:conn.close()
                with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM '+RESULTS).fetchone()[0]==1
    asyncio.run(run())


def test_actual_main15_cross_actor_historical_replay_readonly_delete_and_latewrite(prepared):
    from web.backend.tests.test_formal_main_admission import envelope,problem
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid)
                saved=await calculate(client,rid,body);assert saved.status_code==200,saved.text
                meta=saved.json()['data']['metadata'];ref=meta['result_ref']
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as other:
                    await login(other,messages,'foreign-fin3@example.invalid');await create(other,'foreign-root')
                    assert (await other.get(f'/api/research/{rid}/financial-results/{ref}')).status_code==404
                    assert (await calculate(other,rid,body)).status_code==404
                revised=problem();revised['summary']='synthetic revised problem'
                changed=await client.post(f'/api/research/{rid}/revisions',json=envelope({'expected_revision':1,'problem':revised}),
                    headers={'Origin':BETA,'Idempotency-Key':'fin3-revision'})
                assert changed.status_code==200,changed.text
                replay=await calculate(client,rid,body);assert replay.status_code==200,replay.text
                assert replay.json()['data']['is_historical'] is True and replay.json()['data']['metadata']==meta
                assert (await calculate(client,rid,body,'new-key-old-revision')).status_code==409
                from api import auth
                from research import ResearchStore
                store=ResearchStore(auth._store())
                with store.transaction(write=True) as conn:
                    conn.execute('UPDATE research_grants SET scopes=? WHERE research_id=?',(json.dumps(['read']),rid))
                assert (await client.get(f'/api/research/{rid}/financial-results/{ref}')).status_code==200
                assert (await calculate(client,rid,body)).status_code==404
                deleted=await client.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':BETA})
                assert deleted.status_code==200,deleted.text
                assert (await calculate(client,rid,body)).status_code in (401,404)
                with store.transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM research_financial_results').fetchone()[0]==0
                    assert conn.execute('SELECT count(*) FROM research_financial_registries').fetchone()[0]==0
    asyncio.run(run())


def test_actual_main15_result_capacity_rollback_and_possible_saved_response(prepared,monkeypatch):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid,currency='USD')
                large=deepcopy(body);request=large['data']['request'];scenario=request['scenarios'][0]
                template=deepcopy(scenario['costs'][0])
                for i in range(15):
                    cost=deepcopy(template);cost.update(id=f'adjust_{i}',kind='operating_adjustment',coverage=[])
                    for item in cost['values']:item['parameter'].update(id=f'adj_{i}_{item["year"]}',value='0.01')
                    scenario['costs'].append(cost)
                ids=[f'segment_{i}' for i in range(7)]+['unallocated']
                request['categories']=[{'id':name,'label':name,'definition':'synthetic exclusive partition','dimension':'monetization',
                    'excludes':[v for v in ids if v!=name],'kind':'unallocated' if name=='unallocated' else 'segment'} for name in ids]
                for i in range(7):
                    values=deepcopy(template['values'])
                    for item in values:item['parameter'].update(id=f'alloc_{i}_{item["year"]}',value='1',unit='million',currency='USD')
                    scenario['allocations'].append({'category_id':f'segment_{i}','mode':'amount','values':values})
                denied=await calculate(client,rid,large,'fin3-too-large');assert denied.status_code==413,denied.text
                from api import auth,research as route
                from research import ResearchStore,financial_execution as ex,financial_input as native
                store=ResearchStore(auth._store())
                with store.transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM research_financial_results').fetchone()[0]==0
                    assert conn.execute('SELECT version FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==2
                assert ex._CONTEXTS==ex._RETURNS==native._RESOLVED_OWNER=={}
                response=route.JSONResponse
                def lost_response(value,*a,**kw):
                    if type(value) is dict and value.get('data',{}).get('persisted') is True and value.get('contract_revision')=='financial-result-v2':
                        raise ValueError('synthetic post-commit response loss')
                    return response(value,*a,**kw)
                with monkeypatch.context() as fault:
                    fault.setattr(route,'JSONResponse',lost_response)
                    lost=await calculate(client,rid,body,'fin3-lost-response')
                    assert lost.status_code==503 and lost.json()['error']['code']=='RESPONSE_UNAVAILABLE',lost.text
                replay=await calculate(client,rid,body,'fin3-lost-response');assert replay.status_code==200,replay.text
                with store.transaction() as conn:assert conn.execute('SELECT count(*) FROM research_financial_results').fetchone()[0]==1
    asyncio.run(run())


def test_actual_main15_corrupt_owned_result_fails_read_and_history_without_repair(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid)
                saved=await calculate(client,rid,body);assert saved.status_code==200,saved.text
                ref=saved.json()['data']['metadata']['result_ref']
                from api import auth
                from research import ResearchStore
                store=ResearchStore(auth._store());conn=sqlite3.connect(store.path,isolation_level=None)
                try:
                    # Negative corruption of owned synthetic data, with exact
                    # original DDL restored. This is no native write positive.
                    ddl=conn.execute("SELECT sql FROM sqlite_schema WHERE name='research_financial_results_immutable'").fetchone()[0]
                    conn.execute('DROP TRIGGER research_financial_results_immutable')
                    conn.execute('UPDATE research_financial_results SET snapshot_digest=? WHERE result_ref=?',('0'*64,ref))
                    conn.execute(ddl)
                finally:conn.close()
                for suffix in ('',f'/{ref}'):
                    denied=await client.get(f'/api/research/{rid}/financial-results'+suffix)
                    assert denied.status_code==503 and denied.json()['error']['code']=='STORE_UNAVAILABLE',denied.text
    asyncio.run(run())


def test_actual_main15_noncanonical_executor_is_rejected_before_invocation(prepared,monkeypatch):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client);body=await setup_financial(client,rid)
                from research import financial_execution as execution,ResearchStore
                from api import auth
                calls=[]
                def substituted(*args,**kwargs):
                    calls.append('unapproved executor entered')
                    raise PermissionError('synthetic substitute must never run')
                with monkeypatch.context() as fault:
                    fault.setattr(execution,'execute',substituted)
                    response=await calculate(client,rid,body,'noncanonical-executor')
                    assert response.status_code==409,response.text
                    assert calls==[],'a substituted executor ran before code/globals verification'
                with ResearchStore(auth._store()).transaction() as conn:
                    assert conn.execute('SELECT count(*) FROM research_financial_results').fetchone()[0]==0
                    assert conn.execute('SELECT version FROM research_controls WHERE id=?',(rid,)).fetchone()[0]==2
                assert execution._CONTEXTS==execution._RETURNS=={}
    asyncio.run(run())
