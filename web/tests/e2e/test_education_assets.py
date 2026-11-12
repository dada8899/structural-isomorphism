"""Session #18 (Track D) — Education / growth-asset e2e.

Covers the "资料陈列 → 增长引擎" upgrade of /discoveries and /classes:

  1. /discoveries loads and renders discovery cards with hook headlines.
  2. A discovery card can be deep-linked via ?d=<rank> — the matching card
     gets focused (expanded + focus ring).
  3. The per-discovery "复制链接" button exists and is clickable.
  4. The "生成图片卡片" button opens a share-card preview modal with a
     non-empty <img> (canvas → dataURL).
  5. /classes detail view exposes the "用它分析你自己的问题" CTA, and the
     CTA navigates to /analyze with canonical id/q prefill params.
  6. /classes "学习路径" view groups classes into progressive bands.

Base URL: PHASE_BASE env (default local static/dev server). The suite
skips cleanly when the base URL is unreachable — the orchestrator runs
it against a live instance.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/tests/e2e/test_education_assets.py -v
"""
from __future__ import annotations

import os
import re
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Page, expect

BASE = os.environ.get("PHASE_BASE", "http://localhost:8000").rstrip("/")


def _base_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _base_reachable(BASE),
    reason=f"PHASE base URL not reachable: {BASE}",
)


# --- /discoveries ----------------------------------------------------------

def test_discoveries_page_loads_with_hook_headlines(page: Page):
    """The discoveries list renders cards, each carrying a hook headline."""
    page.goto(f"{BASE}/discoveries", wait_until="domcontentloaded")
    page.wait_for_selector(".disc-item", timeout=10000)
    cards = page.locator(".disc-item")
    assert cards.count() >= 10, f"expected >= 10 discovery cards, got {cards.count()}"
    # Every visible card has a non-empty hook headline.
    hooks = page.locator(".disc-item__hook")
    assert hooks.count() == cards.count(), "each card should have one hook headline"
    first_hook = hooks.first.inner_text().strip()
    assert len(first_hook) > 4, f"hook headline looks empty: {first_hook!r}"


def test_discovery_deep_link_focuses_card(page: Page):
    """?d=<rank> focuses the matching card (expanded + focus ring)."""
    page.goto(f"{BASE}/discoveries?d=1", wait_until="domcontentloaded")
    target = page.locator("#d-1")
    target.wait_for(state="visible", timeout=10000)
    # The focused card is auto-expanded and ringed.
    expect(target).to_have_class(re.compile(r"disc-item--focused"))
    expect(target).to_have_class(re.compile(r"disc-item--expanded"))


def test_discovery_copy_link_button_clickable(page: Page):
    """Each card exposes a 复制链接 button inside its expanded detail."""
    page.goto(f"{BASE}/discoveries?d=1", wait_until="domcontentloaded")
    page.locator("#d-1").wait_for(state="visible", timeout=10000)
    # Locate by a STABLE selector — the copy button is the first share
    # action. Filtering by has_text="复制链接" would go stale after the
    # click flips the label to "已复制 ✓".
    copy_btn = page.locator("#d-1 .share-actions__btn").first
    expect(copy_btn).to_be_visible()
    expect(copy_btn).to_contain_text("复制链接")
    # Grant clipboard so the click does not throw in headless Chromium.
    try:
        page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    except Exception:  # noqa: BLE001
        pass
    copy_btn.click()
    # Button label flips to a confirmation state.
    expect(copy_btn).to_contain_text("已复制", timeout=3000)


def test_discovery_share_image_modal_renders(page: Page):
    """生成图片卡片 opens a modal whose <img> carries a real data URL."""
    page.goto(f"{BASE}/discoveries?d=1", wait_until="domcontentloaded")
    page.locator("#d-1").wait_for(state="visible", timeout=10000)
    img_btn = page.locator("#d-1 .share-actions__btn", has_text="生成图片卡片")
    expect(img_btn).to_be_visible()
    img_btn.click()
    modal = page.locator(".share-modal")
    expect(modal).to_be_visible(timeout=5000)
    modal_img = page.locator(".share-modal__img")
    expect(modal_img).to_be_visible()
    src = modal_img.get_attribute("src") or ""
    assert src.startswith("data:image/png"), f"share card image not generated: {src[:40]!r}"
    # Modal closes cleanly.
    page.locator(".share-modal__close").click()
    expect(modal).to_have_count(0)


# --- /classes --------------------------------------------------------------

def test_classes_detail_has_analyze_cta(page: Page):
    """Opening a class detail surfaces the 用它分析你自己的问题 CTA which
    links to /analyze with a public id and private one-use handoff."""
    page.goto(f"{BASE}/classes", wait_until="domcontentloaded")
    page.wait_for_selector(".uc-card--preview", timeout=20000)
    # Navigate into the first class.
    page.locator(".uc-card--preview").first.click()
    cta = page.locator(".uc-detail__cta-btn")
    expect(cta).to_be_visible(timeout=8000)
    href = cta.get_attribute("href") or ""
    assert "/analyze" in href, f"CTA should target /analyze, got {href!r}"
    query = parse_qs(urlparse(href).query)
    assert len(query.get("id", [])) == 1, f"CTA should select an id: {href!r}"
    assert len(query.get("handoff", [])) == 1, f"CTA should create handoff: {href!r}"
    assert "q" not in query and "b_id" not in query and "text_a" not in query


def test_classes_cta_navigates_to_analyze(page: Page):
    """Clicking the class CTA actually lands on /analyze."""
    page.goto(f"{BASE}/classes", wait_until="domcontentloaded")
    page.wait_for_selector(".uc-card--preview", timeout=20000)
    page.locator(".uc-card--preview").first.click()
    cta = page.locator(".uc-detail__cta-btn")
    expect(cta).to_be_visible(timeout=8000)
    cta.click()
    page.wait_for_url("**/analyze*", timeout=10000)
    assert "/analyze" in page.url, f"did not land on /analyze: {page.url}"


def test_classes_learning_path_view_groups_cards(page: Page):
    """The 学习路径 filter switches the list into progressive bands."""
    page.goto(f"{BASE}/classes", wait_until="domcontentloaded")
    page.wait_for_selector(".uc-card--preview", timeout=20000)
    path_btn = page.locator('.uc-filter__btn[data-filter="path"]')
    expect(path_btn).to_be_visible()
    path_btn.click()
    bands = page.locator(".uc-path-band")
    expect(bands.first).to_be_visible(timeout=5000)
    assert bands.count() >= 2, f"expected >= 2 path bands, got {bands.count()}"
    # Cards still render inside the bands.
    assert page.locator(".uc-path-band .uc-card--preview").count() >= 10


def test_classes_detail_has_share_actions(page: Page):
    """Class detail view exposes the share-action row."""
    page.goto(f"{BASE}/classes", wait_until="domcontentloaded")
    page.wait_for_selector(".uc-card--preview", timeout=20000)
    page.locator(".uc-card--preview").first.click()
    share_row = page.locator(".uc-detail__share-actions .share-actions__btn")
    expect(share_row.first).to_be_visible(timeout=8000)
    assert share_row.count() >= 2, "expected copy-link + image-card buttons at minimum"
