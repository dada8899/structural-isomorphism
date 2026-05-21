"""M1.4 PR ***REMOVED***5 e2e — persisted report share + feedback flow (session ***REMOVED***17).

Covers the 5 acceptance scenarios from
`docs/sessions/M1.4-frontend-integration-guide.md` §5:

  1. Persist flow      — a persisted report is reachable via its share URL.
  2. Cross-browser     — the share URL works from a fresh (incognito) context
                         with no anon cookie.
  3. Feedback flow     — a 👍 vote is recorded and the counter reflects it.
  4. Vote flip         — 👍 then 👎 by the same voter on the same section
                         leaves total_up=0, total_down=1 (idempotent upsert).
  5. Overall dedup     — an anonymous (no X-Anon-Id) overall 👍 cast twice
                         still counts once (voter_anon='anon', section='').

Two phases, same as test_favorites.py:

  A. API contract — drives a local FastAPI shim with the report router
     mounted; reports are seeded straight into the SQLite store the shim
     reads. Always runs.
  B. Browser — Playwright loads the shim-served report.html at
     /report/share/<token>. Self-skips if Playwright/Chromium is absent so
     it can live alongside pre-deploy work.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \\
        web/tests/e2e/test_report_share.py -v --tb=short
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

***REMOVED*** Fixed secret shared by the test process (seeding) and the shim (verifying)
***REMOVED*** so HMAC share tokens match across both. Set before importing report_store.
_SHARE_SECRET = "e2e-test-share-secret-session-17"
os.environ["STRUCTURAL_SHARE_TOKEN_SECRET"] = _SHARE_SECRET
os.environ["STRUCTURAL_ENV"] = "test"

_LOCAL_VENV = REPO_ROOT / ".venv" / "bin" / "python"
_MAIN_VENV = Path.home() / "Projects" / "structural-isomorphism" / ".venv" / "bin" / "python"

***REMOVED*** The 9 canonical section keys (mirror of report.py _ALLOWED_SECTIONS).
SECTION_KEYS = [
    "shared_structure",
    "your_problem_breakdown",
    "target_domain_intro",
    "structural_mapping",
    "borrowable_insights",
    "how_to_combine",
    "research_directions",
    "risks_and_limits",
    "action_plan",
]


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


def _wait_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def _sample_payload() -> dict:
    """A full 9-section payload — enough for the browser to render 9 cards."""
    return {
        key: f"Sample content for {key}. 这是 {key} 小节的占位文本。"
        for key in SECTION_KEYS
    }


***REMOVED*** ---------------- shim + store fixtures ------------------------------ ***REMOVED***


@pytest.fixture(scope="module")
def report_backend(tmp_path_factory):
    """Spin up a FastAPI shim with the report router + report.html routes.

    The shim reads the same SQLite file the test process seeds into, so
    tests can `seed_report(...)` then exercise the HTTP API / browser.
    """
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("report-e2e")
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
from api import report as report_api
from services.report_store import ReportStore

try:
    from errors import install_problem_handlers
except Exception:
    install_problem_handlers = None

FRONTEND = Path({str(FRONTEND_DIR)!r})

***REMOVED*** Point the router's lazily-initialised store at our temp DB.
report_api._store = ReportStore({str(db_path)!r})

app = FastAPI()
if install_problem_handlers:
    install_problem_handlers(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
)
app.include_router(report_api.router, prefix="/api")
app.mount("/assets", StaticFiles(directory=str(FRONTEND / "assets")), name="assets")


@app.get("/report/share/{{token}}")
def _share(token: str):
    return FileResponse(FRONTEND / "report.html")


@app.get("/report/{{report_id}}")
def _byid(report_id: str):
    return FileResponse(FRONTEND / "report.html")


@app.get("/reports")
def _my_reports():
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
        if not _wait_port("127.0.0.1", port, timeout=20.0):
            output = proc.stdout.read(4096) if proc.stdout else b""
            pytest.fail(f"report shim on {port} didn't start: {output!r}")
        yield {"base": f"http://127.0.0.1:{port}", "db_path": db_path}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture
def seed_report(report_backend):
    """Return a callable that inserts a report row and returns its dict.

    report_store.py imports only stdlib, so we can open the same SQLite
    file from the test process without dragging in the FastAPI app.
    """
    if str(WEB_BACKEND) not in sys.path:
        sys.path.insert(0, str(WEB_BACKEND))
    from services.report_store import ReportStore  ***REMOVED*** noqa: WPS433

    store = ReportStore(report_backend["db_path"])

    def _seed(*, query="测试查询", b_id="b_demo", lang="zh",
              creator_anon_id=None, is_partial=False, payload=None):
        return store.create(
            query=query,
            b_id=b_id,
            lang=lang,
            payload=payload or _sample_payload(),
            model="deepseek/deepseek-chat",
            creator_anon_id=creator_anon_id,
            is_partial=is_partial,
        )

    return _seed


def _api(method: str, url: str, headers: dict | None = None, body=None):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={**(headers or {}), "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload else None)
    except urllib.error.HTTPError as e:
        payload = e.read()
        try:
            return e.code, json.loads(payload) if payload else None
        except json.JSONDecodeError:
            return e.code, {"_raw": payload.decode(errors="replace")}


***REMOVED*** =================== Phase A — API contract ========================= ***REMOVED***


def test_persist_flow_share_token_round_trip(report_backend, seed_report):
    """Scenario 1 — a persisted report is readable via its share token."""
    rep = seed_report(query="为什么蚁群能找到最短路径")
    base = report_backend["base"]
    status, body = _api("GET", f"{base}/api/report/share/{rep['share_token']}")
    assert status == 200, body
    assert body["id"] == rep["id"]
    assert body["query"] == "为什么蚁群能找到最短路径"
    ***REMOVED*** payload comes back as a parsed dict with all 9 sections.
    assert isinstance(body["payload"], dict)
    assert set(body["payload"]) == set(SECTION_KEYS)


def test_credibility_lifted_from_payload(report_backend, seed_report):
    """V4 — credibility persisted inside payload (_credibility) is lifted to
    a top-level field on read, and the payload comes back section-only."""
    cred = {"kb_source": True, "similarity": 0.84, "has_verified_pairs": True,
            "verified_pair_count": 3}
    payload = {**_sample_payload(), "_credibility": cred}
    rep = seed_report(query="V4 徽章测试", payload=payload)
    base = report_backend["base"]
    status, body = _api("GET", f"{base}/api/report/share/{rep['share_token']}")
    assert status == 200, body
    assert body["credibility"] == cred
    ***REMOVED*** _credibility must not leak into the section payload.
    assert "_credibility" not in body["payload"]
    assert set(body["payload"]) == set(SECTION_KEYS)


def test_share_invalid_token_returns_404(report_backend):
    base = report_backend["base"]
    ***REMOVED*** Well-formed (32 hex) but unsigned token.
    status, _ = _api("GET", f"{base}/api/report/share/{'a' * 32}")
    assert status == 404
    ***REMOVED*** Malformed length — also 404, never 500.
    status2, _ = _api("GET", f"{base}/api/report/share/tooshort")
    assert status2 == 404


def test_report_by_id_soft_owner_check(report_backend, seed_report):
    """A report with a creator_anon_id is 404 to the wrong anon-id."""
    rep = seed_report(creator_anon_id="owner-anon-1")
    base = report_backend["base"]
    s_wrong, _ = _api(
        "GET", f"{base}/api/report/{rep['id']}",
        headers={"X-Anon-Id": "someone-else"},
    )
    assert s_wrong == 404
    s_ok, body = _api(
        "GET", f"{base}/api/report/{rep['id']}",
        headers={"X-Anon-Id": "owner-anon-1"},
    )
    assert s_ok == 200
    assert body["id"] == rep["id"]


def test_feedback_flow_increments_count(report_backend, seed_report):
    """Scenario 3 — a section 👍 is recorded and counted."""
    rep = seed_report()
    base = report_backend["base"]
    status, body = _api(
        "POST", f"{base}/api/report/{rep['id']}/feedback",
        headers={"X-Anon-Id": "voter-A"},
        body={"section": "borrowable_insights", "vote": 1},
    )
    assert status == 200, body
    assert body == {"ok": True, "total_up": 1, "total_down": 0}


def test_vote_flip_overwrites_not_double_counts(report_backend, seed_report):
    """Scenario 4 — 👍 then 👎 by the same voter+section flips, not stacks."""
    rep = seed_report()
    base = report_backend["base"]
    url = f"{base}/api/report/{rep['id']}/feedback"
    hdr = {"X-Anon-Id": "voter-flip"}

    s1, b1 = _api("POST", url, headers=hdr, body={"section": "action_plan", "vote": 1})
    assert s1 == 200 and b1["total_up"] == 1 and b1["total_down"] == 0

    s2, b2 = _api("POST", url, headers=hdr, body={"section": "action_plan", "vote": -1})
    assert s2 == 200, b2
    assert b2["total_up"] == 0, "the earlier 👍 should be overwritten"
    assert b2["total_down"] == 1


def test_overall_vote_dedup_for_anonymous(report_backend, seed_report):
    """Scenario 5 — anon overall 👍 cast twice still counts once.

    No X-Anon-Id header => voter_anon collapses to 'anon'; section omitted
    => '' in the store; UNIQUE(report_id,'anon','') makes the 2nd an upsert.
    """
    rep = seed_report()
    base = report_backend["base"]
    url = f"{base}/api/report/{rep['id']}/feedback"

    s1, b1 = _api("POST", url, body={"vote": 1})
    assert s1 == 200 and b1["total_up"] == 1

    s2, b2 = _api("POST", url, body={"vote": 1})
    assert s2 == 200, b2
    assert b2["total_up"] == 1, "second anonymous overall 👍 must not double-count"


def test_feedback_unknown_section_rejected(report_backend, seed_report):
    rep = seed_report()
    base = report_backend["base"]
    status, _ = _api(
        "POST", f"{base}/api/report/{rep['id']}/feedback",
        body={"section": "not_a_real_section", "vote": 1},
    )
    assert status == 400


def test_feedback_on_missing_report_404(report_backend):
    base = report_backend["base"]
    status, _ = _api(
        "POST", f"{base}/api/report/r_0000000000000000/feedback",
        body={"section": "action_plan", "vote": 1},
    )
    assert status == 404


def test_reports_mine_lists_only_my_reports(report_backend, seed_report):
    """/api/reports/mine filters by X-Anon-Id, newest first."""
    seed_report(query="anonA report 1", creator_anon_id="list-anon-A")
    time.sleep(0.01)  ***REMOVED*** keep created_at strictly ordered
    seed_report(query="anonA report 2", creator_anon_id="list-anon-A")
    seed_report(query="anonB report", creator_anon_id="list-anon-B")

    base = report_backend["base"]
    status, body = _api(
        "GET", f"{base}/api/reports/mine",
        headers={"X-Anon-Id": "list-anon-A"},
    )
    assert status == 200, body
    queries = [it["query"] for it in body["items"]]
    assert "anonA report 1" in queries
    assert "anonA report 2" in queries
    assert "anonB report" not in queries
    ***REMOVED*** Newest first.
    assert queries.index("anonA report 2") < queries.index("anonA report 1")


def test_reports_mine_without_anon_id_is_empty(report_backend):
    base = report_backend["base"]
    status, body = _api("GET", f"{base}/api/reports/mine")
    assert status == 200
    assert body == {"items": [], "has_more": False}


***REMOVED*** =================== Phase B — browser ============================== ***REMOVED***

try:
    from playwright.sync_api import sync_playwright  ***REMOVED*** noqa: F401
    _PLAYWRIGHT = True
except Exception:  ***REMOVED*** pragma: no cover - env without playwright
    _PLAYWRIGHT = False


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_share_page_renders_in_browser(report_backend, seed_report):
    """Scenarios 1 + 2 — the share URL renders the 9-section report in a
    fresh browser context (no anon cookie)."""
    from playwright.sync_api import sync_playwright

    rep = seed_report(query="跨领域同构 e2e 渲染测试")
    url = f"{report_backend['base']}/report/share/{rep['share_token']}"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ***REMOVED*** A brand-new context == incognito: no localStorage anonId.
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            ***REMOVED*** report.js reuses analyze.js renderFinalReport — sections render
            ***REMOVED*** as ***REMOVED***analyze-sections > section.section (one per 9-section key).
            page.wait_for_selector("***REMOVED***analyze-sections .section", timeout=10000)
            sections = page.locator("***REMOVED***analyze-sections .section")
            assert sections.count() == 9, "expected all 9 sections rendered"
            ***REMOVED*** Meta header (query title) is shown, loading spinner gone.
            assert page.locator("***REMOVED***report-meta").is_visible()
            assert "跨领域同构 e2e 渲染测试" in page.locator("***REMOVED***report-meta").inner_text()
            assert page.locator("***REMOVED***report-loading").is_hidden()
            ***REMOVED*** Share bar is wired for a share-route load.
            assert page.locator("***REMOVED***analyze-share-bar").count() == 1
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_feedback_button_posts_in_browser(report_backend, seed_report):
    """Scenario 3 (UI) — clicking the share-bar 👍 fires a POST that 200s."""
    from playwright.sync_api import sync_playwright

    rep = seed_report()
    url = f"{report_backend['base']}/report/share/{rep['share_token']}"
    feedback_path = f"/api/report/{rep['id']}/feedback"

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            ***REMOVED*** Overall 👍/👎 live in the share bar (renderShareBar unhides it).
            page.wait_for_selector("***REMOVED***analyze-share-bar .analyze-vote--up", timeout=10000)
            up_btn = page.locator("***REMOVED***analyze-share-bar .analyze-vote--up").first
            with page.expect_response(
                lambda r: feedback_path in r.url and r.request.method == "POST",
                timeout=10000,
            ) as resp_info:
                up_btn.click()
            resp = resp_info.value
            assert resp.status == 200, resp.text()
            assert resp.json()["total_up"] == 1
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_my_reports_empty_state_in_browser(report_backend):
    """/reports with no anonId in localStorage shows the empty state."""
    from playwright.sync_api import sync_playwright

    url = f"{report_backend['base']}/reports"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()  ***REMOVED*** fresh — no anonId
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector(".myr-state", timeout=10000)
            assert "还没有保存的报告" in page.locator(".myr-state").inner_text()
            assert page.locator(".myr-card").count() == 0
        finally:
            ctx.close()
            browser.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_my_reports_lists_cards_in_browser(report_backend, seed_report):
    """/reports lists this device's reports and each card links to /report/<id>."""
    from playwright.sync_api import sync_playwright

    anon = "myreports-browser-anon"
    seed_report(query="蚁群优化与城市交通", creator_anon_id=anon)
    seed_report(query="珊瑚白化与系统性金融风险", creator_anon_id=anon)

    url = f"{report_backend['base']}/reports"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context()
        ***REMOVED*** Seed anonId before any page script runs.
        ctx.add_init_script(f"localStorage.setItem('anonId', {anon!r});")
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector(".myr-card", timeout=10000)
            cards = page.locator(".myr-card")
            assert cards.count() == 2
            text = page.locator("***REMOVED***myr-list").inner_text()
            assert "蚁群优化与城市交通" in text
            assert "珊瑚白化与系统性金融风险" in text
            ***REMOVED*** Each card links to a report detail URL.
            href = cards.first.get_attribute("href")
            assert href and href.startswith("/report/r_")
        finally:
            ctx.close()
            browser.close()
