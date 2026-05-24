#!/usr/bin/env python3
"""
Multi-protocol SOC analysis on DeFi liquidations.

Loads Aave V2 + Compound V2 + MakerDAO Dog datasets, normalises each to a
unified (ts_unix, usd_size) schema, then runs the same powerlaw + Omori
stack on each protocol independently, then on the pooled dataset.

Protocol-specific size extraction:
  - Aave V2: debt_to_cover / 10^decimals for stablecoin debts only
  - Compound V2: repay_raw / 10^decimals when debt_symbol in {USDC, DAI, USDT}
  - Maker Dog: debt_dai_approx = art / 1e18 (approximate DAI, exact factor
    is per-ilk rate which drops out of the power-law exponent)

Output:
  - multiprotocol_results.json  (per-protocol + pooled)
"""

import json
import math
from pathlib import Path
from collections import defaultdict

import numpy as np
import powerlaw

OUT_DIR = Path(__file__).resolve().parent
AAVE_FILE = OUT_DIR / "aave_v2_liquidations.jsonl"
COMPOUND_FILE = OUT_DIR / "compound_v2_liquidations.jsonl"
MAKER_FILE = OUT_DIR / "maker_dog_liquidations.jsonl"
OUT_FILE = OUT_DIR / "multiprotocol_results.json"

AAVE_STABLES = {
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18),
    "0x4fabb145d64652a948d72533023f6e7a623c7c53": ("BUSD", 18),
    "0x853d955acef822db058eb8505911ed77f175b99e": ("FRAX", 18),
    "0x8e870d67f660d95d5be530380d0ec0bd388289e1": ("USDP", 18),
    "0x0000000000085d4780b73119b644ae5ecd22b376": ("TUSD", 18),
    "0x57ab1ec28d129707052df4df418d58a2d46d5f51": ("SUSD", 18),
}


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    return rows


def extract_aave(events):
    out = []
    for e in events:
        da = (e.get("debt_asset") or "").lower()
        if da not in AAVE_STABLES:
            continue
        sym, dec = AAVE_STABLES[da]
        try:
            raw = int(e.get("debt_to_cover_raw", "0"))
        except Exception:
            continue
        usd = raw / (10 ** dec)
        if usd <= 0:
            continue
        out.append({"ts": e.get("ts_unix"), "usd": usd, "protocol": "aave_v2"})
    return out


def extract_compound(events):
    out = []
    for e in events:
        if e.get("debt_symbol") not in ("USDC", "DAI", "USDT"):
            continue
        usd = e.get("debt_usd")
        if usd is None or usd <= 0:
            continue
        out.append({"ts": e.get("ts_unix"), "usd": usd, "protocol": "compound_v2"})
    return out


def extract_maker(events):
    """Maker Dog Bark: art is normalized debt in 18-decimal fixed point.
    Actual DAI = art * rate, where rate ~= 1 + tiny accrual. For power-law
    exponent the multiplicative factor drops out; use art/1e18 as size."""
    out = []
    for e in events:
        try:
            art = int(e.get("art_raw", "0"))
        except Exception:
            continue
        # art is 18-decimal; for SAI legacy some are in RAD format (45 decimals)
        # Use heuristic: if value >> 1e30 assume RAD and divide by 1e45
        if art > 10 ** 40:
            usd = art / 1e45
        else:
            usd = art / 1e18
        if usd <= 0:
            continue
        out.append({"ts": e.get("ts_unix"), "usd": usd, "protocol": "maker_dog"})
    return out


def powerlaw_fit(sizes):
    vals = np.array([s for s in sizes if s > 0], dtype=float)
    if len(vals) < 50:
        return {"error": f"too few: {len(vals)}"}
    try:
        fit = powerlaw.Fit(vals, discrete=False, xmin_distance="D", verbose=False)
        R_ln, p_ln = fit.distribution_compare("power_law", "lognormal", normalized_ratio=True)
        R_exp, p_exp = fit.distribution_compare("power_law", "exponential", normalized_ratio=True)
        R_tp, p_tp = fit.distribution_compare("power_law", "truncated_power_law", normalized_ratio=True)
        return {
            "alpha": float(fit.power_law.alpha),
            "sigma_alpha": float(fit.power_law.sigma),
            "xmin_usd": float(fit.power_law.xmin),
            "n_total": int(len(vals)),
            "n_tail": int(np.sum(vals >= float(fit.power_law.xmin))),
            "vs_lognormal_R": float(R_ln),
            "vs_lognormal_p": float(p_ln),
            "vs_exponential_R": float(R_exp),
            "vs_exponential_p": float(p_exp),
            "vs_truncated_R": float(R_tp),
            "vs_truncated_p": float(p_tp),
        }
    except Exception as e:
        return {"error": str(e)}


