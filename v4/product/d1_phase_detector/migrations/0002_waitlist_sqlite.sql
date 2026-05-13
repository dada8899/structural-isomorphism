-- D1 Phase Detector: waitlist signups (W8-D), SQLite fallback.
-- TIMESTAMPTZ -> TEXT (ISO 8601). BOOLEAN -> INTEGER 0/1.

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
