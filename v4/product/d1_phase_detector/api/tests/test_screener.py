"""Tests for the Phase Detector Screener API.

Strategy:
- Each test gets an isolated SQLite DB file in a tmp dir.
- We point DB_URL to that path BEFORE importing the app (env-driven), seed fixture
  rows directly via sqlite3, and use FastAPI's TestClient.
"""

from __future__ import annotations

import importlib
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PROJECT_DIR = Path(__file__).resolve().parents[2]  # v4/product/d1_phase_detector
MIGRATION = PROJECT_DIR / "migrations" / "0001_companies_structtuples_sqlite.sql"


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


def _sample_rows() -> list[dict]:
    now = datetime(2026, 5, 13, tzinfo=timezone.utc)
    return [
        dict(
            ticker="AAPL", name="Apple Inc.", sector="tech_hardware", industry="consumer_electronics",
            market_cap_usd_b=3500.0,
            dynamics_family="preferential_attachment", critical_point_state="far_from_critical",
            universality_class="bose_einstein_network",
            extraction_confidence=0.85, extraction_model="test-model",
            extracted_at=now,
            tldr="Apple ecosystem network effect.",
            primary_indicators={"ar1_trend": "stable"}, caveats=None,
            raw_response={"foo": "bar"},
        ),
        dict(
            ticker="BBY", name="Best Buy Co. Inc.", sector="retail", industry="electronics_retail",
            market_cap_usd_b=20.0,
            dynamics_family="linear_quasi_equilibrium", critical_point_state="far_from_critical",
            universality_class=None,
            extraction_confidence=0.85, extraction_model="test-model",
            extracted_at=now,
            tldr="Best Buy mean-reverting retail.",
            primary_indicators=None, caveats=None,
            raw_response=None,
        ),
        dict(
            ticker="LEH", name="Lehman Brothers", sector="finance", industry="investment_bank",
            market_cap_usd_b=0.1,
            dynamics_family="soc", critical_point_state="tipped",
            universality_class="soc_threshold_cascade",
            extraction_confidence=0.92, extraction_model="test-model",
            extracted_at=now,
            tldr="Lehman cascade exemplar.",
            primary_indicators={"ar1_trend": "rising"}, caveats="historical post-2008",
            raw_response={"hist": True},
        ),
        dict(
            ticker="GME", name="GameStop Corp.", sector="retail", industry="game_retail",
            market_cap_usd_b=8.0,
            dynamics_family="soc", critical_point_state="near_critical",
            universality_class="soc_threshold_cascade",
            extraction_confidence=0.55, extraction_model="test-model",
            extracted_at=now,
            tldr="GME short-squeeze meta.",
            primary_indicators={"variance_trend": "rising"}, caveats="meme-stock noise",
            raw_response=None,
        ),
        dict(
            ticker="LOWCONF", name="LowConf Co", sector="misc", industry=None,
            market_cap_usd_b=1.0,
            dynamics_family="fold", critical_point_state="subcritical",
            universality_class=None,
            extraction_confidence=0.1, extraction_model="test-model",
            extracted_at=now,
            tldr="Low confidence row for filter test.",
            primary_indicators=None, caveats=None,
            raw_response=None,
        ),
    ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "d1.sqlite"
    _seed(db_path, _sample_rows())
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")

    # reload the api modules so they pick up the new DB_URL
    import v4.product.d1_phase_detector.api.db as db_mod
    import v4.product.d1_phase_detector.api.main as main_mod
    importlib.reload(db_mod)
    importlib.reload(main_mod)
    return TestClient(main_mod.app)


# ---------- /health ----------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


# ---------- /stats ----------


def test_stats(client):
    r = client.get("/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert body["by_dynamics_family"]["soc"] == 2
    assert body["by_dynamics_family"]["preferential_attachment"] == 1
    assert body["by_critical_point_state"]["tipped"] == 1
    assert body["by_critical_point_state"]["far_from_critical"] == 2
    assert body["by_sector"]["retail"] == 2
    assert body["by_universality_class"]["soc_threshold_cascade"] == 2


# ---------- /screener ----------


def test_screener_no_filter(client):
    r = client.get("/screener")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 5
    # ordered by confidence desc
    assert items[0]["ticker"] == "LEH"
    assert items[0]["extraction_confidence"] == 0.92


def test_screener_filter_dynamics_family(client):
    r = client.get("/screener", params={"dynamics_family": "soc"})
    assert r.status_code == 200
    tickers = {i["ticker"] for i in r.json()}
    assert tickers == {"LEH", "GME"}


def test_screener_filter_combo(client):
    r = client.get(
        "/screener",
        params={"dynamics_family": "soc", "critical_point_state": "tipped"},
    )
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["ticker"] == "LEH"


def test_screener_filter_sector(client):
    r = client.get("/screener", params={"sector": "retail"})
    assert r.status_code == 200
    tickers = {i["ticker"] for i in r.json()}
    assert tickers == {"BBY", "GME"}


def test_screener_filter_universality_class(client):
    r = client.get("/screener", params={"universality_class": "soc_threshold_cascade"})
    assert r.status_code == 200
    tickers = {i["ticker"] for i in r.json()}
    assert tickers == {"LEH", "GME"}


def test_screener_min_confidence(client):
    r = client.get("/screener", params={"min_confidence": 0.8})
    assert r.status_code == 200
    tickers = {i["ticker"] for i in r.json()}
    # LEH 0.92, AAPL 0.85, BBY 0.85
    assert tickers == {"LEH", "AAPL", "BBY"}


def test_screener_limit(client):
    r = client.get("/screener", params={"limit": 2})
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2


def test_screener_limit_validation(client):
    r = client.get("/screener", params={"limit": 0})
    assert r.status_code == 422
    r = client.get("/screener", params={"limit": 501})
    assert r.status_code == 422


def test_screener_min_confidence_validation(client):
    r = client.get("/screener", params={"min_confidence": 1.5})
    assert r.status_code == 422
    r = client.get("/screener", params={"min_confidence": -0.1})
    assert r.status_code == 422


def test_screener_empty_result(client):
    r = client.get("/screener", params={"dynamics_family": "no_such_family"})
    assert r.status_code == 200
    assert r.json() == []


# ---------- /company/{ticker} ----------


def test_company_detail_hit(client):
    r = client.get("/company/LEH")
    assert r.status_code == 200
    body = r.json()
    assert body["ticker"] == "LEH"
    assert body["dynamics_family"] == "soc"
    assert body["primary_indicators"] == {"ar1_trend": "rising"}


def test_company_detail_case_insensitive(client):
    r = client.get("/company/leh")
    assert r.status_code == 200
    assert r.json()["ticker"] == "LEH"


def test_company_detail_404(client):
    r = client.get("/company/NOPE")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


# ---------- CORS ----------


def test_cors_headers(client):
    r = client.get(
        "/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "*"
