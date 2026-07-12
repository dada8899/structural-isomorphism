"""Real Next.js auth/favorites journeys (no substitute HTML shell)."""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from urllib.parse import urlsplit

import pytest

ROOT = Path(__file__).resolve().parents[3]
PHASE = ROOT / "web" / "phase-detector"
BACKEND = ROOT / "web" / "backend"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)
AXE = PHASE / "node_modules" / "axe-core" / "axe.min.js"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_url(url: str, timeout: float = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.25)
    pytest.fail(f"service did not become ready: {url}")


@pytest.fixture(scope="module")
def real_stack(tmp_path_factory):
    if not (PHASE / "node_modules/.bin/next").exists():
        pytest.skip("Next.js dependencies are not installed")
    next_port, api_port = free_port(), free_port()
    origin = f"http://127.0.0.1:{next_port}"
    data_dir = tmp_path_factory.mktemp("real-auth")
    shim = data_dir / "auth_api.py"
    shim.write_text(
        "\n".join([
            "import os, sys", f"sys.path.insert(0, {str(BACKEND)!r})",
            "os.environ['AUTH_ENABLED']='true'", "os.environ['AUTH_DEV_MODE']='true'",
            f"os.environ['AUTH_LINK_BASE_URL']={origin!r}",
            f"os.environ['AUTH_DATA_DIR']={str(data_dir)!r}",
            "os.environ['JWT_SECRET']='real-e2e-secret-with-at-least-32-characters'",
            "from fastapi import FastAPI", "from api.auth import router",
            "from api.favorites import router as favorites_router",
            "app=FastAPI()", "app.include_router(router, prefix='/api')",
            "app.include_router(favorites_router, prefix='/api')",
            "import uvicorn", f"uvicorn.run(app, host='127.0.0.1', port={api_port}, log_level='warning')",
        ]), encoding="utf-8",
    )
    env = os.environ.copy()
    env.update({
        "NEXT_TELEMETRY_DISABLED": "1", "NEXT_PUBLIC_AUTH_ENABLED": "true",
        "NEXT_PUBLIC_AUTH_DEV_MODE": "true", "NEXT_PUBLIC_API_BASE": "/api",
        "NEXT_PUBLIC_USE_MOCK": "true",
    })
    api = subprocess.Popen([str(PYTHON), str(shim)], cwd=ROOT)
    web = subprocess.Popen(
        [str(PHASE / "node_modules/.bin/next"), "dev", "--port", str(next_port)],
        cwd=PHASE, env=env,
    )
    try:
        wait_url(f"http://127.0.0.1:{api_port}/docs")
        wait_url(origin + "/auth/login")
        yield {"origin": origin, "api": f"http://127.0.0.1:{api_port}"}
    finally:
        for process in (web, api):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def install_auth_proxy(page, stack) -> None:
    def proxy(route):
        request = route.request
        path = urlsplit(request.url).path
        headers = dict(request.headers)
        headers["origin"] = stack["origin"]
        upstream = urllib.request.Request(
            stack["api"] + path,
            method=request.method,
            headers=headers,
            data=request.post_data.encode() if request.post_data else None,
        )
        try:
            response = urllib.request.urlopen(upstream, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            route.fulfill(
                status=response.status,
                headers=dict(response.headers.items()),
                body=response.read(),
            )
    page.route("**/api/auth/**", proxy)
    page.route("**/api/favorites**", proxy)


def test_real_next_magic_link_cookie_refresh_and_logout_failure(browser, real_stack):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.set_default_timeout(8_000)
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"] + "/auth/login")
    page.get_by_test_id("auth-login-email").fill("real-next@example.com")
    page.get_by_test_id("auth-login-submit").click()
    page.get_by_test_id("auth-login-dev-link").wait_for()
    link = page.get_by_test_id("auth-login-dev-link").get_attribute("href")
    assert link and "token=" in link
    page.goto(link)
    page.get_by_test_id("auth-verify-success").wait_for()
    page.wait_for_url("**/me")
    page.reload()
    assert page.get_by_test_id("me-email").inner_text() == "real-next@example.com"

    page.route("**/api/auth/logout", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body=json.dumps({"ok": False, "error": "temporary"}),
    ))
    page.get_by_test_id("me-logout").click()
    page.get_by_text("退出失败，你仍处于登录状态，请重试。", exact=True).wait_for()
    assert page.get_by_test_id("me-email").is_visible()
    context.close()


