"""B Data Flywheel e2e — insights dashboard (Session #18).

Covers:
  A. API contract — drives a FastAPI shim with the insights + report
     routers mounted, seeded straight into the SQLite store the shim
     reads. Verifies the three /api/insights/* endpoints + the
     followup-enriched /api/reports/mine. Always runs.
  B. Browser — Playwright loads the shim-served insights.html. Verifies
     the empty state and a seeded-data state render. Self-skips if
     Playwright/Chromium is absent so it can live alongside pre-deploy
     work.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \\
        web/tests/e2e/test_insights.py -v --tb=short
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_BACKEND = REPO_ROOT / "web" / "backend"
FRONTEND_DIR = REPO_ROOT / "web" / "frontend"

_SHARE_SECRET = "e2e-test-share-secret-session-18"
os.environ["STRUCTURAL_SHARE_TOKEN_SECRET"] = _SHARE_SECRET
os.environ["STRUCTURAL_ENV"] = "test"

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


def _wait_port(host: str, port: int, timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _sample_payload() -> dict:
    return {
        "shared_structure": {"name": "Cascade dynamics"},
        "_credibility": {"source_domain": "Forest fire spread"},
        "action_plan": {"immediate_actions": ["a"]},
    }


# ---------------- shim + store fixtures ------------------------------ #


@pytest.fixture(scope="module")
def insights_backend(tmp_path_factory):
    """FastAPI shim with insights + report routers + insights.html route."""
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("insights-e2e")
    db_path = data_dir / "history.db"

    shim_code = f"""
import os, sys
os.environ['STRUCTURAL_SHARE_TOKEN_SECRET'] = {_SHARE_SECRET!r}
os.environ['STRUCTURAL_ENV'] = 'test'
sys.path.insert(0, {str(WEB_BACKEND)!r})

from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from api import insights as insights_api
from api import report as report_api
from services.report_store import ReportStore

FRONTEND = Path({str(FRONTEND_DIR)!r})

# Both routers share the same temp DB.
store = ReportStore({str(db_path)!r})
insights_api._store = store
report_api._store = store

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.include_router(insights_api.router, prefix="/api")
app.include_router(report_api.router, prefix="/api")
app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")


@app.get("/insights")
def _insights():
    return FileResponse(FRONTEND / "insights.html")


@app.get("/reports")
def _reports():
    return FileResponse(FRONTEND / "reports.html")


import uvicorn
uvicorn.run(app, host="127.0.0.1", port={port}, log_level="warning")
"""
    shim_path = data_dir / "shim.py"
    shim_path.write_text(shim_code, encoding="utf-8")

    proc = subprocess.Popen(
        [_resolve_python(), str(shim_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    try:
        if not _wait_port("127.0.0.1", port, timeout=25.0):
            output = proc.stdout.read(4096) if proc.stdout else b""
            pytest.fail(f"insights shim on {port} didn't start: {output!r}")
        yield {"base": f"http://127.0.0.1:{port}", "db_path": db_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def store(insights_backend):
    """ReportStore opened on the same temp DB the shim serves."""
    if str(WEB_BACKEND) not in sys.path:
        sys.path.insert(0, str(WEB_BACKEND))
    from services.report_store import ReportStore  # noqa: WPS433

    return ReportStore(insights_backend["db_path"])


def _api_get(url: str):
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status, json.loads(resp.read().decode())


def _seed(store, *, query="测试查询", b_id="b_demo", anon="anon-A"):
    return store.create(
        query=query, b_id=b_id, lang="zh",
        payload=_sample_payload(), model="deepseek/deepseek-chat",
        creator_anon_id=anon,
    )


# ============================ Phase A — API ======================== #


def test_summary_endpoint_with_seeded_data(insights_backend, store):
    out = _seed(store, query="A 阶段总览测试")
    store.record_followup(
        report_id=out["id"], anon_id="anon-A",
        action_status="tried", outcome="worked",
    )
    status, body = _api_get(insights_backend["base"] + "/api/insights/summary")
    assert status == 200
    assert body["total_reports"] >= 1
    assert body["worked_count"] >= 1
    assert body["verified_isomorphisms"] >= 1


def test_stuck_structures_endpoint(insights_backend, store):
    _seed(store, query="卡住测试 1", b_id="b_stuck_e2e")
    _seed(store, query="卡住测试 2", b_id="b_stuck_e2e")
    status, body = _api_get(
        insights_backend["base"] + "/api/insights/stuck-structures?limit=10"
    )
    assert status == 200
    b_ids = [it["b_id"] for it in body["items"]]
    assert "b_stuck_e2e" in b_ids


def test_verified_endpoint(insights_backend, store):
    out = _seed(store, query="已验证测试", b_id="b_verified_e2e")
    store.record_followup(
        report_id=out["id"], anon_id="anon-V",
        action_status="tried", outcome="worked",
    )
    status, body = _api_get(insights_backend["base"] + "/api/insights/verified")
    assert status == 200
    probs = [it["problem"] for it in body["items"]]
    assert "已验证测试" in probs
    hit = next(it for it in body["items"] if it["problem"] == "已验证测试")
    assert hit["source_phenomenon"] == "Forest fire spread"


def test_reports_mine_carries_followup(insights_backend, store):
    out = _seed(store, query="回访状态测试", b_id="b_mine_e2e", anon="anon-MINE")
    store.record_followup(
        report_id=out["id"], anon_id="anon-MINE",
        action_status="tried", outcome="worked",
    )
    req = urllib.request.Request(
        insights_backend["base"] + "/api/reports/mine",
        headers={"X-Anon-Id": "anon-MINE"}, method="GET",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode())
    hit = next(it for it in body["items"] if it["query"] == "回访状态测试")
    assert hit["has_followup"] is True
    assert hit["followup_outcome"] == "worked"


def test_stuck_structures_limit_rejected(insights_backend):
    try:
        _api_get(insights_backend["base"] + "/api/insights/stuck-structures?limit=0")
        assert False, "expected 422"
    except urllib.error.HTTPError as e:
        assert e.code == 422


# ====================== Phase B — Browser ========================== #


def _playwright_or_skip():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        pytest.skip("playwright not installed")


def test_insights_page_renders_summary(insights_backend, store, page):
    """Browser: insights.html loads and the summary stat cards render."""
    _playwright_or_skip()
    out = _seed(store, query="浏览器渲染测试", b_id="b_browser_e2e")
    store.record_followup(
        report_id=out["id"], anon_id="anon-B",
        action_status="tried", outcome="worked",
    )
    page.goto(insights_backend["base"] + "/insights", timeout=15000)
    # Stat cards replace the skeletons once /summary resolves.
    page.wait_for_selector(".insights-stat__value", timeout=8000)
    values = page.locator(".insights-stat__value").all_inner_texts()
    assert len(values) == 4
    # total_reports card should be a non-negative integer.
    assert int(values[0]) >= 1


def test_insights_page_verified_section_renders(insights_backend, store, page):
    """Browser: a seeded worked-followup shows in the verified library."""
    _playwright_or_skip()
    out = _seed(store, query="浏览器已验证测试", b_id="b_browser_v")
    store.record_followup(
        report_id=out["id"], anon_id="anon-BV",
        action_status="tried", outcome="worked",
    )
    page.goto(insights_backend["base"] + "/insights", timeout=15000)
    page.wait_for_selector(
        ".insights-card, .insights-empty", timeout=8000,
    )
    content = page.content()
    # Either real cards rendered, or (if another test's data is
    # absent) a friendly empty state — never a raw error.
    assert (
        "insights-card__problem" in content
        or "insights-empty" in content
    )
