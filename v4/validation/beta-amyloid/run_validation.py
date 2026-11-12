#!/usr/bin/env python3
"""Beta-amyloid burden distribution validation (X3 Wave 2 candidate 7).

Pipeline
--------
1. Load 5 Aβ burden series from Allen Brain TBI Donor Metric REST API:
   - ab42_pg_per_mg (ELISA, ~333 samples)
   - ab40_pg_per_mg (ELISA, ~328 samples)
   - ihc_a_beta (immunohistochemistry quantified area fraction, 377 samples)
   - ihc_a_beta_ffpe (FFPE IHC, 354 samples)
   - ab42_over_ab40_ratio (~328 samples)
2. For each series, fit Clauset 2009 continuous power-law on the upper tail.
3. Vuong LR vs lognormal & exponential.
4. Verdict against aggregation-kinetics expected band:
   - Smoluchowski / Family-Vicsek aggregation tail exponent τ ∈ [1.5, 2.5]
     (Family-Vicsek 1985; Krapivsky-Redner-Ben-Naim 2010 review).
   - Clauset PL exponent for the *cumulative* burden distribution
     interpreted directly as α = τ_smol + 1; thus the canonical α band
     for Aβ-load is [2.5, 3.5] under Smoluchowski coagulation, and
     [1.5, 2.5] under direct interpretation of the power-law density.
   - We use sanity band [1.5, 4.0] and canonical band [2.0, 3.5] to
     accommodate both conventions.

Outputs
-------
results.json     fit + verdict per series + cross-series isomorphism
amyloid_ccdf.png log-log CCDF overlay
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
RAW = ROOT / "raw"

sys.path.insert(0, str(REPO / "packages" / "soc-pipeline" / "src"))
try:
    from soc_pipeline import (
        fit_clauset_powerlaw, bootstrap_ci, vuong_lr_test,
    )
    HAS_SOC = True
except Exception as e:
    print(f"[fatal] soc-pipeline import failed: {e}")
    HAS_SOC = False


# ------------------------------------------------------------------
# Data loaders
# ------------------------------------------------------------------

SERIES = [
    "ab42_pg_per_mg",
    "ab40_pg_per_mg",
    "ihc_a_beta",
    "ihc_a_beta_ffpe",
    "ab42_over_ab40_ratio",
]


def load_series(name: str) -> np.ndarray:
    p = RAW / f"{name}.txt"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing — run fetch_amyloid.py first")
    arr = np.loadtxt(p, dtype=float)
    arr = arr[arr > 0]
    return arr


# ------------------------------------------------------------------
# Fit
# ------------------------------------------------------------------

def fit_one(name: str, x: np.ndarray) -> Dict:
    """Fit one Aβ burden series and run LR tests."""
    out: Dict = {
        "series": name,
        "n": int(len(x)),
        "min": float(x.min()),
        "max": float(x.max()),
        "median": float(np.median(x)),
        "mean": float(x.mean()),
    }
    if not HAS_SOC:
        out["error"] = "soc-pipeline unavailable"
        return out
    if len(x) < 50:
        out["error"] = f"too few samples: {len(x)}"
        return out

    # Continuous PL fit — biomarker values are real-valued
    print(f"  [{name}] fitting Clauset PL on n={len(x)}…")
    try:
        fit = fit_clauset_powerlaw(x, discrete=False, min_samples=50)
        out["alpha"] = float(fit.alpha) if fit.alpha is not None else None
        out["alpha_se"] = float(fit.sigma) if fit.sigma is not None else None
        out["xmin"] = float(fit.xmin) if fit.xmin is not None else None
        out["n_tail"] = int(fit.n_tail) if fit.n_tail is not None else None
        out["ks"] = float(fit.ks_statistic) if fit.ks_statistic is not None else None
    except Exception as e:
        out["fit_error"] = str(e)
        return out

    # Bootstrap CI on smaller series — fewer reps but still informative
    try:
        ci = bootstrap_ci(x, n_boot=100, discrete=False)
        out["alpha_ci_low"] = float(ci.ci_low)
        out["alpha_ci_high"] = float(ci.ci_high)
    except Exception as e:
        out["bootstrap_error"] = str(e)

    # Vuong LR vs lognormal & exponential
    if out.get("alpha") is not None:
        try:
            lr_ln = vuong_lr_test(x, vs="lognormal", discrete=False)
            out["R_lognormal"] = float(lr_ln.R) if lr_ln.R is not None else None
            out["p_lognormal"] = float(lr_ln.p) if lr_ln.p is not None else None
            out["winner_vs_lognormal"] = lr_ln.winner
        except Exception as e:
            out["lr_lognormal_error"] = str(e)
        try:
            lr_exp = vuong_lr_test(x, vs="exponential", discrete=False)
            out["R_exponential"] = float(lr_exp.R) if lr_exp.R is not None else None
            out["p_exponential"] = float(lr_exp.p) if lr_exp.p is not None else None
            out["winner_vs_exponential"] = lr_exp.winner
        except Exception as e:
            out["lr_exponential_error"] = str(e)
    return out


# ------------------------------------------------------------------
# Verdict
# ------------------------------------------------------------------

def verdict(alpha: float | None, n_tail: int | None,
            R_ln: float | None, p_ln: float | None,
            canonical_band: Tuple[float, float] = (2.0, 3.5),
            sanity_band: Tuple[float, float] = (1.5, 4.0),
            min_n_tail: int = 30) -> str:
    if alpha is None or n_tail is None or n_tail < min_n_tail:
        return "INCONCLUSIVE"
    lognormal_wins = (R_ln is not None and p_ln is not None
                      and R_ln < 0 and p_ln < 0.05)
    in_canonical = canonical_band[0] <= alpha <= canonical_band[1]
    in_sanity = sanity_band[0] <= alpha <= sanity_band[1]
    if in_canonical and not lognormal_wins:
        return "PASS"
    if in_sanity:
        return "INCONCLUSIVE"
    return "FAIL"


def isomorphism_distance(a: float, a_ref: float,
                         se_a: float, se_ref: float) -> float:
    pooled = float(np.sqrt(se_a ** 2 + se_ref ** 2))
    return float(abs(a - a_ref) / pooled) if pooled > 0 else float("inf")


# ------------------------------------------------------------------
# Plot
# ------------------------------------------------------------------

def make_plot(per_series: Dict, out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [plot] matplotlib unavailable: {e}")
        return

    fig, ax = plt.subplots(figsize=(8, 6))
    colors = {"ab42_pg_per_mg": "#1f77b4", "ab40_pg_per_mg": "#ff7f0e",
              "ihc_a_beta": "#2ca02c", "ihc_a_beta_ffpe": "#d62728",
              "ab42_over_ab40_ratio": "#9467bd"}
    for name, entry in per_series.items():
        x = entry.pop("_data", None)
        if x is None:
            continue
        x = np.sort(x)
        n = len(x)
        ccdf = 1.0 - np.arange(n) / n
        a = entry.get("alpha", float("nan"))
        ax.loglog(x, ccdf, ".", ms=3, alpha=0.5, color=colors.get(name, "gray"),
                  label=f"{name} α={a:.2f} (n={n})")
    ax.set_xlabel("Aβ burden (units vary by series)")
    ax.set_ylabel("CCDF P(X ≥ x)")
    ax.set_title("Beta-amyloid burden distributions — Allen Brain TBI study")
    ax.legend(loc="lower left", fontsize=9)
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ------------------------------------------------------------------
# Main
# ------------------------------------------------------------------

def main() -> None:
    print("=" * 64)
    print("X3 Wave 2 — Beta-amyloid burden validation (Allen Brain TBI)")
    print("=" * 64)

    per_series: Dict[str, Dict] = {}
    for name in SERIES:
        try:
            x = load_series(name)
        except FileNotFoundError as e:
            print(f"  [skip] {e}")
            continue
        entry = fit_one(name, x)
        if "alpha" in entry and entry["alpha"] is not None:
            print(f"    α={entry['alpha']:.3f} ± {entry.get('alpha_se', float('nan')):.3f}, "
                  f"xmin={entry.get('xmin'):.4g}, n_tail={entry.get('n_tail')}, "
                  f"KS={entry.get('ks', float('nan')):.4f}")
            if "alpha_ci_low" in entry:
                print(f"    bootstrap 95% CI: [{entry['alpha_ci_low']:.3f}, "
                      f"{entry['alpha_ci_high']:.3f}]")
            if "R_lognormal" in entry and entry["R_lognormal"] is not None:
                print(f"    LR vs lognormal: R={entry['R_lognormal']:.3f}, "
                      f"p={entry.get('p_lognormal', float('nan')):.3f}")
            if "R_exponential" in entry and entry["R_exponential"] is not None:
                print(f"    LR vs exponential: R={entry['R_exponential']:.3f}, "
                      f"p={entry.get('p_exponential', float('nan')):.3f}")
        v = verdict(entry.get("alpha"), entry.get("n_tail"),
                    entry.get("R_lognormal"), entry.get("p_lognormal"))
        entry["verdict"] = v
        print(f"    VERDICT: {v}")
        entry["_data"] = x
        per_series[name] = entry

    # Cross-series isomorphism: each pair of Aβ series should share α
    # (they all measure the same coagulating system in different ways).
    series_alphas = {k: (v.get("alpha"), v.get("alpha_se"))
                     for k, v in per_series.items()
                     if v.get("alpha") is not None}
    iso_within: Dict[str, Dict[str, float]] = {}
    for a_name, (a_val, a_se) in series_alphas.items():
        iso_within[a_name] = {}
        for b_name, (b_val, b_se) in series_alphas.items():
            if a_name == b_name:
                continue
            iso_within[a_name][b_name] = isomorphism_distance(
                a_val, b_val, a_se or 0.1, b_se or 0.1
            )

    # External references — Smoluchowski coagulation kinetics
    references = {
        # Family-Vicsek 1985 + Krapivsky-Redner 2010 review: aggregation
        # kernel K(i,j) ~ i^a * j^b gives tail tau = 1.5-2.5 for diffusion-
        # limited aggregation (DLA).
        "smoluchowski_dla_alpha": {
            "alpha": 2.50, "se": 0.20,
            "source": "Family-Vicsek 1985; Krapivsky-Redner 2010 review"
        },
        # Cruz et al. 1997 J. Neurosci.: distribution of plaque sizes in
        # AD brain, reported PL with α ≈ 1.6-1.8 for cross-sectional
        # plaque-area distribution.
        "cruz1997_plaque_alpha": {
            "alpha": 1.70, "se": 0.10,
            "source": "Cruz et al. 1997 J. Neurosci. 17:7873"
        },
        # Hartig et al. 2018: 5xFAD mouse plaque growth volume PL with
        # α ≈ 2.1 for volume distribution.
        "hartig2018_5xfad_alpha": {
            "alpha": 2.10, "se": 0.15,
            "source": "Hartig et al. 2018 Acta Neuropathol Comm 6:131"
        },
    }
    iso_external: Dict[str, Dict[str, float]] = {}
    for s_name, (s_val, s_se) in series_alphas.items():
        iso_external[s_name] = {}
        for ref_name, ref in references.items():
            iso_external[s_name][ref_name] = isomorphism_distance(
                s_val, ref["alpha"], s_se or 0.1, ref["se"]
            )

    # Save
    out_path = ROOT / "results.json"
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_provenance": "ALLEN_BRAIN_LIVE",
        "per_series": {k: {kk: vv for kk, vv in v.items() if kk != "_data"}
                       for k, v in per_series.items()},
        "iso_within_series": iso_within,
        "iso_vs_literature": iso_external,
        "references": references,
        "canonical_band": [2.0, 3.5],
        "sanity_band": [1.5, 4.0],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults: {out_path}")

    plot_path = ROOT / "amyloid_ccdf.png"
    make_plot(per_series, plot_path)
    print(f"Plot:    {plot_path}")


if __name__ == "__main__":
    main()
