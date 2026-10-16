"""Authenticated research persistence, locally opt-in until lifecycle review."""
from __future__ import annotations

import json
import os
import re
import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

if __package__ == "web.backend.api":
    from . import auth
    from ..research.authorization import AccountIdentity
    from ..research.errors import ResearchError
    from ..research.provider_schemas import ProviderFailure
    from ..research.schemas import CreateEnvelope, RevisionEnvelope, StartEnvelope, TaskEnvelope, SourcePreviewEnvelope, SourceApprovalEnvelope, SourceStartEnvelope, ResearchIndexQuery, PaidPreviewEnvelope, PaidConfirmationEnvelope
    from ..research import source_integration
    from ..research import ResearchService, ResearchStore
else:
    from api import auth
    from research.authorization import AccountIdentity
    from research.errors import ResearchError
    from research.provider_schemas import ProviderFailure
    from research.schemas import CreateEnvelope, RevisionEnvelope, StartEnvelope, TaskEnvelope, SourcePreviewEnvelope, SourceApprovalEnvelope, SourceStartEnvelope, ResearchIndexQuery, PaidPreviewEnvelope, PaidConfirmationEnvelope
    from research import source_integration
    from research import ResearchService, ResearchStore

router = APIRouter(tags=["research"])
_KEY = re.compile(r"[A-Za-z0-9._:-]{1,128}\Z", re.ASCII)
_HEADERS = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


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
        return schema.model_validate(body)
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
            result = await run_in_threadpool(service.view, identity, research_id, task_id)
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
            envelope = await _parse(request,{"create":CreateEnvelope,"revise":RevisionEnvelope,"start":StartEnvelope,
                                             'paid-preview':PaidPreviewEnvelope,'paid-confirm':PaidConfirmationEnvelope,
                                             "source-preview":SourcePreviewEnvelope,"source-approve":SourceApprovalEnvelope,"source-start":SourceStartEnvelope,
                                             "cancel":TaskEnvelope,"reconcile":TaskEnvelope,"resume":TaskEnvelope}[operation])
            if operation == "create":
                result = await run_in_threadpool(service.create, identity, envelope.data, key)
            elif operation in ('paid-preview','paid-confirm'):
                # Server composition only. Requests/env booleans cannot install
                # this controlled source; the normal application has none.
                resolver=getattr(request.app.state,'research_paid_resolver',None)
                method=service.paid_preview if operation=='paid-preview' else service.paid_confirm
                result=await run_in_threadpool(method,identity,research_id,envelope.data,key,funding_resolver=resolver)
            elif operation == "revise":
                result = await run_in_threadpool(service.revise, identity, research_id, envelope.data, key)
            elif operation == "start":
                result=await run_in_threadpool(service.start,identity,research_id,envelope.data,key)
            elif operation == "source-preview":
                result=await run_in_threadpool(source_integration.preview,service,identity,research_id,envelope.data)
            elif operation == "source-approve":
                result=await run_in_threadpool(source_integration.approve,service,identity,research_id,envelope.data,key)
            elif operation == "source-start":
                result=await run_in_threadpool(source_integration.start_source,service,identity,research_id,envelope.data,key)
            else:
                result=await run_in_threadpool(service.task_action,identity,research_id,envelope.data,key,operation)
        return JSONResponse(result, headers=_HEADERS)
    except ResearchError as exc:
        return JSONResponse(exc.body(), status_code=exc.status, headers=_HEADERS)
    except ProviderFailure as exc:
        if operation not in ('paid-preview','paid-confirm') or str(exc)!='request_limit':raise
        error=ResearchError('PAYLOAD_LIMIT',413,'最终外发请求超过16KiB上限。')
        return JSONResponse(error.body(),status_code=error.status,headers=_HEADERS)
    except (sqlite3.Error, OSError):
        error = ResearchError("STORE_UNAVAILABLE", 503, "研究存储暂时不可用，请保留当前内容。")
        return JSONResponse(error.body(), status_code=error.status, headers=_HEADERS)


@router.post("/research")
async def create_research(request: Request):
    return await _dispatch(request, operation="create")


@router.get("/research")
async def list_research(request: Request):
    return await _dispatch(request,operation="index")


@router.post("/research/{research_id}/revisions")
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


@router.post('/research/{research_id}/paid-previews')
async def paid_preview(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='paid-preview')


@router.post('/research/{research_id}/paid-approvals')
async def paid_confirmation(research_id:str,request:Request):
    return await _dispatch(request,research_id=research_id,operation='paid-confirm')