def aggregate_counts(rows, bin_seconds):
    counts = defaultdict(int)
    for r in rows:
        t = r.get("ts") or 0
        if not t:
            continue
        counts[int(t // bin_seconds)] += 1
    if not counts:
        return np.array([]), np.array([])
    b0, b1 = min(counts), max(counts)
    bins = np.arange(b0, b1 + 1)
    cnt = np.array([counts.get(int(b), 0) for b in bins], dtype=float)
    return bins, cnt


def fit_omori(counts, sigma_k=3.0, window_bins=30):
    mu = counts.mean()
    sig = counts.std()
    threshold = mu + sigma_k * sig
    main_idx = np.where(counts > threshold)[0]
    valid = main_idx[(main_idx + window_bins) < len(counts)]
    if len(valid) < 10:
        return {"error": f"too few main: {len(valid)}", "threshold": float(threshold), "mu": float(mu)}
    rates = np.zeros(window_bins)
    for tau in range(1, window_bins + 1):
        rates[tau - 1] = counts[valid + tau].mean() - mu
    tau_days = np.arange(1, window_bins + 1, dtype=float)
    keep = rates > 0
    if keep.sum() < 6:
        return {"error": f"too few positive bins: {int(keep.sum())}"}
    t_fit = tau_days[keep]
    r_fit = rates[keep]
    w = np.ones_like(t_fit)
    best = None
    for c in [0.1, 0.3, 0.5, 1.0, 1.5, 2.0]:
        x = np.log10(t_fit + c)
        y = np.log10(r_fit)
        Sw = np.sum(w); Sx = np.sum(w * x); Sy = np.sum(w * y)
        Sxx = np.sum(w * x * x); Sxy = np.sum(w * x * y)
        denom = Sw * Sxx - Sx * Sx
        slope = (Sw * Sxy - Sx * Sy) / denom
        intercept = (Sy - slope * Sx) / Sw
        p_est = -slope
        pred = intercept + slope * x
        ss_res = float(np.sum(w * (y - pred) ** 2))
        ss_tot = float(np.sum(w * (y - np.average(y, weights=w)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
        dof = max(len(y) - 2, 1)
        mse = float(np.sum(w * (y - pred) ** 2) / dof)
        var_slope = mse * Sw / denom
        sig_p = float(math.sqrt(abs(var_slope)))
        if best is None or (r2 is not None and r2 > best["R2"]):
            best = {"c": c, "p": float(p_est), "p_sigma": sig_p, "R2": float(r2) if r2 else None}
    return {"n_main": int(len(valid)), "mu": float(mu), "threshold": float(threshold),
            "c_bins": best["c"], "p": best["p"], "p_sigma": best["p_sigma"], "R2": best["R2"]}


def analyze_protocol(name, rows, extract_fn):
    data = extract_fn(rows)
    sizes = [r["usd"] for r in data]
    print(f"\n--- {name} ---  events: {len(data)}")
    pl = powerlaw_fit(sizes)
    print(f"  alpha = {pl.get('alpha', '?')}")
    if "n_tail" in pl:
        print(f"  n_tail = {pl['n_tail']}, xmin = {pl.get('xmin_usd'):.2f}")
    # Omori at 3 scales
    scales = {"daily": 86400, "6hour": 21600, "1hour": 3600}
    omori_fits = {}
    for label, sec in scales.items():
        _, cnt = aggregate_counts(data, sec)
        window = {"daily": 30, "6hour": 120, "1hour": 720}[label]
        fit = fit_omori(cnt, sigma_k=3.0, window_bins=window)
        omori_fits[label] = fit
        if "p" in fit:
            print(f"  {label:6s}: n_bins={len(cnt):5d}  n_main={fit['n_main']:3d}  p={fit['p']:.3f}±{fit['p_sigma']:.3f}  R²={fit['R2']:.3f}")
        else:
            print(f"  {label:6s}: {fit.get('error')}")
    best_scale = max((k for k in omori_fits if "p" in omori_fits[k]),
                     key=lambda k: (omori_fits[k].get("R2") or 0) / max(omori_fits[k].get("p_sigma") or 1, 0.01),
                     default=None)
    return {
        "n_events_total": len(rows),
        "n_events_with_size": len(data),
        "power_law": pl,
        "omori": omori_fits,
        "best_omori_scale": best_scale,
    }


def main():
    print("Loading datasets...")
    aave = load_jsonl(AAVE_FILE)
    comp = load_jsonl(COMPOUND_FILE)
    maker = load_jsonl(MAKER_FILE)
    print(f"  Aave V2:    {len(aave):6d} events")
    print(f"  Compound V2:{len(comp):6d} events")
    print(f"  Maker Dog:  {len(maker):6d} events")
    print(f"  Pooled:     {len(aave)+len(comp)+len(maker):6d}")

    results = {}
    results["aave_v2"] = analyze_protocol("Aave V2", aave, extract_aave)
    results["compound_v2"] = analyze_protocol("Compound V2", comp, extract_compound)
    results["maker_dog"] = analyze_protocol("Maker Dog", maker, extract_maker)

    # Pooled analysis
    print("\n--- POOLED (all three) ---")
    pooled = []
    pooled.extend(extract_aave(aave))
    pooled.extend(extract_compound(comp))
    pooled.extend(extract_maker(maker))
    sizes = [r["usd"] for r in pooled]
    print(f"  events with size: {len(pooled)}")
    pl_pool = powerlaw_fit(sizes)
    print(f"  alpha = {pl_pool.get('alpha', '?')}")
    if "n_tail" in pl_pool:
        print(f"  n_tail = {pl_pool['n_tail']}, xmin = {pl_pool.get('xmin_usd'):.2f}")
    scales = {"daily": 86400, "6hour": 21600, "1hour": 3600}
    pool_omori = {}
    for label, sec in scales.items():
        _, cnt = aggregate_counts(pooled, sec)
        window = {"daily": 30, "6hour": 120, "1hour": 720}[label]
        fit = fit_omori(cnt, sigma_k=3.0, window_bins=window)
        pool_omori[label] = fit
        if "p" in fit:
            print(f"  {label:6s}: p={fit['p']:.3f}±{fit['p_sigma']:.3f}  R²={fit['R2']:.3f}  n_main={fit['n_main']}")
    results["pooled"] = {
        "n_events": len(pooled),
        "power_law": pl_pool,
        "omori": pool_omori,
    }

    OUT_FILE.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {OUT_FILE}")

    # Print compact comparison table
    print("\n" + "=" * 72)
    print(f"{'Protocol':<14} {'N events':<10} {'α':<14} {'n_tail':<8} {'Omori p (best scale)':<30}")
    print("-" * 72)
    for proto, label in [("aave_v2", "Aave V2"), ("compound_v2", "Compound V2"), ("maker_dog", "Maker Dog"), ("pooled", "POOLED")]:
        r = results[proto]
        n = r.get("n_events", r.get("n_events_with_size", 0))
        pl = r.get("power_law", {})
        alpha = f"{pl.get('alpha', 0):.3f}±{pl.get('sigma_alpha', 0):.3f}" if "alpha" in pl else "—"
        n_tail = pl.get("n_tail", 0)
        om = r.get("omori", {})
        best_s = r.get("best_omori_scale")
        if not best_s:
            # pick best from omori dict
            good = [(k, v) for k, v in om.items() if "p" in v]
            if good:
                best_s = max(good, key=lambda kv: (kv[1].get("R2") or 0))[0]
        if best_s and "p" in om.get(best_s, {}):
            p = om[best_s]["p"]
            ps = om[best_s]["p_sigma"]
            r2 = om[best_s]["R2"]
            p_str = f"{p:.3f}±{ps:.3f} ({best_s}, R²={r2:.2f})"
        else:
            p_str = "—"
        print(f"{label:<14} {n:<10} {alpha:<14} {n_tail:<8} {p_str:<30}")


if __name__ == "__main__":
    main()
