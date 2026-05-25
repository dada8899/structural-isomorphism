#!/usr/bin/env python3
"""
Cross-source Pythia α universality comparison.

Combines three α-fit sources for the Pythia scaling-law learning curve
L(C) = A · C^(-α) + L_inf and reports how robust the universality claim
(α nearly constant across model sizes) is when you change the fit source /
method:

  S1. LAMBADA v1                 — results_lambada.json     (SESSION-24,
                                   L_inf free, 8 sizes)
  S2. LAMBADA v2                 — results_lambada_v2.json  (SESSION-25,
                                   L_inf >= 1.0 constrained, 8 sizes)
  S3. Train-loss / lit-anchored  — results.json             (SESSION-24
                                   earlier, mixed REAL/SYNTHETIC + 2
                                   literature anchors, up to 7 Pythia sizes
                                   + 2 lit refs)

Outputs:
  - v4/validation/llm-scaling/figures/cross_source_alpha.png
  - v4/validation/llm-scaling/cross_source_summary.json
  - v4/validation/llm-scaling/pythia_12b_cross_source.json
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
FIG_DIR = ROOT / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# Pythia model size in parameters (used for log-x in panel A; literature only)
# ----------------------------------------------------------------------------
PYTHIA_N_PARAMS = {
    "pythia-70m": 70e6,
    "pythia-160m": 160e6,
    "pythia-410m": 410e6,
    "pythia-1b": 1.0e9,
    "pythia-1.4b": 1.4e9,
    "pythia-2.8b": 2.8e9,
    "pythia-6.9b": 6.9e9,
    "pythia-12b": 12e9,
}

PYTHIA_ORDER = [
    "pythia-70m",
    "pythia-160m",
    "pythia-410m",
    "pythia-1b",
    "pythia-1.4b",
    "pythia-2.8b",
    "pythia-6.9b",
    "pythia-12b",
]

# ----------------------------------------------------------------------------
# Universality verdict thresholds (same convention as SESSION-24 handoff §6.3)
# ----------------------------------------------------------------------------
CV_TIGHT_MAX = 0.15
CV_MODERATE_MAX = 0.20
# (>0.20 = BROAD_SPREAD)


def verdict(cv: float) -> str:
    if cv <= CV_TIGHT_MAX:
        return "TIGHT_UNIVERSALITY"
    if cv <= CV_MODERATE_MAX:
        return "MODERATE_UNIVERSALITY"
    return "BROAD_SPREAD"


# ----------------------------------------------------------------------------
# Load all 3 source JSONs into one tidy DataFrame
# ----------------------------------------------------------------------------
def load_sources() -> pd.DataFrame:
    rows: list[dict] = []

    # S1: LAMBADA v1
    with open(ROOT / "results_lambada.json") as f:
        s1 = json.load(f)
    for size, fit in s1["per_size_fits"].items():
        if not size.startswith("pythia"):
            continue
        rows.append(
            dict(
                source="LAMBADA_v1",
                size=size,
                n_params=PYTHIA_N_PARAMS.get(size, np.nan),
                alpha=fit["alpha"],
                alpha_se=fit["alpha_se"],
                R2=fit["R2"],
                n_points=fit["n_points"],
                L_inf=fit["L_inf"],
                provenance=fit.get("provenance", ""),
            )
        )

    # S2: LAMBADA v2
    with open(ROOT / "results_lambada_v2.json") as f:
        s2 = json.load(f)
    for size, fit in s2["per_size_fits"].items():
        if not size.startswith("pythia"):
            continue
        rows.append(
            dict(
                source="LAMBADA_v2",
                size=size,
                n_params=PYTHIA_N_PARAMS.get(size, np.nan),
                alpha=fit["alpha"],
                alpha_se=fit["alpha_se"],
                R2=fit["R2"],
                n_points=fit["n_points"],
                L_inf=fit["L_inf"],
                provenance=fit.get("provenance", ""),
            )
        )

    # S3: train-loss / lit-anchored (results.json) — has 7 Pythia sizes (no 12b)
    # plus 2 literature anchors (Kaplan2020-GPT + Hoffmann2022-Chinchilla).
    # We attach the 2 literature anchors at a synthetic "size" key so they
    # surface in the per-source table but are excluded from per-(size) matrix.
    with open(ROOT / "results.json") as f:
        s3 = json.load(f)
    for name, fit in s3["fits"].items():
        if name.startswith("pythia"):
            rows.append(
                dict(
                    source="TRAIN_LOSS",
                    size=name,
                    n_params=PYTHIA_N_PARAMS.get(name, np.nan),
                    alpha=fit["alpha"],
                    alpha_se=fit["alpha_se"],
                    R2=fit["R2"],
                    n_points=fit["n_points"],
                    L_inf=fit["L_inf"],
                    provenance=fit.get("provenance", ""),
                )
            )
        else:
            # literature anchor row (kept for per-source verdict only)
            rows.append(
                dict(
                    source="TRAIN_LOSS_LIT",
                    size=name,
                    n_params=np.nan,
                    alpha=fit["alpha"],
                    alpha_se=fit["alpha_se"],
                    R2=fit["R2"],
                    n_points=fit["n_points"],
                    L_inf=fit["L_inf"],
                    provenance=fit.get("provenance", ""),
                )
            )

    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Per-source stats (mean α, σ_α, CV, mean R², verdict)
# ----------------------------------------------------------------------------
def per_source_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    For per-source universality verdicts we report 3 views of TRAIN_LOSS to be
    transparent about how subset choice changes the verdict:

      TRAIN_LOSS_RAW            = all 7 Pythia fits as-is (broken fits in)
      TRAIN_LOSS_R2_GE_0_95     = quality filter (drop R²<0.95)
      TRAIN_LOSS_WANDB_NO_1P4B  = drop pythia-1.4b (broken fit)
                                  ≈ SESSION-24 'Train-loss wandb mixed' row
      TRAIN_LOSS_LIT_SUBSET     = 3 best Pythia (160m/1b/6.9b) + 2 literature
                                  ≈ SESSION-24 'Literature anchored' row
    """
    out_rows = []

    def stat_row(label: str, sub: pd.DataFrame, note: str = "") -> dict:
        a = sub["alpha"].to_numpy()
        m = float(np.mean(a))
        s = float(np.std(a, ddof=1)) if len(a) > 1 else 0.0
        cv = float(s / m) if m else float("nan")
        r2 = float(np.mean(sub["R2"]))
        return dict(
            source=label,
            n_sizes=int(len(a)),
            alpha_mean=m,
            alpha_std=s,
            alpha_cv=cv,
            mean_R2=r2,
            verdict=verdict(cv),
            members=sub["size"].tolist(),
            note=note,
        )

    out_rows.append(stat_row("LAMBADA_v1", df[df.source == "LAMBADA_v1"]))
    out_rows.append(stat_row("LAMBADA_v2", df[df.source == "LAMBADA_v2"]))

    train = df[df.source == "TRAIN_LOSS"].copy()
    train_lit_only = df[df.source == "TRAIN_LOSS_LIT"].copy()

    out_rows.append(
        stat_row(
            "TRAIN_LOSS_RAW",
            train,
            note="all 7 Pythia fits as-is; includes 2 broken fits (1.4b R²<0, 2.8b R²~0)",
        )
    )

    train_r2 = train[train.R2 >= 0.95]
    out_rows.append(
        stat_row(
            "TRAIN_LOSS_R2_GE_0_95",
            train_r2,
            note="quality-filtered: drop R²<0.95 (removes 1.4b + 2.8b)",
        )
    )

    train_no_14b = train[train["size"] != "pythia-1.4b"]
    out_rows.append(
        stat_row(
            "TRAIN_LOSS_WANDB_NO_1P4B",
            train_no_14b,
            note="approx. SESSION-24 'Train-loss wandb mixed' (6 sizes, 1.4b dropped)",
        )
    )

    # Lit-anchored subset: best Pythia + literature anchors
    lit_pythia = train[train["size"].isin(["pythia-160m", "pythia-1b", "pythia-6.9b"])]
    lit_subset = pd.concat([lit_pythia, train_lit_only], ignore_index=True)
    out_rows.append(
        stat_row(
            "TRAIN_LOSS_LIT_SUBSET",
            lit_subset,
            note="approx. SESSION-24 'Literature anchored': 3 best Pythia (R²>0.95, α<0.2) + Kaplan2020-GPT + Hoffmann2022-Chinchilla",
        )
    )

    return pd.DataFrame(out_rows)


