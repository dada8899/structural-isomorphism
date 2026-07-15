"""POST /api/diagnose — 结构诊断（Session #18, feature F）.

输入一段对组织/公司/团队/项目处境的自然语言描述，产品给出一份「结构
诊断」：提出它可能处于哪种候选结构状态（阻尼收敛 / 正反馈失控 / 滞回陷阱 /
级联脆弱 / 自组织临界 等），为什么，不干预会怎样演化，该盯哪个信号，
以及 1-2 条结构性建议。它不预测股价。

普通 JSON 端点（非 SSE）—— LLM 调用 + KB 检索，结构化结果，无需流式。
结构状态是代码里的固定白名单，LLM 只能从中选，输出经 guardrail 校验。
诊断书可附一个内部 KB 候选参照，但检索命中不证明机制相同；检索不可用时
保持为空，诊断照常完成。LLM 不可用时返回 503。
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

from services import llm_client
from services.diagnose_service import (
    SITUATION_MAX_LEN,
    list_states,
    run_diagnosis,
    validate_situation,
)
from services.rate_limit import tier_limit_decorator
from services.input_limits import normalize_research_text
from services.secondary_tool_contracts import (
    CONTRACT_VERSION,
    DiagnoseResponse,
    ensure_request_id,
    internal_screen_evidence,
    secondary_scope_guard,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["diagnose"])


class DiagnoseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    # Bounds mirror diagnose_service.validate_situation — pydantic rejects
    # the obvious abuse early; validate_situation re-checks after .strip().
    situation: StrictStr = Field(..., min_length=1, max_length=SITUATION_MAX_LEN)
    client_request_id: StrictStr | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$",
    )

    @field_validator("situation", mode="before")
    @classmethod
    def canonical_situation(cls, value: str) -> str:
        return normalize_research_text(
            value,
            max_chars=SITUATION_MAX_LEN,
            allow_layout=True,
            field_name="situation",
        )


@router.get("/diagnose/states")
async def diagnose_states():
    """Return the structural-state catalogue (for the frontend's examples)."""
    return {"states": list_states()}


@router.post("/diagnose", response_model=DiagnoseResponse)
@tier_limit_decorator(default_anon="10/minute")
async def diagnose(request: Request, req: DiagnoseRequest):
    """Run a structural diagnosis on one organisation/team situation."""
    # Re-validate after strip — pydantic min_length doesn't strip whitespace.
    try:
        situation = validate_situation(req.situation)
    except ValueError as e:
        raise HTTPException(422, str(e))

    out_of_scope, reason = secondary_scope_guard(situation)
    if out_of_scope:
        raise HTTPException(
            422,
            {
                "error": "out_of_scope",
                "reason": reason,
                "message": "这里只分析组织、团队或项目的结构处境。请补充参与者、反馈和变化过程。",
            },
        )

    # No API key locally / in tests → be honest, don't fake a diagnosis.
    if not llm_client.llm_available():
        raise HTTPException(
            503,
            "结构诊断需要 LLM 服务，当前不可用。请稍后重试。",
        )

    # Best-effort: use KB search for an optional candidate reference only.
    # Missing search leaves the reference null and does not change the screen.
    try:
        from main import app_state

        search_svc = app_state.get("search")
    except Exception:  # noqa: BLE001 — search anchor is optional
        search_svc = None

    result = await run_diagnosis(situation, search_svc=search_svc)
    if result is None:
        # LLM call failed or returned unrecoverable garbage.
        raise HTTPException(
            503,
            "结构诊断未能完成（模型无响应或输出无法解析）。请稍后重试。",
        )

    request_id = ensure_request_id(req.client_request_id)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        "situation": situation,
        **result,
        "evidence": internal_screen_evidence(
            kind="structural_state_hypothesis", label=situation
        ),
    }
    try:
        return DiagnoseResponse.model_validate(payload).model_dump()
    except ValidationError:
        logger.error("structural.diagnose_response_contract_rejected")
        raise HTTPException(503, "诊断结果未通过完整性校验，请重试。") from None


__all__ = ["router"]
