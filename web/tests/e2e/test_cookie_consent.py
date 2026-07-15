"""W14-C (session #10, 2026-05-15) — Cookie consent banner e2e.

Tests the 3-tier cookie consent system mounted via <CookieConsent />:
  1. First visit (no localStorage) shows the banner.
  2. "Accept all" sets consent + dynamically imports the pinned Plausible module.
  3. "Essential only" suppresses Plausible.
  4. DNT (Do Not Track) header auto-disables analytics + hides banner.
  5. "Manage preferences" reopens the banner from elsewhere.

Strategy mirrors test_dark_mode.py — boot Next.js dev server, run Playwright
contexts with fresh localStorage per test. If Next.js / node_modules is
unavailable the entire module skips cleanly.

Run:
    cd web
    PYTHONPATH=. ../.venv/bin/python -m pytest tests/e2e/test_cookie_consent.py -v
"""
from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE_DIR = REPO_ROOT / "web" / "phase-detector"
PLAUSIBLE_EVENT = "https://plausible.bytedance.city/api/event"

_LOCAL_VENV = REPO_ROOT / ".venv" / "bin" / "python"
_MAIN_VENV = (
    Path.home() / "Projects" / "structural-isomorphism" / ".venv" / "bin" / "python"
)


def _published_universality_paths() -> tuple[str, ...]:
    source = (PHASE_DIR / "lib" / "sitemap-data.ts").read_text(encoding="utf-8")
    block = source.split(
        "export const PHASE_DETECTOR_UNIVERSALITY_CLASSES: string[] = [", 1
    )[1].split("];", 1)[0]
    return tuple(
        f"/universality/{class_id}"
        for class_id in re.findall(r'"([A-Za-z0-9_]+)"', block)
    )


def _resolve_python() -> str:
    env_override = os.environ.get("STRUCTURAL_TEST_PYTHON")
    if env_override and Path(env_override).exists():
        return env_override
    if _LOCAL_VENV.exists():
        return str(_LOCAL_VENV)
    if _MAIN_VENV.exists():
        return str(_MAIN_VENV)
    return sys.executable


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_port(host: str, port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _have_next_dev() -> bool:
    return (PHASE_DIR / "node_modules" / ".bin" / "next").exists()


def _capture_plausible_events(page) -> list[dict[str, object]]:
    payloads: list[dict[str, object]] = []

    def capture_event(route) -> None:
        payloads.append(json.loads(route.request.post_data or "{}"))
        route.fulfill(status=202, body="ok")

    # The official package ignores webdriver traffic unless the verifier flag
    # is present. The analytics origin is mocked; tracker code stays real.
    page.add_init_script("window.__plausible = true")
    # Capture every spelling of the analytics origin. A privacy regression
    # must not escape the test merely because it percent-encodes `/api/event`.
    page.route("https://plausible.bytedance.city/**", capture_event)
    page.route("https://plausible.bytedance.city./**", capture_event)
    page.route("http://plausible.bytedance.city/**", capture_event)
    page.route("https://plausible.bytedance.city:444/**", capture_event)
    return payloads


@pytest.fixture(scope="module")
def next_dev():
    """Spin up Next.js dev server. Skip if node_modules missing (CI-friendly)."""
    if not _have_next_dev():
        pytest.skip("Next.js not installed in phase-detector/node_modules")

    port = _free_port()
    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["PORT"] = str(port)
    env["NEXT_PUBLIC_USE_MOCK"] = "true"

    proc = subprocess.Popen(
        [str(PHASE_DIR / "node_modules" / ".bin" / "next"), "dev", "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(PHASE_DIR),
        env=env,
    )
    try:
        timeout = float(os.environ.get("STRUCTURAL_E2E_TIMEOUT", "90"))
        booted = _wait_port("127.0.0.1", port, timeout=timeout)
        if not booted:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
            except Exception:
                pass
            out = (proc.stdout.read(8192) if proc.stdout else b"").decode(
                errors="replace"
            )
            pytest.fail(f"next dev on :{port} did not start in {timeout}s\n{out[-2000:]}")
        deadline = time.time() + 60
        last_status = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=15
                ) as r:
                    last_status = r.status
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(1.0)
        if last_status != 200:
            out = (proc.stdout.read(4096) if proc.stdout else b"").decode(
                errors="replace"
            )
            pytest.fail(f"next dev / not 200 (last={last_status})\n{out[-1500:]}")
        yield {"base": f"http://127.0.0.1:{port}"}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def fresh_page(browser, next_dev):
    """Fresh context: clean localStorage, no DNT by default."""
    context = browser.new_context()
    page = context.new_page()
    yield page, next_dev["base"]
    context.close()


@pytest.fixture
def dnt_page(browser, next_dev):
    """Fresh context with DNT header — emulates a privacy-conscious user."""
    context = browser.new_context(extra_http_headers={"DNT": "1"})
    page = context.new_page()
    # navigator.doNotTrack is the client-side flag the banner checks.
    page.add_init_script("Object.defineProperty(navigator, 'doNotTrack', { value: '1', configurable: true });")
    yield page, next_dev["base"]
    context.close()


# ---------------------------------------------------------------------------
# 1. First visit shows banner
# ---------------------------------------------------------------------------
def test_first_visit_shows_banner(fresh_page):
    page, base = fresh_page
    page.goto(base + "/privacy", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('[data-testid="cookie-consent"]', state="visible", timeout=8000)
    # No localStorage choice yet
    stored = page.evaluate("() => localStorage.getItem('cookie_consent_v1')")
    assert stored is None, f"expected no consent on first visit, got {stored!r}"


# ---------------------------------------------------------------------------
# 2. Accept all → consent saved + Plausible loads
# ---------------------------------------------------------------------------
def test_accept_all_loads_plausible(fresh_page):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('[data-testid="cookie-accept-all"]', state="visible", timeout=8000)
    page.locator('[data-testid="cookie-accept-all"]').click()
    # Banner closes
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="detached", timeout=5000
    )
    # Consent persisted
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('cookie_consent_v1'))")
    assert stored["analytics"] is True
    assert stored["essential"] is True
    assert stored["marketing"] is False
    assert stored["version"] == 1
    page.wait_for_function("() => window.plausible?.s === 'npm'")
    deadline = time.time() + 5
    while not payloads and time.time() < deadline:
        page.wait_for_timeout(50)
    assert payloads and payloads[0]["n"] == "pageview"
    assert page.evaluate(
        """() => !document.querySelector('script[src*="/js/script.js"]')"""
    )


