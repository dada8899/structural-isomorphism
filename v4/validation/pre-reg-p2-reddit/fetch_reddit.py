#!/usr/bin/env python3
"""Pre-reg P2 — fetch Reddit comment-cascade sizes from arctic_shift archive.

Data source: arctic-shift.photon-reddit.com (public Reddit archive replacing
the defunct pushshift.io public API). Strategy: collect submission records
across multiple high-traffic subreddits over a fixed retrospective window,
and use `num_comments` as the cascade-size proxy. This is the standard proxy
in Cheng et al. 2014 "Can cascades be predicted?" and follow-up work — each
top-level submission roots one cascade tree whose total size is num_comments.

Outputs:
  reddit_posts.jsonl       one record per submission
  reddit_cascade_sizes.json  flat list of num_comments + metadata

References:
  Pre-registration: paper/v0-unified-pipeline-2026-05-13.md Table 7, P2
  predicted band: alpha = 2.0 +/- 0.3
  Cheng et al. 2014 — root-cascade size distribution.

The arctic_shift API requires explicit `after`/`before` unix timestamps and
returns submissions sorted by created_utc desc. We page backwards via the
`before` cursor until the time window is exhausted.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import urllib.request
import urllib.error

OUT_DIR = Path(__file__).resolve().parent
POSTS_FILE = OUT_DIR / "reddit_posts.jsonl"
SIZES_FILE = OUT_DIR / "reddit_cascade_sizes.json"
META_FILE = OUT_DIR / "fetch_meta.json"

API_BASE = "https://arctic-shift.photon-reddit.com/api/posts/search"

# Subreddits chosen for high traffic + diverse topical mix
SUBREDDITS = [
    "AskReddit",
    "news",
    "worldnews",
    "politics",
    "todayilearned",
    "science",
    "technology",
    "movies",
    "gaming",
    "wallstreetbets",
]

# 30-day window ending 2 days ago (avoid edge of archive ingestion)
END_TS = int((datetime.now(timezone.utc) - timedelta(days=2)).timestamp())
START_TS = END_TS - 30 * 86400
PAGE_LIMIT = 100  # arctic_shift max
SLEEP_BETWEEN_CALLS = 1.2
MAX_PAGES_PER_SUB = 60  # bound runtime ~6000 posts / sub


def fetch_page(subreddit: str, after: int, before: int) -> list[dict]:
    url = (
        f"{API_BASE}?subreddit={subreddit}&limit={PAGE_LIMIT}&sort=desc"
        f"&after={after}&before={before}"
        f"&fields=id,created_utc,num_comments,score,title,subreddit"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "structural-isomorphism/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        print(f"  [warn] {subreddit} fetch failed: {e}", file=sys.stderr)
        return []
    if payload.get("error"):
        print(f"  [warn] {subreddit} api error: {payload['error']}", file=sys.stderr)
        return []
    return payload.get("data") or []


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if POSTS_FILE.exists():
        print(f"[skip] {POSTS_FILE} exists; remove to refetch.")
    else:
        total = 0
        with open(POSTS_FILE, "w") as fout:
            for sub in SUBREDDITS:
                print(f"[fetch] r/{sub}")
                before = END_TS
                pages = 0
                sub_count = 0
                while pages < MAX_PAGES_PER_SUB:
                    page = fetch_page(sub, START_TS, before)
                    if not page:
                        break
                    for p in page:
                        fout.write(json.dumps(p) + "\n")
                    sub_count += len(page)
                    # cursor: oldest created_utc - 1
                    oldest = min(int(p["created_utc"]) for p in page)
                    if oldest <= START_TS:
                        break
                    before = oldest
                    pages += 1
                    if len(page) < PAGE_LIMIT:
                        break
                    time.sleep(SLEEP_BETWEEN_CALLS)
                total += sub_count
                print(f"  -> {sub_count} posts (pages={pages+1})")
        print(f"[ok] total {total} posts -> {POSTS_FILE}")

    # Load and dedupe by id
    posts: dict[str, dict] = {}
    with open(POSTS_FILE) as f:
        for line in f:
            p = json.loads(line)
            pid = p.get("id")
            if pid:
                posts[pid] = p
    posts_list = list(posts.values())
    print(f"[load] {len(posts_list)} unique posts after dedupe")

    # Cascade sizes
    sizes = [int(p.get("num_comments") or 0) for p in posts_list]
    sizes = [s for s in sizes if s > 0]
    print(f"[stats] {len(sizes)} cascades with num_comments > 0; "
          f"max={max(sizes) if sizes else 0}; median={sorted(sizes)[len(sizes)//2] if sizes else 0}")

    out = {
        "source": "arctic-shift.photon-reddit.com (Reddit submissions archive)",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start_utc": datetime.fromtimestamp(START_TS, tz=timezone.utc).isoformat(),
        "window_end_utc": datetime.fromtimestamp(END_TS, tz=timezone.utc).isoformat(),
        "subreddits": SUBREDDITS,
        "n_posts_total": len(posts_list),
        "n_cascades_positive": len(sizes),
        "cascade_sizes": sizes,
    }
    with open(SIZES_FILE, "w") as f:
        json.dump(out, f)
    print(f"[ok] wrote {len(sizes)} cascade sizes -> {SIZES_FILE}")

    with open(META_FILE, "w") as f:
        json.dump({k: v for k, v in out.items() if k != "cascade_sizes"}, f, indent=2)


if __name__ == "__main__":
    main()
