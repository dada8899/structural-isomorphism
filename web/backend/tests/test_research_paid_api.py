"""Frozen paid HTTP contract; real auth/DB, server-only OFFLINE composition."""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib
import json
import logging
import sys
import hashlib
from functools import partial
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from .test_research_persistence import stack,app,post,login,problem,trusted_sso,envelope
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_lifecycle import lifecycle
from api import auth
from research import ResearchService
from research import paid_approval


@pytest.fixture
def paid_api(approved_inputs):
    original,path,store,rid,pid,excerpt,resolver=approved_inputs
    application=app()
    application.state.research_paid_resolver=resolver
    with TestClient(application) as client:
        client.cookies.update(original.cookies)
        yield client,path,store,rid,excerpt,resolver


def preview_data(client,rid,excerpt):
    view=client.get('/api/research/'+rid).json()['data']
    return dict(input_revision=view['current_problem']['revision'],expected_research_version=view['research_version'],excerpt_ids=[excerpt],purpose='method_hypothesis')


def confirm_data(preview):
    return dict(preview_ref=preview['preview_ref'],expected_preview_version=preview['preview_version'],input_revision=preview['bindings']['input_revision'],
        expected_research_version=preview['bindings']['research_version'],preview_digest=preview['preview_digest'],confirm_external_input=True,confirm_maximum_reserve=True)


def counts(store):
    with store.transaction() as conn:
        return {name:conn.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in
            ('research_paid_approvals','research_tasks','research_grants','research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions')}


def make_preview(data,key='api-preview'):
    client,_,_,rid,excerpt,_=data
    response=post(client,'/api/research/'+rid+'/paid-previews',preview_data(client,rid,excerpt),key)
    assert response.status_code==200,response.text
    return response.json()['data']


PREVIEW_FIELDS={'preview_ref','preview_version','status','expires_at','bindings','purpose','provider','model','declared_model_version','execution_mode','policy_revision','quote','maximum_reserve','actual','cost_label','max_calls','manifest','manifest_digest','outbound_request_digest','preview_digest','may_send_to_provider','model_analysis_ran'}
APPROVAL_FIELDS={'approval_ref','preview_ref','preview_version','preview_digest','research_version','task_id','task_version','execution','status','execution_mode','model_analysis_ran'}


def test_default_source_and_fake_env_do_not_enable_paid_api(paid_api,monkeypatch):
    client,_,store,rid,excerpt,_=paid_api
    client.app.state.research_paid_resolver=None
    monkeypatch.setenv('STRUCTURAL_PAID_ENABLED','true')
    before=counts(store)
    request=preview_data(client,rid,excerpt)
    response=post(client,'/api/research/'+rid+'/paid-previews',request)
    assert response.status_code==503 and response.json()['error']['code']=='BUDGET_UNVERIFIED'
    assert counts(store)==before


def test_exact_public_preview_then_only_queued_confirm_no_dispatch(paid_api):
    client,_,store,rid,excerpt,_=paid_api;before=counts(store)
    draft=make_preview(paid_api)
    assert set(draft)==PREVIEW_FIELDS and draft['execution_mode']=='offline_probe'
    assert draft['maximum_reserve']=={'currency':'CNY','scale':6,'amount_units':3}
    assert draft['actual'] is None and draft['may_send_to_provider'] is draft['model_analysis_ran'] is False
    assert set(draft['bindings'])=={'research_id','input_revision','input_digest','research_version'}
    assert set(draft['quote'])=={'revision','digest','valid_until'}
    assert set(draft['manifest'])=={'problem_summary','sources','handles'}
    assert counts(store)=={**before,'research_paid_approvals':before['research_paid_approvals']+1}
    assert make_preview(paid_api)==draft
    assert counts(store)['research_paid_approvals']==1
    response=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'api-confirm')
    assert response.status_code==200,response.text
    result=response.json()['data'];assert set(result)==APPROVAL_FIELDS
    assert result['execution']=='QUEUED' and result['status']=='queued' and result['model_analysis_ran'] is False
    assert response.headers['cache-control']=='no-store' and response.headers['referrer-policy']=='no-referrer'
    current=counts(store)
    assert current['research_tasks']==before['research_tasks']+1 and current['research_grants']==before['research_grants']+1
    for key in ('research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions'):assert current[key]==0
    assert post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'api-confirm').json()==response.json()


