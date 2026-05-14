"""Session #9 W5-D — /company/[ticker] detail page audit.

Audits the live Phase Detector detail pages for 5 representative tickers
(AAPL / TSLA / NVDA / AMZN / META) across desktop (1280x800) + mobile
(375x667 iPhone SE) viewports.

This implements CLAUDE.md "功能验收三层" — real-env e2e layer. Zero LLM
cost: just navigate + screenshot + DOM asserts on prod
(https://phase.bytedance.city).

W4-B (#113) wrapped CompanyCard in Link → /company/[ticker]. W5-D verifies
the destination page actually delivers value (fields present, breadcrumb
back-path, mobile layout, copy quality).

Run:
    cd /Users/dadamini/Projects/structural-isomorphism  # or worktree
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/tests/e2e/test_phase_company_detail.py -v

Outputs:
    web/tests/e2e/screenshots/session-9-w5-d/*.png
    web/tests/e2e/results/session-9-w5-d-results.json
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

PHASE = "https://phase.bytedance.city"
DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 375, "height": 667}  # iPhone SE

TICKERS = ["AAPL", "TSLA", "NVDA", "AMZN", "META"]

REPO_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOT_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "screenshots" / "session-9-w5-d"
RESULTS_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "results"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_RESULTS: list[dict[str, Any]] = []


def _record(ticker: str, viewport: str, success: bool, asserts: dict[str, Any], error: str | None = None) -> None:
    _RESULTS.append(
        {
            "ticker": ticker,
            "viewport": viewport,
            "success": success,
            "asserts": asserts,
            "error": error,
        }
    )


def _shot(page: Page, name: str) -> str:
    path = SCREENSHOT_DIR / f"{name}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
    except Exception as exc:  # noqa: BLE001
        return f"<screenshot-failed: {exc}>"
    return str(path.relative_to(REPO_ROOT))


def _audit_detail(page: Page, ticker: str, viewport_name: str) -> dict[str, Any]:
    """Navigate to /company/<ticker> and audit fields.

    Returns a dict of assertion results (booleans + text snippets).
    """
    url = f"{PHASE}/company/{ticker}"
    # W5-D: use domcontentloaded not networkidle — Plausible beacons + font
    # warming can keep the network active past the 30s default, even though
    # the page is fully usable. domcontentloaded fires once HTML is parsed,
    # then we explicitly wait for the H1 (post-fetchCompany hydration).
    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    # Wait for fetchCompany() to populate. Skeleton loader has
    # `animate-pulse` class; once gone, content is rendered.
    try:
        page.wait_for_selector("h1", timeout=15_000)
    except PWTimeout:
        pass  # capture screenshot anyway

    # Give React a beat to flush state after the API responds.
    time.sleep(1.5)

    asserts: dict[str, Any] = {}

    # H1 ticker
    h1 = page.locator("h1").first
    asserts["h1_ticker_present"] = h1.is_visible() and ticker in (h1.text_content() or "")

    # Breadcrumb (W6-B / W5-E)
    bc = page.locator("nav[aria-label='面包屑导航']")
    asserts["breadcrumb_present"] = bc.is_visible()
    asserts["breadcrumb_text"] = (bc.text_content() or "").strip()
    asserts["breadcrumb_has_home_link"] = bc.locator("a[href='/']").count() > 0

    # CPS badge — text "稳态远离" / "接近临界" / "已翻转" / etc.
    cps_label = page.locator("[aria-label]:has-text('稳态'), [aria-label]:has-text('临界'), [aria-label]:has-text('翻转'), [aria-label]:has-text('未知')").first
    asserts["cps_badge_present"] = cps_label.count() > 0

    # Dynamics family label nearby — heuristic: contains common CN words
    body_text = page.locator("body").text_content() or ""
    asserts["has_dynamics_label"] = any(
        kw in body_text
        for kw in ["优先依附", "自组织临界", "回滞", "Scheffer", "极值", "线性", "反身", "Motter", "混合"]
    )

    # TL;DR section
    tldr_section = page.locator("section:has-text('30 秒一句话')").first
    asserts["tldr_section_present"] = tldr_section.count() > 0
    if tldr_section.count() > 0:
        tldr_text = tldr_section.text_content() or ""
        asserts["tldr_length_chars"] = len(tldr_text)
        asserts["tldr_nonempty"] = len(tldr_text) > 50
    else:
        asserts["tldr_length_chars"] = 0
        asserts["tldr_nonempty"] = False

    # Primary indicators panel
    indicators_section = page.locator("h2:has-text('主要指标')").first
    asserts["indicators_section_present"] = indicators_section.count() > 0

    # Confidence panel
    conf_section = page.locator("h2:has-text('置信度')").first
    asserts["confidence_section_present"] = conf_section.count() > 0
    # progressbar role
    progressbar = page.locator("[role='progressbar']").first
    asserts["confidence_progressbar_present"] = progressbar.count() > 0
    if progressbar.count() > 0:
        try:
            asserts["confidence_pct"] = progressbar.get_attribute("aria-valuenow")
        except Exception:  # noqa: BLE001
            asserts["confidence_pct"] = None

    # Metadata toggle (or absent if no universality_class)
    metadata_btn = page.locator("button:has-text('查看元数据'), button:has-text('隐藏元数据')")
    asserts["metadata_toggle_present"] = metadata_btn.count() > 0

    # Top nav (cross-page navigation back)
    asserts["top_nav_home_link"] = page.locator("header a[aria-label='Phase Detector 首页']").count() > 0
    asserts["top_nav_company_table_link"] = page.locator("header a[href='/']").count() > 0

    # Cross-site link to Structural beta
    asserts["structural_cross_link"] = page.locator("a[href*='beta.structural.bytedance.city']").count() > 0

    # Skeleton must not still be visible (means fetch failed or pending)
    asserts["skeleton_gone"] = page.locator(".animate-pulse").count() == 0

    return asserts


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize("viewport_name,viewport", [("desktop", DESKTOP), ("mobile", MOBILE)])
def test_company_detail_page(ticker: str, viewport_name: str, viewport: dict[str, int]) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(viewport=viewport)
            page = context.new_page()
            error: str | None = None
            asserts: dict[str, Any] = {}
            try:
                asserts = _audit_detail(page, ticker, viewport_name)
            except Exception as exc:  # noqa: BLE001
                error = repr(exc)
            finally:
                _shot(page, f"{ticker}-{viewport_name}")
                context.close()
        finally:
            browser.close()

    success = error is None and asserts.get("h1_ticker_present") and asserts.get("tldr_nonempty")
    _record(ticker, viewport_name, bool(success), asserts, error)

    # Soft-assert: we record everything but only hard-fail on the cardinal
    # signals (page renders + tldr text appears). Other gaps go into the
    # audit doc as improvement TODOs, not test failures.
    assert error is None, f"e2e error for {ticker}/{viewport_name}: {error}"
    assert asserts.get("h1_ticker_present"), f"H1 ticker missing for {ticker}/{viewport_name}"
    assert asserts.get("tldr_nonempty"), f"TL;DR empty for {ticker}/{viewport_name}"


def teardown_module(module: Any) -> None:  # noqa: ARG001
    out = RESULTS_DIR / "session-9-w5-d-results.json"
    out.write_text(json.dumps(_RESULTS, ensure_ascii=False, indent=2))
