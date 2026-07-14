"""Fail-closed public evidence contract shared by beta product surfaces.

Evidence level and result provenance are deliberately independent.  A user
outcome or an internal model screen may be recorded without promoting a
candidate.  Promotion above ``candidate`` requires an auditable ledger
binding; missing or malformed bindings always downgrade the public level.
"""
from __future__ import annotations

from enum import Enum
from datetime import date
import math
import re
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit


class ResultProvenance(str, Enum):
    NOT_TESTED = "NOT_TESTED"
    INTERNAL_AI_SCREEN = "INTERNAL_AI_SCREEN"
    HUMAN_ANNOTATION = "HUMAN_ANNOTATION"
    SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"
    INTERNAL_REAL_DATA = "INTERNAL_REAL_DATA"
    USER_RECORDED_OUTCOME = "USER_RECORDED_OUTCOME"
    EXTERNAL_REVIEW = "EXTERNAL_REVIEW"
    INDEPENDENT_REPLICATION = "INDEPENDENT_REPLICATION"


LEVELS = (
    "candidate",
    "source_backed",
    "analysis_recorded",
    "falsification_tested",
    "externally_reviewed",
    "replicated",
)
VERDICTS = {"PASS", "FAIL", "REJECT", "NULL", "PARTIAL", "INCONCLUSIVE", "NOT_TESTED"}
INDEPENDENCE_KINDS = {"not_recorded", "internal", "human_annotation", "external_review", "independent_team"}
SOURCE_KINDS = {"not_recorded", "internal_kb", "external_source"}
COUNTEREXAMPLE_STATUSES = {"not_recorded", "gap_recorded", "searched", "found", "none_found"}
FALSIFICATION_COUNTEREXAMPLES = {"searched", "found", "none_found"}
ANALYSIS_PROVENANCE = {
    ResultProvenance.HUMAN_ANNOTATION.value,
    ResultProvenance.SYNTHETIC_CONTROL.value,
    ResultProvenance.INTERNAL_REAL_DATA.value,
    ResultProvenance.EXTERNAL_REVIEW.value,
    ResultProvenance.INDEPENDENT_REPLICATION.value,
}
FALSIFICATION_PROVENANCE = {
    ResultProvenance.SYNTHETIC_CONTROL.value,
    ResultProvenance.INTERNAL_REAL_DATA.value,
    ResultProvenance.EXTERNAL_REVIEW.value,
    ResultProvenance.INDEPENDENT_REPLICATION.value,
}
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _text(value: Any, limit: int = 1000) -> Optional[str]:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] if value else None


def _score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    if not math.isfinite(result):
        return None
    return round(max(0.0, min(1.0, result)), 4)


