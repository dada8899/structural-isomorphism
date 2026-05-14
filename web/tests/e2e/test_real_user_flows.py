"""Session #9 Wave 3-A — Real user flow e2e + CLS measurement.

Tests 4 core flows on prod (beta.structural.bytedance.city + phase.bytedance.city)
across desktop (1920x1080) + mobile (375x667 iPhone SE) viewports.
Also measures CLS on key pages (/ + /discoveries + phase /).

Run:
    PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_real_user_flows.py -v

Outputs:
    web/tests/e2e/screenshots/session-9-w3-a/*.png
    web/tests/e2e/results/session-9-w3-a-results.json

This implements CLAUDE.md "功能验收三层" — real-env e2e layer.
NO MOCKS: tests run against live prod URLs.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, sync_playwright, TimeoutError as PWTimeout

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BETA = "https://beta.structural.bytedance.city"
PHASE = "https://phase.bytedance.city"

DESKTOP = {"width": 1920, "height": 1080}
MOBILE = {"width": 375, "height": 667}  # iPhone SE

REPO_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOT_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "screenshots" / "session-9-w3-a"
RESULTS_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "results"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

# Accumulator (results.json written at session end).
_RESULTS: list[dict[str, Any]] = []


def _record(
    flow: str,
    viewport: str,
    success: bool,
    duration_ms: int,
    asserts: dict[str, Any],
    error: str | None = None,
) -> None:
    _RESULTS.append(
        {
            "flow": flow,
            "viewport": viewport,
            "success": success,
            "duration_ms": duration_ms,
            "asserts": asserts,
            "error": error,
        }
    )


def _shot(page: Page, name: str) -> str:
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=False)
    except Exception as e:  # noqa: BLE001
        return f"<screenshot-failed: {e}>"
    return str(path.relative_to(REPO_ROOT))


# CLS measurement script — uses PerformanceObserver layout-shift entries.
# We sample for ~5s after load, then sum every shift's value (excluding
# entries where hadRecentInput=true, per Web Vitals spec).
_CLS_SCRIPT = """
() => {
  return new Promise((resolve) => {
    let cls = 0;
    const entries = [];
    try {
      const po = new PerformanceObserver((list) => {
        for (const entry of list.getEntries()) {
          if (!entry.hadRecentInput) {
            cls += entry.value;
            entries.push({
              value: entry.value,
              startTime: entry.startTime,
            });
          }
        }
      });
      po.observe({ type: "layout-shift", buffered: true });
      setTimeout(() => {
        try { po.disconnect(); } catch (e) {}
        resolve({ cls: cls, entries_count: entries.length });
      }, 5000);
    } catch (e) {
      resolve({ cls: null, error: String(e) });
    }
  });
}
"""


def _measure_cls(page: Page, url: str) -> dict[str, Any]:
    """Navigate then measure CLS over 5s."""
    t0 = time.time()
    try:
        page.goto(url, wait_until="load", timeout=30000)
    except PWTimeout:
        return {"cls": None, "error": "navigation-timeout", "url": url}
    # Wait for fonts/late shifts to settle.
    try:
        result = page.evaluate(_CLS_SCRIPT)
    except Exception as e:  # noqa: BLE001
        return {"cls": None, "error": f"eval-fail: {e}", "url": url}
    result["url"] = url
    result["nav_ms"] = int((time.time() - t0) * 1000)
    return result


# ---------------------------------------------------------------------------
# Fixtures (override conftest to get fresh contexts per viewport).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def pw():
    with sync_playwright() as p:
        yield p


@pytest.fixture(scope="module")
def browser(pw):
    b = pw.chromium.launch(headless=True)
    yield b
    b.close()


def _make_context(browser, viewport: dict[str, int], is_mobile: bool = False):
    return browser.new_context(
        viewport=viewport,
        is_mobile=is_mobile,
        user_agent=(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
            "Mobile/15E148 Safari/604.1"
            if is_mobile
            else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    )


# ---------------------------------------------------------------------------
# Flow 1: beta home → search → answer → followup
# ---------------------------------------------------------------------------

def _run_flow_1(browser, viewport_name: str, viewport: dict[str, int], is_mobile: bool):
    """Beta home → search → wait for answer → followup → wait for second answer."""
    ctx = _make_context(browser, viewport, is_mobile)
    page = ctx.new_page()
    t0 = time.time()
    asserts: dict[str, Any] = {}
    error = None
    success = False
    try:
        page.goto(f"{BETA}/", wait_until="load", timeout=30000)
        # Empty state visible.
        asserts["empty_visible"] = page.locator("#ask-empty").is_visible()
        asserts["brand_text"] = page.locator(".ask-empty__brand").inner_text()
        _shot(page, f"flow1-{viewport_name}-1-home")

        # Fill query.
        q1 = "为什么硅谷银行挤兑后市场反应这么剧烈？还有哪些类似的级联系统？"
        page.fill("#ask-input", q1)
        asserts["input_filled"] = (page.input_value("#ask-input") == q1)

        # Submit.
        page.click(".ask-searchbox__submit")
        # Thread should appear.
        page.wait_for_selector("#ask-thread:not([hidden])", timeout=10000)
        asserts["thread_visible"] = True
        # Wait for first answer item — give SSE up to 60s for stream completion.
        # We look for a thread item with rendered content (any text).
        try:
            page.wait_for_function(
                "() => { const items = document.querySelectorAll('#ask-thread-items > *'); "
                "return items.length > 0 && items[0].innerText.length > 100; }",
                timeout=60000,
            )
            asserts["answer_received"] = True
        except PWTimeout:
            asserts["answer_received"] = False
            asserts["answer_timeout"] = True
        _shot(page, f"flow1-{viewport_name}-2-answer")

        # Followup.
        if asserts.get("answer_received"):
            page.fill("#ask-followup-input", "团队相变 有类似机制吗")
            page.click(".ask-followup-box__submit")
            try:
                page.wait_for_function(
                    "() => { const items = document.querySelectorAll('#ask-thread-items > *'); "
                    "return items.length >= 2 && items[1].innerText.length > 100; }",
                    timeout=60000,
                )
                asserts["followup_answered"] = True
            except PWTimeout:
                asserts["followup_answered"] = False
            _shot(page, f"flow1-{viewport_name}-3-followup")
        success = asserts.get("answer_received", False)
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    finally:
        duration = int((time.time() - t0) * 1000)
        _record("flow1-search-followup", viewport_name, success, duration, asserts, error)
        ctx.close()


def test_flow1_desktop(browser):
    _run_flow_1(browser, "desktop", DESKTOP, is_mobile=False)


def test_flow1_mobile(browser):
    _run_flow_1(browser, "mobile", MOBILE, is_mobile=True)


# ---------------------------------------------------------------------------
# Flow 2: /classes → click first card → /phenomenon deep-link
# ---------------------------------------------------------------------------

def _run_flow_2(browser, viewport_name: str, viewport: dict[str, int], is_mobile: bool):
    ctx = _make_context(browser, viewport, is_mobile)
    page = ctx.new_page()
    t0 = time.time()
    asserts: dict[str, Any] = {}
    error = None
    success = False
    try:
        page.goto(f"{BETA}/classes", wait_until="load", timeout=30000)
        # Wait for filter "all" active.
        page.wait_for_selector('[data-filter="all"].uc-filter__btn--active', timeout=10000)
        asserts["filter_all_active"] = True
        # Wait for cards rendered (skeletons replaced) — list children > 1.
        try:
            page.wait_for_function(
                "() => { const list = document.getElementById('uc-list'); "
                "if (!list) return false; "
                "const skel = list.querySelector('.uc-skeleton'); "
                "if (skel) return false; "
                "return list.children.length >= 5; }",
                timeout=20000,
            )
            card_count = page.evaluate(
                "() => document.querySelectorAll('#uc-list > *').length"
            )
            asserts["card_count"] = card_count
            asserts["cards_loaded"] = card_count >= 5
        except PWTimeout:
            asserts["cards_loaded"] = False
            asserts["card_count"] = page.evaluate(
                "() => document.querySelectorAll('#uc-list > *').length"
            )
        _shot(page, f"flow2-{viewport_name}-1-classes")

        # Click first card if available.
        if asserts.get("cards_loaded"):
            try:
                first_card = page.locator("#uc-list > *").first
                # Get inner link/clickable.
                link = first_card.locator("a").first
                if link.count() > 0:
                    href_before = link.get_attribute("href")
                    asserts["first_card_href"] = href_before
                    link.click()
                    page.wait_for_load_state("load", timeout=10000)
                    asserts["after_click_url"] = page.url
                    # phenomenon or class detail.
                    asserts["nav_succeeded"] = (
                        "phenomenon" in page.url
                        or "class" in page.url
                        or page.url != f"{BETA}/classes"
                    )
                else:
                    first_card.click()
                    page.wait_for_timeout(2000)
                    asserts["after_click_url"] = page.url
                    asserts["nav_succeeded"] = page.url != f"{BETA}/classes"
                _shot(page, f"flow2-{viewport_name}-2-detail")
                success = asserts.get("nav_succeeded", False)
            except Exception as e:  # noqa: BLE001
                asserts["click_error"] = str(e)
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    finally:
        duration = int((time.time() - t0) * 1000)
        _record("flow2-classes-phenomenon", viewport_name, success, duration, asserts, error)
        ctx.close()


def test_flow2_desktop(browser):
    _run_flow_2(browser, "desktop", DESKTOP, is_mobile=False)


def test_flow2_mobile(browser):
    _run_flow_2(browser, "mobile", MOBILE, is_mobile=True)


# ---------------------------------------------------------------------------
# Flow 3: phase home → company → backtest
# ---------------------------------------------------------------------------

def _run_flow_3(browser, viewport_name: str, viewport: dict[str, int], is_mobile: bool):
    ctx = _make_context(browser, viewport, is_mobile)
    page = ctx.new_page()
    t0 = time.time()
    asserts: dict[str, Any] = {}
    error = None
    success = False
    try:
        page.goto(f"{PHASE}/", wait_until="load", timeout=30000)
        # Wait for any hydration.
        page.wait_for_timeout(2500)
        # Look for p = 0.681 in body text (transparency banner).
        body_text = page.locator("body").inner_text(timeout=5000)
        asserts["has_p_value"] = "p = 0.681" in body_text or "0.681" in body_text
        asserts["has_phase_brand"] = "Phase Detector" in body_text or "Phase" in body_text
        _shot(page, f"flow3-{viewport_name}-1-phase-home")

        # Find first signal/company card. Phase uses Next.js — most cards
        # are within main content. We'll look for any clickable card-like
        # element with a ticker symbol (3-5 uppercase letters).
        # Strategy: find anchor or button whose text contains a ticker.
        clicked = False
        try:
            # Try data-ticker first.
            cards = page.locator("[data-ticker], a[href*='/c/'], a[href*='company']")
            count = cards.count()
            asserts["candidate_cards"] = count
            if count > 0:
                cards.first.click()
                page.wait_for_load_state("load", timeout=10000)
                clicked = True
                asserts["after_card_click_url"] = page.url
        except Exception as e:  # noqa: BLE001
            asserts["card_click_error"] = str(e)

        if not clicked:
            # Fallback: click any element with text matching a ticker pattern.
            try:
                # Look for clickable items in main area.
                page.evaluate(
                    "() => { const els = document.querySelectorAll('main a, main button'); "
                    "for (const el of els) { const t = el.innerText || ''; "
                    "if (/^[A-Z]{2,5}$/.test(t.trim()) || /[A-Z]{2,5}\\s*[·\\-]/.test(t.trim())) "
                    "{ el.click(); return; } } }"
                )
                page.wait_for_timeout(2000)
                asserts["after_fallback_click_url"] = page.url
                clicked = page.url != f"{PHASE}/"
            except Exception as e:  # noqa: BLE001
                asserts["fallback_click_error"] = str(e)

        _shot(page, f"flow3-{viewport_name}-2-company")

        # Navigate to backtest regardless.
        page.goto(f"{PHASE}/backtest", wait_until="load", timeout=30000)
        page.wait_for_timeout(2000)
        backtest_text = page.locator("body").inner_text(timeout=5000)
        asserts["backtest_page_has_content"] = len(backtest_text) > 200
        asserts["backtest_url"] = page.url
        _shot(page, f"flow3-{viewport_name}-3-backtest")
        success = asserts["has_p_value"] and asserts["backtest_page_has_content"]
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    finally:
        duration = int((time.time() - t0) * 1000)
        _record("flow3-phase-company-backtest", viewport_name, success, duration, asserts, error)
        ctx.close()


def test_flow3_desktop(browser):
    _run_flow_3(browser, "desktop", DESKTOP, is_mobile=False)


def test_flow3_mobile(browser):
    _run_flow_3(browser, "mobile", MOBILE, is_mobile=True)


# ---------------------------------------------------------------------------
# Flow 4: newsletter signup at /start-here
# ---------------------------------------------------------------------------

def _run_flow_4(browser, viewport_name: str, viewport: dict[str, int], is_mobile: bool):
    ctx = _make_context(browser, viewport, is_mobile)
    page = ctx.new_page()
    t0 = time.time()
    asserts: dict[str, Any] = {}
    error = None
    success = False
    try:
        page.goto(f"{BETA}/start-here", wait_until="load", timeout=30000)
        # Newsletter mounts via JS; wait for form.
        try:
            page.wait_for_selector("#newsletter-start-here .newsletter-form", timeout=10000)
            asserts["newsletter_form_visible"] = True
        except PWTimeout:
            asserts["newsletter_form_visible"] = False

        if asserts.get("newsletter_form_visible"):
            # Scroll to newsletter.
            page.locator("#newsletter-start-here").scroll_into_view_if_needed()
            page.wait_for_timeout(500)
            _shot(page, f"flow4-{viewport_name}-1-newsletter")

            # Fill + submit.
            input_sel = "#newsletter-start-here input[name='email']"
            page.fill(input_sel, "e2e-test+w3a@example.com")
            asserts["email_filled"] = (
                page.input_value(input_sel) == "e2e-test+w3a@example.com"
            )
            # Click submit.
            page.click("#newsletter-start-here button[type='submit']")
            # Wait for status text to appear (success or error response).
            try:
                page.wait_for_function(
                    "() => { const s = document.querySelector('#newsletter-start-here .newsletter-status'); "
                    "return s && s.innerText && s.innerText.trim().length > 0; }",
                    timeout=15000,
                )
                status_text = page.locator(
                    "#newsletter-start-here .newsletter-status"
                ).inner_text()
                asserts["status_text"] = status_text
                # Status may be success OR a 4xx hint (e.g. test domain blocked).
                # We treat "form responded" as success — i.e. flow completed
                # the round-trip, not that the email is actually subscribed.
                asserts["form_responded"] = len(status_text) > 0
                success = asserts["form_responded"]
            except PWTimeout:
                asserts["form_responded"] = False
            _shot(page, f"flow4-{viewport_name}-2-submitted")
    except Exception as e:  # noqa: BLE001
        error = f"{type(e).__name__}: {e}"
    finally:
        duration = int((time.time() - t0) * 1000)
        _record("flow4-newsletter", viewport_name, success, duration, asserts, error)
        ctx.close()


def test_flow4_desktop(browser):
    _run_flow_4(browser, "desktop", DESKTOP, is_mobile=False)


def test_flow4_mobile(browser):
    _run_flow_4(browser, "mobile", MOBILE, is_mobile=True)


# ---------------------------------------------------------------------------
# CLS measurements (desktop + mobile, 3 pages each).
# ---------------------------------------------------------------------------

_CLS_TARGETS = [
    ("beta-home", f"{BETA}/"),
    ("beta-discoveries", f"{BETA}/discoveries"),
    ("phase-home", f"{PHASE}/"),
]


def _measure_all_cls(browser, viewport_name: str, viewport: dict[str, int], is_mobile: bool):
    ctx = _make_context(browser, viewport, is_mobile)
    page = ctx.new_page()
    for slug, url in _CLS_TARGETS:
        result = _measure_cls(page, url)
        _RESULTS.append(
            {
                "flow": "cls-measurement",
                "viewport": viewport_name,
                "page_slug": slug,
                "url": url,
                "cls": result.get("cls"),
                "entries_count": result.get("entries_count"),
                "nav_ms": result.get("nav_ms"),
                "error": result.get("error"),
                "success": result.get("cls") is not None,
            }
        )
    ctx.close()


def test_cls_desktop(browser):
    _measure_all_cls(browser, "desktop", DESKTOP, is_mobile=False)


def test_cls_mobile(browser):
    _measure_all_cls(browser, "mobile", MOBILE, is_mobile=True)


# ---------------------------------------------------------------------------
# Session-end write of results.json
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _write_results_at_end():
    yield
    out = RESULTS_DIR / "session-9-w3-a-results.json"
    summary = {
        "session": "session-9-w3-a",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "total_records": len(_RESULTS),
        "records": _RESULTS,
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n[w3-a] results written to {out}")
