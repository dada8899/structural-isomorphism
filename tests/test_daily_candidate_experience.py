from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_daily_api_has_one_public_candidate_authority() -> None:
    source = read("web/backend/api/daily.py")
    assert "build_public_discoveries" in source
    assert "DailyResponse.model_validate" in source
    for forbidden in (
        "v2-discoveries-expanded",
        "a_discoveries.json",
        "float(conf) / 100.0",
        "app_state.get(\"search\")",
    ):
        assert forbidden not in source


def test_daily_schema_is_exact_and_reuses_discovery_candidate() -> None:
    source = read("web/backend/schemas.py")
    block = source.split("class DailyResponse", 1)[1].split("class FlagsResponse", 1)[0]
    assert 'lang: Literal["zh", "en"]' in block
    assert "List[DiscoveryCandidate]" in block
    assert "min_length=3, max_length=3" in block
    assert 'model_config = {"extra": "forbid"}' in block
    assert "daily candidate ids must be unique" in block


def test_daily_cards_show_candidate_boundary_without_public_score() -> None:
    script = read("web/frontend/assets/js/home.js")
    assert "discovery-candidate-v2" in script
    assert "evidence.evidence_level !== 'candidate'" in script
    assert "/discoveries?candidate=" in script
    assert "待验证候选" in script
    assert "来源未独立复核" in script
    assert "不能证明两边机制相同" in script
    assert "≈?" in script
    assert "formatScore(d.similarity)" not in script
    assert "/analyze?a_id=" not in script.split("function renderDaily", 1)[1].split(
        "// === Local history chips", 1
    )[0]


def test_daily_copy_and_accessibility_contract() -> None:
    learn = read("web/frontend/learn.html")
    css = read("web/frontend/assets/css/home.css")
    content = json.loads(read("web/frontend/assets/data/i18n/content.json"))

    assert "从知识库中查看 <em>3 组</em>跨领域候选联系" in learn
    assert "每天从知识库中揭示" not in learn
    assert 'aria-label="待检验的结构联系">≈?</span>' in learn
    assert ".disc-card:focus-visible" in css
    assert ".disc-card__open" in css and "min-height: 44px" in css
    assert content["page.home.daily_boundary"]["zh"].endswith("它不能证明两边机制相同。")
    assert content["page.home.hero_evidence.sym_aria"]["en"] == "Structural connection to test"
