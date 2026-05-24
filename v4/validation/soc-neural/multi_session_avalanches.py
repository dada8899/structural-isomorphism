#!/usr/bin/env python3
"""
C1 v0.3 P0-N1 (multi-session expansion) + P0-N2 (per-unit vs pooled).

For each DANDI:000006 session:
  - Load pooled spikes (P0-N2 baseline) and per-unit spike lists.
  - Detect avalanches on pooled spikes with bin = <IEI>.
  - Detect avalanches per-unit (each unit's spikes binned independently,
    avalanche = run of consecutive non-empty bins) and aggregate.
  - Fit tau (size) and alpha_T (duration) via powerlaw.Fit.
  - Compute scaling-relation gamma from mean(size|duration) ~ T^gamma.
  - Compute the "criticality target" gamma_pred = (alpha_T - 1)/(tau - 1).

Across all sessions, report:
  - Per-session (tau, alpha_T, gamma, gamma_pred)
  - Cross-session mean / SE / range
  - Whether the scaling relation gamma vs gamma_pred holds per-session
  - tau, alpha_T inside literature bands [1.5, 3.0] and [1.5, 2.5]

Output: multi_session_results.json
"""
import argparse
import json
import math
from pathlib import Path

import h5py
import numpy as np

try:
    import powerlaw
except ImportError:
    powerlaw = None

HERE = Path(__file__).resolve().parent
EXTRA = HERE / "data" / "extra_sessions"
ORIGINAL = HERE / "data" / "sample.nwb"
OUT = HERE / "multi_session_results.json"


def load_spike_units(path: Path):
    """Return (per_unit_spike_lists, all_spikes_pooled, n_units)."""
    with h5py.File(path, "r") as f:
        # NWB stores spike_times as a flat array; spike_times_index gives
        # cumulative end-index per unit
        spike_times = f["units/spike_times"][:]
        idx = f["units/spike_times_index"][:]
    n_units = len(idx)
    # Reconstruct per-unit spike lists
    per_unit = []
    start = 0
    for end in idx:
        per_unit.append(spike_times[start:end])
        start = end
    pooled = np.sort(spike_times)
    return per_unit, pooled, n_units


def avalanches_from_binned(counts: np.ndarray):
    """Standard Beggs-Plenz definition on a 1-D bin-count array."""
    sizes = []
    durations = []
    in_ava = False
    cur_size = 0
    cur_dur = 0
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


def bin_pooled(pooled: np.ndarray, bin_width_s: float):
    t0 = pooled.min(); t1 = pooled.max()
    n_bins = int(np.ceil((t1 - t0) / bin_width_s)) + 1
    bin_idx = np.clip(((pooled - t0) / bin_width_s).astype(np.int64), 0, n_bins - 1)
    counts = np.bincount(bin_idx, minlength=n_bins).astype(np.int64)
    return counts


def detect_avalanches_pooled(pooled, bin_width_s):
    counts = bin_pooled(pooled, bin_width_s)
    return avalanches_from_binned(counts)


def detect_avalanches_per_unit(per_unit, bin_width_s):
    """Per-unit avalanche detection (no spike pooling across units).

    Each unit produces its own avalanche list; aggregate sizes/durations.
    """
    all_sizes = []
    all_durs = []
    for spikes in per_unit:
        if len(spikes) < 5:
            continue
        spikes = np.sort(spikes)
        counts = bin_pooled(spikes, bin_width_s)
        s, d = avalanches_from_binned(counts)
        if len(s):
            all_sizes.append(s)
            all_durs.append(d)
    if not all_sizes:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    return np.concatenate(all_sizes), np.concatenate(all_durs)


def fit_distribution(vals, name):
    """Clauset 2009 power-law fit on discrete data."""
    if powerlaw is None:
        return {"error": "powerlaw unavailable"}
    vals = vals[vals > 0]
    if len(vals) < 200:
        return {"error": f"too few ({len(vals)})", "name": name}
    try:
        fit = powerlaw.Fit(vals, discrete=True, xmin_distance="D", verbose=False)
        alpha = float(fit.power_law.alpha)
        sigma = float(fit.power_law.sigma)
        xmin = float(fit.power_law.xmin)
        try:
            R_ln, p_ln = fit.distribution_compare(
                "power_law", "lognormal", normalized_ratio=True)
        except Exception:
            R_ln, p_ln = (None, None)
        return {
            "name": name,
            "alpha": alpha,
            "sigma_alpha": sigma,
            "xmin": xmin,
            "n_total": int(len(vals)),
            "n_tail": int(np.sum(vals >= xmin)),
            "vs_lognormal_R": None if R_ln is None else float(R_ln),
            "vs_lognormal_p": None if p_ln is None else float(p_ln),
        }
    except Exception as e:
        return {"error": str(e), "name": name}


