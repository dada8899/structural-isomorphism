#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate figure panels for hysteresis_first_order_transition validation."""

import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
FIGS = HERE / "figs"
FIGS.mkdir(exist_ok=True, parents=True)

# import the synthesizers and loaders from the run script
sys.path.insert(0, str(HERE))
import run_validation as rv  # noqa: E402

# --- Re-seed for reproducible figures ---
rv.RNG = np.random.default_rng(20260525)

# --- 1. Synthetic Landau hysteresis loop -------------------------------------
landau = rv.synth_landau_first_order()
preisach = rv.synth_preisach_cascade()

fig, axes = plt.subplots(1, 3, figsize=(15, 4))
ax = axes[0]
# plot one sweep h vs m
mask0 = landau["sweep_id"] == 0
ax.plot(landau["h"][mask0], landau["m"][mask0], lw=0.8, alpha=0.7, color="C3",
        label="sweep 0")
mask1 = landau["sweep_id"] == 1
ax.plot(landau["h"][mask1], landau["m"][mask1], lw=0.8, alpha=0.4, color="C0",
        label="sweep 1")
ax.set_xlabel("bias h"); ax.set_ylabel("order param m")
ax.set_title("Synthetic Landau φ⁴: 1st-order spinodal jumps\n(low inner-loop R²)")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[1]
mask0 = preisach["sweep_id"] == 0
mask1 = preisach["sweep_id"] == 1
ax.plot(preisach["h"][mask0], preisach["m"][mask0], lw=1, color="C2",
        alpha=0.85, label="sweep 0")
ax.plot(preisach["h"][mask1], preisach["m"][mask1], lw=1, color="C0",
        alpha=0.45, label="sweep 1")
ax.set_xlabel("bias h"); ax.set_ylabel("magnetisation M")
ax.set_title("Synthetic Preisach cascade\n(perfect inner-loop reproducibility R²=1.0)")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

ax = axes[2]
# synthetic saddle-node tipping
saddle = rv.synth_saddle_node(n_trials=6, n_steps=4000)
for tr in saddle["trials"]:
    ax.plot(tr["r"], tr["x"], lw=0.8, alpha=0.6)
ax.axvline(2 / (3 * math.sqrt(3)), color="k", ls="--", lw=0.8,
           label=r"fold $r_c$")
ax.set_xlabel("control r"); ax.set_ylabel("state x")
ax.set_title("Synthetic saddle-node (Scheffer)\n(slow drift through fold)")
ax.legend(fontsize=8)
ax.grid(alpha=0.3)

fig.suptitle("Three synthetic ground-truth references", y=1.02, fontsize=12)
fig.tight_layout()
fig.savefig(FIGS / "01_synthetic_references.png", dpi=120, bbox_inches="tight")
plt.close(fig)

# --- 2. US recession unemployment first-order jumps -------------------------
df_rec = rv.load_recession_panel()
fig, axes = plt.subplots(2, 1, figsize=(12, 6), sharex=True)
ax = axes[0]
ax.plot(df_rec["date"], df_rec["unrate"], color="C0", lw=1.2)
# shade recessions
rec_mask = df_rec["recession"].fillna(0) > 0
for i in range(1, len(df_rec)):
    if rec_mask.iloc[i] and not rec_mask.iloc[i - 1]:
        start = df_rec["date"].iloc[i]
    if not rec_mask.iloc[i] and rec_mask.iloc[i - 1]:
        end = df_rec["date"].iloc[i]
        ax.axvspan(start, end, color="C3", alpha=0.18)
ax.set_ylabel("UNRATE %"); ax.grid(alpha=0.3)
ax.set_title("US unemployment with NBER recessions shaded\n(first-order: rapid onset, slow recovery)")

ax = axes[1]
ax.plot(df_rec["date"], df_rec["gdp_growth"], color="C2", lw=0.9)
ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("date"); ax.set_ylabel("real GDP QoQ %")
ax.grid(alpha=0.3)
ax.set_title("Quarterly GDP growth: asymmetric jumps")
fig.tight_layout()
fig.savefig(FIGS / "02_us_recessions.png", dpi=120, bbox_inches="tight")
plt.close(fig)

# --- 3. Boom-bust on WTI oil -----------------------------------------------
df_oil = rv.load_oil_boom_bust()
fig, ax = plt.subplots(figsize=(12, 4))
ax.semilogy(df_oil["date"], df_oil["price"], lw=0.8, color="C1")
# annotate regime flips
flip_dates = []
cur = 0
for i in range(1, len(df_oil)):
    r = df_oil["regime"].iloc[i]
    if r != 0 and r != cur:
        flip_dates.append((df_oil["date"].iloc[i], r))
        cur = r
