"""POST /api/struct-lint — C2 structural-lint endpoint (Session ***REMOVED***18).

Takes a strategy / plan document and returns its structural claims with
failure modes and risk levels. See services/struct_lint_service.py for
the extraction logic and the LLM-output guardrail.
"""
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services import llm_client
from services.struct_lint_service import (
    MAX_DOC_CHARS,
    check_doc_length,
    lint_document,
)

logger = logging.getLogger("structural.api.struct_lint")
router = APIRouter(tags=["struct-lint"])


class StructLintRequest(BaseModel):
    """Body for POST /api/struct-lint.

    `document` carries the full plan text. The pydantic max_length is a
    structural floor; check_doc_length() gives a friendlier JSON error
    with the limit + received counts before we ever reach the LLM.
    """

    document: str = Field(..., max_length=MAX_DOC_CHARS + 5000)


@router.post("/struct-lint")
async def struct_lint(req: StructLintRequest):
    """Extract structural claims + failure modes from a document.

    Responses:
      200 — {"summary", "claims": [...]}
      400 — empty or over-long document
      503 — no LLM key configured / LLM call failed
    """
    document = req.document or ""

    ***REMOVED*** --- Input validation (cheap, before any LLM call) ---
    err = check_doc_length(document)
    if err == "empty_document":
        return JSONResponse(
            status_code=400,
            content={"error": "empty_document", "message": "请粘贴一段文档内容。"},
        )
    if err == "document_too_long":
        return JSONResponse(
            status_code=400,
            content={
                "error": "document_too_long",
                "message": f"文档过长，最多 {MAX_DOC_CHARS} 字符。",
                "limit": MAX_DOC_CHARS,
                "received": len(document),
            },
        )

    ***REMOVED*** --- LLM availability gate — fail clean, don't attempt a doomed call ---
    if not llm_client.llm_available():
        logger.warning("struct_lint: no OPENROUTER_API_KEY configured")
        return JSONResponse(
            status_code=503,
            content={
                "error": "llm_unavailable",
                "message": "结构 lint 暂时不可用（未配置模型服务）。",
            },
        )

    result = await lint_document(document)
    if result is None:
        logger.error("struct_lint: lint_document returned no usable result")
        return JSONResponse(
            status_code=503,
            content={
                "error": "llm_failed",
                "message": "结构 lint 生成失败，请稍后重试。",
            },
        )

    return result


__all__ = ["router"]
