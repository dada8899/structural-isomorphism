"""POST /api/synthesize — 基于用户 query + top 搜索结果，生成合成回答"""
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from services.llm_service import LLMService
from services.rate_limit import limit as _rl

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
@_rl("10/minute")
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
