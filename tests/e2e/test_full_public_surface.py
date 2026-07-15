"""Fail-closed browser matrix for every intentional public product surface."""

from __future__ import annotations

import json
import functools
import threading
from datetime import datetime, timedelta, timezone
import time
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
            response = None
            for attempt in range(3):
                response = page.goto(origin + route, wait_until="domcontentloaded", timeout=20_000)
                if response is not None and response.status < 500:
                    break
                if attempt < 2:
                    time.sleep(2 ** attempt)
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


def test_beta_analytics_is_absent_until_explicit_consent(
    page: Page, local_beta_origin: str
):
    requests: list[str] = []
    page.route(
        "https://plausible.bytedance.city/**",
        lambda route: (
            requests.append(route.request.url),
            route.fulfill(status=200, content_type="application/javascript", body=""),
        ),
    )
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)

    expect(page.locator("#analytics-consent")).to_be_visible()
    expect(page.locator("#plausible-script")).to_have_count(0)
    assert requests == []

    page.get_by_role("button", name="仅必要功能").click()
    expect(page.locator("#analytics-consent")).to_have_count(0)
    choice = page.evaluate(
        "() => JSON.parse(localStorage.getItem('cookie_consent_v1'))"
    )
    assert choice["essential"] is True
    assert choice["analytics"] is False
    assert choice["marketing"] is False
    assert requests == []

    page.get_by_role("button", name="分析设置").click()
    expect(page.locator("#analytics-consent")).to_be_visible()


def test_beta_explicit_consent_posts_only_canonical_pageview(
    page: Page, local_beta_origin: str
):
    requests: list[dict[str, object]] = []

    def capture(route):
        requests.append(
            {
                "url": route.request.url,
                "method": route.request.method,
                "payload": route.request.post_data_json,
            }
        )
        route.fulfill(status=202, content_type="text/plain", body="ok")

    page.route("https://plausible.bytedance.city/**", capture)
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
    page.get_by_role("button", name="允许匿名分析").click()

    page.wait_for_function("() => window.plausible?.s === 'direct'")
    page.wait_for_timeout(100)
    expect(page.locator("#plausible-script")).to_have_count(0)
    assert requests == [
        {
            "url": "https://plausible.bytedance.city/api/event",
            "method": "POST",
            "payload": {
                "name": "pageview",
                "url": local_beta_origin + "/",
                "domain": "beta.structural.bytedance.city",
            },
        }
    ]


