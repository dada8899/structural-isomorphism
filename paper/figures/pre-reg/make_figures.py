#!/usr/bin/env python3
"""Render CCDF figures for P1 BCH + P2 Reddit pre-registered replications.

Each figure shows:
  - Empirical CCDF (blue circles)
  - Fitted power-law tail (red line) over [xmin, max]
  - Pre-registered alpha band shaded (light gray slope envelope)
  - Verdict text annotation

Outputs:
  fig_p1_bch_ccdf.pdf + .png
  fig_p2_reddit_ccdf.pdf + .png
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[3]
FIG_DIR = Path(__file__).resolve().parent

CASES = [
    {
        "label": "P1: Bitcoin Cash daily log returns",
        "fit_file": REPO_ROOT / "v4/validation/pre-reg-p1-bch/p1_fit_result.json",
        "ccdf_file": REPO_ROOT / "v4/validation/pre-reg-p1-bch/p1_ccdf.json",
        "predicted_band": (2.5, 3.1),
        "literature_band": (2.0, 3.5),
        "xlabel": r"absolute daily log return $|r_t|$",
        "out_stem": "fig_p1_bch_ccdf",
    },
    {
        "label": "P2: Reddit comment cascade sizes",
        "fit_file": REPO_ROOT / "v4/validation/pre-reg-p2-reddit/p2_fit_result.json",
        "ccdf_file": REPO_ROOT / "v4/validation/pre-reg-p2-reddit/p2_ccdf.json",
        "predicted_band": (1.7, 2.3),
        "literature_band": (1.5, 2.5),
        "xlabel": r"cascade size $s$ (num\_comments)",
        "out_stem": "fig_p2_reddit_ccdf",
    },
]


def render_case(case: dict) -> None:
    with open(case["fit_file"]) as f:
        fit = json.load(f)
    with open(case["ccdf_file"]) as f:
        ccdf = json.load(f)

    grid = np.asarray(ccdf["grid"], dtype=float) if ccdf.get("grid") else None
    cc = np.asarray(ccdf["ccdf"], dtype=float) if ccdf.get("ccdf") else None
    if grid is None or cc is None:
        print(f"[skip] no CCDF data for {case['label']}")
        return

    alpha = ccdf.get("alpha")
    xmin = ccdf.get("xmin")
    verdict = fit.get("verdict", "")
    ci = fit.get("bootstrap_ci") or {}

    fig, ax = plt.subplots(figsize=(6.5, 4.5))

    # Empirical CCDF
    mask_pos = (cc > 0) & (grid > 0)
    ax.plot(
        grid[mask_pos], cc[mask_pos],
        "o", color="#1f77b4", markersize=3.5, alpha=0.7,
        label="empirical CCDF", zorder=2,
    )

    # Pre-registered band — shaded envelope of slopes
    plo, phi = case["predicted_band"]
    llo, lhi = case["literature_band"]
    if xmin is not None and xmin > 0:
        x_tail = np.geomspace(max(xmin, grid[mask_pos].min()), grid[mask_pos].max(), 100)
        # CCDF at xmin (from empirical)
        try:
            idx = np.searchsorted(grid, xmin)
            y_anchor = max(cc[min(idx, len(cc) - 1)], 1e-6)
        except Exception:
            y_anchor = cc[mask_pos][0]

        # Literature band envelope (wider, lighter)
        y_lit_lo = y_anchor * (x_tail / xmin) ** (-(llo - 1))
        y_lit_hi = y_anchor * (x_tail / xmin) ** (-(lhi - 1))
        ax.fill_between(x_tail, y_lit_lo, y_lit_hi,
                        color="#cccccc", alpha=0.3,
                        label=fr"literature band $\alpha\in[{llo},{lhi}]$",
                        zorder=1)

        # Predicted band envelope (tighter, darker)
        y_pred_lo = y_anchor * (x_tail / xmin) ** (-(plo - 1))
        y_pred_hi = y_anchor * (x_tail / xmin) ** (-(phi - 1))
        ax.fill_between(x_tail, y_pred_lo, y_pred_hi,
                        color="#888888", alpha=0.4,
                        label=fr"predicted band $\alpha\in[{plo},{phi}]$",
                        zorder=1.5)

        # Fitted alpha line
        if alpha is not None and np.isfinite(alpha):
            y_fit = y_anchor * (x_tail / xmin) ** (-(alpha - 1))
            ax.plot(x_tail, y_fit, "r-", lw=2.0,
                    label=fr"fit $\alpha = {alpha:.2f}$", zorder=3)
            ax.axvline(xmin, color="green", ls="--", lw=1, alpha=0.6,
                       label=fr"$x_\mathrm{{min}}={xmin:.3g}$")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(case["xlabel"])
    ax.set_ylabel(r"$P(X \geq x)$")
    title_parts = [case["label"]]
    if ci:
        title_parts.append(fr"$\hat\alpha={alpha:.2f}$, 95% CI [{ci['ci_low']:.2f}, {ci['ci_high']:.2f}], $n_\mathrm{{tail}}={fit['fit']['n_tail']}$")
    title_parts.append(f"verdict: {verdict}")
    ax.set_title("\n".join(title_parts), fontsize=10)
    ax.legend(loc="lower left", fontsize=8, framealpha=0.85)
    ax.grid(True, alpha=0.3, which="both")

    fig.tight_layout()
    for ext in ("pdf", "png"):
        out_path = FIG_DIR / f"{case['out_stem']}.{ext}"
        fig.savefig(out_path, dpi=180 if ext == "png" else None)
        print(f"[ok] {out_path}")
    plt.close(fig)


def main():
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        if not case["fit_file"].exists():
            print(f"[skip] {case['fit_file']} missing")
            continue
        render_case(case)


if __name__ == "__main__":
    main()
