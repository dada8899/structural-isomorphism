"""Session #18 e2e tests — C2 structural lint (/lint page).

Run: pytest web/tests/e2e/test_struct_lint.py -v

@pytest.mark.post_deploy — only pass once Session #18 ships lint.html.
The orchestrator runs these; in baseline phase skip via `-k "not post_deploy"`.
The example-chip regressions are self-contained and run before deployment.
"""
import json
import re
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE = "https://beta.structural.bytedance.city"
REPO_ROOT = Path(__file__).resolve().parents[3]
LINT_HTML = REPO_ROOT / "web" / "frontend" / "lint.html"
LINT_JS = REPO_ROOT / "web" / "frontend" / "assets" / "js" / "lint.js"
CONTRACTS_JS = (
    REPO_ROOT / "web" / "frontend" / "assets" / "js" /
    "secondary-tool-contracts.js"
)

# /api/struct-lint is streamed via a POST body + SSE response.
# First event (`meta` -> loading hint) arrives sub-second; the full result
# block lands once the `done` event fires (~36-165s, LLM-bound).
#
# SESSION-22 §8: dropped from a flat 210s wait to a layered budget that
# catches a stalled SSE channel fast (10s for first byte) but still gives
# the LLM enough headroom (180s for `done`). The two-tier wait turns a
# hung connection into a fail-fast signal instead of a 3.5-min timeout.
LINT_FIRST_EVENT_TIMEOUT_MS = 10000     # SSE first byte (meta event)
LINT_RESULT_TIMEOUT_MS = 180000         # full pipeline -> #lint-result visible

_SAMPLE_DOC = (
    "我们的增长方案：竞品 X 靠裂变拉新做到了百万用户，我们照搬同一套裂变机制也能做到。"
    "只要把补贴预算提上去，用户量就会自然增长，用户量上来之后收入也会随之上来。"
    "团队现在 5 个人，扩到 20 人后产能会翻 4 倍，所以三个月内就能上线全部功能。"
)