@pytest.mark.parametrize(
    ("entry_path", "private_path"),
    (
        ("/analyze.html", "/analyze"),
        ("/reports.html", "/reports"),
        ("/report.html", "/report"),
        ("/report.html", "/report/r_0123456789abcdef"),
        (
            "/report.html",
            "/report/share/0123456789abcdef0123456789abcdef",
        ),
        ("/", "/invite/550e8400-e29b-41d4-a716-446655440000"),
        ("/", "/resource/550e8400-e29b-41d4-a716-446655440000"),
        ("/", "/claim/abcdefghijklmnopqrstuvwxyz0123456789"),
        ("/", "/resource/abcdefghijklmnopqrstuvwxyz0123456789"),
        (
            "/",
            "/verify/"
            + ".".join(
                ("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "signature00")
            ),
        ),
        (
            "/",
            "/resource/"
            + ".".join(
                ("eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0", "signature00")
            ),
        ),
        ("/", "/connect/AbCdEf012345.ghIjKl678901.mnOpQr234567"),
        ("/", "/resource/AbCdEf012345.ghIjKl678901.mnOpQr234567"),
        ("/", "/auth/connect"),
        ("/", "/callback/start"),
        ("/", "/Report/share/test-referrer-capability"),
        ("/", "/%72eport/share/test-referrer-capability"),
        ("/", "/%2572eport/share/test-referrer-capability"),
        ("/", "/resource/user%2540example.com"),
        (
            "/",
            "/phenomenon/"
            + "-".join(
                ("xoxb", "123456789012", "123456789012", "abcdefghijklmnopqrstuvwx")
            ),
        ),
        ("/", "/phenomenon/abcdefghijklmnopqrstuvwxyz-0123456789"),
        (
            "/",
            "/phenomenon/"
            + "-".join(("glpat", "abcdefghijklmnopqrstuvwxyz0123456789")),
        ),
        ("/", "/resource/ordinary-semantic-slug"),
        ("/", "/404"),
    ),
)
def test_beta_private_or_capability_routes_never_load_analytics(
    page: Page, local_beta_origin: str, entry_path: str, private_path: str,
):
    requests: list[str] = []
    page.add_init_script(
        """
        if (location.protocol === 'http:' || location.protocol === 'https:') {
          history.replaceState(null, '', PRIVATE_PATH);
          localStorage.setItem('cookie_consent_v1', JSON.stringify({
            version: 1, essential: true, analytics: true, marketing: false,
            source: 'explicit'
          }));
        }
        """.replace("PRIVATE_PATH", json.dumps(private_path))
    )
    page.route(
        "https://plausible.bytedance.city/**",
        lambda route: requests.append(route.request.url) or route.abort(),
    )

    page.goto(
        local_beta_origin + entry_path,
        wait_until="domcontentloaded",
        timeout=20_000,
    )
    page.wait_for_timeout(100)

    assert page.url.endswith(private_path)
    expect(page.locator("#plausible-script")).to_have_count(0)
    expect(page.locator("#analytics-consent")).to_have_count(0)
    assert page.evaluate("() => window.plausible") is None
    assert requests == []


@pytest.mark.parametrize(
    "public_path",
    (
        "/paper/soc-universal-collapse-2026-05-13",
        "/paper/structural.isomorphism.research-paper",
        "/phenomenon/sci-001",
    ),
)
def test_beta_public_semantic_slugs_keep_canonical_analytics(
    page: Page, local_beta_origin: str, public_path: str,
):
    requests: list[dict[str, object]] = []
    page.add_init_script(
        """
        if (location.protocol === 'http:' || location.protocol === 'https:') {
          history.replaceState(null, '', PUBLIC_PATH);
          localStorage.setItem('cookie_consent_v1', JSON.stringify({
            version: 1, essential: true, analytics: true, marketing: false,
            source: 'explicit'
          }));
        }
        """.replace("PUBLIC_PATH", json.dumps(public_path))
    )

    def capture(route):
        requests.append(
            {
                "url": route.request.url,
                "method": route.request.method,
                "payload": route.request.post_data_json,
            }
        )
        route.fulfill(status=202, content_type="text/plain", body="ok")

    page.route("https://plausible.bytedance.city/**", capture)
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
    page.wait_for_function("() => window.plausible?.s === 'direct'")
    page.wait_for_timeout(100)

    assert requests == [
        {
            "url": "https://plausible.bytedance.city/api/event",
            "method": "POST",
            "payload": {
                "name": "pageview",
                "url": local_beta_origin + public_path,
                "domain": "beta.structural.bytedance.city",
            },
        }
    ]


def test_beta_share_capability_never_becomes_same_origin_referrer(
    page: Page, local_beta_origin: str
):
    token = "test-referrer-capability"
    page.add_init_script(
        f"""(() => {{
          const token = {json.dumps(token)};
          if (location.pathname === '/report.html') {{
            history.replaceState(null, '', '/report/share/' + token);
          }}
        }})()""",
    )
    page.goto(
        local_beta_origin + "/report.html",
        wait_until="domcontentloaded",
        timeout=20_000,
    )
    assert page.url.endswith("/report/share/" + token)

    page.locator(".analyze-crumb__link").click()
    page.wait_for_url(local_beta_origin + "/")

    assert page.evaluate("document.referrer") == ""
    assert token not in page.content()


def test_beta_dnt_overrides_a_saved_analytics_choice(
    browser, local_beta_origin: str
):
    context = browser.new_context(extra_http_headers={"DNT": "1"})
    current = context.new_page()
    current.add_init_script(
        """
        localStorage.setItem('cookie_consent_v1', JSON.stringify({
          version: 1, essential: true, analytics: true, marketing: false,
          source: 'explicit'
        }));
        Object.defineProperty(navigator, 'doNotTrack', {
          value: '1', configurable: true
        });
        """
    )
    requests: list[str] = []
    current.route(
        "https://plausible.bytedance.city/**",
        lambda route: requests.append(route.request.url) or route.abort(),
    )
    try:
        current.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
        expect(current.locator("#analytics-consent")).to_have_count(0)
        expect(current.locator("#plausible-script")).to_have_count(0)
        choice = current.evaluate(
            "() => JSON.parse(localStorage.getItem('cookie_consent_v1'))"
        )
        assert choice["analytics"] is False
        assert choice["source"] == "dnt"
        assert requests == []
    finally:
        context.close()


@pytest.mark.parametrize("path", ("/diagnose.html", "/pricing.html", "/thank-you.html"))
def test_beta_consent_copy_respects_stored_english_without_i18n(
    page: Page, local_beta_origin: str, path: str
):
    page.add_init_script("localStorage.setItem('structural.lang', 'en')")
    page.goto(local_beta_origin + path, wait_until="domcontentloaded", timeout=20_000)

    expect(
        page.get_by_text("You decide whether to share anonymous usage data", exact=True)
    ).to_be_visible()
    expect(page.get_by_role("button", name="Essential only")).to_be_visible()
    page.get_by_role("button", name="Essential only").click()
    expect(page.get_by_role("button", name="Analytics settings")).to_be_visible()


def test_beta_320_header_and_consent_controls_stay_inside_viewport(
    page: Page, local_beta_origin: str
):
    page.set_viewport_size({"width": 320, "height": 720})
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)

    assert page.evaluate("document.documentElement.scrollWidth") <= 320
    for selector in (
        ".site-header__logo",
        ".site-header__account-cta",
        "#site-menu-btn",
        "[data-analytics-choice='false']",
        "[data-analytics-choice='true']",
    ):
        box = page.locator(selector).bounding_box()
        assert box is not None, selector
        assert box["x"] >= 0, (selector, box)
        assert box["x"] + box["width"] <= 320, (selector, box)
    expect(page.locator("#site-menu-btn")).to_have_attribute("aria-label", "打开菜单")


