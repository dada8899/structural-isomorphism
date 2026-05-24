#!/usr/bin/env python3
"""Fetch Twitter retweet cascade data from SNAP Higgs Twitter archive.

Source
------
De Domenico, M., Lima, A., Mougel, P., & Musolesi, M. (2013).
"The Anatomy of a Scientific Rumor." Scientific Reports 3, 2980.
https://snap.stanford.edu/data/higgs-twitter.html

Files fetched
-------------
- higgs-retweet_network.edgelist.gz   (~5.6 MB)
- higgs-activity_time.txt.gz          (activity timestamps)

What we derive
--------------
1. Cascade size = out-degree (number of retweeters per origin tweet) on the
   retweet network.
2. Inter-arrival times of activity events (for Omori-decay tail probe).

This gives Twitter cascade-size distribution = canonical
preferential_attachment validation system per De Domenico 2013, who
report cascade-size power-law with alpha ~ 1.8-2.5 depending on filter.
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

SNAP_BASE = "https://snap.stanford.edu/data"
FILES = [
    ("higgs-retweet_network.edgelist.gz", "retweet"),
    ("higgs-activity_time.txt.gz", "activity"),
]

UA = "structural-isomorphism-validation/0.1 (research; X3 wave2)"


def download(name: str) -> Path:
    """Download one SNAP file with retry; return local path."""
    url = f"{SNAP_BASE}/{name}"
    out = RAW / name
    if out.exists() and out.stat().st_size > 1024:
        print(f"  [cache] {out.name} ({out.stat().st_size:,} bytes)")
        return out

    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            out.write_bytes(data)
            print(f"  [ok]    {out.name} ({len(data):,} bytes)")
            return out
        except Exception as e:
            print(f"  [retry {attempt + 1}/3] {name}: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {name}")


def parse_retweet_edgelist(path: Path, max_rows: int | None = None) -> dict:
    """Parse SNAP edgelist gz format: 'src dst ts' per row.

    Returns dict with:
      - n_edges: total RT edges parsed
      - origin_counts: dict[user_id -> RT count] (i.e. cascade size)
      - earliest_ts, latest_ts
    """
    origin_counts: dict[str, int] = {}
    n = 0
    earliest = None
    latest = None
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            # SNAP higgs RT edgelist has 3 cols: src dst ts
            if len(parts) < 2:
                continue
            src = parts[0]
            # The "src" in the SNAP convention is the RETWEETER; the "dst" is
            # the ORIGIN (the one being RT'd). So aggregate cascades by dst.
            origin = parts[1]
            origin_counts[origin] = origin_counts.get(origin, 0) + 1
            n += 1
            if len(parts) >= 3:
                try:
                    ts = int(parts[2])
                    if earliest is None or ts < earliest:
                        earliest = ts
                    if latest is None or ts > latest:
                        latest = ts
                except ValueError:
                    pass
            if max_rows is not None and n >= max_rows:
                break
    return {
        "n_edges": n,
        "n_origins": len(origin_counts),
        "origin_counts": origin_counts,
        "earliest_ts": earliest,
        "latest_ts": latest,
    }


def parse_activity_times(path: Path, max_rows: int | None = None) -> list[int]:
    """Parse SNAP higgs activity time file.

    Each line: 'user1 user2 ts type' where type ∈ {RT, MT, RE}.
    Returns sorted list of timestamps.
    """
    ts: list[int] = []
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                t = int(parts[2])
                ts.append(t)
            except ValueError:
                continue
            if max_rows is not None and len(ts) >= max_rows:
                break
    ts.sort()
    return ts


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Higgs Twitter cascades")
    ap.add_argument("--max-rows", type=int, default=None,
                    help="Cap rows parsed (testing only)")
    args = ap.parse_args()

    print("Fetching Higgs Twitter cascade data from SNAP …")
    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "https://snap.stanford.edu/data/higgs-twitter.html",
        "citation": "De Domenico et al. 2013, Scientific Reports 3:2980",
        "files": [],
    }

    rt_path = None
    act_path = None
    for fname, kind in FILES:
        try:
            p = download(fname)
            sz = p.stat().st_size
            log["files"].append({"name": fname, "kind": kind, "bytes": sz})
            if kind == "retweet":
                rt_path = p
            elif kind == "activity":
                act_path = p
        except Exception as e:
            log["files"].append({"name": fname, "kind": kind, "error": str(e)})

    summary: dict = {"data_provenance": "SNAP_LIVE"}
    if rt_path is not None:
        print("Parsing retweet edgelist (this takes ~20-40s for 354K edges)…")
        rt = parse_retweet_edgelist(rt_path, max_rows=args.max_rows)
        # Save cascade size distribution as plain text (one count per line)
        sizes_path = RAW / "cascade_sizes.txt"
        sizes_path.write_text(
            "\n".join(str(c) for c in sorted(rt["origin_counts"].values(),
                                              reverse=True)) + "\n"
        )
        summary["retweet"] = {
            "n_edges": rt["n_edges"],
            "n_origins": rt["n_origins"],
            "earliest_ts": rt["earliest_ts"],
            "latest_ts": rt["latest_ts"],
            "cascade_sizes_file": str(sizes_path.relative_to(ROOT)),
            "max_cascade": max(rt["origin_counts"].values()) if rt["origin_counts"] else 0,
        }
        print(f"  edges={rt['n_edges']:,}  origins={rt['n_origins']:,}  "
              f"max_cascade={summary['retweet']['max_cascade']}")

    if act_path is not None:
        print("Parsing activity timestamps…")
        ts = parse_activity_times(act_path, max_rows=args.max_rows)
        ts_path = RAW / "activity_ts.txt"
        ts_path.write_text("\n".join(str(t) for t in ts) + "\n")
        summary["activity"] = {
            "n_events": len(ts),
            "earliest_ts": ts[0] if ts else None,
            "latest_ts": ts[-1] if ts else None,
            "ts_file": str(ts_path.relative_to(ROOT)),
        }
        print(f"  events={len(ts):,}  "
              f"span={ts[-1] - ts[0] if ts else 0:,}s")

    log["summary"] = summary
    (ROOT / "fetch_log.json").write_text(json.dumps(log, indent=2))
    print(f"Log: {ROOT / 'fetch_log.json'}")


if __name__ == "__main__":
    sys.exit(main() or 0)