@pytest.mark.parametrize('field,value',[
    ('confirm_external_input',False),('confirm_external_input',1),('confirm_external_input','true'),
    ('confirm_maximum_reserve',False),('confirm_maximum_reserve',1),('confirm_maximum_reserve',None),
    ('owner',str(uuid4())),('funding',{'verified':True}),('price',1),('maximum_reserve',{'amount_units':0}),
    ('authority',True),('expected_preview_version',True),('preview_ref','invalid'),('preview_digest','bad'),
])
def test_confirmation_strict_values_and_no_self_asserted_authority(paid_api,field,value):
    client,_,store,rid,_,_=paid_api;draft=make_preview(paid_api);data=confirm_data(draft);data[field]=value;before=counts(store)
    response=post(client,'/api/research/'+rid+'/paid-approvals',data)
    assert response.status_code==422 and counts(store)==before


@pytest.mark.parametrize('field,value',[
    ('owner',str(uuid4())),('funding',True),('quote',{}),('summary','override'),('provider','other'),('policy','other'),
    ('input_revision',True),('expected_research_version','3'),('purpose','trade'),('excerpt_ids',[]),('excerpt_ids',['bad']),
])
def test_preview_strict_shape_does_not_write(paid_api,field,value):
    client,_,store,rid,excerpt,_=paid_api;data=preview_data(client,rid,excerpt);data[field]=value;before=counts(store)
    response=post(client,'/api/research/'+rid+'/paid-previews',data)
    assert response.status_code==422 and counts(store)==before


def test_origin_key_json_duplicates_limits_and_query_reject(paid_api):
    client,_,store,rid,excerpt,_=paid_api;url='/api/research/'+rid+'/paid-previews';body=envelope(preview_data(client,rid,excerpt));before=counts(store)
    assert client.post(url,json=body,headers={'Origin':'https://other.test','Idempotency-Key':'origin'}).status_code==403
    assert client.post(url,json=body,headers={'Origin':'http://testserver'}).status_code==422
    assert client.post(url,content=b' '*65537,headers={'Origin':'http://testserver','Idempotency-Key':'size','Content-Type':'application/json'}).status_code==413
    raw=json.dumps(body).replace('"purpose": "method_hypothesis"','"purpose":"other","purpose":"method_hypothesis"')
    assert client.post(url,content=raw,headers={'Origin':'http://testserver','Idempotency-Key':'dupe','Content-Type':'application/json'}).status_code==422
    assert post(client,url+'?funding=true',preview_data(client,rid,excerpt)).status_code==422
    assert counts(store)==before


def test_cookie_only_conflict_and_bearer_cannot_rescue_invalid_cookie(paid_api):
    client,_,store,rid,excerpt,_=paid_api;data=preview_data(client,rid,excerpt);url='/api/research/'+rid+'/paid-previews';before=counts(store)
    cookie=client.cookies.get('phase_session')
    client.cookies.clear()
    response=client.post(url,json=envelope(data),headers={'Origin':'http://testserver','Idempotency-Key':'bearer','Authorization':'Bearer '+cookie})
    assert response.status_code==401
    client.cookies.set('phase_session','invalid')
    assert client.post(url,json=envelope(data),headers={'Origin':'http://testserver','Idempotency-Key':'rescue','Authorization':'Bearer '+cookie}).status_code==401
    client.cookies.clear();client.cookies.set('phase_session',cookie)
    with TestClient(app()) as other:login(other,'api-other@example.test')
    client.cookies.set('structural_beta_session',trusted_sso('api-other@example.test'))
    assert post(client,url,data).status_code==409
    assert counts(store)==before


