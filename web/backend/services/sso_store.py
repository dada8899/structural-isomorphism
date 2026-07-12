"""Transactional replay ledger for cross-origin account exchange codes."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path


class SsoReplayStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS consumed_sso_codes("
                "jti TEXT PRIMARY KEY, consumed_at INTEGER NOT NULL, expires_at INTEGER NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS issued_sso_codes("
                "jti TEXT PRIMARY KEY, subject_id TEXT NOT NULL, tier TEXT NOT NULL, "
                "expires_at INTEGER NOT NULL, consumed_at INTEGER)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS revoked_sso_subjects("
                "subject_id TEXT PRIMARY KEY, revoked_at INTEGER NOT NULL)"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def consume_once(self, jti: str, expires_at: int) -> bool:
        """Atomically consume a non-expired code identifier exactly once."""
        now = int(time.time())
        if not jti or expires_at < now:
            return False
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM consumed_sso_codes WHERE expires_at < ?", (now,))
            inserted = conn.execute(
                "INSERT OR IGNORE INTO consumed_sso_codes(jti,consumed_at,expires_at) "
                "VALUES(?,?,?)", (jti, now, expires_at),
            ).rowcount
            conn.commit()
            return inserted == 1

    def issue(self, jti: str, subject_id: str, tier: str, expires_at: int) -> None:
        if not jti or not subject_id:
            raise ValueError("jti and subject_id are required")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO issued_sso_codes(jti,subject_id,tier,expires_at) VALUES(?,?,?,?)",
                (jti, subject_id, tier, expires_at),
            )

    def consume_issued(self, jti: str) -> dict | None:
        now = int(time.time())
        if not jti:
            return None
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT subject_id,tier,expires_at,consumed_at FROM issued_sso_codes WHERE jti=?",
                (jti,),
            ).fetchone()
            if not row or row[3] is not None or int(row[2]) < now:
                conn.rollback()
                return None
            updated = conn.execute(
                "UPDATE issued_sso_codes SET consumed_at=? WHERE jti=? AND consumed_at IS NULL",
                (now, jti),
            ).rowcount
            conn.commit()
        return {"subject_id": row[0], "tier": row[1]} if updated == 1 else None

    def revoke_subject(self, subject_id: str, revoked_at: int | None = None) -> int:
        if not subject_id:
            raise ValueError("subject_id is required")
        epoch = time.time_ns() if revoked_at is None else int(revoked_at)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO revoked_sso_subjects(subject_id,revoked_at) VALUES(?,?) "
                "ON CONFLICT(subject_id) DO UPDATE SET revoked_at=MAX(revoked_at,excluded.revoked_at)",
                (subject_id, epoch),
            )
        return epoch

    def subject_revoked_at(self, subject_id: str) -> int | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT revoked_at FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,)
            ).fetchone()
        return int(row[0]) if row else None

    def restore_subject_revocation(self, subject_id: str, previous: int | None, applied: int) -> None:
        """Compensate only our own epoch; never erase a newer concurrent revoke."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT revoked_at FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,)
            ).fetchone()
            if row and int(row[0]) == applied:
                if previous is None:
                    conn.execute("DELETE FROM revoked_sso_subjects WHERE subject_id=?", (subject_id,))
                else:
                    conn.execute(
                        "UPDATE revoked_sso_subjects SET revoked_at=? WHERE subject_id=?",
                        (previous, subject_id),
                    )
            conn.commit()
