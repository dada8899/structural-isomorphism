"""W10-B (session #10) — Pricing page + mock-checkout e2e.

Tests:
  1. Pricing page renders 3 tiers (Free, Pro, Team)
  2. Annual / monthly toggle changes the displayed price
  3. "Start Pro" CTA navigates to /checkout/mock?tier=pro
  4. Mock checkout success flow → /thank-you?tier=pro
  5. Mock checkout decline flow (force) → /pricing?error=declined
  6. /api/checkout/mock and /api/usage backend smoke

Strategy: spin up Next.js dev server + a minimal FastAPI backend on adjacent
ports. Next dev proxies /api/* to the backend via the rewrite below (inline
shim). Playwright drives the real DOM.

Run:
    cd web
    PYTHONPATH=. ../.venv/bin/python -m pytest tests/e2e/test_pricing_page.py -v

If Next dev server takes too long to boot, set STRUCTURAL_E2E_TIMEOUT=120.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE_DIR = REPO_ROOT / "web" / "phase-detector"
WEB_BACKEND = REPO_ROOT / "web" / "backend"

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


@pytest.fixture(scope="module")
def backend(tmp_path_factory):
    """Minimal FastAPI app with just checkout_mock router mounted, on its own port."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("ck-data")

    shim_code = f"""
import sys
sys.path.insert(0, {str(WEB_BACKEND)!r})
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api import checkout_mock as ck
from pathlib import Path

def _patched_data_file():
    return Path({str(data_dir)!r}) / "mock_checkouts.jsonl"
ck._data_file = _patched_data_file

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)
app.include_router(ck.router, prefix="/api")

import uvicorn
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""
    shim_path = data_dir / "shim.py"
    shim_path.write_text(shim_code, encoding="utf-8")
    venv_py = _resolve_python()
    proc = subprocess.Popen(
        [str(venv_py), str(shim_path)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    try:
        assert _wait_port("127.0.0.1", port, timeout=15.0), \
            f"backend on {port} didn't start: {(proc.stdout.read(4096) if proc.stdout else b'')!r}"
        yield {"base": f"http://127.0.0.1:{port}", "data_dir": data_dir, "port": port}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def _have_next_dev() -> bool:
    return (PHASE_DIR / "node_modules" / ".bin" / "next").exists()


@pytest.fixture(scope="module")
def next_dev(backend):
    """Spin up Next.js dev server. Slow to boot (~10-20s).

    NOTE: we do NOT modify next.config.js — that would trigger HMR rebuilds
    every fixture cycle and race with `router.push()`. Instead, the e2e
    browser context injects `window.__API_BASE__` via `add_init_script`,
    and the React components read it before falling back to relative URLs.
    """
    if not _have_next_dev():
        pytest.skip("Next.js not installed in phase-detector/node_modules")

    port = _free_port()
    env = os.environ.copy()
    env["NEXT_TELEMETRY_DISABLED"] = "1"
    env["PORT"] = str(port)

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
        # Wait for the app to be reachable (compile on first request).
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}/pricing", timeout=15) as r:
                    if r.status == 200:
                        break
            except Exception:
                time.sleep(1.0)
        yield {
            "base": f"http://127.0.0.1:{port}",
            "api_base": backend["base"],
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------- Backend smoke (no browser) ----------


def test_backend_checkout_success_smoke(backend):
    """API contract: forced-success returns customer_id + checkout_session_id."""
    req = urllib.request.Request(
        f"{backend['base']}/api/checkout/mock",
        data=json.dumps({
            "tier": "pro",
            "interval": "month",
            "email": "smoke@example.com",
            "force_status": "success",
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200
    assert body["status"] == "success"
    assert body["customer_id"].startswith("mock_cus_")
    assert body["checkout_session_id"].startswith("mock_cs_")
    assert body["amount_usd"] == 19


def test_backend_checkout_decline_smoke(backend):
    """API contract: forced-decline returns status=declined with reason."""
    req = urllib.request.Request(
        f"{backend['base']}/api/checkout/mock",
        data=json.dumps({
            "tier": "team",
            "interval": "year",
            "email": "decline@example.com",
            "force_status": "declined",
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200
    assert body["status"] == "declined"
    assert body["reason"] == "card_declined"


def test_backend_usage_default_free(backend):
    """/api/usage default tier is free, 100-ticker limit."""
    with urllib.request.urlopen(f"{backend['base']}/api/usage", timeout=5) as r:
        body = json.loads(r.read())
    assert body["tier"] == "free"
    assert body["ticker_limit"] == 100


def test_backend_persists_to_jsonl(backend):
    """Successful mock checkout appends to mock_checkouts.jsonl."""
    req = urllib.request.Request(
        f"{backend['base']}/api/checkout/mock",
        data=json.dumps({
            "tier": "pro",
            "interval": "month",
            "email": "jsonl-check@example.com",
            "force_status": "success",
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as _:
        pass
    f = backend["data_dir"] / "mock_checkouts.jsonl"
    assert f.exists()
    content = f.read_text(encoding="utf-8")
    assert "jsonl-check@example.com" in content
    # Most recent line should be valid JSON with success
    last = content.strip().splitlines()[-1]
    row = json.loads(last)
    assert row["status"] == "success"


# ---------- Browser-driven e2e (Next.js dev server) ----------
# These are slower; skip whole class if Next isn't installed.


def _have_playwright_chromium() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa
        return True
    except Exception:
        return False


def _new_context(browser, api_base: str):
    ctx = browser.new_context()
    # Inject API base BEFORE any page JS runs, so React components pick it up
    # via window.__API_BASE__ on first fetch.
    ctx.add_init_script(f"window.__API_BASE__ = {api_base!r};")
    return ctx


@pytest.mark.skipif(not _have_next_dev(), reason="Next.js not installed")
@pytest.mark.skipif(not _have_playwright_chromium(), reason="playwright not installed")
def test_pricing_page_renders_three_tiers(next_dev):
    from playwright.sync_api import sync_playwright

    base = next_dev["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = _new_context(browser, next_dev["api_base"])
        page = ctx.new_page()
        try:
            page.goto(f"{base}/pricing", wait_until="domcontentloaded", timeout=60000)
            # Wait for the three tier cards to render.
            page.wait_for_selector('[data-testid="tier-free"]', timeout=20000)
            page.wait_for_selector('[data-testid="tier-pro"]', timeout=5000)
            page.wait_for_selector('[data-testid="tier-team"]', timeout=5000)
            # Most popular badge is on Pro
            pro_html = page.inner_html('[data-testid="tier-pro"]')
            assert "Most popular" in pro_html
            # CTAs visible
            assert page.locator('[data-testid="cta-free"]').is_visible()
            assert page.locator('[data-testid="cta-pro"]').is_visible()
            assert page.locator('[data-testid="cta-team"]').is_visible()
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _have_next_dev(), reason="Next.js not installed")
@pytest.mark.skipif(not _have_playwright_chromium(), reason="playwright not installed")
def test_pricing_interval_toggle_changes_price(next_dev):
    from playwright.sync_api import sync_playwright

    base = next_dev["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = _new_context(browser, next_dev["api_base"])
        page = ctx.new_page()
        try:
            page.goto(f"{base}/pricing", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector('[data-testid="tier-pro"]', timeout=20000)
            # Wait for client-side hydration so the toggle button has its
            # React onClick handler bound.
            page.wait_for_selector(
                '[data-testid="pricing-table"][data-hydrated="true"]',
                timeout=15000,
            )
            month_text = page.inner_text('[data-testid="tier-pro"]')
            assert "$19" in month_text, f"Pro should show $19/month: {month_text[:200]}"
            # Click annual toggle and wait for price to update.
            # Annual displayed as $/mo equivalent — Pro is $19*10/12 ≈ $16.
            page.click('[data-testid="interval-year"]')
            # Poll the rendered text rather than relying on wait_for_function
            # — Next.js hydration can race with our wait window.
            import time as _t
            deadline = _t.time() + 8
            year_text = ""
            while _t.time() < deadline:
                year_text = page.inner_text('[data-testid="tier-pro"]')
                if "$16" in year_text and "$19" not in year_text.split("年付")[0]:
                    break
                _t.sleep(0.2)
            assert "$16" in year_text, (
                f"Expected $16/月 after annual toggle, got: {year_text[:400]}"
            )
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _have_next_dev(), reason="Next.js not installed")
@pytest.mark.skipif(not _have_playwright_chromium(), reason="playwright not installed")
def test_checkout_mock_success_flow(next_dev):
    """Pro CTA → checkout form → fill → submit → thank-you with mock=1."""
    from playwright.sync_api import sync_playwright

    base = next_dev["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = _new_context(browser, next_dev["api_base"])
        page = ctx.new_page()
        try:
            page.goto(
                f"{base}/checkout/mock?tier=pro&interval=month&force=success",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_selector('[data-testid="checkout-mock-form"]', timeout=20000)
            # Wait until React has hydrated; otherwise the click triggers the
            # form's native GET submission (no onSubmit handler bound yet).
            page.wait_for_selector(
                '[data-testid="checkout-mock-form"][data-hydrated="true"]',
                timeout=15000,
            )
            page.fill('[data-testid="email-input"]', "e2e-success@example.com")
            page.fill('[data-testid="name-input"]', "E2E Success")
            page.fill('[data-testid="card-input"]', "4242")
            page.click('[data-testid="submit-checkout"]')
            # router.push is racing with Next dev HMR; give it generous time
            # and use commit (URL change) rather than 'load'.
            page.wait_for_url("**/thank-you*", timeout=30000, wait_until="commit")
            assert "tier=pro" in page.url
            assert "mock=1" in page.url
            # Success banner should render once the thank-you page hydrates.
            page.wait_for_selector(
                '[data-testid="checkout-success-banner"]',
                timeout=15000,
            )
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _have_next_dev(), reason="Next.js not installed")
@pytest.mark.skipif(not _have_playwright_chromium(), reason="playwright not installed")
def test_checkout_mock_decline_flow(next_dev):
    """Forced-decline returns user to /pricing?error=declined."""
    from playwright.sync_api import sync_playwright

    base = next_dev["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = _new_context(browser, next_dev["api_base"])
        page = ctx.new_page()
        try:
            page.goto(
                f"{base}/checkout/mock?tier=team&interval=year&force=declined",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_selector('[data-testid="checkout-mock-form"]', timeout=20000)
            page.wait_for_selector(
                '[data-testid="checkout-mock-form"][data-hydrated="true"]',
                timeout=15000,
            )
            page.fill('[data-testid="email-input"]', "e2e-decline@example.com")
            page.click('[data-testid="submit-checkout"]')
            page.wait_for_url(
                "**/pricing**error=declined**",
                timeout=30000,
                wait_until="commit",
            )
        finally:
            ctx.close()
            browser.close()
