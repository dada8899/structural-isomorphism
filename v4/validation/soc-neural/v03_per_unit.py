#!/usr/bin/env python3
"""P0-N2 — Per-unit vs pooled avalanche detection on DANDI 000006 sample.

Approach:
  - Per-unit: detect avalanches *within each unit's spike train independently*,
    with a per-unit bin width = (per-unit-mean-IEI) * 1.0.
    Avalanche = consecutive non-empty bins, size = total spikes in run,
    duration = number of bins.
  - Pool across units AFTER per-unit detection (i.e., concatenate the per-unit
    avalanche lists into one corpus of {size, duration}).
  - Fit Clauset to that pooled corpus and compare with the pooled-spike
    detection result (from v0.2 §3.4).
"""
import json
from pathlib import Path

import h5py
import numpy as np
import powerlaw

NWB = Path("/Users/dadamini/Projects/structural-isomorphism/v4/validation/soc-neural/data/sample.nwb")
OUT = Path("/tmp/c1_v03_p0_n2_per_unit_results.json")


def bin_run_avalanches(times: np.ndarray, bin_width_s: float):
    if len(times) < 2:
        return np.array([]), np.array([])
    t0 = times.min()
    t1 = times.max()
    n_bins = int(np.ceil((t1 - t0) / bin_width_s)) + 1
    bin_idx = ((times - t0) / bin_width_s).astype(np.int64)
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    counts = np.bincount(bin_idx, minlength=n_bins).astype(np.int64)
    sizes = []
    durations = []
    cur_size = 0
    cur_dur = 0
    in_ava = False
    for c in counts:
        if c > 0:
            cur_size += int(c)
            cur_dur += 1
            in_ava = True
        else:
            if in_ava:
                sizes.append(cur_size)
                durations.append(cur_dur)
                cur_size = 0
                cur_dur = 0
                in_ava = False
    if in_ava:
        sizes.append(cur_size)
        durations.append(cur_dur)
    return np.array(sizes, dtype=np.int64), np.array(durations, dtype=np.int64)


def clauset(vals: np.ndarray, name: str):
    vals = vals[vals > 0]
    if len(vals) < 100:
        return {"error": f"too few ({len(vals)})", "name": name}
    fit = powerlaw.Fit(vals.astype(float), discrete=True, xmin_distance="D", verbose=False)
    alpha = float(fit.power_law.alpha)
    sigma = float(fit.power_law.sigma)
    xmin = float(fit.power_law.xmin)
    R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
    R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
    return {
        "name": name, "alpha": alpha, "sigma_alpha": sigma, "xmin": xmin,
        "n_total": int(len(vals)), "n_tail": int(np.sum(vals >= xmin)),
        "vs_lognormal_R": float(R_ln), "vs_lognormal_p": float(p_ln),
        "vs_exponential_R": float(R_exp), "vs_exponential_p": float(p_exp),
    }


