"""GET /api/report/* — read persisted analyze reports (M1.4).

POST /api/report/{id}/feedback — section-level 👍/👎.

PRD: docs/sessions/M1.4-report-generator-prd.md
Companion: services/report_store.py
"""
from __future__ import annotations

import hmac
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError

if __package__ == "web.backend.api":
    from ..logging_config import get_logger, new_incident_id
    from ..services.candidate_origin import normalize_origin_candidate
    from ..services.deep_report import (
        DeepAnalysisReportV2,
        validate_bound_deep_report,
    )
    from ..services.report_store import ReportStore, verify_share_token
    from .sso import resolve_beta_user
else:
    from logging_config import get_logger, new_incident_id
    from services.candidate_origin import normalize_origin_candidate
    from services.deep_report import DeepAnalysisReportV2, validate_bound_deep_report
    from services.report_store import ReportStore, verify_share_token
    from api.sso import resolve_beta_user

logger = get_logger("structural.report")
router = APIRouter(tags=["report"])

_store: Optional[ReportStore] = None


def _get_store() -> ReportStore:
    global _store
    if _store is None:
        # Reuse history.db (same file as analyze.py / history_db.py).
        db_path = Path(__file__).parent.parent / "data" / "history.db"
        _store = ReportStore(db_path)
    return _store


# ---------------- response shapes ----------------------------------- #


class OriginCandidatePair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    a_id: str
    b_id: str


class OriginCandidateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discovery_id: str
    contract_version: Literal["discovery-candidate-v2"]
    candidate_family_id: str
    tier: Literal["priority_review", "candidate_pool"]
    pair: OriginCandidatePair
    origin_content_id: str = Field(pattern=r"^origin-[0-9a-f]{24}$")


class ReportDetailResponse(BaseModel):
    id: str
    query: str
    rewritten_query: Optional[str]
    b_id: str
    lang: str
    payload: dict
    model: str
    prompt_version: str
    created_at: str
    view_count: int
    is_partial: bool
    credibility: Optional[dict] = None
    fingerprint: Optional[dict] = None
    source: Optional[dict] = None
    evidence: Optional[dict] = None
    origin_candidate: Optional[OriginCandidateResponse] = None
    report_sha256: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    share_url: Optional[str] = None
    snapshot_status: Optional[Literal["current_artifact", "historical_snapshot"]] = None


class ReportListItem(BaseModel):
    id: str
    query: str
    b_id: str
    lang: str
    created_at: str
    view_count: int
    # B Data Flywheel (Session #18) — revisit status for the '未回访' badge.
    has_followup: bool = False
    followup_outcome: str = ""
    followup_status: str = ""
    experiment_status: str = ""
    experiment_deadline: Optional[str] = None
    origin_candidate: Optional[OriginCandidateResponse] = None


class ReportListResponse(BaseModel):
    items: list[ReportListItem]
    has_more: bool


class FeedbackRequest(BaseModel):
    section: Optional[str] = Field(
        None,
        description=(
            "Which 9-section key the vote applies to. None / omitted "
            "= overall vote on the report."
        ),
    )
    vote: int = Field(..., description="+1 (up) or -1 (down)")
    note: Optional[str] = Field(None, max_length=2000)


class FeedbackResponse(BaseModel):
    ok: bool
    total_up: int
    total_down: int


# Session #17 V6 — report → action → result revisit loop.
_ALLOWED_ACTION_STATUSES = {"planned", "in_progress", "tried", "abandoned"}
_ALLOWED_OUTCOMES = {"", "worked", "partial", "no_effect", "too_early"}


class ExperimentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypothesis: Optional[str] = Field(None, min_length=1, max_length=2000)
    owner: Optional[str] = Field(None, max_length=120)
    deadline: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    baseline: Optional[float] = None
    primary_metric: Optional[str] = Field(None, max_length=200)
    success_threshold: Optional[float] = None
    stop_condition: Optional[str] = Field(None, max_length=1000)
    status: str = Field("planned", pattern=r"^(planned|in_progress|completed|stopped|abandoned)$")
    notes: Optional[str] = Field(None, max_length=4000)


class OutcomeDetailInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actual_metric: Optional[float] = None
    result: Optional[str] = Field(
        None, pattern=r"^(success|partial|failure|inconclusive)$",
    )
    failure_reason: Optional[str] = Field(None, max_length=2000)
    learning: Optional[str] = Field(None, max_length=4000)
    next_decision: Optional[str] = Field(
        None, pattern=r"^(iterate|scale|stop|retest)$",
    )


class FollowupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_status: str = Field(
        ...,
        description=(
            "Where the user is with the report's action plan: "
            "planned | in_progress | tried | abandoned"
        ),
    )
    outcome: str = Field(
        "",
        description=(
            "Result so far (optional): '' (not reported) | worked | "
            "partial | no_effect | too_early"
        ),
    )
    note: Optional[str] = Field(None, max_length=2000)
    experiment: Optional[ExperimentInput] = None
    outcome_detail: Optional[OutcomeDetailInput] = None
    publish_to_insights: Optional[StrictBool] = Field(
        None,
        description=(
            "Versioned preference for a possible future public Insights "
            "aggregate. Public aggregation is currently paused. Omitted "
            "preserves the current choice; true records consent; false "
            "revokes it."
        ),
    )


