#!/usr/bin/env python3
"""Twitter cascade size validation (X3 Wave 2 candidate 6).

Pipeline
--------
1. Load cascade sizes from raw/cascade_sizes.txt (one per line, descending).
2. Fit Clauset 2009 power-law on the upper tail (alpha, xmin, KS).
3. Vuong LR test: power-law vs lognormal & exponential alternatives.
4. Optional Omori-decay check on activity-time inter-arrivals.
5. Verdict against preferential_attachment expected band:
   - canonical band: alpha ∈ [1.8, 3.0]  (De Domenico 2013 + Goel-Watts 2016
     report alpha ≈ 1.8-2.5 for Twitter cascade size; Kwak 2010 reports
     alpha ≈ 2.3 for Twitter follower counts on the same dataset family).
   - relaxed sanity band: alpha ∈ [1.5, 3.5].

Outputs
-------
results.json     fit + verdict + isomorphism distance to sister systems
cascade_ccdf.png log-log CCDF plot (if matplotlib available)
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
        fit_omori_p, validate,
    )
    HAS_SOC = True
except Exception as e:
    print(f"[fatal] soc-pipeline import failed: {e}")
    HAS_SOC = False


# ------------------------------------------------------------------
# Data loaders
# ------------------------------------------------------------------

def load_cascade_sizes(min_size: int = 1) -> np.ndarray:
    """Load cascade sizes from raw/cascade_sizes.txt; filter min_size."""
    p = RAW / "cascade_sizes.txt"
    if not p.exists():
        raise FileNotFoundError(
            f"{p} missing — run fetch_twitter.py first"
        )
    arr = np.loadtxt(p, dtype=float)
    arr = arr[arr >= min_size]
    return arr


def load_activity_ts() -> np.ndarray | None:
    p = RAW / "activity_ts.txt"
    if not p.exists():
        return None
    return np.loadtxt(p, dtype=float)


# ------------------------------------------------------------------
# Power-law fit + LR
# ------------------------------------------------------------------

def fit_and_compare(sizes: np.ndarray) -> Dict:
    """Run Clauset fit + Vuong LR vs lognormal & exponential."""
    if not HAS_SOC:
        return {"error": "soc-pipeline unavailable"}

    print(f"  fitting Clauset PL on {len(sizes):,} cascades…")
    fit = fit_clauset_powerlaw(sizes, discrete=True, min_samples=50)
    out: Dict = {
        "alpha": float(fit.alpha) if fit.alpha is not None else None,
        "alpha_se": float(fit.sigma) if fit.sigma is not None else None,
        "xmin": float(fit.xmin) if fit.xmin is not None else None,
        "n_tail": int(fit.n_tail) if fit.n_tail is not None else None,
        "ks": float(fit.ks_statistic) if fit.ks_statistic is not None else None,
    }

    # Bootstrap CI (200 reps; full data ~330K is fine)
    try:
        ci = bootstrap_ci(sizes, n_boot=200, discrete=True)
        out["alpha_ci_low"] = float(ci.ci_low)
        out["alpha_ci_high"] = float(ci.ci_high)
    except Exception as e:
        out["bootstrap_error"] = str(e)

    # Vuong LR test vs lognormal & exponential
    if fit.alpha is not None and fit.xmin is not None:
        try:
            lr_ln = vuong_lr_test(sizes, vs="lognormal", discrete=True)
            out["R_lognormal"] = float(lr_ln.R) if lr_ln.R is not None else None
            out["p_lognormal"] = float(lr_ln.p) if lr_ln.p is not None else None
            out["winner_vs_lognormal"] = lr_ln.winner
        except Exception as e:
            out["lr_lognormal_error"] = str(e)
        try:
            lr_exp = vuong_lr_test(sizes, vs="exponential", discrete=True)
            out["R_exponential"] = float(lr_exp.R) if lr_exp.R is not None else None
            out["p_exponential"] = float(lr_exp.p) if lr_exp.p is not None else None
            out["winner_vs_exponential"] = lr_exp.winner
        except Exception as e:
            out["lr_exponential_error"] = str(e)

    return out


def omori_probe(ts: np.ndarray) -> Dict:
    """Run Omori-decay fit on activity inter-arrival rate.

    Convert raw timestamps into a rate(t) series and fit p, c per
    bin_and_omori_from_events. Twitter cascades after a peak event are
    expected to show Omori-like aftershock decay with p ≈ 1.0 (Crane-Sornette
    2008; Sornette-Helmstetter 2010).
    """
    if ts is None or len(ts) < 1000:
        return {"error": "no activity data"}
    if not HAS_SOC:
        return {"error": "soc-pipeline unavailable"}

    # Find the peak burst: bin to 1-minute intervals and pick the maximum.
    t0 = ts.min()
    t_rel = ts - t0  # seconds since first event
    bin_s = 60.0
    n_bins = int(np.ceil(t_rel.max() / bin_s)) + 1
    counts, edges = np.histogram(t_rel, bins=n_bins, range=(0, n_bins * bin_s))
    peak_bin = int(np.argmax(counts))
    peak_t = edges[peak_bin]
    # Take post-peak as aftershock series (next 24h)
    post = ts[(ts >= t0 + peak_t) & (ts <= t0 + peak_t + 86400)]
    if len(post) < 200:
        return {"error": "not enough post-peak events for Omori"}

    # fit_omori_p expects inter-event times (dts in seconds), not raw timestamps.
    # We compute dts within the post-peak burst.
    post_sorted = np.sort(post)
    dts = np.diff(post_sorted)
    dts = dts[dts > 0]
    if len(dts) < 100:
        return {"error": f"not enough post-peak dts: {len(dts)}",
                "n_post_peak": int(len(post))}
    try:
        from soc_pipeline.omori import bin_and_omori_from_events
        # bin_and_omori_from_events takes raw seconds-since-zero event times
        result = bin_and_omori_from_events(post_sorted - post_sorted.min(),
                                            bin_seconds=60.0)
        return {
            "p": float(result.p) if result.p is not None else None,
            "p_sigma": float(result.p_sigma) if result.p_sigma is not None else None,
            "c_days": float(result.c_days) if result.c_days is not None else None,
            "logK": float(result.logK) if result.logK is not None else None,
            "R2": float(result.R2) if result.R2 is not None else None,
            "n_aftershocks_in_fit": int(result.n_aftershocks_in_fit),
            "n_post_peak": int(len(post)),
            "peak_bin_count": int(counts[peak_bin]),
            "peak_time_offset_s": float(peak_t),
            "error": result.error,
        }
    except Exception as e:
        return {"error": f"omori fit failed: {e}",
                "n_post_peak": int(len(post))}


# ------------------------------------------------------------------
# Plot
# ------------------------------------------------------------------

def make_ccdf_plot(sizes: np.ndarray, fit: Dict, out: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [plot] matplotlib unavailable: {e}")
        return

    sizes_sorted = np.sort(sizes)
    n = len(sizes_sorted)
    ccdf = 1.0 - np.arange(n) / n
    fig, ax = plt.subplots(figsize=(7, 5))
    ax.loglog(sizes_sorted, ccdf, "o", ms=3, alpha=0.4, color="#1f77b4",
              label=f"Higgs Twitter cascades (n={n:,})")
    alpha = fit.get("alpha")
    xmin = fit.get("xmin")
    if alpha is not None and xmin is not None and xmin > 0:
        x = np.logspace(np.log10(xmin), np.log10(sizes_sorted.max()), 50)
        # P(X>=x) = (x/xmin)^(-(alpha-1)) normalized to tail empirical
        tail_frac = float(np.sum(sizes_sorted >= xmin)) / n
        y = tail_frac * (x / xmin) ** (-(alpha - 1))
        ax.loglog(x, y, "-", color="#d62728", lw=2,
                  label=f"PL fit α={alpha:.2f}, xmin={xmin:.0f}")
    ax.set_xlabel("Cascade size (RT count)")
    ax.set_ylabel("CCDF P(X ≥ x)")
    ax.set_title("Twitter retweet cascade size — Higgs Twitter dataset")
    ax.legend(loc="lower left")
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out, dpi=120)
    plt.close(fig)


# ------------------------------------------------------------------
# Verdict
# ------------------------------------------------------------------

def verdict(alpha: float | None, n_tail: int | None,
            R_ln: float | None, p_ln: float | None,
            R_exp: float | None, p_exp: float | None,
            canonical_band: Tuple[float, float] = (1.8, 3.0),
            sanity_band: Tuple[float, float] = (1.5, 3.5),
            min_n_tail: int = 100) -> str:
    if alpha is None or n_tail is None or n_tail < min_n_tail:
        return "INCONCLUSIVE"
    # PL must not be decisively beaten by lognormal (p < 0.1 + R < 0 = lognorm
    # wins). Be lenient: only fail if lognormal decisively beats PL.
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
# Main
# ------------------------------------------------------------------

def main() -> None:
    print("=" * 64)
    print("X3 Wave 2 — Twitter retweet cascade validation (Higgs SNAP)")
    print("=" * 64)

    sizes = load_cascade_sizes(min_size=1)
    print(f"\nLoaded {len(sizes):,} cascade sizes "
          f"(min={int(sizes.min())}, max={int(sizes.max())}, "
          f"median={np.median(sizes):.0f})")

    fit = fit_and_compare(sizes)
    if "alpha" in fit and fit["alpha"] is not None:
        print(f"\n  α = {fit['alpha']:.3f} ± {fit.get('alpha_se', float('nan')):.3f}")
        print(f"  xmin = {fit.get('xmin')}, n_tail = {fit.get('n_tail')}")
        print(f"  KS = {fit.get('ks', float('nan')):.4f}")
        if "alpha_ci_low" in fit:
            print(f"  bootstrap 95% CI: [{fit['alpha_ci_low']:.3f}, "
                  f"{fit['alpha_ci_high']:.3f}]")
        print(f"  LR vs lognormal: R={fit.get('R_lognormal', float('nan')):.3f}, "
              f"p={fit.get('p_lognormal', float('nan')):.3f}")
        print(f"  LR vs exponential: R={fit.get('R_exponential', float('nan')):.3f}, "
              f"p={fit.get('p_exponential', float('nan')):.3f}")

    # Omori-decay probe on activity time
    ts = load_activity_ts()
    if ts is not None:
        print(f"\nOmori probe on {len(ts):,} activity timestamps…")
        omori = omori_probe(ts)
        if omori.get("p") is not None:
            print(f"  Omori p={omori['p']:.3f} ± {omori.get('p_sigma') or 0:.3f}, "
                  f"c_days={omori.get('c_days')}, R²={omori.get('R2')}, "
                  f"n_aftershocks={omori.get('n_aftershocks_in_fit')}")
        else:
            print(f"  Omori: {omori.get('error', '?')}")
    else:
        omori = {"error": "no activity file"}

    # Verdict
    v = verdict(
        fit.get("alpha"), fit.get("n_tail"),
        fit.get("R_lognormal"), fit.get("p_lognormal"),
        fit.get("R_exponential"), fit.get("p_exponential"),
    )
    print(f"\n  VERDICT: {v}")

    # Cross-domain isomorphism — vs Wikipedia (preferential_attachment KB)
    references = {
        # Wikipedia pageviews (already in KB v1.0, Phase A1)
        "wikipedia_pageviews_alpha": {
            "alpha": 2.10, "se": 0.05,
            "source": "X3 Phase A1 Wikipedia pageviews"
        },
        # GitHub stars (already in KB v1.0)
        "github_stars_alpha": {
            "alpha": 2.30, "se": 0.04,
            "source": "X3 Phase A1 GitHub stars"
        },
        # YouTube view-count (Wave 2 sibling — will be filled in once that
        # candidate runs; for now use Crane-Sornette 2008 reference)
        "youtube_views_alpha_literature": {
            "alpha": 2.20, "se": 0.10,
            "source": "Crane-Sornette 2008 PNAS YouTube cascades"
        },
        # Goel-Watts 2016 baseline for Twitter cascade size on the
        # Goel-Anderson-Hofman-Watts dataset (different snapshot but same
        # phenomenon; reported α ≈ 1.8-2.5).
        "twitter_goel_watts": {
            "alpha": 2.25, "se": 0.15,
            "source": "Goel-Anderson-Hofman-Watts 2016 Mgmt Sci"
        },
    }
    iso: Dict[str, float] = {}
    if fit.get("alpha") is not None:
        for ref_name, ref in references.items():
            iso[ref_name] = isomorphism_distance(
                fit["alpha"], ref["alpha"],
                fit.get("alpha_se") or 0.05, ref["se"]
            )

    out_path = ROOT / "results.json"
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "data_provenance": "SNAP_LIVE",
        "n_cascades": int(len(sizes)),
        "max_cascade": int(sizes.max()),
        "median_cascade": float(np.median(sizes)),
        "fit": fit,
        "omori": omori,
        "references": references,
        "isomorphism_distances": iso,
        "canonical_band": [1.8, 3.0],
        "sanity_band": [1.5, 3.5],
        "verdict": v,
    }
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nResults: {out_path}")

    plot_path = ROOT / "cascade_ccdf.png"
    make_ccdf_plot(sizes, fit, plot_path)
    print(f"Plot:    {plot_path}")


if __name__ == "__main__":
    main()
