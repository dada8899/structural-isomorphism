"""Fail-closed mobile release audit for every intentional Beta and Phase route.

The project gate requires 44x44 CSS px, except sentence-level inline text links
with surrounding copy and no visual chrome, and a small checkbox/radio enclosed
by a visible 44px label. An inline-flex sentence link must opt in with
``data-touch-target="inline-text"``; navigation, cards, and buttons cannot use
that exception. Score remains diagnostic only.
"""
from __future__ import annotations

import json
import os
import subprocess
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

INLINE_TEXT_POLICY_JS = r"""facts => (
  facts.tag === 'A' && facts.semanticTextBlock && facts.surroundingText &&
  !facts.visualChrome &&
  !facts.structuralTarget && !facts.forbiddenContext &&
  (facts.display === 'inline' ||
    (facts.display === 'inline-flex' && facts.markedInline))
)"""

INLINE_TEXT_FACTS_JS = r"""(el, style, pseudoStyles = []) => {
  const semanticTextBlock=el.closest('p,li,dd,dt,blockquote,figcaption');
  const ownText=(el.innerText || el.textContent || '').trim();
  const blockText=(semanticTextBlock?.innerText || semanticTextBlock?.textContent || '').trim();
  const surroundingText=blockText.replace(ownText, '').replace(/\s+/g, '').length > 0;
  const hasChrome=sample => {
    const padding=['Top','Right','Bottom','Left'].reduce(
      (sum, side) => sum + (parseFloat(sample['padding'+side]) || 0), 0);
    const border=['Top','Right','Bottom','Left'].reduce(
      (sum, side) => sum + (parseFloat(sample['border'+side+'Width']) || 0), 0);
    const background=(sample.backgroundColor || '').replace(/\s+/g, '');
    const transparent=background === 'transparent' || background === 'rgba(0,0,0,0)';
    const outlined=sample.outlineStyle !== 'none' &&
      (parseFloat(sample.outlineWidth) || 0) > 0;
    return padding > 0 || border > 0 || !transparent ||
      sample.backgroundImage !== 'none' || sample.boxShadow !== 'none' || outlined;
  };
  const pseudoChrome=pseudoStyles.some(sample => {
    const content=(sample.content || '').trim();
    return !['', 'none', 'normal'].includes(content) && hasChrome(sample);
  });
  const descendants=[...el.querySelectorAll('*')];
  const descendantChrome=descendants.some(node => {
    const nodeStyle=getComputedStyle(node);
    const nodeChrome=hasChrome(nodeStyle);
    const nodePseudoChrome=['::before','::after'].some(pseudo => {
      const sample=getComputedStyle(node, pseudo);
      const content=(sample.content || '').trim();
      return !['', 'none', 'normal'].includes(content) && hasChrome(sample);
    });
    return nodeChrome || nodePseudoChrome;
  });
  const structuralChild=el.querySelector(
    'nav,article,section,a[href],button,input,select,textarea,summary,div,p,' +
    'h1,h2,h3,h4,ul,ol,table,img,svg,[contenteditable="true"],' +
    '[role="button"],[role="link"],[role="menu"],[role="toolbar"],[role="tablist"]');
  const markedInline=el.getAttribute('data-touch-target') === 'inline-text';
  const isCardLike=node => {
    const cls=typeof node.className === 'string' ? node.className : '';
    const testId=(node.getAttribute?.('data-testid') || '').toLowerCase();
    const role=(node.getAttribute?.('role') || '').toLowerCase();
    return /(^|\s)[^\s]*card[^\s]*(\s|$)/i.test(cls) ||
      node.getAttribute?.('data-card') !== null || testId.includes('card') ||
      (['ARTICLE','SECTION'].includes(node.tagName) && role === 'link');
  };
  let cardLike=descendants.some(isCardLike);
  for (let node=el; node && !cardLike; node=node.parentElement) {
    cardLike=isCardLike(node);
  }
  const forbiddenContext=cardLike || !!el.closest(
    'nav,button,summary,[role="button"],[role="menu"],[role="toolbar"],[role="tablist"]');
  return {
    tag:el.tagName, semanticTextBlock:!!semanticTextBlock, surroundingText,
    visualChrome:hasChrome(style) || pseudoChrome || descendantChrome,
    structuralTarget:!!structuralChild ||
      el.matches('nav,article,section,button,summary,[role="button"]'),
    forbiddenContext, display:style.display, markedInline
  };
}"""


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
        # Audit a settled first render. Dynamic states that intentionally open
        # later (tour/custom cookie panel) have dedicated interaction gates
        # below; a fixed 100ms snapshot previously let both escape review.
        page.wait_for_load_state("load", timeout=5_000)
        page.evaluate("() => document.fonts?.ready")
        page.wait_for_timeout(250)
        script = """() => { const inlineTextPolicy=__INLINE_TEXT_POLICY__;
      const inlineTextFacts=__INLINE_TEXT_FACTS__;
      const selector =
      'a[href],button,input,select,textarea,summary,[contenteditable="true"],[role="button"],[role="tab"],[role="checkbox"],[role="switch"],[role="slider"],[role="spinbutton"],[role="combobox"],'
      + '[role="menuitem"],[role="menuitemcheckbox"],[role="menuitemradio"],[role="radio"],[role="option"],[role="treeitem"],[role="gridcell"][tabindex],[role="row"][tabindex],[role="link"]';
      return ({
      viewport: document.documentElement.clientWidth,
      content: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
      overflowers: [...document.querySelectorAll('body *')]
        .map(el => { const r=el.getBoundingClientRect(), s=getComputedStyle(el); return {
          tag:el.tagName, cls:typeof el.className==='string' ? el.className : '',
          name:(el.getAttribute('aria-label') || el.innerText || '').trim().slice(0, 120),
          left:Math.round(r.left), right:Math.round(r.right), width:Math.round(r.width),
          visible:s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0
        }; })
        .filter(el => el.visible && el.left < document.documentElement.clientWidth && el.right > document.documentElement.clientWidth + 1)
        .sort((a, b) => b.right - a.right).slice(0, 8),
      controls: [...document.querySelectorAll(selector)]
        .filter(el => { const s=getComputedStyle(el), r=el.getBoundingClientRect();
          return s.visibility !== 'hidden' && s.display !== 'none' && r.width > 0 && r.height > 0; })
        .map((el, index) => { const r=el.getBoundingClientRect(), style=getComputedStyle(el);
          const label=el.matches('input[type="checkbox"],input[type="radio"]') ? el.closest('label') : null, labelBox=label?.getBoundingClientRect(), labelStyle=label && getComputedStyle(label), hit=labelBox && document.elementFromPoint(r.left+r.width/2,r.top+r.height/2);
          const compositeSelector='[role="toolbar"],[role="tablist"],[role="radiogroup"],[role="menu"],[role="listbox"],[role="tree"],[role="grid"]', pairs={tablist:['tab'],radiogroup:['radio'],menu:['menuitem','menuitemcheckbox','menuitemradio'],listbox:['option'],tree:['treeitem'],grid:['gridcell','row']};
          const composite=el.closest(compositeSelector), role=composite?.getAttribute('role');
          const isMember=peer => peer.closest(compositeSelector)===composite && (role==='toolbar' ? peer.matches('a[href],button,input,select,textarea,[role="button"]') : (pairs[role] || []).includes(peer.getAttribute('role')));
          const active=composite && isMember(el) ? [...composite.querySelectorAll(selector)].filter(peer =>
            isMember(peer) && !peer.disabled && peer.getAttribute('aria-disabled') !== 'true' && peer.tabIndex === 0) : [];
          const facts=inlineTextFacts(el, style, [
            getComputedStyle(el, '::before'), getComputedStyle(el, '::after')]);
          const inlineText=inlineTextPolicy(facts);
          return {
          index, tag: el.tagName, cls: typeof el.className==='string' ? el.className : '', role: el.getAttribute('role') || '', disabled: !!el.disabled || el.getAttribute('aria-disabled')==='true',
          name: (el.getAttribute('aria-label') || el.getAttribute('title') ||
            el.getAttribute('placeholder') || el.innerText || el.value || '').trim(),
          tabIndex: el.tabIndex, roving: el.getAttribute('tabindex') === '-1' && active.length === 1,
          width:r.width, height:r.height, covered: !!labelBox && labelBox.width >= 44 && labelBox.height >= 44 && typeof label.checkVisibility === 'function' && label.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) && labelStyle.pointerEvents !== 'none' && !label.closest('[inert]') && !!hit && (hit===el || label.contains(hit)),
          inline: inlineText,
          inlineReason: inlineText ? (facts.markedInline ? 'declared-inline-text' : 'sentence-inline-text') : '',
          inlineFacts:facts
        }; })
    }) }""".replace("__INLINE_TEXT_POLICY__", INLINE_TEXT_POLICY_JS).replace(
            "__INLINE_TEXT_FACTS__", INLINE_TEXT_FACTS_JS)
        for attempt in range(3):
            try:
                metrics = page.evaluate(script)
                break
            except PlaywrightError:
                if attempt == 2:
                    raise
                page.wait_for_timeout(150)
        if metrics["content"] > metrics["viewport"] + 1:
            issues.append({
                "kind": "overflow",
                "url": url,
                "detail": {
                    "viewport": metrics["viewport"],
                    "content": metrics["content"],
                    "elements": metrics["overflowers"],
                },
            })
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


