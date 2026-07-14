"""POST /api/synthesize — 基于用户 query + top 搜索结果，生成合成回答

Two endpoints:
- POST /api/synthesize         — blocking, returns full JSON (kept for back-compat)
- POST /api/synthesize/stream  — SSE, streams `text` deltas + final `done` event
"""
import json as _json
from typing import Any, List, Literal, Mapping, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from services.input_limits import MAX_RESEARCH_QUERY_CHARS, normalize_research_text
from services.llm_service import LLMService
from services.search_synthesis import MAX_REWRITTEN_QUERY_CHARS
from services.rate_limit import tier_limit_decorator

router = APIRouter(tags=["synthesize"])

_llm: Optional[LLMService] = None


def _get_llm():
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm


class SynthesizeCandidateRef(BaseModel):
    """One client-selected reference; canonical content is always reloaded."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(
        ..., min_length=1, max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    )


class SynthesizeRequest(BaseModel):
    """Bounded request envelope for one allowlisted Top-5 comparison."""

    model_config = ConfigDict(extra="forbid", strict=True)

    query: str = Field(..., min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    rewritten_query: Optional[str] = Field(
        default=None, min_length=1, max_length=MAX_REWRITTEN_QUERY_CHARS,
    )
    results: List[SynthesizeCandidateRef] = Field(..., min_length=1, max_length=5)
    # i18n: "zh" (default) or "en". Controls output language of the synthesis.
    lang: Literal["zh", "en"] = "zh"

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: Any) -> str:
        return normalize_research_text(
            value,
            max_chars=MAX_RESEARCH_QUERY_CHARS,
            allow_layout=True,
            field_name="query",
        )

    @field_validator("rewritten_query", mode="before")
    @classmethod
    def normalize_rewrite(cls, value: Any) -> Optional[str]:
        if value is None:
            return None
        return normalize_research_text(
            value,
            max_chars=MAX_REWRITTEN_QUERY_CHARS,
            allow_layout=True,
            field_name="rewritten_query",
        )

    @model_validator(mode="after")
    def unique_candidate_ids(self) -> "SynthesizeRequest":
        ids = [candidate.id for candidate in self.results]
        if len(ids) != len(set(ids)):
            raise ValueError("candidate ids must be unique")
        return self


_PROMPT_KB_FIELDS = ("id", "name", "domain", "type_id", "description")


def _requested_id(item: object) -> Optional[str]:
    if isinstance(item, SynthesizeCandidateRef):
        return item.id
    if isinstance(item, Mapping):
        value = item.get("id")
        return value if isinstance(value, str) else None
    return None


def _canonical_top_results(requested: List[object], effective_query: str) -> List[dict]:
    """Resolve client references back to canonical KB records.

    The browser can request IDs, but it cannot provide model prompt text,
    invent a source, or reorder the server result. We recompute Top-5 for the
    effective query, intersect it with requested IDs, then reload KB content.
    """
    from main import app_state

    service = app_state.get("search")
    if (
        service is None
        or not callable(getattr(service, "get_by_id", None))
        or not callable(getattr(service, "search", None))
    ):
        raise HTTPException(503, "Search service not ready")
    requested_ids = {kb_id for item in (requested or []) if (kb_id := _requested_id(item))}
    try:
        server_top = service.search(effective_query, top_k=5)
    except Exception as exc:
        raise HTTPException(503, "Search service not ready") from exc
    canonical: List[dict] = []
    seen: set[str] = set()
    for item in server_top or []:
        kb_id = item.get("id") if isinstance(item, dict) else None
        if (
            not isinstance(kb_id, str)
            or not kb_id
            or kb_id in seen
            or kb_id not in requested_ids
        ):
            continue
        record = service.get_by_id(kb_id)
        if not isinstance(record, dict) or record.get("id") != kb_id:
            continue
        canonical.append({field: record.get(field, "") for field in _PROMPT_KB_FIELDS})
        seen.add(kb_id)
    if not canonical:
        raise HTTPException(400, "No valid KB candidates")
    return canonical


@router.post("/synthesize")
@tier_limit_decorator(default_anon="5/minute")
async def synthesize(request: Request, req: SynthesizeRequest):
    if not req.query or not req.results:
        raise HTTPException(400, "Missing query or results")

    top_results = _canonical_top_results(
        req.results, req.rewritten_query or req.query,
    )
    llm = _get_llm()
    result = await llm.synthesize_answer(
        query=req.query,
        rewritten_query=req.rewritten_query,
        top_results=top_results,
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

    - `text`  → {"content": "", "total_length": N} (non-semantic progress)
    - `done`  → {"result": {...full parsed JSON...}}
    - `error` → {"message": "..."}
    """
    if not req.query or not req.results:
        raise HTTPException(400, "Missing query or results")

    top_results = _canonical_top_results(
        req.results, req.rewritten_query or req.query,
    )
    llm = _get_llm()

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        async for chunk in llm.stream_synthesize_answer(
            query=req.query,
            rewritten_query=req.rewritten_query,
            top_results=top_results,
            lang=req.lang,
        ):
            ctype = chunk.get("type")
            if ctype == "text":
                yield sse("text", {
                    # Defense in depth: even a regressed provider adapter
                    # cannot forward unvalidated semantic deltas.
                    "content": "",
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