def _candidate_evidence(label: str) -> dict:
    return {
        "schema_version": "evidence-envelope-v1",
        "evidence_level": "candidate",
        "candidate": {
            "status": "recorded", "kind": "document_screen",
            "label": label, "score": None,
        },
        "source": {
            "status": "not_recorded", "kind": "not_recorded",
            "label": None, "url": None, "source_review": None,
        },
        "result": {
            "status": "recorded", "provenance": "INTERNAL_AI_SCREEN",
            "verdict": "INCONCLUSIVE", "summary": None,
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


def _lint_stream(request, summary: str) -> str:
    request_id = request.post_data_json["client_request_id"]
    result = {
        "contract_version": "secondary-tools-v2",
        "request_id": request_id,
        "screening_kind": "internal_ai_document_screen",
        "summary": summary,
        "claims": [],
        "evidence": _candidate_evidence("用户提交的策略文档"),
    }
    return (
        "event: meta\ndata: " + json.dumps({
            "max_doc_chars": 20000,
            "request_id": request_id,
            "contract_version": "secondary-tools-v2",
        }, ensure_ascii=False) + "\n\n"
        "event: progress\ndata: {\"stage\":\"extract\",\"message\":\"正在抽取\"}\n\n"
        "event: done\ndata: " + json.dumps(
            {"result": result}, ensure_ascii=False
        ) + "\n\n"
    )


def _load_local_lint(page: Page) -> None:
    """Load the real lint markup and script without network or backend calls."""
    html = re.sub(
        r"<script\b[^>]*>.*?</script>",
        "",
        LINT_HTML.read_text(encoding="utf-8"),
        flags=re.IGNORECASE | re.DOTALL,
    )
    html = html.replace("<head>", '<head><base href="https://local.structural.test/">', 1)
    page.set_content(html, wait_until="domcontentloaded")
    page.add_script_tag(content=CONTRACTS_JS.read_text(encoding="utf-8"))
    page.add_script_tag(content=LINT_JS.read_text(encoding="utf-8"))


def test_lint_example_chips_fill_without_submitting(page: Page):
    """Every example fills, recounts, focuses, and stays on the input view."""
    _load_local_lint(page)
    chips = page.locator(".lint-chip[data-example]")
    textarea = page.locator("#lint-textarea")
    assert chips.count() == 3

    examples = set()
    for index in range(chips.count()):
        chip = chips.nth(index)
        label = chip.inner_text().strip()
        example = chip.get_attribute("data-example") or ""
        assert chip.get_attribute("type") == "button"
        assert label and 0 < len(example) <= 20_000
        assert page.get_by_role("button", name=label, exact=True).count() == 1
        examples.add(example)

        textarea.fill("旧内容")
        chip.click()
        expect(textarea).to_have_value(example)
        expect(page.locator("#lint-charcount")).to_have_text(
            f"{len(example)} / 20000"
        )
        expect(textarea).to_be_focused()
        expect(page.locator("#lint-input")).to_be_visible()
        expect(page.locator("#lint-loading")).to_be_hidden()
        expect(page.locator("#lint-result")).to_be_hidden()

    assert len(examples) == 3, "example payloads must remain distinct"


def test_lint_example_chip_supports_keyboard_activation(page: Page):
    """Native keyboard activation follows the same focus-preserving path."""
    _load_local_lint(page)
    chip = page.locator(".lint-chip[data-example]").first
    example = chip.get_attribute("data-example") or ""
    chip.focus()
    chip.press("Enter")
    expect(page.locator("#lint-textarea")).to_have_value(example)
    expect(page.locator("#lint-textarea")).to_be_focused()
    expect(page.locator("#lint-loading")).to_be_hidden()


def test_lint_20k_cjk_uses_post_body_and_parses_stream(page: Page):
    """The largest supported CJK document never enters the request URL."""
    requests = []

    def fulfill_stream(route):
        requests.append(route.request)
        route.fulfill(
            status=200,
            content_type="text/event-stream; charset=utf-8",
            headers={"Cache-Control": "no-store"},
            body=_lint_stream(route.request, "已完成"),
        )

    page.route("**/api/struct-lint/stream", fulfill_stream)
    _load_local_lint(page)
    document = "策" * 20_000
    page.locator("#lint-textarea").fill(document)
    page.locator("#lint-submit").click()

    expect(page.locator("#lint-result")).to_be_visible()
    expect(page.locator("#lint-summary-text")).to_have_text("已完成")
    assert len(requests) == 1
    request = requests[0]
    assert request.method == "POST"
    assert request.url == "https://local.structural.test/api/struct-lint/stream"
    assert request.post_data_json["document"] == document
    assert re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_-]{11,63}",
        request.post_data_json["client_request_id"],
    )
    assert document[:20] not in request.url


def test_lint_transport_error_can_retry_without_url_leak(page: Page):
    """A failed POST returns to input and a clean retry renders the stream."""
    requests = []

    def route_stream(route):
        requests.append(route.request)
        if len(requests) == 1:
            route.abort("failed")
            return
        route.fulfill(
            status=200,
            content_type="text/event-stream",
            body=_lint_stream(route.request, "retry ok"),
        )

    page.route("**/api/struct-lint/stream", route_stream)
    _load_local_lint(page)
    secret = "内部未发布的策略原文"
    page.locator("#lint-textarea").fill(secret)
    page.locator("#lint-submit").click()
    expect(page.locator("#lint-error")).to_be_visible()
    page.locator("#lint-retry").click()
    expect(page.locator("#lint-input")).to_be_visible()
    page.locator("#lint-submit").click()
    expect(page.locator("#lint-result")).to_be_visible()
    expect(page.locator("#lint-summary-text")).to_have_text("retry ok")
    assert len(requests) == 2
    assert all(request.method == "POST" for request in requests)
    assert all(secret not in request.url for request in requests)