def test_plausible_transport_strips_url_secrets_referrer_and_unknown_props(
    fresh_page,
):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.goto(
        base + "/companies?email=private%40example.test#access-token",
        referer="https://referrer.example/private?secret=1",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.wait_for_selector(
        '[data-testid="cookie-accept-all"]', state="visible", timeout=8000
    )
    page.locator('[data-testid="cookie-accept-all"]').click()
    page.wait_for_function("() => window.plausible?.s === 'npm'")
    deadline = time.time() + 5
    while len(payloads) < 1 and time.time() < deadline:
        page.wait_for_timeout(50)
    assert payloads, "expected a sanitized Plausible pageview"

    pageview = payloads[0]
    assert set(pageview) <= {"u", "n", "d", "v", "p"}
    assert pageview["n"] == "pageview"
    assert pageview["u"] == base + "/companies"
    assert "?" not in str(pageview["u"])
    assert "#" not in str(pageview["u"])
    assert not {"r", "ref", "referrer"}.intersection(pageview)

    # The endpoint-scoped guard must leave unrelated application fetches alone.
    assert page.evaluate("() => fetch('/companies').then((r) => r.status)") == 200
    assert page.evaluate(
        """() => fetch('data:text/plain,ok').then(async (response) => ({
          status: response.status,
          body: await response.text(),
        }))"""
    ) == {"status": 200, "body": "ok"}

    # URL variants of the protected endpoint are not unrelated traffic. Query,
    # fragment and path-normalization aliases must fail closed before their raw
    # body reaches the wire. Browser URL parsing resolves dot segments before
    # the request; the guard must still compare the caller's raw target.
    before_endpoint_variants = len(payloads)
    variant_statuses = page.evaluate(
        """
        async (endpoint) => {
          const origin = new URL(endpoint).origin;
          const variants = [
            `${endpoint}?email=private@example.test`,
            `${endpoint}#private-fragment`,
            `${origin}/api/%65vent`,
            `${origin}/%61pi/event`,
            `${origin}/api%2fevent`,
            `${origin}/api//event`,
            `${origin}/api/private/../event`,
            `${origin}/api/%2e%2e/api/event`,
            `${origin}/api/%252e%252e/api/event`,
            `${origin}/api/%E0%A4%A`,
            `https://plausible.bytedance.city./api/event`,
            `http://plausible.bytedance.city/api/event`,
            `https://plausible.bytedance.city:444/api/event`,
            `https://PLAUSIBLE.BYTEDANCE.CITY/api/event`,
            `https://plausible.bytedance.city:443/api/event`,
            `https://plausible.bytedance.city%2e/api/event`,
          ];
          return Promise.all(variants.map((target) => fetch(target, {
            method: "POST",
            body: JSON.stringify({
              n: "pageview",
              u: "https://private.example/?token=1",
              p: { secret: "must-not-leave-browser" },
            }),
          }).then((response) => response.status)));
        }
        """,
        PLAUSIBLE_EVENT,
    )
    assert variant_statuses == [204] * 16
    assert len(payloads) == before_endpoint_variants

    # A URL object from another same-origin realm must still enter the same
    # sanitizer. Realm-specific `instanceof URL` checks are not a security
    # boundary.
    cross_realm_status = page.evaluate(
        """
        async (endpoint) => {
          const frame = document.createElement("iframe");
          document.body.append(frame);
          try {
            const ForeignURL = frame.contentWindow.URL;
            return await fetch(new ForeignURL(endpoint), {
              method: "POST",
              body: JSON.stringify({
                n: "pageview",
                u: "https://private.example/?token=1",
                p: { secret: "must-not-leave-browser" },
              }),
            }).then((response) => response.status);
          } finally {
            frame.remove();
          }
        }
        """,
        PLAUSIBLE_EVENT,
    )
    assert cross_realm_status == 202
    assert len(payloads) == before_endpoint_variants + 1
    assert payloads[-1] == {
        "n": "pageview",
        "u": base + "/companies",
        "d": "phase.bytedance.city",
    }

    # Runtime route checks use the browser's current path, not only the value
    # React observed at mount. Encoded, repeated-slash, dot-segment and
    # malformed spellings of a private route all stay fail closed even before
    # React observes a navigation and tears down the installed transport.
    route_variants = [
        "/%61uth/login",
        "/auth%2flogin",
        "/%2561uth/login",
        "/companies//auth/login",
        "/companies/../auth/login",
        "/companies/%2e%2e/auth/login",
        "/companies/%252e%252e/auth/login",
        "/%61uth/%E0%A4%A",
    ]
    before_route_variants = len(payloads)
    route_statuses = page.evaluate(
        """
        async ({ endpoint, aliasEndpoint, paths }) => {
          const statuses = [];
          for (const path of paths) {
            history.replaceState(null, "", path);
            for (const target of [endpoint, aliasEndpoint]) {
              statuses.push(await fetch(target, {
                method: "POST",
                body: JSON.stringify({
                  n: "newsletter_link_click",
                  u: "https://private.example/?token=1",
                  p: { issue: "private", destination: "archive" },
                }),
              }).then((response) => response.status));
            }
          }
          history.replaceState(null, "", "/companies");
          return statuses;
        }
        """,
        {
            "endpoint": PLAUSIBLE_EVENT,
            "aliasEndpoint": "https://plausible.bytedance.city./api/event",
            "paths": route_variants,
        },
    )
    assert route_statuses == [204] * (2 * len(route_variants))
    assert len(payloads) == before_route_variants

    # Exercise the real module's internal engagement path. Plausible 0.4.5
    # sends this directly, bypassing transformRequest; the endpoint guard must
    # observe the attempt but keep it from reaching the mocked event endpoint.
    before_engagement = len(payloads)
    engagement_attempts = page.evaluate(
        """
        async (endpoint) => {
          const guardedFetch = window.fetch;
          const ownVisibility = Object.getOwnPropertyDescriptor(
            document,
            "visibilityState",
          );
          const attempts = [];
          window.fetch = (input, init) => {
            const raw =
              typeof input === "string"
                ? input
                : input instanceof URL
                  ? input.href
                  : input.url;
            if (
              new URL(raw, window.location.href).href === endpoint &&
              typeof init?.body === "string"
            ) {
              attempts.push(JSON.parse(init.body));
            }
            return guardedFetch(input, init);
          };
          try {
            Object.defineProperty(document, "visibilityState", {
              configurable: true,
              value: "hidden",
            });
            document.dispatchEvent(new Event("visibilitychange"));
            await new Promise((resolve) => setTimeout(resolve, 150));
          } finally {
            window.fetch = guardedFetch;
            if (ownVisibility) {
              Object.defineProperty(document, "visibilityState", ownVisibility);
            } else {
              delete document.visibilityState;
            }
          }
          return attempts;
        }
        """,
        PLAUSIBLE_EVENT,
    )
    assert any(event.get("n") == "engagement" for event in engagement_attempts)
    assert len(payloads) == before_engagement

    before_custom = len(payloads)
    page.evaluate(
        """
        () => window.plausible("newsletter_link_click", {
          props: {
            issue: "42",
            destination: "archive",
            secret: "must-not-leave-browser",
            url: "https://private.example/token",
          },
        })
        """
    )
    deadline = time.time() + 5
    while len(payloads) <= before_custom and time.time() < deadline:
        page.wait_for_timeout(50)
    assert len(payloads) == before_custom + 1, (
        "expected exactly one sanitized Plausible custom event"
    )
    custom = payloads[-1]
    assert set(custom) <= {"u", "n", "d", "v", "p"}
    assert custom["n"] == "newsletter_link_click"
    assert custom["u"] == base + "/companies"
    assert custom["p"] == {"issue": "42", "destination": "archive"}
    assert not {"r", "ref", "referrer"}.intersection(custom)

    before_unknown_event = len(payloads)
    page.evaluate(
        """
        () => window.plausible("unregistered_private_event", {
          props: { secret: "must-not-leave-browser" },
        })
        """
    )
    page.wait_for_timeout(200)
    assert len(payloads) == before_unknown_event

    before_sensitive_route = len(payloads)
    page.goto(
        base + "/privacy?email=private%40example.test#access-token",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    page.evaluate(
        """
        () => window.plausible?.("newsletter_link_click", {
          props: { issue: "43", destination: "private" },
        })
        """
    )
    page.wait_for_timeout(400)
    assert len(payloads) == before_sensitive_route


def test_withdrawal_blocks_window_and_stale_official_tracker(fresh_page):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    page.locator('[data-testid="cookie-accept-all"]').click()
    page.wait_for_function("() => window.plausible?.s === 'npm'")
    deadline = time.time() + 5
    while not payloads and time.time() < deadline:
        page.wait_for_timeout(50)
    assert payloads
    page.evaluate("window.__stalePlausible = window.plausible")

    page.evaluate("window.dispatchEvent(new CustomEvent('cookie-consent:open'))")
    page.locator('[data-testid="cookie-tier-analytics"]').uncheck()
    page.locator('[data-testid="cookie-save-custom"]').click()
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="detached", timeout=5000
    )
    before_withdrawn_calls = len(payloads)
    page.evaluate(
        """
        () => {
          window.plausible?.("newsletter_link_click", {
            props: { issue: "withdrawn", destination: "private" },
          });
          window.__stalePlausible?.("newsletter_link_click", {
            props: { issue: "stale", destination: "private" },
          });
        }
        """
    )
    page.wait_for_timeout(400)
    assert len(payloads) == before_withdrawn_calls


# ---------------------------------------------------------------------------
# 3. Essential only → Plausible module NOT imported
# ---------------------------------------------------------------------------
def test_essential_only_suppresses_plausible(fresh_page):
    page, base = fresh_page
    page.goto(base + "/privacy", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('[data-testid="cookie-essential-only"]', state="visible", timeout=8000)
    page.locator('[data-testid="cookie-essential-only"]').click()
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="detached", timeout=5000
    )
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('cookie_consent_v1'))")
    assert stored["analytics"] is False
    has_plausible = page.evaluate(
        "() => !!document.getElementById('plausible-script')"
    )
    assert has_plausible is False


