"""GET /api/privacy/export — GDPR data subject access (DSAR) endpoint.

W14-C (session #10, 2026-05-15): self-service data export.

Returns a JSON document with every record we hold for the given email
identifier across:
  • newsletter-subscribers.jsonl
  • mock_checkouts.jsonl
  • error_log.jsonl (matched by sessionId, not email — pass ?session_id=
    in addition to ?email=)
  • error_log.jsonl.1 (rotated segment, if present)

Verification:
  Phase 1 (now): mock verification code. The endpoint accepts the literal
  string "123456" as the verification code (configurable via
  STRUCTURAL_PRIVACY_MOCK_CODE env). This lets us:
    1. Ship the endpoint shape today.
    2. Test it in CI without a real mail server.
    3. Surface a clear "needs real email loop" item for Phase 2.
  Phase 2 (when SES/Postmark wired): send a 6-digit OTP, expire after 10
  min, single-use. Same endpoint, just `code` verification changes.

Rate limit:
  1 request / hour / email. Prevents enumeration + abuse. Uses an in-
  memory deque keyed by email; restarts reset. Documented as best-effort.

Authentication:
  Email + verification code only. We deliberately don't require any prior
  account because we don't have accounts. The "verification" is the proof.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

router = APIRouter(tags=["privacy"], prefix="/privacy")
logger = logging.getLogger("structural.privacy.export")

# --- Tuning ---
RATE_LIMIT_WINDOW_S = 3600  # 1 hour
RATE_LIMIT_MAX = 1  # one export per hour per email
_MAX_EMAIL_LEN = 200

# In-memory bucket. Cleared on restart — acceptable (worst case: user gets
# one extra export after a server restart, not a security risk).
_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def _data_dir() -> Path:
    """Single point for tests to monkeypatch all data files at once."""
    return Path(__file__).resolve().parent.parent.parent / "data"


def _newsletter_file() -> Path:
    return _data_dir() / "newsletter-subscribers.jsonl"


def _checkouts_file() -> Path:
    return _data_dir() / "mock_checkouts.jsonl"


def _error_log_files() -> List[Path]:
    base = _data_dir() / "error_log.jsonl"
    rotated = base.with_suffix(base.suffix + ".1")
    return [p for p in (base, rotated) if p.exists()]


def _expected_verification_code() -> str:
    """Mock verification code. Phase 2 replaces with a real OTP store."""
    return os.getenv("STRUCTURAL_PRIVACY_MOCK_CODE", "123456")


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


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file safely. Skips malformed lines (logged once)."""
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except Exception:
                    # Single bad line shouldn't tank the whole export.
                    continue
    except Exception as e:
        logger.warning("read jsonl failed path=%s err=%s", path, e)
    return out


def _filter_by_email(rows: List[Dict[str, Any]], email: str) -> List[Dict[str, Any]]:
    target = email.lower()
    return [r for r in rows if (r.get("email") or "").lower() == target]


def _filter_by_session(rows: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
    return [r for r in rows if (r.get("sessionId") or "") == session_id]


@router.get("/export")
async def export_data(
    request: Request,
    email: Optional[str] = Query(None, max_length=_MAX_EMAIL_LEN),
    session_id: Optional[str] = Query(None, max_length=128),
    code: Optional[str] = Query(None, max_length=32),
):
    """Export all data tied to a given email + optional session id.

    Args:
        email: Identifier for newsletter / checkout records.
        session_id: Identifier for error log entries (different keying).
        code: Verification code (mock for Phase 1).

    Returns 200 with full payload on success. 401 if unverified.
    429 if rate-limit exceeded. 400 if no identifier supplied.
    """
    now = time.time()

    # --- Input validation ---
    if not email and not session_id:
        return JSONResponse(
            {"ok": False, "error": "must supply email or session_id"},
            status_code=400,
        )

    if not code:
        return JSONResponse(
            {"ok": False, "error": "verification code required"},
            status_code=401,
        )
    if code != _expected_verification_code():
        logger.info(
            "privacy export bad code: email=%s ip=%s",
            email,
            request.client.host if request.client else "?",
        )
        return JSONResponse(
            {"ok": False, "error": "invalid verification code"},
            status_code=401,
        )

    # --- Rate limit (after auth so 401 doesn't burn quota) ---
    rl_key = (email or session_id or "").lower()
    if not _check_rate_limit(rl_key, now):
        return JSONResponse(
            {
                "ok": False,
                "error": "rate_limited",
                "retry_after_s": RATE_LIMIT_WINDOW_S,
            },
            status_code=429,
        )

    # --- Gather data ---
    payload: Dict[str, Any] = {
        "ok": True,
        "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
        "email": email,
        "session_id": session_id,
        "data": {
            "newsletter_subscribers": [],
            "mock_checkouts": [],
            "error_log": [],
            "search_history": [],  # local-only, never on server; documented
        },
    }

    if email:
        payload["data"]["newsletter_subscribers"] = _filter_by_email(
            _read_jsonl(_newsletter_file()), email
        )
        payload["data"]["mock_checkouts"] = _filter_by_email(
            _read_jsonl(_checkouts_file()), email
        )

    if session_id:
        # error_log can span current file + 1 rotated segment
        error_rows: List[Dict[str, Any]] = []
        for f in _error_log_files():
            error_rows.extend(_filter_by_session(_read_jsonl(f), session_id))
        payload["data"]["error_log"] = error_rows

    logger.info(
        "privacy export: email=%s session=%s newsletter=%d checkouts=%d errors=%d",
        email,
        session_id,
        len(payload["data"]["newsletter_subscribers"]),
        len(payload["data"]["mock_checkouts"]),
        len(payload["data"]["error_log"]),
    )

    return JSONResponse(payload, status_code=200)
