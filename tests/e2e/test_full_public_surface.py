"""Fail-closed browser matrix for every intentional public product surface."""

from __future__ import annotations

import json
import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright")
from playwright.sync_api import Page, expect, sync_playwright  # noqa: E402

pytestmark = pytest.mark.e2e

BETA = "https://beta.structural.bytedance.city"
PHASE = "https://phase.bytedance.city"
FRONTEND_DIR = Path(__file__).resolve().parents[2] / "web" / "frontend"

BETA_ROUTES = (
    "/", "/start-here", "/search", "/classes", "/discoveries", "/papers",
    "/methods", "/tools", "/whitespace", "/insights", "/apply",
    "/stress-test", "/lint", "/diagnose", "/taxonomy-v2", "/learn",
    "/about", "/privacy", "/reports", "/analyze", "/thank-you",
    "/phenomenon/sci-001",
    "/paper/unified-pipeline-v0.2-2026-05-13",
)
PHASE_ROUTES = (
    "/", "/zh", "/companies", "/company/AAPL",
    "/compare?tickers=AAPL,TSLA", "/universality",
    "/universality/preferential_attachment", "/methodology", "/backtest",
    "/newsletter", "/newsletter/001", "/about", "/privacy", "/pricing",
    "/onboarding", "/search", "/offline", "/auth/login", "/me",
    "/me/favorites", "/thank-you", "/auth/verify", "/checkout/mock",
)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as runtime:
        instance = runtime.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 900})
    current = context.new_page()
    yield current
    context.close()


@pytest.fixture(scope="module")
def local_beta_origin():
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(FRONTEND_DIR))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)


def assert_route_matrix(page: Page, origin: str, routes: tuple[str, ...]) -> None:
    failures: list[str] = []
    for route in routes:
        try:
            response = page.goto(origin + route, wait_until="domcontentloaded", timeout=20_000)
            if response is None or response.status >= 400:
                failures.append(f"{route}: HTTP {response.status if response else 'none'}")
                continue
            text = page.locator("body").inner_text(timeout=5_000).strip()
            if len(text) < 40:
                failures.append(f"{route}: unexpectedly empty")
            if "Application error" in text or "Internal Server Error" in text:
                failures.append(f"{route}: rendered error fallback")
        except Exception as exc:  # fail closed and report every broken route
            failures.append(f"{route}: {type(exc).__name__}")
    assert failures == [], "public route failures:\n" + "\n".join(failures)


@pytest.mark.requires_internet
def test_all_beta_public_routes_render(page: Page):
    assert_route_matrix(page, BETA, BETA_ROUTES)


@pytest.mark.requires_internet
def test_all_phase_public_routes_render(page: Page):
    assert_route_matrix(page, PHASE, PHASE_ROUTES)


def test_beta_workbench_requires_fingerprint_and_explicit_candidate(
    page: Page, local_beta_origin: str
):
    cards = [
        {"id": "candidate-1", "name": "Cascade A", "domain": "Physics", "score": 0.82},
        {"id": "candidate-2", "name": "Feedback B", "domain": "Biology", "score": 0.77},
        {"id": "candidate-3", "name": "Threshold C", "domain": "Economics", "score": 0.71},
    ]
    events = [
        ("meta", {"query": "团队为什么恢复很慢？", "rewritten": "团队恢复反馈结构"}),
        ("retrieval_done", {"count": 3, "retrieval_ms": 20}),
        ("kb_cards", {"cards": cards}),
        ("answer_chunk", {"delta": "候选说明"}),
        ("answer_done", {"full_text": "候选说明", "citations": []}),
        ("done", {"latency_ms": 30}),
    ]
    body = "".join(
        f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
        for event, payload in events
    )
    page.route(
        "**/api/ask/stream",
        lambda route: route.fulfill(status=200, content_type="text/event-stream", body=body),
    )
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
    page.locator("#ask-input").fill("团队为什么恢复很慢？")
    page.locator("#ask-form").evaluate("form => form.requestSubmit()")

    fingerprint = page.locator("#ask-fingerprint")
    expect(fingerprint).to_be_visible()
    expect(page.get_by_role("radiogroup", name="选择一个跨领域候选")).to_have_count(0)
    page.locator("#ask-fingerprint-variables").fill("信任, 反馈延迟")
    page.locator("#ask-fingerprint-constraints").fill("两周内")
    page.locator("#ask-fingerprint-confirm").click()

    group = page.get_by_role("radiogroup", name="选择一个跨领域候选")
    expect(group).to_be_visible(timeout=5_000)
    expect(page.get_by_text("系统不会替你默认选择 Top 1")).to_be_visible()
    candidates = page.get_by_role("radio")
    expect(candidates).to_have_count(3)
    source = page.get_by_role("link", name="查看候选来源：Feedback B")
    source.focus()
    with page.context.expect_page() as popup_info:
        source.press("Enter")
    popup = popup_info.value
    popup.wait_for_load_state("domcontentloaded")
    assert popup.url.endswith("/phenomenon/candidate-2")
    popup.close()
    candidates.nth(1).click()
    expect(candidates.nth(1)).to_have_attribute("aria-checked", "true")
    cta = page.get_by_role("link", name="生成研究报告")
    expect(cta).to_be_visible()
    assert "id=candidate-2" in (cta.get_attribute("href") or "")
    assert "id=candidate-1" not in (cta.get_attribute("href") or "")


@pytest.mark.requires_internet
def test_phase_companies_controls_activate_after_scroll(page: Page):
    page.goto(f"{PHASE}/companies", wait_until="domcontentloaded", timeout=20_000)
    screener = page.locator("#screener")
    screener.scroll_into_view_if_needed()
    expect(page.get_by_role("region", name="筛选条件")).to_be_visible(timeout=10_000)
    expect(page.locator("#screener select")).to_have_count(3)
    expect(page.locator('#screener input[type="range"]')).to_be_visible()
