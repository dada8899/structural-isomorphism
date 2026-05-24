"""GET /api/insights/* — aggregate data-flywheel dashboard.

B Data Flywheel (Session #18).

Three read-only endpoints powering /insights:
  * /api/insights/summary           — top-line counters
  * /api/insights/stuck-structures  — which problem targets users hit most
  * /api/insights/verified          — the result-verified isomorphism library

All three degrade to empty/zero on a fresh DB — no auth, no anon-id; this
is aggregate, non-PII data. Companion: services/report_store.py +
services/verified_isomorphisms.py.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from services.report_store import ReportStore
from services.verified_isomorphisms import list_verified

logger = logging.getLogger(__name__)
router = APIRouter(tags=["insights"])

_store: Optional[ReportStore] = None


def _get_store() -> ReportStore:
    """Resolve the shared ReportStore (same history.db as api/report.py).

    Kept as a module global mirroring api/report.py so tests can monkeypatch
    a tmp-path store the same way.
    """
    global _store
    if _store is None:
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ReportStore(db_path)
    return _store


# ---------------- response shapes ----------------------------------- #


class SummaryResponse(BaseModel):
    total_reports: int
    total_followups: int
    worked_count: int
    verified_isomorphisms: int


class StuckStructureItem(BaseModel):
    b_id: str
    report_count: int
    followup_count: int
    worked_count: int
    worked_rate: float


class StuckStructuresResponse(BaseModel):
    items: list[StuckStructureItem]


class VerifiedItem(BaseModel):
    report_id: str
    problem: str
    b_id: str
    lang: str
    source_phenomenon: str
    structure_name: str
    verifier_count: int
    last_verified_at: str
    created_at: str


class VerifiedResponse(BaseModel):
    items: list[VerifiedItem]


# ---------------- endpoints ----------------------------------------- #


@router.get(
    "/insights/summary",
    response_model=SummaryResponse,
    summary="Top-line data-flywheel counters",
)
async def insights_summary():
    """Total reports / followups / worked / verified. Fresh DB → all zero."""
    return _get_store().insights_summary()


@router.get(
    "/insights/stuck-structures",
    response_model=StuckStructuresResponse,
    summary="Problem targets users hit most (Top N)",
)
async def stuck_structures(limit: int = Query(20, ge=1, le=100)):
    """Aggregate report_count / followup_count / worked_rate per b_id."""
    return {"items": _get_store().stuck_structures(limit=limit)}


@router.get(
    "/insights/verified",
    response_model=VerifiedResponse,
    summary="Result-verified isomorphism library",
)
async def verified(limit: int = Query(50, ge=1, le=100)):
    """Reports a real user came back and marked outcome='worked'."""
    return {"items": list_verified(_get_store(), limit=limit)}
