"""Session #18 e2e tests — feature E structural stress-test (/stress-test page).

Run: pytest web/tests/e2e/test_stress_test.py -v

@pytest.mark.post_deploy — only pass once Session #18 ships stress-test.html.
The orchestrator runs these; in baseline phase skip via `-k "not post_deploy"`.
"""
import pytest
from playwright.sync_api import Page, expect

BASE = "https://beta.structural.bytedance.city"


@pytest.mark.post_deploy
def test_stress_test_page_loads(page: Page):
    """/stress-test should show the intro + claim input form."""
    page.goto(f"{BASE}/stress-test")
    expect(page.locator(".stress-intro__title")).to_be_visible()
    expect(page.locator("#stress-claim")).to_be_visible()
    expect(page.locator("#stress-submit")).to_be_visible()


@pytest.mark.post_deploy
def test_stress_test_example_chips_present(page: Page):
    """Example chips should be rendered for one-click entry."""
    page.goto(f"{BASE}/stress-test")
    chips = page.locator(".stress-chip").all()
    assert len(chips) >= 3, "should have at least 3 example chips"


@pytest.mark.post_deploy
def test_stress_test_chip_fills_input(page: Page):
    """Clicking an example chip fills the textarea (no auto-submit)."""
    page.goto(f"{BASE}/stress-test")
    page.locator(".stress-chip").first.click()
    value = page.locator("#stress-claim").input_value()
    assert len(value) > 4, "chip click should populate the claim textarea"
    expect(page.locator("#stress-result")).to_be_hidden()


@pytest.mark.post_deploy
def test_stress_test_short_input_rejected(page: Page):
    """Submitting < 4 chars should surface an inline error, no result block."""
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "ab")
    page.click("#stress-submit")
    expect(page.locator("#stress-error")).to_be_visible()
    expect(page.locator("#stress-result")).to_be_hidden()


@pytest.mark.post_deploy
def test_stress_test_submit_shows_verdict_and_correspondences(page: Page):
    """A real claim submit should render the verdict badge + correspondences."""
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "我们是中国版的 Notion")
    page.click("#stress-submit")
    # Result block appears once /api/stress-test resolves.
    expect(page.locator("#stress-result")).to_be_visible(timeout=45000)
    badge = page.locator("#stress-verdict-badge")
    expect(badge).to_be_visible()
    badge_text = badge.inner_text()
    assert any(v in badge_text for v in ("PASS", "FAIL", "CONDITIONAL")), (
        f"verdict badge missing enum: {badge_text!r}"
    )
    # At least the source / target pair must render.
    expect(page.locator("#stress-source")).to_be_visible()
    expect(page.locator("#stress-target")).to_be_visible()


@pytest.mark.post_deploy
def test_stress_test_weakest_link_rendered(page: Page):
    """The weakest-link block should render after a successful test."""
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "这次 AI 泡沫和 2000 年互联网泡沫一样")
    page.click("#stress-submit")
    expect(page.locator("#stress-result")).to_be_visible(timeout=45000)
    weakest = page.locator("#stress-weakest-text")
    expect(weakest).to_be_visible()
    assert len(weakest.inner_text().strip()) > 0, "weakest link should have text"


@pytest.mark.post_deploy
def test_stress_test_precedent_block_graceful(page: Page):
    """The KB-precedent block either shows with real content or stays hidden.

    Precedent depends on a KB search hit clearing the relevance floor — it
    may legitimately be absent. When present it must carry a phenomenon
    name + a failure-precedent sentence + a /phenomenon link.
    """
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "这次 AI 泡沫和 2000 年互联网泡沫一样")
    page.click("#stress-submit")
    expect(page.locator("#stress-result")).to_be_visible(timeout=45000)
    prec = page.locator("#stress-precedent")
    if prec.is_visible():
        name = page.locator("#stress-precedent-name").inner_text().strip()
        failure = page.locator("#stress-precedent-failure").inner_text().strip()
        assert len(name) > 0, "precedent should name a phenomenon"
        assert len(failure) > 0, "precedent should explain how it broke"
        href = page.locator("#stress-precedent-link").get_attribute("href") or ""
        assert href.startswith("/phenomenon/"), f"bad precedent link: {href!r}"
