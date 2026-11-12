"""W10-D — newsletter archive + issue #001 e2e tests.

Verifies the SSR newsletter pages added in W10-D:
  - /newsletter (archive index) lists issue #001 with date + subject + summary
  - /newsletter/001 renders the hero subject line, repeats phase-flip tickers,
    and fires the `newsletter_archive_view` Plausible event on mount

Local server: spins up `next dev` from the phase-detector workspace on a
random port. We don't hit prod and we don't ship a production build — these
are devserver tests, same pattern as other phase-detector e2e tests.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_newsletter_archive.py -v

Note: requires `pnpm install` to have been run inside web/phase-detector once
(for Next + react). If pnpm is missing the test self-skips with a clear msg.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
PHASE_DETECTOR = REPO_ROOT / "web" / "phase-detector"
ISSUE_001_MD = (
    REPO_ROOT
    / "docs"
    / "community"
    / "newsletters"
    / "issue-001-2026-05-15.md"
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http_ok(url: str, timeout: float = 60.0) -> bool:
    import urllib.request
    import urllib.error

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as r:
                if r.status == 200:
                    return True
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError):
            pass
        time.sleep(1.0)
    return False


@pytest.fixture(scope="module")
def next_devserver():
    """Spin up `pnpm dev` on a random port for the phase-detector workspace.

    Skips the test module if pnpm isn't installed or node_modules is missing.
    """
    if not (PHASE_DETECTOR / "package.json").exists():
        pytest.skip(f"phase-detector workspace not found at {PHASE_DETECTOR}")
    if not (PHASE_DETECTOR / "node_modules").exists():
        pytest.skip("phase-detector/node_modules missing — run `pnpm install` first")
    next_bin = PHASE_DETECTOR / "node_modules" / ".bin" / "next"
    if not next_bin.exists():
        pytest.skip(
            f"next binary not found at {next_bin} — run `pnpm install` first"
        )
    if not ISSUE_001_MD.exists():
        pytest.fail(f"issue markdown missing at {ISSUE_001_MD}")

    port = _free_port()
    env = {**os.environ, "NEXT_TELEMETRY_DISABLED": "1"}

    log_dir = REPO_ROOT / "web" / "tests" / "e2e" / "results"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "newsletter_archive_devserver.log"
    log_fh = log_path.open("wb")

    # Invoke `next` directly to avoid pnpm's `--` argv mangling.
    proc = subprocess.Popen(
        [str(next_bin), "dev", "-p", str(port)],
        cwd=str(PHASE_DETECTOR),
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        if not _wait_http_ok(f"{base}/newsletter", timeout=120.0):
            log_fh.flush()
            tail = log_path.read_text(errors="replace")[-2000:]
            pytest.fail(f"next dev didn't come up on {port}; last log:\n{tail}")
        yield {"base": base, "log_path": str(log_path)}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_fh.close()


def test_archive_index_lists_issue_001(next_devserver):
    """Visit /newsletter and assert issue #001 is listed with date + subject."""
    from playwright.sync_api import sync_playwright

    base = next_devserver["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(
                f"{base}/newsletter",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_selector("h1", timeout=10000)
            body = page.text_content("body") or ""
            assert "Structural Signals" in body, "archive page missing brand"
            assert "Issue #001" in body, "issue #001 entry not listed"
            assert "2026-05-15" in body, "publish date not shown"
            assert "block-bootstrap" in body, "summary not shown"
            # Click-through to issue page works.
            link = page.locator("a[href='/newsletter/001']").first
            assert link.count() > 0, "no link to /newsletter/001"
        finally:
            ctx.close()
            browser.close()


def test_issue_001_hero_and_phase_flips(next_devserver):
    """Visit /newsletter/001 and assert hero subject + ≥6 phase-flip tickers
    + ≥1 outbound link to phase.bytedance.city.
    """
    from playwright.sync_api import sync_playwright

    base = next_devserver["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(
                f"{base}/newsletter/001",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            page.wait_for_selector("h1", timeout=10000)
            heading = page.text_content("h1") or ""
            assert "Structural Signals #001" in heading, (
                f"unexpected hero h1: {heading!r}"
            )
            body = page.text_content("body") or ""
            # At least 6 of the 10 known phase-flip tickers should render.
            expected_tickers = [
                "AFRM",
                "AIG",
                "ALL",
                "BIIB",
                "BLDP",
                "BNTX",
                "COIN",
                "COP",
                "CVX",
                "DDOG",
            ]
            found = [t for t in expected_tickers if t in body]
            assert len(found) >= 6, (
                f"expected ≥6 phase-flip tickers, only found {len(found)}: {found}"
            )
            # Methodology spotlight is present.
            assert "block-bootstrap" in body, "methodology spotlight not rendered"
            # Outbound CTA link exists.
            phase_link = page.locator(
                "a[href*='phase.bytedance.city']"
            ).first
            assert phase_link.count() > 0, "missing CTA link to phase.bytedance.city"
        finally:
            ctx.close()
            browser.close()


def test_issue_001_fires_plausible_archive_view(next_devserver):
    """Plausible event `newsletter_archive_view` is invoked on mount.

    We stub window.plausible before navigation and capture invocations.
    """
    from playwright.sync_api import sync_playwright

    base = next_devserver["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            # Install plausible stub *before* page scripts run.
            page.add_init_script(
                """
                window.__plausibleCalls = [];
                window.plausible = function(name, opts) {
                  window.__plausibleCalls.push({ name: name, opts: opts });
                };
                """
            )
            page.goto(
                f"{base}/newsletter/001",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            # Wait for the PageOpenTracker useEffect to fire.
            page.wait_for_function(
                "Array.isArray(window.__plausibleCalls) && "
                "window.__plausibleCalls.some(c => c.name === 'newsletter_archive_view')",
                timeout=10000,
            )
            calls = page.evaluate("window.__plausibleCalls")
            names = [c["name"] for c in calls]
            assert "newsletter_archive_view" in names, (
                f"expected newsletter_archive_view event, got {names}"
            )
            # Verify issue prop captured.
            view_call = next(
                c for c in calls if c["name"] == "newsletter_archive_view"
            )
            props = (view_call.get("opts") or {}).get("props") or {}
            assert props.get("issue") == "001", (
                f"expected issue=001 prop, got {props}"
            )
        finally:
            ctx.close()
            browser.close()


def test_issue_001_outbound_link_click_fires_event(next_devserver):
    """Clicking an outbound link fires `newsletter_link_click`."""
    from playwright.sync_api import sync_playwright

    base = next_devserver["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.add_init_script(
                """
                window.__plausibleCalls = [];
                window.plausible = function(name, opts) {
                  window.__plausibleCalls.push({ name: name, opts: opts });
                };
                """
            )
            page.goto(
                f"{base}/newsletter/001",
                wait_until="domcontentloaded",
                timeout=30000,
            )
            # Wait for the link tracker mount.
            page.wait_for_selector("a[href*='phase.bytedance.city']", timeout=10000)

            # Prevent the actual navigation so we stay on /newsletter/001.
            # Use a bubble-phase listener so the capture-phase NewsletterLinkTracker
            # fires first; otherwise preventDefault in capture phase wouldn't stop
            # the tracker, but ordering of multiple capture listeners is fragile
            # across browsers.
            page.evaluate(
                """
                document.addEventListener('click', function(e) {
                  const t = e.target;
                  const a = (t && t.closest) ? t.closest('a') : null;
                  if (a) { e.preventDefault(); }
                }, false);
                """
            )

            link = page.locator("a[href*='phase.bytedance.city']").first
            link.click()
            page.wait_for_function(
                "window.__plausibleCalls && "
                "window.__plausibleCalls.some(c => c.name === 'newsletter_link_click')",
                timeout=10000,
            )
            calls = page.evaluate("window.__plausibleCalls")
            click_call = next(
                c for c in calls if c["name"] == "newsletter_link_click"
            )
            props = (click_call.get("opts") or {}).get("props") or {}
            assert "phase.bytedance.city" in (props.get("url") or ""), (
                f"unexpected click url prop: {props}"
            )
            assert props.get("issue") == "001"
        finally:
            ctx.close()
            browser.close()
