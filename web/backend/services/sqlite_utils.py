"""SQLite connection helpers shared by backend stores."""
from __future__ import annotations

import sqlite3
from types import TracebackType


class ClosingConnection(sqlite3.Connection):
    """Commit/rollback like sqlite3's context manager, then always close."""

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        try:
            return bool(super().__exit__(exc_type, exc_value, traceback))
        finally:
            self.close()


class PrivateHistoryConnection(ClosingConnection):
    """A native connection holding only a directory FD and stat identity snapshot."""

    _history_file = None

    _history_read_resource = None
    _native_close_state = 'live'
    _close_uncertain = False

    def __enter__(self):
        try:
            self._history_file.check()
            return super().__enter__()
        except BaseException as primary:
            try: self.close()
            except BaseException as cleanup: primary.add_note('private cleanup uncertain: ' + type(cleanup).__name__)
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        primary = exc_value
        try:
            try:
                self._history_file.check()
            except BaseException:
                self.rollback()
                raise
            return sqlite3.Connection.__exit__(self, exc_type, exc_value, traceback)
        except BaseException as error:
            if primary is None: primary = error
            elif error is not primary: primary.add_note('private transaction cleanup uncertain: ' + type(error).__name__)
            raise primary
        finally:
            try: self.close()
            except BaseException as cleanup:
                if primary is None: raise
                primary.add_note('private cleanup uncertain: ' + type(cleanup).__name__)

    def commit(self):
        witness = self._history_file
        if witness is not None: witness.check()
        try: return sqlite3.Connection.commit(self)
        finally:
            if witness is not None: witness.check()

    def rollback(self):
        witness = self._history_file
        try: return sqlite3.Connection.rollback(self)
        finally:
            if witness is not None: witness.check()

    def _close_native(self):
        return sqlite3.Connection.close(self)

    def close(self):
        from . import formal_admission
        if self._close_uncertain:
            raise RuntimeError('private connection closure uncertain; no retry')
        if self._native_close_state == 'closed' and self._history_file is None: return
        witness, resource = self._history_file, self._history_read_resource
        formal_admission.begin_history_resource_close(resource)
        errors = []
        if self._native_close_state != 'closed':
            try: self._close_native()
            except BaseException as error:
                self._native_close_state = 'uncertain'; errors.append(error)
            else: self._native_close_state = 'closed'
        if witness is not None:
            try: witness.check()
            except BaseException as error: errors.append(error)
            try: witness.close()
            except BaseException as error: errors.append(error)
        if errors:
            self._close_uncertain = True
            formal_admission.finish_history_resource(resource, errors[0])
            for error in errors[1:]: errors[0].add_note('independent private cleanup failed: ' + type(error).__name__)
            raise errors[0]
        formal_admission.finish_history_resource(resource)
        self._history_file = self._history_read_resource = None


def prepare_private_history(path):
    """Precreate only the approved file; never create a parent directory."""
    from .runtime_paths import PrivateHistoryFile
    witness = PrivateHistoryFile.acquire(path, create=True)
    witness.close()


def connect_private_history(path, *, detect_types=0, foreign_keys=False):
    """Open the prevalidated file mode=rw, never SQLite's implicit create mode."""
    from .runtime_paths import PrivateHistoryFile, RuntimePathError, HISTORY_OPEN_LOCK
    from . import formal_admission
    resource = formal_admission.reserve_history_resource('connection')
    witness = None
    conn = None
    try:
        # Share the creation mutex only through the actual native open. A new
        # inode's ordinary creation FD must already be closed before this point.
        # SQL transactions and PRAGMAs run under SQLite's own locking protocol.
        with HISTORY_OPEN_LOCK:
            witness = PrivateHistoryFile.acquire(path, create=False)
            witness.check()
            conn = sqlite3.connect(witness.uri, uri=True, timeout=10.0,
                                   detect_types=detect_types, factory=PrivateHistoryConnection)
            conn._history_file = witness
            conn._history_read_resource = resource
            formal_admission.bind_history_connection(resource, conn, witness)
        witness.check()
        conn.row_factory = sqlite3.Row
        if foreign_keys:
            conn.execute('PRAGMA foreign_keys=ON')
            witness.check()
            if conn.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise RuntimePathError('formal history foreign keys are unavailable')
            witness.check()
        row = conn.execute('PRAGMA journal_mode=WAL').fetchone()
        if row is None or row[0].lower() != 'wal':
            raise RuntimePathError('formal history WAL mode is unavailable')
        witness.check()
        return conn
    except BaseException as primary:
        if conn is not None:
            try: conn.close()
            except BaseException as cleanup: primary.add_note('private connection cleanup uncertain: ' + type(cleanup).__name__)
        elif resource is not None:
            formal_admission.finish_history_resource(resource)
        if witness is not None and conn is None:
            try: witness.close()
            except BaseException as cleanup: primary.add_note('private parent cleanup uncertain: ' + type(cleanup).__name__)
        raise


class PrivateAuthConnection(PrivateHistoryConnection):
    """Native SQLite semantics (including autocommit None), guarded close."""
    @property
    def private_storage_identity(self):
        return self._history_file.file_identity if self._history_file is not None else None


