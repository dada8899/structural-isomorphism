"""Mobile language journey for the candidate-classes surface."""
from __future__ import annotations

import functools
import re
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest


pytest.importorskip("playwright")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.e2e

FRONTEND = Path(__file__).resolve().parents[2] / "web" / "frontend"
AXE = FRONTEND.parent / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return


def serious_axe_violations(page: Page) -> list[dict]:
    if not page.evaluate("typeof window.axe !== 'undefined'"):
        page.add_script_tag(path=str(AXE))
    return page.evaluate(
        """async () => (await axe.run(document, {
          runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
        })).violations.filter(item => ['serious', 'critical'].includes(item.impact))
          .map(item => ({id: item.id, impact: item.impact, targets: item.nodes.map(node => node.target)}))"""
    )


@pytest.fixture(scope="module")
def classes_origin():
    handler = functools.partial(_QuietHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def test_detail_language_switch_closes_drawer_and_refreshes_list(
    page: Page, classes_origin: str,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_init_script("localStorage.clear()")
    page.route(
        "**/api/auth/me*",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}',
        ),
    )
    page.goto(
        f"{classes_origin}/classes.html?lang=zh",
        wait_until="networkidle",
        timeout=20_000,
    )

    cards = page.locator("#uc-list .uc-card--preview")
    expect(cards).to_have_count(26)
    expect(page.locator("#uc-filter [data-count-all]")).to_have_text("26")

    cards.first.click()
    detail = page.locator("#uc-view-detail")
    expect(detail).to_be_visible()
    expect(detail.locator(".uc-detail__hook")).to_contain_text("候选")
    assert detail.locator(".uc-pred__rationale, .uc-pred__text, .uc-pred__paper-link").count() == 0
    projection_audit = page.evaluate(
        """() => {
          const fields = ['prediction', 'rationale', 'status', 'paper_target', 'paper_title'];
          const leaks = [];
          const strong = [];
          const original = window.__classesData.classes[0];
          for (const cls of window.__classesData.classes) {
            renderDetail(cls);
            const html = document.getElementById('uc-view-detail').innerHTML;
            const text = document.getElementById('uc-view-detail').innerText.toLowerCase();
            for (const item of (cls.predictions || [])) {
              for (const field of fields) {
                for (const key of [field, field + '_en']) {
                  const value = item[key];
                  if (typeof value === 'string' && value.trim() && html.includes(value)) {
                    leaks.push([cls.class_id, key, value]);
                  }
                }
              }
            }
            for (const marker of ['首次验证', 'criticality 确认', '目标期刊',
                                  'first validation', 'confirms criticality', 'target journal']) {
              if (text.includes(marker)) strong.push([cls.class_id, marker]);
            }
          }
          renderDetail(original);
          return { leaks, strong };
        }"""
    )
    assert projection_audit == {"leaks": [], "strong": []}

    menu = page.locator("#site-menu-btn")
    drawer = page.locator("#site-menu-drawer")
    menu.click()
    expect(drawer).to_have_class(re.compile(r"site-menu--open"))
    page.locator("#site-menu-lang-toggle").click()

    expect(page.locator("html")).to_have_attribute("lang", "en")
    expect(drawer).to_be_hidden(timeout=1_500)
    expect(menu).to_have_attribute("aria-expanded", "false")
    expect(menu).to_be_focused(timeout=1_500)
    detail_hook = detail.locator(".uc-detail__hook").inner_text().casefold()
    assert (
        "candidate" in detail_hook
        or "test" in detail_hook
        or "not an established law" in detail_hook
    )

    detail.locator("[data-back-link]").first.click()
    expect(page.locator("#uc-view-list")).to_be_visible()
    expect(cards).to_have_count(26)

    count_nodes = page.locator(
        "#uc-filter [data-count-all], #uc-filter [data-count-manual], "
        "#uc-filter [data-count-llm], #uc-filter [data-count-unclassified]"
    )
    expect(count_nodes).to_have_count(4)
    assert all(re.fullmatch(r"\d+", value) for value in count_nodes.all_inner_texts())
    assert page.locator("#uc-filter [data-i18n]").all_inner_texts() == [
        "All", "Curated", "AI-assisted", "Later candidates", "Learning path",
    ]

    hooks = page.locator("#uc-list .uc-card__hook").all_inner_texts()
    assert len(hooks) == 26
    assert all(
        "candidate" in hook.casefold()
        or "test" in hook.casefold()
        or "not an established law" in hook.casefold()
        for hook in hooks
    )


