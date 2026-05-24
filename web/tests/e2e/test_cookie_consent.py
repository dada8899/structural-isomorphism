"""W14-C (session #10, 2026-05-15) — Cookie consent banner e2e.

Tests the 3-tier cookie consent system mounted via <CookieConsent />:
  1. First visit (no localStorage) shows the banner.
  2. "Accept all" sets consent + loads Plausible script.
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

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE_DIR = REPO_ROOT / "web" / "phase-detector"

_LOCAL_VENV = REPO_ROOT / ".venv" / "bin" / "python"
_MAIN_VENV = (
    Path.home() / "Projects" / "structural-isomorphism" / ".venv" / "bin" / "python"
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
    page.goto(base + "/privacy", wait_until="domcontentloaded", timeout=30000)
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
    assert stored["version"] == 1
    # Plausible script injected
    has_plausible = page.evaluate(
        "() => !!document.getElementById('plausible-script')"
    )
    assert has_plausible is True


# ---------------------------------------------------------------------------
# 3. Essential only → Plausible NOT loaded
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
    # Plausible NOT injected
    has_plausible = page.evaluate(
        "() => !!document.getElementById('plausible-script')"
    )
    assert has_plausible is False


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
    page.locator('[data-testid="manage-cookies-button"]').click()
    # Banner reopens in customize mode
    page.wait_for_selector('[data-testid="cookie-consent"]', state="visible", timeout=5000)
    # Analytics checkbox should reflect prior choice (checked)
    checked = page.evaluate(
        "() => document.querySelector('[data-testid=\"cookie-tier-analytics\"]').checked"
    )
    assert checked is True
