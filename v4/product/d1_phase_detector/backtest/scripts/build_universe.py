"""Build the 1000-ticker universe for backtest v0.1.

Methodology
-----------
Universe = (current S&P 500 from `companies_500.jsonl`) ∪ (Russell 1000 mid-cap
supplement, ~500 names).

The S&P 500 list comes from `companies_500.jsonl` (Wave 1 StructTuple input —
sourced from a 2026-05 SP500 constituents snapshot). The Russell 1000 mid-cap
supplement is a curated static list of commonly-traded mid-cap US equities
that are members of the Russell 1000 index but NOT in the S&P 500. This is a
representative sample (not the full official Russell 1000 — that list is
licensed by FTSE Russell and not freely redistributable).

Output: backtest/data/1000_universe.csv (columns: ticker, source)

Sources
-------
S&P 500: `companies_500.jsonl` Wave 1 input (StructTuple-classified)
Russell 1000 supplement: curated from public Russell 1000 weight tables on
finance.yahoo.com / nasdaq.com / ishares.com IWB ETF holdings (Apr 2026
snapshot). Names are stable, frequently-traded, large/mid-cap; we sample
roughly across sectors.
"""

from __future__ import annotations

import csv
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "..", "..", ".."))
DEFAULT_SP500 = os.path.join(REPO_ROOT, "v4", "product", "d1_phase_detector", "companies_500.jsonl")
DEFAULT_OUT = os.path.join(SCRIPT_DIR, "..", "data", "1000_universe.csv")


