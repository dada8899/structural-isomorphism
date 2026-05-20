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
        # Reuse history.db (same file as analyze.py / history_db.py).
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ReportStore(db_path)
    return _store


# ---------------- response shapes ----------------------------------- #


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


class ReportListItem(BaseModel):
    id: str
    query: str
    b_id: str
    lang: str
    created_at: str
    view_count: int


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


# ---------------- endpoints ----------------------------------------- #


def _detail_dict(r: dict) -> dict:
    """Project a store row to the public detail shape (drops share_token)."""
    return {
        "id": r["id"],
        "query": r["query"],
        "rewritten_query": r.get("rewritten_query"),
        "b_id": r["b_id"],
        "lang": r["lang"],
        "payload": r["payload"],
        "model": r["model"],
        "prompt_version": r["prompt_version"],
        "created_at": r["created_at"],
        "view_count": r.get("view_count", 0),
        "is_partial": r.get("is_partial", False),
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
    # Constant-time check that the token actually signs this row (defence
    # against a future schema change that lets non-HMAC tokens slip in).
    if not verify_share_token(r["id"], token):
        # Token DB row exists but HMAC doesn't verify — config drift.
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
        # Hide existence rather than leak via 403.
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
        # No anon-id ≈ no history. Return empty rather than 401 so
        # frontend can render "no reports yet" cleanly.
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
