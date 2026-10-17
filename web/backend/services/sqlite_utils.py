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
    """A native connection whose file witnesses survive until finally-close."""

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
    from .runtime_paths import PrivateHistoryFile, RuntimePathError
    witness = PrivateHistoryFile.acquire(path, create=False)
    conn = None
    try:
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
            witness.close()
        raise
