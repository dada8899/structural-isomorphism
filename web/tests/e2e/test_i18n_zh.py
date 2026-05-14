"""W11-B i18n e2e: Chinese landing + language switcher.

Asserts:
  - /zh renders the Chinese hero ("每日 1000+ ...")
  - Click "EN" switcher from /zh → navigate to /
  - Click "中" switcher from / → navigate to /zh
  - localStorage persistence after refresh (auto-redirect to last-chosen)

Run modes (matching test_phase_landing_v2.py):
  - Default → live prod https://phase.bytedance.city
  - PHASE_BASE=http://localhost:3718 → locally-booted `next start -p 3718`

The default targets prod so failures expose deployed regressions. CI runs
the test against a local build via PHASE_BASE override.
"""
from __future__ import annotations

import os
import pytest


BASE = os.environ.get("PHASE_BASE", "https://phase.bytedance.city").rstrip("/")


def _hero_text(page) -> str:
    h1 = page.locator('[data-testid="hero-headline"]').first
    h1.wait_for(state="visible", timeout=8000)
    return h1.inner_text()


def test_zh_landing_hero_in_chinese(page):
    """/zh hero contains the W11-B Chinese positioning line."""
    page.goto(BASE + "/zh", wait_until="domcontentloaded", timeout=30000)
    text = _hero_text(page)
    assert "每日" in text and "1000+" in text and "上市公司" in text, (
        f"/zh hero missing Chinese positioning: {text!r}"
    )
    # The original EN headline must not be the primary on /zh.
    assert "Daily structural signals" not in text, (
        f"/zh hero unexpectedly shows EN copy: {text!r}"
    )


def test_zh_subheadline_translated(page):
    """/zh body must reflect translated CTA labels."""
    page.goto(BASE + "/zh", wait_until="domcontentloaded", timeout=30000)
    primary = page.locator('[data-testid="cta-primary"]').first
    primary.wait_for(state="visible", timeout=5000)
    label = primary.inner_text().strip()
    assert "浏览" in label or "公司表" in label, (
        f"/zh primary CTA not translated: {label!r}"
    )


def test_language_switcher_renders_both_locales(page):
    """TopNav language switcher visible with EN and 中 buttons on /."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    sw = page.locator('[data-testid="lang-switcher"]').first
    sw.wait_for(state="attached", timeout=5000)
    en = page.locator('[data-testid="lang-en"]').first
    zh = page.locator('[data-testid="lang-zh"]').first
    en.wait_for(state="attached", timeout=5000)
    zh.wait_for(state="attached", timeout=5000)


def test_switch_en_to_zh(page):
    """Click 中 from /, end up on /zh."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    zh_btn = page.locator('[data-testid="lang-zh"]').first
    zh_btn.wait_for(state="visible", timeout=5000)
    href = zh_btn.get_attribute("href")
    assert href and "/zh" in href, f"中 link href wrong: {href!r}"
    zh_btn.click()
    page.wait_for_url("**/zh", timeout=10000)
    text = _hero_text(page)
    assert "每日" in text, f"after switch, hero not in Chinese: {text!r}"


def test_switch_zh_to_en(page):
    """Click EN from /zh, end up on /."""
    page.goto(BASE + "/zh", wait_until="domcontentloaded", timeout=30000)
    en_btn = page.locator('[data-testid="lang-en"]').first
    en_btn.wait_for(state="visible", timeout=5000)
    href = en_btn.get_attribute("href")
    assert href is not None
    # Either "/" or absolute with /. (Not /zh.)
    assert href.endswith("/") or not href.endswith("/zh"), (
        f"EN link href shouldn't keep /zh: {href!r}"
    )
    en_btn.click()
    # The base URL "/" — we wait for the page where headline is English.
    page.wait_for_function(
        """() => {
            const h = document.querySelector('[data-testid=\"hero-headline\"]');
            return h && /Daily structural signals/i.test(h.innerText);
        }""",
        timeout=10000,
    )


def test_localstorage_persists_locale_choice(page):
    """Choosing zh sets localStorage; reload + /  ⇒ auto-redirect once to /zh."""
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    zh_btn = page.locator('[data-testid="lang-zh"]').first
    zh_btn.wait_for(state="visible", timeout=5000)
    zh_btn.click()
    page.wait_for_url("**/zh", timeout=10000)
    # Confirm localStorage written.
    stored = page.evaluate(
        "() => window.localStorage.getItem('phase-detector-locale')"
    )
    assert stored == "zh", f"localStorage locale not persisted: {stored!r}"
    # Clear the session redirect flag so auto-redirect fires on next /.
    page.evaluate(
        "() => window.sessionStorage.removeItem('phase-detector-locale-redirected')"
    )
    # Now navigate to / — should auto-redirect to /zh because localStorage='zh'.
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_url("**/zh", timeout=10000)


def test_readme_language_switcher_link_exists_in_repo():
    """Sanity: README.md must contain the language-switcher line we shipped.

    This is a repo-level invariant — keeps the EN README from drifting to
    look unchanged while the Chinese page exists. Not an HTTP test.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[3]
    readme = (root / "README.md").read_text(encoding="utf-8")
    assert "README-zh.md" in readme, (
        "README.md missing language switcher to README-zh.md"
    )
    readme_zh = root / "README-zh.md"
    assert readme_zh.exists() and readme_zh.stat().st_size > 1024, (
        "README-zh.md missing or too short"
    )