def test_concurrent_same_confirmation_and_commit_ack_loss_do_not_duplicate(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api;draft=make_preview(paid_api);data=confirm_data(draft);url='/api/research/'+rid+'/paid-approvals'
    original=ResearchService._paid_envelope;lost=[]
    def ack(value):
        if 'approval_ref' in value and not lost:
            lost.append(True);raise OSError('owned post-commit ack fault')
        return original(value)
    monkeypatch.setattr(ResearchService,'_paid_envelope',staticmethod(ack))
    assert post(client,url,data,'ack-one').status_code==503
    replay=post(client,url,data,'ack-one');assert replay.status_code==200,replay.text
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:post(client,url,data,'ack-one'),range(2)))
    assert all(r.status_code==200 and r.json()==replay.json() for r in responses)
    assert counts(store)['research_tasks']==2 and counts(store)['research_reservations']==0
    assert post(client,url,data,'different-key').status_code==409


def test_expired_draft_replay_denied_but_committed_confirmation_is_readonly(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api;draft=make_preview(paid_api);body=confirm_data(draft);url='/api/research/'+rid+'/paid-approvals'
    result=post(client,url,body,'once');assert result.status_code==200,result.text
    # Negative-only controlled Core clock; no positive quote is admitted with
    # invented time and no global auth/JWT clock is changed.
    now=paid_approval.time.time();monkeypatch.setattr(paid_approval,'time',SimpleNamespace(time=lambda:now+61))
    replay=post(client,url,body,'once');assert replay.status_code==200 and replay.json()==result.json()
    before=counts(store)
    response=post(client,'/api/research/'+rid+'/paid-previews',preview_data(client,rid,paid_api[4]),'new-expired')
    assert response.status_code in (409,503) and counts(store)==before


def test_cross_owner_path_binding_and_same_email_generation_are_not_inherited(paid_api):
    client,_,store,rid,excerpt,resolver=paid_api;draft=make_preview(paid_api);body=confirm_data(draft);before=counts(store)
    with TestClient(app()) as other:
        other.app.state.research_paid_resolver=resolver;login(other,'other-paid-api@example.test')
        assert post(other,'/api/research/'+rid+'/paid-approvals',body).status_code==404
    other=post(client,'/api/research',{'problem':problem('different private problem')}).json()['data']['research']['id']
    assert post(client,'/api/research/'+other+'/paid-approvals',body).status_code==404
    old=client.cookies.get('phase_session');auth._store().delete_account_data('research-a@example.test');login(client)
    assert post(client,'/api/research/'+rid+'/paid-approvals',body).status_code==404
    client.cookies.clear();client.cookies.set('phase_session',old)
    assert post(client,'/api/research/'+rid+'/paid-approvals',body).status_code==401
    assert counts(store)['research_reservations']==0


def test_valid_duplicate_json_true_and_client_binding_mismatch_reject(paid_api):
    client,_,store,rid,excerpt,_=paid_api;draft=make_preview(paid_api);body=confirm_data(draft);url='/api/research/'+rid+'/paid-approvals';before=counts(store)
    raw=json.dumps(envelope(body)).replace('"confirm_external_input": true','"confirm_external_input":false,"confirm_external_input":true')
    response=client.post(url,content=raw,headers={'Origin':'http://testserver','Idempotency-Key':'duplicate-confirm','Content-Type':'application/json'})
    assert response.status_code==422
    for changed in ({'input_revision':2},{'expected_research_version':999},{'expected_preview_version':2}):
        response=post(client,url,{**body,**changed})
        assert response.status_code==409,response.text
    assert counts(store)==before


def test_preview_idempotent_concurrency_and_source_revocation(paid_api):
    client,_,store,rid,excerpt,_=paid_api;data=preview_data(client,rid,excerpt);url='/api/research/'+rid+'/paid-previews'
    with ThreadPoolExecutor(max_workers=2) as pool:responses=list(pool.map(lambda _:post(client,url,data,'one-preview'),range(2)))
    assert all(response.status_code==200 for response in responses)
    assert responses[0].json()==responses[1].json() and counts(store)['research_paid_approvals']==1
    draft=responses[0].json()['data']
    with store.transaction(write=True) as conn:conn.execute("UPDATE research_grants SET status='revoked' WHERE research_id=?",(rid,))
    before=counts(store)
    denied=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'revoked')
    assert denied.status_code==404 and counts(store)==before


