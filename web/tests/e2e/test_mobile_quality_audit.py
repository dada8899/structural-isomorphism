"""Fail-closed mobile release audit for every intentional Beta and Phase route.

The project gate requires 44x44 CSS px, except inline text links and a small
checkbox/radio enclosed by a visible 44px label. Score remains diagnostic only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import Error as PlaywrightError

BETA = os.getenv("BETA_BASE", "https://beta.structural.bytedance.city").rstrip("/")
PHASE = os.getenv("PHASE_BASE", "https://phase.bytedance.city").rstrip("/")
WIDTHS = (320, 375, 390, 430)
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
        return origin + "/paper.html?doc=" + route.removeprefix("/paper/")
    if route.startswith("/phenomenon/"):
        return origin + "/phenomenon.html?id=" + route.removeprefix("/phenomenon/")
    return origin + route + ".html"


def audit_route(context, url: str) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    timing = {"url": url, "navigation_ms": None, "total_ms": None, "status": None}
    started = time.perf_counter()
    page = None
    try:
        page, navigation_started = context.new_page(), time.perf_counter()
        response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        timing["navigation_ms"] = round((time.perf_counter() - navigation_started) * 1000)
        timing["status"] = response.status if response else None
        if response is None or response.status >= 400:
            issues.append({"kind": "route", "url": url, "detail": timing})
            return issues, timing
        page.wait_for_timeout(100)
        script = """() => { const selector =
      'a[href],button,input,select,textarea,summary,[contenteditable="true"],[role="button"],[role="tab"],[role="checkbox"],[role="switch"],[role="slider"],[role="spinbutton"],[role="combobox"],'
      + '[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"],[role="radio"],[role="option"],[role="treeitem"],[role="gridcell"][tabindex],[role="row"][tabindex],[role="link"]';
      return ({
      viewport: document.documentElement.clientWidth,
      content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      controls: [...document.querySelectorAll(selector)]
        .filter(el => { const s=getComputedStyle(el), r=el.getBoundingClientRect();
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0; })
        .map((el, index) => { const r=el.getBoundingClientRect();
          const label=el.matches('input[type="checkbox"],input[type="radio"]') ? el.closest('label') : null, labelBox=label?.getBoundingClientRect(), labelStyle=label && getComputedStyle(label), hit=labelBox && document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
          const compositeSelector='[role="toolbar"],[role="tablist"],[role="radiogroup"],[role="menu"],[role="listbox"],[role="tree"],[role="grid"]', pairs={tablist:['tab'],radiogroup:['radio'],menu:['menuitem','menuitemcheckbox','menuitemradio'],listbox:['option'],tree:['treeitem'],grid:['gridcell','row']};
          const composite=el.closest(compositeSelector), role=composite?.getAttribute('role');
          const isMember=peer => peer.closest(compositeSelector)===composite && (role==='toolbar' ? peer.matches('a[href],button,input,select,textarea,[role="button"]') : (pairs[role] || []).includes(peer.getAttribute('role')));
          const active=composite && isMember(el) ? [...composite.querySelectorAll(selector)].filter(peer =>
            isMember(peer) && !peer.disabled && peer.getAttribute('aria-disabled') !== 'true' && peer.tabIndex === 0) : [];
          return {
          index, tag: el.tagName, cls: typeof el.className==='string' ? el.className : '', role: el.getAttribute('role') || '', disabled: !!el.disabled || el.getAttribute('aria-disabled')==='true',
          name: (el.getAttribute('aria-label') || el.getAttribute('title') ||
            el.getAttribute('placeholder') || el.innerText || el.value || '').trim(),
          tabIndex: el.tabIndex, roving: el.getAttribute('tabindex') === '-1' && active.length === 1,
          width:r.width, height:r.height, covered: !!labelBox && labelBox.width >= 44 && labelBox.height >= 44 && typeof label.checkVisibility === 'function' && label.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) && labelStyle.pointerEvents !== 'none' && !label.closest('[inert]') && !!hit && (hit===el || label.contains(hit)),
          inline: el.tagName==='A' && getComputedStyle(el).display==='inline'
        }; })
    }) }"""
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
        for control in metrics["controls"]:
            if not control["name"]:
                issues.append({"kind": "unnamed", "url": url, "detail": control})
            if not control["disabled"] and control["tabIndex"] < 0 and not control["roving"]:
                issues.append({"kind": "keyboard", "url": url, "detail": control})
            if (not control["disabled"] and not control["inline"] and not control["covered"] and
                    (control["width"] < 44 or control["height"] < 44)):
                issues.append({"kind": "touch", "url": url, "detail": control})
    except PlaywrightError as exc:
        timing["error"] = f"{type(exc).__name__}: {str(exc).splitlines()[0]}"
        issues.append({"kind": "route", "url": url, "detail": timing})
    finally:
        timing["total_ms"] = round((time.perf_counter() - started) * 1000)
        if page is not None:
            try:
                page.close()
            except PlaywrightError as exc:
                issues.append({"kind": "route", "url": url, "detail": f"close: {str(exc).splitlines()[0]}"})
    return issues, timing


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_mobile_public_surface_score(browser, width):
    issues: list[dict] = []
    timings: list[dict] = []
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
    products = os.getenv("AUDIT_PRODUCT", "all")
    matrices = []
    if products in {"all", "beta"}:
        matrices.append((BETA, BETA_ROUTES))
    if products in {"all", "phase"}:
        matrices.append((PHASE, PHASE_ROUTES))
    for origin, routes in matrices:
        for route in routes:
            url = local_static_url(origin, route) if origin == BETA else origin + route
            route_issues, timing = audit_route(context, url)
            timings.append(timing | {"width": width})
            if timing["total_ms"] >= 5_000:
                issues.append({"kind": "slow", "url": url, "detail": timing, "width": width})
            for issue in route_issues:
                issue["width"] = width
                issues.append(issue)
    context.close()
    counts = {kind: sum(item["kind"] == kind for item in issues)
              for kind in ("route", "slow", "overflow", "unnamed", "keyboard", "touch")}
    score = 100
    score -= min(20, (counts["route"] + counts["slow"]) * 5)
    score -= min(20, counts["overflow"] * 2)
    score -= min(20, (counts["unnamed"] + counts["keyboard"]) * 2)
    score -= min(20, counts["touch"])
    examples = {
        kind: [item for item in issues if item["kind"] == kind][:8]
        for kind in counts
    }
    report = {"score": score, "counts": counts, "examples": examples, "route_timings": (ordered_timings := sorted(timings, key=lambda item: item["total_ms"], reverse=True)), "slow_routes": [item for item in ordered_timings if item["total_ms"] >= 5_000]}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    assert all(count == 0 for count in counts.values()), json.dumps(report, ensure_ascii=False)


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_mobile_key_flows_have_no_serious_axe_violations(browser, width):
    assert AXE_PATH.is_file(), "run pnpm install in web/phase-detector before axe audit"
    axe = AXE_PATH.read_text(encoding="utf-8")
    context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True, has_touch=True)
    failures = []
    products = os.getenv("AUDIT_PRODUCT", "all")
    urls = []
    if products in {"all", "beta"}:
        urls.extend(local_static_url(BETA, route) for route in BETA_ROUTES)
    if products in {"all", "phase"}:
        urls.extend((PHASE + "/companies", PHASE + "/auth/login",
                     PHASE + "/me/favorites"))
    for url in urls:
        page = None
        try:
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            if response is None or response.status >= 400:
                failures.append({"url": url, "route": response.status if response else None})
                continue
            page.wait_for_timeout(600)
            page.add_script_tag(content=axe)
            violations = page.evaluate("""async () => (await axe.run(document, {
              runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}
            })).violations.filter(v => ['critical','serious'].includes(v.impact))""")
            if violations:
                failures.append({"url": url, "violations": violations})
        except PlaywrightError as exc:
            failures.append({"url": url, "route": f"{type(exc).__name__}: {str(exc).splitlines()[0]}"})
        finally:
            try:
                if page is not None:
                    page.close()
            except PlaywrightError as exc:
                failures.append({"url": url, "route": f"close: {str(exc).splitlines()[0]}"})
    context.close()
    assert failures == [], json.dumps(failures, ensure_ascii=False)
