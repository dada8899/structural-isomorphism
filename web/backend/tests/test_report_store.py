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

from services.report_store import (  # noqa: E402
    ReportStore,
    new_report_id,
    sign_share_token,
    verify_share_token,
)


# --------- fixtures --------- #


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


# --------- share token helpers --------- #


class TestShareToken:
    def test_token_is_32_hex_chars(self):
        rid = "r_abc123"
        tok = sign_share_token(rid)
        assert len(tok) == 32
        int(tok, 16)  # must be valid hex

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
        assert len(rid) == 18  # "r_" + 16 hex chars

    def test_new_ids_are_unique(self):
        ids = {new_report_id() for _ in range(50)}
        assert len(ids) == 50


# --------- CRUD --------- #


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
        assert "Z" in out["created_at"]  # ISO-8601 with Z suffix

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
        # payload is decoded back to dict
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
        # Different anon — must not appear in the list
        store.create(
            query="other", b_id="b", lang="en",
            payload=sample_payload, model="m",
            creator_anon_id="anon-B",
        )
        listing = store.list_by_anon(anon)
        assert len(listing) == 3
        # Newest first
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


# --------- feedback --------- #


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
        """Validator session-#16 P1: section=None used to accumulate because
        SQLite UNIQUE indexes treat NULL != NULL. Now normalised to '',
        the UPSERT actually fires. Pin behaviour so we don't regress."""
        out = store.create(
            query="q", b_id="b", lang="en", payload=sample_payload, model="m",
        )
        # First overall up-vote
        store.record_feedback(
            report_id=out["id"], section=None, vote=1, voter_anon="V",
        )
        # Same voter flips to down — should overwrite, not double-count.
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
        # Two clicks from the same (None→'anon') bucket → one row, one up.
        assert counts == {"total_up": 1, "total_down": 0}


# --------- P0-1: schema-drift self-heal migration --------- #


class TestSchemaDriftMigration:
    """`_init_schema` ADDs any `reports` column an older DB is missing.

    Root cause of the "report saved == lost" bug class: `report_store`
    shares `history.db` and uses `CREATE TABLE IF NOT EXISTS`, which is a
    no-op when `reports` already exists. A `reports` table created by a
    pre-M1.4 schema lacked creator_anon_id / is_partial; every persist
    then raised OperationalError (swallowed by analyze.py's best-effort
    try/except) — the user's report silently never landed.
    `_migrate_reports_columns` backfills the missing columns via ALTER
    TABLE so a long-lived DB stays forward-compatible.
    """

    def _make_old_reports_db(self, path):
        """Create a `reports` table with a pre-M1.4 (drifted) shape —
        missing rewritten_query / creator_anon_id / is_partial / etc."""
        import sqlite3
        conn = sqlite3.connect(str(path))
        conn.executescript(
            """
            CREATE TABLE reports (
                id          TEXT PRIMARY KEY,
                share_token TEXT,
                query       TEXT,
                b_id        TEXT,
                lang        TEXT,
                payload     TEXT,
                model       TEXT,
                prompt_version TEXT,
                created_at  TEXT
            );
            """
        )
        conn.commit()
        conn.close()

    def test_old_reports_table_gets_missing_columns(self, tmp_path):
        db = tmp_path / "drifted.db"
        self._make_old_reports_db(db)

        # Opening a ReportStore on it must self-heal the schema.
        ReportStore(db)

        import sqlite3
        conn = sqlite3.connect(str(db))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(reports)")}
        conn.close()
        for required in (
            "rewritten_query", "creator_anon_id", "creator_tier",
            "is_public", "view_count", "last_viewed_at", "is_partial",
        ):
            assert required in cols, f"migration must add {required!r}"

    def test_persist_works_after_drift_migration(self, tmp_path, sample_payload):
        """The whole point: after the self-heal, create()/list_by_anon()
        work — i.e. the persist→list chain is no longer silently broken."""
        db = tmp_path / "drifted.db"
        self._make_old_reports_db(db)
        store = ReportStore(db)

        out = store.create(
            query="q", b_id="b", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="anon-after-migrate",
        )
        listed = store.list_by_anon("anon-after-migrate")
        assert [r["id"] for r in listed] == [out["id"]]
        fetched = store.get_by_id(out["id"])
        assert fetched["creator_anon_id"] == "anon-after-migrate"

    def test_migration_is_idempotent(self, tmp_path, sample_payload):
        """Re-opening an already-migrated DB must not error or duplicate."""
        db = tmp_path / "drifted.db"
        self._make_old_reports_db(db)
        ReportStore(db)        # first heal
        store = ReportStore(db)  # second open — must be a no-op
        out = store.create(
            query="q", b_id="b", lang="zh", payload=sample_payload, model="m",
        )
        assert store.get_by_id(out["id"]) is not None


