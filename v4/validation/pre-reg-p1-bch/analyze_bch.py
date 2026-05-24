#!/usr/bin/env python3
"""Pre-reg P1 — Clauset 2009 power-law fit on BCH absolute daily log returns.

Imports the FROZEN pipeline from `soc_pipeline` package; does not modify it.

Pre-registration band (paper/v0-unified-pipeline-2026-05-13.md §8.2, P1):
    System: Bitcoin Cash daily log returns
    Class: SOC threshold-cascade (financial); inverse-cubic-law regime
    predicted: alpha = 2.8 +/- 0.3   -> [2.5, 3.1]
    literature: [2.0, 3.5] (Gopikrishnan/Stanley)

Verdict map (verdict_from_alpha_band):
    CONFIRMED        : alpha in [2.5, 3.1]
    CONFIRMED (literature band) : alpha in [2.0, 3.5] but outside predicted
    DEVIATING        : alpha outside literature band
    INCONCLUSIVE     : fit failed

Outputs:
    p1_fit_result.json   FitResult.to_dict() + bootstrap CI + verdict
    p1_ccdf.json         empirical CCDF for plotting
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

from soc_pipeline import (
    fit_clauset_powerlaw,
    bootstrap_ci,
    empirical_ccdf,
    verdict_from_alpha_band,
)

OUT_DIR = Path(__file__).resolve().parent
INTERVALS_FILE = OUT_DIR / "bch_intervals.json"
FIT_RESULT_FILE = OUT_DIR / "p1_fit_result.json"
CCDF_FILE = OUT_DIR / "p1_ccdf.json"

PREDICTED_BAND = (2.5, 3.1)  # 2.8 +/- 0.3
LITERATURE_BAND = (2.0, 3.5)


def main():
    if not INTERVALS_FILE.exists():
        print(f"[err] {INTERVALS_FILE} missing; run fetch_bch.py first", file=sys.stderr)
        sys.exit(1)

    with open(INTERVALS_FILE) as f:
        data = json.load(f)
    intervals = np.asarray(data["intervals_seconds"], dtype=float)
    intervals = intervals[np.isfinite(intervals) & (intervals > 0)]
    print(f"[load] n_intervals={len(intervals)} median={np.median(intervals):.4f}s "
          f"min={intervals.min():.6f}s max={intervals.max():.2f}s")

    # Clauset fit
    fit = fit_clauset_powerlaw(intervals, name="P1_bitcoin_cash_intervals", discrete=False)
    print(f"[fit] alpha={fit.alpha} xmin={fit.xmin} sigma={fit.sigma} "
          f"n_tail={fit.n_tail} ks={fit.ks_statistic}")
    print(f"[fit] vs_lognormal R={fit.vs_lognormal_R} p={fit.vs_lognormal_p}")
    print(f"[fit] vs_exponential R={fit.vs_exponential_R} p={fit.vs_exponential_p}")

    # Bootstrap CI on alpha
    ci = bootstrap_ci(intervals, n_boot=200, seed=42, discrete=False)
    ci_dict = None
    if not ci.error:
        ci_dict = {
            "alpha_mean": ci.alpha_mean,
            "alpha_median": ci.alpha_median,
            "alpha_std": ci.alpha_std,
            "ci_low": ci.ci_low,
            "ci_high": ci.ci_high,
            "n_boot_succeeded": ci.n_boot_succeeded,
        }
        print(f"[ci] 95% CI on alpha = [{ci.ci_low:.3f}, {ci.ci_high:.3f}] "
              f"(mean={ci.alpha_mean:.3f}, std={ci.alpha_std:.3f})")
    else:
        print(f"[ci] bootstrap failed: {ci.error}")

    verdict = verdict_from_alpha_band(fit.alpha, PREDICTED_BAND, LITERATURE_BAND)
    print(f"[VERDICT] {verdict}  (predicted {PREDICTED_BAND}, literature {LITERATURE_BAND})")

    out = {
        "label": "P1_bitcoin_cash",
        "data_source": data.get("source"),
        "fetched_at_utc": data.get("fetched_at_utc"),
        "n_intervals": int(len(intervals)),
        "fit": fit.to_dict(),
        "bootstrap_ci": ci_dict,
        "predicted_band": list(PREDICTED_BAND),
        "literature_band": list(LITERATURE_BAND),
        "verdict": verdict,
    }
    with open(FIT_RESULT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] -> {FIT_RESULT_FILE}")

    # CCDF for plotting (subsample if huge for grid efficiency)
    sample = intervals if len(intervals) < 200_000 else np.random.default_rng(42).choice(intervals, 200_000, replace=False)
    grid, ccdf = empirical_ccdf(sample, n_points=200)
    with open(CCDF_FILE, "w") as f:
        json.dump({
            "grid": grid.tolist() if grid is not None else None,
            "ccdf": ccdf.tolist() if ccdf is not None else None,
            "alpha": fit.alpha,
            "xmin": fit.xmin,
            "n_sample": int(len(sample)),
        }, f)
    print(f"[ok] CCDF -> {CCDF_FILE}")


if __name__ == "__main__":
    main()
