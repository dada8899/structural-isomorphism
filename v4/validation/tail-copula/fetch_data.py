"""Fetch NOAA Storm Events data for 1996-2024.

Downloads yearly CSV.gz files from NOAA NCEI, extracts:
- date (BEGIN_YEARMONTH + BEGIN_DAY)
- damage_property (parsed dollar amount)
- damage_crops

Produces: storm_daily_damage.csv (date, total_damage_usd, n_events).

S&P 500 daily series is reused from ../soc-stockmarket/sp500_daily.csv.
"""

from __future__ import annotations

import gzip
import re
import sys
import time
from pathlib import Path
from urllib.request import urlretrieve

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

# NOAA file index (canonical filenames discovered 2026-05-13 via index page)
NOAA_FILES = {
    1996: "StormEvents_details-ftp_v1.0_d1996_c20260323.csv.gz",
    1997: "StormEvents_details-ftp_v1.0_d1997_c20260323.csv.gz",
    1998: "StormEvents_details-ftp_v1.0_d1998_c20260323.csv.gz",
    1999: "StormEvents_details-ftp_v1.0_d1999_c20260323.csv.gz",
    2000: "StormEvents_details-ftp_v1.0_d2000_c20260323.csv.gz",
    2001: "StormEvents_details-ftp_v1.0_d2001_c20260323.csv.gz",
    2002: "StormEvents_details-ftp_v1.0_d2002_c20260323.csv.gz",
    2003: "StormEvents_details-ftp_v1.0_d2003_c20260323.csv.gz",
    2004: "StormEvents_details-ftp_v1.0_d2004_c20260323.csv.gz",
    2005: "StormEvents_details-ftp_v1.0_d2005_c20260323.csv.gz",
    2006: "StormEvents_details-ftp_v1.0_d2006_c20260323.csv.gz",
    2007: "StormEvents_details-ftp_v1.0_d2007_c20260323.csv.gz",
    2008: "StormEvents_details-ftp_v1.0_d2008_c20260323.csv.gz",
    2009: "StormEvents_details-ftp_v1.0_d2009_c20260323.csv.gz",
    2010: "StormEvents_details-ftp_v1.0_d2010_c20260323.csv.gz",
    2011: "StormEvents_details-ftp_v1.0_d2011_c20260323.csv.gz",
    2012: "StormEvents_details-ftp_v1.0_d2012_c20260323.csv.gz",
    2013: "StormEvents_details-ftp_v1.0_d2013_c20260323.csv.gz",
    2014: "StormEvents_details-ftp_v1.0_d2014_c20260323.csv.gz",
    2015: "StormEvents_details-ftp_v1.0_d2015_c20260323.csv.gz",
    2016: "StormEvents_details-ftp_v1.0_d2016_c20260323.csv.gz",
    2017: "StormEvents_details-ftp_v1.0_d2017_c20260323.csv.gz",
    2018: "StormEvents_details-ftp_v1.0_d2018_c20260323.csv.gz",
    2019: "StormEvents_details-ftp_v1.0_d2019_c20260323.csv.gz",
    2020: "StormEvents_details-ftp_v1.0_d2020_c20260323.csv.gz",
    2021: "StormEvents_details-ftp_v1.0_d2021_c20260323.csv.gz",
    2022: "StormEvents_details-ftp_v1.0_d2022_c20260323.csv.gz",
    2023: "StormEvents_details-ftp_v1.0_d2023_c20260323.csv.gz",
    2024: "StormEvents_details-ftp_v1.0_d2024_c20260421.csv.gz",
}

BASE_URL = "https://www.ncei.noaa.gov/pub/data/swdi/stormevents/csvfiles/"


def parse_damage(s: str) -> float:
    """Parse NOAA damage string like '1.50K', '2.30M', '500.00', '5.00B'."""
    if pd.isna(s) or s in ("", "0", "0.00", "0.00K"):
        return 0.0
    s = str(s).strip().upper().replace("$", "")
    m = re.match(r"([0-9.]+)\s*([KMBT]?)", s)
    if not m:
        return 0.0
    try:
        val = float(m.group(1))
    except ValueError:
        return 0.0
    mult = {"": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}.get(m.group(2), 1)
    return val * mult


def download_year(year: int) -> Path:
    fname = NOAA_FILES[year]
    out = DATA_DIR / f"storm_{year}.csv.gz"
    if out.exists() and out.stat().st_size > 100_000:
        return out
    url = BASE_URL + fname
    print(f"  downloading {year}...", flush=True)
    urlretrieve(url, out)
    time.sleep(0.3)  # be nice to NOAA
    return out


def load_year(year: int) -> pd.DataFrame:
    path = download_year(year)
    # Read only needed columns
    cols = [
        "BEGIN_YEARMONTH",
        "BEGIN_DAY",
        "EVENT_TYPE",
        "DAMAGE_PROPERTY",
        "DAMAGE_CROPS",
    ]
    df = pd.read_csv(path, usecols=cols, low_memory=False, compression="gzip")
    df["damage_property_usd"] = df["DAMAGE_PROPERTY"].apply(parse_damage)
    df["damage_crops_usd"] = df["DAMAGE_CROPS"].apply(parse_damage)
    df["total_damage_usd"] = df["damage_property_usd"] + df["damage_crops_usd"]
    # Build date
    ym = df["BEGIN_YEARMONTH"].astype(int).astype(str).str.zfill(6)
    dd = df["BEGIN_DAY"].astype(int).astype(str).str.zfill(2)
    df["date"] = pd.to_datetime(ym + dd, format="%Y%m%d", errors="coerce")
    df = df.dropna(subset=["date"])
    return df[["date", "total_damage_usd", "EVENT_TYPE"]]


def main():
    print("Fetching NOAA Storm Events 1996-2024...", flush=True)
    pieces = []
    for year in range(1996, 2025):
        try:
            pieces.append(load_year(year))
        except Exception as e:
            print(f"  year {year} failed: {e}", flush=True)
    if not pieces:
        print("ERROR: no NOAA data fetched", file=sys.stderr)
        sys.exit(1)
    raw = pd.concat(pieces, ignore_index=True)
    print(f"Total raw events: {len(raw):,}", flush=True)

    # Aggregate daily
    daily = (
        raw.groupby("date")
        .agg(
            total_damage_usd=("total_damage_usd", "sum"),
            n_events=("EVENT_TYPE", "count"),
        )
        .reset_index()
        .sort_values("date")
    )
    print(f"Daily aggregated: {len(daily):,} days", flush=True)
    print(
        f"  Top 5 damage days: \n{daily.nlargest(5, 'total_damage_usd')[['date','total_damage_usd','n_events']]}",
        flush=True,
    )

    out = DATA_DIR.parent / "storm_daily_damage.csv"
    daily.to_csv(out, index=False)
    print(f"Wrote {out}", flush=True)


if __name__ == "__main__":
    main()
