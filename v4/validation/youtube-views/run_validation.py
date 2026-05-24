#!/usr/bin/env python3
"""YouTube view-count distribution validation (X3 Wave 2 candidate 8).

Pipeline
--------
1. Load max-view-count per video from raw/video_max_views.txt (one value
   per line, descending).
2. Fit Clauset 2009 continuous power-law on the upper tail.
3. Vuong LR vs lognormal & exponential.
4. Verdict against preferential_attachment expected band:
   - canonical: alpha ∈ [1.8, 3.0]  (Crane-Sornette 2008 YouTube ~2.0-2.5;
     Cha-Mislove-Gummadi 2009 YouTube SocComm ~2.1).
   - sanity: alpha ∈ [1.5, 3.5].

Outputs
-------
results.json     fit + verdict + isomorphism distances
views_ccdf.png   log-log CCDF + PL overlay
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Tuple

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


def load_view_counts() -> np.ndarray:
    p = RAW / "video_max_views.txt"
    if not p.exists():
        raise FileNotFoundError(f"{p} missing — run fetch_youtube.py first")
    arr = np.loadtxt(p, dtype=float)
    arr = arr[arr > 0]
    return arr


def fit_and_compare(x: np.ndarray) -> Dict:
    if not HAS_SOC:
        return {"error": "soc-pipeline unavailable"}
    print(f"  fitting Clauset PL on {len(x):,} videos…")
    # Continuous because view-counts are large integers — discrete model
    # would be slow and equivalent to continuous beyond xmin > 100.
    fit = fit_clauset_powerlaw(x, discrete=False, min_samples=100)
    out: Dict = {
        "alpha": float(fit.alpha) if fit.alpha is not None else None,
        "alpha_se": float(fit.sigma) if fit.sigma is not None else None,
        "xmin": float(fit.xmin) if fit.xmin is not None else None,
        "n_tail": int(fit.n_tail) if fit.n_tail is not None else None,
        "ks": float(fit.ks_statistic) if fit.ks_statistic is not None else None,
    }
    try:
        ci = bootstrap_ci(x, n_boot=200, discrete=False)
        out["alpha_ci_low"] = float(ci.ci_low)
        out["alpha_ci_high"] = float(ci.ci_high)
    except Exception as e:
        out["bootstrap_error"] = str(e)

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
        try:
            lr_tpl = vuong_lr_test(x, vs="truncated_power_law", discrete=False)
            out["R_truncated_pl"] = float(lr_tpl.R) if lr_tpl.R is not None else None
            out["p_truncated_pl"] = float(lr_tpl.p) if lr_tpl.p is not None else None
            out["winner_vs_truncated_pl"] = lr_tpl.winner
        except Exception as e:
            out["lr_tpl_error"] = str(e)
    return out


def verdict(alpha: float | None, n_tail: int | None,
            R_ln: float | None, p_ln: float | None,
            canonical_band: Tuple[float, float] = (1.8, 3.0),
            sanity_band: Tuple[float, float] = (1.5, 3.5),
            min_n_tail: int = 100) -> str:
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


def make_plot(x: np.ndarray, fit: Dict, out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [plot] matplotlib unavailable: {e}")
        return

    x_sorted = np.sort(x)
    n = len(x_sorted)
    ccdf = 1.0 - np.arange(n) / n
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.loglog(x_sorted, ccdf, ".", ms=3, alpha=0.5, color="#1f77b4",
              label=f"YouTube Trending US (n={n:,})")
    alpha = fit.get("alpha")
    xmin = fit.get("xmin")
    if alpha and xmin:
        x_pl = np.logspace(np.log10(xmin), np.log10(x_sorted.max()), 50)
        tail_frac = float(np.sum(x_sorted >= xmin)) / n
        y_pl = tail_frac * (x_pl / xmin) ** (-(alpha - 1))
        ax.loglog(x_pl, y_pl, "-", lw=2, color="#d62728",
                  label=f"PL fit α={alpha:.2f}, xmin={xmin:,.0f}")
    ax.set_xlabel("Max view count per video")
    ax.set_ylabel("CCDF P(X ≥ x)")
    ax.set_title("YouTube Trending US — per-video max view distribution")
    ax.legend(loc="lower left")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


def main() -> None:
    print("=" * 64)
    print("X3 Wave 2 — YouTube view-count validation (Trending US 2017-2018)")
    print("=" * 64)

    x = load_view_counts()
    print(f"\nLoaded {len(x):,} videos, "
          f"max={int(x.max()):,}, median={int(np.median(x)):,}, "
          f"min={int(x.min()):,}")

    fit = fit_and_compare(x)
    if fit.get("alpha") is not None:
        print(f"\n  α = {fit['alpha']:.3f} ± {fit.get('alpha_se', float('nan')):.3f}")
        print(f"  xmin = {fit.get('xmin'):,.0f}, n_tail = {fit.get('n_tail')}")
        print(f"  KS = {fit.get('ks', float('nan')):.4f}")
        if "alpha_ci_low" in fit:
            print(f"  bootstrap 95% CI: [{fit['alpha_ci_low']:.3f}, "
                  f"{fit['alpha_ci_high']:.3f}]")
        if "R_lognormal" in fit and fit["R_lognormal"] is not None:
            print(f"  LR vs lognormal: R={fit['R_lognormal']:.3f}, "
                  f"p={fit.get('p_lognormal', float('nan')):.3f}")
        if "R_exponential" in fit and fit["R_exponential"] is not None:
            print(f"  LR vs exponential: R={fit['R_exponential']:.3f}, "
                  f"p={fit.get('p_exponential', float('nan')):.3f}")
        if "R_truncated_pl" in fit and fit["R_truncated_pl"] is not None:
            print(f"  LR vs truncated PL: R={fit['R_truncated_pl']:.3f}, "
                  f"p={fit.get('p_truncated_pl', float('nan')):.3f}")

    v = verdict(fit.get("alpha"), fit.get("n_tail"),
                fit.get("R_lognormal"), fit.get("p_lognormal"))
    print(f"\n  VERDICT: {v}")

    # Cross-domain isomorphism
    references = {
        # X3 Wave 2 sibling — fresh result from companion validation
        "twitter_higgs_alpha": {
            "alpha": 1.898, "se": 0.004,
            "source": "X3 Wave 2 Higgs Twitter cascade (this session)"
        },
        "wikipedia_pageviews_alpha": {
            "alpha": 2.10, "se": 0.05,
            "source": "X3 Phase A1 Wikipedia pageviews"
        },
        "github_stars_alpha": {
            "alpha": 2.30, "se": 0.04,
            "source": "X3 Phase A1 GitHub stars"
        },
        "crane_sornette_2008_yt": {
            "alpha": 2.20, "se": 0.10,
            "source": "Crane-Sornette 2008 PNAS YouTube cascades"
        },
        "cha_mislove_2009_yt": {
            "alpha": 2.10, "se": 0.05,
            "source": "Cha-Mislove-Gummadi 2009 IMC YouTube views"
        },
    }
    iso = {}
    if fit.get("alpha") is not None:
        for name, ref in references.items():
            iso[name] = isomorphism_distance(
                fit["alpha"], ref["alpha"],
                fit.get("alpha_se") or 0.05, ref["se"]
            )

    out_path = ROOT / "results.json"
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_provenance": "GITHUB_MIRROR_LIVE",
        "n_videos": int(len(x)),
        "max_views": int(x.max()),
        "median_views": int(np.median(x)),
        "fit": fit,
        "references": references,
        "isomorphism_distances": iso,
        "canonical_band": [1.8, 3.0],
        "sanity_band": [1.5, 3.5],
        "verdict": v,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults: {out_path}")

    plot_path = ROOT / "views_ccdf.png"
    make_plot(x, fit, plot_path)
    print(f"Plot:    {plot_path}")


if __name__ == "__main__":
    main()
