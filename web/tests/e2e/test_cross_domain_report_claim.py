"""Real browser: beta anonymous report -> Phase SSO -> cross-device report."""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
PHASE = ROOT / "web" / "phase-detector"
BACKEND = ROOT / "web" / "backend"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_url(url, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status < 500:
                    return
        except Exception:
            time.sleep(0.2)
    pytest.fail(f"service not ready: {url}")


@pytest.fixture(scope="module")
def sso_stack(tmp_path_factory):
    if not (PHASE / "node_modules/.bin/next").exists():
        pytest.skip("Next dependencies unavailable")
    beta_port, phase_web_port, phase_api_port = free_port(), free_port(), free_port()
    beta_origin = f"http://127.0.0.1:{beta_port}"
    phase_origin = f"http://127.0.0.1:{phase_web_port}"
    phase_api_origin = f"http://127.0.0.1:{phase_api_port}"
    root = tmp_path_factory.mktemp("cross-domain-sso")
    secret = "real-browser-shared-sso-secret-at-least-32-characters"

    beta_shim = root / "beta.py"
    beta_shim.write_text("\n".join([
        "import os,sys", f"sys.path.insert(0,{str(BACKEND)!r})",
        f"os.environ['AUTH_DATA_DIR']={str(root / 'beta-auth')!r}",
        f"os.environ['STRUCTURAL_SSO_DATA_DIR']={str(root / 'shared-sso')!r}",
        f"os.environ['STRUCTURAL_SSO_SECRET']={secret!r}",
        f"os.environ['STRUCTURAL_SSO_PHASE_ORIGIN']={phase_origin!r}",
        f"os.environ['STRUCTURAL_SSO_BETA_ORIGIN']={beta_origin!r}",
        "from pathlib import Path", "from fastapi import FastAPI",
        "from fastapi.responses import FileResponse", "from fastapi.staticfiles import StaticFiles",
        "from api.sso import router as sso", "import api.report_account as account_module",
        "import api.report as report_module", "from services.report_store import ReportStore",
        f"TEST_STORE=ReportStore(Path({str(root / 'history.db')!r}))",
        "account_module._store=TEST_STORE", "report_module._store=TEST_STORE",
        f"FRONT=Path({str(ROOT / 'web/frontend')!r})", "app=FastAPI()",
        "app.include_router(sso,prefix='/api')", "app.include_router(account_module.router,prefix='/api')",
        "app.include_router(report_module.router,prefix='/api')",
        "app.mount('/assets',StaticFiles(directory=FRONT/'assets'),name='assets')",
        "@app.on_event('startup')", "async def seed():",
        " TEST_STORE.create(query='匿名研究报告',b_id='b1',lang='zh',payload={},model='m',creator_anon_id='anon-browser-proof')",
        "@app.get('/reports')", "async def reports_page(): return FileResponse(FRONT/'reports.html')",
        "@app.get('/auth/callback')", "async def callback(): return FileResponse(FRONT/'auth-callback.html')",
        "@app.get('/report/share/{token}')", "async def report(token:str): return FileResponse(FRONT/'report.html')",
        "import uvicorn", f"uvicorn.run(app,host='127.0.0.1',port={beta_port},log_level='warning')",
    ]), encoding="utf-8")
    phase_shim = root / "phase.py"
    phase_shim.write_text("\n".join([
        "import os,sys", f"sys.path.insert(0,{str(BACKEND)!r})",
        "os.environ['AUTH_ENABLED']='true'", "os.environ['AUTH_DEV_MODE']='true'",
        f"os.environ['AUTH_LINK_BASE_URL']={phase_origin!r}",
        f"os.environ['AUTH_DATA_DIR']={str(root / 'phase-auth')!r}",
        f"os.environ['STRUCTURAL_SSO_DATA_DIR']={str(root / 'shared-sso')!r}",
        "os.environ['JWT_SECRET']='real-browser-auth-secret-at-least-32-characters'",
        f"os.environ['STRUCTURAL_SSO_SECRET']={secret!r}",
        f"os.environ['STRUCTURAL_SSO_PHASE_ORIGIN']={phase_origin!r}",
        f"os.environ['STRUCTURAL_SSO_BETA_ORIGIN']={beta_origin!r}",
        "from fastapi import FastAPI", "from fastapi.middleware.cors import CORSMiddleware",
        "from api.auth import router as auth", "from api.sso import router as sso",
        "app=FastAPI()", f"app.add_middleware(CORSMiddleware,allow_origins=[{phase_origin!r}],allow_credentials=True,allow_methods=['*'],allow_headers=['*'])",
        "app.include_router(auth,prefix='/api')", "app.include_router(sso,prefix='/api')",
        "import uvicorn", f"uvicorn.run(app,host='127.0.0.1',port={phase_api_port},log_level='warning')",
    ]), encoding="utf-8")
    env = os.environ.copy()
    env.update({
        "NEXT_TELEMETRY_DISABLED": "1", "NEXT_PUBLIC_AUTH_ENABLED": "true",
        "NEXT_PUBLIC_AUTH_DEV_MODE": "true", "NEXT_PUBLIC_API_BASE": phase_api_origin,
        "NEXT_PUBLIC_STRUCTURAL_BETA_ORIGIN": beta_origin, "NEXT_PUBLIC_USE_MOCK": "true",
    })
    processes = [
        subprocess.Popen([str(PYTHON), str(beta_shim)], cwd=ROOT),
        subprocess.Popen([str(PYTHON), str(phase_shim)], cwd=ROOT),
        subprocess.Popen([str(PHASE / "node_modules/.bin/next"), "dev", "--port", str(phase_web_port)], cwd=PHASE, env=env),
    ]
    try:
        wait_url(beta_origin + "/reports")
        wait_url(phase_api_origin + "/docs")
        wait_url(phase_origin + "/auth/login")
        yield {"beta": beta_origin, "phase": phase_origin, "phase_api": phase_api_origin}
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def test_anonymous_report_claim_and_cross_device_restore(browser, sso_stack):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    page.goto(sso_stack["phase"] + "/auth/login")
    page.get_by_test_id("auth-login-email").fill("cross-device@example.com")
    page.get_by_test_id("auth-login-submit").click()
    link = page.get_by_test_id("auth-login-dev-link")
    link.wait_for()
    page.goto(link.get_attribute("href"))
    page.wait_for_url("**/me")

    page.goto(sso_stack["beta"] + "/reports")
    page.evaluate("localStorage.setItem('anonId','anon-browser-proof')")
    page.reload()
    diagnostic = page.evaluate("""async () => {
      const account = await fetch('/api/me/reports', {credentials:'include'});
      const legacy = await fetch('/api/reports/mine', {headers:{'X-Anon-Id':'anon-browser-proof'}});
      return {anon: localStorage.getItem('anonId'), account: account.status,
              legacy: legacy.status, body: await legacy.text()};
    }""")
    assert diagnostic["anon"] == "anon-browser-proof"
    assert diagnostic["account"] == 401
    assert diagnostic["legacy"] == 200, diagnostic
    assert "匿名研究报告" in diagnostic["body"], diagnostic
    page.get_by_text("匿名研究报告", exact=True).wait_for()
    page.get_by_text("登录并跨设备同步", exact=True).click()
    page.wait_for_url("**/auth/connect?**")
    page.get_by_test_id("sso-connect-submit").click()
    page.wait_for_url(sso_stack["beta"] + "/reports")
    page.get_by_text("这些报告已与你的 Structural 账户关联，可在其他已登录设备继续。", exact=True).wait_for()
    page.get_by_text("匿名研究报告", exact=True).wait_for()
    beta_cookie = next(cookie for cookie in context.cookies() if cookie["name"] == "structural_beta_session")

    other = browser.new_context(viewport={"width": 430, "height": 932})
    other.add_cookies([beta_cookie])
    other_page = other.new_page()
    other_page.goto(sso_stack["beta"] + "/reports")
    other_page.get_by_text("匿名研究报告", exact=True).wait_for()
    href = other_page.get_by_text("匿名研究报告", exact=True).locator("xpath=ancestor::a").get_attribute("href")
    assert href.startswith("/report/share/")
    other.close()
    context.close()