class FollowupResponse(BaseModel):
    ok: bool
    report_id: str
    action_status: str
    outcome: str
    note: Optional[str]
    experiment: Optional[ExperimentInput] = None
    outcome_detail: Optional[OutcomeDetailInput] = None
    publish_to_insights: bool = False
    consent_version: Optional[str] = None
    consented_at: Optional[str] = None
    withdrawn_at: Optional[str] = None
    created_at: str
    updated_at: str


class StoredFollowupResponse(BaseModel):
    """Persisted follow-up as returned by the anonymous owner read API."""

    report_id: str
    anon_id: str
    action_status: str
    outcome: str
    note: Optional[str] = None
    experiment: Optional[dict[str, Any]] = None
    outcome_detail: Optional[dict[str, Any]] = None
    publish_to_insights: bool = False
    consent_version: Optional[str] = None
    consented_at: Optional[str] = None
    withdrawn_at: Optional[str] = None
    created_at: str
    updated_at: str


class FollowupReadResponse(BaseModel):
    followup: Optional[StoredFollowupResponse] = None


_ALLOWED_SECTIONS = {
    None,
    "shared_structure",
    "your_problem_breakdown",
    "target_domain_intro",
    "structural_mapping",
    "borrowable_insights",
    "how_to_combine",
    "research_directions",
    "risks_and_limits",
    "action_plan",
}


# ---------------- endpoints ----------------------------------------- #


_PUBLIC_CREDIBILITY_KEYS = {
    "kb_source",
    "similarity",
    "source_domain",
    "source_type_id",
    "has_verified_pairs",
    "verified_pair_count",
    "best_verified_pair",
}
_PUBLIC_PAIR_KEYS = {
    "other_name", "other_domain", "score", "similarity",
}
_EVIDENCE_LEVELS = {
    "candidate", "source_backed", "analysis_recorded",
    "falsification_tested", "externally_reviewed", "replicated",
}
# User outcomes are private workbench state. Every other provenance below is
# produced by the evidence-envelope schema and can be represented in a public
# share without guessing from prose. Unknown/missing provenance fails closed.
_PUBLIC_RESULT_PROVENANCE = {
    "NOT_TESTED",
    "INTERNAL_AI_SCREEN",
    "HUMAN_ANNOTATION",
    "SYNTHETIC_CONTROL",
    "INTERNAL_REAL_DATA",
    "EXTERNAL_REVIEW",
    "INDEPENDENT_REPLICATION",
}
_EVIDENCE_VERDICTS = {
    "PASS", "FAIL", "REJECT", "NULL", "PARTIAL", "INCONCLUSIVE",
    "NOT_TESTED",
}
_SOURCE_KINDS = {"not_recorded", "internal_kb", "external_source"}
_INDEPENDENCE_KINDS = {
    "not_recorded", "internal", "human_annotation", "external_review",
    "independent_team",
}
_COUNTEREXAMPLE_STATUSES = {
    "not_recorded", "gap_recorded", "searched", "found", "none_found",
}
_SHARE_NO_STORE_HEADERS = {
    "Cache-Control": "no-store",
    "Pragma": "no-cache",
}


def _public_text(value: Any, *, limit: int = 2000) -> tuple[bool, Optional[str]]:
    if value is None:
        return True, None
    if not isinstance(value, str) or len(value) > limit:
        return False, None
    return True, value


def _public_number(
    value: Any, *, minimum: float, maximum: float,
) -> tuple[bool, Optional[float]]:
    if value is None:
        return True, None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False, None
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        return False, None
    return True, result


def _public_https_url(value: Optional[str]) -> bool:
    if value is None:
        return True
    parsed = urlsplit(value)
    return bool(
        parsed.scheme == "https" and parsed.netloc
        and not parsed.username and not parsed.password
    )


def _public_iso_date(value: Optional[str]) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    if value[4] != "-" or value[7] != "-":
        return False
    if not (value[:4] + value[5:7] + value[8:]).isdigit():
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return parsed <= date.today()


def _project_public_pair(value: Any) -> tuple[bool, Optional[dict[str, Any]]]:
    if value is None:
        return True, None
    if not isinstance(value, dict):
        return False, None
    if not _PUBLIC_PAIR_KEYS <= set(value):
        return False, None
    projected: dict[str, Any] = {}
    for key in ("other_name", "other_domain"):
        if key not in value:
            continue
        valid, text = _public_text(value[key], limit=500)
        if not valid:
            return False, None
        projected[key] = text
    if "score" in value:
        valid, score = _public_number(value["score"], minimum=0, maximum=5)
        if not valid:
            return False, None
        projected["score"] = score
    if "similarity" in value:
        valid, similarity = _public_number(
            value["similarity"], minimum=0, maximum=1,
        )
        if not valid:
            return False, None
        projected["similarity"] = similarity
    # Unknown, camelCase and collection-valued fields never enter projection.
    return True, {key: projected[key] for key in _PUBLIC_PAIR_KEYS if key in projected}


