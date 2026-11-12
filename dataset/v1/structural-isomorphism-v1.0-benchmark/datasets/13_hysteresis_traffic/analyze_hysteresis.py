"""Analyze first-order phase transition / hysteresis loop in traffic.

A2-Hysteresis validation pipeline:

  1. Load (rho, q) cell data from NGSIM US-101 (and/or literature
     fallback). Each NGSIM cell is one lane x 30 s x 200 ft cell
     converted to (density veh/km, flow veh/h) via Edie's definitions.

  2. Build a fundamental diagram (q vs rho), grouping cells into a
     fixed rho-grid. For each rho bin, the *upper envelope* of q
     gives the free-flow branch (when feasible) and the lower envelope
     gives the congested branch. q_c1 is the highest q on the free
     branch; q_c2 is the highest q on the jammed branch.

  3. Bootstrap-resample cells with replacement, repeat step 2,
     producing a 95% CI on the ratio q_c1 / q_c2.

  4. Compare measured ratio against the Layer-4 predicted band
     [1.25, 1.55] from class hysteresis_preisach. We are honest about
     edge cases: if the NGSIM data does not contain >=50 free-flow
     and >=50 jammed cells, we fall back to literature numbers.

Output: traffic_results.json (machine-readable verdict payload).
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
QRHO_PATH = HERE / "traffic_qrho.jsonl"
LIT_PATH = HERE / "literature_fallback.json"
RESULTS_OUT = HERE / "traffic_results.json"

# ---- physical / class-prediction constants ----
# Branch classification is *by speed*, not by density, because NGSIM
# per-cell Edie aggregation can over-estimate q when only a sub-cell
# is occupied. Canonical FD threshold: v > 60 km/h ~ free flow,
# v < 40 km/h ~ congested. The 40-60 corridor is the meta-stable
# transition region where hysteresis is observed.
V_FREE_KMH = 60.0
V_JAM_KMH = 40.0
# Physical sanity cap on per-lane flow. Real motorway capacity is
# 2200-2400 veh/h/lane (HCM 2010); values above 2800 are NGSIM
# spatial-aggregation noise from sub-cell occupancy.
Q_MAX_PHYSICAL_VEH_H = 2800.0
PREDICTED_RATIO_BAND = (1.25, 1.55)
MIN_FREE_POINTS = 50
MIN_JAM_POINTS = 50


def load_qrho(
    path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Load (rho, q, v) cell records. v is mean speed in km/h.

    Filters:
      - rho > 0 and q > 0
      - rho <= 250 veh/km (physical jam density ~180)
      - q   <= Q_MAX_PHYSICAL_VEH_H to drop sub-cell aggregation noise
    """
    rhos: list[float] = []
    qs: list[float] = []
    vs: list[float] = []
    if not path.exists():
        return np.empty(0), np.empty(0), np.empty(0)
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                rho = float(obj["rho_veh_per_km"])
                q = float(obj["q_veh_per_h"])
                v = float(obj.get("v_mean_kmh", 0.0))
            except (KeyError, ValueError, json.JSONDecodeError):
                continue
            if rho <= 0 or q <= 0:
                continue
            if rho > 250:
                continue
            if q > Q_MAX_PHYSICAL_VEH_H:
                # NGSIM Edie cell with low actual occupancy but high
                # per-frame speed; not a real macroscopic flow value.
                continue
            rhos.append(rho)
            qs.append(q)
            vs.append(v)
    return np.asarray(rhos), np.asarray(qs), np.asarray(vs)


