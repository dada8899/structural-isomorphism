"""Authenticated research persistence, locally opt-in until lifecycle review."""
from __future__ import annotations

import json
import os
import re
import sqlite3
from uuid import UUID, uuid4

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
    from ..research.projection import projection_bytes,RESEARCH_RESPONSE_LIMIT
    from ..research.schemas import SCHEMA_VERSION,CONTRACT_REVISION
else:
    from api import auth
    from research.authorization import AccountIdentity
    from research.errors import ResearchError
    from research.provider_schemas import ProviderFailure
    from research.schemas import CreateEnvelope, RevisionEnvelope, StartEnvelope, TaskEnvelope, SourcePreviewEnvelope, SourceApprovalEnvelope, SourceStartEnvelope, ResearchIndexQuery, PaidPreviewEnvelope, PaidConfirmationEnvelope, FormulaCheckEnvelope, FormulaCheckResponse, FormulaResultResponse
    from research import source_integration
    from research import paid_api_public as paid_public
    from research import ResearchService, ResearchStore
    from research.projection import projection_bytes,RESEARCH_RESPONSE_LIMIT
    from research.schemas import SCHEMA_VERSION,CONTRACT_REVISION

if __package__=='web.backend.api':
    from ..research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope,PlanPreviewResponse,PlanConfirmationResponse,PlanReadResponse
    from ..research.plan_native_schemas import NativePlanPreviewEnvelope,NativePlanConfirmationEnvelope,NativePlanPreviewResponse,NativePlanConfirmationResponse,NativePlanReadResponse
else:
    from research.plan_schemas import PlanPreviewEnvelope,PlanConfirmationEnvelope,PlanPreviewResponse,PlanConfirmationResponse,PlanReadResponse
    from research.plan_native_schemas import NativePlanPreviewEnvelope,NativePlanConfirmationEnvelope,NativePlanPreviewResponse,NativePlanConfirmationResponse,NativePlanReadResponse

if __package__=='web.backend.api':
    from ..research.method_draft_schemas import MethodDraftEnvelope,MethodDraftResponse,MethodDraftHistoryResponse
    from ..research.financial_input_schemas import FinancialImportPreviewEnvelope,FinancialImportPreviewResponse
    from ..research.financial_input_schemas import FinancialRegistryConfirmationEnvelope,FinancialRegistryConfirmationResponse,FinancialRegistryReadResponse,FinancialRegistryHistoryResponse
else:
    from research.method_draft_schemas import MethodDraftEnvelope,MethodDraftResponse,MethodDraftHistoryResponse
    from research.financial_input_schemas import FinancialImportPreviewEnvelope,FinancialImportPreviewResponse
    from research.financial_input_schemas import FinancialRegistryConfirmationEnvelope,FinancialRegistryConfirmationResponse,FinancialRegistryReadResponse,FinancialRegistryHistoryResponse

if __package__=='web.backend.api':
    from ..research.evidence_method_plan_schemas import EvidenceMethodPreviewEnvelope,EvidenceMethodConfirmEnvelope,EvidenceMethodPreviewResponse,EvidenceMethodConfirmResponse,EvidenceMethodReadResponse,EvidenceMethodListResponse,EvidenceMethodErrorResponse
    from ..research import evidence_method_plan as evidence_method,evidence_method_plan_codec as evidence_codec
else:
    from research.evidence_method_plan_schemas import EvidenceMethodPreviewEnvelope,EvidenceMethodConfirmEnvelope,EvidenceMethodPreviewResponse,EvidenceMethodConfirmResponse,EvidenceMethodReadResponse,EvidenceMethodListResponse,EvidenceMethodErrorResponse
    from research import evidence_method_plan as evidence_method,evidence_method_plan_codec as evidence_codec
_EVIDENCE_OPERATIONS=('evidence-method-preview','evidence-method-confirm','evidence-method-read','evidence-method-list')
_EVIDENCE_MODELS=(EvidenceMethodPreviewResponse,EvidenceMethodConfirmResponse,EvidenceMethodReadResponse,EvidenceMethodListResponse)


