from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "web/backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.evidence_envelope import (  # noqa: E402
    ResultProvenance,
    build_evidence_envelope,
    retrieval_candidate,
)
from services.report_store import ReportStore  # noqa: E402
from services.verified_isomorphisms import shape_verified  # noqa: E402


SURFACES = {
    "search.html": "search.js",
    "analyze.html": "analyze.js",
    "index.html": "ask.js",
    "discoveries.html": "discoveries.js",
    "insights.html": "insights.js",
    "report.html": "analyze.js",
}
SIX_FIELDS = {"candidate", "source", "result", "independence", "counterexamples", "ledger"}


def _ledger() -> dict:
    return {
        "status": "bound",
        "claim_id": "claim-1",
        "version": "v1",
        "recorded_at": "2026-07-13",
        "artifact_sha256": "a" * 64,
        "url": "https://example.test/ledger/claim-1",
    }


def _source() -> dict:
    return {
        "source_kind": "external_source",
        "source_label": "Reviewed paper",
        "source_url": "https://example.test/paper",
        "source_review": {"reviewer": "reviewer-a", "reviewed_at": "2026-07-13"},
    }


def _frontend_normalize(payload: dict) -> dict:
    js = ROOT / "web/frontend/assets/js/evidence-envelope.js"
    program = f"""
const fs=require('fs'),vm=require('vm');
const window={{}}; const document={{documentElement:{{lang:'en'}}}};
vm.runInNewContext(fs.readFileSync({json.dumps(str(js))},'utf8'),{{window,document,URL}});
process.stdout.write(JSON.stringify(window.StructuralEvidence.normalize({json.dumps(payload)})));
"""
    result = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def test_envelope_always_has_six_explicit_fields() -> None:
    row = retrieval_candidate({"name": "candidate", "score": 0.72})
    assert SIX_FIELDS <= set(row)
    assert row["source"] == {
        "status": "recorded",
        "kind": "internal_kb",
        "label": "Structural KB record",
        "url": None,
        "source_review": None,
    }
    assert row["result"]["status"] == "not_recorded"
    assert row["independence"]["status"] == "not_recorded"
    assert row["counterexamples"]["status"] == "not_recorded"
    assert row["ledger"]["status"] == "not_recorded"


def test_result_provenance_is_allowlisted_and_orthogonal_to_level() -> None:
    for provenance in ResultProvenance:
        row = build_evidence_envelope(
            candidate_kind="test", result_provenance=provenance,
            result_verdict="INCONCLUSIVE",
        )
        assert row["result"]["provenance"] == provenance.value
        assert row["evidence_level"] == "candidate"
    unknown = build_evidence_envelope(candidate_kind="test", result_provenance="AI_VERIFIED")
    assert unknown["result"]["provenance"] == "NOT_TESTED"
    assert retrieval_candidate({"name": "x", "score": float("nan")})["candidate"]["score"] is None


def test_any_unbound_promotion_downgrades_to_candidate() -> None:
    for level in (
        "source_backed", "analysis_recorded", "falsification_tested",
        "externally_reviewed", "replicated",
    ):
        row = build_evidence_envelope(
            candidate_kind="test", requested_level=level, **_source(),
            result_provenance="INDEPENDENT_REPLICATION", result_verdict="PASS",
            independence_kind="independent_team", counterexample_status="searched",
        )
        assert row["evidence_level"] == "candidate"


def test_external_source_requires_https_review_identity_and_date() -> None:
    for url, review in (
        ("http://example.test/paper", {"reviewer": "r", "reviewed_at": "2026-07-13"}),
        ("https://example.test/paper", {"reviewer": "r"}),
        ("https://example.test/paper", {"reviewer": "r", "reviewed_at": "not-a-date"}),
        ("https://user:pass@example.test/paper", {"reviewer": "r", "reviewed_at": "2026-07-13"}),
    ):
        row = build_evidence_envelope(
            candidate_kind="test", requested_level="source_backed",
            source_kind="external_source", source_url=url, source_review=review,
            ledger=_ledger(),
        )
        assert row["source"]["status"] == "not_recorded"
        assert row["evidence_level"] == "candidate"