class TestSingleOwnedReportDeletion:
    def test_owner_delete_is_atomic_cascades_children_and_revokes_share(
        self, store, sample_payload,
    ):
        created = store.create(
            query="delete one", b_id="b", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="owner-device",
        )
        rid = created["id"]
        store.claim_by_anon("owner-device", "account-owner")
        store.record_feedback(
            report_id=rid, section=None, vote=1, voter_anon="reader",
        )
        store.record_followup(
            report_id=rid, anon_id="owner-device", action_status="planned",
            publish_to_insights=False,
        )

        with pytest.raises(PermissionError):
            store.delete_report_by_owner(rid, "different-account")
        assert store.get_by_id(rid) is not None
        assert store.get_by_share_token(created["share_token"]) is not None

        deleted = store.delete_report_by_owner(rid, "account-owner")
        assert deleted == {
            "reports": 1,
            "followups": 1,
            "feedback": 1,
            "share_revoked": True,
        }
        assert store.get_by_id(rid) is None
        assert store.get_by_share_token(created["share_token"]) is None
        assert store.get_followup(rid, "owner-device") is None
        assert store.feedback_counts(rid) == {"total_up": 0, "total_down": 0}

    def test_unclaimed_or_unknown_report_cannot_be_deleted_as_owned(
        self, store, sample_payload,
    ):
        created = store.create(
            query="local only", b_id="b", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="local-device",
        )
        with pytest.raises(PermissionError):
            store.delete_report_by_owner(created["id"], "account-owner")
        with pytest.raises(PermissionError):
            store.delete_report_by_owner("r_missing", "account-owner")
        assert store.get_by_id(created["id"]) is not None


# --------- Session #17 V6 — report followup (revisit loop) --------- #


