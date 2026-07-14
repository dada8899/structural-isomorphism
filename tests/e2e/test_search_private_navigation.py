"""Real Chromium contracts for private natural-language search navigation."""
from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

import pytest


pytest.importorskip("playwright")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.e2e

FRONTEND = Path(__file__).resolve().parents[2] / "web" / "frontend"


class _SearchHandler(SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802 - stdlib hook
        parsed = urlsplit(self.path)
        if parsed.path == "/search":
            self.path = "/search.html" + (f"?{parsed.query}" if parsed.query else "")
        super().do_GET()


@pytest.fixture(scope="module")
def search_origin():
    handler = functools.partial(_SearchHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _result(kb_id: str, name: str, domain: str) -> dict:
    return {
        "id": kb_id,
        "name": name,
        "domain": domain,
        "type_id": "cascade",
        "description": "A bounded candidate record for browser testing.",
        "cross_domain": True,
    }


def _install_routes(page: Page, seen_queries: list[str]) -> None:
    def search(route) -> None:
        body = route.request.post_data_json
        query = body["query"]
        seen_queries.append(query)
        payload = {
            "count": 2,
            "results": [
                _result("kb-1", "Grid cascade candidate", "engineering"),
                _result("kb-2", "Bank-run candidate", "finance"),
            ],
            "rewritten_query": None,
            "v2_pairs_for_top": [],
            "stats": {"cross_domain_count": 2, "same_domain_count": 0},
        }
        route.fulfill(
            status=200,
            content_type="application/json; charset=utf-8",
            body=json.dumps(payload),
        )

    def assess(route) -> None:
        query = route.request.post_data_json["query"]
        low_fit = query.startswith("low fit")
        route.fulfill(
            status=200,
            content_type="application/json; charset=utf-8",
            body=json.dumps({
                "worth_score": 1 if low_fit else 4,
                "category": "test",
                "coaching": "Add a measurable boundary.",
                "rewrite_suggestion": "threshold cascade with a measurable boundary",
                "rewritten": query,
            }),
        )

    degraded = {
        "schema_version": "search-candidate-synthesis-v1",
        "synthesis_status": "degraded",
        "main_insight": "Candidate comparison safely degraded.",
        "why_these_matter": "Inspect each source record before use.",
        "primary_recommendation": None,
        "alternative_angles": [],
        "relevance_snippets": [],
    }
    page.route("**/api/search", search)
    page.route("**/api/search/assess", assess)
    page.route(
        "**/api/synthesize/stream",
        lambda route: route.fulfill(
            status=200,
            content_type="text/event-stream; charset=utf-8",
            body="event: done\ndata: " + json.dumps({"result": degraded}) + "\n\n",
        ),
    )
    page.route(
        "**/api/auth/me**",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"no session"}',
        ),
    )
    page.route("https://plausible.bytedance.city/**", lambda route: route.abort())


def _build_link(page: Page, origin: str, query: str, *, force: bool = False) -> str:
    page.goto(f"{origin}/search.html?lang=zh", wait_until="domcontentloaded")
    page.wait_for_function("typeof window.buildPrivateSearchUrl === 'function'")
    link = page.evaluate(
        """({query, force}) => window.buildPrivateSearchUrl({
          query, force, lang: 'zh', source: 'home'
        })""",
        {"query": query, "force": force},
    )
    parsed = urlsplit(link)
    assert "q=" not in link and query not in link
    assert parsed.path == "/search" and "context=" in parsed.query
    return link


def _open_private_search(
    page: Page,
    origin: str,
    query: str,
    *,
    expect_initial_results: bool = True,
) -> str:
    link = _build_link(page, origin, query)
    page.goto(origin + link, wait_until="domcontentloaded")
    expect(page.locator(".search-question__text")).to_have_text(query)
    if expect_initial_results:
        expect(page.locator(".result-card")).to_have_count(2)
    return link


