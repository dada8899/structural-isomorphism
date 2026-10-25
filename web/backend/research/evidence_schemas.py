"""Unwired D1 method-evidence records. No market statistics or model execution.

These types deliberately use only the standard library. C0 owns their eventual
contract revision, migration and API projection; none is a public API yet.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import json
import re
from uuid import UUID


POLICY = "d1-method-evidence-v1"
KINDS = ("snapshots", "plans", "executions", "excerpts", "claims", "reports")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def sha256(data: bytes):
    return hashlib.sha256(data).hexdigest()


def text(value, cap=1000, minimum=1):
    if type(value) is not str or not minimum <= len(value) <= cap:
        raise ValueError("invalid bounded text")
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("control character")


def identifier(value):
    if type(value) is not str or str(UUID(value, version=4)) != value:
        raise ValueError("canonical UUID4 required")


def digest(value):
    if type(value) is not str or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("invalid digest")


def positive(value):
    if type(value) is not int or not 1 <= value <= 2147483647:
        raise ValueError("invalid version")


def utc(value):
    text(value, 40)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not value.endswith("Z") or parsed.utcoffset() is None or parsed.utcoffset().total_seconds() != 0:
        raise ValueError("UTC timestamp required")


def refs(values, cap=20):
    if type(values) is not tuple or len(values) > cap or len(set(values)) != len(values):
        raise ValueError("bounded unique tuple required")
    for value in values:
        identifier(value)


@dataclass(frozen=True, kw_only=True)
class Binding:
    research_id: str
    input_revision: int
    task_id: str
    attempt: int
    input_digest: str

    def __post_init__(self):
        identifier(self.research_id)
        identifier(self.task_id)
        positive(self.input_revision)
        positive(self.attempt)
        digest(self.input_digest)


@dataclass(frozen=True, kw_only=True)
class Record(Binding):
    id: str

    def __post_init__(self):
        super().__post_init__()
        identifier(self.id)


@dataclass(frozen=True, kw_only=True)
class Licence:
    status: str = "unknown"
    private_cache: bool = False
    display_excerpt: bool = False
    export_excerpt: bool = False
    basis: str = "No verified permission."

    def __post_init__(self):
        if self.status not in {"verified", "unknown", "denied"}:
            raise ValueError("invalid permission status")
        for flag in (self.private_cache, self.display_excerpt, self.export_excerpt):
            if type(flag) is not bool:
                raise ValueError("strict permission flag required")
        if self.status != "verified" and any((self.private_cache, self.display_excerpt, self.export_excerpt)):
            raise ValueError("unknown permission cannot authorize reuse")
        if self.export_excerpt and not self.display_excerpt:
            raise ValueError("export requires excerpt permission")
        text(self.basis, 700)


@dataclass(frozen=True, kw_only=True)
class DataSnapshot(Record):
    source_id: str
    source_revision: int
    title: str
    doi: str
    canonical_url: str
    query_digest: str
    discovery_digest: str
    acquired_at: str
    information_cutoff: str
    raw_digest: str
    extracted_digest: str
    parser_version: str
    licence: Licence
    origin: str
    access: str = "body_retrieved"
    kind: str = "document_text"

    def __post_init__(self):
        super().__post_init__()
        identifier(self.source_id)
        positive(self.source_revision)
        text(self.title, 300)
        if re.fullmatch(r"10\.1371/journal\.pone\.[0-9]{7}", self.doi) is None:
            raise ValueError("unsupported DOI")
        if self.canonical_url != "https://journals.plos.org/plosone/article?id=" + self.doi:
            raise ValueError("noncanonical publisher URL")
        for value in (self.query_digest, self.discovery_digest, self.raw_digest, self.extracted_digest):
            digest(value)
        utc(self.acquired_at)
        utc(self.information_cutoff)
        if self.parser_version not in ("plos-html-text-v1", "plos-author-narrative-subset-v2") or type(self.licence) is not Licence:
            raise ValueError("unsupported parser/permission")
        if self.origin not in {"live", "historical_import", "offline_probe"}:
            raise ValueError("invalid provenance")
        if self.kind != "document_text" or self.access != "body_retrieved":
            raise ValueError("only retrieved document snapshots supported")


@dataclass(frozen=True, kw_only=True)
class AnalysisPlan(Record):
    query: str
    external_query_approved: bool
    objective: str
    competing_explanations: tuple[str, ...]
    required_evidence: tuple[str, ...]
    stop_rule: str
    created_at: str
    policy_revision: str = POLICY
    samples: tuple[str, ...] = ("NASDAQ:GFS", "SSE:688981", "HKEX:00981")
    exploration: str = "2024-01-01/2025-12-31"
    validation: str = "2026-01-01/2026-09-30"
    scope: str = "u1_method_evidence_subchain"
    price_series_available: bool = False
    max_requests: int = 4

    def __post_init__(self):
        super().__post_init__()
        # Deliberately excludes arbitrary input bodies, URLs and identities.
        if type(self.query) is not str or re.fullmatch(r"[A-Za-z][A-Za-z -]{2,159}", self.query) is None:
            raise ValueError("bounded academic query required")
        if type(self.external_query_approved) is not bool or not self.external_query_approved:
            raise ValueError("explicit external query approval required")
        text(self.objective, 700)
        for values in (self.competing_explanations, self.required_evidence):
            if type(values) is not tuple or not 1 <= len(values) <= 5:
                raise ValueError("bounded evidence plan required")
            for value in values:
                text(value, 400)
        text(self.stop_rule, 400)
        utc(self.created_at)
        if (self.policy_revision != POLICY or self.samples != ("NASDAQ:GFS", "SSE:688981", "HKEX:00981")
                or self.exploration != "2024-01-01/2025-12-31" or self.validation != "2026-01-01/2026-09-30"
                or self.scope != "u1_method_evidence_subchain" or self.price_series_available is not False
                or type(self.max_requests) is not int or self.max_requests != 4):
            raise ValueError("outside fixed method-evidence scope")


@dataclass(frozen=True, kw_only=True)
class ExecutionRecord(Record):
    plan_id: str
    step_id: str
    dispatch_id: str
    step_version: int
    executor_version: str
    started_at: str
    ended_at: str
    status: str
    origin: str
    request_count: int
    http_status: int | None
    snapshot_refs: tuple[str, ...] = ()
    safe_code: str = "none"

    def __post_init__(self):
        super().__post_init__()
        for value in (self.plan_id, self.step_id, self.dispatch_id):
            identifier(value)
        positive(self.step_version)
        utc(self.started_at)
        utc(self.ended_at)
        if datetime.fromisoformat(self.ended_at.replace("Z", "+00:00")) < datetime.fromisoformat(self.started_at.replace("Z", "+00:00")):
            raise ValueError("invalid execution interval")
        if self.executor_version != POLICY or self.status not in {"succeeded", "failed", "outcome_unknown", "discarded"}:
            raise ValueError("invalid execution result")
        if self.origin not in {"live", "historical_import", "offline_probe"}:
            raise ValueError("invalid execution provenance")
        if type(self.request_count) is not int or not 0 <= self.request_count <= 4:
            raise ValueError("invalid request count")
        if self.http_status is not None and (type(self.http_status) is not int or not 100 <= self.http_status <= 599):
            raise ValueError("invalid HTTP observation")
        if self.origin == "historical_import" and (self.request_count != 0 or self.http_status is not None):
            raise ValueError("import cannot claim a new HTTP observation")
        if self.safe_code not in {"none", "access_denied", "unavailable", "limit", "cancelled", "invalid_source", "permission_unknown", "outcome_unknown"}:
            raise ValueError("invalid error code")
        refs(self.snapshot_refs, 3)


@dataclass(frozen=True, kw_only=True)
class EvidenceExcerpt(Record):
    snapshot_id: str
    extracted_digest: str
    start: int
    end: int
    quote: str

    def __post_init__(self):
        super().__post_init__()
        identifier(self.snapshot_id)
        digest(self.extracted_digest)
        if type(self.start) is not int or type(self.end) is not int or not 0 <= self.start < self.end <= 200000:
            raise ValueError("invalid Unicode character range")
        text(self.quote, 1000)
        if len(self.quote.split()) > 20 or self.end - self.start != len(self.quote):
            raise ValueError("bounded exact excerpt required")


@dataclass(frozen=True, kw_only=True)
class EvidenceClaim(Record):
    text: str
    excerpt_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    level: str = "hypothesis"
    assessment: str = "unreviewed"

    def __post_init__(self):
        super().__post_init__()
        text(self.text, 1200)
        refs(self.excerpt_refs, 5)
        if not self.excerpt_refs:
            raise ValueError("claim must cite evidence")
        if type(self.limitations) is not tuple or not 1 <= len(self.limitations) <= 5:
            raise ValueError("explicit limitations required")
        for value in self.limitations:
            text(value, 400)
        # Link checking cannot elevate a mechanism or infer semantic support.
        if self.level != "hypothesis" or self.assessment != "unreviewed":
            raise ValueError("D1 does not perform semantic/model review")


@dataclass(frozen=True, kw_only=True)
class EvidenceReport(Record):
    plan_id: str
    snapshot_refs: tuple[str, ...]
    execution_refs: tuple[str, ...]
    claim_refs: tuple[str, ...]
    outstanding_requirements: tuple[str, ...]
    origin: str
    status: str = "notes"
    evidence: str = "INSUFFICIENT"
    model_analysis_ran: bool = False
    statistics_ran: bool = False
    artifact_refs: tuple[str, ...] = ()

    def __post_init__(self):
        super().__post_init__()
        identifier(self.plan_id)
        if self.origin not in {"live", "historical_import", "offline_probe"}:
            raise ValueError("invalid report provenance")
        for values in (self.snapshot_refs, self.execution_refs, self.claim_refs):
            refs(values)
            if not values:
                raise ValueError("report needs concrete records")
        if type(self.outstanding_requirements) is not tuple or not 1 <= len(self.outstanding_requirements) <= 12:
            raise ValueError("incomplete U1 must retain gaps")
        for value in self.outstanding_requirements:
            text(value, 400)
        if (self.status != "notes" or self.evidence != "INSUFFICIENT" or self.model_analysis_ran is not False
                or self.statistics_ran is not False or self.artifact_refs != ()):
            raise ValueError("method subchain cannot claim completed research or calculations")


RECORD_TYPES = dict(zip(KINDS, (DataSnapshot, AnalysisPlan, ExecutionRecord, EvidenceExcerpt, EvidenceClaim, EvidenceReport)))


def encode(record):
    if type(record) not in RECORD_TYPES.values():
        from .source_document_raw import encode_raw
        return encode_raw(record)
    # Revalidate even instances constructed through unsafe deserialization.
    decode(next(k for k, t in RECORD_TYPES.items() if t is type(record)), canonical(asdict(record)))
    return canonical(asdict(record))


def decode(kind, payload):
    if kind not in RECORD_TYPES or type(payload) is not str or len(payload) > 32000:
        raise ValueError("invalid persisted evidence")
    def pairs(items):
        result = {}
        for k, v in items:
            if k in result:
                raise ValueError("duplicate key")
            result[k] = v
        return result
    data = json.loads(payload, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    if type(data) is dict and 'record_schema' in data:
        from .source_document_raw import decode_raw
        return decode_raw(kind,payload)
    if kind == "snapshots":
        data["licence"] = Licence(**data["licence"])
    for key in ("competing_explanations", "required_evidence", "samples", "snapshot_refs", "excerpt_refs", "limitations", "execution_refs", "claim_refs", "outstanding_requirements", "artifact_refs"):
        if key in data:
            if type(data[key]) is not list:
                raise ValueError("JSON array required")
            data[key] = tuple(data[key])
    return RECORD_TYPES[kind](**data)