# ----------------------------------------------------------------------------
# Per-size matrix and per-size σ across sources
# ----------------------------------------------------------------------------
def per_size_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Wide matrix: rows = Pythia size, cols = source, cells = α.
    Only Pythia sizes (not lit anchors). Source-set for the matrix uses the
    three primary sources: LAMBADA_v1, LAMBADA_v2, TRAIN_LOSS (raw, so the
    reader can see broken fits explicitly).
    """
    pythia_df = df[df["size"].str.startswith("pythia")].copy()
    primary = pythia_df[pythia_df.source.isin(["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"])]
    wide = primary.pivot_table(index="size", columns="source", values="alpha", aggfunc="first")
    r2 = primary.pivot_table(index="size", columns="source", values="R2", aggfunc="first")
    # Reorder rows by parameter count
    order = [s for s in PYTHIA_ORDER if s in wide.index]
    wide = wide.loc[order]
    r2 = r2.loc[order]
    return wide, r2


def per_size_sigma(wide: pd.DataFrame) -> pd.DataFrame:
    """For each size, compute mean α + σ across available sources."""
    rows = []
    for size, row in wide.iterrows():
        vals = row.dropna().to_numpy()
        n = len(vals)
        m = float(np.mean(vals)) if n else float("nan")
        s = float(np.std(vals, ddof=1)) if n > 1 else 0.0
        cv = float(s / m) if m else float("nan")
        rows.append(
            dict(
                size=size,
                n_sources=n,
                alpha_mean_across_sources=m,
                alpha_sigma_across_sources=s,
                alpha_cv_across_sources=cv,
            )
        )
    return pd.DataFrame(rows)


# ----------------------------------------------------------------------------
# Pooled cross-source CV: treat every (size × source) Pythia α as one
# independent observation and compute CV over the whole cloud.
# ----------------------------------------------------------------------------
def pooled_stats(df: pd.DataFrame, restrict_high_quality: bool = False) -> dict:
    sub = df[df.source.isin(["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"])].copy()
    sub = sub[sub["size"].str.startswith("pythia")]
    if restrict_high_quality:
        sub = sub[sub.R2 >= 0.5]
    a = sub["alpha"].to_numpy()
    m = float(np.mean(a))
    s = float(np.std(a, ddof=1))
    cv = float(s / m) if m else float("nan")
    return dict(
        n_obs=int(len(a)),
        alpha_mean=m,
        alpha_std=s,
        alpha_cv=cv,
        verdict=verdict(cv),
        restrict_high_quality=restrict_high_quality,
    )


# ----------------------------------------------------------------------------
# Pythia-12b cross-source spotlight
# ----------------------------------------------------------------------------
def pythia_12b_spotlight(df: pd.DataFrame) -> dict:
    sub = df[df["size"] == "pythia-12b"].copy()
    per_source = {}
    for _, r in sub.iterrows():
        per_source[r["source"]] = dict(
            alpha=float(r["alpha"]),
            alpha_se=float(r["alpha_se"]),
            R2=float(r["R2"]),
            n_points=int(r["n_points"]),
            L_inf=float(r["L_inf"]),
            provenance=r["provenance"],
        )
    alphas = sub["alpha"].to_numpy()
    return dict(
        size="pythia-12b",
        n_sources=len(alphas),
        sources=per_source,
        alpha_mean=float(np.mean(alphas)) if len(alphas) else float("nan"),
        alpha_std=float(np.std(alphas, ddof=1)) if len(alphas) > 1 else 0.0,
        alpha_cv=(
            float(np.std(alphas, ddof=1) / np.mean(alphas))
            if len(alphas) > 1 and np.mean(alphas)
            else float("nan")
        ),
        note="pythia-12b only exists in LAMBADA v1 + v2; train-loss source did not include 12b checkpoints. σ here is across LAMBADA v1 vs v2 (L_inf free vs constrained).",
    )


# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------
def make_figure(df: pd.DataFrame, wide: pd.DataFrame, per_src: pd.DataFrame,
                pooled: dict, out_path: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))

    # ---------- Panel A: per-size α vs size, one line per source ----------
    ax = axes[0]
    pythia_df = df[df["size"].str.startswith("pythia")].copy()
    pythia_df["n_params"] = pythia_df["size"].map(PYTHIA_N_PARAMS)

    color_for = {
        "LAMBADA_v1": "#1f77b4",
        "LAMBADA_v2": "#d62728",
        "TRAIN_LOSS": "#2ca02c",
    }
    marker_for = {
        "LAMBADA_v1": "o",
        "LAMBADA_v2": "s",
        "TRAIN_LOSS": "^",
    }

    for src in ["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"]:
        sub = pythia_df[pythia_df.source == src].sort_values("n_params")
        if sub.empty:
            continue
        # mark broken fits (R²<0.5) with hollow markers
        good = sub[sub.R2 >= 0.5]
        bad = sub[sub.R2 < 0.5]
        ax.errorbar(
            good["n_params"],
            good["alpha"],
            yerr=good["alpha_se"],
            fmt=marker_for[src],
            color=color_for[src],
            label=f"{src} (R²≥0.5)",
            markersize=7,
            capsize=3,
            alpha=0.85,
        )
        if not bad.empty:
            ax.errorbar(
                bad["n_params"],
                bad["alpha"],
                yerr=bad["alpha_se"],
                fmt=marker_for[src],
                mfc="white",
                mec=color_for[src],
                ecolor=color_for[src],
                label=f"{src} broken (R²<0.5)",
                markersize=7,
                capsize=3,
                alpha=0.5,
            )

    ax.set_xscale("log")
    ax.set_xlabel("Pythia model size (N params)")
    ax.set_ylabel("learning-curve exponent α")
    ax.set_title("Per-size α across sources")
    ax.axhline(0.155, color="grey", linestyle=":", alpha=0.6, label="Chinchilla α_C ≈ 0.155")
    ax.grid(True, which="both", linestyle="--", alpha=0.3)
    ax.legend(fontsize=7, loc="upper right")
    ax.set_ylim(-0.05, 0.7)

    # ---------- Panel B: per-source CV bar chart with threshold bands ----
    ax = axes[1]
    src_labels = per_src["source"].tolist()
    cvs = per_src["alpha_cv"].to_numpy()
    n_sizes = per_src["n_sizes"].to_numpy()
    colors_b = []
    for cv in cvs:
        if cv <= CV_TIGHT_MAX:
            colors_b.append("#2ca02c")  # green
        elif cv <= CV_MODERATE_MAX:
            colors_b.append("#ff7f0e")  # orange
        else:
            colors_b.append("#d62728")  # red

    x = np.arange(len(src_labels))
    bars = ax.bar(x, cvs, color=colors_b, edgecolor="black", linewidth=0.5)
    for i, (b, n) in enumerate(zip(bars, n_sizes)):
        ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.01,
                f"n={n}", ha="center", fontsize=7)

    ax.axhspan(0, CV_TIGHT_MAX, color="#2ca02c", alpha=0.08, label="TIGHT ≤ 0.15")
    ax.axhspan(CV_TIGHT_MAX, CV_MODERATE_MAX, color="#ff7f0e", alpha=0.08,
               label=f"MODERATE ({CV_TIGHT_MAX}–{CV_MODERATE_MAX})")
    ax.axhspan(CV_MODERATE_MAX, max(cvs) * 1.15 if max(cvs) > CV_MODERATE_MAX else 0.5,
               color="#d62728", alpha=0.08, label="BROAD > 0.20")

    # pooled CV reference line
    ax.axhline(pooled["alpha_cv"], color="black", linestyle="--", linewidth=1.0,
               label=f"pooled CV = {pooled['alpha_cv']:.3f}")

    ax.set_xticks(x)
    ax.set_xticklabels([s.replace("_", "\n") for s in src_labels], rotation=0,
                       fontsize=7)
    ax.set_ylabel("CV(α) within source")
    ax.set_title("Per-source CV vs universality bands")
    ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, axis="y", linestyle="--", alpha=0.3)

    # ---------- Panel C: pooled α distribution across all (size, source) ----
    ax = axes[2]
    sub = df[(df.source.isin(["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"])) &
             (df["size"].str.startswith("pythia"))]

    for src in ["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"]:
        vals = sub[sub.source == src]["alpha"].to_numpy()
        ax.scatter(vals, np.full_like(vals, list(["LAMBADA_v1", "LAMBADA_v2", "TRAIN_LOSS"]).index(src)),
                   color=color_for[src], s=50, alpha=0.75,
                   edgecolor="black", linewidth=0.4, label=src)

    # quality-filtered pooled (R²>=0.5)
    pooled_q = pooled_stats(df, restrict_high_quality=True)
    ax.axvline(pooled["alpha_mean"], color="black", linestyle="--",
               label=f"pooled α̅ = {pooled['alpha_mean']:.3f} (CV={pooled['alpha_cv']:.3f})")
    ax.axvline(pooled_q["alpha_mean"], color="purple", linestyle=":",
               label=f"R²≥0.5 α̅ = {pooled_q['alpha_mean']:.3f} (CV={pooled_q['alpha_cv']:.3f})")
    ax.set_yticks([0, 1, 2])
    ax.set_yticklabels(["v1", "v2", "train"])
    ax.set_xlabel("α (every Pythia (size × source) observation)")
    ax.set_title("Pooled cross-source α cloud")
    ax.legend(fontsize=7, loc="lower right")
    ax.grid(True, axis="x", linestyle="--", alpha=0.3)

    fig.suptitle("Pythia learning-curve α: cross-source universality robustness",
                 fontsize=11, y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    print(f"[fig] wrote {out_path}")


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main() -> None:
    df = load_sources()
    print(f"[load] {len(df)} (size × source) rows")
    print(df.groupby("source").size())

    per_src = per_source_stats(df)
    print("\n[per-source stats]")
    print(per_src[["source", "n_sizes", "alpha_mean", "alpha_std", "alpha_cv",
                   "mean_R2", "verdict"]].to_string(index=False))

    wide, r2_wide = per_size_matrix(df)
    print("\n[per-size α matrix]")
    print(wide.round(4).to_string())

    sigmas = per_size_sigma(wide)
    print("\n[per-size cross-source σ]")
    print(sigmas.round(4).to_string(index=False))

    pooled = pooled_stats(df, restrict_high_quality=False)
    pooled_q = pooled_stats(df, restrict_high_quality=True)
    print(f"\n[pooled raw]            {pooled}")
    print(f"[pooled R²>=0.5 only]   {pooled_q}")

    spot = pythia_12b_spotlight(df)
    print(f"\n[pythia-12b spotlight]")
    for k, v in spot.items():
        print(f"  {k}: {v}")

    # ---------- write JSON summary ----------
    summary = dict(
        generated_at="SESSION-25 cross-source α comparison",
        sources={
            "LAMBADA_v1": "v4/validation/llm-scaling/results_lambada.json",
            "LAMBADA_v2": "v4/validation/llm-scaling/results_lambada_v2.json",
            "TRAIN_LOSS": "v4/validation/llm-scaling/results.json",
        },
        verdict_thresholds=dict(
            tight_max=CV_TIGHT_MAX,
            moderate_max=CV_MODERATE_MAX,
        ),
        per_source=per_src.to_dict(orient="records"),
        per_size_matrix=wide.where(wide.notna(), None).round(6).to_dict(orient="index"),
        per_size_R2_matrix=r2_wide.where(r2_wide.notna(), None).round(4).to_dict(orient="index"),
        per_size_cross_source_sigma=sigmas.to_dict(orient="records"),
        pooled_all=pooled,
        pooled_R2_filtered=pooled_q,
        pythia_12b_spotlight=spot,
    )
    out_json = ROOT / "cross_source_summary.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2, default=_json_default)
    print(f"\n[json] wrote {out_json}")

    # ---------- write pythia-12b standalone ----------
    out_12b = ROOT / "pythia_12b_cross_source.json"
    with open(out_12b, "w") as f:
        json.dump(spot, f, indent=2, default=_json_default)
    print(f"[json] wrote {out_12b}")

    # ---------- figure ----------
    make_figure(df, wide, per_src, pooled, FIG_DIR / "cross_source_alpha.png")

    # ---------- final verdict line ----------
    print("\n===== FINAL =====")
    print(f"Pooled CV (all Pythia obs):          {pooled['alpha_cv']:.4f} → {pooled['verdict']}")
    print(f"Pooled CV (R²>=0.5 filter):          {pooled_q['alpha_cv']:.4f} → {pooled_q['verdict']}")
    if spot["n_sources"] >= 2:
        a = spot["sources"]
        print("Pythia-12b α per source:")
        for src, info in a.items():
            print(f"  {src}: α={info['alpha']:.4f}  (R²={info['R2']:.3f})")
        print(f"  σ across sources = {spot['alpha_std']:.4f}  "
              f"(CV = {spot['alpha_cv']:.4f})")


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    raise TypeError(f"cannot serialize {type(o)}")


if __name__ == "__main__":
    main()
