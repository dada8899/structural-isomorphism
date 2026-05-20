"""Tests for ReportStore — M1.4 persisted analyze.py reports.

PRD: docs/sessions/M1.4-report-generator-prd.md
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from services.report_store import (  ***REMOVED*** noqa: E402
    ReportStore,
    new_report_id,
    sign_share_token,
    verify_share_token,
)


***REMOVED*** --------- fixtures --------- ***REMOVED***


@pytest.fixture
def store(tmp_path):
    """Fresh ReportStore per test, isolated DB file."""
    return ReportStore(tmp_path / "test_reports.db")


@pytest.fixture
def sample_payload():
    """A mini 9-section report mirror — enough to exercise round-trip."""
    return {
        "shared_structure": {"name": "Cascade dynamics", "intuition": "..."},
        "your_problem_breakdown": {"summary": "..."},
        "target_domain_intro": {"domain_name": "Physics"},
        "structural_mapping": {"rationale": "..."},
        "borrowable_insights": ["i1", "i2"],
        "how_to_combine": {"steps": ["s1"]},
        "research_directions": {"literature_status": "..."},
        "risks_and_limits": {"failure_cases": []},
        "action_plan": {"immediate_actions": []},
    }


***REMOVED*** --------- share token helpers --------- ***REMOVED***


class TestShareToken:
    def test_token_is_32_hex_chars(self):
        rid = "r_abc123"
        tok = sign_share_token(rid)
        assert len(tok) == 32
        int(tok, 16)  ***REMOVED*** must be valid hex

    def test_token_is_deterministic(self):
        """Same rid + same env → same token (so we can re-derive on lookup)."""
        rid = "r_xyz"
        assert sign_share_token(rid) == sign_share_token(rid)

    def test_token_differs_per_rid(self):
        assert sign_share_token("r_a") != sign_share_token("r_b")

    def test_verify_accepts_valid_token(self):
        rid = "r_test"
        tok = sign_share_token(rid)
        assert verify_share_token(rid, tok) is True

    def test_verify_rejects_wrong_token(self):
        assert verify_share_token("r_test", "ff" * 16) is False
        assert verify_share_token("r_test", "") is False

    def test_verify_rejects_swapped_rid(self):
        tok = sign_share_token("r_a")
        assert verify_share_token("r_b", tok) is False


class TestReportId:
    def test_new_id_format(self):
        rid = new_report_id()
        assert rid.startswith("r_")
        assert len(rid) == 18  ***REMOVED*** "r_" + 16 hex chars

    def test_new_ids_are_unique(self):
        ids = {new_report_id() for _ in range(50)}
        assert len(ids) == 50


***REMOVED*** --------- CRUD --------- ***REMOVED***


class TestCreate:
    def test_create_returns_id_and_token(self, store, sample_payload):
        out = store.create(
            query="why teams fall apart",
            b_id="soc-160",
            lang="en",
            payload=sample_payload,
            model="deepseek/deepseek-chat:nitro",
        )
        assert out["id"].startswith("r_")
        assert len(out["share_token"]) == 32
        assert "Z" in out["created_at"]  ***REMOVED*** ISO-8601 with Z suffix

    def test_create_persists_all_fields(self, store, sample_payload):
        out = store.create(
            query="q",
            b_id="b1",
            lang="zh",
            payload=sample_payload,
            model="m1",
            rewritten_query="q-rewritten",
            creator_anon_id="anon-123",
            creator_tier="free",
            is_public=True,
            is_partial=False,
        )
        r = store.get_by_id(out["id"])
        assert r["query"] == "q"
        assert r["rewritten_query"] == "q-rewritten"
        assert r["b_id"] == "b1"
        assert r["lang"] == "zh"
        assert r["model"] == "m1"
        assert r["creator_anon_id"] == "anon-123"
        assert r["creator_tier"] == "free"
        assert r["is_public"] is True
        assert r["is_partial"] is False
        ***REMOVED*** payload is decoded back to dict
        assert r["payload"]["shared_structure"]["name"] == "Cascade dynamics"

    def test_payload_preserves_unicode(self, store):
        payload = {"shared_structure": {"name": "银行挤兑级联"}}
        out = store.create(
            query="为什么银行会倒",
            b_id="soc-001", lang="zh",
            payload=payload, model="m",
        )
        r = store.get_by_id(out["id"])
        assert r["payload"]["shared_structure"]["name"] == "银行挤兑级联"
        assert r["query"] == "为什么银行会倒"


class TestRead:
    def test_get_by_id_missing(self, store):
        assert store.get_by_id("r_doesnotexist") is None

    def test_get_by_share_token(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        r = store.get_by_share_token(out["share_token"])
        assert r is not None
        assert r["id"] == out["id"]

    def test_get_by_share_token_invalid(self, store):
        assert store.get_by_share_token("0" * 32) is None

    def test_list_by_anon_returns_recent_first(self, store, sample_payload):
        anon = "anon-A"
        ids = []
        for i in range(3):
            out = store.create(
                query=f"q{i}", b_id="b", lang="en",
                payload=sample_payload, model="m",
                creator_anon_id=anon,
            )
            ids.append(out["id"])
        ***REMOVED*** Different anon — must not appear in the list
        store.create(
            query="other", b_id="b", lang="en",
            payload=sample_payload, model="m",
            creator_anon_id="anon-B",
        )
        listing = store.list_by_anon(anon)
        assert len(listing) == 3
        ***REMOVED*** Newest first
        listing_ids = [r["id"] for r in listing]
        assert listing_ids == list(reversed(ids))

    def test_list_by_anon_respects_limit(self, store, sample_payload):
        for i in range(5):
            store.create(
                query=f"q{i}", b_id="b", lang="en",
                payload=sample_payload, model="m",
                creator_anon_id="A",
            )
        out = store.list_by_anon("A", limit=2)
        assert len(out) == 2

    def test_record_view_increments_count(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        r0 = store.get_by_id(out["id"])
        assert r0["view_count"] == 0
        store.record_view(out["id"])
        store.record_view(out["id"])
        r2 = store.get_by_id(out["id"])
        assert r2["view_count"] == 2
        assert r2["last_viewed_at"] is not None


***REMOVED*** --------- feedback --------- ***REMOVED***


class TestFeedback:
    def test_record_up_vote(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        counts = store.record_feedback(
            report_id=out["id"], section="borrowable_insights",
            vote=1, voter_anon="V",
        )
        assert counts == {"total_up": 1, "total_down": 0}

    def test_record_down_vote(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        counts = store.record_feedback(
            report_id=out["id"], section=None,
            vote=-1, voter_anon="V",
        )
        assert counts == {"total_up": 0, "total_down": 1}

    def test_same_voter_same_section_upserts(self, store, sample_payload):
        """Voter flip-flopping on the SAME section should overwrite, not double."""
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        store.record_feedback(
            report_id=out["id"], section="risks_and_limits",
            vote=1, voter_anon="V",
        )
        counts = store.record_feedback(
            report_id=out["id"], section="risks_and_limits",
            vote=-1, voter_anon="V",
        )
        assert counts == {"total_up": 0, "total_down": 1}

    def test_different_voters_accumulate(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        for v in ("A", "B", "C"):
            store.record_feedback(
                report_id=out["id"], section="action_plan",
                vote=1, voter_anon=v,
            )
        counts = store.feedback_counts(out["id"])
        assert counts == {"total_up": 3, "total_down": 0}

    def test_different_sections_per_voter_independent(self, store, sample_payload):
        """Same voter can vote DIFFERENTLY on different sections."""
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        store.record_feedback(
            report_id=out["id"], section="shared_structure",
            vote=1, voter_anon="V",
        )
        store.record_feedback(
            report_id=out["id"], section="action_plan",
            vote=-1, voter_anon="V",
        )
        counts = store.feedback_counts(out["id"])
        assert counts == {"total_up": 1, "total_down": 1}

    def test_invalid_vote_raises(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        with pytest.raises(ValueError):
            store.record_feedback(
                report_id=out["id"], section=None, vote=2, voter_anon="V",
            )

    def test_feedback_counts_zero_for_no_votes(self, store, sample_payload):
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        assert store.feedback_counts(out["id"]) == {"total_up": 0, "total_down": 0}

    def test_overall_vote_same_voter_upserts(self, store, sample_payload):
        """Validator session-***REMOVED***16 P1: section=None used to accumulate because
        SQLite UNIQUE indexes treat NULL != NULL. Now normalised to '',
        the UPSERT actually fires. Pin behaviour so we don't regress."""
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        ***REMOVED*** First overall up-vote
        store.record_feedback(
            report_id=out["id"], section=None, vote=1, voter_anon="V",
        )
        ***REMOVED*** Same voter flips to down — should overwrite, not double-count.
        counts = store.record_feedback(
            report_id=out["id"], section=None, vote=-1, voter_anon="V",
        )
        assert counts == {"total_up": 0, "total_down": 1}

    def test_payload_size_cap_rejects_oversize(self, store):
        """Validator P2: payload > 256 KB should raise so the caller can
        decide what to do instead of silently writing a bloated row."""
        huge_payload = {"shared_structure": {"description": "x" * (300 * 1024)}}
        with pytest.raises(ValueError, match="too large"):
            store.create(
                query="q", b_id="b", lang="en",
                payload=huge_payload, model="m",
            )

    def test_anonymous_voter_one_overall_vote_only(self, store, sample_payload):
        """voter_anon=None now collapses to 'anon'; one anonymous voter
        can only have one overall vote per report (no NULL pile-up)."""
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        store.record_feedback(
            report_id=out["id"], section=None, vote=1, voter_anon=None,
        )
        store.record_feedback(
            report_id=out["id"], section=None, vote=1, voter_anon=None,
        )
        counts = store.feedback_counts(out["id"])
        ***REMOVED*** Two clicks from the same (None→'anon') bucket → one row, one up.
        assert counts == {"total_up": 1, "total_down": 0}
