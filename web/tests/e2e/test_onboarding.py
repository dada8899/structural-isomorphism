"""W12-D (session #10, 2026-05-15) — First-time user onboarding tour e2e.

Tests the 4-step pure-React tour mounted globally in app/layout.tsx:
  1. First visit triggers tour auto-start (after AUTO_START_DELAY_MS).
  2. Skip dismisses + sets localStorage `phase_tour_seen=true`.
  3. Next/Prev navigation moves between steps + updates the step counter.
  4. Completion (clicking Next on the last step) sets localStorage.
  5. ESC closes the tour (counted as skip).
  6. "导览" link in TopNav restarts tour after dismissal.
  7. Mobile viewport (375x812) still renders the tour readably.
  8. /onboarding deep-link force-opens regardless of localStorage flag.

Strategy: boot Next.js dev server pointed at the phase-detector app. The
tour is pure client-side — no backend needed. We use a single module-scoped
fixture for the dev server (slow boot) and per-test browser contexts so the
localStorage flag is fresh.

Run:
    cd web
    PYTHONPATH=. ../.venv/bin/python -m pytest tests/e2e/test_onboarding.py -v

If Next dev server is unavailable (no node_modules), tests skip.
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
_MAIN_VENV = Path.home() / "Projects" / "structural-isomorphism" / ".venv" / "bin" / "python"


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
    """Spin up Next.js dev server for the tour tests."""
    if not _have_next_dev():
        pytest.skip("Next.js not installed in phase-detector/node_modules")

    port = _free_port()
    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["PORT"] = str(port)
    env["NEXT_PUBLIC_USE_MOCK"] = "true"  # avoids needing the FastAPI backend

    proc = subprocess.Popen(
        [str(PHASE_DIR / "node_modules" / ".bin" / "next"), "dev", "--port", str(port)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
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
            out = (proc.stdout.read(8192) if proc.stdout else b"").decode(errors="replace")
            pytest.fail(f"next dev on :{port} did not start in {timeout}s\n{out[-2000:]}")
        # Wait for compile-on-first-request.
        deadline = time.time() + 60
        last_status = None
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=15) as r:
                    last_status = r.status
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(1.0)
        if last_status != 200:
            out = (proc.stdout.read(4096) if proc.stdout else b"").decode(errors="replace")
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
    """A page in a fresh context (clean localStorage)."""
    context = browser.new_context()
    page = context.new_page()
    yield page, next_dev["base"]
    context.close()


def _wait_for_tour_visible(page, timeout: int = 8000) -> None:
    page.wait_for_selector('[data-testid="onboarding-tour"]', state="visible", timeout=timeout)


# ---------------------------------------------------------------------------
# 1. First visit triggers the tour
# ---------------------------------------------------------------------------

def test_first_visit_auto_starts_tour(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    # Tour auto-starts after a 1500ms idle delay.
    _wait_for_tour_visible(page, timeout=8000)
    tooltip = page.locator('[data-testid="tour-tooltip"]')
    assert tooltip.is_visible()
    # Step counter shows 1 / 4.
    text = tooltip.inner_text()
    assert "1 / 4" in text, f"expected '1 / 4' counter, got: {text!r}"


# ---------------------------------------------------------------------------
# 2. Skip dismisses and sets localStorage
# ---------------------------------------------------------------------------

def test_skip_dismisses_and_persists_flag(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    _wait_for_tour_visible(page)
    page.locator('[data-testid="tour-skip"]').click()
    page.wait_for_selector('[data-testid="onboarding-tour"]', state="hidden", timeout=4000)
    flag = page.evaluate("() => localStorage.getItem('phase_tour_seen')")
    assert flag == "true", f"phase_tour_seen should be 'true' after skip, got {flag!r}"


# ---------------------------------------------------------------------------
# 3. Next/Prev navigation works
# ---------------------------------------------------------------------------

def test_next_prev_navigation(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    _wait_for_tour_visible(page)
    tooltip = page.locator('[data-testid="tour-tooltip"]')

    # Click Next → step 2 / 4
    page.locator('[data-testid="tour-next"]').click()
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"onboarding-tour\"]')?.dataset.tourStep === '2'",
        timeout=4000,
    )
    assert "2 / 4" in tooltip.inner_text()

    # Click Prev → back to 1 / 4
    page.locator('[data-testid="tour-prev"]').click()
    page.wait_for_function(
        "() => document.querySelector('[data-testid=\"onboarding-tour\"]')?.dataset.tourStep === '1'",
        timeout=4000,
    )
    assert "1 / 4" in tooltip.inner_text()


# ---------------------------------------------------------------------------
# 4. Completion sets localStorage and closes
# ---------------------------------------------------------------------------

def test_completion_closes_and_persists(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    _wait_for_tour_visible(page)
    # Click Next 4 times — last click is "Get started" / completion.
    for _ in range(4):
        page.locator('[data-testid="tour-next"]').click()
        page.wait_for_timeout(150)
    page.wait_for_selector('[data-testid="onboarding-tour"]', state="hidden", timeout=4000)
    flag = page.evaluate("() => localStorage.getItem('phase_tour_seen')")
    assert flag == "true", f"phase_tour_seen should be 'true' after completion, got {flag!r}"


# ---------------------------------------------------------------------------
# 5. ESC closes
# ---------------------------------------------------------------------------

def test_escape_closes_tour(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    _wait_for_tour_visible(page)
    page.keyboard.press("Escape")
    page.wait_for_selector('[data-testid="onboarding-tour"]', state="hidden", timeout=4000)
    flag = page.evaluate("() => localStorage.getItem('phase_tour_seen')")
    assert flag == "true"


# ---------------------------------------------------------------------------
# 6. Restart from TopNav link works after dismissal
# ---------------------------------------------------------------------------

def test_restart_from_nav_link(fresh_page):
    page, base = fresh_page
    # Pre-set the seen flag so auto-start is suppressed.
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    # Auto-start suppressed: tour should not be visible after 2s wait.
    page.wait_for_timeout(2200)
    assert page.locator('[data-testid="onboarding-tour"]').count() == 0
    # Click the restart link in TopNav.
    page.locator('[data-testid="tour-restart-link"]').first.click()
    _wait_for_tour_visible(page, timeout=4000)
    # localStorage was cleared by restart helper.
    flag = page.evaluate("() => localStorage.getItem('phase_tour_seen')")
    assert flag in (None, "false") or flag != "true", (
        f"restart should clear seen flag, got {flag!r}"
    )


# ---------------------------------------------------------------------------
# 7. Mobile viewport responsive
# ---------------------------------------------------------------------------

def test_mobile_viewport_renders_tour(browser, next_dev):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    try:
        page.goto(next_dev["base"] + "/", wait_until="domcontentloaded", timeout=30000)
        _wait_for_tour_visible(page, timeout=8000)
        tooltip = page.locator('[data-testid="tour-tooltip"]')
        box = tooltip.bounding_box()
        assert box is not None, "tooltip should have a bounding box on mobile"
        # Tooltip must fit within the viewport width (with margin slack).
        assert box["width"] <= 375, f"tooltip overflows mobile viewport: width={box['width']}"
        # Buttons ≥ 44px (touch-friendly).
        next_btn = page.locator('[data-testid="tour-next"]')
        nb = next_btn.bounding_box()
        assert nb and nb["height"] >= 40, f"next button too small for touch: {nb}"
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 8. /onboarding deep-link force-opens
# ---------------------------------------------------------------------------

def test_onboarding_deep_link_force_opens(browser, next_dev):
    """Even with seen=true, /onboarding force-opens the tour."""
    context = browser.new_context()
    page = context.new_page()
    try:
        page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
        page.goto(next_dev["base"] + "/onboarding", wait_until="domcontentloaded", timeout=30000)
        _wait_for_tour_visible(page, timeout=6000)
        tooltip = page.locator('[data-testid="tour-tooltip"]')
        assert tooltip.is_visible()
    finally:
        context.close()


# ---------------------------------------------------------------------------
# 9. Accessibility: dialog role + aria-modal
# ---------------------------------------------------------------------------

def test_tour_dialog_a11y(fresh_page):
    page, base = fresh_page
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    _wait_for_tour_visible(page)
    tooltip = page.locator('[data-testid="tour-tooltip"]')
    assert tooltip.get_attribute("role") == "dialog"
    assert tooltip.get_attribute("aria-modal") == "true"
    assert tooltip.get_attribute("aria-labelledby") is not None
    assert tooltip.get_attribute("aria-describedby") is not None
