"""Session #18 e2e tests — A1 method-search (/apply page).

Run: pytest web/tests/e2e/test_method_search.py -v

@pytest.mark.post_deploy — only pass once Session #18 ships apply.html.
The orchestrator runs these; in baseline phase skip via `-k "not post_deploy"`.
"""
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, expect

BASE = "https://beta.structural.bytedance.city"


@pytest.mark.post_deploy
def test_apply_page_loads(page: Page):
    """/apply should show the intro + method input form."""
    page.goto(f"{BASE}/apply")
    expect(page.locator(".apply-intro__title")).to_be_visible()
    expect(page.locator("#apply-input")).to_be_visible()
    expect(page.locator("#apply-submit")).to_be_visible()


@pytest.mark.post_deploy
def test_apply_example_chips_present(page: Page):
    """Example chips should be rendered for one-click entry."""
    page.goto(f"{BASE}/apply")
    chips = page.locator(".apply-chip").all()
    assert len(chips) >= 3, "should have at least 3 example chips"


@pytest.mark.post_deploy
def test_apply_short_input_rejected(page: Page):
    """Submitting < 4 chars should surface an inline error, no result block."""
    page.goto(f"{BASE}/apply")
    page.fill("#apply-input", "ab")
    page.click("#apply-submit")
    expect(page.locator(".apply-status--error")).to_be_visible()
    expect(page.locator("#apply-result")).to_be_hidden()


@pytest.mark.post_deploy
def test_apply_submit_shows_signature_and_candidates(page: Page):
    """A real method submit renders an unverified signature + candidates."""
    page.goto(f"{BASE}/apply")
    page.fill("#apply-input", "梯度下降——在带噪声的反馈下沿局部信息迭代逼近最优解")
    page.click("#apply-submit")
    # Result block appears once /api/method/apply resolves.
    expect(page.locator("#apply-result")).to_be_visible(timeout=30000)
    expect(page.locator(".apply-signature__text")).to_be_visible()
    cards = page.locator(".apply-card")
    assert cards.count() >= 1, "expected at least one match card"
    rank = cards.first.locator(".apply-card__rel").inner_text()
    assert "候选 #" in rank and "%" not in rank


@pytest.mark.post_deploy
def test_apply_card_links_to_analyze(page: Page):
    """The 深入分析 link keeps method text in a local handoff."""
    page.goto(f"{BASE}/apply")
    page.fill("#apply-input", "模拟退火——以逐渐降低的随机扰动跳出局部最优")
    page.click("#apply-submit")
    expect(page.locator("#apply-result")).to_be_visible(timeout=30000)
    href = page.locator(".apply-card__link").first.get_attribute("href")
    assert href and href.startswith("/analyze?")
    query = parse_qs(urlparse(href).query)
    assert len(query.get("id", [])) == 1
    assert len(query.get("handoff", [])) == 1
    assert "q" not in query and "b_id" not in query and "text_a" not in query
