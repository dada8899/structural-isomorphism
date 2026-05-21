"""POST /api/method/apply — A1 方法反查（Session ***REMOVED***18）.

引擎的反向用法：用户输入一个方法/算法/模型的描述，引擎找出 KB 里
"结构上能套用这个方法"的其他领域现象。

这是一个普通（非流式）端点——签名抽取 + 一次搜索 + 一次批量标注，
延迟可接受。流程见 services/method_search_service.py。

LLM 不可用时优雅降级：仍返回搜索结果，只是没有结构签名细化和套用说明。
"""
import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.method_search_service import (
    MAX_METHOD_LEN,
    MAX_TOP_N,
    MIN_METHOD_LEN,
    run_method_search,
)
from services.rate_limit import tier_limit_decorator

logger = logging.getLogger("structural.api.method_search")
router = APIRouter(tags=["method"])


class MethodApplyRequest(BaseModel):
    method: str = Field(
        ...,
        min_length=MIN_METHOD_LEN,
        max_length=MAX_METHOD_LEN,
        description="方法/算法/模型的自然语言描述",
    )
    top_n: int = Field(
        8, ge=1, le=MAX_TOP_N, description="返回多少个可套用现象"
    )


@router.post("/method/apply")
@tier_limit_decorator(default_anon="15/minute")
async def method_apply(request: Request, req: MethodApplyRequest):
    """抽取方法的结构签名，再在 KB 找结构上能套用它的现象。"""
    from main import app_state

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    method_text = req.method.strip()
    if len(method_text) < MIN_METHOD_LEN:
        ***REMOVED*** min_length 在 pydantic 已挡空字符串，这里挡纯空白输入。
        raise HTTPException(422, "method 内容过短")

    try:
        result = await run_method_search(method_text, svc, req.top_n)
    except Exception:  ***REMOVED*** noqa: BLE001 — LLM degrade is inside the service;
        ***REMOVED*** this only catches a search-layer failure. Surface as 500, log it.
        logger.exception("[method/apply] pipeline failed")
        raise HTTPException(500, "Method search failed")

    return result