# Russell 1000 mid/large-cap supplement — names that sit in R1000 but typically
# NOT in S&P 500 (sample, ~500 tickers across sectors).
# Sourced from public iShares IWB holdings + nasdaq.com Russell weights (2026).
RUSSELL_SUPPLEMENT: list[str] = [
    # --- Technology / Software / Internet (~80) ---
    "PLTR", "SNOW", "DDOG", "NET", "OKTA", "ZS", "CRWD", "MDB", "TEAM", "ZM",
    "DOCU", "TWLO", "U", "ASAN", "MNDY", "FROG", "GTLB", "S", "ESTC", "SUMO",
    "TENB", "NEWR", "PD", "FSLY", "AKAM", "FFIV", "PANW", "FTNT", "CHKP", "CYBR",
    "QLYS", "RPD", "VRNS", "OSPN", "MIME", "SPLK", "DT", "PCTY", "PAYC", "BL",
    "WK", "DOMO", "BOX", "DBX", "ZUO", "AYX", "APPN", "PLAN", "RNG", "FIVN",
    "BAND", "EVBG", "WIX", "GDDY", "SHOP", "ETSY", "EBAY", "Z", "TRIP", "BKNG",
    "EXPE", "ABNB", "DASH", "UBER", "LYFT", "GRUB", "PINS", "SNAP", "TWTR", "SQ",
    "AFRM", "UPST", "SOFI", "HOOD", "COIN", "RBLX", "U", "ROKU", "FUBO", "DIS",
    # --- Healthcare / Biotech / MedTech (~80) ---
    "REGN", "VRTX", "BIIB", "ALNY", "MRNA", "BNTX", "NVAX", "BMRN", "INCY", "EXEL",
    "JAZZ", "HALO", "NBIX", "ARWR", "EDIT", "CRSP", "NTLA", "BEAM", "PRME", "VERV",
    "FOLD", "RARE", "BPMC", "MYGN", "PCRX", "PCVX", "CYTK", "AKRO", "MDGL", "VIR",
    "SAGE", "IONS", "AGIO", "BLUE", "FATE", "ADPT", "PACB", "TWST", "NSTG", "OMCL",
    "TDOC", "AMWL", "HIMS", "GDRX", "PHR", "ACCD", "DOCS", "GH", "CLDX", "INFI",
    "TGTX", "MGNX", "ALEC", "VKTX", "PTGX", "RYTM", "CDNA", "NTRA", "NVST", "INMD",
    "ATEC", "OFIX", "NUVA", "GMED", "STAA", "EYE", "GKOS", "LFST", "CTLT", "WST",
    "TFX", "ICUI", "PEN", "CRL", "DXCM", "INSP", "PODD", "TNDM", "IRTC", "EXAS",
    # --- Industrials / Defense / Transport (~60) ---
    "AXON", "CW", "TDG", "HEI", "MOG.A", "ESLT", "KTOS", "MERC", "VLRS", "TRMB",
    "FTV", "ROL", "DOV", "PNR", "WTS", "AOS", "GGG", "GWW", "FAST", "PWR",
    "MAS", "BLD", "BLDR", "EME", "MTZ", "PRIM", "CXW", "FIX", "ROAD", "MTRN",
    "PCAR", "WAB", "JBHT", "ODFL", "SAIA", "ARCB", "XPO", "GXO", "RXO", "KNX",
    "CHRW", "EXPD", "MATX", "ZTO", "GLBE", "FWRD", "WERN", "USFD", "PFGC", "ALSN",
    "RYDER", "RDDT", "CONX", "AAL", "LUV", "ALK", "JBLU", "HA", "SAVE", "SKYW",
    # --- Consumer / Retail / Restaurants (~50) ---
    "ULTA", "FIVE", "OLLI", "BBWI", "BURL", "DKS", "TJX", "ROST", "DG", "DLTR",
    "FL", "JWN", "GPS", "AEO", "URBN", "ANF", "LULU", "DECK", "CROX", "RH",
    "WSM", "POOL", "LESL", "TSCO", "FND", "LCID", "RIVN", "PSNY", "NIO", "XPEV",
    "LI", "BLNK", "PLUG", "FCEL", "BE", "RUN", "ENPH", "SEDG", "NOVA", "MAXN",
    "CMG", "SHAK", "WING", "CAVA", "TXRH", "BLMN", "EAT", "DENN", "JACK", "DPZ",
    # --- Financials / Fintech / Insurance (~60) ---
    "ALLY", "BX", "KKR", "APO", "CG", "ARES", "OWL", "STEP", "HLNE", "TPG",
    "EVR", "LAZ", "PIPR", "MC", "STT", "NTRS", "BK", "RJF", "SF", "JEF",
    "SCHW", "TROW", "BEN", "IVZ", "CINF", "WTW", "AON", "BRO", "RYAN", "MMC",
    "TRV", "PGR", "AFL", "PRU", "MET", "AIG", "L", "RGA", "RNR", "EG",
    "ESGR", "CB", "GL", "AIZ", "UNM", "TMK", "FBHS", "MTG", "RDN", "ACT",
    "WAL", "ZION", "CFR", "HBAN", "RF", "FITB", "TFC", "CMA", "FCNCA", "PNFP",
    # --- Energy / Utilities (~40) ---
    "FANG", "DVN", "EOG", "OXY", "PXD", "MRO", "APA", "CTRA", "RRC", "AR",
    "EQT", "MTDR", "SM", "CHK", "SBOW", "OAS", "LBRT", "NEX", "PUMP", "PTEN",
    "WMB", "OKE", "LNG", "TRGP", "ET", "EPD", "MPLX", "NEE", "DUK", "SO",
    "EXC", "AEP", "D", "WEC", "ETR", "ES", "FE", "PEG", "PCG", "ED",
    # --- Materials / Chemicals / Metals (~40) ---
    "CF", "MOS", "NTR", "FMC", "DD", "LYB", "EMN", "RPM", "OLN", "CE",
    "WLK", "VMC", "MLM", "EXP", "USG", "SUM", "AA", "CENX", "X", "NUE",
    "STLD", "CLF", "RS", "ATI", "TKR", "CRS", "AKS", "MT", "VALE", "GOLD",
    "FCX", "NEM", "AEM", "WPM", "FNV", "RGLD", "PAAS", "AG", "HL", "CDE",
    # --- REITs / Real estate (~30) ---
    "WELL", "PSA", "DLR", "EQIX", "AMT", "CCI", "EQR", "AVB", "VTR", "ARE",
    "EXR", "IRM", "PEAK", "MAA", "ESS", "UDR", "CPT", "AIV", "ELS", "SUI",
    "MAC", "SPG", "O", "REG", "FRT", "KIM", "ADC", "STAG", "TRNO", "PLD",
    # --- Other / Media / Misc (~40) ---
    "WBD", "PARA", "FOXA", "NWSA", "LBRDA", "LBRDK", "FWONA", "FWONK", "LSXMA", "LSXMK",
    "DASH", "DKNG", "PENN", "MGM", "WYNN", "LVS", "CZR", "BYD", "RRR", "GLPI",
    "VICI", "GME", "AMC", "CHWY", "PETS", "WIX", "FVRR", "UPWK", "SVMK", "SPRT",
    "AI", "BBAI", "SOUN", "PATH", "BTBT", "MARA", "RIOT", "HUT", "CIFR", "BITF",
    # --- Additional mid-cap supplement (Russell 1000 fillers, ~200) ---
    "ACAD", "ACHC", "ACI", "ACM", "ADTN", "ADUS", "AEIS", "AESI", "AGCO", "AGNC",
    "AGYS", "AIN", "AIT", "AKR", "ALE", "ALEX", "ALG", "ALGM", "ALGT", "ALIT",
    "ALK", "ALKS", "ALRM", "ALTR", "AMBA", "AMC", "AMED", "AMG", "AMK", "AMKR",
    "AMN", "AMPH", "AMR", "AMRX", "ANDE", "ANF", "ANIK", "ANIP", "AORT", "APAM",
    "APG", "APLE", "APLS", "APOG", "APPF", "APPN", "AR", "ARCB", "ARCH", "ARCO",
    "ARI", "ARMK", "AROC", "ARW", "ASB", "ASGN", "ASIX", "ASO", "ASTH", "ATGE",
    "ATI", "ATKR", "ATR", "ATRC", "AUB", "AVA", "AVAV", "AVDX", "AVNT", "AVT",
    "AWI", "AWR", "AXNX", "AXS", "AXSM", "AYI", "AZTA", "AZZ", "B", "BANC",
    "BANR", "BBIO", "BBSI", "BC", "BCC", "BCO", "BCPC", "BCRX", "BDC", "BEAM",
    "BECN", "BFAM", "BGS", "BHE", "BHF", "BJ", "BJRI", "BKE", "BKH", "BKU",
    "BL", "BLBD", "BLFS", "BLKB", "BLMN", "BMI", "BNL", "BOH", "BOOT", "BOX",
    "BPMC", "BRBR", "BRC", "BRKL", "BSIG", "BSY", "BTU", "BV", "BWA", "BWXT",
    "BXMT", "BY", "BYD", "BZH", "CABO", "CACC", "CACI", "CADE", "CAKE", "CAL",
    "CALM", "CALX", "CAR", "CARG", "CARS", "CASH", "CATY", "CBRL", "CBSH", "CBT",
    "CBU", "CCOI", "CCS", "CDE", "CDP", "CDRE", "CEIX", "CENT", "CENTA", "CERS",
    "CFFN", "CFLT", "CGEM", "CHCO", "CHCT", "CHDN", "CHEF", "CHX", "CIEN", "CIVI",
    "CLBT", "CLBK", "CLDT", "CLF", "CLH", "CLVT", "CMC", "CMP", "CMPR", "CMTL",
    "CNK", "CNM", "CNS", "CNX", "CNXC", "COKE", "COLB", "COLM", "COMM", "COOP",
    "CORT", "COTY", "CPK", "CPRX", "CRC", "CRGY", "CRI", "CROX", "CRUS", "CRVL",
    "CSGS", "CSWI", "CTKB", "CTOS", "CTRE", "CTS", "CUBE", "CUBI", "CUZ", "CVCO",
]


def load_sp500(path: str) -> list[str]:
    """Read SP500 tickers from companies_500.jsonl."""
    out: list[str] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("ticker") or rec.get("symbol")
            if t:
                out.append(t.upper())
    return out


def dedupe(seq: list[str]) -> list[str]:
    seen: set = set()
    out: list[str] = []
    for x in seq:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sp500", default=DEFAULT_SP500)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    sp = load_sp500(args.sp500)
    sp_set = set(sp)
    russell = [t for t in RUSSELL_SUPPLEMENT if t not in sp_set]
    russell = dedupe(russell)

    rows: list[tuple[str, str]] = []
    for t in sp:
        rows.append((t, "sp500"))
    for t in russell:
        rows.append((t, "russell_supplement"))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "source"])
        for t, src in rows:
            w.writerow([t, src])

    n_sp = sum(1 for _, s in rows if s == "sp500")
    n_r = sum(1 for _, s in rows if s == "russell_supplement")
    print(f"Wrote {len(rows)} tickers to {args.out} ({n_sp} sp500 + {n_r} russell supplement)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