@pytest.mark.parametrize("width", (320, 390))
def test_beta_consent_privacy_link_has_real_touch_target(
    page: Page, local_beta_origin: str, width: int,
):
    page.set_viewport_size({"width": width, "height": 720})
    page.add_init_script("localStorage.clear()")
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)

    privacy_link = page.locator("#analytics-consent a[href='/privacy']")
    expect(privacy_link).to_be_visible()
    box = privacy_link.bounding_box()
    assert box is not None
    assert box["height"] >= 44, box
    assert page.evaluate(
        """() => {
          const link = document.querySelector("#analytics-consent a[href='/privacy']");
          const box = link.getBoundingClientRect();
          const hit = document.elementFromPoint(
            box.left + box.width / 2,
            box.top + box.height / 2,
          );
          return hit === link || link.contains(hit);
        }"""
    )
    assert page.evaluate("document.documentElement.scrollWidth - innerWidth") <= 0


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
        ("answer_validated", {"ok": True, "source": "model"}),
        ("answer_chunk", {"delta": "候选说明 [1]"}),
        (
            "answer_done",
            {
                "full_text": "候选说明 [1]",
                "citations": [
                    {"idx": 1, "kb_id": "candidate-1", "label": "Cascade A"}
                ],
            },
        ),
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
    expect(page.locator("#ask-fingerprint-summary")).to_have_value("团队为什么恢复很慢？")
    expect(page.locator("#ask-fingerprint-variables")).to_have_value("恢复速度")
    expect(page.locator("#ask-fingerprint-unknowns")).to_have_value(
        "这些变量之间的因果方向与可观测指标"
    )
    expect(page.locator("#ask-fingerprint-confirm")).to_be_focused()
    expect(page.get_by_role("radiogroup", name="选择一个跨领域候选")).to_have_count(0)
    page.locator("#ask-fingerprint-variables").fill("信任, 反馈延迟")
    page.locator("#ask-fingerprint-constraints").fill("两周内")
    page.locator("#ask-fingerprint-confirm").click()

    group = page.get_by_role("radiogroup", name="选择一个跨领域候选")
    expect(group).to_be_visible(timeout=5_000)
    expect(page.get_by_text("系统不会替你默认选择 Top 1")).to_be_visible()
    candidates = page.get_by_role("radio")
    expect(candidates).to_have_count(3)
    first_shell = candidates.nth(0).locator("xpath=..")
    expect(first_shell.get_by_text("结构匹配线索")).to_be_visible()
    expect(first_shell.get_by_text("反证 / 尚缺证据")).to_be_visible()
    expect(first_shell.get_by_text("适用边界")).to_be_visible()
    expect(first_shell.get_by_text("尚未完成变量、因果方向与边界条件的逐项核对。")).to_be_visible()
    source = page.get_by_role("link", name="查看内部 KB 记录：Feedback B")
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


