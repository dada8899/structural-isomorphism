#!/usr/bin/env python3
"""
01_phase_1_quick.py
===================

Minimal command-line reproduction of structural-isomorphism Phase 1
earthquake SOC fit. No Jupyter required.

Pulls one year of global M>=2.5 earthquakes from the USGS FDSN API, fits
Aki b-value with bootstrap CI, and runs a Clauset 2009 power-law MLE on
released energy. Prints a verdict.

Usage
-----
    pip install numpy scipy pandas matplotlib requests powerlaw
    python 01_phase_1_quick.py
    python 01_phase_1_quick.py --start 2020-01-01 --end 2025-01-01

Defaults pull 1 year (2020) which lands ~10k tail events. Five years
matches the published headline (b=1.084, CI [1.073, 1.094], n=37281).
"""

import argparse
import math
import sys
import time
import warnings
from typing import Tuple

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")

USGS = "https://earthquake.usgs.gov/fdsnws/event/1/query"


def fetch_usgs(start: str, end: str, min_mag: float = 3.5, retries: int = 3) -> pd.DataFrame:
    """Pull events in one window. USGS caps single queries at ~20000 events,
    so a 1-year M>=3.5 window (~15700 events) is safe; longer windows or
    lower M thresholds should be batched (see fetch_earthquakes.py)."""
    params = {
        "format": "geojson",
        "starttime": start,
        "endtime": end,
        "minmagnitude": min_mag,
        "orderby": "time-asc",
    }
    for attempt in range(retries):
        try:
            r = requests.get(USGS, params=params, timeout=180)
            r.raise_for_status()
            feat = r.json().get("features", [])
            break
        except Exception as e:
            print(f"  USGS attempt {attempt + 1} failed: {e}", file=sys.stderr)
            time.sleep(5)
    else:
        raise SystemExit("USGS API unreachable after 3 attempts")

    rows = []
    for f in feat:
        p = f.get("properties", {})
        rows.append({"mag": p.get("mag"), "type": p.get("type")})
    df = pd.DataFrame(rows)
    df = df[df["type"] == "earthquake"].dropna(subset=["mag"]).copy()
    df["mag"] = df["mag"].astype(float)
    return df


def estimate_mc(mags: np.ndarray, bin_width: float = 0.1) -> float:
    """Magnitude of completeness — max-curvature method (Wiemer-Wyss 2000)."""
    lo = math.floor(mags.min() * 10) / 10
    hi = math.ceil(mags.max() * 10) / 10
    bins = np.arange(lo, hi + bin_width, bin_width)
    counts, edges = np.histogram(mags, bins=bins)
    idx = int(np.argmax(counts))
    return float((edges[idx] + edges[idx + 1]) / 2)


def aki_b(mags_above: np.ndarray, mc: float, bin_width: float = 0.1) -> Tuple[float, float]:
    """Aki 1965 MLE for b, with Shi-Bolt 1982 sigma."""
    n = len(mags_above)
    if n < 50:
        raise SystemExit(f"too few events above Mc: n={n}")
    mean_mag = float(np.mean(mags_above))
    b = math.log10(math.e) / (mean_mag - (mc - bin_width / 2))
    var = float(np.sum((mags_above - mean_mag) ** 2)) / (n * (n - 1))
    sigma_b = 2.3 * b ** 2 * math.sqrt(var)
    return b, sigma_b


def bootstrap_b(mags_above: np.ndarray, mc: float, n_boot: int = 500,
                seed: int = 42) -> Tuple[float, float]:
    rng = np.random.default_rng(seed)
    n = len(mags_above)
    out = np.empty(n_boot)
    for i in range(n_boot):
        sample = rng.choice(mags_above, size=n, replace=True)
        out[i] = math.log10(math.e) / (sample.mean() - (mc - 0.05))
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def clauset_fit(mags_above: np.ndarray) -> dict:
    """Clauset-Shalizi-Newman 2009 MLE on energy s = 10^(1.5 M)."""
    try:
        import powerlaw
    except ImportError:
        return {"skipped": "pip install powerlaw to run this stage"}
    s = np.power(10.0, 1.5 * mags_above)
    s = s[np.isfinite(s) & (s > 0)]
    fit = powerlaw.Fit(s, discrete=False, xmin_distance="D", verbose=False)
    R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
    return {
        "alpha": float(fit.power_law.alpha),
        "sigma_alpha": float(fit.power_law.sigma),
        "xmin": float(fit.power_law.xmin),
        "n_fit": int((s >= fit.power_law.xmin).sum()),
        "vs_lognormal_R": float(R_ln),
        "vs_lognormal_p": float(p_ln),
        "vs_exponential_R": float(R_exp),
        "vs_exponential_p": float(p_exp),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2020-01-01", help="window start, YYYY-MM-DD (default 2020-01-01)")
    ap.add_argument("--end", default="2020-12-31", help="window end, YYYY-MM-DD (default 2020-12-31)")
    ap.add_argument("--min-mag", type=float, default=3.5, help="minimum magnitude (default 3.5; lower will exceed USGS 20k cap)")
    args = ap.parse_args()

    print(f"[1/5] fetching USGS {args.start} -> {args.end}, M>={args.min_mag} ...")
    df = fetch_usgs(args.start, args.end, args.min_mag)
    mags = df["mag"].to_numpy()
    print(f"      {len(mags)} tectonic earthquakes")

    print("[2/5] estimating Mc (max-curvature) ...")
    mc = estimate_mc(mags)
    above = mags[mags >= mc]
    print(f"      Mc={mc:.2f}, n_above={len(above)}")

    print("[3/5] Aki MLE b-value ...")
    b, sigma_b = aki_b(above, mc)
    print(f"      b = {b:.3f} +/- {sigma_b:.3f} (Shi-Bolt)")

    print("[4/5] bootstrap 95% CI (500 resamples) ...")
    ci_lo, ci_hi = bootstrap_b(above, mc)
    print(f"      CI = [{ci_lo:.3f}, {ci_hi:.3f}]")

    print("[5/5] Clauset 2009 fit on energy ...")
    pl = clauset_fit(above)
    if "alpha" in pl:
        print(f"      alpha = {pl['alpha']:.3f} +/- {pl['sigma_alpha']:.3f}")
        print(f"      vs lognormal:   R={pl['vs_lognormal_R']:+.2f}  p={pl['vs_lognormal_p']:.3f}")
        print(f"      vs exponential: R={pl['vs_exponential_R']:+.2f}  p={pl['vs_exponential_p']:.3f}")
    else:
        print(f"      {pl['skipped']}")

    narrow = (0.9 <= b <= 1.1)
    lit = (0.8 <= b <= 1.2)
    exp_rejected = "alpha" in pl and pl["vs_exponential_p"] < 0.1 and pl["vs_exponential_R"] > 0
    if narrow and exp_rejected:
        verdict = "CONFIRMED"
    elif lit and exp_rejected:
        verdict = "CONFIRMED (literature band)"
    elif "alpha" not in pl:
        verdict = "PARTIAL (b only — install powerlaw for full test)"
    else:
        verdict = "INCONCLUSIVE (try a longer window with --start 2020-01-01 --end 2025-01-01)"

    print()
    print(f"================ VERDICT: {verdict} ================")
    print(f"b        = {b:.3f}    CI [{ci_lo:.3f}, {ci_hi:.3f}]")
    if "alpha" in pl:
        print(f"alpha    = {pl['alpha']:.3f}   xmin = {pl['xmin']:.3e}   n_fit = {pl['n_fit']}")
    print("Reference (Phase 1 paper, 5 yr): b = 1.084, CI [1.073, 1.094], n=37281.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
