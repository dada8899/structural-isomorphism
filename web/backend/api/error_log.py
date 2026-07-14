"""POST /api/errors — client-side error log receiver.

W12-E: receives reports from app/error.tsx + app/global-error.tsx (and any
other instrumentation via lib/error-reporter.ts).

Storage (content-free operational events):
    web/backend/data/error_log.jsonl — append-only, rotated at 10 MB
    web/backend/data/error_log.jsonl.1 — most recent prior segment (kept once)

Rate limit:
    10 errors / minute / client IP (sliding 60s window, in-memory ring).
    The address is HMAC-bucketed in memory and is never persisted or logged.

Privacy:
    • Only an exact allowlisted error class, timestamp and fatal flag enter the
      application model. Pre-hardening raw fields are rejected with 422.
    • The durable row contains a coarse allowlisted error type, fatal flag,
      server timestamp and random incident ID only.
    • No localStorage contents accepted (schema forbids extra fields).

Body schema (JSON):
    {
      "message":    allowlisted coarse error class,
      "timestamp":  int | None (client event time; persistence uses server time),
      "fatal":      bool (true when reported from global-error.tsx)
    }

Response:
    200 { "accepted": true,  "stored_at": <iso> }
    200 { "accepted": false, "reason": "rate_limited" }
    422 — pydantic validation
"""
from __future__ import annotations

import json
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Deque, Dict, Literal, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from schemas import ErrorAcceptedResponse
if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

router = APIRouter(tags=["errors"])
logger = get_logger("structural.client_errors")

# --- Tuning constants ---
RATE_LIMIT_WINDOW_S = 60
RATE_LIMIT_MAX = 10
MAX_LOG_BYTES = 10 * 1024 * 1024  # 10 MB

# Rate limiter state: ephemeral IP-HMAC bucket -> deque[timestamps]. In-memory
# only; restarts reset the window. The address never enters the bucket key.
_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_RATE_KEY = secrets.token_bytes(32)


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
        logger.info("privacy.client_error_log_rotated")
    except Exception as exc:  # pragma: no cover — best-effort
        logger.warning(
            "privacy.client_error_log_rotate_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )


def _bucket_key(client_ip: str) -> str:
    digest = hmac.new(
        _RATE_KEY,
        b"ip\0" + (client_ip or "unknown").encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"ip:{digest}"


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
    message: Literal[
        "ChunkLoadError", "ClientError", "Error", "NetworkError",
        "RangeError", "ReferenceError", "SyntaxError", "TypeError", "URIError",
    ]
    timestamp: Optional[int] = Field(default=None, ge=0, le=4_102_444_800)
    fatal: bool = False

    model_config = {"extra": "forbid"}  # reject unknown fields (privacy)


@router.post("/errors", response_model=ErrorAcceptedResponse, response_model_exclude_none=True)
async def submit_error(body: ErrorReportBody, request: Request):
    now = time.time()
    client_ip = request.client.host if request.client else "?"

    # --- Rate limit ---
    key = _bucket_key(client_ip)
    if not _check_rate_limit(key, now):
        return JSONResponse(
            {"accepted": False, "reason": "rate_limited"}, status_code=200
        )

    # --- Normalise ---
    record = {
        "event": "client_error",
        "incident_id": new_incident_id(),
        "error_type": body.message,
        "timestamp": int(now),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "fatal": bool(body.fatal),
    }

    # --- Persist ---
    f = _data_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_needed(f)
    try:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:  # pragma: no cover
        logger.error(
            "privacy.client_error_write_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse(
            {"accepted": False, "reason": "storage_failure"}, status_code=500
        )

    logger.info("privacy.client_error_accepted")
    return {"accepted": True, "stored_at": record["iso"]}
