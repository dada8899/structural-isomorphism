"""GET /api/report/* — read persisted analyze reports (M1.4).

POST /api/report/{id}/feedback — section-level 👍/👎.

PRD: docs/sessions/M1.4-report-generator-prd.md
Companion: services/report_store.py
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field, ValidationError

from services.report_store import ReportStore, verify_share_token

logger = logging.getLogger(__name__)
router = APIRouter(tags=["report"])

_store: Optional[ReportStore] = None


def _get_store() -> ReportStore:
    global _store
    if _store is None:
        ***REMOVED*** Reuse history.db (same file as analyze.py / history_db.py).
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ReportStore(db_path)
    return _store


***REMOVED*** ---------------- response shapes ----------------------------------- ***REMOVED***


class ReportDetailResponse(BaseModel):
    id: str
    query: str
    rewritten_query: Optional[str]
    b_id: str
    lang: str
    payload: dict
    model: str
    prompt_version: str
    created_at: str
    view_count: int
    is_partial: bool
    credibility: Optional[dict] = None


class ReportListItem(BaseModel):
    id: str
    query: str
    b_id: str
    lang: str
    created_at: str
    view_count: int
    ***REMOVED*** B Data Flywheel (Session ***REMOVED***18) — revisit status for the '未回访' badge.
    has_followup: bool = False
    followup_outcome: str = ""


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    has_more: bool


class FeedbackRequest(BaseModel):
    section: Optional[str] = Field(
        None,
        description=(
            "Which 9-section key the vote applies to. None / omitted "
            "= overall vote on the report."
        ),
    )
    vote: int = Field(..., description="+1 (up) or -1 (down)")
    note: Optional[str] = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    ok: bool
    total_up: int
    total_down: int


***REMOVED*** Session ***REMOVED***17 V6 — report → action → result revisit loop.
_ALLOWED_ACTION_STATUSES = {"planned", "in_progress", "tried", "abandoned"}
_ALLOWED_OUTCOMES = {"", "worked", "partial", "no_effect", "too_early"}


class FollowupRequest(BaseModel):
    action_status: str = Field(
        ...,
        description=(
            "Where the user is with the report's action plan: "
            "planned | in_progress | tried | abandoned"
        ),
    )
    outcome: str = Field(
        "",
        description=(
            "Result so far (optional): '' (not reported) | worked | "
            "partial | no_effect | too_early"
        ),
    )
    note: Optional[str] = Field(None, max_length=2000)


class FollowupResponse(BaseModel):
    ok: bool
    report_id: str
    action_status: str
    outcome: str
    note: Optional[str]
    created_at: str
    updated_at: str


_ALLOWED_SECTIONS = {
    None,
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


***REMOVED*** ---------------- endpoints ----------------------------------------- ***REMOVED***


def _detail_dict(r: dict) -> dict:
    """Project a store row to the public detail shape (drops share_token)."""
    payload = r["payload"]
    ***REMOVED*** V4: credibility was persisted inside the payload under a reserved key
    ***REMOVED*** (see analyze.py _maybe_persist) — lift it to a top-level field and
    ***REMOVED*** hand back a section-only payload. Older reports lack it → None.
    credibility = None
    if isinstance(payload, dict) and "_credibility" in payload:
        payload = dict(payload)
        credibility = payload.pop("_credibility", None)
    return {
        "id": r["id"],
        "query": r["query"],
        "rewritten_query": r.get("rewritten_query"),
        "b_id": r["b_id"],
        "lang": r["lang"],
        "payload": payload,
        "model": r["model"],
        "prompt_version": r["prompt_version"],
        "created_at": r["created_at"],
        "view_count": r.get("view_count", 0),
        "is_partial": r.get("is_partial", False),
        "credibility": credibility,
    }


@router.get(
    "/report/share/{token}",
    response_model=ReportDetailResponse,
    summary="Read a report by share token (no auth required)",
)
async def get_report_by_share(token: str):
    """Public read via HMAC-signed share token.

    The token alone is the capability — no anon-id / cookie check. Anyone
    holding the token can read. v1 acceptable; v1.1 may add revoke.
    """
    if not token or len(token) != 32:
        raise HTTPException(404, "Report not found")
    store = _get_store()
    r = store.get_by_share_token(token)
    if r is None:
        raise HTTPException(404, "Report not found")
    ***REMOVED*** Constant-time check that the token actually signs this row (defence
    ***REMOVED*** against a future schema change that lets non-HMAC tokens slip in).
    if not verify_share_token(r["id"], token):
        ***REMOVED*** Token DB row exists but HMAC doesn't verify — config drift.
        logger.warning("share token verify mismatch for report %s", r["id"])
        raise HTTPException(404, "Report not found")
    store.record_view(r["id"])
    return _detail_dict(r)


@router.get(
    "/report/{report_id}",
    response_model=ReportDetailResponse,
    summary="Read a report by id (owner check via X-Anon-Id)",
)
async def get_report_by_id(
    report_id: str,
    x_anon_id: Optional[str] = Header(None),
):
    """Read by id. Soft owner check: if the row has a creator_anon_id and
    the request lacks the matching X-Anon-Id, return 404 (NOT 403, so we
    don't leak existence). Anyone with the share_token should use the
    /share/{token} endpoint instead.
    """
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    owner = r.get("creator_anon_id")
    if owner and owner != (x_anon_id or ""):
        ***REMOVED*** Hide existence rather than leak via 403.
        raise HTTPException(404, "Report not found")
    store.record_view(report_id)
    return _detail_dict(r)


@router.get(
    "/reports/mine",
    response_model=ReportListResponse,
    summary="List recent reports by the current anon-id",
)
async def list_my_reports(
    x_anon_id: Optional[str] = Header(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if not x_anon_id:
        ***REMOVED*** No anon-id ≈ no history. Return empty rather than 401 so
        ***REMOVED*** frontend can render "no reports yet" cleanly.
        return {"items": [], "has_more": False}
    store = _get_store()
    items = store.list_by_anon(x_anon_id, limit=limit + 1, offset=offset)
    has_more = len(items) > limit
    items = items[:limit]
    return {
        "items": [
            {
                "id": it["id"],
                "query": it["query"],
                "b_id": it["b_id"],
                "lang": it["lang"],
                "created_at": it["created_at"],
                "view_count": it.get("view_count", 0),
                "has_followup": bool(it.get("has_followup", False)),
                "followup_outcome": it.get("followup_outcome", "") or "",
            }
            for it in items
        ],
        "has_more": has_more,
    }


@router.post(
    "/report/{report_id}/feedback",
    response_model=FeedbackResponse,
    summary="Submit section-level 👍/👎 feedback",
)
async def submit_feedback(
    report_id: str,
    body: FeedbackRequest,
    x_anon_id: Optional[str] = Header(None),
):
    """Section-level feedback. Idempotent on (report_id, voter_anon, section):
    re-voting on the same section overwrites the previous vote rather
    than double-counting.

    Voter identity is x-anon-id; if missing we still record the row but
    every anonymous vote collapses to the same bucket (acceptable for v1
    — anti-spam is the rate-limiter's job).
    """
    if body.section not in _ALLOWED_SECTIONS:
        raise HTTPException(400, f"Unknown section: {body.section!r}")
    if body.vote not in (-1, 1):
        raise HTTPException(400, "vote must be -1 or +1")
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    try:
        counts = store.record_feedback(
            report_id=report_id,
            section=body.section,
            vote=body.vote,
            voter_anon=x_anon_id or "anon",
            note=body.note,
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, **counts}


@router.post(
    "/report/{report_id}/followup",
    response_model=FollowupResponse,
    summary="Record a report → action → result revisit (Session ***REMOVED***17 V6)",
)
async def submit_followup(
    report_id: str,
    body: FollowupRequest,
    x_anon_id: Optional[str] = Header(None),
):
    """Record the user coming back to report '我试过了 / 结果如何'.

    Idempotent upsert on (report_id, anon_id) — re-submitting overwrites
    the previous followup (latest wins) rather than piling up rows.
    Identity is X-Anon-Id; missing anon-id collapses to the 'anon' bucket
    (acceptable for v1, same model as feedback).
    """
    if body.action_status not in _ALLOWED_ACTION_STATUSES:
        raise HTTPException(
            400, f"Unknown action_status: {body.action_status!r}"
        )
    if (body.outcome or "") not in _ALLOWED_OUTCOMES:
        raise HTTPException(400, f"Unknown outcome: {body.outcome!r}")
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    try:
        fu = store.record_followup(
            report_id=report_id,
            anon_id=x_anon_id,
            action_status=body.action_status,
            outcome=body.outcome or "",
            note=body.note,
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(400, str(e)) from e
    return {
        "ok": True,
        "report_id": fu["report_id"],
        "action_status": fu["action_status"],
        "outcome": fu["outcome"],
        "note": fu.get("note"),
        "created_at": fu["created_at"],
        "updated_at": fu["updated_at"],
    }


@router.get(
    "/report/{report_id}/followup",
    summary="Read the current anon's followup for a report (Session ***REMOVED***17 V6)",
)
async def get_followup(
    report_id: str,
    x_anon_id: Optional[str] = Header(None),
):
    """Return this anon-id's followup for the report.

    Returns {followup: null} when none recorded — lets the frontend render
    the empty 'how did it go?' prompt without a 404 round-trip.
    """
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    fu = store.get_followup(report_id, x_anon_id)
    return {"followup": fu}
