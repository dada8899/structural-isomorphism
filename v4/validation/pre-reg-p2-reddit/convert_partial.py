#!/usr/bin/env python3
"""Convert the partial reddit_posts.jsonl to reddit_cascade_sizes.json.

Used if `fetch_reddit.py` is stopped early (e.g. due to rate-limit, network
flap, or time budget). Reads the JSONL, dedupes by id, extracts num_comments,
and writes the same output schema the analyze step expects.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
POSTS_FILE = OUT_DIR / "reddit_posts.jsonl"
SIZES_FILE = OUT_DIR / "reddit_cascade_sizes.json"

# Match fetch_reddit.py constants — keep in sync if those change
SUBREDDITS = [
    "AskReddit", "news", "worldnews", "politics", "todayilearned",
    "science", "technology", "movies", "gaming", "wallstreetbets",
]


def main():
    if not POSTS_FILE.exists():
        raise SystemExit(f"{POSTS_FILE} missing — run fetch_reddit.py first")
    posts: dict[str, dict] = {}
    with open(POSTS_FILE) as f:
        for line in f:
            try:
                p = json.loads(line)
            except json.JSONDecodeError:
                continue
            pid = p.get("id")
            if pid:
                posts[pid] = p
    posts_list = list(posts.values())
    sizes = [int(p.get("num_comments") or 0) for p in posts_list]
    sizes = [s for s in sizes if s > 0]

    # Window edges from the actual data
    ts = [int(p.get("created_utc") or 0) for p in posts_list]
    ts = [t for t in ts if t > 0]
    t_min, t_max = min(ts), max(ts)

    subs_seen = sorted({p.get("subreddit", "") for p in posts_list})

    out = {
        "source": "arctic-shift.photon-reddit.com (Reddit submissions archive) — PARTIAL FETCH",
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "window_start_utc": datetime.fromtimestamp(t_min, tz=timezone.utc).isoformat(),
        "window_end_utc": datetime.fromtimestamp(t_max, tz=timezone.utc).isoformat(),
        "subreddits_intended": SUBREDDITS,
        "subreddits_actually_present": subs_seen,
        "n_posts_total": len(posts_list),
        "n_cascades_positive": len(sizes),
        "note_partial": (
            "fetch_reddit.py was stopped before completing all subreddits; "
            "this file converts the partial JSONL into the same schema the "
            "analyze step expects. All num_comments values are real "
            "(arctic_shift-archive sourced); the only effect of partial "
            "fetch is reduced sample size."
        ),
        "cascade_sizes": sizes,
    }
    with open(SIZES_FILE, "w") as f:
        json.dump(out, f)
    print(f"[ok] wrote {len(sizes)} cascade sizes (partial) -> {SIZES_FILE}")
    print(f"     subs seen: {subs_seen}")


if __name__ == "__main__":
    main()