def _valid_ledger(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    if value.get("status") != "bound":
        return False
    required = ("claim_id", "version", "recorded_at", "artifact_sha256")
    if not all(_text(value.get(key), 200) for key in required):
        return False
    digest = _text(value.get("artifact_sha256"), 64)
    recorded_at = _text(value.get("recorded_at"), 100) or ""
    if not ISO_DATE.fullmatch(recorded_at):
        return False
    try:
        recorded_date = date.fromisoformat(recorded_at)
    except ValueError:
        return False
    locator = _text(value.get("url"), 2048)
    if locator and not _valid_https_url(locator):
        return False
    return bool(
        digest and len(digest) == 64
        and all(ch in "0123456789abcdef" for ch in digest.lower())
        and recorded_date <= date.today()
    )


def _valid_https_url(locator: str) -> bool:
    parsed = urlsplit(locator)
    return bool(
        parsed.scheme == "https" and parsed.netloc
        and not parsed.username and not parsed.password
    )


def _valid_external_source(url: Any, review: Any) -> bool:
    locator = _text(url, 2048)
    if not locator or not isinstance(review, Mapping):
        return False
    reviewed_at = _text(review.get("reviewed_at"), 100)
    if not reviewed_at or not ISO_DATE.fullmatch(reviewed_at):
        return False
    try:
        reviewed_date = date.fromisoformat(reviewed_at)
    except ValueError:
        return False
    return bool(
        _valid_https_url(locator) and _text(review.get("reviewer"), 200)
        and reviewed_date <= date.today()
    )


def build_evidence_envelope(
    *,
    candidate_kind: str,
    candidate_label: Optional[str] = None,
    candidate_score: Any = None,
    requested_level: str = "candidate",
    source_kind: str = "not_recorded",
    source_label: Optional[str] = None,
    source_url: Optional[str] = None,
    source_review: Optional[Mapping[str, Any]] = None,
    result_provenance: ResultProvenance | str = ResultProvenance.NOT_TESTED,
    result_verdict: str = "NOT_TESTED",
    result_summary: Optional[str] = None,
    independence_kind: str = "not_recorded",
    independence_summary: Optional[str] = None,
    counterexample_status: str = "not_recorded",
    counterexample_summary: Optional[str] = None,
    ledger: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    """Build a complete six-field envelope and enforce promotion rules."""
    provenance = result_provenance.value if isinstance(result_provenance, ResultProvenance) else str(result_provenance)
    if provenance not in {item.value for item in ResultProvenance}:
        provenance = ResultProvenance.NOT_TESTED.value
    verdict = result_verdict if result_verdict in VERDICTS else "INCONCLUSIVE"
    source_kind = source_kind if source_kind in SOURCE_KINDS else "not_recorded"
    independence_kind = independence_kind if independence_kind in INDEPENDENCE_KINDS else "not_recorded"
    counterexample_status = (
        counterexample_status if counterexample_status in COUNTEREXAMPLE_STATUSES else "not_recorded"
    )
    requested = requested_level if requested_level in LEVELS else "candidate"
    ledger_bound = _valid_ledger(ledger)
    external_url = _text(source_url, 2048) if source_kind == "external_source" else None
    review = dict(source_review) if isinstance(source_review, Mapping) and source_review else None
    if source_kind == "external_source" and not _valid_external_source(external_url, review):
        source_kind = "not_recorded"
        external_url = None
        review = None
    # Strict promotion is quarantined until the runtime consumes the same
    # content-bound artifact/review manifest as the offline evidence ladder.
    # The legacy contract only proves that fields are well formed; it cannot
    # prove that a digest exists, that a review is content-bound, or that the
    # source has two independent reviewers.  Keeping every requested upgrade
    # at candidate is the only honest fail-closed behavior during migration.
    promotion_ok = False
    if requested != "candidate":
        promotion_ok = promotion_ok and source_kind == "external_source"
    if requested in {"analysis_recorded", "falsification_tested", "externally_reviewed", "replicated"}:
        promotion_ok = promotion_ok and provenance in ANALYSIS_PROVENANCE
    if requested in {"falsification_tested", "externally_reviewed", "replicated"}:
        promotion_ok = (
            promotion_ok
            and provenance in FALSIFICATION_PROVENANCE
            and verdict not in {"NOT_TESTED", "INCONCLUSIVE"}
            and counterexample_status in FALSIFICATION_COUNTEREXAMPLES
        )
    if requested in {"externally_reviewed", "replicated"}:
        promotion_ok = promotion_ok and provenance in {ResultProvenance.EXTERNAL_REVIEW.value, ResultProvenance.INDEPENDENT_REPLICATION.value} and independence_kind in {"external_review", "independent_team"}
    if requested == "replicated":
        promotion_ok = promotion_ok and provenance == ResultProvenance.INDEPENDENT_REPLICATION.value and independence_kind == "independent_team"
    effective_level = requested if requested == "candidate" or promotion_ok else "candidate"

    return {
        "schema_version": "evidence-envelope-v1",
        "evidence_level": effective_level,
        "candidate": {
            "status": "recorded",
            "kind": _text(candidate_kind, 100) or "unspecified_candidate",
            "label": _text(candidate_label),
            "score": _score(candidate_score),
        },
        "source": {
            "status": "recorded" if source_kind != "not_recorded" else "not_recorded",
            "kind": source_kind,
            "label": _text(source_label),
            "url": external_url,
            "source_review": review,
        },
        "result": {
            "status": "not_recorded" if provenance == ResultProvenance.NOT_TESTED.value else "recorded",
            "provenance": provenance,
            "verdict": verdict,
            "summary": _text(result_summary),
        },
        "independence": {
            "status": "not_recorded" if independence_kind == "not_recorded" else "recorded",
            "kind": independence_kind,
            "summary": _text(independence_summary),
        },
        "counterexamples": {
            "status": _text(counterexample_status, 40) or "not_recorded",
            "summary": _text(counterexample_summary),
        },
        "ledger": {
            "status": "bound" if ledger_bound else "not_recorded",
            "claim_id": _text((ledger or {}).get("claim_id"), 200),
            "version": _text((ledger or {}).get("version"), 100),
            "recorded_at": _text((ledger or {}).get("recorded_at"), 100),
            "artifact_sha256": _text((ledger or {}).get("artifact_sha256"), 64),
            "url": _text((ledger or {}).get("url"), 2048),
        },
    }


def retrieval_candidate(item: Mapping[str, Any], *, counterexample: Optional[str] = None) -> dict[str, Any]:
    """Envelope for a legacy KB retrieval row: internal record, no external source."""
    return build_evidence_envelope(
        candidate_kind="retrieval_candidate",
        candidate_label=_text(item.get("name")),
        candidate_score=item.get("score", item.get("relevance")),
        source_kind="internal_kb",
        source_label="Structural KB record",
        counterexample_status="gap_recorded" if counterexample else "not_recorded",
        counterexample_summary=counterexample,
    )
