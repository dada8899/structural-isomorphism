"""POST /api/ask/stream — Perplexity-like SSE search endpoint.

Wires the AskOrchestrator into FastAPI. Returns a Server-Sent Events
StreamingResponse that emits, in order:

    meta → kb_cards → answer_chunk* → answer_done →
    similar_phenomena → followups → done

Rate-limited to 5 requests/minute per IP (DeepSeek calls cost real $).

W5-A guardrail (2026-05-15): the orchestrator emits an
`out_of_scope: true` flag plus `scope_reason` inside `answer_done` when
the retrieval scores fail the relevance gate (top-1 < 0.75 OR top-3
mean < 0.65). Frontend code should detect this flag and render the
answer with a softer "outside KB coverage" badge instead of the usual
isomorphism framing. See services/ask_orchestrator.py
`_evaluate_relevance` for thresholds and env knobs.
"""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from services.ask_orchestrator import AskOrchestrator
from services.auth import verify_api_token
from services.llm_service import LLMService
from services.rate_limit import tier_limit_decorator

router = APIRouter(tags=["ask"])

# W6-D (session #7 P1 backlog): bump query cap from 500 → 8000 chars so
# users can paste full paragraphs / longer context. We keep pydantic
# validation as a structural floor (1..8000 with safe headroom), and add
# an explicit pre-validation check below that returns a structured
# `input_too_long` JSON error with the limit + received counts so the
# frontend can surface a friendly inline message instead of a generic
# 422 from pydantic. See `docs/sessions/SESSION-10-HANDOFF.md` §6 Option D.
MAX_QUERY_CHARS = 8000

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

    # Pydantic upper bound is intentionally one above MAX_QUERY_CHARS so
    # that exactly-at-cap requests pass the schema and the structured
    # `input_too_long` handler below owns the boundary check (returns 422
    # with a JSON body the frontend can render specifically).
    query: str = Field(..., min_length=1, max_length=MAX_QUERY_CHARS + 1)
    lang: Literal["zh", "en"] = Field("zh")


@router.post("/ask/stream")
@tier_limit_decorator(default_anon="5/minute")
async def ask_stream(request: Request, req: AskRequest):
    """SSE endpoint streaming a Perplexity-style cross-domain answer.

    Auth: optional Bearer token / cookie promotes the caller to free/paid
    tier (looser rate limits). Anonymous traffic still allowed.
    """
    # W6-D structured 8000-char cap: surface a JSON-shaped error the
    # frontend can recognize (vs an opaque pydantic 422 string).
    if len(req.query) > MAX_QUERY_CHARS:
        return JSONResponse(
            status_code=422,
            content={
                "error": "input_too_long",
                "limit": MAX_QUERY_CHARS,
                "received": len(req.query),
                "message": (
                    f"Input limit {MAX_QUERY_CHARS} chars — try focusing "
                    "your question or splitting into two queries."
                ),
            },
        )

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
