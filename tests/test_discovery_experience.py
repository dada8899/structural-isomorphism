from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_discovery_page_uses_strict_candidate_contract() -> None:
    script = _text("web/frontend/assets/js/discoveries.js")
    assert "discovery-candidate-v2" in script
    assert "Unsupported discovery schema" in script
    assert "(data.tier2 || []).map(normalizeDiscovery)" in script
    assert "candidate_summary" in script and "validation_plan" in script


def test_public_renderer_does_not_consume_internal_hype_fields() -> None:
    script = _text("web/frontend/assets/js/discoveries.js")
    for forbidden in (
        "target_venue", "paper_title", "full_analysis", "final_score",
        "isomorphism_confidence", "d.similarity", "raw.similarity",
        "建议投稿", "A 级发现",
    ):
        assert forbidden not in script


def test_validation_plan_is_downloadable_and_keeps_boundary() -> None:
    script = _text("web/frontend/assets/js/discoveries.js")
    for required in (
        "downloadValidationPlan", "text/markdown;charset=utf-8",
        "Evidence level: candidate", "Preregistered: no",
        "Not a preregistration", "不是预注册、机制证明或投稿计划",
    ):
        assert required in script
    assert "primary_metric" in script and "failure_condition" in script
    assert "validation_gaps" in script
    assert "model_generated_gaps" not in script
    assert "markdownText" in script and "&lt;" in script and "&gt;" in script


def test_discovery_copy_states_current_zero_evidence_gate() -> None:
    html = _text("web/frontend/discoveries.html")
    assert "不是发现清单或同行评审" in html
    assert "当前所有条目都停留在候选层" in html
    assert "先补来源、数据、比较方法、主指标和失败条件" in html
    assert "AI 内部评分" not in html
    assert html.rstrip().endswith("</html>")


def test_discovery_i18n_copy_cannot_restore_old_public_claims() -> None:
    content = json.loads(_text("web/frontend/assets/data/i18n/content.json"))
    expected = {
        "page.discoveries.hero_eyebrow": ("不是发现清单", "not a list of established discoveries"),
        "page.discoveries.hero_lede": ("所有条目都停留在候选层", "Every item currently remains a candidate"),
        "page.discoveries.cta_hint": ("不生成机制证明", "not mechanism proof"),
        "page.discoveries.stat_a_grade": ("优先核查候选", "Priority-review candidates"),
    }
    for key, (zh, en) in expected.items():
        assert zh in content[key]["zh"]
        assert en in content[key]["en"]


def test_discovery_mobile_controls_and_plan_are_accessible() -> None:
    css = _text("web/frontend/assets/css/discoveries.css")
    script = _text("web/frontend/assets/js/discoveries.js")
    assert "@media (max-width: 360px)" in css
    assert ".disc-plan__grid { grid-template-columns: 1fr; }" in css
    assert "min-height: 44px" in css
    assert ":focus-visible" in css
    assert 'type="button" class="disc-item__cta-btn disc-plan-download"' in script
    assert 'type="button" class="disc-item__expand"' in script
    assert 'aria-expanded="false"' in script and 'aria-controls=' in script
    assert "setDiscoveryExpanded" in script
    assert "if (e.target.closest('a, button')) return" in script


def test_discovery_asset_versions_are_explicit() -> None:
    html = _text("web/frontend/discoveries.html")
    assert "/assets/css/discoveries.css?v=20260714n2" in html
    assert "/assets/js/discoveries.js?v=20260714n2" in html
