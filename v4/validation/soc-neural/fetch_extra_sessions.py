#!/usr/bin/env python3
"""Fetch additional DANDI:000006 sessions for C1 v0.3 P0-N1 multi-session expansion.

Picks 4 sessions in addition to the existing sub-anm369962_ses-20170313:
  - sub-anm369962/sub-anm369962_ses-20170314.nwb  (same animal, +1 day)
  - sub-anm369962/sub-anm369962_ses-20170317.nwb  (same animal, +4 days)
  - sub-anm369963/sub-anm369963_ses-20170227.nwb  (different animal)
  - sub-anm369964/sub-anm369964_ses-20170320.nwb  (different animal)

This gives 3-animal coverage at 5 sessions total.
"""
import json
import sys
from pathlib import Path

from dandi.dandiapi import DandiAPIClient

HERE = Path(__file__).resolve().parent
DEST = HERE / "data" / "extra_sessions"
DEST.mkdir(parents=True, exist_ok=True)

ASSETS_WANTED = [
    "sub-anm369962/sub-anm369962_ses-20170314.nwb",
    "sub-anm369962/sub-anm369962_ses-20170317.nwb",
    "sub-anm369963/sub-anm369963_ses-20170227.nwb",
    "sub-anm369964/sub-anm369964_ses-20170320.nwb",
]


def main():
    client = DandiAPIClient()
    ds = client.get_dandiset("000006", "draft")
    fetched = []
    for path in ASSETS_WANTED:
        local = DEST / Path(path).name
        if local.exists() and local.stat().st_size > 100_000:
            print(f"SKIP existing {local.name} ({local.stat().st_size/1e6:.1f} MB)")
            fetched.append({"path": path, "local": str(local), "skipped": True})
            continue
        try:
            asset = ds.get_asset_by_path(path)
        except Exception as e:
            print(f"MISSING {path}: {e}")
            continue
        url = asset.download_url
        print(f"Downloading {path} ({asset.size/1e6:.1f} MB) ...")
        asset.download(local)
        fetched.append({
            "path": path,
            "local": str(local),
            "size_bytes": int(local.stat().st_size),
        })

    (DEST / "fetch_log.json").write_text(json.dumps(fetched, indent=2))
    print(f"\nWrote: {DEST/'fetch_log.json'}")
    print(f"Total sessions fetched: {len(fetched)}")


if __name__ == "__main__":
    main()
