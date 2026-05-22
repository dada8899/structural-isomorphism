"""POST /api/diagnose — 结构诊断（Session ***REMOVED***18, feature F）.

输入一段对组织/公司/团队/项目处境的自然语言描述，产品给出一份「结构
诊断」：判定它处于哪种结构状态（阻尼收敛 / 正反馈失控 / 滞回陷阱 /
级联脆弱 / 自组织临界 等），为什么，不干预会怎样演化，该盯哪个信号，
以及 1-2 条结构性建议。它不预测股价。

普通 JSON 端点（非 SSE）—— LLM 调用 + KB 检索，结构化结果，无需流式。
结构状态是代码里的固定白名单，LLM 只能从中选，输出经 guardrail 校验。
诊断书会额外挂一个「同结构的真实参照案例」（来自 KB），让结论有据可依；
检索不可用时优雅降级，诊断照常完成。LLM 不可用时返回 503。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import llm_client
from services.diagnose_service import (
    SITUATION_MAX_LEN,
    list_states,
    run_diagnosis,
    validate_situation,
)
from services.rate_limit import tier_limit_decorator

logger = logging.getLogger(__name__)
router = APIRouter(tags=["diagnose"])


class DiagnoseRequest(BaseModel):
    ***REMOVED*** Bounds mirror diagnose_service.validate_situation — pydantic rejects
    ***REMOVED*** the obvious abuse early; validate_situation re-checks after .strip().
    situation: str = Field(..., min_length=1, max_length=SITUATION_MAX_LEN)


@router.get("/diagnose/states")
async def diagnose_states():
    """Return the structural-state catalogue (for the frontend's examples)."""
    return {"states": list_states()}


@router.post("/diagnose")
@tier_limit_decorator(default_anon="10/minute")
async def diagnose(request: Request, req: DiagnoseRequest):
    """Run a structural diagnosis on one organisation/team situation."""
    ***REMOVED*** Re-validate after strip — pydantic min_length doesn't strip whitespace.
    try:
        situation = validate_situation(req.situation)
    except ValueError as e:
        raise HTTPException(422, str(e))

    ***REMOVED*** No API key locally / in tests → be honest, don't fake a diagnosis.
    if not llm_client.llm_available():
        raise HTTPException(
            503,
            "结构诊断需要 LLM 服务，当前不可用。请稍后重试。",
        )

    ***REMOVED*** Best-effort: hand the KB search service to the diagnosis so it can
    ***REMOVED*** anchor the result to a real same-structure phenomenon. When it is
    ***REMOVED*** missing (not booted / tests) run_diagnosis just skips the lookup.
    try:
        from main import app_state

        search_svc = app_state.get("search")
    except Exception:  ***REMOVED*** noqa: BLE001 — search anchor is optional
        search_svc = None

    result = await run_diagnosis(situation, search_svc=search_svc)
    if result is None:
        ***REMOVED*** LLM call failed or returned unrecoverable garbage.
        raise HTTPException(
            503,
            "结构诊断未能完成（模型无响应或输出无法解析）。请稍后重试。",
        )

    return {"situation": situation, **result}


__all__ = ["router"]