def test_beta_fingerprint_draft_mobile_keyboard_and_recovery(
    page: Page, local_beta_origin: str
):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
    query = "留存率下降，需要在 2 周内验证，不能改变价格"
    page.locator("#ask-input").fill(query)
    page.locator("#ask-form").evaluate("form => form.requestSubmit()")

    panel = page.locator("#ask-fingerprint")
    expect(panel).to_be_visible()
    expect(page.locator("#ask-fingerprint-variables")).to_have_value("留存率，价格")
    expect(page.locator("#ask-fingerprint-constraints")).to_have_value(
        "在 2 周内，不能改变价格"
    )
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    page.locator("#ask-fingerprint-unknowns").fill("需要确认流失发生在哪一阶段")
    page.locator("#ask-fingerprint-cancel").click()
    expect(panel).to_be_hidden()
    expect(page.locator("#ask-input")).to_be_focused()

    page.locator("#ask-form").evaluate("form => form.requestSubmit()")
    expect(page.locator("#ask-fingerprint-unknowns")).to_have_value(
        "需要确认流失发生在哪一阶段"
    )
    page.locator("#ask-fingerprint-summary").press("Escape")
    expect(panel).to_be_hidden()
    expect(page.locator("#ask-input")).to_be_focused()


def test_beta_fingerprint_draft_does_not_invent_english_or_trust_bad_cache(
    page: Page, local_beta_origin: str
):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(local_beta_origin, wait_until="domcontentloaded", timeout=20_000)
    query = "Why did retention fall <script>alert(1)</script>?"
    page.evaluate(
        """([query]) => sessionStorage.setItem(
          'structural_fingerprint_draft',
          JSON.stringify({query, summary: {invented: true}, variables: ['fake']})
        )""",
        [query],
    )
    page.locator("#ask-input").fill(query)
    page.locator("#ask-form").evaluate("form => form.requestSubmit()")

    expect(page.locator("#ask-fingerprint-summary")).to_have_value(query)
    expect(page.locator("#ask-fingerprint-variables")).to_have_value("")
    expect(page.locator("#ask-fingerprint-constraints")).to_have_value("")
    expect(page.locator("#ask-fingerprint-unknowns")).to_have_value(
        "需要确认关键变量、可观测指标与因果方向"
    )
    assert page.locator("script").filter(has_text="alert(1)").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    page.set_viewport_size({"width": 430, "height": 932})
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    page.locator("#ask-fingerprint-summary").press("Control+Enter")
    expect(page.locator("#ask-fingerprint")).to_be_hidden()
    expect(page.locator("#ask-thread")).to_be_visible()

    page.reload(wait_until="domcontentloaded")
    page.locator("#ask-input").fill("2 + 2 = ?")
    page.locator("#ask-form").evaluate("form => form.requestSubmit()")
    expect(page.locator("#ask-fingerprint-variables")).to_have_value("")
    expect(page.locator("#ask-fingerprint-constraints")).to_have_value("")
    expect(page.locator("#ask-fingerprint-unknowns")).to_have_value(
        "需要确认关键变量、可观测指标与因果方向"
    )


