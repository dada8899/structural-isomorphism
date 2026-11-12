"""Request snapshot/copy controls, never formal Main READY/send evidence.

Gate substitutes below test port orchestration only; no Main/supervisor registry
is installed. Real legacy14 HTTP controls retain actual Auth, typed storage and
idempotency. Actual formal READY/retirement remain 07's composition tests.
"""
from copy import deepcopy
import hashlib
import json
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from api import auth, research as api
from research import ResearchStore, source_integration, source_supervisor, runtime_profile
from research.errors import ResearchError
from .test_research_source_terminal14 import current14
from .test_research_persistence import post, problem
from .test_research_formula_lifecycle import formula_problem
from .test_private_runtime_bootstrap import roots
from .test_private_registration import stack

RID='12345678-1234-4234-8234-123456789abc'
OTHER='22345678-1234-4234-8234-123456789abc'


def root_view():
    return {'schema_version':'structure-research-v1','contract_revision':'b1-candidate-01','data':{
        'research':{'id':RID,'created_at':'2026-10-20T00:00:00.000000Z'},
        'research_version':2,'current_problem':{'revision':1},'revisions':[{'revision':1}],
        'capabilities':{'source_evidence':False,'execution':True,'formula_checks':{'host_supported':False}},
        'method_result':{'protocol':'synthetic-copy-shape-only','result_ref':OTHER,
                         'recorded_at':'2026-10-19T00:00:00.000000Z','body':{'ref':'unchanged'}}}}


@pytest.fixture
def ports(monkeypatch):
    app=FastAPI();service=SimpleNamespace(store=SimpleNamespace(_formal_mode=lambda:True));calls=[]
    monkeypatch.setattr(runtime_profile,'formal_request_required',lambda app:False)
    def gate(app,capability):calls.append(('gate',app,capability))
    def supervisor(app,request_service):calls.append(('supervisor',app,request_service))
    monkeypatch.setattr(runtime_profile,'require_formal_application',gate)
    monkeypatch.setattr(source_supervisor,'require_available',supervisor)
    return app,service,calls


def test_port_order_uses_this_request_service_without_installing_authority(ports):
    app,service,calls=ports
    assert source_integration.request_execution_available(app,service) is True
    assert calls==[('gate',app,'research_basic'),('gate',app,'source_execute'),('supervisor',app,service)]


@pytest.mark.parametrize('where',['basic','source','supervisor'])
def test_only_source_unavailable_becomes_false_and_basic_still_raises(ports,monkeypatch,where):
    app,service,calls=ports;error=ResearchError('FEATURE_UNAVAILABLE',503,'synthetic unavailable')
    def gate(app,capability):
        calls.append(capability)
        if (where=='basic' and capability=='research_basic') or (where=='source' and capability=='source_execute'):raise error
    def supervisor(app,service):calls.append('supervisor');raise error
    monkeypatch.setattr(runtime_profile,'require_formal_application',gate)
    monkeypatch.setattr(source_supervisor,'require_available',supervisor)
    if where=='basic':
        with pytest.raises(ResearchError) as raised:source_integration.request_execution_available(app,service)
        assert raised.value is error and calls==['research_basic']
    else:
        assert source_integration.request_execution_available(app,service) is False
        assert calls==(['research_basic','source_execute']+(['supervisor'] if where=='supervisor' else []))


@pytest.mark.parametrize('error',[OSError('do-not-echo'),sqlite3.OperationalError('do-not-echo'),
    ResearchError('AUTH_REQUIRED',401,'synthetic'),ResearchError('FEATURE_UNAVAILABLE',409,'synthetic')])
@pytest.mark.parametrize('where',['source','supervisor'])
def test_unexpected_port_failures_do_not_become_false(ports,monkeypatch,error,where):
    app,service,_=ports
    if where=='source':
        def fail(app,capability):
            if capability=='source_execute':raise error
        monkeypatch.setattr(runtime_profile,'require_formal_application',fail)
    else:
        def fail(app,service):raise error
        monkeypatch.setattr(source_supervisor,'require_available',fail)
    with pytest.raises(type(error)) as raised:source_integration.request_execution_available(app,service)
    assert raised.value is error


