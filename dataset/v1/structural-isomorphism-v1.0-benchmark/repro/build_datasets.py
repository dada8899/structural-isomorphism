#!/usr/bin/env python3
"""
build_datasets.py — populate the bundle's `datasets/` tree.

For each of the 13 primary phases listed in paper/v0-unified-pipeline-2026-05-13.md
we copy raw fetched data and fitted results from v4/validation/<src>/ into
datasets/<slot>/.

Policy:
  - Files <= 50 MB: copy verbatim.
  - Files > 50 MB: write a `<name>.LARGE_FILE_README.md` stub describing
    SHA-256, source URL, fetch date, and how to regenerate via the bundled
    fetch script (also copied).

Idempotent: re-running overwrites.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root
BUNDLE = Path(__file__).resolve().parents[1]  # .../structural-isomorphism-v1.0-benchmark
DEST = BUNDLE / "datasets"
LARGE_THRESHOLD_BYTES = 50 * 1024 * 1024  # 50 MB

# 13 primary phases per paper v0 §3 + 2 non-PL invariant phases (12, 13_hyst).
# slot -> (v4 source dir, phase number, short label, source URL)
SYSTEMS = {
    "01_earthquake": ("soc-earthquake", 1, "USGS earthquake catalog 2020-2025",
                      "https://earthquake.usgs.gov/fdsnws/event/1/"),
    "02_stockmarket": ("soc-stockmarket", 2, "S&P 500 daily returns 1990-2025",
                       "Yahoo Finance ^GSPC"),
    "03_defi": ("soc-defi", 3, "Aave V2 + Compound V2 + MakerDAO Dog liquidations",
                "Dune Analytics + protocol event logs"),
    "04_neural": ("soc-neural", 4, "Mouse ALM cortex avalanches (DANDI:000006)",
                  "https://dandiarchive.org/dandiset/000006"),
    "05_wildfire": ("soc-wildfire", 10, "NIFC US wildfires",
                    "https://www.nifc.gov/fire-information/statistics"),
    "06_solar": ("soc-solar", 11, "GOES X-ray flares 2000-2016",
                 "https://www.ngdc.noaa.gov/stp/satellite/goes-r.html"),
    "07_bank_failures": ("soc-bank-failures", 8, "FDIC bank failures 1934-2026",
                         "https://www.fdic.gov/resources/resolutions/bank-failures/"),
    "08_github_stars": ("soc-github-stars", 6, "GitHub stargazers 8398 repos",
                        "https://api.github.com/"),
    "09_power_grid": ("soc-power-grid", 7, "North American power-grid cascades (literature-meta)",
                      "Carreras / Dobson / Newman papers; NERC TADS"),
    "10_wikipedia_views": ("soc-wikipedia-views", 13, "English Wikipedia pageviews 2023-2024",
                           "https://wikimedia.org/api/rest_v1/"),
    "11_hawkes_omori": ("soc-hawkes-omori", "synthetic", "Hawkes-Omori synthetic baseline",
                        "internal generator"),
    "12_scheffer_lake": ("scheffer-lake", "A2", "Scheffer-style lake regime shift (USGS Fox River)",
                         "https://waterdata.usgs.gov/"),
    "13_hysteresis_traffic": ("hysteresis-traffic", "A2", "US-101 NGSIM traffic q-rho hysteresis",
                              "https://ops.fhwa.dot.gov/trafficanalysistools/ngsim.htm"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_large_file_stub(dest: Path, src: Path, source_url: str) -> None:
    h = sha256_file(src)
    size = src.stat().st_size
    rel_src = src.relative_to(ROOT)
    text = f"""# {src.name} (large file)

This file is **not bundled** because it exceeds the
{LARGE_THRESHOLD_BYTES // (1024 * 1024)} MB inline-bundle threshold.

| field | value |
| --- | --- |
| filename | `{src.name}` |
| size_bytes | {size} |
| size_human | {size / 1024 / 1024:.2f} MB |
| sha256 | `{h}` |
| source_url | {source_url} |
| repo_path | `{rel_src}` |

## To obtain

Option A — re-fetch from upstream using the bundled fetch script:

```bash
cd /path/to/structural-isomorphism
python {rel_src.parent}/fetch_{rel_src.stem}.py
```

Option B — clone the structural-isomorphism repo at git commit
{os.environ.get("GIT_COMMIT_SHA", "see MANIFEST.json")} and use the file at
`{rel_src}`.

Option C — download the Zenodo archive (DOI in `../README.md`) which
includes the raw file in the data tarball.

After obtaining the file, verify with:

```bash
sha256sum {src.name}
# expected: {h}
```
"""
    dest.write_text(text)


def copy_phase(slot: str, src_subdir: str, source_url: str) -> dict:
    src_dir = ROOT / "v4" / "validation" / src_subdir
    dest_dir = DEST / slot
    dest_dir.mkdir(parents=True, exist_ok=True)
    if not src_dir.exists():
        return {"slot": slot, "status": "MISSING_SOURCE", "src_dir": str(src_dir)}
    info = {"slot": slot, "source_dir": str(src_dir.relative_to(ROOT)),
            "files_copied": [], "files_stubbed": []}
    for f in sorted(src_dir.iterdir()):
        if f.is_dir():
            continue
        if f.name.startswith("."):
            continue
        size = f.stat().st_size
        if size > LARGE_THRESHOLD_BYTES:
            stub_path = dest_dir / f"{f.name}.LARGE_FILE_README.md"
            write_large_file_stub(stub_path, f, source_url)
            info["files_stubbed"].append(f.name)
        else:
            shutil.copy2(f, dest_dir / f.name)
            info["files_copied"].append(f.name)
    return info


def main():
    summary = {"systems": {}, "_meta": {"large_threshold_bytes": LARGE_THRESHOLD_BYTES}}
    for slot, (src_subdir, phase, label, url) in SYSTEMS.items():
        info = copy_phase(slot, src_subdir, url)
        info["phase"] = phase
        info["label"] = label
        summary["systems"][slot] = info
        n_c = len(info.get("files_copied", []))
        n_s = len(info.get("files_stubbed", []))
        print(f"  {slot:30s}  phase={str(phase):8s}  copied={n_c}  stubbed={n_s}")
    (DEST / "_build_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nWrote {DEST / '_build_summary.json'}")


if __name__ == "__main__":
    main()
