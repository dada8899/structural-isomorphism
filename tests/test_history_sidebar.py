"""Sidebar breakpoint/keyboard regression; browser cases are local-only."""

from __future__ import annotations

import functools
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading
from urllib.parse import parse_qs, urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "web/frontend"
QUERY = "sidebar navigation synthetic private question"


def wait_for_desktop_sidebar(page):
    # CSS responds before the resize handler; wait for the complete a11y state.
    page.wait_for_function("""() => {
      const sidebar = document.getElementById('history-sidebar');
      return sidebar && sidebar.getAttribute('role') === null &&
        sidebar.getAttribute('aria-modal') === null &&
        sidebar.getAttribute('aria-hidden') === 'false' &&
        !sidebar.hasAttribute('inert') &&
        !sidebar.classList.contains('history-sidebar--open') &&
        !document.body.classList.contains('history-sidebar--drawer-open');
    }""")


def test_breakpoint_does_not_flush_layout():
    subprocess.run(
        ["node", str(FRONTEND / "tests/test_historySidebarPerformance.js")],
        cwd=ROOT, check=True, capture_output=True, text=True,
    )


@pytest.fixture(scope="module")
def sidebar_origin():
    class StaticHandler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(StaticHandler, directory=str(FRONTEND)),
    )
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()


@pytest.fixture(scope="module")
def sidebar_browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            assert browser.version.split(".")[0] == "147"
            yield browser
        finally:
            browser.close()


@pytest.fixture
def sidebar_page(sidebar_browser, sidebar_origin):
    context = sidebar_browser.new_context(viewport={"width": 1023, "height": 900})
    page = context.new_page()
    unexpected = []
    errors = []
    page.on("pageerror", lambda exc: errors.append(type(exc).__name__))

    def controlled_route(route):
        parsed = urlsplit(route.request.url)
        if parsed.netloc != urlsplit(sidebar_origin).netloc:
            unexpected.append("external request")
            route.abort()
        elif parsed.path == "/api/auth/me":
            route.fulfill(status=401, content_type="application/json", body='{"error":"no session"}')
        elif parsed.path == "/api/favorites":
            route.fulfill(status=401, content_type="application/json", body='{"error":"no session"}')
        elif parsed.path.startswith("/api/"):
            unexpected.append((route.request.method, parsed.path))
            route.fulfill(status=599, content_type="application/json", body='{"error":"unexpected API"}')
        elif parsed.path == "/search":
            route.fulfill(
                status=200, content_type="text/html",
                body="<html><main id='controlled-search-target'>History handoff target</main></html>",
            )
        elif parsed.path == "/tools":
            route.fulfill(
                status=200, content_type="text/html", body=(FRONTEND / "tools.html").read_text(),
            )
        else:
            route.continue_()

    page.route("**/*", controlled_route)
    page.add_init_script(
        """if (localStorage.getItem('structural_sidebar_collapsed') === null) {
          localStorage.setItem('structural_sidebar_collapsed','1');
        }
        localStorage.setItem('cookie_consent_v1',JSON.stringify({essential:true,analytics:false,marketing:false,source:'explicit',version:1,timestamp:0}));
        sessionStorage.setItem('structural_tab_history_v2',JSON.stringify([{query:%s,timestamp:1}]));
        """ % json.dumps(QUERY)
    )
    try:
        yield page, sidebar_origin
        assert unexpected == []
        assert errors == []
    finally:
        context.close()