def _evidence_error(error):
    allowed={401:{'AUTH_REQUIRED'},403:{'AUTHORIZATION_STALE','FUNDING_GRANT_REQUIRED'},404:{'NOT_FOUND'},409:{'REVISION_CONFLICT','IDEMPOTENCY_CONFLICT','PREVIEW_CHANGED','PREVIEW_EXPIRED','TASK_ACTIVE','FUNDING_BUSY','FUNDING_STALE','SOURCE_PERMISSION_UNAVAILABLE','RECONCILIATION_REQUIRED'},413:{'PAYLOAD_LIMIT'},422:{'INPUT_INVALID'},429:{'BUDGET_EXHAUSTED'},503:{'FEATURE_UNAVAILABLE','FUNDING_CLOSED','STORE_UNAVAILABLE','RESULT_UNAVAILABLE','RESPONSE_UNAVAILABLE','CLEANUP_UNCERTAIN'}}
    if error.code=='AUTHORIZATION_STALE':error=ResearchError('AUTHORIZATION_STALE',403,'当前权限已变化，请重新登录并读取研究。')
    if error.code not in allowed.get(error.status,set()):error=ResearchError('RESULT_UNAVAILABLE',503,'方法计划记录当前无法核对，请保留原操作标识。')
    body=EvidenceMethodErrorResponse.model_validate(error.body()).model_dump(mode='json')
    if len(evidence_codec.bounded(body,4096))>4096:raise ValueError('bounded evidence error required')
    return JSONResponse(body,status_code=error.status,headers=_HEADERS)


async def _parse_evidence(request,model):
    if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':raise ResearchError('INPUT_INVALID',422,'请提交 JSON 格式的方法计划请求。')
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>65536:raise ResearchError('PAYLOAD_LIMIT',413,'方法计划请求超过上限。')
        raw.extend(chunk)
    try:value=evidence_codec.parse_model(model,bytes(raw),65536)
    except evidence_codec.EvidenceMethodLimit:raise ResearchError('PAYLOAD_LIMIT',413,'方法计划请求超过上限。') from None
    except (ValueError,TypeError,RecursionError,OverflowError):raise ResearchError('INPUT_INVALID',422,'方法计划字段或版本不符合要求。') from None
    request._body=bytes(raw);return value


router = APIRouter(tags=["research"])
_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
_PAID_OPERATIONS = ('paid-preview','paid-confirm')
_ROOT_VIEW_OPERATIONS = ('create','revise','view','start','source-start','cancel','reconcile','resume')


def _with_request_source_capability(result,*,app,service,research_id,operation):
    """Copy only the Root envelope/data/caps; cached typed content stays intact."""
    if operation not in _ROOT_VIEW_OPERATIONS:return result
    if (type(result) is not dict or set(result)!={'schema_version','contract_revision','data'}
            or result['schema_version']!=SCHEMA_VERSION or result['contract_revision']!=CONTRACT_REVISION
            or type(result['data']) is not dict):
        raise ValueError('Root envelope unavailable')
    data=result['data'];research=data.get('research');caps=data.get('capabilities')
    if (type(research) is not dict or type(research.get('id')) is not str
            or type(caps) is not dict or type(caps.get('source_evidence')) is not bool):
        raise ValueError('Root capability shape unavailable')
    rid=research['id'];parsed=UUID(rid)
    if parsed.version!=4 or str(parsed)!=rid or (operation!='create' and rid!=research_id):
        raise ValueError('Root research identity differs')
    available=source_integration.request_execution_available(app,service)
    if type(available) is not bool:raise TypeError('Source availability must be boolean')
    return {**result,'data':{**data,'capabilities':{**caps,'source_evidence':available}}}


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
        if schema in (PlanPreviewEnvelope,PlanConfirmationEnvelope) and type(body) is dict and body.get('contract_revision')=='funded-plan-v2':
            if __package__=='web.backend.api':from ..research.plan_native_schemas import NativePlanPreviewEnvelope,NativePlanConfirmationEnvelope
            else:from research.plan_native_schemas import NativePlanPreviewEnvelope,NativePlanConfirmationEnvelope
            schema=NativePlanPreviewEnvelope if schema is PlanPreviewEnvelope else NativePlanConfirmationEnvelope
        validated=schema.model_validate(body)
        request._body=bytes(raw)
        return validated
    except (ValueError, ValidationError, RecursionError, OverflowError):
        # Never return Pydantic input/ctx or JSON parser excerpts.
        raise ResearchError("INPUT_INVALID", 422, "研究内容、版本或字段不符合要求，请核对后再保存。") from None


