#!/usr/bin/env python3
"""Fetch top-N cities by population for 5 countries from Wikipedia.

Source: Wikipedia "List of cities in <country> by population". The underlying
authoritative data come from the respective national census / statistics
offices (US Census Bureau ACS 2020, China 2020 Census, India 2011 Census +
2024 estimates, Destatis 2021, IBGE 2022 Census).

5 countries chosen for geographic and economic diversity:
    - United States (top ~330 cities, 2020 census + 2025 estimate)
    - China (top ~134 cities, 2020 census)
    - India (top ~290 cities, 2011 census)
    - Germany (top ~80 cities, 2021 estimate)
    - Brazil (top ~330 cities, 2022 census + 2025 estimate)

Output:
    raw/<country>.jsonl   one record per city: {rank, name, population, region}
    raw/fetch_log.json    timestamp + source URLs + row counts
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

HERE = Path(__file__).resolve().parent
RAW = HERE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

USER_AGENT = "structural-isomorphism-research/1.0 (riazward110@gmail.com)"


# Per-country fetch spec.
# - url: Wikipedia page
# - table_idx: which wikitable on the page holds the long city list
# - name_col / pop_col: 0-indexed columns
# - region_col: state/province column (-1 if not present)
# - skip_header_rows: how many sub-header rows before data starts
SPEC = {
    "united_states": {
        "url": "https://en.wikipedia.org/wiki/List_of_United_States_cities_by_population",
        "table_idx": 1,
        "name_col": 0,
        "region_col": 1,
        "pop_col": 3,  # 2020 census (the authoritative published count)
        "skip_header_rows": 2,  # main header + units sub-header (mi2/km2)
        "source": "US Census Bureau 2020 decennial census via Wikipedia",
        "year": 2020,
    },
    "china": {
        "url": "https://en.wikipedia.org/wiki/List_of_cities_in_China_by_population",
        "table_idx": 2,
        "name_col": 0,
        "region_col": 1,
        "pop_col": 2,  # 2020 census
        "skip_header_rows": 1,
        "source": "China 2020 census via Wikipedia",
        "year": 2020,
    },
    "india": {
        "url": "https://en.wikipedia.org/wiki/List_of_cities_in_India_by_population",
        # India: top-46 cities live in table 0, ranks 47-300 in table 1.
        # We merge both tables to recover a single ranked list.
        "table_idx": [0, 1],
        "name_col": 1,
        "region_col": 2,
        "pop_col": 3,  # 2011 census
        "skip_header_rows": 1,
        "source": "India 2011 census via Wikipedia",
        "year": 2011,
    },
    "germany": {
        "url": "https://en.wikipedia.org/wiki/List_of_cities_in_Germany_by_population",
        "table_idx": 0,
        "name_col": 1,
        "region_col": 2,
        "pop_col": 3,  # 2021 estimate
        "skip_header_rows": 1,
        "source": "Destatis 2021 estimate via Wikipedia",
        "year": 2021,
    },
    "brazil": {
        "url": "https://en.wikipedia.org/wiki/List_of_largest_cities_in_Brazil",
        "table_idx": 1,
        "name_col": 0,
        "region_col": 1,
        "pop_col": 3,  # 2022 census
        "skip_header_rows": 1,
        "source": "IBGE 2022 census via Wikipedia",
        "year": 2022,
    },
}


_NUMBER_RE = re.compile(r"-?[\d,\.]+")


def parse_population(text: str) -> int | None:
    """Extract integer population from Wikipedia cell text.

    Handles: '8,804,190', '8 804 190', '8.804.190' (some i18n styles),
    drops footnote markers like '[c]', '⍟', '#'.
    """
    if not text:
        return None
    # Strip footnote markers and decoration
    cleaned = re.sub(r"\[[^\]]*\]", "", text)
    cleaned = cleaned.replace("\xa0", " ").replace("﻿", "")
    # Find longest numeric blob
    m = _NUMBER_RE.findall(cleaned)
    if not m:
        return None
    # Pick longest hit (avoids matching footnote idx)
    best = max(m, key=len)
    digits = re.sub(r"[^\d]", "", best)
    if not digits:
        return None
    try:
        v = int(digits)
        if v < 1000:  # sanity: city pop is much larger
            return None
        return v
    except ValueError:
        return None


def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="ignore")


def extract_country(country: str, spec: dict) -> list[dict]:
    html = fetch_url(spec["url"])
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="wikitable")
    table_idxs = spec["table_idx"]
    if isinstance(table_idxs, int):
        table_idxs = [table_idxs]
    for ti in table_idxs:
        if ti >= len(tables):
            raise RuntimeError(
                f"{country}: requested table_idx={ti} but only {len(tables)} wikitables"
            )

    out: list[dict] = []
    seen = set()  # de-dupe by name across merged tables
    for ti in table_idxs:
        t = tables[ti]
        rows = t.find_all("tr")
        if len(rows) < spec["skip_header_rows"] + 3:
            continue
        max_col = max(
            spec["name_col"],
            spec["pop_col"],
            spec["region_col"] if spec["region_col"] >= 0 else 0,
        )
        for row in rows[spec["skip_header_rows"]:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= max_col:
                continue
            name = cells[spec["name_col"]].get_text(strip=True)
            # Strip footnotes / icons from name
            name = re.sub(r"\[[^\]]*\]", "", name)
            name = re.sub(r"[⍟#*†‡§~◇♦▲►]", "", name).strip()
            # Drop national-total summary rows like "India:"
            if not name or name.endswith(":") or name.lower() in {"total", "subtotal"}:
                continue
            pop = parse_population(cells[spec["pop_col"]].get_text(strip=True))
            region = (
                cells[spec["region_col"]].get_text(strip=True)
                if spec["region_col"] >= 0
                else ""
            )
            region = re.sub(r"\[[^\]]*\]", "", region).strip()
            if pop is None:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": name,
                "region": region,
                "population": pop,
            })

    # Sort by population descending and assign ranks
    out.sort(key=lambda r: -r["population"])
    for i, r in enumerate(out, start=1):
        r["rank"] = i
    # Reorder rank to leading position
    out = [{"rank": r["rank"], "name": r["name"], "region": r["region"], "population": r["population"]} for r in out]
    return out


def main() -> int:
    log = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "countries": {},
    }
    for country, spec in SPEC.items():
        print(f"[{country}] fetching {spec['url']}")
        try:
            rows = extract_country(country, spec)
        except Exception as exc:
            print(f"  ERROR: {exc}")
            log["countries"][country] = {"error": str(exc), "n": 0}
            continue
        # Cap to top-100 (per task spec)
        rows = rows[:100]
        # Re-rank to 1..N strictly
        for i, r in enumerate(rows, start=1):
            r["rank"] = i
        out_path = RAW / f"{country}.jsonl"
        with out_path.open("w") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  wrote {out_path} ({len(rows)} cities, "
              f"pop range {rows[0]['population']:,} -- {rows[-1]['population']:,})")
        log["countries"][country] = {
            "n": len(rows),
            "source": spec["source"],
            "year": spec["year"],
            "url": spec["url"],
            "top_population": rows[0]["population"],
            "bottom_population": rows[-1]["population"],
        }
        time.sleep(1.0)  # polite rate-limit

    log_path = RAW / "fetch_log.json"
    log_path.write_text(json.dumps(log, ensure_ascii=False, indent=2))
    print(f"\nlog -> {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