def test_real_next_session_favorites_persist_across_browser_contexts(browser, real_stack):
    first = browser.new_context(viewport={"width": 390, "height": 844})
    page = first.new_page()
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"] + "/auth/login")
    page.get_by_test_id("auth-login-email").fill("favorites-real@example.com")
    page.get_by_test_id("auth-login-submit").click()
    page.get_by_test_id("auth-login-dev-link").wait_for()
    link = page.get_by_test_id("auth-login-dev-link").get_attribute("href")
    assert link
    page.goto(link)
    page.wait_for_url("**/me")
    result = page.evaluate("""async () => {
      const response = await fetch('/api/favorites/AAPL', {
        method: 'POST', credentials: 'include'
      });
      return {status: response.status, url: response.url};
    }""")
    assert result["status"] == 201
    assert "/api/api/" not in result["url"]
    first.close()

    second = browser.new_context(viewport={"width": 390, "height": 844})
    page = second.new_page()
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"] + "/auth/login")
    page.get_by_test_id("auth-login-email").fill("favorites-real@example.com")
    page.get_by_test_id("auth-login-submit").click()
    page.get_by_test_id("auth-login-dev-link").wait_for()
    second_link = page.get_by_test_id("auth-login-dev-link").get_attribute("href")
    assert second_link
    page.goto(second_link)
    page.wait_for_url("**/me")
    page.goto(real_stack["origin"] + "/me/favorites")
    page.get_by_test_id("favorites-page").wait_for()
    assert page.get_by_test_id("favorites-count").inner_text() == "共 1 家公司"
    page.get_by_test_id("favorite-card-AAPL").wait_for()
    assert page.get_by_test_id("favorite-card-AAPL").get_by_text(
        "AAPL", exact=True
    ).is_visible()
    second.close()


def test_phase_account_entry_is_visible_on_desktop_and_mobile(browser, real_stack):
    desktop = browser.new_context(viewport={"width": 1280, "height": 800})
    page = desktop.new_page()
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"])
    entry = page.get_by_test_id("auth-nav-signin")
    entry.wait_for()
    assert entry.inner_text() == "注册 / 登录"
    assert entry.get_attribute("href") == "/auth/login"
    desktop.close()

    mobile = browser.new_context(viewport={"width": 390, "height": 844})
    page = mobile.new_page()
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"])
    page.get_by_test_id("mobile-nav-toggle").click()
    entry = page.get_by_role("menu", name="主导航（移动）").get_by_test_id(
        "auth-nav-signin"
    )
    entry.wait_for()
    assert entry.inner_text() == "注册 / 登录"
    assert entry.get_attribute("href") == "/auth/login"
    mobile.close()

def test_favorites_partial_delete_retains_failed_row(browser, real_stack):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.add_init_script("localStorage.setItem('phase_api_key','e2e-key')")

    def favorites(route):
        request = route.request
        if request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"tickers":["AAPL","TSLA"],"authenticated":true}',
            )
        elif request.url.endswith("/TSLA"):
            route.fulfill(status=503, content_type="application/json", body='{"error":"temporary"}')
        else:
            route.fulfill(status=204, body="")
    page.route("**/api/favorites**", favorites)
    page.route("**/api/company/**", lambda route: route.fulfill(status=503, body=""))
    page.goto(real_stack["origin"] + "/me/favorites")
    page.get_by_test_id("favorites-page").wait_for()
    page.get_by_test_id("favorites-remove-all").click()
    page.get_by_test_id("favorites-confirm-remove-all").click()
    failure = page.get_by_text(re.compile(r"1 个收藏删除失败"))
    failure.wait_for()
    assert "已保留在列表中" in failure.inner_text()
    assert page.get_by_test_id("favorites-count").inner_text() == "共 1 家公司"
    context.close()


@pytest.mark.parametrize("path", ["/auth/login", "/me/favorites", "/privacy"])
def test_mobile_keyboard_and_axe_critical_pages(browser, real_stack, path):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    install_auth_proxy(page, real_stack)
    page.goto(real_stack["origin"] + path)
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement !== document.body")
    page.add_script_tag(content=AXE.read_text(encoding="utf-8"))
    violations = page.evaluate("""async () => (await axe.run(document, {
      runOnly: {type: 'tag', values: ['wcag2a','wcag2aa','wcag21aa']}
    })).violations.filter(v => ['critical','serious'].includes(v.impact))""")
    assert violations == []
    context.close()


@pytest.mark.parametrize("width", [375, 390])
def test_phase_key_control_inventory_is_named_and_keyboard_reachable(
    browser, real_stack, width,
):
    context = browser.new_context(viewport={"width": width, "height": 844})
    page = context.new_page()
    install_auth_proxy(page, real_stack)
    failures: list[str] = []
    routes = (
        "/", "/zh", "/companies", "/company/AAPL",
        "/compare?tickers=AAPL,TSLA", "/universality",
        "/universality/preferential_attachment", "/methodology", "/backtest",
        "/newsletter", "/newsletter/001", "/about", "/privacy", "/pricing",
        "/onboarding", "/search", "/offline", "/auth/login", "/auth/verify",
        "/me", "/me/favorites", "/thank-you", "/checkout/mock",
    )
    for path in routes:
        page.goto(real_stack["origin"] + path, wait_until="domcontentloaded")
        controls = page.locator("a[href],button,input,select,textarea")
        for index in range(controls.count()):
            control = controls.nth(index)
            if not control.is_visible():
                continue
            if control.is_disabled() or control.get_attribute("aria-disabled") == "true":
                continue
            label = control.evaluate("""el => (
              el.getAttribute('aria-label') || el.getAttribute('title') ||
              el.getAttribute('placeholder') || el.innerText || el.value || ''
            ).trim()""")
            if not label:
                failures.append(f"{path}: unnamed {control.evaluate('el => el.tagName')}[{index}]")
            if not control.evaluate("el => el.tabIndex >= 0"):
                failures.append(f"{path}: unfocusable control[{index}] {label!r}")
    context.close()
    assert failures == [], "control inventory failures:\n" + "\n".join(failures)
