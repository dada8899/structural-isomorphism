"""Evidence persistence inside a caller-owned C0 transaction, never a new DB.

DDL is an integration proposal, not executed on import or by this repository.
C0's migration/deletion owner must review and install it before wiring D1.
The supplied authorizer must recheck identity/owner epochs, input revision,
task/attempt/step CAS and stop intent in *this* transaction on every call.
"""
from dataclasses import dataclass
import sqlite3

from .evidence_schemas import (
    Binding, DataSnapshot, EvidenceExcerpt, EvidenceClaim, EvidenceReport,
    ExecutionRecord, AnalysisPlan, KINDS, RECORD_TYPES, canonical, decode, encode, sha256,
)


DDL = (
    """CREATE TABLE research_evidence_objects (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN
        ('snapshots','plans','executions','excerpts','claims','reports')),
        research_id TEXT NOT NULL REFERENCES research_controls(id) ON DELETE CASCADE,
        input_revision INTEGER NOT NULL, task_id TEXT NOT NULL, attempt INTEGER NOT NULL,
        payload TEXT NOT NULL CHECK(json_valid(payload)), payload_digest TEXT NOT NULL,
        raw BLOB, extracted TEXT, discovery BLOB)""",
    "CREATE INDEX research_evidence_scope ON research_evidence_objects(research_id,input_revision,task_id,attempt,kind)",
    """CREATE TRIGGER research_evidence_immutable BEFORE UPDATE ON research_evidence_objects
        BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END""",
)


@dataclass(frozen=True, kw_only=True)
class EvidenceContext(Binding):
    """Opaque integration context; possession alone is never authorization."""
    principal_id: str
    principal_epoch: int
    owner_epoch: int
    acl_epoch: int
    task_version: int
    step_id: str
    step_version: int

    def __post_init__(self):
        super().__post_init__()
        from .evidence_schemas import identifier, positive
        identifier(self.principal_id)
        identifier(self.step_id)
        for v in (self.principal_epoch, self.owner_epoch, self.acl_epoch, self.task_version, self.step_version):
            positive(v)


