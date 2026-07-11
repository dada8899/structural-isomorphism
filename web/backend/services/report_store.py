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
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------- Share token helpers --------------------------------- #


def _share_secret() -> bytes:
    """Resolve the HMAC secret.

    Priority: STRUCTURAL_SHARE_TOKEN_SECRET env > deterministic dev
    fallback. In **prod** (STRUCTURAL_ENV=prod) the env MUST be set —
    we raise rather than silently fall back, because the fallback is
    predictable from cwd and the prod cwd is well-known
    (/root/Projects/structural-isomorphism/web/backend). Letting that
    secret leak by accident defeats the share-token capability model.

    Validator review (session #16) found this fallback exploitable in
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
    # Dev / test fallback — deterministic per-cwd is fine here.
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

-- Session #17 V6 — report → action → result revisit loop. One row per
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
    experiment_json TEXT,
    outcome_detail_json TEXT,
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
    -- (session #16) caught this; the conversion happens in record_feedback.
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

    # Columns the `reports` table MUST have. `CREATE TABLE IF NOT EXISTS`
    # is a no-op when the table already exists, so a `reports` table created
    # by an OLDER schema version silently keeps its old shape — any newer
    # column (creator_anon_id / is_partial / ...) would then be missing and
    # every INSERT would raise OperationalError. We additively self-heal via
    # ALTER TABLE so a long-lived history.db stays forward-compatible.
    # (col_name, sqlite column definition for ALTER TABLE ADD COLUMN)
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
                # Migrate FIRST: on a drifted DB the `reports` table already
                # exists with an old shape, and `_SCHEMA` below contains a
                # `CREATE INDEX ... ON reports(creator_anon_id, ...)` that
                # would fail if that column is still missing. Backfilling
                # the columns before running `_SCHEMA` lets the index land.
                # On a fresh DB the table doesn't exist yet, so the migrate
                # step is a no-op (PRAGMA returns nothing) and `_SCHEMA`
                # creates everything from scratch.
                self._migrate_reports_columns(conn)
                self._migrate_followup_columns(conn)
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
            # Fresh table just created by _SCHEMA — nothing to migrate.
            return
        for col, col_def in self._REPORTS_COLUMNS:
            if col not in existing:
                logger.warning(
                    "report_store: reports table missing column %r — "
                    "adding via ALTER TABLE (schema drift self-heal)", col,
                )
                conn.execute(f"ALTER TABLE reports ADD COLUMN {col} {col_def}")

    def _migrate_followup_columns(self, conn: sqlite3.Connection) -> None:
        """Add structured workbench fields to pre-workbench databases."""
        existing = {
            row[1]
            for row in conn.execute("PRAGMA table_info(report_followup)").fetchall()
        }
        if not existing:
            return
        for col in ("experiment_json", "outcome_detail_json"):
            if col not in existing:
                conn.execute(f"ALTER TABLE report_followup ADD COLUMN {col} TEXT")

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
        # Validator session-#16 P2 — cap payload at 256 KB. A real 9-section
        # report is ~30-50 KB; anything 5× that is almost certainly an
        # accident or attack. We raise rather than silently truncate so
        # the caller decides (analyze.py logs and continues without
        # tearing down the SSE stream).
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

        B Data Flywheel (Session #18): each row also carries the SAME
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

    # ------ B Data Flywheel (Session #18) -------------------------- #

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
                    ON f.report_id = r.id
                   AND f.outcome = 'worked'
                   AND r.creator_anon_id IS NOT NULL
                   AND f.anon_id = r.creator_anon_id
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

    def count_human_verified(self, b_id: str) -> dict:
        """How many DISTINCT users marked outcome='worked' on a report whose
        target phenomenon is `b_id`.

        B Data Flywheel closure (Session #18): this feeds the analyze
        credibility badge "N 人验证这个跨域迁移真的有效". We count distinct
        anon_id (not followup rows) so one user re-submitting doesn't
        inflate the number. Empty b_id or no matches → count 0, recent ''.

        Returns {count: int, recent: str}. `recent` is the latest
        followup updated_at across matching 'worked' rows ('' if none).
        """
        if not b_id:
            return {"count": 0, "recent": ""}
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(DISTINCT f.anon_id) AS verifier_count,
                       MAX(f.updated_at)         AS last_verified_at
                FROM report_followup f
                JOIN reports r ON r.id = f.report_id
                WHERE r.b_id = ? AND f.outcome = 'worked'
                  AND r.creator_anon_id IS NOT NULL
                  AND f.anon_id = r.creator_anon_id
                """,
                (b_id,),
            ).fetchone()
        if row is None:
            return {"count": 0, "recent": ""}
        return {
            "count": int(row["verifier_count"] or 0),
            "recent": row["last_verified_at"] or "",
        }

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
                LEFT JOIN report_followup f
                    ON f.report_id = r.id
                   AND r.creator_anon_id IS NOT NULL
                   AND f.anon_id = r.creator_anon_id
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
                "SELECT COUNT(*) FROM report_followup f JOIN reports r ON r.id=f.report_id "
                "WHERE r.creator_anon_id IS NOT NULL AND f.anon_id=r.creator_anon_id"
            ).fetchone()[0]
            worked = conn.execute(
                "SELECT COUNT(*) FROM report_followup f JOIN reports r ON r.id=f.report_id "
                "WHERE f.outcome='worked' AND r.creator_anon_id IS NOT NULL "
                "AND f.anon_id=r.creator_anon_id"
            ).fetchone()[0]
            # verified isomorphisms = distinct reports with a 'worked' followup
            verified = conn.execute(
                "SELECT COUNT(DISTINCT f.report_id) FROM report_followup f "
                "JOIN reports r ON r.id=f.report_id WHERE f.outcome='worked' "
                "AND r.creator_anon_id IS NOT NULL AND f.anon_id=r.creator_anon_id"
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
        # Normalise None → '' so the UNIQUE index actually fires on
        # overall-report votes (SQLite treats NULL != NULL in unique
        # indexes; without this, repeated overall votes by one voter
        # accumulate instead of upserting). Validator session-#16 P1.
        section_norm = section if section is not None else ""
        voter_norm = voter_anon if voter_anon is not None else "anon"
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

    # ------ followup (Session #17 V6) ------------------------------ #

    # Allowed enum values — validated here so a bad client value never
    # lands in the DB. The API layer validates too (defence in depth).
    ACTION_STATUSES = ("planned", "in_progress", "tried", "abandoned")
    OUTCOMES = ("", "worked", "partial", "no_effect", "too_early")
    EXPERIMENT_STATUSES = (
        "planned", "in_progress", "completed", "stopped", "abandoned",
    )
    EXPERIMENT_TRANSITIONS = {
        "planned": {"planned", "in_progress", "abandoned"},
        "in_progress": {"in_progress", "completed", "stopped", "abandoned"},
        "completed": {"completed"},
        "stopped": {"stopped"},
        "abandoned": {"abandoned"},
    }
    RESULT_VALUES = ("success", "partial", "failure", "inconclusive")
    DECISION_VALUES = ("iterate", "scale", "stop", "retest")
    STATUS_TO_ACTION = {
        "planned": "planned",
        "in_progress": "in_progress",
        "completed": "tried",
        "stopped": "abandoned",
        "abandoned": "abandoned",
    }
    RESULT_TO_OUTCOME = {
        "success": "worked",
        "partial": "partial",
        "failure": "no_effect",
        "inconclusive": "too_early",
    }

    @staticmethod
    def _validate_text(value: Any, field: str, limit: int, *, required=False) -> None:
        if value is None and not required:
            return
        if not isinstance(value, str) or (required and not value.strip()):
            raise ValueError(f"{field} must be a non-empty string")
        if len(value) > limit:
            raise ValueError(f"{field} must be at most {limit} characters")

    def _validate_experiment(self, experiment: Optional[dict]) -> None:
        if experiment is None:
            return
        if not isinstance(experiment, dict):
            raise ValueError("experiment must be an object")
        allowed = {
            "hypothesis", "owner", "deadline", "baseline", "primary_metric",
            "success_threshold", "stop_condition", "status", "notes",
        }
        if set(experiment) - allowed:
            raise ValueError("experiment contains unknown fields")
        self._validate_text(experiment.get("hypothesis"), "hypothesis", 2000, required=True)
        self._validate_text(experiment.get("owner"), "owner", 120)
        self._validate_text(experiment.get("primary_metric"), "primary_metric", 200)
        self._validate_text(experiment.get("stop_condition"), "stop_condition", 1000)
        self._validate_text(experiment.get("notes"), "experiment.notes", 4000)
        deadline = experiment.get("deadline")
        if deadline is not None:
            if not isinstance(deadline, str) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}", deadline
            ):
                raise ValueError("deadline must be YYYY-MM-DD")
            try:
                _dt.date.fromisoformat(deadline)
            except ValueError as exc:
                raise ValueError("deadline must be a valid calendar date") from exc
        for field in ("baseline", "success_threshold"):
            value = experiment.get(field)
            if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)):
                raise ValueError(f"{field} must be a number")
        if experiment.get("status", "planned") not in self.EXPERIMENT_STATUSES:
            raise ValueError(f"experiment.status must be one of {self.EXPERIMENT_STATUSES}")

    def _validate_outcome_detail(self, detail: Optional[dict]) -> None:
        if detail is None:
            return
        if not isinstance(detail, dict):
            raise ValueError("outcome_detail must be an object")
        allowed = {
            "actual_metric", "result", "failure_reason", "learning", "next_decision",
        }
        if set(detail) - allowed:
            raise ValueError("outcome_detail contains unknown fields")
        actual = detail.get("actual_metric")
        if actual is not None and (not isinstance(actual, (int, float)) or isinstance(actual, bool)):
            raise ValueError("actual_metric must be a number")
        result = detail.get("result")
        if result not in (None, *self.RESULT_VALUES):
            raise ValueError(f"result must be one of {self.RESULT_VALUES}")
        if detail.get("next_decision") not in (None, *self.DECISION_VALUES):
            raise ValueError(f"next_decision must be one of {self.DECISION_VALUES}")
        self._validate_text(detail.get("failure_reason"), "failure_reason", 2000)
        self._validate_text(detail.get("learning"), "learning", 4000)
        if result == "failure" and not (detail.get("failure_reason") or "").strip():
            raise ValueError("failure_reason is required when result is failure")

    def record_followup(
        self,
        *,
        report_id: str,
        anon_id: Optional[str],
        action_status: str,
        outcome: str = "",
        note: Optional[str] = None,
        experiment: Optional[dict] = None,
        outcome_detail: Optional[dict] = None,
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
        self._validate_text(note, "note", 2000)
        anon_norm = anon_id if anon_id else "anon"
        now = _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        with self._connect() as conn:
            previous = conn.execute(
                "SELECT experiment_json, outcome_detail_json FROM report_followup "
                "WHERE report_id = ? AND anon_id = ?",
                (report_id, anon_norm),
            ).fetchone()
            old = (
                json.loads(previous["experiment_json"])
                if previous and previous["experiment_json"] else None
            )
            old_outcome_detail = (
                json.loads(previous["outcome_detail_json"])
                if previous and previous["outcome_detail_json"] else None
            )
            merged_experiment = (
                {**(old or {}), **experiment} if experiment is not None else old
            )
            merged_outcome_detail = (
                {**(old_outcome_detail or {}), **outcome_detail}
                if outcome_detail is not None else old_outcome_detail
            )
            self._validate_experiment(merged_experiment)
            self._validate_outcome_detail(merged_outcome_detail)
            if old is not None and experiment is not None:
                old_status = old.get("status", "planned")
                new_status = merged_experiment.get("status", "planned")
                if new_status not in self.EXPERIMENT_TRANSITIONS[old_status]:
                    raise ValueError(
                        f"invalid experiment status transition: {old_status} -> {new_status}"
                    )
            effective_experiment = merged_experiment
            if outcome_detail is not None and (
                effective_experiment is None
                or effective_experiment.get("status", "planned")
                not in {"completed", "stopped"}
            ):
                raise ValueError(
                    "outcome_detail requires a completed or stopped experiment"
                )
            if effective_experiment is not None:
                expected_action = self.STATUS_TO_ACTION[
                    effective_experiment.get("status", "planned")
                ]
                if action_status != expected_action:
                    raise ValueError(
                        "action_status conflicts with experiment.status: "
                        f"expected {expected_action!r}"
                    )
            if merged_outcome_detail is not None and merged_outcome_detail.get("result"):
                expected_outcome = self.RESULT_TO_OUTCOME[
                    merged_outcome_detail["result"]
                ]
                if outcome != expected_outcome:
                    raise ValueError(
                        "outcome conflicts with outcome_detail.result: "
                        f"expected {expected_outcome!r}"
                    )
            # created_at is set on first insert only; the upsert keeps it.
            conn.execute(
                """
                INSERT INTO report_followup (
                    report_id, anon_id, action_status, outcome, note,
                    experiment_json, outcome_detail_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(report_id, anon_id) DO UPDATE SET
                    action_status = excluded.action_status,
                    outcome = excluded.outcome,
                    note = excluded.note,
                    experiment_json = COALESCE(
                        excluded.experiment_json, report_followup.experiment_json
                    ),
                    outcome_detail_json = COALESCE(
                        excluded.outcome_detail_json, report_followup.outcome_detail_json
                    ),
                    updated_at = excluded.updated_at
                """,
                (report_id, anon_norm, action_status, outcome, note,
                 json.dumps(merged_experiment, ensure_ascii=False)
                 if experiment is not None else None,
                 json.dumps(merged_outcome_detail, ensure_ascii=False)
                 if outcome_detail is not None else None,
                 now, now),
            )
            row = conn.execute(
                """
                SELECT report_id, anon_id, action_status, outcome, note,
                       experiment_json, outcome_detail_json, created_at, updated_at
                FROM report_followup
                WHERE report_id = ? AND anon_id = ?
                """,
                (report_id, anon_norm),
            ).fetchone()
        return self._followup_row(row) or {}

    def get_followup(
        self, report_id: str, anon_id: Optional[str],
    ) -> Optional[dict]:
        """Return this anon's followup for the report, or None."""
        anon_norm = anon_id if anon_id else "anon"
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT report_id, anon_id, action_status, outcome, note,
                       experiment_json, outcome_detail_json, created_at, updated_at
                FROM report_followup
                WHERE report_id = ? AND anon_id = ?
                """,
                (report_id, anon_norm),
            ).fetchone()
        return self._followup_row(row)

    @staticmethod
    def _followup_row(row: Optional[sqlite3.Row]) -> Optional[dict]:
        if row is None:
            return None
        result = dict(row)
        result["experiment"] = (
            json.loads(result.pop("experiment_json"))
            if result.get("experiment_json") else None
        )
        result["outcome_detail"] = (
            json.loads(result.pop("outcome_detail_json"))
            if result.get("outcome_detail_json") else None
        )
        return result

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