def _project_public_credibility(value: Any) -> Optional[dict[str, Any]]:
    """Project the historical credibility snapshot through an exact schema.

    This intentionally does not classify natural-language prose. Scientific
    statements about human review, control or experiments are legitimate; the
    privacy boundary is the field schema and evidence provenance, not words.
    """
    if not isinstance(value, dict):
        return None
    projected: dict[str, Any] = {}
    for key in ("kb_source", "has_verified_pairs"):
        if key in value:
            if not isinstance(value[key], bool):
                return None
            projected[key] = value[key]
    if "similarity" in value:
        valid, similarity = _public_number(
            value["similarity"], minimum=0, maximum=1,
        )
        if not valid:
            return None
        projected["similarity"] = similarity
    for key in ("source_domain", "source_type_id"):
        if key in value:
            valid, text = _public_text(value[key], limit=500)
            if not valid:
                return None
            projected[key] = text
    if "verified_pair_count" in value:
        count = value["verified_pair_count"]
        if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 1_000_000:
            return None
        projected["verified_pair_count"] = count
    if "best_verified_pair" in value:
        valid, pair = _project_public_pair(value["best_verified_pair"])
        if not valid:
            return None
        projected["best_verified_pair"] = pair
    if (
        projected.get("has_verified_pairs") is False
        and projected.get("verified_pair_count", 0) != 0
    ):
        return None
    if (
        projected.get("has_verified_pairs") is False
        and projected.get("best_verified_pair") is not None
    ):
        return None
    if (
        projected.get("has_verified_pairs") is True
        and projected.get("verified_pair_count") == 0
    ):
        return None
    return {
        key: projected[key]
        for key in _PUBLIC_CREDIBILITY_KEYS
        if key in projected
    } or None


def _project_public_evidence(value: Any) -> Optional[dict[str, Any]]:
    """Validate and rebuild an evidence-envelope-v1 public representation.

    Rebuilding from named fields ensures recursive unknown keys, arrays and
    camelCase variants cannot leak. Missing/unknown provenance, malformed
    shapes, and USER_RECORDED_OUTCOME all remove the envelope from a share.
    """
    if not isinstance(value, dict):
        return None
    required = {
        "schema_version", "evidence_level", "candidate", "source", "result",
        "independence", "counterexamples", "ledger",
    }
    if not required <= set(value):
        return None
    if value.get("schema_version") != "evidence-envelope-v1":
        return None
    level = value.get("evidence_level")
    if level not in _EVIDENCE_LEVELS:
        return None
    candidate = value.get("candidate")
    source = value.get("source")
    result = value.get("result")
    independence = value.get("independence")
    counterexamples = value.get("counterexamples")
    ledger = value.get("ledger")
    if not all(
        isinstance(item, dict)
        for item in (
            candidate, source, result, independence, counterexamples, ledger,
        )
    ):
        return None

    if candidate.get("status") != "recorded":
        return None
    valid, candidate_kind = _public_text(candidate.get("kind"), limit=100)
    if not valid or not candidate_kind:
        return None
    valid, candidate_label = _public_text(candidate.get("label"))
    if not valid:
        return None
    valid, candidate_score = _public_number(
        candidate.get("score"), minimum=0, maximum=1,
    )
    if not valid:
        return None

    source_kind = source.get("kind")
    source_status = source.get("status")
    if source_kind not in _SOURCE_KINDS or source_status not in {
        "recorded", "not_recorded",
    }:
        return None
    if (source_kind == "not_recorded") != (source_status == "not_recorded"):
        return None
    valid, source_label = _public_text(source.get("label"))
    if not valid:
        return None
    valid, source_url = _public_text(source.get("url"), limit=2048)
    if not valid or not _public_https_url(source_url):
        return None
    source_review = source.get("source_review")
    projected_review = None
    if source_review is not None:
        if not isinstance(source_review, dict):
            return None
        valid_reviewer, reviewer = _public_text(
            source_review.get("reviewer"), limit=200,
        )
        valid_date, reviewed_at = _public_text(
            source_review.get("reviewed_at"), limit=100,
        )
        if not valid_reviewer or not reviewer or not valid_date or not reviewed_at:
            return None
        if not _public_iso_date(reviewed_at):
            return None
        projected_review = {
            "reviewer": reviewer, "reviewed_at": reviewed_at,
        }
    if source_kind == "external_source" and (
        not source_url or projected_review is None
    ):
        return None
    if source_kind != "external_source" and (
        source_url is not None or projected_review is not None
    ):
        return None

    provenance = result.get("provenance")
    if provenance not in _PUBLIC_RESULT_PROVENANCE:
        return None
    result_status = result.get("status")
    expected_result_status = (
        "not_recorded" if provenance == "NOT_TESTED" else "recorded"
    )
    if result_status != expected_result_status:
        return None
    verdict = result.get("verdict")
    if verdict not in _EVIDENCE_VERDICTS:
        return None
    valid, result_summary = _public_text(result.get("summary"))
    if not valid:
        return None

    independence_kind = independence.get("kind")
    independence_status = independence.get("status")
    if independence_kind not in _INDEPENDENCE_KINDS:
        return None
    expected_independence_status = (
        "not_recorded" if independence_kind == "not_recorded" else "recorded"
    )
    if independence_status != expected_independence_status:
        return None
    valid, independence_summary = _public_text(independence.get("summary"))
    if not valid:
        return None

    counterexample_status = counterexamples.get("status")
    if counterexample_status not in _COUNTEREXAMPLE_STATUSES:
        return None
    valid, counterexample_summary = _public_text(
        counterexamples.get("summary"),
    )
    if not valid:
        return None

    ledger_status = ledger.get("status")
    if ledger_status not in {"bound", "not_recorded"}:
        return None
    projected_ledger: dict[str, Any] = {"status": ledger_status}
    for key, limit in (
        ("claim_id", 200), ("version", 100), ("recorded_at", 100),
        ("artifact_sha256", 64), ("url", 2048),
    ):
        valid, text = _public_text(ledger.get(key), limit=limit)
        if not valid:
            return None
        projected_ledger[key] = text
    if not _public_https_url(projected_ledger["url"]):
        return None
    if ledger_status == "bound" and (
        not projected_ledger["claim_id"]
        or not projected_ledger["version"]
        or not projected_ledger["recorded_at"]
        or not isinstance(projected_ledger["artifact_sha256"], str)
        or len(projected_ledger["artifact_sha256"]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in projected_ledger["artifact_sha256"].casefold()
        )
        or not _public_iso_date(projected_ledger["recorded_at"])
    ):
        return None
    if ledger_status == "not_recorded":
        projected_ledger = {
            "status": "not_recorded",
            "claim_id": None,
            "version": None,
            "recorded_at": None,
            "artifact_sha256": None,
            "url": None,
        }

    return {
        "schema_version": "evidence-envelope-v1",
        "evidence_level": level,
        "candidate": {
            "status": "recorded", "kind": candidate_kind,
            "label": candidate_label, "score": candidate_score,
        },
        "source": {
            "status": source_status, "kind": source_kind,
            "label": source_label, "url": source_url,
            "source_review": projected_review,
        },
        "result": {
            "status": result_status, "provenance": provenance,
            "verdict": verdict, "summary": result_summary,
        },
        "independence": {
            "status": independence_status, "kind": independence_kind,
            "summary": independence_summary,
        },
        "counterexamples": {
            "status": counterexample_status, "summary": counterexample_summary,
        },
        "ledger": projected_ledger,
    }