def mean_size_per_duration(sizes, durations, min_per_bin=30):
    T_unique = np.unique(durations.astype(int))
    T_bins = []; mean_s = []
    for T in T_unique:
        mask = durations == T
        if mask.sum() < min_per_bin:
            continue
        T_bins.append(T); mean_s.append(sizes[mask].mean())
    if len(T_bins) < 4:
        return {"error": "too few T bins"}
    T_bins = np.array(T_bins, dtype=float)
    mean_s = np.array(mean_s, dtype=float)
    keep = (T_bins > 0) & (mean_s > 0)
    x = np.log10(T_bins[keep]); y = np.log10(mean_s[keep])
    slope, intercept = np.polyfit(x, y, 1)
    pred = slope * x + intercept
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    n_pts = int(keep.sum())
    mse = ss_res / max(n_pts - 2, 1)
    var_slope = mse / float(np.sum((x - x.mean()) ** 2))
    return {
        "gamma": float(slope),
        "gamma_sigma": float(math.sqrt(max(var_slope, 0))),
        "R2": float(r2) if r2 is not None else None,
        "n_T_bins": n_pts,
        "T_range": [float(T_bins[keep].min()), float(T_bins[keep].max())],
    }


def analyze_one(name, nwb_path):
    """Run pooled + per-unit pipelines on one session."""
    per_unit, pooled, n_units = load_spike_units(nwb_path)
    # Compute per-session bin width = <IEI> on the pooled stream
    iei = np.diff(pooled)
    iei_pos = iei[iei > 0]
    if len(iei_pos) < 100:
        return {"label": name, "error": "too few spikes"}
    bin_width_s = float(np.mean(iei_pos))
    span_s = float(pooled.max() - pooled.min())

    # Pooled detection
    s_p, d_p = detect_avalanches_pooled(pooled, bin_width_s)
    pooled_size_fit = fit_distribution(s_p, "size_pooled")
    pooled_dur_fit = fit_distribution(d_p, "duration_pooled")
    pooled_rel = mean_size_per_duration(s_p, d_p)

    # Per-unit detection
    s_u, d_u = detect_avalanches_per_unit(per_unit, bin_width_s)
    perunit_size_fit = fit_distribution(s_u, "size_per_unit")
    perunit_dur_fit = fit_distribution(d_u, "duration_per_unit")
    perunit_rel = mean_size_per_duration(s_u, d_u)

    return {
        "label": name,
        "nwb_file": nwb_path.name,
        "n_units": int(n_units),
        "n_spikes": int(len(pooled)),
        "span_seconds": span_s,
        "mean_iei_ms": bin_width_s * 1000,
        "pooled": {
            "n_avalanches": int(len(s_p)),
            "size_fit": pooled_size_fit,
            "duration_fit": pooled_dur_fit,
            "scaling_relation": pooled_rel,
        },
        "per_unit": {
            "n_avalanches": int(len(s_u)),
            "size_fit": perunit_size_fit,
            "duration_fit": perunit_dur_fit,
            "scaling_relation": perunit_rel,
        },
    }


