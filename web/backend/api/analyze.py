"""POST /api/analyze/stream — 深度跨学科迁移研究报告（SSE 流式）

支持两种模式：
1. Query mode: text_a (用户的原始问题) + b_id (KB 中的目标现象)
   → 语义：从 KB 借用答案到用户的问题
   → 内部：KB 作为 SOURCE (a)，用户问题作为 TARGET (b)
2. Pair mode: a_id + b_id (两个 KB 现象)
   → 语义：两个已知现象的深度对比
"""
import hashlib
import hmac
import json as _json
import os
import secrets
from pathlib import Path
from typing import Annotated, Literal, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
else:
    from logging_config import get_logger, new_incident_id

if __package__ == "web.backend.api":
    from ..services.ask_orchestrator import ASK_MODEL
    from ..services.auth import verify_api_token
    from ..services.cache import MappingCache
    from ..services.candidate_origin import (
        SCHEMA_VERSION,
        build_origin_candidate,
        normalize_discovery_id,
    )
    from ..services.llm_service import LLMService
    from ..services.input_limits import MAX_RESEARCH_QUERY_CHARS
    from ..services.input_limits import normalize_research_text
    from ..services.deep_report import (
        DeepAnalysisReportV2,
        GeneratedDeepReportV2,
        SourceBinding,
        SourceRef,
        bind_deep_report,
        validate_bound_deep_report,
        validate_generated_deep_report_value,
    )
    from ..services.rate_limit import tier_limit_decorator
    from ..services.report_store import ReportStore
else:
    from services.ask_orchestrator import ASK_MODEL
    from services.auth import verify_api_token
    from services.cache import MappingCache
    from services.candidate_origin import (
        SCHEMA_VERSION,
        build_origin_candidate,
        normalize_discovery_id,
    )
    from services.llm_service import LLMService
    from services.input_limits import MAX_RESEARCH_QUERY_CHARS
    from services.input_limits import normalize_research_text
    from services.deep_report import (
        DeepAnalysisReportV2,
        GeneratedDeepReportV2,
        SourceBinding,
        SourceRef,
        bind_deep_report,
        validate_bound_deep_report,
        validate_generated_deep_report_value,
    )
    from services.rate_limit import tier_limit_decorator
    from services.report_store import ReportStore

logger = get_logger("structural.analyze")
router = APIRouter(tags=["analyze"])

_cache: Optional[MappingCache] = None
_llm: Optional[LLMService] = None
_report_store: Optional[ReportStore] = None

_ENTITY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,119}$"
_DISCOVERY_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_FingerprintItem = Annotated[StrictStr, Field(min_length=1, max_length=120)]
_REPORT_SECTION_KEYS = (
    "shared_structure",
    "your_problem_breakdown",
    "target_domain_intro",
    "structural_mapping",
    "borrowable_insights",
    "how_to_combine",
    "research_directions",
    "risks_and_limits",
    "action_plan",
)
_DEEP_CACHE_SCHEMA = "deep-analysis-report-v2-deep-report-v2"
_DEEP_LLM_ERROR_CODES = frozenset({
    "provider_auth_failed",
    "provider_rate_limited",
    "provider_request_rejected",
    "provider_unavailable",
    "report_validation_failed",
    "report_unavailable",
    "upstream_error",
    "upstream_timeout",
    "upstream_unreachable",
})


def _canonical_text(value: str, *, field: str, allow_layout: bool = True) -> str:
    """NFKC-normalize user text and reject invisible/unsafe controls."""
    return normalize_research_text(
        value,
        max_chars=MAX_RESEARCH_QUERY_CHARS,
        allow_layout=allow_layout,
        field_name=field,
    )


