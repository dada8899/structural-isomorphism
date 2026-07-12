"""Transactional SQLite storage for passwordless authentication."""
from __future__ import annotations

import hashlib
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional


class DeletedCredentialError(ValueError):
    """A credential predates the owner's latest account deletion."""


class AuthStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS auth_users (
                    email TEXT PRIMARY KEY, tier TEXT NOT NULL, created_at TEXT NOT NULL,
                    session_generation TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS magic_tokens (
                    token_hash TEXT PRIMARY KEY, email TEXT NOT NULL,
                    created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    consumed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS revoked_sessions (
                    jti TEXT PRIMARY KEY, revoked_at TEXT NOT NULL, email TEXT
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
                CREATE TABLE IF NOT EXISTS account_deletion_epochs (
                    owner_hash TEXT PRIMARY KEY, deleted_at TEXT NOT NULL
                );
            """)
            revoked_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(revoked_sessions)").fetchall()
            }
            if "email" not in revoked_columns:
                conn.execute("ALTER TABLE revoked_sessions ADD COLUMN email TEXT")
            user_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(auth_users)").fetchall()
            }
            if "session_generation" not in user_columns:
                conn.execute("ALTER TABLE auth_users ADD COLUMN session_generation TEXT")
                conn.execute(
                    "UPDATE auth_users SET session_generation=lower(hex(randomblob(16))) "
                    "WHERE session_generation IS NULL"
                )
            epoch_columns = {
                row[1] for row in conn.execute("PRAGMA table_info(account_deletion_epochs)").fetchall()
            }
            if "email" in epoch_columns:
                # Migrate the brief pre-release schema without retaining raw
                # deleted-account identifiers in the security marker.
                conn.execute("BEGIN IMMEDIATE")
                try:
                    rows = conn.execute(
                        "SELECT email,deleted_at FROM account_deletion_epochs"
                    ).fetchall()
                    conn.execute(
                        "ALTER TABLE account_deletion_epochs "
                        "RENAME TO account_deletion_epochs_raw"
                    )
                    conn.execute(
                        "CREATE TABLE account_deletion_epochs("
                        "owner_hash TEXT PRIMARY KEY,deleted_at TEXT NOT NULL)"
                    )
                    conn.executemany(
                        "INSERT INTO account_deletion_epochs(owner_hash,deleted_at) VALUES(?,?)",
                        [(_email_hash(row["email"]), row["deleted_at"]) for row in rows],
                    )
                    conn.execute("DROP TABLE account_deletion_epochs_raw")
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA journal_mode=WAL")
        # Account erasure must also clear deleted payloads from SQLite pages,
        # not merely unlink rows into the freelist.
        conn.execute("PRAGMA secure_delete=ON")
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
                "INSERT OR IGNORE INTO auth_users(email,tier,created_at,session_generation) "
                "VALUES(?,?,?,lower(hex(randomblob(16))))",
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

    def ensure_user_from_token(
        self, email: str, tier: str, created_at: str, token_created_at: str,
    ) -> tuple[dict, bool]:
        """Create/login atomically unless the credential predates deletion."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            epoch = conn.execute(
                "SELECT deleted_at FROM account_deletion_epochs WHERE owner_hash=?",
                (_email_hash(email),),
            ).fetchone()
            if epoch and token_created_at <= epoch["deleted_at"]:
                conn.rollback()
                raise DeletedCredentialError("credential predates account deletion")
            created = conn.execute(
                "INSERT OR IGNORE INTO auth_users(email,tier,created_at,session_generation) "
                "VALUES(?,?,?,lower(hex(randomblob(16))))",
                (email, tier, created_at),
            ).rowcount == 1
            user = dict(conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone())
            if created:
                conn.execute(
                    "INSERT OR IGNORE INTO auth_notification_outbox(kind,email,created_at) "
                    "VALUES('new_user',?,?)", (email, created_at),
                )
            conn.commit()
            return user, created

    def user(self, email: str) -> Optional[dict]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM auth_users WHERE email=?", (email,)).fetchone()
            return dict(row) if row else None

    def export_account_data(self, email: str) -> dict:
        """Return every auth-store row linked to ``email``, excluding hashes."""
        with self._connection() as conn:
            user = conn.execute(
                "SELECT email,tier,created_at FROM auth_users WHERE email=?", (email,)
            ).fetchone()
            tokens = conn.execute(
                "SELECT created_at,expires_at,consumed_at FROM magic_tokens "
                "WHERE email=? ORDER BY created_at", (email,)
            ).fetchall()
            notifications = conn.execute(
                "SELECT kind,created_at,attempts,last_error,delivered_at "
                "FROM auth_notification_outbox WHERE email=? ORDER BY id", (email,)
            ).fetchall()
            revocations = conn.execute(
                "SELECT revoked_at FROM revoked_sessions WHERE email=? ORDER BY revoked_at",
                (email,),
            ).fetchall()
            deletion_epoch = conn.execute(
                "SELECT deleted_at FROM account_deletion_epochs WHERE owner_hash=?",
                (_email_hash(email),),
            ).fetchone()
            return {
                "account": dict(user) if user else None,
                "magic_link_events": [dict(row) for row in tokens],
                "registration_notifications": [dict(row) for row in notifications],
                "revoked_session_events": [dict(row) for row in revocations],
                "prior_deletion_security_event": (
                    {"deleted_at": deletion_epoch["deleted_at"], "retention": "security"}
                    if deletion_epoch else None
                ),
            }

    def delete_account_data(self, email: str) -> dict:
        """Atomically remove all auth rows linked to an account."""
        with self._connection() as conn:
            conn.execute("BEGIN IMMEDIATE")
            deleted_at = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO account_deletion_epochs(owner_hash,deleted_at) VALUES(?,?) "
                "ON CONFLICT(owner_hash) DO UPDATE SET deleted_at=excluded.deleted_at",
                (_email_hash(email), deleted_at),
            )
            counts = {
                "magic_link_events": conn.execute(
                    "DELETE FROM magic_tokens WHERE email=?", (email,)
                ).rowcount,
                "registration_notifications": conn.execute(
                    "DELETE FROM auth_notification_outbox WHERE email=?", (email,)
                ).rowcount,
                "rate_limit_events": conn.execute(
                    "DELETE FROM auth_rate_requests WHERE email=?", (email,)
                ).rowcount,
                "revoked_session_events": conn.execute(
                    "DELETE FROM revoked_sessions WHERE email=?", (email,)
                ).rowcount,
                "account": conn.execute(
                    "DELETE FROM auth_users WHERE email=?", (email,)
                ).rowcount,
                "security_deletion_epoch": "retained without raw email",
            }
            conn.commit()
            return counts

    def revoke(self, jti: str, revoked_at: str, email: Optional[str] = None) -> None:
        with self._connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO revoked_sessions(jti,revoked_at,email) VALUES(?,?,?)",
                (jti, revoked_at, email),
            )

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


def _email_hash(email: str) -> str:
    return hashlib.sha256(email.strip().lower().encode("utf-8")).hexdigest()
