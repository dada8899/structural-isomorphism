"""
Performance audit — Core Web Vitals (LCP, CLS, INP, TBT) across phase-detector
pages and viewports.

Drives a real Chromium via Playwright; collects:
  * LCP via PerformanceObserver(type: 'largest-contentful-paint')
  * CLS via PerformanceObserver(type: 'layout-shift') with the standard
    session-window accumulation (we keep the running total which is the
    standard CLS metric for monitoring).
  * TBT (total blocking time) via PerformanceObserver(type: 'longtask')
    summing (duration - 50) across the FCP→TTI window. Practical proxy:
    we sum all longtasks during a fixed observation window (5s after load).
  * INP — proxied via the worst Long Animation Frame (LoAF) observed
    during a programmatic interaction (click on the primary CTA / link
    inside the viewport). We use LoAF when available, falling back to
    the sum of (entry.duration) on `event` entries.
  * Transfer size + JS bytes via Performance.getEntries (resource).

Usage:
    .venv/bin/python scripts/perf_audit.py --base http://localhost:3017 \\
        --pages all --viewport both --out docs/performance/perf-audit.json

Pages list mirrors the W12-A accessibility audit so before/after comparisons
make sense.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

# 10 pages mirroring W12-A audit
PAGES: list[tuple[str, str]] = [
    ("landing", "/"),
    ("companies", "/companies"),
    ("company_AAPL", "/company/AAPL"),
    ("universality", "/universality"),
    ("universality_class", "/universality/self_organized_criticality"),
    ("compare", "/compare?tickers=AAPL,TSLA"),
    ("pricing", "/pricing"),
    ("backtest", "/backtest"),
    ("about", "/about"),
    ("methodology", "/methodology"),
]

VIEWPORTS = {
    "desktop": {"width": 1280, "height": 800, "isMobile": False},
    "mobile": {"width": 390, "height": 844, "isMobile": True},
}

# Inject before any page script runs so we catch every relevant entry.
INIT_SCRIPT = r"""
window.__perf = {
  lcp: 0,
  lcpElement: null,
  cls: 0,
  clsEntries: [],
  longTasks: [],   // {start, duration}
  loaf: [],        // long animation frames
  events: [],      // event timing entries
  navStart: performance.timeOrigin,
};

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      // LCP keeps the latest (largest) candidate
      window.__perf.lcp = e.startTime;
      window.__perf.lcpElement = e.element ? (e.element.tagName + (e.element.id ? '#' + e.element.id : '')) : null;
    }
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.hadRecentInput) {
        window.__perf.cls += e.value;
        window.__perf.clsEntries.push({ value: e.value, startTime: e.startTime });
      }
    }
  }).observe({ type: 'layout-shift', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      window.__perf.longTasks.push({ start: e.startTime, duration: e.duration });
    }
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      window.__perf.loaf.push({ start: e.startTime, duration: e.duration });
    }
  }).observe({ type: 'long-animation-frame', buffered: true });
} catch (e) {}

