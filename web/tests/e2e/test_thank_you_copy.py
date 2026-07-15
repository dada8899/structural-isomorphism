"""Deterministic browser regressions for the /thank-you copy-link control."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


ROOT = Path(__file__).resolve().parents[3]
THANK_YOU_HTML = ROOT / "web" / "frontend" / "thank-you.html"
AXE = ROOT / "web" / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"
SHARE_URL = "https://structural.bytedance.city"

pytestmark = pytest.mark.e2e


def _load_page(page: Page, setup_script: str) -> list[str]:
    source = THANK_YOU_HTML.read_text(encoding="utf-8")
    scripts = re.findall(
        r"<script\b[^>]*>(.*?)</script>", source, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(
        r"<script\b[^>]*>.*?</script>", "", source,
        flags=re.IGNORECASE | re.DOTALL,
    )
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.set_content(html, wait_until="domcontentloaded")
    page.evaluate(setup_script)
    page.add_script_tag(content=scripts[-1])
    return errors


def _assert_manual_fallback(page: Page) -> None:
    button = page.get_by_role("button", name="重试复制")
    manual = page.get_by_role("textbox", name="手动复制链接")
    expect(button).to_be_visible()
    expect(page.get_by_role("status")).to_contain_text("未能自动复制")
    expect(manual).to_be_visible()
    expect(manual).to_have_value(SHARE_URL)
    expect(manual).to_be_focused()
    assert manual.evaluate(
        "el => el.selectionStart === 0 && el.selectionEnd === el.value.length"
    )
    expect(page.locator("#ty-copy-link")).not_to_contain_text("已复制")


def test_clipboard_rejection_uses_truthful_manual_fallback(page: Page):
    errors = _load_page(page, """() => {
      window.__events = [];
      window.plausible = (...args) => window.__events.push(args);
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: { writeText: () => Promise.reject(new Error('DENIED_SENTINEL')) } });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: () => false });
    }""")
    page.locator("#ty-copy-link").click()
    _assert_manual_fallback(page)
    assert errors == []
    assert "DENIED_SENTINEL" not in page.locator("body").inner_text()
    assert page.evaluate(
        "window.__events.filter(e => e[0] === 'thank_you_share').length"
    ) == 0


def test_missing_clipboard_supports_keyboard_and_manual_copy(page: Page):
    page.set_viewport_size({"width": 320, "height": 844})
    errors = _load_page(page, """() => {
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: undefined });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: () => false });
    }""")
    button = page.get_by_role("button", name="复制链接")
    expect(button).to_have_attribute("type", "button")
    button.focus()
    button.press("Enter")
    _assert_manual_fallback(page)
    assert errors == []
    assert page.locator("#ty-copy-url").bounding_box()["height"] >= 44
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )
    assert AXE.is_file(), f"locked axe-core asset is missing: {AXE}"
    page.add_script_tag(path=str(AXE))
    violations = page.evaluate("""async () => (await axe.run(document, {
      runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa'] }
    })).violations.filter(v => ['serious', 'critical'].includes(v.impact))""")
    assert violations == []


def test_missing_clipboard_reports_only_confirmed_legacy_success(page: Page):
    errors = _load_page(page, """() => {
      window.__legacyCalls = 0;
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: undefined });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: command => { window.__legacyCalls += 1; return command === 'copy'; } });
    }""")
    page.locator("#ty-copy-link").click()
    expect(page.locator("#ty-copy-link")).to_have_text("已复制 ✓")
    expect(page.get_by_role("status")).to_have_text("链接已复制到剪贴板。")
    assert page.evaluate("window.__legacyCalls") == 1
    assert errors == []


def test_confirmed_clipboard_write_reports_success(page: Page):
    errors = _load_page(page, """() => {
      window.__writes = [];
      window.__events = [];
      window.plausible = (...args) => window.__events.push(args);
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: { writeText: url => { window.__writes.push(url); return Promise.resolve(); } } });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: () => { throw new Error('legacy fallback must not run'); } });
    }""")
    page.locator("#ty-copy-link").click()
    expect(page.locator("#ty-copy-link")).to_have_text("已复制 ✓")
    expect(page.get_by_role("status")).to_have_text("链接已复制到剪贴板。")
    expect(page.locator("#ty-copy-fallback")).to_be_hidden()
    assert page.evaluate("window.__writes") == [SHARE_URL]
    assert page.evaluate(
        "window.__events.filter(e => e[0] === 'thank_you_share').length"
    ) == 1
    assert errors == []


def test_non_thenable_clipboard_result_is_not_reported_as_success(page: Page):
    errors = _load_page(page, """() => {
      window.__events = [];
      window.plausible = (...args) => window.__events.push(args);
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: { writeText: () => undefined } });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: () => false });
    }""")
    page.locator("#ty-copy-link").click()
    _assert_manual_fallback(page)
    assert page.evaluate(
        "window.__events.filter(e => e[0] === 'thank_you_share').length"
    ) == 0
    assert errors == []


def test_pending_clipboard_times_out_and_ignores_late_success(page: Page):
    errors = _load_page(page, """() => {
      window.__events = [];
      window.plausible = (...args) => window.__events.push(args);
      Object.defineProperty(navigator, 'clipboard', { configurable: true,
        value: { writeText: () => new Promise(resolve => {
          window.__resolveClipboardWrite = resolve;
        }) } });
      Object.defineProperty(document, 'execCommand', { configurable: true,
        value: () => false });
    }""")
    page.locator("#ty-copy-link").click()
    expect(page.locator("#ty-copy-link")).to_be_disabled()
    expect(page.locator("#ty-copy-link")).to_have_attribute("aria-busy", "true")
    page.wait_for_timeout(4200)
    _assert_manual_fallback(page)
    page.evaluate("window.__resolveClipboardWrite()")
    page.wait_for_timeout(50)
    _assert_manual_fallback(page)
    assert page.evaluate(
        "window.__events.filter(e => e[0] === 'thank_you_share').length"
    ) == 0
    assert errors == []
