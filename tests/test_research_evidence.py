"""D1's isolated transaction probes, not C0/product integration acceptance."""
from dataclasses import replace
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from uuid import uuid4

from web.backend.research.evidence_repository import DDL, EvidenceContext, EvidenceRepository
from web.backend.research.evidence_schemas import (
    AnalysisPlan, DataSnapshot, EvidenceExcerpt, EvidenceClaim, EvidenceReport,
    ExecutionRecord, Licence, POLICY, canonical, decode, encode, sha256,
)


def uid():
    return str(uuid4())


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "controlled-auth.sqlite"
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.context = EvidenceContext(research_id=uid(), input_revision=1, task_id=uid(), attempt=1,
            input_digest="a" * 64, principal_id=uid(), principal_epoch=1, owner_epoch=1,
            acl_epoch=1, task_version=1, step_id=uid(), step_version=1)
        # Minimal fixture for the C0-owned authorizer and parent control table;
        # D1 never initializes a separate production DB or claims this is C0.
        self.conn.execute("CREATE TABLE research_controls(id TEXT PRIMARY KEY)")
        self.conn.execute("CREATE TABLE fixture_auth(binding TEXT, stopped INTEGER, lifecycle TEXT)")
        self.conn.execute("INSERT INTO research_controls VALUES(?)", (self.context.research_id,))
        self.conn.execute("INSERT INTO fixture_auth VALUES(?,0,'active')", (canonical(self.context.__dict__),))
        for statement in DDL:
            self.conn.execute(statement)
        self.conn.commit()
        self.conn.execute("BEGIN IMMEDIATE")
        self.repo = EvidenceRepository(self.conn, self.authorize)
        binding = {k: getattr(self.context, k) for k in ("research_id", "input_revision", "task_id", "attempt", "input_digest")}
        self.binding = binding
        self.plan = AnalysisPlan(**binding, id=uid(), query="stock market partial correlation", external_query_approved=True,
            objective="Distinguish common drivers from a causal claim.", competing_explanations=("Common news",),
            required_evidence=("Methods and pilot identity evidence",), stop_rule="Stop at permission or response limit.",
            created_at="2026-10-17T00:00:00Z")
        self.raw = b"<article>Partial correlation is not proof of causation.</article>"
        self.extracted = "Partial correlation is not proof of causation."
        self.discovery = json.dumps({"message": {"items": [{"DOI": "10.1371/journal.pone.0015032", "title": ["Fixture method article"]}]}}).encode()
        self.snapshot = DataSnapshot(**binding, id=uid(), source_id=uid(), source_revision=1,
            title="Fixture method article", doi="10.1371/journal.pone.0015032",
            canonical_url="https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0015032",
            query_digest=sha256(self.plan.query.encode()), discovery_digest=sha256(self.discovery), acquired_at="2026-10-17T00:00:00Z",
            information_cutoff="2026-10-17T00:00:00Z", raw_digest=sha256(self.raw),
            extracted_digest=sha256(self.extracted.encode()), parser_version="plos-html-text-v1",
            licence=Licence(status="verified", private_cache=True, display_excerpt=True, export_excerpt=True, basis="Synthetic permission fixture, not a real article licence."),
            origin="offline_probe")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def authorize(self, conn, context, operation):
        binding, stopped, lifecycle = conn.execute("SELECT * FROM fixture_auth").fetchone()
        if binding != canonical(context.__dict__) or lifecycle not in ({"active", "deleting"} if operation == "delete" else {"active"}):
            raise PermissionError("revoked")
        if stopped and operation == "write":
            raise PermissionError("cancelled")
        return True

    def seed(self):
        self.repo.put(self.context, self.plan)
        self.repo.put(self.context, self.snapshot, raw=self.raw, extracted=self.extracted, discovery=self.discovery)
        self.excerpt = EvidenceExcerpt(**self.binding, id=uid(), snapshot_id=self.snapshot.id,
            extracted_digest=self.snapshot.extracted_digest, start=0, end=len(self.extracted), quote=self.extracted)
        self.repo.put(self.context, self.excerpt)
        self.claim = EvidenceClaim(**self.binding, id=uid(), text="Possible common-factor explanation; not a pilot result.",
            excerpt_refs=(self.excerpt.id,), limitations=("Source identity and semantic support require independent review.",))
        self.repo.put(self.context, self.claim)
        self.execution = ExecutionRecord(**self.binding, id=uid(), plan_id=self.plan.id,
            step_id=self.context.step_id, dispatch_id=uid(), step_version=1, executor_version=POLICY,
            started_at="2026-10-17T00:00:00Z", ended_at="2026-10-17T00:00:01Z",
            status="succeeded", origin="offline_probe", request_count=2, http_status=200, snapshot_refs=(self.snapshot.id,))
        self.repo.put(self.context, self.execution)
        self.report = EvidenceReport(**self.binding, id=uid(), plan_id=self.plan.id,
            snapshot_refs=(self.snapshot.id,), execution_refs=(self.execution.id,), claim_refs=(self.claim.id,),
            outstanding_requirements=("No pilot price series or model analysis.",), origin="offline_probe")
        self.repo.put(self.context, self.report)

    def test_complete_subchain_persists_reopens_same_auth_db(self):
        self.seed()
        expected = encode(self.repo.get(self.context, "reports", self.report.id))
        self.conn.commit()
        self.conn.close()
        self.conn = sqlite3.connect(self.path)
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("BEGIN")
        self.repo = EvidenceRepository(self.conn, self.authorize)
        self.assertEqual(encode(self.repo.get(self.context, "reports", self.report.id)), expected)
        self.assertFalse(self.report.model_analysis_ran)
        self.assertEqual(self.report.evidence, "INSUFFICIENT")

    def test_duplicate_worker_is_idempotent_but_changed_record_rejected(self):
        self.assertTrue(self.repo.put(self.context, self.plan))
        self.assertFalse(self.repo.put(self.context, self.plan))
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.plan, objective="Changed objective"))

    def test_cancellation_and_late_source_cannot_write(self):
        self.repo.put(self.context, self.plan)
        self.conn.execute("UPDATE fixture_auth SET stopped=1")
        with self.assertRaises(PermissionError):
            self.repo.put(self.context, self.snapshot, raw=self.raw, extracted=self.extracted, discovery=self.discovery)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0], 1)

    def test_each_authorization_dimension_is_rechecked(self):
        self.seed()
        for field, value in (("principal_id", uid()), ("owner_epoch", 2), ("acl_epoch", 2),
                ("principal_epoch", 2), ("input_revision", 2), ("task_id", uid()),
                ("attempt", 2), ("step_version", 2), ("task_version", 2)):
            with self.subTest(field=field), self.assertRaises(PermissionError):
                self.repo.get(replace(self.context, **{field: value}), "reports", self.report.id)

    def test_deleted_account_blocks_read_and_cannot_resurrect(self):
        self.seed()
        self.conn.execute("UPDATE fixture_auth SET lifecycle='deleting'")
        with self.assertRaises(PermissionError):
            self.repo.get(self.context, "reports", self.report.id)
        self.assertEqual(self.repo.purge(self.context), 6)
        self.conn.execute("UPDATE fixture_auth SET lifecycle='deleted'")
        with self.assertRaises(PermissionError):
            self.repo.put(self.context, self.plan)

    def test_parent_deletion_cascades_private_cached_content(self):
        self.seed()
        self.conn.execute("DELETE FROM research_controls WHERE id=?", (self.context.research_id,))
        self.assertEqual(self.conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0], 0)

    def test_repository_does_not_commit_or_open_another_database(self):
        self.repo.put(self.context, self.plan)
        self.conn.rollback()
        self.conn.execute("BEGIN")
        self.assertEqual(self.conn.execute("SELECT count(*) FROM research_evidence_objects").fetchone()[0], 0)
        self.assertEqual([p.name for p in Path(self.tmp.name).iterdir()], [self.path.name])

    def test_requires_transaction_and_explicit_authorizer_ack(self):
        self.conn.commit()
        with self.assertRaises(ValueError):
            self.repo.put(self.context, self.plan)
        self.conn.execute("BEGIN")
        with self.assertRaises(PermissionError):
            EvidenceRepository(self.conn, lambda *_: None).put(self.context, self.plan)

    def test_no_permission_means_no_cache_or_excerpt(self):
        unknown = replace(self.snapshot, licence=Licence())
        self.repo.put(self.context, unknown)
        with self.assertRaises(PermissionError):
            self.repo.put(self.context, unknown, raw=self.raw, extracted=self.extracted, discovery=self.discovery)
        self.excerpt = EvidenceExcerpt(**self.binding, id=uid(), snapshot_id=unknown.id,
            extracted_digest=unknown.extracted_digest, start=0, end=7, quote="Partial")
        with self.assertRaises(PermissionError):
            self.repo.put(self.context, self.excerpt)

    def test_export_permission_is_independent_of_cache_and_display(self):
        self.snapshot = replace(self.snapshot, licence=replace(self.snapshot.licence, export_excerpt=False))
        self.seed()
        self.assertEqual(self.repo.get(self.context, "reports", self.report.id), self.report)
        with self.assertRaises(PermissionError):
            self.repo.get(self.context, "reports", self.report.id, export=True)

    def test_fabricated_quote_or_hash_rejected(self):
        self.seed()
        for excerpt in (replace(self.excerpt, id=uid(), quote="X" * len(self.extracted)),
                        replace(self.excerpt, id=uid(), extracted_digest="b" * 64)):
            with self.assertRaises(ValueError):
                self.repo.put(self.context, excerpt)
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.snapshot, id=uid()), raw=b"tampered", extracted=self.extracted, discovery=self.discovery)

    def test_reference_cannot_cross_task_or_revision(self):
        self.seed()
        context = replace(self.context, input_revision=2)
        self.conn.execute("UPDATE fixture_auth SET binding=?", (canonical(context.__dict__),))
        with self.assertRaises(LookupError):
            self.repo.put(context, replace(self.claim, id=uid(), input_revision=2))

    def test_failed_execution_or_unrelated_source_not_reported(self):
        self.seed()
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.execution, id=uid(), status="outcome_unknown"))
        with self.assertRaises(LookupError):
            self.repo.put(self.context, replace(self.report, id=uid(), snapshot_refs=(uid(),)))

    def test_offline_evidence_cannot_be_relabelled_as_live_execution(self):
        self.seed()
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.execution, id=uid(), origin="live"))
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.report, id=uid(), origin="live"))

    def test_cache_tampering_and_fabricated_discovery_identity_rejected(self):
        self.seed()
        fake = json.dumps({"message": {"items": [{"DOI": "10.1371/journal.pone.9999999", "title": [self.snapshot.title]}]}}).encode()
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.snapshot, id=uid(), discovery_digest=sha256(fake)),
                          raw=self.raw, extracted=self.extracted, discovery=fake)
        self.conn.execute("DROP TRIGGER research_evidence_immutable")
        self.conn.execute("UPDATE research_evidence_objects SET extracted='tampered' WHERE kind='snapshots'")
        with self.assertRaises(ValueError):
            self.repo.get(self.context, "excerpts", self.excerpt.id)

    def test_report_cannot_borrow_a_different_querys_execution(self):
        self.seed()
        plan = replace(self.plan, id=uid(), query="unrelated market topic")
        self.repo.put(self.context, plan)
        execution = replace(self.execution, id=uid(), plan_id=plan.id)
        self.repo.put(self.context, execution)
        with self.assertRaises(ValueError):
            self.repo.put(self.context, replace(self.report, id=uid(), plan_id=plan.id, execution_refs=(execution.id,)))

    def test_historical_import_cannot_claim_new_request_observation(self):
        self.seed()
        with self.assertRaises(ValueError):
            replace(self.execution, origin="historical_import")
        imported = replace(self.execution, origin="historical_import", request_count=0, http_status=None)
        self.assertEqual(imported.request_count, 0)

    def test_stale_execution_cannot_commit(self):
        self.seed()
        with self.assertRaises(PermissionError):
            self.repo.put(self.context, replace(self.execution, id=uid(), step_version=2))

    def test_false_completion_and_unreviewed_semantics_cannot_be_upgraded(self):
        self.seed()
        for kwargs in ({"evidence": "SCOPE_COMPLETE"}, {"status": "complete_for_scope"},
                       {"model_analysis_ran": True}, {"statistics_ran": True}, {"artifact_refs": (uid(),)}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                replace(self.report, **kwargs)
        with self.assertRaises(ValueError):
            replace(self.claim, level="empirical_record")

    def test_strict_schema_bounds_and_unknown_keys(self):
        with self.assertRaises(ValueError):
            replace(self.context, attempt=True)
        with self.assertRaises(ValueError):
            replace(self.plan, max_requests=True)
        with self.assertRaises(ValueError):
            replace(self.plan, external_query_approved=False)
        with self.assertRaises(ValueError):
            Licence(private_cache=True)
        with self.assertRaises(TypeError):
            decode("plans", encode(self.plan)[:-1] + ',"sql":"SELECT 1"}')
        with self.assertRaises(ValueError):
            decode("plans", '{"id":"x","id":"y"}')

    def test_persisted_tampering_detected(self):
        self.repo.put(self.context, self.plan)
        self.conn.execute("DROP TRIGGER research_evidence_immutable")
        self.conn.execute("UPDATE research_evidence_objects SET payload_digest=?", ("0" * 64,))
        with self.assertRaises(ValueError):
            self.repo.get(self.context, "plans", self.plan.id)


if __name__ == "__main__":
    unittest.main()
