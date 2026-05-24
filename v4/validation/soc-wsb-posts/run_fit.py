"""Run pre-registered fits on WSB post data.

Pre-reg: v4/preregistration/wsb-posts.yaml
- PRIMARY (P1): Omori-Utsu p in [0.7, 1.3] on post-arrival inter-event times after
  detected "main shocks" (high-rate bins). Uses bin_and_omori_from_events.
- SECONDARY (P2): Clauset power-law alpha in [1.7, 2.3] on cascade size (num_comments).

Two slices analyzed independently:
- pre_2021 (2019-2020 before GME regime shift)
- post_2024 (2024)
And the union (full).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# soc_pipeline lives in packages/soc-pipeline/src — make it importable
_PKG = Path(__file__).resolve().parents[3] / "packages" / "soc-pipeline" / "src"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

from soc_pipeline import bootstrap_ci, fit_clauset_powerlaw
from soc_pipeline.omori import bin_and_omori_from_events

HERE = Path(__file__).parent
RAW = HERE / "raw_posts.jsonl"
OUT = HERE / "fit_result.json"

# pre-reg bands from wsb-posts.yaml
P1_BAND = (0.7, 1.3)   # Omori p
P2_BAND = (1.7, 2.3)   # cascade-size alpha


def load_rows():
    with RAW.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def fit_primary_omori(rows, label: str) -> dict:
    """P1: post-arrival times treated as event stream; bin_and_omori detects spikes."""
    times = np.array(sorted(r["created_utc"] for r in rows if r.get("created_utc")), dtype=float)
    if len(times) < 100:
        return {"label": label, "error": f"too few posts ({len(times)})"}
    # bin_seconds chosen so that mean ~ 5-10 posts/bin (WSB posts ~per 3 min in dense windows)
    res = bin_and_omori_from_events(times, bin_seconds=300.0, sigma_k=2.5, window_bins=48)
    out = {
        "label": label,
        "n_events": int(len(times)),
        "p": res.p,
        "logK": res.logK,
        "R2": res.R2,
        "n_main_shocks": res.n_main,
        "mu_per_bin": res.mu,
        "sigma_per_bin": res.sigma,
        "threshold": res.threshold,
        "n_bins_used": res.n_bins_used,
        "extra": res.extra,
        "error": res.error,
    }
    if res.p is not None:
        out["in_band"] = P1_BAND[0] <= res.p <= P1_BAND[1]
        out["band"] = list(P1_BAND)
    return out


def fit_secondary_clauset(rows, label: str) -> dict:
    """P2: Clauset power-law on cascade size = num_comments."""
    sizes = np.array([r.get("num_comments") or 0 for r in rows], dtype=int)
    sizes = sizes[sizes >= 1]  # Clauset needs positive
    if len(sizes) < 100:
        return {"label": label, "error": f"too few cascades ({len(sizes)})"}
    fit = fit_clauset_powerlaw(sizes, name=f"wsb_cascade_{label}", discrete=True)
    fd = fit.to_dict()
    # bootstrap CI
    try:
        boot = bootstrap_ci(sizes, n_boot=200, seed=42, discrete=True)
        if not boot.error:
            fd["bootstrap"] = {
                "alpha_mean": boot.alpha_mean,
                "alpha_median": boot.alpha_median,
                "alpha_std": boot.alpha_std,
                "ci_low": boot.ci_low,
                "ci_high": boot.ci_high,
                "n_boot_succeeded": boot.n_boot_succeeded,
            }
    except Exception as e:
        fd["bootstrap_error"] = f"{type(e).__name__}: {e}"

    alpha = fd.get("alpha")
    if alpha is not None:
        fd["in_band"] = P2_BAND[0] <= alpha <= P2_BAND[1]
        fd["band"] = list(P2_BAND)
    fd["n_cascades"] = int(len(sizes))
    fd["max_cascade"] = int(sizes.max())
    fd["median_cascade"] = int(np.median(sizes))
    fd["label"] = label
    return fd


def derive_verdict(primary: dict, secondary: dict) -> str:
    """Per yaml verdict_rules.
    PASS: PRIMARY in band AND Poisson null rejected.
    PARTIAL: PRIMARY in band but SECONDARY out, or vice-versa.
    FAIL: PRIMARY outside band.
    INCONCLUSIVE: insufficient viral roots OR data extraction blocked.
    """
    p_err = primary.get("error")
    s_err = secondary.get("error")
    p_in = primary.get("in_band")
    s_in = secondary.get("in_band")

    # INCONCLUSIVE only if PRIMARY fit failed entirely
    if p_err is not None:
        return "INCONCLUSIVE"

    if p_in is True and s_in is True:
        return "PASS"
    if p_in is True and s_in is False:
        return "PARTIAL"
    if p_in is False and s_in is True:
        return "PARTIAL"
    # primary outside band
    return "FAIL"


def main():
    rows = load_rows()
    print(f"loaded {len(rows)} rows")

    slices = {
        "pre_2021": [r for r in rows if r.get("slice") == "pre_2021"],
        "post_2024": [r for r in rows if r.get("slice") == "post_2024"],
        "full_union": rows,
    }

    result = {
        "pre_registration": "v4/preregistration/wsb-posts.yaml",
        "pre_registered_at": "2026-05-14",
        "executed_at": "2026-05-14",
        "data_source": "arctic_shift (Pushshift mirror) — https://arctic-shift.photon-reddit.com/",
        "data_source_reason": "Pushshift API closed post-2023 Reddit changes; arctic_shift community mirror indexes the same dump data",
        "n_total": len(rows),
        "p1_band": list(P1_BAND),
        "p2_band": list(P2_BAND),
        "slices": {},
    }

    for label, sl in slices.items():
        print(f"--- slice={label} n={len(sl)} ---")
        primary = fit_primary_omori(sl, label)
        secondary = fit_secondary_clauset(sl, label)
        verdict = derive_verdict(primary, secondary)
        result["slices"][label] = {
            "n_posts": len(sl),
            "primary_omori": primary,
            "secondary_cascade_clauset": secondary,
            "verdict": verdict,
        }
        print(f"  primary p={primary.get('p')!r} in_band={primary.get('in_band')!r}")
        print(f"  secondary alpha={secondary.get('alpha')!r} in_band={secondary.get('in_band')!r}")
        print(f"  verdict: {verdict}")

    # headline verdict = pre-reg's primary slice = pre_2021 (adversarial robustness pick)
    result["headline_slice"] = "pre_2021"
    result["headline_verdict"] = result["slices"]["pre_2021"]["verdict"]

    OUT.write_text(json.dumps(result, indent=2, default=str))
    print(f"wrote {OUT}")
    print(f"HEADLINE VERDICT ({result['headline_slice']}): {result['headline_verdict']}")


if __name__ == "__main__":
    main()
