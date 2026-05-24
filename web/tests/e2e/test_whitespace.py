"""A2 Whitespace Map — /whitespace page e2e (session #18).

Asserts:
  1. /whitespace renders the intro, the matrix heatmap, and the leads list.
  2. The matrix shows at least one `lead` cell and one `filled` cell.
  3. The leads list renders cards with a 「生成验证方案」 link whose href
     is /analyze?text_a=...&b_id=<anchor>.
  4. The class filter narrows the leads list.

Self-contained: serves the static frontend out of web/frontend/ and stubs
/api/whitespace/* with canned JSON via Playwright route interception.
No live backend needed.

Run:
    cd web/tests/e2e
    pytest test_whitespace.py -v
"""
from __future__ import annotations

import http.server
import json
import os
import socket
import socketserver
import threading
from pathlib import Path
from typing import Generator

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = REPO_ROOT / "web" / "frontend"


# --- Canned API payloads --- #

_MATRIX = {
    "available": True,
    "meta": {"n_classes": 2, "n_domains": 3, "n_filled": 2,
             "n_lead": 3, "n_leads": 3},
    "classes": [
        {"class_id": "c1", "class_name": "阈值级联类", "rank": 0},
        {"class_id": "c2", "class_name": "二阶振子类", "rank": 1},
    ],
    "domains": ["金融", "医学", "海洋学"],
    "matrix": {
        "c1": {
            "金融": {"state": "filled", "score": 0.31},
            "医学": {"state": "lead", "score": 0.28},
            "海洋学": {"state": "empty", "score": 0.05},
        },
        "c2": {
            "金融": {"state": "lead", "score": 0.20},
            "医学": {"state": "filled", "score": 0.30},
            "海洋学": {"state": "lead", "score": 0.36},
        },
    },
}

# Two leads carry LLM verdicts (yes / maybe), one does not (degraded path)
# — exercises both the LLM-enriched and the no-key fallback rendering.
_LEADS = {
    "available": True,
    "total": 3,
    "count": 3,
    "limit": 500,
    "leads": [
        {"class_id": "c2", "class_name": "二阶振子类", "domain": "海洋学",
         "score": 0.36, "anchor_id": "p-100", "anchor_name": "海气耦合",
         "anchor_desc": "风浪与海面的耦合振荡。",
         "signal": {"type_match": 0.71, "embedding_cos": 0.12,
                    "used_type_signature": True},
         "plausible": "yes", "rationale": "海气耦合具二阶阻尼振子结构。",
         "research_question": "海洋学中的厄尔尼诺振荡是否符合阻尼二阶振子模型？"},
        {"class_id": "c1", "class_name": "阈值级联类", "domain": "医学",
         "score": 0.28, "anchor_id": "p-200", "anchor_name": "免疫级联",
         "anchor_desc": "免疫反应的级联放大。",
         "signal": {"type_match": 0.55, "embedding_cos": 0.09,
                    "used_type_signature": True},
         "plausible": "maybe", "rationale": "免疫级联可能存在阈值触发。",
         "research_question": "医学中的细胞因子风暴是否存在阈值触发的雪崩？"},
        {"class_id": "c2", "class_name": "二阶振子类", "domain": "金融",
         "score": 0.20, "anchor_id": "p-300", "anchor_name": "价格振荡",
         "anchor_desc": "市场价格的阻尼振荡。"},
    ],
}


# --- Local static server --- #


class _SilentHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args, **kwargs):  # silence stderr
        pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def local_server() -> Generator[str, None, None]:
    port = _free_port()
    handler = _SilentHandler
    handler.directory = str(FRONTEND_DIR)
    httpd = socketserver.TCPServer(("127.0.0.1", port), handler)

    orig_cwd = os.getcwd()
    os.chdir(str(FRONTEND_DIR))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        os.chdir(orig_cwd)


@pytest.fixture(scope="module")
def chromium_browser(playwright_instance):
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


def _open_page(browser, base_url: str):
    """Open /whitespace with /api/whitespace/* stubbed."""
    context = browser.new_context()
    page = context.new_page()

    def _route(route):
        url = route.request.url
        if "/api/whitespace/matrix" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(_MATRIX))
        elif "/api/whitespace/leads" in url:
            route.fulfill(status=200, content_type="application/json",
                          body=json.dumps(_LEADS))
        else:
            route.continue_()

    page.route("**/api/whitespace/**", _route)
    page.goto(f"{base_url}/whitespace.html", wait_until="networkidle")
    return page


# --- Tests --- #


def test_page_renders_intro_and_sections(local_server, chromium_browser):
    page = _open_page(chromium_browser, local_server)
    try:
        assert page.locator(".ws-intro__title").inner_text().strip() == "研究空白地图"
        # Matrix + leads sections become visible after data loads.
        assert page.locator("#ws-matrix-section").is_visible()
        assert page.locator("#ws-leads-section").is_visible()
        assert not page.locator("#ws-error").is_visible()
    finally:
        page.context.close()


def test_matrix_has_lead_and_filled_cells(local_server, chromium_browser):
    page = _open_page(chromium_browser, local_server)
    try:
        assert page.locator(".ws-matrix__row").count() == 2
        assert page.locator(".ws-cell--lead").count() >= 1
        assert page.locator(".ws-cell--filled").count() >= 1
    finally:
        page.context.close()


def test_leads_render_with_analyze_link(local_server, chromium_browser):
    page = _open_page(chromium_browser, local_server)
    try:
        cards = page.locator(".ws-lead")
        assert cards.count() == 3
        first = page.locator(".ws-lead").first
        first_link = first.locator("a.ws-btn--primary")
        href = first_link.get_attribute("href")
        assert href.startswith("/analyze?")
        # The /analyze prefill carries the concrete research question.
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(href).query)
        assert "厄尔尼诺振荡" in qs["text_a"][0]
        # Top lead anchors p-100 (海气耦合).
        assert "b_id=p-100" in href
    finally:
        page.context.close()


def test_leads_show_llm_question_rationale_and_badge(local_server, chromium_browser):
    """When the json carries LLM fields the card shows the research
    question, the rationale, and a yes/maybe plausibility badge."""
    page = _open_page(chromium_browser, local_server)
    try:
        first = page.locator(".ws-lead").first
        # The concrete LLM research question is the card headline.
        assert "厄尔尼诺振荡" in first.locator(".ws-lead__question").inner_text()
        # The LLM rationale is rendered.
        assert "二阶阻尼振子" in first.locator(".ws-lead__claim").inner_text()
        # yes -> 大概率成立 badge; the maybe lead -> 值得验证.
        assert first.locator(".ws-lead__plausible--yes").count() == 1
        assert page.locator(".ws-lead__plausible--maybe").count() == 1
        # The unjudged third lead has no badge.
        assert page.locator(".ws-lead__plausible").count() == 2
    finally:
        page.context.close()


def test_class_filter_narrows_leads(local_server, chromium_browser):
    page = _open_page(chromium_browser, local_server)
    try:
        assert page.locator(".ws-lead").count() == 3
        page.select_option("#ws-filter-class", "c1")
        # Only one lead belongs to class c1.
        assert page.locator(".ws-lead").count() == 1
        page.click("#ws-filter-reset")
        assert page.locator(".ws-lead").count() == 3
    finally:
        page.context.close()
