-- D1 Phase Detector: waitlist signups (W8-D)
-- Postgres dialect. SQLite fallback uses 0002_waitlist_sqlite.sql.

CREATE TABLE IF NOT EXISTS waitlist (
    email TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'phase_detector',
    signed_up_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed BOOLEAN NOT NULL DEFAULT FALSE,
    -- Optional metadata: where on the page they signed up (e.g. hero, footer, thank-you).
    placement TEXT,
    -- Optional: arbitrary referrer / UTM dump for analytics.
    referrer TEXT
);

CREATE INDEX IF NOT EXISTS idx_waitlist_source ON waitlist(source);
CREATE INDEX IF NOT EXISTS idx_waitlist_signed_up_at ON waitlist(signed_up_at);
