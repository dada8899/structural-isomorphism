"""Browser gates for the typed, unified Structural/Phase bookmark library."""

from __future__ import annotations

import functools
import json
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

pytest.importorskip("playwright")
from playwright.sync_api import Page, expect  # noqa: E402

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "web" / "frontend"
AXE = ROOT / "web" / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"


@pytest.fixture(scope="module")
def origin():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(FRONTEND))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def _axe(page: Page) -> list[dict]:
    assert AXE.is_file(), f"locked axe-core missing: {AXE}"
    page.add_script_tag(path=str(AXE))
    return page.evaluate(
        """async () => (await axe.run(document, {
          runOnly: {type: 'tag', values: ['wcag2a', 'wcag2aa']}
        })).violations.filter(v => ['serious', 'critical'].includes(v.impact))"""
    )


def _auth_routes(page: Page, favorites: dict, merge: dict | None = None) -> None:
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok":true,"user":{"email":"owner@example.test"}}',
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"items":[],"has_more":false}'
        ),
    )

    def favorites_handler(route):
        if route.request.method == "POST":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(merge if merge is not None else favorites),
            )
        else:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(favorites))

    page.route("**/api/favorites", favorites_handler)
    page.route(
        "**/api/favorites/merge",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(merge if merge is not None else favorites),
        ),
    )


def test_authenticated_library_syncs_only_confirmed_and_keeps_failed_remove(
    page: Page, origin: str
):
    page.set_viewport_size({"width": 390, "height": 844})
    page.add_init_script(
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Local candidate',a_id:'local-source',b_id:'local-target',"
        "analyze_url:'javascript:alert(1)',timestamp:1}]));"
    )
    server_item = {
        "schema_version": "bookmark-v2",
        "bookmark_id": "bm_aaaaaaaaaaaaaaaaaaaaaaaa",
        "kind": "structural_analysis",
        "title": "Server candidate",
        "query": "Server question",
        "source_id": "server-source",
        "target_id": "server-target",
        "href": "/analyze?id=server-target",
        "source": "Structural",
        "created_at": "2026-07-13T00:00:00+00:00",
    }
    phase_item = {
        "schema_version": "bookmark-v2",
        "bookmark_id": "bm_bbbbbbbbbbbbbbbbbbbbbbbb",
        "kind": "phase_company",
        "title": "AAPL",
        "href": "https://phase.bytedance.city/company/AAPL",
        "source": "Phase",
        "created_at": None,
    }
    synced_local = {
        "schema_version": "bookmark-v2",
        "bookmark_id": "bm_cccccccccccccccccccccccc",
        "kind": "structural_analysis",
        "title": "Local candidate",
        "query": "Local candidate",
        "source_id": "local-source",
        "target_id": "local-target",
        "href": "/analyze?id=local-target",
        "source": "Structural",
        "created_at": "2026-07-13T00:00:00+00:00",
    }
    initial = {
        "schema_version": "favorites-v2",
        "authenticated": True,
        "tickers": ["AAPL"],
        "bookmarks": [server_item, phase_item],
    }
    merged = {
        **initial,
        "bookmarks": [server_item, phase_item, synced_local],
        "confirmed_bookmark_ids": [synced_local["bookmark_id"]],
        "dropped_bookmark_ids": [],
    }
    _auth_routes(page, initial, merged)
    page.route(
        "**/api/favorites/bookmarks/*",
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"error":"retry"}'
        ),
    )

    page.goto(origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.get_by_text("Server candidate", exact=True)).to_be_visible()
    expect(page.get_by_text("Local candidate", exact=True)).to_be_visible()
    expect(page.locator(".myr-favorite", has_text="AAPL")).to_contain_text(
        "Phase 子产品账户收藏"
    )
    expect(page.get_by_role("link", name="打开收藏：Local candidate")).to_have_attribute(
        "href", "/analyze?id=local-target"
    )
    assert page.evaluate("JSON.parse(localStorage.getItem('structural_favorites')).length") == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    remove = page.get_by_role("button", name="移除收藏：Server candidate")
    assert remove.bounding_box()["height"] >= 44
    remove.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_text("Server candidate", exact=True)).to_be_visible()
    expect(page.get_by_role("alert")).to_contain_text("移除没有完成")
    assert _axe(page) == []


