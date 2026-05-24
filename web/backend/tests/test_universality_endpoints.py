"""Tests for the W10-E /api/universality/* endpoints.

The endpoints are registered on the Phase Detector backend
(`v4/product/d1_phase_detector/api/main.py`). The frontend at
`web/phase-detector/` consumes them via NEXT_PUBLIC_API_BASE.

Each test gets:
  * an isolated SQLite DB seeded with a few companies tagged with
    real `universality_class` slugs from the YAML taxonomy,
  * the canonical taxonomy directory under `dataset/v1/taxonomy/`
    (no fixturing — we trust the YAML in the repo).

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/backend/tests/test_universality_endpoints.py -v
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make sure project root + d1_phase_detector are importable when this test
# is collected from `web/backend/tests/`.
PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MIGRATION = (
    PROJECT_ROOT
    / "v4"
    / "product"
    / "d1_phase_detector"
    / "migrations"
    / "0001_companies_structtuples_sqlite.sql"
)


def _seed_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(MIGRATION.read_text())
        rows = _sample_rows()
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
                json.dumps(params["raw_response"])
                if params.get("raw_response") is not None
                else None
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


def _sample_rows():
    now = datetime(2026, 5, 15, tzinfo=timezone.utc)
    return [
        dict(
            ticker="LEH", name="Lehman Brothers", sector="finance",
            industry="investment_bank", market_cap_usd_b=0.1,
            dynamics_family="soc_threshold_cascade",
            critical_point_state="post_critical_transition",
            universality_class="soc_threshold_cascade",
            extraction_confidence=0.92, extraction_model="test-model",
            extracted_at=now, tldr="Cascade exemplar.",
            primary_indicators={"ar1_trend": "rising"}, caveats=None,
            raw_response=None,
        ),
        dict(
            ticker="GME", name="GameStop Corp.", sector="retail",
            industry="game_retail", market_cap_usd_b=8.0,
            dynamics_family="soc_threshold_cascade",
            critical_point_state="approaching_critical",
            universality_class="soc_threshold_cascade",
            extraction_confidence=0.55, extraction_model="test-model",
            extracted_at=now, tldr="Short squeeze.",
            primary_indicators={"variance_trend": "rising"}, caveats=None,
            raw_response=None,
        ),
        dict(
            ticker="AAPL", name="Apple Inc.", sector="tech_hardware",
            industry="consumer_electronics", market_cap_usd_b=3500.0,
            dynamics_family="preferential_attachment",
            critical_point_state="far_from_critical",
            universality_class="preferential_attachment",
            extraction_confidence=0.85, extraction_model="test-model",
            extracted_at=now, tldr="Network-effect ecosystem.",
            primary_indicators={"ar1_trend": "stable"}, caveats=None,
            raw_response=None,
        ),
        dict(
            ticker="UNKNOWN_CLASS_CO", name="Unknown Class Co",
            sector="misc", industry=None, market_cap_usd_b=0.5,
            dynamics_family="mixed_or_unclear",
            critical_point_state="unknown",
            universality_class="does_not_exist_in_taxonomy",
            extraction_confidence=0.30, extraction_model="test-model",
            extracted_at=now, tldr="Untagged.",
            primary_indicators=None, caveats=None,
            raw_response=None,
        ),
    ]


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "d1.sqlite"
    _seed_db(db_path)
    monkeypatch.setenv("DB_URL", f"sqlite:///{db_path}")
    # Reload modules so DB_URL is picked up + class loader cache is fresh.
    import v4.product.d1_phase_detector.api.db as db_mod
    import v4.product.d1_phase_detector.api.universality as uni_mod
    import v4.product.d1_phase_detector.api.main as main_mod
    importlib.reload(db_mod)
    importlib.reload(uni_mod)
    importlib.reload(main_mod)
    # Bust the lru_cache so taxonomy is re-loaded under monkeypatched env.
    main_mod.universality_router  # noqa: B018 -- side-effect: ensure registered
    uni_mod._load_all_classes.cache_clear()
    return TestClient(main_mod.app)


# ---------- /api/universality/classes ----------


def test_list_classes_returns_count_and_array(client):
    r = client.get("/api/universality/classes")
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert "classes" in body
    assert isinstance(body["classes"], list)
    # Should have at least 12 classes (umbrella file alone has 12; with
    # per-class files we expect 20+).
    assert body["count"] >= 12, f"only {body['count']} classes loaded"


def test_list_classes_card_shape(client):
    r = client.get("/api/universality/classes")
    cards = r.json()["classes"]
    sample = cards[0]
    for key in ("class_id", "display_name", "definition", "status",
                "exponent_band", "evidence_count"):
        assert key in sample, f"card missing {key}: {sample.keys()}"
    # Status sort: well-established or emerging should bubble first.
    statuses = [c["status"] for c in cards]
    # Find first speculative — every well-established/emerging should be earlier.
    if "speculative" in statuses and "well-established" in statuses:
        first_spec = statuses.index("speculative")
        last_well = max(
            (i for i, s in enumerate(statuses) if s == "well-established"),
            default=-1,
        )
        assert last_well < first_spec, "speculative leaked above well-established"


def test_list_classes_contains_known_class(client):
    r = client.get("/api/universality/classes")
    ids = {c["class_id"] for c in r.json()["classes"]}
    # These are known to exist in the taxonomy (per-class file + umbrella).
    assert "soc_threshold_cascade" in ids
    assert "preferential_attachment" in ids


# ---------- /api/universality/classes/{class_id} ----------


def test_class_detail_hit(client):
    r = client.get("/api/universality/classes/preferential_attachment")
    assert r.status_code == 200
    body = r.json()
    assert body["class_id"] == "preferential_attachment"
    assert body["definition"]
    assert isinstance(body["key_invariants"], list)
    assert isinstance(body["evidence_systems"], list)
    assert isinstance(body["references"], list)
    assert isinstance(body["negative_examples"], list)


def test_class_detail_404(client):
    r = client.get("/api/universality/classes/does_not_exist_at_all")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"]


def test_class_detail_soc_loads_via_umbrella_fallback(client):
    """soc_threshold_cascade per-class YAML has a known parse bug at line
    55, but the umbrella file `universality_classes.yaml` covers it.
    The endpoint must still serve the class via umbrella fallback."""
    r = client.get("/api/universality/classes/soc_threshold_cascade")
    assert r.status_code == 200
    body = r.json()
    assert body["class_id"] == "soc_threshold_cascade"
    assert body["definition"], "soc must have a non-empty definition"


# ---------- /api/universality/companies/{class_id} ----------


def test_companies_for_class_returns_matches(client):
    r = client.get("/api/universality/companies/soc_threshold_cascade")
    assert r.status_code == 200
    body = r.json()
    assert body["class_id"] == "soc_threshold_cascade"
    assert body["count"] == 2
    tickers = {c["ticker"] for c in body["companies"]}
    assert tickers == {"LEH", "GME"}
    # Sort: highest extraction_confidence first.
    assert body["companies"][0]["ticker"] == "LEH"


def test_companies_for_class_empty_for_unmatched(client):
    """A real taxonomy class with no companies in the seeded DB returns
    count=0, not 404."""
    # Pick a class that exists in taxonomy but isn't on any seed company.
    r = client.get("/api/universality/companies/kuramoto_sync")
    # Either 200 with empty list (class exists in umbrella YAML) or 404
    # if taxonomy load failed. Class exists in umbrella so expect 200.
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["companies"] == []


def test_companies_for_class_404_on_unknown_taxonomy(client):
    r = client.get("/api/universality/companies/totally_made_up_class")
    assert r.status_code == 404