@pytest.mark.parametrize('where',['basic','source','supervisor'])
def test_non_none_gate_result_is_not_authority(ports,monkeypatch,where):
    app,service,_=ports
    if where=='supervisor':monkeypatch.setattr(source_supervisor,'require_available',lambda *args:True)
    else:
        monkeypatch.setattr(runtime_profile,'require_formal_application',
                            lambda app,capability:True if capability==('research_basic' if where=='basic' else 'source_execute') else None)
    with pytest.raises(RuntimeError):source_integration.request_execution_available(app,service)


def test_dev_keeps_original_enabled_semantics_and_cannot_promote_to_formal(monkeypatch):
    app=FastAPI();service=SimpleNamespace(store=SimpleNamespace(_formal_mode=lambda:False))
    for name,value in {'STRUCTURAL_ENV':'test','STRUCTURAL_RESEARCH_ENABLED':'true','STRUCTURAL_D1_SOURCES_ENABLED':'true'}.items():monkeypatch.setenv(name,value)
    assert source_integration.request_execution_available(app,service) is True
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','false')
    assert source_integration.request_execution_available(app,service) is False
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','true');monkeypatch.setenv('STRUCTURAL_ENV','prod')
    with pytest.raises(ResearchError):source_integration.request_execution_available(app,service)


def test_real_captured_private_store_cannot_downgrade_basic_admission(stack,monkeypatch):
    store=ResearchStore(auth._store());service=SimpleNamespace(store=store)
    assert store._formal_mode() is True
    monkeypatch.setenv('STRUCTURAL_ENV','test')
    with pytest.raises(ResearchError) as denied:source_integration.request_execution_available(FastAPI(),service)
    assert denied.value.code=='FEATURE_UNAVAILABLE' and denied.value.status==503


@pytest.mark.parametrize('operation',api._ROOT_VIEW_OPERATIONS)
def test_root_snapshot_copies_only_outer_data_caps_and_preserves_typed_fields(monkeypatch,operation):
    original=root_view();before=deepcopy(original);service=object();app=FastAPI();calls=[]
    def available(given_app,given_service):calls.append((given_app,given_service));return True
    monkeypatch.setattr(source_integration,'request_execution_available',available)
    value=api._with_request_source_capability(original,app=app,service=service,
        research_id=None if operation=='create' else RID,operation=operation)
    assert original==before and calls==[(app,service)]
    assert value is not original and value['data'] is not original['data']
    assert value['data']['capabilities'] is not original['data']['capabilities']
    assert value['data']['method_result'] is original['data']['method_result']
    expected=deepcopy(before);expected['data']['capabilities']['source_evidence']=True
    assert value==expected


@pytest.mark.parametrize('operation',['index','records','source-preview','source-approve','formula-check','formula-read','draft-save','draft-history','plan-confirm','paid-confirm'])
def test_non_root_operations_are_not_projected(monkeypatch,operation):
    value=object()
    def forbidden(*args):raise AssertionError('non-Root cannot query a Source snapshot')
    monkeypatch.setattr(source_integration,'request_execution_available',forbidden)
    assert api._with_request_source_capability(value,app=None,service=None,research_id=None,operation=operation) is value


@pytest.mark.parametrize('fault',['extra-envelope','schema','contract','data','research','missing-id','bad-id',
    'version1-id','uppercase-id','caps','missing-source','integer-source','mismatched-id'])
def test_strict_root_shape_and_identity_reject_before_runtime_lookup(monkeypatch,fault):
    value=root_view();rid=RID
    if fault=='extra-envelope':value['other']=True
    if fault=='schema':value['schema_version']='other'
    if fault=='contract':value['contract_revision']='other'
    if fault=='data':value['data']=[]
    if fault=='research':value['data']['research']=[]
    if fault=='missing-id':del value['data']['research']['id']
    if fault=='bad-id':value['data']['research']['id']='not-a-reference'
    if fault=='version1-id':value['data']['research']['id']='12345678-1234-1234-8234-123456789abc'
    if fault=='uppercase-id':value['data']['research']['id']=RID.upper()
    if fault=='caps':value['data']['capabilities']=[]
    if fault=='missing-source':del value['data']['capabilities']['source_evidence']
    if fault=='integer-source':value['data']['capabilities']['source_evidence']=1
    if fault=='mismatched-id':rid=OTHER
    def forbidden(*args):raise AssertionError('invalid shape must not reach runtime')
    monkeypatch.setattr(source_integration,'request_execution_available',forbidden)
    with pytest.raises((ValueError,TypeError)):
        api._with_request_source_capability(value,app=None,service=None,research_id=rid,operation='view')


