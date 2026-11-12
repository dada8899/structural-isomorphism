"""Strict public contracts for the four secondary research tools.

These surfaces are useful hypothesis generators, not experimental validators.
The contract therefore keeps every result at the ``candidate`` evidence level,
binds every response to one client request id, and never exposes retrieval
scores as probabilities or model self-confidence as calibration.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Literal, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .evidence_envelope import (
    ResultProvenance,
    build_evidence_envelope,
)
from .scope_guard import is_out_of_scope


CONTRACT_VERSION = "secondary-tools-v2"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$")
_STRUCTURAL_CONTEXT = re.compile(
    r"(?:公司|团队|组织|项目|策略|方案|业务|用户|系统|方法|算法|模型|机制|反馈|"
    r"流程|决策|结构|增长|市场|产品|网络|供应链|实验|数据|干预|迁移|类比|"
    r"company|team|organisation|organization|project|strategy|business|user|"
    r"system|method|algorithm|model|mechanism|feedback|process|decision|growth)",
    re.IGNORECASE,
)
_CLAUSE_BREAK = re.compile(r"[,，。;；!?！？\n]")
_DIRECT_FACT_QUERY = re.compile(
    r"(?:是什么|是哪里|在哪里|是谁|多少|几岁|几点|何时|什么时候|"
    r"首都|天气|人口|面积|定义)(?:[^。！？!?]{0,30})(?:[。！？!?]|$)",
    re.IGNORECASE,
)


def ensure_request_id(value: Optional[str]) -> str:
    """Return a validated client id or a server-generated compatibility id."""
    if value is None:
        return uuid.uuid4().hex
    if not isinstance(value, str) or not REQUEST_ID_PATTERN.fullmatch(value):
        raise ValueError("client_request_id has an invalid shape")
    return value


def secondary_scope_guard(value: str) -> tuple[bool, str]:
    """Close trivial-query suffix bypasses without changing primary Search."""
    out_of_scope, reason = is_out_of_scope(value)
    if out_of_scope:
        return out_of_scope, reason
    has_context = bool(_STRUCTURAL_CONTEXT.search(value))
    first_clause = _CLAUSE_BREAK.split(value, maxsplit=1)[0].strip()
    if first_clause and first_clause != value and not has_context:
        clause_out, clause_reason = is_out_of_scope(first_clause)
        if clause_out:
            return True, clause_reason
    if not has_context and _DIRECT_FACT_QUERY.search(value):
        return True, "trivia"
    return False, "ok"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class EvidenceCandidate(_StrictModel):
    status: Literal["recorded"]
    kind: str = Field(min_length=1, max_length=100)
    label: Optional[str] = Field(default=None, max_length=1_000)
    # Numeric retrieval scores are not calibrated transfer probabilities.
    # Keep them out of every secondary-tool response, including nested fields.
    score: None = None


class EvidenceSource(_StrictModel):
    status: Literal["recorded", "not_recorded"]
    kind: Literal["not_recorded", "internal_kb"]
    label: Optional[str] = Field(default=None, max_length=1_000)
    url: None = None
    source_review: None = None


class EvidenceResult(_StrictModel):
    status: Literal["recorded", "not_recorded"]
    provenance: Literal["NOT_TESTED", "INTERNAL_AI_SCREEN"]
    verdict: Literal["NOT_TESTED", "INCONCLUSIVE"]
    summary: Optional[str] = Field(default=None, max_length=1_000)


class EvidenceIndependence(_StrictModel):
    status: Literal["not_recorded"]
    kind: Literal["not_recorded"]
    summary: Optional[str] = Field(default=None, max_length=1_000)


class EvidenceCounterexamples(_StrictModel):
    status: Literal["not_recorded", "gap_recorded"]
    summary: Optional[str] = Field(default=None, max_length=1_000)


class EvidenceLedger(_StrictModel):
    status: Literal["not_recorded"]
    claim_id: Optional[str] = Field(default=None, max_length=200)
    version: Optional[str] = Field(default=None, max_length=100)
    recorded_at: Optional[str] = Field(default=None, max_length=100)
    artifact_sha256: Optional[str] = Field(default=None, max_length=64)
    url: Optional[str] = Field(default=None, max_length=2_048)


class CandidateEvidenceEnvelope(_StrictModel):
    schema_version: Literal["evidence-envelope-v1"]
    evidence_level: Literal["candidate"]
    candidate: EvidenceCandidate
    source: EvidenceSource
    result: EvidenceResult
    independence: EvidenceIndependence
    counterexamples: EvidenceCounterexamples
    ledger: EvidenceLedger

    @model_validator(mode="after")
    def coherent_candidate_state(self) -> "CandidateEvidenceEnvelope":
        if self.source.kind == "internal_kb":
            if (
                self.source.status != "recorded"
                or self.source.label != "Structural KB record"
                or self.result.status != "not_recorded"
                or self.result.provenance != "NOT_TESTED"
                or self.result.verdict != "NOT_TESTED"
            ):
                raise ValueError("KB candidate evidence state is inconsistent")
        elif (
            self.source.status != "not_recorded"
            or self.source.label is not None
            or self.result.status != "recorded"
            or self.result.provenance != "INTERNAL_AI_SCREEN"
            or self.result.verdict != "INCONCLUSIVE"
        ):
            raise ValueError("internal screen evidence state is inconsistent")
        if any((
            self.ledger.claim_id,
            self.ledger.version,
            self.ledger.recorded_at,
            self.ledger.artifact_sha256,
            self.ledger.url,
        )):
            raise ValueError("candidate evidence cannot carry an unbound ledger")
        return self


def internal_screen_evidence(*, kind: str, label: str) -> dict[str, Any]:
    """Candidate envelope for an LLM screen with no empirical validation."""
    raw = build_evidence_envelope(
        candidate_kind=kind,
        candidate_label=label,
        result_provenance=ResultProvenance.INTERNAL_AI_SCREEN,
        result_verdict="INCONCLUSIVE",
        result_summary="内部模型筛查；尚未经过独立数据或实验验证。",
        counterexample_status="gap_recorded",
        counterexample_summary="需要用反例搜索或现实数据继续检验。",
    )
    return CandidateEvidenceEnvelope.model_validate(raw).model_dump()


def kb_candidate_evidence(
    item: Mapping[str, Any], *, counterexample: Optional[str] = None
) -> dict[str, Any]:
    """Candidate envelope for one allowlisted internal-KB retrieval row."""
    raw = build_evidence_envelope(
        candidate_kind="retrieval_candidate",
        candidate_label=item.get("name") if isinstance(item.get("name"), str) else None,
        source_kind="internal_kb",
        source_label="Structural KB record",
        counterexample_status="gap_recorded" if counterexample else "not_recorded",
        counterexample_summary=counterexample,
    )
    return CandidateEvidenceEnvelope.model_validate(raw).model_dump()


class CandidateReference(_StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(max_length=120)
    description: str = Field(max_length=600)
    retrieval_rank: int = Field(ge=1, le=30)
    candidate_note: Optional[str] = Field(default=None, max_length=600)
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def bind_evidence(self) -> "CandidateReference":
        if self.evidence.candidate.label != self.name:
            raise ValueError("candidate evidence label is not bound to the record")
        if self.evidence.source.kind != "internal_kb":
            raise ValueError("candidate reference must come from the internal KB")
        return self


class StressCorrespondence(_StrictModel):
    claim: str = Field(min_length=1, max_length=600)
    screening_outcome: Literal["not_broken", "breaks", "uncertain"]
    stress_result: str = Field(min_length=1, max_length=1_000)


class StressTestResponse(_StrictModel):
    contract_version: Literal["secondary-tools-v2"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$")
    claim: str = Field(min_length=4, max_length=600)
    screening_outcome: Literal[
        "not_broken_in_screen", "breaks_in_screen", "condition_dependent"
    ]
    screening_basis: Literal["internal_ai_red_team"]
    source: str = Field(min_length=1, max_length=400)
    target: str = Field(min_length=1, max_length=400)
    structural_correspondences: list[StressCorrespondence] = Field(
        min_length=1, max_length=12
    )
    weakest_link: str = Field(min_length=1, max_length=1_000)
    rationale: str = Field(min_length=1, max_length=1_200)
    candidate_reference: Optional[CandidateReference]
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def bind_screen(self) -> "StressTestResponse":
        if self.evidence.candidate.label != self.claim:
            raise ValueError("stress evidence is not bound to the request")
        return self


class StructuralState(_StrictModel):
    state_id: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    name: str = Field(min_length=1, max_length=120)
    definition: str = Field(min_length=1, max_length=500)
    typical_signal: str = Field(min_length=1, max_length=500)


class DiagnoseResponse(_StrictModel):
    contract_version: Literal["secondary-tools-v2"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$")
    situation: str = Field(min_length=12, max_length=1_500)
    assessment_kind: Literal["structural_state_hypothesis"]
    primary_state: StructuralState
    secondary_state: Optional[StructuralState]
    reasoning: str = Field(min_length=1, max_length=1_500)
    evolution: str = Field(min_length=1, max_length=1_200)
    signals_to_watch: list[str] = Field(max_length=6)
    recommendations: list[str] = Field(max_length=5)
    candidate_reference: Optional[CandidateReference]
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def distinct_states(self) -> "DiagnoseResponse":
        if self.secondary_state and self.secondary_state.state_id == self.primary_state.state_id:
            raise ValueError("primary and secondary state must differ")
        if self.evidence.candidate.label != self.situation:
            raise ValueError("diagnosis evidence is not bound to the request")
        return self


class MethodCandidate(_StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
    name: str = Field(min_length=1, max_length=200)
    domain: str = Field(max_length=120)
    type_id: str = Field(max_length=120)
    description: str = Field(max_length=600)
    retrieval_rank: int = Field(ge=1, le=20)
    candidate_note: Optional[str] = Field(default=None, max_length=240)
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def bind_evidence(self) -> "MethodCandidate":
        if self.evidence.candidate.label != self.name:
            raise ValueError("method candidate evidence label is not bound")
        if self.evidence.source.kind != "internal_kb":
            raise ValueError("method candidate must be an internal KB row")
        return self


class MethodApplyResponse(_StrictModel):
    contract_version: Literal["secondary-tools-v2"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$")
    method: str = Field(min_length=4, max_length=1_000)
    signature: str = Field(min_length=1, max_length=600)
    signature_origin: Literal["model_generated", "input_fallback"]
    keywords: list[str] = Field(max_length=6)
    count: int = Field(ge=0, le=20)
    candidates: list[MethodCandidate] = Field(max_length=20)
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def bind_candidate_set(self) -> "MethodApplyResponse":
        if self.count != len(self.candidates):
            raise ValueError("candidate count mismatch")
        ids = [candidate.id for candidate in self.candidates]
        ranks = [candidate.retrieval_rank for candidate in self.candidates]
        if len(ids) != len(set(ids)) or ranks != list(range(1, len(ranks) + 1)):
            raise ValueError("candidate identity or retrieval rank is invalid")
        if self.evidence.candidate.label != self.method:
            raise ValueError("method evidence is not bound to the request")
        return self


class LintClaim(_StrictModel):
    claim_id: str = Field(pattern=r"^lint-[0-9a-f]{16}$")
    quote: str = Field(min_length=1, max_length=600)
    claim_type: Literal["assumption", "analogy", "causal_judgment"]
    structure: str = Field(min_length=1, max_length=800)
    failure_mode: str = Field(min_length=1, max_length=800)
    review_priority: Literal["high", "medium", "low"]
    suggestion: str = Field(min_length=1, max_length=800)
    reference_candidate: Optional[CandidateReference]
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def bind_screen(self) -> "LintClaim":
        if self.evidence.candidate.label != self.quote:
            raise ValueError("lint evidence is not bound to its quote")
        return self


class StructLintResponse(_StrictModel):
    contract_version: Literal["secondary-tools-v2"]
    request_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{11,63}$")
    screening_kind: Literal["internal_ai_document_screen"]
    summary: str = Field(min_length=1, max_length=1_200)
    claims: list[LintClaim] = Field(max_length=30)
    evidence: CandidateEvidenceEnvelope

    @model_validator(mode="after")
    def unique_claims(self) -> "StructLintResponse":
        ids = [claim.claim_id for claim in self.claims]
        if len(ids) != len(set(ids)):
            raise ValueError("claim ids must be unique")
        if self.evidence.candidate.label != "用户提交的策略文档":
            raise ValueError("lint evidence is not bound to the submitted document")
        return self


__all__ = [
    "CONTRACT_VERSION",
    "REQUEST_ID_PATTERN",
    "CandidateEvidenceEnvelope",
    "CandidateReference",
    "StressTestResponse",
    "DiagnoseResponse",
    "MethodApplyResponse",
    "StructLintResponse",
    "ensure_request_id",
    "secondary_scope_guard",
    "internal_screen_evidence",
    "kb_candidate_evidence",
]
