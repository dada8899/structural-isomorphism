"""Database adapter: supports SQLite (default for dev/tests) and Postgres."""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_URL = os.environ.get(
    "DB_URL",
    "sqlite:///" + str(Path(__file__).resolve().parent.parent / "d1.sqlite"),
)


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite:///") or url == ":memory:" or url.startswith("file:")


def _sqlite_path(url: str) -> str:
    if url == ":memory:":
        return ":memory:"
    if url.startswith("sqlite:///"):
        return url[len("sqlite:///") :]
    return url


@contextmanager
def get_cursor(db_url: str | None = None) -> Iterator[tuple[Any, str]]:
    """Yield (cursor, driver_name). Auto-commits on success, rolls back on error."""
    url = db_url or DEFAULT_DB_URL
    if _is_sqlite(url):
        conn = sqlite3.connect(_sqlite_path(url))
        conn.row_factory = sqlite3.Row
        try:
            yield conn.cursor(), "sqlite"
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        try:
            import psycopg2  # type: ignore
            import psycopg2.extras  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "psycopg2 not installed; set DB_URL=sqlite:///... or pip install psycopg2-binary"
            ) from exc
        conn = psycopg2.connect(url)
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            yield cur, "postgres"
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def row_to_dict(row: Any, driver: str) -> dict[str, Any]:
    """Normalize a row to a plain dict regardless of driver."""
    if driver == "sqlite":
        d = dict(row)
    else:  # postgres RealDictCursor
        d = dict(row)
    # decode JSON-encoded text columns when on sqlite
    for jcol in ("primary_indicators", "raw_response"):
        v = d.get(jcol)
        if isinstance(v, str):
            try:
                d[jcol] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                pass
    return d


def placeholder(driver: str) -> str:
    return "?" if driver == "sqlite" else "%s"