def summarize_issue_patterns(issues: list[dict], kind: str) -> list[dict]:
    """Group repeated shared-shell defects without hiding affected routes."""
    groups: dict[tuple[str, str, str], dict] = {}
    for item in issues:
        if item["kind"] != kind:
            continue
        detail = item.get("detail")
        if not isinstance(detail, dict):
            continue
        key = (
            str(detail.get("tag", "")),
            str(detail.get("cls", "")),
            str(detail.get("name", ""))[:120],
        )
        group = groups.setdefault(
            key,
            {"count": 0, "tag": key[0], "class": key[1], "name": key[2], "routes": []},
        )
        group["count"] += 1
        if item["url"] not in group["routes"]:
            group["routes"].append(item["url"])
    return sorted(groups.values(), key=lambda entry: (-entry["count"], entry["name"]))[:40]


def test_inline_text_policy_mutations() -> None:
    """Execute the exact browser policy against allow/deny mutations."""
    base = {
        "tag": "A",
        "semanticTextBlock": True,
        "surroundingText": True,
        "visualChrome": False,
        "structuralTarget": False,
        "forbiddenContext": False,
        "display": "inline",
        "markedInline": False,
    }

    def mutation(name: str, expected: bool, **changes) -> dict:
        return {"name": name, "expected": expected, "facts": base | changes}

    cases = [
        mutation("sentence-inline", True),
        mutation("declared-inline-flex", True, display="inline-flex", markedInline=True),
        mutation("unmarked-inline-flex", False, display="inline-flex"),
        mutation("declared-block", False, display="block", markedInline=True),
        mutation("declared-flex", False, display="flex", markedInline=True),
        mutation("declared-grid", False, display="grid", markedInline=True),
        mutation("generic-parent", False, semanticTextBlock=False),
        mutation("no-surrounding-copy", False, surroundingText=False, markedInline=True),
        mutation("visual-button-link", False, visualChrome=True, markedInline=True),
        mutation("navigation", False, forbiddenContext=True, markedInline=True),
        mutation("card", False, forbiddenContext=True, markedInline=True),
        mutation("anchor-wrapping-article", False, structuralTarget=True, markedInline=True),
        mutation("article-target", False, tag="ARTICLE", markedInline=True),
        mutation("section-target", False, tag="SECTION", markedInline=True),
        mutation("button-target", False, tag="BUTTON", markedInline=True),
        mutation("summary-target", False, tag="SUMMARY", markedInline=True),
    ]
    program = (
        f"const policy={INLINE_TEXT_POLICY_JS};"
        f"const cases={json.dumps(cases)};"
        "const failures=cases.filter(c=>policy(c.facts)!==c.expected);"
        "if(failures.length){console.error(JSON.stringify(failures));process.exit(1)}"
    )
    result = subprocess.run(
        ["node", "-e", program],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.e2e
def test_inline_text_dom_fact_mutations(browser) -> None:
    """Run the shared facts extractor against real browser DOM mutations."""
    page = browser.new_page()
    try:
        script = """() => {
          const policy=__INLINE_TEXT_POLICY__;
          const factsFor=__INLINE_TEXT_FACTS__;
          const style=document.createElement('style');
          style.textContent='.pseudo-chrome::before{content:"";box-shadow:0 0 0 2px red}';
          document.head.append(style);
          const cases=[
            {name:'semantic-p', expected:true, container:'p'},
            {name:'semantic-li', expected:true, container:'li'},
            {name:'semantic-dd', expected:true, container:'dd'},
            {name:'semantic-dt', expected:true, container:'dt'},
            {name:'semantic-blockquote', expected:true, container:'blockquote'},
            {name:'semantic-figcaption', expected:true, container:'figcaption'},
            {name:'generic-div-with-sibling-text', expected:false, container:'div'},
            {name:'header-with-sibling-text', expected:false, container:'header'},
            {name:'footer-with-sibling-text', expected:false, container:'footer'},
            {name:'generic-span-with-sibling-text', expected:false, container:'span'},
            {name:'declared-inline-flex', expected:true, container:'p',
              display:'inline-flex', marked:true},
            {name:'declared-generic-inline-flex', expected:false, container:'div',
              display:'inline-flex', marked:true},
            {name:'declared-block', expected:false, display:'block', marked:true},
            {name:'declared-flex', expected:false, display:'flex', marked:true},
            {name:'declared-grid', expected:false, display:'grid', marked:true},
            {name:'nav-ancestor', expected:false, display:'inline-flex', marked:true, ancestor:'nav'},
            {name:'card-class-ancestor', expected:false, display:'inline-flex', marked:true,
              ancestor:'article', ancestorClass:'result-card'},
            {name:'wrapped-nav', expected:false, display:'inline-flex', marked:true, child:'nav'},
            {name:'wrapped-article', expected:false, display:'inline-flex', marked:true, child:'article'},
            {name:'wrapped-section', expected:false, display:'inline-flex', marked:true, child:'section'},
            {name:'wrapped-button', expected:false, display:'inline-flex', marked:true, child:'button'},
            {name:'wrapped-summary', expected:false, display:'inline-flex', marked:true, child:'summary'},
            {name:'nested-plain-span', expected:true, child:'span'},
            {name:'descendant-chrome', expected:false, child:'span',
              childCss:{display:'inline-block',padding:'2px 6px',background:'#000'}},
            {name:'wrapped-span-data-card', expected:false, child:'span', childDataCard:true},
            {name:'wrapped-span-card-class', expected:false, child:'span', childClass:'result-card'},
            {name:'wrapped-span-role-button', expected:false, child:'span', childRole:'button'},
            {name:'box-shadow', expected:false, display:'inline-flex', marked:true,
              css:{boxShadow:'0 0 0 2px red'}},
            {name:'background-image', expected:false, display:'inline-flex', marked:true,
              css:{backgroundImage:'linear-gradient(red, blue)'}},
            {name:'outline', expected:false, display:'inline-flex', marked:true,
              css:{outline:'2px solid red'}},
            {name:'pseudo-chrome', expected:false, display:'inline-flex', marked:true,
              cls:'pseudo-chrome'}
          ];
          return cases.map(test => {
            const outer=document.createElement(test.ancestor || 'div');
            outer.className=test.ancestorClass || '';
            const textContainer=document.createElement(test.container || 'p');
            const anchor=document.createElement('a');
            anchor.href='#'; anchor.textContent='details'; anchor.className=test.cls || '';
            if(test.display) anchor.style.display=test.display;
            if(test.marked) anchor.setAttribute('data-touch-target','inline-text');
            Object.assign(anchor.style, test.css || {});
            if(test.child){
              anchor.textContent='';
              const child=document.createElement(test.child);
              child.textContent='details'; child.className=test.childClass || '';
              Object.assign(child.style, test.childCss || {});
              if(test.childDataCard) child.setAttribute('data-card','');
              if(test.childRole) child.setAttribute('role',test.childRole);
              anchor.append(child);
            }
            textContainer.append('Before ', anchor, ' after'); outer.append(textContainer);
            document.body.append(outer);
            const facts=factsFor(anchor, getComputedStyle(anchor), [
              getComputedStyle(anchor,'::before'), getComputedStyle(anchor,'::after')]);
            return {name:test.name, expected:test.expected, actual:policy(facts), facts};
          }).filter(test => test.actual !== test.expected);
        }""".replace("__INLINE_TEXT_POLICY__", INLINE_TEXT_POLICY_JS).replace(
            "__INLINE_TEXT_FACTS__", INLINE_TEXT_FACTS_JS)
        assert page.evaluate(script) == []
    finally:
        page.close()


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
    failure_report = {
        "score": score,
        "counts": counts,
        "examples": examples,
        "touch_patterns": summarize_issue_patterns(issues, "touch"),
        "slow_routes": report["slow_routes"],
    }
    assert all(count == 0 for count in counts.values()), json.dumps(
        failure_report,
        ensure_ascii=False,
    )


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
        urls.extend((PHASE + "/companies", PHASE + "/compare?tickers=AAPL,TSLA",
                     PHASE + "/auth/login", PHASE + "/me/favorites"))
    for url in urls:
        page = None
        try:
            page = context.new_page()
            response = page.goto(url, wait_until="domcontentloaded", timeout=20_000)
            if response is None or response.status >= 400:
                failures.append({"url": url, "route": response.status if response else None})
                continue
            page.wait_for_timeout(600)
            if url == PHASE + "/me/favorites":
                title = page.title()
                expected_title = "我的收藏 — Structural Labs · Phase"
                if title != expected_title:
                    failures.append({
                        "url": url,
                        "title": title,
                        "expected_title": expected_title,
                    })
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


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_onboarding_single_owner_keyboard_contract(browser, width):
    """Wait past auto-start and reject duplicate tour owners or broken keys."""
    context = browser.new_context(
        viewport={"width": width, "height": 844},
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    try:
        response = page.goto(PHASE + "/onboarding", wait_until="domcontentloaded", timeout=20_000)
        assert response is not None and response.status < 400
        page.wait_for_timeout(2_300)
        snapshot = page.evaluate("""() => {
          const roots=[...document.querySelectorAll('[data-testid="onboarding-tour"]')];
          const ids=roots.flatMap(root => [...root.querySelectorAll('[id]')]
            .map(element => element.id).filter(Boolean));
          const duplicates=[...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))];
          return {
            owners:roots.length,
            duplicates,
            activeTestId:document.activeElement?.getAttribute('data-testid') || ''
          };
        }""")
        assert snapshot == {
            "owners": 1,
            "duplicates": [],
            "activeTestId": "tour-next",
        }, json.dumps(snapshot, ensure_ascii=False)

        page.keyboard.press("Enter")
        page.wait_for_function("""() => {
          const root=document.querySelector('[data-testid="onboarding-tour"]');
          return root?.getAttribute('data-tour-step') === '2';
        }""", timeout=4_000)
        page.wait_for_timeout(100)
        page.keyboard.press("Tab")
        active_after_tab = page.evaluate(
            "() => document.activeElement?.getAttribute('data-testid') || ''"
        )
        assert active_after_tab == "tour-skip", active_after_tab

        page.keyboard.press("Escape")
        page.wait_for_function(
            "() => !document.querySelector('[data-testid=\"onboarding-tour\"]')",
            timeout=4_000,
        )
        assert page.evaluate("() => localStorage.getItem('phase_tour_seen')") == "true"
    finally:
        page.close()
        context.close()


@pytest.mark.requires_internet
@pytest.mark.parametrize("width", WIDTHS)
def test_cookie_customize_touch_and_axe_contract(browser, width):
    """Open the real custom-consent state before checking touch and WCAG AA."""
    assert AXE_PATH.is_file(), "run pnpm install in web/phase-detector before axe audit"
    axe = AXE_PATH.read_text(encoding="utf-8")
    context = browser.new_context(
        viewport={"width": width, "height": 844},
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true')")
    try:
        response = page.goto(PHASE + "/privacy", wait_until="domcontentloaded", timeout=20_000)
        assert response is not None and response.status < 400
        customize = page.locator('[data-testid="cookie-customize"]')
        customize.wait_for(state="visible", timeout=4_000)
        customize.click()
        analytics = page.locator('[data-testid="cookie-tier-analytics"]')
        analytics.wait_for(state="visible", timeout=4_000)

        touch = page.evaluate("""() => {
          const dialog=document.querySelector('[data-testid="cookie-consent"]');
          const analytics=document.querySelector('[data-testid="cookie-tier-analytics"]');
          const visibleLabel=analytics?.labels?.[0] || null;
          const labelBox=visibleLabel?.getBoundingClientRect();
          const controls=[...dialog.querySelectorAll('button,input:not([disabled])')]
            .filter(control => {
              const style=getComputedStyle(control), box=control.getBoundingClientRect();
              return style.display !== 'none' && style.visibility !== 'hidden' &&
                box.width > 0 && box.height > 0;
            }).map(control => {
              const box=control.getBoundingClientRect();
              const label=control.matches('input[type="checkbox"],input[type="radio"]')
                ? control.closest('label') : null;
              const hitBox=label?.getBoundingClientRect() || box;
              return {
                testId:control.getAttribute('data-testid') || control.textContent.trim(),
                width:Math.round(hitBox.width), height:Math.round(hitBox.height),
              };
            });
          return {
            labelText:(visibleLabel?.innerText || '').trim(),
            labelWidth:Math.round(labelBox?.width || 0),
            labelHeight:Math.round(labelBox?.height || 0),
            undersized:controls.filter(control => control.width < 44 || control.height < 44),
          };
        }""")
        assert "分析（可选）" in touch["labelText"], json.dumps(touch, ensure_ascii=False)
        assert touch["labelWidth"] >= 44 and touch["labelHeight"] >= 44, touch
        assert touch["undersized"] == [], json.dumps(touch, ensure_ascii=False)

        page.add_script_tag(content=axe)
        violations = page.evaluate("""async () => (await axe.run(
          document.querySelector('[data-testid="cookie-consent"]'), {
            runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}
          })).violations.filter(violation =>
            ['critical','serious'].includes(violation.impact));""")
        assert violations == [], json.dumps(violations, ensure_ascii=False)
    finally:
        page.close()
        context.close()