def aggregate(per_session_results):
    """Cross-session mean / SE / range of (tau, alpha_T, gamma) for pooled fits."""
    def safe(d, *keys, default=None):
        for k in keys:
            if not isinstance(d, dict):
                return default
            d = d.get(k, {})
        return d if d not in ({}, None) else default

    rows = []
    for r in per_session_results:
        if "error" in r:
            continue
        tau = safe(r, "pooled", "size_fit", "alpha")
        atau = safe(r, "pooled", "size_fit", "sigma_alpha")
        ad = safe(r, "pooled", "duration_fit", "alpha")
        ad_s = safe(r, "pooled", "duration_fit", "sigma_alpha")
        gamma = safe(r, "pooled", "scaling_relation", "gamma")
        gamma_s = safe(r, "pooled", "scaling_relation", "gamma_sigma")
        rows.append({
            "label": r["label"],
            "tau": tau, "tau_sigma": atau,
            "alpha_T": ad, "alpha_T_sigma": ad_s,
            "gamma": gamma, "gamma_sigma": gamma_s,
            "gamma_predicted": (
                (ad - 1) / (tau - 1) if (tau and ad and tau > 1) else None
            ),
        })

    if not rows:
        return {"error": "no successful sessions"}

    def stats(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return None
        vals = np.array(vals, dtype=float)
        return {
            "mean": float(vals.mean()),
            "std": float(vals.std(ddof=1)) if len(vals) > 1 else 0.0,
            "min": float(vals.min()),
            "max": float(vals.max()),
            "n": int(len(vals)),
        }

    return {
        "rows": rows,
        "cross_session": {
            "tau": stats("tau"),
            "alpha_T": stats("alpha_T"),
            "gamma_measured": stats("gamma"),
            "gamma_predicted_from_alpha_T_tau": stats("gamma_predicted"),
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--include-original", action="store_true", default=True)
    args = ap.parse_args()

    sessions = []
    if args.include_original and ORIGINAL.exists():
        sessions.append(("anm369962_ses-20170313_original", ORIGINAL))
    for nwb in sorted(EXTRA.glob("*.nwb")):
        sessions.append((nwb.stem.replace("sub-", ""), nwb))

    print(f"Found {len(sessions)} sessions")
    per_session = []
    for name, p in sessions:
        print(f"\n=== {name} ===")
        try:
            r = analyze_one(name, p)
        except Exception as e:
            print(f"  ERROR: {e}")
            r = {"label": name, "error": str(e)}
        per_session.append(r)
        if "error" not in r:
            pf = r["pooled"]; uf = r["per_unit"]
            tau_p = pf["size_fit"].get("alpha") if "error" not in pf["size_fit"] else None
            tau_u = uf["size_fit"].get("alpha") if "error" not in uf["size_fit"] else None
            ad_p = pf["duration_fit"].get("alpha") if "error" not in pf["duration_fit"] else None
            ad_u = uf["duration_fit"].get("alpha") if "error" not in uf["duration_fit"] else None
            g_p = pf["scaling_relation"].get("gamma") if "error" not in pf["scaling_relation"] else None
            g_u = uf["scaling_relation"].get("gamma") if "error" not in uf["scaling_relation"] else None
            print(f"  n_units={r['n_units']} span={r['span_seconds']:.0f}s "
                  f"mean_iei={r['mean_iei_ms']:.2f}ms")
            print(f"  pooled:   n_aval={pf['n_avalanches']:>7d}  tau={tau_p}  "
                  f"alpha_T={ad_p}  gamma={g_p}")
            print(f"  per-unit: n_aval={uf['n_avalanches']:>7d}  tau={tau_u}  "
                  f"alpha_T={ad_u}  gamma={g_u}")

    agg = aggregate(per_session)

    # Verdict
    cs = agg.get("cross_session", {})
    verdict = {}
    if cs.get("tau"):
        tau_mean = cs["tau"]["mean"]; tau_range = (cs["tau"]["min"], cs["tau"]["max"])
        verdict["tau_in_[1.5, 3.0]"] = bool(1.5 <= tau_mean <= 3.0)
        verdict["tau_cross_session_mean"] = tau_mean
        verdict["tau_cross_session_range"] = list(tau_range)
        verdict["tau_cross_session_std"] = cs["tau"]["std"]
    if cs.get("alpha_T"):
        a_mean = cs["alpha_T"]["mean"]; a_range = (cs["alpha_T"]["min"], cs["alpha_T"]["max"])
        verdict["alpha_T_in_[1.5, 2.5]"] = bool(1.5 <= a_mean <= 2.5)
        verdict["alpha_T_cross_session_mean"] = a_mean
        verdict["alpha_T_cross_session_range"] = list(a_range)
        verdict["alpha_T_cross_session_std"] = cs["alpha_T"]["std"]
    # Scaling relation: gamma_measured ~= gamma_predicted
    gm = cs.get("gamma_measured"); gp = cs.get("gamma_predicted_from_alpha_T_tau")
    if gm and gp:
        diff = abs(gm["mean"] - gp["mean"])
        verdict["scaling_relation_holds_cross_session"] = bool(diff < 0.1)
        verdict["gamma_measured_minus_predicted"] = float(gm["mean"] - gp["mean"])

    result = {
        "n_sessions": len(per_session),
        "per_session": per_session,
        "cross_session": agg,
        "verdict": verdict,
        "method_notes": {
            "P0_N1": (
                "Multi-session expansion: 5 sessions (3 animals from DANDI:000006). "
                "Cross-session SE on tau / alpha_T checks whether the original "
                "single-session result is animal-specific or universality-class."
            ),
            "P0_N2": (
                "Per-unit avalanche detection vs pooled. Pooled is the standard "
                "Beggs-Plenz 2003 method; per-unit avoids the Priesemann 2014 "
                "pooling-induces-subcritical-look critique. If exponents agree "
                "qualitatively the pooled-vs-per-unit issue is resolved; if not "
                "the C1 claim must be conditioned on the detection method."
            ),
        },
    }

    def coerce(o):
        if isinstance(o, (np.integer,)): return int(o)
        if isinstance(o, (np.floating,)): return float(o)
        if isinstance(o, np.ndarray): return o.tolist()
        if isinstance(o, dict): return {str(k): coerce(v) for k, v in o.items()}
        if isinstance(o, (list, tuple)): return [coerce(x) for x in o]
        return o

    OUT.write_text(json.dumps(coerce(result), indent=2))
    print(f"\nWrote: {OUT}")
    print(f"\nVERDICT: {json.dumps(coerce(verdict), indent=2)}")


if __name__ == "__main__":
    main()
