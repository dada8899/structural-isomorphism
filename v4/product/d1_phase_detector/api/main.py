"""Phase Detector Screener FastAPI service.

Endpoints:
    GET /health
    GET /screener
    GET /company/{ticker}
    GET /stats

Run:
    .venv/bin/uvicorn v4.product.d1_phase_detector.api.main:app --reload --port 8000

Env:
    DB_URL  default sqlite:///<api>/../d1.sqlite
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .db import get_cursor, placeholder, row_to_dict

app = FastAPI(title="Phase Detector Screener API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


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