def test_query_leaves_url_and_survives_reload_edit_back_and_mobile_keyboard(
    page: Page, search_origin: str,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    seen: list[str] = []
    _install_routes(page, seen)
    first = "confidential retention collapse after week three"
    _open_private_search(page, search_origin, first)

    assert first not in page.url
    assert all(key not in page.url for key in ("q=", "context=", "from_query=", "text_a="))
    assert page.locator('meta[name="referrer"]').get_attribute("content") == "no-referrer"
    state = page.evaluate("history.state.structuralPrivateNavigation")
    assert state["query"] == first and len(state["results"]) == 2
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    page.reload(wait_until="domcontentloaded")
    expect(page.locator(".search-question__text")).to_have_text(first)
    assert first not in page.url and "q=" not in page.url

    page.locator("#search-edit-btn").click()
    editor = page.locator(".search-question__editor")
    expect(editor).to_be_focused()
    second = "confidential queue collapse after threshold"
    editor.fill(second)
    editor.press("Control+Enter")
    expect(page.locator(".search-question__text")).to_have_text(second)
    assert second not in page.url and "q=" not in page.url and "context=" not in page.url

    page.go_back(wait_until="domcontentloaded")
    expect(page.locator(".search-question__text")).to_have_text(first)
    assert seen.count(first) >= 2 and second in seen
    assert page.locator("#search-edit-btn").evaluate(
        "el => el.getBoundingClientRect().height >= 44"
    )


def test_force_rewrite_replay_expiry_and_storage_failure_are_fail_closed(
    page: Page, search_origin: str,
) -> None:
    seen: list[str] = []
    _install_routes(page, seen)
    original = _open_private_search(
        page,
        search_origin,
        "low fit private question",
        expect_initial_results=False,
    )
    expect(page.locator("#assess-force-search")).to_be_visible()
    page.locator("#assess-force-search").click()
    expect(page.locator(".result-card")).to_have_count(2)
    assert "force=1" in page.url and "q=" not in page.url and "context=" not in page.url

    # The original handoff is one-use. Replaying it in a fresh history entry
    # cannot recover from the current page's unrelated state.
    page.goto(search_origin + original, wait_until="domcontentloaded")
    expect(page.locator(".search-context-lost")).to_be_visible()
    assert "q=" not in page.url and "context=" not in page.url

    page.goto(f"{search_origin}/search.html", wait_until="domcontentloaded")
    expired_key = "a" * 32
    page.evaluate(
        """key => sessionStorage.setItem(
          'structural_private_navigation:' + key,
          JSON.stringify({
            version: 1, kind: 'search', created_at: Date.now() - 16 * 60 * 1000,
            query: 'expired private query', rewritten_query: null, lang: 'zh',
            force: false, source: 'home', phenomenon_id: null, results: []
          })
        )""",
        expired_key,
    )
    page.goto(f"{search_origin}/search?context={expired_key}", wait_until="domcontentloaded")
    expect(page.locator(".search-context-lost")).to_be_visible()
    assert "expired private query" not in page.url

    page.goto(f"{search_origin}/search.html", wait_until="domcontentloaded")
    failed_url = page.evaluate(
        """() => {
          const storagePrototype = Object.getPrototypeOf(sessionStorage);
          const original = storagePrototype.setItem;
          storagePrototype.setItem = function (key, value) {
            if (String(key).startsWith('structural_private_navigation:')) throw new Error('blocked');
            return original.call(this, key, value);
          };
          try {
            return buildPrivateSearchUrl({query:'never expose this',lang:'zh',source:'home'});
          } finally {
            storagePrototype.setItem = original;
          }
        }"""
    )
    assert failed_url is None
    expect(page.locator("#private-navigation-error")).to_be_visible()
    assert page.locator("#private-navigation-error").get_attribute(
        "data-error-code"
    ) == "secure_handoff_unavailable"
    assert page.url == f"{search_origin}/search.html"

    crypto_url = page.evaluate(
        """() => {
          const descriptor = Object.getOwnPropertyDescriptor(Crypto.prototype, 'getRandomValues');
          Object.defineProperty(Crypto.prototype, 'getRandomValues', {
            configurable: true,
            value() { throw new Error('entropy unavailable'); }
          });
          try {
            return buildPrivateSearchUrl({query:'never expose crypto failure',lang:'zh',source:'home'});
          } finally {
            Object.defineProperty(Crypto.prototype, 'getRandomValues', descriptor);
          }
        }"""
    )
    assert crypto_url is None
    expect(page.locator("#private-navigation-error")).to_be_visible()
    assert page.url == f"{search_origin}/search.html"


def test_two_tabs_keep_private_questions_isolated(page: Page, search_origin: str) -> None:
    first_seen: list[str] = []
    _install_routes(page, first_seen)
    other = page.context.new_page()
    other_seen: list[str] = []
    _install_routes(other, other_seen)
    try:
        page.goto(f"{search_origin}/learn.html?lang=zh", wait_until="domcontentloaded")
        other.goto(f"{search_origin}/learn.html?lang=zh", wait_until="domcontentloaded")
        expect(page.locator("#history-sidebar")).to_be_visible()
        expect(other.locator("#history-sidebar")).to_be_visible()

        page.locator(".searchbox__input").fill("tab alpha private query")
        page.locator(".searchbox__submit").click()
        expect(page.locator(".search-question__text")).to_have_text("tab alpha private query")
        expect(page.locator(".result-card")).to_have_count(2)
        expect(page.locator(".history-entry__query")).to_have_text(
            "tab alpha private query"
        )
        expect(other.locator(".history-entry__query")).to_have_count(0)

        other.locator(".searchbox__input").fill("tab beta private query")
        other.locator(".searchbox__submit").click()
        expect(other.locator(".search-question__text")).to_have_text("tab beta private query")
        expect(other.locator(".result-card")).to_have_count(2)
        expect(other.locator(".history-entry__query")).to_have_text(
            "tab beta private query"
        )
        expect(page.locator(".history-entry__query")).to_have_text(
            "tab alpha private query"
        )
        assert "tab beta" not in page.locator("body").inner_text()
        assert "tab alpha" not in other.locator("body").inner_text()
        assert page.evaluate("history.state.structuralPrivateNavigation.query") != other.evaluate(
            "history.state.structuralPrivateNavigation.query"
        )
        assert page.evaluate("localStorage.getItem('structural_history')") is None
        assert other.evaluate("localStorage.getItem('structural_history')") is None
        assert page.evaluate(
            "JSON.parse(sessionStorage.getItem('structural_tab_history_v2'))[0].query"
        ) == "tab alpha private query"
        assert other.evaluate(
            "JSON.parse(sessionStorage.getItem('structural_tab_history_v2'))[0].query"
        ) == "tab beta private query"
    finally:
        other.close()


def test_history_is_private_by_default_and_fails_closed_on_storage_or_crypto(
    page: Page,
    search_origin: str,
) -> None:
    history_requests: list[str] = []
    page.route(
        "**/api/history**",
        lambda route: (
            history_requests.append(route.request.method),
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[]}',
            ),
        )[-1],
    )
    page.goto(f"{search_origin}/search.html", wait_until="domcontentloaded")
    page.evaluate(
        """() => localStorage.setItem(
          'structural_history',
          JSON.stringify([{query:'legacy raw history must be erased',timestamp:1}])
        )"""
    )
    page.reload(wait_until="domcontentloaded")
    assert page.evaluate("localStorage.getItem('structural_history')") is None
    assert page.evaluate("window.getHistory()") == []
    assert history_requests == []
    assert page.evaluate("window.getDeviceId()") is None
    assert "structural_device_id=" not in page.evaluate("document.cookie")

    failed_write = page.evaluate(
        """() => {
          const storagePrototype = Object.getPrototypeOf(sessionStorage);
          const originalSet = storagePrototype.setItem;
          storagePrototype.setItem = function (key, value) {
            if (this === sessionStorage && key === 'structural_tab_history_v2') {
              throw new Error('session write blocked');
            }
            return originalSet.call(this, key, value);
          };
          try {
            return window.addToHistory({query:'never use local fallback',timestamp:2});
          } finally {
            storagePrototype.setItem = originalSet;
          }
        }"""
    )
    assert failed_write == []
    assert page.evaluate("window.getHistory()") == []
    assert page.evaluate("localStorage.getItem('structural_history')") is None

    crypto_page = page.context.new_page()
    crypto_requests: list[str] = []
    crypto_page.route(
        "**/api/history**",
        lambda route: (
            crypto_requests.append(route.request.method),
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"items":[]}',
            ),
        )[-1],
    )
    crypto_page.add_init_script(
        """try { localStorage.setItem('structural_use_remote_history', '1'); } catch (_) {}
        Object.defineProperty(Crypto.prototype, 'randomUUID', {
          configurable: true,
          value() { throw new Error('entropy unavailable'); }
        });"""
    )
    try:
        crypto_page.goto(
            f"{search_origin}/search.html",
            wait_until="domcontentloaded",
        )
        assert crypto_page.evaluate("window.getDeviceId()") is None
        assert crypto_page.evaluate(
            "window.recordHistoryRemote('must not leave browser','search')"
        ) is None
        assert crypto_requests == []
        assert "structural_device_id=" not in crypto_page.evaluate("document.cookie")
    finally:
        crypto_page.close()
