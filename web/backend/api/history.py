"""
GET / DELETE /api/history — per-device anonymous query history.

Both endpoints require the `X-Device-ID` header (anonymous cookie value
forwarded by the frontend). Wave 2 will wire frontend localStorage → these
endpoints; this is foundation only.
"""

from __future__ import annotations

import os
import threading
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

if __package__ == "web.backend.api":
    from ..services.history_db import ALLOWED_KINDS, HistoryDB
    from ..logging_config import get_logger
else:
    from services.history_db import ALLOWED_KINDS, HistoryDB
    from logging_config import get_logger

logger = get_logger("structural.api.history")

router = APIRouter(tags=["history"])

_db: Optional[HistoryDB] = None

# Resource coordination only; neither this mutex nor a cache binding admits
# the formal app. Both supported API package names share one interpreter lock.
_HISTORY_STORE_LOCK = vars(sqlite3).setdefault('_structural_history_getter_lock_v1', threading.RLock())


def _history_context(development_path):
    if __package__ == "web.backend.api":
        from ..services import runtime_paths as runtime
    else:
        from services import runtime_paths as runtime
    formal = runtime.formal_history_runtime()
    if not formal and os.getenv("STRUCTURAL_ENV", "dev").strip().lower() == "prod":
        raise runtime.RuntimePathError("formal history profile contains invalid whitespace")
    if not formal:
        return False, Path(development_path)
    expected = runtime.STATE_ROOT / "history.db"
    override = os.environ.get("STRUCTURAL_HISTORY_DB")
    if override is not None and (
        not override or override.startswith("file:") or not Path(override).is_absolute()
        or ".." in Path(override).parts or Path(override) != expected
    ):
        raise runtime.RuntimePathError("formal history environment does not name the approved database")
    repository = Path(__file__).resolve().parents[3]
    frontend = repository / "web/frontend"
    inspected = runtime.RuntimePaths.inspect_formal(repository=repository, public_roots=[
        frontend, frontend / "assets", frontend / "phase/samples", frontend / "phase/data",
    ])
    return True, inspected.file("history")


def _schema_metadata(connection, expected_objects=None):
    """Inspect schema only; never select application rows."""
    objects = {}
    tables = {}
    indexes = {}
    declarations = list(connection.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"
    ))
    for kind, name, table, sql in declarations:
        objects[(kind, name)] = (table, ' '.join(sql.split()) if sql is not None else None)
    # Reject unknown/changed auxiliaries before asking SQLite to introspect
    # any table or virtual-module declaration outside the frozen contract.
    if expected_objects is not None and objects != expected_objects:
        return objects, tables, indexes
    for kind, name, table, sql in declarations:
        quoted = '"' + name.replace('"', '""') + '"'
        if kind == 'table':
            tables[name] = (
                tuple(tuple(row) for row in connection.execute('PRAGMA table_xinfo(' + quoted + ')')),
                tuple(tuple(row) for row in connection.execute('PRAGMA foreign_key_list(' + quoted + ')')),
                tuple(sorted(tuple(row)[1:] for row in connection.execute('PRAGMA index_list(' + quoted + ')'))),
            )
        elif kind == 'index':
            indexes[name] = tuple(tuple(row) for row in connection.execute('PRAGMA index_xinfo(' + quoted + ')'))
    return objects, tables, indexes


@lru_cache(maxsize=1)
def _history_schema_contract():
    """Derive the fixed four-Store closure only in native in-memory SQLite.

    Reuse their SQL and migration methods, not a second business schema. The
    uninitialized shells carry class constants only; no constructor/user DB is
    invoked. Reapplying existing migrations makes post-migration metadata part
    of the expectation instead of relying solely on CREATE declarations.
    """
    if __package__ == "web.backend.api":
        from ..services import history_db, report_store, connections_store, connections_p3_store
        from ..services.sqlite_utils import ClosingConnection
    else:
        from services import history_db, report_store, connections_store, connections_p3_store
        from services.sqlite_utils import ClosingConnection
    with sqlite3.connect(':memory:', factory=ClosingConnection) as expected:
        expected.executescript(history_db._SCHEMA)
        for module, factory, migrations in (
            (report_store, report_store.ReportStore, ('_migrate_reports_columns', '_migrate_followup_columns')),
            (connections_store, connections_store.ConnectionsStore, ('_migrate_columns',)),
            (connections_p3_store, connections_p3_store.ConnectionsP3Store, ('_migrate_columns',)),
        ):
            shell = factory.__new__(factory)
            for name in migrations:
                getattr(shell, name)(expected)
            expected.executescript(module._SCHEMA)
            for name in migrations:
                getattr(shell, name)(expected)
        return _schema_metadata(expected)


def _history_identity(path):
    if __package__ == "web.backend.api":
        from ..services import runtime_paths as runtime
        from ..services.sqlite_utils import ClosingConnection
    else:
        from services import runtime_paths as runtime
        from services.sqlite_utils import ClosingConnection
    # Consumers require provisioned, complete storage. The independent B1
    # bootstrap may create/migrate it before requests; consumers never repair.
    inspected = runtime.PrivateHistoryFile.acquire(path, create=False)
    connection = None
    try:
        inspected.check()
        with runtime.HISTORY_OPEN_LOCK:
            connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True,
                                         timeout=10.0, factory=ClosingConnection)
        inspected.check()
        with connection:
            connection.execute('BEGIN')
            expected = _history_schema_contract()
            actual = _schema_metadata(connection, expected_objects=expected[0])
            if actual != expected:
                raise runtime.RuntimePathError("formal history schema is incomplete or differs from its contract")
        inspected.check()
        return inspected.file_identity
    except sqlite3.Error:
        raise runtime.RuntimePathError("formal history schema cannot be inspected") from None
    finally:
        try:
            if connection is not None:
                connection.close()
        finally:
            try:
                inspected.check()
            finally:
                inspected.close()