def test_beta_header_exposes_one_dynamic_primary_account_entry(
    page: Page, local_beta_origin: str
):
    page.goto(local_beta_origin, wait_until="domcontentloaded")
    account = page.locator(".site-header__account-cta")
    expect(account).to_have_count(1)
    expect(account).to_be_visible()
    expect(account).to_have_text("登录以同步")
    expect(account).to_have_attribute("href", "/auth/login?next=%2Freports")

    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok":true,"user":{"email":"owned@example.test"}}',
        ),
    )
    page.reload(wait_until="domcontentloaded")
    expect(account).to_have_text("我的研究")
    expect(account).to_have_attribute("href", "/reports")


def test_beta_mobile_menu_traps_and_restores_focus(page: Page, local_beta_origin: str):
    page.set_viewport_size({"width": 375, "height": 812})
    page.goto(local_beta_origin, wait_until="domcontentloaded")
    menu = page.locator("#site-menu-btn")
    menu.click()
    close = page.locator("[data-menu-close]").filter(has=page.locator("svg")).last
    expect(close).to_be_focused()
    close.press("Shift+Tab")
    expect(page.locator(".site-menu__link").last).to_be_focused()
    mobile_language = page.locator("#site-menu-lang-toggle")
    expect(mobile_language).to_be_visible()
    mobile_language.click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    page.keyboard.press("Escape")
    expect(menu).to_be_focused(timeout=1_000)


def test_beta_header_never_picks_one_of_two_accounts(page: Page, local_beta_origin: str):
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=409,
            content_type="application/json",
            body='{"ok":false,"error":"credential_conflict"}',
        ),
    )
    page.goto(local_beta_origin, wait_until="domcontentloaded")
    account = page.locator(".site-header__account-cta")
    expect(account).to_have_text("确认账户")
    expect(account).to_have_attribute("data-auth-state", "conflict")
    expect(account).to_have_attribute("href", "/auth/login?next=%2Freports")


def test_report_workbench_groups_action_state(page: Page, local_beta_origin: str):
    now = datetime.now(timezone.utc)
    items = [
        {"id": "r_1111111111111111", "query": "today", "created_at": now.isoformat(), "view_count": 0, "lang": "zh", "has_followup": False, "followup_status": "", "followup_outcome": ""},
        {"id": "r_2222222222222222", "query": "week", "created_at": (now - timedelta(days=2)).isoformat(), "view_count": 0, "lang": "zh", "has_followup": False, "followup_status": "", "followup_outcome": ""},
        {"id": "r_3333333333333333", "query": "waiting", "created_at": (now - timedelta(days=10)).isoformat(), "view_count": 0, "lang": "zh", "has_followup": True, "followup_status": "in_progress", "followup_outcome": "too_early"},
        {"id": "r_4444444444444444", "query": "completed", "created_at": (now - timedelta(days=12)).isoformat(), "view_count": 0, "lang": "zh", "has_followup": True, "followup_status": "tried", "followup_outcome": "worked"},
    ]
    page.add_init_script("localStorage.setItem('anonId', 'e2e-owner')")
    page.route(
        "**/api/reports/mine**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"items": items, "has_more": False}),
        ),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    for section_id, query in (("today", "today"), ("week", "week"), ("waiting", "waiting"), ("completed", "completed")):
        section = page.locator("#myr-bucket-" + section_id)
        expect(section).to_be_visible()
        expect(section.get_by_text(query, exact=True)).to_be_visible()