async def _read_financial_import_bytes(request):
    if __package__=='web.backend.api':
        from ..research.financial_input_schemas import WIRE_LIMIT, FinancialImportError
    else:
        from research.financial_input_schemas import WIRE_LIMIT, FinancialImportError
    if request.headers.get('content-type','').split(';',1)[0].strip().lower()!='application/json':
        raise FinancialImportError('JSON_CONTENT_TYPE_REQUIRED')
    raw=bytearray()
    async for chunk in request.stream():
        if len(raw)+len(chunk)>WIRE_LIMIT:raise FinancialImportError('WIRE_LIMIT',limit=True)
        raw.extend(chunk)
    return bytes(raw)


async def _parse_financial_import_preview(request):
    if __package__=='web.backend.api':from ..research.financial_input_schemas import decode_financial_import_preview
    else:from research.financial_input_schemas import decode_financial_import_preview
    raw=await _read_financial_import_bytes(request)
    envelope=decode_financial_import_preview(raw)
    request._body=bytes(raw)
    return envelope


async def _parse_financial_registry_confirmation(request):
    if __package__=='web.backend.api':from ..research.financial_input_schemas import decode_financial_registry_confirmation
    else:from research.financial_input_schemas import decode_financial_registry_confirmation
    raw=await _read_financial_import_bytes(request)
    envelope=decode_financial_registry_confirmation(raw)
    request._body=raw
    return envelope


