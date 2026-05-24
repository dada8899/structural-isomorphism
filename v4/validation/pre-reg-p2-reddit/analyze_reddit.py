#!/usr/bin/env python3
"""Pre-reg P2 — Clauset 2009 power-law fit on Reddit cascade sizes.

Imports the FROZEN pipeline from `soc_pipeline` package; does not modify it.

Pre-registration band (paper/v0-unified-pipeline-2026-05-13.md Table 7, P2):
    predicted: alpha = 2.0 +/- 0.3   -> [1.7, 2.3]
    literature: [1.5, 2.5] (preferential-attachment + cascade, Cheng 2014)

Outputs:
    p2_fit_result.json
    p2_ccdf.json
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
SIZES_FILE = OUT_DIR / "reddit_cascade_sizes.json"
FIT_RESULT_FILE = OUT_DIR / "p2_fit_result.json"
CCDF_FILE = OUT_DIR / "p2_ccdf.json"

PREDICTED_BAND = (1.7, 2.3)
LITERATURE_BAND = (1.5, 2.5)


def main():
    if not SIZES_FILE.exists():
        print(f"[err] {SIZES_FILE} missing; run fetch_reddit.py first", file=sys.stderr)
        sys.exit(1)

    with open(SIZES_FILE) as f:
        data = json.load(f)
    sizes = np.asarray(data["cascade_sizes"], dtype=float)
    sizes = sizes[np.isfinite(sizes) & (sizes > 0)]
    print(f"[load] n_cascades={len(sizes)} median={int(np.median(sizes))} "
          f"max={int(sizes.max())} mean={sizes.mean():.1f}")

    # Cascade sizes are integer counts — use discrete fit
    fit = fit_clauset_powerlaw(sizes, name="P2_reddit_cascade_sizes", discrete=True)
    print(f"[fit] alpha={fit.alpha} xmin={fit.xmin} sigma={fit.sigma} "
          f"n_tail={fit.n_tail} ks={fit.ks_statistic}")
    print(f"[fit] vs_lognormal R={fit.vs_lognormal_R} p={fit.vs_lognormal_p}")
    print(f"[fit] vs_exponential R={fit.vs_exponential_R} p={fit.vs_exponential_p}")

    ci = bootstrap_ci(sizes, n_boot=200, seed=42, discrete=True)
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
        "label": "P2_reddit_cascade",
        "data_source": data.get("source"),
        "fetched_at_utc": data.get("fetched_at_utc"),
        "window_start_utc": data.get("window_start_utc"),
        "window_end_utc": data.get("window_end_utc"),
        "subreddits": data.get("subreddits"),
        "n_cascades": int(len(sizes)),
        "fit": fit.to_dict(),
        "bootstrap_ci": ci_dict,
        "predicted_band": list(PREDICTED_BAND),
        "literature_band": list(LITERATURE_BAND),
        "verdict": verdict,
    }
    with open(FIT_RESULT_FILE, "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] -> {FIT_RESULT_FILE}")

    grid, ccdf = empirical_ccdf(sizes, n_points=200)
    with open(CCDF_FILE, "w") as f:
        json.dump({
            "grid": grid.tolist() if grid is not None else None,
            "ccdf": ccdf.tolist() if ccdf is not None else None,
            "alpha": fit.alpha,
            "xmin": fit.xmin,
            "n_sample": int(len(sizes)),
        }, f)
    print(f"[ok] CCDF -> {CCDF_FILE}")


if __name__ == "__main__":
    main()
