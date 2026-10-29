"""Public response wiring over real auth/service/SQLite; no provider execution."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import sqlite3

import pytest

from .test_research_persistence import stack,post,envelope,problem
from .test_research_d1_integration import source_stack
from .test_research_paid_approval import approved_inputs
from .test_research_paid_api import paid_api,preview_data,confirm_data,make_preview,counts
from api import research as api
from research import ResearchService
from research import paid_api_public as public
from research.errors import ResearchError

CANARY='PRIVATE-RESPONSE-CANARY-a072'
CHECK_ERROR=public.validate_error_response


def request_case(data,operation):
    client,_,_,rid,excerpt,_=data
    if operation=='paid-preview':return '/api/research/'+rid+'/paid-previews',preview_data(client,rid,excerpt)
    return '/api/research/'+rid+'/paid-approvals',confirm_data(make_preview(data))


def assert_unavailable(response):
    assert response.status_code==503,response.text
    assert response.headers['cache-control']=='no-store'
    assert response.headers['referrer-policy']=='no-referrer'
    value=response.json()
    assert CHECK_ERROR(value)==value
    assert value['error']['code']=='RESPONSE_UNAVAILABLE'
    assert value['error']['retryable'] is False
    assert value['error']['allowed_next_actions']==[]
    assert '可能已保存' in value['error']['message'] and '原操作标识' in value['error']['message']
    assert CANARY not in response.text and 'input_value' not in response.text
    return value


def assert_no_paid_execution(store):
    actual=counts(store)
    for name in ('research_reservations','research_dispatch_permits','research_cost_observations','research_provider_sessions'):
        assert actual[name]==0


def test_metadata_has_self_contained_requests_success_and_safe_errors_only(paid_api):
    client=paid_api[0];schema=client.app.openapi()
    for suffix,operation,model in [('paid-previews','paid-preview','PaidPreviewSuccessEnvelope'),
            ('paid-approvals','paid-confirm','PaidConfirmationSuccessEnvelope')]:
        path='/api/research/{research_id}/'+suffix
        declaration=schema['paths'][path]['post']
        assert declaration['requestBody']==public.request_body_schema(operation)
        assert '$ref' not in json.dumps(declaration['requestBody'])
        assert '$defs' not in json.dumps(declaration['requestBody'])
        assert declaration['responses']['200']['content']['application/json']['schema']=={'$ref':'#/components/schemas/'+model}
        for status in (401,403,404,409,413,422,429,503):
            assert declaration['responses'][str(status)]['content']['application/json']['schema']=={'$ref':'#/components/schemas/ResearchPublicErrorEnvelope'}
        route=next(route for route in client.app.routes if getattr(route,'path',None)==path)
        assert route.dependant.body_params==[] and route.response_field is None
    from research.schemas import CreateEnvelope
    from api.research import _formula_request_body
    create=schema['paths']['/api/research']['post']['requestBody']
    from fastapi.encoders import jsonable_encoder
    assert create==jsonable_encoder(_formula_request_body(CreateEnvelope),exclude_none=True)
    assert '$ref' not in json.dumps(create) and '$defs' not in json.dumps(create)
    route=next(route for route in client.app.routes if getattr(route,'path',None)=='/api/research')
    assert route.dependant.body_params==[] and route.response_field is None


@pytest.mark.parametrize('operation',['paid-preview','paid-confirm'])
@pytest.mark.parametrize('gate,status,code',[('disabled',503,'FEATURE_UNAVAILABLE'),('anonymous',401,'AUTH_REQUIRED'),('csrf',403,'AUTHORIZATION_STALE')])
@pytest.mark.parametrize('raw',[b'{',b'x'*65537],ids=['bad-json','over-limit'])
def test_metadata_never_reads_or_validates_body_before_existing_permissions(paid_api,monkeypatch,operation,gate,status,code,raw):
    client,_,store,_,_,_=paid_api;url,_=request_case(paid_api,operation);before=counts(store)
    if gate=='disabled':monkeypatch.setenv('STRUCTURAL_RESEARCH_ENABLED','false')
    elif gate=='anonymous':client.cookies.clear()
    response=client.post(url,content=raw,headers={'Content-Type':'application/json','Idempotency-Key':'priority',
        'Origin':'https://wrong.test' if gate=='csrf' else 'http://testserver'})
    assert response.status_code==status,response.text
    assert response.json()['error']['code']==code and counts(store)==before
    assert CHECK_ERROR(response.json())==response.json()


@pytest.mark.parametrize('operation,path,value',[
    ('paid-preview',('data','private'),CANARY),
    ('paid-preview',('data','maximum_reserve','amount_units'),True),
    ('paid-preview',('data','maximum_reserve','amount_units'),'3'),
    ('paid-preview',('data','maximum_reserve','scale'),6.0),
    ('paid-preview',('data','maximum_reserve','currency'),'USD'),
    ('paid-preview',('data','actual'),0),
    ('paid-preview',('data','may_send_to_provider'),True),
    ('paid-preview',('data','model_analysis_ran'),True),
    ('paid-preview',('data','preview_digest'),'0'*64),
    ('paid-preview',('data','private'),CANARY+'x'*(512*1024)),
    ('paid-confirm',('data','private'),CANARY),
    ('paid-confirm',('data','task_version'),True),
    ('paid-confirm',('data','preview_version'),1.0),
    ('paid-confirm',('data','model_analysis_ran'),True),
    ('paid-confirm',('data','execution_mode'),'live'),
],ids=['preview-extra','bool-money','string-money','float-scale','currency','actual','send-flag','model-flag','digest','over-response-cap',
    'confirm-extra','task-bool','version-float','confirm-model-flag','live-label'])
def test_actual_committed_output_must_pass_strict_public_validator(paid_api,monkeypatch,caplog,capsys,operation,path,value):
    client,_,store,_,_,_=paid_api;url,body=request_case(paid_api,operation)
    original=ResearchService._paid_envelope;validate=public.validate_success_response;safe_errors=[]
    def corrupt(data):
        output=deepcopy(original(data));node=output
        for key in path[:-1]:node=node[key]
        node[path[-1]]=value
        return output
    def inspect_failure(op,payload):
        try:return validate(op,payload)
        except public.PaidPublicValidationError as exc:
            safe_errors.append((exc.__context__,exc.__cause__,str(exc),repr(vars(exc))))
            raise
    monkeypatch.setattr(ResearchService,'_paid_envelope',staticmethod(corrupt))
    monkeypatch.setattr(public,'validate_success_response',inspect_failure)
    assert_unavailable(post(client,url,body,'fault-output'))
    assert safe_errors and all(context is None and cause is None and CANARY not in text+attrs for context,cause,text,attrs in safe_errors)
    assert_no_paid_execution(store)
    captured=capsys.readouterr()
    assert CANARY not in caplog.text+captured.out+captured.err


@pytest.mark.parametrize('fault',['body-extra','body-raises','validator-raises','serialization-raises'])
def test_error_output_failure_has_independent_nonrecursive_safe_fallback(paid_api,monkeypatch,caplog,capsys,fault):
    client,_,store,_,_,_=paid_api;url,body=request_case(paid_api,'paid-preview');before=counts(store);calls=[]
    if fault=='body-extra':
        original=ResearchError.body
        def bad(error):
            value=original(error);value['error']['private']=CANARY;calls.append(True);return value
        monkeypatch.setattr(ResearchError,'body',bad)
    elif fault=='body-raises':
        def bad(error):calls.append(True);raise ValueError(CANARY)
        monkeypatch.setattr(ResearchError,'body',bad)
    elif fault=='validator-raises':
        def bad(value):calls.append(True);raise ValueError(CANARY)
        monkeypatch.setattr(public,'validate_error_response',bad)
    else:
        original=api.JSONResponse
        def bad(content,*args,**kwargs):
            if content.get('error',{}).get('code')!='RESPONSE_UNAVAILABLE':
                calls.append(True)
                raise ValueError(CANARY)
            return original(content,*args,**kwargs)
        monkeypatch.setattr(api,'JSONResponse',bad)
    first=assert_unavailable(post(client,url+'?unapproved=true',body,'error-fault'))
    second=assert_unavailable(post(client,url+'?unapproved=true',body,'error-fault'))
    assert len(calls)==2 and first['error']['incident_id']!=second['error']['incident_id']
    assert counts(store)==before
    captured=capsys.readouterr()
    assert CANARY not in caplog.text+captured.out+captured.err


def test_confirm_commit_then_validation_failure_recovers_original_key_and_cancelled_task(paid_api,monkeypatch):
    client,_,store,rid,_,_=paid_api;url,body=request_case(paid_api,'paid-confirm');before=counts(store)
    original=ResearchService._paid_envelope
    def corrupt(data):
        value=original(data);value['data']['private']=CANARY;return value
    with monkeypatch.context() as patch:
        patch.setattr(ResearchService,'_paid_envelope',staticmethod(corrupt))
        assert_unavailable(post(client,url,body,'committed-response'))
    committed=counts(store)
    assert committed['research_tasks']==before['research_tasks']+1 and committed['research_grants']==before['research_grants']+1
    assert_no_paid_execution(store)
    recovered=post(client,url,body,'committed-response');assert recovered.status_code==200,recovered.text
    first=recovered.json()['data'];assert first['execution']=='QUEUED'
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses=list(pool.map(lambda _:post(client,url,body,'committed-response'),range(3)))
    assert all(response.status_code==200 and response.json()==recovered.json() for response in responses)
    cancelled=post(client,f'/api/research/{rid}/cancel',{'task_id':first['task_id'],'expected_task_version':first['task_version']})
    assert cancelled.status_code==200,cancelled.text
    replay=post(client,url,body,'committed-response');assert replay.status_code==200,replay.text
    assert replay.json()['data']['task_id']==first['task_id'] and replay.json()['data']['execution']=='CANCELLED'
    assert replay.json()['data']['status']=='cancelled' and counts(store)==committed
    assert_no_paid_execution(store)


def test_serialization_failure_after_confirmation_also_preserves_commit(paid_api,monkeypatch):
    client,_,store,_,_,_=paid_api;url,body=request_case(paid_api,'paid-confirm');before=counts(store);original=api.JSONResponse
    def encode(content,*args,**kwargs):
        if type(content) is dict and 'data' in content:raise ValueError(CANARY)
        return original(content,*args,**kwargs)
    with monkeypatch.context() as patch:
        patch.setattr(api,'JSONResponse',encode)
        assert_unavailable(post(client,url,body,'encode-once'))
    response=post(client,url,body,'encode-once');assert response.status_code==200,response.text
    assert counts(store)['research_tasks']==before['research_tasks']+1
    assert_no_paid_execution(store)


@pytest.mark.parametrize('error',[OSError,sqlite3.OperationalError])
def test_real_service_io_fault_keeps_original_store_error_mapping(paid_api,monkeypatch,error):
    client,_,store,_,_,_=paid_api;url,body=request_case(paid_api,'paid-preview');before=counts(store)
    def fail(*args,**kwargs):raise error(CANARY)
    monkeypatch.setattr(ResearchService,'paid_preview',fail)
    response=post(client,url,body,'store-fault')
    assert response.status_code==503 and response.json()['error']['code']=='STORE_UNAVAILABLE'
    assert CANARY not in response.text and counts(store)==before


def test_other_research_operations_never_use_paid_public_validation(paid_api,monkeypatch):
    client,_,_,rid,_,_=paid_api
    def forbidden(*args,**kwargs):pytest.fail('unrelated API entered paid output validation')
    monkeypatch.setattr(public,'validate_success_response',forbidden)
    monkeypatch.setattr(public,'validate_error_response',forbidden)
    assert client.get('/api/research/'+rid).status_code==200
    assert post(client,'/api/research',{'problem':problem()},'unrelated-create').status_code==200
    assert post(client,'/api/research',{},'unrelated-error').status_code==422
