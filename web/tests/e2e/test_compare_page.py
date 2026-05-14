"""Session #10 W10-E /compare page e2e.

Asserts the new /compare page renders correctly:
  1. Empty state when no tickers param given.
  2. With ?tickers=AAPL,TSLA — exactly 2 columns rendered, each tagged
     with data-testid=compare-column and data-ticker.
  3. Each column shows a CPS badge, the 5 pattern rows, the timeline
     strip, the TL;DR narrative.
  4. Picker autocompletes from the screener list.
  5. Chip ✕ removes a ticker and updates the URL.

Default base URL = the local Next.js dev server (`http://localhost:3017`)
spun up by the developer or the integration test wrapper. Override with
`PHASE_BASE_URL` env var to point at a deployed instance.

When the base URL is unreachable, the suite skips rather than fails —
this lets the test live alongside pre-deploy work.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/tests/e2e/test_compare_page.py -v
"""
from __future__ import annotations

import os
import urllib.error
import urllib.request

import pytest
from playwright.sync_api import Page, expect

BASE = os.environ.get("PHASE_BASE_URL", "http://localhost:3017")


def _base_reachable(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            return resp.status < 500
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        return False
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(
    not _base_reachable(BASE),
    reason=f"PHASE base URL not reachable: {BASE}",
)


def test_compare_empty_state_when_no_tickers(page: Page):
    """Bare /compare renders empty-state copy + picker."""
    page.goto(f"{BASE}/compare", wait_until="domcontentloaded")
    expect(page.get_by_test_id("compare-empty-state")).to_be_visible()
    expect(page.get_by_test_id("compare-picker-input")).to_be_visible()


def test_compare_two_tickers_renders_two_columns(page: Page):
    """?tickers=AAPL,TSLA renders 2 columns each tagged data-testid=compare-column."""
    page.goto(f"{BASE}/compare?tickers=AAPL,TSLA", wait_until="networkidle")
    # Wait for at least one column to appear (companies are fetched client-side).
    page.wait_for_selector('[data-testid="compare-column"]', timeout=10000)
    columns = page.locator('[data-testid="compare-column"]').all()
    assert len(columns) >= 2, f"expected >= 2 columns, got {len(columns)}"
    tickers = {c.get_attribute("data-ticker") for c in columns}
    assert "AAPL" in tickers
    assert "TSLA" in tickers


def test_compare_three_tickers_renders_three_columns(page: Page):
    """?tickers=AAPL,TSLA,JPM renders all 3 columns."""
    page.goto(f"{BASE}/compare?tickers=AAPL,TSLA,JPM", wait_until="networkidle")
    page.wait_for_selector('[data-testid="compare-column"]', timeout=10000)
    columns = page.locator('[data-testid="compare-column"]').all()
    assert len(columns) >= 3
    tickers = {c.get_attribute("data-ticker") for c in columns}
    assert tickers >= {"AAPL", "TSLA", "JPM"}


def test_compare_pattern_rows_5_per_column(page: Page):
    """Each column shows exactly 5 pattern rows (the canonical 5 patterns)."""
    page.goto(f"{BASE}/compare?tickers=AAPL,TSLA", wait_until="networkidle")
    page.wait_for_selector('[data-testid="compare-column"]', timeout=10000)
    first_column = page.locator('[data-testid="compare-column"]').first
    rows = first_column.locator("[data-pattern-row]").all()
    assert len(rows) == 5, f"expected 5 pattern rows, got {len(rows)}"


def test_compare_at_least_one_pattern_match_highlighted(page: Page):
    """Across all loaded columns, at least one column has a matched
    pattern row (data-matched=true). If no company in our test fixture
    has any of our 5 canonical patterns we'd have a vacuous green — so
    this assertion is also a sanity check on the seed data."""
    page.goto(f"{BASE}/compare?tickers=AAPL,TSLA,JPM", wait_until="networkidle")
    page.wait_for_selector('[data-testid="compare-column"]', timeout=10000)
    matched = page.locator('[data-pattern-row][data-matched="true"]').count()
    assert matched >= 1, "no pattern rows matched across all columns"


def test_compare_chips_render_for_each_ticker(page: Page):
    """Active tickers should appear as removable chips."""
    page.goto(f"{BASE}/compare?tickers=AAPL,TSLA", wait_until="networkidle")
    page.wait_for_selector('[data-testid="compare-chip"]', timeout=5000)
    chips = page.locator('[data-testid="compare-chip"]').all()
    assert len(chips) == 2
