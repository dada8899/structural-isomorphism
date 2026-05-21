"""POST /api/search — 搜索结构相似的现象

Latency note: the LLM "assess + rewrite" call used to run synchronously
before returning results, which added ~5-17s to every search. We now split
it off:

- POST /api/search        → pure vector search, returns in <1s
- POST /api/search/assess → the LLM pre-flight gate, called in parallel
                            by the frontend

The frontend uses Promise.all to fire both at once. Results render as soon
as /api/search returns; the assessment gate overlays later if low-fit.
"""
from collections import Counter
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from services.llm_service import LLMService
from services.rate_limit import tier_limit_decorator
from services.translation import translate_category, translate_kb_items
from services.v2_pairs import get_pairs_for, has_pairs

router = APIRouter(tags=["search"])

_llm: Optional[LLMService] = None


def _get_llm() -> LLMService:
    global _llm
    if _llm is None:
        _llm = LLMService()
    return _llm


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(12, ge=1, le=30)
    ***REMOVED*** Default False: the fast path skips the LLM rewrite/assessment entirely.
    ***REMOVED*** The frontend calls /api/search/assess separately when it wants the gate.
    rewrite: bool = Field(False, description="Use LLM to rewrite query for better matching")
    ***REMOVED*** i18n: "zh" (default, legacy) or "en" — controls output language of the
    ***REMOVED*** optional LLM rewrite/assessment. Vector search itself is language-neutral.
    lang: str = Field("zh", description="Output language for LLM-generated text: 'zh' or 'en'")


class AssessRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
    lang: str = Field("zh", description="Output language for LLM-generated text: 'zh' or 'en'")


class SearchResult(BaseModel):
    id: str
    name: str
    domain: str
    type_id: str
    description: str
    ***REMOVED*** Fused BM25+embedding ranking score, [0, 1]. Use for visual tiering.
    score: float
    ***REMOVED*** Session ***REMOVED***17 V3 — unified relevance口径 in [0, 1]. This is the SAME
    ***REMOVED*** value the /api/analyze scope gate uses, so a result shown here will
    ***REMOVED*** not be self-contradictorily rejected by analyze.
    relevance: float = 0.0
    ***REMOVED*** Session ***REMOVED***17 V2 — True when this candidate's domain differs from the
    ***REMOVED*** query's inferred surface domain (i.e. a genuine cross-domain mapping).
    ***REMOVED*** True is also the default when no surface domain could be inferred.
    cross_domain: bool = True
    ***REMOVED*** The query's inferred surface domain; None when no domain dominates.
    ***REMOVED*** Echoed on every result for frontend grouping convenience.
    surface_domain: Optional[str] = None


class SearchResponse(BaseModel):
    query: str
    count: int
    results: list  ***REMOVED*** list of SearchResult


def _looks_like_question(query: str) -> bool:
    """Heuristic: does this query look like a natural-language question?"""
    if len(query) < 8:
        return False
    ***REMOVED*** Punctuation-based
    if "?" in query or "？" in query:
        return True
    ***REMOVED*** Common Chinese question words
    markers = ["为什么", "怎么", "如何", "什么时候", "哪里", "是不是", "会不会", "能不能"]
    return any(m in query for m in markers)


