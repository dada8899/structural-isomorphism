"""POST /api/method/apply — A1 方法反查（Session #18）.

引擎的反向用法：用户输入一个方法/算法/模型的描述，引擎找出 KB 里
值得进一步检验的其他领域候选现象。

这是一个普通（非流式）端点——签名抽取 + 一次搜索 + 一次批量标注。
两次可选 LLM 增强受严格总预算约束，超时即返回本地检索结果。
流程见 services/method_search_service.py。

LLM 不可用时优雅降级：仍返回检索候选，只是没有结构签名细化和候选说明。
"""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError, field_validator

_PACKAGE_TOPOLOGY = (__package__ or "").startswith("web.backend.")
if _PACKAGE_TOPOLOGY:
    from ..logging_config import get_logger, new_incident_id
    from ..services.method_search_service import (
        MAX_METHOD_LEN,
        MAX_TOP_N,
        MIN_METHOD_LEN,
        run_method_search,
    )
    from ..services.rate_limit import tier_limit_decorator
    from ..services.input_limits import normalize_research_text
    from ..services.secondary_tool_contracts import (
        CONTRACT_VERSION,
        MethodApplyResponse,
        ensure_request_id,
        internal_screen_evidence,
        secondary_scope_guard,
    )
else:
    from logging_config import get_logger, new_incident_id
    from services.method_search_service import (
        MAX_METHOD_LEN,
        MAX_TOP_N,
        MIN_METHOD_LEN,
        run_method_search,
    )
    from services.rate_limit import tier_limit_decorator
    from services.input_limits import normalize_research_text
    from services.secondary_tool_contracts import (
        CONTRACT_VERSION,
        MethodApplyResponse,
        ensure_request_id,
        internal_screen_evidence,
        secondary_scope_guard,
    )

logger = get_logger("structural.api.method_search")
router = APIRouter(tags=["method"])


class MethodApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    method: StrictStr = Field(
        ...,
        min_length=MIN_METHOD_LEN,
        max_length=MAX_METHOD_LEN,
        description="方法/算法/模型的自然语言描述",
    )
    top_n: int = Field(
        8, ge=1, le=MAX_TOP_N, description="返回多少个待验证候选"
    )
    client_request_id: StrictStr | None = Field(
        default=None,
        min_length=12,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$",
    )

    @field_validator("method", mode="before")
    @classmethod
    def canonical_method(cls, value: str) -> str:
        return normalize_research_text(
            value,
            max_chars=MAX_METHOD_LEN,
            allow_layout=True,
            field_name="method",
        )


@router.post("/method/apply", response_model=MethodApplyResponse)
@tier_limit_decorator(default_anon="15/minute")
async def method_apply(request: Request, req: MethodApplyRequest):
    """抽取方法的结构签名，再在 KB 找值得进一步检验的候选现象。"""
    if _PACKAGE_TOPOLOGY:
        from ..main import app_state
    else:
        from main import app_state

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    method_text = req.method.strip()
    if len(method_text) < MIN_METHOD_LEN:
        # min_length 在 pydantic 已挡空字符串，这里挡纯空白输入。
        raise HTTPException(422, "method 内容过短")

    out_of_scope, reason = secondary_scope_guard(method_text)
    if out_of_scope:
        raise HTTPException(
            422,
            {
                "error": "out_of_scope",
                "reason": reason,
                "message": "这里只检索方法、算法或模型的跨领域候选。请描述方法依赖的机制和前提。",
            },
        )

    try:
        result = await run_method_search(method_text, svc, req.top_n)
    except Exception as exc:  # noqa: BLE001 — optional LLM degrade is inside the service
        incident_id = new_incident_id()
        logger.error(
            "retrieval.method_pipeline_failed",
            error_type=type(exc).__name__,
            incident_id=incident_id,
        )
        raise HTTPException(
            500,
            "Method search failed",
            headers={"X-Incident-ID": incident_id},
        ) from None

    request_id = ensure_request_id(req.client_request_id)
    payload = {
        "contract_version": CONTRACT_VERSION,
        "request_id": request_id,
        **result,
        "evidence": internal_screen_evidence(
            kind="method_transfer_candidate_search", label=method_text
        ),
    }
    try:
        return MethodApplyResponse.model_validate(payload).model_dump()
    except ValidationError:
        incident_id = new_incident_id()
        logger.error(
            "retrieval.method_response_contract_rejected",
            incident_id=incident_id,
        )
        raise HTTPException(
            503,
            "Method candidate response failed validation",
            headers={"X-Incident-ID": incident_id},
        ) from None
