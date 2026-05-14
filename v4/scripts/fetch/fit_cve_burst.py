#!/usr/bin/env python3
"""Fit per-month CVE disclosure-burst counts to a power-law (Clauset 2009).

Inputs:
  v4/validation/cve-vulnerabilities/burst_sizes.json  (from fetch_cve_nvd.py)

Outputs:
  v4/validation/cve-vulnerabilities/fit_result.json
  v4/validation/cve-vulnerabilities/result.json     (verdict file expected by
                                                     run_preregistered_validation.py)

Verdict rule (mirrors run_preregistered_validation.compute_verdict):
  - PASS:        alpha in predicted_band AND >=2 null alternatives rejected (Vuong p<0.1)
  - FAIL:        alpha outside band
  - INCONCLUSIVE: in band but few nulls rejected OR small n_tail

Pre-registration band: [1.5, 2.5] (see v4/preregistration/cve-vulnerabilities.yaml)

Honest scoping note: with a 2022-2023 sample fetch (~24 months), n_tail will
likely be small. We report results but flag INCONCLUSIVE when n_tail < 100.
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--burst-sizes",
        default=str(REPO / "v4" / "validation" / "cve-vulnerabilities" / "burst_sizes.json"),
    )
    ap.add_argument("--predicted-band", nargs=2, type=float, default=[1.5, 2.5])
    ap.add_argument("--out-dir", default=str(REPO / "v4" / "validation" / "cve-vulnerabilities"))
    ap.add_argument("--n-boot", type=int, default=500)
    args = ap.parse_args()

    burst_path = Path(args.burst_sizes)
    if not burst_path.exists():
        print(f"[fit] FATAL: burst_sizes.json not found: {burst_path}", file=sys.stderr)
        return 2

    raw = json.loads(burst_path.read_text())
    if not isinstance(raw, list):
        print(f"[fit] FATAL: burst_sizes.json must be a list, got {type(raw)}", file=sys.stderr)
        return 2

    arr = np.array([int(x) for x in raw if int(x) > 0], dtype=float)
    if arr.size < 5:
        print(f"[fit] INSUFFICIENT_DATA: n={arr.size}, need >=5 for any fit", file=sys.stderr)
        result = {
            "verdict": "INCONCLUSIVE",
            "reason": f"n={arr.size} burst-sizes (need >=5 for Clauset fit)",
            "alpha_measured": None,
            "n_input": arr.size,
            "fit_status": "skipped_insufficient_data",
        }
    else:
        # Discrete distribution: monthly counts are integers.
        # min_samples relaxed because sample-fetch (24 months) is intentionally small.
        fit = fit_clauset_powerlaw(arr, name="cve_monthly_burst", discrete=True, min_samples=5)
        # bootstrap_ci requires min_samples=200 default; relax for sample run.
        try:
            ci = bootstrap_ci(arr, n_boot=args.n_boot, discrete=True, min_samples=5)
            ci_low, ci_high = ci.ci_low, ci.ci_high
        except Exception as e:
            ci_low, ci_high = None, None
            print(f"  [fit] bootstrap_ci skipped: {e}", file=sys.stderr)

        # Vuong tests vs lognormal + exponential. signature: vuong_lr_test(x, vs=..., discrete=...)
        vuong_results: dict[str, dict] = {}
        for alt in ("lognormal", "exponential"):
            try:
                lr = vuong_lr_test(arr, vs=alt, discrete=True)
                vuong_results[alt] = {
                    "R": getattr(lr, "R", None),
                    "p_value": getattr(lr, "p", None),
                    "winner": getattr(lr, "winner", None),
                    "error": getattr(lr, "error", None),
                }
            except Exception as e:
                vuong_results[alt] = {"error": str(e)}

        # Also expose pre-computed vs_lognormal / vs_exponential from FitResult directly
        vuong_results["from_fit_result"] = {
            "vs_lognormal_R": getattr(fit, "vs_lognormal_R", None),
            "vs_lognormal_p": getattr(fit, "vs_lognormal_p", None),
            "vs_exponential_R": getattr(fit, "vs_exponential_R", None),
            "vs_exponential_p": getattr(fit, "vs_exponential_p", None),
        }

        n_null_rejected = sum(
            1
            for v in vuong_results.values()
            if isinstance(v.get("p_value"), (int, float)) and v["p_value"] < 0.1
        )

        lo, hi = args.predicted_band
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
        elif n_null_rejected < 2:
            verdict = "INCONCLUSIVE"
            reason = (
                f"alpha={alpha:.3f} in band; only {n_null_rejected} null alternatives "
                "rejected (spec requires >=2)"
            )
        else:
            verdict = "PASS"
            reason = (
                f"alpha={alpha:.3f} in band [{lo}, {hi}]; "
                f"{n_null_rejected} null alternatives rejected; n_tail={n_tail}"
            )

        result = {
            "verdict": verdict,
            "reason": reason,
            "alpha_measured": alpha,
            "xmin": fit.xmin,
            "n_tail": n_tail,
            "ci_low": ci_low,
            "ci_high": ci_high,
            "n_boot": args.n_boot,
            "vuong": vuong_results,
            "n_null_rejected": n_null_rejected,
            "predicted_band": list(args.predicted_band),
            "n_input": arr.size,
            "fit_status": "real_fit_completed",
        }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fit_path = out_dir / "fit_result.json"
    result_path = out_dir / "result.json"

    # honest provenance metadata
    result["computed_at"] = datetime.now(timezone.utc).isoformat()
    result["yaml_spec"] = "v4/preregistration/cve-vulnerabilities.yaml"
    result["fetcher"] = "v4/scripts/fetch/fetch_cve_nvd.py"
    result["session"] = "session-7-W2-C"

    fit_path.write_text(json.dumps(result, indent=2, default=float))
    result_path.write_text(json.dumps(result, indent=2, default=float))
    print(f"[fit] verdict={result['verdict']}")
    print(f"[fit] {result['reason']}")
    print(f"[fit] wrote {fit_path}")
    print(f"[fit] wrote {result_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
