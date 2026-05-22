"""Session ***REMOVED***18 e2e tests — C2 structural lint (/lint page).

Run: pytest web/tests/e2e/test_struct_lint.py -v

@pytest.mark.post_deploy — only pass once Session ***REMOVED***18 ships lint.html.
The orchestrator runs these; in baseline phase skip via `-k "not post_deploy"`.
"""
import pytest
from playwright.sync_api import Page, expect

BASE = "https://beta.structural.bytedance.city"

***REMOVED*** /api/struct-lint is a single synchronous LLM call; measured ~165s online.
***REMOVED*** Allow generous headroom so a slow-but-healthy response is not a test failure.
LINT_RESULT_TIMEOUT_MS = 210000

_SAMPLE_DOC = (
    "我们的增长方案：竞品 X 靠裂变拉新做到了百万用户，我们照搬同一套裂变机制也能做到。"
    "只要把补贴预算提上去，用户量就会自然增长，用户量上来之后收入也会随之上来。"
    "团队现在 5 个人，扩到 20 人后产能会翻 4 倍，所以三个月内就能上线全部功能。"
)


@pytest.mark.post_deploy
def test_lint_page_loads(page: Page):
    """/lint should show the intro + document textarea + submit button."""
    page.goto(f"{BASE}/lint")
    expect(page.locator(".lint-input__title")).to_be_visible()
    expect(page.locator("***REMOVED***lint-textarea")).to_be_visible()
    expect(page.locator("***REMOVED***lint-submit")).to_be_visible()


@pytest.mark.post_deploy
def test_lint_empty_input_rejected(page: Page):
    """Submitting an empty document surfaces an inline error, no result."""
    page.goto(f"{BASE}/lint")
    page.click("***REMOVED***lint-submit")
    expect(page.locator("***REMOVED***lint-input-error")).to_be_visible()
    expect(page.locator("***REMOVED***lint-result")).to_be_hidden()


@pytest.mark.post_deploy
def test_lint_char_counter_updates(page: Page):
    """Typing into the textarea updates the character counter."""
    page.goto(f"{BASE}/lint")
    page.fill("***REMOVED***lint-textarea", "测试文档内容")
    expect(page.locator("***REMOVED***lint-charcount")).to_contain_text("6 / 20000")


@pytest.mark.post_deploy
def test_lint_submit_shows_summary_and_claims(page: Page):
    """A real document submit renders the summary banner + claim cards."""
    page.goto(f"{BASE}/lint")
    page.fill("***REMOVED***lint-textarea", _SAMPLE_DOC)
    page.click("***REMOVED***lint-submit")
    ***REMOVED*** Result block appears once /api/struct-lint resolves.
    expect(page.locator("***REMOVED***lint-result")).to_be_visible(timeout=LINT_RESULT_TIMEOUT_MS)
    expect(page.locator("***REMOVED***lint-summary-text")).not_to_be_empty()
    cards = page.locator(".lint-claim")
    assert cards.count() >= 1, "expected at least one claim card"


@pytest.mark.post_deploy
def test_lint_claim_card_has_risk_tag(page: Page):
    """Each claim card should carry a risk tag and a quote block."""
    page.goto(f"{BASE}/lint")
    page.fill("***REMOVED***lint-textarea", _SAMPLE_DOC)
    page.click("***REMOVED***lint-submit")
    expect(page.locator("***REMOVED***lint-result")).to_be_visible(timeout=LINT_RESULT_TIMEOUT_MS)
    first = page.locator(".lint-claim").first
    expect(first.locator(".lint-tag--type")).to_be_visible()
    expect(first.locator(".lint-claim__quote")).to_be_visible()
    risk_tag = first.locator(
        ".lint-tag--risk-high, .lint-tag--risk-medium, .lint-tag--risk-low"
    )
    assert risk_tag.count() >= 1, "expected a risk-level tag on the claim card"