def test_expired_unconsumed_preview_key_returns_conflict(paid_api,monkeypatch):
    client,_,store,rid,excerpt,_=paid_api;data=preview_data(client,rid,excerpt);draft=make_preview(paid_api)
    before=counts(store);now=paid_approval.time.time()
    monkeypatch.setattr(paid_approval,'time',SimpleNamespace(time=lambda:now+61))
    response=post(client,'/api/research/'+rid+'/paid-previews',data,'api-preview')
    assert response.status_code==409 and counts(store)==before


def test_deleted_owner_and_old_ack_cannot_revive_confirmation(paid_api,lifecycle):
    client,_,store,rid,_,_=paid_api;draft=make_preview(paid_api);body=confirm_data(draft);url='/api/research/'+rid+'/paid-approvals'
    assert post(client,url,body,'before-delete').status_code==200
    deleting,_,_=lifecycle
    response=deleting.post('/api/me/delete',json={'confirmation':'DELETE'},headers={'Origin':'http://testserver'})
    assert response.status_code==200,response.text
    denied=post(client,url,body,'before-delete')
    assert denied.status_code==401
    with store.transaction() as conn:
        assert conn.execute('SELECT payload_json FROM research_paid_approvals').fetchone()[0] is None
        assert conn.execute('SELECT count(*) FROM research_cost_observations').fetchone()[0]==0


def test_replay_state_comes_from_original_task_after_newer_queue(paid_api):
    client,_,_,rid,_,_=paid_api;first=make_preview(paid_api)
    response=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(first),'old-confirm');assert response.status_code==200
    old=response.json()['data']
    assert post(client,'/api/research/'+rid+'/cancel',{'task_id':old['task_id'],'expected_task_version':old['task_version']}).status_code==200
    second=make_preview(paid_api,'next-preview')
    queued=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(second),'next-confirm')
    assert queued.status_code==200,queued.text
    restored=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(first),'old-confirm').json()['data']
    assert restored['task_id']==old['task_id'] and restored['task_id']!=queued.json()['data']['task_id']
    assert restored['execution']=='CANCELLED' and restored['status']=='cancelled'


