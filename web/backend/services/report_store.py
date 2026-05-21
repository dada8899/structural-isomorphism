"""ReportStore — persisted analyze.py reports + share tokens + feedback.

Session ***REMOVED***16 / M1.4. PRD: `docs/sessions/M1.4-report-generator-prd.md`.

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


***REMOVED*** ---------------- Share token helpers --------------------------------- ***REMOVED***


def _share_secret() -> bytes:
    """Resolve the HMAC secret.

    Priority: STRUCTURAL_SHARE_TOKEN_SECRET env > deterministic dev
    fallback. In **prod** (STRUCTURAL_ENV=prod) the env MUST be set —
    we raise rather than silently fall back, because the fallback is
    predictable from cwd and the prod cwd is well-known
    (/root/Projects/structural-isomorphism/web/backend). Letting that
    secret leak by accident defeats the share-token capability model.

    Validator review (session ***REMOVED***16) found this fallback exploitable in
    prod; this guard closes the gap.
    """
    s = os.getenv("STRUCTURAL_SHARE_TOKEN_SECRET", "")
    if s:
        return s.encode("utf-8")
    env = os.getenv("STRUCTURAL_ENV", "dev").lower()
    if env == "prod":
        raise RuntimeError(
            "STRUCTURAL_SHARE_TOKEN_SECRET is not set in prod. "
            "Set it in /root/Projects/structural-isomorphism/web/backend/.env "
            "(stable across deploys — rotating breaks existing share URLs)."
        )
    ***REMOVED*** Dev / test fallback — deterministic per-cwd is fine here.
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


***REMOVED*** ---------------- Schema --------------------------------------------- ***REMOVED***


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

-- Session ***REMOVED***17 V6 — report → action → result revisit loop. One row per
-- (report_id, anon_id): the latest followup wins (upsert), so a user can
-- come back and update "我试过了 / 结果如何" without piling up rows.
CREATE TABLE IF NOT EXISTS report_followup (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   TEXT NOT NULL,
    anon_id     TEXT NOT NULL DEFAULT 'anon',
    -- action_status ∈ planned | in_progress | tried | abandoned
    action_status TEXT NOT NULL,
    -- outcome ∈ '' (not reported yet) | worked | partial | no_effect | too_early
    outcome     TEXT NOT NULL DEFAULT '',
    note        TEXT,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE,
    UNIQUE (report_id, anon_id)
);
CREATE INDEX IF NOT EXISTS idx_followup_report
    ON report_followup(report_id);

CREATE TABLE IF NOT EXISTS report_feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id   TEXT NOT NULL,
    -- section is '' for an overall-report vote (NOT NULL). SQLite treats
    -- NULL != NULL in UNIQUE indexes, so storing NULL here would silently
    -- let one voter accumulate multiple overall-votes. Validator review
    -- (session ***REMOVED***16) caught this; the conversion happens in record_feedback.
    section     TEXT NOT NULL DEFAULT '',
    vote        INTEGER NOT NULL CHECK(vote IN (-1, 1)),
    voter_anon  TEXT NOT NULL DEFAULT 'anon',
    note        TEXT,
    created_at  TEXT NOT NULL,
    FOREIGN KEY (report_id) REFERENCES reports(id) ON DELETE CASCADE,
    UNIQUE (report_id, voter_anon, section)
);
CREATE INDEX IF NOT EXISTS idx_feedback_report
    ON report_feedback(report_id);
"""