@router.post("/search")
@tier_limit_decorator(default_anon="30/minute")
async def search_phenomena(request: Request, req: SearchRequest):
    from main import app_state

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    original_query = req.query
    effective_query = original_query
    rewritten = None
    lang_norm = (req.lang or "zh").lower()
    if lang_norm not in ("zh", "en"):
        lang_norm = "zh"

    ***REMOVED*** Session ***REMOVED***17 V3.3 — out-of-scope gate. Previously /api/search had NO
    ***REMOVED*** scope check at all: "今天天气怎么样" still returned 12 candidates.
    ***REMOVED*** /ask and /analyze both gate; search now matches that contract so the
    ***REMOVED*** whole funnel is consistent. Deterministic only (arithmetic / chit-chat
    ***REMOVED*** / trivia) — search has no LLM call on the fast path, and the genuine
    ***REMOVED*** relevance floor is the analyze gate's job.
    from services.scope_guard import is_out_of_scope as _is_oos
    _oos, _oos_reason = _is_oos(original_query)
    if _oos:
        return {
            "query": original_query,
            "rewritten_query": None,
            "count": 0,
            "results": [],
            "out_of_scope": True,
            "scope_reason": _oos_reason,
            "assessment": {
                "worth_score": 0,
                "category": "out_of_scope",
                "coaching": None,
                "rewrite_suggestion": None,
                "pending": False,
            },
            "stats": {"types": [], "domains": [], "top_score": 0},
            "v2_pairs_for_top": [],
        }
    ***REMOVED*** Default assessment is a permissive passthrough so downstream code that
    ***REMOVED*** reads `assessment.worth_score` still sees a valid shape. The `category`
    ***REMOVED*** value stays ZH internally (enum shape) and is translated on output
    ***REMOVED*** when lang=en.
    assessment = {
        "worth_score": 5,
        "category": "现象描述",
        "coaching": None,
        "rewrite_suggestion": None,
        "pending": True,  ***REMOVED*** frontend should still call /search/assess for the real gate
    }

    ***REMOVED*** Optional inline LLM pre-flight (rewrite + worthiness) — opt-in via req.rewrite.
    ***REMOVED*** The default path skips this entirely so /api/search returns in <1s.
    if req.rewrite:
        try:
            llm = _get_llm()
            result = await llm.assess_and_rewrite(original_query, lang=req.lang)
            rewritten_text = result.get("rewritten") or original_query
            if rewritten_text and rewritten_text != original_query:
                rewritten = rewritten_text
                effective_query = rewritten_text
            assessment = {
                "worth_score": result.get("worth_score", 5),
                "category": result.get("category", "现象描述"),
                "coaching": result.get("coaching"),
                "rewrite_suggestion": result.get("rewrite_suggestion"),
                "pending": False,
            }
        except Exception:
            ***REMOVED*** Fail open: if the LLM pre-flight misbehaves, don't block results.
            pass

    results = svc.search(effective_query, top_k=req.top_k)

    ***REMOVED*** When lang=en, translate KB results (name/domain/description). Other
    ***REMOVED*** fields (id/type_id/score) pass through. Domain stats are computed
    ***REMOVED*** AFTER translation so the aggregated domain names are also in EN.
    if lang_norm == "en":
        results = await translate_kb_items(results, lang_norm)

    ***REMOVED*** Aggregate stats for the results page UI
    type_counts = Counter(r["type_id"] for r in results if r.get("type_id"))
    domain_counts = Counter(r["domain"] for r in results if r.get("domain"))

    ***REMOVED*** Phase 2: enrich with v2 cross-domain pairs for the top phenomena.
    ***REMOVED*** Walk the results in order and collect up to 3 phenomena that actually
    ***REMOVED*** have v2-rated cross-domain neighbors. Skip ones without pairs.
    v2_pairs_for_top: list = []
    for r in results:
        if len(v2_pairs_for_top) >= 3:
            break
        rid = r.get("id")
        if not rid or not has_pairs(rid):
            continue
        raw_pairs = get_pairs_for(rid, limit=8)
        trimmed_pairs = [
            {
                "other_id": p.get("other_id"),
                "other_name": p.get("other_name"),
                "other_domain": p.get("other_domain"),
                "score": p.get("score"),
                "similarity": p.get("similarity"),
                "reason": p.get("reason"),
            }
            for p in raw_pairs
        ]
        ***REMOVED*** When lang=en, translate the "other" side of each pair too so the
        ***REMOVED*** UI renders a uniform English block.
        if lang_norm == "en" and trimmed_pairs:
            as_items = [
                {
                    "id": p["other_id"],
                    "name": p.get("other_name") or "",
                    "domain": p.get("other_domain") or "",
                    "description": "",  ***REMOVED*** unused for pair cards
                }
                for p in trimmed_pairs
            ]
            translated = await translate_kb_items(as_items, lang_norm)
            for p, t in zip(trimmed_pairs, translated):
                p["other_name"] = t.get("name") or p["other_name"]
                p["other_domain"] = t.get("domain") or p["other_domain"]

        v2_pairs_for_top.append(
            {
                "phenomenon_id": rid,
                "phenomenon_name": r.get("name"),
                "phenomenon_domain": r.get("domain"),
                "pairs": trimmed_pairs,
            }
        )

    ***REMOVED*** Translate the hard-coded ZH category enum on the way out.
    if lang_norm == "en":
        assessment = dict(assessment)
        assessment["category"] = translate_category(assessment.get("category"))

    ***REMOVED*** Session ***REMOVED***17 V2 — surface-domain summary so the frontend can decide
    ***REMOVED*** whether to recommend a cross-domain source or honestly warn the user
    ***REMOVED*** that every candidate is same-domain ("跨域感≈0" report risk).
    surface_domain = results[0].get("surface_domain") if results else None
    cross_domain_count = sum(1 for r in results if r.get("cross_domain"))

    return {
        "query": original_query,
        "rewritten_query": rewritten,
        "count": len(results),
        "results": results,
        "out_of_scope": False,
        "scope_reason": "ok",
        "assessment": assessment,
        "stats": {
            "types": [{"id": t, "count": c} for t, c in type_counts.most_common(5)],
            "domains": [{"name": d, "count": c} for d, c in domain_counts.most_common(5)],
            "top_score": results[0]["score"] if results else 0,
            ***REMOVED*** V2 cross-domain summary.
            "surface_domain": surface_domain,
            "cross_domain_count": cross_domain_count,
            "same_domain_count": len(results) - cross_domain_count,
        },
        "v2_pairs_for_top": v2_pairs_for_top,
    }


@router.post("/search/assess")
@tier_limit_decorator(default_anon="10/minute")
async def assess_query(request: Request, req: AssessRequest):
    """
    Run the LLM "worthiness + rewrite" pre-flight independently.

    The frontend calls this in parallel with /api/search so it can show
    results immediately and then overlay the coaching gate if the query
    scores below threshold. On any error we fail open (worth_score=5).
    """
    lang_norm = (req.lang or "zh").lower()
    if lang_norm not in ("zh", "en"):
        lang_norm = "zh"
    default_category = "phenomenon description" if lang_norm == "en" else "现象描述"
    fallback = {
        "query": req.query,
        "rewritten": req.query,
        "worth_score": 5,
        "category": default_category,
        "coaching": None,
        "rewrite_suggestion": None,
    }
    try:
        llm = _get_llm()
        result = await llm.assess_and_rewrite(req.query, lang=req.lang)
        category = result.get("category", "现象描述")
        if lang_norm == "en":
            category = translate_category(category)
        return {
            "query": req.query,
            "rewritten": result.get("rewritten") or req.query,
            "worth_score": result.get("worth_score", 5),
            "category": category,
            "coaching": result.get("coaching"),
            "rewrite_suggestion": result.get("rewrite_suggestion"),
        }
    except Exception:
        return fallback
