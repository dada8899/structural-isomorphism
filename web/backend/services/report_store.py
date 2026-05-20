"""ReportStore — persisted analyze.py reports + share tokens + feedback.

Session #16 / M1.4. PRD: `docs/sessions/M1.4-report-generator-prd.md`.

Schema (added to existing `history.db`):
    reports          — one row per persisted analyze report
    report_feedback  — section-level 👍/👎 votes

Design choices:
  * Same SQLite file as history (single-file simplicity wins over
    cross-DB joins, of which we have none).
  * WAL mode (already enabled by HistoryDB; we just re-PRAGMA on our
    connections).
  * Report IDs are short opaque strings ("r_" + 16 hex chars).
  * Share tokens are HMAC-SHA256(report_id, SECRET) truncated to 32 hex
    chars — anyone-with-link semantics; not revocable in v1.
  * payload is stored as JSON-text; we never push it through SQL queries
    (no full-text search in v1, just `WHERE id = ?` lookups).

We do NOT support multi-tenant ACL in v1. The list_by_anon filter is a
soft-privacy / convenience feature (cookies expire, people switch devices),
NOT a security boundary. Anyone with the share_token can read the report.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------- Share token helpers --------------------------------- #


def _share_secret() -> bytes:
    """Resolve the HMAC secret.

    Priority: STRUCTURAL_SHARE_TOKEN_SECRET env > derived-from-DB-path
    fallback (deterministic but not committed). In prod we set the env;
    in tests / dev we want a usable default rather than a hard error.
    """
    s = os.getenv("STRUCTURAL_SHARE_TOKEN_SECRET", "")
    if s:
        return s.encode("utf-8")
    # Deterministic dev default — does NOT leak between machines because
    # every cwd hashes differently. Acceptable for local dev / tests.
    fallback = f"dev-share-secret-{Path.cwd()}".encode("utf-8")
    return hashlib.sha256(fallback).digest()


def sign_share_token(report_id: str) -> str:
    """Return a 32-hex-char HMAC token for `report_id`."""
    return hmac.new(_share_secret(), report_id.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def verify_share_token(report_id: str, token: str) -> bool:
    """Constant-time check that `token` is a valid HMAC for `report_id`."""
    expected = sign_share_token(report_id)
    return hmac.compare_digest(expected, token or "")


def new_report_id() -> str:
    """Mint a fresh opaque report id ('r_' + 16 hex chars)."""
    return "r_" + secrets.token_hex(8)


# ---------------- Schema --------------------------------------------- #


_SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
    id              TEXT PRIMARY KEY,
    share_token     TEXT UNIQUE NOT NULL,
    query           TEXT NOT NULL,
    rewritten_query TEXT,
    b_id            TEXT NOT NULL,
    lang            TEXT NOT NULL,
    payload         TEXT NOT NULL,
    model           TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    creator_anon_id TEXT,
    creator_tier    TEXT,
    is_public       INTEGER NOT NULL DEFAULT 0,
    view_count      INTEGER NOT NULL DEFAULT 0,
    last_viewed_at  TEXT,
    is_partial      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reports_anon
    ON reports(creator_anon_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_reports_share_token
    ON reports(share_token);

CREATE TABLE IF NOT EXISTS report_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   TEXT NOT NULL,
    section     TEXT,
    vote        INTEGER NOT NULL CHECK(vote IN (-1, 1)),
    voter_anon  TEXT,
    note        TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE,
    UNIQUE (report_id, voter_anon, section)
);
CREATE INDEX IF NOT EXISTS idx_feedback_report
    ON report_feedback(report_id);
"""


# ---------------- ReportStore ---------------------------------------- #


