"""Typed POST mapping endpoints; private text never travels in a URL.

Two endpoints:
- POST /api/mapping      — synchronous, returns cached or full result at once
- POST /api/mapping/stream — SSE stream, for fresh generations
"""
import json as _json
import math
from pathlib import Path
from typing import Literal, Optional
import unicodedata

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

from schemas import CandidateMapping, MappingRequest, MappingResponse, MappingSide
from services.cache import MappingCache
from services.llm_service import LLMService
from services.input_limits import MAX_RESEARCH_QUERY_CHARS
from services.rate_limit import tier_limit_decorator

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

router = APIRouter(tags=["mapping"])
logger = get_logger("structural.mapping")

MAPPING_SCHEMA_VERSION = "candidate-mapping-v2"
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$"

_cache: Optional[MappingCache] = None
_llm: Optional[LLMService] = None


def _init():
    global _cache, _llm
    if _cache is None:
        cache_path = Path(__file__).parent.parent.parent / "data" / "mapping_cache.jsonl"
        _cache = MappingCache(
            cache_path,
            schema_version=MAPPING_SCHEMA_VERSION,
            validator=lambda value: CandidateMapping.model_validate(value).model_dump(mode="json"),
        )
    if _llm is None:
        _llm = LLMService()


def _shape_side(item: dict) -> dict:
    """Whitelist the only KB/query fields that may cross the public API."""
    return MappingSide.model_validate({
        "id": item.get("id"),
        "name": item.get("name"),
        "domain": item.get("domain"),
        "type_id": item.get("type_id"),
        "description": item.get("description"),
        "original_query": item.get("original_query"),
    }).model_dump(mode="json")


