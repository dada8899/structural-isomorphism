"""W6-D (session #7 P1 backlog): mobile first-fold LCP < 2.5s.

Measures Largest Contentful Paint on the beta production home page at a
375×667 viewport (iPhone SE-ish). Asserts LCP < 2500ms — Google CWV
"good" threshold.

The page deploys with W6-D preloads (Noto Serif SC 600 + Inter 400) +
plausible preconnect to bring the LCP element (`.ask-empty__tagline`)
in well under target.

Run:
    cd web/tests/e2e
    pytest test_mobile_lcp.py -v
"""
from __future__ import annotations

import pytest


BASE = "https://beta.structural.bytedance.city"

# CWV LCP "good" threshold (Google). Anything <2500ms passes.
LCP_BUDGET_MS = 2500


def _measure_lcp(url: str, viewport: dict, browser) -> dict:
    """Open `url` on a fresh context at `viewport`, return LCP entry dict.

    Returns: {"startTime": ms, "size": px², "element": "TAG.class"}
    Raises pytest.fail if no LCP entry was captured within 8s.
    """
    context = browser.new_context(viewport=viewport)
    page = context.new_page()
    try:
        page.goto(url, wait_until="load")
        # The LCP event can land *after* `load`; give the page a settle
        # window similar to what Chrome's CrUX collector uses (~3s).
        page.wait_for_timeout(3000)
        entries = page.evaluate(
            """() => new Promise((resolve) => {
                try {
                    const seen = performance.getEntriesByType('largest-contentful-paint');
                    if (seen && seen.length) {
                        resolve(seen.map(e => ({
                            startTime: e.startTime,
                            size: e.size,
                            element: e.element ? (e.element.tagName + '.' + (e.element.className || '')) : 'n/a'
                        })));
                        return;
                    }
                    const po = new PerformanceObserver((list) => {
                        const ent = list.getEntries();
                        if (ent && ent.length) {
                            resolve(ent.map(e => ({
                                startTime: e.startTime,
                                size: e.size,
                                element: e.element ? (e.element.tagName + '.' + (e.element.className || '')) : 'n/a'
                            })));
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

    if not entries or "error" in entries[0]:
        pytest.fail(f"failed to capture LCP entry for {url}: {entries!r}")
    # Pick the LATEST (largest) candidate — LCP can fire multiple times,
    # and the final entry is the one CWV uses.
    return entries[-1]


@pytest.fixture(scope="module")
def chromium_browser(playwright_instance):
    """Reuse the session-scoped sync_playwright from conftest.py.

    Spawning a second sync_playwright() in-process collides with the one
    started by the `page` fixture in conftest — playwright errors out
    with "Sync API inside the asyncio loop".
    """
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


def test_mobile_home_lcp_under_2500ms(chromium_browser):
    """Mobile (375×667) home page LCP must beat the 2500ms CWV "good" gate."""
    entry = _measure_lcp(
        f"{BASE}/",
        viewport={"width": 375, "height": 667},
        browser=chromium_browser,
    )
    lcp_ms = int(entry["startTime"])
    element = entry.get("element", "n/a")
    print(
        f"[mobile lcp] startTime={lcp_ms}ms size={entry.get('size')}px² "
        f"element={element} budget={LCP_BUDGET_MS}ms"
    )
    assert lcp_ms < LCP_BUDGET_MS, (
        f"mobile LCP {lcp_ms}ms exceeds {LCP_BUDGET_MS}ms budget "
        f"(element={element}); see W6-D preload changes in index.html"
    )


def test_desktop_home_lcp_under_2500ms(chromium_browser):
    """Sanity: desktop (1280×800) home page LCP also under budget.

    Desktop is usually faster than mobile so this is a freebie regression
    guard — if we ever regress the LCP element to something behind a slow
    asset, desktop will trip first.
    """
    entry = _measure_lcp(
        f"{BASE}/",
        viewport={"width": 1280, "height": 800},
        browser=chromium_browser,
    )
    lcp_ms = int(entry["startTime"])
    print(f"[desktop lcp] startTime={lcp_ms}ms element={entry.get('element', 'n/a')}")
    assert lcp_ms < LCP_BUDGET_MS, (
        f"desktop LCP {lcp_ms}ms exceeds {LCP_BUDGET_MS}ms budget"
    )