def _create_cache(store,key):
    with store.transaction() as conn:
        return conn.execute("SELECT result_json FROM research_idempotency WHERE operation='create' AND key_digest=?",(hashlib.sha256(key.encode()).hexdigest(),)).fetchone()[0]


def test_same_key_replay_refreshes_only_cap_and_keeps_formula_refs_time_and_cached_body(current14,monkeypatch):
    client,store,_=current14;key='request-source-cached-formula'
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','false')
    body={'problem':formula_problem()}
    first=post(client,'/api/research',body,key);assert first.status_code==200,first.text
    before=first.json();cached=_create_cache(store,key);rid=before['data']['research']['id']
    assert before['data']['capabilities']['source_evidence'] is False
    snapshot=client.get('/api/research/'+rid+'/formula-revisions/1')
    assert snapshot.status_code==200
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','true')
    second=post(client,'/api/research',body,key);assert second.status_code==200,second.text
    expected=deepcopy(before);expected['data']['capabilities']['source_evidence']=True
    assert second.json()==expected and _create_cache(store,key)==cached
    assert client.get('/api/research/'+rid+'/formula-revisions/1').json()==snapshot.json()
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','false')
    assert post(client,'/api/research',body,key).json()==before
    assert _create_cache(store,key)==cached


def test_presentation_boolean_does_not_unlock_any_source_post(current14,monkeypatch):
    client,store,rid=current14
    monkeypatch.setenv('STRUCTURAL_D1_SOURCES_ENABLED','false')
    monkeypatch.setattr(source_integration,'request_execution_available',lambda *args:True)
    view=client.get('/api/research/'+rid)
    assert view.status_code==200 and view.json()['data']['capabilities']['source_evidence'] is True
    request={'input_revision':1,'expected_research_version':view.json()['data']['research_version'],'query':'queue theory'}
    cases=[('source-preview',request),('source-approvals',{**request,'preview_digest':'0'*64,'confirm_external':True}),
           ('source-tasks',{'input_revision':1,'expected_research_version':request['expected_research_version'],'approval_ref':OTHER})]
    for suffix,body in cases:
        result=post(client,'/api/research/'+rid+'/'+suffix,body)
        assert result.status_code==503 and result.json()['error']['code']=='FEATURE_UNAVAILABLE'
    with store.transaction() as conn:
        assert conn.execute('SELECT count(*) FROM research_source_approvals').fetchone()[0]==0
        assert conn.execute('SELECT count(*) FROM research_source_runs').fetchone()[0]==0


@pytest.mark.parametrize('fault',['os-error','basic-unavailable','non-boolean','oversized','non-json'])
def test_post_commit_projection_failure_is_safe_and_original_key_recovers_saved_row(current14,monkeypatch,fault):
    client,store,_=current14;key='post-commit-source-'+fault;body={'problem':problem()}
    sentinel='DO_NOT_ECHO_CAPABILITY_INTERNAL'
    with monkeypatch.context() as broken:
        if fault in ('os-error','basic-unavailable'):
            def fail(*args):
                if fault=='os-error':raise OSError(sentinel)
                raise ResearchError('FEATURE_UNAVAILABLE',503,sentinel)
            broken.setattr(source_integration,'request_execution_available',fail)
        elif fault=='non-boolean':broken.setattr(source_integration,'request_execution_available',lambda *args:1)
        else:
            original=api._with_request_source_capability
            def bad(*args,**kwargs):
                value=original(*args,**kwargs)
                value['data']['synthetic_response_fault']='x'*api.RESEARCH_RESPONSE_LIMIT if fault=='oversized' else float('nan')
                return value
            broken.setattr(api,'_with_request_source_capability',bad)
        failed=post(client,'/api/research',body,key)
    assert failed.status_code==503 and failed.json()['error']['code']=='RESPONSE_UNAVAILABLE'
    assert '可能已保存' in failed.json()['error']['message'] and sentinel not in failed.text
    assert failed.json()['error']['retryable'] is False
    cache=_create_cache(store,key);saved=json.loads(cache)
    recovered=post(client,'/api/research',body,key)
    assert recovered.status_code==200,recovered.text
    assert recovered.json()==saved and _create_cache(store,key)==cache
    with store.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM research_idempotency WHERE operation='create' AND key_digest=?",(hashlib.sha256(key.encode()).hexdigest(),)).fetchone()[0]==1
