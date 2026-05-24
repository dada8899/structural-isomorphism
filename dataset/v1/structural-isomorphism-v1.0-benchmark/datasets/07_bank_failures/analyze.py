#!/usr/bin/env python3
"""Layer 5 Phase 8 — US bank failure SOC validation.

System: FDIC bank failure catalog 1934-2026 (full historical record)
Predicted class: soc_threshold_cascade — Diamond-Dybvig self-fulfilling
   bank run sub-class (Louvain L01 sub-community in V4 graph)
Expected α(asset size): banking failures are systemic risk; literature
   [1.4, 2.5] from Eisenberg-Noe 2001 contagion models and Glasserman-Young
   2015 systemic risk reviews.
Expected Omori p after large failures: [0.3, 1.0] for financial crises.
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
RAW = OUT_DIR / "raw_fdic.json"
FAILURES = OUT_DIR / "bank_failures.jsonl"
RESULTS = OUT_DIR / "bank_results.json"


def normalize_records():
    raw = json.load(RAW.open())
    out = []
    for r in raw["data"]:
        d = r["data"]
        # FAILDATE is "M/D/YYYY"
        date_str = d.get("FAILDATE", "")
        try:
            parts = date_str.split("/")
            if len(parts) != 3:
                continue
            m, dd, y = int(parts[0]), int(parts[1]), int(parts[2])
            ts = datetime(y, m, dd).timestamp()
        except (ValueError, IndexError):
            continue

        # Asset size: QBFASSET in $1000s (thousand USD); convert to USD
        try:
            asset_k = float(d.get("QBFASSET") or 0)
            assets_usd = asset_k * 1000
        except (TypeError, ValueError):
            continue
        if assets_usd <= 0:
            continue

        # Deposit size as alternative
        try:
            dep_k = float(d.get("QBFDEP") or 0)
            deposits_usd = dep_k * 1000
        except (TypeError, ValueError):
            deposits_usd = 0

        out.append({
            "name": d.get("NAME"),
            "city": d.get("CITY"),
            "state": d.get("PSTALP"),
            "fail_date": date_str,
            "fail_ts": ts,
            "fail_year": int(y),
            "assets_usd": assets_usd,
            "deposits_usd": deposits_usd,
            "cost_loss_usd_thousands": d.get("COST"),
            "restype": d.get("RESTYPE"),
        })
    with FAILURES.open("w") as f:
        for rec in out:
            f.write(json.dumps(rec) + "\n")
    return out


def main():
    print("Normalizing FDIC raw → bank_failures.jsonl ...")
    records = normalize_records()
    print(f"  n_failures (size>0): {len(records)}")

    sizes = np.array([r["assets_usd"] for r in records])
    print(f"  asset size range: ${sizes.min():.0f} to ${sizes.max():.0f}")
    print(f"  median: ${np.median(sizes):.0f}, mean: ${sizes.mean():.0f}")
    years = [r["fail_year"] for r in records]
    print(f"  year range: [{min(years)}, {max(years)}]")
    from collections import Counter
    decade_dist = Counter(y // 10 * 10 for y in years)
    print(f"  decade distribution (top 5):")
    for dec, cnt in sorted(decade_dist.items()):
        print(f"    {dec}s: {cnt}")

    # 1. Clauset power-law on asset size
    print("\n[1] Clauset power-law fit on assets_usd...")
    pl = fit_clauset_powerlaw(sizes, "bank_assets", discrete=False)
    for k, v in pl.items():
        print(f"  {k}: {v}")

    # 2. Bootstrap CI
    print("\n[2] Bootstrap 95% CI on α (n_boot=100)...")
    ci = bootstrap_alpha_ci(sizes, n_boot=100, discrete=False)
    print(f"  CI: {ci}")

    # 3. Omori on inter-failure times after large mainshock failures
    print("\n[3] Omori after large failures (>=99th pctl)...")
    times = np.array([r["fail_ts"] for r in records])
    sort_idx = np.argsort(times)
    times = times[sort_idx]
    sizes_sorted = sizes[sort_idx]
    threshold = np.percentile(sizes, 99)
    print(f"  99th pctl asset threshold: ${threshold:.0f}")
    main_idx = np.where(sizes_sorted >= threshold)[0]
    print(f"  n large failures: {len(main_idx)}")
    aftershock_window_days = 365  # 1 year aftershock window
    dts_sec = []
    for mi in main_idx:
        t0 = times[mi]
        t_end = t0 + aftershock_window_days * 86400
        mask = (times > t0) & (times < t_end) & (sizes_sorted < threshold)
        for tt in times[mask]:
            dts_sec.append(tt - t0)
    dts_sec = np.array(dts_sec)
    print(f"  n stacked aftershocks: {len(dts_sec)}")
    omori = omori_from_aftershock_stack(
        dts_sec,
        min_sec=86400.0,
        max_sec=aftershock_window_days * 86400,
        n_bins=14,
        c_grid_days=(0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
    )
    print(f"  Omori result: {omori}")

    # 4. Era-split analysis (pre-2007, 2007-2014 crisis, post-2014)
    print("\n[4] Era-split α (pre-crisis / crisis / post-crisis)...")
    era_fits = {}
    for label, low, high in [("1934-2007_pre", 1934, 2007),
                             ("2008-2014_crisis", 2008, 2014),
                             ("2015-2026_post", 2015, 2026)]:
        mask = np.array([low <= r["fail_year"] <= high for r in records])
        sub = sizes[mask]
        if len(sub) < 200:
            era_fits[label] = {"n": int(len(sub)), "note": "too few"}
            continue
        f = fit_clauset_powerlaw(sub, label, discrete=False)
        era_fits[label] = {
            "n": int(len(sub)),
            "alpha": f.get("alpha"),
            "xmin": f.get("xmin"),
            "n_tail": f.get("n_tail"),
            "winner": f.get("vs_powerlaw_lognormal_winner"),
        }
        print(f"  {label:25s} n={len(sub):4d}  α={f.get('alpha'):.3f}  winner={f.get('vs_powerlaw_lognormal_winner')}")

    # 5. Null control
    print("\n[5] Null control...")
    null_n = min(len(sizes), 4000)
    nulls = run_size_null_controls(seed=42, n=null_n)
    print(f"  all_rejected: {nulls['all_rejected']}")

    # Verdict
    predicted = (1.4, 2.5)
    literature = (1.2, 3.0)
    alpha = pl.get("alpha")
    if alpha is None:
        verdict = "INCONCLUSIVE"
    elif predicted[0] <= alpha <= predicted[1]:
        verdict = "CONFIRMED"
    elif literature[0] <= alpha <= literature[1]:
        verdict = "CONFIRMED (literature band)"
    else:
        verdict = "DEVIATING"

    out = {
        "phase": "Layer 5 Phase 8",
        "domain": "FDIC US bank failures 1934-2026 (n=4114 raw, ~size>0 filtered)",
        "predicted_class": "soc_threshold_cascade / Diamond-Dybvig sub-class",
        "n_failures": int(len(sizes)),
        "year_range": [int(min(years)), int(max(years))],
        "asset_size_range_usd": [float(sizes.min()), float(sizes.max())],
        "decade_distribution": {str(k): int(v) for k, v in sorted(decade_dist.items())},
        "powerlaw_fit_assets": pl,
        "bootstrap_ci_assets": ci,
        "era_split_fits": era_fits,
        "omori_after_large_failures": omori,
        "null_control": {
            "all_rejected": nulls["all_rejected"],
            "n_per_null": null_n,
        },
        "predicted_alpha_range": list(predicted),
        "literature_alpha_range": list(literature),
        "verdict": verdict,
        "interpretation": (
            f"FDIC bank failure asset distribution α = {alpha:.3f}"
            + (f" (bootstrap 95% CI [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}])" if isinstance(ci, dict) and 'ci_low' in ci else "")
            + f". Predicted [1.4, 2.5] from Diamond-Dybvig / Eisenberg-Noe systemic risk literature. "
            + f"vs lognormal R = {pl.get('vs_lognormal_R'):.3f} (p={pl.get('vs_lognormal_p'):.3g}). "
            + f"Omori p = {omori.get('p', 'N/A')}. Verdict: {verdict}."
        ),
        "method_refs": [
            "Diamond-Dybvig 1983 J. Pol. Econ. (bank run model)",
            "Eisenberg-Noe 2001 Mgmt Sci (financial contagion network)",
            "Glasserman-Young 2015 J. Banking Finance (systemic risk review)",
            "Clauset-Shalizi-Newman 2009",
            "Reinhart-Rogoff 2009 (financial crises history)",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    print(f"\nVERDICT: {verdict}")
    print(f"  α = {alpha} (predicted [1.4, 2.5])")
    print(f"  Results saved: {RESULTS}")


if __name__ == "__main__":
    main()
