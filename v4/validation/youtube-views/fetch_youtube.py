#!/usr/bin/env python3
"""Fetch YouTube Trending Videos dataset (US) from GitHub mirror.

Source
------
Mitchell Bowden's Kaggle "YouTube Trending Video Dataset" (originally
hosted on Kaggle as `datasnaek/youtube-new`; mirrored on GitHub).
Mirror: https://github.com/mendsalbert/Youtube-trending-video-dataset-analysis

Files fetched
-------------
- USvideos.csv.zip   (~24 MB)
  Daily snapshot 2017-11-14 → 2018-06-14, US region, top-200 trending /day.

Each row is one (video × snapshot-day) record with `views`, `likes`,
`dislikes`, `comment_count`. Many videos appear on multiple consecutive
days; we de-duplicate by max `views` per `video_id` for the cascade-size
analysis.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

CSV_ZIP_URL = (
    "https://raw.githubusercontent.com/mendsalbert/"
    "Youtube-trending-video-dataset-analysis/main/USvideos.csv.zip"
)
CATEGORY_JSON_URL = (
    "https://raw.githubusercontent.com/mendsalbert/"
    "Youtube-trending-video-dataset-analysis/main/US_category_id.json"
)

UA = "structural-isomorphism-validation/0.1 (research; X3 wave2)"


def download(url: str, dest: Path) -> Path:
    if dest.exists() and dest.stat().st_size > 1024:
        print(f"  [cache] {dest.name} ({dest.stat().st_size:,} bytes)")
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            dest.write_bytes(data)
            print(f"  [ok]    {dest.name} ({len(data):,} bytes)")
            return dest
        except Exception as e:
            print(f"  [retry {attempt + 1}/3] {url}: {e}")
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}")


def unzip(zpath: Path, out_dir: Path) -> Path | None:
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        csv_name = next((n for n in names if n.endswith(".csv")), None)
        if csv_name is None:
            return None
        out_path = out_dir / Path(csv_name).name
        if out_path.exists() and out_path.stat().st_size > 1024:
            return out_path
        z.extract(csv_name, out_dir)
        extracted = out_dir / csv_name
        # If nested, move
        if extracted != out_path:
            extracted.rename(out_path)
        return out_path


def parse_csv_to_view_counts(csv_path: Path) -> dict:
    """Read USvideos.csv; aggregate max views per video_id.

    Returns dict with:
      - per_video_max_views: dict[video_id -> max(views)]
      - n_rows: row count
      - distinct_videos: int
      - date_range: (min, max) trending_date strings
    """
    per_video: dict[str, int] = {}
    dates: set[str] = set()
    n = 0
    with open(csv_path, encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            n += 1
            vid = row.get("video_id")
            if not vid:
                continue
            try:
                v = int(float(row.get("views", "0")))
            except ValueError:
                continue
            if v <= 0:
                continue
            if vid not in per_video or v > per_video[vid]:
                per_video[vid] = v
            d = row.get("trending_date")
            if d:
                dates.add(d)
    return {
        "per_video_max_views": per_video,
        "n_rows": n,
        "distinct_videos": len(per_video),
        "date_range": (min(dates), max(dates)) if dates else (None, None),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    print("Fetching YouTube Trending US dataset …")
    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": ("https://github.com/mendsalbert/"
                   "Youtube-trending-video-dataset-analysis"
                   " (mirror of Kaggle datasnaek/youtube-new)"),
        "citation": "Bowden 2018 Kaggle YouTube Trending Video Dataset",
        "region": "US",
        "data_provenance": "GITHUB_MIRROR_LIVE",
        "files": [],
    }

    zip_path = RAW / "USvideos.csv.zip"
    cat_path = RAW / "US_category_id.json"
    if args.no_cache and zip_path.exists():
        zip_path.unlink()

    download(CSV_ZIP_URL, zip_path)
    download(CATEGORY_JSON_URL, cat_path)
    log["files"].append({"name": zip_path.name, "bytes": zip_path.stat().st_size})
    log["files"].append({"name": cat_path.name, "bytes": cat_path.stat().st_size})

    print("Unzipping…")
    csv_path = unzip(zip_path, RAW)
    if csv_path is None:
        raise RuntimeError("no CSV in zip")
    print(f"  CSV: {csv_path.name} ({csv_path.stat().st_size:,} bytes)")

    print("Parsing CSV (this takes ~15-30 s for 40K rows)…")
    parsed = parse_csv_to_view_counts(csv_path)

    # Save per-video max-view list (descending)
    sizes_path = RAW / "video_max_views.txt"
    values = sorted(parsed["per_video_max_views"].values(), reverse=True)
    sizes_path.write_text("\n".join(str(v) for v in values) + "\n")

    log["summary"] = {
        "n_csv_rows": parsed["n_rows"],
        "distinct_videos": parsed["distinct_videos"],
        "date_range": list(parsed["date_range"]),
        "max_views": int(values[0]) if values else 0,
        "median_views": int(values[len(values) // 2]) if values else 0,
        "video_max_views_file": str(sizes_path.relative_to(ROOT)),
    }
    print(f"  rows={parsed['n_rows']:,}  videos={parsed['distinct_videos']:,}  "
          f"max_views={log['summary']['max_views']:,}")
    (ROOT / "fetch_log.json").write_text(json.dumps(log, indent=2))
    print(f"Log: {ROOT / 'fetch_log.json'}")


if __name__ == "__main__":
    sys.exit(main() or 0)
