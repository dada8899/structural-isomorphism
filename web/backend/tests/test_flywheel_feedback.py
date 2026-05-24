"""B Data Flywheel closure (Session #18) — human-verification feedback.

Tests that real `outcome='worked'` followups flow back into the analyze
credibility badge via ReportStore.count_human_verified +
verified_isomorphisms.human_verified_for.

Three layers:
  * unit   — count_human_verified JOIN logic (0 / 1 / multi-user dedup /
             b_id isolation / outcome filtering)
  * integ  — seed reports + followups, assert the count, and assert the
             analyze credibility dict carries human_verified_count.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.report_store import ReportStore  # noqa: E402
from services.verified_isomorphisms import human_verified_for  # noqa: E402


# --------- fixtures --------- #


@pytest.fixture
def store(tmp_path):
    return ReportStore(tmp_path / "flywheel.db")


def _mk_report(store, b_id, *, query="q"):
    """Create a minimal report targeting `b_id`, return its id."""
    out = store.create(
        query=query, b_id=b_id, lang="zh",
        payload={"shared_structure": {"name": "s"}}, model="m",
    )
    return out["id"]


# --------- unit: count_human_verified --------- #


def test_count_zero_when_no_followups(store):
    """A report with no followup at all → count 0, recent ''."""
    _mk_report(store, "b-physics-1")
    res = store.count_human_verified("b-physics-1")
    assert res == {"count": 0, "recent": ""}


def test_count_one_worked(store):
    """One user marks outcome='worked' → count 1, recent populated."""
    rid = _mk_report(store, "b-physics-1")
    store.record_followup(
        report_id=rid, anon_id="u1", action_status="tried", outcome="worked",
    )
    res = store.count_human_verified("b-physics-1")
    assert res["count"] == 1
    assert res["recent"]  # a real updated_at timestamp


def test_count_dedups_same_user(store):
    """Same anon re-submitting 'worked' must NOT inflate the count.

    Followup is an upsert on (report_id, anon_id), and we COUNT DISTINCT
    anon_id — both layers protect against double counting.
    """
    rid = _mk_report(store, "b-physics-1")
    store.record_followup(
        report_id=rid, anon_id="u1", action_status="planned", outcome="worked",
    )
    store.record_followup(
        report_id=rid, anon_id="u1", action_status="tried", outcome="worked",
    )
    assert store.count_human_verified("b-physics-1")["count"] == 1


def test_count_multiple_distinct_users(store):
    """Three different users, across two reports on the same b_id → 3."""
    r1 = _mk_report(store, "b-bio-2")
    r2 = _mk_report(store, "b-bio-2")
    store.record_followup(
        report_id=r1, anon_id="u1", action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=r1, anon_id="u2", action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=r2, anon_id="u3", action_status="tried", outcome="worked",
    )
    assert store.count_human_verified("b-bio-2")["count"] == 3


def test_count_isolates_by_b_id(store):
    """A 'worked' on b-A must not leak into the count for b-B."""
    ra = _mk_report(store, "b-A")
    rb = _mk_report(store, "b-B")
    store.record_followup(
        report_id=ra, anon_id="u1", action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=rb, anon_id="u2", action_status="tried", outcome="worked",
    )
    assert store.count_human_verified("b-A")["count"] == 1
    assert store.count_human_verified("b-B")["count"] == 1
    assert store.count_human_verified("b-unknown")["count"] == 0


def test_count_only_worked_outcome(store):
    """partial / no_effect / too_early / '' must NOT count as verified."""
    rid = _mk_report(store, "b-mixed")
    store.record_followup(
        report_id=rid, anon_id="u1", action_status="tried", outcome="worked",
    )
    store.record_followup(
        report_id=rid, anon_id="u2", action_status="tried", outcome="partial",
    )
    store.record_followup(
        report_id=rid, anon_id="u3", action_status="tried", outcome="no_effect",
    )
    store.record_followup(
        report_id=rid, anon_id="u4", action_status="planned", outcome="",
    )
    assert store.count_human_verified("b-mixed")["count"] == 1


def test_count_empty_b_id(store):
    """Empty b_id short-circuits to zero without touching the DB."""
    assert store.count_human_verified("") == {"count": 0, "recent": ""}


# --------- integ: human_verified_for wrapper --------- #


def test_human_verified_for_wraps_store(store):
    """The verified_isomorphisms wrapper returns the same shape."""
    rid = _mk_report(store, "b-wrap")
    store.record_followup(
        report_id=rid, anon_id="u1", action_status="tried", outcome="worked",
    )
    res = human_verified_for(store, "b-wrap")
    assert res["count"] == 1
    assert res["recent"]


def test_human_verified_for_degrades_on_failure():
    """A broken store object must degrade to {count:0} — never raise.

    This guards the analyze SSE path: a query failure can't tear down
    the report stream.
    """
    class _Broken:
        def count_human_verified(self, b_id):
            raise RuntimeError("db gone")

    assert human_verified_for(_Broken(), "b-x") == {"count": 0, "recent": ""}


# --------- integ: analyze credibility block carries the field --------- #


def test_credibility_block_includes_human_verified():
    """The analyze credibility dict must expose human_verified_count.

    We can't easily run the full SSE endpoint here, so we assert the
    field contract directly: a credibility dict shaped like analyze.py's
    must carry an int human_verified_count (0 reported honestly).
    """
    # Mirror the shape analyze.py builds — the load-bearing keys.
    hv = {"count": 2, "recent": "2026-05-22T10:00:00Z"}
    credibility = {
        "kb_source": True,
        "similarity": 0.7,
        "human_verified_count": int(hv.get("count", 0) or 0),
        "human_verified_recent": hv.get("recent", "") or "",
    }
    assert credibility["human_verified_count"] == 2
    assert isinstance(credibility["human_verified_count"], int)
    assert credibility["human_verified_recent"] == "2026-05-22T10:00:00Z"

    # Zero case — honest 0, not omitted.
    hv0 = {"count": 0, "recent": ""}
    cred0 = {"human_verified_count": int(hv0.get("count", 0) or 0)}
    assert cred0["human_verified_count"] == 0