def _existing_history_path(development_path):
    with _HISTORY_STORE_LOCK:
        formal, path = _history_context(development_path)
        if formal:
            _history_identity(path)
        return path


def _history_store(current, factory, development_path):
    """Called under _HISTORY_STORE_LOCK; publish only a complete real Store.

    The object-local binding is cache metadata, not a filesystem guarantee.
    Every formal hit still inspects the actual existing database; every native
    connection retains B1's checks. Unknown externally supplied dev fixtures
    preserve the old single-slot override behavior, outside formal mode only.
    """
    formal, path = _history_context(development_path)
    key = (formal, str(path.absolute()))
    binding = getattr(current, '_history_consumer_binding', None) if current is not None else None
    owned = (isinstance(binding, tuple) and len(binding) == 2
             and type(binding[0]) is bool and isinstance(binding[1], str))
    if current is not None and not formal and not owned:
        return current
    if current is not None and formal and owned and binding == key and (
        not isinstance(current, factory) or Path(current.db_path).absolute() != path.absolute()
        or not getattr(current, '_formal_history', False)
    ):
        if __package__ == "web.backend.api":
            from ..services.runtime_paths import RuntimePathError
        else:
            from services.runtime_paths import RuntimePathError
        raise RuntimePathError("history consumer cache binding is inconsistent")
    identity = _history_identity(path) if formal else None
    if current is not None and owned and binding == key:
        if formal and getattr(current, '_history_consumer_inode', None) != identity:
            if __package__ == "web.backend.api":
                from ..services.runtime_paths import RuntimePathError
            else:
                from services.runtime_paths import RuntimePathError
            raise RuntimePathError("history consumer cache inode is inconsistent")
        return current
    candidate = factory(path)
    # A changed configuration must not publish an object under an obsolete key.
    after_formal, after_path = _history_context(development_path)
    if (after_formal, str(after_path.absolute())) != key:
        if __package__ == "web.backend.api":
            from ..services.runtime_paths import RuntimePathError
        else:
            from services.runtime_paths import RuntimePathError
        raise RuntimePathError("history configuration changed during initialization")
    if formal:
        if _history_identity(path) != identity:
            if __package__ == "web.backend.api":
                from ..services.runtime_paths import RuntimePathError
            else:
                from services.runtime_paths import RuntimePathError
            raise RuntimePathError("history database changed during initialization")
        candidate._history_consumer_inode = identity
    candidate._history_consumer_binding = key
    return candidate


def _resolve_db_path() -> Path:
    """Keep the legacy dev override; formal requires the approved state file."""
    override = os.getenv("STRUCTURAL_HISTORY_DB")
    default = Path(override) if override else Path(__file__).resolve().parent.parent / "data/history.db"
    return _history_context(default)[1]


def get_db() -> HistoryDB:
    """Lazy singleton — initialised on first request so the file isn't created
    at import time (helps tests + cold-start observability)."""
    global _db
    with _HISTORY_STORE_LOCK:
        previous = _db
        _db = _history_store(_db, HistoryDB, _resolve_db_path())
        if _db is not previous:
            logger.info("structural.history.initialized")
        return _db


def _require_device_id(x_device_id: str | None) -> str:
    if not x_device_id or not x_device_id.strip():
        raise HTTPException(status_code=400, detail="X-Device-ID header required")
    return x_device_id.strip()


class HistoryRecordRequest(BaseModel):
    """Body for POST /api/history.

    Mirrors HistoryDB.record fields. `result_summary` is optional and any
    JSON-serialisable shape is accepted; HistoryDB normalises to a string.
    """

    query: str = Field(..., min_length=1, max_length=2000)
    kind: str = Field(..., min_length=1)
    result_summary: dict | None = None


@router.get("/history")
async def list_history(
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
    limit: int = 20,
):
    device_id = _require_device_id(x_device_id)
    if limit <= 0 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be in (0, 200]")
    db = get_db()
    rows = db.list_recent(device_id, limit=limit)
    return {"items": rows, "count": len(rows)}


@router.post("/history")
async def record_history(
    body: HistoryRecordRequest,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    """Record a single history entry. Anonymous, scoped by device_id cookie."""
    device_id = _require_device_id(x_device_id)
    kind = body.kind.strip().lower()
    if kind not in ALLOWED_KINDS:
        raise HTTPException(
            status_code=400,
            detail=f"kind must be one of {sorted(ALLOWED_KINDS)}",
        )
    db = get_db()
    try:
        rid = db.record(device_id, body.query.strip(), kind, body.result_summary)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "id": rid}


@router.delete("/history/{history_id}")
async def delete_history(
    history_id: int,
    x_device_id: Optional[str] = Header(default=None, alias="X-Device-ID"),
):
    device_id = _require_device_id(x_device_id)
    db = get_db()
    ok = db.delete(device_id, history_id)
    if not ok:
        raise HTTPException(status_code=404, detail="history row not found")
    return {"ok": True, "id": history_id}
