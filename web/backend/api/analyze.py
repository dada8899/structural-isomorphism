"""GET /api/analyze/stream — 深度跨学科迁移研究报告（SSE 流式）

支持两种模式：
1. Query mode: text_a (用户的原始问题) + b_id (KB 中的目标现象)
   → 语义：从 KB 借用答案到用户的问题
   → 内部：KB 作为 SOURCE (a)，用户问题作为 TARGET (b)
2. Pair mode: a_id + b_id (两个 KB 现象)
   → 语义：两个已知现象的深度对比
"""
import hashlib
import json as _json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from services.auth import verify_api_token
from services.cache import MappingCache
from services.llm_service import LLMService
from services.rate_limit import tier_limit_decorator
from services.ask_orchestrator import ASK_MODEL  # canonical source of truth
from services.report_store import ReportStore, sign_share_token
from services.translation import translate_kb_item

logger = logging.getLogger(__name__)
router = APIRouter(tags=["analyze"])

_cache: Optional[MappingCache] = None
_llm: Optional[LLMService] = None
_report_store: Optional[ReportStore] = None


def _build_share_url(request: Request, report_id: str, token: str) -> str:
    """Return a full https URL to the share page.

    Honours X-Forwarded-Host / X-Forwarded-Proto so the URL is correct
    behind nginx. Falls back to request.base_url when those are missing
    (local dev / tests).
    """
    fwd_host = request.headers.get("x-forwarded-host")
    fwd_proto = request.headers.get("x-forwarded-proto", "https")
    if fwd_host:
        base = f"{fwd_proto}://{fwd_host.split(',')[0].strip()}"
    else:
        base = str(request.base_url).rstrip("/")
    return f"{base}/report/share/{token}"


def _init():
    global _cache, _llm, _report_store
    if _cache is None:
        cache_path = Path(__file__).parent.parent.parent / "data" / "analysis_cache.jsonl"
        _cache = MappingCache(cache_path)
    if _llm is None:
        _llm = LLMService()
    if _report_store is None:
        # Reuse the existing history.db file so we don't fragment storage.
        # Path matches services/history_db.py initialiser in main.py lifespan.
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _report_store = ReportStore(db_path)


def _looks_like_question(text: str) -> bool:
    if len(text) < 8:
        return False
    if "?" in text or "？" in text:
        return True
    markers = ["为什么", "怎么", "如何", "什么时候", "哪里", "是不是", "会不会", "能不能"]
    return any(m in text for m in markers)


def _query_cache_key(text: str, b_id: str, lang: str = "zh") -> str:
    """For query-mode caching, use a hash of the (query, b_id, lang) tuple.

    Lang is part of the cache key so zh/en reports don't collide.
    """
    normalized = text.strip()
    h = hashlib.md5(f"{normalized}||{b_id}||{lang}".encode("utf-8")).hexdigest()[:16]
    return f"q_{h}"


