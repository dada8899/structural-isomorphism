"""Local Chromium functional checks; no performance measurement or external API."""

from __future__ import annotations

import functools
import hashlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import os
import json
from pathlib import Path
import socket
import sys
import threading
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts import beta_perf_audit as fixtures


@pytest.fixture(scope="module")
def local_origin():
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),
        functools.partial(Handler, directory=str(ROOT / "web/frontend")),
    )
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        assert not thread.is_alive()
        with socket.socket() as probe:
            assert probe.connect_ex(server.server_address) != 0


@pytest.fixture(scope="module")
def local_browser():
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        assert browser.version.split(".")[0] == "147"
        try:
            yield browser
        finally:
            browser.close()
            assert not browser.is_connected()


@pytest.mark.parametrize("surface", ["home", "analyze"])
@pytest.mark.parametrize("viewport", [{"width": 390, "height": 844}, {"width": 1280, "height": 800}])
@pytest.mark.e2e
def test_header_scroll_visual_keyboard_and_restore(local_browser, local_origin, surface, viewport):
    request, stream = fixtures._analyze_fixture()
    context = local_browser.new_context(viewport=viewport, reduced_motion="reduce")
    page = context.new_page()
    origin = urlsplit(local_origin)
    state = fixtures._page_setup_factory(
        surface, fixtures.PAGES[surface], (origin.scheme, origin.hostname, origin.port),
        request, stream,
    )(page, "functional", 1)
    source = Path(os.environ.get("HEADER_SCROLL_SOURCE", ROOT / "web/frontend/assets/js/utils.js"))
    if os.environ.get("HEADER_SCROLL_SOURCE"):
        page.route("**/assets/js/utils.js*", lambda route: route.fulfill(
            status=200, content_type="application/javascript", body=source.read_text(),
        ))
    page.add_init_script("""localStorage.setItem('structural_sidebar_collapsed','1');
      localStorage.setItem('cookie_consent_v1',JSON.stringify({essential:true,
        analytics:false,marketing:false,source:'explicit',version:1,timestamp:0}));""")
    try:
        page.goto(local_origin + "/" + fixtures.PAGES[surface].path, wait_until="load")
        expect(page.locator(fixtures.PAGES[surface].ready_selector).first).to_be_visible()
        header = page.locator(".site-header")
        expect(header).to_be_visible()
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_function("!document.querySelector('.site-header').classList.contains('scrolled')")
        top = header.bounding_box()
        position = header.evaluate("h => getComputedStyle(h).position")
        before_border = header.evaluate("h => getComputedStyle(h).borderBottomColor")
        focus = page.locator("#site-menu-btn" if viewport["width"] == 390 else ".site-header__lang-toggle")
        focus.focus()
        expect(focus).to_be_focused()
        page.keyboard.press("Tab")
        assert page.evaluate("document.activeElement !== document.body")
        focus.focus()
        page.evaluate("window.scrollTo(0, 300)")
        page.wait_for_function("scrollY > 4 && document.querySelector('.site-header').classList.contains('scrolled')")
        expect(focus).to_be_focused()
        scrolled = header.bounding_box()
        assert abs(scrolled["height"] - top["height"]) < 1
        assert abs(scrolled["width"] - top["width"]) < 1
        assert header.evaluate("h => getComputedStyle(h).position") == position
        page.wait_for_function(
            "before => getComputedStyle(document.querySelector('.site-header')).borderBottomColor !== before",
            arg=before_border,
        )
        scrolled_border = header.evaluate("h => getComputedStyle(h).borderBottomWidth")

        # Reinitialization after DOM churn must not steal keyboard focus.
        page.evaluate("for (let i=0;i<5;i++) window.initHeaderScroll()")
        expect(focus).to_be_focused()
        if viewport["width"] == 390:
            focus.press("Enter")
            expect(focus).to_have_attribute("aria-expanded", "true")
            page.wait_for_function("document.querySelector('#site-menu-drawer').classList.contains('site-menu--open')")
            expect(page.locator("#site-menu-drawer .site-menu__close")).to_be_focused()
            page.keyboard.press("Shift+Tab")
            expect(page.locator("#site-menu-lang-toggle")).to_be_focused()
            page.keyboard.press("Tab")
            expect(page.locator("#site-menu-drawer .site-menu__close")).to_be_focused()
            page.keyboard.press("Escape")
            expect(focus).to_have_attribute("aria-expanded", "false")
            expect(focus).to_be_focused()

        # Real history traversal checks native restoration, not a fake pageshow.
        page.evaluate("document.activeElement.blur(); window.scrollTo(0, 300)")
        page.wait_for_function("scrollY > 4 && document.querySelector('.site-header').classList.contains('scrolled')")
        page.evaluate("history.replaceState(null, '', location.pathname + location.search + '#header-scroll')")
        page.goto(local_origin + "/tools.html", wait_until="load")
        page.go_back(wait_until="load")
        expect(page.locator(fixtures.PAGES[surface].ready_selector).first).to_be_visible()
        page.wait_for_function("scrollY > 4 && document.querySelector('.site-header').classList.contains('scrolled')")
        page.evaluate("window.scrollTo(0, 0)")
        page.wait_for_function("scrollY === 0 && !document.querySelector('.site-header').classList.contains('scrolled')")
        artifacts = os.environ.get("HEADER_SCROLL_ARTIFACT_DIR")
        if artifacts:
            page.screenshot(path=str(Path(artifacts) / f"{surface}-{viewport['width']}.png"))
            (Path(artifacts) / f"{surface}-{viewport['width']}-visual.json").write_text(json.dumps({
                "utils_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "top": top, "scrolled": scrolled, "position": position,
                "scrolled_border": scrolled_border,
                "keyboard_and_restoration": "passed",
            }, indent=2) + "\n")
        assert state["invalid_api"] == []
        assert state["unknown_requests"] == []
        assert state["page_errors"] == []
        assert state["bad_static_responses"] == []
    finally:
        context.close()
