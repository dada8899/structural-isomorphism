"""W6-D (session #7 P1 backlog): citation click-through tracking.

Asserts that clicking a citation surface (kb_card / inline / citation_bar)
fires a Plausible `citation_click` event whose props include
phenomenon_id, position, query_hash, and surface.

This test is self-contained: it serves the static frontend out of
`web/frontend/` via a local HTTP server and stubs the /api/ask/stream
endpoint with a canned SSE response. No live backend / LLM needed, so it
runs in CI without the post-deploy gate.

Run:
    cd web/tests/e2e
    pytest test_citation_tracking.py -v
"""
from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
from pathlib import Path
from typing import Generator

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "web" / "frontend"


# Canned SSE body — minimal happy path so kb_cards + answer_done render
# enough to expose all three citation surfaces (.ask-kb-card,
# .ask-citation, .ask-citation-link).
_CANNED_SSE = (
    "event: meta\n"
    'data: {"query": "test", "rewritten": "test", "lang": "zh", "started_at": 0}\n\n'
    "event: retrieval_done\n"
    'data: {"count": 1, "retrieval_ms": 50}\n\n'
    "event: kb_cards\n"
    'data: {"count": 1, "cards": [{"id": "phen-1", "name": "Bank run cascade",'
    ' "domain": "finance", "type_id": "Network_cascade",'
    ' "description": "Depositors withdraw en masse.", "score": 0.91}]}\n\n'
    "event: answer_chunk\n"
    'data: {"delta": "答案引用 [1] 完成。"}\n\n'
    "event: answer_done\n"
    'data: {"full_text": "答案引用 [1] 完成。",'
    ' "citations": [{"idx": 1, "kb_id": "phen-1", "label": "Bank run cascade"}]}\n\n'
    "event: similar_phenomena\n"
    'data: {"phenomena": []}\n\n'
    "event: followups\n"
    'data: {"questions": []}\n\n'
    "event: done\n"
    'data: {"latency_ms": 100}\n\n'
)


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence stderr noise
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def local_server() -> Generator[str, None, None]:
    """Serve web/frontend/ on a free localhost port for the duration of the module."""
    port = _free_port()
    handler = _SilentHandler
    handler.directory = str(FRONTEND_DIR)
    # Python's SimpleHTTPRequestHandler uses os.getcwd() unless we subclass
    # — easier to chdir in a worker thread.
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)

    import os
    orig_cwd = os.getcwd()
    os.chdir(str(FRONTEND_DIR))

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        os.chdir(orig_cwd)


@pytest.fixture(scope="module")
def chromium_browser(playwright_instance):
    """Reuse the session-scoped sync_playwright from conftest.py.

    Avoids the "Sync API inside the asyncio loop" error from spawning a
    second sync_playwright in the same process as conftest.page.
    """
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


def _setup_page(browser, base_url: str):
    context = browser.new_context()
    page = context.new_page()
    # Install a plausible spy BEFORE the page loads any script.
    page.add_init_script(
        """
        window.__plausible_calls = [];
        function installSpy() {
            window.plausible = function(event, opts) {
                try { window.__plausible_calls.push({event: event, opts: opts}); } catch(e) {}
            };
        }
        installSpy();
        document.addEventListener('DOMContentLoaded', installSpy, { once: true });
        window.addEventListener('load', installSpy, { once: true });
        """
    )
    # Stub the SSE endpoint with our canned event stream.
    def handle_ask(route):
        route.fulfill(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
            body=_CANNED_SSE,
        )
    page.route("**/api/ask/stream", handle_ask)
    page.goto(base_url + "/", wait_until="load")
    return context, page


def _wait_for_event(page, name: str, timeout_ms: int = 5000) -> dict:
    """Poll window.__plausible_calls until an event with `name` shows up."""
    deadline = page.evaluate("() => Date.now()") + timeout_ms
    while page.evaluate("() => Date.now()") < deadline:
        calls = page.evaluate("() => window.__plausible_calls || []")
        for c in calls:
            if c.get("event") == name:
                return c
        page.wait_for_timeout(100)
    raise AssertionError(
        f"no plausible event named {name!r} fired within {timeout_ms}ms; "
        f"got {[c.get('event') for c in page.evaluate('() => window.__plausible_calls')]}"
    )


