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
def test_stress_test_submit_shows_screening_outcome_and_correspondences(page: Page):
    """A real claim renders a candidate-only screen, never a hard verdict."""
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "我们是中国版的 Notion")
    page.click("#stress-submit")
    # Result block appears once /api/stress-test resolves.
    expect(page.locator("#stress-result")).to_be_visible(timeout=45000)
    badge = page.locator("#stress-verdict-badge")
    expect(badge).to_be_visible()
    badge_text = badge.inner_text()
    assert "内部模型筛查" in badge_text
    assert any(label in badge_text for label in (
        "本轮未找到致命断点", "本轮发现关键断点", "取决于前提条件",
    ))
    assert not any(value in badge_text for value in ("PASS", "FAIL", "CONDITIONAL"))
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
def test_stress_test_candidate_reference_block_graceful(page: Page):
    """The KB candidate block either shows with real content or stays hidden.

    A candidate may legitimately be absent. When present it must carry a
    record name, a falsifiable comparison note and a /phenomenon link.
    """
    page.goto(f"{BASE}/stress-test")
    page.fill("#stress-claim", "这次 AI 泡沫和 2000 年互联网泡沫一样")
    page.click("#stress-submit")
    expect(page.locator("#stress-result")).to_be_visible(timeout=45000)
    prec = page.locator("#stress-precedent")
    if prec.is_visible():
        name = page.locator("#stress-precedent-name").inner_text().strip()
        failure = page.locator("#stress-precedent-failure").inner_text().strip()
        assert len(name) > 0, "candidate should name a KB record"
        assert len(failure) > 0, "candidate should explain what to verify"
        href = page.locator("#stress-precedent-link").get_attribute("href") or ""
        assert href.startswith("/phenomenon/"), f"bad precedent link: {href!r}"
