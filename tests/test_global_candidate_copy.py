from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web" / "frontend"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_core_entry_surfaces_do_not_promise_identical_structure_or_mature_answers() -> None:
    paths = [
        "web/frontend/index.html",
        "web/frontend/search.html",
        "web/frontend/tools.html",
        "web/frontend/reports.html",
        "web/frontend/report.html",
        "web/frontend/connections.html",
        "web/frontend/diagnose.html",
        "web/frontend/learn.html",
        "web/frontend/assets/js/connections.js",
        "web/frontend/assets/js/ask.js",
    ]
    public = "\n".join(read(path) for path in paths)
    for forbidden in (
        "早就解过",
        "已经把它研究透",
        "骨子里常是同一套规律",
        "能照着做的清单",
        "数学结构相同的成熟解法",
        "把别的学科的成熟解法借到你的问题上",
        "骨子里常是同一道数学题",
        "经过 AI 多轮评审的高质量跨域结构同构",
        "结构相同、但领域不同",
        "和你结构相同的真实现象",
        "是同一种结构",
        "本质上和<strong>放射性衰变 / 药物代谢</strong>是一回事",
        "结构相同的现象（其他领域）",
    ):
        assert forbidden not in public


def test_newsletter_frequency_and_candidate_copy_are_consistent() -> None:
    index = read("web/frontend/index.html")
    newsletter = read("web/frontend/assets/js/newsletter.js")
    thank_you = read("web/frontend/thank-you.html")
    public = "\n".join((index, newsletter, thank_you))

    for forbidden in (
        "每周一封",
        "每周 1 封",
        "每周日",
        "下个周日",
        "下周二",
        "周二早晨",
        "一周后",
        "新发现的跨域结构同构",
    ):
        assert forbidden not in public

    assert "有经复核的研究更新时会通知你" in index
    assert "不定期研究更新" in newsletter
    assert "公开负结果" in newsletter
    assert "不承诺固定频率" in thank_you
    assert "经复核" in thank_you


def test_tools_hub_exposes_exactly_eight_supported_public_tools() -> None:
    tools = read("web/frontend/tools.html")
    index = read("web/frontend/index.html")
    about = read("web/frontend/about.html")
    public = "\n".join((tools, index, about))

    assert tools.count('class="tool-card"') == 8
    assert 'href="/insights"' not in tools
    assert "8 个公开工具" in tools
    assert "8 个公开工具" in index
    assert "8 个公开工具" in about
    assert "9 个工具" not in public


def test_index_and_navigation_name_the_queue_as_candidates() -> None:
    index = read("web/frontend/index.html")
    ui = json.loads(read("web/frontend/assets/data/i18n/ui.json"))
    assert "23 组候选跨域模式" in index
    assert "39 个优先核查候选" in index
    assert "等待来源复核和实证检验" in index
    assert ui["nav.discoveries"] == {
        "zh": "候选发现",
        "en": "Candidate discoveries",
    }


def test_learn_no_script_fallback_matches_authoritative_i18n_copy() -> None:
    learn = read("web/frontend/learn.html")
    content = json.loads(read("web/frontend/assets/data/i18n/content.json"))
    for card in (1, 2, 3):
        for field in ("title", "sample", "value"):
            key = f"page.home.usecases.card{card}.{field}"
            assert content[key]["zh"] in learn, key


def test_connections_call_similarity_a_candidate_not_identity() -> None:
    html = read("web/frontend/connections.html")
    script = read("web/frontend/assets/js/connections.js")
    assert "结构指纹相近、但领域不同" in html
    assert "不能证明双方具有同一机制" in html
    assert "结构指纹相近、但领域不同" in script


def test_current_api_and_privacy_docs_match_the_account_product() -> None:
    api = read("docs/api.md")
    api_index = read("docs/api/index.md")
    privacy = read("docs/privacy-policy.md")
    phase_privacy = read("web/phase-detector/app/privacy/page.tsx")
    phase_about = read("web/phase-detector/app/about/page.tsx")

    for stale in (
        "always `123456`",
        "we don't have user accounts yet",
        "Mock checkout entries",
        "GET /api/privacy/export?email=",
        "DELETE /api/privacy/delete?email=",
        "riazward110@gmail.com",
    ):
        assert stale not in privacy
    assert "/api/me/export" in privacy
    assert "/api/me/delete" in privacy
    assert "410 Gone" in privacy
    assert "hello@bytedance.city" in privacy

    combined_api = f"{api}\n{api_index}"
    for stale in (
        "Live docs:",
        "Swagger UI served by FastAPI",
        "A-grade structural discoveries",
        "Stripe checkout mock (pre-PMF)",
        "All endpoints accept anonymous traffic",
        "To request a token, open an issue",
    ):
        assert stale not in combined_api
    assert "openapi.json" in combined_api
    assert "Production" in combined_api and "410 Gone" in combined_api
    assert "candidate" in combined_api.lower()

    assert "/api/privacy/export" not in phase_privacy
    assert "/api/privacy/delete" not in phase_privacy
    assert "https://beta.structural.bytedance.city/reports" in phase_privacy
    assert "riazward110@gmail.com" not in phase_about
    assert phase_about.count("hello@bytedance.city") >= 2


def test_favorites_limit_never_promises_an_unavailable_upgrade() -> None:
    backend = read("web/backend/api/favorites.py")
    button = read("web/phase-detector/components/FavoriteButton.tsx")

    for stale in ("upgrade for more", "Upgrade for more", "升级后可继续"):
        assert stale not in backend
        assert stale not in button
    assert "Remove an item before adding another" in backend
    assert "已达收藏上限，请移除一项后再试" in button
