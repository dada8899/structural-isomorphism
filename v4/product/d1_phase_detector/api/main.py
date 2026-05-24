"""Phase Detector Screener FastAPI service.

Endpoints:
    GET  /health
    GET  /screener
    GET  /company/{ticker}
    GET  /stats
    POST /api/waitlist           (W8-D: waitlist signup, form-encoded)
    GET  /api/waitlist/count     (W8-D: public count)

Run:
    .venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --reload --port 8000

Env:
    DB_URL              default sqlite:///<api>/../d1.sqlite
    BUTTONDOWN_API_KEY  optional; if set, waitlist signups also POST to Buttondown
"""

from __future__ import annotations

import os
import re
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Optional

from fastapi import FastAPI, Form, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import get_cursor, placeholder, row_to_dict
from .universality import router as universality_router


# W8-D: ensure waitlist table exists on startup (idempotent).
# Mirrors migrations/0002_waitlist*.sql but inline so tests + dev don't
# need a separate migrate step.
_WAITLIST_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS waitlist (
    email TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'phase_detector',
    signed_up_at TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed INTEGER NOT NULL DEFAULT 0,
    placement TEXT,
    referrer TEXT
);
CREATE INDEX IF NOT EXISTS idx_waitlist_source ON waitlist(source);
CREATE INDEX IF NOT EXISTS idx_waitlist_signed_up_at ON waitlist(signed_up_at);
"""

_WAITLIST_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS waitlist (
    email TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'phase_detector',
    signed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    placement TEXT,
    referrer TEXT
);
CREATE INDEX IF NOT EXISTS idx_waitlist_source ON waitlist(source);
CREATE INDEX IF NOT EXISTS idx_waitlist_signed_up_at ON waitlist(signed_up_at);
"""


def _ensure_waitlist_table() -> None:
    try:
        with get_cursor() as (cur, driver):
            ddl = _WAITLIST_DDL_SQLITE if driver == "sqlite" else _WAITLIST_DDL_POSTGRES
            if driver == "sqlite":
                cur.executescript(ddl)
            else:
                cur.execute(ddl)
    except Exception:  # pragma: no cover -- never block app boot on DDL race
        pass


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # startup: idempotent waitlist DDL (replaces deprecated @app.on_event("startup")).
    _ensure_waitlist_table()
    yield
    # shutdown: nothing to clean up currently.