def _sanitize_reserved_payload(value: Any) -> Any:
    """Project public evidence and erase private reserved fields at every depth.

    Persisted JSON has a 256 KiB cap, but it can still be deeper than a
    recursive Python walk safely supports.  The explicit stack preserves all
    ordinary sibling/array content while removing server-owned receipt,
    fingerprint, source and origin keys wherever they appear.  The caller
    lifts only validated top-level metadata before this projection.  A
    generous node budget fails the whole response instead of silently
    truncating public content.
    """
    if not isinstance(value, (dict, list)):
        return value
    root: dict[str, Any] | list[Any] = {} if isinstance(value, dict) else []
    stack: list[tuple[dict[Any, Any] | list[Any], dict[str, Any] | list[Any]]] = [
        (value, root),
    ]
    node_count = 0
    while stack:
        source, target = stack.pop()
        entries = source.items() if isinstance(source, dict) else enumerate(source)
        for key, item in entries:
            node_count += 1
            if node_count > 100_000:
                raise ValueError("report payload structure exceeds node budget")
            if isinstance(source, dict) and key in {
                "_origin_candidate", "_fingerprint", "_source",
                "_report_sha256", "_report_receipt", "_source_record",
                "_target_record",
            }:
                continue
            if isinstance(source, dict) and key == "_credibility":
                projected: Any = _project_public_credibility(item)
            elif isinstance(source, dict) and key == "_evidence":
                projected = _project_public_evidence(item)
            elif isinstance(item, dict):
                projected = {}
                stack.append((item, projected))
            elif isinstance(item, list):
                projected = []
                stack.append((item, projected))
            else:
                projected = item
            if isinstance(target, dict):
                target[key] = projected
            else:
                target.append(projected)
    return root


class StoredReportUnavailable(ValueError):
    """A stored row cannot be safely reconstructed at the current boundary."""


_CURRENT_REPORT_PROMPT = "deep-report-v2"
_CURRENT_REPORT_RESERVED = {
    "_evidence", "_fingerprint", "_origin_candidate", "_source",
    "_report_sha256", "_report_receipt", "_source_record", "_target_record",
}
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _runtime_report_state() -> dict[str, Any]:
    """Read the already-loaded application state without importing main again."""
    module = sys.modules.get("main") or sys.modules.get("web.backend.main")
    state = getattr(module, "app_state", None) if module is not None else None
    return state if isinstance(state, dict) else {}


_INTERNAL_REPORT_CAPABILITY_RE = re.compile(
    r"/(?:api/)?report/share/[0-9a-f]{32}(?![0-9a-f])",
    re.IGNORECASE,
)


def _payload_contains_capability(value: Any) -> bool:
    """Reject any report bearer capability copied into public report data.

    Checking only the row's own token is ineffective: that token is minted
    after generation, while a user can paste a different report's share URL
    into the query or model-visible text.  Scan keys and values iteratively so
    nested payloads cannot launder either the browser or API share route.
    """
    stack = [value]
    visited = 0
    while stack:
        item = stack.pop()
        visited += 1
        if visited > 100_000:
            raise StoredReportUnavailable("stored report exceeds node budget")
        if isinstance(item, str):
            candidate = unicodedata.normalize("NFKC", item)
            # Two rounds cover ordinary and once-double-encoded URLs without
            # turning this bounded scanner into a general URL parser.
            for _ in range(2):
                if _INTERNAL_REPORT_CAPABILITY_RE.search(candidate):
                    return True
                candidate = unquote(candidate)
        if isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)
    return False