# ---------------------------------------------------------------------------
# 4. DNT auto-disables analytics + hides banner
# ---------------------------------------------------------------------------
def test_dnt_auto_disables_analytics(dnt_page):
    page, base = dnt_page
    page.goto(base + "/privacy", wait_until="domcontentloaded", timeout=30000)
    # Banner should not appear within a reasonable window
    # (we wait_for_timeout 1s then assert hidden)
    page.wait_for_timeout(1500)
    visible = page.evaluate(
        "() => { const el = document.querySelector('[data-testid=\"cookie-consent\"]'); return el && el.offsetParent !== null; }"
    )
    assert not visible, "banner should be hidden for DNT users"
    # Implicit consent record stored with analytics=false
    stored = page.evaluate("() => JSON.parse(localStorage.getItem('cookie_consent_v1'))")
    assert stored is not None and stored["analytics"] is False
    # The retired legacy Plausible script is never injected.
    has_plausible = page.evaluate(
        "() => !!document.getElementById('plausible-script')"
    )
    assert has_plausible is False


def test_dnt_cannot_be_overridden_from_reopened_preferences(dnt_page):
    page, base = dnt_page
    payloads = _capture_plausible_events(page)
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(500)

    page.evaluate("window.dispatchEvent(new CustomEvent('cookie-consent:open'))")
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="visible", timeout=5000
    )
    page.get_by_role("button", name="返回").click()
    page.locator('[data-testid="cookie-accept-all"]').click()
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="detached", timeout=5000
    )

    stored = page.evaluate(
        "() => JSON.parse(localStorage.getItem('cookie_consent_v1'))"
    )
    assert stored["analytics"] is False
    assert stored["marketing"] is False
    page.evaluate(
        """
        () => window.plausible?.("newsletter_link_click", {
          props: { issue: "dnt", destination: "archive" },
        })
        """
    )
    page.wait_for_timeout(300)
    assert payloads == []