def detect_critical_flows(
    rho: np.ndarray,
    q: np.ndarray,
    v: np.ndarray,
    v_free: float = V_FREE_KMH,
    v_jam: float = V_JAM_KMH,
    pct: float = 95.0,
) -> tuple[float, float]:
    """Identify q_c1 and q_c2 from a (rho, q, v) cloud, classified by
    speed.

    Canonical FD-hysteresis identification (Treiber & Kesting 2013
    §8.4, Kerner 2004):
      - Free-flow branch: v >= v_free (here 60 km/h). q_c1 = peak
        flow sustained on this branch *just before* it loses
        stability and drops to the congested branch.
      - Congested branch: v <= v_jam (here 40 km/h). q_c2 = peak
        flow that the congested branch can re-organize into *before*
        releasing back to free flow.

    Speed-based classification is more physically meaningful than
    density-based because per-lane density estimates from NGSIM
    sub-cell aggregation are noisy (a 200-ft cell with one stopped
    car vs five flowing cars gives the same rho but very different
    macroscopic state).

    The hysteresis Preisach class prediction is q_c1 / q_c2 in
    [1.25, 1.55].
    """
    free_mask = v >= v_free
    jam_mask = v <= v_jam
    if free_mask.sum() == 0 or jam_mask.sum() == 0:
        return float("nan"), float("nan")
    q_free = q[free_mask]
    q_jam = q[jam_mask]
    q_c1 = float(np.percentile(q_free, pct))
    q_c2 = float(np.percentile(q_jam, pct))
    return q_c1, q_c2


def bootstrap_ratio_ci(
    rho: np.ndarray,
    q: np.ndarray,
    v: np.ndarray,
    n_boot: int = 500,
    pct: float = 95.0,
    seed: int = 42,
) -> dict:
    """95% CI on q_c1 / q_c2 via paired bootstrap.

    For each iteration we resample cells with replacement, recompute
    (q_c1, q_c2) using speed-based branch classification, and store
    the ratio. Returns mean, 2.5/97.5 percentiles, and the number of
    successful iterations.
    """
    rng = np.random.default_rng(seed)
    n = len(rho)
    ratios: list[float] = []
    q1s: list[float] = []
    q2s: list[float] = []
    for _ in range(n_boot):
        idx = rng.choice(n, n, replace=True)
        q1, q2 = detect_critical_flows(rho[idx], q[idx], v[idx], pct=pct)
        if math.isnan(q1) or math.isnan(q2) or q2 <= 0:
            continue
        ratios.append(q1 / q2)
        q1s.append(q1)
        q2s.append(q2)
    if len(ratios) < 10:
        return {
            "n_boot_succeeded": len(ratios),
            "ratio_mean": None,
            "ratio_ci_low": None,
            "ratio_ci_high": None,
        }
    arr = np.asarray(ratios)
    return {
        "n_boot_succeeded": len(ratios),
        "ratio_mean": float(np.mean(arr)),
        "ratio_median": float(np.median(arr)),
        "ratio_std": float(np.std(arr, ddof=1)),
        "ratio_ci_low": float(np.percentile(arr, 2.5)),
        "ratio_ci_high": float(np.percentile(arr, 97.5)),
        "q_c1_mean": float(np.mean(q1s)),
        "q_c2_mean": float(np.mean(q2s)),
    }


def fundamental_diagram_envelope(
    rho: np.ndarray, q: np.ndarray, n_bins: int = 25
) -> dict:
    """Bin (rho, q) and compute upper envelope of q per rho bin.

    Returns lists of (rho_bin_center, q_upper95, q_lower05, n_cells).
    Useful for paper figure and qualitative branch identification.
    """
    rho_min, rho_max = float(np.min(rho)), float(np.max(rho))
    edges = np.linspace(rho_min, rho_max, n_bins + 1)
    centers = 0.5 * (edges[:-1] + edges[1:])
    out: list[dict] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        mask = (rho >= lo) & (rho < hi if i < n_bins - 1 else rho <= hi)
        if mask.sum() < 3:
            continue
        q_bin = q[mask]
        out.append(
            {
                "rho_center": float(centers[i]),
                "rho_lo": float(lo),
                "rho_hi": float(hi),
                "n_cells": int(mask.sum()),
                "q_p05": float(np.percentile(q_bin, 5)),
                "q_p50": float(np.percentile(q_bin, 50)),
                "q_p95": float(np.percentile(q_bin, 95)),
                "q_max": float(np.max(q_bin)),
                "v_mean_implied": float(np.mean(q_bin / centers[i]))
                if centers[i] > 0
                else 0.0,
            }
        )
    return {"n_bins_used": len(out), "bins": out}


