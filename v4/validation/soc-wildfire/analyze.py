#!/usr/bin/env python3
"""Layer 5 Phase 10 — wildfire size distribution SOC validation.

System: NIFC Interagency Fire Perimeter History (US, 2010s-2024)
Predicted class: soc_threshold_cascade (Drossel-Schwabl 1992 forest-fire model)
Expected α (size power-law, acres): literature [1.3, 2.5], canonical ≈ 1.4 (Malamud 1998)
"""

from __future__ import annotations

import json
import sys
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
FIRES = OUT_DIR / "fires.jsonl"
RESULTS = OUT_DIR / "wildfire_results.json"


def load_fires() -> list[dict]:
    fires = []
    with FIRES.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                fires.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return fires


def main():
    print("Loading fires...")
    fires = load_fires()
    print(f"  n_fires: {len(fires)}")
    sizes = np.array([f["size_acres"] for f in fires if "size_acres" in f])
    sizes = sizes[sizes > 0]
    print(f"  size_acres range: [{sizes.min():.2f}, {sizes.max():.0f}]")
    print(f"  median: {np.median(sizes):.1f}, mean: {sizes.mean():.1f}")

    # 1. Clauset power-law fit on size
    print("\n[1] Clauset power-law fit on size (acres)...")
    pl = fit_clauset_powerlaw(sizes, "wildfire_size", discrete=False)
    for k, v in pl.items():
        print(f"  {k}: {v}")

    # 2. Bootstrap CI on alpha
    print("\n[2] Bootstrap 95% CI on α (n_boot=100, takes ~30s)...")
    ci = bootstrap_alpha_ci(sizes, n_boot=100, discrete=False)
    print(f"  CI: {ci}")

    # 3. Inter-fire time Omori — stack waiting times after "main" fires
    print("\n[3] Omori on inter-fire times after main fires (>=95th pctl)...")
    # Build event-times in seconds from date strings
    from datetime import datetime
    rows = []
    for f in fires:
        try:
            dt = datetime.strptime(f["date"], "%Y-%m-%d")
            rows.append((dt.timestamp(), float(f["size_acres"])))
        except Exception:
            continue
    rows.sort()
    times = np.array([r[0] for r in rows])
    sizes_t = np.array([r[1] for r in rows])
    threshold = np.percentile(sizes_t, 95)
    print(f"  95th pctl size threshold: {threshold:.1f} acres")
    main_idx = np.where(sizes_t >= threshold)[0]
    print(f"  n main fires (size >= 95th pctl): {len(main_idx)}")
    aftershock_window_days = 60
    dts_sec = []
    for mi in main_idx:
        t0 = times[mi]
        t_end = t0 + aftershock_window_days * 86400
        mask = (times > t0) & (times < t_end) & (sizes_t < threshold)
        for tt in times[mask]:
            dts_sec.append(tt - t0)
    dts_sec = np.array(dts_sec)
    print(f"  n stacked aftershocks: {len(dts_sec)}")
    omori = omori_from_aftershock_stack(
        dts_sec,
        min_sec=86400.0,  # daily resolution (date-only data)
        max_sec=aftershock_window_days * 86400,
        n_bins=12,
        c_grid_days=(0.5, 1.0, 2.0, 5.0, 10.0),
    )
    print(f"  Omori result: {omori}")

    # 4. Null control (matched n)
    print("\n[4] Null control (matched n synthetic non-SOC)...")
    null_n = min(len(sizes), 20000)
    nulls = run_size_null_controls(seed=42, n=null_n)
    print(f"  all_rejected: {nulls['all_rejected']}")

    # Verdict
    predicted_narrow = (1.3, 2.5)
    literature = (1.3, 2.5)
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
        "phase": "Layer 5 Phase 10",
        "domain": "wildfire (NIFC US 2010s-2024)",
        "predicted_class": "soc_threshold_cascade (Drossel-Schwabl forest-fire model)",
        "n_total_fires": int(len(sizes)),
        "size_acres_range": [float(sizes.min()), float(sizes.max())],
        "size_acres_median": float(np.median(sizes)),
        "powerlaw_fit": pl,
        "bootstrap_ci": ci,
        "omori_inter_fire": omori,
        "null_control": {
            "all_rejected": nulls["all_rejected"],
            "n_per_null": null_n,
        },
        "predicted_alpha_range": list(predicted_narrow),
        "literature_alpha_range": list(literature),
        "verdict": verdict,
        "interpretation": (
            f"NIFC wildfire size distribution fit Clauset α = {alpha:.3f}"
            + (f" (bootstrap 95% CI [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}])" if isinstance(ci, dict) and 'ci_low' in ci else "")
            + f". Predicted [1.3, 2.5] from Drossel-Schwabl / Malamud 1998. "
            + f"vs lognormal R = {pl.get('vs_lognormal_R'):.3f} (p={pl.get('vs_lognormal_p'):.3g}), "
            + f"vs exponential R = {pl.get('vs_exponential_R'):.3f}. "
            + f"Pipeline null-control all rejected: {nulls['all_rejected']}. "
            + f"Verdict: {verdict}."
        ),
        "method_refs": [
            "Drossel-Schwabl 1992 PRL (forest-fire CA model)",
            "Malamud-Morein-Turcotte 1998 PNAS",
            "Clauset-Shalizi-Newman 2009 SIAM Review (power-law fitting)",
            "Bak-Tang-Wiesenfeld 1987 PRL (BTW sandpile / SOC)",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    print(f"\nVERDICT: {verdict}")
    print(f"  α = {alpha} (predicted [1.3, 2.5])")
    print(f"  Results saved: {RESULTS}")


if __name__ == "__main__":
    main()