async def _dispatch(request, *, research_id=None, operation="view"):
    try:
        if __package__=='web.backend.api':from ..research.runtime_profile import formal_request_required,require_formal_application
        else:from research.runtime_profile import formal_request_required,require_formal_application
        if formal_request_required(request.app):require_formal_application(request.app,'research_basic')
        elif not enabled():
            raise ResearchError("FEATURE_UNAVAILABLE", 503, "研究保存功能尚未开放。")
        identity = await run_in_threadpool(_identity, request)
        service = await run_in_threadpool(lambda: ResearchService(ResearchStore(auth._store())))
        # Captured private storage never falls back to a development flag after
        # environment downgrade, including requests outside canonical Main.
        if service.store._formal_mode():require_formal_application(request.app,'research_basic')
        if operation in _EVIDENCE_OPERATIONS:
            if __package__=='web.backend.api':
                from ..research.paid_control import issue_authenticated_action
                from ..research import plan_native_runtime
            else:
                from research.paid_control import issue_authenticated_action
                from research import plan_native_runtime
            if operation in _EVIDENCE_OPERATIONS[:2]:
                if auth.require_same_origin(request) is not None:raise ResearchError('AUTHORIZATION_STALE',403,'请从本站页面确认外发范围。')
                key=request.headers.get('idempotency-key','')
                if not _KEY.fullmatch(key) or request.query_params:raise ResearchError('INPUT_INVALID',422,'方法计划操作标识或参数不合法。')
                parsed=await _parse_evidence(request,EvidenceMethodPreviewEnvelope if operation=='evidence-method-preview' else EvidenceMethodConfirmEnvelope)
            elif operation=='evidence-method-list':limit,cursor=evidence_method.list_query(list(request.query_params.multi_items()))
            elif request.query_params:raise ResearchError('INPUT_INVALID',422,'方法计划读取不接受查询参数。')
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:
                if operation in _EVIDENCE_OPERATIONS[:2]:
                    function=plan_native_runtime.preview if operation=='evidence-method-preview' else plan_native_runtime.confirm
                    result=await run_in_threadpool(function,service,identity,research_id,parsed.data,key,source)
                elif operation=='evidence-method-read':result=await run_in_threadpool(evidence_method.read,service,identity,research_id,request.path_params['result_ref'],source)
                else:result=await run_in_threadpool(evidence_method.list_results,service,identity,research_id,limit,cursor,source)
            finally:source.close()
            try:
                checked=_EVIDENCE_MODELS[_EVIDENCE_OPERATIONS.index(operation)].model_validate(result)
                evidence_codec.bounded(checked,(32768,4096,49152,49152)[_EVIDENCE_OPERATIONS.index(operation)])
                return JSONResponse(checked.model_dump(mode='json'),headers=_HEADERS)
            except Exception:return _paid_response_unavailable()
        if operation in ('financial-registry-save','financial-registry-read','financial-registry-history'):
            if __package__=='web.backend.api':
                from ..research import financial_input
                from ..research.paid_control import issue_authenticated_action
            else:
                from research import financial_input
                from research.paid_control import issue_authenticated_action
            if operation=='financial-registry-save':
                if auth.require_same_origin(request) is not None:raise ResearchError('AUTHORIZATION_STALE',403,'请从本站页面确认财务输入。')
                key=request.headers.get('idempotency-key','')
                if not _KEY.fullmatch(key) or request.query_params:raise ResearchError('INPUT_INVALID',422,'财务保存操作标识或参数不合法。')
                envelope=await _parse_financial_registry_confirmation(request)
            elif operation=='financial-registry-history':limit,cursor=financial_input.history_query(list(request.query_params.multi_items()))
            elif request.query_params:raise ResearchError('INPUT_INVALID',422,'财务记录读取不接受查询参数。')
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:
                if operation=='financial-registry-save':response=await run_in_threadpool(financial_input.save_registry,service,identity,research_id,envelope.data,key,source)
                elif operation=='financial-registry-read':response=await run_in_threadpool(financial_input.read_registry,service,identity,research_id,request.path_params['registry_ref'],source)
                else:response=await run_in_threadpool(financial_input.history,service,identity,research_id,limit,cursor,source)
            finally:source.close()
            try:
                model={'financial-registry-save':FinancialRegistryConfirmationResponse,'financial-registry-read':FinancialRegistryReadResponse,'financial-registry-history':FinancialRegistryHistoryResponse}[operation]
                if type(response) is not model:raise ValueError('fixed registry response required')
                result=model.model_validate_json(response.model_dump_json()).model_dump(mode='json')
                if projection_bytes(result)>RESEARCH_RESPONSE_LIMIT:raise ValueError('registry response limit')
                return JSONResponse(result,headers=_HEADERS)
            except Exception:
                if operation=='financial-registry-save':return _paid_response_unavailable()
                return JSONResponse(ResearchError('RESPONSE_UNAVAILABLE',503,'财务记录响应当前无法核对，请重新读取。').body(),status_code=503,headers=_HEADERS)
        elif operation=='financial-import-preview':
            if __package__=='web.backend.api':
                from ..research.financial_import import preview_import
                from ..research.paid_control import issue_authenticated_action
            else:
                from research.financial_import import preview_import
                from research.paid_control import issue_authenticated_action
            if auth.require_same_origin(request) is not None:raise ResearchError('AUTHORIZATION_STALE',403,'请从本站页面预览财务输入。')
            if not _KEY.fullmatch(request.headers.get('idempotency-key','')) or request.query_params:
                raise ResearchError('INPUT_INVALID',422,'预览操作标识或请求参数不合法。')
            envelope=await _parse_financial_import_preview(request)
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:
                response=await run_in_threadpool(preview_import,service,identity,research_id,envelope.data,source)
                result=response.model_dump(mode='json')
            finally:source.close()
        elif operation in ('draft-save','draft-read','draft-history'):
            if __package__=='web.backend.api':
                from ..research import method_draft
                from ..research.paid_control import issue_authenticated_action
            else:
                from research import method_draft
                from research.paid_control import issue_authenticated_action
            if operation=='draft-save':
                if auth.require_same_origin(request) is not None:raise ResearchError('AUTHORIZATION_STALE',403,'请从本站页面保存草稿。')
                key=request.headers.get('idempotency-key','')
                if not _KEY.fullmatch(key):raise ResearchError('INPUT_INVALID',422,'保存操作标识缺失或不合法。')
                if request.query_params:raise ResearchError('INPUT_INVALID',422,'草稿保存不接受查询参数。')
                envelope=await _parse(request,MethodDraftEnvelope)
            elif operation=='draft-history':
                pairs=list(request.query_params.multi_items());raw_limit=request.query_params.get('limit','20')
                if len({k for k,_ in pairs})!=len(pairs) or any(k not in ('limit','cursor') for k,_ in pairs) or re.fullmatch(r'[1-9]|1[0-9]|20',raw_limit,re.ASCII) is None:
                    raise ResearchError('INPUT_INVALID',422,'草稿分页参数无效。')
                cursor=request.query_params.get('cursor')
                if cursor is not None:service._id(cursor)
            elif request.query_params:raise ResearchError('INPUT_INVALID',422,'草稿读取不接受查询参数。')
            source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
            try:
                if operation=='draft-save':result=await run_in_threadpool(method_draft.save,service,identity,research_id,envelope.data,key,source)
                elif operation=='draft-read':result=await run_in_threadpool(method_draft.read,service,identity,research_id,request.path_params['draft_ref'],source)
                else:result=await run_in_threadpool(method_draft.history,service,identity,research_id,int(raw_limit),cursor,source)
            finally:source.close()
        elif operation == "index":
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
            try:
                if __package__=='web.backend.api':from ..research import plan_native_runtime
                else:from research import plan_native_runtime
                with service.store.transaction() as conn:
                    native=conn.execute("SELECT 1 FROM sqlite_schema WHERE name='research_plan_native_runs'").fetchone()
                    native=native and conn.execute('SELECT 1 FROM research_plan_native_runs WHERE result_ref=?',(request.path_params['result_ref'],)).fetchone()
                if native:result=await run_in_threadpool(plan_native_runtime.read,service,identity,research_id,request.path_params['result_ref'],source)
                else:result=await run_in_threadpool(read,service,identity,research_id,request.path_params['result_ref'],source)
            finally:source.close()
        elif operation == "source-records":
            result=await run_in_threadpool(source_integration.records,service,identity,research_id,request.query_params.get("task_id",""),request.query_params.get("kind",""),request.query_params.get("cursor"),request_app=request.app)
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
                if envelope.contract_revision=='funded-plan-v2':
                    if __package__=='web.backend.api':from ..research import plan_native_runtime
                    else:from research import plan_native_runtime
                    function=plan_native_runtime.preview if operation=='plan-preview' else plan_native_runtime.confirm
                else:function=plan_runtime.preview if operation=='plan-preview' else plan_runtime.confirm
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
                result=await run_in_threadpool(source_integration.preview,service,identity,research_id,envelope.data,request_app=request.app)
            elif operation in ('source-approve','source-start'):
                if __package__=='web.backend.api':from ..research.paid_control import issue_authenticated_action
                else:from research.paid_control import issue_authenticated_action
                source=await run_in_threadpool(issue_authenticated_action,request,action=operation)
                function=source_integration.approve if operation=='source-approve' else source_integration.start_source
                try:result=await run_in_threadpool(function,service,identity,research_id,envelope.data,key,request_source=source,request_app=request.app)
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
                models=({'plan-preview':NativePlanPreviewResponse,'plan-confirm':NativePlanConfirmationResponse,'plan-read':NativePlanReadResponse} if result.get('contract_revision')=='funded-plan-v2' else {'plan-preview':PlanPreviewResponse,'plan-confirm':PlanConfirmationResponse,'plan-read':PlanReadResponse})
                model=models[operation]
                result=model.model_validate(result).model_dump(mode='json')
            except ValueError:return _paid_response_unavailable()
        if operation in _ROOT_VIEW_OPERATIONS:
            try:
                result=await run_in_threadpool(_with_request_source_capability,result,
                    app=request.app,service=service,research_id=research_id,operation=operation)
                if projection_bytes(result)>RESEARCH_RESPONSE_LIMIT:
                    raise ValueError('Root response exceeds bounded projection')
                return JSONResponse(result,headers=_HEADERS)
            except Exception:
                # Business work may already be committed. Use the fixed safe
                # possible-save/retain-key response; never claim a rollback.
                return _paid_response_unavailable()
        if len(json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'))>524288:
            raise ResearchError('PAYLOAD_LIMIT',413,'响应超过研究范围上限；旧记录未更改。')
        return JSONResponse(result, headers=_HEADERS)
    except ResearchError as exc:
        if operation in _EVIDENCE_OPERATIONS:return _evidence_error(exc)
        if operation in _PAID_OPERATIONS:return _paid_error_response(exc)
        return JSONResponse(exc.body(), status_code=exc.status, headers=_HEADERS)
    except ProviderFailure as exc:
        if operation not in ('paid-preview','paid-confirm') or str(exc)!='request_limit':raise
        error=ResearchError('PAYLOAD_LIMIT',413,'最终外发请求超过16KiB上限。')
        return _paid_error_response(error)
    except evidence_codec.EvidenceMethodLimit:
        if operation not in _EVIDENCE_OPERATIONS:raise
        if operation in ('evidence-method-read','evidence-method-list'):return _evidence_error(ResearchError('RESULT_UNAVAILABLE',503,'原方法计划记录当前无法完整核对。'))
        return _evidence_error(ResearchError('PAYLOAD_LIMIT',413,'完整方法计划或引用超过上限，请缩小选择范围。'))
    except (ValueError,TypeError,LookupError):
        if operation not in _EVIDENCE_OPERATIONS:raise
        return _evidence_error(ResearchError('RESULT_UNAVAILABLE',503,'方法计划完整性当前无法核对，请保留原标识。'))
    except PermissionError:
        if operation in _EVIDENCE_OPERATIONS:return _evidence_error(ResearchError('AUTHORIZATION_STALE',403,'当前权限已变化，请重新读取。'))
        if operation not in ('draft-save','draft-read','draft-history','financial-import-preview','financial-registry-save','financial-registry-read','financial-registry-history'):raise
        error=ResearchError('AUTHORIZATION_STALE',409,'财务操作权限已变化，请重新读取后再操作。' if operation.startswith('financial-') else '方法草稿权限已变化，请重新读取后再操作。')
        return JSONResponse(error.body(),status_code=error.status,headers=_HEADERS)
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


@router.post('/research/{research_id}/plan-previews',response_model=PlanPreviewResponse|NativePlanPreviewResponse,openapi_extra={'requestBody':{'required':True,'content':{'application/json':{'schema':{'oneOf':[_formula_request_body(PlanPreviewEnvelope)['content']['application/json']['schema'],_formula_request_body(NativePlanPreviewEnvelope)['content']['application/json']['schema']]}}}}})
async def preview_research_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-preview')

@router.post('/research/{research_id}/plan-approvals',response_model=PlanConfirmationResponse|NativePlanConfirmationResponse,openapi_extra={'requestBody':{'required':True,'content':{'application/json':{'schema':{'oneOf':[_formula_request_body(PlanConfirmationEnvelope)['content']['application/json']['schema'],_formula_request_body(NativePlanConfirmationEnvelope)['content']['application/json']['schema']]}}}}})
async def confirm_research_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-confirm')

@router.get('/research/{research_id}/plan-results/{result_ref}',response_model=PlanReadResponse|NativePlanReadResponse)
async def read_research_plan(research_id:str,result_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='plan-read')


@router.post('/research/{research_id}/method-drafts',response_model=MethodDraftResponse,openapi_extra={'requestBody':_formula_request_body(MethodDraftEnvelope)})
async def save_research_method_draft(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='draft-save')

@router.get('/research/{research_id}/method-drafts',response_model=MethodDraftHistoryResponse)
async def list_research_method_drafts(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='draft-history')

@router.get('/research/{research_id}/method-drafts/{draft_ref}',response_model=MethodDraftResponse)
async def read_research_method_draft(research_id:str,draft_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='draft-read')


@router.post('/research/{research_id}/financial-import-preview',response_model=FinancialImportPreviewResponse,
             openapi_extra={'requestBody':_formula_request_body(FinancialImportPreviewEnvelope)})
async def preview_research_financial_import(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='financial-import-preview')


@router.post('/research/{research_id}/financial-registries',response_model=FinancialRegistryConfirmationResponse,
             openapi_extra={'requestBody':_formula_request_body(FinancialRegistryConfirmationEnvelope)})
async def save_research_financial_registry(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='financial-registry-save')


@router.get('/research/{research_id}/financial-registries',response_model=FinancialRegistryHistoryResponse)
async def list_research_financial_registries(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='financial-registry-history')


@router.get('/research/{research_id}/financial-registries/{registry_ref}',response_model=FinancialRegistryReadResponse)
async def read_research_financial_registry(research_id:str,registry_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='financial-registry-read')


@router.post('/research/{research_id}/evidence-method-plan-previews',response_model=EvidenceMethodPreviewResponse,responses={s:{'model':EvidenceMethodErrorResponse} for s in (401,403,404,409,413,422,429,503)},openapi_extra={'requestBody':_formula_request_body(EvidenceMethodPreviewEnvelope)})
async def preview_evidence_method_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='evidence-method-preview')

@router.post('/research/{research_id}/evidence-method-plan-approvals',response_model=EvidenceMethodConfirmResponse,responses={s:{'model':EvidenceMethodErrorResponse} for s in (401,403,404,409,413,422,429,503)},openapi_extra={'requestBody':_formula_request_body(EvidenceMethodConfirmEnvelope)})
async def confirm_evidence_method_plan(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='evidence-method-confirm')

@router.get('/research/{research_id}/evidence-method-plans/{result_ref}',response_model=EvidenceMethodReadResponse,responses={s:{'model':EvidenceMethodErrorResponse} for s in (401,403,404,409,413,422,429,503)})
async def read_evidence_method_plan(research_id:str,result_ref:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='evidence-method-read')

@router.get('/research/{research_id}/evidence-method-plans',response_model=EvidenceMethodListResponse,responses={s:{'model':EvidenceMethodErrorResponse} for s in (401,403,404,409,413,422,429,503)})
async def list_evidence_method_plans(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='evidence-method-list')