def test_my_research_account_and_data_failures_are_honest(page: Page, local_beta_origin: str):
    page.set_viewport_size({"width": 390, "height": 844})
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok":true,"user":{"email":"owner@example.test","tier":"free"}}',
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"items":[],"has_more":false}'
        ),
    )
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"tickers":["AAPL"]}'
        ),
    )
    page.route(
        "**/api/auth/logout",
        lambda route: route.fulfill(status=503, content_type="application/json", body='{"error":"retry"}'),
    )
    page.route(
        "**/api/me/delete",
        lambda route: route.fulfill(status=500, content_type="application/json", body='{"error":"kept"}'),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    expect(page.locator("#lang-toggle")).to_have_count(1)
    expect(page.get_by_role("heading", name="我的研究", exact=True)).to_be_visible()
    expect(page.get_by_text("owner@example.test", exact=True)).to_be_visible()
    account_favorite = page.locator(".myr-favorite", has_text="AAPL")
    expect(account_favorite).to_be_visible()
    expect(account_favorite).to_contain_text("Phase 子产品账户收藏")
    expect(page.get_by_role("button", name="导出我的数据")).to_be_visible()
    for control in (
        page.locator(".myr-sections a").first,
        account_favorite,
        page.get_by_role("button", name="导出我的数据"),
        page.get_by_role("button", name="退出登录"),
        page.get_by_text("永久删除账户与关联数据", exact=True),
    ):
        assert control.bounding_box()["height"] >= 44

    page.get_by_role("button", name="退出登录").click()
    expect(page.locator("#myr-account-status")).to_contain_text("退出失败")

    page.get_by_text("永久删除账户与关联数据", exact=True).click()
    page.get_by_role("button", name="永久删除", exact=True).click()
    expect(page.locator("#myr-account-status")).to_contain_text("请输入 DELETE")
    page.locator("#myr-delete-confirmation").fill("DELETE")
    page.get_by_role("button", name="永久删除", exact=True).click()
    expect(page.locator("#myr-account-status")).to_contain_text("删除没有完成")


@pytest.mark.parametrize("conflict_surface", ("auth", "reports", "favorites"))
def test_my_research_locks_instead_of_falling_back_on_credential_conflict(
    page: Page, local_beta_origin: str, conflict_surface: str
):
    page.add_init_script(
        "localStorage.setItem('anonId', 'must-not-fallback');"
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Local secret', analyze_url:'/analyze?id=secret'}]));"
    )
    conflict = '{"ok":false,"error":"credential_conflict"}'
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=409 if conflict_surface == "auth" else 200,
            content_type="application/json",
            body=conflict if conflict_surface == "auth" else '{"ok":true,"user":{"email":"owner@example.test"}}',
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=409 if conflict_surface == "reports" else 200,
            content_type="application/json",
            body=conflict if conflict_surface == "reports" else '{"items":[],"has_more":false}',
        ),
    )
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=409 if conflict_surface == "favorites" else 200,
            content_type="application/json",
            body=conflict if conflict_surface == "favorites" else '{"tickers":[]}',
        ),
    )
    page.route(
        "**/api/reports/mine**",
        lambda route: pytest.fail("credential conflict must not fall back to anonymous reports"),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.locator("#myr-account")).to_contain_text("两个不同账户")
    expect(page.locator("#myr-list")).to_contain_text("研究资产已保持锁定")
    expect(page.locator("#myr-favorites")).to_contain_text("重新确认账户后再显示收藏")
    expect(page.get_by_text("Local secret", exact=True)).to_have_count(0)
    expect(page.get_by_role("link", name="重新确认账户")).to_have_count(2)


def test_my_research_ordinary_unauthorized_keeps_local_assets(
    page: Page, local_beta_origin: str
):
    page.add_init_script(
        "localStorage.setItem('anonId', 'local-owner');"
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Local candidate', analyze_url:'/analyze?id=local'}]));"
    )
    unauthorized = '{"ok":false,"error":"unauthorized"}'
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body=unauthorized
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=401, content_type="application/json", body=unauthorized
        ),
    )
    page.route(
        "**/api/reports/mine**",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"items":[],"has_more":false}',
        ),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.locator("#myr-account")).to_contain_text("尚未登录")
    expect(page.locator("#myr-list")).to_contain_text("还没有保存的报告")
    expect(page.get_by_text("Local candidate", exact=True)).to_be_visible()
    expect(page.get_by_text("研究资产已保持锁定")).to_have_count(0)


