#!/usr/bin/env python3
"""Minimal NVD CVE fetcher for pre-registered validation.

Pulls CVEs from NIST NVD REST API v2.0 for a configurable date range and
extracts monthly disclosure-burst counts (CVSS_v3 >= 7.0). Output suitable
for soc_pipeline.fit_clauset_powerlaw.

Pre-registration spec: v4/preregistration/cve-vulnerabilities.yaml
  PRIMARY distribution = per-month disclosure-burst counts (high+critical only)

NVD REST API: https://services.nvd.nist.gov/rest/json/cves/2.0
  - 120s rate limit window, 5 req/30s for public (no API key)
  - Public access is rate-limited; we paginate cautiously with sleeps
  - resultsPerPage max = 2000

Output:
  v4/validation/cve-vulnerabilities/raw_sample.json  — per-month counts
  v4/validation/cve-vulnerabilities/burst_sizes.json — list of int counts (for fitter input)

CLI:
  python3 v4/scripts/fetch/fetch_cve_nvd.py [--year-start 2020] [--year-end 2023] [--max-pages 30] [--max-records N]

Notes:
  - Default range narrowed to 2020-2023 to stay within rate limits for one
    session (~ 40k CVEs after CVSS_v3>=7.0 filter).
  - W2-C session: this is a "sample" fetch. Full 2010-2025 pull will be a
    follow-up session with NVD API key (5000 req/30min instead of 5/30s).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

NVD_BASE = "https://services.nvd.nist.gov/rest/json/cves/2.0"

REPO = Path(__file__).resolve().parents[3]
OUT_DIR = REPO / "v4" / "validation" / "cve-vulnerabilities"


def fetch_window(start: datetime, end: datetime, results_per_page: int = 2000) -> list[dict]:
    """Fetch a single time window from NVD. Paginates by startIndex.

    Returns list of cve raw dicts from `vulnerabilities` field.
    """
    out: list[dict] = []
    start_index = 0
    total = None
    pages = 0
    while True:
        params = {
            "pubStartDate": start.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "pubEndDate": end.strftime("%Y-%m-%dT%H:%M:%S.000"),
            "resultsPerPage": str(results_per_page),
            "startIndex": str(start_index),
        }
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url = f"{NVD_BASE}?{qs}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "structural-isomorphism-v4-research/0.1"},
        )
        # Retry once on transient errors
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                last_err = None
                break
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                last_err = e
                # NVD 503 = rate limit; back off harder
                wait = 8 * (attempt + 1)
                print(f"  [fetch] retry {attempt+1} after {wait}s: {e}", file=sys.stderr)
                time.sleep(wait)
        if last_err is not None:
            raise RuntimeError(f"NVD fetch failed after retries: {last_err}")
        if total is None:
            total = int(payload.get("totalResults", 0))
            print(
                f"  [fetch] window {start.date()}..{end.date()} total={total}",
                file=sys.stderr,
            )
        vulns = payload.get("vulnerabilities", []) or []
        out.extend(vulns)
        start_index += len(vulns)
        pages += 1
        if not vulns or start_index >= total:
            break
        # public rate limit ~ 5 req / 30s; sleep 7s between pages
        time.sleep(7)
    return out


def extract_disclosures(vulns: list[dict]) -> list[dict]:
    """Filter CVEs with CVSS_v3 >= 7.0 and emit (published, score, cwe) records."""
    records = []
    for entry in vulns:
        cve = entry.get("cve", {}) or {}
        published = cve.get("published")
        if not published:
            continue
        metrics = cve.get("metrics", {}) or {}
        # prefer cvssMetricV31; fallback v30
        score = None
        for key in ("cvssMetricV31", "cvssMetricV30"):
            arr = metrics.get(key) or []
            for m in arr:
                cdata = m.get("cvssData", {}) or {}
                s = cdata.get("baseScore")
                if isinstance(s, (int, float)):
                    score = float(s)
                    break
            if score is not None:
                break
        if score is None or score < 7.0:
            continue
        weaknesses = cve.get("weaknesses", []) or []
        cwe_id = None
        for w in weaknesses:
            for d in w.get("description", []) or []:
                v = d.get("value", "")
                if v.startswith("CWE-"):
                    cwe_id = v
                    break
            if cwe_id:
                break
        records.append(
            {
                "id": cve.get("id"),
                "published": published,
                "score": score,
                "cwe": cwe_id or "CWE-UNKNOWN",
            }
        )
    return records


def aggregate_monthly_counts(records: list[dict]) -> dict[str, int]:
    """Bucket records by YYYY-MM and return count of CVSSv3>=7.0 disclosures per month."""
    buckets: Counter[str] = Counter()
    for r in records:
        pub = r["published"]
        # NVD ISO 8601 like '2023-01-15T14:30:00.000'
        month = pub[:7]
        buckets[month] += 1
    return dict(sorted(buckets.items()))


def main() -> int:
    ap = argparse.ArgumentParser(description="Minimal NVD CVE fetcher.")
    ap.add_argument("--year-start", type=int, default=2022)
    ap.add_argument("--year-end", type=int, default=2023)
    ap.add_argument(
        "--max-records",
        type=int,
        default=0,
        help="If > 0, cap total CVEs fetched (useful for sample runs).",
    )
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    all_vulns: list[dict] = []
    # NVD allows window <= 120 days; chunk by 90 days.
    year = args.year_start
    cur = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_cap = datetime(args.year_end, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    while cur < end_cap:
        win_end = min(cur + timedelta(days=90), end_cap)
        try:
            chunk = fetch_window(cur.replace(tzinfo=None), win_end.replace(tzinfo=None))
        except Exception as e:
            print(f"[fetch] window error: {e}", file=sys.stderr)
            break
        all_vulns.extend(chunk)
        if args.max_records and len(all_vulns) >= args.max_records:
            all_vulns = all_vulns[: args.max_records]
            print(f"[fetch] hit max-records cap {args.max_records}", file=sys.stderr)
            break
        cur = win_end + timedelta(seconds=1)
        time.sleep(7)
    print(f"[fetch] total vulns pulled: {len(all_vulns)}", file=sys.stderr)

    records = extract_disclosures(all_vulns)
    print(f"[fetch] after CVSSv3>=7.0 filter: {len(records)} records", file=sys.stderr)

    monthly = aggregate_monthly_counts(records)
    burst_sizes = list(monthly.values())

    raw_sample = {
        "data_source": "NIST NVD REST API v2.0",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "year_range": [args.year_start, args.year_end],
        "filter": "CVSS_v3 >= 7.0 (high+critical only)",
        "total_cves_pulled": len(all_vulns),
        "records_after_filter": len(records),
        "monthly_counts": monthly,
        "n_months": len(monthly),
        "sum_burst_sizes": sum(burst_sizes),
    }

    out_raw = out_dir / "raw_sample.json"
    out_burst = out_dir / "burst_sizes.json"
    out_raw.write_text(json.dumps(raw_sample, indent=2))
    out_burst.write_text(json.dumps(burst_sizes))
    print(f"[fetch] wrote {out_raw}")
    print(f"[fetch] wrote {out_burst}  (n={len(burst_sizes)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
