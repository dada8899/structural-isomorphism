#!/usr/bin/env python3
"""Fetch JHU CSSE COVID-19 global confirmed-cases time series.

Source:
  https://github.com/CSSEGISandData/COVID-19
  csse_covid_19_data/csse_covid_19_time_series/time_series_covid19_confirmed_global.csv

The repo was archived 2023-03-10, so the file is a frozen time series
spanning 2020-01-22 → 2023-03-09 (~1142 days). Daily granularity, by
country/region with optional sub-region rows (we sum sub-regions per
country).

Five countries are extracted: US / UK / India / Brazil / Italy. The
raw file is saved to raw/time_series_covid19_confirmed_global.csv and
per-country daily-new-case series to raw/<country>.csv with columns
date, cumulative, new_cases (7-day MA also computed).

Output:
  raw/time_series_covid19_confirmed_global.csv  (raw JHU archive)
  raw/{us,uk,india,brazil,italy}.csv             (per-country)
  raw/fetch_log.json                             (metadata)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUT_DIR / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)

JHU_URL = (
    "https://raw.githubusercontent.com/CSSEGISandData/COVID-19/master/"
    "csse_covid_19_data/csse_covid_19_time_series/"
    "time_series_covid19_confirmed_global.csv"
)

# JHU calls them by these names in the Country/Region column.
COUNTRIES = {
    "us": "US",
    "uk": "United Kingdom",
    "india": "India",
    "brazil": "Brazil",
    "italy": "Italy",
}


def fetch_raw() -> bytes:
    """Download JHU confirmed-global CSV; cache locally."""
    local = RAW_DIR / "time_series_covid19_confirmed_global.csv"
    if local.exists() and local.stat().st_size > 100_000:
        print(f"  cache hit: {local} ({local.stat().st_size} bytes)")
        return local.read_bytes()
    print(f"  fetching {JHU_URL}")
    req = urllib.request.Request(JHU_URL, headers={"User-Agent": "structural-isomorphism/v4-covid-omori"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = resp.read()
    local.write_bytes(data)
    print(f"  saved: {local} ({len(data)} bytes)")
    return data


def parse_dates(header_row: list[str]) -> list[tuple[int, str]]:
    """Header columns 0..3 are Province/State, Country/Region, Lat, Long.
    Columns 4.. are dates formatted M/D/YY (e.g. 1/22/20). Return list of
    (col_index, iso_date_string)."""
    out = []
    for i, h in enumerate(header_row):
        if i < 4:
            continue
        m, d, yy = h.split("/")
        year = 2000 + int(yy)
        iso = f"{year:04d}-{int(m):02d}-{int(d):02d}"
        out.append((i, iso))
    return out


def aggregate_country(rows: list[list[str]], header: list[str], country: str) -> list[tuple[str, int]]:
    """Sum sub-region cumulative counts for a country; return (date, cumulative) list."""
    date_cols = parse_dates(header)
    cum_by_date: dict[str, int] = {iso: 0 for _, iso in date_cols}
    n_matched = 0
    for row in rows:
        if len(row) < len(header):
            continue
        # Country/Region is col 1
        if row[1] != country:
            continue
        n_matched += 1
        for col, iso in date_cols:
            try:
                cum_by_date[iso] += int(row[col]) if row[col] else 0
            except ValueError:
                cum_by_date[iso] += 0
    return sorted(cum_by_date.items()), n_matched


def cumulative_to_new(cum_pairs: list[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """(date, cum) → (date, cum, new_today). First row new=0."""
    out = []
    prev = None
    for date, cum in cum_pairs:
        if prev is None:
            new = 0
        else:
            new = max(0, cum - prev)  # clip negative adjustments
        out.append((date, cum, new))
        prev = cum
    return out


def smooth_7day(series: list[tuple[str, int, int]]) -> list[tuple[str, int, int, float]]:
    """Append 7-day centered MA on the new-cases series."""
    new = [s[2] for s in series]
    n = len(new)
    out = []
    for i in range(n):
        lo = max(0, i - 3)
        hi = min(n, i + 4)
        ma = sum(new[lo:hi]) / (hi - lo)
        out.append((series[i][0], series[i][1], series[i][2], round(ma, 2)))
    return out


def write_country_csv(country_key: str, smoothed: list[tuple[str, int, int, float]], n_matched: int) -> Path:
    out = RAW_DIR / f"{country_key}.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "cumulative", "new_cases", "new_7d_ma"])
        for row in smoothed:
            w.writerow(row)
    print(f"  {country_key}: {len(smoothed)} days, {n_matched} sub-region rows summed → {out}")
    return out


def main():
    print("Fetching JHU CSSE COVID-19 confirmed-global time series...")
    raw_bytes = fetch_raw()
    sha = hashlib.sha256(raw_bytes).hexdigest()
    print(f"  sha256: {sha}")

    text = raw_bytes.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    header = next(reader)
    rows = list(reader)
    print(f"  header: {len(header)} cols  rows: {len(rows)}")

    summary = {
        "source_url": JHU_URL,
        "fetched_at": datetime.utcnow().isoformat() + "Z",
        "sha256": sha,
        "raw_size_bytes": len(raw_bytes),
        "header_cols": len(header),
        "n_rows": len(rows),
        "n_date_columns": len(header) - 4,
        "first_date": "1/22/20 (=2020-01-22)",
        "last_date": header[-1],
        "countries": {},
    }

    for key, name in COUNTRIES.items():
        print(f"\n[{key}] {name}")
        cum, n_matched = aggregate_country(rows, header, name)
        if not any(c[1] > 0 for c in cum):
            print(f"  WARNING: country '{name}' produced all-zero series.")
        series = cumulative_to_new(cum)
        smoothed = smooth_7day(series)
        out_csv = write_country_csv(key, smoothed, n_matched)
        peak = max(smoothed, key=lambda r: r[3])
        summary["countries"][key] = {
            "country_jhu_name": name,
            "n_subregion_rows_summed": n_matched,
            "n_days": len(smoothed),
            "first_date": smoothed[0][0] if smoothed else None,
            "last_date": smoothed[-1][0] if smoothed else None,
            "cumulative_final": smoothed[-1][1] if smoothed else None,
            "peak_date_7dma": peak[0],
            "peak_7dma_new_cases": peak[3],
            "csv": str(out_csv.name),
        }

    log_path = RAW_DIR / "fetch_log.json"
    log_path.write_text(json.dumps(summary, indent=2))
    print(f"\nWrote fetch log: {log_path}")


if __name__ == "__main__":
    main()