@pytest.mark.parametrize(
    "lang,expected_locale", (("zh", "zh-CN"), ("en", "en-US")),
)
def test_learn_local_favorite_keeps_the_rest_of_home_boot_alive(
    page: Page, local_beta_origin: str, lang: str, expected_locale: str,
):
    """A non-empty local library must not break daily/home initialization."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    favorite = json.dumps({
        "query": "Local verified candidate",
        "analyze_url": "/analyze?id=p-100&q=local",
        "timestamp": 1_784_006_400_000,
    })
    page.add_init_script(
        f"""(() => {{
          const favorite = {favorite};
          localStorage.setItem('structural_favorites', JSON.stringify([favorite]));
          window.__favoriteLocales = [];
          const original = Date.prototype.toLocaleDateString;
          Date.prototype.toLocaleDateString = function(locale, ...args) {{
            window.__favoriteLocales.push(locale);
            return original.call(this, locale, ...args);
          }};
        }})();""",
    )
    page.route(
        "**/api/suggest*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"suggestions":[]}',
        ),
    )
    page.route(
        "**/api/daily*",
        lambda route: route.fulfill(
            status=200, content_type="application/json", body='{"discoveries":[]}',
        ),
    )
    page.goto(
        f"{local_beta_origin}/learn.html?lang={lang}",
        wait_until="domcontentloaded",
    )
    expect(page.locator("#home-favorites")).to_be_visible()
    expect(page.locator(".home__fav-card__title")).to_have_text(
        "Local verified candidate"
    )
    expect(page.locator(".home__fav-card__time")).not_to_be_empty()
    expect(page.locator(".home__daily-empty")).to_be_visible()
    locales = page.evaluate("window.__favoriteLocales")
    assert locales
    assert set(locales) == {expected_locale}
    assert errors == []


def test_my_research_waits_for_identity_before_any_asset_read(
    page: Page, local_beta_origin: str
):
    page.add_init_script(
        "localStorage.setItem('anonId', 'race-owner');"
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Race secret', analyze_url:'/analyze?id=race'}]));"
        "localStorage.setItem('structural_local_reminders', 'on');"
        "window.__assetReads = 0;"
        "const originalGetItem = Storage.prototype.getItem;"
        "Storage.prototype.getItem = function(key) {"
        "if (['anonId','structural_favorites','structural_local_reminders'].includes(key)) "
        "window.__assetReads += 1;"
        "return originalGetItem.call(this, key);"
        "};"
    )
    requests = {"reports": 0, "favorites": 0, "legacy": 0, "proof": 0}

    def delayed_conflict(route):
        time.sleep(0.15)
        route.fulfill(
            status=409,
            content_type="application/json",
            body='{"ok":false,"error":"credential_conflict"}',
        )

    def reject_asset(name):
        def handler(route):
            requests[name] += 1
            route.fulfill(status=500, body="unexpected asset read")
        return handler

    page.route("**/api/auth/me", delayed_conflict)
    page.route("**/api/me/reports**", reject_asset("reports"))
    page.route("**/api/favorites", reject_asset("favorites"))
    page.route("**/api/reports/mine**", reject_asset("legacy"))
    page.route("**/api/reports/anon-proof", reject_asset("proof"))
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.locator("#myr-list")).to_contain_text("研究资产已保持锁定")
    assert requests == {"reports": 0, "favorites": 0, "legacy": 0, "proof": 0}
    assert page.evaluate("window.__assetReads") == 0
    expect(page.get_by_text("Race secret", exact=True)).to_have_count(0)


@pytest.mark.parametrize("delayed_conflict", ("reports", "favorites"))
def test_my_research_authenticated_asset_preflight_never_partially_commits(
    page: Page, local_beta_origin: str, delayed_conflict: str
):
    page.add_init_script(
        "localStorage.setItem('anonId', 'atomic-owner');"
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Local secret', analyze_url:'/analyze?id=atomic'}]));"
        "localStorage.setItem('structural_local_reminders', 'on');"
        "window.__assetReads = 0; window.__seenSecret = false; window.__seenReport = false;"
        "const originalGetItem = Storage.prototype.getItem;"
        "Storage.prototype.getItem = function(key) {"
        "if (['anonId','structural_favorites','structural_local_reminders'].includes(key)) "
        "window.__assetReads += 1;"
        "return originalGetItem.call(this, key);"
        "};"
        "new MutationObserver(function() {"
        "const text = document.body ? document.body.innerText : '';"
        "if (text.includes('Local secret')) window.__seenSecret = true;"
        "if (text.includes('Staged report')) window.__seenReport = true;"
        "}).observe(document.documentElement, {subtree:true, childList:true, characterData:true});"
    )
    conflict = '{"ok":false,"error":"credential_conflict"}'
    report_ok = json.dumps({
        "items": [{
            "id": "r_atomic000000001",
            "query": "Staged report",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "view_count": 0,
            "lang": "zh",
            "has_followup": False,
            "followup_status": "",
            "followup_outcome": "",
        }],
        "has_more": False,
    })

    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"ok":true,"user":{"email":"owner@example.test"}}',
        ),
    )

    def reports_handler(route):
        if delayed_conflict == "reports":
            time.sleep(0.35)
            route.fulfill(status=409, content_type="application/json", body=conflict)
        else:
            route.fulfill(status=200, content_type="application/json", body=report_ok)

    def favorites_handler(route):
        if delayed_conflict == "favorites":
            time.sleep(0.35)
            route.fulfill(status=409, content_type="application/json", body=conflict)
        else:
            route.fulfill(status=200, content_type="application/json", body='{"tickers":[]}')

    page.route("**/api/me/reports**", reports_handler)
    page.route("**/api/favorites", favorites_handler)
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.locator("#myr-list")).to_contain_text("研究资产已保持锁定")
    assert page.evaluate("window.__assetReads") == 0
    assert page.evaluate("window.__seenSecret") is False
    assert page.evaluate("window.__seenReport") is False
    expect(page.get_by_text("Local secret", exact=True)).to_have_count(0)
    expect(page.get_by_text("Staged report", exact=True)).to_have_count(0)


@pytest.mark.parametrize("failed_surface", ("reports", "favorites"))
def test_my_research_authenticated_partial_failure_is_explicit(
    page: Page, local_beta_origin: str, failed_surface: str
):
    page.add_init_script(
        "localStorage.setItem('structural_favorites', JSON.stringify(["
        "{query:'Local candidate', analyze_url:'/analyze?id=partial'}]));"
    )
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
            status=503 if failed_surface == "reports" else 200,
            content_type="application/json",
            body='{"error":"unavailable"}' if failed_surface == "reports" else '{"items":[],"has_more":false}',
        ),
    )
    page.route(
        "**/api/favorites",
        lambda route: route.fulfill(
            status=503 if failed_surface == "favorites" else 200,
            content_type="application/json",
            body='{"error":"unavailable"}' if failed_surface == "favorites" else '{"tickers":["AAPL"]}',
        ),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    if failed_surface == "reports":
        expect(page.locator("#myr-list")).to_contain_text("报告暂时无法读取")
        expect(page.locator(".myr-favorite", has_text="AAPL")).to_be_visible()
    else:
        expect(page.locator("#myr-list")).to_contain_text("还没有保存的报告")
        expect(page.locator("#myr-favorites-copy")).to_contain_text("账户收藏暂时无法读取")
        expect(page.get_by_text("Local candidate", exact=True)).to_be_visible()


def test_my_research_mobile_language_switch_persists(
    page: Page, local_beta_origin: str
):
    page.set_viewport_size({"width": 390, "height": 844})
    page.route(
        "**/api/auth/me",
        lambda route: route.fulfill(
            status=401,
            content_type="application/json",
            body='{"ok":false,"error":"unauthorized"}',
        ),
    )
    page.route(
        "**/api/me/reports**",
        lambda route: route.fulfill(
            status=401,
            content_type="application/json",
            body='{"ok":false,"error":"unauthorized"}',
        ),
    )
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    page.locator("#site-menu-btn").click()
    language = page.locator("#site-menu-lang-toggle")
    expect(language).to_be_visible()
    language.click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    assert page.evaluate("localStorage.getItem('structural.lang')") == "en"
    page.reload(wait_until="domcontentloaded")
    expect(page.locator("html")).to_have_attribute("lang", "en")


@pytest.mark.requires_internet
def test_phase_companies_controls_activate_after_scroll(page: Page):
    page.goto(f"{PHASE}/companies", wait_until="domcontentloaded", timeout=20_000)
    screener = page.locator("#screener")
    screener.scroll_into_view_if_needed()
    expect(page.get_by_role("region", name="筛选条件")).to_be_visible(timeout=10_000)
    expect(page.locator("#screener select")).to_have_count(3)
    expect(page.locator('#screener input[type="range"]')).to_be_visible()
