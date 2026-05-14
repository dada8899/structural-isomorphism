"""POST /api/ask/stream — Perplexity-like SSE search endpoint.

Wires the AskOrchestrator into FastAPI. Returns a Server-Sent Events
StreamingResponse that emits, in order:

    meta → kb_cards → answer_chunk* → answer_done →
    similar_phenomena → followups → done

Rate-limited to 5 requests/minute per IP (DeepSeek calls cost real $).
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services.ask_orchestrator import AskOrchestrator
from services.auth import verify_api_token
from services.llm_service import LLMService
from services.rate_limit import tier_limit_decorator

router = APIRouter(tags=["ask"])

# Reuse a single LLMService instance so its API key + model env are
# captured once and the underlying http client is shared.
_llm: Optional[LLMService] = None


def _get_llm() -> LLMService:
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm


class AskRequest(BaseModel):
    """Body for /api/ask/stream.

    `query` is the raw user question. We don't pre-rewrite it here — the
    orchestrator emits `meta.rewritten` mirroring the query verbatim, so
    the frontend can show a single "thinking about: <query>" line.
    """

    query: str = Field(..., min_length=1, max_length=500)
    lang: Literal["zh", "en"] = Field("zh")


@router.post("/ask/stream")
@tier_limit_decorator(default_anon="5/minute")
async def ask_stream(request: Request, req: AskRequest):
    """SSE endpoint streaming a Perplexity-style cross-domain answer.

    Auth: optional Bearer token / cookie promotes the caller to free/paid
    tier (looser rate limits). Anonymous traffic still allowed.
    """
    # Tier classification — None means token provided but invalid.
    tier = verify_api_token(request)
    if tier is None:
        raise HTTPException(401, "Invalid API token")

    # Import inside the handler to avoid a circular import at module load.
    # (api.ask is imported in main.py, which itself owns app_state.)
    from main import app_state

    search = app_state.get("search")
    if search is None:
        raise HTTPException(503, "Search service not ready")

    orchestrator = AskOrchestrator(search_service=search, llm=_get_llm())

    return StreamingResponse(
        orchestrator.stream(req.query, lang=req.lang),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Disable nginx buffering so SSE chunks flush immediately.
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