def test_external_source_rejects_future_and_impossible_review_dates_in_both_runtimes() -> None:
    for reviewed_at in ("2999-01-01", "2026-99-99"):
        backend = build_evidence_envelope(
            candidate_kind="test", requested_level="source_backed",
            source_kind="external_source", source_url="https://example.test/paper",
            source_review={"reviewer": "r", "reviewed_at": reviewed_at}, ledger=_ledger(),
        )
        frontend = _frontend_normalize({
            "evidence_level": "source_backed", "candidate": {"kind": "test"},
            "source": {"kind": "external_source", "url": "https://example.test/paper", "source_review": {"reviewer": "r", "reviewed_at": reviewed_at}},
            "ledger": {"status": "bound", **_ledger()},
        })
        assert backend["evidence_level"] == frontend["evidence_level"] == "candidate"
        assert backend["source"]["kind"] == frontend["source"]["kind"] == "not_recorded"


def test_valid_source_and_ledger_can_reach_source_backed() -> None:
    row = build_evidence_envelope(
        candidate_kind="test", requested_level="source_backed", **_source(),
        ledger=_ledger(),
    )
    assert row["evidence_level"] == "source_backed"
    assert row["source"]["kind"] == "external_source"
    assert row["ledger"]["status"] == "bound"


def test_external_review_and_replication_require_matching_independence() -> None:
    weak = build_evidence_envelope(
        candidate_kind="test", requested_level="replicated", **_source(), ledger=_ledger(),
        result_provenance="EXTERNAL_REVIEW", result_verdict="PASS",
        independence_kind="external_review", counterexample_status="searched",
    )
    assert weak["evidence_level"] == "candidate"
    strong = build_evidence_envelope(
        candidate_kind="test", requested_level="replicated", **_source(), ledger=_ledger(),
        result_provenance="INDEPENDENT_REPLICATION", result_verdict="PASS",
        independence_kind="independent_team", counterexample_status="searched",
    )
    assert strong["evidence_level"] == "replicated"


def test_unknown_verdict_and_weak_provenance_cannot_promote_in_either_runtime() -> None:
    for provenance, verdict, counterexample in (
        ("INDEPENDENT_REPLICATION", "MAGIC_PASS", "searched"),
        ("INTERNAL_AI_SCREEN", "PASS", "searched"),
        ("USER_RECORDED_OUTCOME", "PASS", "searched"),
        ("INTERNAL_REAL_DATA", "PASS", "invented_status"),
        ("INTERNAL_REAL_DATA", "PASS", "gap_recorded"),
    ):
        backend = build_evidence_envelope(
            candidate_kind="test", requested_level="falsification_tested", **_source(), ledger=_ledger(),
            result_provenance=provenance, result_verdict=verdict,
            independence_kind="internal", counterexample_status=counterexample,
        )
        frontend = _frontend_normalize({
            "evidence_level": "falsification_tested", "candidate": {"kind": "test"},
            "source": {"kind": "external_source", "url": "https://example.test/paper", "source_review": {"reviewer": "reviewer-a", "reviewed_at": "2026-07-13"}},
            "result": {"provenance": provenance, "verdict": verdict},
            "independence": {"status": "recorded", "kind": "internal"},
            "counterexamples": {"status": counterexample}, "ledger": {"status": "bound", **_ledger()},
        })
        assert backend["evidence_level"] == frontend["evidence_level"] == "candidate"


