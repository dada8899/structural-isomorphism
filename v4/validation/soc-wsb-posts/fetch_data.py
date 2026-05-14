"""Fetch WSB posts via arctic_shift (Pushshift replacement).

arctic_shift.photon-reddit.com is a community-maintained Pushshift mirror that
indexes the same Reddit dump data Pushshift used to provide. Public API, no auth.

Strategy (auto-mode):
- Pull recent slice (2024-2025) for current-regime test
- Pull pre-2021 slice (2019-2020) for pre-regime-shift adversarial test
- Use after/before unix timestamps + sort=asc + paginate by last created_utc
- Cap total fetched ~5-10k per slice (rate-limit polite, <30 min budget)
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

OUT = Path(__file__).parent / "raw_posts.jsonl"
META_OUT = Path(__file__).parent / "fetch_meta.json"
API = "https://arctic-shift.photon-reddit.com/api/posts/search"
UA = "wsb-prereg-fit/1.0 (academic, structural-isomorphism)"
KEEP_FIELDS = (
    "id", "created_utc", "num_comments", "score", "ups",
    "title", "subreddit", "upvote_ratio", "is_self",
)


def fetch_slice(after_ts: int, before_ts: int, max_posts: int, label: str) -> list[dict]:
    """Page forward by created_utc, asc sort, limit=100 per call."""
    out: list[dict] = []
    cursor = after_ts
    page = 0
    while len(out) < max_posts:
        params = {
            "subreddit": "wallstreetbets",
            "limit": 100,
            "sort": "asc",
            "after": cursor,
            "before": before_ts,
        }
        try:
            r = requests.get(API, params=params, timeout=20, headers={"User-Agent": UA})
        except Exception as e:
            print(f"[{label}] page {page} err: {type(e).__name__} {e}", file=sys.stderr)
            break
        if r.status_code != 200:
            print(f"[{label}] page {page} HTTP {r.status_code}: {r.text[:200]}", file=sys.stderr)
            break
        data = r.json().get("data", [])
        if not data:
            print(f"[{label}] page {page} empty, stop", file=sys.stderr)
            break
        for p in data:
            row = {k: p.get(k) for k in KEEP_FIELDS}
            row["slice"] = label
            out.append(row)
        page += 1
        cursor = max(int(p.get("created_utc", cursor)) for p in data) + 1
        if page % 5 == 0:
            print(f"[{label}] page {page} n={len(out)} cursor={cursor}", file=sys.stderr)
        # be polite — arctic_shift has unpublished rate limits
        time.sleep(0.15)
    return out[:max_posts]


def main():
    # two slices to test pre-reg's "pre-2021 separately" robustness note
    slices = [
        # pre-regime-shift: 2019-2020 (before GME squeeze)
        ("pre_2021", 1546300800, 1609459200, 3000),   # 2019-01-01 to 2021-01-01
        # post-regime: 2024
        ("post_2024", 1704067200, 1735689600, 3000),  # 2024-01-01 to 2025-01-01
    ]
    all_rows: list[dict] = []
    meta = {"slices": {}}
    for label, after, before, cap in slices:
        t0 = time.time()
        rows = fetch_slice(after, before, cap, label)
        meta["slices"][label] = {
            "after_unix": after,
            "before_unix": before,
            "n_fetched": len(rows),
            "wall_sec": round(time.time() - t0, 2),
        }
        all_rows.extend(rows)
        print(f"[{label}] DONE n={len(rows)} wall={meta['slices'][label]['wall_sec']}s", file=sys.stderr)

    with OUT.open("w") as f:
        for r in all_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    meta["total_n"] = len(all_rows)
    meta["out_path"] = str(OUT)
    meta["out_size_mb"] = round(OUT.stat().st_size / 1e6, 2)
    META_OUT.write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))


if __name__ == "__main__":
    main()