def _actual_current_main_paid_closed_probe(root):
    """Current15 normal Main has no legacy offline funding composition."""
    import asyncio
    from contextlib import contextmanager
    from pathlib import Path
    import httpx
    from .test_formal_main_admission import smtp,prepared,BETA,login as formal_login
    from .test_research_index import business_rows
    from research import ResearchStore
    with pytest.MonkeyPatch.context() as patch:
        with contextmanager(smtp.__wrapped__)() as mail:
            with contextmanager(prepared.__wrapped__)(root,patch,mail) as configured:
                main,admission,paths,messages=configured
                async def run():
                    async with main.lifespan(main.app):
                        assert admission.require(main.app,'research_basic') is None
                        assert 'search' not in main.app_state
                        assert getattr(main.app.state,'research_paid_resolver',None) is None
                        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url=BETA) as client:
                            await formal_login(client,messages,'research-a@example.test')
                            made=await client.post('/api/research',json=envelope({'problem':problem()}),headers={'Origin':BETA,'Idempotency-Key':str(uuid4())})
                            assert made.status_code==200
                            rid=made.json()['data']['research']['id']
                            detail=await client.get('/api/research/'+rid)
                            assert detail.status_code==200
                            store=ResearchStore(auth._store())
                            assert store._formal_mode() is True
                            with store.transaction() as conn:
                                assert conn.execute('SELECT version FROM research_schema').fetchone()[0]==15
                                assert store.auth_store.check_offline_auth_metadata(conn)=='auth-provision-v1'
                            before=business_rows(paths.STATE_ROOT/'auth.sqlite3')
                            body=dict(input_revision=detail.json()['data']['current_problem']['revision'],expected_research_version=detail.json()['data']['research_version'],excerpt_ids=[str(uuid4())],purpose='method_hypothesis')
                            refused=await client.post('/api/research/'+rid+'/paid-previews',json=envelope(body),headers={'Origin':BETA,'Idempotency-Key':str(uuid4())})
                            assert refused.status_code==503
                            assert refused.json()['error']['code']=='BUDGET_UNVERIFIED'
                            assert all(counts(store)[name]==0 for name in ('research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions','research_paid_approvals','research_tasks'))
                            assert business_rows(paths.STATE_ROOT/'auth.sqlite3')==before
                            assert (await client.get('/api/research/'+rid)).json()==detail.json()
                            assert refused.headers['cache-control']=='no-store'
                            assert refused.headers['referrer-policy']=='no-referrer'
                            assert problem()['original_input'] not in refused.text
                asyncio.run(run())
                assert id(main.app) not in admission._STATE
    print('owned-current-main-paid-closed-ok')


def test_actual_current_main_default_offline_paid_closed_without_sending(tmp_path):
    from pathlib import Path
    from .research_process_fixture import _run_owned_probe
    root=tmp_path/'current-main-paid-closed';root.mkdir()
    program="""
import sys
from pathlib import Path
source=Path(SOURCE_ROOT)
sys.path[:0]=[str(source/'web/backend'),str(source)]
from web.backend.tests.test_research_paid_api import _actual_current_main_paid_closed_probe
_actual_current_main_paid_closed_probe(Path(DATA_ROOT))
""".replace('DATA_ROOT',repr(str(root))).replace('SOURCE_ROOT',repr(str(Path(__file__).resolve().parents[3])))
    result=_run_owned_probe(program,root)
    assert result.returncode==0,result.stdout+result.stderr
    assert 'owned-current-main-paid-closed-ok' in result.stdout


def test_confirmation_with_default_source_cannot_consume_existing_draft(paid_api):
    client,_,store,rid,_,_=paid_api;draft=make_preview(paid_api);before=counts(store)
    client.app.state.research_paid_resolver=None
    response=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'disabled')
    assert response.status_code==503 and response.json()['error']['code']=='BUDGET_UNVERIFIED'
    assert counts(store)==before


def test_read_only_owner_can_preview_but_cannot_confirm(paid_api):
    client,_,store,rid,_,_=paid_api
    with store.transaction(write=True) as conn:
        conn.execute("UPDATE research_grants SET scopes='[\"read\"]' WHERE research_id=? AND EXISTS(SELECT 1 FROM json_each(scopes) WHERE value='write')",(rid,))
    draft=make_preview(paid_api);before=counts(store)
    response=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'read-only')
    assert response.status_code==404 and counts(store)==before


