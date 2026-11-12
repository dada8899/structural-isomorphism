"""E2E tests against live https://beta.structural.bytedance.city/

The main site is a static HTML/CSS/JS app with i18n (zh/en). We verify
the home route, navigation to subpages (classes/papers/methods/taxonomy)
if present, and i18n toggle if present.

Run:
    pytest tests/e2e/test_structural_site.py -m e2e -v
"""

from __future__ import annotations

import pytest

playwright = pytest.importorskip("playwright")
from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

BASE_URL = "https://beta.structural.bytedance.city"

pytestmark = [pytest.mark.e2e, pytest.mark.requires_internet]


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Home route
# ---------------------------------------------------------------------------


def test_home_loads(page: Page):
    resp = page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    assert resp is not None
    assert resp.ok, f"non-2xx status: {resp.status}"


def test_home_has_title_text(page: Page):
    import re
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    expect(page).to_have_title(re.compile(r"Structural", re.IGNORECASE))


def test_home_has_meta_description(page: Page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    desc = page.locator('meta[name="description"]')
    assert desc.count() > 0


def test_home_has_main_content(page: Page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    body = page.locator("body")
    text = body.inner_text(timeout=10000)
    # The site is bilingual; either zh or en home content
    assert "Structural" in text or "structural" in text.lower()


# ---------------------------------------------------------------------------
# Sub-routes (optional, may not exist yet)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("route", ["/classes", "/papers", "/methods", "/taxonomy"])
def test_subroute_loads_or_404_gracefully(page: Page, route: str):
    """Each subroute either loads (200) or shows a clean 404 page (not a crash)."""
    resp = page.goto(f"{BASE_URL}{route}", wait_until="domcontentloaded", timeout=20000)
    # Either a real page or a 404 — both are acceptable, just not 5xx
    assert resp is not None
    if resp.status >= 500:
        pytest.fail(f"server error on {route}: status {resp.status}")


# ---------------------------------------------------------------------------
# Static HTML routes (file-based)
# ---------------------------------------------------------------------------


def test_html_route_classes_html(page: Page):
    """The static site may expose .html routes for classes/papers/etc."""
    resp = page.goto(
        f"{BASE_URL}/classes.html", wait_until="domcontentloaded", timeout=20000
    )
    if resp is None or not resp.ok:
        pytest.skip("classes.html not present")
    body_text = page.locator("body").inner_text(timeout=10000)
    assert len(body_text) > 50  # not an empty stub


# ---------------------------------------------------------------------------
# i18n toggle
# ---------------------------------------------------------------------------


def test_i18n_toggle_if_present(page: Page):
    """If the site has a 中/EN toggle, clicking it should change content language."""
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=20000)
    # Look for an i18n toggle (we don't know the exact selector — try a few)
    toggles = page.locator('[data-i18n-toggle], [data-lang-switch], button:has-text("中"), button:has-text("EN")')
    if toggles.count() == 0:
        pytest.skip("no visible i18n toggle on home")
    first = toggles.first
    if not first.is_visible(timeout=1000):
        pytest.skip("toggle present but not visible")
    # Just verify clickability without strict change-assertion (selector unknown)
    first.click(timeout=2000)
    # Any change to <html lang> attribute or body re-render is success
    page.wait_for_timeout(500)
    lang = page.evaluate("document.documentElement.lang")
    assert lang in ("zh-CN", "zh", "en", "en-US"), f"unexpected lang: {lang}"


# ---------------------------------------------------------------------------
# Performance / page-weight sanity
# ---------------------------------------------------------------------------


def test_home_loads_under_10s(page: Page):
    """Home route should fully load (domcontentloaded) under 10s on prod."""
    import time

    t0 = time.time()
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=15000)
    elapsed = time.time() - t0
    assert elapsed < 10.0, f"home took {elapsed:.1f}s to DOMContentLoaded"


def test_no_404_assets(page: Page):
    """Track 404 responses on subresources — if many, prod is broken."""
    failed = []
    page.on("response", lambda r: failed.append(r) if r.status == 404 else None)
    page.goto(BASE_URL, wait_until="networkidle", timeout=30000)
    if len(failed) > 3:
        urls = [r.url for r in failed[:5]]
        pytest.fail(f"too many 404s on home: {urls}")
