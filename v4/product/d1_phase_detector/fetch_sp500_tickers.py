#!/usr/bin/env python3
"""Fetch S&P 500 ticker list from Wikipedia, with a hardcoded fallback.

Outputs `sp500_tickers.json` next to this script. Each row is
`{symbol, name, sector}`.

Source: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
The Wikipedia table has columns: Symbol, Security, GICS Sector, GICS Sub-Industry, etc.

If the fetch fails (network blocked, parser drift), we fall back to a static
list of ~120 of the largest S&P 500 names so downstream pipeline can still
produce a usable >=500 input file once merged with existing companies.jsonl.

CLI:
    python3 fetch_sp500_tickers.py [--output PATH] [--force-fallback]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DEFAULT_OUTPUT = Path(__file__).parent / "sp500_tickers.json"

# Static fallback — top ~120 S&P 500 components by market cap as of 2024-2025.
# Used when Wikipedia fetch fails. Sector strings follow the same coarse buckets
# already used in companies.jsonl (lower_snake_case).
STATIC_FALLBACK: list[dict] = [
    # Mega-cap tech / consumer
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "tech_hardware"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "tech_software"},
    {"symbol": "GOOGL", "name": "Alphabet Inc. Class A", "sector": "tech_software"},
    {"symbol": "GOOG", "name": "Alphabet Inc. Class C", "sector": "tech_software"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "consumer_discretionary"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "tech_semiconductors"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "tech_software"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "consumer_discretionary"},
    {"symbol": "BRK.B", "name": "Berkshire Hathaway Inc. Class B", "sector": "financials"},
    {"symbol": "AVGO", "name": "Broadcom Inc.", "sector": "tech_semiconductors"},
    # Large-cap tech / comms
    {"symbol": "ORCL", "name": "Oracle Corporation", "sector": "tech_software"},
    {"symbol": "ADBE", "name": "Adobe Inc.", "sector": "tech_software"},
    {"symbol": "CRM", "name": "Salesforce Inc.", "sector": "tech_software"},
    {"symbol": "NFLX", "name": "Netflix Inc.", "sector": "comms"},
    {"symbol": "AMD", "name": "Advanced Micro Devices Inc.", "sector": "tech_semiconductors"},
    {"symbol": "INTC", "name": "Intel Corporation", "sector": "tech_semiconductors"},
    {"symbol": "QCOM", "name": "Qualcomm Inc.", "sector": "tech_semiconductors"},
    {"symbol": "TXN", "name": "Texas Instruments Inc.", "sector": "tech_semiconductors"},
    {"symbol": "INTU", "name": "Intuit Inc.", "sector": "tech_software"},
    {"symbol": "IBM", "name": "International Business Machines", "sector": "tech_software"},
    {"symbol": "CSCO", "name": "Cisco Systems Inc.", "sector": "tech_hardware"},
    {"symbol": "AMAT", "name": "Applied Materials Inc.", "sector": "tech_semiconductors"},
    {"symbol": "MU", "name": "Micron Technology Inc.", "sector": "tech_semiconductors"},
    {"symbol": "LRCX", "name": "Lam Research Corporation", "sector": "tech_semiconductors"},
    {"symbol": "KLAC", "name": "KLA Corporation", "sector": "tech_semiconductors"},
    {"symbol": "PANW", "name": "Palo Alto Networks Inc.", "sector": "tech_software"},
    {"symbol": "NOW", "name": "ServiceNow Inc.", "sector": "tech_software"},
    {"symbol": "SNPS", "name": "Synopsys Inc.", "sector": "tech_software"},
    {"symbol": "CDNS", "name": "Cadence Design Systems Inc.", "sector": "tech_software"},
    {"symbol": "ANET", "name": "Arista Networks Inc.", "sector": "tech_hardware"},
    # Telecom / media
    {"symbol": "DIS", "name": "Walt Disney Company", "sector": "comms"},
    {"symbol": "CMCSA", "name": "Comcast Corporation", "sector": "comms"},
    {"symbol": "T", "name": "AT&T Inc.", "sector": "comms"},
    {"symbol": "VZ", "name": "Verizon Communications Inc.", "sector": "comms"},
    {"symbol": "TMUS", "name": "T-Mobile US Inc.", "sector": "comms"},
    {"symbol": "CHTR", "name": "Charter Communications Inc.", "sector": "comms"},
    # Financials / banks
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "financials"},
    {"symbol": "BAC", "name": "Bank of America Corporation", "sector": "financials"},
    {"symbol": "WFC", "name": "Wells Fargo & Company", "sector": "financials"},
    {"symbol": "GS", "name": "Goldman Sachs Group Inc.", "sector": "financials"},
    {"symbol": "MS", "name": "Morgan Stanley", "sector": "financials"},
    {"symbol": "C", "name": "Citigroup Inc.", "sector": "financials"},
    {"symbol": "BLK", "name": "BlackRock Inc.", "sector": "financials"},
    {"symbol": "AXP", "name": "American Express Company", "sector": "financials"},
    {"symbol": "SCHW", "name": "Charles Schwab Corporation", "sector": "financials"},
    {"symbol": "USB", "name": "U.S. Bancorp", "sector": "financials"},
    {"symbol": "PNC", "name": "PNC Financial Services Group", "sector": "financials"},
    {"symbol": "TFC", "name": "Truist Financial Corporation", "sector": "financials"},
    {"symbol": "COF", "name": "Capital One Financial Corporation", "sector": "financials"},
    {"symbol": "SPGI", "name": "S&P Global Inc.", "sector": "financials"},
    {"symbol": "MCO", "name": "Moody's Corporation", "sector": "financials"},
    {"symbol": "ICE", "name": "Intercontinental Exchange Inc.", "sector": "financials"},
    {"symbol": "CME", "name": "CME Group Inc.", "sector": "financials"},
    {"symbol": "V", "name": "Visa Inc.", "sector": "financials"},
    {"symbol": "MA", "name": "Mastercard Inc.", "sector": "financials"},
    {"symbol": "PYPL", "name": "PayPal Holdings Inc.", "sector": "financials"},
    # Insurance
    {"symbol": "BRK.A", "name": "Berkshire Hathaway Inc. Class A", "sector": "financials"},
    {"symbol": "PGR", "name": "Progressive Corporation", "sector": "insurance"},
    {"symbol": "TRV", "name": "Travelers Companies Inc.", "sector": "insurance"},
    {"symbol": "AIG", "name": "American International Group Inc.", "sector": "insurance"},
    {"symbol": "MET", "name": "MetLife Inc.", "sector": "insurance"},
    {"symbol": "PRU", "name": "Prudential Financial Inc.", "sector": "insurance"},
    {"symbol": "ALL", "name": "Allstate Corporation", "sector": "insurance"},
    {"symbol": "CB", "name": "Chubb Limited", "sector": "insurance"},
    {"symbol": "AFL", "name": "Aflac Inc.", "sector": "insurance"},
    {"symbol": "MMC", "name": "Marsh & McLennan Companies", "sector": "insurance"},
    # Healthcare / pharma
    {"symbol": "UNH", "name": "UnitedHealth Group Inc.", "sector": "healthcare"},
    {"symbol": "JNJ", "name": "Johnson & Johnson", "sector": "healthcare"},
    {"symbol": "LLY", "name": "Eli Lilly and Company", "sector": "healthcare"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "healthcare"},
    {"symbol": "MRK", "name": "Merck & Co. Inc.", "sector": "healthcare"},
    {"symbol": "ABBV", "name": "AbbVie Inc.", "sector": "healthcare"},
    {"symbol": "TMO", "name": "Thermo Fisher Scientific Inc.", "sector": "healthcare"},
    {"symbol": "ABT", "name": "Abbott Laboratories", "sector": "healthcare"},
    {"symbol": "DHR", "name": "Danaher Corporation", "sector": "healthcare"},
    {"symbol": "BMY", "name": "Bristol-Myers Squibb Company", "sector": "healthcare"},
    {"symbol": "AMGN", "name": "Amgen Inc.", "sector": "healthcare"},
    {"symbol": "GILD", "name": "Gilead Sciences Inc.", "sector": "healthcare"},
    {"symbol": "CVS", "name": "CVS Health Corporation", "sector": "healthcare"},
    {"symbol": "MDT", "name": "Medtronic plc", "sector": "healthcare"},
    {"symbol": "ISRG", "name": "Intuitive Surgical Inc.", "sector": "healthcare"},
    {"symbol": "ELV", "name": "Elevance Health Inc.", "sector": "healthcare"},
    {"symbol": "CI", "name": "Cigna Group", "sector": "healthcare"},
    {"symbol": "HCA", "name": "HCA Healthcare Inc.", "sector": "healthcare"},
    {"symbol": "VRTX", "name": "Vertex Pharmaceuticals Inc.", "sector": "healthcare"},
    {"symbol": "REGN", "name": "Regeneron Pharmaceuticals Inc.", "sector": "healthcare"},
    {"symbol": "BIIB", "name": "Biogen Inc.", "sector": "healthcare"},
    # Consumer staples
    {"symbol": "WMT", "name": "Walmart Inc.", "sector": "consumer_staples"},
    {"symbol": "PG", "name": "Procter & Gamble Company", "sector": "consumer_staples"},
    {"symbol": "KO", "name": "Coca-Cola Company", "sector": "consumer_staples"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "sector": "consumer_staples"},
    {"symbol": "COST", "name": "Costco Wholesale Corporation", "sector": "consumer_staples"},
    {"symbol": "MDLZ", "name": "Mondelez International Inc.", "sector": "consumer_staples"},
    {"symbol": "PM", "name": "Philip Morris International", "sector": "consumer_staples"},
    {"symbol": "MO", "name": "Altria Group Inc.", "sector": "consumer_staples"},
    {"symbol": "CL", "name": "Colgate-Palmolive Company", "sector": "consumer_staples"},
    {"symbol": "KMB", "name": "Kimberly-Clark Corporation", "sector": "consumer_staples"},
    {"symbol": "GIS", "name": "General Mills Inc.", "sector": "consumer_staples"},
    {"symbol": "KHC", "name": "Kraft Heinz Company", "sector": "consumer_staples"},
    {"symbol": "STZ", "name": "Constellation Brands Inc.", "sector": "consumer_staples"},
    {"symbol": "SYY", "name": "Sysco Corporation", "sector": "consumer_staples"},
    # Consumer discretionary
    {"symbol": "HD", "name": "Home Depot Inc.", "sector": "consumer_discretionary"},
    {"symbol": "LOW", "name": "Lowe's Companies Inc.", "sector": "consumer_discretionary"},
    {"symbol": "MCD", "name": "McDonald's Corporation", "sector": "consumer_discretionary"},
    {"symbol": "SBUX", "name": "Starbucks Corporation", "sector": "consumer_discretionary"},
    {"symbol": "NKE", "name": "Nike Inc.", "sector": "consumer_discretionary"},
    {"symbol": "TGT", "name": "Target Corporation", "sector": "consumer_discretionary"},
    {"symbol": "BKNG", "name": "Booking Holdings Inc.", "sector": "consumer_discretionary"},
    {"symbol": "ABNB", "name": "Airbnb Inc.", "sector": "consumer_discretionary"},
    {"symbol": "MAR", "name": "Marriott International Inc.", "sector": "consumer_discretionary"},
    {"symbol": "F", "name": "Ford Motor Company", "sector": "consumer_discretionary"},
    {"symbol": "GM", "name": "General Motors Company", "sector": "consumer_discretionary"},
    {"symbol": "ORLY", "name": "O'Reilly Automotive Inc.", "sector": "consumer_discretionary"},
    {"symbol": "AZO", "name": "AutoZone Inc.", "sector": "consumer_discretionary"},
    {"symbol": "CMG", "name": "Chipotle Mexican Grill Inc.", "sector": "consumer_discretionary"},
    # Energy
    {"symbol": "XOM", "name": "Exxon Mobil Corporation", "sector": "energy"},
    {"symbol": "CVX", "name": "Chevron Corporation", "sector": "energy"},
    {"symbol": "COP", "name": "ConocoPhillips", "sector": "energy"},
    {"symbol": "EOG", "name": "EOG Resources Inc.", "sector": "energy"},
    {"symbol": "SLB", "name": "Schlumberger Limited", "sector": "energy"},
    {"symbol": "PXD", "name": "Pioneer Natural Resources Company", "sector": "energy"},
    {"symbol": "MPC", "name": "Marathon Petroleum Corporation", "sector": "energy"},
    {"symbol": "PSX", "name": "Phillips 66", "sector": "energy"},
    {"symbol": "VLO", "name": "Valero Energy Corporation", "sector": "energy"},
    {"symbol": "OXY", "name": "Occidental Petroleum Corporation", "sector": "energy"},
    {"symbol": "WMB", "name": "Williams Companies Inc.", "sector": "energy"},
    {"symbol": "KMI", "name": "Kinder Morgan Inc.", "sector": "energy"},
    {"symbol": "HAL", "name": "Halliburton Company", "sector": "energy"},
    # Utilities
    {"symbol": "NEE", "name": "NextEra Energy Inc.", "sector": "utilities"},
    {"symbol": "SO", "name": "Southern Company", "sector": "utilities"},
    {"symbol": "DUK", "name": "Duke Energy Corporation", "sector": "utilities"},
    {"symbol": "AEP", "name": "American Electric Power Company", "sector": "utilities"},
    {"symbol": "SRE", "name": "Sempra", "sector": "utilities"},
    {"symbol": "D", "name": "Dominion Energy Inc.", "sector": "utilities"},
    {"symbol": "EXC", "name": "Exelon Corporation", "sector": "utilities"},
    {"symbol": "XEL", "name": "Xcel Energy Inc.", "sector": "utilities"},
    # Industrials
    {"symbol": "BA", "name": "Boeing Company", "sector": "industrials"},
    {"symbol": "CAT", "name": "Caterpillar Inc.", "sector": "industrials"},
    {"symbol": "GE", "name": "General Electric Company", "sector": "industrials"},
    {"symbol": "HON", "name": "Honeywell International Inc.", "sector": "industrials"},
    {"symbol": "UPS", "name": "United Parcel Service Inc.", "sector": "industrials"},
    {"symbol": "RTX", "name": "RTX Corporation", "sector": "industrials"},
    {"symbol": "LMT", "name": "Lockheed Martin Corporation", "sector": "industrials"},
    {"symbol": "DE", "name": "Deere & Company", "sector": "industrials"},
    {"symbol": "UNP", "name": "Union Pacific Corporation", "sector": "industrials"},
    {"symbol": "FDX", "name": "FedEx Corporation", "sector": "industrials"},
    {"symbol": "ETN", "name": "Eaton Corporation plc", "sector": "industrials"},
    {"symbol": "EMR", "name": "Emerson Electric Co.", "sector": "industrials"},
    {"symbol": "ITW", "name": "Illinois Tool Works Inc.", "sector": "industrials"},
    {"symbol": "NSC", "name": "Norfolk Southern Corporation", "sector": "industrials"},
    {"symbol": "GD", "name": "General Dynamics Corporation", "sector": "industrials"},
    {"symbol": "NOC", "name": "Northrop Grumman Corporation", "sector": "industrials"},
    {"symbol": "WM", "name": "Waste Management Inc.", "sector": "industrials"},
    {"symbol": "CSX", "name": "CSX Corporation", "sector": "industrials"},
    {"symbol": "PH", "name": "Parker-Hannifin Corporation", "sector": "industrials"},
    {"symbol": "MMM", "name": "3M Company", "sector": "industrials"},
    # Materials
    {"symbol": "LIN", "name": "Linde plc", "sector": "materials"},
    {"symbol": "APD", "name": "Air Products and Chemicals Inc.", "sector": "materials"},
    {"symbol": "SHW", "name": "Sherwin-Williams Company", "sector": "materials"},
    {"symbol": "ECL", "name": "Ecolab Inc.", "sector": "materials"},
    {"symbol": "FCX", "name": "Freeport-McMoRan Inc.", "sector": "materials"},
    {"symbol": "NEM", "name": "Newmont Corporation", "sector": "materials"},
    {"symbol": "DD", "name": "DuPont de Nemours Inc.", "sector": "materials"},
    {"symbol": "DOW", "name": "Dow Inc.", "sector": "materials"},
    # Real Estate
    {"symbol": "AMT", "name": "American Tower Corporation", "sector": "real_estate"},
    {"symbol": "PLD", "name": "Prologis Inc.", "sector": "real_estate"},
    {"symbol": "EQIX", "name": "Equinix Inc.", "sector": "real_estate"},
    {"symbol": "CCI", "name": "Crown Castle Inc.", "sector": "real_estate"},
    {"symbol": "PSA", "name": "Public Storage", "sector": "real_estate"},
    {"symbol": "O", "name": "Realty Income Corporation", "sector": "real_estate"},
    {"symbol": "SPG", "name": "Simon Property Group Inc.", "sector": "real_estate"},
    {"symbol": "WELL", "name": "Welltower Inc.", "sector": "real_estate"},
]

# GICS Sector (Wikipedia) -> our coarse bucket
GICS_TO_BUCKET = {
    "Information Technology": "tech_software",  # refined post-hoc for HW vs SW
    "Health Care": "healthcare",
    "Financials": "financials",
    "Consumer Discretionary": "consumer_discretionary",
    "Communication Services": "comms",
    "Industrials": "industrials",
    "Consumer Staples": "consumer_staples",
    "Energy": "energy",
    "Utilities": "utilities",
    "Real Estate": "real_estate",
    "Materials": "materials",
}


class SP500TableParser(HTMLParser):
    """Extract S&P 500 constituents from the first wikitable on the page.

    The first table on /wiki/List_of_S%26P_500_companies has the headers:
        Symbol | Security | GICS Sector | GICS Sub-Industry | Headquarters Location | Date added | CIK | Founded
    We grab columns 0, 1, 2 and stop after the first table closes.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_table = False
        self._table_count = 0
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []
        self._done = False
        # The Symbol column uses an <a> linking to the company's page; we
        # accumulate raw text including link text. First <td> contains an <a>.

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        attrs_d = dict(attrs)
        if tag == "table":
            cls = attrs_d.get("class") or ""
            if "wikitable" in cls and not self._in_table and self._table_count == 0:
                self._in_table = True
                self._table_count += 1
        elif self._in_table and tag == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag in ("td", "th"):
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if self._in_cell and tag in ("td", "th"):
            self._current_row.append("".join(self._current_cell).strip())
            self._in_cell = False
            self._current_cell = []
        elif self._in_row and tag == "tr":
            if self._current_row:
                self.rows.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif self._in_table and tag == "table":
            self._in_table = False
            self._done = True

    def handle_data(self, data: str) -> None:
        if self._in_cell and not self._done:
            self._current_cell.append(data)


