"""Transactional SQLite storage for passwordless authentication."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS auth_users (
                    email TEXT PRIMARY KEY, tier TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS magic_tokens (
                    token_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS revoked_sessions (
                    jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_rate_requests (
                    email TEXT NOT NULL, requested_at INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_auth_rate
                    ON auth_rate_requests(email, requested_at);
                CREATE TABLE IF NOT EXISTS auth_notification_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL, email TEXT NOT NULL,
                    created_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT, delivered_at TEXT, claimed_at INTEGER,
                    UNIQUE(kind, email)
                );
            """)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    def record_rate_request(self, email: str, limit: int, window_seconds: int = 3600) -> bool:
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM auth_rate_requests WHERE requested_at < ?", (now - window_seconds,))
            count = conn.execute(
                "SELECT COUNT(*) FROM auth_rate_requests WHERE email=? AND requested_at>=?",
                (email, now - window_seconds),
            ).fetchone()[0]
            if count >= limit:
                conn.rollback()
                return False
            conn.execute("INSERT INTO auth_rate_requests VALUES (?, ?)", (email, now))
            conn.commit()
            return True

    def add_token(self, token_hash: str, email: str, created_at: str, expires_at: str) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO magic_tokens(token_hash,email,created_at,expires_at) VALUES(?,?,?,?)",
                (token_hash, email, created_at, expires_at),
            )

    def consume_token(self, token_hash: str, consumed_at: str) -> tuple[Optional[dict], str]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM magic_tokens WHERE token_hash=?", (token_hash,)).fetchone()
            if not row:
                conn.rollback()
                return None, "invalid"
            if row["consumed_at"]:
                conn.rollback()
                return None, "used"
            updated = conn.execute(
                "UPDATE magic_tokens SET consumed_at=? WHERE token_hash=? AND consumed_at IS NULL",
                (consumed_at, token_hash),
            ).rowcount
            if updated != 1:
                conn.rollback()
                return None, "used"
            conn.commit()
            return dict(row), "ok"

    def ensure_user_and_notification(self, email: str, tier: str, created_at: str) -> tuple[dict, bool]:
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            created = conn.execute(
                "INSERT OR IGNORE INTO auth_users(email,tier,created_at) VALUES(?,?,?)",
                (email, tier, created_at),
            ).rowcount == 1
            user = dict(conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone())
            if created:
                conn.execute(
                    "INSERT OR IGNORE INTO auth_notification_outbox(kind,email,created_at) VALUES('new_user',?,?)",
                    (email, created_at),
                )
            conn.commit()
            return user, created

    def user(self, email: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone()
            return dict(row) if row else None

    def revoke(self, jti: str, revoked_at: str) -> None:
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO revoked_sessions VALUES(?,?)", (jti, revoked_at))

    def is_revoked(self, jti: str) -> bool:
        with self._connection() as conn:
            return conn.execute("SELECT 1 FROM revoked_sessions WHERE jti=?", (jti,)).fetchone() is not None

    def claim_notifications(self, limit: int = 50) -> list[dict]:
        now = int(time.time())
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                "SELECT * FROM auth_notification_outbox WHERE delivered_at IS NULL "
                "AND (claimed_at IS NULL OR claimed_at<?) ORDER BY id LIMIT ?",
                (now - 300, limit),
            ).fetchall()
            ids = [row["id"] for row in rows]
            if ids:
                marks = ",".join("?" for _ in ids)
                conn.execute(
                    f"UPDATE auth_notification_outbox SET claimed_at=? WHERE id IN ({marks})",
                    (now, *ids),
                )
            conn.commit()
            return [dict(row) for row in rows]

    def pending_notification_count(self) -> int:
        with self._connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM auth_notification_outbox WHERE delivered_at IS NULL"
            ).fetchone()[0]

    def mark_notification(self, item_id: int, *, delivered_at: Optional[str], error: Optional[str]) -> None:
        with self._connection() as conn:
            conn.execute(
                "UPDATE auth_notification_outbox SET attempts=attempts+1,last_error=?,delivered_at=?,claimed_at=NULL WHERE id=?",
                (error, delivered_at, item_id),
            )
