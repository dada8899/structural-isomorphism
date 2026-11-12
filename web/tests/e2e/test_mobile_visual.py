"""W12-C (session #10): mobile visual regression — 4 viewports × 8 pages.

Compares screenshots of key pages at 4 device viewports against committed
baselines. Fails if average per-pixel diff exceeds 5% (>5% of the image
changed by >32 luminance levels). On first run with `--update-baselines`
the test writes baselines + skips comparison.

Viewports:
  - iPhone SE         375 × 812  (tightest mobile)
  - iPhone 14 Pro Max 414 × 896  (typical large iOS phone)
  - iPad portrait     768 × 1024 (tablet column tipping point)
  - iPad landscape    1024 × 768 (full-bleed wide layout)

Pages (8):
  /, /companies, /company/AAPL, /universality, /pricing,
  /backtest, /methodology, /about

Run (against deployed beta):
    PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_mobile_visual.py -v

Run against a local dev server:
    MOBILE_VISUAL_BASE_URL=http://localhost:3000 \
        PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_mobile_visual.py -v

Update baselines after intentional UI changes:
    UPDATE_VISUAL_BASELINES=1 \
        PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_mobile_visual.py -v
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Iterator

import pytest

# Default base URL. Points at the production beta so the test works without
# a local dev server. Override with MOBILE_VISUAL_BASE_URL.
DEFAULT_BASE = "https://phase.bytedance.city"
BASE = os.environ.get("MOBILE_VISUAL_BASE_URL", DEFAULT_BASE).rstrip("/")

# Where baselines + diffs live. Inside repo, gitignored except `.gitkeep` and
# committed baseline images.
SCREENSHOT_ROOT = Path(__file__).parent / "screenshots" / "mobile-visual"
BASELINE_DIR = SCREENSHOT_ROOT / "baseline"
ACTUAL_DIR = SCREENSHOT_ROOT / "actual"
DIFF_DIR = SCREENSHOT_ROOT / "diff"

UPDATE_BASELINES = os.environ.get("UPDATE_VISUAL_BASELINES") == "1"

# Diff threshold: 5% of pixels can differ.
PIXEL_DIFF_BUDGET = 0.05

# Viewport matrix. (slug, width, height, isMobile).
VIEWPORTS = [
    ("iphone-se", 375, 812, True),
    ("iphone-pro-max", 414, 896, True),
    ("ipad-portrait", 768, 1024, True),
    ("ipad-landscape", 1024, 768, False),
]

# Page paths. Keep stable; if a page disappears upstream the test will
# capture the 404 page and fail loudly which is the desired behavior.
PAGES = [
    ("home", "/"),
    ("companies", "/companies"),
    ("company-aapl", "/company/AAPL"),
    ("universality", "/universality"),
    ("pricing", "/pricing"),
    ("backtest", "/backtest"),
    ("methodology", "/methodology"),
    ("about", "/about"),
]


def _ensure_dirs() -> None:
    for d in (BASELINE_DIR, ACTUAL_DIR, DIFF_DIR):
        d.mkdir(parents=True, exist_ok=True)


@pytest.fixture(scope="module")
def chromium_browser(playwright_instance):
    browser = playwright_instance.chromium.launch(headless=True)
    yield browser
    browser.close()


def _have_image_libs() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


def _compute_pixel_diff(actual_path: Path, baseline_path: Path, diff_path: Path) -> float:
    """Return fraction of pixels that differ by > 32 luminance levels.

    Pure-Python diff via Pillow to avoid playwright-pytest extra dep.
    """
    from PIL import Image, ImageChops

    a = Image.open(actual_path).convert("RGB")
    b = Image.open(baseline_path).convert("RGB")
    # Resize baseline to actual size if they drift slightly (DPR, OS chrome).
    if a.size != b.size:
        b = b.resize(a.size)
    diff = ImageChops.difference(a, b)
    # Sum per-pixel max channel diff; count pixels above threshold.
    bands = diff.split()
    # Use 'V' channel (max of R,G,B) as a proxy via .convert('L').
    luminance_diff = diff.convert("L")
    pixels = list(luminance_diff.getdata())
    total = len(pixels)
    above = sum(1 for p in pixels if p > 32)
    # Save the diff for human inspection.
    diff.save(diff_path)
    return above / total if total else 0.0


def _matrix() -> Iterator[tuple[str, int, int, bool, str, str]]:
    for vp_slug, w, h, is_mobile in VIEWPORTS:
        for page_slug, page_path in PAGES:
            yield vp_slug, w, h, is_mobile, page_slug, page_path


@pytest.mark.parametrize(
    "vp_slug,width,height,is_mobile,page_slug,page_path",
    list(_matrix()),
    ids=[f"{p}@{v}" for v, _, _, _, p, _ in _matrix()],
)
def test_visual(chromium_browser, vp_slug, width, height, is_mobile, page_slug, page_path):
    """Capture one viewport × page and compare to baseline."""
    _ensure_dirs()
    name = f"{page_slug}--{vp_slug}.png"
    actual = ACTUAL_DIR / name
    baseline = BASELINE_DIR / name
    diff = DIFF_DIR / name

    context = chromium_browser.new_context(
        viewport={"width": width, "height": height},
        is_mobile=is_mobile,
        device_scale_factor=2 if is_mobile else 1,
    )
    page = context.new_page()
    url = f"{BASE}{page_path}"
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            pytest.skip(f"upstream {url} unreachable: {e}")
        # Brief settle for fonts + first paint.
        page.wait_for_timeout(1500)
        # Capture above-the-fold only (full_page=False) — avoids long pages
        # ballooning baseline storage and gives us a stable hero shot.
        page.screenshot(path=str(actual), full_page=False)
    finally:
        context.close()

    if UPDATE_BASELINES or not baseline.exists():
        # First run or explicit update: copy actual → baseline.
        baseline.parent.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(actual.read_bytes())
        pytest.skip(f"baseline {'updated' if UPDATE_BASELINES else 'created'}: {baseline}")

    if not _have_image_libs():
        pytest.skip("Pillow not installed; cannot diff. `pip install Pillow`.")

    pct = _compute_pixel_diff(actual, baseline, diff)
    msg = (
        f"visual diff {pct*100:.2f}% > budget {PIXEL_DIFF_BUDGET*100:.0f}% "
        f"for {name}\n"
        f"  actual:   {actual}\n"
        f"  baseline: {baseline}\n"
        f"  diff:     {diff}\n"
        f"Update baseline with UPDATE_VISUAL_BASELINES=1 if change is intended."
    )
    assert pct <= PIXEL_DIFF_BUDGET, msg


def test_matrix_size():
    """Sanity: 4 viewports × 8 pages = 32 cases."""
    cases = list(_matrix())
    assert len(cases) == 32, f"expected 32 visual-test cases, got {len(cases)}"