def test_replication_independence_status_is_derived_consistently() -> None:
    frontend = _frontend_normalize({
        "evidence_level": "replicated", "candidate": {"kind": "test"},
        "source": {"kind": "external_source", "url": "https://example.test/paper", "source_review": {"reviewer": "reviewer-a", "reviewed_at": "2026-07-13"}},
        "result": {"provenance": "INDEPENDENT_REPLICATION", "verdict": "PASS"},
        "independence": {"kind": "independent_team"}, "counterexamples": {"status": "searched"},
        "ledger": {"status": "bound", **_ledger()},
    })
    assert frontend["evidence_level"] == "replicated"
    assert frontend["independence"]["status"] == "recorded"


def test_numeric_string_scores_are_not_coerced_in_either_runtime() -> None:
    backend = build_evidence_envelope(candidate_kind="test", candidate_score="0.8")
    frontend = _frontend_normalize({"candidate": {"kind": "test", "score": "0.8"}})
    assert backend["candidate"]["score"] is None
    assert frontend["candidate"]["score"] is None


def test_frontend_normalizer_matches_fail_closed_ledger_rule() -> None:
    js = ROOT / "web/frontend/assets/js/evidence-envelope.js"
    program = f"""
const fs=require('fs'),vm=require('vm');
const window={{}}; const document={{documentElement:{{lang:'en'}}}};
vm.runInNewContext(fs.readFileSync({json.dumps(str(js))},'utf8'),{{window,document,URL}});
const row=window.StructuralEvidence.normalize({{
  evidence_level:'replicated', candidate:{{kind:'x'}},
  source:{{kind:'external_source',url:'https://example.test/x',source_review:{{reviewer:'r',reviewed_at:'2026-07-13'}}}},
  result:{{provenance:'INDEPENDENT_REPLICATION',verdict:'PASS'}},
  independence:{{status:'recorded',kind:'independent_team'}}, counterexamples:{{status:'searched'}},
  ledger:{{status:'not_recorded'}}
}});
process.stdout.write(JSON.stringify(row));
"""
    result = subprocess.run(["node", "-e", program], check=True, capture_output=True, text=True)
    row = json.loads(result.stdout)
    assert row["evidence_level"] == "candidate"
    assert SIX_FIELDS <= set(row)


def test_all_target_pages_load_renderer_before_surface_script() -> None:
    for html_name, js_name in SURFACES.items():
        html = (ROOT / "web/frontend" / html_name).read_text(encoding="utf-8")
        assert "/assets/css/evidence-envelope.css" in html
        assert "/assets/js/i18n.js" in html
        assert html.index("/assets/js/i18n.js") < html.index("/assets/js/evidence-envelope.js")
        assert html.index("/assets/js/evidence-envelope.js") < html.index(f"/assets/js/{js_name}")


def test_all_target_surface_scripts_render_evidence() -> None:
    for js_name in SURFACES.values():
        text = (ROOT / "web/frontend/assets/js" / js_name).read_text(encoding="utf-8")
        assert "StructuralEvidence.render" in text, js_name
    analyze = (ROOT / "web/frontend/assets/js/analyze.js").read_text(encoding="utf-8")
    assert "decision-brief" in analyze and "m.evidence" in analyze


def test_internal_kb_and_external_source_actions_are_distinct() -> None:
    renderer = (ROOT / "web/frontend/assets/js/evidence-envelope.js").read_text(encoding="utf-8")
    ask = (ROOT / "web/frontend/assets/js/ask.js").read_text(encoding="utf-8")
    assert "查看 KB 记录" in renderer and "查看外部来源" in renderer
    assert "查看 KB 记录" in ask and "查看来源 ↗" not in ask
    assert "KB 记录摘要" in ask and "来源摘要</dt>" not in ask


def test_old_escalation_copy_is_absent_from_changed_surfaces() -> None:
    paths = [ROOT / "web/frontend/assets/js" / name for name in SURFACES.values()]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    for forbidden in (
        "人验证这个跨域迁移真的有效",
        "经 AI 评审验证过的同构对",
        "真正来自其他学科的同构现象",
        "结构相同的成熟解法",
        "跨学科迁移才成立",
        "跨领域证据')",
    ):
        assert forbidden not in combined