def native_thread_budget(path,expected_identity=None):
    """Only either canonical C family's registered thread may shorten waits."""
    import sys,types
    from pathlib import Path
    found=[]
    for name in ('research.native_plan_supervisor','web.backend.research.native_plan_supervisor'):
        module=sys.modules.get(name)
        if module is None:continue
        expected=Path(__file__).resolve().parents[1]/'research/native_plan_supervisor.py'
        function=getattr(module,'database_budget',None);codes=getattr(module,'_NATIVE_CODES',{})
        if (type(module) is not types.ModuleType or Path(module.__file__).resolve()!=expected or Path(module.__file__).is_symlink()
                or type(function) is not types.FunctionType or function.__globals__ is not vars(module)
                or function.__code__ is not codes.get('database_budget')):raise RuntimeError('canonical native wait scope required')
        budget=function(path,expected_identity)
        if budget is not None:
            if type(budget) is not module._ThreadBudget:raise RuntimeError('actual registered native wait scope required')
            budget.check();found.append(budget)
    if len(found)>1 and any(value is not found[0] for value in found):raise RuntimeError('ambiguous native wait scope')
    return found[0] if found else None


def configure_native_wait(conn,path,expected_identity=None,*,legacy_ms):
    budget=native_thread_budget(path,expected_identity)
    if budget is not None:
        budget.check();conn.execute('PRAGMA busy_timeout=0')
        conn.set_progress_handler(budget.progress,1000)
    else:conn.execute('PRAGMA busy_timeout=%d'%legacy_ms)
    return budget


def connect_private_auth(path, *, readonly=False, timeout=10.0, expected_identity=None):
    """Existing static Auth role only. Caller owns BEGIN/hooks/policy/close."""
    from .runtime_paths import PrivateAuthFile, RuntimePathError, HISTORY_OPEN_LOCK
    from . import formal_admission
    resource = formal_admission.reserve_history_resource('connection')
    witness=None;connection=None;locked=False
    budget=None
    try:
        if type(readonly) is not bool:raise TypeError('readonly must be a boolean')
        budget=native_thread_budget(path,expected_identity)
        if budget is not None:
            budget.check();locked=HISTORY_OPEN_LOCK.acquire(blocking=False)
            if not locked:raise __import__(budget.__class__.__module__,fromlist=['_busy'])._busy()
        else:HISTORY_OPEN_LOCK.acquire();locked=True
        try:
            if budget is not None:budget.check()
            witness=PrivateAuthFile.acquire(path)
            if expected_identity is not None and witness.file_identity!=expected_identity:
                raise RuntimePathError('private auth object has an obsolete file identity')
            mode='ro' if readonly else 'rw'
            connection=sqlite3.connect(witness.path.as_uri()+'?mode='+mode,uri=True,
                timeout=0 if budget is not None else timeout,isolation_level=None,factory=PrivateAuthConnection)
            connection._history_file=witness
            connection._history_read_resource=resource
            formal_admission.bind_history_connection(resource, connection, witness)
            configure_native_wait(connection,path,expected_identity,legacy_ms=int(timeout*1000))
        finally:
            if locked:HISTORY_OPEN_LOCK.release();locked=False
        if budget is not None:budget.check()
        witness.check()
        connection.row_factory=sqlite3.Row
        if connection.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
            raise RuntimePathError('private auth requires preprovisioned WAL mode')
        witness.check()
        return connection
    except BaseException as primary:
        if connection is not None:
            try: connection.close()
            except BaseException as cleanup: primary.add_note('private connection cleanup uncertain: ' + type(cleanup).__name__)
        elif resource is not None:
            formal_admission.finish_history_resource(resource)
        if witness is not None and connection is None:
            try: witness.close()
            except BaseException as cleanup: primary.add_note('private parent cleanup uncertain: ' + type(cleanup).__name__)
        raise


class PrivateSsoConnection(PrivateHistoryConnection):
    @property
    def private_storage_identity(self):
        return self._history_file.file_identity if self._history_file is not None else None


def connect_private_sso(path,*,readonly=False,timeout=10.0,expected_identity=None):
    """Replay-specific, tuple rows/autocommit; caller owns transactions."""
    from .runtime_paths import PrivateSsoFile,RuntimePathError,HISTORY_OPEN_LOCK
    from . import formal_admission
    resource = formal_admission.reserve_history_resource('connection')
    inspected=None;conn=None
    try:
        if type(readonly) is not bool:raise TypeError('readonly must be a boolean')
        with HISTORY_OPEN_LOCK:
            inspected=PrivateSsoFile.acquire(path)
            if expected_identity is not None and inspected.file_identity!=expected_identity:
                raise RuntimePathError('private SSO object has obsolete ledger identity')
            conn=sqlite3.connect(inspected.path.as_uri()+'?mode='+('ro' if readonly else 'rw'),
                uri=True,timeout=timeout,isolation_level=None,factory=PrivateSsoConnection)
            conn._history_file=inspected
            conn._history_read_resource=resource
            formal_admission.bind_history_connection(resource, conn, inspected)
        inspected.check()
        # No Auth Row factory/default hook, no policy/grant or journal rewrite.
        if conn.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
            raise RuntimePathError('private SSO requires preprovisioned WAL mode')
        inspected.check()
        return conn
    except BaseException as primary:
        if conn is not None:
            try: conn.close()
            except BaseException as cleanup: primary.add_note('private connection cleanup uncertain: ' + type(cleanup).__name__)
        elif resource is not None:
            formal_admission.finish_history_resource(resource)
        if inspected is not None and conn is None:
            try: inspected.close()
            except BaseException as cleanup: primary.add_note('private parent cleanup uncertain: ' + type(cleanup).__name__)
        raise