class AnalyzeFingerprint(BaseModel):
    """User-confirmed structure, bound to exactly one source question."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_query: StrictStr = Field(
        min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    summary: StrictStr = Field(min_length=8, max_length=1000)
    variables: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    constraints: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    unknowns: list[_FingerprintItem] = Field(default_factory=list, max_length=12)
    revision: StrictInt = Field(default=1, ge=1, le=1000)

    @field_validator("source_query")
    @classmethod
    def _validate_source_query(cls, value: str) -> str:
        normalized = _canonical_text(value, field="fingerprint.source_query")
        if not normalized or len(normalized) > MAX_RESEARCH_QUERY_CHARS:
            raise ValueError(
                "fingerprint.source_query must be "
                f"1-{MAX_RESEARCH_QUERY_CHARS} characters"
            )
        return normalized

    @field_validator("summary")
    @classmethod
    def _validate_summary(cls, value: str) -> str:
        normalized = _canonical_text(value, field="fingerprint.summary")
        if not 8 <= len(normalized) <= 1000:
            raise ValueError("fingerprint.summary must be 8-1000 characters")
        return normalized

    @field_validator("variables", "constraints", "unknowns")
    @classmethod
    def _validate_items(cls, values: list[str], info) -> list[str]:
        cleaned: list[str] = []
        for item in values:
            normalized = _canonical_text(
                item,
                field=f"fingerprint.{info.field_name}",
                allow_layout=False,
            )
            if not normalized or len(normalized) > 120:
                raise ValueError(
                    f"fingerprint.{info.field_name} items must be 1-120 characters"
                )
            cleaned.append(normalized)
        return cleaned


class AnalyzeStreamRequest(BaseModel):
    """Sensitive analysis inputs; this model is accepted only in a POST body."""

    model_config = ConfigDict(extra="forbid", strict=True)

    b_id: StrictStr = Field(pattern=_ENTITY_ID_PATTERN)
    a_id: Optional[StrictStr] = Field(default=None, pattern=_ENTITY_ID_PATTERN)
    text_a: Optional[StrictStr] = Field(
        default=None, min_length=1, max_length=MAX_RESEARCH_QUERY_CHARS
    )
    lang: Literal["zh", "en"] = "zh"
    persist: StrictInt = Field(default=0, ge=0, le=1)
    anon_id: Optional[StrictStr] = Field(default=None, min_length=1, max_length=128)
    fingerprint: Optional[AnalyzeFingerprint] = None
    origin_discovery_id: Optional[StrictStr] = Field(
        default=None,
        pattern=_DISCOVERY_ID_PATTERN,
    )
    origin_contract_version: Optional[StrictStr] = Field(
        default=None,
        pattern=_DISCOVERY_ID_PATTERN,
    )

    @field_validator("text_a")
    @classmethod
    def _validate_text_a(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _canonical_text(value, field="text_a")
        if not normalized or len(normalized) > MAX_RESEARCH_QUERY_CHARS:
            raise ValueError(
                f"text_a must be 1-{MAX_RESEARCH_QUERY_CHARS} characters"
            )
        return normalized

    @field_validator("anon_id")
    @classmethod
    def _validate_anon_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _canonical_text(value, field="anon_id", allow_layout=False)
        if not normalized or len(normalized) > 128:
            raise ValueError("anon_id must be 1-128 characters")
        return normalized

    @model_validator(mode="after")
    def _validate_mode(self):
        if (self.text_a is None) == (self.a_id is None):
            raise ValueError("provide exactly one of text_a or a_id")
        if self.a_id is not None and self.a_id == self.b_id:
            raise ValueError("a_id must differ from b_id")
        if self.fingerprint is not None:
            if self.text_a is None:
                raise ValueError("fingerprint is only valid in query mode")
            if self.fingerprint.source_query != self.text_a:
                raise ValueError("fingerprint does not match text_a")
        if (self.origin_discovery_id is None) != (
            self.origin_contract_version is None
        ):
            raise ValueError("discovery origin fields must be provided together")
        return self


def _resolve_origin_candidate(
    origin_discovery_id: Optional[str],
    origin_contract_version: Optional[str],
    *,
    a_id: Optional[str],
    b_id: str,
    is_query_mode: bool,
) -> Optional[dict]:
    """Bind a discovery deep link to the exact current public candidate.

    The pair and contract are validated again on the server; URL parameters
    alone are never accepted as provenance.  Reports may retain this stable
    identity, but user outcomes never mutate or upgrade the source candidate.
    """
    raw_id = origin_discovery_id or ""
    raw_contract = origin_contract_version or ""
    candidate_id = raw_id.strip()
    contract_version = raw_contract.strip()
    if not candidate_id and not contract_version:
        return None
    if (
        candidate_id != raw_id
        or contract_version != raw_contract
        or not candidate_id
        or not contract_version
        or normalize_discovery_id(candidate_id) is None
    ):
        raise HTTPException(400, "Invalid discovery origin")

    if contract_version != SCHEMA_VERSION:
        raise HTTPException(409, "Discovery contract version is no longer current")
    if is_query_mode or not a_id:
        raise HTTPException(409, "Discovery origin requires its bound KB pair")

    if __package__ == "web.backend.api":
        from . import discoveries as discoveries_api
    else:
        from api import discoveries as discoveries_api

    payload = discoveries_api.build_public_discoveries()
    candidates = [*payload["discoveries"], *payload["tier2"]]
    candidate = next(
        (row for row in candidates if row["discovery_id"] == candidate_id),
        None,
    )
    if candidate is None:
        raise HTTPException(409, "Discovery candidate is no longer available")
    pair = candidate["pair"]
    if pair["a"]["id"] != a_id or pair["b"]["id"] != b_id:
        raise HTTPException(409, "Discovery candidate does not match the requested pair")
    origin = build_origin_candidate(
        discovery_id=candidate["discovery_id"],
        contract_version=candidate["schema_version"],
        candidate_family_id=candidate["candidate_family_id"],
        tier=candidate["tier"],
        a_id=pair["a"]["id"],
        b_id=pair["b"]["id"],
    )
    if origin is None:
        logger.error(
            "analyze.candidate_origin_failed",
            incident_id=new_incident_id(),
        )
        raise HTTPException(500, "Discovery origin is unavailable")
    return origin


def _build_share_url(request: Request, report_id: str, token: str) -> str:
    """Return a share URL without trusting client-controlled origin headers."""
    del report_id  # The public capability path is token-addressed.
    path = f"/report/share/{token}"
    if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
        return f"https://beta.structural.bytedance.city{path}"

    parsed = urlsplit(str(request.base_url))
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1", "testserver"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        return path
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def _init():
    global _cache, _llm, _report_store
    if _cache is None:
        cache_path = Path(__file__).parent.parent.parent / "data" / "analysis_cache.jsonl"
        _cache = MappingCache(
            cache_path,
            schema_version=_DEEP_CACHE_SCHEMA,
            validator=lambda value: DeepAnalysisReportV2.model_validate(value).model_dump(
                mode="json"
            ),
        )
    if _llm is None:
        _llm = LLMService()
    if _report_store is None:
        # Reuse the existing history.db file so we don't fragment storage.
        # Path matches services/history_db.py initialiser in main.py lifespan.
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _report_store = ReportStore(db_path)


def _fingerprint_payload(value: Optional[AnalyzeFingerprint]) -> Optional[dict]:
    """Project the validated request model into the persisted public shape."""
    if value is None:
        return None
    return {
        "summary": value.summary,
        "variables": list(value.variables),
        "constraints": list(value.constraints),
        "unknowns": list(value.unknowns),
        "revision": value.revision,
        "provenance": "user_confirmed",
    }


def _parse_fingerprint(raw: Optional[str], expected_query: Optional[str]) -> Optional[dict]:
    """Compatibility helper for focused unit tests; HTTP accepts typed JSON."""
    if not raw:
        return None
    try:
        parsed = AnalyzeFingerprint.model_validate_json(raw, strict=True)
        expected = _canonical_text(expected_query or "", field="text_a")
        if parsed.source_query != expected:
            raise ValueError("fingerprint does not match text_a")
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Invalid fingerprint") from exc
    return _fingerprint_payload(parsed)


def _canonical_digest(value: object) -> str:
    payload = _json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _binding_secret() -> bytes:
    """Derive a domain-separated query-binding key from a private root."""
    value = os.getenv("STRUCTURAL_SHARE_TOKEN_SECRET", "")
    env = os.getenv("STRUCTURAL_ENV", "dev").lower()
    weak_markers = ("replace", "example", "changeme", "placeholder")
    if env == "prod" and (
        len(value) < 32 or any(marker in value.lower() for marker in weak_markers)
    ):
        raise RuntimeError("private query-binding root is unavailable in production")
    if not value:
        value = f"deep-report-dev-only:{Path.cwd()}"
    return hmac.new(
        value.encode("utf-8"),
        b"structural:deep-report-query-binding:v2",
        hashlib.sha256,
    ).digest()


def _query_binding(query: str, *, b_id: str, lang: str) -> str:
    payload = _json.dumps(
        {"query": query, "b_id": b_id, "lang": lang},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(_binding_secret(), payload, hashlib.sha256).hexdigest()


def _archive_record(record: dict) -> dict:
    """Freeze only the source fields covered by the canonical record digest."""
    return {
        key: record.get(key)
        for key in ("id", "name", "domain", "type_id", "description")
    }


def _persisted_report_receipt(
    *,
    query: str,
    b_id: str,
    lang: str,
    model: str,
    prompt_version: str,
    payload: dict,
) -> str:
    """Authenticate one immutable report archive independently of current KB.

    Persisted reports are historical research artifacts, not cache entries.
    The domain-separated HMAC lets a later read validate the exact generated
    report, source snapshots, provenance and row bindings after the live KB
    advances, while any edited or legacy unsigned v2 row fails closed.
    """
    message = _json.dumps(
        {
            "b_id": b_id,
            "lang": lang,
            "model": model,
            "payload": payload,
            "prompt_version": prompt_version,
            "query": query,
            "version": "persisted-deep-report-v2",
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    receipt_key = hmac.new(
        _binding_secret(),
        b"structural:persisted-deep-report:v2",
        hashlib.sha256,
    ).digest()
    return hmac.new(receipt_key, message, hashlib.sha256).hexdigest()


def _record_digest(record: dict) -> str:
    return _canonical_digest({
        key: record.get(key)
        for key in ("id", "name", "domain", "type_id", "description")
    })


def _cache_identity(
    *,
    source_record_sha256: str,
    target_record_sha256: str,
    artifact_id: str,
    model_id: str,
) -> str:
    return "pair_" + _canonical_digest({
        "schema": "deep-analysis-report-v2",
        "prompt": "deep-report-v2",
        "source": source_record_sha256,
        "target": target_record_sha256,
        "artifact": artifact_id,
        "model": model_id,
    })


def _source_ref(record: dict, *, lang: str, target: bool = False) -> SourceRef:
    label = str(record.get("name") or record.get("id") or "Internal KB record")[:240]
    if lang == "en":
        limitation = (
            "Internal candidate record only; it does not establish mechanism, "
            "causality, transfer success, or independent review."
        )
    else:
        limitation = "仅为内部候选记录；不证明机制、因果、迁移有效或独立复核。"
    if target:
        limitation = (
            "Internal target record used only for comparison; it does not show that the mechanisms are the same."
            if lang == "en"
            else "仅作为比较目标的内部记录；不能据此判断两边机制相同。"
        )
    return SourceRef(
        source_ref_id=f"kb:{record['id']}",
        source_kind="internal_kb",
        record_id=str(record["id"]),
        label=label,
        limitations=limitation,
    )


@router.get("/analyze/stream", include_in_schema=False)
async def retired_analyze_stream_get():
    """Retire the URL-bearing transport without ever parsing its query string."""
    return JSONResponse(
        status_code=410,
        content={
            "error": "sensitive_get_retired",
            "message": "Use POST /api/analyze/stream with a JSON body.",
        },
        headers={"Cache-Control": "no-store"},
    )


def _analyze_sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"


def _analyze_stream_response(generator) -> StreamingResponse:
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _terminal_error_response(*, code: str, message: str, retryable: bool):
    async def events():
        # `error` is the single terminal event.  Emitting a later `done` would
        # let clients accidentally treat a failed generation as completed.
        yield _analyze_sse("error", {
            "code": code,
            "message": message,
            "retryable": retryable,
        })

    return _analyze_stream_response(events())


async def _stream_analyze_v2(
    request: Request,
    req: AnalyzeStreamRequest,
) -> StreamingResponse:
    """Generate a source-bound report with validation-before-display."""
    tier = verify_api_token(request)
    if tier is None:
        raise HTTPException(401, "Invalid API token")

    from main import app_state

    svc = app_state.get("search")
    if not svc:
        raise HTTPException(503, "Search service not ready")

    lang = req.lang
    text_a = req.text_a
    # Raw scope classification runs before KB lookup, retrieval, cache init or
    # any LLM call.  This is the cheapest and least leaky rejection boundary.
    if text_a is not None:
        if __package__ == "web.backend.api":
            from ..services.scope_guard import is_out_of_scope
        else:
            from services.scope_guard import is_out_of_scope
        out_of_scope, _reason = is_out_of_scope(text_a)
        if out_of_scope:
            logger.info("analyze.raw_scope_refused")
            return _terminal_error_response(
                code="out_of_scope",
                message=(
                    "This request is outside the cross-domain research workflow. "
                    "Try a question with variables, constraints, and an observable outcome."
                    if lang == "en"
                    else "这个请求不适合跨领域研究流程。请改写为包含变量、约束和可观察结果的问题。"
                ),
                retryable=False,
            )

    _init()
    raw_b = svc.get_by_id(req.b_id)
    if not raw_b:
        raise HTTPException(404, "Phenomenon not found")

    artifact_id = str((app_state.get("artifact") or {}).get("artifact_id") or "")
    if not artifact_id:
        if os.getenv("STRUCTURAL_ENV", "dev").lower() == "prod":
            raise HTTPException(503, "Verified knowledge artifact is unavailable")
        artifact_id = "unverified-dev-artifact"

    model_id = str(getattr(_llm, "model", None) or ASK_MODEL)
    user_query: Optional[str] = None
    raw_target: Optional[dict] = None

    if text_a is not None:
        user_query = text_a
        source_record = raw_b
        # The selected KB row is a candidate source; the raw user question is
        # the target.  No preliminary model rewrite is allowed to alter it.
        source = dict(source_record)
        target = {
            "id": "__query__",
            "name": text_a[:60] + ("..." if len(text_a) > 60 else ""),
            "domain": "Your question" if lang == "en" else "你的问题",
            "type_id": "unknown",
            "description": text_a,
            "original_query": text_a,
        }
        signal = svc.relevance_score(text_a, req.b_id)
        try:
            floor = float(os.getenv("ANALYZE_SCOPE_MIN_SIMILARITY", "0.50"))
        except ValueError as exc:
            raise RuntimeError("invalid ANALYZE_SCOPE_MIN_SIMILARITY") from exc
        if not 0.0 <= floor <= 1.0:
            raise RuntimeError("ANALYZE_SCOPE_MIN_SIMILARITY must be within [0,1]")
        if not isinstance(signal, (int, float)) or not 0.0 <= float(signal) <= 1.0:
            logger.warning("analyze.invalid_retrieval_signal")
            signal = 0.0
        if float(signal) < floor:
            return _terminal_error_response(
                code="candidate_not_supported",
                message=(
                    "The selected candidate is too weak to support a report. "
                    "Return to the candidates and choose another lead."
                    if lang == "en"
                    else "当前候选不足以支撑研究草案。请返回候选列表并选择另一条线索。"
                ),
                retryable=False,
            )
    else:
        assert req.a_id is not None
        raw_a = svc.get_by_id(req.a_id)
        if not raw_a:
            raise HTTPException(404, "Phenomenon A not found")
        source_record = raw_a
        raw_target = raw_b
        source = dict(source_record)
        target = dict(raw_target)

    origin_candidate = _resolve_origin_candidate(
        req.origin_discovery_id,
        req.origin_contract_version,
        a_id=req.a_id,
        b_id=req.b_id,
        is_query_mode=user_query is not None,
    )
    confirmed_fingerprint = _fingerprint_payload(req.fingerprint)
    source_refs = [_source_ref(source_record, lang=lang)]
    if raw_target is not None:
        source_refs.append(_source_ref(raw_target, lang=lang, target=True))

    source_record_sha = _record_digest(source_record)
    fingerprint_sha = (
        _canonical_digest(confirmed_fingerprint)
        if confirmed_fingerprint is not None
        else None
    )
    try:
        source_binding = SourceBinding(
            source_kb_id=str(source_record["id"]),
            source_record_sha256=source_record_sha,
            kb_artifact_id=artifact_id,
            target_kind="query" if user_query is not None else "kb",
            target_kb_id=None if user_query is not None else str(raw_target["id"]),
            query_binding=(
                _query_binding(user_query, b_id=req.b_id, lang=lang)
                if user_query is not None
                else None
            ),
            fingerprint_sha256=fingerprint_sha,
            fingerprint_revision=(
                confirmed_fingerprint["revision"]
                if confirmed_fingerprint is not None
                else None
            ),
            lang=lang,
            model_id=model_id,
            prompt_version="deep-report-v2",
            schema_version="deep-analysis-report-v2",
        )
    except (KeyError, RuntimeError, ValueError) as exc:
        logger.error(
            "analyze.source_binding_unavailable",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        raise HTTPException(503, "Report provenance binding is unavailable") from exc

    if __package__ == "web.backend.api":
        from ..services.evidence_envelope import build_evidence_envelope
    else:
        from services.evidence_envelope import build_evidence_envelope
    evidence = build_evidence_envelope(
        candidate_kind="analysis_candidate",
        candidate_label=str(source.get("name") or "") or None,
        candidate_score=None,
        requested_level="candidate",
        source_kind="internal_kb",
        source_label="Structural internal KB candidate",
        result_provenance="NOT_TESTED",
        result_verdict="NOT_TESTED",
        independence_kind="not_recorded",
        counterexample_status="gap_recorded",
        counterexample_summary=(
            "The report must propose falsifiers; no completed falsification result is bound."
            if lang == "en"
            else "报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。"
        ),
    )
    boundary = {
        "conclusion_status": "candidate_analogy",
        "mechanism_status": "not_verified",
        "independent_review": "not_recorded",
        "literature_status": "not_checked",
    }

    pair_cache_id: Optional[str] = None
    if raw_target is not None:
        pair_cache_id = _cache_identity(
            source_record_sha256=source_record_sha,
            target_record_sha256=_record_digest(raw_target),
            artifact_id=artifact_id,
            model_id=model_id,
        )

    creator_tier = tier if isinstance(tier, str) else None

    def persist_report(
        report: dict,
        *,
        generation_id: str,
        report_sha256: str,
    ) -> Optional[dict]:
        if req.persist != 1:
            return None
        try:
            row_query = user_query or ""
            prompt_version = "deep-report-v2"
            sealed_payload = {
                **report,
                "_report_sha256": report_sha256,
                "_source_record": _archive_record(source_record),
                **(
                    {"_target_record": _archive_record(raw_target)}
                    if raw_target is not None else {}
                ),
                "_evidence": evidence,
                **({"_fingerprint": confirmed_fingerprint} if confirmed_fingerprint else {}),
                **({"_origin_candidate": origin_candidate} if origin_candidate else {}),
                "_source": {
                    "id": source.get("id"),
                    "name": source.get("name"),
                    "domain": source.get("domain"),
                    "type_id": source.get("type_id"),
                },
            }
            receipt = _persisted_report_receipt(
                query=row_query,
                b_id=req.b_id,
                lang=lang,
                model=model_id,
                prompt_version=prompt_version,
                payload=sealed_payload,
            )
            out = _report_store.create(
                query=row_query,
                rewritten_query=None,
                b_id=req.b_id,
                lang=lang,
                payload={**sealed_payload, "_report_receipt": receipt},
                model=model_id,
                prompt_version=prompt_version,
                creator_anon_id=req.anon_id,
                creator_tier=creator_tier,
                is_partial=False,
            )
            return {
                "id": out["id"],
                "share_url": _build_share_url(request, out["id"], out["share_token"]),
                "created_at": out["created_at"],
                "is_partial": False,
                "origin_candidate": origin_candidate,
                "generation_id": generation_id,
                "report_sha256": report_sha256,
            }
        except Exception as exc:
            logger.error(
                "analyze.persist_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
            return None

    async def events():
        generation_id = "g_" + secrets.token_hex(12)
        yield _analyze_sse("meta", {
            "generation_id": generation_id,
            "a": source,
            "b": target,
            "is_query_mode": user_query is not None,
            "evidence": evidence,
            "fingerprint": confirmed_fingerprint,
            "model": model_id,
            "lang": lang,
            "artifact_id": artifact_id,
            "prompt_version": "deep-report-v2",
            "schema_version": "deep-analysis-report-v2",
            "report_boundary": boundary,
            "source_binding": source_binding.model_dump(mode="json"),
            "source_refs": [item.model_dump(mode="json") for item in source_refs],
            "origin_candidate": origin_candidate,
        })

        # Query reports never touch the durable generation cache.  Pair-mode
        # rows contain public KB ids only and are revalidated against the exact
        # artifact/model/source binding before release.
        if pair_cache_id is not None:
            cached = _cache.get(pair_cache_id, req.b_id, lang=lang)
            if cached is not None:
                try:
                    cached_model = validate_bound_deep_report(
                        cached,
                        expected_source_binding=source_binding,
                        expected_source_refs=source_refs,
                        expected_source_record=source_record,
                    )
                    report = cached_model.model_dump(mode="json")
                    report_sha = _canonical_digest(report)
                    yield _analyze_sse("report_validated", {
                        "generation_id": generation_id,
                        "report_sha256": report_sha,
                        "schema_version": "deep-analysis-report-v2",
                        "from_cache": True,
                    })
                    for key in _REPORT_SECTION_KEYS:
                        yield _analyze_sse("section", {"key": key, "data": report[key]})
                    persisted = persist_report(
                        report,
                        generation_id=generation_id,
                        report_sha256=report_sha,
                    )
                    if persisted is not None:
                        yield _analyze_sse("persisted", persisted)
                    yield _analyze_sse("done", {
                        "generation_id": generation_id,
                        "report_sha256": report_sha,
                        "report": report,
                        "from_cache": True,
                    })
                    return
                except Exception as exc:
                    logger.warning(
                        "analyze.cache_row_rejected",
                        error_type=type(exc).__name__,
                        incident_id=new_incident_id(),
                    )

        generated: Optional[GeneratedDeepReportV2] = None
        last_code = "report_unavailable"
        last_retryable = True
        for attempt in (1, 2):
            if __package__ == "web.backend.api":
                from ..services.cost_ledger import ledger as cost_ledger
                from ..errors import BudgetExceeded
            else:
                from services.cost_ledger import ledger as cost_ledger
                from errors import BudgetExceeded
            try:
                cost_ledger.charge(endpoint="/api/analyze/stream")
            except BudgetExceeded as exc:
                yield _analyze_sse("error", {
                    "code": "budget_exceeded",
                    "message": str(exc.detail),
                    "retryable": False,
                })
                return

            yield _analyze_sse("generation_progress", {
                "stage": "generating" if attempt == 1 else "retrying",
                "attempt": attempt,
            })
            report_payload = None
            terminal_type: Optional[str] = None
            protocol_failed = False
            last_progress_chars = 0
            try:
                async for chunk in _llm.stream_deep_analysis(
                    source,
                    target,
                    source_refs=source_refs,
                    fingerprint=confirmed_fingerprint,
                    lang=lang,
                ):
                    if not isinstance(chunk, dict) or terminal_type is not None:
                        protocol_failed = True
                        break
                    chunk_type = chunk.get("type")
                    if chunk_type == "progress":
                        received_chars = chunk.get("received_chars")
                        if (
                            type(received_chars) is not int
                            or not last_progress_chars <= received_chars <= 96_000
                        ):
                            protocol_failed = True
                            break
                        last_progress_chars = received_chars
                        yield _analyze_sse("generation_progress", {
                            "stage": "validating",
                            "attempt": attempt,
                            "received_chars": received_chars,
                        })
                    elif chunk_type == "done":
                        terminal_type = "done"
                        report_payload = chunk.get("report")
                    elif chunk_type == "error":
                        code = chunk.get("code")
                        retryable = chunk.get("retryable")
                        if (
                            code not in _DEEP_LLM_ERROR_CODES
                            or type(retryable) is not bool
                        ):
                            protocol_failed = True
                            break
                        terminal_type = "error"
                        last_code = code
                        last_retryable = retryable
                    else:
                        protocol_failed = True
                        break
            except Exception as exc:
                logger.error(
                    "analyze.llm_stream_failed",
                    error_type=type(exc).__name__,
                    incident_id=new_incident_id(),
                )
                if terminal_type is not None:
                    protocol_failed = True
                else:
                    terminal_type = "error"
                    last_code = "upstream_error"
                    last_retryable = True

            if protocol_failed or terminal_type is None:
                last_code = "report_protocol_failed"
                last_retryable = False
                logger.warning(
                    "analyze.llm_protocol_rejected",
                    incident_id=new_incident_id(),
                )
                break
            if terminal_type == "error":
                if not last_retryable:
                    break
                continue
            if report_payload is not None:
                try:
                    generated = validate_generated_deep_report_value(
                        report_payload,
                        allowed_source_ref_ids={
                            item.source_ref_id for item in source_refs
                        },
                        source_ref_id=source_refs[0].source_ref_id,
                        fingerprint_revision=source_binding.fingerprint_revision,
                        expected_lang=source_binding.lang,
                    )
                    break
                except Exception as exc:
                    last_code = "report_validation_failed"
                    last_retryable = True
                    logger.warning(
                        "analyze.generated_report_rejected",
                        error_type=type(exc).__name__,
                        incident_id=new_incident_id(),
                    )
            if not last_retryable:
                break

        if generated is None:
            yield _analyze_sse("error", {
                "code": last_code,
                "message": (
                    "The report did not pass evidence and source validation. No partial report was published."
                    if lang == "en"
                    else "研究草案未通过证据与来源校验，系统没有发布任何半成品。"
                ),
                "retryable": last_retryable,
            })
            return

        try:
            bound = bind_deep_report(
                generated,
                source_binding=source_binding,
                source_refs=source_refs,
                source_record=source_record,
            )
            report = bound.model_dump(mode="json")
        except Exception as exc:
            logger.error(
                "analyze.report_binding_failed",
                error_type=type(exc).__name__,
                incident_id=new_incident_id(),
            )
            yield _analyze_sse("error", {
                "code": "report_binding_failed",
                "message": (
                    "The report could not be bound to its source record."
                    if lang == "en"
                    else "研究草案无法绑定到来源记录，未发布正文。"
                ),
                "retryable": False,
            })
            return

        report_sha = _canonical_digest(report)
        yield _analyze_sse("report_validated", {
            "generation_id": generation_id,
            "report_sha256": report_sha,
            "schema_version": "deep-analysis-report-v2",
            "from_cache": False,
        })
        for key in _REPORT_SECTION_KEYS:
            yield _analyze_sse("section", {"key": key, "data": report[key]})
        persisted = persist_report(
            report,
            generation_id=generation_id,
            report_sha256=report_sha,
        )
        if persisted is not None:
            yield _analyze_sse("persisted", persisted)
        if pair_cache_id is not None:
            try:
                _cache.put(pair_cache_id, req.b_id, report, lang=lang)
            except Exception as exc:
                logger.warning(
                    "analyze.cache_write_failed",
                    error_type=type(exc).__name__,
                    incident_id=new_incident_id(),
                )
        yield _analyze_sse("done", {
            "generation_id": generation_id,
            "report_sha256": report_sha,
            "report": report,
            "from_cache": False,
        })

    return _analyze_stream_response(events())


@router.post(
    "/analyze/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "Content-free progress followed by one source-bound, fully "
                "validated report event sequence."
            ),
            "content": {
                "text/event-stream": {"schema": {"type": "string"}},
            },
        },
    },
)
@tier_limit_decorator(default_anon="10/minute")
async def stream_analyze(
    request: Request,
    req: AnalyzeStreamRequest,
):
    return await _stream_analyze_v2(request, req)
