"""Unwired model candidates -> server-owned hypotheses, never D1 notes or D2 checks."""
from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from uuid import uuid4
from typing import Annotated, Literal

from pydantic import Field, StringConstraints, field_validator

from .provider_schemas import (
    DTO, Digest, Id, Handle, Natural, Positive, CallContext, EvidencePacket, ProviderObservation,
    ProviderFailure, CANDIDATE_CAP, canonical, digest, strict_json,
)


Text120 = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=120)]
Text400 = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=400)]


class CandidateDTO(DTO):
    @field_validator('*', mode='after')
    @classmethod
    def safe_text(cls, value):
        def check(v):
            if isinstance(v, str) and (not v.strip() or re.search(r'(?i)(?:[a-z][a-z0-9+.-]*://|www\.|(?:javascript|data|file|mailto):)', v)
                    or any(unicodedata.category(c) in {'Cc', 'Cf', 'Cs'} and c not in '\n\t' for c in v)):
                raise ValueError('unsupported candidate text')
            if isinstance(v, tuple):
                for item in v:
                    check(item)
        check(value)
        return value


class VariableMapping(CandidateDTO):
    source: Text120
    target: Text120
    rationale: Text400


class Mechanism(CandidateDTO):
    label: Text120
    mechanism: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1200)]
    variable_map: Annotated[tuple[VariableMapping, ...], Field(max_length=12)]
    conditions: Annotated[tuple[Text400, ...], Field(max_length=5)]
    nontransferable: Annotated[tuple[Text400, ...], Field(max_length=5)]
    evidence_handles: Annotated[tuple[Handle, ...], Field(max_length=20)]


class ValidationPlan(CandidateDTO):
    measurement: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=700)]
    outcome: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=240)]
    falsification: Text400
    stop_rule: Text400


class ModelReportCandidate(CandidateDTO):
    summary: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
    mechanisms: Annotated[tuple[Mechanism, ...], Field(max_length=3)]
    competing_explanations: Annotated[tuple[Text400, ...], Field(max_length=5)]
    validation_plan: ValidationPlan
    gaps: Annotated[tuple[Text400, ...], Field(max_length=12)]


def parse_candidate(raw: bytes, packet: EvidencePacket):
    packet = EvidencePacket.model_validate(packet)
    value = strict_json(raw, CANDIDATE_CAP)
    try:
        candidate = ModelReportCandidate.model_validate_json(canonical(value))
        if not candidate.mechanisms and not candidate.gaps:
            raise ValueError('missing gaps')
        allowed = {h.handle for h in packet.handles}
        for mechanism in candidate.mechanisms:
            if (len(set(mechanism.evidence_handles)) != len(mechanism.evidence_handles)
                    or not set(mechanism.evidence_handles) <= allowed):
                raise ValueError('invalid handle')
        return candidate
    except ValueError:
        raise ProviderFailure('candidate_invalid') from None


class HypothesisClaim(DTO):
    id: Id
    text: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1200)]
    excerpt_ids: tuple[Id, ...]
    source_ids: tuple[Id, ...]
    level: Literal['hypothesis'] = 'hypothesis'
    assessment: Literal['llm_inference'] = 'llm_inference'
    review: Literal['unreviewed'] = 'unreviewed'


class CitationRef(DTO):
    handle: Handle
    source_id: Id
    source_revision: Positive
    excerpt_id: Id
    extracted_digest: Digest
    start: Natural
    end: Natural
    quote: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]


class ModelReportRecord(DTO):
    id: Id
    context: CallContext
    dispatch_id: Id
    request_digest: Digest
    evidence_digest: Digest
    declared_model_version: Literal['DeepSeek-V4.1-Flash']
    candidate_schema: Literal['ModelReportCandidate-v1'] = 'ModelReportCandidate-v1'
    execution_mode: Literal['offline_probe'] = 'offline_probe'
    model_analysis_ran: Literal[False] = False
    candidate: ModelReportCandidate
    claims: tuple[HypothesisClaim, ...]
    citations: tuple[CitationRef, ...]
    usage_observation_ref: Digest
    cost_observation_ref: Digest
    content_digest: Digest
    created_at: str
    status: Literal['qualified_report'] = 'qualified_report'
    evidence: Literal['INSUFFICIENT'] = 'INSUFFICIENT'
    # No check ids supplied by the model or promoted by this unwired producer.
    check_refs: tuple[()] = ()


def _build_model_report(observation, packet, current_authorizer, *, timestamp=None):
    """No DB writes. The caller must later recheck ACL/CAS in its write transaction.

    No D2 integration in this module: all claims remain hypotheses. A future
    owner can join real immutable CheckResults through its existing authority.
    """
    observation = ProviderObservation.model_validate(observation)
    packet = EvidencePacket.model_validate(packet)
    if (not callable(current_authorizer) or current_authorizer(packet.context, packet.binding_digest()) != packet
            or observation.context != packet.context or observation.evidence_digest != packet.binding_digest()
            or observation.safe_code != 'ok' or observation.candidate is None or observation.usage is None
            or observation.cost.kind != 'estimated_upper' or observation.cost.booked_upper is None
            or observation.cost.dispatch_id != observation.dispatch_id):
        raise ProviderFailure('report_not_authorized')
    # Revalidate hashes, offsets, independent send/display permissions now.
    candidate = parse_candidate(observation.candidate.encode(), packet)
    by_handle = {handle.handle: handle for handle in packet.handles}
    claims = []
    used_handles = set()
    for mechanism in candidate.mechanisms:
        handles = [by_handle[h] for h in mechanism.evidence_handles]
        used_handles.update(mechanism.evidence_handles)
        claims.append(HypothesisClaim(id=str(uuid4()), text=mechanism.mechanism,
            excerpt_ids=tuple(dict.fromkeys(h.excerpt_id for h in handles)),
            source_ids=tuple(dict.fromkeys(h.source_id for h in handles))))
    created = timestamp or datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    try:
        parsed = datetime.fromisoformat(created.replace('Z', '+00:00'))
        if not created.endswith('Z') or parsed.utcoffset().total_seconds() != 0:
            raise ValueError('invalid UTC')
    except (ValueError, AttributeError):
        raise ProviderFailure('invalid_time') from None
    return ModelReportRecord(id=str(uuid4()), context=packet.context,
        dispatch_id=observation.dispatch_id, request_digest=observation.request_digest,
        evidence_digest=observation.evidence_digest, declared_model_version=observation.declared_version,
        candidate=candidate, claims=tuple(claims),
        citations=tuple(CitationRef(**h.model_dump(include={
            'handle', 'source_id', 'source_revision', 'excerpt_id', 'extracted_digest', 'start', 'end', 'quote'
        })) for h in packet.handles if h.handle in used_handles),
        usage_observation_ref=observation.cost.usage_ref,
        cost_observation_ref=digest(canonical(observation.cost.model_dump())),
        content_digest=digest(canonical(candidate.model_dump())), created_at=created)


def build_model_report(observation, packet, current_authorizer, *, timestamp=None):
    try:
        return _build_model_report(observation, packet, current_authorizer, timestamp=timestamp)
    except ProviderFailure:
        raise
    except Exception:
        raise ProviderFailure('report_invalid') from None
