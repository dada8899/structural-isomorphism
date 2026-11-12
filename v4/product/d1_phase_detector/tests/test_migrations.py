"""Test the D1 SQLite migration applies cleanly to a fresh DB.

We only test the sqlite variant — the postgres variant requires a running
server and is exercised in real-env deployment.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

PROJECT_DIR = Path(__file__).resolve().parents[1]
MIG_SQLITE = PROJECT_DIR / "migrations" / "0001_companies_structtuples_sqlite.sql"
MIG_PG = PROJECT_DIR / "migrations" / "0001_companies_structtuples.sql"


@pytest.fixture
def db(tmp_path):
    db_path = tmp_path / "d1_mig.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(MIG_SQLITE.read_text())
    conn.commit()
    yield conn
    conn.close()


def test_migration_creates_table(db):
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert "d1_companies" in tables


def test_migration_columns(db):
    cur = db.execute("PRAGMA table_info(d1_companies)")
    cols = {r[1]: r[2] for r in cur.fetchall()}  # name -> type
    required = {
        "ticker", "name", "sector", "industry", "market_cap_usd_b",
        "dynamics_family", "critical_point_state", "universality_class",
        "extraction_confidence", "extraction_model", "extracted_at",
        "tldr", "primary_indicators", "caveats", "raw_response",
    }
    missing = required - set(cols.keys())
    assert not missing, f"migration missing columns: {missing}"


def test_migration_indexes(db):
    cur = db.execute("SELECT name FROM sqlite_master WHERE type='index'")
    idx_names = {r[0] for r in cur.fetchall() if r[0]}
    for expected in (
        "idx_d1_dynamics_family",
        "idx_d1_critical_point_state",
        "idx_d1_universality_class",
        "idx_d1_sector",
    ):
        assert expected in idx_names, f"missing index {expected}"


def test_primary_key_is_ticker(db):
    cur = db.execute("PRAGMA table_info(d1_companies)")
    pk_cols = [r[1] for r in cur.fetchall() if r[5] == 1]  # cid 5 = pk flag
    assert pk_cols == ["ticker"]


def test_insert_basic_row(db):
    db.execute(
        """
        INSERT INTO d1_companies (
            ticker, name, dynamics_family, critical_point_state, extracted_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("TEST", "Test Co", "preferential_attachment", "far_from_critical",
         "2026-05-13T00:00:00Z"),
    )
    db.commit()
    cur = db.execute("SELECT ticker FROM d1_companies WHERE ticker='TEST'")
    assert cur.fetchone()[0] == "TEST"


def test_insert_duplicate_ticker_fails(db):
    db.execute(
        """
        INSERT INTO d1_companies (
            ticker, name, dynamics_family, critical_point_state, extracted_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("DUP", "Dup Co", "fold", "approaching_critical", "2026-05-13T00:00:00Z"),
    )
    db.commit()
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            """
            INSERT INTO d1_companies (
                ticker, name, dynamics_family, critical_point_state, extracted_at
            ) VALUES (?, ?, ?, ?, ?)
            """,
            ("DUP", "Dup Co 2", "soc", "at_critical", "2026-05-13T00:00:00Z"),
        )
        db.commit()


def test_upsert_via_on_conflict(db):
    """SQLite supports INSERT ... ON CONFLICT DO UPDATE syntax."""
    db.execute(
        """
        INSERT INTO d1_companies (
            ticker, name, dynamics_family, critical_point_state, extracted_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        ("UPS", "v1", "soc", "approaching_critical", "2026-05-13T00:00:00Z"),
    )
    db.commit()
    db.execute(
        """
        INSERT INTO d1_companies (
            ticker, name, dynamics_family, critical_point_state, extracted_at
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            name = excluded.name,
            dynamics_family = excluded.dynamics_family
        """,
        ("UPS", "v2", "fold", "at_critical", "2026-05-13T00:00:00Z"),
    )
    db.commit()
    cur = db.execute("SELECT name, dynamics_family FROM d1_companies WHERE ticker='UPS'")
    name, fam = cur.fetchone()
    assert name == "v2"
    assert fam == "fold"


def test_jsonb_text_storage(db):
    """SQLite stores JSON as TEXT; we just verify round-trip."""
    payload = {"ar1_trend": "rising", "variance_trend": "stable"}
    db.execute(
        """
        INSERT INTO d1_companies (
            ticker, name, dynamics_family, critical_point_state, extracted_at, primary_indicators
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("JSN", "JsonCo", "soc", "approaching_critical",
         "2026-05-13T00:00:00Z", json.dumps(payload)),
    )
    db.commit()
    cur = db.execute("SELECT primary_indicators FROM d1_companies WHERE ticker='JSN'")
    raw = cur.fetchone()[0]
    parsed = json.loads(raw)
    assert parsed == payload


# ---------------------------------------------------------------------------
# Postgres migration syntactic smoke (no DB needed)
# ---------------------------------------------------------------------------


def test_pg_migration_file_exists_and_nonempty():
    """We can't apply pg DDL to sqlite, but verify file integrity."""
    assert MIG_PG.exists()
    text = MIG_PG.read_text()
    assert "CREATE TABLE" in text.upper()
    assert "d1_companies" in text
    # Must have the same canonical columns
    for col in (
        "ticker", "dynamics_family", "critical_point_state",
        "extraction_confidence", "extracted_at",
    ):
        assert col in text, f"pg migration missing column {col}"
