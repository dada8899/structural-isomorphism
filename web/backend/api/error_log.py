"""POST /api/errors — client-side error log receiver.

W12-E: receives reports from app/error.tsx + app/global-error.tsx (and any
other instrumentation via lib/error-reporter.ts).

Storage:
    web/backend/data/error_log.jsonl — append-only, rotated at 10 MB
    web/backend/data/error_log.jsonl.1 — most recent prior segment (kept once)

Rate limit:
    10 errors / minute / sessionId (sliding 60s window, in-memory ring).
    Anonymous (no sessionId) requests bucketed by client IP instead.

Privacy:
    • URL query string stripped server-side (defence-in-depth).
    • stack / message truncated to bounded sizes.
    • No localStorage contents accepted (schema forbids extra fields).

Body schema (JSON):
    {
      "message":    str (1..500),
      "stack":      str | None (max 4000),
      "digest":     str | None,
      "url":        str | None (query stripped before storage),
      "userAgent":  str | None (max 300),
      "timestamp":  int  | None (seconds since epoch; defaults to server now),
      "sessionId":  str  | None (max 64),
      "fatal":      bool | None (true when reported from global-error.tsx)
    }

Response:
    200 { "accepted": true,  "stored_at": <iso> }
    200 { "accepted": false, "reason": "rate_limited" }
    422 — pydantic validation
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Optional
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from schemas import ErrorAcceptedResponse

router = APIRouter(tags=["errors"])
logger = logging.getLogger("structural.errors")

# --- Tuning constants ---
RATE_LIMIT_WINDOW_S = 60
RATE_LIMIT_MAX = 10
MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_MESSAGE = 500
_MAX_STACK = 4000
_MAX_URL = 500
_MAX_UA = 300
_MAX_SESSION = 64
_MAX_DIGEST = 64

# Rate limiter state: sessionId -> deque[timestamps]. In-memory only; restarts
# reset the window. Sufficient for client-side error reports — we tolerate a
# slight burst right after process restart.
_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def _data_file() -> Path:
    """Active log target. Tests monkeypatch this."""
    return Path(__file__).parent.parent / "data" / "error_log.jsonl"


def _rotate_if_needed(path: Path) -> None:
    """Cap log at MAX_LOG_BYTES by sliding to .1 (single-rotation, no .2/.3).

    Keeps disk usage bounded ≤ 2 × MAX_LOG_BYTES. Failure to rotate is logged
    but never raised — error logging must never block its own caller.
    """
    try:
        if not path.exists():
            return
        if path.stat().st_size < MAX_LOG_BYTES:
            return
        rotated = path.with_suffix(path.suffix + ".1")
        if rotated.exists():
            rotated.unlink()
        os.replace(path, rotated)
        logger.info("error_log rotated: %s -> %s", path.name, rotated.name)
    except Exception as e:  # pragma: no cover — best-effort
        logger.warning("error_log rotate failed: %s", e)


def _strip_query(url: Optional[str]) -> Optional[str]:
    """Server-side belt-and-braces query stripper (client also strips)."""
    if not url:
        return None
    try:
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return url.split("?")[0]


def _bucket_key(session_id: Optional[str], client_ip: str) -> str:
    if session_id and len(session_id) <= _MAX_SESSION:
        return f"sid:{session_id}"
    return f"ip:{client_ip}"


def _check_rate_limit(key: str, now: float) -> bool:
    """Return True iff under limit. Side-effect: appends `now` if accepted."""
    bucket = _buckets[key]
    cutoff = now - RATE_LIMIT_WINDOW_S
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True


class ErrorReportBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=_MAX_MESSAGE)
    stack: Optional[str] = Field(default=None, max_length=_MAX_STACK)
    digest: Optional[str] = Field(default=None, max_length=_MAX_DIGEST)
    url: Optional[str] = Field(default=None, max_length=_MAX_URL)
    userAgent: Optional[str] = Field(default=None, max_length=_MAX_UA)
    timestamp: Optional[int] = None
    sessionId: Optional[str] = Field(default=None, max_length=_MAX_SESSION)
    fatal: Optional[bool] = False

    model_config = {"extra": "forbid"}  # reject unknown fields (privacy)


@router.post("/errors", response_model=ErrorAcceptedResponse, response_model_exclude_none=True)
async def submit_error(body: ErrorReportBody, request: Request):
    now = time.time()
    client_ip = request.client.host if request.client else "?"

    # --- Rate limit ---
    key = _bucket_key(body.sessionId, client_ip)
    if not _check_rate_limit(key, now):
        return JSONResponse(
            {"accepted": False, "reason": "rate_limited"}, status_code=200
        )

    # --- Normalise ---
    record = {
        "message": body.message[:_MAX_MESSAGE],
        "stack": (body.stack or "")[:_MAX_STACK] or None,
        "digest": body.digest,
        "url": _strip_query(body.url),
        "userAgent": (body.userAgent or "")[:_MAX_UA] or None,
        "timestamp": int(body.timestamp) if body.timestamp else int(now),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "sessionId": body.sessionId,
        "fatal": bool(body.fatal),
        "client_ip": client_ip,
    }

    # --- Persist ---
    f = _data_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(f)
    try:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:  # pragma: no cover
        logger.error("error_log write failed: %s", e)
        return JSONResponse(
            {"accepted": False, "reason": "storage_failure"}, status_code=500
        )

    logger.info(
        "error_report: session=%s digest=%s fatal=%s msg=%s",
        body.sessionId,
        body.digest,
        bool(body.fatal),
        body.message[:120],
    )
    return {"accepted": True, "stored_at": record["iso"]}