@router.get("/analyze/stream")
@tier_limit_decorator(default_anon="10/minute")
async def stream_analyze(
    request: Request,
    b_id: str = Query(...),
    a_id: Optional[str] = Query(None),
    text_a: Optional[str] = Query(None),
    lang: str = Query("zh", description="Output language for LLM-generated text: 'zh' or 'en'"),
    persist: int = Query(
        0,
        description=(
            "Session #16 M1.4 — if 1, persist the final report to the "
            "report store and emit a `persisted` SSE event with id + "
            "share_url before `done`. Default 0 keeps existing callers "
            "backward-compatible."
        ),
    ),
):
    # Auth tier classification — None means token was provided but invalid.
    tier = verify_api_token(request)
    if tier is None:
        raise HTTPException(401, "Invalid API token")

    from main import app_state

    _init()

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    # Always fetch the KB phenomenon (used as SOURCE)
    kb_phenom = svc.get_by_id(b_id)
    if not kb_phenom:
        raise HTTPException(404, "Phenomenon not found")

    user_query = None  # original question for query mode

    # Normalize the lang parameter once
    lang = (lang or "zh").lower()
    if lang not in ("zh", "en"):
        lang = "zh"

    if text_a:
        # === Query mode ===
        rewritten = await _llm.rewrite_query(text_a, lang=lang) if _looks_like_question(text_a) else text_a

        import numpy as np
        query_emb = svc.encode_query(rewritten)
        idx_kb = svc.idx_by_id.get(b_id)
        if idx_kb is None:
            raise HTTPException(404, "Phenomenon not in KB")
        similarity = float(np.dot(query_emb.flatten(), svc._embeddings[idx_kb]))

        # SOURCE (a) = KB phenomenon; TARGET (b) = user's question.
        # The synthetic `b.domain` is hardcoded ZH; translate for lang=en.
        a = kb_phenom
        b = {
            "id": "__query__",
            "name": text_a[:60] + ("..." if len(text_a) > 60 else ""),
            "domain": "Your question" if lang == "en" else "你的问题",
            "type_id": "?",
            "description": rewritten,
            "original_query": text_a,
        }
        user_query = text_a
        cache_key_a = _query_cache_key(text_a, b_id, lang=lang)
    elif a_id:
        # === Pair mode ===
        other = svc.get_by_id(a_id)
        if not other:
            raise HTTPException(404, "Phenomenon A not found")
        import numpy as np
        idx_a = svc.idx_by_id.get(a_id)
        idx_b = svc.idx_by_id.get(b_id)
        if idx_a is None or idx_b is None:
            raise HTTPException(404, "Phenomenon not in KB")
        similarity = float(np.dot(svc._embeddings[idx_a], svc._embeddings[idx_b]))
        a = other
        b = kb_phenom
        # Suffix lang onto pair-mode cache key so zh/en don't collide. Legacy
        # zh entries keep their unsuffixed keys, preserving the existing cache.
        cache_key_a = a_id if lang == "zh" else f"{a_id}__en"
    else:
        raise HTTPException(400, "Must provide either a_id or text_a")

    # When lang=en, translate the KB fields in a/b before emitting meta.
    # `b` in query mode is the user's own question (not KB) so we skip it;
    # its fields are either user-written or already produced by the LLM
    # rewrite in the target language.
    if lang == "en":
        a = await translate_kb_item(a, lang) or a
        if user_query is None:
            # Pair mode — b is a KB item too.
            b = await translate_kb_item(b, lang) or b

    # Expected 9 top-level sections in a complete report
    EXPECTED_SECTIONS = {
        "shared_structure",
        "your_problem_breakdown",
        "target_domain_intro",
        "structural_mapping",
        "borrowable_insights",
        "how_to_combine",
        "research_directions",
        "risks_and_limits",
        "action_plan",
    }
    MAX_MISSING_SECTIONS = 4

    # Session #16 M1.4 — capture identity bits for optional persist=1.
    # X-Anon-Id is the same anonymous cookie/localStorage UUID used by
    # services/flags / history; treat empty as None so list_by_anon
    # doesn't bucket every anon-less call together.
    anon_id_raw = request.headers.get("x-anon-id", "").strip() or None
    creator_tier = tier if isinstance(tier, str) else None
    # ASK_MODEL is imported from ask_orchestrator (single source of truth);
    # it already honours the ASK_LLM_MODEL env override.
    ask_model = ASK_MODEL

    def _maybe_persist(report: dict, is_partial: bool) -> Optional[dict]:
        """Persist the report if persist=1 and we have a non-empty payload.

        Returns the SSE payload for the `persisted` event, or None when
        persistence is skipped (persist=0) or fails (logged, not raised).
        We never let a persist failure tear down the SSE stream — the
        report itself is what the user came for.
        """
        if not persist or not report:
            return None
        try:
            out = _report_store.create(
                query=user_query or "",
                rewritten_query=(b.get("description") if user_query else None),
                b_id=b_id,
                lang=lang,
                payload=report,
                model=ask_model,
                prompt_version="v1",
                creator_anon_id=anon_id_raw,
                creator_tier=creator_tier,
                is_partial=is_partial,
            )
            return {
                "id": out["id"],
                "share_token": out["share_token"],
                "share_url": _build_share_url(request, out["id"], out["share_token"]),
                "created_at": out["created_at"],
                "is_partial": is_partial,
            }
        except Exception:
            logger.exception("[analyze] persist failed (persist=1)")
            return None

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        # Emit meta first so the client can render the pair header
        yield sse("meta", {
            "a": a,
            "b": b,
            "similarity": similarity,
            "is_query_mode": user_query is not None,
        })

        # Check cache
        cached = _cache.get(cache_key_a, b_id)
        if cached:
            # Emit each section as a separate event so frontend renders uniformly
            for key, value in cached.items():
                yield sse("section", {"key": key, "data": value})
            # M1.4: optional persist even on cache hit — same payload, new
            # share token / row, so the user gets a shareable URL each time
            # they explicitly ask for it.
            persist_payload = _maybe_persist(cached, is_partial=False)
            if persist_payload is not None:
                yield sse("persisted", persist_payload)
            yield sse("done", {"report": cached, "from_cache": True})
            return

        def _report_quality(report):
            """Return (is_fallback, missing_count) for a final report dict."""
            if not report:
                return True, len(EXPECTED_SECTIONS)
            name_val = report.get("shared_structure", {}).get("name")
            is_fallback = name_val in (
                LLMService.FALLBACK_STRUCTURE_NAME_ZH,
                LLMService.FALLBACK_STRUCTURE_NAME_EN,
            )
            missing = len(EXPECTED_SECTIONS - set(report.keys()))
            return is_fallback, missing

        async def _stream_once():
            """
            Run one pass of LLM stream. This is an async generator that yields
            tuples: ("sse", event_type, data) for progressive events to forward,
            and finally ("result", final_report, pending_error) as the sentinel.
            """
            local_emitted = set()
            local_final = None
            local_err = None
            async for chunk in _llm.stream_deep_analysis(
                a, b, similarity, user_query=user_query, lang=lang
            ):
                ctype = chunk.get("type")
                if ctype == "text":
                    yield ("sse", "text", {
                        "content": chunk.get("content", ""),
                        "total_length": chunk.get("total_length", 0),
                    })
                elif ctype == "section":
                    key = chunk.get("key", "")
                    if key in local_emitted:
                        continue
                    local_emitted.add(key)
                    yield ("sse", "section", {
                        "key": key,
                        "data": chunk.get("data"),
                    })
                elif ctype == "done":
                    local_final = chunk.get("report")
                elif ctype == "error":
                    local_err = chunk.get("message", "unknown error")
            yield ("result", local_final, local_err)

        # ---- First attempt: stream progressively ----
        final_report = None
        first_err = None
        async for item in _stream_once():
            if item[0] == "sse":
                yield sse(item[1], item[2])
            else:
                _, final_report, first_err = item

        is_fallback, missing = _report_quality(final_report)
        needs_retry = (
            final_report is None
            or is_fallback
            or missing >= MAX_MISSING_SECTIONS
        )

        if needs_retry:
            # Inform the client the first pass was incomplete and we'll retry.
            reason_parts = []
            if final_report is None:
                reason_parts.append("final JSON parse failed")
            elif is_fallback:
                reason_parts.append("fallback report returned")
            if missing:
                reason_parts.append(f"{missing} sections missing")
            if first_err:
                reason_parts.append(first_err)
            reason = "; ".join(reason_parts) or "incomplete report"
            yield sse("retry", {"reason": reason})

            # Second attempt — fresh LLM call, bypass cache.
            final_report = None
            second_err = None
            async for item in _stream_once():
                if item[0] == "sse":
                    yield sse(item[1], item[2])
                else:
                    _, final_report, second_err = item

            is_fallback2, missing2 = _report_quality(final_report)
            retry_failed = (
                final_report is None
                or is_fallback2
                or missing2 >= MAX_MISSING_SECTIONS
            )

            if retry_failed:
                err_reason_parts = []
                if final_report is None:
                    err_reason_parts.append("retry: final JSON parse failed")
                elif is_fallback2:
                    err_reason_parts.append("retry: fallback report returned")
                if missing2:
                    err_reason_parts.append(f"retry: {missing2} sections missing")
                if second_err:
                    err_reason_parts.append(second_err)
                err_reason = "; ".join(err_reason_parts) or "retry failed"
                # Preserve backward-compat error shape; only ADD retryable flag.
                yield sse("error", {
                    "message": err_reason,
                    "retryable": False,
                })

        # M1.4: persist BEFORE the `done` event so clients see the
        # share URL alongside the final report in one SSE flush. Treat
        # an incomplete/retried-then-failed report as is_partial=True so
        # the frontend can dim the share button.
        # Validator session #16 P1: also flag is_partial when >= 4 sections
        # missing, not just on fallback-name match (a report with 5/9
        # sections doesn't have the fallback name but is still partial).
        if final_report is None:
            is_partial = True
        else:
            is_fb, missing_count = _report_quality(final_report)
            is_partial = is_fb or missing_count >= MAX_MISSING_SECTIONS
        persist_payload = _maybe_persist(final_report or {}, is_partial=is_partial)
        if persist_payload is not None:
            yield sse("persisted", persist_payload)

        yield sse("done", {"report": final_report, "from_cache": False})

        # Cache successful reports (both first-try and retry-try). Skip the
        # fallback sentinel in either language so we don't poison the cache.
        if final_report and final_report.get("shared_structure", {}).get("name") not in (
            LLMService.FALLBACK_STRUCTURE_NAME_ZH,
            LLMService.FALLBACK_STRUCTURE_NAME_EN,
        ):
            try:
                _cache.put(cache_key_a, b_id, final_report)
            except Exception:
                pass

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
