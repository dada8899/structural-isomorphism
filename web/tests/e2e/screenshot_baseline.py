"""Capture baseline screenshots of key pages (pre-deploy state).

Run from repo root:
    source .venv-e2e/bin/activate
    python3 web/tests/e2e/screenshot_baseline.py

Output: docs/screenshots/session-7/baseline/<name>.png

After W3-C ships new /index.html, run again with output dir
`docs/screenshots/session-7/post-deploy/` to compare.
"""
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

OUTPUT = Path("docs/screenshots/session-7/baseline")
OUTPUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("home-desktop", "https://beta.structural.bytedance.city/", {"width": 1280, "height": 800}),
    ("home-mobile", "https://beta.structural.bytedance.city/", {"width": 375, "height": 812}),
    ("search-desktop", "https://beta.structural.bytedance.city/search.html?q=bank+run", {"width": 1280, "height": 800}),
    ("analyze-desktop", "https://beta.structural.bytedance.city/analyze.html", {"width": 1280, "height": 800}),
    ("discoveries-desktop", "https://beta.structural.bytedance.city/discoveries", {"width": 1280, "height": 800}),
    ("learn-desktop", "https://beta.structural.bytedance.city/learn", {"width": 1280, "height": 800}),
    ("phase-desktop", "https://phase.bytedance.city/", {"width": 1280, "height": 800}),
    ("legacy-structural-desktop", "https://structural.bytedance.city/", {"width": 1280, "height": 800}),
]


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for name, url, vp in PAGES:
            print(f"Capturing {name} -> {url}", flush=True)
            try:
                context = browser.new_context(viewport=vp)
                page = context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                # Give a moment for late-arriving content (CSS, fonts)
                page.wait_for_timeout(1500)
                path = OUTPUT / f"{name}.png"
                page.screenshot(path=str(path), full_page=True)
                size = path.stat().st_size if path.exists() else 0
                print(f"  OK  {path}  ({size} bytes)", flush=True)
                results.append((name, "ok", size))
                context.close()
            except Exception as e:
                print(f"  FAIL  {e}", flush=True)
                results.append((name, "fail", str(e)))
        browser.close()
    print(f"\nSaved {sum(1 for _, s, _ in results if s == 'ok')}/{len(results)} screenshots to {OUTPUT}/", flush=True)
    # Exit code: 0 if at least half succeeded
    ok = sum(1 for _, s, _ in results if s == "ok")
    return 0 if ok >= len(results) // 2 else 1


if __name__ == "__main__":
    sys.exit(main())