def test_runtime_dnt_blocks_current_and_stale_tracker(fresh_page):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    page.locator('[data-testid="cookie-accept-all"]').click()
    page.wait_for_function("() => window.plausible?.s === 'npm'")
    deadline = time.time() + 5
    while not payloads and time.time() < deadline:
        page.wait_for_timeout(50)
    assert payloads

    page.evaluate(
        """
        () => {
          window.__stalePlausible = window.plausible;
          Object.defineProperty(navigator, "doNotTrack", {
            value: "1", configurable: true,
          });
        }
        """
    )
    before_dnt = len(payloads)
    page.evaluate(
        """
        () => {
          window.plausible?.("newsletter_link_click", {
            props: { issue: "current", destination: "archive" },
          });
          window.__stalePlausible?.("newsletter_link_click", {
            props: { issue: "stale", destination: "archive" },
          });
        }
        """
    )
    page.wait_for_timeout(400)
    assert len(payloads) == before_dnt


def test_malformed_consent_cannot_enable_analytics(fresh_page):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.add_init_script(
        """
        localStorage.setItem("cookie_consent_v1", JSON.stringify({
          essential: true,
          analytics: "yes",
          marketing: false,
          version: 1,
          timestamp: Date.now(),
        }));
        """
    )
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="visible", timeout=8000
    )
    page.wait_for_timeout(300)
    assert payloads == []


