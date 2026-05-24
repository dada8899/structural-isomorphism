#!/usr/bin/env python3
"""
Time-resolution sweep: re-fit Clauset power-law across multiple temporal
bin widths and report whether the scaling exponent is stable, drifting,
or breaking down.

Motivation
----------
Layer 5 Phase 4 (mouse cortex, Beggs-Plenz avalanches) made it visible
that the fitted tail exponent depends on the time-binning factor used
to define avalanches. This is *expected* for SOC at finite size — the
exponent may drift slightly with bin width — but a large drift or a
breakdown of the power law at certain bins is itself a signature
worth surfacing for any phase, not just neural.

This script systematises that sweep:

  - For a phase, take its raw event stream (timestamps + sizes).
  - For each bin_factor in BIN_FACTORS_DEFAULT, bin events into windows
    of width `base_bin_seconds * bin_factor`.
  - Inside each bin: aggregate sizes into one number — `sum` for
    additive quantities (energy, debt value), `count` for arrival-
    rate quantities, depending on the phase config.
  - Refit Clauset alpha + xmin + p_KS on the resulting distribution.
  - Persist results per phase + an aggregate summary across phases.

Schema of output  v4/results/<phase_slug>_time_resolution_sweep.json
-------------------------------------------------------------------
    {
      "phase_slug": str,
      "bin_factors": [int, ...],
      "results": [
        {"bin": int, "alpha": float, "xmin": float, "n_tail": int, "p_ks": float},
        ...
      ],
      "scaling_dependence": "stable" | "drift" | "breakdown",
      "note": str
    }

Aggregate summary lands at
    v4/results/time_resolution_sweep_summary.md

Usage
-----
    # All built-in phases
    python3 v4/scripts/time_resolution_sweep.py

    # Single phase
    python3 v4/scripts/time_resolution_sweep.py --phase soc-earthquake
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

# powerlaw library emits many edge-of-range / log-of-nan warnings during
# distribution_compare; they are cosmetic for our purposes.
warnings.filterwarnings("ignore", category=UserWarning, module="powerlaw")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="powerlaw")

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATION_DIR = REPO_ROOT / "v4" / "validation"
RESULTS_DIR = REPO_ROOT / "v4" / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


# --------- phase configurations ---------

@dataclass
class PhaseConfig:
    slug: str
    raw_data_loader: Callable[[], List[Tuple[float, float]]]
    base_bin_seconds: float
    aggregate: str  # "sum" or "count"
    bin_factors: List[int]
    description: str


# ---- Phase 1: earthquakes ----------

def _load_earthquake_events() -> List[Tuple[float, float]]:
    """Return list of (time_seconds, energy_proxy) tuples.

    Energy proxy from magnitude via Hanks-Kanamori-style log scaling:
        log10(E) = 1.5 * mag + 4.8  (E in J, ignoring constant; we only
                                     need a monotone proxy for tail fits)
    We use 1.5 * mag (a log-energy proxy) and exponentiate so Clauset
    sees real (not log-transformed) energies.
    """
    path = VALIDATION_DIR / "soc-earthquake" / "catalog.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"earthquake catalog missing: {path}")
    events: List[Tuple[float, float]] = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") and d["type"] != "earthquake":
                continue
            mag = d.get("mag")
            t_ms = d.get("time_ms")
            if mag is None or t_ms is None:
                continue
            try:
                mag = float(mag)
                t_ms = float(t_ms)
            except (TypeError, ValueError):
                continue
            if not (mag >= 4.5):  # rough Mc to mirror Phase 1 Mc=4.45
                continue
            # log-energy proxy
            log_energy = 1.5 * mag
            energy = 10.0 ** log_energy
            events.append((t_ms / 1000.0, energy))
    return events


# ---- Phase 3: DeFi liquidations -------

def _load_defi_events() -> List[Tuple[float, float]]:
    """Return list of (time_seconds, debt_to_cover_normalised) tuples.

    Concatenate Aave + Compound + Maker liquidations. Use the
    `debt_to_cover_raw` field as a (log-)heavy size proxy.
    """
    out: List[Tuple[float, float]] = []
    files = [
        VALIDATION_DIR / "soc-defi" / "aave_v2_liquidations.jsonl",
        VALIDATION_DIR / "soc-defi" / "compound_v2_liquidations.jsonl",
        VALIDATION_DIR / "soc-defi" / "maker_dog_liquidations.jsonl",
    ]
    for fp in files:
        if not fp.exists():
            continue
        with fp.open() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ts = d.get("ts_unix")
                # `debt_to_cover_raw` is a numeric string (wei-like
                # huge ints); use float for sizing
                raw = d.get("debt_to_cover_raw") or d.get("debtToCoverRaw")
                if ts is None or raw is None:
                    continue
                try:
                    ts = float(ts)
                    raw = float(raw)
                except (TypeError, ValueError):
                    continue
                if raw <= 0:
                    continue
                out.append((ts, raw))
    return out


# ---- Phase 4: neural avalanches (precomputed) ----

def _load_neural_precomputed() -> Optional[Dict[str, Any]]:
    """Use the already-fit Beggs-Plenz neural avalanche results.

    Neural is special because the avalanche concept is already binned
    at the source. We harvest the bf_<n>_fit.json files written by
    analyze_avalanches.py and reformat them into the sweep schema.

    Returns None if any bin factor's fit file is missing.
    """
    neural_dir = VALIDATION_DIR / "soc-neural"
    bf_factors = [1, 2, 4, 8, 16]
    # Neural base bin is 4 ms (Beggs-Plenz pipeline default).
    neural_base_bin_seconds = 0.004
    results = []
    for bf in bf_factors:
        fp = neural_dir / f"bf_{bf}_fit.json"
        if not fp.exists():
            return None
        d = json.loads(fp.read_text())
        size_fit = d.get("size_fit", {})
        if "error" in size_fit:
            continue
        results.append(
            {
                "bin": bf,
                "bin_seconds": neural_base_bin_seconds * bf,
                "alpha": size_fit.get("alpha"),
                "xmin": size_fit.get("xmin"),
                "n_tail": size_fit.get("n_tail"),
                "p_ks": None,
                "vs_lognormal_R": size_fit.get("vs_lognormal_R"),
                "vs_exponential_R": size_fit.get("vs_exponential_R"),
                "n_total": size_fit.get("n_total"),
            }
        )
    if not results:
        return None
    return {
        "phase_slug": "soc-neural",
        "bin_factors": bf_factors,
        "results": results,
        "source": "precomputed bf_<n>_fit.json from analyze_avalanches.py",
    }


# --------- core sweep machinery ---------

def bin_events(
    events: List[Tuple[float, float]],
    bin_seconds: float,
    aggregate: str,
) -> np.ndarray:
    """Bin events into time windows of width bin_seconds, aggregating sizes.

    `aggregate`:
      - "sum"   → sum of sizes within each bin (heavy-tailed input)
      - "count" → number of events within each bin (counts-only)

    Returns a 1-D float array of per-bin values (only non-empty bins).
    """
    if not events:
        return np.array([], dtype=float)
    arr = np.asarray(events, dtype=float)
    arr = arr[arr[:, 0].argsort()]
    t0 = float(arr[0, 0])
    t_rel = arr[:, 0] - t0
    bin_idx = (t_rel // bin_seconds).astype(np.int64)
    n_bins = int(bin_idx.max()) + 1
    sizes = arr[:, 1]
    if aggregate == "sum":
        out = np.bincount(bin_idx, weights=sizes, minlength=n_bins)
    elif aggregate == "count":
        out = np.bincount(bin_idx, minlength=n_bins).astype(float)
    else:
        raise ValueError(f"unknown aggregate: {aggregate}")
    # Drop empty bins (zero sizes)
    return out[out > 0]


def fit_clauset(values: np.ndarray) -> Dict[str, Any]:
    """Fit Clauset power-law to a 1-D array of positive values."""
    if values is None or len(values) < 100:
        return {"error": f"too few values ({0 if values is None else len(values)})"}
    try:
        import powerlaw
    except Exception as e:
        return {"error": f"powerlaw not installed: {e}"}
    try:
        fit = powerlaw.Fit(values, discrete=False, xmin_distance="D", verbose=False)
        alpha = float(fit.power_law.alpha)
        sigma_alpha = float(fit.power_law.sigma)
        xmin = float(fit.power_law.xmin)
        n_tail = int(np.sum(values >= xmin))
        # KS-style D statistic from powerlaw is the goodness-of-fit
        # distance. powerlaw exposes it as fit.power_law.KS.
        try:
            ks_d = float(fit.power_law.KS())
        except Exception:
            ks_d = None
        # p_ks approximation: powerlaw provides Clauset bootstrap p
        # only when explicitly requested; here we report the D distance
        # and let downstream interpret. We *do* compute the convenient
        # R-comparisons.
        try:
            R_ln, p_ln = fit.distribution_compare(
                "power_law", "lognormal", normalized_ratio=True
            )
            R_exp, p_exp = fit.distribution_compare(
                "power_law", "exponential", normalized_ratio=True
            )
        except Exception:
            R_ln = p_ln = R_exp = p_exp = None
        return {
            "alpha": alpha,
            "sigma_alpha": sigma_alpha,
            "xmin": xmin,
            "n_tail": n_tail,
            "n_total": int(len(values)),
            "ks_d": ks_d,
            "p_ks": ks_d,  # report the KS distance as p_ks proxy
            "vs_lognormal_R": float(R_ln) if R_ln is not None else None,
            "vs_lognormal_p": float(p_ln) if p_ln is not None else None,
            "vs_exponential_R": float(R_exp) if R_exp is not None else None,
            "vs_exponential_p": float(p_exp) if p_exp is not None else None,
        }
    except Exception as e:
        return {"error": f"fit failed: {e}"}


def classify_scaling_dependence(
    fits: List[Dict[str, Any]], drift_threshold: float = 0.05
) -> Tuple[str, str]:
    """Classify across bin factors:
      - "stable"     if relative spread of alpha < drift_threshold AND
                       every bin has n_tail >= 100
      - "breakdown"  if any bin failed or has too few values
      - "drift"      otherwise
    """
    good_alphas: List[float] = []
    any_breakdown = False
    for f in fits:
        if "error" in f:
            any_breakdown = True
            continue
        a = f.get("alpha")
        n_tail = f.get("n_tail")
        if a is None or n_tail is None or n_tail < 100:
            any_breakdown = True
            continue
        good_alphas.append(float(a))

    if any_breakdown:
        return (
            "breakdown",
            f"at least one bin factor produced a failed fit or n_tail<100 "
            f"({sum(1 for f in fits if 'error' in f or (f.get('n_tail') or 0) < 100)}/{len(fits)})",
        )

    if not good_alphas:
        return "breakdown", "no usable fits"

    mean_a = float(np.mean(good_alphas))
    spread = (max(good_alphas) - min(good_alphas)) / mean_a if mean_a > 0 else 0.0
    if spread < drift_threshold:
        return (
            "stable",
            f"alpha spread {spread:.2%} across {len(good_alphas)} bin factors "
            f"(mean alpha={mean_a:.3f})",
        )
    return (
        "drift",
        f"alpha spread {spread:.2%} across {len(good_alphas)} bin factors "
        f"(mean alpha={mean_a:.3f}); finite-size or bin-dependence effect",
    )


def run_phase(cfg: PhaseConfig) -> Dict[str, Any]:
    """Run sweep for a single configured phase."""
    print(f"[{cfg.slug}] loading raw events...", file=sys.stderr)
    events = cfg.raw_data_loader()
    print(f"[{cfg.slug}] loaded {len(events)} events", file=sys.stderr)
    results = []
    for bf in cfg.bin_factors:
        bin_seconds = cfg.base_bin_seconds * bf
        agg = bin_events(events, bin_seconds, cfg.aggregate)
        fit = fit_clauset(agg)
        entry = {"bin": bf, "bin_seconds": bin_seconds, **fit}
        results.append(entry)
        if "error" in fit:
            print(
                f"[{cfg.slug}] bin={bf:>4d} bs={bin_seconds:>8.1f}s "
                f"ERROR: {fit['error']}",
                file=sys.stderr,
            )
        else:
            print(
                f"[{cfg.slug}] bin={bf:>4d} bs={bin_seconds:>8.1f}s "
                f"alpha={fit['alpha']:.3f} xmin={fit['xmin']:.2g} "
                f"n_tail={fit['n_tail']}",
                file=sys.stderr,
            )
    dep, note = classify_scaling_dependence(results)
    return {
        "phase_slug": cfg.slug,
        "description": cfg.description,
        "bin_factors": cfg.bin_factors,
        "base_bin_seconds": cfg.base_bin_seconds,
        "aggregate": cfg.aggregate,
        "n_events_loaded": len(events),
        "results": results,
        "scaling_dependence": dep,
        "note": note,
    }


# --------- phase registry ---------

def get_phase_configs() -> List[PhaseConfig]:
    return [
        PhaseConfig(
            slug="soc-earthquake",
            raw_data_loader=_load_earthquake_events,
            base_bin_seconds=3600.0,  # 1 hour
            aggregate="sum",
            bin_factors=[1, 2, 6, 12, 24, 72, 168],  # 1h ... 1wk
            description="Phase 1 USGS earthquakes; per-bin total energy proxy "
            "(10^(1.5m)); Mc=4.5",
        ),
        PhaseConfig(
            slug="soc-defi",
            raw_data_loader=_load_defi_events,
            base_bin_seconds=600.0,  # 10 min
            aggregate="sum",
            bin_factors=[1, 3, 6, 12, 24, 72, 144],  # 10m ... 24h
            description="Phase 3 DeFi liquidations (Aave + Compound + Maker); "
            "per-bin total debt_to_cover_raw",
        ),
    ]


# --------- driver ---------

def write_phase_result(phase_slug: str, result: Dict[str, Any]) -> Path:
    out = RESULTS_DIR / f"{phase_slug}_time_resolution_sweep.json"
    out.write_text(json.dumps(result, indent=2))
    return out


def write_summary(all_results: List[Dict[str, Any]]) -> Path:
    """Aggregate markdown summary."""
    lines: List[str] = [
        "# Time-Resolution Sweep — Aggregate Summary",
        "",
        "Generated by `v4/scripts/time_resolution_sweep.py`. For each phase",
        "we refit Clauset power-law at multiple time-bin widths and classify",
        "how the tail exponent `alpha` behaves across resolutions.",
        "",
        "Classes:",
        "- **stable**: alpha spread < 5% across bin factors (clean scale-free)",
        "- **drift**: alpha varies > 5% (finite-size or bin-dependence effect)",
        "- **breakdown**: power-law fails at some bin factors",
        "",
        "## Per-phase outcomes",
        "",
        "| phase | n_events | bin factors | scaling_dependence | mean alpha | spread | note |",
        "|---|---:|---|---|---:|---:|---|",
    ]
    for r in all_results:
        good = [
            f["alpha"]
            for f in r["results"]
            if "error" not in f and f.get("alpha") is not None
        ]
        mean_a = float(np.mean(good)) if good else float("nan")
        if good and mean_a > 0:
            spread = (max(good) - min(good)) / mean_a
        else:
            spread = float("nan")
        lines.append(
            f"| {r['phase_slug']} | {r.get('n_events_loaded', 'n/a')} "
            f"| {','.join(str(b) for b in r['bin_factors'])} "
            f"| {r['scaling_dependence']} "
            f"| {mean_a:.3f} | {spread:.2%} "
            f"| {r['note']} |"
        )

    lines.append("")
    lines.append("## Detail per phase")
    lines.append("")
    for r in all_results:
        lines.append(f"### {r['phase_slug']}")
        lines.append("")
        lines.append(f"- {r.get('description', '')}")
        lines.append(f"- aggregate: `{r.get('aggregate', 'n/a')}`")
        lines.append(
            f"- base bin: `{r.get('base_bin_seconds', 'n/a')}` seconds"
        )
        lines.append(f"- verdict: **{r['scaling_dependence']}** — {r['note']}")
        lines.append("")
        lines.append("| bin factor | bin (s) | alpha | xmin | n_tail | R_vs_lognormal | R_vs_exponential |")
        lines.append("|---:|---:|---:|---:|---:|---:|---:|")
        for f in r["results"]:
            if "error" in f:
                lines.append(
                    f"| {f.get('bin', '?')} | {f.get('bin_seconds', '?')} "
                    f"| ERROR | — | — | — | — |"
                )
                continue
            r_ln = f.get("vs_lognormal_R")
            r_exp = f.get("vs_exponential_R")
            r_ln_s = "—" if r_ln is None else f"{r_ln:.2f}"
            r_exp_s = "—" if r_exp is None else f"{r_exp:.2f}"
            alpha = f.get("alpha", float("nan"))
            xmin = f.get("xmin", float("nan"))
            lines.append(
                f"| {f.get('bin', '?')} | {f.get('bin_seconds', '?')} "
                f"| {alpha:.3f} | {xmin:.2g} | {f.get('n_tail', 0)} "
                f"| {r_ln_s} | {r_exp_s} |"
            )
        lines.append("")

    out = RESULTS_DIR / "time_resolution_sweep_summary.md"
    out.write_text("\n".join(lines))
    return out


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--phase",
        type=str,
        default=None,
        help="Run only this phase slug (e.g. soc-earthquake). Default: all.",
    )
    p.add_argument(
        "--skip-neural",
        action="store_true",
        help="Skip harvesting neural precomputed bf fits",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    cfgs = get_phase_configs()
    if args.phase:
        cfgs = [c for c in cfgs if c.slug == args.phase]
        if not cfgs and args.phase != "soc-neural":
            print(f"error: unknown phase {args.phase}", file=sys.stderr)
            return 2

    all_results: List[Dict[str, Any]] = []

    # 1. Computed phases (earthquake, defi)
    for cfg in cfgs:
        try:
            r = run_phase(cfg)
        except Exception as e:
            print(f"[{cfg.slug}] FAILED: {e}", file=sys.stderr)
            r = {
                "phase_slug": cfg.slug,
                "description": cfg.description,
                "error": str(e),
                "scaling_dependence": "breakdown",
                "note": f"loader/fit error: {e}",
                "bin_factors": cfg.bin_factors,
                "results": [],
                "n_events_loaded": 0,
            }
        out = write_phase_result(cfg.slug, r)
        print(f"[{cfg.slug}] wrote {out}", file=sys.stderr)
        all_results.append(r)

    # 2. Neural precomputed harvest
    if not args.skip_neural and (args.phase is None or args.phase == "soc-neural"):
        neural = _load_neural_precomputed()
        if neural is None:
            print("[soc-neural] WARNING: precomputed bf fits missing, skipping",
                  file=sys.stderr)
        else:
            # reuse the same classifier
            dep, note = classify_scaling_dependence(neural["results"])
            neural["scaling_dependence"] = dep
            neural["note"] = note
            neural["description"] = (
                "Phase 4 mouse cortex avalanches (Beggs-Plenz). Precomputed "
                "fits at bin factors 1/2/4/8/16 of base bin (4 ms)."
            )
            neural["aggregate"] = "count"
            neural["base_bin_seconds"] = 0.004
            neural["n_events_loaded"] = sum(
                r.get("n_total", 0) for r in neural["results"]
            )
            out = write_phase_result("soc-neural", neural)
            print(f"[soc-neural] wrote {out}", file=sys.stderr)
            all_results.append(neural)

    out_md = write_summary(all_results)
    print(f"summary: {out_md}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
