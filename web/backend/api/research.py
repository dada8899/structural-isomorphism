"""Authenticated research persistence, locally opt-in until lifecycle review."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

if __package__ == "web.backend.api":
    from . import auth
    from ..research.authorization import AccountIdentity
    from ..research.errors import ResearchError
    from ..research.provider_schemas import ProviderFailure
    from ..research.schemas import CreateEnvelope, RevisionEnvelope, StartEnvelope, TaskEnvelope, SourcePreviewEnvelope, SourceApprovalEnvelope, SourceStartEnvelope, ResearchIndexQuery, PaidPreviewEnvelope, PaidConfirmationEnvelope, FormulaCheckEnvelope, FormulaCheckResponse, FormulaResultResponse
    from ..research import source_integration
    from ..research import paid_api_public as paid_public
    from ..research import ResearchService, ResearchStore
else:
    from api import auth
    from research.authorization import AccountIdentity
    from research.errors import ResearchError
    from research.provider_schemas import ProviderFailure
    from research.schemas import CreateEnvelope, RevisionEnvelope, StartEnvelope, TaskEnvelope, SourcePreviewEnvelope, SourceApprovalEnvelope, SourceStartEnvelope, ResearchIndexQuery, PaidPreviewEnvelope, PaidConfirmationEnvelope, FormulaCheckEnvelope, FormulaCheckResponse, FormulaResultResponse
    from research import source_integration
    from research import paid_api_public as paid_public
    from research import ResearchService, ResearchStore

if __package__=='web.backend.api':
    from ..research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope,PlanPreviewResponse,PlanConfirmationResponse,PlanReadResponse
else:
    from research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope,PlanPreviewResponse,PlanConfirmationResponse,PlanReadResponse

router = APIRouter(tags=["research"])
_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
_PAID_OPERATIONS = ('paid-preview','paid-confirm')


def _paid_response_unavailable():
    # A response failure does not undo a committed approval. This literal
    # fallback never depends on a failing DTO validator or ResearchError.body.
    return JSONResponse({'error':{'code':'RESPONSE_UNAVAILABLE',
        'message':'响应暂时无法核对，操作可能已保存。请保留原操作标识，核对原记录。',
        'retryable':False,'allowed_next_actions':[],'incident_id':str(uuid4())}},status_code=503,headers=_HEADERS)


def _paid_error_response(error):
    try:
        body=paid_public.validate_error_response(error.body())
        return JSONResponse(body,status_code=error.status,headers=_HEADERS)
    except Exception:
        return _paid_response_unavailable()


def _paid_success_response(operation,result):
    try:
        body=paid_public.validate_success_response(operation,result)
        return JSONResponse(body,headers=_HEADERS)
    except Exception:
        return _paid_response_unavailable()


def _paid_responses(operation):
    return {200:{'model':paid_public.success_response_model(operation)},
        **{status:{'model':paid_public.ResearchPublicErrorEnvelope} for status in (401,403,404,409,413,422,429,503)}}


def _formula_request_body(schema):
    value=schema.model_json_schema();definitions=value.get('$defs',{})
    def expand(item):
        if type(item) is list:return [expand(v) for v in item]
        if type(item) is not dict:return item
        if '$ref' in item:return expand(definitions[item['$ref'].split('/')[-1]])
        return {k:expand(v) for k,v in item.items() if k!='$defs'}
    return {'required':True,'content':{'application/json':{'schema':expand(value)}}}


def enabled():
    # Claim, runner and billing remain incomplete. No flag can opt this
    # persistence/lifecycle candidate into production before release review.
    return (os.getenv("STRUCTURAL_RESEARCH_ENABLED", "false").lower() == "true"
            and os.getenv("STRUCTURAL_ENV", "dev").lower() != "prod")


def _identity(request):
    # Every account surface must reject conflicting or poisoned credentials.
    # Only after that common check may this checkpoint require a direct cookie.
    unified, unified_status = auth.resolve_account_user(request)
    if unified_status == "credential_conflict":
        raise ResearchError("AUTHORIZATION_STALE", 409, "登录凭据存在冲突，请退出后重新登录。")
    if unified_status != "valid" or unified is None:
        raise ResearchError("AUTH_REQUIRED", 401, "请先登录，再保存或读取研究。")
    user, status = auth.resolve_session_user(request)
    if status != "valid" or user is None or user["email"] != unified["email"]:
        raise ResearchError("AUTH_REQUIRED", 401, "请先登录，再保存或读取研究。")
    claims = auth._decode_jwt(request.cookies.get(auth._COOKIE_NAME, ""))
    if not claims or not all(isinstance(claims.get(k), str) and claims[k] for k in ("sub", "gen", "jti")):
        raise ResearchError("AUTH_REQUIRED", 401, "登录已失效，请重新登录。")
    if type(claims.get("exp")) is not int:
        raise ResearchError("AUTH_REQUIRED", 401, "登录已失效，请重新登录。")
    return AccountIdentity(user["email"], claims["gen"], claims["jti"], claims["exp"])


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("duplicate JSON key")
        obj[key] = value
    return obj


def _invalid_constant(_):
    raise ValueError("nonfinite JSON value")


async def _parse(request, schema):
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ResearchError("INPUT_INVALID", 422, "请提交 JSON 格式的研究内容。")
    raw = bytearray()
    async for chunk in request.stream():
        if len(raw) + len(chunk) > 65536:
            raise ResearchError("PAYLOAD_LIMIT", 413, "内容超过保存上限，请缩短后再试。")
        raw.extend(chunk)
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
        validated=schema.model_validate(body)
        request._body=bytes(raw)
        return validated
    except (ValueError, ValidationError, RecursionError, OverflowError):
        # Never return Pydantic input/ctx or JSON parser excerpts.
        raise ResearchError("INPUT_INVALID", 422, "研究内容、版本或字段不符合要求，请核对后再保存。") from None


async def _dispatch(request, *, research_id=None, operation="view"):
    try:
        if not enabled():
            raise ResearchError("FEATURE_UNAVAILABLE", 503, "研究保存功能尚未开放。")
        identity = await run_in_threadpool(_identity, request)
        service = await run_in_threadpool(lambda: ResearchService(ResearchStore(auth._store())))
        if operation == "index":
            pairs=list(request.query_params.multi_items())
            if len({key for key,_ in pairs})!=len(pairs) or any(key not in ("limit","cursor") for key,_ in pairs):
                raise ResearchError("INPUT_INVALID",422,"列表分页参数无效。")
            raw_limit=request.query_params.get("limit","20")
            if re.fullmatch(r"[1-9]|1[0-9]|20",raw_limit,re.ASCII) is None:
                raise ResearchError("INPUT_INVALID",422,"列表分页参数无效。")
            try:query=ResearchIndexQuery(limit=int(raw_limit),cursor=request.query_params.get("cursor"))
            except ValidationError:raise ResearchError("INPUT_INVALID",422,"列表分页参数无效。") from None
            result=await run_in_threadpool(service.index,identity,query)
        elif operation == "view":
            task_id=request.query_params.get("task_id")
            if task_id:service._id(task_id)
            if __package__=='web.backend.api':from ..research.paid_control import issue_authenticated_action
            else:from research.paid_control import issue_authenticated_action
            source=await run_in_threadpool(issue_authenticated_action,request,action='method-read')
            try:result = await run_in_threadpool(service.view, identity, research_id, task_id,request_source=source)
            finally:source.close()
        elif operation in ('formula-read','formula-revision-read'):
            if request.query_params:raise ResearchError('INPUT_INVALID',422,'公式读取不接受查询参数。')
            if __package__=='web.backend.api':
                from ..research.paid_control import issue_authenticated_action
                from ..research import formula_result
            else:
                from research.paid_control import issue_authenticated_action
                from research import formula_result
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:
                if operation=='formula-read':result=await run_in_threadpool(formula_result.read_result,service,identity,research_id,request.path_params['result_ref'],request_source=source)
                else:
                    raw_revision=request.path_params['revision']
                    if type(raw_revision) is not str or re.fullmatch(r'[1-9][0-9]{0,9}',raw_revision) is None:raise ResearchError('INPUT_INVALID',422,'公式修订无效。')
                    revision=int(raw_revision)
                    if not 1<=revision<=2147483647:raise ResearchError('INPUT_INVALID',422,'公式修订无效。')
                    result=await run_in_threadpool(formula_result.read_revision,service,identity,research_id,revision,request_source=source)
            finally:source.close()
        elif operation=='plan-read':
            if __package__=='web.backend.api':
                from ..research.paid_control import issue_authenticated_action
                from ..research.plan_result import read
            else:
                from research.paid_control import issue_authenticated_action
                from research.plan_result import read
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:result=await run_in_threadpool(read,service,identity,research_id,request.path_params['result_ref'],source)
            finally:source.close()
        elif operation == "source-records":
            result=await run_in_threadpool(source_integration.records,service,identity,research_id,request.query_params.get("task_id",""),request.query_params.get("kind",""),request.query_params.get("cursor"))
        elif operation == "events":
            raw_cursor=request.query_params.get("after_seq","0")
            if not re.fullmatch(r"[0-9]{1,12}",raw_cursor):raise ResearchError("INPUT_INVALID",422,"事件游标无效。")
            result=await run_in_threadpool(service.events,identity,research_id,request.query_params.get("task_id",""),int(raw_cursor))
        else:
            if auth.require_same_origin(request) is not None:
                raise ResearchError("AUTHORIZATION_STALE", 403, "请从本站页面保存研究。")
            key = request.headers.get("idempotency-key", "")
            if not _KEY.fullmatch(key):
                raise ResearchError("INPUT_INVALID", 422, "保存操作标识缺失或不合法。")
            if operation in ('paid-preview','paid-confirm') and request.query_params:
                raise ResearchError('INPUT_INVALID',422,'付费范围请求不接受查询参数。')
            if __package__=='web.backend.api':from ..research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope
            else:from research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope
            envelope = await _parse(request,{'plan-preview':PlanPreviewEnvelope,'plan-confirm':PlanConfirmationEnvelope,"create":CreateEnvelope,"revise":RevisionEnvelope,"start":StartEnvelope,
                                             'paid-preview':PaidPreviewEnvelope,'paid-confirm':PaidConfirmationEnvelope,
                                             "source-preview":SourcePreviewEnvelope,"source-approve":SourceApprovalEnvelope,"source-start":SourceStartEnvelope,
                                             "cancel":TaskEnvelope,"reconcile":TaskEnvelope,"resume":TaskEnvelope,"formula-check":FormulaCheckEnvelope}[operation])
            if operation in ('plan-preview','plan-confirm'):
                if __package__=='web.backend.api':
                    from ..research.paid_control import issue_authenticated_action
                    from ..research import plan_runtime
                else:
                    from research.paid_control import issue_authenticated_action
                    from research import plan_runtime
                source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
                function=plan_runtime.preview if operation=='plan-preview' else plan_runtime.confirm
                try:result=await run_in_threadpool(function,service,identity,research_id,envelope.data,key,source)
                finally:source.close()
            elif operation == "create":
                result = await run_in_threadpool(service.create, identity, envelope.data, key)
            elif operation in ('paid-preview','paid-confirm'):
                # Server composition only. Requests/env booleans cannot install
                # this controlled source; the normal application has none.
                resolver=getattr(request.app.state,'research_paid_resolver',None)
                method=service.paid_preview if operation=='paid-preview' else service.paid_confirm
                result=await run_in_threadpool(method,identity,research_id,envelope.data,key,funding_resolver=resolver)
            elif operation=='formula-check':
                if request.query_params:raise ResearchError('INPUT_INVALID',422,'公式检查不接受查询参数。')
                if __package__=='web.backend.api':
                    from ..research.paid_control import issue_authenticated_action
                    from ..research.formula_result import start as formula_start
                else:
                    from research.paid_control import issue_authenticated_action
                    from research.formula_result import start as formula_start
                source=await run_in_threadpool(issue_authenticated_action,request,action='formula-check')
                try:result=await run_in_threadpool(formula_start,service,identity,research_id,envelope.data,key,request_source=source)
                finally:source.close()
            elif operation == "revise":
                result = await run_in_threadpool(service.revise, identity, research_id, envelope.data, key)
            elif operation == "start":
                result=await run_in_threadpool(service.start,identity,research_id,envelope.data,key)
            elif operation == "source-preview":
                result=await run_in_threadpool(source_integration.preview,service,identity,research_id,envelope.data)
            elif operation in ('source-approve','source-start'):
                if __package__=='web.backend.api':from ..research.paid_control import issue_authenticated_action
                else:from research.paid_control import issue_authenticated_action
                source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
                function=source_integration.approve if operation=='source-approve' else source_integration.start_source
                try:result=await run_in_threadpool(function,service,identity,research_id,envelope.data,key,request_source=source)
                finally:source.close()
            else:
                if operation in ('cancel','reconcile'):
                    if __package__=='web.backend.api':from ..research.paid_control import issue_authenticated_action
                    else:from research.paid_control import issue_authenticated_action
                    source=await run_in_threadpool(issue_authenticated_action,request,action='cancel' if operation=='cancel' else 'method-reconcile')
                    try:result=await run_in_threadpool(service.task_action,identity,research_id,envelope.data,key,operation,request_source=source)
                    finally:source.close()
                else:result=await run_in_threadpool(service.task_action,identity,research_id,envelope.data,key,operation)
        if operation in _PAID_OPERATIONS:return _paid_success_response(operation,result)
        if operation in ('plan-preview','plan-confirm','plan-read'):
            try:
                model={'plan-preview':PlanPreviewResponse,'plan-confirm':PlanConfirmationResponse,'plan-read':PlanReadResponse}[operation]
                result=model.model_validate(result).model_dump(mode='json')
            except ValueError:return _paid_response_unavailable()
        if len(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'))>524288:
            raise ResearchError('PAYLOAD_LIMIT',413,'响应超过研究范围上限；旧记录未更改。')
        return JSONResponse(result, headers=_HEADERS)
    except ResearchError as exc:
        if operation in _PAID_OPERATIONS:return _paid_error_response(exc)
        return JSONResponse(exc.body(), status_code=exc.status, headers=_HEADERS)
    except ProviderFailure as exc:
        if operation not in ('paid-preview','paid-confirm') or str(exc)!='request_limit':raise
        error=ResearchError('PAYLOAD_LIMIT',413,'最终外发请求超过16KiB上限。')
        return _paid_error_response(error)
    except (sqlite3.Error, OSError):
        error = ResearchError("STORE_UNAVAILABLE", 503, "研究存储暂时不可用，请保留当前内容。")
        if operation in _PAID_OPERATIONS:return _paid_error_response(error)
        return JSONResponse(error.body(), status_code=error.status, headers=_HEADERS)


@router.post("/research",openapi_extra={"requestBody":_formula_request_body(CreateEnvelope)})
async def create_research(request: Request):
    return await _dispatch(request, operation="create")


@router.get("/research")
async def list_research(request: Request):
    return await _dispatch(request,operation="index")


@router.post("/research/{research_id}/revisions",openapi_extra={"requestBody":_formula_request_body(RevisionEnvelope)})
async def revise_research(research_id: str, request: Request):
    return await _dispatch(request, research_id=research_id, operation="revise")


@router.get("/research/{research_id}")
async def view_research(research_id: str, request: Request):
    return await _dispatch(request, research_id=research_id)


@router.post("/research/{research_id}/tasks")
async def start_research_task(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="start")


@router.post("/research/{research_id}/cancel")
async def cancel_research_task(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="cancel")


@router.post("/research/{research_id}/reconcile")
async def reconcile_research_task(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="reconcile")


@router.post("/research/{research_id}/resume")
async def resume_research_task(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="resume")


@router.get("/research/{research_id}/events")
async def research_task_events(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="events")


@router.post("/research/{research_id}/source-preview")
async def source_preview(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="source-preview")


@router.get("/research/{research_id}/records")
async def source_records(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="source-records")


@router.post("/research/{research_id}/source-approvals")
async def source_approval(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="source-approve")


@router.post("/research/{research_id}/source-tasks")
async def source_task(research_id: str,request: Request):
    return await _dispatch(request,research_id=research_id,operation="source-start")


@router.post('/research/{research_id}/paid-previews',
    openapi_extra={'requestBody':paid_public.request_body_schema('paid-preview')},responses=_paid_responses('paid-preview'))
async def paid_preview(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='paid-preview')


@router.post('/research/{research_id}/paid-approvals',
    openapi_extra={'requestBody':paid_public.request_body_schema('paid-confirm')},responses=_paid_responses('paid-confirm'))
async def paid_confirmation(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='paid-confirm')


@router.post('/research/{research_id}/formula-checks',openapi_extra={'requestBody':_formula_request_body(FormulaCheckEnvelope)},responses={200:{'model':FormulaCheckResponse}})
async def check_research_formula(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='formula-check')


@router.get('/research/{research_id}/formula-results/{result_ref}',responses={200:{'model':FormulaResultResponse}})
async def read_research_formula_result(research_id:str,result_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='formula-read')


@router.get('/research/{research_id}/formula-revisions/{revision}')
async def read_research_formula_revision(research_id:str,revision:int,request:Request):
    return await _dispatch(request,research_id=research_id,operation='formula-revision-read')


@router.post('/research/{research_id}/plan-previews',response_model=PlanPreviewResponse,openapi_extra={'requestBody':_formula_request_body(PlanPreviewEnvelope)})
async def preview_research_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-preview')

@router.post('/research/{research_id}/plan-approvals',response_model=PlanConfirmationResponse,openapi_extra={'requestBody':_formula_request_body(PlanConfirmationEnvelope)})
async def confirm_research_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-confirm')

@router.get('/research/{research_id}/plan-results/{result_ref}',response_model=PlanReadResponse)
async def read_research_plan(research_id:str,result_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-read')