def _bounded_similarity(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("retrieval similarity must be numeric")
    result = float(value)
    if not math.isfinite(result) or result < -1.000001 or result > 1.000001:
        raise ValueError("retrieval similarity is outside cosine bounds")
    return max(-1.0, min(1.0, result))


def _bounded_query_text(value: object) -> str:
    """Validate user/rewrite text before embedding or LLM use."""
    if not isinstance(value, str):
        raise ValueError("mapping query must be text")
    text = unicodedata.normalize("NFKC", value).strip()
    if not text or len(text) > MAX_RESEARCH_QUERY_CHARS:
        raise ValueError("mapping query length is invalid")
    for char in text:
        if unicodedata.category(char) in {"Cc", "Cf"} and char not in "\t\n\r":
            raise ValueError("mapping query contains unsafe control text")
    return text


class MappingStreamRequest(BaseModel):
    """Exact-one typed stream input accepted only in a JSON request body."""

    model_config = ConfigDict(extra="forbid", strict=True)

    b_id: StrictStr = Field(
        min_length=1, max_length=120, pattern=_ID_PATTERN
    )
    a_id: Optional[StrictStr] = Field(
        default=None, min_length=1, max_length=120, pattern=_ID_PATTERN
    )
    text_a: Optional[StrictStr] = Field(
        default=None, min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    lang: Literal["zh", "en"] = "zh"

    @field_validator("text_a")
    @classmethod
    def validate_text_a(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else _bounded_query_text(value)

    @model_validator(mode="after")
    def validate_mode(self):
        if (self.a_id is None) == (self.text_a is None):
            raise ValueError("provide exactly one of a_id or text_a")
        if self.a_id == self.b_id:
            raise ValueError("mapping pair must contain two distinct phenomena")
        return self


def _mapping_response(
    *, from_cache: bool, a: dict, b: dict, similarity: float, mapping: object,
) -> dict:
    return MappingResponse.model_validate({
        "schema_version": "mapping-response-v2",
        "from_cache": from_cache,
        "a": a,
        "b": b,
        "retrieval_similarity": similarity,
        "mapping": mapping,
    }).model_dump(mode="json")


@router.post("/mapping", response_model=MappingResponse)
@tier_limit_decorator(default_anon="5/minute")
async def generate_mapping(request: Request, req: MappingRequest):
    from main import app_state

    _init()

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    a = svc.get_by_id(req.a_id)
    b = svc.get_by_id(req.b_id)
    if not a or not b:
        raise HTTPException(404, "Phenomenon not found")

    # Compute similarity from embeddings — O(1) via idx_by_id.
    import numpy as np
    idx_a = svc.idx_by_id.get(req.a_id)
    idx_b = svc.idx_by_id.get(req.b_id)
    if idx_a is None or idx_b is None:
        raise HTTPException(404, "Phenomenon not in KB")
    try:
        similarity = _bounded_similarity(
            float(np.dot(svc._embeddings[idx_a], svc._embeddings[idx_b]))
        )
        a_public = _shape_side(a)
        b_public = _shape_side(b)
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Mapping inputs are invalid") from exc

    cached = _cache.get(req.a_id, req.b_id, lang=req.lang)
    if cached:
        return _mapping_response(
            from_cache=True,
            a=a_public,
            b=b_public,
            similarity=similarity,
            mapping=cached,
        )

    # Generate with LLM
    mapping = await _llm.generate_mapping(a_public, b_public, similarity, lang=req.lang)
    try:
        mapping = CandidateMapping.model_validate(mapping).model_dump(mode="json")
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Mapping output is invalid") from exc

    if mapping["generation_status"] == "generated":
        try:
            _cache.put(req.a_id, req.b_id, mapping, lang=req.lang)
        except OSError as exc:
            logger.error(
                "structural.mapping.cache_write_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )

    return _mapping_response(
        from_cache=False,
        a=a_public,
        b=b_public,
        similarity=similarity,
        mapping=mapping,
    )


@router.get("/mapping/stream", include_in_schema=False)
async def retired_mapping_stream_get():
    """Retire query-string transport without parsing or echoing its values."""
    return JSONResponse(
        status_code=410,
        content={
            "error": "sensitive_get_retired",
            "message": "Use POST /api/mapping/stream with a JSON body.",
        },
        headers={"Cache-Control": "no-store"},
    )


@router.post("/mapping/stream")
@tier_limit_decorator(default_anon="5/minute")
async def stream_mapping(request: Request, req: MappingStreamRequest):
    """
    SSE stream of a mapping generation.

    Two modes:
    1. Pair mode (a_id + b_id): both sides are KB phenomena, result is cached
    2. Query mode (text_a + b_id): KB source is A and the user's problem is B;
       the result is not cached

    Event types:
    - "cache":  {"mapping": {...}}           — immediate cache hit (pair mode only)
    - "meta":   {"a": {...}, "b": {...}, "retrieval_similarity": 0.95}
    - "text":   {"total_length": N}          — non-semantic progress only
    - "done":   {"mapping": {...}}
    - "error":  {"message": "..."}
    """
    from main import app_state

    b_id = req.b_id
    a_id = req.a_id
    text_a = req.text_a
    lang = req.lang

    _init()

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    b = svc.get_by_id(b_id)
    if not b:
        raise HTTPException(404, "Phenomenon B not found")

    if a_id:
        # Pair mode: both sides are real KB phenomena
        a = svc.get_by_id(a_id)
        if not a:
            raise HTTPException(404, "Phenomenon A not found")

        import numpy as np
        idx_a = svc.idx_by_id.get(a_id)
        idx_b = svc.idx_by_id.get(b_id)
        if idx_a is None or idx_b is None:
            raise HTTPException(404, "Phenomenon not in KB")
        try:
            similarity = _bounded_similarity(
                float(np.dot(svc._embeddings[idx_a], svc._embeddings[idx_b]))
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(503, "Mapping similarity is invalid") from exc
        cache_pair = (a_id, b_id)
    elif text_a:
        # Query mode: text_a is user's free-text question
        #
        # Product semantics: the user wants to BORROW methods FROM a known
        # phenomenon (KB) TO solve their own question. So the KB phenomenon
        # is the SOURCE (A, left) and the user's question is the TARGET (B, right).
        # This makes the LLM's "A domain -> B domain" action suggestions point
        # in the correct direction: from known answers to the user's problem.
        from services.llm_service import LLMService
        llm_for_rewrite = _llm or LLMService()

        rewrite_candidate = (
            await llm_for_rewrite.rewrite_query(text_a, lang=lang)
            if _looks_like_question(text_a)
            else text_a
        )
        try:
            rewritten = _bounded_query_text(rewrite_candidate)
        except ValueError:
            logger.warning("structural.mapping.rewrite_invalid")
            rewritten = text_a

        import numpy as np
        query_emb = svc.encode_query(rewritten)
        idx_b_requested = svc.idx_by_id.get(b_id)
        if idx_b_requested is None:
            raise HTTPException(404, "Phenomenon not in KB")
        try:
            similarity = _bounded_similarity(
                float(np.dot(query_emb.flatten(), svc._embeddings[idx_b_requested]))
            )
        except (TypeError, ValueError) as exc:
            raise HTTPException(503, "Mapping similarity is invalid") from exc

        # Swap: KB phenomenon becomes A (source), query becomes B (target)
        kb_phenom = svc.get_by_id(b_id)
        query_phenom = {
            "id": "__query__",
            "name": text_a[:80] + ("..." if len(text_a) > 80 else ""),
            "domain": "Your question" if lang == "en" else "你的问题",
            "type_id": "query",
            "description": rewritten,
            "original_query": text_a,
        }
        a = kb_phenom
        b = query_phenom
        cache_pair = None

    try:
        a_public = _shape_side(a)
        b_public = _shape_side(b)
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Mapping inputs are invalid") from exc

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        # Meta event first — so client can render pair header immediately
        yield sse(
            "meta",
            {
                "schema_version": "mapping-stream-meta-v2",
                "a": a_public,
                "b": b_public,
                "retrieval_similarity": similarity,
            },
        )

        # Check cache only in pair mode
        if cache_pair:
            cached = _cache.get(*cache_pair, lang=lang)
            if cached:
                yield sse("cache", {"mapping": cached})
                yield sse("done", {"mapping": cached, "from_cache": True})
                return

        async for chunk in _llm.stream_mapping(a_public, b_public, similarity, lang=lang):
            ctype = chunk.get("type")
            if ctype == "text":
                total_length = chunk.get("total_length", 0)
                if isinstance(total_length, bool) or not isinstance(total_length, int):
                    total_length = 0
                yield sse("text", {"total_length": max(0, min(total_length, 100_000))})
            elif ctype == "done":
                try:
                    final_mapping = CandidateMapping.model_validate(
                        chunk.get("mapping")
                    ).model_dump(mode="json")
                except (TypeError, ValueError):
                    yield sse("error", {"message": "invalid_mapping_output"})
                    return
                if cache_pair and final_mapping["generation_status"] == "generated":
                    try:
                        _cache.put(*cache_pair, final_mapping, lang=lang)
                    except OSError as exc:
                        logger.error(
                            "structural.mapping.cache_write_failed",
                            error_type=type(exc).__name__,
                            incident_id=new_incident_id(),
                        )
                yield sse("done", {"mapping": final_mapping, "from_cache": False})
                return
            elif ctype == "error":
                message = chunk.get("message")
                if message not in {"upstream_timeout", "upstream_unreachable", "upstream_error"}:
                    message = "upstream_error"
                yield sse("error", {"message": message})
                return

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",  # Nginx: disable buffering
        },
    )


def _looks_like_question(text: str) -> bool:
    if len(text) < 8:
        return False
    if "?" in text or "？" in text:
        return True
    markers = ["为什么", "怎么", "如何", "什么时候", "哪里", "是不是", "会不会", "能不能"]
    return any(m in text for m in markers)
