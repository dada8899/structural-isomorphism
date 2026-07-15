"""Legacy unauthenticated deletion retained only as a development fixture.

A well-formed, constraint-valid production request returns HTTP 410; malformed
or constraint-invalid queries return HTTP 422 before the handler. The supported
account-bound erasure flow is ``POST /api/me/delete`` with an active signed-in
session. The email-code implementation below exists solely for isolated local
and CI compatibility; it is not a public verification or account-deletion flow.
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

from schemas import PrivacyDeleteResponse as LegacyPrivacyDeleteResponse
if __package__ == "web.backend.api.privacy":
    from ...logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id
try:
    from services.privacy_identifiers import opaque_identifier
except ModuleNotFoundError:
    from web.backend.services.privacy_identifiers import opaque_identifier

router = APIRouter(tags=["privacy"], prefix="/privacy")
logger = get_logger("structural.privacy.delete")

RATE_LIMIT_WINDOW_S = 3600
RATE_LIMIT_MAX = 1
_MAX_EMAIL_LEN = 200

_buckets: Dict[str, Deque[float]] = defaultdict(deque)
_RATE_KEY = secrets.token_bytes(32)


class LegacyPrivacyDeleteRetiredResponse(BaseModel):
    error: Literal["legacy_privacy_endpoint_retired"]
    detail: str


def _is_prod() -> bool:
    return os.getenv("STRUCTURAL_ENV", "dev").strip().lower() == "prod"


def _data_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "data"


def _newsletter_file() -> Path:
    return _data_dir() / "newsletter-subscribers.jsonl"


def _checkouts_file() -> Path:
    return _data_dir() / "mock_checkouts.jsonl"


def _error_log_files() -> List[Path]:
    base = _data_dir() / "error_log.jsonl"
    rotated = base.with_suffix(base.suffix + ".1")
    return [p for p in (base, rotated) if p.exists()]


def _audit_file() -> Path:
    return _data_dir() / "privacy_audit.jsonl"


def _history_db() -> Path:
    """history.db holds the structural_fingerprints table (G connections)."""
    return _data_dir() / "history.db"


def _delete_fingerprints(email: str) -> int:
    """Delete the user's structural fingerprints (G connections feature).

    Fingerprints live in a SQLite table, not the JSONL files — so the
    JSONL rewrite path misses them. design §2.4 requires them to be in
    DSAR delete scope. Returns rows removed; 0 if the DB doesn't exist yet.
    """
    db = _history_db()
    if not db.exists():
        return 0
    from services.connections_store import ConnectionsStore

    return ConnectionsStore(db).delete_all_for_user(email)


def _delete_p3(email: str) -> dict:
    """Delete the user's P3 data: match_requests / referrals / messages / prefs.

    Mirrors _delete_fingerprints — P3 introduced four new tables in the same
    history.db and they must be DSAR-deletable per SESSION-21 §6 pattern.
    Returns per-table row counts; all zeros if DB doesn't exist yet.
    """
    db = _history_db()
    if not db.exists():
        return {
            "match_requests": 0,
            "referrals": 0,
            "connections_messages": 0,
            "connections_prefs": 0,
        }
    from services.connections_p3_store import ConnectionsP3Store

    return ConnectionsP3Store(db).delete_all_for_user(email)


# Random per-process fallback — see export.py for the rationale. An unset
# STRUCTURAL_PRIVACY_MOCK_CODE must fail closed (unguessable), never fall back
# to a public default that would expose the data-deletion endpoint.
_FALLBACK_VERIFICATION_CODE = secrets.token_hex(16)


def _expected_verification_code() -> str:
    """Resolve the development-fixture code, failing closed when unset.

    A constraint-valid production request never reaches this flow because the
    route returns HTTP 410.
    """
    code = os.getenv("STRUCTURAL_PRIVACY_MOCK_CODE")
    if code:
        return code
    logger.warning("privacy.delete_fixture_locked")
    return _FALLBACK_VERIFICATION_CODE


def _check_rate_limit(key: str, now: float, legacy_key: str | None = None) -> bool:
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
    return opaque_identifier(f"privacy-delete-rate.{kind}", identifier, kind=kind)


def _filter_out_email(path: Path, email: str) -> int:
    """Rewrite `path` removing any line with matching email. Returns count
    removed. Atomic via tmp + rename. No-op if file missing."""
    if not path.exists():
        return 0
    target = email.lower()
    tmp = path.with_suffix(path.suffix + ".tmp")
    removed = 0
    try:
        with open(path, "r", encoding="utf-8") as src, open(
            tmp, "w", encoding="utf-8"
        ) as dst:
            for line in src:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except Exception:
                    # Preserve malformed lines verbatim — we can't decide if
                    # they belong to this user, so keep them rather than risk
                    # deleting someone else's data.
                    dst.write(line if line.endswith("\n") else line + "\n")
                    continue
                row_email = (row.get("email") or "").lower()
                if row_email == target:
                    removed += 1
                    continue
                dst.write(stripped + "\n")
        os.replace(tmp, path)
    except Exception as exc:
        logger.error(
            "privacy.delete_rewrite_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        # Clean up tmp if still around
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return removed


def _filter_out_session(path: Path, session_id: str) -> int:
    """Same as _filter_out_email but keyed by sessionId."""
    if not path.exists():
        return 0
    tmp = path.with_suffix(path.suffix + ".tmp")
    removed = 0
    try:
        with open(path, "r", encoding="utf-8") as src, open(
            tmp, "w", encoding="utf-8"
        ) as dst:
            for line in src:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    row = json.loads(stripped)
                except Exception:
                    dst.write(line if line.endswith("\n") else line + "\n")
                    continue
                if (row.get("sessionId") or "") == session_id:
                    removed += 1
                    continue
                dst.write(stripped + "\n")
        os.replace(tmp, path)
    except Exception as exc:
        logger.error(
            "privacy.delete_rewrite_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        raise
    return removed


def _audit(email: Optional[str], session_id: Optional[str], ip: str, removed: Dict[str, int]) -> None:
    """Append an audit row. The audit log itself never gets deleted by
    this endpoint. Identifiers and network metadata are deliberately omitted;
    the row retains only aggregate removal counts and a random incident ID."""
    f = _audit_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "event": "delete_requested",
        "incident_id": new_incident_id(),
        "removed_counts": removed,
        "ts": int(time.time()),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    try:
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.error(
            "privacy.delete_audit_write_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )


def _mock_send_confirmation(email: str, removed: Dict[str, int]) -> None:
    """Log a development-fixture confirmation; never used in production."""
    logger.info("privacy.delete_confirmation_fixture")


@router.delete(
    "/delete",
    response_model=LegacyPrivacyDeleteResponse,
    summary="Legacy email-code deletion (retired in production)",
    description=(
        "Development compatibility endpoint. A well-formed, constraint-valid "
        "production request returns HTTP 410 before business logic or "
        "persistence; a malformed, overlong, or otherwise constraint-invalid "
        "query returns HTTP 422 before the handler. Signed-in users delete "
        "account data through /api/me/delete."
    ),
    deprecated=True,
    responses={
        410: {
            "model": LegacyPrivacyDeleteRetiredResponse,
            "description": "Production legacy deletion is retired",
        },
    },
)
async def delete_data(
    request: Request,
    email: Optional[str] = Query(None, max_length=_MAX_EMAIL_LEN),
    session_id: Optional[str] = Query(None, max_length=128),
    code: Optional[str] = Query(None, max_length=32),
):
    """Exercise the retired deletion fixture outside production only.

    Returns 200 with removal counts on success. 401 if unverified.
    429 if rate-limit exceeded. 400 if no identifier supplied.
    """
    if _is_prod():
        return JSONResponse(
            {
                "error": "legacy_privacy_endpoint_retired",
                "detail": "Use the signed-in account deletion flow.",
            },
            status_code=410,
        )

    now = time.time()
    client_ip = request.client.host if request.client else "?"

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
        logger.info("privacy.delete_verification_rejected")
        return JSONResponse(
            {"ok": False, "error": "invalid verification code"},
            status_code=401,
        )

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

    removed: Dict[str, int] = {
        "newsletter_subscribers": 0,
        "mock_checkouts": 0,
        "error_log": 0,
        "structural_fingerprints": 0,
        "match_requests": 0,
        "referrals": 0,
        "connections_messages": 0,
        "connections_prefs": 0,
    }

    try:
        if email:
            removed["newsletter_subscribers"] = _filter_out_email(
                _newsletter_file(), email
            )
            removed["mock_checkouts"] = _filter_out_email(
                _checkouts_file(), email
            )
            removed["structural_fingerprints"] = _delete_fingerprints(email)
            # P3 — SESSION-22 §5: match_requests / referrals / messages / prefs
            p3_removed = _delete_p3(email)
            removed["match_requests"] = p3_removed["match_requests"]
            removed["referrals"] = p3_removed["referrals"]
            removed["connections_messages"] = p3_removed["connections_messages"]
            removed["connections_prefs"] = p3_removed["connections_prefs"]
        if session_id:
            n = 0
            for f in _error_log_files():
                n += _filter_out_session(f, session_id)
            removed["error_log"] = n
    except Exception as exc:
        logger.error(
            "privacy.delete_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        return JSONResponse(
            {"ok": False, "error": "storage failure"}, status_code=500
        )

    # Audit + mock email regardless of removed counts (request was valid).
    _audit(email, session_id, client_ip, removed)
    if email:
        _mock_send_confirmation(email, removed)

    logger.info("privacy.delete_completed")
    return JSONResponse(
        {
            "ok": True,
            "deleted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
            "removed": removed,
            "email_confirmation": "sent" if email else "skipped",
        },
        status_code=200,
    )
