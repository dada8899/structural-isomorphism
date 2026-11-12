"""D1 full-stack integration tests.

In-process FastAPI TestClient against a fresh SQLite-backed schema, seeded
from a slimmed sample of the real `sample_structtuples.jsonl` artifact (so
we verify the data shape produced by the LLM pipeline survives the
extractor → schema → API path).
"""

from __future__ import annotations

import importlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_DIR = Path(__file__).resolve().parents[1]  # v4/product/d1_phase_detector
MIGRATION = PROJECT_DIR / "migrations" / "0001_companies_structtuples_sqlite.sql"
SAMPLE_JSONL = PROJECT_DIR / "sample_structtuples.jsonl"


def _build_rows_from_jsonl(jsonl_path: Path, limit: int = 5) -> list[dict]:
    """Convert sample extractor output into d1_companies row shape.

    The extractor writes {ticker, struct_tuple: {...}, ...} records; the API
    DB stores a flat row. Mirror the field mapping that the real ingester
    would do.
    """
    rows: list[dict] = []
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if not rec.get("ok"):
                continue
            st = rec.get("struct_tuple") or {}
            rows.append(
                {
                    "ticker": st.get("ticker") or rec["ticker"],
                    "name": st.get("company_name") or rec["ticker"],
                    "sector": None,
                    "industry": None,
                    "market_cap_usd_b": None,
                    "dynamics_family": st.get("dynamics_family", "mixed_or_unclear"),
                    "critical_point_state": st.get("critical_point_state", "unknown"),
                    "universality_class": None,
                    "extraction_confidence": st.get("confidence"),
                    "extraction_model": "deepseek-v4-pro",
                    "extracted_at": st.get("as_of_date", "2026-05-13") + "T00:00:00Z",
                    "tldr": st.get("structural_summary", "")[:200],
                    "primary_indicators": st.get("early_warning_indicators"),
                    "caveats": None,
                    "raw_response": None,
                }
            )
            if len(rows) >= limit:
                break
    return rows


def _seed(db_path: Path, rows: list[dict]) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(MIGRATION.read_text())
        for r in rows:
            params = dict(r)
            if isinstance(params.get("extracted_at"), datetime):
                params["extracted_at"] = params["extracted_at"].isoformat()
            params["primary_indicators"] = (
                json.dumps(params["primary_indicators"])
                if params.get("primary_indicators") is not None
                else None
            )
            params["raw_response"] = (
                json.dumps(params["raw_response"]) if params.get("raw_response") is not None else None
            )
            conn.execute(
                """
                INSERT INTO d1_companies (
                    ticker, name, sector, industry, market_cap_usd_b,
                    dynamics_family, critical_point_state, universality_class,
                    extraction_confidence, extraction_model, extracted_at,
                    tldr, primary_indicators, caveats, raw_response
                ) VALUES (
                    :ticker, :name, :sector, :industry, :market_cap_usd_b,
                    :dynamics_family, :critical_point_state, :universality_class,
                    :extraction_confidence, :extraction_model, :extracted_at,
                    :tldr, :primary_indicators, :caveats, :raw_response
                )
                """,
                params,
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def client(tmp_path, monkeypatch):
    if not SAMPLE_JSONL.exists():
        pytest.skip(f"missing sample_structtuples.jsonl at {SAMPLE_JSONL}")
    rows = _build_rows_from_jsonl(SAMPLE_JSONL, limit=10)
    if not rows:
        pytest.skip("no successful rows in sample_structtuples.jsonl")
    db_path = tmp_path / "d1_integration.sqlite"
    _seed(db_path, rows)
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")

    import v4.product.d1_phase_detector.api.db as db_mod
    import v4.product.d1_phase_detector.api.main as main_mod
    importlib.reload(db_mod)
    importlib.reload(main_mod)
    return TestClient(main_mod.app), rows


# ---------------------------------------------------------------------------
# End-to-end pipeline shape
# ---------------------------------------------------------------------------


def test_real_pipeline_data_loads(client):
    """Sample LLM extractor output round-trips through the API schema."""
    c, rows = client
    r = c.get("/screener")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == len(rows)
    # All tickers from JSONL appear in response
    expected = {row["ticker"] for row in rows}
    got = {i["ticker"] for i in items}
    assert expected == got


def test_real_pipeline_stats_aggregation(client):
    c, rows = client
    r = c.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(rows)
    # Sum of by_dynamics_family equals total (assuming all rows have non-null dynamics_family)
    fam_total = sum(body["by_dynamics_family"].values())
    assert fam_total == body["total"]


def test_real_pipeline_company_detail(client):
    c, rows = client
    first = rows[0]
    r = c.get(f"/company/{first['ticker']}")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == first["ticker"]
    assert body["dynamics_family"] == first["dynamics_family"]


def test_real_pipeline_filter_by_dynamics(client):
    c, rows = client
    # Pick the most common dynamics_family in the sample
    families = [r["dynamics_family"] for r in rows]
    from collections import Counter

    most_common, _count = Counter(families).most_common(1)[0]
    r = c.get("/screener", params={"dynamics_family": most_common})
    assert r.status_code == 200
    for item in r.json():
        assert item["dynamics_family"] == most_common


# ---------------------------------------------------------------------------
# CORS / OPTIONS
# ---------------------------------------------------------------------------


def test_cors_preflight_get_allowed(client):
    """OPTIONS preflight should include GET in allow-methods."""
    c, _ = client
    r = c.options(
        "/screener",
        headers={
            "Origin": "https://phase.bytedance.city",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Some test clients return 200/204 for preflight depending on middleware
    assert r.status_code in (200, 204)
    allowed = r.headers.get("access-control-allow-methods", "")
    assert "GET" in allowed


# ---------------------------------------------------------------------------
# Health probe
# ---------------------------------------------------------------------------


def test_health_with_loaded_db(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