def _archive_record(value: Any) -> Optional[dict[str, Any]]:
    keys = {"id", "name", "domain", "type_id", "description"}
    if not isinstance(value, dict) or set(value) != keys:
        return None
    if not isinstance(value.get("id"), str) or not value["id"]:
        return None
    if any(item is not None and not isinstance(item, str) for item in value.values()):
        return None
    return {key: value.get(key) for key in keys}


def _validate_current_report_row(
    r: dict,
) -> tuple[dict[str, Any], str, Literal["current_artifact", "historical_snapshot"]]:
    """Rebuild every server-owned v2 expectation before exposing report text.

    The persisted payload is never allowed to serve as its own authority.  We
    bind it again to the row columns, authenticated generation-time source
    snapshots, the private query-binding key, the confirmed fingerprint
    digest and the server-written canonical report receipt.  Live KB changes
    only mark the archive historical; they never corrupt a valid old report.
    """
    payload = r.get("payload")
    if not isinstance(payload, dict):
        raise StoredReportUnavailable("stored report payload is unavailable")
    report_keys = set(DeepAnalysisReportV2.model_fields)
    if set(payload) - report_keys - _CURRENT_REPORT_RESERVED:
        raise StoredReportUnavailable("stored report contains unknown fields")
    if not {
        "_evidence", "_source", "_source_record", "_report_sha256",
        "_report_receipt",
    } <= set(payload):
        raise StoredReportUnavailable("stored report receipt is unavailable")
    report_value = {key: payload[key] for key in report_keys if key in payload}
    report_sha256 = payload.get("_report_sha256")
    if not isinstance(report_sha256, str) or not _SHA256_RE.fullmatch(report_sha256):
        raise StoredReportUnavailable("stored report receipt is unavailable")

    if __package__ == "web.backend.api":
        from .analyze import (
            _canonical_digest,
            _persisted_report_receipt,
            _query_binding,
            _record_digest,
            _source_ref,
        )
    else:
        from api.analyze import (
            _canonical_digest,
            _persisted_report_receipt,
            _query_binding,
            _record_digest,
            _source_ref,
        )

    sealed_payload = {key: value for key, value in payload.items() if key != "_report_receipt"}
    report_receipt = payload.get("_report_receipt")
    if not isinstance(report_receipt, str) or not _SHA256_RE.fullmatch(report_receipt):
        raise StoredReportUnavailable("stored report archive receipt is unavailable")
    expected_receipt = _persisted_report_receipt(
        query=str(r.get("query") or ""),
        b_id=str(r.get("b_id") or ""),
        lang=str(r.get("lang") or ""),
        model=str(r.get("model") or ""),
        prompt_version=str(r.get("prompt_version") or ""),
        payload=sealed_payload,
    )
    if not hmac.compare_digest(report_receipt, expected_receipt):
        raise StoredReportUnavailable("stored report archive receipt does not match")

    if _canonical_digest(report_value) != report_sha256:
        raise StoredReportUnavailable("stored report receipt does not match")
    try:
        report = DeepAnalysisReportV2.model_validate(report_value)
    except ValidationError as exc:
        raise StoredReportUnavailable("stored report schema is unavailable") from exc
    binding = report.source_binding
    if (
        r.get("prompt_version") != _CURRENT_REPORT_PROMPT
        or r.get("lang") != binding.lang
        or r.get("model") != binding.model_id
        or binding.prompt_version != _CURRENT_REPORT_PROMPT
        or binding.schema_version != "deep-analysis-report-v2"
        or bool(r.get("is_partial"))
        or r.get("rewritten_query") not in {None, ""}
    ):
        raise StoredReportUnavailable("stored report row binding is stale")

    source_record = _archive_record(payload.get("_source_record"))
    if source_record is None or source_record["id"] != binding.source_kb_id:
        raise StoredReportUnavailable("stored report source is unavailable")
    if _record_digest(source_record) != binding.source_record_sha256:
        raise StoredReportUnavailable("stored report source digest is stale")

    row_b_id = str(r.get("b_id") or "")
    row_query = str(r.get("query") or "")
    expected_refs = [_source_ref(source_record, lang=binding.lang)]
    if binding.target_kind == "query":
        if (
            row_b_id != binding.source_kb_id
            or not row_query
            or binding.query_binding
            != _query_binding(row_query, b_id=row_b_id, lang=binding.lang)
        ):
            raise StoredReportUnavailable("stored report query binding is stale")
    else:
        if row_query or row_b_id != binding.target_kb_id:
            raise StoredReportUnavailable("stored report target binding is stale")
        target_record = _archive_record(payload.get("_target_record"))
        if target_record is None or target_record["id"] != binding.target_kb_id:
            raise StoredReportUnavailable("stored report target is unavailable")
        expected_refs.append(_source_ref(target_record, lang=binding.lang, target=True))
    if binding.target_kind == "query" and payload.get("_target_record") is not None:
        raise StoredReportUnavailable("stored report target snapshot is unexpected")

    raw_fingerprint = payload.get("_fingerprint")
    if binding.fingerprint_sha256 is None:
        if raw_fingerprint is not None or binding.fingerprint_revision is not None:
            raise StoredReportUnavailable("stored report fingerprint is stale")
    elif (
        not isinstance(raw_fingerprint, dict)
        or _canonical_digest(raw_fingerprint) != binding.fingerprint_sha256
        or raw_fingerprint.get("revision") != binding.fingerprint_revision
    ):
        raise StoredReportUnavailable("stored report fingerprint is stale")

    source_snapshot = payload.get("_source")
    expected_source_snapshot = {
        key: source_record.get(key) for key in ("id", "name", "domain", "type_id")
    }
    if source_snapshot != expected_source_snapshot:
        raise StoredReportUnavailable("stored report source metadata is stale")
    if _project_public_evidence(payload.get("_evidence")) is None:
        raise StoredReportUnavailable("stored report evidence is unavailable")

    raw_origin = payload.get("_origin_candidate")
    if raw_origin is not None:
        origin = normalize_origin_candidate(raw_origin)
        if (
            origin is None
            or binding.target_kind != "kb"
            or origin["pair"] != {
                "a_id": binding.source_kb_id,
                "b_id": binding.target_kb_id,
            }
        ):
            raise StoredReportUnavailable("stored report candidate origin is stale")

    try:
        validated = validate_bound_deep_report(
            report_value,
            expected_source_binding=binding,
            expected_source_refs=expected_refs,
            expected_source_record=source_record,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise StoredReportUnavailable("stored report trust validation failed") from exc

    snapshot_status: Literal["current_artifact", "historical_snapshot"] = (
        "historical_snapshot"
    )
    state = _runtime_report_state()
    search = state.get("search")
    current_artifact = str((state.get("artifact") or {}).get("artifact_id") or "")
    if not current_artifact:
        current_artifact = "unverified-dev-artifact"
    if callable(getattr(search, "get_by_id", None)):
        current_source = search.get_by_id(binding.source_kb_id)
        if (
            current_artifact == binding.kb_artifact_id
            and isinstance(current_source, dict)
            and _record_digest(current_source) == binding.source_record_sha256
        ):
            snapshot_status = "current_artifact"
    return validated.model_dump(mode="json"), report_sha256, snapshot_status


def _no_store_share(response: Response) -> None:
    for key, value in _SHARE_NO_STORE_HEADERS.items():
        response.headers[key] = value


async def no_store_report_share_responses(request: Request, call_next):
    """Prevent caches retaining any success/error report-read representation."""
    path = request.url.path
    if request.method != "GET" or not (
        path == "/api/report/share" or path.startswith("/api/report/")
    ):
        return await call_next(request)
    response: Optional[Response] = None
    try:
        response = await call_next(request)
    except Exception as exc:
        logger.error(
            "structural.report.read_failed",
            error_type=type(exc).__name__,
            incident_id=new_incident_id(),
        )
        response = JSONResponse(
            {"detail": "Internal Server Error"}, status_code=500,
        )
    finally:
        if response is not None:
            _no_store_share(response)
    return response


def _detail_dict(r: dict, *, share_url: Optional[str] = None) -> dict:
    """Project a validated store row without ever returning a raw token."""
    raw_payload = r.get("payload")
    if not isinstance(raw_payload, dict):
        raise StoredReportUnavailable("stored report payload is unavailable")
    current_v2 = (
        r.get("prompt_version") == _CURRENT_REPORT_PROMPT
        or raw_payload.get("schema_version") == "deep-analysis-report-v2"
    )
    if _payload_contains_capability({
        "query": r.get("query"),
        "rewritten_query": r.get("rewritten_query"),
        "payload": raw_payload,
    }):
        raise StoredReportUnavailable("stored report contains a private capability")
    report_sha256 = None
    snapshot_status = None
    if current_v2:
        report_payload, report_sha256, snapshot_status = _validate_current_report_row(r)
        payload = {
            **report_payload,
            **{
                key: raw_payload[key]
                for key in _CURRENT_REPORT_RESERVED
                if key in raw_payload
            },
        }
    else:
        payload = raw_payload
    # V4: credibility was persisted inside the payload under a reserved key
    # (see analyze.py _maybe_persist) — lift it to a top-level field and
    # hand back a section-only payload. Older reports lack it → None.
    credibility = None
    fingerprint = None
    source = None
    evidence = None
    origin_candidate = None
    if isinstance(payload, dict):
        origin_candidate = normalize_origin_candidate(
            payload.get("_origin_candidate"),
        )
        fingerprint = payload.get("_fingerprint")
        if isinstance(fingerprint, dict) and current_v2:
            # The persisted fingerprint digest deliberately excludes the raw
            # query.  Add the receipt-bound row query only to the response so
            # the browser can verify source_query == query, then hash the
            # remaining fingerprint fields against source_binding.
            fingerprint = {**fingerprint, "source_query": r.get("query", "")}
        source = payload.get("_source")
        payload = _sanitize_reserved_payload(payload)
        credibility = payload.pop("_credibility", None)
        evidence = payload.pop("_evidence", None)
    return {
        "id": r["id"],
        "query": r["query"],
        # Current v2 never has a model rewrite; normalize historical empty
        # strings to None so response_model_exclude_none yields one exact
        # browser contract instead of absent-vs-empty ambiguity.
        "rewritten_query": None if current_v2 else r.get("rewritten_query"),
        "b_id": r["b_id"],
        "lang": r["lang"],
        "payload": payload,
        "model": r["model"],
        "prompt_version": r["prompt_version"],
        "created_at": r["created_at"],
        "view_count": r.get("view_count", 0),
        "is_partial": r.get("is_partial", False),
        "credibility": credibility,
        "fingerprint": fingerprint,
        "source": source,
        "evidence": evidence,
        "origin_candidate": origin_candidate,
        "report_sha256": report_sha256,
        "share_url": share_url,
        "snapshot_status": snapshot_status,
    }


def _owner_share_url(r: dict) -> Optional[str]:
    """Return one relative capability URL only to an already-authorized owner."""
    token = r.get("share_token")
    if not isinstance(token, str) or len(token) != 32:
        return None
    if not verify_share_token(str(r.get("id") or ""), token):
        return None
    return f"/report/share/{token}"


def _authorized_report_identity(
    r: dict,
    request: Request,
    x_anon_id: Optional[str],
) -> tuple[bool, Optional[str]]:
    """Authorize an account owner or the original anonymous browser.

    The returned identity is the persisted follow-up key.  Account ownership
    deliberately maps back to the original creator key so a second device
    continues the same experiment instead of creating a competing row.
    """
    account_owner = r.get("owner_user_id")
    creator = r.get("creator_anon_id")
    if account_owner:
        try:
            user, status = resolve_beta_user(request)
        except Exception:
            return False, None
        if status != "valid" or not user or user.get("id") != account_owner:
            return False, None
        return True, str(creator or account_owner)
    if creator:
        return creator == (x_anon_id or ""), str(creator)
    # Historical v1 reports predate creator binding. Keep their old id-view
    # compatibility, but never extend it to current deep-report-v2 rows.
    if r.get("prompt_version") != _CURRENT_REPORT_PROMPT:
        return True, x_anon_id or "anon"
    return False, None


@router.get(
    "/report/share/{token}",
    response_model=ReportDetailResponse,
    response_model_exclude_none=True,
    summary="Read a report by share token (no auth required)",
)
async def get_report_by_share(token: str, response: Response):
    """Public read via HMAC-signed share token.

    The token alone is the capability — no anon-id / cookie check. Anyone
    holding the token can read. v1 acceptable; v1.1 may add revoke.
    """
    _no_store_share(response)
    if not token or len(token) != 32:
        raise HTTPException(
            404, "Report not found", headers=_SHARE_NO_STORE_HEADERS,
        )
    store = _get_store()
    r = store.get_by_share_token(token)
    if r is None:
        raise HTTPException(
            404, "Report not found", headers=_SHARE_NO_STORE_HEADERS,
        )
    # Constant-time check that the token actually signs this row (defence
    # against a future schema change that lets non-HMAC tokens slip in).
    if not verify_share_token(r["id"], token):
        # Token DB row exists but HMAC doesn't verify — config drift.
        logger.warning("structural.report.share_token_invalid")
        raise HTTPException(
            404, "Report not found", headers=_SHARE_NO_STORE_HEADERS,
        )
    try:
        detail = _detail_dict(r)
    except StoredReportUnavailable:
        logger.warning("structural.report.share_unavailable")
        raise HTTPException(
            404, "Report not found", headers=_SHARE_NO_STORE_HEADERS,
        ) from None
    store.record_view(r["id"])
    return detail


@router.get(
    "/report/{report_id}",
    response_model=ReportDetailResponse,
    response_model_exclude_none=True,
    summary="Read a report by id (owner check via X-Anon-Id)",
)
async def get_report_by_id(
    report_id: str,
    request: Request,
    response: Response,
    x_anon_id: Optional[str] = Header(None),
):
    """Read by id. Soft owner check: if the row has a creator_anon_id and
    the request lacks the matching X-Anon-Id, return 404 (NOT 403, so we
    don't leak existence). Anyone with the share_token should use the
    /share/{token} endpoint instead.
    """
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    authorized, _ = _authorized_report_identity(r, request, x_anon_id)
    if not authorized:
        # Hide existence rather than leak via 403.
        raise HTTPException(404, "Report not found")
    try:
        detail = _detail_dict(r, share_url=_owner_share_url(r))
    except StoredReportUnavailable:
        logger.warning("structural.report.owner_unavailable")
        raise HTTPException(
            409,
            "This saved report can no longer be verified. Generate a new report.",
            headers=_SHARE_NO_STORE_HEADERS,
        ) from None
    _no_store_share(response)
    store.record_view(report_id)
    return detail


@router.get(
    "/reports/mine",
    response_model=ReportListResponse,
    summary="List recent reports by the current anon-id",
)
async def list_my_reports(
    response: Response,
    x_anon_id: Optional[str] = Header(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    _no_store_share(response)
    if not x_anon_id:
        # No anon-id ≈ no history. Return empty rather than 401 so
        # frontend can render "no reports yet" cleanly.
        return {"items": [], "has_more": False}
    store = _get_store()
    items = store.list_by_anon(x_anon_id, limit=limit + 1, offset=offset)
    has_more = len(items) > limit
    items = items[:limit]
    return {
        "items": [
            {
                "id": it["id"],
                "query": it["query"],
                "b_id": it["b_id"],
                "lang": it["lang"],
                "created_at": it["created_at"],
                "view_count": it.get("view_count", 0),
                "has_followup": bool(it.get("has_followup", False)),
                "followup_outcome": it.get("followup_outcome", "") or "",
                "followup_status": it.get("followup_status", "") or "",
                "experiment_status": it.get("experiment_status", "") or "",
                "experiment_deadline": it.get("experiment_deadline"),
                "origin_candidate": it.get("origin_candidate"),
            }
            for it in items
        ],
        "has_more": has_more,
    }


@router.post(
    "/report/{report_id}/feedback",
    response_model=FeedbackResponse,
    summary="Submit section-level 👍/👎 feedback",
)
async def submit_feedback(
    report_id: str,
    body: FeedbackRequest,
    x_anon_id: Optional[str] = Header(None),
):
    """Section-level feedback. Idempotent on (report_id, voter_anon, section):
    re-voting on the same section overwrites the previous vote rather
    than double-counting.

    Voter identity is x-anon-id; if missing we still record the row but
    every anonymous vote collapses to the same bucket (acceptable for v1
    — anti-spam is the rate-limiter's job).
    """
    if body.section not in _ALLOWED_SECTIONS:
        raise HTTPException(400, f"Unknown section: {body.section!r}")
    if body.vote not in (-1, 1):
        raise HTTPException(400, "vote must be -1 or +1")
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    try:
        counts = store.record_feedback(
            report_id=report_id,
            section=body.section,
            vote=body.vote,
            voter_anon=x_anon_id or "anon",
            note=body.note,
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, **counts}


@router.post(
    "/report/{report_id}/followup",
    response_model=FollowupResponse,
    summary="Record a report → action → result revisit (Session #17 V6)",
)
async def submit_followup(
    report_id: str,
    body: FollowupRequest,
    request: Request,
    x_anon_id: Optional[str] = Header(None),
):
    """Record the user coming back to report '我试过了 / 结果如何'.

    Idempotent upsert on (report_id, anon_id) — re-submitting overwrites
    the previous followup (latest wins) rather than piling up rows.
    Identity is X-Anon-Id; missing anon-id collapses to the 'anon' bucket
    (acceptable for v1, same model as feedback).
    """
    if body.action_status not in _ALLOWED_ACTION_STATUSES:
        raise HTTPException(
            400, f"Unknown action_status: {body.action_status!r}"
        )
    if (body.outcome or "") not in _ALLOWED_OUTCOMES:
        raise HTTPException(400, f"Unknown outcome: {body.outcome!r}")
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    authorized, followup_identity = _authorized_report_identity(
        r, request, x_anon_id,
    )
    if not authorized or not followup_identity:
        # Followup changes experimental state and feeds research evidence;
        # possession of a public share URL is read-only, not write authority.
        raise HTTPException(404, "Report not found")
    if r.get("prompt_version") == _CURRENT_REPORT_PROMPT:
        try:
            _detail_dict(r)
        except StoredReportUnavailable:
            raise HTTPException(
                409,
                "This saved report can no longer be verified. Generate a new report.",
                headers=_SHARE_NO_STORE_HEADERS,
            ) from None
    try:
        fu = store.record_followup(
            report_id=report_id,
            anon_id=followup_identity,
            action_status=body.action_status,
            outcome=body.outcome or "",
            note=body.note,
            experiment=(
                body.experiment.model_dump(exclude_unset=True)
                if body.experiment else None
            ),
            outcome_detail=(
                body.outcome_detail.model_dump(exclude_unset=True)
                if body.outcome_detail else None
            ),
            publish_to_insights=body.publish_to_insights,
        )
    except (ValueError, ValidationError) as e:
        raise HTTPException(400, str(e)) from e
    return {
        "ok": True,
        "report_id": fu["report_id"],
        "action_status": fu["action_status"],
        "outcome": fu["outcome"],
        "note": fu.get("note"),
        "experiment": fu.get("experiment"),
        "outcome_detail": fu.get("outcome_detail"),
        "publish_to_insights": fu.get("publish_to_insights", False),
        "consent_version": fu.get("consent_version"),
        "consented_at": fu.get("consented_at"),
        "withdrawn_at": fu.get("withdrawn_at"),
        "created_at": fu["created_at"],
        "updated_at": fu["updated_at"],
    }


@router.get(
    "/report/{report_id}/followup",
    response_model=FollowupReadResponse,
    summary="Read this browser's follow-up for a report",
)
async def get_followup(
    report_id: str,
    request: Request,
    response: Response,
    x_anon_id: Optional[str] = Header(None),
):
    """Return this anon-id's followup for the report.

    Returns {followup: null} when none recorded — lets the frontend render
    the empty 'how did it go?' prompt without a 404 round-trip.
    """
    store = _get_store()
    r = store.get_by_id(report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    authorized, followup_identity = _authorized_report_identity(
        r, request, x_anon_id,
    )
    if not authorized or not followup_identity:
        raise HTTPException(404, "Report not found")
    if r.get("prompt_version") == _CURRENT_REPORT_PROMPT:
        try:
            _detail_dict(r)
        except StoredReportUnavailable:
            raise HTTPException(
                409,
                "This saved report can no longer be verified. Generate a new report.",
                headers=_SHARE_NO_STORE_HEADERS,
            ) from None
    _no_store_share(response)
    fu = store.get_followup(report_id, followup_identity)
    return {"followup": fu}