class TestReportFollowup:
    """ReportStore.record_followup / get_followup — V6 revisit loop."""

    def _make_report(self, store, sample_payload):
        return store.create(
            query="q", b_id="b1", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="anon-1",
        )["id"]

    def test_record_and_read_followup(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        fu = store.record_followup(
            report_id=rid, anon_id="anon-1",
            action_status="tried", outcome="worked", note="留存涨了 3 个点",
        )
        assert fu["action_status"] == "tried"
        assert fu["outcome"] == "worked"
        got = store.get_followup(rid, "anon-1")
        assert got["note"] == "留存涨了 3 个点"
        assert got["publish_to_insights"] is False
        # created_at == updated_at on first insert.
        assert got["created_at"] == got["updated_at"]

    def test_followup_upsert_latest_wins(self, store, sample_payload):
        """Re-submitting updates the row, keeps created_at, bumps updated_at."""
        rid = self._make_report(store, sample_payload)
        first = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
        )
        second = store.record_followup(
            report_id=rid, anon_id="anon-1",
            action_status="tried", outcome="partial",
        )
        # One row only — the unique (report_id, anon_id) upsert fired.
        assert second["action_status"] == "tried"
        assert second["outcome"] == "partial"
        assert second["created_at"] == first["created_at"]

    def test_followup_per_anon_isolated(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="tried",
        )
        store.record_followup(
            report_id=rid, anon_id="anon-2", action_status="abandoned",
        )
        assert store.get_followup(rid, "anon-1")["action_status"] == "tried"
        assert store.get_followup(rid, "anon-2")["action_status"] == "abandoned"

    def test_publication_consent_is_explicit_preserved_and_revocable(
        self, store, sample_payload,
    ):
        rid = self._make_report(store, sample_payload)
        first = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="tried",
            outcome="worked", publish_to_insights=True,
        )
        assert first["publish_to_insights"] is True
        assert first["consent_version"] == "insights-public-v1"
        assert first["consented_at"]
        assert first["withdrawn_at"] is None
        preserved = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="tried",
            outcome="worked",
        )
        assert preserved["publish_to_insights"] is True
        assert preserved["consent_version"] == first["consent_version"]
        assert preserved["consented_at"] == first["consented_at"]
        revoked = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="tried",
            outcome="worked", publish_to_insights=False,
        )
        assert revoked["publish_to_insights"] is False
        assert revoked["consent_version"] == first["consent_version"]
        assert revoked["consented_at"] == first["consented_at"]
        assert revoked["withdrawn_at"]

    def test_first_private_choice_is_not_mislabeled_as_withdrawal(
        self, store, sample_payload,
    ):
        rid = self._make_report(store, sample_payload)
        first = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
            publish_to_insights=False,
        )
        assert first["publish_to_insights"] is False
        assert first["consent_version"] is None
        assert first["consented_at"] is None
        assert first["withdrawn_at"] is None
        repeated = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
            publish_to_insights=False,
        )
        assert repeated["withdrawn_at"] is None

    def test_reconsent_after_text_version_change_refreshes_timestamp(
        self, store, sample_payload,
    ):
        rid = self._make_report(store, sample_payload)
        store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
            publish_to_insights=True,
        )
        old_timestamp = "2026-01-01T00:00:00.000000Z"
        with store._connect() as conn:
            conn.execute(
                "UPDATE report_followup SET consent_version=?, consented_at=? "
                "WHERE report_id=? AND anon_id=?",
                ("insights-public-v0", old_timestamp, rid, "anon-1"),
            )
        renewed = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
            publish_to_insights=True,
        )
        assert renewed["consent_version"] == "insights-public-v1"
        assert renewed["consented_at"] != old_timestamp
        assert renewed["withdrawn_at"] is None

    def test_claimed_owner_can_withdraw_consent_from_another_device(
        self, store, sample_payload,
    ):
        rid = store.create(
            query="q", b_id="b1", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="device-a",
        )["id"]
        store.record_followup(
            report_id=rid, anon_id="device-a", action_status="tried",
            outcome="worked", publish_to_insights=True,
        )
        store.claim_by_anon("device-a", "account-owner")
        with pytest.raises(PermissionError):
            store.withdraw_insights_consent_by_owner(rid, "different-account")
        withdrawn = store.withdraw_insights_consent_by_owner(
            rid, "account-owner",
        )
        assert withdrawn["publish_to_insights"] is False
        assert withdrawn["consent_version"] == "insights-public-v1"
        assert withdrawn["consented_at"]
        assert withdrawn["withdrawn_at"]
        assert store.get_followup(rid, "device-a")[
            "publish_to_insights"
        ] is False

    def test_owner_withdraw_without_prior_consent_has_no_withdrawal_timestamp(
        self, store, sample_payload,
    ):
        rid = store.create(
            query="q", b_id="b1", lang="zh", payload=sample_payload,
            model="m", creator_anon_id="device-a",
        )["id"]
        store.record_followup(
            report_id=rid, anon_id="device-a", action_status="planned",
            publish_to_insights=False,
        )
        store.claim_by_anon("device-a", "account-owner")
        withdrawn = store.withdraw_insights_consent_by_owner(
            rid, "account-owner",
        )
        assert withdrawn["publish_to_insights"] is False
        assert withdrawn["consent_version"] is None
        assert withdrawn["consented_at"] is None
        assert withdrawn["withdrawn_at"] is None

    def test_publication_consent_rejects_non_boolean(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        with pytest.raises(ValueError, match="must be a boolean"):
            store.record_followup(
                report_id=rid, anon_id="anon-1", action_status="tried",
                outcome="worked", publish_to_insights="yes",
            )

    def test_followup_missing_anon_collapses_to_anon_bucket(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        store.record_followup(
            report_id=rid, anon_id=None, action_status="planned",
        )
        assert store.get_followup(rid, None)["anon_id"] == "anon"

    def test_followup_rejects_bad_action_status(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        with pytest.raises(ValueError):
            store.record_followup(
                report_id=rid, anon_id="a", action_status="garbage",
            )

    def test_followup_rejects_bad_outcome(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        with pytest.raises(ValueError):
            store.record_followup(
                report_id=rid, anon_id="a", action_status="tried",
                outcome="exploded",
            )

    def test_get_followup_returns_none_when_absent(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        assert store.get_followup(rid, "nobody") is None

    def test_followup_table_self_heals_on_drifted_db(self, tmp_path, sample_payload):
        """A history.db lacking report_followup gets the table on open."""
        import sqlite3
        db = tmp_path / "drift.db"
        # Simulate a pre-V6 DB: reports table exists, no report_followup.
        conn = sqlite3.connect(str(db))
        conn.execute(
            "CREATE TABLE reports (id TEXT PRIMARY KEY, share_token TEXT, "
            "query TEXT, b_id TEXT, lang TEXT, payload TEXT, model TEXT, "
            "prompt_version TEXT, created_at TEXT)"
        )
        conn.commit()
        conn.close()
        store = ReportStore(db)  # CREATE TABLE IF NOT EXISTS adds followup
        rid = store.create(
            query="q", b_id="b", lang="zh", payload=sample_payload, model="m",
        )["id"]
        fu = store.record_followup(
            report_id=rid, anon_id="a", action_status="tried",
        )
        assert fu["action_status"] == "tried"

    def test_structured_experiment_round_trip_and_legacy_update(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        experiment = {
            "hypothesis": "A shorter form improves completion",
            "owner": "PM",
            "deadline": "2026-08-01",
            "baseline": 0.31,
            "primary_metric": "completion_rate",
            "success_threshold": 0.4,
            "stop_condition": "1000 exposures",
            "status": "planned",
            "notes": "Segment by device",
        }
        created = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
            experiment=experiment,
        )
        assert created["experiment"] == experiment
        assert created["outcome_detail"] is None

        # An old client updating only legacy fields must not erase new data.
        updated = store.record_followup(
            report_id=rid, anon_id="anon-1", action_status="planned",
        )
        assert updated["experiment"] == experiment

    def test_experiment_state_machine_and_outcome_guardrails(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        store.record_followup(
            report_id=rid, anon_id="a", action_status="planned",
            experiment={"hypothesis": "h", "status": "planned"},
        )
        with pytest.raises(ValueError, match="status transition"):
            store.record_followup(
                report_id=rid, anon_id="a", action_status="tried",
                experiment={"hypothesis": "h", "status": "completed"},
            )
        with pytest.raises(ValueError, match="completed or stopped"):
            store.record_followup(
                report_id=rid, anon_id="a", action_status="tried",
                outcome_detail={"result": "success", "actual_metric": 0.5},
            )
        store.record_followup(
            report_id=rid, anon_id="a", action_status="in_progress",
            experiment={"status": "in_progress"},
        )
        done = store.record_followup(
            report_id=rid, anon_id="a", action_status="tried", outcome="worked",
            experiment={"status": "completed"},
            outcome_detail={
                "actual_metric": 0.5, "result": "success",
                "learning": "Less friction helped", "next_decision": "scale",
            },
        )
        assert done["outcome_detail"]["next_decision"] == "scale"

    def test_partial_experiment_update_merges_old_fields(self, store, sample_payload):
        rid = self._make_report(store, sample_payload)
        store.record_followup(
            report_id=rid, anon_id="a", action_status="planned",
            experiment={
                "hypothesis": "h", "owner": "Ada", "deadline": "2026-08-01",
                "status": "planned",
            },
        )
        updated = store.record_followup(
            report_id=rid, anon_id="a", action_status="in_progress",
            experiment={"status": "in_progress"},
        )
        assert updated["experiment"]["owner"] == "Ada"
        assert updated["experiment"]["deadline"] == "2026-08-01"
        assert updated["experiment"]["hypothesis"] == "h"

    @pytest.mark.parametrize("action_status,outcome,experiment,detail", [
        ("abandoned", "", {"hypothesis": "h", "status": "in_progress"}, None),
        ("tried", "worked", {"hypothesis": "h", "status": "stopped"}, None),
        ("tried", "worked", {"hypothesis": "h", "status": "completed"},
         {"result": "failure", "failure_reason": "no lift"}),
    ])
    def test_rejects_conflicting_legacy_and_structured_state(
        self, store, sample_payload, action_status, outcome, experiment, detail,
    ):
        rid = self._make_report(store, sample_payload)
        with pytest.raises(ValueError, match="conflicts"):
            store.record_followup(
                report_id=rid, anon_id="a", action_status=action_status,
                outcome=outcome, experiment=experiment, outcome_detail=detail,
            )

    @pytest.mark.parametrize("experiment", [
        {"hypothesis": ""},
        {"hypothesis": "h", "deadline": "01-08-2026"},
        {"hypothesis": "h", "baseline": True},
        {"hypothesis": "h", "unknown": "x"},
    ])
    def test_experiment_rejects_invalid_schema(self, store, sample_payload, experiment):
        rid = self._make_report(store, sample_payload)
        with pytest.raises(ValueError):
            store.record_followup(
                report_id=rid, anon_id="a", action_status="planned",
                experiment=experiment,
            )

    def test_followup_columns_self_heal_without_losing_old_row(self, tmp_path):
        import sqlite3
        db = tmp_path / "old_followup.db"
        ReportStore(db)
        with sqlite3.connect(str(db)) as conn:
            conn.execute("ALTER TABLE report_followup RENAME TO old_followup")
            conn.execute(
                "CREATE TABLE report_followup (id INTEGER PRIMARY KEY, "
                "report_id TEXT, anon_id TEXT, action_status TEXT, outcome TEXT, "
                "note TEXT, created_at TEXT, updated_at TEXT, "
                "UNIQUE(report_id, anon_id))"
            )
            conn.execute(
                "INSERT INTO report_followup VALUES "
                "(1, 'r_old', 'a', 'tried', 'worked', 'legacy', 't', 't')"
            )
            conn.execute("DROP TABLE old_followup")
        healed = ReportStore(db)
        got = healed.get_followup("r_old", "a")
        assert got["note"] == "legacy"
        assert got["experiment"] is None
        assert got["publish_to_insights"] is False
        assert got["consent_version"] is None
        assert got["consented_at"] is None
        assert got["withdrawn_at"] is None


def test_private_followups_do_not_install_public_aggregate_api(
    store, sample_payload,
):
    out = store.create(
        query="q", b_id="target", lang="en", payload=sample_payload,
        model="m", creator_anon_id="owner-0",
    )
    store.record_followup(
        report_id=out["id"], anon_id="attacker",
        action_status="tried", outcome="worked", publish_to_insights=True,
    )
    store.record_followup(
        report_id=out["id"], anon_id="owner-0",
        action_status="tried", outcome="worked", publish_to_insights=True,
    )
    for i in range(1, 5):
        owner = f"owner-{i}"
        extra = store.create(
            query="private", b_id="target", lang="en",
            payload=sample_payload, model="m", creator_anon_id=owner,
        )
        store.record_followup(
            report_id=extra["id"], anon_id=owner,
            action_status="tried", outcome="worked", publish_to_insights=True,
        )
    for removed in (
        "verified_isomorphisms", "count_human_verified",
        "stuck_structures", "insights_summary",
    ):
        assert not hasattr(store, removed)
