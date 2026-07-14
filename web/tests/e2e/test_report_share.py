"""M1.4 PR #5 e2e — persisted report share + feedback flow (session #17).

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
from datetime import date, timedelta
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
WEB_BACKEND = REPO_ROOT / "web" / "backend"
FRONTEND_DIR = REPO_ROOT / "web" / "frontend"
AXE_PATH = REPO_ROOT / "web" / "phase-detector" / "node_modules" / "axe-core" / "axe.min.js"

# Fixed secret shared by the test process (seeding) and the shim (verifying)
# so HMAC share tokens match across both. Set before importing report_store.
_SHARE_SECRET = "e2e-test-share-secret-session-17"
os.environ["STRUCTURAL_SHARE_TOKEN_SECRET"] = _SHARE_SECRET
os.environ["STRUCTURAL_ENV"] = "test"

_LOCAL_VENV = REPO_ROOT / ".venv" / "bin" / "python"
_MAIN_VENV = Path.home() / "Projects" / "structural-isomorphism" / ".venv" / "bin" / "python"

# The 9 canonical section keys (mirror of report.py _ALLOWED_SECTIONS).
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


def _origin_candidate() -> dict:
    from web.backend.services.candidate_origin import (
        build_origin_candidate,
        discovery_id_for_pair,
    )

    pair = ("kb-origin-a", "kb-origin-b")
    candidate = build_origin_candidate(
        discovery_id=discovery_id_for_pair(*pair),
        contract_version="discovery-candidate-v2",
        candidate_family_id="pair-deadbeef0000",
        tier="priority_review",
        a_id=pair[0],
        b_id=pair[1],
    )
    assert candidate is not None
    return candidate


# ---------------- shim + store fixtures ------------------------------ #


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

# Point the router's lazily-initialised store at our temp DB.
report_api._store = ReportStore({str(db_path)!r})

app = FastAPI()
if install_problem_handlers:
    install_problem_handlers(app)
app.middleware("http")(report_api.no_store_report_share_responses)
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
    from services.report_store import ReportStore  # noqa: WPS433

    store = ReportStore(report_backend["db_path"])

    def _seed(*, query="测试查询", b_id="b_demo", lang="zh",
              creator_anon_id=None, is_partial=False, payload=None):
        # Pytest imports all selected modules before running fixtures. Other
        # E2E modules use their own deterministic share secret, so restore this
        # module's secret at the exact signing boundary for combined runs.
        os.environ["STRUCTURAL_SHARE_TOKEN_SECRET"] = _SHARE_SECRET
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


# =================== Phase A — API contract ========================= #


def test_persist_flow_share_token_round_trip(report_backend, seed_report):
    """Scenario 1 — a persisted report is readable via its share token."""
    rep = seed_report(query="为什么蚁群能找到最短路径")
    base = report_backend["base"]
    status, body = _api("GET", f"{base}/api/report/share/{rep['share_token']}")
    assert status == 200, body
    assert body["id"] == rep["id"]
    assert body["query"] == "为什么蚁群能找到最短路径"
    # payload comes back as a parsed dict with all 9 sections.
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
    # _credibility must not leak into the section payload.
    assert "_credibility" not in body["payload"]
    assert set(body["payload"]) == set(SECTION_KEYS)


def test_share_invalid_token_returns_404(report_backend):
    base = report_backend["base"]
    # Well-formed (32 hex) but unsigned token.
    status, _ = _api("GET", f"{base}/api/report/share/{'a' * 32}")
    assert status == 404
    # Malformed length — also 404, never 500.
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
    time.sleep(0.01)  # keep created_at strictly ordered
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
    # Newest first.
    assert queries.index("anonA report 2") < queries.index("anonA report 1")


def test_reports_mine_without_anon_id_is_empty(report_backend):
    base = report_backend["base"]
    status, body = _api("GET", f"{base}/api/reports/mine")
    assert status == 200
    assert body == {"items": [], "has_more": False}


# =================== Phase B — browser ============================== #

try:
    from playwright.sync_api import sync_playwright  # noqa: F401
    _PLAYWRIGHT = True
except Exception:  # pragma: no cover - env without playwright
    _PLAYWRIGHT = False


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_share_page_renders_in_browser(report_backend, seed_report, browser):
    """Scenarios 1 + 2 — the share URL renders the 9-section report in a
    fresh browser context (no anon cookie)."""
    rep = seed_report(
        query="跨领域同构 e2e 渲染测试",
        payload={**_sample_payload(), "_origin_candidate": _origin_candidate()},
    )
    url = f"{report_backend['base']}/report/share/{rep['share_token']}"

    # A brand-new context == incognito: no localStorage anonId.
    ctx = browser.new_context()
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        # report.js reuses analyze.js renderFinalReport — sections render
        # as #analyze-sections > section.section (one per 9-section key).
        page.wait_for_selector("#analyze-sections .section", timeout=10000)
        sections = page.locator("#analyze-sections .section")
        assert sections.count() == 9, "expected all 9 sections rendered"
        # Meta header (query title) is shown, loading spinner gone.
        assert page.locator("#report-meta").is_visible()
        assert "跨领域同构 e2e 渲染测试" in page.locator("#report-meta").inner_text()
        assert page.locator("#report-loading").is_hidden()
        origin = page.locator("#report-origin")
        assert origin.is_visible()
        assert "不会自动升级候选证据" in origin.inner_text()
        assert origin.locator("a").get_attribute("href") == (
            "/discoveries?candidate=" + _origin_candidate()["discovery_id"]
        )
        # Share bar is wired for a share-route load.
        assert page.locator("#analyze-share-bar").count() == 1
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_feedback_button_posts_in_browser(report_backend, seed_report, browser):
    """Scenario 3 (UI) — clicking the share-bar 👍 fires a POST that 200s."""
    rep = seed_report()
    url = f"{report_backend['base']}/report/share/{rep['share_token']}"
    feedback_path = f"/api/report/{rep['id']}/feedback"

    ctx = browser.new_context()
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        # Overall 👍/👎 live in the share bar (renderShareBar unhides it).
        page.wait_for_selector("#analyze-share-bar .analyze-vote--up", timeout=10000)
        up_btn = page.locator("#analyze-share-bar .analyze-vote--up").first
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


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_owner_decision_brief_download_and_create_experiment(
    report_backend, seed_report, browser,
):
    """Saved owner report exposes evidence-bounded brief and inline experiment."""
    anon = "decision-brief-owner"
    payload = _sample_payload()
    payload.update({
        "shared_structure": {"name": "负反馈", "intuition": "通过延迟反馈抑制过冲"},
        "risks_and_limits": [{"risk_name": "时滞失配", "explanation": "反馈周期可能不同"}],
        "action_plan": {
            "this_week": [{
                "title": "小流量试验", "verification": "新策略将过冲降低至少 10%",
                "expected_impact": "过冲率",
            }],
        },
        "_fingerprint": {"summary": "需求过冲来自反馈时滞", "revision": 1},
        "_source": {"id": "p_feedback", "name": "Feedback control", "domain": "Control"},
    })
    rep = seed_report(query="如何降低需求过冲", creator_anon_id=anon, payload=payload)
    url = f"{report_backend['base']}/report/{rep['id']}"
    followup_path = f"/api/report/{rep['id']}/followup"

    ctx = browser.new_context(accept_downloads=True)
    ctx.add_init_script(f"localStorage.setItem('anonId', {anon!r});")
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector("#decision-brief-root .decision-brief", timeout=10000)
        page.set_viewport_size({"width": 375, "height": 812})
        brief = page.locator("#decision-brief-root")
        assert "未经实证验证" in brief.inner_text()
        assert "需求过冲来自反馈时滞" in brief.inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert page.locator("#decision-brief-hypothesis").is_hidden()
        with page.expect_download() as download_info:
            page.locator("#decision-brief-download").click()
        assert download_info.value.suggested_filename.endswith(".md")
        page.locator("#decision-brief-create").click()
        assert page.locator("#decision-brief-experiment").is_visible()
        assert page.evaluate("document.activeElement?.id") == "decision-brief-hypothesis"
        expected_deadline = page.evaluate("""() => {
          const d = new Date(); d.setDate(d.getDate() + 7);
          return [d.getFullYear(), String(d.getMonth()+1).padStart(2,'0'), String(d.getDate()).padStart(2,'0')].join('-');
        }""")
        assert page.locator("#decision-brief-deadline").input_value() == expected_deadline
        page.locator("#decision-brief-stop").fill("过冲未改善或投诉率上升时停止")
        with page.expect_response(
            lambda r: followup_path in r.url and r.request.method == "POST",
            timeout=10000,
        ) as response_info:
            page.locator("#decision-brief-save").click()
        assert response_info.value.status == 200
        assert "实验已保存" in page.locator("#decision-brief-message").inner_text()
        assert page.locator("#decision-brief-save").is_disabled()
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_shared_decision_brief_is_read_only(report_backend, seed_report, browser):
    rep = seed_report()
    url = f"{report_backend['base']}/report/share/{rep['share_token']}"
    ctx = browser.new_context()
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector("#decision-brief-download", timeout=10000)
        assert page.locator("#decision-brief-create").count() == 0
        assert page.locator("#report-followup").count() == 0
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_legacy_report_without_evidence_cannot_create_experiment(
    report_backend, seed_report, browser,
):
    anon = "legacy-brief-owner"
    rep = seed_report(creator_anon_id=anon)
    url = f"{report_backend['base']}/report/{rep['id']}"
    ctx = browser.new_context()
    ctx.add_init_script(f"localStorage.setItem('anonId', {anon!r});")
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector("#decision-brief-download", timeout=10000)
        assert "当前报告没有这项证据" in page.locator("#decision-brief-root").inner_text()
        assert page.locator("#decision-brief-create").count() == 0
        escaped = page.evaluate(
            "model => decisionBriefMarkdown(model)",
            {
                "problem": "# injected\n<script>alert(1)</script>",
                "fingerprint": {}, "source": {}, "mechanism": "$x^2$",
                "boundary": "[click](javascript:alert(1))", "hypothesis": "",
                "metric": "", "reportId": "r/../../bad", "model": "",
                "promptVersion": "", "createdAt": "", "partial": False,
            },
        )
        assert "\\# injected" in escaped
        assert "\\<script\\>" in escaped
        assert "\\$x\\^2\\$" in escaped
        assert "\\[click\\]\\(javascript:alert\\(1\\)\\)" in escaped
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_my_reports_empty_state_in_browser(report_backend, browser):
    """/reports with no anonId in localStorage shows the empty state."""
    url = f"{report_backend['base']}/reports"
    ctx = browser.new_context()  # fresh — no anonId
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector(".myr-state", timeout=10000)
        assert "还没有保存的报告" in page.locator(".myr-state").inner_text()
        assert page.locator(".myr-card").count() == 0
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_my_reports_lists_cards_in_browser(report_backend, seed_report, browser):
    """/reports lists this device's reports and each card links to /report/<id>."""
    anon = "myreports-browser-anon"
    seed_report(
        query="蚁群优化与城市交通",
        creator_anon_id=anon,
        payload={**_sample_payload(), "_origin_candidate": _origin_candidate()},
    )
    seed_report(query="珊瑚白化与系统性金融风险", creator_anon_id=anon)

    url = f"{report_backend['base']}/reports"
    ctx = browser.new_context()
    # Seed anonId before any page script runs.
    ctx.add_init_script(f"localStorage.setItem('anonId', {anon!r});")
    page = ctx.new_page()
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        page.wait_for_selector(".myr-card", timeout=10000)
        cards = page.locator(".myr-card")
        assert cards.count() == 2
        text = page.locator("#myr-list").inner_text()
        assert "蚁群优化与城市交通" in text
        assert "珊瑚白化与系统性金融风险" in text
        # Each card links to a report detail URL.
        href = cards.first.get_attribute("href")
        assert href and href.startswith("/report/r_")
        origin_link = page.locator(".myr-card__origin")
        assert origin_link.count() == 1
        assert origin_link.get_attribute("href") == (
            "/discoveries?candidate=" + _origin_candidate()["discovery_id"]
        )
        assert origin_link.bounding_box()["height"] >= 44
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_account_report_delete_is_confirmed_and_updates_ui(
    report_backend, browser,
):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    page = ctx.new_page()
    deleted: list[str] = []
    delete_attempts = 0

    def fulfill_json(route, payload, status=200):
        route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(payload),
        )

    page.route(
        "**/api/auth/me",
        lambda route: fulfill_json(route, {
            "ok": True,
            "user": {"id": "account-owner", "email": "owner@example.test"},
        }),
    )
    page.route(
        "**/api/favorites",
        lambda route: fulfill_json(route, {"tickers": []}),
    )

    def reports_route(route):
        nonlocal delete_attempts
        request = route.request
        if request.method == "DELETE":
            deleted.append(request.url)
            delete_attempts += 1
            if delete_attempts == 1:
                fulfill_json(route, {"error": "temporary failure"}, status=503)
                return
            fulfill_json(route, {
                "ok": True,
                "report_id": "r_delete_me",
                "reports": 1,
                "followups": 1,
                "feedback": 0,
                "share_revoked": True,
            })
            return
        fulfill_json(route, {
            "items": [{
                "id": "r_delete_me",
                "share_token": "a" * 32,
                "query": "删除流程体验测试",
                "b_id": "b",
                "lang": "zh",
                "created_at": "2026-07-13T00:00:00Z",
                "view_count": 1,
                "has_followup": True,
                "followup_status": "planned",
                "followup_outcome": "",
                "experiment_status": "planned",
                "experiment_deadline": None,
                "publish_to_insights": False,
            }],
            "has_more": False,
        })

    page.route("**/api/me/reports*", reports_route)
    page.route("**/api/me/reports/**", reports_route)
    try:
        page.goto(
            report_backend["base"] + "/reports",
            wait_until="domcontentloaded",
            timeout=20000,
        )
        page.wait_for_selector("[data-delete-report]", timeout=10000)
        delete_button = page.locator("[data-delete-report]")
        assert delete_button.evaluate(
            "element => element.getBoundingClientRect().height"
        ) >= 44
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

        delete_button.click()
        assert deleted == []
        assert delete_button.inner_text() == "确认永久删除"
        assert "分享链接都会删除" in page.locator(
            "[data-delete-status]"
        ).inner_text()
        page.locator("[data-cancel-delete-report]").click()
        assert delete_button.inner_text() == "删除报告"

        delete_button.click()
        delete_button.click()
        page.wait_for_function(
            "document.querySelector('[data-delete-report]').textContent.includes('重试')"
        )
        assert page.evaluate(
            "document.activeElement === document.querySelector('[data-delete-report]')"
        )
        assert page.locator(".myr-card").count() == 1
        assert "仍然保留" in page.locator("[data-delete-status]").inner_text()
        page.keyboard.press("Space")
        page.wait_for_selector(".myr-state", timeout=10000)
        assert len(deleted) == 2
        assert all(url.endswith("/api/me/reports/r_delete_me") for url in deleted)
        assert page.locator(".myr-card").count() == 0
        assert "还没有保存的报告" in page.locator(".myr-state").inner_text()
        assert page.evaluate(
            "document.activeElement === document.querySelector('#myr-list')"
        )
        assert page.locator("#myr-list").get_attribute("tabindex") == "-1"
    finally:
        ctx.close()