@pytest.mark.parametrize('fixture_enabled',[False,True])
def test_old_worker_skips_paid_queue_and_explicit_paid_is_rejected(paid_api,monkeypatch,fixture_enabled):
    from research import ResearchRunner
    from research.errors import ResearchError
    from research.source_policy import PinnedPublicTransport
    from web.backend.tests.source_http_fixture import source_server,get_local
    from .test_research_d1_integration import start as start_source
    client,_,store,rid,_,_=paid_api
    monkeypatch.setenv('STRUCTURAL_C0_ENABLED','true' if fixture_enabled else 'false')
    draft=make_preview(paid_api)
    approved=post(client,'/api/research/'+rid+'/paid-approvals',confirm_data(draft),'queue-only')
    assert approved.status_code==200,approved.text
    paid_task=approved.json()['data']['task_id']
    data=problem('separate legitimate source task');data['confirmed']=True
    source_rid=post(client,'/api/research',{'problem':data}).json()['data']['research']['id']
    source_task=start_source(client,source_rid)
    with source_server() as (port,calls):
        runner=ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port)))
        assert runner.run_once()=='COMPLETED'
        assert runner.run_once()=='idle'
        assert runner.run_once(source_task)=='COMPLETED' and calls==['/discovery','/article']
        before=counts(store)
        with pytest.raises(ResearchError) as error:runner.run_once(paid_task)
        assert error.value.code=='FEATURE_UNAVAILABLE' and counts(store)==before
    with store.transaction() as conn:
        assert conn.execute('SELECT execution FROM research_tasks WHERE id=?',(paid_task,)).fetchone()[0]=='QUEUED'
        assert conn.execute('SELECT count(*) FROM research_reservations').fetchone()[0]==0


@pytest.mark.parametrize('number,expected',[(2,200),(3,413)])
def test_unicode_complete_final_request_limit_is_413_with_zero_new_objects(paid_api,number,expected):
    from research import ResearchRunner
    from research.source_policy import PinnedPublicTransport
    from web.backend.tests.source_http_fixture import source_server,get_local,ARTICLE,TITLE
    from .test_research_d1_integration import start as start_source
    client,_,store,_,_,_=paid_api
    data=problem('saved bounded original input');data.update(confirmed=True,summary='😀'*1000)
    rid=post(client,'/api/research',{'problem':data}).json()['data']['research']['id']
    tid=start_source(client,rid)
    article=ARTICLE.replace(('Citation: '+TITLE).encode(),('Citation: Example A, Example B (2026) '+TITLE).encode())
    article=article.replace(b'Waiting time depends on arrivals and service variability.',('😀'*1000).encode())
    with source_server(article=article) as (port,calls):
        assert ResearchRunner(store,source_transport=PinnedPublicTransport(_worker=partial(get_local,port))).run_once(tid)=='COMPLETED'
        assert calls==['/discovery','/article']
    with store.transaction(write=True) as conn:
        row=dict(conn.execute("SELECT * FROM research_evidence_objects WHERE task_id=? AND kind='excerpts'",(tid,)).fetchone());refs=[row['id']]
        for _ in range(number-1):
            new={**row,'id':str(uuid4())};payload=json.loads(new['payload']);payload['id']=new['id']
            new['payload']=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False);new['payload_digest']=hashlib.sha256(new['payload'].encode()).hexdigest()
            conn.execute('INSERT INTO research_evidence_objects ('+','.join(new)+') VALUES('+','.join('?' for _ in new)+')',tuple(new.values()));refs.append(new['id'])
    request=preview_data(client,rid,refs[0]);request['excerpt_ids']=refs;before=counts(store)
    response=post(client,'/api/research/'+rid+'/paid-previews',request,'unicode-'+str(number))
    assert response.status_code==expected,response.text
    if expected==413:
        assert response.json()['error']['code']=='PAYLOAD_LIMIT' and counts(store)==before
        assert '😀' not in response.text
    else:assert counts(store)=={**before,'research_paid_approvals':before['research_paid_approvals']+1}


def test_other_codec_failures_are_not_relabelled_payload_limit(paid_api,monkeypatch):
    from research import preview_codec
    from research.provider_schemas import ProviderFailure
    client,_,store,rid,excerpt,_=paid_api;before=counts(store)
    def fail(*args,**kwargs):raise ProviderFailure('invalid_input')
    monkeypatch.setattr(preview_codec,'preview_request',fail)
    with TestClient(client.app,raise_server_exceptions=False) as actual:
        actual.cookies.update(client.cookies)
        response=post(actual,'/api/research/'+rid+'/paid-previews',preview_data(client,rid,excerpt),'unrelated')
    assert response.status_code==500 and counts(store)==before