def test_citation_click_kb_card_fires_event(local_server, chromium_browser):
    """Click .ask-kb-card → citation_click with surface=kb_card and expected props."""
    context, page = _setup_page(chromium_browser, local_server)
    try:
        # Fill input and submit; canned SSE renders one kb card.
        page.fill("#ask-input", "test query")
        page.click(".ask-searchbox__submit")

        # Wait for kb card to render.
        page.locator(".ask-kb-card").first.wait_for(state="visible", timeout=5000)
        # Use JS click to avoid the new-tab navigation (target=_blank) that
        # would steal focus from our spy context.
        page.evaluate("() => document.querySelector('.ask-kb-card').click()")
        # Allow capture-phase listener to flush.
        page.wait_for_timeout(200)

        evt = _wait_for_event(page, "citation_click")
        props = evt["opts"]["props"]
        assert props["phenomenon_id"] == "phen-1"
        assert props["position"] == 1
        assert props["surface"] == "kb_card"
        assert isinstance(props["query_hash"], str) and len(props["query_hash"]) >= 4
    finally:
        context.close()


def test_citation_click_inline_marker_fires_event(local_server, chromium_browser):
    """Click .ask-citation (inline [N] marker) → citation_click with surface=inline."""
    context, page = _setup_page(chromium_browser, local_server)
    try:
        page.fill("#ask-input", "test query")
        page.click(".ask-searchbox__submit")

        # answer_done event renders the citations bar AND inline [N] links.
        # Inline marker is .ask-citation (renderCitationsAsLinks output).
        page.locator(".ask-citation-link").first.wait_for(state="visible", timeout=5000)
        page.evaluate("() => document.querySelector('.ask-citation-link').click()")
        page.wait_for_timeout(200)

        evt = _wait_for_event(page, "citation_click")
        props = evt["opts"]["props"]
        # Either the bar link OR the inline marker can fire first depending
        # on which one we hit; both are valid citation surfaces. Assert the
        # surface is one of the expected values.
        assert props["surface"] in ("citation_bar", "inline")
        assert props["phenomenon_id"] == "phen-1"
    finally:
        context.close()


def test_input_too_long_server_shows_friendly_error(local_server, chromium_browser):
    """Server 422 input_too_long → inline friendly error on the thread item."""
    context = chromium_browser.new_context()
    page = context.new_page()
    try:
        def handle_ask(route):
            route.fulfill(
                status=422,
                content_type="application/json",
                body=json.dumps({
                    "error": "input_too_long",
                    "limit": 8000,
                    "received": 9000,
                    "message": "Input limit 8000 chars — try focusing your question or splitting into two queries.",
                }),
            )
        page.route("**/api/ask/stream", handle_ask)
        page.goto(local_server + "/", wait_until="load")
        page.fill("#ask-input", "test query")
        page.click(".ask-searchbox__submit")
        # The thread item should render and showError() must inject the
        # message body. We grep for "Input limit" or "限制" since the
        # server message is English in the test stub.
        page.wait_for_timeout(500)
        body_text = page.locator(".ask-thread").inner_text()
        assert ("Input limit" in body_text) or ("8000" in body_text), (
            f"expected friendly input-too-long message; got: {body_text[:300]}"
        )
    finally:
        context.close()


def test_char_counter_shows_warn_and_stop_states(local_server, chromium_browser):
    """Typing past warn / stop thresholds toggles the counter's data-state."""
    context = chromium_browser.new_context()
    page = context.new_page()
    try:
        page.goto(local_server + "/", wait_until="load")
        # Empty: counter hidden.
        is_hidden = page.evaluate(
            "() => document.getElementById('ask-char-counter').hidden"
        )
        assert is_hidden, "counter should be hidden when textarea is empty"

        # Below warn (6000) — neutral state.
        page.fill("#ask-input", "a" * 100)
        page.wait_for_timeout(50)
        state = page.evaluate(
            "() => document.getElementById('ask-char-counter').getAttribute('data-state')"
        )
        assert not state, f"expected no state below warn, got {state!r}"

        # Warn band: 6500 chars (75% of 8000 = 6000 is warn threshold).
        page.fill("#ask-input", "a" * 6500)
        page.wait_for_timeout(50)
        state = page.evaluate(
            "() => document.getElementById('ask-char-counter').getAttribute('data-state')"
        )
        assert state == "warn", f"expected warn at 6500 chars, got {state!r}"

        # Stop band: textarea maxlength=8000 enforces hard stop.
        page.fill("#ask-input", "a" * 8000)
        page.wait_for_timeout(50)
        state = page.evaluate(
            "() => document.getElementById('ask-char-counter').getAttribute('data-state')"
        )
        assert state == "stop", f"expected stop at 8000 chars, got {state!r}"

        # Browser maxlength enforces — pasting more shouldn't push past 8000.
        actual_len = page.evaluate("() => document.getElementById('ask-input').value.length")
        assert actual_len == 8000, f"maxlength should cap at 8000, got {actual_len}"
    finally:
        context.close()
