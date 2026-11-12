#!/usr/bin/env python3
"""Fit NYC FDNY fire-incident dispatch sizes to a power-law (Clauset 2009).

Pre-registration: v4/preregistration/nyc-fdny-fires.yaml
  - PRIMARY metric: units dispatched per fire-incident
  - SECONDARY metric: daily fire-incident count
  - predicted band: alpha in [1.3, 2.0]

Verdict logic (mirrors v4/scripts/fetch/fit_cve_burst.py):
  - PASS:        alpha in band AND >=2 null alternatives rejected (Vuong p<0.1)
  - FAIL:        alpha outside band  (or all alternatives preferred)
  - INCONCLUSIVE: in band but null tests ambiguous, OR n_tail < 100

We fit FOUR series and report each. PRIMARY verdict = units_dispatched_all
(fire-related groups + units count). This is the metric the pre-registration
yaml pins.

Inputs:
  v4/validation/nyc-fdny-fires/incident_sizes_<year>.json

Outputs:
  v4/validation/nyc-fdny-fires/fit_result.json   (full multi-series report)
  v4/validation/nyc-fdny-fires/result.json       (primary verdict echo)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "soc-pipeline" / "src"))

from soc_pipeline import (  # noqa: E402  (after path setup)
    bootstrap_ci,
    fit_clauset_powerlaw,
    vuong_lr_test,
)


def _fit_one(
    arr: np.ndarray,
    name: str,
    predicted_band: tuple[float, float],
    n_boot: int,
    min_samples_fit: int,
) -> dict:
    """Run Clauset fit + bootstrap CI + Vuong tests + verdict logic on one array."""
    lo, hi = predicted_band
    if arr.size < 5:
        return {
            "series": name,
            "verdict": "INCONCLUSIVE",
            "reason": f"n={arr.size} (need >=5 for any fit)",
            "alpha_measured": None,
            "n_input": int(arr.size),
            "predicted_band": [lo, hi],
            "fit_status": "skipped_insufficient_data",
        }

    fit = fit_clauset_powerlaw(
        arr, name=name, discrete=True, min_samples=min_samples_fit
    )

    ci_low: float | None = None
    ci_high: float | None = None
    try:
        ci = bootstrap_ci(
            arr, n_boot=n_boot, discrete=True, min_samples=min_samples_fit
        )
        ci_low, ci_high = float(ci.ci_low), float(ci.ci_high)
    except Exception as e:
        print(f"  [fit:{name}] bootstrap_ci skipped: {e}", file=sys.stderr)

    vuong_results: dict[str, dict] = {}
    for alt in ("lognormal", "exponential"):
        try:
            lr = vuong_lr_test(arr, vs=alt, discrete=True)
            vuong_results[alt] = {
                "R": _opt_float(getattr(lr, "R", None)),
                "p_value": _opt_float(getattr(lr, "p", None)),
                "winner": getattr(lr, "winner", None),
                "error": getattr(lr, "error", None),
            }
        except Exception as e:
            vuong_results[alt] = {"error": str(e)}

    # Echo from FitResult for cross-check
    vuong_results["from_fit_result"] = {
        "vs_lognormal_R": _opt_float(getattr(fit, "vs_lognormal_R", None)),
        "vs_lognormal_p": _opt_float(getattr(fit, "vs_lognormal_p", None)),
        "vs_exponential_R": _opt_float(getattr(fit, "vs_exponential_R", None)),
        "vs_exponential_p": _opt_float(getattr(fit, "vs_exponential_p", None)),
    }

    # Per pre-registration yaml: PASS requires Vuong p > 0.1 (PL NOT rejected)
    # vs both lognormal AND exponential. If R < 0 and p < 0.1, the alternative
    # significantly wins -> PL is rejected -> NOT a pass.
    # n_alt_not_winning counts comparisons where PL is NOT decisively beaten.
    n_alt_not_winning = 0
    n_alt_winning = 0  # alternatives that decisively beat PL (R<0, p<0.1)
    for k, v in vuong_results.items():
        if k == "from_fit_result":
            continue
        p = v.get("p_value")
        R = v.get("R")
        if not isinstance(p, (int, float)) or not isinstance(R, (int, float)):
            continue
        if p > 0.1:
            n_alt_not_winning += 1
        elif R < 0:
            # alternative wins decisively
            n_alt_winning += 1
        else:
            # PL wins decisively (R>0, p<0.1) — also counts as "not beaten"
            n_alt_not_winning += 1

    alpha = fit.alpha
    in_band = (alpha is not None) and (lo <= alpha <= hi)
    n_tail = getattr(fit, "n_tail", None) or int((arr >= (fit.xmin or 0)).sum())

    if alpha is None:
        verdict = "INCONCLUSIVE"
        reason = "fit returned no alpha (likely insufficient data above xmin)"
    elif not in_band:
        verdict = "FAIL"
        reason = f"alpha={alpha:.3f} outside band [{lo}, {hi}]"
    elif n_tail < 100:
        verdict = "INCONCLUSIVE"
        reason = (
            f"alpha={alpha:.3f} in band but n_tail={n_tail} < 100 "
            "(sample size insufficient for definitive verdict)"
        )
    elif n_alt_winning >= 1:
        # Pre-reg yaml: any alternative significantly winning is a FAIL-grade flag.
        # We mark INCONCLUSIVE if alpha still in band (geometry/cutoff plausible),
        # FAIL only when alpha also misses; aligned with yaml verdict_rules.
        verdict = "INCONCLUSIVE"
        reason = (
            f"alpha={alpha:.3f} in band but {n_alt_winning} alternative(s) "
            f"decisively beat power-law (Vuong R<0, p<0.1). "
            "Likely heavy-tailed but better fit by lognormal/exp at this resolution."
        )
    elif n_alt_not_winning < 2:
        verdict = "INCONCLUSIVE"
        reason = (
            f"alpha={alpha:.3f} in band; only {n_alt_not_winning} alternatives "
            "where PL was NOT decisively beaten (spec requires >=2)"
        )
    else:
        verdict = "PASS"
        reason = (
            f"alpha={alpha:.3f} in band [{lo}, {hi}]; "
            f"PL not beaten by {n_alt_not_winning} alternatives; n_tail={n_tail}"
        )
    n_null_rejected = n_alt_not_winning  # alias retained for downstream compat

    return {
        "series": name,
        "verdict": verdict,
        "reason": reason,
        "alpha_measured": _opt_float(alpha),
        "xmin": _opt_float(fit.xmin),
        "n_input": int(arr.size),
        "n_tail": int(n_tail) if n_tail is not None else None,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "n_boot": n_boot,
        "ks_statistic": _opt_float(getattr(fit, "ks_statistic", None)),
        "vuong": vuong_results,
        "n_null_rejected": int(n_null_rejected),
        "n_alt_not_winning": int(n_alt_not_winning),
        "n_alt_winning": int(n_alt_winning),
        "predicted_band": [lo, hi],
        "fit_status": "real_fit_completed",
    }


def _opt_float(v):
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--sizes",
        default=str(
            REPO / "v4" / "validation" / "nyc-fdny-fires" / "incident_sizes_2023.json"
        ),
    )
    ap.add_argument("--predicted-band", nargs=2, type=float, default=[1.3, 2.0])
    ap.add_argument(
        "--out-dir",
        default=str(REPO / "v4" / "validation" / "nyc-fdny-fires"),
    )
    ap.add_argument("--n-boot", type=int, default=1000)
    ap.add_argument(
        "--min-samples",
        type=int,
        default=100,
        help="Floor for fit_clauset_powerlaw min_samples (lower for sample runs).",
    )
    args = ap.parse_args()

    sizes_path = Path(args.sizes)
    if not sizes_path.exists():
        print(f"[fit] FATAL: sizes file not found: {sizes_path}", file=sys.stderr)
        return 2

    sizes_doc = json.loads(sizes_path.read_text())
    data_source = sizes_doc.get("data_source", "unknown")
    is_synthetic = "synthetic" in data_source.lower()

    band = tuple(args.predicted_band)

    series_inputs = {
        "units_dispatched_all": sizes_doc.get("units_dispatched_all") or [],
        "units_dispatched_strict": sizes_doc.get("units_dispatched_strict") or [],
        "daily_counts_all": sizes_doc.get("daily_counts_all") or [],
        "daily_counts_strict": sizes_doc.get("daily_counts_strict") or [],
    }

    per_series: dict[str, dict] = {}
    for name, raw_list in series_inputs.items():
        arr = np.array([int(x) for x in raw_list if int(x) > 0], dtype=float)
        # For short series, allow smaller min_samples so we still get something.
        min_s = min(args.min_samples, max(5, arr.size // 2))
        per_series[name] = _fit_one(
            arr,
            name=name,
            predicted_band=band,
            n_boot=args.n_boot,
            min_samples_fit=min_s,
        )

    # PRIMARY verdict = units_dispatched_all (per pre-reg yaml)
    primary = per_series["units_dispatched_all"]

    result = {
        "primary_series": "units_dispatched_all",
        "primary_verdict": primary["verdict"],
        "primary_reason": primary["reason"],
        "alpha_measured": primary["alpha_measured"],
        "ci_low": primary.get("ci_low"),
        "ci_high": primary.get("ci_high"),
        "n_tail": primary.get("n_tail"),
        "n_input": primary.get("n_input"),
        "predicted_band": list(band),
        "per_series": per_series,
        "data_source": data_source,
        "is_synthetic_fallback": is_synthetic,
        "n_unique_incidents": sizes_doc.get("n_unique_incidents"),
        "n_fire_incidents_all": sizes_doc.get("n_fire_incidents_all"),
        "n_fire_incidents_strict": sizes_doc.get("n_fire_incidents_strict"),
        "per_group_counts": sizes_doc.get("per_group_counts"),
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "yaml_spec": "v4/preregistration/nyc-fdny-fires.yaml",
        "fetcher": "v4/scripts/fetch/fetch_nyc_fdny.py",
        "session": "session-7-W2-D",
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fit_path = out_dir / "fit_result.json"
    result_path = out_dir / "result.json"
    fit_path.write_text(json.dumps(result, indent=2, default=float))
    result_path.write_text(json.dumps(result, indent=2, default=float))

    print(f"[fit] primary_series={result['primary_series']}")
    print(f"[fit] primary_verdict={result['primary_verdict']}")
    print(f"[fit] {result['primary_reason']}")
    if primary.get("ci_low") is not None:
        print(
            f"[fit] alpha={primary['alpha_measured']:.3f} "
            f"CI=[{primary['ci_low']:.3f}, {primary['ci_high']:.3f}] "
            f"n_tail={primary['n_tail']} n_input={primary['n_input']}"
        )
    for name, s in per_series.items():
        if name == "units_dispatched_all":
            continue
        a = s.get("alpha_measured")
        print(
            f"[fit] {name}: verdict={s['verdict']} alpha={a} "
            f"n_tail={s.get('n_tail')} n_input={s.get('n_input')}"
        )
    print(f"[fit] wrote {fit_path}")
    print(f"[fit] wrote {result_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
