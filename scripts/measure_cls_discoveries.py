"""
Measure Cumulative Layout Shift (CLS) for /discoveries page.

Drives a real Chromium via Playwright, hooks PerformanceObserver to accumulate
layout-shift entries, waits for network idle + a bit more (so async chunks settle),
then reports the final CLS value.

Usage:
    ./.venv/bin/python scripts/measure_cls_discoveries.py [URL]

Default URL: https://beta.structural.bytedance.city/discoveries

Exit code 0 if CLS < 0.1 (Web Vitals "good"), 1 if >= 0.1.
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

DEFAULT_URL = "https://beta.structural.bytedance.city/discoveries"

# Inject before any page script runs so we catch shifts from the very first frame.
INIT_SCRIPT = """
window.__clsEntries = [];
window.__clsValue = 0;
try {
  const po = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
      // Per spec, ignore shifts with hadRecentInput (user-initiated like tap/scroll).
      if (!entry.hadRecentInput) {
        window.__clsValue += entry.value;
        window.__clsEntries.push({
          value: entry.value,
          startTime: entry.startTime,
          sources: (entry.sources || []).map(s => ({
            node: s.node ? (s.node.nodeName + (s.node.id ? '#' + s.node.id : '') + (s.node.className ? '.' + String(s.node.className).split(' ').join('.') : '')) : '?',
            prevRect: s.previousRect ? {x: s.previousRect.x, y: s.previousRect.y, w: s.previousRect.width, h: s.previousRect.height} : null,
            currRect: s.currentRect ? {x: s.currentRect.x, y: s.currentRect.y, w: s.currentRect.width, h: s.currentRect.height} : null,
          })),
        });
      }
    }
  });
  po.observe({ type: 'layout-shift', buffered: true });
  window.__clsObserver = po;
} catch (e) {
  window.__clsError = String(e);
}
"""


def measure(url: str) -> dict:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (CLS-measurement) Playwright",
        )
        ctx.add_init_script(INIT_SCRIPT)
        page = ctx.new_page()

        t0 = time.time()
        page.goto(url, wait_until="networkidle", timeout=45_000)
        # Wait a bit more for any deferred async rendering (i18n, discoveries.js fetch).
        page.wait_for_timeout(3000)
        # Trigger a small viewport tick to flush any pending observer callbacks.
        page.evaluate("() => window.scrollBy(0, 1)")
        page.wait_for_timeout(500)
        page.evaluate("() => window.scrollBy(0, -1)")
        page.wait_for_timeout(500)

        result = page.evaluate(
            "() => ({"
            " cls: window.__clsValue,"
            " entries: window.__clsEntries,"
            " err: window.__clsError || null"
            "})"
        )
        result["url"] = url
        result["elapsed_s"] = round(time.time() - t0, 2)

        browser.close()
        return result


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    res = measure(url)
    cls = res.get("cls", 0) or 0
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print(f"\n== CLS: {cls:.4f}  ({'GOOD' if cls < 0.1 else 'NEEDS IMPROVEMENT' if cls < 0.25 else 'POOR'})", file=sys.stderr)
    return 0 if cls < 0.1 else 1


if __name__ == "__main__":
    sys.exit(main())
