#!/usr/bin/env python3
"""Fetch GitHub repository star counts to test preferential_attachment / SOC class.

Strategy: stratified search over `stars:>N` buckets to span 5 orders of magnitude
from highly-popular repos to median repos.

GitHub Search API:
- 60 unauth req/h
- 30 req/min with GITHUB_TOKEN env var (5000/h with token, 30 req/min hard cap)
- Returns at most 1000 results per query
- Sorted by stars desc

Stratification:
    stars:>100000        : ~30 repos
    stars:50000..100000  : ~100 repos
    stars:20000..50000   : ~500 repos
    stars:10000..20000   : ~1500 repos (capped at 1000)
    stars:5000..10000    : ~3500 repos (capped at 1000)
    stars:2000..5000     : ~10k repos (capped at 1000)
    stars:1000..2000     : ~30k repos (capped at 1000)
    stars:500..1000      : capped at 1000
    stars:200..500       : capped at 1000
    stars:100..200       : capped at 1000

This gives ~9k repos spanning [100, 400k] stars.

Output: repos.jsonl
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

OUT = Path(__file__).parent / "repos.jsonl"
LOG = Path(__file__).parent / "fetch_log.json"

API = "https://api.github.com/search/repositories"

BUCKETS = [
    "stars:>100000",
    "stars:50000..100000",
    "stars:20000..50000",
    "stars:10000..20000",
    "stars:5000..10000",
    "stars:2500..5000",
    "stars:1000..2500",
    "stars:500..1000",
    "stars:250..500",
    "stars:100..250",
]


def headers():
    h = {"Accept": "application/vnd.github+json", "User-Agent": "v4-phase6-fetcher"}
    tok = os.environ.get("GITHUB_TOKEN")
    if tok:
        h["Authorization"] = f"token {tok}"
    return h


def fetch_bucket(q: str, max_pages: int = 10) -> tuple[list[dict], dict]:
    items = []
    info = {"q": q, "pages": 0, "got": 0}
    for page in range(1, max_pages + 1):
        params = {
            "q": q,
            "sort": "stars",
            "order": "desc",
            "per_page": 100,
            "page": page,
        }
        for attempt in range(3):
            try:
                r = requests.get(API, headers=headers(), params=params, timeout=30)
            except Exception as e:
                if attempt == 2:
                    info["error"] = f"net: {e}"
                    return items, info
                time.sleep(3)
                continue
            if r.status_code == 200:
                break
            if r.status_code in (403, 429):
                # rate-limited
                reset = r.headers.get("X-RateLimit-Reset")
                if reset:
                    wait = max(0, int(reset) - int(time.time())) + 2
                    info["rate_wait_s"] = wait
                    if wait > 0 and wait < 1200:
                        print(f"  [bucket {q[:30]}] rate-limited, waiting {wait}s...")
                        time.sleep(wait)
                        continue
                info["error"] = f"http {r.status_code}: {r.text[:200]}"
                return items, info
            if attempt == 2:
                info["error"] = f"http {r.status_code}"
                return items, info
            time.sleep(2)

        try:
            data = r.json()
        except Exception as e:
            info["error"] = f"json: {e}"
            return items, info

        if "items" not in data:
            info["error"] = f"no items in response: {data.get('message','')}"
            return items, info

        page_items = data["items"]
        for it in page_items:
            items.append({
                "full_name": it["full_name"],
                "stars": int(it["stargazers_count"]),
                "created_at": it["created_at"],
                "language": it.get("language"),
                "size_kb": int(it["size"]),
            })
        info["pages"] = page
        info["got"] = len(items)
        if len(page_items) < 100:
            break
        time.sleep(1)  # API courtesy
    return items, info


def main() -> int:
    all_repos: dict[str, dict] = {}
    log = {"buckets": [], "total_unique": 0}
    for q in BUCKETS:
        print(f"[fetch] {q} ...", flush=True)
        items, info = fetch_bucket(q, max_pages=10)
        log["buckets"].append(info)
        print(f"  → {info}")
        for it in items:
            all_repos[it["full_name"]] = it
        # If hit rate limit hard, save what we have and stop
        if info.get("error", "").startswith("http 403") and "rate limit" in str(info.get("error", "")).lower():
            log["aborted"] = q
            break

    log["total_unique"] = len(all_repos)
    with OUT.open("w") as f:
        for v in all_repos.values():
            f.write(json.dumps(v) + "\n")
    LOG.write_text(json.dumps(log, indent=2))
    print(f"\n[fetch] wrote {len(all_repos)} unique repos to {OUT}")
    # Quick stats
    stars = sorted([r["stars"] for r in all_repos.values()], reverse=True)
    if stars:
        print(f"  star range: [{stars[-1]}, {stars[0]}]")
        print(f"  median stars: {stars[len(stars)//2]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
