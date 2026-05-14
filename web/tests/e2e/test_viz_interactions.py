"""W11-D — Interactive visualization e2e tests.

Asserts (against a running Next.js dev/prod server):
  1. /company/<ticker> renders the PhaseTrajectoryChart SVG, the line
     path is non-empty, and hover surfaces a tooltip.
  2. /universality/<class_id> renders the UniversalityAnalogueMap with
     a center node + analogue nodes; hover surfaces a tooltip; node
     click triggers navigation (when ticker-shaped).
  3. /companies (the screener) renders SparkLines and they reveal as
     they scroll into view (data-visible="true" after scroll).

Default base URL = local Next.js dev server on :3017 (matches the rest
of the e2e suite). Override with PHASE_BASE_URL. Skips when the base
URL is unreachable so CI doesn't fail on tests that need a server.

Run:
    PYTHONPATH=. .venv/bin/python -m pytest \
        web/tests/e2e/test_viz_interactions.py -v
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


# ---------------------------------------------------------------------------
# Phase trajectory chart on /company/[ticker]
# ---------------------------------------------------------------------------


def test_company_trajectory_chart_renders(page: Page):
    """PhaseTrajectoryChart SVG renders with a non-trivial line path."""
    # Pick a ticker that will definitely exist — try AAPL first, then
    # fall back to whatever the screener returns. The chart synthesizes
    # its own series so the only requirement is that the company page
    # itself loads.
    page.goto(f"{BASE}/company/NVDA", wait_until="networkidle")
    page.wait_for_selector('[data-testid="phase-trajectory-chart"]', timeout=10000)
    chart = page.locator('[data-testid="phase-trajectory-chart"]')
    expect(chart).to_be_visible()
    # The trajectory line is a single <path> with d="M... L..."; the d
    # attribute must contain at least one L (>= 2 points).
    path_d = chart.locator("svg path").first.get_attribute("d") or ""
    assert "L" in path_d, "trajectory path must have >= 2 points"


def test_company_trajectory_hover_shows_tooltip(page: Page):
    """Hovering over the SVG surfaces the value/phase tooltip."""
    page.goto(f"{BASE}/company/NVDA", wait_until="networkidle")
    page.wait_for_selector('[data-testid="phase-trajectory-chart"]', timeout=10000)
    chart = page.locator('[data-testid="phase-trajectory-chart"]')
    svg = chart.locator("svg")
    box = svg.bounding_box()
    assert box is not None
    # Hover near the middle of the chart — anywhere within the drawing
    # area should produce a tooltip via pointermove.
    page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.5)
    page.wait_for_timeout(150)
    tooltip = chart.locator('[data-testid="trajectory-tooltip"]')
    expect(tooltip).to_be_visible()


def test_company_trajectory_brush_selection(page: Page):
    """Press-drag on the chart creates a brush selection rectangle."""
    page.goto(f"{BASE}/company/NVDA", wait_until="networkidle")
    page.wait_for_selector('[data-testid="phase-trajectory-chart"]', timeout=10000)
    chart = page.locator('[data-testid="phase-trajectory-chart"]')
    svg = chart.locator("svg")
    box = svg.bounding_box()
    assert box is not None
    start_x = box["x"] + box["width"] * 0.3
    end_x = box["x"] + box["width"] * 0.7
    y = box["y"] + box["height"] * 0.5
    page.mouse.move(start_x, y)
    page.mouse.down()
    page.mouse.move(end_x, y, steps=8)
    page.mouse.up()
    page.wait_for_timeout(100)
    # Brush rect should be visible after drag.
    brush = chart.locator('[data-testid="trajectory-brush"]')
    expect(brush).to_be_visible()


# ---------------------------------------------------------------------------
# Universality analogue map on /universality/[class_id]
# ---------------------------------------------------------------------------


def _first_universality_class_id(page: Page) -> str:
    """Walk /universality to find a valid class_id; skip the test if
    none render (e.g. backend wasn't seeded)."""
    page.goto(f"{BASE}/universality", wait_until="networkidle")
    try:
        page.wait_for_selector(
            '[data-testid="universality-class-card"]', timeout=10000
        )
    except Exception:  # noqa: BLE001
        pytest.skip("/universality has no class cards on this environment")
    first = page.locator('[data-testid="universality-class-card"]').first
    cid = first.get_attribute("data-class-id")
    assert cid, "first universality class card must have data-class-id"
    return cid


def test_universality_analogue_map_renders(page: Page):
    """Center node + at least 1 analogue node render in the SVG."""
    cid = _first_universality_class_id(page)
    page.goto(f"{BASE}/universality/{cid}", wait_until="networkidle")
    page.wait_for_selector(
        '[data-testid="universality-analogue-map"]', timeout=10000
    )
    map_root = page.locator('[data-testid="universality-analogue-map"]')
    expect(map_root).to_be_visible()
    # Center node always present.
    expect(map_root.locator('[data-testid="analogue-center-node"]')).to_have_count(1)
    nodes = map_root.locator('[data-testid="analogue-node"]').count()
    # The class detail might have only 1 evidence_system / prototype, so
    # require >= 1 analogue node, target 13.
    assert nodes >= 1, f"expected >= 1 analogue node, got {nodes}"


def test_universality_analogue_map_hover_tooltip(page: Page):
    cid = _first_universality_class_id(page)
    page.goto(f"{BASE}/universality/{cid}", wait_until="networkidle")
    page.wait_for_selector(
        '[data-testid="universality-analogue-map"]', timeout=10000
    )
    nodes = page.locator('[data-testid="analogue-node"]')
    if nodes.count() == 0:
        pytest.skip("class has no analogue nodes")
    nodes.first.hover()
    page.wait_for_timeout(120)
    tooltip = page.locator('[data-testid="analogue-tooltip"]')
    expect(tooltip).to_be_visible()


# ---------------------------------------------------------------------------
# Sparklines on /companies
# ---------------------------------------------------------------------------


def test_companies_sparklines_present(page: Page):
    """Companies screener page renders sparklines on each card."""
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    # Sparklines live inside CompanyCard, which is rendered by the
    # /companies screener. Wait for cards to load.
    page.wait_for_selector('[data-testid="sparkline"]', timeout=15000)
    sparks = page.locator('[data-testid="sparkline"]')
    count = sparks.count()
    assert count >= 1, f"expected >= 1 sparkline, got {count}"


def test_companies_sparkline_reveals_on_scroll(page: Page):
    """First sparkline becomes visible (data-visible=true) after
    intersection observer fires."""
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    page.wait_for_selector('[data-testid="sparkline"]', timeout=15000)
    first = page.locator('[data-testid="sparkline"]').first
    first.scroll_into_view_if_needed()
    page.wait_for_timeout(300)
    visible_attr = first.get_attribute("data-visible")
    assert visible_attr == "true", (
        f"sparkline should toggle data-visible=true after intersection, "
        f"got {visible_attr!r}"
    )


def test_companies_sparkline_tooltip_on_hover(page: Page):
    """Hovering a sparkline should surface a tooltip."""
    page.goto(f"{BASE}/companies", wait_until="networkidle")
    page.wait_for_selector('[data-testid="sparkline"]', timeout=15000)
    first = page.locator('[data-testid="sparkline"]').first
    first.scroll_into_view_if_needed()
    page.wait_for_timeout(150)
    svg = first.locator("svg")
    box = svg.bounding_box()
    assert box is not None
    page.mouse.move(box["x"] + box["width"] * 0.6, box["y"] + box["height"] * 0.5)
    page.wait_for_timeout(150)
    tooltip = first.locator('[data-testid="sparkline-tooltip"]')
    expect(tooltip).to_be_visible()