def test_paid_source_callbacks_survive_shadowed_tests_namespace_in_real_spawn(tmp_path):
    from pathlib import Path
    from web.backend.tests.research_process_fixture import _run_owned_probe

    data_root=tmp_path/'paid-spawn-shadow';data_root.mkdir()
    program=r'''
import importlib,pathlib,pickle,subprocess,sys
from contextlib import contextmanager
from functools import partial
from types import SimpleNamespace
from uuid import uuid4
backend=pathlib.Path.cwd();root=backend.parents[1]
sys.path[:]=[str(backend)]+[p for p in sys.path if p not in ('',str(root),str(backend))]
api=importlib.import_module('tests.test_research_paid_api')
approval=importlib.import_module('tests.test_research_paid_approval')
legacy=importlib.import_module('tests.source_http_fixture')
assert pathlib.Path(sys.modules['tests'].__file__).resolve()==backend/'tests/__init__.py'
sys.path.remove(str(root))
importlib.import_module('tests.test_universality_endpoints')
assert sys.path[0]==str(root)
# A fresh interpreter resolves tests from the root, so an old pickled callback
# cannot even be reconstructed. Do not run that callback or touch the network.
serialized=pickle.dumps(partial(legacy.get_local,1))
child=subprocess.run([sys.executable,'-c','import pickle;pickle.loads(bytes.fromhex('+repr(serialized.hex())+'))'],
    cwd=root,capture_output=True,text=True,timeout=15)
assert child.returncode!=0 and 'tests.source_http_fixture' in child.stderr and 'ModuleNotFoundError' in child.stderr
import pytest
from research.authorization import AuthorizationGate
from research.source_policy import PinnedPublicTransport,SourceFailure,article_target
from web.backend.tests.source_http_fixture import source_server,DOI
# Reproduce the actual old pickled callback failure in a fresh child, while
# the parent's cached tests package still points to backend/tests.
from web.backend.tests.test_research_source_spawn import development_auth
with pytest.MonkeyPatch.context() as backing_setup:
    backing=development_auth.__wrapped__(pathlib.Path(DATA_ROOT),backing_setup)
    with source_server() as (port,calls):
        gate=AuthorizationGate(backing)
        with gate.owner_gate_id(str(uuid4())) as lease:
            with pytest.raises(SourceFailure):
                PinnedPublicTransport(_worker=partial(legacy.get_local,port)).get(
                    article_target(DOI),still_authorized=lambda:True,owner_lease=lease)
        assert calls==[]
# Exercise all three actual callback import sites through unchanged fixtures
# and original assertions, not a replacement worker, alias or status stub.
for index,(kind,number) in enumerate((('queue',None),('unicode',2),('unicode',3))):
    monkeypatch=pytest.MonkeyPatch();directory=pathlib.Path(DATA_ROOT)/str(index);directory.mkdir()
    try:
        with contextmanager(api.stack.__wrapped__)(directory,monkeypatch) as stack:
            with contextmanager(api.source_stack.__wrapped__)(stack,monkeypatch) as saved_source:
                with contextmanager(approval.approved_inputs.__wrapped__)(saved_source,SimpleNamespace(param=True)) as approved:
                    with contextmanager(api.paid_api.__wrapped__)(approved) as paid:
                        if kind=='queue':
                            api.test_old_worker_skips_paid_queue_and_explicit_paid_is_rejected(paid,monkeypatch,False)
                        else:
                            api.test_unicode_complete_final_request_limit_is_413_with_zero_new_objects(paid,number,200 if number==2 else 413)
                        actual=api.counts(paid[2])
                        for table in ('research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions'):
                            assert actual[table]==0
    finally:monkeypatch.undo()
print('owned-paid-canonical-spawn-ok')
'''.replace('DATA_ROOT',repr(str(data_root)))
    result=_run_owned_probe(program,Path(__file__).resolve().parents[1])
    assert result.returncode==0,result.stdout+result.stderr
    assert 'owned-paid-canonical-spawn-ok' in result.stdout