@pytest.mark.skipif(not _PLAYWRIGHT, reason="playwright not installed")
def test_report_dashboard_deadlines_counts_and_local_reminder_toggle(
    report_backend, seed_report, browser,
):
    from services.report_store import ReportStore

    anon = "deadline-dashboard-owner"
    overdue = seed_report(query="逾期实验", creator_anon_id=anon)
    soon = seed_report(query="即将到期实验", creator_anon_id=anon)
    done = seed_report(query="已结束实验", creator_anon_id=anon)
    store = ReportStore(report_backend["db_path"])
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    two_days = (date.today() + timedelta(days=2)).isoformat()
    for rep, deadline, status, action in [
        (overdue, yesterday, "planned", "planned"),
        (soon, two_days, "in_progress", "in_progress"),
        (done, yesterday, "completed", "tried"),
    ]:
        kwargs = {}
        if status == "completed":
            kwargs = {
                "outcome": "worked",
                "outcome_detail": {"result": "success"},
            }
        store.record_followup(
            report_id=rep["id"], anon_id=anon, action_status=action,
            experiment={"hypothesis": "h", "status": status, "deadline": deadline},
            **kwargs,
        )

    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.add_init_script(f"localStorage.setItem('anonId', {anon!r});")
    page = ctx.new_page()
    try:
            page.goto(report_backend["base"] + "/reports", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector(".myr-card", timeout=10000)
            summary = page.locator("#myr-reminder-summary")
            if AXE_PATH.is_file():
                page.add_script_tag(content=AXE_PATH.read_text(encoding="utf-8"))
                serious = page.evaluate("""async () => (await axe.run(document, {
                  runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}
                })).violations.filter(v => ['critical','serious'].includes(v.impact))""")
                assert serious == []
            assert "1 个实验已逾期" in summary.inner_text()
            assert "1 个将在 3 天内到期" in summary.inner_text()
            overdue_card = page.locator(".myr-card", has_text="逾期实验")
            assert "已逾期" in overdue_card.inner_text()
            done_card = page.locator(".myr-card", has_text="已结束实验")
            assert "已逾期" not in done_card.inner_text()
            toggle = page.locator("#myr-reminder-toggle")
            assert toggle.is_checked()
            toggle.uncheck()
            assert "本地提醒已关闭" in summary.inner_text()
            assert "1 个实验已逾期" in summary.inner_text()
            assert "1 个将在 3 天内到期" in summary.inner_text()
            assert page.evaluate("localStorage.getItem('structural_local_reminders')") == "off"
            assert toggle.evaluate("el => el.getBoundingClientRect().height") >= 18
            states = page.evaluate("""() => ({
              spring: __myReports.deadlineState(
                {experiment_status:'planned', experiment_deadline:'2026-03-09'},
                new Date(2026, 2, 8, 12)
              ),
              fall: __myReports.deadlineState(
                {experiment_status:'planned', experiment_deadline:'2026-11-02'},
                new Date(2026, 10, 1, 12)
              ),
              invalid: __myReports.deadlineState(
                {experiment_status:'planned', experiment_deadline:'2026-02-30'}
              ),
              missing: __myReports.deadlineState({experiment_status:'planned'}),
              abandoned: __myReports.deadlineState({
                experiment_status:'planned', experiment_deadline:'2020-01-01',
                followup_status:'abandoned'
              })
            })""")
            assert states["spring"] == {"kind": "soon", "days": 1}
            assert states["fall"] == {"kind": "soon", "days": 1}
            assert states["invalid"]["kind"] == "invalid"
            assert states["missing"]["kind"] == "none"
            assert states["abandoned"]["kind"] == "done"
            page.evaluate("localStorage.setItem('structural_local_reminders', 'corrupt')")
            page.reload(wait_until="domcontentloaded")
            page.wait_for_selector(".myr-card", timeout=10000)
            assert not page.locator("#myr-reminder-toggle").is_checked()
            assert "1 个实验已逾期" in page.locator("#myr-reminder-summary").inner_text()
            page.goto(report_backend["base"] + "/report/" + done["id"], wait_until="domcontentloaded", timeout=20000)
            page.wait_for_selector("#report-followup", timeout=10000)
            assert "实验已结束，不再提醒" in page.locator("#report-reminder-message").inner_text()
            consent = page.locator("#rf-publish-insights")
            assert consent.is_visible()
            assert not consent.is_checked()
            assert "当前暂停" in page.locator(
                ".report-publication-consent"
            ).inner_text()
            consent.check()
            page.locator("#rf-submit").click()
            page.wait_for_function("document.querySelector('#rf-msg').textContent.includes('公开聚合当前暂停')")
            page.wait_for_timeout(450)
            assert page.locator("#rf-publish-insights").is_checked()
            page.locator("#rf-publish-insights").uncheck()
            page.locator("#rf-submit").click()
            page.wait_for_function("document.querySelector('#rf-msg').textContent.includes('保持私密')")
    finally:
        ctx.close()
