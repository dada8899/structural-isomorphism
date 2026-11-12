"""Regression tests for explicit SQLite connection ownership."""
from __future__ import annotations

import sqlite3
import sys
from contextlib import closing
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.connections_p3_store import ConnectionsP3Store  # noqa: E402
from services.connections_store import ConnectionsStore  # noqa: E402
from services.history_db import HistoryDB  # noqa: E402
from services.report_store import ReportStore  # noqa: E402
from services.sqlite_utils import ClosingConnection  # noqa: E402
from services.sso_store import SsoReplayStore  # noqa: E402


def _assert_closed(conn: sqlite3.Connection) -> None:
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        conn.execute("SELECT 1")


def test_closing_connection_commits_then_closes(tmp_path: Path) -> None:
    database = tmp_path / "commit.sqlite3"
    conn = sqlite3.connect(database, factory=ClosingConnection)
    with conn:
        conn.execute("CREATE TABLE values_table(value INTEGER)")
        conn.execute("INSERT INTO values_table VALUES (1)")
    _assert_closed(conn)
    with closing(sqlite3.connect(database)) as reader:
        assert reader.execute("SELECT value FROM values_table").fetchone() == (1,)


def test_closing_connection_rolls_back_then_closes(tmp_path: Path) -> None:
    database = tmp_path / "rollback.sqlite3"
    with closing(sqlite3.connect(database)) as setup:
        setup.execute("CREATE TABLE values_table(value INTEGER)")
        setup.commit()
    conn = sqlite3.connect(database, factory=ClosingConnection)
    with pytest.raises(RuntimeError, match="stop"):
        with conn:
            conn.execute("INSERT INTO values_table VALUES (1)")
            raise RuntimeError("stop")
    _assert_closed(conn)
    with closing(sqlite3.connect(database)) as reader:
        assert reader.execute("SELECT COUNT(*) FROM values_table").fetchone() == (0,)


@pytest.mark.parametrize(
    "factory",
    [ReportStore, HistoryDB, ConnectionsStore, ConnectionsP3Store, SsoReplayStore],
)
def test_store_contexts_close_connections(factory, tmp_path: Path) -> None:
    store = factory(tmp_path / f"{factory.__name__}.sqlite3")
    conn = store._connect()
    with conn:
        conn.execute("SELECT 1")
    _assert_closed(conn)
