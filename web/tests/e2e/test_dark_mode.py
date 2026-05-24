"""W13-A (session #10, 2026-05-15) — Dark mode + theme provider e2e.

Tests the 3-mode theme system mounted at app/layout.tsx via <ThemeProvider>:
  1. Default theme (no localStorage) = system.
  2. Toggle to dark applies `.dark` class on <html>.
  3. Toggle to light removes `.dark`.
  4. Persistence across page reload (localStorage `phase_theme`).
  5. Charts re-render with theme-aware palette (SparkLine + PhaseTrajectoryChart).
  6. No hydration mismatch warning in browser console.
  7. system mode follows `prefers-color-scheme` media query.
  8. WCAG AAA on body text in both themes (verified via JS contrast calc).

Strategy mirrors test_onboarding.py — boot Next.js dev server, run Playwright
contexts with fresh localStorage per test. If Next.js is unavailable (no
node_modules / port conflict) tests skip cleanly.

Run:
    cd web
    PYTHONPATH=. ../.venv/bin/python -m pytest tests/e2e/test_dark_mode.py -v
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
    """Spin up Next.js dev server for theme tests."""
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
            out = (proc.stdout.read(8192) if proc.stdout else b"").decode(errors="replace")
            pytest.fail(f"next dev on :{port} did not start in {timeout}s\n{out[-2000:]}")
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


# ---------------------------------------------------------------------------
# 1. Default theme (no localStorage) = system → renders without .dark class on
#    server, then client effect applies it iff prefers-color-scheme: dark.
# ---------------------------------------------------------------------------


def test_default_theme_is_system(fresh_page):
    page, base = fresh_page
    # Force light system preference so we can deterministically assert no .dark.
    page.emulate_media(color_scheme="light")
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    # Tour may auto-open — dismiss it via localStorage to avoid interference.
    page.evaluate("() => localStorage.setItem('phase_tour_seen', 'true')")
    page.reload(wait_until="domcontentloaded", timeout=30000)
    # Wait until the theme toggle is visible (ensures ThemeProvider mounted).
    page.wait_for_selector('[data-testid="theme-toggle"]', state="attached", timeout=8000)
    stored = page.evaluate("() => localStorage.getItem('phase_theme')")
    # We never set localStorage on first visit unless the user clicked the toggle.
    assert stored is None, f"expected no localStorage on first visit, got {stored!r}"
    # No `.dark` class on <html> when system pref is light.
    has_dark = page.evaluate("() => document.documentElement.classList.contains('dark')")
    assert has_dark is False, "html.dark should NOT be present when system=light"


# ---------------------------------------------------------------------------
# 2. Toggle to dark → applies .dark
# ---------------------------------------------------------------------------


def test_toggle_to_dark_applies_class(fresh_page):
    page, base = fresh_page
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    # Wait for the toggle to be ready (ThemeProvider mounted, useTheme wired).
    page.wait_for_selector('[data-testid="theme-toggle-dark"]', state="visible", timeout=8000)
    page.locator('[data-testid="theme-toggle-dark"]').first.click()
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=8000,
    )
    stored = page.evaluate("() => localStorage.getItem('phase_theme')")
    assert stored == "dark", f"localStorage should be 'dark', got {stored!r}"
    # color-scheme inline style flips so native form controls match.
    cs = page.evaluate("() => document.documentElement.style.colorScheme")
    assert cs == "dark", f"colorScheme should be 'dark', got {cs!r}"


# ---------------------------------------------------------------------------
# 3. Toggle to light → removes .dark
# ---------------------------------------------------------------------------


def test_toggle_to_light_removes_class(fresh_page):
    page, base = fresh_page
    # Start from dark so we can verify the flip.
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        "localStorage.setItem('phase_tour_seen', 'true'); localStorage.setItem('phase_theme', 'dark');"
    )
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    page.locator('[data-testid="theme-toggle-light"]').first.click()
    page.wait_for_function(
        "() => !document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    stored = page.evaluate("() => localStorage.getItem('phase_theme')")
    assert stored == "light", f"localStorage should be 'light', got {stored!r}"


# ---------------------------------------------------------------------------
# 4. Persistence across reload
# ---------------------------------------------------------------------------


def test_theme_persists_across_reload(fresh_page):
    page, base = fresh_page
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    page.locator('[data-testid="theme-toggle-dark"]').first.click()
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    page.reload(wait_until="domcontentloaded", timeout=30000)
    # After reload, ThemeProvider's mount effect should re-apply the dark class.
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    stored = page.evaluate("() => localStorage.getItem('phase_theme')")
    assert stored == "dark"


# ---------------------------------------------------------------------------
# 5. system mode follows prefers-color-scheme
# ---------------------------------------------------------------------------


def test_system_mode_follows_prefers_color_scheme(fresh_page):
    page, base = fresh_page
    # Explicit `system` mode in storage so we test the system-tracking branch
    # rather than the no-localStorage default branch.
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        "localStorage.setItem('phase_tour_seen', 'true'); localStorage.setItem('phase_theme', 'system');"
    )
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    # Flip system preference and verify the html class follows.
    page.emulate_media(color_scheme="light")
    page.wait_for_function(
        "() => !document.documentElement.classList.contains('dark')",
        timeout=4000,
    )


# ---------------------------------------------------------------------------
# 6. Charts re-render with theme-aware palette
# ---------------------------------------------------------------------------


def test_sparkline_recolors_in_dark_mode(fresh_page):
    page, base = fresh_page
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
    # SparkLine renders inside CompanyCard on the /companies screener page,
    # not on the landing page (which uses ExploreCardsGrid).
    page.goto(base + "/companies", wait_until="domcontentloaded", timeout=30000)
    # Wait for at least one SparkLine to render.
    page.wait_for_selector('[data-testid="sparkline"]', state="attached", timeout=15000)
    # Grab the first segment's stroke color in light mode.
    light_strokes = page.evaluate(
        """
        () => {
            const sparkLines = document.querySelectorAll('[data-testid="sparkline"]');
            if (sparkLines.length === 0) return [];
            const first = sparkLines[0];
            const paths = first.querySelectorAll('path');
            return Array.from(paths).map(p => p.getAttribute('stroke'));
        }
        """
    )
    assert len(light_strokes) > 0, "expected at least one path in SparkLine"
    # Toggle to dark.
    page.locator('[data-testid="theme-toggle-dark"]').first.click()
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    # Re-read the same first sparkline's stroke colors.
    dark_strokes = page.evaluate(
        """
        () => {
            const first = document.querySelector('[data-testid="sparkline"]');
            if (!first) return [];
            const paths = first.querySelectorAll('path');
            return Array.from(paths).map(p => p.getAttribute('stroke'));
        }
        """
    )
    # At least one color should differ between light and dark palettes.
    assert (
        light_strokes != dark_strokes
    ), f"SparkLine should recolor in dark mode (light={light_strokes[:3]}, dark={dark_strokes[:3]})"


# ---------------------------------------------------------------------------
# 7. No hydration mismatch warning in console
# ---------------------------------------------------------------------------


def test_no_hydration_mismatch_warning(fresh_page):
    page, base = fresh_page
    console_messages: list[str] = []

    def on_console(msg):
        text = msg.text
        # React 18 hydration mismatch warnings.
        lower = text.lower()
        if (
            "did not match" in lower
            or "hydration" in lower
            or "text content does not match" in lower
        ):
            console_messages.append(text)

    page.on("console", on_console)
    page.emulate_media(color_scheme="dark")
    page.add_init_script(
        "localStorage.setItem('phase_tour_seen', 'true'); localStorage.setItem('phase_theme', 'dark');"
    )
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    # Allow React to flush any deferred errors.
    page.wait_for_timeout(1500)
    # `suppressHydrationWarning` on <html> should mute the class-mismatch warning.
    assert console_messages == [], (
        f"unexpected hydration warnings in console: {console_messages[:3]}"
    )


# ---------------------------------------------------------------------------
# 8. WCAG AAA body-text contrast in both themes (≥ 7:1 normal text)
# ---------------------------------------------------------------------------


def test_wcag_aaa_body_contrast(fresh_page):
    """Verify computed body color vs body background ≥ 7:1 in both themes."""
    page, base = fresh_page
    page.emulate_media(color_scheme="light")
    page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
    page.goto(base + "/", wait_until="domcontentloaded", timeout=30000)

    contrast_script = """
    () => {
        function srgbToLin(c) {
            c = c / 255;
            return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
        }
        function relLum(rgb) {
            const [r, g, b] = rgb;
            return 0.2126 * srgbToLin(r) + 0.7152 * srgbToLin(g) + 0.0722 * srgbToLin(b);
        }
        function parseRgb(s) {
            const m = s.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/);
            return m ? [+m[1], +m[2], +m[3]] : null;
        }
        function contrast(a, b) {
            const la = relLum(a), lb = relLum(b);
            const hi = Math.max(la, lb), lo = Math.min(la, lb);
            return (hi + 0.05) / (lo + 0.05);
        }
        const body = document.body;
        const fg = parseRgb(getComputedStyle(body).color);
        const bg = parseRgb(getComputedStyle(body).backgroundColor);
        if (!fg || !bg) return null;
        return contrast(fg, bg);
    }
    """
    light_ratio = page.evaluate(contrast_script)
    assert light_ratio is not None, "could not compute light contrast"
    assert light_ratio >= 7.0, f"light body contrast {light_ratio:.2f}:1 < AAA 7.0:1"

    # Toggle to dark.
    page.locator('[data-testid="theme-toggle-dark"]').first.click()
    page.wait_for_function(
        "() => document.documentElement.classList.contains('dark')",
        timeout=4000,
    )
    # Let the 300ms color transition complete.
    page.wait_for_timeout(400)
    dark_ratio = page.evaluate(contrast_script)
    assert dark_ratio is not None, "could not compute dark contrast"
    assert dark_ratio >= 7.0, f"dark body contrast {dark_ratio:.2f}:1 < AAA 7.0:1"


# ---------------------------------------------------------------------------
# 9. Mobile drawer also exposes the toggle (touchable in compact mode)
# ---------------------------------------------------------------------------


def test_theme_toggle_visible_in_mobile_drawer(browser, next_dev):
    context = browser.new_context(viewport={"width": 375, "height": 812})
    page = context.new_page()
    try:
        page.add_init_script("localStorage.setItem('phase_tour_seen', 'true');")
        page.goto(next_dev["base"] + "/", wait_until="domcontentloaded", timeout=30000)
        page.locator('[data-testid="mobile-nav-toggle"]').click()
        # Drawer renders a second theme-toggle group.
        page.wait_for_selector(
            '#mobile-nav-drawer [data-testid="theme-toggle"]',
            state="visible",
            timeout=4000,
        )
    finally:
        context.close()