def test_mobile_touch_targets_keyboard_focus_and_unclassified_source(
    page: Page, classes_origin: str,
) -> None:
    page.add_init_script("localStorage.clear()")
    page.route(
        "**/api/auth/me*",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}',
        ),
    )
    page.goto(f"{classes_origin}/classes.html?lang=zh", wait_until="networkidle")
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    filter_heights = page.locator("#uc-filter .uc-filter__btn").evaluate_all(
        "nodes => nodes.map(node => node.getBoundingClientRect().height)"
    )
    assert filter_heights and min(filter_heights) >= 44
    unclassified = page.locator('#uc-filter [data-filter="unclassified"]')
    expect(unclassified.locator("[data-count-unclassified]")).to_have_text("3")
    unclassified.click()
    cards = page.locator("#uc-list .uc-card--preview")
    expect(cards).to_have_count(3)
    assert all("来源未分类" in text for text in page.locator(".uc-card__badges").all_inner_texts())

    origin = cards.first
    origin.focus()
    origin.press("Enter")
    expect(page.locator("#uc-view-detail")).to_be_visible()
    expect(page.locator("#uc-view-detail [data-back-link]").first).to_be_focused()
    targets = page.locator(
        "#uc-view-detail a:visible, #uc-view-detail button:visible"
    ).evaluate_all("nodes => nodes.map(node => node.getBoundingClientRect().height)")
    assert targets and min(targets) >= 44
    page.locator("#uc-view-detail [data-back-link]").first.press("Enter")
    expect(page.locator("#uc-view-list")).to_be_visible()
    expect(origin).to_be_focused()
    assert page.evaluate("document.activeElement.closest('[hidden]') === null")


def test_mobile_data_arrival_keeps_stats_filter_and_list_geometry_stable(
    page: Page, classes_origin: str,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_init_script(
        """(() => {
          const originalFetch = window.fetch.bind(window);
          window.fetch = async (...args) => {
            const response = await originalFetch(...args);
            const url = new URL(String(args[0]), location.href);
            if (url.pathname.endsWith('/assets/data/universality-classes.json')) {
              await new Promise(resolve => setTimeout(resolve, 1200));
            }
            return response;
          };
        })()"""
    )
    page.route(
        "**/api/auth/me*",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}',
        ),
    )
    page.goto(f"{classes_origin}/classes.html?lang=zh", wait_until="domcontentloaded")
    stats = page.locator("#uc-hero-stats")
    expect(stats.locator(".uc-hero__stat")).to_have_count(4)
    expect(stats).to_have_attribute("aria-busy", "true")
    before = page.evaluate(
        """() => Object.fromEntries(['#uc-filter', '#uc-list'].map(selector => {
          const box = document.querySelector(selector).getBoundingClientRect();
          return [selector, {top: box.top, height: box.height}];
        }))"""
    )

    expect(page.locator("#uc-list .uc-card--preview")).to_have_count(26)
    expect(stats).to_have_attribute("aria-busy", "false")
    after = page.evaluate(
        """() => Object.fromEntries(['#uc-filter', '#uc-list'].map(selector => {
          const box = document.querySelector(selector).getBoundingClientRect();
          return [selector, {top: box.top, height: box.height}];
        }))"""
    )
    assert abs(after["#uc-filter"]["top"] - before["#uc-filter"]["top"]) <= 1
    assert abs(after["#uc-filter"]["height"] - before["#uc-filter"]["height"]) <= 1
    assert abs(after["#uc-list"]["top"] - before["#uc-list"]["top"]) <= 1