@pytest.mark.parametrize(
    "path",
    (
        "/company/AAPL",
        "/company/PG",
        "/company/0700.HK",
        "/newsletter/001",
        *_published_universality_paths(),
    ),
)
def test_allowlisted_dynamic_routes_emit_canonical_pageviews(fresh_page, path):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.add_init_script(
        """
        localStorage.setItem("cookie_consent_v1", JSON.stringify({
          essential: true,
          analytics: true,
          marketing: false,
          version: 1,
          timestamp: Date.now(),
        }));
        """
    )
    page.goto(
        base + path + "?private=discard#secret",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    deadline = time.time() + 5
    while not payloads and time.time() < deadline:
        page.wait_for_timeout(50)
    assert payloads
    assert payloads[0]["n"] == "pageview"
    assert payloads[0]["u"] == base + path


@pytest.mark.parametrize(
    "path",
    (
        "/unknown-private-capability",
        "/invite/opaque-token",
        "/company/SECRET123",
        "/company/TOO-LONG-TICKER",
        "/universality/opaque-token",
        "/universality/secrettoken_0123456789",
        "/universality/not_a_real_class",
        "/newsletter/not-an-issue",
        "/newsletter/999",
        "/%2569nvite%252fopaque-token",
    ),
)
def test_unknown_and_opaque_routes_never_emit_pageviews(fresh_page, path):
    page, base = fresh_page
    payloads = _capture_plausible_events(page)
    page.add_init_script(
        """
        localStorage.setItem("cookie_consent_v1", JSON.stringify({
          essential: true,
          analytics: true,
          marketing: false,
          version: 1,
          timestamp: Date.now(),
        }));
        """
    )
    page.goto(base + path, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(500)
    assert payloads == []


# ---------------------------------------------------------------------------
# 5. Manage preferences reopens the banner from privacy page button
# ---------------------------------------------------------------------------
def test_manage_preferences_reopens(fresh_page):
    page, base = fresh_page
    # First, accept all to dismiss banner
    page.goto(base + "/privacy", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_selector('[data-testid="cookie-accept-all"]', state="visible", timeout=8000)
    page.locator('[data-testid="cookie-accept-all"]').click()
    page.wait_for_selector(
        '[data-testid="cookie-consent"]', state="detached", timeout=5000
    )
    # Now click "Manage cookies" button on the privacy page
    page.locator('#main-content [data-testid="manage-cookies-button"]').click()
    # Banner reopens in customize mode
    page.wait_for_selector('[data-testid="cookie-consent"]', state="visible", timeout=5000)
    # Analytics checkbox should reflect prior choice (checked)
    checked = page.evaluate(
        "() => document.querySelector('[data-testid=\"cookie-tier-analytics\"]').checked"
    )
    assert checked is True
