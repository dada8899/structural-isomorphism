"""POST /api/struct-lint — C2 structural-lint endpoint (Session ***REMOVED***18).

Takes a strategy / plan document and returns its structural claims with
failure modes and risk levels. See services/struct_lint_service.py for
the extraction logic and the LLM-output guardrail.

GET /api/struct-lint/stream is the SSE variant: same pipeline, but it
emits progress events (extract → claims → per-claim isomorph) so the
frontend can show live progress instead of a 36-165s blank wait. The
POST endpoint is kept for backward compatibility.
"""
import json as _json
import logging

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from services import llm_client
from services.struct_lint_service import (
    MAX_DOC_CHARS,
    check_doc_length,
    lint_document,
    lint_document_streamed,
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

    ***REMOVED*** --- KB search service — the structural-isomorphism engine. Optional:
    ***REMOVED*** when it isn't ready, lint_document degrades to a basic lint (every
    ***REMOVED*** claim gets isomorph=None) rather than failing the request. ---
    search_svc = None
    try:
        from main import app_state
        search_svc = app_state.get("search")
    except Exception:
        logger.warning("struct_lint: search service unavailable, degrading")

    result = await lint_document(document, search_svc=search_svc)
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


@router.get("/struct-lint/stream")
async def struct_lint_stream(
    document: str = Query(..., max_length=MAX_DOC_CHARS + 5000),
):
    """SSE variant of /struct-lint — emits progress while the lint runs.

    Events (mirrors api/analyze.py's naming):
      meta     — {"max_doc_chars": N} sent immediately so the client knows
                 the stream is alive (fast first byte).
      progress — {"stage", "message", ...} for each pipeline stage.
      done     — {"result": {"summary", "claims": [...]}} final payload.
      error    — {"error", "message"} terminal failure.

    Validation errors (empty / too-long doc, no LLM key) are surfaced as a
    terminal `error` event rather than an HTTP status, because by the time
    the generator runs the 200 + headers are already sent.
    """

    def sse(event_type: str, data: dict) -> str:
        return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

    async def event_gen():
        doc = document or ""

        ***REMOVED*** meta first — gives the client an instant "stream is alive" signal.
        yield sse("meta", {"max_doc_chars": MAX_DOC_CHARS})

        ***REMOVED*** --- Input validation (same checks as the POST endpoint) ---
        err = check_doc_length(doc)
        if err == "empty_document":
            yield sse("error", {
                "error": "empty_document",
                "message": "请粘贴一段文档内容。",
            })
            return
        if err == "document_too_long":
            yield sse("error", {
                "error": "document_too_long",
                "message": f"文档过长，最多 {MAX_DOC_CHARS} 字符。",
                "limit": MAX_DOC_CHARS,
                "received": len(doc),
            })
            return

        ***REMOVED*** --- LLM availability gate ---
        if not llm_client.llm_available():
            logger.warning("struct_lint_stream: no OPENROUTER_API_KEY configured")
            yield sse("error", {
                "error": "llm_unavailable",
                "message": "结构 lint 暂时不可用（未配置模型服务）。",
            })
            return

        ***REMOVED*** --- Optional KB search service (degrades to basic lint) ---
        search_svc = None
        try:
            from main import app_state
            search_svc = app_state.get("search")
        except Exception:
            logger.warning("struct_lint_stream: search service unavailable, degrading")

        ***REMOVED*** --- Run the streamed pipeline, forwarding each event ---
        try:
            async for ev in lint_document_streamed(doc, search_svc=search_svc):
                etype = ev.get("type")
                if etype == "progress":
                    yield sse("progress", {k: v for k, v in ev.items() if k != "type"})
                elif etype == "done":
                    yield sse("done", {"result": ev.get("result")})
                elif etype == "error":
                    yield sse("error", {
                        "error": "llm_failed",
                        "message": ev.get("message", "结构 lint 生成失败，请稍后重试。"),
                    })
        except Exception:
            logger.exception("struct_lint_stream: pipeline raised")
            yield sse("error", {
                "error": "llm_failed",
                "message": "结构 lint 生成失败，请稍后重试。",
            })

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


__all__ = ["router"]
