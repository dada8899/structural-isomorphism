"""POST /api/stress-test — 结构压力测试（Session #18, feature E）.

输入一个商业类比 / 战略判断，产品只做证伪：把类比拆成 source/target，
列出隐含的结构对应关系，对每一条做对抗性压力测试，指出最薄弱的一环。
公开结果只描述本轮内部筛查是否发现断点，不把模型裁决当作现实证据。

普通 JSON 端点（非 SSE）—— 单次 LLM 调用、结构化结果，无需流式。
LLM 不可用时返回 503，不假装能测。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from services import llm_client
from services.rate_limit import tier_limit_decorator
from services.input_limits import normalize_research_text
from services.secondary_tool_contracts import (
    CONTRACT_VERSION,
    StressTestResponse,
    ensure_request_id,
    internal_screen_evidence,
    secondary_scope_guard,
)
from services.stress_test_service import (
    CLAIM_MAX_LEN,
    run_stress_test,
    validate_claim,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["stress-test"])


class StressTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Bounds mirror stress_test_service.validate_claim — pydantic rejects the
    # obvious abuse early; validate_claim re-checks after .strip().
    claim: StrictStr = Field(..., min_length=1, max_length=CLAIM_MAX_LEN)
    client_request_id: StrictStr | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$",
    )

    @field_validator("claim", mode="before")
    @classmethod
    def canonical_claim(cls, value: str) -> str:
        return normalize_research_text(
            value,
            max_chars=CLAIM_MAX_LEN,
            allow_layout=True,
            field_name="claim",
        )


@router.post("/stress-test", response_model=StressTestResponse)
@tier_limit_decorator(default_anon="10/minute")
async def stress_test(request: Request, req: StressTestRequest):
    """Run a structural stress test on one analogy / strategic claim."""
    # Re-validate after strip — pydantic min_length doesn't strip whitespace.
    try:
        claim = validate_claim(req.claim)
    except ValueError as e:
        raise HTTPException(422, str(e))

    out_of_scope, reason = secondary_scope_guard(claim)
    if out_of_scope:
        raise HTTPException(
            422,
            {
                "error": "out_of_scope",
                "reason": reason,
                "message": "这里只测试完整的结构类比或战略判断。请补充要比较的两个对象和机制。",
            },
        )

    # No API key locally / in tests → be honest, don't fake an analysis.
    if not llm_client.llm_available():
        raise HTTPException(
            503,
            "结构压力测试需要 LLM 服务，当前不可用。请稍后重试。",
        )

    # Fetch the live KB search engine for an optional candidate reference.
    # Retrieval is not validation; an unavailable search leaves it null.
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

    request_id = ensure_request_id(req.client_request_id)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "claim": claim,
        **result,
        "evidence": internal_screen_evidence(kind="analogy_red_team_screen", label=claim),
    }
    try:
        return StressTestResponse.model_validate(payload).model_dump()
    except ValidationError:
        logger.error("structural.stress_test.response_contract_rejected")
        raise HTTPException(503, "压力测试结果未通过完整性校验，请重试。") from None


__all__ = ["router"]
