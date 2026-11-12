"""Minimal Playwright checks for a locally served Phase build.

Set PHASE_TEST_BASE_URL to the current worktree's Next server. The test stays
skipped in static-only CI rather than accidentally validating stale production.
"""
import os

import pytest


playwright = pytest.importorskip("playwright")
from playwright.sync_api import sync_playwright  # noqa: E402


BASE_URL = os.getenv("PHASE_TEST_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="PHASE_TEST_BASE_URL is not set")


def test_desktop_and_mobile_main_product_journey_is_keyboard_accessible():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            desktop = browser.new_page(viewport={"width": 1280, "height": 900})
            desktop.goto(BASE_URL, wait_until="domcontentloaded")
            assert "Structural Labs · Phase" in desktop.locator("body").inner_text()
            boundary = desktop.get_by_test_id("phase-main-product-return")
            assert boundary.is_visible()
            assert boundary.get_attribute("href") == "https://beta.structural.bytedance.city"
            assert boundary.evaluate("el => el.getBoundingClientRect().height") >= 44
            boundary.focus()
            assert desktop.evaluate("document.activeElement?.dataset.testid") == "phase-main-product-return"

            for width in (320, 375, 390, 640, 1024, 1279):
                mobile = browser.new_page(viewport={"width": width, "height": 844})
                mobile.goto(BASE_URL, wait_until="domcontentloaded")
                assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                compact_boundary = mobile.get_by_test_id("phase-main-product-return-mobile")
                assert compact_boundary.is_visible()
                assert compact_boundary.evaluate("el => el.getBoundingClientRect().height") >= 44
                boundary_height = mobile.get_by_test_id("phase-product-boundary").evaluate(
                    "el => el.getBoundingClientRect().height"
                )
                header_height = mobile.locator("header").evaluate(
                    "el => el.getBoundingClientRect().height"
                )
                assert boundary_height <= 64
                assert boundary_height + header_height <= 125

                toggle = mobile.get_by_test_id("mobile-nav-toggle")
                toggle.click()
                drawer = mobile.locator("#mobile-nav-drawer")
                assert drawer.is_visible()
                assert mobile.locator("main").get_attribute("inert") == ""
                assert mobile.locator("main").get_attribute("aria-hidden") == "true"
                focusable = drawer.locator(
                    'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
                )
                first = focusable.first
                last = focusable.last
                assert focusable.evaluate_all(
                    "nodes => nodes.every(node => node.getBoundingClientRect().height >= 44)"
                )
                assert first.evaluate("el => document.activeElement === el")
                first.press("Shift+Tab")
                assert last.evaluate("el => document.activeElement === el")
                last.press("Tab")
                assert first.evaluate("el => document.activeElement === el")
                main_link = drawer.get_by_role("menuitem", name="返回 Structural 主产品", exact=False)
                assert main_link.is_visible()
                assert main_link.evaluate("el => el.getBoundingClientRect().height") >= 44
                mobile.keyboard.press("Escape")
                assert not drawer.is_visible()
                assert mobile.locator("main").get_attribute("inert") is None
                mobile.wait_for_function(
                    "document.activeElement?.dataset.testid === 'mobile-nav-toggle'",
                    timeout=500,
                )
                assert mobile.evaluate("document.activeElement?.dataset.testid") == "mobile-nav-toggle"

                mobile.goto(f"{BASE_URL}/privacy", wait_until="domcontentloaded")
                assert mobile.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                assert mobile.locator("article code").evaluate_all(
                    "nodes => nodes.every(node => node.getBoundingClientRect().right <= window.innerWidth)"
                )
                mobile.close()
        finally:
            browser.close()
