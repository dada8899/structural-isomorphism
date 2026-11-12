#!/usr/bin/env python3
"""Fetch Allen Brain Atlas TBI Aβ-burden measurements (public REST API).

Source
------
Allen Institute for Brain Science. Aging, Dementia & TBI Study.
https://aging.brain-map.org/

API endpoint
------------
https://api.brain-map.org/api/v2/data/query.json
  ?criteria=model::ApiTbiDonorMetric

Each record is one (donor × structure) tissue measurement with biomarker
columns: ab40_pg_per_mg, ab42_pg_per_mg, ihc_a_beta, ptau_ng_per_mg, plus
cytokines, neurotrophins. We extract:
  - ab42_pg_per_mg (ELISA): the *plaque-relevant* fraction of Aβ peptide
  - ihc_a_beta and ihc_a_beta_ffpe: immunohistochemistry-quantified Aβ load
    (= fraction of tissue area positive for Aβ stain)

The 'plaque size distribution' is operationalised here as the distribution
of per-sample Aβ burden values across the ~377 donor-structure samples.
This is one well-known proxy in the aggregation-kinetics literature
(Hyman 2008; Cruz 1997 review): tissue-aggregate Aβ load behaves like the
total mass of an aggregating-coagulating system, so its distribution
across many samples carries Smoluchowski-coagulation tail-exponent
signatures.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(parents=True, exist_ok=True)

API = "https://api.brain-map.org/api/v2/data/query.json"
UA = "structural-isomorphism-validation/0.1 (research; X3 wave2)"


def fetch_all_donor_metrics(max_pages: int = 20) -> list[dict]:
    """Page through the TbiDonorMetric model until exhausted."""
    all_rows: list[dict] = []
    start = 0
    page_size = 50
    for pg in range(max_pages):
        url = (f"{API}?criteria=model::ApiTbiDonorMetric"
               f"&num_rows={page_size}&start_row={start}")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        except Exception as e:
            print(f"  [retry-skip pg {pg}] {e}")
            time.sleep(2)
            continue
        rows = data.get("msg", [])
        total = data.get("total_rows", 0)
        if not rows:
            break
        all_rows.extend(rows)
        print(f"  page {pg}: rows {start}-{start + len(rows)} / total {total}")
        if start + len(rows) >= total:
            break
        start += page_size
        time.sleep(0.3)
    return all_rows


def main() -> None:
    print("Fetching Allen Brain TBI Aβ burden metrics …")
    rows = fetch_all_donor_metrics()
    print(f"Total rows: {len(rows)}")
    (RAW / "tbi_donor_metric.json").write_text(json.dumps(rows, indent=2))

    # Project key columns into 1 series each
    ab42 = [r["ab42_pg_per_mg"] for r in rows
            if r.get("ab42_pg_per_mg") is not None]
    ab40 = [r["ab40_pg_per_mg"] for r in rows
            if r.get("ab40_pg_per_mg") is not None]
    ihc = [r["ihc_a_beta"] for r in rows
           if r.get("ihc_a_beta") is not None]
    ihc_ffpe = [r["ihc_a_beta_ffpe"] for r in rows
                if r.get("ihc_a_beta_ffpe") is not None]
    ratio = [r["ab42_over_ab40_ratio"] for r in rows
             if r.get("ab42_over_ab40_ratio") is not None]

    # Save as plain text, one value per line (descending)
    def save(series: list[float], name: str) -> None:
        s = sorted([x for x in series if x > 0], reverse=True)
        (RAW / f"{name}.txt").write_text("\n".join(repr(x) for x in s) + "\n")
        print(f"  {name}: n={len(s)}, max={s[0] if s else 0:.4g}, "
              f"median={s[len(s)//2] if s else 0:.4g}")

    save(ab42, "ab42_pg_per_mg")
    save(ab40, "ab40_pg_per_mg")
    save(ihc, "ihc_a_beta")
    save(ihc_ffpe, "ihc_a_beta_ffpe")
    save(ratio, "ab42_over_ab40_ratio")

    log = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "source": "https://aging.brain-map.org/ "
                  "(Allen Brain TBI Donor Metric REST API)",
        "citation": "Miller et al. 2017 eLife 6:e26571",
        "api_endpoint": API,
        "total_rows": len(rows),
        "data_provenance": "ALLEN_BRAIN_LIVE",
        "fields_extracted": [
            "ab42_pg_per_mg", "ab40_pg_per_mg",
            "ihc_a_beta", "ihc_a_beta_ffpe", "ab42_over_ab40_ratio",
        ],
        "raw_file": "tbi_donor_metric.json",
        "n_ab42": len(ab42),
        "n_ab40": len(ab40),
        "n_ihc": len(ihc),
    }
    (ROOT / "fetch_log.json").write_text(json.dumps(log, indent=2))
    print(f"\nLog: {ROOT / 'fetch_log.json'}")


if __name__ == "__main__":
    sys.exit(main() or 0)
