#!/usr/bin/env bash
#
# measure-cls.sh — quick CLS measurement wrapper
#
# Usage:
#   bash scripts/measure-cls.sh [url] [viewport] [--throttle]
#
# viewport: desktop (default, 1920×1080) or mobile (375×667 + iOS UA)
# --throttle: emulate slow 3G (400 kbps, 400ms RTT) + 4× CPU on mobile
#
# Examples:
#   bash scripts/measure-cls.sh http://localhost:8128/discoveries.html mobile --throttle
#   bash scripts/measure-cls.sh https://beta.structural.bytedance.city/discoveries
#
# Built for W4-A (2026-05-14) /discoveries CLS regression hunt.
set -euo pipefail

URL="${1:-https://beta.structural.bytedance.city/discoveries}"
VIEWPORT="${2:-desktop}"
THROTTLE_FLAG="${3:-}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${REPO_ROOT}/.venv/bin/python"

# Fallback: try common monorepo / git-worktree sibling locations.
if [[ ! -x "$PY" ]]; then
  for cand in \
      "$HOME/Projects/structural-isomorphism/.venv/bin/python" \
      "$(git -C "$REPO_ROOT" rev-parse --show-toplevel 2>/dev/null)/.venv/bin/python"; do
    if [[ -x "$cand" ]]; then PY="$cand"; break; fi
  done
fi

if [[ ! -x "$PY" ]]; then
  echo "[measure-cls] Python venv not found at $PY"
  echo "[measure-cls] Run: python3 -m venv .venv && .venv/bin/pip install playwright && .venv/bin/python -m playwright install chromium"
  exit 2
fi

THROTTLE_PY="False"
if [[ "$THROTTLE_FLAG" == "--throttle" ]]; then
  THROTTLE_PY="True"
fi

"$PY" - "$URL" "$VIEWPORT" "$THROTTLE_PY" <<'PYEOF'
import sys
from playwright.sync_api import sync_playwright

url, vp, throttle_str = sys.argv[1], sys.argv[2], sys.argv[3]
throttle = throttle_str == "True"

CLS_EVAL = """
() => new Promise(resolve => {
  let cls = 0;
  const po = new PerformanceObserver(list => {
    for (const e of list.getEntries()) if (!e.hadRecentInput) cls += e.value;
  });
  po.observe({type: 'layout-shift', buffered: true});
  setTimeout(() => { po.disconnect(); resolve(cls); }, 5000);
})
"""

if vp == "mobile":
    w, h, is_mobile, ua = 375, 667, True, (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
        "Mobile/15E148 Safari/604.1"
    )
else:
    w, h, is_mobile, ua = 1920, 1080, False, None

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx_kwargs = {"viewport": {"width": w, "height": h}, "is_mobile": is_mobile}
    if is_mobile:
        ctx_kwargs["device_scale_factor"] = 2
    if ua:
        ctx_kwargs["user_agent"] = ua
    ctx = browser.new_context(**ctx_kwargs)
    page = ctx.new_page()

    if throttle:
        client = page.context.new_cdp_session(page)
        client.send("Network.emulateNetworkConditions", {
            "offline": False,
            "downloadThroughput": 400 * 1024 / 8,
            "uploadThroughput": 400 * 1024 / 8,
            "latency": 400,
        })
        if is_mobile:
            client.send("Emulation.setCPUThrottlingRate", {"rate": 4})

    page.goto(url, wait_until="load")
    page.wait_for_timeout(1000)
    cls = page.evaluate(CLS_EVAL)
    suffix = " (throttled)" if throttle else ""
    print(f"{vp} CLS{suffix} = {cls:.4f}  [url={url}]")
    # Web Vitals thresholds: good < 0.10, needs-improvement < 0.25.
    if cls < 0.1:
        rating = "good"
    elif cls < 0.25:
        rating = "needs-improvement"
    else:
        rating = "poor"
    print(f"  rating: {rating}")
    browser.close()
PYEOF
