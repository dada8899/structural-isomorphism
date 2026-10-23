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


def _legacy_ask_component_only(page,origin):
    """Keep historical renderer coverage; this is NOT the public entry page.

    These three pre-existing tests already mock SSE. Remove only the new
    retirement wrapper in an isolated document so every original component
    assertion remains. Separate production-page tests never use this helper.
    """
    def document(route):
        response=route.fetch()
        html=response.text().replace(' data-legacy-ask-retired','')
        html=html.replace('<fieldset id="legacy-ask-entry" hidden disabled inert style="border:0;padding:0;margin:0">','',1).replace('</fieldset>','',1)
        html=html.replace('id="ask-thread" hidden inert','id="ask-thread" hidden')
        route.fulfill(response=response,body=html)
    page.route(origin+"/",document)


def test_beta_workbench_requires_fingerprint_and_explicit_candidate(
    page: Page, local_beta_origin: str
):
    """Historical component regression, not a live public research promise."""
    _legacy_ask_component_only(page,local_beta_origin)
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
    """Historical component keyboard regression; production is retired."""
    _legacy_ask_component_only(page,local_beta_origin)
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
    """Historical input/cache regression; production entry is tested below."""
    _legacy_ask_component_only(page,local_beta_origin)
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
    expect(account).to_have_attribute("href", "/auth/login?next=%2Fresearch")

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
    expect(account).to_have_attribute("href", "/research#my-research")


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
    expect(account).to_have_attribute("href", "/auth/login?next=%2Fresearch")


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
    expect(page.locator("#myr-account-status")).to_contain_text("删除结果尚未确认。请先刷新页面核对账户状态，请勿重复提交。")
    expect(page.locator("#myr-delete-confirmation")).to_be_disabled()
    expect(page.get_by_role("button", name="导出我的数据")).to_be_disabled()
    expect(page.get_by_role("button", name="永久删除", exact=True)).to_be_disabled()


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


def hold_research_dictionaries(page: Page):
    held = {}
    catalog = json.loads(
        (FRONTEND_DIR / "assets/data/i18n/content.json").read_text(encoding="utf-8")
    )
    page.route("https://**", lambda route: route.abort())
    page.route("**/assets/data/i18n/*.json?*", lambda route: held.__setitem__(
        "ui" if "/ui.json" in route.request.url else "content", route,
    ))
    return held, catalog


def assert_research_copy_survives_dictionaries(page: Page, held, catalog, state):
    key = "page.reports.favorites_" + state
    copy = page.locator("#myr-favorites-copy")
    # The API/identity result must be visible before releasing either catalog.
    expect(copy).to_have_text(catalog[key]["zh"])
    assert set(held) == {"ui", "content"}
    for name in ("ui", "content"):
        body = (FRONTEND_DIR / f"assets/data/i18n/{name}.json").read_text(encoding="utf-8")
        held[name].fulfill(status=200, content_type="application/json", body=body)
    page.wait_for_function(
        "([key, value]) => window.__i18n_strings?.en?.[key] === value",
        arg=[key, catalog[key]["en"]], timeout=5_000,
    )
    expect(copy).to_have_text(catalog[key]["zh"])
    for lang in ("en", "zh"):
        page.evaluate("lang => window.i18n.setLang(lang)", lang)
        expect(copy).to_have_text(catalog[key][lang])
        expect(copy).to_have_attribute("data-i18n", key)
        expect(copy).to_have_attribute("data-i18n-orig", catalog[key]["zh"])