for d, r in flip_dates[:80]:
    ax.axvline(d, color="C3" if r < 0 else "C2", alpha=0.15, lw=0.6)
ax.set_ylabel("WTI $/bbl (log)"); ax.set_xlabel("date")
ax.set_title("WTI crude oil boom (green) / bust (red) regime flips, n_flips ~ 100")
ax.grid(alpha=0.3)
fig.tight_layout()
fig.savefig(FIGS / "03_wti_boom_bust.png", dpi=120, bbox_inches="tight")
plt.close(fig)

# --- 4. Signature comparison matrix ----------------------------------------
res = json.load(open(HERE / "results.json"))


def safe(d, *path):
    cur = d
    for p in path:
        if cur is None:
            return None
        cur = cur.get(p) if isinstance(cur, dict) else None
    return cur


rows = [
    ("Landau (1st-order)",
     safe(res, "synthetic", "landau_first_order", "S1_jump_strength", "strength"),
     safe(res, "synthetic", "landau_first_order", "S2_inner_loop_repro", "r2"),
     None,
     safe(res, "synthetic", "landau_first_order", "S6_bimodality", "separation"),
     safe(res, "synthetic", "landau_first_order", "latent_heat", "delta_L")),
    ("Preisach (cascade)",
     safe(res, "synthetic", "preisach_cascade", "S1_jump_strength", "strength"),
     safe(res, "synthetic", "preisach_cascade", "S2_inner_loop_repro", "r2"),
     None,
     safe(res, "synthetic", "preisach_cascade", "S6_bimodality", "separation"),
     None),
    ("Saddle-node",
     None, None,
     safe(res, "synthetic", "saddle_node", "S4_csd_detected_fraction"),
     None, None),
    ("US recessions",
     safe(res, "empirical", "recession_panel", "S1_jump_strength_rel_unrate"),
     None,
     safe(res, "empirical", "recession_panel", "S4_csd_detected_fraction"),
     safe(res, "empirical", "recession_panel", "S6_bimodality_unrate", "separation"),
     safe(res, "empirical", "recession_panel", "S1_jump_strength_abs_unrate_pp")),
    ("WTI oil boom-bust",
     safe(res, "empirical", "oil_boom_bust", "S1_regime_flip_log_jump_median"),
     None,
     safe(res, "empirical", "oil_boom_bust", "S4_csd_pre_bust_detected_frac"),
     safe(res, "empirical", "oil_boom_bust", "S6_bimodality_logprice", "separation"),
     None),
    ("Lake DO (Scheffer)",
     safe(res, "empirical", "lake_do_control", "S1_jump_strength", "strength"),
     None,
     None,
     safe(res, "empirical", "lake_do_control", "S6_bimodality", "separation"),
     None),
    ("Traffic (Preisach)",
     safe(res, "empirical", "traffic_qrho", "S1_jump_strength_q", "strength"),
     safe(res, "empirical", "traffic_qrho", "S2_inner_loop_repro_across_lanes", "r2"),
     None, None, None),
]

fig, ax = plt.subplots(figsize=(10, 4))
ax.axis("off")
cols = ["", "S1 jump", "S2 inner-R²", "S4 CSD frac", "S6 bimod. sep.", "ΔL / |Δu|pp"]
disp = [list(r) for r in rows]
for r in disp:
    for i in range(1, len(r)):
        if r[i] is None or (isinstance(r[i], float) and math.isnan(r[i])):
            r[i] = "—"
        else:
            r[i] = f"{r[i]:.3f}" if isinstance(r[i], float) else str(r[i])
the_table = ax.table(cellText=disp, colLabels=cols, loc="center",
                     cellLoc="center")
the_table.auto_set_font_size(False)
the_table.set_fontsize(9)
the_table.scale(1, 1.6)
ax.set_title("Signature matrix — 3-way distinguishability "
             "(Landau ≠ Preisach ≠ Saddle)", fontsize=11)
fig.tight_layout()
fig.savefig(FIGS / "04_signature_matrix.png", dpi=120, bbox_inches="tight")
plt.close(fig)

print("Wrote figures to", FIGS)
for p in sorted(FIGS.glob("*.png")):
    print(" ", p.name, p.stat().st_size, "bytes")
