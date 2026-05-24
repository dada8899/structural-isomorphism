"""
POST /api/waitlist — W7-D mini-brief 1 (2026-05-24).

Email collection for the "weekly structural signals" newsletter. Distinct from
`/api/newsletter/subscribe` (which is the beta-site essay-end newsletter) — this
is the homepage Pro/Phase-Detector waitlist that ALSO captures UTM source for
acquisition-channel attribution.

Storage: SQLite (independent table `waitlist_signups` in `data/waitlist.db`).
Schema:
    waitlist_signups(
        id INTEGER PRIMARY KEY,
        email TEXT NOT NULL UNIQUE,
        created_at TEXT NOT NULL,          -- ISO 8601, UTC
        source TEXT NOT NULL,              -- placement id (homepage-hero, phase-footer, ...)
        utm_source TEXT,
        utm_medium TEXT,
        utm_campaign TEXT,
        utm_term TEXT,
        utm_content TEXT,
        ip TEXT,
        ua TEXT
    )

Why SQLite vs JSONL (newsletter.py uses JSONL):
    - We expect waitlist to grow into the auth/user table later — SQLite gives
      us free UNIQUE constraint, indexable queries, easy migration path.
    - Newsletter JSONL is OK to leave alone (semantic separation).

Body (JSON):
    {
        "email": "user@example.com",
        "source": "homepage-hero",
        "utm_source": "twitter",        ***REMOVED*** optional
        "utm_medium": "tweet",          ***REMOVED*** optional
        "utm_campaign": "phase-launch", ***REMOVED*** optional
        "utm_term": "",                 ***REMOVED*** optional
        "utm_content": ""               ***REMOVED*** optional
    }

Response:
    200  { "ok": true,  "created": true,  "email": "<normalized>" }
    200  { "ok": true,  "created": false, "email": "<normalized>" }   ***REMOVED*** duplicate
    400  { "ok": false, "error": "invalid email" }
    400  { "ok": false, "error": "invalid source" }
    429  { "ok": false, "error": "rate_limited" }
"""
from __future__ import annotations

import datetime as _dt
import logging
import re
import sqlite3
import time
from collections import deque
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(tags=["waitlist"])
logger = logging.getLogger("structural.waitlist")

***REMOVED*** Pragmatic RFC-5322-ish — same shape as newsletter.py for consistency.
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

***REMOVED*** Whitelist placements so the table stays auditable. Add here when adding new
***REMOVED*** CTAs (keep in sync with frontend mountWaitlist calls).
_ALLOWED_SOURCES = {
    "homepage-hero",
    "homepage-bottom",
    "phase-footer",
    "pricing-page",
    "test",  ***REMOVED*** for tests only — filter out in analytics
}

_MAX_EMAIL_LEN = 200
_MAX_SOURCE_LEN = 60
_MAX_UTM_LEN = 200

***REMOVED*** Rate limit: 5 signups per IP per 10 minutes. Cheap in-memory ring buffer.
_RATE_WINDOW_SEC = 600
_RATE_MAX = 5
_rate_buckets: dict[str, deque] = {}


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
    except sqlite3.Error:  ***REMOVED*** pragma: no cover
        pass
    conn.executescript(_SCHEMA)
    return conn


def _check_rate_limit(ip: str, now: float) -> bool:
    """Return True iff under limit. Side-effect: appends `now` if accepted.

    Bucket is per-IP. testclient (FastAPI TestClient) reports 'testclient' as
    host — we still rate-limit it so the rate-limit-test path exercises the
    code; tests that need many signups should rotate IPs via header or reset
    the bucket via the helper below.
    """
    bucket = _rate_buckets.setdefault(ip, deque())
    ***REMOVED*** Evict old entries
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


@router.post("/waitlist")
async def waitlist(body: WaitlistBody, request: Request):
    email = (body.email or "").strip().lower()
    source = (body.source or "homepage-hero").strip().lower()
    ip = request.client.host if request.client else "?"

    ***REMOVED*** --- Validation ---
    if not email or len(email) > _MAX_EMAIL_LEN or not _EMAIL_RE.match(email):
        return JSONResponse(
            {"ok": False, "error": "invalid email"}, status_code=400
        )
    if len(source) > _MAX_SOURCE_LEN or source not in _ALLOWED_SOURCES:
        return JSONResponse(
            {"ok": False, "error": "invalid source"}, status_code=400
        )

    ***REMOVED*** --- Rate limit ---
    if not _check_rate_limit(ip, time.time()):
        logger.info("waitlist rate_limited: ip=%s", ip)
        return JSONResponse(
            {"ok": False, "error": "rate_limited"}, status_code=429
        )

    utm_source = _norm_utm(body.utm_source)
    utm_medium = _norm_utm(body.utm_medium)
    utm_campaign = _norm_utm(body.utm_campaign)
    utm_term = _norm_utm(body.utm_term)
    utm_content = _norm_utm(body.utm_content)

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat(
        sep=" ", timespec="seconds"
    )
    ua = (request.headers.get("user-agent") or "")[:300]

    try:
        with _connect() as conn:
            try:
                conn.execute(
                    "INSERT INTO waitlist_signups "
                    "(email, created_at, source, utm_source, utm_medium, "
                    " utm_campaign, utm_term, utm_content, ip, ua) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        email, created_at, source,
                        utm_source, utm_medium, utm_campaign,
                        utm_term, utm_content, ip, ua,
                    ),
                )
                conn.commit()
                logger.info(
                    "waitlist signup: email=%s source=%s utm_source=%s",
                    email, source, utm_source,
                )
                return JSONResponse(
                    {"ok": True, "created": True, "email": email}
                )
            except sqlite3.IntegrityError:
                ***REMOVED*** UNIQUE constraint on email — duplicate is *not* an error.
                logger.info("waitlist duplicate: email=%s source=%s", email, source)
                return JSONResponse(
                    {"ok": True, "created": False, "email": email}
                )
    except sqlite3.Error as e:
        logger.error("waitlist storage failure: %s", e)
        return JSONResponse(
            {"ok": False, "error": "storage failure"}, status_code=500
        )


@router.get("/waitlist/count")
async def count():
    """Public count — used by social-proof widgets ("join 1,234 analysts...").
    Cheap at our scale; refactor to cache if hot."""
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM waitlist_signups"
            ).fetchone()
            n = int(row["n"] if row else 0)
            return JSONResponse({"count": n})
    except sqlite3.Error as e:  ***REMOVED*** pragma: no cover
        logger.error("waitlist count failed: %s", e)
        return JSONResponse({"count": 0})