try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      window.__perf.events.push({
        name: e.name,
        duration: e.duration,
        processingStart: e.processingStart,
        startTime: e.startTime,
      });
    }
  }).observe({ type: 'event', buffered: true, durationThreshold: 16 });
} catch (e) {}
"""


def compute_tbt(long_tasks: list[dict[str, float]], fcp_ms: float, max_ms: float) -> float:
    """Total Blocking Time: sum(duration - 50) for longtasks within [FCP, TTI].

    We use [FCP, FCP + 5000] as the observation window since TTI is expensive to
    compute reliably from synthetic data.
    """
    tbt = 0.0
    for t in long_tasks:
        start = t["start"]
        dur = t["duration"]
        # Clip to observation window
        win_start = fcp_ms
        win_end = max_ms
        clipped_start = max(start, win_start)
        clipped_end = min(start + dur, win_end)
        if clipped_end <= clipped_start:
            continue
        effective = clipped_end - clipped_start
        if effective > 50:
            tbt += effective - 50
    return tbt


def collect_resource_sizes(resources: list[dict[str, Any]]) -> dict[str, float]:
    js_bytes = 0
    css_bytes = 0
    img_bytes = 0
    other_bytes = 0
    for r in resources:
        size = r.get("transferSize") or 0
        url = r.get("name", "")
        if url.endswith(".js") or "/_next/static/chunks/" in url:
            js_bytes += size
        elif url.endswith(".css"):
            css_bytes += size
        elif any(url.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".avif", ".svg", ".gif")):
            img_bytes += size
        else:
            other_bytes += size
    return {
        "js_kb": round(js_bytes / 1024, 1),
        "css_kb": round(css_bytes / 1024, 1),
        "img_kb": round(img_bytes / 1024, 1),
        "other_kb": round(other_bytes / 1024, 1),
        "total_kb": round((js_bytes + css_bytes + img_bytes + other_bytes) / 1024, 1),
    }


def audit_one(
    p,
    base_url: str,
    path: str,
    viewport_name: str,
    viewport: dict[str, Any],
    runs: int = 1,
) -> dict[str, Any]:
    results = []
    for run in range(runs):
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": viewport["width"], "height": viewport["height"]},
            is_mobile=viewport["isMobile"],
            device_scale_factor=2 if viewport["isMobile"] else 1,
            # Throttle CPU 4x to simulate mid-tier mobile when on mobile viewport
        )
        # CPU throttling via CDP for mobile
        page = context.new_page()
        page.add_init_script(INIT_SCRIPT)

        if viewport["isMobile"]:
            cdp = context.new_cdp_session(page)
            cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
            # Simulate slow 4G
            cdp.send(
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 150,
                    "downloadThroughput": 1.5 * 1024 * 1024 / 8,
                    "uploadThroughput": 750 * 1024 / 8,
                },
            )

        url = f"{base_url}{path}"
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else 0
        except Exception as exc:
            browser.close()
            results.append({"error": f"navigation failed: {exc}"})
            continue

        # Wait for network idle + extra settle time so async chunks/images stop shifting
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(2000)

        # Try interacting with a clickable element to get INP measurement
        try:
            page.evaluate("window.scrollBy(0, 200)")
            page.wait_for_timeout(300)
            page.evaluate("window.scrollBy(0, -200)")
            page.wait_for_timeout(300)
            # Click on first visible link/button to measure event timing
            page.evaluate(
                """
                () => {
                  const candidate = Array.from(document.querySelectorAll('a, button')).find(el => {
                    const rect = el.getBoundingClientRect();
                    return rect.width > 10 && rect.height > 10 && rect.top >= 0 && rect.top < window.innerHeight - 100;
                  });
                  if (candidate) {
                    candidate.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    candidate.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                  }
                }
            """
            )
            page.wait_for_timeout(500)
        except Exception:
            pass

        # Compute FCP from paint entries
        fcp_ms = page.evaluate(
            """
            () => {
              const entry = performance.getEntriesByType('paint').find(e => e.name === 'first-contentful-paint');
              return entry ? entry.startTime : 0;
            }
        """
        )

        perf = page.evaluate("() => JSON.parse(JSON.stringify(window.__perf))")
        resources = page.evaluate(
            """
            () => performance.getEntriesByType('resource').map(r => ({
              name: r.name,
              transferSize: r.transferSize,
              encodedBodySize: r.encodedBodySize,
              duration: r.duration,
              initiatorType: r.initiatorType,
            }))
        """
        )

        # Navigation timing
        nav = page.evaluate(
            """
            () => {
              const n = performance.getEntriesByType('navigation')[0];
              if (!n) return null;
              return {
                domContentLoadedEventEnd: n.domContentLoadedEventEnd,
                loadEventEnd: n.loadEventEnd,
                responseEnd: n.responseEnd,
                transferSize: n.transferSize,
              };
            }
        """
        )

        long_tasks = perf.get("longTasks", [])
        loaf = perf.get("loaf", [])
        events = perf.get("events", [])

        # TBT calculation
        tbt = compute_tbt(long_tasks, fcp_ms, fcp_ms + 5000)

        # INP proxy: worst event duration OR worst LoAF duration
        worst_event = max((e["duration"] for e in events), default=0)
        worst_loaf = max((e["duration"] for e in loaf), default=0)
        inp_proxy = max(worst_event, worst_loaf)

        sizes = collect_resource_sizes(resources)

        results.append(
            {
                "status": status,
                "lcp_ms": round(perf.get("lcp", 0), 1),
                "lcp_element": perf.get("lcpElement"),
                "cls": round(perf.get("cls", 0), 4),
                "fcp_ms": round(fcp_ms, 1),
                "tbt_ms": round(tbt, 1),
                "inp_proxy_ms": round(inp_proxy, 1),
                "long_task_count": len(long_tasks),
                "long_task_total_ms": round(sum(t["duration"] for t in long_tasks), 1),
                "loaf_count": len(loaf),
                "event_count": len(events),
                "transfer_kb": sizes,
                "resource_count": len(resources),
                "dom_loaded_ms": round(nav["domContentLoadedEventEnd"], 1) if nav else 0,
                "load_event_ms": round(nav["loadEventEnd"], 1) if nav else 0,
            }
        )

        browser.close()

    # Aggregate runs (median for stability)
    if not results or "error" in results[0]:
        return {"error": results[0].get("error", "no results"), "runs": runs}

    def median(key: str) -> float:
        return round(statistics.median([r[key] for r in results if isinstance(r.get(key), (int, float))]), 2)

    agg = {
        "runs": runs,
        "status": results[-1]["status"],
        "lcp_ms": median("lcp_ms"),
        "lcp_element": results[-1].get("lcp_element"),
        "cls": median("cls"),
        "fcp_ms": median("fcp_ms"),
        "tbt_ms": median("tbt_ms"),
        "inp_proxy_ms": median("inp_proxy_ms"),
        "long_task_count": results[-1]["long_task_count"],
        "long_task_total_ms": results[-1]["long_task_total_ms"],
        "transfer_kb": results[-1]["transfer_kb"],
        "resource_count": results[-1]["resource_count"],
        "dom_loaded_ms": results[-1]["dom_loaded_ms"],
        "load_event_ms": results[-1]["load_event_ms"],
        "raw_runs": results if runs > 1 else None,
    }
    return agg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:3017", help="base URL")
    parser.add_argument("--pages", default="all", help="comma-separated page keys or 'all'")
    parser.add_argument("--viewport", default="both", choices=["desktop", "mobile", "both"])
    parser.add_argument("--out", default="docs/performance/perf-audit.json")
    parser.add_argument("--runs", type=int, default=1, help="median across N runs")
    args = parser.parse_args()

    if args.pages == "all":
        selected = PAGES
    else:
        keys = set(args.pages.split(","))
        selected = [(k, p) for k, p in PAGES if k in keys]

    viewports = {"desktop": "desktop", "mobile": "mobile"} if args.viewport == "both" else {args.viewport: args.viewport}

    print(f"Auditing {len(selected)} pages × {len(viewports)} viewports = {len(selected) * len(viewports)} runs (base: {args.base})", flush=True)
    print(f"  pages={[k for k, _ in selected]}", flush=True)

    out: dict[str, Any] = {
        "base_url": args.base,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "runs_per_page": args.runs,
        "pages": {},
    }

    with sync_playwright() as p:
        for key, path in selected:
            out["pages"][key] = {"path": path}
            for vp_name in viewports:
                vp = VIEWPORTS[vp_name]
                t0 = time.time()
                result = audit_one(p, args.base, path, vp_name, vp, runs=args.runs)
                elapsed = time.time() - t0
                out["pages"][key][vp_name] = result
                print(
                    f"  [{vp_name:7}] {key:24} {path:40} LCP={result.get('lcp_ms', 0):>6.0f}ms CLS={result.get('cls', 0):.3f} TBT={result.get('tbt_ms', 0):>5.0f}ms INP*={result.get('inp_proxy_ms', 0):>5.0f}ms JS={result.get('transfer_kb', {}).get('js_kb', 0):>5.0f}KB ({elapsed:.1f}s)",
                    flush=True,
                )

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=2))
    print(f"\nWrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
