#!/usr/bin/env python3
"""Layer 5 Phase 11 — solar flare peak-flux SOC validation.

System: NOAA NGDC GOES X-ray flare catalog 2000-2016
Predicted class: soc_threshold_cascade (Lu-Hamilton 1991 ApJ avalanche model)
Expected α on peak flux: literature [1.5, 2.5], canonical ≈ 1.7-1.9
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve()
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO / "v4" / "lib"))

from soc_pipeline import (  # noqa: E402
    bootstrap_alpha_ci,
    fit_clauset_powerlaw,
    omori_from_aftershock_stack,
    run_size_null_controls,
)

OUT_DIR = ROOT.parent
FLARES = OUT_DIR / "flares.jsonl"
RESULTS = OUT_DIR / "solar_results.json"


def load_flares() -> list[dict]:
    out = []
    with FLARES.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def main():
    print("Loading flares...")
    flares = load_flares()
    print(f"  n_flares: {len(flares)}")
    flux = np.array([f["peak_flux_W_m2"] for f in flares if "peak_flux_W_m2" in f])
    flux = flux[flux > 0]
    print(f"  peak_flux_W_m2 range: [{flux.min():.2e}, {flux.max():.2e}]")
    # Class distribution
    from collections import Counter
    dist = Counter(f["class_letter"] for f in flares if "class_letter" in f)
    print(f"  class distribution: {dict(dist)}")

    # 1. Clauset power-law fit
    print("\n[1] Clauset power-law fit on peak_flux (W/m²)...")
    pl = fit_clauset_powerlaw(flux, "flare_peak_flux", discrete=False)
    for k, v in pl.items():
        print(f"  {k}: {v}")

    # 2. Bootstrap CI
    print("\n[2] Bootstrap 95% CI on α (n_boot=100, takes ~20s)...")
    ci = bootstrap_alpha_ci(flux, n_boot=100, discrete=False)
    print(f"  CI: {ci}")

    # 3. Omori on inter-flare times after X-class events
    print("\n[3] Omori on inter-flare times after X-class mainshocks...")
    rows = []
    for f in flares:
        try:
            t = f["peak_ts"]
            fl = float(f["peak_flux_W_m2"])
            rows.append((t, fl, f["class_letter"]))
        except Exception:
            continue
    rows.sort()
    times = np.array([r[0] for r in rows])
    fluxes = np.array([r[1] for r in rows])
    letters = np.array([r[2] for r in rows])
    main_idx = np.where(letters == "X")[0]
    print(f"  n X-class mainshocks: {len(main_idx)}")
    aftershock_window_hours = 72
    dts_sec = []
    for mi in main_idx:
        t0 = times[mi]
        t_end = t0 + aftershock_window_hours * 3600
        mask = (times > t0) & (times < t_end)
        for tt in times[mask]:
            dts_sec.append(tt - t0)
    dts_sec = np.array(dts_sec)
    print(f"  n stacked aftershocks: {len(dts_sec)}")
    omori = omori_from_aftershock_stack(
        dts_sec,
        min_sec=300.0,  # 5 minutes
        max_sec=aftershock_window_hours * 3600,
        n_bins=20,
        c_grid_days=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2),
    )
    print(f"  Omori result: {omori}")

    # 4. Power-law on inter-arrival times (Wheatland 2000)
    print("\n[4] Power-law fit on inter-arrival times...")
    iat = np.diff(times)  # seconds between successive flares
    iat = iat[iat > 0]
    pl_iat = fit_clauset_powerlaw(iat, "flare_interarrival", discrete=False)
    print(f"  IAT α: {pl_iat.get('alpha')}, R vs lognormal: {pl_iat.get('vs_lognormal_R')}")

    # 5. Null control
    print("\n[5] Null control (matched n)...")
    null_n = min(len(flux), 20000)
    nulls = run_size_null_controls(seed=42, n=null_n)
    print(f"  all_rejected: {nulls['all_rejected']}")

    # Verdict
    predicted_narrow = (1.5, 2.5)
    literature = (1.5, 2.5)
    alpha = pl.get("alpha")
    if alpha is None:
        verdict = "INCONCLUSIVE"
    elif predicted_narrow[0] <= alpha <= predicted_narrow[1]:
        verdict = "CONFIRMED"
    elif literature[0] <= alpha <= literature[1]:
        verdict = "CONFIRMED (literature band)"
    else:
        verdict = "DEVIATING"

    out = {
        "phase": "Layer 5 Phase 11",
        "domain": "solar flare X-ray (NOAA GOES 2000-2016)",
        "predicted_class": "soc_threshold_cascade (Lu-Hamilton 1991 avalanche model)",
        "n_total_flares": int(len(flux)),
        "peak_flux_range_W_m2": [float(flux.min()), float(flux.max())],
        "class_distribution": dict(dist),
        "powerlaw_fit_peak_flux": pl,
        "bootstrap_ci_peak_flux": ci,
        "powerlaw_fit_interarrival": pl_iat,
        "omori_after_X_class": omori,
        "null_control": {
            "all_rejected": nulls["all_rejected"],
            "n_per_null": null_n,
        },
        "predicted_alpha_range": list(predicted_narrow),
        "literature_alpha_range": list(literature),
        "verdict": verdict,
        "interpretation": (
            f"GOES X-ray flare peak-flux distribution α = {alpha:.3f}"
            + (f" (bootstrap 95% CI [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}])" if isinstance(ci, dict) and 'ci_low' in ci else "")
            + f". Predicted [1.5, 2.5] from Lu-Hamilton 1991 / Crosby 1993 / Aschwanden 2011. "
            + f"vs lognormal R = {pl.get('vs_lognormal_R'):.3f} (p={pl.get('vs_lognormal_p'):.3g}). "
            + f"Pipeline null-control all rejected: {nulls['all_rejected']}. Verdict: {verdict}."
        ),
        "method_refs": [
            "Lu-Hamilton 1991 ApJ (avalanche model for solar flares)",
            "Crosby-Aschwanden-Dennis 1993 Solar Phys (RHESSI flare statistics)",
            "Aschwanden 2011 Solar Phys (SOC review)",
            "Wheatland 2000 ApJ (flare inter-arrival times)",
            "Clauset-Shalizi-Newman 2009 SIAM Rev",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    print(f"\nVERDICT: {verdict}")
    print(f"  α = {alpha} (predicted [1.5, 2.5])")
    print(f"  Results saved: {RESULTS}")


if __name__ == "__main__":
    main()
