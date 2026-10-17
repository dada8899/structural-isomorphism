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

    def __enter__(self):
        try:
            self._history_file.check()
            return super().__enter__()
        except BaseException:
            self.close()
            raise

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            try:
                self._history_file.check()
            except BaseException:
                self.rollback()
                raise
            return sqlite3.Connection.__exit__(self, exc_type, exc_value, traceback)
        finally:
            self.close()

    def commit(self):
        witness = self._history_file
        if witness is not None:
            witness.check()
        try:
            return sqlite3.Connection.commit(self)
        finally:
            if witness is not None:
                witness.check()

    def rollback(self):
        witness = self._history_file
        try:
            return sqlite3.Connection.rollback(self)
        finally:
            if witness is not None:
                witness.check()

    def close(self):
        witness = self._history_file
        self._history_file = None
        try:
            sqlite3.Connection.close(self)
        finally:
            if witness is not None:
                try:
                    witness.check()
                finally:
                    witness.close()


def prepare_private_history(path):
    """Precreate only the approved file; never create a parent directory."""
    from .runtime_paths import PrivateHistoryFile
    witness = PrivateHistoryFile.acquire(path, create=True)
    witness.close()


def connect_private_history(path, *, detect_types=0, foreign_keys=False):
    """Open the prevalidated file mode=rw, never SQLite's implicit create mode."""
    from .runtime_paths import PrivateHistoryFile, RuntimePathError, HISTORY_OPEN_LOCK
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
    except BaseException:
        try:
            if conn is not None:
                conn.close()
        finally:
            if witness is not None:
                witness.close()
        raise


class PrivateAuthConnection(PrivateHistoryConnection):
    """Native SQLite semantics (including autocommit None), guarded close."""
    @property
    def private_storage_identity(self):
        return self._history_file.file_identity if self._history_file is not None else None


def connect_private_auth(path, *, readonly=False, timeout=10.0, expected_identity=None):
    """Existing static Auth role only. Caller owns BEGIN/hooks/policy/close."""
    from .runtime_paths import PrivateAuthFile, RuntimePathError, HISTORY_OPEN_LOCK
    if type(readonly) is not bool:
        raise TypeError('readonly must be a boolean')
    witness=None;connection=None
    try:
        with HISTORY_OPEN_LOCK:
            witness=PrivateAuthFile.acquire(path)
            if expected_identity is not None and witness.file_identity!=expected_identity:
                raise RuntimePathError('private auth object has an obsolete file identity')
            mode='ro' if readonly else 'rw'
            connection=sqlite3.connect(witness.path.as_uri()+'?mode='+mode,uri=True,
                timeout=timeout,isolation_level=None,factory=PrivateAuthConnection)
            connection._history_file=witness
        witness.check()
        connection.row_factory=sqlite3.Row
        if connection.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
            raise RuntimePathError('private auth requires preprovisioned WAL mode')
        witness.check()
        return connection
    except BaseException:
        try:
            if connection is not None:connection.close()
        finally:
            if witness is not None:witness.close()
        raise


class PrivateSsoConnection(PrivateHistoryConnection):
    @property
    def private_storage_identity(self):
        return self._history_file.file_identity if self._history_file is not None else None


def connect_private_sso(path,*,readonly=False,timeout=10.0,expected_identity=None):
    """Replay-specific, tuple rows/autocommit; caller owns transactions."""
    from .runtime_paths import PrivateSsoFile,RuntimePathError,HISTORY_OPEN_LOCK
    if type(readonly) is not bool:raise TypeError('readonly must be a boolean')
    inspected=None;conn=None
    try:
        with HISTORY_OPEN_LOCK:
            inspected=PrivateSsoFile.acquire(path)
            if expected_identity is not None and inspected.file_identity!=expected_identity:
                raise RuntimePathError('private SSO object has obsolete ledger identity')
            conn=sqlite3.connect(inspected.path.as_uri()+'?mode='+('ro' if readonly else 'rw'),
                uri=True,timeout=timeout,isolation_level=None,factory=PrivateSsoConnection)
            conn._history_file=inspected
        inspected.check()
        # No Auth Row factory/default hook, no policy/grant or journal rewrite.
        if conn.execute('PRAGMA journal_mode').fetchone()[0].lower()!='wal':
            raise RuntimePathError('private SSO requires preprovisioned WAL mode')
        inspected.check()
        return conn
    except BaseException:
        try:
            if conn is not None:conn.close()
        finally:
            if inspected is not None:inspected.close()
        raise
