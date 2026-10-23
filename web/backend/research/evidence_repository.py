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
        from .source_document_raw import RAW_TYPES
        if type(record) in RAW_TYPES:
            raise PermissionError('DOC records require the protected raw reader')
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
        from .source_document_raw import RAW_TYPES
        if type(record) in RAW_TYPES:raise PermissionError('raw DOC is not display/export/provider evidence')
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
        from .source_document_raw import RAW_TYPES,RawPrepPlan
        if type(record) in RAW_TYPES:
            if type(record) is not RawPrepPlan or any(value is not None for value in (raw,extracted,discovery)):
                raise PermissionError('ordinary put cannot create native DOC output')
            from .source_guard import _WRITES
            from .source_integration import plan_for
            scope=_WRITES.get(id(self.conn))
            if scope is None or scope.mode!='admit' or not scope.active:raise PermissionError('actual DOC admission required')
            scope.validate()
            task=self.conn.execute('SELECT * FROM research_tasks WHERE id=?',(record.task_id,)).fetchone()
            run=self.conn.execute('SELECT * FROM research_source_runs WHERE task_id=?',(record.task_id,)).fetchone()
            approval=self.conn.execute('SELECT * FROM research_source_approvals WHERE id=?',(run['approval_id'],)).fetchone() if run else None
            if not task or not run or not approval or record!=plan_for(task,approval,run['plan_id']):raise PermissionError('DOC admitted plan differs')
            return self._insert_raw(context,record,None)
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

    def _insert_raw(self,context,record,raw):
        import inspect
        if inspect.currentframe().f_back.f_code not in (EvidenceRepository.put.__code__,EvidenceRepository.put_raw_in_completion.__code__,EvidenceRepository.put_raw_bundle.__code__):raise PermissionError('native DOC output entry required')
        from .source_document_raw import RAW_TYPES,encode_raw
        self._guard(context,'write');self._same(context,record)
        payload=encode_raw(record);kind=RAW_TYPES[type(record)]
        if self.conn.execute('SELECT 1 FROM research_evidence_objects WHERE id=?',(record.id,)).fetchone():raise PermissionError('DOC output reference already exists')
        self.conn.execute('INSERT INTO research_evidence_objects VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (record.id,kind,record.research_id,record.input_revision,record.task_id,record.attempt,payload,sha256(payload.encode()),raw,None,None))
        return True

    def put_raw_in_completion(self,context,completion):
        from .source_document_access import DocCompletion
        from .source_guard import _WRITES
        scope=_WRITES.get(id(self.conn))
        if type(completion) is not DocCompletion or scope is None or scope.doc_completion is not completion or not scope.active:
            raise PermissionError('actual DOC transaction completion required')
        completion.check(self.conn)
        if completion.state!='WRITING' or completion.conn is not self.conn:raise PermissionError('DOC completion transaction absent')
        artifact,receipt,_=completion.derive(self.conn)
        if artifact is not None:self._insert_raw(context,artifact,completion.outcome.raw)
        self._insert_raw(context,receipt,None)

    def put_raw_bundle(self,context,record,store):
        from .source_document_raw import RawPrepBundleReceipt
        from .source_document_access import session_supervisor
        from .source_supervisor import _require_store_worker
        supervisor=_require_store_worker(store,operation='send');session=supervisor._session
        if session is None or session_supervisor(session) is not supervisor or type(record) is not RawPrepBundleReceipt:
            raise PermissionError('actual DOC bundle worker required')
        if record.plan_id!=session.plan.id:raise PermissionError('DOC bundle plan differs')
        receipts=[];digests=[];artifacts=[];variants=[]
        rows=self.conn.execute('SELECT * FROM research_source_requests WHERE task_id=? ORDER BY ordinal',(context.task_id,)).fetchall()
        if not 1<=len(rows)<=2:raise PermissionError('DOC bundle fixed pair request count differs')
        for position,request in enumerate(rows):
            receipt,artifact,_,commitment_digest=self._raw_receipt_anchor(context,request['id'],store)
            if receipt.observation.requested_target!=session.plan.plan.documents[position] or (position<len(rows)-1 and request['outcome']!='SUCCEEDED'):
                raise PermissionError('DOC fixed ordered first-failure stop differs')
            if receipt.artifact_ref is not None:
                artifacts.append(receipt.artifact_ref)
            receipts.append(receipt.id);digests.append(commitment_digest);variants.append(receipt.output_variant)
        if len(rows)==1 and rows[-1]['outcome']!='FAILED':raise PermissionError('DOC index cannot be omitted after successful main GET')
        state=('RAW_PAIR_COMPLETE_UNVERIFIED' if len(variants)==2 and all(v=='complete_candidate' for v in variants)
            else 'QUARANTINED' if 'quarantined_complete' in variants else 'FAILED')
        if (record.request_receipt_refs,record.commitment_digests,record.raw_artifact_refs,record.package_state)!=(tuple(receipts),tuple(digests),tuple(artifacts),state):raise PermissionError('DOC bundle projection differs')
        return self._insert_raw(context,record,None)

    def _raw_receipt_anchor(self,context,request_id,store):
        """Recompute a stored first output from its protected request anchor."""
        from .store import ResearchStore
        from .source_guard import require_hook
        if __package__=='web.backend.research':from ..services.sqlite_utils import PrivateAuthConnection
        else:from services.sqlite_utils import PrivateAuthConnection
        if type(store) is not ResearchStore or not store._formal_mode() or type(self.conn) is not PrivateAuthConnection or not self.conn.in_transaction:
            raise ValueError('DOC actual protected private transaction required')
        witness=self.conn._history_file
        if witness is None or witness.path!=store.path or witness.file_identity!=store.storage_identity:
            raise ValueError('DOC protected private object differs')
        witness.check();require_hook(self.conn)
        from .source_document_raw import (RawPrepPlan,RawArtifact,RawPrepRequestReceipt,decode_raw,
            decode_commitment,encode_raw,request_output_data)
        from .source_guard import check_origin
        request=self.conn.execute('SELECT * FROM research_source_requests WHERE id=?',(request_id,)).fetchone()
        if (request is None or request['task_id']!=context.task_id or request['outcome'] not in ('SUCCEEDED','FAILED')
                or request['execution_closed']!=1 or request['closure_ref'] is None or request['closure_proof'] is None):raise ValueError('DOC protected first output absent')
        c=decode_commitment(request['closure_proof'])
        if canonical(c)!=request['closure_proof'] or c['receipt_ref']!=request['closure_ref']:raise ValueError('DOC canonical anchor differs')
        def stored(ref,kind,expected):
            row=self.conn.execute('SELECT * FROM research_evidence_objects WHERE id=? AND kind=?',(ref,kind)).fetchone()
            if row is None or sha256(row['payload'].encode())!=row['payload_digest']:raise ValueError('DOC anchored payload absent')
            record=decode_raw(kind,row['payload']);self._same(context,record)
            if type(record) is not expected or encode_raw(record)!=row['payload']:raise ValueError('DOC anchored canonical type differs')
            if (row['research_id'],row['input_revision'],row['task_id'],row['attempt'])!=(record.research_id,record.input_revision,record.task_id,record.attempt):raise ValueError('DOC anchored row scope differs')
            return row,record
        rrow,receipt=stored(request['closure_ref'],'executions',RawPrepRequestReceipt)
        if any(rrow[k] is not None for k in ('raw','extracted','discovery')):raise ValueError('DOC receipt cannot contain body')
        try:resource=check_origin(store,self.conn,context.task_id)
        except (PermissionError,ValueError,KeyError,AttributeError):raise ValueError('DOC protected original admission absent') from None
        run=self.conn.execute('SELECT * FROM research_source_runs WHERE task_id=?',(context.task_id,)).fetchone()
        if run is None:raise ValueError('DOC original run absent')
        prow,plan=stored(run['plan_id'],'plans',RawPrepPlan)
        if any(prow[k] is not None for k in ('raw','extracted','discovery')):raise ValueError('DOC plan cannot contain body')
        from .source_integration import plan_for
        task=self.conn.execute('SELECT * FROM research_tasks WHERE id=?',(context.task_id,)).fetchone()
        approval=self.conn.execute('SELECT * FROM research_source_approvals WHERE id=?',(run['approval_id'],)).fetchone()
        if task is None or approval is None or plan!=plan_for(task,approval,run['plan_id']):raise ValueError('DOC exact admitted plan differs')
        step=self.conn.execute('SELECT * FROM research_steps WHERE id=? AND task_id=?',(request['step_id'],context.task_id)).fetchone()
        if (step is None or type(step['position']) is not int or not 0<=step['position']<2 or step['kind']!='fetch_source'
                or request['semantic']!='fetch_source' or request['chain_id']!=run['chain_id']
                or receipt.observation.requested_target!=plan.plan.documents[step['position']]):raise ValueError('DOC original fixed step target differs')
        original=dict(request,outcome='SENDING',execution_closed=0,closure_ref=None,closure_proof=None,ended_at=None,http_status=None,safe_code='none')
        expected_a,expected_r,expected_c=request_output_data(plan,original,receipt.observation,receipt.retirement,
            artifact_ref=receipt.artifact_ref,receipt_ref=receipt.id,admission_digest=resource['admission_digest'],producer_code_digest=c['producer_code_digest'])
        if (expected_c!=c or expected_r!=receipt or c['result']['request_outcome']!=request['outcome']
                or c['result']['actual_http_status']!=request['http_status'] or c['result']['safe_code']!=request['safe_code']
                or c['result']['completion_observed_at']!=request['ended_at']):raise ValueError('DOC anchored output differs')
        raw=None
        if expected_a is not None:
            arow,artifact=stored(expected_a.id,'snapshots',RawArtifact);raw=arow['raw']
            if (artifact!=expected_a or type(raw) is not bytes or len(raw)!=artifact.raw_length or sha256(raw)!=artifact.raw_sha256
                    or arow['extracted'] is not None or arow['discovery'] is not None):raise ValueError('DOC anchored complete raw differs')
        return receipt,expected_a,raw,sha256(request['closure_proof'].encode())

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

    def _raw_anchor(self, context, artifact_ref, store):
        """Reverse-check the protected first output, never an ordinary self hash."""
        from dataclasses import asdict
        from .source_document_raw import decode_raw,RawArtifact
        row=self.conn.execute('SELECT payload FROM research_evidence_objects WHERE id=? AND kind=?',(artifact_ref,'snapshots')).fetchone()
        if row is None:raise ValueError('DOC output reference absent')
        candidate=decode_raw('snapshots',row[0])
        if type(candidate) is not RawArtifact:raise ValueError('DOC exact artifact required')
        receipt,artifact,raw,_=self._raw_receipt_anchor(context,candidate.request_id,store)
        if artifact is None or artifact.id!=artifact_ref:raise ValueError('DOC artifact is not the protected output')
        return {'artifact_ref':artifact.id,'receipt_ref':receipt.id,'request_ref':artifact.request_id,
            'doc_ref':asdict(artifact.doc_ref),'raw_length':artifact.raw_length,'raw_sha256':artifact.raw_sha256,
            'http_status':receipt.observation.http_status,'received_at':receipt.observation.received_at,'document_identity':'unverified'}

    def read_raw_candidate(self,context,artifact_ref,*,read_scope):
        from .source_document_access import RawReadScope,require_private_cache
        self._guard(context,'read')
        if type(read_scope) is not RawReadScope:raise PermissionError('actual DOC read lifetime required')
        read_scope.check(self.conn,context)
        result=self._raw_anchor(context,artifact_ref,read_scope.service.store)
        require_private_cache()
        return result
