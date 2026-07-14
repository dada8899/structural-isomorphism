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
insights_api._canonical_lookup = lambda b_id: {{
    "id": b_id,
    "name": "Canonical " + b_id,
    "domain": "Canonical Domain",
}} if b_id else None
report_api._store = store

app = FastAPI()
app.middleware("http")(insights_api.no_store_insights_responses)
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
    # Keep combined pytest runs deterministic when another E2E module sets a
    # different test-only share secret during collection.
    os.environ["STRUCTURAL_SHARE_TOKEN_SECRET"] = _SHARE_SECRET
    return store.create(
        query=query, b_id=b_id, lang="zh",
        payload=_sample_payload(), model="deepseek/deepseek-chat",
        creator_anon_id=anon,
    )


# ============================ Phase A — API ======================== #


def _seed_claimed_batch(store, *, start, stop, b_id):
    for i in range(start, stop):
        anon = f"account-device-{b_id}-{i}"
        out = _seed(store, query=f"private {i}", b_id=b_id, anon=anon)
        store.record_followup(
            report_id=out["id"], anon_id=anon,
            action_status="tried", outcome="worked",
            publish_to_insights=True,
        )
        store.claim_by_anon(anon, f"account-{b_id}-{i}")


def _snapshot(base):
    return {
        "summary": _api_get(base + "/api/insights/summary")[1],
        "stuck": _api_get(base + "/api/insights/stuck-structures")[1],
        "verified": _api_get(base + "/api/insights/verified")[1],
    }


def test_all_public_endpoints_start_in_stable_paused_state(insights_backend):
    assert _snapshot(insights_backend["base"]) == {
        "summary": {"status": "public_aggregation_paused"},
        "stuck": {"status": "public_aggregation_paused"},
        "verified": {"status": "public_aggregation_paused"},
    }


def test_four_to_five_to_six_never_changes_public_response(
    insights_backend, store,
):
    before = _snapshot(insights_backend["base"])
    _seed_claimed_batch(store, start=0, stop=4, b_id="threshold-five")
    at_four = _snapshot(insights_backend["base"])
    _seed_claimed_batch(store, start=4, stop=5, b_id="threshold-five")
    at_five = _snapshot(insights_backend["base"])
    _seed_claimed_batch(store, start=5, stop=6, b_id="threshold-five")
    at_six = _snapshot(insights_backend["base"])
    assert before == at_four == at_five == at_six


def test_nineteen_to_twenty_never_changes_public_response(
    insights_backend, store,
):
    _seed_claimed_batch(store, start=0, stop=19, b_id="threshold-twenty")
    at_nineteen = _snapshot(insights_backend["base"])
    _seed_claimed_batch(store, start=19, stop=20, b_id="threshold-twenty")
    at_twenty = _snapshot(insights_backend["base"])
    assert at_nineteen == at_twenty


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


def test_exact_404_and_validation_errors_are_no_store(insights_backend):
    for path, expected in (
        ("/api/insights", 404),
        ("/api/insights/not-a-route", 404),
        ("/api/insights/stuck-structures?limit=0", 422),
    ):
        try:
            _api_get(insights_backend["base"] + path)
            assert False, f"expected {expected}"
        except urllib.error.HTTPError as error:
            assert error.code == expected
            assert error.headers.get("Cache-Control") == "no-store"
            assert error.headers.get("Pragma") == "no-cache"


# ====================== Phase B — Browser ========================== #


def _playwright_or_skip():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except Exception:
        pytest.skip("playwright not installed")


def test_insights_page_renders_paused_state_after_many_records(
    insights_backend, store, page,
):
    _playwright_or_skip()
    _seed_claimed_batch(store, start=0, stop=21, b_id="browser-paused")
    page.goto(insights_backend["base"] + "/insights", timeout=15000)
    page.wait_for_selector(".insights-empty", timeout=8000)
    content = page.locator("main").inner_text()
    assert "公开结果聚合已暂停" in content
    assert "排行已关闭" in content
    assert "公开用户结果已关闭" in content


def test_insights_page_never_renders_private_or_aggregate_cards(
    insights_backend, store, page,
):
    _playwright_or_skip()
    for i in range(6):
        anon = f"browser-private-{i}"
        out = _seed(
            store, query=f"victim-{i}@example.com",
            b_id="private-browser-id", anon=anon,
        )
        store.record_followup(
            report_id=out["id"], anon_id=anon, action_status="tried",
            outcome="worked", publish_to_insights=True,
        )
    page.goto(insights_backend["base"] + "/insights", timeout=15000)
    page.wait_for_selector(".insights-empty", timeout=8000)
    content = page.content()
    assert "victim-" not in content
    assert "private-browser-id" not in content
    assert page.locator(".insights-card:not(.insights-card--skeleton)").count() == 0
    assert page.locator(".insights-row:not(.insights-row--skeleton)").count() == 0
