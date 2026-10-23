"""Strict DOC raw-preparation data. No type, digest or reference is authority.

B1 deliberately supplies no native completion or outbound transport. The fixed
target version describes a mapping, never a verified filing/body identity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import json
import re

from .evidence_schemas import Record, canonical, digest, identifier, positive, sha256

CONTRACT = 'official-document-rawprep-v1'
PROFILE_ID = 'gfs-2025-rawprep-v1'
PURPOSE = 'u1_official_rawprep'
GROUP = 'sec:1709048:000170904826000022'
RAW_CAP = 2097152
RECORD_CAP = 32000
COMMITMENT_CAP = 8192
PUBLIC_CAP = 32768
_MAPPING = {
    'gfs_2025_20f': ('20f', 'disclosure', 'gfs-20251231.htm'),
    'gfs_2025_20f_index': ('filing-index', 'filing_index', '0001709048-26-000022-index.html'),
}


def _literal(value, expected):
    if type(value) is not type(expected) or value != expected: raise ValueError('fixed DOC value required')


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high: raise ValueError('strict bounded DOC integer required')


def _utc(value):
    if type(value) is not str or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z', value) is None:
        raise ValueError('strict DOC UTC required')
    datetime.strptime(value, '%Y-%m-%dT%H:%M:%S.%fZ')


def _text(value, cap):
    if type(value) is not str or not 1 <= len(value) <= cap or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError('bounded DOC text required')


def _nullable(value, check):
    if value is not None: check(value)


def strict_json(payload, cap=RECORD_CAP):
    if type(payload) is str: payload = payload.encode('utf-8')
    if type(payload) is not bytes or not 1 <= len(payload) <= cap: raise ValueError('DOC JSON bound')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate DOC key')
            result[key] = value
        return result
    def invalid(_): raise ValueError('DOC noninteger number')
    try:value = json.loads(payload.decode('utf-8'), object_pairs_hook=pairs, parse_float=invalid, parse_constant=invalid)
    except RecursionError:raise ValueError('DOC nesting limit') from None
    def tree(item, depth=0):
        if depth > 24: raise ValueError('DOC nesting limit')
        if type(item) is dict:
            if len(item) > 80: raise ValueError('DOC object limit')
            for key, child in item.items(): _text(key, 120); tree(child, depth+1)
        elif type(item) is list:
            if len(item) > 64: raise ValueError('DOC array limit')
            for child in item: tree(child, depth+1)
        elif type(item) is str: item.encode('utf-8')
        elif item is not None and type(item) not in (int, bool): raise ValueError('DOC JSON type')
    tree(value)
    return value


@dataclass(frozen=True, kw_only=True)
class DocRef:
    doc_id: str
    doc_version: int

    def __post_init__(self):
        if type(self.doc_id) is not str or self.doc_id not in _MAPPING: raise ValueError('fixed DOC reference required')
        _literal(self.doc_version, 1)


@dataclass(frozen=True, kw_only=True)
class ProfileRef:
    id: str
    revision: int
    digest: str

    def __post_init__(self):
        if type(self.id) is not str or re.fullmatch(r'[A-Za-z0-9._:-]{1,64}', self.id) is None: raise ValueError('DOC profile id')
        positive(self.revision); digest(self.digest)


@dataclass(frozen=True, kw_only=True)
class DocTarget:
    doc_ref: DocRef
    semantic_object_id: str
    document_group_id: str
    document_role: str
    host: str
    path: str
    method: str = 'GET'
    redirect: str = 'none'
    format: str = 'html'

    def __post_init__(self):
        if type(self.doc_ref) is not DocRef: raise ValueError('exact DOC reference')
        self.doc_ref.__post_init__()
        suffix, role, filename = _MAPPING[self.doc_ref.doc_id]
        for value, expected in ((self.semantic_object_id, GROUP+':'+suffix), (self.document_group_id, GROUP),
                (self.document_role, role), (self.host, 'www.sec.gov'),
                (self.path, '/Archives/edgar/data/1709048/000170904826000022/'+filename),
                (self.method, 'GET'), (self.redirect, 'none'), (self.format, 'html')): _literal(value, expected)


def catalog():
    return tuple(DocTarget(doc_ref=DocRef(doc_id=name, doc_version=1), semantic_object_id=GROUP+':'+suffix,
        document_group_id=GROUP, document_role=role, host='www.sec.gov',
        path='/Archives/edgar/data/1709048/000170904826000022/'+filename)
        for name, (suffix, role, filename) in _MAPPING.items())


def common_fingerprint():
    # Raw/subset/profile/revision/attempt never open another four-GET domain.
    return sha256(canonical({'operation_family':'official-document-get',
        'purpose':'u1-issuer-disclosure-evidence', 'semantic_objects':[
            'hkexnews:2026012701265:smic-circular', GROUP+':20f', GROUP+':filing-index']}).encode())


def target_digest(target):
    if type(target) is not DocTarget: raise ValueError('fixed DOC target required')
    target.__post_init__()
    return sha256(canonical({'host':target.host,'path':target.path}).encode())


@dataclass(frozen=True, kw_only=True)
class RawPlanSpec:
    record_schema: str
    contract_revision: str
    purpose: str
    rawprep_profile_id: str
    query: None
    discovery: None
    documents: tuple[DocTarget, ...]
    catalog_digest: str
    selection_digest: str
    access_profile_ref: ProfileRef | None
    rights_digest: str | None
    execution_mode: str
    max_requests: int
    planned_gets: int
    raw_bytes_per_object: int
    get_seconds: int
    stop_rule: str

    def __post_init__(self):
        for value, expected in ((self.record_schema,'RawPrepPlanSpec-v1'), (self.contract_revision,CONTRACT),
                (self.purpose,PURPOSE), (self.rawprep_profile_id,PROFILE_ID), (self.query,None), (self.discovery,None),
                (self.execution_mode,'live'), (self.max_requests,4), (self.planned_gets,2),
                (self.raw_bytes_per_object,RAW_CAP), (self.get_seconds,12),
                (self.stop_rule,'fixed_pair_first_failure_stop_no_retry')): _literal(value, expected)
        if (type(self.documents) is not tuple or any(type(target) is not DocTarget for target in self.documents)
                or self.documents != catalog()): raise ValueError('fixed ordered DOC pair required')
        for target in self.documents: target.__post_init__()
        expected = sha256(canonical([asdict(target) for target in catalog()]).encode())
        _literal(self.catalog_digest, expected)
        _literal(self.selection_digest, sha256(canonical([asdict(t.doc_ref) for t in catalog()]).encode()))
        if self.access_profile_ref is not None:
            if type(self.access_profile_ref) is not ProfileRef: raise ValueError('exact profile reference required')
            self.access_profile_ref.__post_init__()
        _nullable(self.rights_digest, digest)
        if (self.access_profile_ref is None) != (self.rights_digest is None): raise ValueError('DOC acquisition references incomplete')


def rawprep_draft(problem_digest, profile_id=PROFILE_ID):
    digest(problem_digest); _literal(profile_id, PROFILE_ID)
    documents = catalog()
    spec = RawPlanSpec(record_schema='RawPrepPlanSpec-v1', contract_revision=CONTRACT, purpose=PURPOSE,
        rawprep_profile_id=PROFILE_ID, query=None, discovery=None, documents=documents,
        catalog_digest=sha256(canonical([asdict(t) for t in documents]).encode()),
        selection_digest=sha256(canonical([asdict(t.doc_ref) for t in documents]).encode()),
        access_profile_ref=None, rights_digest=None, execution_mode='live', max_requests=4, planned_gets=2,
        raw_bytes_per_object=RAW_CAP, get_seconds=12, stop_rule='fixed_pair_first_failure_stop_no_retry')
    data = asdict(spec); pd = sha256(canonical(data).encode())
    inp = sha256(canonical({'contract_revision':CONTRACT,'purpose':PURPOSE,'problem_digest':problem_digest,'plan_digest':pd}).encode())
    return data, pd, common_fingerprint(), inp


def idempotency_digest(operation, data):
    if operation not in ('source-approve','source-start'): raise ValueError('fixed raw operation required')
    if type(data) is not dict: raise ValueError('strict raw data required')
    return sha256(canonical({'protocol':'doc-rawprep-idempotency-v1','contract_revision':CONTRACT,
        'purpose':PURPOSE,'operation':operation,'data':data}).encode())


def quota_state(chains, unclosed):
    if type(chains) not in (list, tuple) or type(unclosed) is not bool: raise ValueError('strict DOC quota facts required')
    used = 0
    for chain in chains:
        value = chain['used']; _integer(value, 0, 4); used += value
    remaining = max(0, 4-used)
    return {'used':used,'limit':4,'remaining':remaining,'planned_gets':2,
        'eligible':remaining >= 2 and not unclosed,'unclosed':unclosed}


@dataclass(frozen=True, kw_only=True)
class DocObservation:
    requested_target: DocTarget
    observed_final_target: DocTarget | None
    http_status: int | None
    content_type_header: str | None
    media_type: str | None
    content_encoding_header: str | None
    effective_content_encoding: str | None
    content_length: int | None
    transfer_encoding_header: str | None
    location_header: str | None
    attempted_at: str
    request_sent_at: str | None
    received_at: str | None
    observed_failure_at: str | None
    safe_code: str
    body_complete: bool
    raw_length: int | None
    raw_sha256: str | None
    observed_lower_bound: int | None
    job_digest: str

    def __post_init__(self):
        if type(self.requested_target) is not DocTarget: raise ValueError('exact requested DOC target')
        self.requested_target.__post_init__()
        if self.observed_final_target is not None:
            if type(self.observed_final_target) is not DocTarget or self.observed_final_target != self.requested_target: raise ValueError('DOC redirect forbidden')
        _nullable(self.http_status, lambda v:_integer(v,100,599))
        for value, cap in ((self.content_type_header,300),(self.media_type,120),(self.content_encoding_header,64),
                (self.effective_content_encoding,64),(self.transfer_encoding_header,64),(self.location_header,512)):
            _nullable(value, lambda v:_text(v,cap))
        _nullable(self.content_length, lambda v:_integer(v,0,9223372036854775807))
        _utc(self.attempted_at)
        for value in (self.request_sent_at,self.received_at,self.observed_failure_at): _nullable(value,_utc)
        if type(self.safe_code) is not str or self.safe_code not in ('none','access_denied','unavailable','limit','invalid_source','outcome_unknown'): raise ValueError('DOC safe code')
        if type(self.body_complete) is not bool: raise ValueError('DOC body completeness')
        digest(self.job_digest)
        if self.http_status is not None and (self.observed_final_target is None or self.request_sent_at is None): raise ValueError('unobserved DOC HTTP status')
        if self.observed_final_target is not None and self.request_sent_at is None:raise ValueError('unobserved DOC final target')
        if self.media_type is not None and (self.content_type_header is None
                or self.media_type!=self.content_type_header.split(';',1)[0].strip().lower()):raise ValueError('DOC observed media type differs')
        if self.body_complete:
            _integer(self.raw_length,1,RAW_CAP); digest(self.raw_sha256)
            if self.http_status is None or self.received_at is None or self.effective_content_encoding != 'identity': raise ValueError('DOC complete observation missing')
            if self.content_encoding_header is not None and self.content_encoding_header.strip().lower()!='identity':raise ValueError('DOC encoded body is not identity')
            if self.content_length is not None and self.content_length != self.raw_length: raise ValueError('DOC declared length mismatch')
        elif self.raw_length is not None or self.raw_sha256 is not None: raise ValueError('incomplete body has no complete digest')
        if self.observed_lower_bound is not None:
            _literal(self.observed_lower_bound,RAW_CAP+1)
            if self.body_complete or self.safe_code != 'limit': raise ValueError('DOC lower bound is not complete length')


@dataclass(frozen=True, kw_only=True)
class TransportRetirementAudit:
    protocol: str
    request_id: str
    dispatch_id: str
    job_digest: str
    retired_at: str
    sender_reaped: bool
    tracker_reaped: bool
    ipc_closed: bool
    pipe_fds_closed: bool
    buffer_released: bool

    def __post_init__(self):
        _literal(self.protocol,'doc-transport-retirement-audit-v1')
        identifier(self.request_id); identifier(self.dispatch_id); digest(self.job_digest); _utc(self.retired_at)
        for value in (self.sender_reaped,self.tracker_reaped,self.ipc_closed,self.pipe_fds_closed,self.buffer_released): _literal(value,True)


@dataclass(frozen=True, kw_only=True)
class RawPrepPlan(Record):
    record_schema: str
    plan: RawPlanSpec
    created_at: str

    def __post_init__(self):
        super().__post_init__(); _literal(self.record_schema,'RawPrepPlan-v1'); _literal(self.attempt,1); _utc(self.created_at)
        if type(self.plan) is not RawPlanSpec: raise ValueError('strict DOC plan required')
        self.plan.__post_init__()


@dataclass(frozen=True, kw_only=True)
class RawArtifact(Record):
    record_schema: str
    doc_ref: DocRef
    plan_id: str
    request_id: str
    dispatch_id: str
    access_profile_ref: ProfileRef
    rights_digest: str
    observation: DocObservation
    raw_length: int
    raw_sha256: str
    origin: str
    document_identity: str
    parser_profile: None
    extracted_digest: None
    regions: tuple

    def __post_init__(self):
        super().__post_init__(); _literal(self.record_schema,'RawArtifact-v1'); _literal(self.attempt,1)
        for value in (self.plan_id,self.request_id,self.dispatch_id): identifier(value)
        if type(self.doc_ref) is not DocRef or type(self.access_profile_ref) is not ProfileRef or type(self.observation) is not DocObservation: raise ValueError('strict DOC acquisition records required')
        self.doc_ref.__post_init__(); self.access_profile_ref.__post_init__(); self.observation.__post_init__(); digest(self.rights_digest)
        _integer(self.raw_length,1,RAW_CAP); digest(self.raw_sha256)
        if not self.observation.body_complete or self.observation.requested_target.doc_ref != self.doc_ref or (self.raw_length,self.raw_sha256)!=(self.observation.raw_length,self.observation.raw_sha256): raise ValueError('DOC body observation differs')
        for value,expected in ((self.origin,'live'),(self.document_identity,'unverified'),(self.parser_profile,None),(self.extracted_digest,None),(self.regions,())): _literal(value,expected)


@dataclass(frozen=True, kw_only=True)
class RawPrepRequestReceipt(Record):
    record_schema: str
    plan_id: str
    request_id: str
    dispatch_id: str
    ordinal: int
    doc_ref: DocRef
    artifact_ref: str | None
    output_variant: str
    observation: DocObservation
    retirement: TransportRetirementAudit

    def __post_init__(self):
        super().__post_init__(); _literal(self.record_schema,'RawPrepRequestReceipt-v1'); _literal(self.attempt,1)
        for value in (self.plan_id,self.request_id,self.dispatch_id): identifier(value)
        _integer(self.ordinal,1,4); _nullable(self.artifact_ref,identifier)
        if type(self.doc_ref) is not DocRef or type(self.observation) is not DocObservation or type(self.retirement) is not TransportRetirementAudit: raise ValueError('strict DOC receipt records required')
        self.doc_ref.__post_init__(); self.observation.__post_init__(); self.retirement.__post_init__()
        if self.output_variant not in ('complete_candidate','quarantined_complete','failed_no_body'): raise ValueError('DOC receipt variant')
        if self.observation.http_status is None:raise ValueError('DOC receipt requires a known HTTP observation')
        if (self.output_variant=='failed_no_body') != (self.artifact_ref is None): raise ValueError('DOC no-body reference mismatch')
        if self.doc_ref != self.observation.requested_target.doc_ref or (self.request_id,self.dispatch_id,self.observation.job_digest)!=(self.retirement.request_id,self.retirement.dispatch_id,self.retirement.job_digest): raise ValueError('DOC receipt domain mismatch')
        if (self.artifact_ref is not None) != self.observation.body_complete: raise ValueError('DOC complete body reference required')
        if self.output_variant=='complete_candidate' and (self.observation.http_status!=200 or self.observation.media_type!='text/html' or self.observation.safe_code!='none'): raise ValueError('DOC candidate HTTP required')
        if self.output_variant!='complete_candidate' and self.observation.safe_code not in ('access_denied','unavailable','limit','invalid_source'): raise ValueError('DOC unknown is not known rejection')


@dataclass(frozen=True, kw_only=True)
class RawPrepBundleReceipt(Record):
    record_schema: str
    plan_id: str
    request_receipt_refs: tuple[str, ...]
    commitment_digests: tuple[str, ...]
    raw_artifact_refs: tuple[str, ...]
    package_state: str
    evidence: str
    document_identity: str
    model_analysis_ran: bool
    statistics_ran: bool

    def __post_init__(self):
        super().__post_init__(); _literal(self.record_schema,'RawPrepBundleReceipt-v1'); _literal(self.attempt,1); identifier(self.plan_id)
        for values,check in ((self.request_receipt_refs,identifier),(self.commitment_digests,digest),(self.raw_artifact_refs,identifier)):
            if type(values) is not tuple or len(values)>2 or len(set(values))!=len(values): raise ValueError('DOC bounded distinct refs')
            for value in values: check(value)
        if len(self.request_receipt_refs)!=len(self.commitment_digests): raise ValueError('DOC commitment refs differ')
        if self.package_state not in ('RAW_PAIR_COMPLETE_UNVERIFIED','INCOMPLETE','QUARANTINED','FAILED','RECONCILIATION_REQUIRED'): raise ValueError('DOC package state')
        if self.package_state=='RAW_PAIR_COMPLETE_UNVERIFIED' and (len(self.request_receipt_refs)!=2 or len(self.raw_artifact_refs)!=2): raise ValueError('DOC index alone cannot complete pair')
        for value,expected in ((self.evidence,'INSUFFICIENT'),(self.document_identity,'unverified'),(self.model_analysis_ran,False),(self.statistics_ran,False)): _literal(value,expected)


RAW_TYPES = {RawPrepPlan:'plans', RawArtifact:'snapshots', RawPrepRequestReceipt:'executions', RawPrepBundleReceipt:'executions'}
_SCHEMAS = {'RawPrepPlan-v1':RawPrepPlan,'RawArtifact-v1':RawArtifact,
    'RawPrepRequestReceipt-v1':RawPrepRequestReceipt,'RawPrepBundleReceipt-v1':RawPrepBundleReceipt}
_NESTED = {DocTarget:{'doc_ref':DocRef}, RawPlanSpec:{'access_profile_ref':ProfileRef},
    DocObservation:{'requested_target':DocTarget,'observed_final_target':DocTarget}, RawPrepPlan:{'plan':RawPlanSpec},
    RawArtifact:{'doc_ref':DocRef,'access_profile_ref':ProfileRef,'observation':DocObservation},
    RawPrepRequestReceipt:{'doc_ref':DocRef,'observation':DocObservation,'retirement':TransportRetirementAudit}}
_TUPLES = {RawArtifact:('regions',),RawPrepBundleReceipt:('request_receipt_refs','commitment_digests','raw_artifact_refs')}


def _construct(cls, data):
    if type(data) is not dict or set(data)!={f.name for f in fields(cls)}: raise ValueError('exact DOC fields required')
    values = dict(data)
    for key,nested in _NESTED.get(cls,{}).items():
        if values[key] is not None: values[key] = _construct(nested,values[key])
    if cls is RawPlanSpec:
        if type(values['documents']) is not list: raise ValueError('DOC target array required')
        values['documents'] = tuple(_construct(DocTarget,v) for v in values['documents'])
    for key in _TUPLES.get(cls,()):
        if type(values[key]) is not list: raise ValueError('DOC array required')
        values[key] = tuple(values[key])
    try:return cls(**values)
    except (TypeError,KeyError,OverflowError,RecursionError):raise ValueError('invalid strict DOC record value') from None


def decode_raw(kind, payload):
    data = strict_json(payload)
    cls = _SCHEMAS.get(data.get('record_schema')) if type(data) is dict else None
    if cls is None or RAW_TYPES[cls]!=kind: raise ValueError('DOC record kind/discriminator mismatch')
    return _construct(cls,data)


def encode_raw(record):
    if type(record) not in RAW_TYPES: raise ValueError('exact DOC record type required')
    encoded = canonical(asdict(record))
    decode_raw(RAW_TYPES[type(record)],encoded)
    return encoded


def decode_plan_spec(data):
    return _construct(RawPlanSpec, strict_json(canonical(data)))


def read_query(pairs):
    if type(pairs) is not list or len(pairs)!=1 or type(pairs[0]) is not tuple or pairs[0][0]!='task_id':
        raise ValueError('one canonical DOC task query required')
    identifier(pairs[0][1])
    return pairs[0][1]


def read_query_digest(task_id):
    identifier(task_id)
    return sha256(canonical({'protocol':'doc-rawprep-read-v1','task_id':task_id}).encode())


def recorded_draft(problem_digest, plan_json):
    """Validate original immutable plan data, without approving a profile."""
    digest(problem_digest)
    data=strict_json(plan_json)
    spec=decode_plan_spec(data)
    fields=asdict(spec);pd=sha256(canonical(fields).encode())
    inp=sha256(canonical({'contract_revision':CONTRACT,'purpose':PURPOSE,'problem_digest':problem_digest,'plan_digest':pd}).encode())
    return fields,pd,common_fingerprint(),inp


def decode_commitment(payload):
    """Pure strict C codec; a valid C is never a native completion permit."""
    value = strict_json(payload,COMMITMENT_CAP)
    required = {'record_schema','scope','request','document','result','artifact','receipt_ref','receipt_payload_digest',
        'observation_digest','retirement_digest','producer_protocol','producer_code_digest'}
    if type(value) is not dict or set(value)!=required: raise ValueError('exact DOC commitment required')
    _literal(value['record_schema'],'DocRawRequestCommitment-v1'); _literal(value['producer_protocol'],'doc-raw-completion-v1')
    shapes = {'scope':{'research_id','input_revision','attempt','input_digest'},
        'request':{'request_id','dispatch_id','chain_id','ordinal','task_id','step_id','semantic','target_digest','write_epoch','owner_gate_identity','task_gate_identity'},
        'document':{'doc_ref','semantic_object_id','document_group_id','document_role','plan_id','plan_digest','catalog_digest','selection_digest','admission_digest','access_profile_ref','rights_digest','job_digest'},
        'result':{'request_outcome','output_variant','actual_http_status','safe_code','completion_observed_at'},
        'artifact':{'artifact_ref','artifact_payload_digest','raw_length','raw_sha256'}}
    for key,names in shapes.items():
        if type(value[key]) is not dict or set(value[key])!=names: raise ValueError('exact DOC commitment domain required')
    scope,request,document,result,artifact = (value[k] for k in shapes)
    identifier(scope['research_id']); positive(scope['input_revision']); _literal(scope['attempt'],1); digest(scope['input_digest'])
    for key in ('request_id','dispatch_id','chain_id','task_id','step_id'): identifier(request[key])
    _integer(request['ordinal'],1,4); positive(request['write_epoch']); _literal(request['semantic'],'fetch_source'); digest(request['target_digest'])
    for key in ('owner_gate_identity','task_gate_identity'):
        identity=request[key]
        if type(identity) is not list or len(identity)!=5: raise ValueError('exact DOC gate identity required')
        for item in identity: _integer(item,0,9223372036854775807)
        _literal(identity[3],0o600); _literal(identity[4],1)
    ref=_construct(DocRef,document['doc_ref']); profile=_construct(ProfileRef,document['access_profile_ref'])
    target=next(t for t in catalog() if t.doc_ref==ref)
    for key in ('semantic_object_id','document_group_id','document_role'): _literal(document[key],getattr(target,key))
    _literal(request['target_digest'],target_digest(target)); identifier(document['plan_id'])
    for key in ('plan_digest','catalog_digest','selection_digest','admission_digest','rights_digest','job_digest'): digest(document[key])
    _integer(result['actual_http_status'],100,599); _utc(result['completion_observed_at'])
    outcome,variant=result['request_outcome'],result['output_variant']
    if outcome=='SUCCEEDED':
        _literal(variant,'complete_candidate'); _literal(result['safe_code'],'none'); _literal(result['actual_http_status'],200)
    elif outcome=='FAILED':
        if variant not in ('quarantined_complete','failed_no_body') or result['safe_code'] not in ('access_denied','unavailable','limit','invalid_source'): raise ValueError('DOC known failure required')
    else: raise ValueError('DOC commitment is not UNKNOWN closure proof')
    if variant=='failed_no_body':
        if any(v is not None for v in artifact.values()): raise ValueError('DOC no-body artifact must be null')
    else:
        identifier(artifact['artifact_ref']); digest(artifact['artifact_payload_digest']); _integer(artifact['raw_length'],1,RAW_CAP); digest(artifact['raw_sha256'])
    identifier(value['receipt_ref'])
    for key in ('receipt_payload_digest','observation_digest','retirement_digest','producer_code_digest'): digest(value[key])
    return value