def test_insights_exposes_complete_outcome_denominator(tmp_path: Path) -> None:
    summary = ReportStore(tmp_path / "history.db").insights_summary()
    assert summary["outcome_counts"] == {
        "worked": 0, "partial": 0, "no_effect": 0,
        "too_early": 0, "not_recorded": 0,
    }
    script = (ROOT / "web/frontend/assets/js/insights.js").read_text(encoding="utf-8")
    for value in ("worked", "partial", "no_effect", "too_early", "not_recorded"):
        assert f"outcomes.{value}" in script
    assert "存在选择偏差，不等于科学验证" in script


def test_user_outcome_is_recorded_without_scientific_promotion() -> None:
    row = shape_verified({
        "id": "r1", "query": "problem", "b_id": "b1", "lang": "zh",
        "payload": {"shared_structure": {"name": "candidate structure"}},
        "verifier_count": 3, "last_verified_at": "2026-07-13", "created_at": "2026-07-13",
    })
    assert row["evidence"]["result"]["provenance"] == "USER_RECORDED_OUTCOME"
    assert row["evidence"]["evidence_level"] == "candidate"
    assert row["evidence"]["independence"]["kind"] == "internal"


def test_discoveries_api_envelopes_every_public_candidate() -> None:
    from api import discoveries

    discoveries._a_cache = None
    discoveries._t2_cache = None
    payload = asyncio.run(discoveries.list_discoveries())
    assert payload["count"] == len(payload["discoveries"])
    assert all(SIX_FIELDS <= set(row["evidence"]) for row in payload["discoveries"])
    assert all(row["evidence"]["evidence_level"] == "candidate" for row in payload["discoveries"])
    assert all(SIX_FIELDS <= set(row["evidence"]) for row in payload["tier2"])


def test_renderer_has_semantics_keyboard_targets_and_mobile_layout() -> None:
    renderer = (ROOT / "web/frontend/assets/js/evidence-envelope.js").read_text(encoding="utf-8")
    css = (ROOT / "web/frontend/assets/css/evidence-envelope.css").read_text(encoding="utf-8")
    assert 'aria-label="' in renderer and '<dl class="evidence-envelope__grid">' in renderer
    assert renderer.count("<dt>") == 6
    assert "min-height:44px" in css and ":focus-visible" in css
    assert "@media(max-width:720px)" in css and "grid-template-columns:1fr" in css
    assert "@media(forced-colors:active)" in css


def test_renderer_preserves_verdict_localizes_levels_and_guards_nested_actions() -> None:
    renderer = (ROOT / "web/frontend/assets/js/evidence-envelope.js").read_text(encoding="utf-8")
    search = (ROOT / "web/frontend/assets/js/search.js").read_text(encoding="utf-8")
    assert "e.result.verdict" in renderer and "NOT_TESTED_VERDICT" in renderer
    assert "c[e.evidence_level]" in renderer
    assert "ledgerLink" in renderer and "e.ledger.url" in renderer
    assert "suppressActions: true" in search
    assert "if (!opts.suppressActions)" in renderer


def test_renderer_reacts_to_language_changes() -> None:
    renderer = (ROOT / "web/frontend/assets/js/evidence-envelope.js").read_text(encoding="utf-8")
    assert "global.i18n.onChange" in renderer
    assert "data-evidence-json" in renderer
    assert "node.outerHTML = render(payload, options)" in renderer


def test_persisted_reports_preserve_evidence_envelope() -> None:
    analyze = (ROOT / "web/backend/api/analyze.py").read_text(encoding="utf-8")
    report_api = (ROOT / "web/backend/api/report.py").read_text(encoding="utf-8")
    report_js = (ROOT / "web/frontend/assets/js/report.js").read_text(encoding="utf-8")
    assert '"_evidence": evidence' in analyze
    assert 'payload.pop("_evidence", None)' in report_api
    assert "detail.evidence" in report_js
