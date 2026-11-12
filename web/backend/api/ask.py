"""Legacy Ask admission endpoint with generation explicitly retired.

Preserves request normalization, fingerprint binding, limits and caller checks.
Valid generation requests fail with a non-retryable problem before any client,
retrieval or SSE preparation. Pure research helpers remain in their own modules.
"""

if __package__ == "web.backend.api":
    from ..errors import deny_legacy_paid
else:
    from errors import deny_legacy_paid

from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictStr,
    field_validator,
    model_validator,
)

if __package__ == "web.backend.api":
    from ..logging_config import get_logger
else:
    from logging_config import get_logger
# Compatibility re-export retained for existing callers and admission probes.
from services.ask_orchestrator import AskOrchestrator as AskOrchestrator
from services.auth import verify_api_token
from services.llm_service import LLMService
from services.input_limits import MAX_RESEARCH_QUERY_CHARS
from services.rate_limit import tier_limit_decorator
from services.research_fingerprint import ConfirmedResearchFingerprint
from services.input_limits import normalize_research_text

router = APIRouter(tags=["ask"])
log = get_logger("structural.api.ask")


class AskEventStreamResponse(StreamingResponse):
    """Streaming response with an explicit OpenAPI media-type contract."""

    media_type = "text/event-stream"

# W6-D (session #7 P1 backlog): bump query cap from 500 → 8000 chars so
# users can paste full paragraphs / longer context. We keep pydantic
# validation as a structural floor (1..8000 with safe headroom), and add
# an explicit pre-validation check below that returns a structured
# `input_too_long` JSON error with the limit + received counts so the
# frontend can surface a friendly inline message instead of a generic
# 422 from pydantic. See `docs/sessions/SESSION-10-HANDOFF.md` §6 Option D.
MAX_QUERY_CHARS = MAX_RESEARCH_QUERY_CHARS


def _get_llm() -> LLMService:
    """Compatibility hook: never construct a retired client or read its settings."""
    deny_legacy_paid()


class AskRequest(BaseModel):
    """Body for /api/ask/stream.

    `query` remains the normalized research input bound to its optional
    confirmed fingerprint. Validation is retained while generation is retired;
    accepting this request shape does not promise an answer or an SSE stream.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    # Pydantic upper bound is intentionally one above MAX_QUERY_CHARS so
    # that exactly-at-cap requests pass the schema and the structured
    # `input_too_long` handler below owns the boundary check (returns 422
    # with a JSON body the frontend can render specifically).
    query: StrictStr = Field(..., min_length=1, max_length=MAX_QUERY_CHARS + 1)
    lang: Literal["zh", "en"] = Field("zh")
    fingerprint: Optional[ConfirmedResearchFingerprint] = None

    @field_validator("query")
    @classmethod
    def _normalize_query(cls, value: str) -> str:
        return normalize_research_text(
            value,
            max_chars=MAX_QUERY_CHARS + 1,
            field_name="query",
        )

    @model_validator(mode="after")
    def _bind_fingerprint_to_query(self):
        if self.fingerprint is not None and self.fingerprint.source_query != self.query:
            raise ValueError("fingerprint does not match query")
        return self


@router.post("/ask/stream", response_class=AskEventStreamResponse)
@tier_limit_decorator(default_anon="5/minute")
async def ask_stream(request: Request, req: AskRequest):
    """Validate legacy Ask input, then reject retired generation before SSE.

    Existing caller identity, input limits, scope checks and rate limits remain.
    Valid requests receive non-retryable FEATURE_UNAVAILABLE (HTTP 503).
    """
    # W14-D structured log: request received (length only, never the full
    # query body — PII / IP-sensitive content stays out of logs by default).
    log.info("ask.request")

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

    from services.scope_guard import is_out_of_scope
    out_of_scope, reason = is_out_of_scope(req.query)
    if out_of_scope:
        raise HTTPException(422, {"error": "out_of_scope", "reason": reason})
    deny_legacy_paid()