app = FastAPI(
    title="Phase Detector Screener API",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # W8-D: include POST so /api/waitlist preflights succeed from main site.
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
# W10-E: /api/universality/* endpoints (class list + detail + companies-by-class)
app.include_router(universality_router)


# -------- pydantic models --------


class CompanyTuple(BaseModel):
    ticker: str
    name: str
    sector: Optional[str] = None
    industry: Optional[str] = None
    market_cap_usd_b: Optional[float] = None
    dynamics_family: str
    critical_point_state: str
    universality_class: Optional[str] = None
    extraction_confidence: Optional[float] = None
    extraction_model: Optional[str] = None
    extracted_at: Optional[str] = None
    tldr: Optional[str] = None
    primary_indicators: Optional[dict[str, Any]] = None
    caveats: Optional[str] = None


class StatsResponse(BaseModel):
    total: int
    by_dynamics_family: dict[str, int]
    by_critical_point_state: dict[str, int]
    by_universality_class: dict[str, int] = Field(default_factory=dict)
    by_sector: dict[str, int] = Field(default_factory=dict)


# W8-D: waitlist models.


class WaitlistSignupResponse(BaseModel):
    status: str
    msg: str
    # W8-D: returned so frontend can decide whether to fire `waitlist_signup`
    # Plausible event (only on first signup, not duplicates).
    created: bool


class WaitlistCountResponse(BaseModel):
    count: int


# W8-D: email regex. Deliberately permissive but rules out obvious garbage.
# We do *not* try to be RFC 5322-perfect; backend stays cheap, frontend already
# uses <input type="email"> for the strict-enough check.
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
# Whitelist sources to keep the column clean (avoids garbage from manual curl).
_ALLOWED_SOURCES = frozenset(
    {"phase_detector", "main_site", "thank_you_share", "footer", "hero"}
)


# -------- helpers --------


SELECT_COLS = (
    "ticker, name, sector, industry, market_cap_usd_b, "
    "dynamics_family, critical_point_state, universality_class, "
    "extraction_confidence, extraction_model, extracted_at, "
    "tldr, primary_indicators, caveats"
)


def _normalize_company(rowdict: dict[str, Any]) -> dict[str, Any]:
    """Apply final shaping for CompanyTuple (cast Decimal / datetime / etc.)."""
    d = dict(rowdict)
    # cast Decimal -> float
    for k in ("market_cap_usd_b", "extraction_confidence"):
        v = d.get(k)
        if v is not None and not isinstance(v, (int, float)):
            try:
                d[k] = float(v)
            except (TypeError, ValueError):
                d[k] = None
    ea = d.get("extracted_at")
    if ea is not None and not isinstance(ea, str):
        try:
            d["extracted_at"] = ea.isoformat()
        except AttributeError:
            d["extracted_at"] = str(ea)
    return d


# -------- routes --------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/screener", response_model=list[CompanyTuple])
def screener(
    dynamics_family: Optional[str] = Query(None),
    critical_point_state: Optional[str] = Query(None),
    universality_class: Optional[str] = Query(None),
    sector: Optional[str] = Query(None),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    limit: int = Query(50, ge=1, le=500),
) -> list[CompanyTuple]:
    where: list[str] = []
    params: list[Any] = []

    with get_cursor() as (cur, driver):
        ph = placeholder(driver)
        if dynamics_family is not None:
            where.append(f"dynamics_family = {ph}")
            params.append(dynamics_family)
        if critical_point_state is not None:
            where.append(f"critical_point_state = {ph}")
            params.append(critical_point_state)
        if universality_class is not None:
            where.append(f"universality_class = {ph}")
            params.append(universality_class)
        if sector is not None:
            where.append(f"sector = {ph}")
            params.append(sector)
        if min_confidence > 0:
            where.append(f"(extraction_confidence IS NOT NULL AND extraction_confidence >= {ph})")
            params.append(min_confidence)

        where_sql = ("WHERE " + " AND ".join(where)) if where else ""
        sql = (
            f"SELECT {SELECT_COLS} FROM d1_companies "
            f"{where_sql} "
            f"ORDER BY extraction_confidence DESC NULLS LAST, ticker ASC "
            f"LIMIT {ph}"
        )
        # SQLite doesn't support NULLS LAST natively in all versions, but modern (>=3.30) does.
        # Defensive: if it raises, retry without NULLS LAST.
        try:
            cur.execute(sql, params + [limit])
            rows = cur.fetchall()
        except Exception:
            sql2 = sql.replace(" NULLS LAST", "")
            cur.execute(sql2, params + [limit])
            rows = cur.fetchall()

        return [CompanyTuple(**_normalize_company(row_to_dict(r, driver))) for r in rows]


@app.get("/company/{ticker}", response_model=CompanyTuple)
def company_detail(ticker: str) -> CompanyTuple:
    with get_cursor() as (cur, driver):
        ph = placeholder(driver)
        cur.execute(
            f"SELECT {SELECT_COLS} FROM d1_companies WHERE ticker = {ph}",
            (ticker.upper(),),
        )
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"ticker={ticker} not found")
        return CompanyTuple(**_normalize_company(row_to_dict(row, driver)))