@pytest.mark.parametrize("failed_surface", ("reports", "favorites"))
def test_my_research_authenticated_partial_failure_is_explicit(
    page: Page, local_beta_origin: str, failed_surface: str
):
    held, catalog = hold_research_dictionaries(page)
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
    page.route(
        "**/api/favorites/merge",
        lambda route: route.fulfill(
            status=503, content_type="application/json", body='{"error":"unavailable"}',
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
    assert_research_copy_survives_dictionaries(
        page, held, catalog, "sync_failed" if failed_surface == "reports" else "read_failed",
    )


@pytest.mark.parametrize("state", (
    "anonymous", "account", "locked", "identity_unavailable",
    "sync_failed", "partial", "synced",
))
def test_my_research_favorite_state_survives_late_dictionary(
    page: Page, local_beta_origin: str, state: str,
):
    held, catalog = hold_research_dictionaries(page)
    pending = state in ("sync_failed", "partial", "synced")
    local = [{"query": "Pending candidate", "b_id": "candidate", "b_name": "Candidate"}] if pending else []
    page.add_init_script("(() => { const local = " + json.dumps(local) + ";" + """
      localStorage.setItem('structural_favorites', JSON.stringify(local));
      window.__assetReads = 0;
      const original = Storage.prototype.getItem;
      Storage.prototype.getItem = function(key) {
        if (['anonId','structural_favorites','structural_local_reminders'].includes(key))
          window.__assetReads += 1;
        return original.call(this, key);
      };
    })();""")
    requests = []
    bookmark = {
        "schema_version": "bookmark-v2", "bookmark_id": "bm_" + "a" * 24,
        "kind": "structural_analysis", "title": "Candidate", "query": "Pending candidate",
        "source_id": None, "target_id": "candidate", "source": "Structural",
        "href": "/analyze?id=candidate",
    }

    def api(route):
        path = route.request.url.split("?", 1)[0].split(local_beta_origin)[-1]
        requests.append((route.request.method, path))
        status = 200
        if path == "/api/auth/me":
            if state == "anonymous":
                status, data = 401, {"error": "unauthorized"}
            elif state == "identity_unavailable":
                status, data = 503, {"error": "unavailable"}
            else:
                data = {"ok": True, "user": {"email": "owner@example.test"}}
        elif path == "/api/me/reports":
            status = 401 if state == "anonymous" else 200
            data = {"items": [], "has_more": False}
        elif path == "/api/favorites":
            status = 409 if state == "locked" else 200
            data = {"error": "credential_conflict"} if state == "locked" else {"tickers": [], "bookmarks": []}
        elif path == "/api/favorites/merge" and pending:
            assert route.request.method == "POST"
            assert len(route.request.post_data_json["bookmarks"]) == 1
            if state == "sync_failed":
                status, data = 503, {"error": "unavailable"}
            else:
                data = {
                    "bookmarks": [bookmark] if state == "synced" else [],
                    "confirmed_bookmark_ids": [bookmark["bookmark_id"]] if state == "synced" else [],
                    "dropped_bookmark_ids": ["bm_" + "b" * 24] if state == "partial" else [],
                }
        else:
            pytest.fail("unexpected research API: " + path)
        route.fulfill(status=status, content_type="application/json", body=json.dumps(data))

    page.route("**/api/**", api)
    page.goto(local_beta_origin + "/reports.html", wait_until="domcontentloaded")
    expect(page.locator("#myr-favorites-copy")).to_have_text(
        catalog["page.reports.favorites_" + state]["zh"]
    )
    before = list(requests)
    assert_research_copy_survives_dictionaries(page, held, catalog, state)
    assert requests == before
    if state in ("locked", "identity_unavailable"):
        assert page.evaluate("window.__assetReads") == 0
    if state == "identity_unavailable":
        # The shared header also checks identity; neither caller may read assets.
        assert requests and set(requests) == {("GET", "/api/auth/me")}
    if state == "account":
        assert ("POST", "/api/favorites/merge") not in requests
        expect(page.locator("#myr-list")).to_contain_text("还没有保存的报告")
    if pending:
        remaining = page.evaluate("JSON.parse(localStorage.getItem('structural_favorites'))")
        assert remaining == ([] if state == "synced" else local)
    before = list(requests)
    page.evaluate("window.i18n.render()")
    assert requests == before


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


def test_analyze_static_lang_writes_preserve_full_report_and_late_dictionary(
    page: Page, local_beta_origin: str,
) -> None:
    # Only pure backend-validated fixture data; no auditor or profiler is invoked.
    from scripts.beta_perf_audit import _analyze_fixture

    expected_request, stream = _analyze_fixture()
    held = {}
    posted = []
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    dictionaries = {
        name: json.loads((FRONTEND_DIR / f'assets/data/i18n/{name}.json').read_text(encoding='utf-8'))
        for name in ('ui', 'content')
    }
    catalog = {**dictionaries['ui'], **dictionaries['content']}
    probe = """<script>
      window.__langChanges=[];window.__langNotifications=[];
      window.__langObserver=new MutationObserver(records=>{
        window.__langChanges.push(...records.map(r=>r.oldValue));
      });
      window.__langObserver.observe(document.documentElement,
        {attributes:true,attributeOldValue:true,attributeFilter:['lang']});
    </script>"""
    html = (FRONTEND_DIR / 'analyze.html').read_text(encoding='utf-8')
    html = html.replace('<head>', '<head>' + probe, 1)
    page.route('https://**', lambda route: route.abort())
    page.route('**/analyze.html?*', lambda route: route.fulfill(
        status=200, content_type='text/html; charset=utf-8', body=html,
    ))
    i18n = (FRONTEND_DIR / 'assets/js/i18n.js').read_text(encoding='utf-8')
    page.route('**/assets/js/i18n.js?*', lambda route: route.fulfill(
        status=200, content_type='application/javascript', body=i18n +
        '\nwindow.i18n.onChange(lang=>window.__langNotifications.push(lang));',
    ))
    page.route('**/assets/data/i18n/*.json?*', lambda route: held.__setitem__(
        'ui' if '/ui.json' in route.request.url else 'content', route,
    ))

    def api(route):
        request = route.request
        if request.url.split('?')[0].endswith('/api/analyze/stream'):
            assert request.method == 'POST'
            posted.append(request.post_data_json)
            assert request.post_data_json == expected_request
            route.fulfill(status=200, content_type='text/event-stream; charset=utf-8', body=stream)
        elif request.url.split('?')[0].endswith(('/api/auth/me', '/api/favorites')):
            route.fulfill(status=401, content_type='application/json', body='{"error":"no session"}')
        else:
            pytest.fail('unexpected API in static Analyze language test')

    page.route('**/api/**', api)
    try:
        page.goto(f'{local_beta_origin}/analyze.html?id=target-two&a_id=source-one', wait_until='domcontentloaded')
        page.wait_for_function("""() => window._finalReport && !document.getElementById('analyze-loading')
          && document.querySelectorAll('.section--revealed').length===9
          && Array.from(document.querySelectorAll('.section__body')).every(n=>n.textContent.trim().length>30)""")
        assert set(held) == {'ui', 'content'}
        assert posted == [expected_request]
        assert page.evaluate('window.__langChanges') == []
        original = page.evaluate('JSON.stringify(window._finalReport)')
        page.evaluate("window.i18n.setLang('en')")
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        # No EN dictionary yet: actual section fallback remains visible.
        expect(page.locator('#section-shared_structure .section__title')).to_have_text('候选结构')
        page.evaluate('window.__langObserver.takeRecords();window.__langChanges=[];window.__langNotifications=[]')
        held['ui'].fulfill(status=200, content_type='application/json', body=json.dumps(dictionaries['ui'], ensure_ascii=False))
        held['content'].fulfill(status=200, content_type='application/json', body=json.dumps(dictionaries['content'], ensure_ascii=False))
        expect(page.locator('#section-shared_structure .section__title')).to_have_text(catalog['page.analyze.section_shared_structure']['en'])
        assert page.evaluate('window.__langChanges') == []
        assert 'en' in page.evaluate('window.__langNotifications')
        same = page.evaluate("""async () => {
          window.__langObserver.takeRecords();window.__langChanges=[];window.__langNotifications=[];
          for(let n=0;n<3;n++)window.i18n.render();
          await Promise.resolve();return {changes:window.__langChanges,notifications:window.__langNotifications};
        }""")
        assert same == {'changes': [], 'notifications': ['en'] * 3}
        for lang, old in [('zh', 'en'), ('en', 'zh-CN'), ('zh', 'en')]:
            result = page.evaluate("""async lang => {
              window.__langObserver.takeRecords();window.__langChanges=[];window.__langNotifications=[];
              window.i18n.setLang(lang);await Promise.resolve();
              return {changes:window.__langChanges,notifications:window.__langNotifications};
            }""", lang)
            assert result == {'changes': [old], 'notifications': [lang]}
            expect(page.locator('html')).to_have_attribute('lang', 'en' if lang == 'en' else 'zh-CN')
            sections = page.locator('.section')
            assert sections.count() == 9
            for section in sections.all():
                key = section.get_attribute('data-key')
                expect(section.locator('.section__title')).to_have_text(catalog[f'page.analyze.section_{key}'][lang])
                assert len((section.locator('.section__body').text_content() or '').strip()) > 30
            expect(page.locator('#analyze-fav-label')).to_have_text(catalog['page.analyze.btn_fav'][lang])
            assert (page.locator('#analyze-tldr').text_content() or '').strip()
            assert page.locator('#analyze-tldr .cred-badge__chip').all_inner_texts() == [
                catalog[f'page.analyze.{key}'][lang]
                for key in ('candidate_only', 'mechanism_not_verified', 'review_not_recorded')
            ]
            assert page.evaluate('JSON.stringify(window._finalReport)') == original
            assert page.locator('.section--revealed').count() == 9
        assert errors == []
    finally:
        if not page.is_closed():
            page.evaluate('window.__langObserver && window.__langObserver.disconnect()')


# Only this public-entry consumer uses the actual formal Main lifespan/SMTP.
# The legacy research/source component fixture keeps its original scope.
from web.backend.tests.acceptance import public_entry_formal_main as _entry_module
real_entry_server = _entry_module.server


@pytest.mark.parametrize("viewport",[{"width":1280,"height":900},{"width":430,"height":932}])
@pytest.mark.parametrize("target",["my-research","kb-section"])
def test_public_entry_actual_owner_index_anchor(page,real_entry_server,viewport,target):
    page.set_viewport_size(viewport)
    base=real_entry_server["base"]
    _entry_module.login(page.context,base)
    _entry_module._entry_create(page.context,base,"导航真实归属对照")
    page.goto(base+"/classes")
    account=page.locator(".site-header__account-cta")
    expect(account).to_have_attribute("href","/research#my-research")
    if target=="my-research":account.click()
    else:
        page.goto(base+"/");page.locator("#local-kb-entry").click()
    expect(page.locator("#research-list-items article")).to_have_count(1)
    assert page.url==base+"/research#"+target
    bounds=page.locator("#"+target).bounding_box()
    # scrollIntoView rounds scrollY to device pixels; permit <1px rounding.
    assert -1<=bounds["y"]<page.viewport_size["height"]-44, {"section_y":bounds["y"],"scroll_y":page.evaluate("scrollY")}
    page.locator("#original-input").fill("导航之后新写的私密草稿不会被列表刷新改写")
    page.locator("#summary").fill("手写摘要必须保留")
    page.locator("#confirmed").check()
    page.locator("#original-input").focus();page.evaluate("scrollTo(0,0)")
    before=page.evaluate("scrollY")
    page.locator("#research-list-refresh").evaluate("e=>e.click()")
    expect(page.locator("#research-list-status")).to_contain_text("已读取 1")
    assert abs(page.evaluate("scrollY")-before)<2
    assert page.locator("#original-input").evaluate("e=>document.activeElement===e")
    expect(page.locator("#summary")).to_have_value("手写摘要必须保留")
    expect(page.locator("#confirmed")).to_be_checked()


@pytest.mark.parametrize("viewport",[{"width":1280,"height":900},{"width":430,"height":932}])
def test_public_entry_default_retirement_and_language(page,local_beta_origin,viewport,tmp_path):
    from urllib.parse import quote,urlsplit,parse_qs,unquote
    page.set_viewport_size(viewport)
    private="private retired input <script>not executable</script>"
    calls=[];network=[]
    def observe(request):
        network.append(request)
        if any(route in request.url for route in ("/api/ask/","/api/analyze","/api/search/assess","/api/search/synthesize")):calls.append(request.url)
    page.on("request",observe)
    page.goto(local_beta_origin+"/?q="+quote(private)+"&lang=zh")
    page.wait_for_function("window.__ask && window.i18n?.getLang() === 'zh'")
    assert "q" not in parse_qs(urlsplit(page.url).query) and private not in page.url
    expect(page.locator("#start-research")).to_have_attribute("href","/research")
    expect(page.locator("#local-kb-entry")).to_have_attribute("href","/research#kb-section")
    expect(page.locator("#ask-input")).to_be_disabled()
    expect(page.locator("#ask-fingerprint")).to_be_hidden()
    page.evaluate("""q=>{
      document.querySelector('#ask-input').value=q;
      document.querySelector('#ask-form').requestSubmit();
      document.querySelector('#ask-followup-input').value=q;
      document.querySelector('#ask-followup-form').requestSubmit();
      document.querySelector('.ask-chip').dispatchEvent(new MouseEvent('click',{bubbles:true}));
      document.querySelector('#ask-input').dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',ctrlKey:true,bubbles:true}));
      document.querySelector('#ask-fingerprint-confirm').dispatchEvent(new MouseEvent('click',{bubbles:true}));
      window.__ask.submitQuery(q,{summary:q});
    }""",private)
    expect(page.locator("#legacy-ask-status")).to_contain_text("已停用")
    page.get_by_role("button",name="仅必要功能",exact=True).click()
    expect(page.locator("#ask-thread")).to_be_hidden()
    expect(page.get_by_role("radiogroup",name="选择一个跨领域候选")).to_have_count(0)
    assert page.evaluate("sessionStorage.getItem('structural_fingerprint_draft')") is None
    assert private not in page.url and calls==[]
    # The incoming legacy URL existed before this page could clean it. None
    # of its subsequent requests may forward the private query or referrer.
    for request in network[1:]:
        assert "private retired input" not in unquote(request.url)
        assert "private retired input" not in unquote(request.headers.get("referer",""))
    assert page.locator("script").filter(has_text="not executable").count()==0
    assert "2–3" not in page.locator("body").inner_text()
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert page.locator("#start-research").bounding_box()["height"]>=44
    page.screenshot(path=str(tmp_path / "public-entry.png"),full_page=True)
    if viewport["width"]<720:
        page.locator("#site-menu-btn").click();page.locator("#site-menu-lang-toggle").click()
    else:page.locator("#lang-toggle").click()
    expect(page.locator("html")).to_have_attribute("lang","en")
    expect(page.locator("#start-research")).to_have_text("Start research")
    expect(page.locator("#legacy-ask-status")).to_contain_text("retired")
    expect(page.locator(".site-footer__link[href='/reports']")).to_have_text("Legacy reports")
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
    assert all(private not in (href or "") for href in page.locator("a").evaluate_all("links=>links.map(link=>link.getAttribute('href'))"))
    if page.locator("#site-menu-drawer").is_visible():page.keyboard.press("Escape")
    page.locator("#start-research").focus()
    assert page.locator("#start-research").evaluate("e=>document.activeElement===e")
    assert calls==[] and private not in page.url


def test_public_entry_no_script_native_forms_never_send_private_get(browser,local_beta_origin):
    context=browser.new_context(java_script_enabled=False)
    try:
        page=context.new_page();page.goto(local_beta_origin)
        expect(page.locator("#start-research")).to_be_visible()
        expect(page.locator("#ask-input")).to_be_disabled()
        expect(page.locator("#ask-followup-input")).to_be_disabled()
        expect(page.locator("#ask-form")).to_have_attribute("method","post")
        expect(page.locator("#ask-followup-form")).to_have_attribute("method","post")
        private="disabled native form private input"
        page.locator("#ask-input").evaluate("(e,q)=>e.value=q",private)
        with page.expect_request(lambda request:request.is_navigation_request()) as navigation:
            page.locator("#ask-form").evaluate("f=>HTMLFormElement.prototype.submit.call(f)")
        request=navigation.value
        assert request.method=="POST" and request.url==local_beta_origin+"/research"
        assert private not in (request.post_data or "") and private not in request.url
    finally:context.close()


def test_public_entry_real_login_return_owner_and_legacy_resource_links(page,real_entry_server):
    base=real_entry_server["base"]
    page.goto(base+"/")
    account=page.locator(".site-header__account-cta")
    expect(account).to_have_attribute("href","/auth/login?next=%2Fresearch")
    account.click()
    page.locator("#auth-email").fill(_entry_module.synthetic_email("public-entry-owner@example.test"))
    with page.expect_response("**/api/auth/request-link") as response:page.locator("#auth-submit").click()
    assert response.value.status==200
    link=_entry_module.magic_link(real_entry_server)
    page.goto(link)
    page.wait_for_url(base+"/research")
    expect(page.locator("#problem-form")).to_be_visible()
    saved=_entry_module._entry_create(page.context,base,"本人私有研究")
    other=page.context.browser.new_context()
    try:
        _entry_module.login(other,base,"public-entry-other@example.test")
        _entry_module._entry_create(other,base,"其他账户不应混入列表")
    finally:other.close()
    page.goto(base+"/classes")
    expect(page.locator(".site-header__account-cta")).to_have_attribute("href","/research#my-research")
    expect(page.locator(".site-footer__link[href='/reports']")).to_have_text("旧报告（历史）")
    page.locator(".site-header__account-cta").click()
    expect(page.locator("#research-list-items a")).to_have_count(1)
    expect(page.locator("#research-list-items a")).to_have_attribute("href","/research/"+saved["research"]["id"])
    assert "其他账户" not in page.locator("#research-list-items").inner_text()
    for route in ("/classes","/discoveries","/papers","/tools"):
        response=page.goto(base+route);assert response.status==200
        if route=="/tools":expect(page.locator(".tool-card")).to_have_count(8)
        else:expect(page.locator(".site-header__nav a[aria-current='page']")).to_have_attribute("href","/classes")


@pytest.mark.parametrize("viewport",[{"width":1280,"height":900},{"width":430,"height":932}])
def test_public_entry_main_cta_first_login_returns_to_research(page,real_entry_server,viewport):
    page.set_viewport_size(viewport)
    base=real_entry_server["base"]
    page.goto(base+"/");page.locator("#start-research").click()
    expect(page.locator("#access")).to_be_visible()
    page.locator("#access a").click()
    page.locator("#auth-email").fill(_entry_module.synthetic_email("first-entry-new-owner@example.test"))
    with page.expect_response("**/api/auth/request-link") as response:page.locator("#auth-submit").click()
    assert response.value.status==200
    page.goto(_entry_module.magic_link(real_entry_server))
    page.wait_for_url(lambda url:"/auth/" not in url)
    assert page.url==base+"/research"
    expect(page.locator("#problem-form")).to_be_visible()
    expect(page.locator("#research-list-status")).to_contain_text("还没有")
    saved=_entry_module._entry_create(page.context,base,"首登之后本人新研究")
    page.locator("#research-list-refresh").click()
    expect(page.locator("#research-list-items a")).to_have_count(1)
    expect(page.locator("#research-list-items a")).to_have_attribute("href","/research/"+saved["research"]["id"])
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
