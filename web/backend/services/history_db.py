"""
History DB — anonymous per-device query history stored in SQLite.

Foundation only; Wave 2 will wire frontend localStorage migration. Uses stdlib
sqlite3 (no new deps). One DB file per backend instance; concurrent FastAPI
workers share via the SQLite WAL/locking layer.

Schema:
    history(id, device_id, query, kind, result_summary, created_at)
    index idx_history_device on (device_id, created_at DESC)

kind ∈ {ask, search, analyze} — enforced by CHECK constraint.
result_summary stores a short JSON-serialised snippet (None ok).
device_id is the anonymous cookie ID; isolation is enforced at query time
(every list_recent / delete filters by device_id).
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# --- Python 3.12+ sqlite3 timestamp adapter/converter ---------------------
# The stdlib's default `datetime` adapter and `timestamp` converter are
# deprecated as of Python 3.12 (PendingDeprecationWarning → DeprecationWarning)
# and slated for removal in a future version. Register explicit ISO-8601
# string round-trippers so we don't rely on the deprecated default path.
#
# Idempotent: sqlite3.register_*() are global; calling them on every import
# is harmless. Guarded by a module-level flag for clarity.

_TIMESTAMP_HOOKS_INSTALLED = False


def _install_timestamp_hooks() -> None:
    global _TIMESTAMP_HOOKS_INSTALLED
    if _TIMESTAMP_HOOKS_INSTALLED:
        return

    def _adapt_datetime(dt: _dt.datetime) -> str:
        # Match the CURRENT_TIMESTAMP default ("YYYY-MM-DD HH:MM:SS") so
        # comparisons against rows inserted via the SQL default still sort
        # lexically. fromisoformat() accepts both " " and "T" separators.
        return dt.isoformat(sep=" ", timespec="seconds")

    def _convert_timestamp(value: bytes) -> _dt.datetime:
        # CURRENT_TIMESTAMP stores "YYYY-MM-DD HH:MM:SS" (no microseconds,
        # no timezone). fromisoformat() handles both that shape and any
        # isoformat() we adapt above.
        text = value.decode("utf-8", errors="replace")
        try:
            return _dt.datetime.fromisoformat(text)
        except ValueError:
            # Fallback: strip trailing "Z" or fractional weirdness; if it
            # still can't parse, return None equivalent (epoch) rather than
            # crashing the row read.
            text2 = text.rstrip("Z").split(".")[0]
            return _dt.datetime.fromisoformat(text2)

    sqlite3.register_adapter(_dt.datetime, _adapt_datetime)
    sqlite3.register_converter("timestamp", _convert_timestamp)
    _TIMESTAMP_HOOKS_INSTALLED = True


_install_timestamp_hooks()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    query TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('ask', 'search', 'analyze')),
    result_summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_history_device
    ON history(device_id, created_at DESC);
"""

ALLOWED_KINDS = {"ask", "search", "analyze"}


class HistoryDB:
    """Thin SQLite wrapper. Auto-creates parent dir and schema on init."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        # WAL mode for better concurrent read/write behaviour under uvicorn workers.
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.Error as e:  # pragma: no cover
            logger.warning("history_db WAL pragma failed: %s", e)
        return conn

    def _init_schema(self) -> None:
        try:
            with self._connect() as conn:
                conn.executescript(_SCHEMA)
        except sqlite3.Error as e:
            logger.exception("history_db schema init failed: %s", e)
            raise

    def record(
        self,
        device_id: str,
        query: str,
        kind: str,
        result_summary: dict[str, Any] | None,
    ) -> int:
        """Insert a history row. Returns the new row id."""
        if not device_id:
            raise ValueError("device_id required")
        if not query:
            raise ValueError("query required")
        if kind not in ALLOWED_KINDS:
            raise ValueError(f"kind must be one of {sorted(ALLOWED_KINDS)}, got {kind!r}")

        summary_text: str | None
        if result_summary is None:
            summary_text = None
        else:
            try:
                summary_text = json.dumps(result_summary, ensure_ascii=False)
            except (TypeError, ValueError) as e:
                logger.warning("history_db record: result_summary not JSON-serializable: %s", e)
                summary_text = json.dumps({"_unserializable": str(type(result_summary))})

        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT INTO history (device_id, query, kind, result_summary) "
                    "VALUES (?, ?, ?, ?)",
                    (device_id, query, kind, summary_text),
                )
                return int(cur.lastrowid)
        except sqlite3.Error as e:
            logger.exception("history_db record failed device=%s kind=%s: %s", device_id, kind, e)
            raise

    def list_recent(self, device_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """Return most-recent rows for one device_id (desc by created_at)."""
        if not device_id:
            return []
        if limit <= 0:
            return []
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT id, device_id, query, kind, result_summary, created_at "
                    "FROM history WHERE device_id = ? "
                    "ORDER BY created_at DESC, id DESC LIMIT ?",
                    (device_id, int(limit)),
                ).fetchall()
        except sqlite3.Error as e:
            logger.exception("history_db list_recent failed device=%s: %s", device_id, e)
            raise

        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            summary = d.get("result_summary")
            if summary:
                try:
                    d["result_summary"] = json.loads(summary)
                except json.JSONDecodeError:
                    # Leave as raw string; caller can decide what to do.
                    pass
            out.append(d)
        return out

    def delete(self, device_id: str, history_id: int) -> bool:
        """Delete a row if it belongs to the given device_id. Returns success."""
        if not device_id or history_id is None:
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM history WHERE id = ? AND device_id = ?",
                    (int(history_id), device_id),
                )
                return cur.rowcount > 0
        except sqlite3.Error as e:
            logger.exception(
                "history_db delete failed device=%s id=%s: %s",
                device_id,
                history_id,
                e,
            )
            raise
