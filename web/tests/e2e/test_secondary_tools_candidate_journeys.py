"""Deterministic browser journeys for the four candidate-only secondary tools."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e
ROOT = Path(__file__).resolve().parents[3]
FRONTEND = ROOT / "web" / "frontend"
JS = FRONTEND / "assets" / "js"
CSS = FRONTEND / "assets" / "css"
VIEWPORTS = (320, 390)


def _evidence(label: str, *, kb: bool = False) -> dict:
    return {
        "schema_version": "evidence-envelope-v1",
        "evidence_level": "candidate",
        "candidate": {
            "status": "recorded", "kind": "candidate", "label": label,
            "score": None,
        },
        "source": {
            "status": "recorded" if kb else "not_recorded",
            "kind": "internal_kb" if kb else "not_recorded",
            "label": "Structural KB record" if kb else None,
            "url": None, "source_review": None,
        },
        "result": {
            "status": "not_recorded" if kb else "recorded",
            "provenance": "NOT_TESTED" if kb else "INTERNAL_AI_SCREEN",
            "verdict": "NOT_TESTED" if kb else "INCONCLUSIVE",
            "summary": None,
        },
        "independence": {
            "status": "not_recorded", "kind": "not_recorded", "summary": None,
        },
        "counterexamples": {"status": "gap_recorded", "summary": None},
        "ledger": {
            "status": "not_recorded", "claim_id": None, "version": None,
            "recorded_at": None, "artifact_sha256": None, "url": None,
        },
    }


def _reference() -> dict:
    name = "库存振荡"
    return {
        "id": "kb-1", "name": name, "domain": "供应链",
        "description": "延迟反馈可能造成过冲。", "retrieval_rank": 1,
        "candidate_note": "核查反馈时滞和状态变量定义；不一致时放弃参照。",
        "evidence": _evidence(name, kb=True),
    }


def _load(page: Page, name: str) -> list[str]:
    html = (FRONTEND / f"{name}.html").read_text(encoding="utf-8")
    html = re.sub(r"<script\b[^>]*>.*?</script>", "", html,
                  flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<link\b[^>]*rel=[\"']stylesheet[\"'][^>]*>", "", html,
                  flags=re.IGNORECASE)
    html = html.replace("<head>", '<head><base href="https://local.structural.test/">', 1)
    url = f"https://local.structural.test/{name}"
    page.route(
        url,
        lambda route: route.fulfill(
            status=200, content_type="text/html; charset=utf-8", body=html
        ),
    )
    page.goto(url, wait_until="domcontentloaded")
    for sheet in (
        "shared-tokens.css", "reset.css", "design-system.css", "common.css",
        f"{name}.css" if name != "stress-test" else "stress-test.css",
        "responsive.css",
    ):
        page.add_style_tag(path=str(CSS / sheet))
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_script_tag(content=(JS / "secondary-tool-contracts.js").read_text())
    if name == "apply":
        page.add_script_tag(content=(JS / "utils" / "buildAnalyzeUrl.js").read_text())
    page.add_script_tag(content=(JS / {
        "stress-test": "stress-test.js", "diagnose": "diagnose.js",
        "apply": "apply.js", "lint": "lint.js",
    }[name]).read_text())
    if name == "stress-test":
        page.evaluate("document.dispatchEvent(new Event('DOMContentLoaded'))")
    return errors


def _assert_no_overflow(page: Page, width: int) -> None:
    dimensions = page.evaluate("""() => ({
      root: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      viewport: window.innerWidth
    })""")
    assert dimensions["viewport"] == width
    assert max(dimensions["root"], dimensions["body"]) <= width + 1


def _assert_mobile(page: Page, submit_selector: str, width: int) -> None:
    _assert_no_overflow(page, width)
    button = page.locator(submit_selector)
    expect(button).to_be_visible()
    box = button.bounding_box()
    assert box and box["height"] >= 44
    assert box["x"] >= -1 and box["x"] + box["width"] <= width + 1


@pytest.mark.parametrize("width", VIEWPORTS)
def test_stress_contract_failure_recovers_and_escapes_model_html(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 844})
    calls = []

    def route_api(route):
        body = route.request.post_data_json
        calls.append(body)
        payload = {
            "contract_version": "secondary-tools-v2", "request_id": body["client_request_id"],
            "claim": body["claim"], "screening_outcome": "condition_dependent",
            "screening_basis": "internal_ai_red_team", "source": "延迟反馈系统",
            "target": "当前团队",
            "structural_correspondences": [{
                "claim": "反馈存在时滞",
                "screening_outcome": "breaks",
                "stress_result": '<img src=x onerror="window.__secondaryXss=1">时滞未测量',
            }],
            "weakest_link": "反馈时滞尚未测量", "rationale": "需要先记录恢复轨迹。",
            "candidate_reference": _reference(), "evidence": _evidence(body["claim"]),
        }
        if len(calls) == 1:
            payload["verdict"] = "PASS"
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/stress-test", route_api)
    errors = _load(page, "stress-test")
    _assert_mobile(page, "#stress-submit", width)
    claim = "我们像一个受延迟反馈控制的系统"
    page.locator("#stress-claim").fill(claim)
    page.locator("#stress-submit").click()
    expect(page.locator("#stress-error")).to_contain_text("完整性校验")
    expect(page.locator("#stress-result")).to_be_hidden()
    page.locator("#stress-submit").click()
    expect(page.locator("#stress-result")).to_be_visible()
    result_text = page.locator("#stress-result").inner_text()
    assert "内部模型筛查" in result_text and "知识库候选参照" in result_text
    assert not re.search(r"\b(?:PASS|FAIL|CONDITIONAL)\b", result_text)
    assert page.locator("#stress-result img").count() == 0
    assert page.evaluate("window.__secondaryXss") is None
    assert calls[-1]["claim"] == claim and "client_request_id" in calls[-1]
    _assert_no_overflow(page, width)
    assert errors == []


@pytest.mark.parametrize("width", VIEWPORTS)
def test_diagnose_contract_failure_retry_then_candidate_report(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 844})
    calls = []

    def route_api(route):
        body = route.request.post_data_json
        calls.append(body)
        state = {
            "state_id": "hysteresis_trap", "name": "滞回陷阱",
            "definition": "移除原诱因后状态仍可能延续。", "typical_signal": "改流程后仍不回弹。",
        }
        payload = {
            "contract_version": "secondary-tools-v2", "request_id": body["client_request_id"],
            "situation": body["situation"], "assessment_kind": "structural_state_hypothesis",
            "primary_state": dict(state), "secondary_state": None,
            "reasoning": "当前描述与路径依赖候选相符。",
            "evolution": "若反馈条件不变，旧模式可能延续。",
            "signals_to_watch": ["干预后决策时长是否下降"],
            "recommendations": ["先记录两周基线。"],
            "candidate_reference": _reference(), "evidence": _evidence(body["situation"]),
        }
        if len(calls) == 1:
            payload["primary_state"]["confidence"] = 0.92
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/diagnose", route_api)
    errors = _load(page, "diagnose")
    _assert_mobile(page, "#diagnose-submit", width)
    situation = "流程改过两次，但团队协作方式没有变化，决策越来越慢。"
    page.locator("#diagnose-textarea").fill(situation)
    page.locator("#diagnose-submit").click()
    expect(page.locator("#diagnose-error")).to_be_visible()
    expect(page.locator("#diagnose-error-msg")).to_contain_text("完整性校验")
    page.locator("#diagnose-retry").click()
    page.locator("#diagnose-submit").click()
    expect(page.locator("#diagnose-report")).to_be_visible()
    report = page.locator("#diagnose-report").inner_text()
    assert "模型生成候选" in report and "知识库检索候选" in report
    assert "%" not in page.locator("#diagnose-status").inner_text()
    _assert_no_overflow(page, width)
    assert errors == []


@pytest.mark.parametrize("width", VIEWPORTS)
def test_apply_rejects_score_payload_then_renders_rank_only(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 844})
    calls = []

    def route_api(route):
        body = route.request.post_data_json
        calls.append(body)
        candidate = {
            "id": "kb-1", "name": "库存振荡", "domain": "供应链", "type_id": "delay",
            "description": "延迟反馈造成过冲。", "retrieval_rank": 1,
            "candidate_note": "核查状态变量和反馈时滞。", "evidence": _evidence("库存振荡", kb=True),
        }
        if len(calls) == 1:
            candidate["relevance"] = 0.94
        payload = {
            "contract_version": "secondary-tools-v2", "request_id": body["client_request_id"],
            "method": body["method"], "signature": "局部反馈迭代",
            "signature_origin": "model_generated", "keywords": ["反馈", "迭代"],
            "count": 1, "candidates": [candidate], "evidence": _evidence(body["method"]),
        }
        route.fulfill(status=200, content_type="application/json", body=json.dumps(payload))

    page.route("**/api/method/apply", route_api)
    errors = _load(page, "apply")
    _assert_mobile(page, "#apply-submit", width)
    method = "用局部反馈迭代寻找较优方案"
    page.locator("#apply-input").fill(method)
    page.locator("#apply-submit").click()
    expect(page.locator(".apply-status--error")).to_contain_text("完整性校验")
    page.locator("#apply-submit").click()
    expect(page.locator("#apply-result")).to_be_visible()
    result = page.locator("#apply-result").inner_text()
    assert "候选 #1" in result and "均未验证" in result
    assert not re.search(r"\d+(?:\.\d+)?\s*%", result)
    href = page.locator(".apply-card__link").get_attribute("href") or ""
    assert href.startswith("/analyze?id=kb-1&handoff=") and method not in href
    _assert_no_overflow(page, width)
    assert errors == []


@pytest.mark.parametrize("width", VIEWPORTS)
def test_lint_rejects_mismatched_stream_then_recovers(page: Page, width: int):
    page.set_viewport_size({"width": width, "height": 844})
    calls = []

    def route_api(route):
        body = route.request.post_data_json
        calls.append(body)
        request_id = body["client_request_id"]
        if len(calls) == 1:
            stream = (
                'event: meta\ndata: {"request_id":"wrong-request-123","contract_version":'
                '"secondary-tools-v2"}\n\n'
            )
        else:
            quote = "预算翻倍会让增长线性放大"
            claim = {
                "claim_id": "lint-0123456789abcdef", "quote": quote,
                "claim_type": "causal_judgment", "structure": "投入和结果被假设为线性。",
                "failure_mode": "边际回报可能递减。", "review_priority": "high",
                "suggestion": "先做分段增量测试。", "reference_candidate": _reference(),
                "evidence": _evidence(quote),
            }
            result = {
                "contract_version": "secondary-tools-v2", "request_id": request_id,
                "screening_kind": "internal_ai_document_screen",
                "summary": "优先核查线性增长假设。", "claims": [claim],
                "evidence": _evidence("用户提交的策略文档"),
            }
            stream = (
                "event: meta\ndata: " + json.dumps({
                    "request_id": request_id, "contract_version": "secondary-tools-v2",
                    "max_doc_chars": 20000,
                }) + "\n\n" +
                "event: done\ndata: " + json.dumps({"result": result}) + "\n\n"
            )
        route.fulfill(status=200, content_type="text/event-stream", body=stream)

    page.route("**/api/struct-lint/stream", route_api)
    errors = _load(page, "lint")
    _assert_mobile(page, "#lint-submit", width)
    document = "我们的计划假设预算翻倍会让增长线性放大。"
    page.locator("#lint-textarea").fill(document)
    page.locator("#lint-submit").click()
    expect(page.locator("#lint-error")).to_be_visible()
    expect(page.locator("#lint-error-msg")).to_contain_text("请求绑定校验")
    page.locator("#lint-retry").click()
    page.locator("#lint-submit").click()
    expect(page.locator("#lint-result")).to_be_visible()
    result = page.locator("#lint-result").inner_text()
    assert "优先复核" in result and "知识库候选参照（未验证）" in result
    assert calls[-1]["document"] == document
    _assert_no_overflow(page, width)
    assert errors == []
