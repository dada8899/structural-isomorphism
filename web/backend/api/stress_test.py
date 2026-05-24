"""POST /api/stress-test — 结构压力测试（Session #18, feature E）.

输入一个商业类比 / 战略判断，产品只做证伪：把类比拆成 source/target，
列出隐含的结构对应关系，对每一条做对抗性压力测试，指出最薄弱的一环，
给出 PASS / FAIL / CONDITIONAL 裁决。

普通 JSON 端点（非 SSE）—— 单次 LLM 调用、结构化结果，无需流式。
LLM 不可用时返回 503，不假装能测。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services import llm_client
from services.rate_limit import tier_limit_decorator
from services.stress_test_service import (
    CLAIM_MAX_LEN,
    run_stress_test,
    validate_claim,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stress-test"])


class StressTestRequest(BaseModel):
    # Bounds mirror stress_test_service.validate_claim — pydantic rejects the
    # obvious abuse early; validate_claim re-checks after .strip().
    claim: str = Field(..., min_length=1, max_length=CLAIM_MAX_LEN)


@router.post("/stress-test")
@tier_limit_decorator(default_anon="10/minute")
async def stress_test(request: Request, req: StressTestRequest):
    """Run a structural stress test on one analogy / strategic claim."""
    # Re-validate after strip — pydantic min_length doesn't strip whitespace.
    try:
        claim = validate_claim(req.claim)
    except ValueError as e:
        raise HTTPException(422, str(e))

    # No API key locally / in tests → be honest, don't fake an analysis.
    if not llm_client.llm_available():
        raise HTTPException(
            503,
            "结构压力测试需要 LLM 服务，当前不可用。请稍后重试。",
        )

    # Fetch the live KB search engine so the weakest link can be backed by
    # a real, structurally-isomorphic phenomenon. When it isn't ready the
    # stress test still runs — precedent simply degrades to null.
    try:
        from main import app_state

        search_svc = app_state.get("search")
    except Exception:  # main not importable in some test harnesses
        search_svc = None

    result = await run_stress_test(claim, search_svc)
    if result is None:
        # LLM call failed or returned unrecoverable garbage.
        raise HTTPException(
            503,
            "压力测试未能完成（模型无响应或输出无法解析）。请稍后重试。",
        )

    return {"claim": claim, **result}


__all__ = ["router"]