@app.get("/stats", response_model=StatsResponse)
def stats() -> StatsResponse:
    with get_cursor() as (cur, driver):
        cur.execute("SELECT COUNT(*) AS n FROM d1_companies")
        n_row = cur.fetchone()
        total = (n_row["n"] if driver == "postgres" else n_row[0]) if n_row else 0

        def _group_by(col: str) -> dict[str, int]:
            cur.execute(
                f"SELECT {col} AS k, COUNT(*) AS n FROM d1_companies "
                f"WHERE {col} IS NOT NULL GROUP BY {col}"
            )
            out: dict[str, int] = {}
            for r in cur.fetchall():
                if driver == "postgres":
                    k, v = r["k"], r["n"]
                else:
                    k, v = r[0], r[1]
                if k is not None:
                    out[str(k)] = int(v)
            return out

        return StatsResponse(
            total=int(total),
            by_dynamics_family=_group_by("dynamics_family"),
            by_critical_point_state=_group_by("critical_point_state"),
            by_universality_class=_group_by("universality_class"),
            by_sector=_group_by("sector"),
        )


# -------- W8-D waitlist routes --------


def _maybe_forward_buttondown(email: str, source: str) -> None:
    """Best-effort POST to Buttondown subscriber API. Never raises.

    Buttondown account / API key are not provisioned yet (see
    docs/newsletter/buttondown-setup.md). This is wired so that once
    BUTTONDOWN_API_KEY env var is set, signups flow through automatically.
    """
    api_key = os.environ.get("BUTTONDOWN_API_KEY")
    if not api_key:
        return
    try:
        import httpx  # type: ignore

        httpx.post(
            "https://api.buttondown.email/v1/subscribers",
            headers={"Authorization": f"Token {api_key}"},
            json={"email_address": email, "tags": [source]},
            timeout=4.0,
        )
    except Exception:
        # Newsletter forwarding is best-effort; storage is the source of truth.
        pass


@app.post("/api/waitlist", response_model=WaitlistSignupResponse)
def waitlist_signup(
    email: str = Form(...),
    source: str = Form("phase_detector"),
    placement: Optional[str] = Form(None),
    referrer: Optional[str] = Form(None),
) -> WaitlistSignupResponse:
    """Capture an email + source into the waitlist table.

    Idempotent: re-signing the same email returns `created=false` instead of 4xx,
    so the frontend can show a friendly "you're already on the list" message.
    """
    email_norm = email.strip().lower()
    if not _EMAIL_RE.match(email_norm):
        raise HTTPException(status_code=422, detail="invalid email")
    if source not in _ALLOWED_SOURCES:
        source = "phase_detector"

    created = False
    with get_cursor() as (cur, driver):
        ph = placeholder(driver)
        cur.execute(f"SELECT 1 FROM waitlist WHERE email = {ph}", (email_norm,))
        existing = cur.fetchone()
        if existing is None:
            if driver == "sqlite":
                cur.execute(
                    "INSERT INTO waitlist (email, source, placement, referrer) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph})",
                    (email_norm, source, placement, referrer),
                )
            else:
                cur.execute(
                    "INSERT INTO waitlist (email, source, placement, referrer) "
                    f"VALUES ({ph}, {ph}, {ph}, {ph}) ON CONFLICT (email) DO NOTHING",
                    (email_norm, source, placement, referrer),
                )
            # rowcount can be -1 on some drivers; treat as success if no existing row.
            created = True

    if created:
        _maybe_forward_buttondown(email_norm, source)
        return WaitlistSignupResponse(
            status="ok", msg="On the list — see you in your inbox.", created=True
        )
    return WaitlistSignupResponse(
        status="ok", msg="You're already on the list.", created=False
    )


@app.get("/api/waitlist/count", response_model=WaitlistCountResponse)
def waitlist_count() -> WaitlistCountResponse:
    with get_cursor() as (cur, driver):
        cur.execute("SELECT COUNT(*) AS n FROM waitlist")
        row = cur.fetchone()
        n = (row["n"] if driver == "postgres" else row[0]) if row else 0
        return WaitlistCountResponse(count=int(n))
