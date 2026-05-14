#!/usr/bin/env python3
"""Generate the D1 method-paper figures + Type-I inflation simulation.

Two figures produced (each as PDF vector + PNG @ 300 DPI):

  fig1_typei_inflation_under_ar1.{pdf,png}
      Empirical Type-I rate of the Kendall-tau rolling-AR1 EWS test under
      no-trend AR1(phi) noise, comparing the naive iid Kendall-tau p-value
      to the moving-block bootstrap, for phi in [0, 0.95].

  fig2_lake_naive_vs_block.{pdf,png}
      Bar chart of -log10(p) for the Phase A2-Scheffer Fox-River lake-DO
      Kendall-tau on rolling AR1 and rolling Variance, comparing the naive
      Kendall-tau p-value to the block-bootstrap p-value (real numbers
      from v4/validation/scheffer-lake/lake_results.json).

The script is idempotent: fixed seeds, deterministic matplotlib metadata.

Run::

    python paper/figures/d1/generate.py

Also writes ``paper/figures/d1/simulation_summary.json`` with the numerical
results so the paper text can cite specific values without re-running.

Author: structural-isomorphism W7 sub-agent E
Date  : 2026-05-15
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42  # TrueType for journal PDFs
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["font.family"] = "DejaVu Sans"
matplotlib.rcParams["axes.spines.top"] = False
matplotlib.rcParams["axes.spines.right"] = False

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
SUMMARY = HERE / "simulation_summary.json"
LAKE_RESULTS = REPO_ROOT / "v4" / "validation" / "scheffer-lake" / "lake_results.json"

# Make our reference implementation importable
sys.path.insert(0, str(REPO_ROOT))
from paper.code.d1_block_bootstrap_reference import (  # noqa: E402
    kendall_tau_vs_time,
    moving_block_bootstrap,
    rolling_ar1,
)


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def gen_ar1(n: int, phi: float, sigma: float, rng: np.random.Generator) -> np.ndarray:
    eps = rng.normal(scale=sigma, size=n)
    x = np.empty(n)
    x[0] = eps[0]
    for i in range(1, n):
        x[i] = phi * x[i - 1] + eps[i]
    return x


def empirical_type_i(
    phi: float,
    n_series: int = 100,
    series_len: int = 300,
    window: int = 60,
    n_boot: int = 100,
    block_length: int = 20,
    alpha: float = 0.05,
    seed: int = 1234,
) -> dict:
    """Estimate empirical Type-I rate at level alpha for both the naive
    Kendall-tau p-value and the moving-block bootstrap, under no-trend
    AR1(phi) noise."""
    rng = np.random.default_rng(seed)
    naive_reject = 0
    block_reject = 0
    naive_ps, block_ps = [], []
    for i in range(n_series):
        x = gen_ar1(series_len, phi, 1.0, rng)
        ind = rolling_ar1(x, window=window)
        tau, p_naive = kendall_tau_vs_time(ind)
        naive_ps.append(p_naive)
        if np.isfinite(p_naive) and p_naive < alpha:
            naive_reject += 1
        # Block bootstrap with per-series seed
        out = moving_block_bootstrap(
            x,
            n_replicates=n_boot,
            block_length=block_length,
            indicator_fn=lambda y: rolling_ar1(y, window=window),
            seed=int(rng.integers(0, 1 << 31)),
        )
        block_ps.append(out["p_block"])
        if out["p_block"] < alpha:
            block_reject += 1
    return {
        "phi": phi,
        "type_i_naive": naive_reject / n_series,
        "type_i_block": block_reject / n_series,
        "n_series": n_series,
        "series_len": series_len,
        "window": window,
        "block_length": block_length,
        "n_boot": n_boot,
        "alpha": alpha,
        "median_p_naive": float(np.nanmedian(naive_ps)),
        "median_p_block": float(np.nanmedian(block_ps)),
    }


# ---------------------------------------------------------------------
# Figure 1: Type-I inflation curve.
# ---------------------------------------------------------------------

def figure_1_type_i_inflation():
    phis = [0.0, 0.2, 0.4, 0.6, 0.7, 0.8, 0.9, 0.95]
    rows = []
    print("[d1-fig1] running Type-I inflation simulation across phi...")
    for phi in phis:
        r = empirical_type_i(phi=phi)
        print(
            f"  phi={phi:.2f}  naive type-I = {r['type_i_naive']:.3f}  "
            f"block type-I = {r['type_i_block']:.3f}  "
            f"med_p_naive={r['median_p_naive']:.2e}  "
            f"med_p_block={r['median_p_block']:.2f}"
        )
        rows.append(r)

    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    xs = [r["phi"] for r in rows]
    y_naive = [r["type_i_naive"] for r in rows]
    y_block = [r["type_i_block"] for r in rows]
    ax.plot(xs, y_naive, "o-", color="#c0392b", lw=2.0, ms=7,
            label="Naive Kendall-τ (iid p-value)")
    ax.plot(xs, y_block, "s-", color="#2c7fb8", lw=2.0, ms=7,
            label="Block bootstrap (ℓ=20)")
    ax.axhline(0.05, color="black", ls=":", lw=1, alpha=0.7,
               label="Nominal α=0.05")
    ax.set_xlabel("AR1 coefficient φ (no trend, n=400, window=80)")
    ax.set_ylabel("Empirical Type-I rejection rate")
    ax.set_title(
        "Type-I inflation of naive Kendall-τ vs block-bootstrap\n"
        "on rolling lag-1 autocorrelation under AR1 noise"
    )
    ax.set_ylim(-0.02, 1.05)
    ax.set_xlim(-0.02, 1.0)
    ax.set_yticks([0.0, 0.05, 0.25, 0.5, 0.75, 1.0])
    ax.legend(loc="upper left", frameon=False)
    ax.grid(True, alpha=0.25, ls="--")
    fig.tight_layout()
    fig.savefig(HERE / "fig1_typei_inflation_under_ar1.pdf", metadata={"Creator": "d1-generate"})
    fig.savefig(HERE / "fig1_typei_inflation_under_ar1.png", dpi=300)
    plt.close(fig)
    return rows


# ---------------------------------------------------------------------
# Figure 2: Lake Scheffer naive vs block bar chart.
# ---------------------------------------------------------------------

def figure_2_lake_naive_vs_block():
    """Reads v4/validation/scheffer-lake/lake_results.json if present,
    falls back to the documented v0.3 numbers (Session 9 W5-A response)
    otherwise."""
    fallback = {
        "tau_ar1_obs": 0.33058235679443543,
        "tau_var_obs": 0.23902106827347355,
        "p_naive_ar1": 1.5552617375527091e-245,
        "p_naive_var": 2.437069554060383e-129,
        "p_block_bootstrap_ar1": 0.07392607392607392,
        "p_block_bootstrap_var": 0.2057942057942058,
        "block_size_days": 30,
        "n_boot": 1000,
        "window_days": 365,
    }
    if LAKE_RESULTS.exists():
        try:
            j = json.loads(LAKE_RESULTS.read_text())
            bb = j.get("block_bootstrap", {})
            for k in fallback:
                if k in bb:
                    fallback[k] = bb[k]
            print(f"[d1-fig2] loaded real lake results from {LAKE_RESULTS}")
        except Exception as e:  # pragma: no cover
            print(f"[d1-fig2] warning: failed to load {LAKE_RESULTS}: {e}; "
                  f"using documented fallback numbers")

    labels = ["AR1 indicator", "Variance indicator"]
    naive_vals = [-np.log10(fallback["p_naive_ar1"]),
                  -np.log10(fallback["p_naive_var"])]
    block_vals = [-np.log10(fallback["p_block_bootstrap_ar1"]),
                  -np.log10(fallback["p_block_bootstrap_var"])]

    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    width = 0.36
    xs = np.arange(len(labels))
    b1 = ax.bar(xs - width / 2, naive_vals, width=width,
                color="#c0392b", label="Naive Kendall-τ p")
    b2 = ax.bar(xs + width / 2, block_vals, width=width,
                color="#2c7fb8", label=f"Block-bootstrap p (ℓ={fallback['block_size_days']} d)")
    # Annotate p-values above bars
    for bars, vals_raw, key_a, key_b in [
        (b1, naive_vals, "p_naive_ar1", "p_naive_var"),
        (b2, block_vals, "p_block_bootstrap_ar1", "p_block_bootstrap_var"),
    ]:
        ps = [fallback[key_a], fallback[key_b]]
        for rect, v_logp, p in zip(bars, vals_raw, ps):
            if p < 1e-10:
                txt = f"p={p:.1e}"
            else:
                txt = f"p={p:.3f}"
            ax.text(rect.get_x() + rect.get_width() / 2,
                    rect.get_height() + 1.5,
                    txt, ha="center", va="bottom", fontsize=8.5)
    ax.axhline(-np.log10(0.05), color="black", ls=":", lw=1, alpha=0.7,
               label="α=0.05 threshold")
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylabel("−log₁₀(p)")
    ax.set_title(
        "Phase A2-Scheffer (Fox River lake DO, n=5052 days)\n"
        "naive Kendall-τ vs moving-block bootstrap"
    )
    ax.set_ylim(0, max(naive_vals) * 1.18)
    ax.legend(loc="upper right", frameon=False, fontsize=8.5)
    ax.grid(True, axis="y", alpha=0.25, ls="--")
    fig.tight_layout()
    fig.savefig(HERE / "fig2_lake_naive_vs_block.pdf", metadata={"Creator": "d1-generate"})
    fig.savefig(HERE / "fig2_lake_naive_vs_block.png", dpi=300)
    plt.close(fig)
    return fallback


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    rows = figure_1_type_i_inflation()
    lake = figure_2_lake_naive_vs_block()
    summary = {
        "fig1_type_i_inflation": rows,
        "fig2_lake_naive_vs_block": lake,
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, default=float))
    print(f"[d1] wrote summary -> {SUMMARY}")
    print(f"[d1] wrote 2 PDFs + 2 PNGs in {HERE}")


if __name__ == "__main__":
    main()