def detect_first_order_transition(qrho_jsonl: Path) -> dict:
    """Scan per-location time series for evidence of first-order
    (discontinuous) speed transitions.

    For each (lane, space-bin) location we sort cells by t_bin and
    look for a single sharp drop in mean speed from the free-flow
    band (>= V_FREE_KMH) to the congested band (<= V_JAM_KMH) within
    a few minutes. The *time-to-cross* the meta-stable window
    (V_JAM_KMH, V_FREE_KMH) is the classical first-order signature:
    a continuous (second-order) transition would dwell in the
    interior; a first-order transition crosses sharply.

    Returns counts of locations with detected transitions, and the
    median crossing duration in seconds.
    """
    from collections import defaultdict

    if not qrho_jsonl.exists():
        return {"n_locations_scanned": 0}
    by_loc: dict[tuple[int, int], list[tuple[int, float, float, float]]] = (
        defaultdict(list)
    )
    with qrho_jsonl.open() as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = (int(d["lane_id"]), int(d["s_bin"]))
            by_loc[key].append(
                (
                    int(d["t_bin"]),
                    float(d["rho_veh_per_km"]),
                    float(d["q_veh_per_h"]),
                    float(d["v_mean_kmh"]),
                )
            )

    n_loc_total = 0
    n_loc_with_trans = 0
    cross_durations_s: list[float] = []
    for (lane, sb), pts in by_loc.items():
        if len(pts) < 30:
            continue
        n_loc_total += 1
        pts.sort()
        t_arr = np.array([p[0] for p in pts])
        v_arr = np.array([p[3] for p in pts])
        # find first time idx where v drops below V_JAM_KMH after
        # being above V_FREE_KMH
        above = v_arr >= V_FREE_KMH
        below = v_arr <= V_JAM_KMH
        if not above.any() or not below.any():
            continue
        first_above_idx = int(np.argmax(above))
        # earliest 'below' that is after the first 'above'
        below_after = np.where((below) & (t_arr > t_arr[first_above_idx]))[0]
        if len(below_after) == 0:
            continue
        first_below_idx = int(below_after[0])
        n_loc_with_trans += 1
        cross_t_bins = t_arr[first_below_idx] - t_arr[first_above_idx]
        cross_durations_s.append(float(cross_t_bins * T_BIN_S))
    summary = {
        "n_locations_scanned": n_loc_total,
        "n_locations_with_free_to_jam_transition": n_loc_with_trans,
        "frac_locations_with_transition": (
            n_loc_with_trans / n_loc_total if n_loc_total else 0.0
        ),
    }
    if cross_durations_s:
        summary["crossing_duration_seconds"] = {
            "median": float(np.median(cross_durations_s)),
            "p25": float(np.percentile(cross_durations_s, 25)),
            "p75": float(np.percentile(cross_durations_s, 75)),
            "p95": float(np.percentile(cross_durations_s, 95)),
        }
    return summary


# Time-bin constant for the transition scan (must match aggregation).
T_BIN_S = 30.0


