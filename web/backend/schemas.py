"""Consolidated public Pydantic schemas for the structural-isomorphism
HTTP API. This module is the **single source of truth** for the
TypeScript types generated into `web/phase-detector/lib/api-types.ts`
via `scripts/gen_ts_types.sh`.

W15-A (session #10, 2026-05-15): introduces the typed-API pipeline:

    Pydantic (here)  ─pydantic2ts─►  api-types.ts  ─import─►  frontend

We re-define (not re-import) every public request/response model here
so that:

1. `pydantic2ts` can `importlib` this single module without dragging in
   the full FastAPI app (which has slow side effects: env, logging,
   slowapi, DB pools, embedding model warm-up).
2. The "TS contract" surface is explicit and reviewable in one file —
   you can grep one place to see every field the frontend can see.
3. Existing endpoint files keep their inline `BaseModel` definitions
   unchanged (no behavioural risk) — those continue to drive the
   runtime FastAPI validation. The schemas here mirror them; a
   conformance test (`tests/test_types_sync.py`) keeps both in step.

Adding a new public endpoint?
    1. Add the request/response model here.
    2. Run `bash scripts/gen_ts_types.sh` and commit the regenerated
       `api-types.ts`.
    3. The CI `types-sync.yml` workflow blocks merges if the committed
       file is stale.

NOTE: Pydantic v2. Avoid `dict` / `list` without parameters — use
`Dict[str, Any]` / `List[T]` so `json2ts` can emit a precise shape.
"""
from __future__ import annotations

from datetime import date as calendar_date
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator

if __package__ == "web.backend":
    from .services.input_limits import MAX_RESEARCH_QUERY_CHARS
    from .services.candidate_origin import (
        analyze_url_for_candidate,
        discovery_id_for_pair,
        normalize_candidate_family_id,
        normalize_candidate_identifier,
    )
else:
    try:
        from services.input_limits import MAX_RESEARCH_QUERY_CHARS
        # Beta runtime imports this file as top-level ``schemas`` with
        # ``web/backend`` on sys.path.
        from services.candidate_origin import (
            analyze_url_for_candidate,
            discovery_id_for_pair,
            normalize_candidate_family_id,
            normalize_candidate_identifier,
        )
    except ModuleNotFoundError as exc:
        if exc.name not in {
            "services", "services.candidate_origin", "services.input_limits"
        }:
            raise
        # Type generation and its conformance tests load this file directly
        # through spec_from_file_location, without putting either the repo root
        # or web/backend on sys.path. Load the same adjacent pure helper by
        # absolute path; do not copy its identity rules into this schema file.
        import importlib.util as _importlib_util
        from pathlib import Path as _Path

        _limits_path = _Path(__file__).resolve().parent / "services" / "input_limits.py"
        _limits_spec = _importlib_util.spec_from_file_location(
            "_structural_input_limits_for_schemas", _limits_path,
        )
        if _limits_spec is None or _limits_spec.loader is None:
            raise ImportError(f"cannot load input limits helper: {_limits_path}")
        _limits = _importlib_util.module_from_spec(_limits_spec)
        _limits_spec.loader.exec_module(_limits)
        MAX_RESEARCH_QUERY_CHARS = _limits.MAX_RESEARCH_QUERY_CHARS

        _identity_path = _Path(__file__).resolve().parent / "services" / "candidate_origin.py"
        _identity_spec = _importlib_util.spec_from_file_location(
            "_structural_candidate_origin_for_schemas", _identity_path,
        )
        if _identity_spec is None or _identity_spec.loader is None:
            raise ImportError(f"cannot load candidate identity helper: {_identity_path}")
        _identity = _importlib_util.module_from_spec(_identity_spec)
        _identity_spec.loader.exec_module(_identity)
        analyze_url_for_candidate = _identity.analyze_url_for_candidate
        discovery_id_for_pair = _identity.discovery_id_for_pair
        normalize_candidate_family_id = _identity.normalize_candidate_family_id
        normalize_candidate_identifier = _identity.normalize_candidate_identifier


# ---------------------------------------------------------------------------
# /api/ask/stream  (web/backend/api/ask.py)
# ---------------------------------------------------------------------------
class AskRequest(BaseModel):
    """Body for POST /api/ask/stream — Perplexity-like SSE endpoint."""

    query: str = Field(..., min_length=1, max_length=8001)
    lang: Literal["zh", "en"] = "zh"


class AskMeta(BaseModel):
    """First SSE event from /api/ask/stream — echoes the rewritten query
    and the planned downstream steps. Frontend renders this as the
    'thinking about: <query>' line.
    """

    rewritten: str
    steps: List[str] = Field(default_factory=list)


class KBCard(BaseModel):
    """A single retrieved phenomenon card surfaced in `kb_cards` event."""

    id: str
    name: str
    domain: str
    score: float
    snippet: Optional[str] = None


class AnswerDone(BaseModel):
    """`answer_done` event payload. `out_of_scope=true` means the
    retrieval relevance gate failed — frontend should soften the UI.
    """

    text: str
    out_of_scope: bool = False
    scope_reason: Optional[str] = None
    citations: List[str] = Field(default_factory=list)


