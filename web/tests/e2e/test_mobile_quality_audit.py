"""Quantified mobile QA audit for every intentional Beta and Phase route.

Touch targets follow WCAG 2.2 AA 2.5.8: 24x24 CSS px, with the inline-text and
24px centre-spacing exceptions. Categories are capped at 20 points so one
shared-chrome defect cannot hide the rest of the product signal.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

BETA = os.getenv("BETA_BASE", "https://beta.structural.bytedance.city").rstrip("/")
PHASE = os.getenv("PHASE_BASE", "https://phase.bytedance.city").rstrip("/")
WIDTHS = (375, 390, 430)
BETA_ROUTES = (
    "/", "/start-here", "/search", "/classes", "/discoveries", "/papers",
    "/methods", "/tools", "/whitespace", "/insights", "/apply",
    "/stress-test", "/lint", "/diagnose", "/taxonomy-v2", "/learn",
    "/about", "/privacy", "/reports", "/analyze", "/thank-you",
    "/phenomenon/sci-001", "/paper/unified-pipeline-v0.2-2026-05-13",
)
PHASE_ROUTES = (
    "/", "/zh", "/companies", "/company/AAPL",
    "/compare?tickers=AAPL,TSLA", "/universality",
    "/universality/preferential_attachment", "/methodology", "/backtest",
    "/newsletter", "/newsletter/001", "/about", "/privacy", "/pricing",
    "/onboarding", "/search", "/offline", "/auth/login", "/auth/verify",
    "/me", "/me/favorites", "/thank-you", "/checkout/mock",
)
AXE_PATH = (
    Path(__file__).resolve().parents[2]
    / "phase-detector/node_modules/axe-core/axe.min.js"
)


def local_static_url(origin: str, route: str) -> str:
    if "127.0.0.1" not in origin and "localhost" not in origin:
        return origin + route
    if route == "/":
        return origin + "/index.html"
    if route.startswith("/paper/"):
        return origin + "/paper.html?id=" + route.removeprefix("/paper/")
    if route.startswith("/phenomenon/"):
        return origin + "/phenomenon.html?id=" + route.removeprefix("/phenomenon/")
    return origin + route + ".html"


def audit_route(page, url: str) -> list[dict]:
    issues: list[dict] = []
    response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
    if response is None or response.status >= 400:
        return [{"kind": "route", "url": url, "detail": response.status if response else None}]
    page.wait_for_timeout(100)
    script = """() => ({
      viewport: document.documentElement.clientWidth,
      content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      controls: [...document.querySelectorAll('a[href],button,input,select,textarea,[role="button"]')]
        .filter(el => { const s=getComputedStyle(el), r=el.getBoundingClientRect();
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0; })
        .map((el, index) => { const r=el.getBoundingClientRect(); return {
          index, tag: el.tagName, disabled: !!el.disabled || el.getAttribute('aria-disabled')==='true',
          name: (el.getAttribute('aria-label') || el.getAttribute('title') ||
            el.getAttribute('placeholder') || el.innerText || el.value || '').trim(),
          tabIndex: el.tabIndex, width:r.width, height:r.height,
          cx:r.left+r.width/2, cy:r.top+r.height/2,
          inline: el.tagName==='A' && getComputedStyle(el).display==='inline'
        }; })
    })"""
    for attempt in range(3):
        try:
            metrics = page.evaluate(script)
            break
        except PlaywrightError:
            if attempt == 2:
                raise
            page.wait_for_timeout(150)
    if metrics["content"] > metrics["viewport"] + 1:
        issues.append({"kind": "overflow", "url": url, "detail": metrics})
    active = [item for item in metrics["controls"] if not item["disabled"]]
    for control in metrics["controls"]:
        if not control["name"]:
            issues.append({"kind": "unnamed", "url": url, "detail": control})
        if not control["disabled"] and control["tabIndex"] < 0:
            issues.append({"kind": "keyboard", "url": url, "detail": control})
        separated = all(
            other["index"] == control["index"] or
            ((other["cx"] - control["cx"]) ** 2 +
             (other["cy"] - control["cy"]) ** 2) ** 0.5 >= 24
            for other in active
        )
        if (not control["disabled"] and not control["inline"] and not separated and
                (control["width"] < 24 or control["height"] < 24)):
            issues.append({"kind": "touch", "url": url, "detail": control})
    return issues


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_mobile_public_surface_score(browser, width):
    issues: list[dict] = []
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True)
    page = context.new_page()
    products = os.getenv("AUDIT_PRODUCT", "all")
    matrices = []
    if products in {"all", "beta"}:
        matrices.append((BETA, BETA_ROUTES))
    if products in {"all", "phase"}:
        matrices.append((PHASE, PHASE_ROUTES))
    for origin, routes in matrices:
        for route in routes:
            url = local_static_url(origin, route) if origin == BETA else origin + route
            for issue in audit_route(page, url):
                issue["width"] = width
                issues.append(issue)
    context.close()
    counts = {kind: sum(item["kind"] == kind for item in issues)
              for kind in ("route", "overflow", "unnamed", "keyboard", "touch")}
    score = 100
    score -= min(20, counts["route"] * 5)
    score -= min(20, counts["overflow"] * 2)
    score -= min(20, (counts["unnamed"] + counts["keyboard"]) * 2)
    score -= min(20, counts["touch"])
    examples = {
        kind: [item for item in issues if item["kind"] == kind][:8]
        for kind in counts
    }
    report = {"score": score, "counts": counts, "examples": examples}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert score >= 90, json.dumps(report, ensure_ascii=False)


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_mobile_key_flows_have_no_serious_axe_violations(browser, width):
    assert AXE_PATH.is_file(), "run pnpm install in web/phase-detector before axe audit"
    axe = AXE_PATH.read_text(encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True)
    page = context.new_page()
    failures = []
    products = os.getenv("AUDIT_PRODUCT", "all")
    urls = []
    if products in {"all", "beta"}:
        urls.extend((BETA + "/", BETA + "/analyze"))
    if products in {"all", "phase"}:
        urls.extend((PHASE + "/companies", PHASE + "/auth/login",
                     PHASE + "/me/favorites"))
    for url in urls:
        page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        page.wait_for_timeout(600)
        page.add_script_tag(content=axe)
        violations = page.evaluate("""async () => (await axe.run(document, {
          runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}
        })).violations.filter(v => ['critical','serious'].includes(v.impact))""")
        if violations:
            failures.append({"url": url, "violations": violations})
    context.close()
    assert failures == [], json.dumps(failures, ensure_ascii=False)
