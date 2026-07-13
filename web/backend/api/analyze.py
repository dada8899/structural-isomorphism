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


def _parse_fingerprint(raw: Optional[str], expected_query: Optional[str]) -> Optional[dict]:
    """Validate the user-confirmed structure before it enters report storage."""
    if not raw:
        return None
    try:
        value = _json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Invalid fingerprint JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(422, "Fingerprint must be an object")
    allowed = {"source_query", "summary", "variables", "constraints", "unknowns", "revision"}
    if set(value) - allowed:
        raise HTTPException(422, "Fingerprint contains unknown fields")
    source_query = value.get("source_query")
    if expected_query and source_query != expected_query:
        raise HTTPException(422, "Fingerprint does not match this question")
    summary = value.get("summary")
    if not isinstance(summary, str) or not 8 <= len(summary.strip()) <= 1000:
        raise HTTPException(422, "Fingerprint summary must be 8-1000 characters")

    def clean_list(name: str) -> list[str]:
        items = value.get(name, [])
        if not isinstance(items, list) or len(items) > 12:
            raise HTTPException(422, f"Fingerprint {name} must be a list of at most 12 items")
        cleaned = []
        for item in items:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 120:
                raise HTTPException(422, f"Invalid fingerprint {name} item")
            cleaned.append(item.strip())
        return cleaned

    revision = value.get("revision", 1)
    if not isinstance(revision, int) or not 1 <= revision <= 1000:
        raise HTTPException(422, "Invalid fingerprint revision")
    return {
        "summary": summary.strip(),
        "variables": clean_list("variables"),
        "constraints": clean_list("constraints"),
        "unknowns": clean_list("unknowns"),
        "revision": revision,
        "provenance": "user_confirmed",
    }


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
    text_a: Optional[str] = Query(
        None,
        max_length=2000,
        description="User's free-text question. Capped at 2000 chars to "
        "prevent unbounded payload growth in persisted reports.",
    ),
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
    anon_id: Optional[str] = Query(
        None,
        max_length=128,
        description=(
            "Anonymous user id. Used to populate reports.creator_anon_id "
            "when persist=1. Provided as a query param because EventSource "
            "(used by the frontend) can not set custom headers. Falls back "
            "to the X-Anon-Id header for callers using fetch + ReadableStream."
        ),
    ),
    fingerprint: Optional[str] = Query(
        None,
        max_length=4096,
        description="User-confirmed structural fingerprint JSON for query mode.",
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

        idx_kb = svc.idx_by_id.get(b_id)
        if idx_kb is None:
            raise HTTPException(404, "Phenomenon not in KB")
        # Session #17 V3.1/V3.2 — UNIFIED similarity口径. The old code did a
        # raw np.dot of a normalized query embedding against an UN-normalized
        # KB embedding (kb_v2_embeddings.npy has norms ~14-22), producing
        # illegal meta.similarity values (9.5 / 4.76 observed). relevance_score
        # returns a true cosine remapped to [0, 1] — the SAME口径 /api/search
        # now exposes as `result.relevance`, so a result search ranked highly
        # will not be self-contradictorily rejected by the scope gate below.
        similarity = svc.relevance_score(rewritten, b_id)

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
        idx_a = svc.idx_by_id.get(a_id)
        idx_b = svc.idx_by_id.get(b_id)
        if idx_a is None or idx_b is None:
            raise HTTPException(404, "Phenomenon not in KB")
        # V3.1 — same UN-normalized embedding bug applies to pair mode.
        # Use the shared _cosine helper (divides by real norms) and remap
        # to [0, 1] so meta.similarity stays in the same口径 as query mode.
        _cos = svc._cosine(svc._embeddings[idx_a], svc._embeddings[idx_b])
        similarity = round((_cos + 1.0) / 2.0, 4)
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
    # Two sources accepted (EventSource can't set headers): query param
    # `anon_id` wins, then X-Anon-Id header, finally None. Treat empty as
    # None so list_by_anon doesn't bucket every anon-less call together.
    anon_id_raw = (
        (anon_id or "").strip()
        or (request.headers.get("x-anon-id", "").strip())
        or None
    )
    creator_tier = tier if isinstance(tier, str) else None
    confirmed_fingerprint = _parse_fingerprint(fingerprint, user_query)
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
                # V4: stash the credibility block inside the payload under a
                # reserved key so saved/shared reports can render the moat
                # badge too. renderFinalReport ignores non-section keys;
                # _detail_dict lifts it back to a top-level field on read.
                payload={
                    **report,
                    "_credibility": credibility,
                    "_evidence": evidence,
                    **({"_fingerprint": confirmed_fingerprint} if confirmed_fingerprint else {}),
                    "_source": {
                        "id": a.get("id"),
                        "name": a.get("name"),
                        "domain": a.get("domain"),
                        "type_id": a.get("type_id"),
                    },
                },
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

    # Session #17 V4 — credibility block. We audited the KB
    # (data/kb-expanded.jsonl): it carries ONLY id/name/domain/type_id/
    # description — there is NO per-phenomenon universality-class label,
    # SIBD-63 membership flag, or review-score field. We therefore do NOT
    # fabricate a "moat badge". What we CAN honestly surface, post-V3-fix:
    #   * similarity        — now a legal [0,1] relevance value;
    #   * source_domain     — the KB phenomenon's domain (the borrowed-from
    #                         field), and source_type_id;
    #   * has_verified_pairs— whether the SOURCE phenomenon appears in the
    #                         v2 cross-domain pair index (LLM-rated pairs,
    #                         the closest thing to "verified isomorphism").
    #   * verified_pair_count + best_verified_pair (top-rated neighbour).
    # `kb_source` is True so the frontend knows this came from the curated
    # KB, not free-text. No field here is invented.
    from services.v2_pairs import get_pairs_for as _v2_pairs_for
    _src_id = a.get("id") if isinstance(a, dict) else None
    _verified_pairs = _v2_pairs_for(_src_id, limit=1) if _src_id else []
    _all_verified = _v2_pairs_for(_src_id) if _src_id else []
    # B Data Flywheel closure (Session #18) — real human-verification count.
    # Distinct users who marked outcome='worked' on a report targeting THIS
    # b_id. This is NOT a fabricated badge: it comes straight from real
    # report_followup data. 0 is reported honestly as 0. The query is one
    # indexed JOIN; it runs before event_gen so it can't slow the stream,
    # and degrades to {count:0} on any failure (never tears down the SSE).
    from services.verified_isomorphisms import human_verified_for
    _hv = human_verified_for(_report_store, b_id)
    credibility = {
        "kb_source": bool(_src_id and _src_id != "__query__"),
        "similarity": similarity,
        "source_domain": a.get("domain") if isinstance(a, dict) else None,
        "source_type_id": a.get("type_id") if isinstance(a, dict) else None,
        "has_verified_pairs": len(_all_verified) > 0,
        "verified_pair_count": len(_all_verified),
        "best_verified_pair": (
            {
                "other_name": _verified_pairs[0].get("other_name"),
                "other_domain": _verified_pairs[0].get("other_domain"),
                "score": _verified_pairs[0].get("score"),
                "similarity": _verified_pairs[0].get("similarity"),
            }
            if _verified_pairs
            else None
        ),
        # B Data Flywheel closure — real users who confirmed it worked.
        "human_verified_count": int(_hv.get("count", 0) or 0),
        "human_verified_recent": _hv.get("recent", "") or "",
    }
    from services.evidence_envelope import build_evidence_envelope
    if credibility["human_verified_count"] > 0:
        _result_provenance = "USER_RECORDED_OUTCOME"
        _result_summary = (
            f'{credibility["human_verified_count"]} user-recorded worked outcome(s); not an independent mechanism validation.'
            if lang == "en" else
            f'{credibility["human_verified_count"]} 条用户“管用”回填；不是独立机制验证。'
        )
    elif credibility["has_verified_pairs"]:
        _result_provenance = "INTERNAL_AI_SCREEN"
        _result_summary = (
            "Internal model-screened pair record; not an external review."
            if lang == "en" else "内部模型筛选记录；不是外部复核。"
        )
    else:
        _result_provenance = "NOT_TESTED"
        _result_summary = None
    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        candidate_label=a.get("name") if isinstance(a, dict) else None,
        candidate_score=similarity,
        source_kind="internal_kb",
        source_label="Structural KB record",
        result_provenance=_result_provenance,
        result_verdict="INCONCLUSIVE" if _result_provenance != "NOT_TESTED" else "NOT_TESTED",
        result_summary=_result_summary,
        independence_kind="internal" if _result_provenance != "NOT_TESTED" else "not_recorded",
        independence_summary=((
            "Internal pipeline or user outcome record; no external reviewer or independent replication team recorded."
            if lang == "en" else "内部管道或用户结果记录；未记录外部评审者或独立复现团队。"
        ) if _result_provenance != "NOT_TESTED" else None),
        counterexample_status="gap_recorded",
        counterexample_summary=(
            "The report proposes boundaries and falsifiers; no completed falsification result is bound to this candidate."
            if lang == "en" else "报告提出边界与反证方向；尚无完成的证伪结果绑定到该候选。"
        ),
    )

    async def event_gen():
        def sse(event_type: str, data: dict) -> str:
            return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        # Emit meta first so the client can render the pair header
        yield sse("meta", {
            "a": a,
            "b": b,
            "similarity": similarity,
            "is_query_mode": user_query is not None,
            # V4 — honest credibility data (see block above for what's real).
            "credibility": credibility,
            "evidence": evidence,
            "fingerprint": confirmed_fingerprint,
            "model": ask_model,
            "prompt_version": "v1",
        })

        # Launch P1-3 — out-of-scope gate for query mode. The deep-report
        # generator previously had NO scope check: "1+1 等于几" + any b_id
        # produced a full 9-section report (验证型产品硬拗 = 信任崩).
        # Two layers, either trips:
        #   (a) deterministic trivial/chit-chat detector (arithmetic,
        #       greetings, trivia) — catches obvious junk;
        #   (b) relevance floor — the UNIFIED query-vs-KB relevance, in
        #       [0, 1], the SAME口径 /api/search exposes as result.relevance.
        #       0.5 ≈ orthogonal; a genuine cross-domain match lands ~0.65+;
        #       pure noise sits near 0.5. ANALYZE_SCOPE_MIN_SIMILARITY is
        #       env-tunable. NOTE: because the口径 is now shared with search,
        #       this floor MUST stay <= the relevance search shows for a
        #       result, or search and analyze contradict each other (V3.2).
        # Pair mode (two KB phenomena) is in-scope by construction — skip.
        if user_query is not None:
            from services.scope_guard import is_out_of_scope as _is_oos
            oos, oos_reason = _is_oos(user_query)
            # Default 0.50 — i.e. refuse only queries that are at-or-below
            # orthogonal to the chosen KB phenomenon. Old default (0.30) was
            # against a raw, unbounded np.dot and is meaningless now.
            scope_floor = float(
                os.getenv("ANALYZE_SCOPE_MIN_SIMILARITY", "0.50")
            )
            if not oos and similarity < scope_floor:
                oos, oos_reason = True, "low_similarity"
            if oos:
                logger.info(
                    "[analyze] out-of-scope query refused; reason=%s "
                    "similarity=%.3f", oos_reason, similarity,
                )
                yield sse("error", {
                    "message": (
                        "这个问题超出了 Structural 的能力范围。Structural "
                        "做的是跨领域结构迁移——把一个领域里验证过的方法，"
                        "迁移到另一个结构相似的问题上。简单计算、事实查询、"
                        "闲聊这类问题，换用更对口的工具会更合适。"
                    ),
                    "code": "out_of_scope",
                    "scope_reason": oos_reason,
                    "retryable": False,
                })
                yield sse("done", {"report": None, "from_cache": False})
                return

        # Check cache
        cached = _cache.get(cache_key_a, b_id)
        if cached:
            # Emit each section as a separate event so frontend renders uniformly
            for key, value in cached.items():
                yield sse("section", {"key": key, "data": value})
            # M1.4: optional persist even on cache hit — same payload, new
            # share token / row, so the user gets a shareable URL each time
            # they explicitly ask for it. Belt-and-suspenders: re-check
            # quality so a stale cached fallback doesn't get persisted as
            # is_partial=False (Validator session-#16 P2).
            cached_missing = len(EXPECTED_SECTIONS - set(cached.keys())) if cached else 9
            cached_partial = cached_missing >= MAX_MISSING_SECTIONS
            persist_payload = _maybe_persist(cached, is_partial=cached_partial)
            if persist_payload is not None:
                yield sse("persisted", persist_payload)
            yield sse("done", {"report": cached, "from_cache": True})
            return

        # Launch P0-2 — daily LLM budget circuit breaker. The cached path
        # above is free (no LLM call) so it is intentionally NOT charged;
        # only a genuine generation counts. Headers are already sent here,
        # so an over-budget request is surfaced as a terminal SSE `error`
        # event + `done` rather than an HTTP 429.
        from services.cost_ledger import ledger as _cost_ledger
        from errors import BudgetExceeded as _BudgetExceeded
        try:
            _cost_ledger.charge(endpoint="/api/analyze/stream")
        except _BudgetExceeded as be:
            yield sse("error", {
                "message": be.detail,
                "code": "budget_exceeded",
                "retryable": False,
            })
            yield sse("done", {"report": None, "from_cache": False})
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
