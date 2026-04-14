"""POST /api/mapping — 生成两个现象之间的结构映射（LLM）

Two endpoints:
- POST /api/mapping      — synchronous, returns cached or full result at once
- GET  /api/mapping/stream — SSE stream, for fresh generations
"""
import json as _json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.cache import MappingCache
from services.llm_service import LLMService
from services.rate_limit import limit as _rl

router = APIRouter(tags=["mapping"])

_cache: Optional[MappingCache] = None
_llm: Optional[LLMService] = None


def _init():
    global _cache, _llm
    if _cache is None:
        cache_path = Path(__file__).parent.parent.parent / "data" / "mapping_cache.jsonl"
        _cache = MappingCache(cache_path)
    if _llm is None:
        _llm = LLMService()


class MappingRequest(BaseModel):
    a_id: str
    b_id: str


@router.post("/mapping")
@_rl("10/minute")
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

    # Check cache first
    cached = _cache.get(req.a_id, req.b_id)
    if cached:
        return {
            "from_cache": True,
            "a": a,
            "b": b,
            "mapping": cached,
        }

    # Compute similarity from embeddings — O(1) via idx_by_id.
    import numpy as np
    idx_a = svc.idx_by_id.get(req.a_id)
    idx_b = svc.idx_by_id.get(req.b_id)
    if idx_a is None or idx_b is None:
        raise HTTPException(404, "Phenomenon not in KB")
    similarity = float(np.dot(svc._embeddings[idx_a], svc._embeddings[idx_b]))

    # Generate with LLM
    mapping = await _llm.generate_mapping(a, b, similarity)

    # Save to cache if successful
    if mapping and mapping.get("structure_name") != "结构分析暂不可用":
        _cache.put(req.a_id, req.b_id, mapping)

    return {
        "from_cache": False,
        "a": a,
        "b": b,
        "similarity": similarity,
        "mapping": mapping,
    }


@router.get("/mapping/stream")
async def stream_mapping(
    b_id: str = Query(...),
    a_id: Optional[str] = Query(None, description="KB phenomenon id for A side"),
    text_a: Optional[str] = Query(None, description="Free-text query as A side (for 'from search' flow)"),
):
    """
    SSE stream of a mapping generation.

    Two modes:
    1. Pair mode (a_id + b_id): both sides are KB phenomena, result is cached
    2. Query mode (text_a + b_id): A is user's free-text query, no cache

    Event types:
    - "cache":  {"mapping": {...}}           — immediate cache hit (pair mode only)
    - "meta":   {"a": {...}, "b": {...}, "similarity": 0.95}
    - "text":   {"content": "...", "total_length": N}
    - "done":   {"mapping": {...}}
    - "error":  {"message": "..."}
    """
    from main import app_state

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
        similarity = float(np.dot(svc._embeddings[idx_a], svc._embeddings[idx_b]))
        cache_key_a = a_id
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

        rewritten = await llm_for_rewrite.rewrite_query(text_a) if _looks_like_question(text_a) else text_a

        import numpy as np
        query_emb = svc.encode_query(rewritten)
        idx_b_requested = svc.idx_by_id.get(b_id)
        if idx_b_requested is None:
            raise HTTPException(404, "Phenomenon not in KB")
        similarity = float(np.dot(query_emb.flatten(), svc._embeddings[idx_b_requested]))

        # Swap: KB phenomenon becomes A (source), query becomes B (target)
        kb_phenom = svc.get_by_id(b_id)
        query_phenom = {
            "id": "__query__",
            "name": text_a[:40] + ("..." if len(text_a) > 40 else ""),
            "domain": "你的问题",
            "type_id": "?",
            "description": rewritten,
            "original_query": text_a,
        }
        a = kb_phenom
        b = query_phenom
        cache_key_a = None  # no caching for free-text queries
    else:
        raise HTTPException(400, "Must provide either a_id or text_a")

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        # Meta event first — so client can render pair header immediately
        yield sse("meta", {"a": a, "b": b, "similarity": similarity})

        # Check cache only in pair mode
        if cache_key_a:
            cached = _cache.get(cache_key_a, b_id)
            if cached:
                yield sse("cache", {"mapping": cached})
                yield sse("done", {"mapping": cached, "from_cache": True})
                return

        # Stream LLM generation
        final_mapping = None
        async for chunk in _llm.stream_mapping(a, b, similarity):
            ctype = chunk.get("type")
            if ctype == "text":
                yield sse("text", {
                    "content": chunk.get("content", ""),
                    "total_length": chunk.get("total_length", 0),
                })
            elif ctype == "done":
                final_mapping = chunk.get("mapping")
                yield sse("done", {"mapping": final_mapping, "from_cache": False})
            elif ctype == "error":
                yield sse("error", {"message": chunk.get("message", "unknown error")})

        # Cache only in pair mode
        if cache_key_a and final_mapping and final_mapping.get("structure_name") != "结构分析暂不可用":
            _cache.put(cache_key_a, b_id, final_mapping)

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
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
