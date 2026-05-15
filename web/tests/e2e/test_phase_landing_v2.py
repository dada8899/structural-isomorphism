"""W10-C alpha-screener landing v2 — e2e acceptance test.

Asserts the new editorial landing renders the contractual blocks:
  - Hero headline ("Daily structural signals from 1000+ public companies.")
  - 6 explore cards (data-testid="explore-card")
  - 3 trust signals (anchored on "Receipts" section heading)
  - 2 hero CTAs (primary + secondary; data-testid="cta-primary"/"cta-secondary")
  - FAQ accordion has at least 7 items
  - Console clean on initial load (no JS errors)

Performance budgets:
  - Desktop LCP < 2500ms
  - Mobile  LCP < 2500ms

Run modes:
  - Default (PHASE_BASE unset)  → tests run against live prod
                                  https://phase.bytedance.city
  - PHASE_BASE=http://localhost:3718 → run against locally-booted
                                  `next start -p 3718` (CI/local dev).

The default targets prod so that test failures expose actual regressions
in the deployed landing — same convention as test_mobile_lcp.py.
"""
from __future__ import annotations

import os
import pytest


BASE = os.environ.get("PHASE_BASE", "https://phase.bytedance.city").rstrip("/")

# Largest Contentful Paint budget — Google CWV "good" threshold (2500ms).
LCP_BUDGET_MS = 2500


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def chromium_browser(playwright_instance):
    """Reuse session-scoped playwright fixture from conftest.py."""
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


def _measure_lcp(url: str, viewport: dict, browser) -> int:
    """Return LCP startTime in ms for `url` at `viewport`.

    Uses PerformanceObserver with `buffered: true` so we capture LCP
    candidates that fired before our observer attached.
    """
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    try:
        page.goto(url, wait_until="load", timeout=30000)
        page.wait_for_timeout(2500)
        entries = page.evaluate(
            """() => new Promise((resolve) => {
                try {
                    const seen = performance.getEntriesByType('largest-contentful-paint');
                    if (seen && seen.length) {
                        resolve(seen.map(e => ({ startTime: e.startTime, size: e.size })));
                        return;
                    }
                    const po = new PerformanceObserver((list) => {
                        const ent = list.getEntries();
                        if (ent && ent.length) {
                            resolve(ent.map(e => ({ startTime: e.startTime, size: e.size })));
                        }
                    });
                    po.observe({type: 'largest-contentful-paint', buffered: true});
                    setTimeout(() => resolve([]), 4000);
                } catch (e) {
                    resolve([{error: String(e)}]);
                }
            })"""
        )
    finally:
        context.close()
    if not entries or (entries and "error" in entries[0]):
        pytest.fail(f"failed to capture LCP entry for {url}: {entries!r}")
    return int(entries[-1]["startTime"])


# ---------------------------------------------------------------------------
# Structural assertions
# ---------------------------------------------------------------------------

def test_hero_headline_renders(page):
    """Hero H1 must surface the cross-domain-universality positioning line.

    Session #12 (W16 pre-launch audit) flipped the headline from
    "Daily structural signals" → "The same math that explains earthquakes,
    applied to 1000+ public companies." so visitors don't pattern-match to
    'alpha screener' before they see the NULL backtest framing.
    """
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    headline = page.locator('[data-testid="hero-headline"]').first
    headline.wait_for(state="visible", timeout=5000)
    text = headline.inner_text()
    assert "1000+" in text, f"hero missing 1000+ marker: {text!r}"
    assert "public companies" in text, f"hero missing 'public companies': {text!r}"
    assert "earthquakes" in text.lower() or "universality" in text.lower(), (
        f"hero must surface the cross-domain framing, got: {text!r}"
    )