class EvidenceRepository:
    def __init__(self, conn: sqlite3.Connection, authorize):
        if not isinstance(conn, sqlite3.Connection) or not callable(authorize):
            raise ValueError("controlled transaction and authorizer required")
        self.conn, self.authorize = conn, authorize

    def _guard(self, context, operation):
        if type(context) is not EvidenceContext or not self.conn.in_transaction:
            raise ValueError("active controlled transaction required")
        if self.conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise ValueError("foreign key enforcement required")
        # Callback must raise on failure and explicitly acknowledge success.
        if self.authorize(self.conn, context, operation) is not True:
            raise PermissionError("evidence authorization denied")

    @staticmethod
    def _same(context, record):
        for key in Binding.__dataclass_fields__:
            if getattr(context, key) != getattr(record, key):
                raise PermissionError("evidence scope mismatch")

    def _get(self, context, kind, record_id):
        if kind not in KINDS:
            raise ValueError("fixed record kind required")
        row = self.conn.execute("SELECT payload,raw,extracted,payload_digest,discovery FROM research_evidence_objects WHERE id=? AND kind=? AND research_id=? AND input_revision=? AND task_id=? AND attempt=?",
            (record_id, kind, context.research_id, context.input_revision, context.task_id, context.attempt)).fetchone()
        if row is None:
            raise LookupError("evidence not found")
        if sha256(row[0].encode()) != row[3]:
            raise ValueError("persisted evidence digest mismatch")
        record = decode(kind, row[0])
        self._same(context, record)
        if type(record) is DataSnapshot and any(v is not None for v in (row[1], row[2], row[4])):
            if (not record.licence.private_cache or type(row[1]) is not bytes or type(row[2]) is not str or type(row[4]) is not bytes
                    or sha256(row[1]) != record.raw_digest or sha256(row[2].encode()) != record.extracted_digest
                    or sha256(row[4]) != record.discovery_digest):
                raise ValueError("cached evidence integrity mismatch")
        return record, row[1], row[2]

    def get(self, context, kind, record_id, *, export=False):
        self._guard(context, "export" if export else "read")
        record, _, _ = self._get(context, kind, record_id)
        self._permissions(context, record, export=export)
        # Raw files and internal context are not an API projection. The caller
        # must still apply C0's explicit public field whitelist.
        return record

    def excerpt_details(self,context,excerpt_id):
        """Authorized exact short quote and original identity; no export grant."""
        excerpt=self.get(context,'excerpts',excerpt_id)
        snapshot=self.get(context,'snapshots',excerpt.snapshot_id)
        _,raw,text=self._get(context,'snapshots',snapshot.id)
        if (type(raw) is not bytes or type(text) is not str or not snapshot.licence.private_cache
                or not snapshot.licence.display_excerpt or excerpt.extracted_digest!=snapshot.extracted_digest
                or text[excerpt.start:excerpt.end]!=excerpt.quote):
            raise PermissionError('original exact readable excerpt required')
        records={row[0]:row[1] for row in self.conn.execute('SELECT id,payload_digest FROM research_evidence_objects WHERE id IN (?,?)',(excerpt.id,snapshot.id))}
        return {'excerpt_id':excerpt.id,'snapshot_id':snapshot.id,'source_id':snapshot.source_id,
            'source_revision':snapshot.source_revision,'content_digest':snapshot.extracted_digest,
            'raw_digest':snapshot.raw_digest,'excerpt_digest':records[excerpt.id],'snapshot_digest':records[snapshot.id],
            'start':excerpt.start,'end':excerpt.end,'quote':excerpt.quote,'title':snapshot.title,
            'canonical_url':snapshot.canonical_url,'licence_basis':snapshot.licence.basis,
            'task_id':context.task_id,'attempt':context.attempt,'input_revision':context.input_revision}

    def provider_eligibility(self,context,excerpt_id):
        """Recheck stored publisher proof; return no grant or outbound handle.

        External consumers use this public port instead of private cache reads.
        Eligibility is deliberately distinct from user/funding/send approval.
        """
        self._guard(context,"read")
        excerpt,_,_=self._get(context,"excerpts",excerpt_id)
        self._permissions(context,excerpt)
        snapshot,raw,extracted=self._get(context,"snapshots",excerpt.snapshot_id)
        if snapshot.parser_version!="plos-author-narrative-subset-v2" or snapshot.origin not in ("live","offline_probe"):
            raise PermissionError("reviewed narrative scope required")
        from .source_adapters.crossref_plos import strict_json,Hit,parse_article
        from .source_policy import decompress,RAW_CAP,TEXT_CAP
        if type(raw) is not bytes or len(raw)>RAW_CAP or type(extracted) is not str or len(extracted)>TEXT_CAP:
            raise ValueError("bounded stored source required")
        discovery=self.conn.execute("SELECT discovery FROM research_evidence_objects WHERE id=? AND kind='snapshots'",(snapshot.id,)).fetchone()[0]
        metadata=strict_json(discovery)
        if (type(metadata) is not dict or metadata.get("status")!="ok" or metadata.get("message-type")!="work-list"
                or type(metadata.get("message")) is not dict):
            raise ValueError("publisher discovery object required")
        items=metadata["message"].get("items")
        if type(items) is not list or len(items)>3:raise ValueError("bounded publisher discovery required")
        matching=[item for item in items if type(item) is dict and item.get("DOI")==snapshot.doi and item.get("title")==[snapshot.title]]
        if len(matching)!=1:raise PermissionError("matched original identity required")
        licences=matching[0].get("license",[])
        if type(licences) is not list or len(licences)>20:raise PermissionError("publisher licence proof unavailable")
        cc_by=any(type(item) is dict and item.get("content-version") in ("vor","unspecified") and item.get("URL") in
            ("http://creativecommons.org/licenses/by/4.0/","https://creativecommons.org/licenses/by/4.0/") for item in licences)
        decoded=decompress(raw,"gzip" if raw.startswith(b"\x1f\x8b") else "identity")
        original,licence=parse_article(decoded,Hit(snapshot.doi,snapshot.title,cc_by))
        if licence.status!="verified" or not cc_by or original!=extracted or sha256(original.encode())!=snapshot.extracted_digest:
            raise PermissionError("independent current-article licence/scope proof required")
        if (excerpt.extracted_digest!=snapshot.extracted_digest or extracted[excerpt.start:excerpt.end]!=excerpt.quote
                or len(excerpt.quote.split())>20 or len(excerpt.quote)>1000):
            raise ValueError("exact short excerpt required")
        from .provider_evidence import ProviderEligibleExcerpt
        return ProviderEligibleExcerpt(source_id=snapshot.source_id,source_revision=snapshot.source_revision,excerpt_id=excerpt.id,
            title=snapshot.title,canonical_url=snapshot.canonical_url,
            attribution=f"{snapshot.title[:180]} — {snapshot.canonical_url} — CC BY 4.0",
            extracted_digest=snapshot.extracted_digest,raw_digest=snapshot.raw_digest,discovery_digest=snapshot.discovery_digest,
            acquired_at=snapshot.acquired_at,information_cutoff=snapshot.information_cutoff,
            start=excerpt.start,end=excerpt.end,quote=excerpt.quote,origin=snapshot.origin,
            permission_basis_digest=sha256(canonical({"policy":"plos-ccby-subset-eligibility-v1","basis":licence.basis,
                "raw_digest":snapshot.raw_digest,"discovery_digest":snapshot.discovery_digest,"read_scope":"author_narrative_subset"}).encode()))

    def confirmed_provider_handle(self,context,excerpt_id,authority,handle):
        """New consent-only port; the CP1 candidate path remains unchanged."""
        from .paid_approval import PaidPacketAuthority
        if type(authority) is not PaidPacketAuthority:raise PermissionError('actual paid consent required')
        binding=authority.require(self.conn,'packet')
        if excerpt_id not in binding.source_refs or context.research_id!=binding.research_id or context.input_revision!=binding.input_revision:
            raise PermissionError('paid source binding mismatch')
        candidate=self.provider_eligibility(context,excerpt_id)
        excerpt,_,_=self._get(context,'excerpts',excerpt_id)
        snapshot,raw,extracted=self._get(context,'snapshots',excerpt.snapshot_id)
        from .source_policy import decompress
        from .provider_evidence import complete_attribution
        from .provider_schemas import EvidenceHandle
        attribution=complete_attribution(decompress(raw,'gzip' if raw.startswith(b'\x1f\x8b') else 'identity'),snapshot)
        return EvidenceHandle(handle=handle,source_id=candidate.source_id,source_revision=candidate.source_revision,
            excerpt_id=excerpt_id,title=candidate.title,attribution=attribution,extracted_digest=candidate.extracted_digest,
            extracted_text=extracted,start=candidate.start,end=candidate.end,quote=candidate.quote,
            display_permission=True,may_send_to_provider=True)

    def preview_provider_handle(self,context,excerpt_id,handle):
        """Read complete credit as display data, never an approved handle."""
        candidate=self.provider_eligibility(context,excerpt_id)
        excerpt,_,_=self._get(context,'excerpts',excerpt_id)
        snapshot,raw,_=self._get(context,'snapshots',excerpt.snapshot_id)
        from .source_policy import decompress
        from .provider_evidence import complete_attribution
        from .preview_codec import PreviewOutboundHandle
        attribution=complete_attribution(decompress(raw,'gzip' if raw.startswith(b'\x1f\x8b') else 'identity'),snapshot)
        return candidate,PreviewOutboundHandle(handle=handle,source_id=candidate.source_id,source_revision=candidate.source_revision,
            excerpt_id=excerpt_id,title=candidate.title,attribution=attribution,extracted_digest=candidate.extracted_digest,
            start=candidate.start,end=candidate.end,quote=candidate.quote)

    def _permissions(self, context, record, *, export=False):
        snapshots = []
        if type(record) is DataSnapshot:
            snapshots = [record]
        elif type(record) is EvidenceExcerpt:
            snapshots = [self._get(context, "snapshots", record.snapshot_id)[0]]
        elif type(record) is EvidenceClaim:
            for ref in record.excerpt_refs:
                self._permissions(context, self._get(context, "excerpts", ref)[0], export=export)
        elif type(record) is EvidenceReport:
            for kind, values in (("snapshots", record.snapshot_refs), ("claims", record.claim_refs)):
                for ref in values:
                    self._permissions(context, self._get(context, kind, ref)[0], export=export)
        for snapshot in snapshots:
            if type(record) is not DataSnapshot and not snapshot.licence.display_excerpt:
                raise PermissionError("excerpt display not permitted")
            if export and not snapshot.licence.export_excerpt:
                raise PermissionError("evidence export not permitted")

    def put(self, context, record, *, raw=None, extracted=None, discovery=None):
        self._guard(context, "write")
        self._same(context, record)
        payload = encode(record)
        kind = next(k for k, t in RECORD_TYPES.items() if type(record) is t)
        if type(record) is DataSnapshot:
            if raw is not None or extracted is not None or discovery is not None:
                if not record.licence.private_cache:
                    raise PermissionError("private cache not permitted")
                if (type(raw) is not bytes or len(raw) > 2097152 or type(extracted) is not str or len(extracted) > 200000
                        or type(discovery) is not bytes or len(discovery) > 2097152):
                    raise ValueError("bounded original and extraction required")
                if (sha256(raw) != record.raw_digest or sha256(extracted.encode()) != record.extracted_digest
                        or sha256(discovery) != record.discovery_digest):
                    raise ValueError("snapshot content digest mismatch")
                from .source_adapters.crossref_plos import strict_json
                metadata = strict_json(discovery)
                if (type(metadata) is not dict or type(metadata.get("message")) is not dict
                        or type(metadata["message"].get("items")) is not list
                        or len(metadata["message"]["items"]) > 3
                        or any(type(item) is not dict or not set(item) <= {"DOI", "title", "license"} for item in metadata["message"]["items"])
                        or not any(type(item) is dict and item.get("DOI") == record.doi
                                   and item.get("title") == [record.title] for item in metadata["message"]["items"])):
                    raise ValueError("snapshot not found in discovery response")
        elif raw is not None or extracted is not None or discovery is not None:
            raise ValueError("only snapshots can contain cached source")
        if type(record) is EvidenceExcerpt:
            snapshot, _, source_text = self._get(context, "snapshots", record.snapshot_id)
            if not snapshot.licence.display_excerpt:
                raise PermissionError("excerpt permission missing")
            if (source_text is None or record.extracted_digest != snapshot.extracted_digest
                    or sha256(source_text.encode()) != record.extracted_digest
                    or source_text[record.start:record.end] != record.quote):
                raise ValueError("unverifiable exact excerpt")
        elif type(record) is EvidenceClaim:
            for ref in record.excerpt_refs:
                self._get(context, "excerpts", ref)
        elif type(record) is ExecutionRecord:
            self._get(context, "plans", record.plan_id)
            if record.step_id != context.step_id or record.step_version != context.step_version:
                raise PermissionError("stale execution step")
            for ref in record.snapshot_refs:
                snapshot = self._get(context, "snapshots", ref)[0]
                if snapshot.origin != record.origin:
                    raise ValueError("execution cannot relabel imported/offline evidence")
            if record.status != "succeeded" and record.snapshot_refs:
                raise ValueError("failed execution cannot publish snapshots")
        elif type(record) is EvidenceReport:
            self._validate_report(context, record)
        previous = self.conn.execute("SELECT payload,raw,extracted,discovery FROM research_evidence_objects WHERE id=?", (record.id,)).fetchone()
        if previous is not None:
            if tuple(previous) != (payload, raw, extracted, discovery):
                raise ValueError("immutable evidence conflict")
            return False
        self.conn.execute("INSERT INTO research_evidence_objects VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (record.id, kind, record.research_id, record.input_revision, record.task_id, record.attempt, payload, sha256(payload.encode()), raw, extracted, discovery))
        return True

    def _validate_report(self, context, report):
        plan = self._get(context, "plans", report.plan_id)[0]
        snapshots = set(report.snapshot_refs)
        covered = set()
        for ref in report.snapshot_refs:
            snapshot = self._get(context, "snapshots", ref)[0]
            if snapshot.origin != report.origin or snapshot.query_digest != sha256(plan.query.encode()):
                raise ValueError("report provenance/query mismatch")
        for ref in report.execution_refs:
            execution = self._get(context, "executions", ref)[0]
            if execution.plan_id != report.plan_id or execution.status != "succeeded" or execution.origin != report.origin:
                raise ValueError("report references unrelated or failed execution")
            covered.update(execution.snapshot_refs)
        if snapshots != covered:
            raise ValueError("report source/execution mismatch")
        for ref in report.claim_refs:
            claim = self._get(context, "claims", ref)[0]
            for excerpt_id in claim.excerpt_refs:
                excerpt = self._get(context, "excerpts", excerpt_id)[0]
                if excerpt.snapshot_id not in snapshots:
                    raise ValueError("claim source omitted from report")
        self._permissions(context, report)

    def purge(self, context):
        """C0 deletion owner must call inside its deletion transaction/gate.

        No commit, lock management, account creation or receipt deletion here.
        Cascades on parent deletion are a second protection, not this hook's
        integration proof. The authorizer must support deleting lifecycle.
        """
        self._guard(context, "delete")
        return self.conn.execute("DELETE FROM research_evidence_objects WHERE research_id=?", (context.research_id,)).rowcount