def main():
    with h5py.File(NWB, "r") as f:
        spike_times = f["units/spike_times"][:]
        idx = f["units/spike_times_index"][:]
        unit_ids = f["units/id"][:]
    n_units = len(unit_ids)
    print(f"n_units={n_units}, n_spikes={len(spike_times)}")
    # spike_times_index is cumulative end index per unit
    per_unit_spikes = []
    prev = 0
    for end in idx:
        per_unit_spikes.append(np.sort(spike_times[prev:end]))
        prev = end
    # Per-unit detection
    all_sizes = []
    all_durs = []
    n_units_used = 0
    n_units_skipped_too_few = 0
    per_unit_stats = []
    for u, st in enumerate(per_unit_spikes):
        if len(st) < 100:
            n_units_skipped_too_few += 1
            continue
        iei = np.diff(st)
        iei = iei[iei > 0]
        if len(iei) < 50:
            n_units_skipped_too_few += 1
            continue
        bin_width = float(np.mean(iei))
        sizes, durs = bin_run_avalanches(st, bin_width)
        if len(sizes) < 5:
            n_units_skipped_too_few += 1
            continue
        all_sizes.append(sizes)
        all_durs.append(durs)
        per_unit_stats.append({
            "unit": int(unit_ids[u]),
            "n_spikes": int(len(st)),
            "mean_iei_ms": float(bin_width * 1000),
            "n_avalanches": int(len(sizes)),
            "size_mean": float(sizes.mean()),
            "duration_mean": float(durs.mean()),
        })
        n_units_used += 1
    sizes_pool = np.concatenate(all_sizes) if all_sizes else np.array([])
    durs_pool = np.concatenate(all_durs) if all_durs else np.array([])
    print(f"Used {n_units_used} units, skipped {n_units_skipped_too_few}")
    print(f"Total per-unit avalanches: {len(sizes_pool)}")
    # Fit Clauset
    size_fit = clauset(sizes_pool, "size_per_unit")
    dur_fit = clauset(durs_pool, "duration_per_unit")
    # Scaling relation gamma = <s|T> ~ T^gamma
    T_unique = np.unique(durs_pool.astype(int))
    T_bins = []
    mean_s = []
    for T in T_unique:
        mask = (durs_pool == T)
        if mask.sum() < 30:
            continue
        T_bins.append(int(T))
        mean_s.append(float(sizes_pool[mask].mean()))
    if len(T_bins) >= 4:
        lx = np.log(np.array(T_bins, dtype=float))
        ly = np.log(np.array(mean_s, dtype=float))
        A = np.vstack([np.ones(len(lx)), lx]).T
        coef, _, _, _ = np.linalg.lstsq(A, ly, rcond=None)
        intercept_fit, gamma_fit = float(coef[0]), float(coef[1])
        yhat = A @ coef
        ss_res = float(np.sum((ly - yhat) ** 2))
        ss_tot = float(np.sum((ly - ly.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot
        # standard error of slope
        sigma2 = ss_res / (len(lx) - 2)
        XtX_inv = np.linalg.inv(A.T @ A)
        se_gamma = float(np.sqrt(sigma2 * XtX_inv[1, 1]))
        scaling = {
            "gamma": gamma_fit, "gamma_sigma": se_gamma, "intercept": intercept_fit,
            "R2": r2, "n_T_bins": len(T_bins),
            "T_range": [min(T_bins), max(T_bins)],
        }
    else:
        scaling = {"error": "too few T bins"}
    out = {
        "method": "per-unit avalanche detection (bin = per-unit mean IEI)",
        "n_units_total": int(n_units),
        "n_units_used": int(n_units_used),
        "n_units_skipped_too_few": int(n_units_skipped_too_few),
        "n_avalanches_pooled_after_per_unit_extraction": int(len(sizes_pool)),
        "size_fit": size_fit,
        "duration_fit": dur_fit,
        "scaling_relation": scaling,
        "per_unit_stats_sample": per_unit_stats[:5],
        "comparison_pooled_v0p2": {
            "size_alpha_pooled": 2.984,
            "duration_alpha_pooled": 2.757,
            "gamma_pooled": 1.098,
            "note": "v0.2 values from neural_results.json (pooled-spike detection)."
        },
    }
    OUT.write_text(json.dumps(out, indent=2, default=str))
    print(json.dumps({
        "n_units_used": n_units_used,
        "n_avalanches_per_unit_pool": int(len(sizes_pool)),
        "size_alpha_per_unit": size_fit.get("alpha"),
        "size_alpha_pooled_v0p2": 2.984,
        "duration_alpha_per_unit": dur_fit.get("alpha"),
        "duration_alpha_pooled_v0p2": 2.757,
        "gamma_per_unit": scaling.get("gamma"),
        "gamma_pooled_v0p2": 1.098,
    }, indent=2))


if __name__ == "__main__":
    main()