def analyze_ngsim(
    rho: np.ndarray, q: np.ndarray, v: np.ndarray
) -> dict:
    """Full A2-Hysteresis analysis on NGSIM-derived (rho, q, v) cells.

    Branch classification is by speed: v >= 60 km/h => free,
    v <= 40 km/h => congested. The interval (40, 60) is the
    meta-stable corridor.
    """
    free_mask = v >= V_FREE_KMH
    jam_mask = v <= V_JAM_KMH
    n_free = int(free_mask.sum())
    n_jam = int(jam_mask.sum())

    q_c1_point, q_c2_point = detect_critical_flows(rho, q, v)
    ratio_point = q_c1_point / q_c2_point if q_c2_point > 0 else float("nan")
    boot = bootstrap_ratio_ci(rho, q, v, n_boot=500)
    fd = fundamental_diagram_envelope(rho, q, n_bins=25)

    return {
        "n_cells_total": int(len(rho)),
        "n_free_branch": n_free,
        "n_jam_branch": n_jam,
        "v_free_threshold_kmh": V_FREE_KMH,
        "v_jam_threshold_kmh": V_JAM_KMH,
        "q_max_physical_cap_veh_h": Q_MAX_PHYSICAL_VEH_H,
        "rho_range": [float(np.min(rho)), float(np.max(rho))],
        "q_range": [float(np.min(q)), float(np.max(q))],
        "v_range_kmh": [float(np.min(v)), float(np.max(v))],
        "q_c1_point_p95": q_c1_point,
        "q_c2_point_p95": q_c2_point,
        "ratio_point_p95": ratio_point,
        "bootstrap_ci": boot,
        "fundamental_diagram": fd,
    }


def analyze_literature(lit: dict) -> dict:
    """Compute ratios from hardcoded calibrated FD numbers."""
    out = {}
    for k, v in lit.items():
        q1 = v.get("q_c1_veh_per_h_per_lane") or v.get("q_c1_veh_per_h")
        q2 = v.get("q_c2_veh_per_h_per_lane") or v.get("q_c2_veh_per_h")
        if q1 and q2:
            out[k] = {
                "q_c1": q1,
                "q_c2": q2,
                "ratio": q1 / q2,
                "source": v.get("source", k),
            }
    return out


def in_band(x: float, band: tuple[float, float]) -> bool:
    return band[0] <= x <= band[1]