@pytest.mark.parametrize("width", [320, 390])
def test_mobile_visible_links_use_real_44px_hitboxes(
    page: Page, classes_origin: str, width: int,
) -> None:
    page.set_viewport_size({"width": width, "height": 844})
    page.add_init_script("localStorage.clear()")
    page.route(
        "**/api/auth/me*",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}',
        ),
    )
    page.goto(f"{classes_origin}/classes.html?lang=zh", wait_until="networkidle")
    expect(page.locator("#uc-list .uc-card--preview")).to_have_count(26)

    links = page.locator("a[href]:visible")
    audit = links.evaluate_all(
        """nodes => nodes.map(node => {
          const box = node.getBoundingClientRect();
          const style = getComputedStyle(node);
          return {
            href: node.getAttribute('href'),
            text: (node.innerText || node.getAttribute('aria-label') || '').trim(),
            height: Number(box.height.toFixed(2)),
            pointerEvents: style.pointerEvents,
          };
        })"""
    )
    assert audit
    assert [item for item in audit if item["height"] < 44] == []
    assert [item for item in audit if item["pointerEvents"] == "none"] == []

    footnote_links = page.locator("#uc-footnote a[href]:visible")
    expect(footnote_links).to_have_count(3)
    footnote_audit = footnote_links.evaluate_all(
        """nodes => nodes.map(node => {
          node.scrollIntoView({block: 'center'});
          const box = node.getBoundingClientRect();
          const hit = document.elementFromPoint(
            box.left + box.width / 2,
            box.top + box.height / 2,
          );
          return {
            href: node.getAttribute('href'),
            height: Number(box.height.toFixed(2)),
            centerHitsAnchor: Boolean(hit && (hit === node || node.contains(hit))),
          };
        })"""
    )
    assert all(item["height"] >= 44 for item in footnote_audit)
    assert all(item["centerHitsAnchor"] for item in footnote_audit)
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0
    assert serious_axe_violations(page) == []

    page.locator("#uc-list .uc-card--preview").first.click()
    clipped = page.locator(
        "#uc-view-detail .uc-detail__badges, "
        "#uc-view-detail .uc-detail__badges > *"
    ).evaluate_all(
        """nodes => nodes.map(node => {
          const box = node.getBoundingClientRect();
          return {className: node.className, left: box.left, right: box.right, width: box.width};
        }).filter(box => box.width > 0 && (box.left < -0.5 || box.right > innerWidth + 0.5))"""
    )
    assert clipped == []

    equation_lines = page.locator("#uc-view-detail .uc-eq-line")
    assert equation_lines.count() >= 1
    assert all(
        value == "0" for value in equation_lines.evaluate_all(
            "nodes => nodes.map(node => node.getAttribute('tabindex'))"
        )
    )
    overflow_index = page.evaluate(
        """() => Array.from(document.querySelectorAll('#uc-view-detail .uc-eq-line'))
          .findIndex(node => node.scrollWidth > node.clientWidth + 1)"""
    )
    if overflow_index >= 0:
        scrollable = equation_lines.nth(overflow_index)
        scrollable.focus()
        expect(scrollable).to_be_focused()
        before = scrollable.evaluate("node => node.scrollLeft")
        page.keyboard.press("ArrowRight")
        page.wait_for_timeout(100)
        assert scrollable.evaluate("node => node.scrollLeft") > before

    assert serious_axe_violations(page) == []

    image_button = page.locator(
        "#uc-view-detail .share-actions__btn", has_text="生成图片卡片",
    )
    image_button.click()
    modal = page.locator(".share-modal")
    expect(modal).to_be_visible()
    dialog = modal.get_by_role("dialog")
    expect(dialog).to_have_attribute("aria-labelledby", "share-modal-title")
    expect(dialog).to_have_attribute("aria-describedby", "share-modal-hint")
    expect(modal.locator(".share-modal__title")).to_have_text("分享图片卡片")
    assert page.evaluate(
        "document.querySelector('main').hasAttribute('inert')"
    ) is True

    modal_controls = modal.locator("button:visible")
    expect(modal_controls).to_have_count(3)
    control_audit = modal_controls.evaluate_all(
        """nodes => nodes.map(node => ({
          label: node.innerText || node.getAttribute('aria-label'),
          height: Number(node.getBoundingClientRect().height.toFixed(2)),
          focusShadow: getComputedStyle(node).boxShadow,
        }))"""
    )
    assert all(item["height"] >= 44 for item in control_audit)
    close_button = modal.locator(".share-modal__close")
    copy_button = modal.locator('[data-act="copy"]')
    expect(close_button).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(copy_button).to_be_focused()
    page.keyboard.press("Tab")
    expect(close_button).to_be_focused()
    assert "none" not in close_button.evaluate(
        "node => getComputedStyle(node).boxShadow"
    )
    page.keyboard.press("Escape")
    expect(modal).to_have_count(0)
    expect(image_button).to_be_focused()
    assert page.evaluate(
        "document.querySelector('main').hasAttribute('inert')"
    ) is False
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


def test_classes_mobile_styles_have_matching_cache_versions() -> None:
    page_source = (FRONTEND / "classes.html").read_text(encoding="utf-8")
    classes_css = re.search(
        r'/assets/css/classes\.css\?v=([^"\']+)', page_source,
    )
    responsive_css = re.search(
        r'/assets/css/responsive\.css\?v=([^"\']+)', page_source,
    )
    assert classes_css is not None
    assert responsive_css is not None
    assert classes_css.group(1) == responsive_css.group(1)
    assert responsive_css.group(1) == "20260714n2"
