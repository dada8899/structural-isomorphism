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

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


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
    """Mock-Stripe checkout body. `force_status` is a test-only override
    honoured for localhost callers only.
    """

    tier: str
    interval: str = "month"
    email: str
    name: Optional[str] = ""
    card_last4: Optional[str] = ""
    force_status: Optional[str] = None


class CheckoutResponse(BaseModel):
    """Response shape from POST /api/checkout/mock."""

    status: Literal["success", "declined", "error"]
    order_id: Optional[str] = None
    message: Optional[str] = None


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
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(12, ge=1, le=30)
    rewrite: bool = False
    lang: str = "zh"


class AssessRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500)
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
    a_id: str
    b_id: str
    lang: str = "zh"


# ---------------------------------------------------------------------------
# /api/error-log  (web/backend/api/error_log.py)
# ---------------------------------------------------------------------------
class ErrorReportBody(BaseModel):
    """Client-side error envelope. All optional fields are size-capped
    in the backend; mirrored here for the typed-frontend contract.
    """

    message: str = Field(..., min_length=1, max_length=4000)
    stack: Optional[str] = Field(default=None, max_length=20000)
    digest: Optional[str] = Field(default=None, max_length=500)
    url: Optional[str] = Field(default=None, max_length=2000)
    userAgent: Optional[str] = Field(default=None, max_length=500)
    timestamp: Optional[int] = None
    sessionId: Optional[str] = Field(default=None, max_length=128)
    fatal: Optional[bool] = False


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
    """Query params for GET /api/privacy/export. Phase 1 mock code = '123456'."""

    email: str
    code: str
    session_id: Optional[str] = None


class PrivacyExportResponse(BaseModel):
    """Self-service DSAR (data subject access request) bundle."""

    email: str
    generated_at: str
    newsletter: List[Dict[str, Any]] = Field(default_factory=list)
    checkouts: List[Dict[str, Any]] = Field(default_factory=list)
    error_log: List[Dict[str, Any]] = Field(default_factory=list)


class PrivacyDeleteRequest(BaseModel):
    """POST /api/privacy/delete — irreversible right-to-be-forgotten."""

    email: str
    code: str
    session_id: Optional[str] = None


class PrivacyDeleteResponse(BaseModel):
    """Counts of records removed across each store."""

    email: str
    newsletter_removed: int = 0
    checkouts_removed: int = 0
    error_log_removed: int = 0


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
    "PrivacyExportResponse",
    "PrivacyDeleteRequest",
    "PrivacyDeleteResponse",
    # screener
    "Company",
    "CompaniesResponse",
    "Phase",
    "PhasesResponse",
]
