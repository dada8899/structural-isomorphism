#!/usr/bin/env python3
"""Layer 5 Phase 13 — Wikipedia pageview catalog.

Pulls Top-1000 English Wikipedia articles for each month of 2024 from the
Wikimedia REST pageviews API, dedupes by article, and aggregates yearly
pageview totals.

Output:
  pageviews_2024.jsonl  one record per unique article (year aggregate)
  fetch_log.json        per-month status + counters

Endpoint:
  https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/
    all-access/<YYYY>/<MM>/all-days

API caps:
  - ~100 req/sec shared; we make 12 calls total, no throttling required
  - non-empty User-Agent header is required
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = "structural-isomorphism/1.0 (contact:https://structural.bytedance.city)"
# Span 2023 + 2024 (24 months) — Wikimedia REST has gaps for some 2024 months
# (2024-09 and 2024-12 return 404 with "data not loaded"). Doubling the
# window (a) compensates and (b) gives n > 5000 unique articles for a robust
# Clauset tail fit.
YEAR_MONTH_PAIRS: list[tuple[int, int]] = [
    (y, m) for y in (2023, 2024) for m in range(1, 13)
]
OUT_DIR = Path(__file__).resolve().parent
OUT_JSONL = OUT_DIR / "pageviews_2023_2024.jsonl"
LOG_PATH = OUT_DIR / "fetch_log.json"

# Excluded by Wikimedia top-list itself (the API returns them, but they are
# not user-readable articles — Main Page, Special:Search, etc.). We drop them
# defensively so they cannot dominate the tail.
EXCLUDED_PREFIXES = (
    "Special:",
    "Wikipedia:",
    "Portal:",
    "Help:",
    "File:",
    "Talk:",
    "User:",
    "Category:",
)
EXCLUDED_EXACT = {
    "Main_Page",
    "-",  # API returns this as a sentinel sometimes
    "Wikipedia",
    "Special:Search",
    "Special:CreateAccount",
    "Special:UserLogin",
    "Special:RecentChanges",
}


def fetch_top(year: int, month: int, max_retry: int = 3) -> list[dict]:
    """Fetch one month's Top-1000 articles. Returns [] on persistent failure."""
    url = (
        f"https://wikimedia.org/api/rest_v1/metrics/pageviews/top/"
        f"en.wikipedia/all-access/{year}/{month:02d}/all-days"
    )
    last_err: str | None = None
    for attempt in range(1, max_retry + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            items = data.get("items", [])
            if not items:
                return []
            articles = items[0].get("articles", [])
            return [
                {"article": a["article"], "views": int(a["views"])}
                for a in articles
            ]
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}: {e.reason}"
            # 429 / 5xx → retry with linear backoff; 4xx other → bail
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retry:
                time.sleep(2.0 * attempt)
                continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt < max_retry:
                time.sleep(2.0 * attempt)
                continue
            break
    print(f"  [WARN] {year}-{month:02d} failed after {max_retry} attempts: {last_err}", file=sys.stderr)
    return []


def keep_article(name: str) -> bool:
    if name in EXCLUDED_EXACT:
        return False
    for p in EXCLUDED_PREFIXES:
        if name.startswith(p):
            return False
    return True


def main() -> int:
    print(
        f"Fetching top-1000 articles for {len(YEAR_MONTH_PAIRS)} months "
        f"({YEAR_MONTH_PAIRS[0][0]}-{YEAR_MONTH_PAIRS[0][1]:02d} ... "
        f"{YEAR_MONTH_PAIRS[-1][0]}-{YEAR_MONTH_PAIRS[-1][1]:02d}) ..."
    )
    aggregate: dict[str, int] = {}
    log: dict[str, dict] = {}
    months_ok = 0
    raw_rows = 0
    t0 = time.time()

    for y, m in YEAR_MONTH_PAIRS:
        t_a = time.time()
        rows = fetch_top(y, m)
        t_b = time.time()
        kept = [r for r in rows if keep_article(r["article"])]
        log[f"{y}-{m:02d}"] = {
            "raw": len(rows),
            "kept": len(kept),
            "elapsed_sec": round(t_b - t_a, 3),
            "status": "ok" if rows else "empty_or_failed",
        }
        if rows:
            months_ok += 1
        raw_rows += len(rows)
        for r in kept:
            aggregate[r["article"]] = aggregate.get(r["article"], 0) + r["views"]
        print(
            f"  {y}-{m:02d}: raw={len(rows):4d} kept={len(kept):4d} "
            f"unique_so_far={len(aggregate):5d}"
        )
        # very light rate-limit hygiene
        time.sleep(0.1)

    # Write JSONL
    n_articles = len(aggregate)
    with OUT_JSONL.open("w") as f:
        for article, views in sorted(aggregate.items(), key=lambda kv: -kv[1]):
            f.write(
                json.dumps({"article": article, "views_total": views}, ensure_ascii=False)
                + "\n"
            )

    elapsed = time.time() - t0
    summary = {
        "year_month_pairs": [f"{y}-{m:02d}" for y, m in YEAR_MONTH_PAIRS],
        "months_requested": len(YEAR_MONTH_PAIRS),
        "months_ok": months_ok,
        "raw_rows_total": raw_rows,
        "unique_articles_after_dedupe_and_filter": n_articles,
        "total_elapsed_sec": round(elapsed, 2),
        "per_month": log,
        "output_jsonl": str(OUT_JSONL),
    }
    LOG_PATH.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nDone.")
    print(
        f"  months_ok={months_ok}/{len(YEAR_MONTH_PAIRS)}  "
        f"unique_articles={n_articles}  elapsed={elapsed:.1f}s"
    )
    print(f"  wrote {OUT_JSONL}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
