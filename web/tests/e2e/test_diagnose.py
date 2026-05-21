"""Feature F — 结构诊断 /diagnose page e2e (Session ***REMOVED***18).

Asserts the diagnose page renders its contractual blocks and the
input → loading → report / error flow works in a real browser.

The diagnose endpoint needs a live LLM; in environments without an
OPENROUTER_API_KEY the backend returns 503, so this test asserts the
*frontend* behaviour (input view, validation, error state) which is what
e2e can verify deterministically without a real model call.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \\
        web/tests/e2e/test_diagnose.py -v

Base URL: STRUCTURAL_BASE (default https://structural.bytedance.city).
Self-skips when the base URL is unreachable so it can live alongside
pre-deploy work.
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import Page, expect

BASE = os.environ.get(
    "STRUCTURAL_BASE", "https://structural.bytedance.city"
).rstrip("/")


def _base_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "/diagnose", timeout=4) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False
    except Exception:  ***REMOVED*** noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _base_reachable(BASE),
    reason=f"STRUCTURAL base URL not reachable: {BASE}",
)


def test_diagnose_page_renders_input(page: Page):
    """The page loads with the input form and quick-example chips."""
    page.goto(f"{BASE}/diagnose", wait_until="networkidle")
    expect(page.locator(".diagnose-intro__title")).to_be_visible()
    expect(page.locator("***REMOVED***diagnose-textarea")).to_be_visible()
    expect(page.locator("***REMOVED***diagnose-submit")).to_be_visible()
    ***REMOVED*** At least the 3 quick examples.
    assert page.locator(".diagnose-example").count() >= 3


def test_diagnose_example_fills_textarea(page: Page):
    """Clicking a quick-example chip populates the textarea."""
    page.goto(f"{BASE}/diagnose", wait_until="networkidle")
    page.locator(".diagnose-example").first.click()
    value = page.locator("***REMOVED***diagnose-textarea").input_value()
    assert len(value) > 12


def test_diagnose_short_input_rejected_inline(page: Page):
    """Submitting too-short text keeps the user on the input view."""
    page.goto(f"{BASE}/diagnose", wait_until="networkidle")
    page.locator("***REMOVED***diagnose-textarea").fill("太短")
    page.locator("***REMOVED***diagnose-submit").click()
    ***REMOVED*** Still on the input section — no loading / report shown.
    expect(page.locator("***REMOVED***diagnose-input-section")).to_be_visible()
    expect(page.locator("***REMOVED***diagnose-textarea")).to_have_class(
        __import__("re").compile(r"is-invalid")
    )


def test_diagnose_submit_reaches_loading_or_result(page: Page):
    """A real submission transitions out of the input view.

    Depending on whether the deployed backend has an LLM key, the flow
    ends at either the report or the error view — both are acceptable;
    what we assert is that the input view is left and a terminal state
    is reached (no infinite loading).
    """
    page.goto(f"{BASE}/diagnose", wait_until="networkidle")
    page.locator("***REMOVED***diagnose-textarea").fill(
        "我们是一家 30 人的公司，扩张很快。最近每加一个人效率反而更慢，"
        "开会变多、决策变慢、老员工抱怨。流程改过两次，情况没变化。"
    )
    page.locator("***REMOVED***diagnose-submit").click()
    ***REMOVED*** Wait for a terminal view — report or error — within 60s.
    page.wait_for_selector(
        "***REMOVED***diagnose-report:not([hidden]), ***REMOVED***diagnose-error:not([hidden])",
        timeout=60_000,
    )
    report_visible = page.locator("***REMOVED***diagnose-report").is_visible()
    error_visible = page.locator("***REMOVED***diagnose-error").is_visible()
    assert report_visible or error_visible
    if report_visible:
        ***REMOVED*** Primary structural-state card must carry a non-empty name.
        name = page.locator("***REMOVED***diagnose-state-name").inner_text()
        assert name.strip()