class Verdict(BaseModel):
    """Final verdict assembled from /api/ask/stream — exported for
    fixtures + Storybook stories so they stay in lockstep with API.
    """

    summary: str
    confidence: float
    similar_phenomena: List[KBCard] = Field(default_factory=list)
    followups: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /api/checkout/mock  (web/backend/api/checkout_mock.py)
# ---------------------------------------------------------------------------
class CheckoutBody(BaseModel):
    """Legacy development simulator input.

    Production returns HTTP 410 before recording any submitted fields.
    """

    tier: str
    interval: str = "month"
    email: str
    name: Optional[str] = ""
    card_last4: Optional[str] = ""
    force_status: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Legacy development-only simulator response.

    Production returns HTTP 410 and has no checkout or paid entitlement.
    This type must not be treated as a current billing contract.
    """

    status: Literal["success", "declined"]
    reason: Optional[Literal["card_declined"]] = None
    customer_id: Optional[str] = None
    checkout_session_id: Optional[str] = None
    tier: Optional[Literal["pro", "team"]] = None
    interval: Optional[Literal["month", "year"]] = None
    amount_usd: Optional[int] = None


# ---------------------------------------------------------------------------
# /api/history  (web/backend/api/history.py)
# ---------------------------------------------------------------------------
class HistoryRecordRequest(BaseModel):
    """Body for POST /api/history — records one user query."""

    query: str = Field(..., min_length=1, max_length=2000)
    kind: str = Field(..., min_length=1)
    result_summary: Optional[Dict[str, Any]] = None


class HistoryRecord(BaseModel):
    """A single history row returned by GET /api/history."""

    id: int
    query: str
    kind: str
    result_summary: Optional[str] = None
    created_at: str  # ISO-8601 UTC


class HistoryResponse(BaseModel):
    """GET /api/history response envelope."""

    items: List[HistoryRecord] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# /api/search  (web/backend/api/search.py)
# ---------------------------------------------------------------------------
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    top_k: int = Field(12, ge=1, le=30)
    rewrite: bool = False
    lang: str = "zh"


class AssessRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS)
    lang: str = "zh"


class SearchResult(BaseModel):
    id: str
    name: str
    domain: str
    type_id: str
    description: str
    score: float


class SearchResponse(BaseModel):
    query: str
    count: int
    results: List[SearchResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# /api/mapping  (web/backend/api/mapping.py)
# ---------------------------------------------------------------------------
class MappingRequest(BaseModel):
    a_id: str = Field(..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    b_id: str = Field(..., min_length=1, max_length=120, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    lang: Literal["zh", "en"] = "zh"

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_distinct_pair(self) -> "MappingRequest":
        if self.a_id == self.b_id:
            raise ValueError("mapping pair must contain two distinct phenomena")
        return self


class MappingStreamRequest(BaseModel):
    b_id: str = Field(
        ..., min_length=1, max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$",
    )
    a_id: Optional[str] = Field(
        default=None, min_length=1, max_length=120,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$",
    )
    text_a: Optional[str] = Field(
        default=None, min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS,
    )
    lang: Literal["zh", "en"] = "zh"

    model_config = {"extra": "forbid", "strict": True}

    @model_validator(mode="after")
    def validate_stream_mode(self) -> "MappingStreamRequest":
        if (self.a_id is None) == (self.text_a is None):
            raise ValueError("provide exactly one of a_id or text_a")
        if self.a_id == self.b_id:
            raise ValueError("mapping pair must contain two distinct phenomena")
        return self


_CONFIRMED_MAPPING_CLAIM = re.compile(
    r"(?:"
    r"本质上(?:是)?同一(?:件事|回事)|"
    r"(?:结构同构|共享机制)(?:已经|已|得到)?(?:确认|证实|证明|成立)|"
    r"必然(?:成立|适用|有效)|"
    r"(?:are|is)\s+(?:structurally\s+)?isomorphic|"
    r"(?:the\s+)?same\s+underlying\s+mechanism|"
    r"(?:has\s+been|is)\s+(?:proven|confirmed|validated)|"
    r"validated\s+mapping"
    r")",
    re.IGNORECASE,
)


def _text_has_safe_controls(value: str) -> bool:
    return not any(ord(char) < 32 and char not in "\t\n\r" for char in value)


def _mapping_text_is_safe(value: str) -> bool:
    if not _text_has_safe_controls(value):
        return False
    return _CONFIRMED_MAPPING_CLAIM.search(value) is None


class MappingParameter(BaseModel):
    a_term: str = Field(..., min_length=1, max_length=160)
    a_symbol: str = Field(default="", max_length=80)
    b_term: str = Field(..., min_length=1, max_length=160)
    b_symbol: str = Field(default="", max_length=80)
    note: str = Field(..., min_length=1, max_length=500)

    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class MappingValidationSuggestion(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field(..., min_length=1, max_length=1000)
    scenario: str = Field(..., min_length=1, max_length=500)
    failure_signal: str = Field(..., min_length=1, max_length=500)

    model_config = {"extra": "forbid", "str_strip_whitespace": True}


class CandidateMapping(BaseModel):
    """A bounded hypothesis contract; never a verified-isomorphism claim."""

    schema_version: Literal["candidate-mapping-v2"]
    evidence_level: Literal["candidate"]
    generation_status: Literal["generated", "fallback"]
    structure_name: str = Field(..., min_length=1, max_length=200)
    formula: str = Field(default="", max_length=500)
    candidate_rationale: str = Field(..., min_length=1, max_length=1200)
    parameter_mapping: List[MappingParameter] = Field(default_factory=list, max_length=8)
    validation_suggestions: List[MappingValidationSuggestion] = Field(
        ..., min_length=1, max_length=5
    )
    alternative_explanations: List[str] = Field(..., min_length=1, max_length=5)
    failure_conditions: List[str] = Field(..., min_length=1, max_length=5)
    why_worth_testing: str = Field(..., min_length=1, max_length=1000)

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_public_claim_boundary(self) -> "CandidateMapping":
        prose = [
            self.structure_name,
            self.candidate_rationale,
            self.why_worth_testing,
            *self.alternative_explanations,
            *self.failure_conditions,
        ]
        if any(not value.strip() or len(value) > 500 for value in self.alternative_explanations):
            raise ValueError("alternative explanations must be bounded non-empty text")
        if any(not value.strip() or len(value) > 500 for value in self.failure_conditions):
            raise ValueError("failure conditions must be bounded non-empty text")
        for row in self.parameter_mapping:
            prose.extend([row.a_term, row.a_symbol, row.b_term, row.b_symbol, row.note])
        for suggestion in self.validation_suggestions:
            prose.extend(
                [
                    suggestion.title,
                    suggestion.description,
                    suggestion.scenario,
                    suggestion.failure_signal,
                ]
            )
        if not all(_mapping_text_is_safe(value) for value in prose):
            raise ValueError("mapping output crosses the candidate evidence boundary")
        if not _mapping_text_is_safe(self.formula):
            raise ValueError("mapping formula contains unsafe control text")
        return self


class MappingSide(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(..., min_length=1, max_length=200)
    type_id: str = Field(..., min_length=1, max_length=120)
    description: str = Field(
        ..., min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    original_query: Optional[str] = Field(
        default=None, min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_public_text(self) -> "MappingSide":
        values = [
            self.id, self.name, self.domain, self.type_id, self.description,
            self.original_query or "",
        ]
        if not all(_text_has_safe_controls(value) for value in values):
            raise ValueError("mapping side contains unsafe control text")
        return self


class MappingResponse(BaseModel):
    schema_version: Literal["mapping-response-v2"]
    from_cache: bool
    a: MappingSide
    b: MappingSide
    retrieval_similarity: float = Field(..., ge=-1.0, le=1.0, allow_inf_nan=False)
    mapping: CandidateMapping

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# /api/phenomenon/{id}  (web/backend/api/phenomenon.py)
# ---------------------------------------------------------------------------
class PhenomenonEvidenceCandidate(BaseModel):
    status: Literal["recorded"]
    kind: Literal[
        "phenomenon_kb_record_candidate",
        "embedding_neighbor_candidate",
        "shared_type_label_candidate",
        "v2_model_pair_candidate",
    ]
    label: str = Field(..., min_length=1, max_length=1000)
    score: Literal[None] = None

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceSource(BaseModel):
    status: Literal["recorded"]
    kind: Literal["internal_kb"]
    label: str = Field(..., min_length=1, max_length=1000)
    url: Literal[None] = None
    source_review: Literal[None] = None

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceResult(BaseModel):
    status: Literal["not_recorded", "recorded"]
    provenance: Literal["NOT_TESTED", "INTERNAL_AI_SCREEN"]
    verdict: Literal["NOT_TESTED", "INCONCLUSIVE"]
    summary: Optional[str] = Field(default=None, max_length=1000)

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceIndependence(BaseModel):
    status: Literal["not_recorded", "recorded"]
    kind: Literal["not_recorded", "internal"]
    summary: Optional[str] = Field(default=None, max_length=1000)

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceCounterexamples(BaseModel):
    status: Literal["gap_recorded"]
    summary: str = Field(..., min_length=1, max_length=1000)

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceLedger(BaseModel):
    status: Literal["not_recorded"]
    claim_id: Literal[None] = None
    version: Literal[None] = None
    recorded_at: Literal[None] = None
    artifact_sha256: Literal[None] = None
    url: Literal[None] = None

    model_config = {"extra": "forbid"}


class PhenomenonEvidenceEnvelope(BaseModel):
    schema_version: Literal["evidence-envelope-v1"]
    evidence_level: Literal["candidate"]
    candidate: PhenomenonEvidenceCandidate
    source: PhenomenonEvidenceSource
    result: PhenomenonEvidenceResult
    independence: PhenomenonEvidenceIndependence
    counterexamples: PhenomenonEvidenceCounterexamples
    ledger: PhenomenonEvidenceLedger

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_generation_path(self) -> "PhenomenonEvidenceEnvelope":
        is_record = self.candidate.kind == "phenomenon_kb_record_candidate"
        if is_record:
            expected_result = ("not_recorded", "NOT_TESTED", "NOT_TESTED", None)
            expected_independence = ("not_recorded", "not_recorded", None)
        else:
            expected_result = ("recorded", "INTERNAL_AI_SCREEN", "INCONCLUSIVE")
            expected_independence = ("recorded", "internal")
        result = (
            self.result.status,
            self.result.provenance,
            self.result.verdict,
            self.result.summary,
        )
        independence = (
            self.independence.status,
            self.independence.kind,
            self.independence.summary,
        )
        if is_record:
            if result != expected_result or independence != expected_independence:
                raise ValueError("KB record evidence must remain untested and unreviewed")
        else:
            if result[:3] != expected_result or not result[3]:
                raise ValueError("candidate screen evidence is incomplete")
            if independence[:2] != expected_independence or not independence[2]:
                raise ValueError("candidate screen independence boundary is incomplete")
        return self


class PhenomenonRecord(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(..., min_length=1, max_length=200)
    type_id: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2500)
    evidence: PhenomenonEvidenceEnvelope

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_record_evidence(self) -> "PhenomenonRecord":
        if self.evidence.candidate.kind != "phenomenon_kb_record_candidate":
            raise ValueError("phenomenon record has the wrong evidence kind")
        if self.evidence.candidate.label != self.name:
            raise ValueError("phenomenon record evidence label does not match")
        return self


class PhenomenonSimilarCandidate(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(..., min_length=1, max_length=200)
    type_id: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2500)
    retrieval_similarity: float = Field(..., ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: PhenomenonEvidenceEnvelope

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_similar_evidence(self) -> "PhenomenonSimilarCandidate":
        if self.evidence.candidate.kind != "embedding_neighbor_candidate":
            raise ValueError("embedding candidate has the wrong evidence kind")
        if self.evidence.candidate.label != self.name:
            raise ValueError("embedding candidate evidence label does not match")
        return self


class PhenomenonSameStructureCandidate(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=500)
    domain: str = Field(..., min_length=1, max_length=200)
    type_id: str = Field(..., min_length=1, max_length=120)
    description: str = Field(..., min_length=1, max_length=2500)
    evidence: PhenomenonEvidenceEnvelope

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_label_candidate_evidence(self) -> "PhenomenonSameStructureCandidate":
        if self.evidence.candidate.kind != "shared_type_label_candidate":
            raise ValueError("shared-label candidate has the wrong evidence kind")
        if self.evidence.candidate.label != self.name:
            raise ValueError("shared-label candidate evidence label does not match")
        return self


class PhenomenonV2Candidate(BaseModel):
    other_id: str = Field(..., min_length=1, max_length=120)
    other_name: str = Field(..., min_length=1, max_length=500)
    other_domain: str = Field(..., min_length=1, max_length=200)
    candidate_reason: str = Field(..., min_length=1, max_length=1200)
    retrieval_similarity: float = Field(..., ge=0.0, le=1.0, allow_inf_nan=False)
    evidence: PhenomenonEvidenceEnvelope

    model_config = {"extra": "forbid", "str_strip_whitespace": True}

    @model_validator(mode="after")
    def validate_v2_evidence(self) -> "PhenomenonV2Candidate":
        if self.evidence.candidate.kind != "v2_model_pair_candidate":
            raise ValueError("V2 candidate has the wrong evidence kind")
        if self.evidence.candidate.label != self.other_name:
            raise ValueError("V2 candidate evidence label does not match")
        return self


class PhenomenonResponse(BaseModel):
    phenomenon: PhenomenonRecord
    similar: List[PhenomenonSimilarCandidate] = Field(default_factory=list, max_length=8)
    same_structure: List[PhenomenonSameStructureCandidate] = Field(
        default_factory=list, max_length=5
    )
    v2_pairs: List[PhenomenonV2Candidate] = Field(default_factory=list, max_length=20)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_unique_candidates(self) -> "PhenomenonResponse":
        collections = [
            [row.id for row in self.similar],
            [row.id for row in self.same_structure],
            [row.other_id for row in self.v2_pairs],
        ]
        if any(len(ids) != len(set(ids)) for ids in collections):
            raise ValueError("phenomenon candidate ids must be unique within each collection")
        if any(self.phenomenon.id in ids for ids in collections):
            raise ValueError("phenomenon response cannot repeat its main record")
        return self


# ---------------------------------------------------------------------------
# /api/error-log  (web/backend/api/error_log.py)
# ---------------------------------------------------------------------------
class ErrorReportBody(BaseModel):
    """Content-free client error envelope mirrored from the runtime API."""

    message: Literal[
        "ChunkLoadError", "ClientError", "Error", "NetworkError",
        "RangeError", "ReferenceError", "SyntaxError", "TypeError", "URIError",
    ]
    timestamp: Optional[int] = Field(default=None, ge=0, le=4_102_444_800)
    fatal: bool = False

    model_config = {"extra": "forbid"}


# ---------------------------------------------------------------------------
# /api/synthesize  (web/backend/api/synthesize.py)
# ---------------------------------------------------------------------------
class SynthesizeRequest(BaseModel):
    query: str
    rewritten_query: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
    lang: str = "zh"


# ---------------------------------------------------------------------------
# /api/newsletter/subscribe  (web/backend/api/newsletter.py)
# ---------------------------------------------------------------------------
class SubscribeBody(BaseModel):
    email: str
    source: Optional[str] = "unknown"


# ---------------------------------------------------------------------------
# /api/privacy/*  (web/backend/api/privacy/*.py)
# ---------------------------------------------------------------------------
class CookieConsent(BaseModel):
    """Cookie-consent record persisted on the client + mirrored on the
    server when the user opts in. W14-C surface model.
    """

    necessary: bool = True
    analytics: bool = False
    marketing: bool = False
    timestamp: Optional[int] = None


class PrivacyExportRequest(BaseModel):
    """Legacy development-only query shape for GET /api/privacy/export.

    A schema-valid production request returns HTTP 410. Constraint-invalid
    query values return HTTP 422 before the handler. This retired email-code
    fixture is not an account right or production authentication mechanism;
    signed-in export is ``GET /api/me/export``.
    """

    email: Optional[str] = None
    code: Optional[str] = None
    session_id: Optional[str] = None


class PrivacyExportData(BaseModel):
    """Data groups emitted by the retired development export fixture."""

    newsletter_subscribers: List[Dict[str, Any]]
    mock_checkouts: List[Dict[str, Any]]
    error_log: List[Dict[str, Any]]
    structural_fingerprints: List[Dict[str, Any]]
    match_requests: List[Dict[str, Any]]
    referrals: List[Dict[str, Any]]
    connections_messages: List[Dict[str, Any]]
    connections_prefs: List[Dict[str, Any]]
    search_history: List[Dict[str, Any]]


class PrivacyExportResponse(BaseModel):
    """Legacy development fixture; not the current account-export contract.

    Production returns HTTP 410. Use ``GET /api/me/export`` for the
    authenticated account-bound export.
    """

    ok: Literal[True]
    exported_at: str
    email: Optional[str]
    session_id: Optional[str]
    data: PrivacyExportData


class PrivacyDeleteRequest(BaseModel):
    """Legacy development-only query shape for DELETE /api/privacy/delete.

    A schema-valid production request returns HTTP 410. Constraint-invalid
    query values return HTTP 422 before the handler. Current authenticated
    account erasure is ``POST /api/me/delete`` and requires an active session.
    """

    email: Optional[str] = None
    code: Optional[str] = None
    session_id: Optional[str] = None


class PrivacyRemovalCounts(BaseModel):
    """Per-store removal counts from the retired development fixture."""

    newsletter_subscribers: int = Field(ge=0)
    mock_checkouts: int = Field(ge=0)
    error_log: int = Field(ge=0)
    structural_fingerprints: int = Field(ge=0)
    match_requests: int = Field(ge=0)
    referrals: int = Field(ge=0)
    connections_messages: int = Field(ge=0)
    connections_prefs: int = Field(ge=0)


class PrivacyDeleteResponse(BaseModel):
    """Legacy development fixture; not the current account-erasure contract.

    Production returns HTTP 410. Use ``POST /api/me/delete`` for the
    authenticated account-bound deletion flow.
    """

    ok: Literal[True]
    deleted_at: str
    removed: PrivacyRemovalCounts
    email_confirmation: Literal["sent", "skipped"]


# ---------------------------------------------------------------------------
# /api/companies + /api/phases  (web/backend/api/* — screener endpoints)
# ---------------------------------------------------------------------------
class Company(BaseModel):
    """A single company row in the screener. Mirrors the inline
    `Company` shape from `web/phase-detector/lib/types.ts` — listed here
    so the generated TS file owns the canonical shape.
    """

    ticker: str
    name: str
    sector: str
    dynamics_family: str
    critical_point_state: str
    extraction_confidence: float
    signals: List[str] = Field(default_factory=list)


class CompaniesResponse(BaseModel):
    items: List[Company] = Field(default_factory=list)
    total: int = 0


class Phase(BaseModel):
    """Universality class / phase descriptor."""

    id: str
    name: str
    domain: str
    description: str
    company_count: int = 0


class PhasesResponse(BaseModel):
    items: List[Phase] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Problem-detail error envelope (web/backend/errors.py)
# ---------------------------------------------------------------------------
class ProblemDetailEnvelope(BaseModel):
    """RFC 7807-style error envelope returned by every failing endpoint.
    Frontend can rely on `type` + `code` being present.
    """

    type: str
    title: str
    status: int
    code: str
    detail: Optional[str] = None
    instance: Optional[str] = None


# ---------------------------------------------------------------------------
# System endpoints (main.py: /api/health, /api/version, /api/whoami)
# ---------------------------------------------------------------------------
# 2026-05-15 W17 typed-OpenAPI fill-in. Added so the public OpenAPI spec
# no longer ships `{}` placeholders for endpoints that have a stable
# response shape. New endpoints should ship typed by default.
class HealthResponse(BaseModel):
    """GET /api/health — liveness/deep-probe response."""

    status: str = "ok"
    kb_size: int = 0
    llm_model: str = "unknown"
    artifact_id: Optional[str] = None
    embedding_shape: Optional[List[int]] = None
    # Deep mode (`?deep=1`) adds a `checks` map of sub-system probes.
    checks: Optional[Dict[str, str]] = None
    query_cache: Optional[Dict[str, float]] = Field(
        default=None,
        description=(
            "Deep mode (`?deep=1`) surfaces the query-embedding LRU cache hit rate "
            "(Session #17 P2). Values are numeric (int counts + float hit_rate)."
        ),
    )


class VersionResponse(BaseModel):
    """GET /api/version — build & version metadata.

    Session #16 added `model` + `deployed_at` after the session #15
    deploy-pipeline incident: dogfood scripts need a single endpoint to
    fingerprint-check that prod is running the latest code AND that the model
    variant matches expectations (e.g. `:nitro` vs non-nitro DeepSeek).
    """

    semver: str
    git_sha: str
    build_date: str
    python_version: str
    python_abi: str
    runtime_id: str
    requirements_sha256: str
    installed_freeze_sha256: str
    fastapi: str
    pydantic: str
    starlette: str
    uvicorn: str
    env: str
    model: str = Field(
        description="Model identifier the /api/ask endpoint will use (session #16).",
    )
    deployed_at: str = Field(
        description=(
            "Deploy timestamp, distinct from build_date (image built once, deployed "
            "many times). Falls back to build_date if STRUCTURAL_DEPLOYED_AT unset."
        ),
    )


class WhoAmIResponse(BaseModel):
    """GET /api/whoami — debug helper reflecting the resolved auth tier."""

    tier: str
    api_key_supplied: bool


# ---------------------------------------------------------------------------
# /api/examples + /api/discoveries + /api/daily + /api/flags + /api/newsletter
# ---------------------------------------------------------------------------
class ExamplesResponse(BaseModel):
    """GET /api/examples — handpicked example phenomenon pairs.

    Items are intentionally loose (raw KB rows are reshaped at render
    time) so we keep `List[Dict[str, Any]]` instead of pinning a strict
    KB-row shape.
    """

    examples: List[Dict[str, Any]] = Field(default_factory=list)


class NewsletterCountResponse(BaseModel):
    """GET /api/newsletter/count — current subscriber count (anon-safe)."""

    count: int = 0


class ErrorAcceptedResponse(BaseModel):
    """POST /api/errors — accepted/rate_limited/storage_failure envelope.

    `accepted=true` ⇒ persisted to disk and `stored_at` is set.
    `accepted=false` ⇒ `reason` is set (`rate_limited` / `storage_failure`).
    """

    accepted: bool
    stored_at: Optional[str] = None  # ISO-8601 UTC when accepted=True
    reason: Optional[str] = None  # set when accepted=False

    model_config = {"extra": "allow"}


class LocalizedDiscoveryText(BaseModel):
    zh: str
    en: str = ""

    model_config = {"extra": "forbid"}


class DiscoveryPairSide(BaseModel):
    id: str
    name: LocalizedDiscoveryText
    domain: LocalizedDiscoveryText

    model_config = {"extra": "forbid"}


class DiscoveryPair(BaseModel):
    a: DiscoveryPairSide
    b: DiscoveryPairSide

    model_config = {"extra": "forbid"}


class DiscoveryProvenance(BaseModel):
    status: Literal["not_started", "incomplete_review"]
    recorded_source_count: int = Field(..., ge=0)
    independent_review_complete: Literal[False]
    systematic_search_recorded: Literal[False]

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_source_progress(self) -> "DiscoveryProvenance":
        expected = "not_started" if self.recorded_source_count == 0 else "incomplete_review"
        if self.status != expected:
            raise ValueError("discovery provenance status does not match source count")
        return self


class DiscoveryReadiness(BaseModel):
    status: Literal["blocked"]
    ready_for_preregistration: Literal[False]
    blockers: List[
        Literal[
            "source_review",
            "candidate_equation",
            "variable_mapping",
            "dataset_record",
            "primary_metric",
            "preregistered_stop_rule",
        ]
    ]

    model_config = {"extra": "forbid"}


class DiscoveryValidationGap(BaseModel):
    gap_id: Literal[
        "source_support_not_reviewed",
        "candidate_equation_not_recorded",
        "candidate_equation_not_expert_reviewed",
        "variable_mapping_not_recorded",
        "variable_mapping_not_expert_reviewed",
        "competing_explanations_not_tested",
        "dataset_and_sampling_not_recorded",
        "baseline_and_stop_rule_not_preregistered",
    ]
    label: LocalizedDiscoveryText

    model_config = {"extra": "forbid"}


class DiscoveryValidationPlan(BaseModel):
    status: Literal["draft_requires_user_completion"]
    hypothesis: LocalizedDiscoveryText
    data_needed: LocalizedDiscoveryText
    baseline: LocalizedDiscoveryText
    primary_metric: LocalizedDiscoveryText
    failure_condition: LocalizedDiscoveryText
    validation_gaps: List[DiscoveryValidationGap] = Field(default_factory=list)
    preregistered: Literal[False]

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceSourceReview(BaseModel):
    reviewer: str
    reviewed_at: str

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceCandidate(BaseModel):
    status: Literal["recorded"]
    kind: Literal["discovery_candidate", "tier2_discovery_candidate"]
    label: Optional[str] = None
    score: Literal[None] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceSource(BaseModel):
    status: Literal["not_recorded"]
    kind: Literal["not_recorded"]
    label: Literal[None] = None
    url: Literal[None] = None
    source_review: Literal[None] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceResult(BaseModel):
    status: Literal["not_recorded"]
    provenance: Literal["NOT_TESTED"]
    verdict: Literal["NOT_TESTED"]
    summary: Literal[None] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceIndependence(BaseModel):
    status: Literal["not_recorded"]
    kind: Literal["not_recorded"]
    summary: Literal[None] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceCounterexamples(BaseModel):
    status: Literal["not_recorded", "gap_recorded"]
    summary: Optional[str] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceLedger(BaseModel):
    status: Literal["not_recorded"]
    claim_id: Literal[None] = None
    version: Literal[None] = None
    recorded_at: Literal[None] = None
    artifact_sha256: Literal[None] = None
    url: Literal[None] = None

    model_config = {"extra": "forbid"}


class DiscoveryEvidenceEnvelope(BaseModel):
    schema_version: Literal["evidence-envelope-v1"]
    evidence_level: Literal["candidate"]
    candidate: DiscoveryEvidenceCandidate
    source: DiscoveryEvidenceSource
    result: DiscoveryEvidenceResult
    independence: DiscoveryEvidenceIndependence
    counterexamples: DiscoveryEvidenceCounterexamples
    ledger: DiscoveryEvidenceLedger

    model_config = {"extra": "forbid"}


class DiscoveryCandidate(BaseModel):
    schema_version: Literal["discovery-candidate-v2"]
    discovery_id: str
    candidate_family_id: str
    family_variant_count: int = Field(..., ge=1)
    rank: int = Field(..., ge=1)
    tier: Literal["priority_review", "candidate_pool"]
    pipeline: Optional[Literal["V2", "V3"]] = None
    pair: DiscoveryPair
    candidate_summary: LocalizedDiscoveryText
    candidate_equations: List[str] = Field(default_factory=list)
    candidate_variable_mapping: Dict[str, str] = Field(default_factory=dict)
    evidence_language: Literal["zh_only", "not_recorded"]
    provenance: DiscoveryProvenance
    readiness: DiscoveryReadiness
    validation_plan: DiscoveryValidationPlan
    analyze_url: str
    evidence: DiscoveryEvidenceEnvelope

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_candidate_consistency(self) -> "DiscoveryCandidate":
        a_id = normalize_candidate_identifier(self.pair.a.id)
        b_id = normalize_candidate_identifier(self.pair.b.id)
        if a_id is None or b_id is None or a_id == b_id:
            raise ValueError("discovery pair ids must be distinct canonical identifiers")
        expected_id = discovery_id_for_pair(a_id, b_id)
        if self.discovery_id != expected_id:
            raise ValueError("discovery id does not match its immutable KB pair")
        if normalize_candidate_family_id(self.candidate_family_id) is None:
            raise ValueError("discovery family id is not canonical")
        expected_kind = "discovery_candidate" if self.tier == "priority_review" else "tier2_discovery_candidate"
        if self.evidence.candidate.kind != expected_kind:
            raise ValueError("discovery evidence kind does not match review tier")
        if self.tier == "priority_review" and self.pipeline not in {"V2", "V3"}:
            raise ValueError("priority discovery pipeline must be V2 or V3")
        if self.tier == "candidate_pool" and self.pipeline is not None:
            raise ValueError("candidate-pool discovery pipeline must be unassigned")
        if self.evidence.candidate.label != self.candidate_summary.zh:
            raise ValueError("discovery evidence label does not match candidate summary")
        expected_url = analyze_url_for_candidate(
            a_id=a_id,
            b_id=b_id,
            discovery_id=expected_id,
            contract_version=self.schema_version,
        )
        if self.analyze_url != expected_url:
            raise ValueError("discovery analyze URL does not preserve candidate identity")
        has_equation = bool(self.candidate_equations)
        has_mapping = bool(self.candidate_variable_mapping)
        expected_language = "zh_only" if has_equation or has_mapping else "not_recorded"
        if self.evidence_language != expected_language:
            raise ValueError("discovery evidence language does not match public structure fields")
        blockers = self.readiness.blockers
        expected_blockers = (
            ([] if has_equation else ["candidate_equation"])
            + ([] if has_mapping else ["variable_mapping"])
            + [
                "source_review",
                "dataset_record",
                "primary_metric",
                "preregistered_stop_rule",
            ]
        )
        if blockers != expected_blockers:
            raise ValueError("discovery readiness blockers do not match public readiness")
        gap_ids = [gap.gap_id for gap in self.validation_plan.validation_gaps]
        fixed_gaps = [
            "source_support_not_reviewed",
            "competing_explanations_not_tested",
            "dataset_and_sampling_not_recorded",
            "baseline_and_stop_rule_not_preregistered",
        ]
        expected_gaps = [
            fixed_gaps[0],
            "candidate_equation_not_expert_reviewed" if has_equation else "candidate_equation_not_recorded",
            "variable_mapping_not_expert_reviewed" if has_mapping else "variable_mapping_not_recorded",
            *fixed_gaps[1:],
        ]
        if gap_ids != expected_gaps:
            raise ValueError("discovery validation gaps do not match structure readiness")
        counterexamples = self.evidence.counterexamples
        if self.tier == "priority_review":
            expected_summary = "；".join(gap.label.zh for gap in self.validation_plan.validation_gaps)
            if counterexamples.status != "gap_recorded" or counterexamples.summary != expected_summary:
                raise ValueError("priority discovery counterexample gaps do not match validation plan")
        elif counterexamples.status != "not_recorded" or counterexamples.summary is not None:
            raise ValueError("candidate-pool counterexamples must remain unrecorded")
        return self


class DiscoveryStats(BaseModel):
    total_candidates: int = Field(..., ge=0)
    priority_review: int = Field(..., ge=0)
    candidate_pool: int = Field(..., ge=0)
    candidate_families: int = Field(..., ge=0)
    source_backed: int = Field(..., ge=0)
    ready_for_preregistration: int = Field(..., ge=0)

    model_config = {"extra": "forbid"}


class DiscoveriesResponse(BaseModel):
    """GET /api/discoveries — bounded, fail-closed candidate queue."""

    count: int = Field(..., ge=0)
    discoveries: List[DiscoveryCandidate] = Field(default_factory=list)
    tier2_count: int = Field(..., ge=0)
    tier2: List[DiscoveryCandidate] = Field(default_factory=list)
    stats: DiscoveryStats

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_response_consistency(self) -> "DiscoveriesResponse":
        if self.count != len(self.discoveries) or self.tier2_count != len(self.tier2):
            raise ValueError("discovery response counts do not match rows")
        all_rows = self.discoveries + self.tier2
        if any(row.tier != "priority_review" for row in self.discoveries):
            raise ValueError("priority discovery list contains the wrong tier")
        if any(row.tier != "candidate_pool" for row in self.tier2):
            raise ValueError("candidate pool contains the wrong tier")
        if len({row.discovery_id for row in all_rows}) != len(all_rows):
            raise ValueError("discovery ids must be unique")
        if len({row.rank for row in self.discoveries}) != len(self.discoveries):
            raise ValueError("priority discovery ranks must be unique")
        if len({row.rank for row in self.tier2}) != len(self.tier2):
            raise ValueError("candidate-pool discovery ranks must be unique")
        family_sizes: Dict[str, int] = {}
        for row in all_rows:
            family_sizes[row.candidate_family_id] = family_sizes.get(row.candidate_family_id, 0) + 1
        if any(row.family_variant_count != family_sizes[row.candidate_family_id] for row in all_rows):
            raise ValueError("discovery family variant counts do not match assigned rows")
        expected = {
            "total_candidates": len(all_rows),
            "priority_review": len(self.discoveries),
            "candidate_pool": len(self.tier2),
            "candidate_families": len({row.candidate_family_id for row in all_rows}),
            "source_backed": 0,
            "ready_for_preregistration": 0,
        }
        if self.stats.model_dump() != expected:
            raise ValueError("discovery response stats do not match rows")
        return self


class DailyResponse(BaseModel):
    """GET /api/daily — a strict preview of the public candidate queue."""

    date: str  # ISO-8601 date
    lang: Literal["zh", "en"]
    discoveries: List[DiscoveryCandidate] = Field(..., min_length=3, max_length=3)

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_daily_candidates(self) -> "DailyResponse":
        try:
            parsed = calendar_date.fromisoformat(self.date)
        except ValueError as exc:
            raise ValueError("daily date must be ISO-8601") from exc
        if parsed.isoformat() != self.date:
            raise ValueError("daily date must be a calendar date")
        if len({row.discovery_id for row in self.discoveries}) != 3:
            raise ValueError("daily candidate ids must be unique")
        return self


class FlagsResponse(BaseModel):
    """GET /api/flags — resolved feature flags + experiment variants."""

    flags: Dict[str, Any] = Field(default_factory=dict)
    experiments: Dict[str, Any] = Field(default_factory=dict)
    variants: Dict[str, str] = Field(default_factory=dict)

    model_config = {"extra": "allow"}


__all__ = [
    # ask
    "AskRequest",
    "AskMeta",
    "KBCard",
    "AnswerDone",
    "Verdict",
    # checkout
    "CheckoutBody",
    "CheckoutResponse",
    # history
    "HistoryRecordRequest",
    "HistoryRecord",
    "HistoryResponse",
    # search
    "SearchRequest",
    "AssessRequest",
    "SearchResult",
    "SearchResponse",
    # mapping
    "MappingRequest",
    "MappingStreamRequest",
    "CandidateMapping",
    "MappingResponse",
    # phenomenon
    "PhenomenonResponse",
    # errors
    "ErrorReportBody",
    "ProblemDetailEnvelope",
    # synthesize
    "SynthesizeRequest",
    # newsletter
    "SubscribeBody",
    # privacy
    "CookieConsent",
    "PrivacyExportRequest",
    "PrivacyExportData",
    "PrivacyExportResponse",
    "PrivacyDeleteRequest",
    "PrivacyRemovalCounts",
    "PrivacyDeleteResponse",
    # screener
    "Company",
    "CompaniesResponse",
    "Phase",
    "PhasesResponse",
    # system + filled-in W17 typed responses
    "HealthResponse",
    "VersionResponse",
    "WhoAmIResponse",
    "ExamplesResponse",
    "NewsletterCountResponse",
    "ErrorAcceptedResponse",
    "DiscoveriesResponse",
    "DailyResponse",
    "FlagsResponse",
]
