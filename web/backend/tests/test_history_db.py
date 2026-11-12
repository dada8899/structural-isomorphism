"""Unit tests for services.history_db.HistoryDB."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure web/backend is on sys.path so `services.*` resolves regardless of
# pytest invocation cwd.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from services.history_db import HistoryDB  # noqa: E402


@pytest.fixture
def db(tmp_path: Path) -> HistoryDB:
    return HistoryDB(tmp_path / "history.db")


def test_record(db: HistoryDB) -> None:
    rid = db.record("dev1", "what is power law", "ask", {"answer": "p(x)=x^-a"})
    assert isinstance(rid, int)
    assert rid > 0


def test_record_no_summary(db: HistoryDB) -> None:
    rid = db.record("dev1", "search q", "search", None)
    assert rid > 0
    rows = db.list_recent("dev1")
    assert len(rows) == 1
    # None summary survives the roundtrip
    assert rows[0]["result_summary"] is None


def test_record_validates_kind(db: HistoryDB) -> None:
    with pytest.raises(ValueError):
        db.record("dev1", "q", "bogus", {})


def test_record_requires_device_and_query(db: HistoryDB) -> None:
    with pytest.raises(ValueError):
        db.record("", "q", "ask", {})
    with pytest.raises(ValueError):
        db.record("dev1", "", "ask", {})


def test_list_recent(db: HistoryDB) -> None:
    db.record("dev1", "q1", "ask", {"i": 1})
    db.record("dev1", "q2", "search", {"i": 2})
    db.record("dev1", "q3", "analyze", {"i": 3})

    rows = db.list_recent("dev1")
    assert len(rows) == 3
    # Most recent first
    queries = [r["query"] for r in rows]
    assert queries == ["q3", "q2", "q1"]
    # JSON roundtrips
    assert rows[0]["result_summary"] == {"i": 3}


def test_list_recent_limit(db: HistoryDB) -> None:
    for i in range(5):
        db.record("dev1", f"q{i}", "ask", {"i": i})
    rows = db.list_recent("dev1", limit=2)
    assert len(rows) == 2
    assert rows[0]["query"] == "q4"
    assert rows[1]["query"] == "q3"


def test_list_recent_empty(db: HistoryDB) -> None:
    assert db.list_recent("nobody") == []
    assert db.list_recent("dev1", limit=0) == []


def test_delete(db: HistoryDB) -> None:
    rid = db.record("dev1", "q", "ask", {})
    assert db.delete("dev1", rid) is True
    assert db.list_recent("dev1") == []
    # Idempotent: second delete returns False
    assert db.delete("dev1", rid) is False


def test_delete_wrong_device(db: HistoryDB) -> None:
    rid = db.record("dev1", "q", "ask", {})
    # dev2 cannot delete dev1's row.
    assert db.delete("dev2", rid) is False
    # Row still present.
    assert len(db.list_recent("dev1")) == 1


def test_device_isolation(db: HistoryDB) -> None:
    db.record("alice", "alice q1", "ask", {"who": "alice"})
    db.record("alice", "alice q2", "search", {"who": "alice"})
    db.record("bob", "bob q1", "analyze", {"who": "bob"})

    alice_rows = db.list_recent("alice")
    bob_rows = db.list_recent("bob")

    assert len(alice_rows) == 2
    assert len(bob_rows) == 1
    assert all(r["device_id"] == "alice" for r in alice_rows)
    assert all(r["device_id"] == "bob" for r in bob_rows)
    # No leakage of bob's query into alice's view.
    assert "bob q1" not in [r["query"] for r in alice_rows]


def test_unserializable_summary_does_not_crash(db: HistoryDB) -> None:
    # set is not JSON-serialisable; record should still succeed with a
    # placeholder rather than raise.
    rid = db.record("dev1", "q", "ask", {"bad": {1, 2, 3}})  # type: ignore[dict-item]
    assert rid > 0
    rows = db.list_recent("dev1")
    assert len(rows) == 1
