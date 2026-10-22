"""FIN-1 actual Main/Auth controls. No fake READY, rows or write authority."""
import asyncio
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import httpx
import pytest
from starlette.requests import Request

from web.backend.tests.test_formal_main_admission import (
    BETA, envelope, login, prepared, problem, smtp as base_smtp,
)
from web.backend.tests.test_research_financial_input_schemas import csv_text, preview_body, sample_rows


@pytest.fixture
def smtp(base_smtp):
    """Register only the actual already-bound owned SMTP fixture with the guard."""
    guard=sys.modules.get('main_smtp_task_guard')
    if guard is not None:guard.OWNED_MAIN_SMTP_PORTS.add(base_smtp[0])
    try:yield base_smtp
    finally:
        if guard is not None:guard.OWNED_MAIN_SMTP_PORTS.discard(base_smtp[0])


def research_snapshot():
    from api import auth
    from research import ResearchStore
    with ResearchStore(auth._store()).transaction() as conn:
        tables=[r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'research_%' ORDER BY name")]
        values={name:[list(r) for r in conn.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in tables}
        assert conn.total_changes==0
    def blob(value):
        if type(value) is bytes:return {'sqlite_blob_hex':value.hex()}
        raise TypeError('unexpected SQLite value')
    raw=json.dumps(values,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=blob).encode()
    return hashlib.sha256(raw).hexdigest()


async def create(client,key='financial-create'):
    response=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':key})
    assert response.status_code==200,response.text
    return response.json()['data']['research']['id']


async def preview(client,rid,body=None,key='financial-preview'):
    return await client.post('/api/research/'+rid+'/financial-import-preview',json=preview_body() if body is None else body,
                             headers={'Origin':BETA,'Idempotency-Key':key})


def test_actual_main_preview_exact_hash_unverified_dynamic_no_db_or_cache_write(prepared):
    main,admission,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                before=research_snapshot()
                response=await preview(client,rid);assert response.status_code==200,response.text
                body=response.json();data=body['data']
                assert body['contract_revision']=='financial-input-v2' and data['execution_authorized'] is False and data['persisted'] is False
                assert data['exact_received_csv_sha256']==hashlib.sha256(csv_text().encode()).hexdigest()
                from research.financial_policy import canonical
                binding={k:data[k] for k in ('parser_revision','research_id','input_revision','problem_digest','expected_research_version','exact_received_csv_sha256','key_based_plan_digest')}
                assert data['preview_digest']==hashlib.sha256(canonical({'contract':'financial-input-v2',**binding}).encode()).hexdigest()
                assert data['plan']['records'][2]['declared_basis']=='media_estimate'
                assert all(r['verification']=='unverified' and r['kind']=='owner_supplied' for r in data['plan']['records'])
                assert (await preview(client,rid)).json()==body
                rows=sample_rows();rows[1]['value']='101'
                changed=await preview(client,rid,preview_body(csv_text(rows)))
                assert changed.status_code==200 and changed.json()['data']['preview_digest']!=data['preview_digest']
                health=(await client.get('/api/health')).json()
                assert health['checks']['native_planner']=='FUNDING_CLOSED'
                assert research_snapshot()==before
                routes=[r.path for r in main.app.routes if 'financial' in r.path]
                assert routes==['/api/research/{research_id}/financial-import-preview']
                print('FINANCIAL_PREVIEW_MAIN_FACTS:'+json.dumps({'actual_main':True,'schema':14,'funding':'closed',
                    'research_before':before,'research_after':research_snapshot(),'preview_digest':data['preview_digest'],
                    'server_generated_ref':False,'source_truth_verified':False}))
        assert admission._STATE.get(id(main.app)) is None
    asyncio.run(run())


def test_actual_main_rejects_cross_actor_readonly_revoked_historical_and_changed_source(prepared,monkeypatch):
    main,admission,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                transport=httpx.ASGITransport(app=main.app)
                async with httpx.AsyncClient(transport=transport,base_url=BETA) as other:
                    await login(other,messages,email='other-financial@example.invalid')
                    assert (await preview(other,rid)).status_code==404
                from api import auth
                from research import ResearchStore,ResearchService,paid_control
                from research.financial_import import preview_import
                from research.financial_input_schemas import decode_financial_import_preview
                store=ResearchStore(auth._store());service=ResearchService(store)
                source_records=[];original=paid_control.issue_authenticated_action
                def changed_source(request,**kwargs):
                    rows=sample_rows();rows[1]['value']='102'
                    request._body=json.dumps(preview_body(csv_text(rows))).encode()
                    source=original(request,**kwargs);source_records.append(source);return source
                monkeypatch.setattr(paid_control,'issue_authenticated_action',changed_source)
                before=research_snapshot()
                assert (await preview(client,rid)).status_code==409
                monkeypatch.setattr(paid_control,'issue_authenticated_action',original)
                assert research_snapshot()==before
                source=source_records[0];assert not source.active
                request=decode_financial_import_preview(json.dumps(preview_body()).encode()).data
                for fake in (source,SimpleNamespace(**{name:getattr(source,name) for name in source.__slots__})):
                    with pytest.raises(PermissionError):preview_import(service,source.identity,rid,request,fake)
                # Narrow/revoke the original real grant, never mint a replacement or seed financial rows.
                with store.transaction(write=True) as conn:
                    scopes=conn.execute('SELECT scopes FROM research_grants WHERE research_id=?',(rid,)).fetchone()[0]
                    conn.execute("UPDATE research_grants SET scopes='[\"read\"]' WHERE research_id=?",(rid,))
                before=research_snapshot();assert (await preview(client,rid)).status_code==404;assert research_snapshot()==before
                with store.transaction(write=True) as conn:
                    conn.execute('UPDATE research_grants SET scopes=?,status=? WHERE research_id=?',(scopes,'revoked',rid))
                before=research_snapshot();assert (await preview(client,rid)).status_code==404;assert research_snapshot()==before
                with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='active' WHERE research_id=?",(rid,))
                revised=await client.post('/api/research/'+rid+'/revisions',json=envelope({'expected_revision':1,'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':'financial-revision'})
                assert revised.status_code==200,revised.text
                before=research_snapshot();assert (await preview(client,rid)).status_code==409;assert research_snapshot()==before
                fresh=preview_body();fresh['data'].update(input_revision=2,expected_research_version=2)
                assert (await preview(client,rid,fresh)).status_code==200
                assert research_snapshot()==before
    asyncio.run(run())


def test_actual_http_reader_and_action_reverify_large_wire_without_relaxing_old64k(prepared):
    main,_,_,messages=prepared
    async def run():
        async with main.lifespan(main.app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                await login(client,messages);rid=await create(client)
                from research.financial_input_schemas import WIRE_LIMIT
                raw=json.dumps(preview_body(),ensure_ascii=True,separators=(',',':')).encode()
                raw+=b' '*(WIRE_LIMIT-len(raw))
                headers={'Origin':BETA,'Idempotency-Key':'financial-wire','Content-Type':'application/json'}
                before=research_snapshot()
                response=await client.post('/api/research/'+rid+'/financial-import-preview',content=raw,headers=headers)
                assert response.status_code==200,response.text
                assert (await client.post('/api/research/'+rid+'/financial-import-preview',content=raw+b' ',headers=headers)).status_code==413
                assert (await client.post('/api/research/'+rid+'/financial-import-preview',json=preview_body('x'*131073),headers=headers)).status_code==413
                bad=preview_body();bad['data']['csv_text']='do-not-echo\x00secret'
                response=await preview(client,rid,bad);assert response.status_code==422 and 'do-not-echo' not in response.text
                assert (await client.post('/api/research/'+rid+'/financial-import-preview',json=preview_body(),headers={'Origin':BETA})).status_code==422
                assert (await client.post('/api/research/'+rid+'/financial-import-preview',json=preview_body(),headers={'Origin':'https://other.invalid','Idempotency-Key':'same-origin'})).status_code in (401,403)
                old=json.dumps(envelope({'problem':problem()})).encode()+b' '*65536
                assert (await client.post('/api/research',content=old,headers=headers)).status_code==413
                assert research_snapshot()==before
    asyncio.run(run())


def test_bounded_stream_stops_before_loading_remaining_chunks():
    from api.research import _parse_financial_import_preview
    from research.financial_input_schemas import WIRE_LIMIT,FinancialImportError
    reads=[]
    async def receive():
        reads.append(True)
        if len(reads)>1:raise AssertionError('oversized stream must not continue')
        return {'type':'http.request','body':b' '*(WIRE_LIMIT+1),'more_body':True}
    request=Request({'type':'http','method':'POST','path':'/reader-only','headers':[(b'content-type',b'application/json')]},receive)
    with pytest.raises(FinancialImportError):asyncio.run(_parse_financial_import_preview(request))
    assert len(reads)==1 and not hasattr(request,'_body')


def test_actual_verified_tls_main_preview_and_shutdown(tmp_path,monkeypatch):
    from web.backend.tests.acceptance.formal_main_browser_service import FormalMainBrowserService,_FOREIGN_INPUTS
    # The clean launcher seeds owned nonformal paths for other tests. This
    # controller requires their absence before constructing its own runtime.
    for name in _FOREIGN_INPUTS:monkeypatch.delenv(name,raising=False)
    owned=tmp_path/'owned-tls-main'
    service=FormalMainBrowserService(owned)
    guard=sys.modules.get('main_smtp_task_guard');port=None
    try:
        with service:
            port=service._smtp.server.server_address[1]
            if guard is not None:guard.OWNED_MAIN_SMTP_PORTS.add(port)
            client=service.client
            assert client.request('POST','/api/auth/request-link',{'email':service.seed.email})[0]==200
            token=service.take_latest_magic_token()
            try:assert client.request('POST','/api/auth/verify',{'token':token})[0]==200
            finally:token=None
            cookies=[cookie for cookie in client.cookies if cookie.name=='phase_session']
            assert len(cookies)==1 and cookies[0].secure and 'HttpOnly' in cookies[0]._rest
            status,made=client.request('POST','/api/research',envelope({'problem':problem()}),key='financial-tls-create')
            assert status==200;rid=made['data']['research']['id']
            before=research_snapshot()
            status,response=client.request('POST','/api/research/'+rid+'/financial-import-preview',preview_body(),key='financial-tls-preview')
            assert status==200 and response['data']['exact_received_csv_sha256']==hashlib.sha256(csv_text().encode()).hexdigest()
            assert research_snapshot()==before
            print('FINANCIAL_TLS_FACTS:'+json.dumps({'actual_main':True,'verified_local_tls':True,'secure_cookie':True,'research_unchanged':True}))
    finally:
        if guard is not None and port is not None:guard.OWNED_MAIN_SMTP_PORTS.discard(port)
    assert not owned.exists() and not service.server_thread.is_alive()


def test_historical_13_inverse_and_source10_plan12_consumers_stay_exact(tmp_path):
    from web.backend.tests.method_v13_reference import reconstruct as method13
    from web.backend.tests.source_v10_reference import reconstruct as source10
    from web.backend.tests.plan_v12_reference import reconstruct as plan12
    root=Path(__file__).resolve().parents[3]
    manifest=json.loads((root/'web/backend/tests/reference/method_v13/manifest.json').read_text())
    counts={}
    for mode in manifest['cases']:
        package,_=method13(root,tmp_path/('method13-'+mode),mode)
        assert not (package/'.git').exists()
        api=(package/'web/backend/api/research.py').read_text()
        assert 'financial_input_schemas' not in api and 'financial-import-preview' not in api
        counts['method13-'+mode]=len(manifest['cases'][mode]['files'])
    for name,reconstruct in (('source10',source10),('plan12',plan12)):
        package,_,manifest_path=reconstruct(root,tmp_path/name)
        assert not (package/'.git').exists()
        counts[name]=len(json.loads(manifest_path.read_text())['files'])
    print('FINANCIAL_HISTORICAL_BYTES:'+json.dumps(counts,sort_keys=True))
