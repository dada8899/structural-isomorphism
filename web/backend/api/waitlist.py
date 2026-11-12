"""Closed Beta waitlist endpoints for this release.

The existing list, external Phase service and provider relationships remain
outside this change. HTTP requests declare no body and never invoke the
legacy SQLite, rate-bucket or UTM helpers retained for separate maintenance.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import re
import secrets
import sqlite3
import time
from collections import deque
from contextlib import closing
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id
try:
    from services.privacy_identifiers import opaque_identifier
except ModuleNotFoundError:
    from web.backend.services.privacy_identifiers import opaque_identifier

if __package__ == "web.backend.api":
    from .newsletter import SubscriptionUnavailableResponse, unavailable_response
else:
    from api.newsletter import SubscriptionUnavailableResponse, unavailable_response

router = APIRouter(tags=["waitlist"])
logger = get_logger("structural.waitlist")

# Pragmatic RFC-5322-ish — same shape as newsletter.py for consistency.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Whitelist placements so the table stays auditable. Add here when adding new
# CTAs (keep in sync with frontend mountWaitlist calls).
_ALLOWED_SOURCES = {
    "homepage-hero",
    "homepage-bottom",
    "phase-footer",
    "pricing-page",
    "test",  # for tests only — filter out in analytics
}

_MAX_EMAIL_LEN = 200
_MAX_SOURCE_LEN = 60
_MAX_UTM_LEN = 200

# Rate limit: 5 signups per IP per 10 minutes. Cheap in-memory ring buffer.
_RATE_WINDOW_SEC = 600
_RATE_MAX = 5
_rate_buckets: dict[str, deque] = {}
_RATE_KEY = secrets.token_bytes(32)


def _rate_bucket_key(client_address: str) -> str:
    """Return the stable domain-separated v2 bucket for a client address."""
    return opaque_identifier("waitlist-rate.ip", client_address, kind="ip")


def _legacy_rate_bucket_key(client_address: str) -> str:
    """Pre-v2 process-local key used only to preserve an active window."""
    return hmac.new(
        _RATE_KEY,
        client_address.encode("utf-8", errors="ignore"),
        hashlib.sha256,
    ).hexdigest()


def _data_file() -> Path:
    """SQLite path. Same data/ dir as history.db so prod paths stay
    consistent."""
    return Path(__file__).parent.parent / "data" / "waitlist.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS waitlist_signups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    email       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL,
    source      TEXT NOT NULL,
    utm_source  TEXT,
    utm_medium  TEXT,
    utm_campaign TEXT,
    utm_term    TEXT,
    utm_content TEXT,
    ip          TEXT,
    ua          TEXT
);
CREATE INDEX IF NOT EXISTS idx_waitlist_created_at
    ON waitlist_signups(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_waitlist_utm_source
    ON waitlist_signups(utm_source);
"""


def _connect() -> sqlite3.Connection:
    """Lazy-create the DB + schema. Each call is cheap (CREATE IF NOT EXISTS)."""
    f = _data_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(f), timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:  # pragma: no cover
        pass
    conn.executescript(_SCHEMA)
    return conn


def _check_rate_limit(ip: str, now: float, legacy_key: str | None = None) -> bool:
    """Return True iff under limit. Side-effect: appends `now` if accepted.

    Bucket is per-IP. testclient (FastAPI TestClient) reports 'testclient' as
    host — we still rate-limit it so the rate-limit-test path exercises the
    code; tests that need many signups should rotate IPs via header or reset
    the bucket via the helper below.
    """
    if legacy_key and legacy_key != ip and legacy_key in _rate_buckets:
        legacy = _rate_buckets.pop(legacy_key)
        current = _rate_buckets.setdefault(ip, deque())
        current.extend(legacy)
        _rate_buckets[ip] = deque(sorted(current))
    bucket = _rate_buckets.setdefault(ip, deque())
    # Evict old entries
    cutoff = now - _RATE_WINDOW_SEC
    while bucket and bucket[0] < cutoff:
        bucket.popleft()
    if len(bucket) >= _RATE_MAX:
        return False
    bucket.append(now)
    return True


def _reset_rate_limits() -> None:
    """Test helper — clear all buckets between tests."""
    _rate_buckets.clear()


class WaitlistBody(BaseModel):
    email: str
    source: Optional[str] = "homepage-hero"
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    utm_term: Optional[str] = None
    utm_content: Optional[str] = None


def _norm_utm(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    return s[:_MAX_UTM_LEN]


@router.post("/waitlist", status_code=503, response_model=SubscriptionUnavailableResponse)
async def waitlist(request: Request):
    """New Beta waitlist signups are unavailable; no body is consumed."""
    return unavailable_response("waitlist")


@router.get("/waitlist/count", status_code=503, response_model=SubscriptionUnavailableResponse)
async def count():
    """Do not open the legacy database or report a fabricated zero."""
    return unavailable_response("waitlist")