def test_lint_new_run_aborts_previous_fetch(page: Page):
    """Starting another run cancels the prior body stream instead of racing it."""
    _load_local_lint(page)
    page.evaluate(
        """
        () => {
          window.__lintAbortCount = 0;
          window.fetch = (_url, options) => new Promise((_resolve, reject) => {
            options.signal.addEventListener('abort', () => {
              window.__lintAbortCount += 1;
              reject(new DOMException('aborted', 'AbortError'));
            }, { once: true });
          });
        }
        """
    )
    page.locator("#lint-textarea").fill("第一份私密文档")
    page.locator("#lint-submit").click()
    page.evaluate(
        """
        () => {
          document.querySelector('#lint-textarea').value = '第二份私密文档';
          document.querySelector('#lint-submit').click();
        }
        """
    )
    page.wait_for_function("window.__lintAbortCount === 1")
    assert page.evaluate("window.__lintAbortCount") == 1


@pytest.mark.post_deploy
def test_lint_page_loads(page: Page):
    """/lint should show the intro + document textarea + submit button."""
    page.goto(f"{BASE}/lint")
    expect(page.locator(".lint-input__title")).to_be_visible()
    expect(page.locator("#lint-textarea")).to_be_visible()
    expect(page.locator("#lint-submit")).to_be_visible()


@pytest.mark.post_deploy
def test_lint_empty_input_rejected(page: Page):
    """Submitting an empty document surfaces an inline error, no result."""
    page.goto(f"{BASE}/lint")
    page.click("#lint-submit")
    expect(page.locator("#lint-input-error")).to_be_visible()
    expect(page.locator("#lint-result")).to_be_hidden()


@pytest.mark.post_deploy
def test_lint_char_counter_updates(page: Page):
    """Typing into the textarea updates the character counter."""
    page.goto(f"{BASE}/lint")
    page.fill("#lint-textarea", "测试文档内容")
    expect(page.locator("#lint-charcount")).to_contain_text("6 / 20000")


@pytest.mark.post_deploy
def test_lint_submit_shows_summary_and_claims(page: Page):
    """A real document submit renders the summary banner + claim cards."""
    page.goto(f"{BASE}/lint")
    page.fill("#lint-textarea", _SAMPLE_DOC)
    page.click("#lint-submit")
    # Layered wait after streaming: loading panel must show within 10s
    # (proves the SSE `meta` event arrived), then the final result block
    # within 180s (`done` event delivers the rendered payload).
    expect(page.locator("#lint-loading")).to_be_visible(
        timeout=LINT_FIRST_EVENT_TIMEOUT_MS
    )
    expect(page.locator("#lint-result")).to_be_visible(timeout=LINT_RESULT_TIMEOUT_MS)
    expect(page.locator("#lint-summary-text")).not_to_be_empty()
    cards = page.locator(".lint-claim")
    assert cards.count() >= 1, "expected at least one claim card"


@pytest.mark.post_deploy
def test_lint_claim_card_has_review_priority_tag(page: Page):
    """Each claim card should carry review priority and a bound quote."""
    page.goto(f"{BASE}/lint")
    page.fill("#lint-textarea", _SAMPLE_DOC)
    page.click("#lint-submit")
    # Same layered SSE wait as test_lint_submit_shows_summary_and_claims.
    expect(page.locator("#lint-loading")).to_be_visible(
        timeout=LINT_FIRST_EVENT_TIMEOUT_MS
    )
    expect(page.locator("#lint-result")).to_be_visible(timeout=LINT_RESULT_TIMEOUT_MS)
    first = page.locator(".lint-claim").first
    expect(first.locator(".lint-tag--type")).to_be_visible()
    expect(first.locator(".lint-claim__quote")).to_be_visible()
    risk_tag = first.locator(
        ".lint-tag--risk-high, .lint-tag--risk-medium, .lint-tag--risk-low"
    )
    assert risk_tag.count() >= 1, "expected a review-priority tag on the claim card"
    assert risk_tag.first.inner_text() in {"优先复核", "建议复核", "常规复核"}