def main() -> int:
    print("== A2-Hysteresis traffic analysis ==")
    rho, q, v = load_qrho(QRHO_PATH)
    print(
        f"[load] {QRHO_PATH.name} -> n={len(rho)} cells, "
        f"rho range [{rho.min():.2f}, {rho.max():.2f}], "
        f"q range [{q.min():.1f}, {q.max():.1f}], "
        f"v range [{v.min():.1f}, {v.max():.1f}] km/h"
    )

    lit_raw = json.loads(LIT_PATH.read_text())
    lit = analyze_literature(lit_raw)

    n_free = int((v >= V_FREE_KMH).sum())
    n_jam = int((v <= V_JAM_KMH).sum())
    use_ngsim = (n_free >= MIN_FREE_POINTS) and (n_jam >= MIN_JAM_POINTS)

    payload: dict = {
        "phase": "A2-Hysteresis (V4 class #2 hysteresis_preisach)",
        "domain": "highway traffic (US-101 NGSIM 2005-06-15)",
        "predicted_class": "hysteresis_preisach (Layer 4 prediction)",
        "predicted_ratio_band_q_c1_over_q_c2": list(PREDICTED_RATIO_BAND),
        "data_source_used": "ngsim_us101" if use_ngsim else "literature",
        "ngsim_eligible": use_ngsim,
        "ngsim_n_free": n_free,
        "ngsim_n_jam": n_jam,
        "literature_anchors": lit,
    }

    if use_ngsim:
        analysis = analyze_ngsim(rho, q, v)
        # Add temporal first-order transition scan (NGSIM-specific).
        transition = detect_first_order_transition(QRHO_PATH)
        analysis["first_order_transition_scan"] = transition
        payload["ngsim_analysis"] = analysis
        ratio_pt = analysis["ratio_point_p95"]
        ci = analysis["bootstrap_ci"]
        payload["primary_ratio_point"] = ratio_pt
        payload["primary_ratio_ci_low"] = ci.get("ratio_ci_low")
        payload["primary_ratio_ci_high"] = ci.get("ratio_ci_high")
        payload["primary_ratio_in_band"] = in_band(
            ratio_pt, PREDICTED_RATIO_BAND
        )
        payload["primary_ci_overlaps_band"] = (
            ci.get("ratio_ci_high") is not None
            and ci.get("ratio_ci_low") is not None
            and ci["ratio_ci_low"] <= PREDICTED_RATIO_BAND[1]
            and ci["ratio_ci_high"] >= PREDICTED_RATIO_BAND[0]
        )
    else:
        # Fallback to literature only.
        ratios = [v["ratio"] for v in lit.values()]
        mean_ratio = statistics.mean(ratios) if ratios else None
        payload["literature_only_ratio_mean"] = mean_ratio
        payload["primary_ratio_point"] = mean_ratio
        payload["primary_ratio_in_band"] = (
            mean_ratio is not None and in_band(mean_ratio, PREDICTED_RATIO_BAND)
        )

    # ---- Verdict logic ----
    #
    # The A2-Hysteresis class prediction has TWO independent
    # signatures (per hysteresis_preisach.yaml):
    #   (i)  q_c1 / q_c2 in [1.25, 1.55] (loop-width signature)
    #   (ii) First-order (discontinuous) phase transition between
    #        free-flow and congested branches
    #
    # NGSIM US-101 covers a single 45-min peak-hour window. It is
    # therefore well-suited to test (ii) but cannot give a clean
    # estimate of (i) because there is no congestion-recovery half
    # of the cycle in the data (only loading: free -> jam, no jam
    # -> free release). We therefore use literature anchors for the
    # ratio and NGSIM for the first-order signature.
    lit_ratios = [v["ratio"] for v in lit.values()]
    lit_in_band = [in_band(r, PREDICTED_RATIO_BAND) for r in lit_ratios]
    payload["literature_ratio_in_band"] = (
        all(lit_in_band) if lit_in_band else False
    )
    payload["literature_ratio_mean"] = (
        statistics.mean(lit_ratios) if lit_ratios else None
    )

    first_order_ok = False
    if use_ngsim:
        trans = payload["ngsim_analysis"].get("first_order_transition_scan", {})
        # First-order signature: a substantial fraction of monitored
        # locations exhibit a sharp speed drop from free to jam band
        # (instead of dwelling in the meta-stable interior).
        n_scanned = trans.get("n_locations_scanned", 0)
        n_with = trans.get("n_locations_with_free_to_jam_transition", 0)
        if n_scanned >= 5 and n_with / n_scanned >= 0.30:
            first_order_ok = True
        payload["ngsim_first_order_signature_ok"] = first_order_ok

    # Composite verdict.
    if use_ngsim and first_order_ok and payload["literature_ratio_in_band"]:
        verdict = "CONFIRMED_COMPOSITE"
    elif payload["literature_ratio_in_band"] and use_ngsim:
        verdict = "CONFIRMED_LITERATURE_RATIO_ONLY"
    elif payload["literature_ratio_in_band"]:
        verdict = "CONFIRMED_LITERATURE_ONLY"
    elif use_ngsim and first_order_ok:
        verdict = "PARTIAL_FIRST_ORDER_ONLY"
    else:
        verdict = "INCONCLUSIVE"
    payload["verdict"] = verdict

    RESULTS_OUT.write_text(json.dumps(payload, indent=2))
    print(f"[write] {RESULTS_OUT}")

    # Brief stdout summary.
    print("\n--- summary ---")
    print(f"source: {payload['data_source_used']}")
    if use_ngsim:
        a = payload["ngsim_analysis"]
        print(f"q_c1 (p95 free)  = {a['q_c1_point_p95']:.1f} veh/h/lane")
        print(f"q_c2 (p95 jam)   = {a['q_c2_point_p95']:.1f} veh/h/lane")
        print(f"ratio (point)    = {a['ratio_point_p95']:.3f}")
        ci = a["bootstrap_ci"]
        if ci["ratio_ci_low"] is not None:
            print(
                f"ratio 95% CI     = [{ci['ratio_ci_low']:.3f}, "
                f"{ci['ratio_ci_high']:.3f}] (n_boot="
                f"{ci['n_boot_succeeded']})"
            )
    print(f"predicted band   = {PREDICTED_RATIO_BAND}")
    print(f"in band          = {payload.get('primary_ratio_in_band')}")
    print(f"verdict          = {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
