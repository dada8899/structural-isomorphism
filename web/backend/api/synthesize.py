"""POST /api/synthesize — 基于用户 query + top 搜索结果，生成合成回答

Two endpoints:
- POST /api/synthesize         — blocking, returns full JSON (kept for back-compat)
- POST /api/synthesize/stream  — SSE, streams `text` deltas + final `done` event
"""
import json as _json
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.llm_service import LLMService
from services.rate_limit import tier_limit_decorator

router = APIRouter(tags=["synthesize"])

_llm: Optional[LLMService] = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm


class SynthesizeRequest(BaseModel):
    query: str
    rewritten_query: Optional[str] = None
    results: List[dict]
    # i18n: "zh" (default) or "en". Controls output language of the synthesis.
    lang: str = "zh"


@router.post("/synthesize")
@tier_limit_decorator(default_anon="5/minute")
async def synthesize(request: Request, req: SynthesizeRequest):
    if not req.query or not req.results:
        raise HTTPException(400, "Missing query or results")

    llm = _get_llm()
    result = await llm.synthesize_answer(
        query=req.query,
        rewritten_query=req.rewritten_query,
        top_results=req.results,
        lang=req.lang,
    )
    if not result:
        return {
            "main_insight": None,
            "why_these_matter": None,
            "relevance_snippets": [],
        }
    return result


@router.post("/synthesize/stream")
@tier_limit_decorator(default_anon="5/minute")
async def synthesize_stream(request: Request, req: SynthesizeRequest):
    """Streaming variant. Server-Sent Events with three event types:

    - `text`  → {"content": "<delta>", "total_length": N}
    - `done`  → {"result": {...full parsed JSON...}}
    - `error` → {"message": "..."}
    """
    if not req.query or not req.results:
        raise HTTPException(400, "Missing query or results")

    llm = _get_llm()

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        async for chunk in llm.stream_synthesize_answer(
            query=req.query,
            rewritten_query=req.rewritten_query,
            top_results=req.results,
            lang=req.lang,
        ):
            ctype = chunk.get("type")
            if ctype == "text":
                yield sse("text", {
                    "content": chunk.get("content", ""),
                    "total_length": chunk.get("total_length", 0),
                })
            elif ctype == "done":
                yield sse("done", {"result": chunk.get("result")})
            elif ctype == "error":
                yield sse("error", {"message": chunk.get("message", "unknown")})

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