class ReportStore:
    """Thin SQLite wrapper for persisted analyze.py reports + feedback.

    Auto-creates parent dir and schema on init. Reuses the existing
    history.db file when given the same path.
    """

    def __init__(self, db_path: Path | str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        # Foreign keys are off by default in sqlite3 — enable so the
        # ON DELETE CASCADE on report_feedback actually fires.
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as e:  # pragma: no cover
            logger.warning("report_store WAL pragma failed: %s", e)
        return conn

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            logger.exception("report_store schema init failed: %s", e)
            raise

    # ------ create / read ------------------------------------------- #

    def create(
        self,
        *,
        query: str,
        b_id: str,
        lang: str,
        payload: dict,
        model: str,
        prompt_version: str = "v1",
        rewritten_query: Optional[str] = None,
        creator_anon_id: Optional[str] = None,
        creator_tier: Optional[str] = None,
        is_public: bool = False,
        is_partial: bool = False,
    ) -> dict:
        """Insert a new report row, return {id, share_token, share_url-less dict}.

        Caller is responsible for ensuring `payload` is JSON-serialisable
        (we serialise it here with ensure_ascii=False to keep zh / en
        characters intact).
        """
        rid = new_report_id()
        token = sign_share_token(rid)
        created_at = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        payload_json = json.dumps(payload, ensure_ascii=False)

        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO reports (
                        id, share_token, query, rewritten_query, b_id, lang,
                        payload, model, prompt_version, created_at,
                        creator_anon_id, creator_tier, is_public, is_partial
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        rid, token, query, rewritten_query, b_id, lang,
                        payload_json, model, prompt_version, created_at,
                        creator_anon_id, creator_tier,
                        1 if is_public else 0, 1 if is_partial else 0,
                    ),
                )
        except sqlite3.Error as e:
            logger.exception("report_store.create failed: %s", e)
            raise

        return {
            "id": rid,
            "share_token": token,
            "created_at": created_at,
        }

    def get_by_id(self, rid: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE id = ?", (rid,)
            ).fetchone()
        return self._row_to_dict(row)

    def get_by_share_token(self, token: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM reports WHERE share_token = ?", (token,)
            ).fetchone()
        return self._row_to_dict(row)

    def list_by_anon(
        self, anon_id: str, *, limit: int = 50, offset: int = 0,
    ) -> list[dict]:
        """List recent reports created by this anon-id.

        Convenience for the 'My Reports' page. NOT a security boundary
        — anyone with a share_token can still read.
        """
        if limit < 1 or limit > 200:
            limit = 50
        if offset < 0:
            offset = 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, query, b_id, lang, created_at, view_count
                FROM reports
                WHERE creator_anon_id = ?
                ORDER BY created_at DESC
                LIMIT ? OFFSET ?
                """,
                (anon_id, limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def record_view(self, rid: str) -> None:
        """Bump view_count + last_viewed_at. Best-effort, never raises."""
        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        try:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE reports SET view_count = view_count + 1, "
                    "last_viewed_at = ? WHERE id = ?",
                    (now, rid),
                )
        except sqlite3.Error:
            logger.exception("record_view failed for %s", rid)

    # ------ feedback ----------------------------------------------- #

    def record_feedback(
        self,
        *,
        report_id: str,
        section: Optional[str],
        vote: int,
        voter_anon: Optional[str],
        note: Optional[str] = None,
    ) -> dict:
        """Idempotent upsert on (report_id, voter_anon, section).

        Returns the up/down counts after the write.
        """
        if vote not in (-1, 1):
            raise ValueError("vote must be -1 or +1")
        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._connect() as conn:
            # Use INSERT ... ON CONFLICT to upsert.
            conn.execute(
                """
                INSERT INTO report_feedback (
                    report_id, section, vote, voter_anon, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, voter_anon, section) DO UPDATE SET
                    vote = excluded.vote,
                    note = excluded.note,
                    created_at = excluded.created_at
                """,
                (report_id, section, vote, voter_anon, note, now),
            )
            counts = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN vote = 1 THEN 1 ELSE 0 END) AS up,
                    SUM(CASE WHEN vote = -1 THEN 1 ELSE 0 END) AS down
                FROM report_feedback
                WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
        return {
            "total_up": counts["up"] or 0,
            "total_down": counts["down"] or 0,
        }

    def feedback_counts(self, report_id: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN vote = 1 THEN 1 ELSE 0 END) AS up,
                    SUM(CASE WHEN vote = -1 THEN 1 ELSE 0 END) AS down
                FROM report_feedback
                WHERE report_id = ?
                """,
                (report_id,),
            ).fetchone()
        return {
            "total_up": (row["up"] if row else 0) or 0,
            "total_down": (row["down"] if row else 0) or 0,
        }

    # ------ internals --------------------------------------------- #

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        # Decode JSON payload eagerly so callers can treat it as a dict.
        try:
            d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        except json.JSONDecodeError:
            logger.warning("report_store: bad JSON payload for %s", d.get("id"))
            d["payload"] = {}
        d["is_public"] = bool(d.get("is_public", 0))
        d["is_partial"] = bool(d.get("is_partial", 0))
        return d
