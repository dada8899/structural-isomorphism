"""Legacy unauthenticated export retained only as a development fixture.

A well-formed, constraint-valid production request returns HTTP 410; malformed
or constraint-invalid queries return HTTP 422 before the handler. The supported
account-bound export is ``GET /api/me/export`` with an active signed-in session.
The email-code implementation below exists solely for isolated local and CI
compatibility; it is not a public verification flow or a current account right.
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
from typing import Any, Deque, Dict, List, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from schemas import PrivacyExportResponse as LegacyPrivacyExportResponse
if __package__ == "web.backend.api.privacy":
    from ...logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id
try:
    from services.privacy_identifiers import opaque_identifier
except ModuleNotFoundError:
    from web.backend.services.privacy_identifiers import opaque_identifier

router = APIRouter(tags=["privacy"], prefix="/privacy")
logger = get_logger("structural.privacy.export")

# --- Tuning ---
RATE_LIMIT_WINDOW_S = 3600  # 1 hour
RATE_LIMIT_MAX = 1  # one export per hour per email
_MAX_EMAIL_LEN = 200

# In-memory bucket. Cleared on restart — acceptable (worst case: user gets
# one extra export after a server restart, not a security risk).
_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_RATE_KEY = secrets.token_bytes(32)


class LegacyPrivacyExportRetiredResponse(BaseModel):
    error: Literal["legacy_privacy_endpoint_retired"]
    detail: str


def _is_prod() -> bool:
    return os.getenv("STRUCTURAL_ENV", "dev").strip().lower() == "prod"


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


def _history_db() -> Path:
    """history.db holds the structural_fingerprints table (G connections)."""
    return _data_dir() / "history.db"


def _export_fingerprints(email: str) -> List[Dict[str, Any]]:
    """Export the user's structural fingerprints (G connections feature).

    Mirrors the delete-side fingerprint integration that SESSION-21 §6
    added. DSAR completeness requires that whatever we can delete on
    request, we must also be able to hand back on request. Returns [] if
    history.db hasn't been created yet (no fingerprints registered).
    """
    db = _history_db()
    if not db.exists():
        return []
    from services.connections_store import ConnectionsStore

    return ConnectionsStore(db).export_all_for_user(email)


def _export_p3(email: str) -> Dict[str, List[Dict[str, Any]]]:
    """Export the user's P3 data (match_requests / referrals / messages / prefs).

    Symmetric to _delete_p3 in delete.py — DSAR completeness (SESSION-21 §6).
    Returns dict-of-lists, all empty when history.db doesn't exist yet.
    """
    empty = {
        "match_requests": [],
        "referrals": [],
        "connections_messages": [],
        "connections_prefs": [],
    }
    db = _history_db()
    if not db.exists():
        return empty
    from services.connections_p3_store import ConnectionsP3Store

    return ConnectionsP3Store(db).export_all_for_user(email)


# Random per-process fallback. Used only when STRUCTURAL_PRIVACY_MOCK_CODE is
# unset — it locks the endpoint (no one can guess it) instead of falling back
# to the retired public fallback. That fallback meant anyone who knew a
# subscriber's email could pull their PII; an unset prod env must FAIL CLOSED.
_FALLBACK_VERIFICATION_CODE = secrets.token_hex(16)


def _expected_verification_code() -> str:
    """Resolve the development-fixture code, failing closed when unset.

    A constraint-valid production request never reaches this flow because the
    route returns HTTP 410.
    The environment override is only for isolated development and CI tests.
    """
    code = os.getenv("STRUCTURAL_PRIVACY_MOCK_CODE")
    if code:
        return code
    logger.warning("privacy.export_fixture_locked")
    return _FALLBACK_VERIFICATION_CODE


def _check_rate_limit(key: str, now: float, legacy_key: str | None = None) -> bool:
    """Return True iff under limit. Side-effect: appends `now` if accepted."""
    if legacy_key and legacy_key != key and legacy_key in _buckets:
        legacy = _buckets.pop(legacy_key)
        current = _buckets[key]
        current.extend(legacy)
        _buckets[key] = deque(sorted(current))
    bucket = _buckets[key]
    cutoff = now - RATE_LIMIT_WINDOW_S
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_MAX:
        return False
    bucket.append(now)
    return True


def _legacy_rate_key(identifier: str) -> str:
    return hmac.new(
        _RATE_KEY,
        identifier.strip().lower().encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _rate_key(identifier: str, kind: str) -> str:
    return opaque_identifier(f"privacy-export-rate.{kind}", identifier, kind=kind)


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
    except Exception as exc:
        logger.warning(
            "privacy.export_read_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
    return out


def _filter_by_email(rows: List[Dict[str, Any]], email: str) -> List[Dict[str, Any]]:
    target = email.lower()
    return [r for r in rows if (r.get("email") or "").lower() == target]


def _filter_by_session(rows: List[Dict[str, Any]], session_id: str) -> List[Dict[str, Any]]:
    return [r for r in rows if (r.get("sessionId") or "") == session_id]


@router.get(
    "/export",
    response_model=LegacyPrivacyExportResponse,
    summary="Legacy email-code export (retired in production)",
    description=(
        "Development compatibility endpoint. A well-formed, constraint-valid "
        "production request returns HTTP 410 before business logic or "
        "persistence; a malformed, overlong, or otherwise constraint-invalid "
        "query returns HTTP 422 before the handler. Signed-in users export "
        "data through /api/me/export."
    ),
    deprecated=True,
    responses={
        410: {
            "model": LegacyPrivacyExportRetiredResponse,
            "description": "Production legacy export is retired",
        },
    },
)
async def export_data(
    request: Request,
    email: Optional[str] = Query(None, max_length=_MAX_EMAIL_LEN),
    session_id: Optional[str] = Query(None, max_length=128),
    code: Optional[str] = Query(None, max_length=32),
):
    """Exercise the retired export fixture outside production only.

    Args:
        email: Identifier for newsletter / checkout records.
        session_id: Identifier for error log entries (different keying).
        code: Development-fixture verification value.

    Returns 200 with full payload on success. 401 if unverified.
    429 if rate-limit exceeded. 400 if no identifier supplied.
    """
    if _is_prod():
        return JSONResponse(
            {
                "error": "legacy_privacy_endpoint_retired",
                "detail": "Use the signed-in account data export.",
            },
            status_code=410,
        )

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
        logger.info("privacy.export_verification_rejected")
        return JSONResponse(
            {"ok": False, "error": "invalid verification code"},
            status_code=401,
        )

    # --- Rate limit (after auth so 401 doesn't burn quota) ---
    identifier = email or session_id or ""
    kind = "email" if email else "opaque"
    rl_key = _rate_key(identifier, kind)
    if not _check_rate_limit(rl_key, now, _legacy_rate_key(identifier)):
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
            "structural_fingerprints": [],  # G connections feature, SESSION-22 §8
            # P3 (SESSION-22 §5): mutual-consent match + referrals + messages.
            "match_requests": [],
            "referrals": [],
            "connections_messages": [],
            "connections_prefs": [],
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
        payload["data"]["structural_fingerprints"] = _export_fingerprints(email)
        p3 = _export_p3(email)
        payload["data"]["match_requests"] = p3["match_requests"]
        payload["data"]["referrals"] = p3["referrals"]
        payload["data"]["connections_messages"] = p3["connections_messages"]
        payload["data"]["connections_prefs"] = p3["connections_prefs"]

    if session_id:
        # error_log can span current file + 1 rotated segment
        error_rows: List[Dict[str, Any]] = []
        for f in _error_log_files():
            error_rows.extend(_filter_by_session(_read_jsonl(f), session_id))
        payload["data"]["error_log"] = error_rows

    logger.info("privacy.export_completed")

    return JSONResponse(payload, status_code=200)