@pytest.mark.parametrize("width", (320, 1280))
def test_anonymous_library_rebuilds_canonical_href_and_removes_locally(
    page: Page, origin: str, width: int
):
    page.set_viewport_size({"width": width, "height": 844})
    page.add_init_script(
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Safe local',a_id:'source-1',b_id:'target-1',"
        "analyze_url:'javascript:alert(1)',timestamp:1}]));"
    )
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"unauthorized"}'
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body='{"error":"unauthorized"}'
        ),
    )
    page.goto(origin + "/reports.html", wait_until="domcontentloaded")
    link = page.get_by_role("link", name="打开收藏：Safe local")
    expect(link).to_have_attribute(
        "href", "/analyze?id=target-1"
    )
    remove = page.get_by_role("button", name="移除收藏：Safe local")
    assert remove.bounding_box()["height"] >= 44
    remove.click()
    expect(page.get_by_text("Safe local", exact=True)).to_have_count(0)
    assert page.evaluate("JSON.parse(localStorage.getItem('structural_favorites')).length") == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


def test_analyze_network_failure_keeps_local_favorite(page: Page, origin: str):
    page.set_viewport_size({"width": 390, "height": 844})
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"authenticated":true,"bookmarks":[],"tickers":[]}',
        ),
    )
    page.route(
        "**/api/favorites/bookmarks",
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"error":"retry"}'
        ),
    )
    page.route("**/api/analyze**", lambda route: route.abort())
    page.goto(
        origin + "/analyze.html?id=target-1&q=Research+question&a_id=source-1&persist=0",
        wait_until="domcontentloaded",
    )
    favorite = page.locator("#analyze-fav-btn")
    assert favorite.bounding_box()["height"] >= 44
    favorite.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".toast")).to_contain_text("已保存在本机，账户同步稍后重试")
    expect(favorite).to_have_attribute("aria-pressed", "true")
    assert page.evaluate("JSON.parse(localStorage.getItem('structural_favorites')).length") == 1
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")


@pytest.mark.parametrize(
    ("status", "body", "message"),
    (
        (401, '{"error":"unauthorized"}', "已保存在本机，登录后同步"),
        (409, '{"error":"credential_conflict"}', "已保存在本机，请重新确认账户后同步"),
    ),
)
def test_analyze_account_statuses_keep_local_copy(
    page: Page, origin: str, status: int, body: str, message: str
):
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"authenticated":true,"bookmarks":[],"tickers":[]}',
        ),
    )
    page.route(
        "**/api/favorites/bookmarks",
        lambda route: route.fulfill(status=status, content_type="application/json", body=body),
    )
    page.route("**/api/analyze**", lambda route: route.abort())
    page.goto(
        origin + "/analyze.html?id=target-2&q=Status+question&a_id=source-2&persist=0",
        wait_until="domcontentloaded",
    )
    page.locator("#analyze-fav-btn").click()
    expect(page.locator(".toast")).to_contain_text(message)
    assert page.evaluate("JSON.parse(localStorage.getItem('structural_favorites')).length") == 1


def test_analyze_second_device_restore_and_failed_remove_stays_active(
    page: Page, origin: str
):
    bookmark = {
        "schema_version": "bookmark-v2",
        "bookmark_id": "bm_dddddddddddddddddddddddd",
        "kind": "structural_analysis",
        "title": "Second device",
        "query": "Second device question",
        "source_id": "source-3",
        "target_id": "target-3",
        "href": "/analyze?id=target-3",
        "source": "Structural",
        "created_at": "2026-07-13T00:00:00+00:00",
    }
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"authenticated": True, "bookmarks": [bookmark], "tickers": []}),
        ),
    )
    page.route(
        "**/api/favorites/bookmarks/*",
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"error":"retry"}'
        ),
    )
    page.route("**/api/analyze**", lambda route: route.abort())
    page.goto(
        origin + "/analyze.html?id=target-3&q=Second+device+question&a_id=source-3&persist=0",
        wait_until="domcontentloaded",
    )
    favorite = page.locator("#analyze-fav-btn")
    expect(favorite).to_have_attribute("aria-pressed", "true")
    favorite.click()
    expect(page.locator(".toast")).to_contain_text("账户移除未完成，收藏仍然保留")
    expect(favorite).to_have_attribute("aria-pressed", "true")
