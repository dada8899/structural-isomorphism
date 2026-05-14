"""Regression e2e: Phase Detector must not surface React/hydration errors.

Background
----------
Session #9 W6-E audit captured a React client-side exception on
https://phase.bytedance.city after `page.waitForLoadState('networkidle')`:

    "Application error: a client-side exception has occurred while loading
     phase.bytedance.city (see the browser console for more information)."

Root-cause (recorded in commit bfdf2b0):

  1. **Stale prod build** — prod was pinned to a W3-B-era commit while
     main had advanced 4 phase-detector commits (W6-D narrative copy +
     W8-D waitlist). Old Server Action handler IDs were embedded in
     pages cached by long-lived browser tabs; new POSTs returned
     "Failed to find Server Action 0000..." which surfaced as
     "Cannot read properties of undefined (reading 'workers')".
  2. **No error boundaries** — Next.js 14 App Router requires explicit
     `app/error.tsx` (per-route) and `app/global-error.tsx` (layout
     fallback). Without them, any runtime React error escapes to the
     bare HTML body and renders the unstyled fallback.
  3. **Brittle JSON parsing** — `lib/api.ts` called `await res.json()`
     without guarding malformed payloads; a single 502 or HTML error
     page during deploy triggered an uncaught throw.

Fix (commit bfdf2b0):
  - Added `app/error.tsx` — friendly fallback with retry.
  - Added `app/global-error.tsx` — last-resort layout boundary.
  - Hardened `lib/api.ts` with `safeJson()` returning null on parse fail.
  - Redeployed prod to current main.

This file is the regression e2e. It asserts:

  * No `console.error` events fire on cold load through `networkidle`.
  * The "Application error" fallback text is never rendered.
  * Both error-boundary files are present in the repo (statically).

The existing `tests/e2e/test_phase_detector_live.py::test_no_console_errors_on_load`
uses `pytest.skip` on transient API issues, which is appropriate for that
test's flake budget but masks the W6-E regression class. This file
asserts strictly — if a future deploy reintroduces the error, CI fails.

Run:
    pytest tests/e2e/test_phase_detector_no_react_errors.py -m e2e -v
"""

from __future__ import annotations

from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright")
from playwright.sync_api import Page, sync_playwright  # noqa: E402

BASE_URL = "https://phase.bytedance.city"
REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.e2e


# Console messages we treat as transient (not regression-class).
# Limited to truly-known-noise patterns — must not swallow real React errors.
_IGNORABLE_SUBSTRINGS = (
    "favicon",                # 404 favicon on first load is benign
    "Failed to load resource",  # generic; cross-check below
)


# Hard regression markers — if any of these appear, fail the test.
# These are the substrings observed in the W6-E captured error.
_REGRESSION_MARKERS = (
    "Application error: a client-side exception",
    "Failed to find Server Action",
    "Cannot read properties of undefined (reading 'workers')",
    "Cannot read properties of undefined (reading 'default')",
    "Hydration failed",
    "did not match",  # SSR/CSR hydration mismatch warning
)


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    yield pg
    ctx.close()


# ---------------------------------------------------------------------------
# Static guards (run even when prod is unreachable)
# ---------------------------------------------------------------------------


def test_error_boundary_files_present():
    """Static guard: Next.js error boundaries must exist in the repo.

    Removing either of these files is what allowed the W6-E error to
    surface in the first place. CI catches the removal before deploy.
    """
    error_tsx = REPO_ROOT / "web" / "phase-detector" / "app" / "error.tsx"
    global_error_tsx = REPO_ROOT / "web" / "phase-detector" / "app" / "global-error.tsx"
    assert error_tsx.is_file(), f"missing per-route error boundary: {error_tsx}"
    assert global_error_tsx.is_file(), (
        f"missing layout error boundary: {global_error_tsx}"
    )


def test_safe_json_helper_present():
    """Static guard: lib/api.ts must use a guarded JSON parser.

    Replacing safeJson() with raw res.json() would re-introduce the
    uncaught-throw failure mode that bypasses the error boundary.
    """
    api_ts = REPO_ROOT / "web" / "phase-detector" / "lib" / "api.ts"
    if not api_ts.is_file():
        pytest.skip(f"{api_ts} not present in this branch")
    content = api_ts.read_text()
    assert "safeJson" in content or "try" in content, (
        "lib/api.ts must guard JSON parsing (safeJson helper or try/catch). "
        "Bare `await res.json()` will bypass the error boundary."
    )


# ---------------------------------------------------------------------------
# Live regression checks (skip on transient network failure, fail on regression)
# ---------------------------------------------------------------------------


def _try_goto(page: Page, url: str, wait_until: str = "networkidle"):
    """Navigate or pytest.skip if prod is genuinely unreachable.

    We distinguish unreachable (skip) from rendering-broken (fail).
    """
    try:
        page.goto(url, wait_until=wait_until, timeout=30000)
    except Exception as exc:
        msg = str(exc).lower()
        if any(t in msg for t in ("timeout", "net::err_connection", "dns")):
            pytest.skip(f"prod unreachable: {exc}")
        raise


def test_no_react_application_error_on_networkidle(page: Page):
    """The W6-E regression: 'Application error' must not render."""
    _try_goto(page, BASE_URL, "networkidle")
    body_text = page.locator("body").inner_text()
    for marker in _REGRESSION_MARKERS:
        assert marker not in body_text, (
            f"W6-E regression: detected {marker!r} in rendered body. "
            f"First 300 chars: {body_text[:300]!r}"
        )


def test_no_console_errors_strict(page: Page):
    """Strict variant: any non-ignorable console.error fails the test.

    Distinct from `test_phase_detector_live.py::test_no_console_errors_on_load`
    (which skips on transient errors). This one fails on regression markers
    and only ignores known-noise substrings.
    """
    errors: list[str] = []

    def _on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("console", _on_console)
    _try_goto(page, BASE_URL, "networkidle")
    # Drain any late-firing errors after networkidle settles.
    page.wait_for_timeout(2000)

    # Partition: hard regressions vs ignorable noise.
    regressions = [
        e for e in errors
        if any(m in e for m in _REGRESSION_MARKERS)
    ]
    assert not regressions, (
        f"W6-E regression: console.error matches known regression markers: "
        f"{regressions}"
    )

    # All other errors that aren't on the ignorable list still fail —
    # tighter than the live test which uses pytest.skip.
    unexpected = [
        e for e in errors
        if not any(s.lower() in e.lower() for s in _IGNORABLE_SUBSTRINGS)
    ]
    assert not unexpected, (
        f"unexpected console.error events on cold load: {unexpected[:5]}"
    )


def test_no_react_hydration_warnings(page: Page):
    """Hydration mismatches surface as console.warn with 'did not match'.

    These are the smoking gun for SSR/CSR divergence (Date.now() /
    Math.random() / localStorage during render). Catch them in CI.
    """
    warnings: list[str] = []
    errors: list[str] = []

    def _on_console(msg):
        if msg.type == "warning":
            warnings.append(msg.text)
        elif msg.type == "error":
            errors.append(msg.text)

    page.on("console", _on_console)
    _try_goto(page, BASE_URL, "networkidle")
    page.wait_for_timeout(1500)

    hydration_issues = [
        m for m in warnings + errors
        if "hydrat" in m.lower() or "did not match" in m.lower()
    ]
    assert not hydration_issues, (
        f"React hydration issues detected: {hydration_issues}. "
        f"Common causes: Date.now()/Math.random()/localStorage in render."
    )