***REMOVED*** ---------------- ReportStore ---------------------------------------- ***REMOVED***


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
        ***REMOVED*** Foreign keys are off by default in sqlite3 — enable so the
        ***REMOVED*** ON DELETE CASCADE on report_feedback actually fires.
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as e:  ***REMOVED*** pragma: no cover
            logger.warning("report_store WAL pragma failed: %s", e)
        return conn

    ***REMOVED*** Columns the `reports` table MUST have. `CREATE TABLE IF NOT EXISTS`
    ***REMOVED*** is a no-op when the table already exists, so a `reports` table created
    ***REMOVED*** by an OLDER schema version silently keeps its old shape — any newer
    ***REMOVED*** column (creator_anon_id / is_partial / ...) would then be missing and
    ***REMOVED*** every INSERT would raise OperationalError. We additively self-heal via
    ***REMOVED*** ALTER TABLE so a long-lived history.db stays forward-compatible.
    ***REMOVED*** (col_name, sqlite column definition for ALTER TABLE ADD COLUMN)
    _REPORTS_COLUMNS = (
        ("share_token", "TEXT"),
        ("query", "TEXT"),
        ("rewritten_query", "TEXT"),
        ("b_id", "TEXT"),
        ("lang", "TEXT"),
        ("payload", "TEXT"),
        ("model", "TEXT"),
        ("prompt_version", "TEXT"),
        ("created_at", "TEXT"),
        ("creator_anon_id", "TEXT"),
        ("creator_tier", "TEXT"),
        ("is_public", "INTEGER NOT NULL DEFAULT 0"),
        ("view_count", "INTEGER NOT NULL DEFAULT 0"),
        ("last_viewed_at", "TEXT"),
        ("is_partial", "INTEGER NOT NULL DEFAULT 0"),
    )

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                ***REMOVED*** Migrate FIRST: on a drifted DB the `reports` table already
                ***REMOVED*** exists with an old shape, and `_SCHEMA` below contains a
                ***REMOVED*** `CREATE INDEX ... ON reports(creator_anon_id, ...)` that
                ***REMOVED*** would fail if that column is still missing. Backfilling
                ***REMOVED*** the columns before running `_SCHEMA` lets the index land.
                ***REMOVED*** On a fresh DB the table doesn't exist yet, so the migrate
                ***REMOVED*** step is a no-op (PRAGMA returns nothing) and `_SCHEMA`
                ***REMOVED*** creates everything from scratch.
                self._migrate_reports_columns(conn)
                conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            logger.exception("report_store schema init failed: %s", e)
            raise

    def _migrate_reports_columns(self, conn: sqlite3.Connection) -> None:
        """Additively backfill any `reports` columns missing on an older DB.

        Idempotent: only ADDs columns absent from PRAGMA table_info. Never
        drops or rewrites data. Without this, a `reports` table created by a
        pre-M1.4 schema version would lack creator_anon_id / is_partial and
        every persist would fail (then get swallowed by analyze.py's
        best-effort try/except — exactly the "report saved == lost" bug).
        """
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(reports)").fetchall()
        }
        if not existing:
            ***REMOVED*** Fresh table just created by _SCHEMA — nothing to migrate.
            return
        for col, col_def in self._REPORTS_COLUMNS:
            if col not in existing:
                logger.warning(
                    "report_store: reports table missing column %r — "
                    "adding via ALTER TABLE (schema drift self-heal)", col,
                )
                conn.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_def}")

    ***REMOVED*** ------ create / read ------------------------------------------- ***REMOVED***

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
        ***REMOVED*** Validator session-***REMOVED***16 P2 — cap payload at 256 KB. A real 9-section
        ***REMOVED*** report is ~30-50 KB; anything 5× that is almost certainly an
        ***REMOVED*** accident or attack. We raise rather than silently truncate so
        ***REMOVED*** the caller decides (analyze.py logs and continues without
        ***REMOVED*** tearing down the SSE stream).
        if len(payload_json.encode("utf-8")) > 256 * 1024:
            raise ValueError(
                f"report payload too large: {len(payload_json)} bytes > 256KB cap"
            )

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

        B Data Flywheel (Session ***REMOVED***18): each row also carries the SAME
        anon's followup summary (has_followup / followup_outcome) via a
        LEFT JOIN report_followup. We join on the same anon_id so the
        '未回访' badge reflects *this device's* revisit status, not some
        other reader's. Reports with no followup row → has_followup=0,
        followup_outcome=''.
        """
        if limit < 1 or limit > 200:
            limit = 50
        if offset < 0:
            offset = 0
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.query, r.b_id, r.lang, r.created_at,
                       r.view_count,
                       CASE WHEN f.report_id IS NULL THEN 0 ELSE 1 END
                           AS has_followup,
                       COALESCE(f.action_status, '') AS followup_status,
                       COALESCE(f.outcome, '')        AS followup_outcome
                FROM reports r
                LEFT JOIN report_followup f
                    ON f.report_id = r.id AND f.anon_id = ?
                WHERE r.creator_anon_id = ?
                ORDER BY r.created_at DESC
                LIMIT ? OFFSET ?
                """,
                (anon_id, anon_id, limit, offset),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["has_followup"] = bool(d.get("has_followup", 0))
            out.append(d)
        return out

    ***REMOVED*** ------ B Data Flywheel (Session ***REMOVED***18) -------------------------- ***REMOVED***

    def verified_isomorphisms(self, *, limit: int = 50) -> list[dict]:
        """Reports whose followup outcome == 'worked' — i.e. a real user
        came back and confirmed the borrowed structure actually helped.

        These are stronger evidence than LLM-rated v2_pairs: someone tried
        it and it worked. We aggregate per report (a report can be marked
        'worked' by several anons → verifier_count). `payload` is decoded
        so the caller can pull shared_structure / _credibility.
        """
        if limit < 1 or limit > 200:
            limit = 50
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.query, r.b_id, r.lang, r.payload,
                       r.created_at,
                       COUNT(f.id)        AS verifier_count,
                       MAX(f.updated_at)  AS last_verified_at
                FROM reports r
                JOIN report_followup f
                    ON f.report_id = r.id AND f.outcome = 'worked'
                GROUP BY r.id
                ORDER BY last_verified_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
            except json.JSONDecodeError:
                d["payload"] = {}
            out.append(d)
        return out

    def stuck_structures(self, *, limit: int = 20) -> list[dict]:
        """Aggregate which problem targets (b_id) users hit most.

        Per b_id: how many reports, how many got a followup, and the
        worked-rate among reports that have a followup. Surfaces 'the
        structures people keep getting stuck on'. Sorted by report_count.
        """
        if limit < 1 or limit > 200:
            limit = 20
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT r.b_id,
                       COUNT(DISTINCT r.id)         AS report_count,
                       COUNT(DISTINCT f.report_id)  AS followup_count,
                       SUM(CASE WHEN f.outcome = 'worked'
                                THEN 1 ELSE 0 END)  AS worked_count
                FROM reports r
                LEFT JOIN report_followup f ON f.report_id = r.id
                GROUP BY r.b_id
                ORDER BY report_count DESC, r.b_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["report_count"] = d.get("report_count", 0) or 0
            d["followup_count"] = d.get("followup_count", 0) or 0
            d["worked_count"] = d.get("worked_count", 0) or 0
            fc = d["followup_count"]
            d["worked_rate"] = (
                round(d["worked_count"] / fc, 3) if fc else 0.0
            )
            out.append(d)
        return out

    def insights_summary(self) -> dict:
        """Top-line counters for the insights dashboard. Empty DB → zeros."""
        with self._connect() as conn:
            total_reports = conn.execute(
                "SELECT COUNT(*) FROM reports"
            ).fetchone()[0]
            total_followups = conn.execute(
                "SELECT COUNT(*) FROM report_followup"
            ).fetchone()[0]
            worked = conn.execute(
                "SELECT COUNT(*) FROM report_followup WHERE outcome = 'worked'"
            ).fetchone()[0]
            ***REMOVED*** verified isomorphisms = distinct reports with a 'worked' followup
            verified = conn.execute(
                "SELECT COUNT(DISTINCT report_id) FROM report_followup "
                "WHERE outcome = 'worked'"
            ).fetchone()[0]
        return {
            "total_reports": total_reports or 0,
            "total_followups": total_followups or 0,
            "worked_count": worked or 0,
            "verified_isomorphisms": verified or 0,
        }

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

    ***REMOVED*** ------ feedback ----------------------------------------------- ***REMOVED***

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
        ***REMOVED*** Normalise None → '' so the UNIQUE index actually fires on
        ***REMOVED*** overall-report votes (SQLite treats NULL != NULL in unique
        ***REMOVED*** indexes; without this, repeated overall votes by one voter
        ***REMOVED*** accumulate instead of upserting). Validator session-***REMOVED***16 P1.
        section_norm = section if section is not None else ""
        voter_norm = voter_anon if voter_anon is not None else "anon"
        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._connect() as conn:
            ***REMOVED*** Use INSERT ... ON CONFLICT to upsert.
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
                (report_id, section_norm, vote, voter_norm, note, now),
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

    ***REMOVED*** ------ followup (Session ***REMOVED***17 V6) ------------------------------ ***REMOVED***

    ***REMOVED*** Allowed enum values — validated here so a bad client value never
    ***REMOVED*** lands in the DB. The API layer validates too (defence in depth).
    ACTION_STATUSES = ("planned", "in_progress", "tried", "abandoned")
    OUTCOMES = ("", "worked", "partial", "no_effect", "too_early")

    def record_followup(
        self,
        *,
        report_id: str,
        anon_id: Optional[str],
        action_status: str,
        outcome: str = "",
        note: Optional[str] = None,
    ) -> dict:
        """Idempotent upsert of a revisit record on (report_id, anon_id).

        Re-submitting updates the existing row (latest wins) and preserves
        the original created_at. Returns the stored followup dict.
        """
        if action_status not in self.ACTION_STATUSES:
            raise ValueError(
                f"action_status must be one of {self.ACTION_STATUSES}"
            )
        outcome = outcome or ""
        if outcome not in self.OUTCOMES:
            raise ValueError(f"outcome must be one of {self.OUTCOMES}")
        anon_norm = anon_id if anon_id else "anon"
        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._connect() as conn:
            ***REMOVED*** created_at is set on first insert only; the upsert keeps it.
            conn.execute(
                """
                INSERT INTO report_followup (
                    report_id, anon_id, action_status, outcome, note,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, anon_id) DO UPDATE SET
                    action_status = excluded.action_status,
                    outcome = excluded.outcome,
                    note = excluded.note,
                    updated_at = excluded.updated_at
                """,
                (report_id, anon_norm, action_status, outcome, note, now, now),
            )
            row = conn.execute(
                """
                SELECT report_id, anon_id, action_status, outcome, note,
                       created_at, updated_at
                FROM report_followup
                WHERE report_id = ? AND anon_id = ?
                """,
                (report_id, anon_norm),
            ).fetchone()
        return dict(row) if row else {}

    def get_followup(
        self, report_id: str, anon_id: Optional[str],
    ) -> Optional[dict]:
        """Return this anon's followup for the report, or None."""
        anon_norm = anon_id if anon_id else "anon"
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT report_id, anon_id, action_status, outcome, note,
                       created_at, updated_at
                FROM report_followup
                WHERE report_id = ? AND anon_id = ?
                """,
                (report_id, anon_norm),
            ).fetchone()
        return dict(row) if row else None

    ***REMOVED*** ------ internals --------------------------------------------- ***REMOVED***

    def _row_to_dict(self, row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        d = dict(row)
        ***REMOVED*** Decode JSON payload eagerly so callers can treat it as a dict.
        try:
            d["payload"] = json.loads(d["payload"]) if d["payload"] else {}
        except json.JSONDecodeError:
            logger.warning("report_store: bad JSON payload for %s", d.get("id"))
            d["payload"] = {}
        d["is_public"] = bool(d.get("is_public", 0))
        d["is_partial"] = bool(d.get("is_partial", 0))
        return d