def fetch_wikipedia() -> list[dict] | None:
    req = urllib.request.Request(
        WIKI_URL,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (compatible; structural-isomorphism/d1-phase-detector; "
                "+https://github.com/dada8899/structural-isomorphism)"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[fetch_sp500] wikipedia fetch failed: {e}", file=sys.stderr)
        return None

    parser = SP500TableParser()
    try:
        parser.feed(html)
    except Exception as e:  # noqa: BLE001
        print(f"[fetch_sp500] html parse failed: {e}", file=sys.stderr)
        return None

    if not parser.rows or len(parser.rows) < 100:
        print(
            f"[fetch_sp500] parser yielded only {len(parser.rows)} rows; suspecting drift",
            file=sys.stderr,
        )
        return None

    out: list[dict] = []
    # Skip header row.
    for row in parser.rows[1:]:
        if len(row) < 3:
            continue
        symbol = row[0].strip()
        name = row[1].strip()
        gics = row[2].strip()
        if not symbol or not name:
            continue
        # Strip footnote refs like "[note]" from name.
        if "[" in name:
            name = name.split("[", 1)[0].strip()
        sector = GICS_TO_BUCKET.get(gics, "other")
        out.append({"symbol": symbol, "name": name, "sector": sector})
    if len(out) < 400:
        print(
            f"[fetch_sp500] only {len(out)} rows parsed from wiki; falling back",
            file=sys.stderr,
        )
        return None
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="skip wikipedia fetch and use the static list",
    )
    args = parser.parse_args()

    rows: list[dict] | None = None
    if not args.force_fallback:
        rows = fetch_wikipedia()

    source = "wikipedia"
    if rows is None:
        rows = STATIC_FALLBACK
        source = "static_fallback"

    # Dedup by symbol, preserve order.
    seen: set[str] = set()
    dedup: list[dict] = []
    for r in rows:
        sym = r["symbol"]
        if sym in seen:
            continue
        seen.add(sym)
        dedup.append(r)

    args.output.write_text(
        json.dumps({"source": source, "count": len(dedup), "tickers": dedup}, indent=2) + "\n"
    )
    print(
        f"[fetch_sp500] wrote {len(dedup)} tickers from {source} to {args.output}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
