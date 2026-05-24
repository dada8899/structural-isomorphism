"""
GET / DELETE /api/history — per-device anonymous query history.

Both endpoints require the `X-Device-ID` header (anonymous cookie value
forwarded by the frontend). Wave 2 will wire frontend localStorage → these
endpoints; this is foundation only.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from services.history_db import ALLOWED_KINDS, HistoryDB

logger = logging.getLogger("structural.api.history")

router = APIRouter(tags=["history"])

_db: Optional[HistoryDB] = None


def _resolve_db_path() -> Path:
    """Allow override via STRUCTURAL_HISTORY_DB; default to web/backend/data/history.db."""
    override = os.getenv("STRUCTURAL_HISTORY_DB")
    if override:
        return Path(override)
    # web/backend/api/history.py → web/backend/data/history.db
    return Path(__file__).resolve().parent.parent / "data" / "history.db"


def get_db() -> HistoryDB:
    """Lazy singleton — initialised on first request so the file isn't created
    at import time (helps tests + cold-start observability)."""
    global _db
    if _db is None:
        _db = HistoryDB(_resolve_db_path())
        logger.info("history_db initialised at %s", _db.db_path)
    return _db


def _require_device_id(x_device_id: str | None) -> str:
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(status_code=400, detail="X-Device-ID header required")
    return x_device_id.strip()


class HistoryRecordRequest(BaseModel):
    """Body for POST /api/history.

    Mirrors HistoryDB.record fields. `result_summary` is optional and any
    JSON-serialisable shape is accepted; HistoryDB normalises to a string.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    kind: str = Field(..., min_length=1)
    result_summary: dict | None = None


@router.get("/history")
async def list_history(
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
    limit: int = 20,
):
    device_id = _require_device_id(x_device_id)
    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in (0, 200]")
    db = get_db()
    rows = db.list_recent(device_id, limit=limit)
    return {"items": rows, "count": len(rows)}


@router.post("/history")
async def record_history(
    body: HistoryRecordRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """Record a single history entry. Anonymous, scoped by device_id cookie."""
    device_id = _require_device_id(x_device_id)
    kind = body.kind.strip().lower()
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(ALLOWED_KINDS)}",
        )
    db = get_db()
    try:
        rid = db.record(device_id, body.query.strip(), kind, body.result_summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": rid}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    device_id = _require_device_id(x_device_id)
    db = get_db()
    ok = db.delete(device_id, history_id)
    if not ok:
        raise HTTPException(status_code=404, detail="history row not found")
    return {"ok": True, "id": history_id}
