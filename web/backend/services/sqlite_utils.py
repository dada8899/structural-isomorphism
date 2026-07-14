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
