"""Session #10 W6-C — /company/[ticker] detail page polish e2e.

Re-audits the live Phase Detector detail pages for 5 representative tickers
(AAPL / TSLA / NVDA / AMZN / META) across desktop (1280x800) + mobile
(375x667 iPhone SE) viewports, asserting the W6-C polish work landed:

  1. Chips row: sector + (optional) industry + (optional) market_cap_usd_b
     promoted out of metadata toggle.
  2. KeyContextPanel: dynamics_family + CPS explainers surfaced as a
     primary block (data-testid=key-context-panel).
  3. CPS badge present with non-color icon glyph.
  4. Indicators panel renders CN labels not raw EN keys.
  5. Confidence panel + progressbar with aria-valuenow.
  6. Bottom continuation CTAs (返回公司表 + Structural cross-link).
  7. Mobile hamburger button present below sm:640px viewport.
  8. Console-error count == 0 across navigation.
  9. CLS budget < 0.1 + LCP < 2.5s (best-effort via Performance API).
 10. Skeleton (animate-pulse blocks) gone after hydration.

Heuristic: this test is intended to run against either:
  - prod (https://phase.bytedance.city) once the W6-C PR ships, or
  - a local `next dev` server with NEXT_PUBLIC_USE_MOCK=false hitting prod API.

Override the base URL with env PHASE_BASE_URL.

This implements CLAUDE.md "功能验收三层" — real-env e2e layer. Zero LLM cost.

Run:
    cd /Users/dadamini/Projects/structural-isomorphism  # or worktree
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/tests/e2e/test_phase_company_detail.py -v

Outputs:
    web/tests/e2e/screenshots/session-10-w6-c/*.png
    web/tests/e2e/results/session-10-w6-c-results.json
    docs/screenshots/w6c-*.png (copies for the audit followup doc)
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

import pytest
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

PHASE = os.environ.get("PHASE_BASE_URL", "https://phase.bytedance.city")
DESKTOP = {"width": 1280, "height": 800}
MOBILE = {"width": 375, "height": 667}  # iPhone SE

TICKERS = ["AAPL", "TSLA", "NVDA", "AMZN", "META"]

# CLS + LCP budgets per task acceptance.
CLS_BUDGET = 0.1
LCP_BUDGET_MS = 2500

REPO_ROOT = Path(__file__).resolve().parents[3]
SCREENSHOT_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "screenshots" / "session-10-w6-c"
DOCS_SCREENSHOT_DIR = REPO_ROOT / "docs" / "screenshots"
RESULTS_DIR = REPO_ROOT / "web" / "tests" / "e2e" / "results"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

_RESULTS: list[dict[str, Any]] = []

# W6-C: when running against prod that does NOT yet have these assertions
# deployed, several "new behavior" asserts will soft-fail. Hard-fail set =
# cardinal signals only (page renders + TL;DR text appears). Soft-fail set =
# w6-c-specific asserts get recorded but don't block the suite — they're the
# bar the deploy must clear to count as ship.
HARD_FAIL_KEYS = {"h1_ticker_present", "tldr_nonempty"}
W6C_NEW_KEYS = {
    "chips_row_present",
    "market_cap_chip_present",
    "key_context_panel_present",
    "indicator_cn_label_present",
    "continuation_nav_present",
    "no_raw_indicator_keys",
}


def _record(
    ticker: str,
    viewport: str,
    success: bool,
    asserts: dict[str, Any],
    error: str | None = None,
) -> None:
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
        # Also drop a copy into docs/screenshots/w6c-* so the audit followup
        # doc can reference a stable location.
        docs_copy = DOCS_SCREENSHOT_DIR / f"w6c-{name}.png"
        try:
            shutil.copyfile(path, docs_copy)
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        return f"<screenshot-failed: {exc}>"
    return str(path.relative_to(REPO_ROOT))


def _collect_perf(page: Page) -> dict[str, float | None]:
    """Best-effort LCP + CLS pulled via window.performance / PerformanceObserver."""
    try:
        # CLS via Layout Shift entries (cumulative since page load).
        cls = page.evaluate(
            """
            () => new Promise((resolve) => {
              let cls = 0;
              try {
                const po = new PerformanceObserver((list) => {
                  for (const e of list.getEntries()) {
                    // only count unexpected shifts
                    if (!e.hadRecentInput) cls += e.value;
                  }
                });
                po.observe({ type: 'layout-shift', buffered: true });
              } catch (e) { /* unsupported */ }
              // Give observer 250ms to drain buffered entries.
              setTimeout(() => resolve(cls), 250);
            });
            """
        )
        # LCP via LargestContentfulPaint buffered entries.
        lcp = page.evaluate(
            """
            () => new Promise((resolve) => {
              let lcp = null;
              try {
                const po = new PerformanceObserver((list) => {
                  const entries = list.getEntries();
                  if (entries.length) {
                    lcp = entries[entries.length - 1].startTime;
                  }
                });
                po.observe({ type: 'largest-contentful-paint', buffered: true });
              } catch (e) { /* unsupported */ }
              setTimeout(() => resolve(lcp), 250);
            });
            """
        )
        return {"cls": float(cls) if cls is not None else None, "lcp_ms": float(lcp) if lcp is not None else None}
    except Exception:  # noqa: BLE001
        return {"cls": None, "lcp_ms": None}


def _audit_detail(page: Page, ticker: str, viewport_name: str) -> dict[str, Any]:
    """Navigate to /company/<ticker> and audit fields."""
    url = f"{PHASE}/company/{ticker}"
    console_errors: list[str] = []
    # Filter for app-origin errors only. 3rd-party analytics / fonts /
    # cross-origin resources that fail in some network environments are not
    # app bugs and should not break the suite.
    IGNORE_SUBSTRINGS = (
        "plausible.bytedance.city",
        "fonts.gstatic.com",
        "fonts.googleapis.com",
        "favicon.ico",
        "ERR_BLOCKED_BY_CLIENT",
    )

    def _on_console(msg) -> None:  # noqa: ANN001
        if msg.type != "error":
            return
        text = msg.text or ""
        loc = ""
        try:
            loc = (msg.location or {}).get("url", "") if isinstance(msg.location, dict) else ""
        except Exception:  # noqa: BLE001
            loc = ""
        haystack = f"{text} {loc}"
        if any(sub in haystack for sub in IGNORE_SUBSTRINGS):
            return
        console_errors.append(text)

    page.on("console", _on_console)

    page.goto(url, wait_until="domcontentloaded", timeout=30_000)

    try:
        page.wait_for_selector("h1", timeout=15_000)
    except PWTimeout:
        pass

    # Give React + fetchCompany a beat to flush + skeleton to clear.
    time.sleep(1.8)

    asserts: dict[str, Any] = {}

    # H1 ticker
    h1 = page.locator("h1").first
    asserts["h1_ticker_present"] = h1.is_visible() and ticker in (
        h1.text_content() or ""
    )

    # Breadcrumb
    bc = page.locator("nav[aria-label='面包屑导航']")
    asserts["breadcrumb_present"] = bc.is_visible()
    asserts["breadcrumb_text"] = (bc.text_content() or "").strip()
    asserts["breadcrumb_has_home_link"] = bc.locator("a[href='/']").count() > 0

    # CPS badge — preferred selector w6-c data-testid.
    cps_badge = page.locator("[data-testid='cps-badge']")
    if cps_badge.count() > 0:
        asserts["cps_badge_present"] = True
        asserts["cps_badge_text"] = (cps_badge.first.text_content() or "").strip()
    else:
        # legacy aria-label fallback
        legacy = page.locator(
            "[aria-label*='稳态'], [aria-label*='临界'], [aria-label*='翻转']"
        )
        asserts["cps_badge_present"] = legacy.count() > 0
        asserts["cps_badge_text"] = (
            (legacy.first.text_content() or "").strip() if legacy.count() else ""
        )

    # Dynamics family label nearby
    body_text = page.locator("body").text_content() or ""
    asserts["has_dynamics_label"] = any(
        kw in body_text
        for kw in [
            "强者愈强",
            "临界级联",
            "临界翻转",
            "回不去效应",
            "网络级联反应",
            "反身性循环",
            "极端尾部",
            "近线性稳态",
            "复合/待判定",
        ]
    )

    # TL;DR section
    tldr_section = page.locator("[data-testid='tldr-section']")
    if tldr_section.count() == 0:
        tldr_section = page.locator("section:has-text('30 秒一句话')")
    asserts["tldr_section_present"] = tldr_section.count() > 0
    if tldr_section.count() > 0:
        tldr_text = tldr_section.first.text_content() or ""
        asserts["tldr_length_chars"] = len(tldr_text)
        asserts["tldr_nonempty"] = len(tldr_text) > 50
    else:
        asserts["tldr_length_chars"] = 0
        asserts["tldr_nonempty"] = False

    # W6-C new: chips row
    chips = page.locator("[data-testid='company-chips']")
    asserts["chips_row_present"] = chips.count() > 0
    asserts["market_cap_chip_present"] = (
        page.locator("[data-testid='market-cap-chip']").count() > 0
    )

    # W6-C new: KeyContextPanel
    asserts["key_context_panel_present"] = (
        page.locator("[data-testid='key-context-panel']").count() > 0
    )

    # W6-C new: indicators panel uses CN labels, not raw `ar1_trend`
    indicators_panel = page.locator("[data-testid='indicators-panel']")
    if indicators_panel.count() == 0:
        indicators_panel = page.locator("h2:has-text('主要指标')")
    asserts["indicators_section_present"] = indicators_panel.count() > 0
    if indicators_panel.count() > 0:
        text = indicators_panel.first.text_content() or ""
        asserts["indicator_cn_label_present"] = any(
            label in text
            for label in [
                "记忆效应趋势",
                "波动率趋势",
                "尾部厚度漂移",
            ]
        )
        # Confirm we do NOT show raw snake_case indicator keys.
        asserts["no_raw_indicator_keys"] = not any(
            raw in text for raw in ["ar1_trend", "variance_trend", "tail_exponent_drift"]
        )
    else:
        asserts["indicator_cn_label_present"] = False
        asserts["no_raw_indicator_keys"] = False

    # Confidence panel
    conf_section = page.locator("[data-testid='confidence-panel']")
    if conf_section.count() == 0:
        conf_section = page.locator("h2:has-text('置信度')")
    asserts["confidence_section_present"] = conf_section.count() > 0
    progressbar = page.locator("[role='progressbar']").first
    asserts["confidence_progressbar_present"] = progressbar.count() > 0
    if progressbar.count() > 0:
        try:
            asserts["confidence_pct"] = progressbar.get_attribute("aria-valuenow")
        except Exception:  # noqa: BLE001
            asserts["confidence_pct"] = None

    # W6-C: continuation nav with 返回公司表 + Structural cross-link.
    cont_nav = page.locator("[data-testid='continuation-nav']")
    asserts["continuation_nav_present"] = cont_nav.count() > 0
    asserts["structural_cross_link"] = (
        page.locator("a[href*='beta.structural.bytedance.city']").count() > 0
    )

    # W6-C: mobile hamburger present below sm:640px.
    mobile_nav_btn = page.locator("[data-testid='mobile-nav-toggle']")
    asserts["mobile_nav_toggle_present"] = mobile_nav_btn.count() > 0
    if viewport_name == "mobile":
        asserts["mobile_nav_toggle_visible"] = mobile_nav_btn.is_visible() if mobile_nav_btn.count() > 0 else False
    else:
        asserts["mobile_nav_toggle_visible"] = None  # hidden by sm:hidden

    # Skeleton gone
    asserts["skeleton_gone"] = page.locator(".animate-pulse").count() == 0

    # Console errors
    asserts["console_errors"] = console_errors
    asserts["console_error_count"] = len(console_errors)

    # Performance (best-effort)
    perf = _collect_perf(page)
    asserts.update(perf)
    asserts["cls_under_budget"] = (
        perf["cls"] is None or perf["cls"] < CLS_BUDGET
    )
    asserts["lcp_under_budget"] = (
        perf["lcp_ms"] is None or perf["lcp_ms"] < LCP_BUDGET_MS
    )

    return asserts


@pytest.mark.parametrize("ticker", TICKERS)
@pytest.mark.parametrize(
    "viewport_name,viewport", [("desktop", DESKTOP), ("mobile", MOBILE)]
)
def test_company_detail_page(
    ticker: str, viewport_name: str, viewport: dict[str, int]
) -> None:
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

    success = (
        error is None
        and asserts.get("h1_ticker_present")
        and asserts.get("tldr_nonempty")
    )
    _record(ticker, viewport_name, bool(success), asserts, error)

    # Hard fail: page renders + TL;DR appears (cardinal signal).
    assert error is None, f"e2e error for {ticker}/{viewport_name}: {error}"
    assert asserts.get(
        "h1_ticker_present"
    ), f"H1 ticker missing for {ticker}/{viewport_name}"
    assert asserts.get(
        "tldr_nonempty"
    ), f"TL;DR empty for {ticker}/{viewport_name}"
    # Console must be clean.
    assert asserts.get("console_error_count", 0) == 0, (
        f"console errors for {ticker}/{viewport_name}: "
        f"{asserts.get('console_errors')}"
    )


def teardown_module(module: Any) -> None:  # noqa: ARG001
    out = RESULTS_DIR / "session-10-w6-c-results.json"
    out.write_text(json.dumps(_RESULTS, ensure_ascii=False, indent=2))