@pytest.mark.e2e
def test_sidebar_breakpoints_resize_and_collapsed_preference(sidebar_page):
    from playwright.sync_api import expect

    page, origin = sidebar_page
    page.goto(origin + "/analyze.html", wait_until="load")
    sidebar = page.locator("#history-sidebar")
    trigger = page.locator("#history-sidebar-trigger")
    toggle = page.locator(".history-sidebar__toggle")
    expect(trigger).to_be_visible()
    expect(sidebar).to_have_attribute("role", "dialog")
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    assert sidebar.get_attribute("inert") is not None

    trigger.click()
    expect(sidebar).to_have_attribute("aria-modal", "true")
    page.set_viewport_size({"width": 1024, "height": 900})
    expect(trigger).to_be_hidden()
    wait_for_desktop_sidebar(page)
    expect(sidebar).to_have_attribute("aria-hidden", "false")
    assert sidebar.get_attribute("role") is None
    assert sidebar.get_attribute("aria-modal") is None
    assert sidebar.get_attribute("inert") is None
    assert "history-sidebar--open" not in sidebar.get_attribute("class")
    assert page.evaluate("document.body.classList.contains('history-sidebar-collapsed')")
    toggle.click()
    assert page.evaluate("localStorage.getItem('structural_sidebar_collapsed')") == "0"
    page.reload(wait_until="load")
    assert not page.evaluate("document.body.classList.contains('history-sidebar-collapsed')")
    toggle.click()
    assert page.evaluate("localStorage.getItem('structural_sidebar_collapsed')") == "1"
    page.reload(wait_until="load")
    assert page.evaluate("document.body.classList.contains('history-sidebar-collapsed')")

    page.set_viewport_size({"width": 390, "height": 900})
    expect(trigger).to_be_visible()
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    trigger.click()
    expect(toggle).to_be_focused()
    page.set_viewport_size({"width": 1280, "height": 900})
    expect(trigger).to_be_hidden()
    wait_for_desktop_sidebar(page)
    expect(sidebar).to_have_attribute("aria-hidden", "false")
    assert sidebar.get_attribute("inert") is None
    page.set_viewport_size({"width": 1023, "height": 900})
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    assert sidebar.get_attribute("inert") is not None


@pytest.mark.e2e
def test_sidebar_focus_trap_escape_and_backdrop(sidebar_page):
    from playwright.sync_api import expect

    page, origin = sidebar_page
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(origin + "/analyze.html", wait_until="load")
    sidebar = page.locator("#history-sidebar")
    trigger = page.locator("#history-sidebar-trigger")
    first = page.locator(".history-sidebar__toggle")
    last = page.locator(".history-sidebar__clear")
    trigger.click()
    expect(first).to_be_focused()
    expect(trigger).to_have_attribute("aria-expanded", "true")
    assert sidebar.get_attribute("inert") is None
    first.press("Shift+Tab")
    expect(last).to_be_focused()
    last.press("Tab")
    expect(first).to_be_focused()
    first.press("Escape")
    expect(trigger).to_be_focused()
    expect(sidebar).to_have_attribute("aria-modal", "false")
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    expect(trigger).to_have_attribute("aria-expanded", "false")
    assert sidebar.get_attribute("inert") is not None

    trigger.click()
    expect(first).to_be_focused()
    page.locator("#history-sidebar-backdrop").click(position={"x": 380, "y": 450})
    expect(trigger).to_be_focused()
    expect(sidebar).to_have_attribute("aria-hidden", "true")
    assert sidebar.get_attribute("inert") is not None


@pytest.mark.e2e
def test_sidebar_private_history_and_main_navigation(sidebar_page):
    from playwright.sync_api import expect

    page, origin = sidebar_page
    page.set_viewport_size({"width": 1280, "height": 900})
    page.goto(origin + "/analyze.html", wait_until="load")
    page.locator(".history-sidebar__toggle").click()
    link = page.locator(".history-entry__link")
    expect(link).to_have_attribute("href", "/search")
    expect(link).to_contain_text(QUERY)
    link.click()
    expect(page.locator("#controlled-search-target")).to_be_visible()
    parsed = urlsplit(page.url)
    assert parsed.path == "/search"
    assert QUERY not in page.url
    assert set(parse_qs(parsed.query)) == {"context"}
    key = parse_qs(parsed.query)["context"][0]
    state = page.evaluate("key => sessionStorage.getItem('structural_private_navigation:' + key)", key)
    assert json.loads(state)["query"] == QUERY

    page.goto(origin + "/analyze.html", wait_until="load")
    tools = page.locator(".site-header__nav a[href='/tools']")
    expect(tools).to_be_visible()
    tools.click()
    page.wait_for_url(origin + "/tools")
    expect(page.locator(".tool-card")).to_have_count(8)
    page.locator(".site-header__logo").click()
    page.wait_for_url(origin + "/")
    expect(page.locator("#history-sidebar")).to_be_visible()
