-- D1 Phase Detector: companies + StructTuple core schema
-- Postgres dialect. For SQLite fallback, use migrations/0001_companies_structtuples_sqlite.sql

CREATE TABLE IF NOT EXISTS d1_companies (
    ticker TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    sector TEXT,
    industry TEXT,
    market_cap_usd_b NUMERIC,
    -- StructTuple core fields
    dynamics_family TEXT NOT NULL,         -- e.g. 'soc', 'preferential_attachment', 'fold', 'hysteresis', 'linear_quasi_equilibrium'
    critical_point_state TEXT NOT NULL,    -- 'subcritical', 'near_critical', 'supercritical', 'tipped', 'far_from_critical'
    universality_class TEXT,               -- e.g. 'soc_threshold_cascade'
    -- Confidence + provenance
    extraction_confidence NUMERIC,
    extraction_model TEXT,
    extracted_at TIMESTAMPTZ NOT NULL,
    -- TL;DR + caveat
    tldr TEXT,
    primary_indicators JSONB,
    caveats TEXT,
    -- Raw
    raw_response JSONB
);

CREATE INDEX IF NOT EXISTS idx_d1_dynamics_family ON d1_companies(dynamics_family);
CREATE INDEX IF NOT EXISTS idx_d1_critical_point_state ON d1_companies(critical_point_state);
CREATE INDEX IF NOT EXISTS idx_d1_universality_class ON d1_companies(universality_class);
CREATE INDEX IF NOT EXISTS idx_d1_sector ON d1_companies(sector);
