-- D1 Phase Detector: SQLite fallback schema
-- Mirrors 0001_companies_structtuples.sql but with SQLite-compatible types.
-- JSONB -> TEXT (we store JSON-serialized strings).
-- TIMESTAMPTZ -> TEXT (ISO 8601).
-- NUMERIC -> REAL.

CREATE TABLE IF NOT EXISTS d1_companies (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    market_cap_usd_b REAL,
    dynamics_family TEXT NOT NULL,
    critical_point_state TEXT NOT NULL,
    universality_class TEXT,
    extraction_confidence REAL,
    extraction_model TEXT,
    extracted_at TEXT NOT NULL,
    tldr TEXT,
    primary_indicators TEXT,  -- JSON string
    caveats TEXT,
    raw_response TEXT          -- JSON string
);

CREATE INDEX IF NOT EXISTS idx_d1_dynamics_family ON d1_companies(dynamics_family);
CREATE INDEX IF NOT EXISTS idx_d1_critical_point_state ON d1_companies(critical_point_state);
CREATE INDEX IF NOT EXISTS idx_d1_universality_class ON d1_companies(universality_class);
CREATE INDEX IF NOT EXISTS idx_d1_sector ON d1_companies(sector);