def test_hero_eyebrow_present(page):
    """Research-preview eyebrow above the H1."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    eyebrow = page.locator('[data-testid="hero-eyebrow"]').first
    eyebrow.wait_for(state="visible", timeout=5000)
    text = eyebrow.inner_text()
    assert "Research preview" in text or "研究预览" in text


def test_six_explore_cards_rendered(page):
    """The 'Recent flips' grid must surface 6 cards (real data, not faked)."""
    page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
    cards = page.locator('[data-testid="explore-card"]')
    cards.first.wait_for(state="visible", timeout=8000)
    count = cards.count()
    assert count == 6, f"expected 6 explore cards, got {count}"


def test_two_hero_ctas_work(page):
    """Primary CTA links to /companies, secondary to /methodology.

    Session #12 (W16 audit) demoted the tertiary "v0.1 NULL backtest"
    text-link out of the hero and changed the secondary CTA from the
    #how-it-works in-page anchor to /methodology so researchers landing
    cold get pulled into the science, not into another marketing scroll.
    """
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    primary = page.locator('[data-testid="cta-primary"]').first
    secondary = page.locator('[data-testid="cta-secondary"]').first
    primary.wait_for(state="visible", timeout=5000)
    secondary.wait_for(state="visible", timeout=5000)
    # Primary destination
    href = primary.get_attribute("href")
    assert href and ("/companies" in href), f"primary CTA href wrong: {href!r}"
    # Secondary destination (full page)
    sec_href = secondary.get_attribute("href")
    assert sec_href and ("/methodology" in sec_href), f"secondary CTA href wrong: {sec_href!r}"
    # Click primary, verify we end up on /companies
    primary.click()
    page.wait_for_url("**/companies", timeout=10000)


def test_trust_signals_present(page):
    """Trust signals row must surface 3 verifiable claims.

    Session #12 (W16 audit) renamed the eyebrow "Receipts · 凭证" →
    "Verifiable claims · 凭证" (English readers were parsing "Receipts" as
    slang) and the first card "Cross-domain validation" →
    "Within-class robustness" (scholar review flagged within-class
    aggregation being framed as cross-domain).
    """
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector("text=Verifiable claims", timeout=10000)
    # 3 card labels:
    page.wait_for_selector("text=Within-class robustness", timeout=10000)
    page.wait_for_selector("text=Honest backtest", timeout=10000)
    page.wait_for_selector("text=Open methodology", timeout=10000)


def test_faq_accordion_has_seven_items(page):
    """FAQ section must list 7 questions for trust/transparency coverage."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('[data-testid="faq-item"]', timeout=10000)
    items = page.locator('[data-testid="faq-item"]')
    count = items.count()
    assert count >= 7, f"FAQ must have >=7 items (covers investment / accuracy / etc), got {count}"


def test_console_clean_on_landing(page):
    """No JS console errors during initial render of /."""
    errors: list[str] = []
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda msg: errors.append(f"console.{msg.type}: {msg.text}") if msg.type == "error" else None,
    )
    page.goto(BASE + "/", wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(1500)
    # Filter out third-party network noise (plausible analytics blocked /
    # closed, favicon 404). We only fail on JS runtime errors that indicate
    # the page itself broke.
    real_errors = [
        e for e in errors
        if "plausible" not in e.lower()
        and "favicon" not in e.lower()
        and "net::err_blocked" not in e.lower()
        and "net::err_connection_closed" not in e.lower()
        and "net::err_failed" not in e.lower()
        and "failed to load resource" not in e.lower()
    ]
    assert not real_errors, f"console errors detected: {real_errors}"


def test_how_it_works_section_anchor(page):
    """Secondary CTA must scroll to a #how-it-works anchor that exists."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    anchor = page.locator("#how-it-works").first
    anchor.wait_for(state="attached", timeout=5000)
    # The section heading lives within.
    assert anchor.locator("text=没有黑盒").count() >= 1 or anchor.locator("text=How it works").count() >= 1


def test_waitlist_form_present(page):
    """Newsletter waitlist form is reused from the prior session and surfaced prominently."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    # WaitlistForm renders an email input + submit button (component contract from session #9).
    page.wait_for_selector('input[type="email"]', timeout=10000)
    inputs = page.locator('input[type="email"]')
    assert inputs.count() >= 1, "newsletter email input missing"


# ---------------------------------------------------------------------------
# Performance assertions
# ---------------------------------------------------------------------------

def test_mobile_landing_lcp_under_budget(chromium_browser):
    """Mobile (375×667) landing v2 LCP must beat the 2500ms CWV gate."""
    lcp_ms = _measure_lcp(
        BASE + "/", viewport={"width": 375, "height": 667}, browser=chromium_browser,
    )
    print(f"\n[lcp] mobile  / : {lcp_ms}ms (budget {LCP_BUDGET_MS}ms)")
    assert lcp_ms < LCP_BUDGET_MS, f"mobile LCP {lcp_ms}ms >= {LCP_BUDGET_MS}ms budget"


def test_desktop_landing_lcp_under_budget(chromium_browser):
    """Desktop (1280×800) landing v2 LCP must beat the 2500ms gate."""
    lcp_ms = _measure_lcp(
        BASE + "/", viewport={"width": 1280, "height": 800}, browser=chromium_browser,
    )
    print(f"\n[lcp] desktop / : {lcp_ms}ms (budget {LCP_BUDGET_MS}ms)")
    assert lcp_ms < LCP_BUDGET_MS, f"desktop LCP {lcp_ms}ms >= {LCP_BUDGET_MS}ms budget"
