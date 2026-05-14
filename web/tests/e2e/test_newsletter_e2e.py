"""Session #9 W4-C — Newsletter form e2e test (local server, no prod pollution).

W3-A flow 4 observed: "Newsletter form caught at '提交中…' within 15s" — the
submit roundtrip fired but the success/error final state wasn't visible. Root
cause analysis (session #9 W4-C):

  - newsletter.js had no client-side request timeout. If the prod
    /api/newsletter/subscribe response hangs (nginx slow / cold-start / network
    blip), the UI stays stuck on "提交中…" indefinitely — exactly what W3-A
    observed at the 15s test budget.
  - The fix adds AbortController with 10s timeout, plus stronger CSS pill
    styling on success/dup/err so the state change is visually unmistakable.

This e2e test verifies the success / duplicate / error paths end-to-end against
a minimal local FastAPI app mounted with just the real newsletter router. No
prod calls, no real email pollution.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_newsletter_e2e.py -v
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_BACKEND = REPO_ROOT / "web" / "backend"
WEB_FRONTEND = REPO_ROOT / "web" / "frontend"

# Resolve a usable Python interpreter for the local backend subprocess.
# Tests may run from a git worktree without its own .venv, so we fall back
# to the main repo's .venv (the project's known good install) and finally
# to sys.executable.
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


def _wait_port(host: str, port: int, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


@pytest.fixture(scope="module")
def local_backend(tmp_path_factory):
    """Spin up a minimal FastAPI app on a random port with just newsletter
    router mounted. Data file lives in a temp dir so we can assert disk state
    without polluting anything real."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("nl-data")

    # We patch the data-file location via env var consumed by a small shim
    # script. Shim writes its own data file in tmp.
    shim_code = f"""
import sys
sys.path.insert(0, {str(WEB_BACKEND)!r})
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from api import newsletter as nl_mod
from pathlib import Path

# Override data file to tmp dir.
def _patched_data_file():
    return Path({str(data_dir)!r}) / "subs.jsonl"
nl_mod._data_file = _patched_data_file

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)
app.include_router(nl_mod.router, prefix="/api")
# Serve the frontend statically from the same origin (mirrors prod behaviour
# where nginx proxies /api/* to backend and serves /* from disk).
app.mount("/", StaticFiles(directory={str(WEB_FRONTEND)!r}, html=True), name="frontend")

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
            f"backend on {port} didn't start: {proc.stdout.read(2048) if proc.stdout else ''!r}"
        yield {"base": f"http://127.0.0.1:{port}", "data_dir": data_dir}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_newsletter_endpoint_smoke(local_backend):
    """Backend route is mounted and responds correctly before we drive the UI."""
    import urllib.request
    base = local_backend["base"]
    req = urllib.request.Request(
        f"{base}/api/newsletter/subscribe",
        data=json.dumps({"email": "smoke@example.com", "source": "test"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        body = json.loads(r.read())
    assert r.status == 200
    assert body["ok"] is True
    assert body["created"] is True
    assert body["email"] == "smoke@example.com"


def test_newsletter_success_state_visible(local_backend):
    """Drive a real browser to start-here.html, submit, assert success class
    appears on the status element within 10s (well under W3-A's failed 15s)."""
    from playwright.sync_api import sync_playwright

    base = local_backend["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(f"{base}/start-here.html", wait_until="domcontentloaded", timeout=10000)
            # Form mounts after JS runs — wait for input element.
            page.wait_for_selector("#newsletter-start-here .newsletter-input", timeout=5000)
            page.fill(
                "#newsletter-start-here .newsletter-input",
                "e2e-success+w4c@example.com",
            )
            page.click("#newsletter-start-here .newsletter-button")
            # The key assertion W4-C is designed to make pass: success state
            # visible inside the test's wait budget. Old code (no timeout)
            # could leave UI stuck on "提交中…" if backend slow. With local
            # backend this completes <500ms typically.
            page.wait_for_selector(
                "#newsletter-start-here .newsletter-status.is-ok",
                timeout=10000,
            )
            status_text = page.text_content(
                "#newsletter-start-here .newsletter-status"
            )
            assert status_text and "已订阅" in status_text, (
                f"unexpected success text: {status_text!r}"
            )
            # Input should be cleared on success.
            input_val = page.input_value(
                "#newsletter-start-here .newsletter-input"
            )
            assert input_val == "", f"expected empty input, got {input_val!r}"
        finally:
            ctx.close()
            browser.close()


def test_newsletter_duplicate_state_visible(local_backend):
    """Submit same email twice — second time should show .is-dup state, not
    stuck on '提交中…'."""
    from playwright.sync_api import sync_playwright

    base = local_backend["base"]
    email = "e2e-dup+w4c@example.com"

    # First subscribe via API to seed the dedupe scan.
    import urllib.request
    req = urllib.request.Request(
        f"{base}/api/newsletter/subscribe",
        data=json.dumps({"email": email, "source": "test"}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        first = json.loads(r.read())
    assert first["created"] is True, f"seed failed: {first}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(f"{base}/start-here.html", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#newsletter-start-here .newsletter-input", timeout=5000)
            page.fill("#newsletter-start-here .newsletter-input", email)
            page.click("#newsletter-start-here .newsletter-button")
            page.wait_for_selector(
                "#newsletter-start-here .newsletter-status.is-dup",
                timeout=10000,
            )
            text = page.text_content("#newsletter-start-here .newsletter-status")
            assert text and "已经订阅" in text, f"unexpected dup text: {text!r}"
        finally:
            ctx.close()
            browser.close()


def test_newsletter_timeout_falls_back_to_err(local_backend):
    """If backend hangs, client-side AbortController should kick in and show
    the error state — NOT leave UI stuck on '提交中…' (W4-C root fix)."""
    from playwright.sync_api import sync_playwright

    base = local_backend["base"]
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(f"{base}/start-here.html", wait_until="domcontentloaded", timeout=10000)
            page.wait_for_selector("#newsletter-start-here .newsletter-input", timeout=5000)

            # Override fetch to never respond, simulating prod nginx hang.
            page.evaluate(
                """
                (function() {
                  const originalFetch = window.fetch;
                  window.fetch = function(url, opts) {
                    if (typeof url === 'string' && url.indexOf('/newsletter/subscribe') >= 0) {
                      return new Promise(function(resolve, reject) {
                        if (opts && opts.signal) {
                          opts.signal.addEventListener('abort', function() {
                            const err = new Error('aborted');
                            err.name = 'AbortError';
                            reject(err);
                          });
                        }
                        // never resolve otherwise
                      });
                    }
                    return originalFetch.apply(this, arguments);
                  };
                })();
                """
            )

            # Patch REQUEST_TIMEOUT_MS isn't exposed, but the constant is 10s.
            # We'd rather not wait 10s — just verify the contract: UI moves
            # off "提交中…" within the budget. To keep test under 15s, we
            # accept the 10s wait once.
            page.fill(
                "#newsletter-start-here .newsletter-input",
                "e2e-timeout+w4c@example.com",
            )
            page.click("#newsletter-start-here .newsletter-button")
            # Verify "提交中…" appears first.
            page.wait_for_function(
                "document.querySelector('#newsletter-start-here .newsletter-status')"
                ".textContent.indexOf('提交中') >= 0",
                timeout=3000,
            )
            # Then after timeout (~10s), should switch to is-err.
            page.wait_for_selector(
                "#newsletter-start-here .newsletter-status.is-err",
                timeout=13000,
            )
            text = page.text_content("#newsletter-start-here .newsletter-status")
            assert text and ("超时" in text or "网络错误" in text), (
                f"unexpected timeout text: {text!r}"
            )
        finally:
            ctx.close()
            browser.close()
