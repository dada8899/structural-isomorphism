#!/usr/bin/env python3
"""Authoritative fail-closed performance gate for the beta product."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

VIEWPORTS: dict[str, dict[str, Any]] = {
    "desktop": {"width": 1280, "height": 800, "isMobile": False},
    "mobile": {"width": 390, "height": 844, "isMobile": True},
}

EVIDENCE_SOURCES = (
    "web/frontend/analyze.html",
    "web/frontend/assets/js/analyze.js",
    "web/frontend/assets/css/analyze.css",
    "scripts/perf_audit.py",
    "scripts/beta_perf_audit.py",
    "perf-budget.json",
)


def _source_snapshot() -> dict[str, str]:
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in EVIDENCE_SOURCES
    }


def _load_authoritative_audit():
    try:
        from scripts.perf_audit import audit_one
    except ImportError as exc:
        raise AuditFailure("playwright and the authoritative perf audit are required") from exc
    return audit_one


@dataclass(frozen=True)
class PageCase:
    path: str
    ready_selector: str
    interaction_selector: str
    required_api: tuple[tuple[str, str], ...] = ()
    interaction_mode: str = "in_page"


PAGES: dict[str, PageCase] = {
    "home": PageCase("index.html", ".ask-chip", ".ask-chip", (("GET", "/api/auth/me"),)),
    "search": PageCase(
        "search.html?context=" + "a" * 32,
        ".result-card",
        "#search-edit-btn",
        (("POST", "/api/search"), ("POST", "/api/search/assess"),
         ("POST", "/api/synthesize/stream"), ("GET", "/api/auth/me")),
    ),
    "analyze": PageCase(
        "analyze.html?id=target-two&a_id=source-one",
        ".section--revealed",
        "#analyze-brief-btn",
        (("POST", "/api/analyze/stream"), ("GET", "/api/favorites"),
         ("GET", "/api/auth/me")),
    ),
    "reports": PageCase(
        "reports.html", ".myr-card", "#myr-export",
        (("GET", "/api/auth/me"), ("GET", "/api/me/reports"),
         ("GET", "/api/favorites")),
    ),
    "discoveries": PageCase(
        "discoveries.html", ".disc-item", ".disc-item__expand",
        (("GET", "/api/discoveries"), ("GET", "/api/auth/me")),
    ),
    "classes": PageCase("classes.html", ".uc-card", ".uc-filter__btn", (("GET", "/api/auth/me"),)),
    "papers": PageCase("papers.html", ".paper-card", ".papers-filter__btn", (("GET", "/api/auth/me"),)),
    "tools": PageCase(
        "tools.html", ".tool-card", ".tool-card",
        (("GET", "/api/auth/me"),), "new_tab",
    ),
}


class AuditFailure(RuntimeError):
    """Raised when a measurement cannot be trusted."""


_AUDIT_STATUSES = frozenset({"passed", "failed"})
_CLEANUP_STATUSES = frozenset({"pending", "passed", "failed"})
_RUN_STAGES = frozenset({
    "browser_setup", "page_setup", "profile_setup", "navigation",
    "load_settle", "ready_selector", "pre_measure_validation",
    "interaction", "paint_measurement", "observation_window",
    "post_measure_validation", "interaction_validation",
    "event_timing_flush", "metric_collection", "event_timing",
    "metric_computation", "complete",
})
_RUN_ERROR_CODES = frozenset({
    "browser_setup_failed", "page_setup_failed", "profile_setup_failed",
    "navigation_failed", "navigation_http_error", "load_settle_failed",
    "ready_selector_failed", "page_validation_failed", "interaction_failed",
    "paint_measurement_failed", "observation_failed",
    "post_measure_validation_failed", "interaction_validation_failed",
    "event_timing_flush_failed", "event_timing_unsupported",
    "event_timing_protocol_invalid", "event_timing_calibration_failed",
    "trusted_interaction_missing",
    "metric_collection_failed", "trusted_event_missing", "metric_computation_failed",
})
_ERROR_TYPES = frozenset({
    "AssertionError", "AttributeError", "AuditFailure", "BaseExceptionGroup",
    "Error", "Exception", "ExceptionGroup", "KeyError", "KeyboardInterrupt",
    "OSError", "RunFinalizationError", "RuntimeError", "SystemExit",
    "TimeoutError", "TypeError", "ValueError",
})
_REQUEST_METHODS = frozenset({
    "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
})
_REQUEST_PATHS = frozenset({
    "/api/analyze/stream", "/api/auth/me", "/api/discoveries",
    "/api/favorites", "/api/me/export", "/api/me/reports", "/api/search",
    "/api/search/assess", "/api/synthesize/stream",
})
_INP_OBSERVATION_MODES = frozenset({
    "event_timing_observed", "trusted_click_threshold_bound",
    "mixed_trusted_modes",
})
_EVENT_TIMING_CALIBRATIONS = frozenset({"chromium_147_threshold_16"})


def _closed_token(value: Any, allowed: frozenset[str], fallback: str) -> str:
    """Map diagnostic labels to a closed vocabulary without echoing input."""
    return value if isinstance(value, str) and value in allowed else fallback


def _closed_error_detail(
    value: Any, *, allowed_codes: frozenset[str], fallback_code: str,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    detail: dict[str, Any] = {
        "code": _closed_token(value.get("code"), allowed_codes, fallback_code),
        "type": (
            None if value.get("type") is None
            else _closed_token(value.get("type"), _ERROR_TYPES, "unknown_error_type")
        ),
    }
    if type(value.get("http_status")) is int:
        detail["http_status"] = value["http_status"]
    return detail


def _checkpoint_run_evidence(sample: Any) -> dict[str, Any]:
    """Whitelist durable run evidence so page text and request values cannot leak."""
    value = sample if isinstance(sample, dict) else {}
    run_index = value.get("run_index")
    evidence: dict[str, Any] = {
        "run_index": (
            run_index if type(run_index) is int and 1 <= run_index <= 1_000_000 else 0
        ),
        "audit_status": _closed_token(
            value.get("audit_status"), _AUDIT_STATUSES, "unknown_audit_status"
        ),
        "stage": _closed_token(value.get("stage"), _RUN_STAGES, "unknown_stage"),
    }
    if "primary_audit_status" in value:
        evidence["primary_audit_status"] = _closed_token(
            value.get("primary_audit_status"), _AUDIT_STATUSES,
            "unknown_audit_status",
        )
    if "cleanup_status" in value:
        evidence["cleanup_status"] = _closed_token(
            value.get("cleanup_status"), _CLEANUP_STATUSES,
            "unknown_cleanup_status",
        )
    if type(value.get("cleanup_attempted")) is bool:
        evidence["cleanup_attempted"] = value["cleanup_attempted"]
    if value.get("evidence_revision") in {1, 2}:
        evidence["evidence_revision"] = value["evidence_revision"]
    for key in (
        "status", "lcp_ms", "lcp_element_text_length", "cls", "fcp_ms",
        "tbt_ms", "inp_proxy_ms", "long_task_count", "long_task_total_ms",
        "loaf_count", "event_count", "interaction_event_count",
        "event_timing_flushed_count", "loaf_flushed_count",
        "observer_animation_frame_flush_count", "trusted_interaction_count",
        "resource_count", "dom_loaded_ms", "load_event_ms",
    ):
        if type(value.get(key)) in {int, float} and math.isfinite(float(value[key])):
            evidence[key] = value[key]
    if type(value.get("event_timing_supported")) is bool:
        evidence["event_timing_supported"] = value["event_timing_supported"]
    if type(value.get("trusted_interaction_window_verified")) is bool:
        evidence["trusted_interaction_window_verified"] = value[
            "trusted_interaction_window_verified"
        ]
    if type(value.get("trusted_pointer_sequence_verified")) is bool:
        evidence["trusted_pointer_sequence_verified"] = value[
            "trusted_pointer_sequence_verified"
        ]
    if "event_timing_threshold_ms" in value:
        evidence["event_timing_threshold_ms"] = (
            16 if value.get("event_timing_threshold_ms") == 16 else 0
        )
    if "inp_observation_mode" in value:
        evidence["inp_observation_mode"] = _closed_token(
            value.get("inp_observation_mode"), _INP_OBSERVATION_MODES,
            "unknown_inp_mode",
        )
    if "event_timing_calibration" in value:
        evidence["event_timing_calibration"] = _closed_token(
            value.get("event_timing_calibration"), _EVENT_TIMING_CALIBRATIONS,
            "unknown_event_timing_calibration",
        )
    if value.get("error") is not None:
        evidence["error"] = _closed_token(
            value.get("error"), _RUN_ERROR_CODES, "unknown_run_error"
        )
    detail = _closed_error_detail(
        value.get("error_detail"), allowed_codes=_RUN_ERROR_CODES,
        fallback_code="unknown_run_error",
    )
    if detail is not None:
        evidence["error_detail"] = detail
    cleanup_detail = _closed_error_detail(
        value.get("cleanup_error"),
        allowed_codes=frozenset({"browser_close_failed"}),
        fallback_code="unknown_cleanup_error",
    )
    if cleanup_detail is not None:
        evidence["cleanup_error"] = cleanup_detail
    timings = value.get("timings_ms")
    if isinstance(timings, dict):
        evidence["timings_ms"] = {
            key: round(float(duration), 1)
            for key, duration in timings.items()
            if key in _RUN_STAGES | {"elapsed"}
            if type(duration) in {int, float} and math.isfinite(float(duration))
        }
    summary = value.get("request_summary")
    if isinstance(summary, dict):
        api_counts = []
        for item in summary.get("api_counts", []):
            if not isinstance(item, dict) or type(item.get("count")) is not int:
                continue
            path = urlsplit(str(item.get("path") or "")).path
            api_counts.append({
                "method": _closed_token(
                    item.get("method"), _REQUEST_METHODS, "UNKNOWN"
                ),
                "path": path if path in _REQUEST_PATHS else "/:unknown_api",
                "count": max(0, item["count"]),
            })
        evidence["request_summary"] = {"api_counts": api_counts}
        for key in (
            "invalid_api_count", "unknown_request_count", "page_error_count",
            "bad_static_response_count",
        ):
            if type(summary.get(key)) is int:
                evidence["request_summary"][key] = max(0, summary[key])
    transfer = value.get("transfer_kb")
    if isinstance(transfer, dict):
        evidence["transfer_kb"] = {
            key: amount for key, amount in transfer.items()
            if key in {"js_kb", "css_kb", "img_kb", "other_kb", "total_kb"}
            and type(amount) in {int, float} and math.isfinite(float(amount))
        }
    return evidence


def _checkpoint_result(result: dict[str, Any]) -> dict[str, Any]:
    safe = _checkpoint_run_evidence(result)
    for key in ("runs", "successful_runs"):
        if type(result.get(key)) is int:
            safe[key] = result[key]
    if "error" in result:
        failed = len(result.get("run_errors", []))
        safe["error"] = f"{failed} of {safe.get('runs', 0)} runs failed"
    for key in ("raw_runs", "run_errors"):
        if isinstance(result.get(key), list):
            safe[key] = [_checkpoint_run_evidence(row) for row in result[key]]
    return safe


def _validate_local_base(base: str) -> str:
    parsed = urlsplit(base)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise AuditFailure("beta perf audit requires a local HTTP origin")
    return base.rstrip("/") + "/"


def _finite_metric(value: Any, *, positive: bool = False) -> bool:
    return (
        type(value) in {int, float}
        and math.isfinite(float(value))
        and (float(value) > 0 if positive else float(value) >= 0)
    )


def _budget_failures(
    page: str,
    viewport: str,
    metrics: dict[str, float],
    thresholds: dict[str, Any],
) -> list[str]:
    lcp_key = f"lcp_{viewport}_ms"
    required = (lcp_key, "cls", "tbt_ms", "inp_proxy_ms")
    for key in required:
        value = thresholds.get(key)
        if (
            type(value) not in {int, float}
            or not math.isfinite(float(value))
            or value <= 0
        ):
            raise AuditFailure(f"missing positive budget: {key}")
    checks = {
        "lcp_ms": float(thresholds[lcp_key]),
        "cls": float(thresholds["cls"]),
        "tbt_ms": float(thresholds["tbt_ms"]),
        "inp_proxy_ms": float(thresholds["inp_proxy_ms"]),
    }
    for metric in checks:
        value = metrics.get(metric)
        if (
            not _finite_metric(value, positive=metric in {"lcp_ms", "inp_proxy_ms"})
        ):
            raise AuditFailure(f"invalid metric: {metric}")
    return [
        f"{page}/{viewport} {metric}={metrics[metric]:.4f} > {limit:.4f}"
        for metric, limit in checks.items()
        if metrics[metric] > limit
    ]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        sort_keys=True,
    )


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _sse_event(name: str, data: Any) -> str:
    body = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return f"event: {name}\ndata: {body}\n\n"


def _analyze_fixture() -> tuple[dict[str, Any], str]:
    """Build a backend-validated report and its browser trust-chain stream."""
    from web.backend.services.deep_report import (
        SourceBinding,
        SourceRef,
        bind_deep_report,
        validate_generated_deep_report_value,
    )
    from web.backend.tests.deep_report_fixtures import report_payload

    source = {
        "id": "source-one", "name": "延迟反馈记录", "domain": "供应链",
        "type_id": "feedback", "description": "内部记录描述了延迟反馈下的候选波动模式。",
    }
    target = {
        "id": "target-two", "name": "目标记录", "domain": "组织协作",
        "type_id": "coordination", "description": "目标记录描述了协作节奏变化。",
    }
    generated_payload = report_payload()
    generated_payload["your_problem_breakdown"]["fingerprint_revision"] = None
    generated_payload["target_domain_intro"]["corresponding_phenomenon"][
        "source_ref_ids"
    ] = ["kb:source-one"]
    generated = validate_generated_deep_report_value(
        generated_payload,
        allowed_source_ref_ids={"kb:source-one"},
        source_ref_id="kb:source-one",
        fingerprint_revision=None,
        expected_lang="zh",
    )
    binding = SourceBinding(
        source_kb_id=source["id"], source_record_sha256=_sha256_json(source),
        kb_artifact_id="kb-artifact-perf", target_kind="kb",
        target_kb_id=target["id"], query_binding=None, fingerprint_sha256=None,
        fingerprint_revision=None, lang="zh", model_id="deterministic-perf-fixture",
        prompt_version="deep-report-v2", schema_version="deep-analysis-report-v2",
    )
    refs = [
        SourceRef(
            source_ref_id="kb:source-one", source_kind="internal_kb",
            record_id=source["id"], label=source["name"],
            limitations="仅为内部候选记录；不证明机制、因果、迁移有效或独立复核。",
        ),
        SourceRef(
            source_ref_id="kb:target-two", source_kind="internal_kb",
            record_id=target["id"], label=target["name"],
            limitations="仅作为比较目标的内部记录；不能据此判断两边机制相同。",
        ),
    ]
    report = bind_deep_report(
        generated, source_binding=binding, source_refs=refs, source_record=source,
    ).model_dump(mode="json")
    boundary = report["report_boundary"]
    meta = {
        "generation_id": "g_" + "1" * 24,
        "a": source, "b": target, "is_query_mode": False,
        "evidence": {
            "schema_version": "evidence-envelope-v1", "evidence_level": "candidate",
            "candidate": {"status": "recorded", "kind": "analysis_candidate", "label": source["name"], "score": None},
            "source": {"status": "recorded", "kind": "internal_kb", "label": "Structural internal KB candidate", "url": None, "source_review": None},
            "result": {"status": "not_recorded", "provenance": "NOT_TESTED", "verdict": "NOT_TESTED", "summary": None},
            "independence": {"status": "not_recorded", "kind": "not_recorded", "summary": None},
            "counterexamples": {"status": "gap_recorded", "summary": "报告必须提出证伪条件；当前未绑定任何已完成的证伪结果。"},
            "ledger": {"status": "not_recorded", "claim_id": None, "version": None, "recorded_at": None, "artifact_sha256": None, "url": None},
        },
        "fingerprint": None, "model": binding.model_id, "lang": "zh",
        "artifact_id": binding.kb_artifact_id, "prompt_version": "deep-report-v2",
        "schema_version": "deep-analysis-report-v2", "report_boundary": boundary,
        "source_binding": binding.model_dump(mode="json"),
        "source_refs": [ref.model_dump(mode="json") for ref in refs],
        "origin_candidate": None,
    }
    report_sha = _sha256_json(report)
    receipt = {
        "generation_id": meta["generation_id"], "report_sha256": report_sha,
        "schema_version": "deep-analysis-report-v2", "from_cache": False,
    }
    stream = _sse_event("meta", meta)
    stream += _sse_event("generation_progress", {"stage": "generating", "attempt": 1})
    stream += _sse_event("generation_progress", {
        "stage": "validating", "attempt": 1,
        "received_chars": len(_canonical_json(report)),
    })
    stream += _sse_event("report_validated", receipt)
    for key in (
        "shared_structure", "your_problem_breakdown", "target_domain_intro",
        "structural_mapping", "borrowable_insights", "how_to_combine",
        "research_directions", "risks_and_limits", "action_plan",
    ):
        stream += _sse_event("section", {"key": key, "data": report[key]})
    stream += _sse_event("done", {
        "generation_id": meta["generation_id"], "report_sha256": report_sha,
        "report": report, "from_cache": False,
    })
    return {"b_id": target["id"], "a_id": source["id"], "lang": "zh", "persist": 0}, stream


def _evidence(label: str) -> dict[str, Any]:
    return {
        "schema_version": "evidence-envelope-v1", "evidence_level": "candidate",
        "candidate": {"status": "recorded", "kind": "discovery_candidate", "label": label, "score": None},
        "source": {"status": "not_recorded", "kind": "not_recorded", "label": None, "url": None, "source_review": None},
        "result": {"status": "not_recorded", "provenance": "NOT_TESTED", "verdict": "NOT_TESTED", "summary": None},
        "independence": {"status": "not_recorded", "kind": "not_recorded", "summary": None},
        "counterexamples": {"status": "gap_recorded", "summary": "共同冲击仍是替代解释。"},
        "ledger": {"status": "not_recorded", "claim_id": None, "version": None, "recorded_at": None, "artifact_sha256": None, "url": None},
    }


def _candidate(rank: int, tier: str) -> dict[str, Any]:
    candidate_id = f"discovery-{rank:016x}"
    return {
        "schema_version": "discovery-candidate-v2",
        "discovery_id": candidate_id,
        "candidate_family_id": f"perf-family-{rank}",
        "family_variant_count": 1,
        "rank": rank,
        "tier": tier,
        "pipeline": "V2" if tier == "priority_review" else None,
        "pair": {
            "a": {"id": "source-one", "name": {"zh": "延迟反馈", "en": "Delayed feedback"}, "domain": {"zh": "供应链", "en": "Supply chain"}},
            "b": {"id": f"target-{rank}", "name": {"zh": "协作节奏", "en": "Coordination rhythm"}, "domain": {"zh": "组织", "en": "Organization"}},
        },
        "candidate_summary": {"zh": "比较反馈延迟与协作过冲；当前仅为候选。", "en": "Compare feedback delay with coordination overshoot; this remains a candidate."},
        "candidate_equations": ["x(t+1)=f(x(t),u(t-d))"],
        "candidate_variable_mapping": {"反馈延迟": "决策延迟"},
        "evidence_language": "zh_only",
        "provenance": {"status": "not_started", "recorded_source_count": 0, "independent_review_complete": False, "systematic_search_recorded": False},
        "readiness": {"status": "blocked", "ready_for_preregistration": False, "blockers": ["source_review", "dataset_record", "primary_metric", "preregistered_stop_rule"]},
        "validation_plan": {
            "status": "draft_requires_user_completion",
            "hypothesis": {"zh": "检验候选映射。", "en": "Test the candidate mapping."},
            "data_needed": {"zh": "补齐来源与样本。", "en": "Add sources and samples."},
            "baseline": {"zh": "比较无迁移基线。", "en": "Compare a no-transfer baseline."},
            "primary_metric": {"zh": "待定义", "en": "To be defined"},
            "failure_condition": {"zh": "与基线相同则拒绝。", "en": "Reject if equal to baseline."},
            "validation_gaps": [
                {"gap_id": "source_support_not_reviewed", "label": {"zh": "来源尚未独立复核。", "en": "Sources are not independently reviewed."}},
                {"gap_id": "candidate_equation_not_expert_reviewed", "label": {"zh": "候选方程尚未专家复核。", "en": "The equation is not expert-reviewed."}},
                {"gap_id": "variable_mapping_not_expert_reviewed", "label": {"zh": "变量对应尚未专家复核。", "en": "The mapping is not expert-reviewed."}},
                {"gap_id": "competing_explanations_not_tested", "label": {"zh": "其他解释尚未检验。", "en": "Alternatives are not tested."}},
                {"gap_id": "dataset_and_sampling_not_recorded", "label": {"zh": "数据和抽样尚未记录。", "en": "Data and sampling are not recorded."}},
                {"gap_id": "baseline_and_stop_rule_not_preregistered", "label": {"zh": "研究方案尚未公开锁定。", "en": "The plan is not publicly locked."}},
            ],
            "preregistered": False,
        },
        "analyze_url": f"/analyze?a_id=source-one&id=target-{rank}",
        "evidence": _evidence(candidate_id),
    }


def _discovery_payload() -> dict[str, Any]:
    priority = [_candidate(rank, "priority_review") for rank in range(1, 4)]
    pool = [_candidate(101, "candidate_pool")]
    return {
        "count": len(priority), "discoveries": priority,
        "tier2_count": len(pool), "tier2": pool,
        "stats": {
            "total_candidates": 4, "priority_review": 3, "candidate_pool": 1,
            "candidate_families": 4, "source_backed": 0,
            "ready_for_preregistration": 0,
        },
    }


def _search_context() -> dict[str, Any]:
    return {
        "version": 1, "kind": "search", "created_at": int(time.time() * 1000),
        "query": "团队扩张后决策反馈变慢并出现反复修正",
        "rewritten_query": None, "lang": "zh", "force": False,
        "source": "home", "phenomenon_id": None, "results": [],
    }


def _search_result() -> dict[str, Any]:
    return {
        "count": 2,
        "results": [
            {"id": "source-one", "name": "延迟反馈候选", "domain": "供应链", "type_id": "feedback", "description": "内部知识库中的候选反馈记录。", "cross_domain": True},
            {"id": "source-two", "name": "阈值级联候选", "domain": "网络科学", "type_id": "cascade", "description": "内部知识库中的候选级联记录。", "cross_domain": True},
        ],
        "rewritten_query": None, "v2_pairs_for_top": [],
        "stats": {"cross_domain_count": 2, "same_domain_count": 0},
    }


def _reports_payload() -> dict[str, Any]:
    return {
        "items": [{
            "id": "r_2222222222222222",
            "query": "团队扩张后决策反馈为何变慢？",
            "created_at": "2026-07-14T05:30:00.000000Z",
            "view_count": 2, "lang": "zh", "has_followup": True,
            "followup_status": "planned", "followup_outcome": "",
            "experiment_status": "planned", "experiment_deadline": "2026-07-20",
            "publish_to_insights": False, "origin_candidate": None,
        }],
        "has_more": False,
    }


def _page_setup_factory(
    page_name: str,
    case: PageCase,
    origin: tuple[str, str, int | None],
    analyze_request: dict[str, Any],
    analyze_stream: str,
):
    def setup(page: Any, _viewport: str, _run: int) -> dict[str, Any]:
        state: dict[str, Any] = {
            "api_counts": {}, "invalid_api": [], "unknown_requests": [],
            "page_errors": [], "bad_static_responses": [],
            "tool_navigation_count": 0,
        }
        if page_name == "search":
            storage_key = "structural_private_navigation:" + "a" * 32
            serialized = json.dumps(_search_context(), ensure_ascii=False)
            page.add_init_script(
                "sessionStorage.setItem(" + json.dumps(storage_key) + "," +
                json.dumps(serialized, ensure_ascii=False) + ");"
            )

        page.on(
            "pageerror",
            lambda error: state["page_errors"].append(type(error).__name__),
        )

        def record_response(response: Any) -> None:
            parsed = urlsplit(response.url)
            current = (parsed.scheme, parsed.hostname or "", parsed.port)
            if current == origin and not parsed.path.startswith("/api/") and response.status >= 400:
                state["bad_static_responses"].append(
                    f"{response.status} {parsed.path}"
                )

        page.on("response", record_response)

        if page_name == "tools":
            host = origin[1] + (f":{origin[2]}" if origin[2] is not None else "")
            tool_target = f"{origin[0]}://{host}/analyze"
            target_html = (ROOT / "web/frontend/analyze.html").read_text(
                encoding="utf-8"
            )

            def serve_tool_target(route: Any) -> None:
                if route.request.method != "GET":
                    state["invalid_api"].append("tool navigation was not GET")
                    route.abort()
                    return
                state["tool_navigation_count"] += 1
                route.fulfill(
                    status=200,
                    content_type="text/html; charset=utf-8",
                    body=target_html,
                )

            page.context.route(tool_target, serve_tool_target)

        def fulfill_json(route: Any, payload: Any, status: int = 200) -> None:
            route.fulfill(
                status=status, content_type="application/json; charset=utf-8",
                body=json.dumps(payload, ensure_ascii=False, allow_nan=False),
            )

        def reject_api(route: Any, key: tuple[str, str], reason: str) -> None:
            state["invalid_api"].append(f"{key[0]} {key[1]}: {reason}")
            fulfill_json(route, {"error": "invalid deterministic request"}, 422)

        def body(route: Any, key: tuple[str, str]) -> dict[str, Any] | None:
            try:
                value = route.request.post_data_json
            except Exception:
                reject_api(route, key, "body is not JSON")
                return None
            if not isinstance(value, dict):
                reject_api(route, key, "body is not an object")
                return None
            return value

        def route_request(route: Any) -> None:
            request = route.request
            parsed = urlsplit(request.url)
            current = (parsed.scheme, parsed.hostname or "", parsed.port)
            if current != origin:
                state["unknown_requests"].append(f"external {request.method} {parsed.hostname}")
                route.abort()
                return
            if not parsed.path.startswith("/api/"):
                route.continue_()
                return

            key = (request.method, parsed.path)
            state["api_counts"][key] = state["api_counts"].get(key, 0) + 1
            if key == ("GET", "/api/auth/me"):
                if page_name == "reports":
                    fulfill_json(route, {"user": {"email": "researcher@example.test"}})
                else:
                    fulfill_json(route, {"error": "no session"}, 401)
                return
            if key == ("GET", "/api/favorites"):
                if page_name == "reports":
                    fulfill_json(route, {"tickers": [], "bookmarks": []})
                else:
                    fulfill_json(route, {"error": "no session"}, 401)
                return
            if page_name == "reports" and key == ("GET", "/api/me/reports"):
                fulfill_json(route, _reports_payload())
                return
            if page_name == "reports" and key == ("GET", "/api/me/export"):
                fulfill_json(
                    route,
                    {
                        "schema_version": 1,
                        "user": {"email": "researcher@example.test"},
                        "reports": _reports_payload()["items"],
                        "favorites": [],
                    },
                )
                return
            if page_name == "discoveries" and key == ("GET", "/api/discoveries"):
                fulfill_json(route, _discovery_payload())
                return

            if page_name == "search" and key == ("POST", "/api/search"):
                posted = body(route, key)
                expected = {
                    "query": _search_context()["query"], "top_k": 20,
                    "rewrite": False, "lang": "zh",
                }
                if posted is None:
                    return
                if posted != expected:
                    reject_api(route, key, "request does not match private search state")
                    return
                fulfill_json(route, _search_result())
                return
            if page_name == "search" and key == ("POST", "/api/search/assess"):
                posted = body(route, key)
                expected = {"query": _search_context()["query"], "lang": "zh"}
                if posted is None:
                    return
                if posted != expected:
                    reject_api(route, key, "assessment request drifted")
                    return
                fulfill_json(route, {
                    "worth_score": 4, "category": "complex system",
                    "coaching": "补充可测量边界。", "rewrite_suggestion": None,
                    "rewritten": expected["query"],
                })
                return
            if page_name == "search" and key == ("POST", "/api/synthesize/stream"):
                posted = body(route, key)
                expected = {
                    "query": _search_context()["query"], "rewritten_query": None,
                    "results": [{"id": "source-one"}, {"id": "source-two"}],
                    "lang": "zh",
                }
                if posted is None:
                    return
                if posted != expected:
                    reject_api(route, key, "synthesis request drifted")
                    return
                degraded = {
                    "schema_version": "search-candidate-synthesis-v1",
                    "synthesis_status": "degraded",
                    "main_insight": "候选比较保持降级状态，采用前仍需核对来源。",
                    "why_these_matter": "逐条检查来源记录、证据缺口与失败条件。",
                    "primary_recommendation": None, "alternative_angles": [],
                    "relevance_snippets": [],
                }
                route.fulfill(
                    status=200, content_type="text/event-stream; charset=utf-8",
                    body=_sse_event("done", {"result": degraded}),
                )
                return
            if page_name == "analyze" and key == ("POST", "/api/analyze/stream"):
                posted = body(route, key)
                if posted is None:
                    return
                if posted != analyze_request:
                    reject_api(route, key, "Analyze request is not fixture-bound")
                    return
                route.fulfill(
                    status=200, content_type="text/event-stream; charset=utf-8",
                    body=analyze_stream,
                )
                return

            state["unknown_requests"].append(f"unknown API {key[0]} {key[1]}")
            fulfill_json(route, {"error": "unknown deterministic endpoint"}, 599)

        page.route("**/*", route_request)
        return state

    return setup


def _page_validator(page_name: str, case: PageCase):
    def validate(page: Any, state: dict[str, Any]) -> None:
        for field in (
            "invalid_api", "unknown_requests", "page_errors", "bad_static_responses",
        ):
            if state.get(field):
                raise AuditFailure(f"{field}: {state[field]}")
        missing = [
            f"{method} {path}" for method, path in case.required_api
            if state["api_counts"].get((method, path), 0) < 1
        ]
        if missing:
            raise AuditFailure(f"required API state was not exercised: {missing}")

        layout = page.evaluate(
            """() => ({
              viewport: window.innerWidth,
              scroll: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth)
            })"""
        )
        if not all(_finite_metric(layout.get(key), positive=True) for key in ("viewport", "scroll")):
            raise AuditFailure("invalid layout dimensions")
        if layout["scroll"] > layout["viewport"] + 1:
            raise AuditFailure(
                f"horizontal overflow: {layout['scroll']} > {layout['viewport']}"
            )

        expected_counts = {
            "home": (".ask-chip", 4),
            "search": (".result-card", 2),
            "analyze": (".section--revealed", 9),
            "reports": (".myr-card", 1),
            "discoveries": (".disc-item", 3),
            "classes": (".uc-card", 1),
            "papers": (".paper-card", 20),
            "tools": (".tool-card", 8),
        }
        selector, minimum = expected_counts[page_name]
        count = page.locator(selector).count()
        if count < minimum:
            raise AuditFailure(f"unexpected {page_name} state: {selector} count={count}")
        if page_name == "search":
            if page.locator(".search-context-lost").count() or "context=" in page.url:
                raise AuditFailure("private search handoff was not consumed safely")
        elif page_name == "analyze":
            valid = page.evaluate(
                "() => !!window._finalReport && !document.getElementById('analyze-loading')"
            )
            if not valid:
                raise AuditFailure("Analyze report did not complete its trust chain")
        elif page_name == "reports":
            if page.locator(".myr-account-email").count() != 1:
                raise AuditFailure("authenticated research library state was not committed")
        elif page_name == "papers":
            busy = page.locator("#papers-content").get_attribute("aria-busy")
            if busy != "false":
                raise AuditFailure("papers manifest did not reach a validated state")

    return validate


def _post_interaction_validator(page_name: str):
    def validate(
        _page: Any, state: dict[str, Any], interaction: dict[str, Any]
    ) -> None:
        if page_name == "reports":
            if state["api_counts"].get(("GET", "/api/me/export"), 0) != 1:
                raise AuditFailure("research-library export action did not complete")
        elif page_name == "tools":
            destination = urlsplit(str(interaction.get("destination_url", "")))
            if (
                interaction.get("mode") != "new_tab"
                or interaction.get("popup_created") is not True
                or destination.path != "/analyze"
                or state.get("tool_navigation_count") != 1
            ):
                raise AuditFailure("tool-card navigation did not load its real target")

    return validate


def _validate_audit_result(result: dict[str, Any], runs: int) -> None:
    if "error" in result:
        raise AuditFailure(str(result["error"]))
    if result.get("runs") != runs:
        raise AuditFailure("authoritative audit returned the wrong run count")
    raw_runs = result.get("raw_runs")
    if not isinstance(raw_runs, list) or len(raw_runs) != runs:
        raise AuditFailure("three raw runs are required for an auditable median")

    metric_keys = (
        "lcp_ms", "cls", "fcp_ms", "tbt_ms", "inp_proxy_ms",
        "long_task_total_ms", "dom_loaded_ms", "load_event_ms",
    )
    for metric in metric_keys:
        if not _finite_metric(
            result.get(metric), positive=metric in {"lcp_ms", "fcp_ms", "inp_proxy_ms"},
        ):
            raise AuditFailure(f"invalid aggregate metric: {metric}")
    if (
        result.get("event_timing_supported") is not True
        or result.get("trusted_interaction_window_verified") is not True
        or result.get("trusted_pointer_sequence_verified") is not True
        or type(result.get("trusted_interaction_count")) is not int
        or result["trusted_interaction_count"] != 1
        or result.get("event_timing_threshold_ms") != 16
        or result.get("event_timing_calibration")
        != "chromium_147_threshold_16"
        or result.get("observer_animation_frame_flush_count") != 2
        or result.get("inp_observation_mode") not in _INP_OBSERVATION_MODES
    ):
        raise AuditFailure("aggregate trusted interaction evidence is invalid")
    for index, sample in enumerate(raw_runs):
        if (
            not isinstance(sample, dict)
            or "error" in sample
            or sample.get("audit_status") != "passed"
            or sample.get("primary_audit_status") != "passed"
            or sample.get("cleanup_status") != "passed"
            or sample.get("cleanup_attempted") is not True
            or sample.get("evidence_revision") != 2
        ):
            raise AuditFailure(f"raw run {index + 1} is incomplete")
        for metric in metric_keys:
            if not _finite_metric(
                sample.get(metric),
                positive=metric in {"lcp_ms", "fcp_ms", "inp_proxy_ms"},
            ):
                raise AuditFailure(f"invalid raw metric {metric} in run {index + 1}")
        interaction_event_count = sample.get("interaction_event_count")
        mode = sample.get("inp_observation_mode")
        if (
            sample.get("status") != 200
            or sample.get("event_timing_supported") is not True
            or sample.get("trusted_interaction_window_verified") is not True
            or sample.get("trusted_pointer_sequence_verified") is not True
            or type(sample.get("trusted_interaction_count")) is not int
            or sample["trusted_interaction_count"] != 1
            or sample.get("event_timing_threshold_ms") != 16
            or sample.get("event_timing_calibration")
            != "chromium_147_threshold_16"
            or sample.get("observer_animation_frame_flush_count") != 2
            or type(interaction_event_count) is not int
            or interaction_event_count < 0
            or type(sample.get("event_timing_flushed_count")) is not int
            or sample["event_timing_flushed_count"] < 0
            or type(sample.get("loaf_flushed_count")) is not int
            or sample["loaf_flushed_count"] < 0
            or mode not in {
                "event_timing_observed", "trusted_click_threshold_bound",
            }
            or (mode == "event_timing_observed" and interaction_event_count < 1)
            or (
                mode == "trusted_click_threshold_bound"
                and (
                    interaction_event_count != 0
                    or float(sample.get("inp_proxy_ms", 0)) < 16
                )
            )
        ):
            raise AuditFailure(f"run {index + 1} lacks a trusted successful interaction")
        sample_transfer = sample.get("transfer_kb")
        if not isinstance(sample_transfer, dict) or any(
            not _finite_metric(sample_transfer.get(key))
            for key in ("js_kb", "css_kb", "img_kb", "other_kb", "total_kb")
        ):
            raise AuditFailure(f"invalid raw resource metrics in run {index + 1}")

    raw_modes = {sample["inp_observation_mode"] for sample in raw_runs}
    expected_mode = (
        next(iter(raw_modes)) if len(raw_modes) == 1 else "mixed_trusted_modes"
    )
    expected_trusted_count = min(
        sample["trusted_interaction_count"] for sample in raw_runs
    )
    expected_interaction_event_count = min(
        sample["interaction_event_count"] for sample in raw_runs
    )
    expected_flushed_count = sum(
        sample["event_timing_flushed_count"] for sample in raw_runs
    )
    expected_loaf_flushed_count = sum(
        sample["loaf_flushed_count"] for sample in raw_runs
    )
    if (
        result.get("inp_observation_mode") != expected_mode
        or result.get("trusted_interaction_count") != expected_trusted_count
        or result.get("interaction_event_count") != expected_interaction_event_count
        or result.get("event_timing_flushed_count") != expected_flushed_count
        or result.get("loaf_flushed_count") != expected_loaf_flushed_count
    ):
        raise AuditFailure("aggregate trusted interaction evidence is inconsistent")

    transfer = result.get("transfer_kb")
    if not isinstance(transfer, dict):
        raise AuditFailure("resource transfer metrics are missing")
    for key in ("js_kb", "css_kb", "img_kb", "other_kb", "total_kb"):
        if not _finite_metric(transfer.get(key)):
            raise AuditFailure(f"invalid resource metric: {key}")


def run(
    base: str,
    runs: int,
    budget_path: Path,
    evidence_path: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    if runs != 3:
        raise AuditFailure("the release gate requires exactly three runs")
    base = _validate_local_base(base)
    parsed = urlsplit(base)
    origin = (parsed.scheme, parsed.hostname or "", parsed.port)
    budget = json.loads(budget_path.read_text(encoding="utf-8"))
    thresholds = budget.get("thresholds")
    if not isinstance(thresholds, dict):
        raise AuditFailure("budget thresholds must be an object")
    audit_one = _load_authoritative_audit()
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuditFailure("playwright is required") from exc

    analyze_request, analyze_stream = _analyze_fixture()
    source_snapshot = _source_snapshot()
    report: dict[str, Any] = {
        "schema_version": 2,
        "engine": "scripts/perf_audit.py:audit_one",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "base_url": base,
        "runs_per_page": runs,
        "profiles": {
            "desktop": {"cpu_throttle": 1, "network": "native"},
            "mobile": {"cpu_throttle": 4, "network": "slow-4g"},
            "tbt_window_ms": 5000,
            "inp": "trusted Playwright click; Event Timing plus LoAF",
        },
        "resource_budget_note": (
            "Transfer bytes are recorded as three-run medians. Existing bundle "
            "thresholds describe Next.js build output and are not compared to static transfer totals."
        ),
        "pages": {},
        "source_snapshot_sha256": source_snapshot,
        "status": "running",
        "failures": [],
    }
    failures: list[str] = []

    def checkpoint() -> None:
        if evidence_path is not None:
            _write_report(evidence_path, report)

    checkpoint()
    with sync_playwright() as runtime:
        for page_name, case in PAGES.items():
            page_report = {"path": case.path, "viewports": {}}
            report["pages"][page_name] = page_report
            for viewport_name, viewport in VIEWPORTS.items():
                started = time.time()
                result: dict[str, Any] | None = None
                progress: dict[str, Any] = {
                    "status": "running", "runs": runs, "completed_runs": 0,
                    "successful_runs": 0, "raw_runs": [], "run_errors": [],
                }
                page_report["viewports"][viewport_name] = progress
                checkpoint()

                def persist_run(sample: dict[str, Any]) -> None:
                    durable = _checkpoint_run_evidence(sample)
                    for index, existing in enumerate(progress["raw_runs"]):
                        if existing.get("run_index") == durable.get("run_index"):
                            progress["raw_runs"][index] = durable
                            break
                    else:
                        progress["raw_runs"].append(durable)
                    progress["raw_runs"].sort(
                        key=lambda row: row.get("run_index", 0)
                    )
                    progress["completed_runs"] = sum(
                        row.get("cleanup_status") in {"passed", "failed"}
                        for row in progress["raw_runs"]
                    )
                    progress["successful_runs"] = sum(
                        row.get("audit_status") == "passed"
                        and row.get("cleanup_status") == "passed"
                        for row in progress["raw_runs"]
                    )
                    progress["run_errors"] = [
                        row for row in progress["raw_runs"]
                        if row.get("audit_status") != "passed"
                        or row.get("cleanup_status") != "passed"
                    ]
                    final_failure = any(
                        row.get("audit_status") != "passed"
                        or row.get("cleanup_status") == "failed"
                        for row in progress["raw_runs"]
                    )
                    pending_cleanup = any(
                        row.get("cleanup_status") not in {"passed", "failed"}
                        for row in progress["raw_runs"]
                    )
                    progress["status"] = (
                        "failed" if final_failure
                        else "incomplete" if pending_cleanup
                        else "running"
                    )
                    progress["last_stage"] = durable.get("stage", "unknown")
                    checkpoint()

                try:
                    result = audit_one(
                        runtime, base, case.path, viewport_name, viewport,
                        case.interaction_selector, runs=runs,
                        page_setup=_page_setup_factory(
                            page_name, case, origin, analyze_request, analyze_stream,
                        ),
                        ready_selector=case.ready_selector,
                        page_validator=_page_validator(page_name, case),
                        post_interaction_validator=_post_interaction_validator(page_name),
                        interaction_mode=case.interaction_mode,
                        run_evidence_sink=persist_run,
                    )
                    _validate_audit_result(result, runs)
                    failures.extend(
                        _budget_failures(page_name, viewport_name, result, thresholds)
                    )
                    result = _checkpoint_result(result)
                except Exception as exc:
                    gate_error = {
                        "code": (
                            "authoritative_result_rejected"
                            if isinstance(exc, AuditFailure)
                            else "audit_execution_failed"
                        ),
                        "type": _closed_token(
                            type(exc).__name__, _ERROR_TYPES, "unknown_error_type"
                        ),
                    }
                    evidence_source = result if isinstance(result, dict) else {
                        "runs": runs,
                        "successful_runs": progress["successful_runs"],
                        "raw_runs": progress["raw_runs"],
                        "run_errors": progress["run_errors"],
                    }
                    result = _checkpoint_result(evidence_source)
                    result["gate_error"] = gate_error
                    result["runs"] = runs
                    failures.append(
                        f"{page_name}/{viewport_name} audit failed: "
                        f"{gate_error['code']} ({gate_error['type']})"
                    )
                page_report["viewports"][viewport_name] = result
                report["failures"] = failures
                checkpoint()
                print(
                    f"[{viewport_name:7}] {page_name:12} "
                    f"LCP={result.get('lcp_ms', 0):.0f} "
                    f"CLS={result.get('cls', 0):.3f} "
                    f"TBT={result.get('tbt_ms', 0):.0f} "
                    f"INP*={result.get('inp_proxy_ms', 0):.0f} "
                    f"JS={result.get('transfer_kb', {}).get('js_kb', 0):.0f}KB "
                    f"({time.time() - started:.1f}s)",
                    flush=True,
                )
    final_snapshot = _source_snapshot()
    if final_snapshot != source_snapshot:
        failures.append("audited source files changed while the gate was running")
        report["final_source_snapshot_sha256"] = final_snapshot
    report["status"] = "failed" if failures else "passed"
    report["failures"] = failures
    checkpoint()
    return report, failures


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        report, indent=2, ensure_ascii=False, allow_nan=False
    ) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError:
            # Some filesystems do not support directory fsync. The same-dir
            # replace is still atomic and the file itself was synced first.
            pass
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:4173")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--budget", type=Path, default=Path("perf-budget.json"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report, failures = run(
            args.base, args.runs, args.budget, evidence_path=args.out
        )
        _write_report(args.out, report)
    except Exception as exc:
        failure_report: dict[str, Any] = {}
        try:
            failure_base = _validate_local_base(args.base)
        except Exception:
            failure_base = "invalid_local_base"
        try:
            existing = json.loads(args.out.read_text(encoding="utf-8"))
            if (
                isinstance(existing, dict)
                and existing.get("schema_version") == 2
                and existing.get("base_url") == failure_base
            ):
                failure_report = existing
        except Exception:
            failure_report = {}
        if not failure_report:
            failure_report = {
                "schema_version": 2,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "base_url": failure_base,
                "runs_per_page": args.runs,
                "pages": {},
                "failures": [],
            }
        failure_report["status"] = "error"
        exception_type = _closed_token(
            type(exc).__name__, _ERROR_TYPES, "unknown_error_type"
        )
        failure_report.setdefault("failures", []).append(
            f"audit_aborted ({exception_type})"
        )
        try:
            _write_report(args.out, failure_report)
        except Exception as write_error:
            print(
                "beta performance audit could not write failure evidence: "
                f"{type(write_error).__name__}"
            )
        print(
            "beta performance audit failed: "
            f"{exception_type}"
        )
        return 2
    for failure in failures:
        print(f"FAIL {failure}")
    if failures:
        return 1
    print(f"beta performance audit passed: {len(PAGES)} pages x {len(VIEWPORTS)} viewports")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
