***REMOVED***!/usr/bin/env python3
"""Phase 6 — run the frozen SOC pipeline on GitHub event cascades.

Reads events.jsonl (issue/PR open timestamps + engagement counts) produced by
fetch_github_cascades.py, builds cascades per the Phase 6 definition, and runs
the SAME pipeline that validated Phase 1-5:

  * fit_clauset_powerlaw + bootstrap_ci  -> cascade-SIZE power-law alpha + 95% CI
  * vuong LR test (inside fit)           -> power-law vs lognormal vs exponential
  * fit_omori_p                          -> Omori-Utsu p on the stacked delays

CASCADE CONSTRUCTION (per repo, independently — repos are not pooled in time)
----------------------------------------------------------------------------
1. Sort all of the repo's events by created_at.
2. "Loudness" of an event = comments + reactions. Main events = those with
   loudness > mu + MAIN_SIGMA*sigma  (per-repo threshold; 2-sigma default).
   This is the GitHub analogue of a mainshock — see fetch script docstring.
3. For each main event at time t0, its cascade = every event opened in the
   SAME repo in the window (t0, t0 + CASCADE_WINDOW_DAYS].
   - cascade SIZE  = count of derived events  -> power-law sample
   - cascade DELAYS = (t_derived - t0) seconds -> Omori delay stack
4. Overlapping cascades are allowed (a derived event may belong to several
   main events) — this mirrors how earthquake aftershock sequences overlap;
   the size/Omori statistics are taken over the pooled cascades.

VERDICT — identical 3-tier logic to Phase 1-5:
  PASS  : alpha inside pre-registered band AND no simpler model (lognormal /
          exponential) significantly beats power-law (Clauset 2009 rule).
  FAIL  : alpha outside band, OR a simpler model wins.
  INCONCLUSIVE / CONDITIONAL : too few cascades / events for a credible fit.

Pre-registered band (committed before seeing the verdict):
  cascade-size alpha in [1.5, 3.5]   (wide; threshold-cascade SOC systems in
  this project land 1.8-3.0, band widened because GitHub cascades have no
  established literature value)
  Omori p in [0.3, 1.3]              (canonical Omori band, same as Phase 1/3)
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve()
REPO_ROOT = ROOT.parents[3]
sys.path.insert(0, str(REPO_ROOT / "packages" / "soc-pipeline" / "src"))

from soc_pipeline import (  ***REMOVED*** noqa: E402
    bootstrap_ci,
    fit_clauset_powerlaw,
    fit_omori_p,
)

EVENTS = ROOT.parent / "events.jsonl"
RESULT_JSON = ROOT.parent / "cascade_results.json"

***REMOVED*** --- pre-registered parameters (frozen before inspecting the verdict) -------
PREREG_ALPHA_BAND = (1.5, 3.5)
PREREG_OMORI_BAND = (0.3, 1.3)
MAIN_SIGMA = 2.0          ***REMOVED*** main-event threshold = mu + 2*sigma loudness
CASCADE_WINDOW_DAYS = 30  ***REMOVED*** derived events counted within 30 days of main
MIN_DELAY_SEC = 3600.0    ***REMOVED*** ignore <1h (co-submitted noise), Omori lower edge
N_BOOT = 300


def load_events() -> list[dict]:
    rows: list[dict] = []
    with EVENTS.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def build_cascades(rows: list[dict]) -> dict:
    """Construct per-repo cascades. Returns sizes + pooled Omori delays."""
    by_repo: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.get("ts_unix"):
            by_repo[r["repo"]].append(r)

    window_s = CASCADE_WINDOW_DAYS * 86400.0
    cascade_sizes: list[int] = []
    omori_delays: list[float] = []
    per_repo: dict[str, dict] = {}

    for repo, evs in by_repo.items():
        evs.sort(key=lambda r: r["ts_unix"])
        ts = np.array([e["ts_unix"] for e in evs], dtype=float)
        loud = np.array(
            [e.get("comments", 0) + e.get("reactions", 0) for e in evs],
            dtype=float,
        )
        mu, sigma = float(loud.mean()), float(loud.std())
        thr = mu + MAIN_SIGMA * sigma
        main_idx = np.where(loud > thr)[0]

        repo_sizes: list[int] = []
        for mi in main_idx:
            t0 = ts[mi]
            ***REMOVED*** derived events strictly after the main event, within window
            mask = (ts > t0) & (ts <= t0 + window_s)
            delays = ts[mask] - t0
            size = int(mask.sum())
            repo_sizes.append(size)
            for d in delays:
                if d >= MIN_DELAY_SEC:
                    omori_delays.append(float(d))
        cascade_sizes.extend(repo_sizes)
        per_repo[repo] = {
            "n_events": len(evs),
            "loud_mu": mu,
            "loud_sigma": sigma,
            "main_threshold": thr,
            "n_main_events": int(len(main_idx)),
            "mean_cascade_size": float(np.mean(repo_sizes)) if repo_sizes else 0.0,
            "max_cascade_size": int(max(repo_sizes)) if repo_sizes else 0,
        }

    return {
        "cascade_sizes": np.array(cascade_sizes, dtype=float),
        "omori_delays": np.array(omori_delays, dtype=float),
        "per_repo": per_repo,
        "n_repos": len(by_repo),
    }


def sensitivity_sweep(rows: list[dict]) -> list[dict]:
    """Re-run the cascade-size fit across (window, sigma) settings.

    A genuine scale-free (power-law) regime would give a window-invariant
    alpha. If alpha drifts strongly with the window, that itself is evidence
    AGAINST SOC — recorded here so the verdict cannot be dismissed as a
    single-parameter artefact.
    """
    global CASCADE_WINDOW_DAYS, MAIN_SIGMA
    saved = (CASCADE_WINDOW_DAYS, MAIN_SIGMA)
    grid = [(30, 2.0), (7, 2.0), (3, 2.0), (1, 2.0), (3, 3.0)]
    results: list[dict] = []
    for win, sig in grid:
        CASCADE_WINDOW_DAYS, MAIN_SIGMA = win, sig
        cas = build_cascades(rows)
        sizes = cas["cascade_sizes"]
        fit = fit_clauset_powerlaw(sizes, discrete=True)
        results.append({
            "window_days": win,
            "main_sigma": sig,
            "n_cascades": int(len(sizes)),
            "mean_size": float(sizes.mean()) if len(sizes) else 0.0,
            "alpha": fit.alpha,
            "ks": fit.ks_statistic,
            "rejects_power_law": fit.rejects_power_law,
            "vs_lognormal_R": fit.vs_lognormal_R,
            "vs_exponential_R": fit.vs_exponential_R,
        })
    CASCADE_WINDOW_DAYS, MAIN_SIGMA = saved
    return results


def decide(alpha, in_band, rejects, n_sizes) -> tuple[str, str]:
    """3-tier verdict, same logic as Phase 1-5 validate()."""
    if n_sizes < 100:
        return "CONDITIONAL", (
            f"only {n_sizes} cascades — below the 100-sample minimum for a "
            f"credible Clauset fit; result is not decisive"
        )
    if rejects:
        return "FAIL", "a simpler model (lognormal/exponential) beats power-law"
    if not in_band:
        return "FAIL", (
            f"alpha={alpha:.3f} outside pre-registered band "
            f"[{PREREG_ALPHA_BAND[0]}, {PREREG_ALPHA_BAND[1]}]"
        )
    return "PASS", (
        f"alpha={alpha:.3f} inside band "
        f"[{PREREG_ALPHA_BAND[0]}, {PREREG_ALPHA_BAND[1]}] and power-law "
        f"not beaten by a simpler model"
    )


def main() -> None:
    if not EVENTS.is_file():
        print(f"missing {EVENTS}; run fetch_github_cascades.py first",
              file=sys.stderr)
        sys.exit(2)

    rows = load_events()
    print(f"loaded {len(rows)} events")
    cas = build_cascades(rows)
    sizes = cas["cascade_sizes"]
    delays = cas["omori_delays"]
    print(f"repos={cas['n_repos']}  cascades={len(sizes)}  "
          f"omori_delays={len(delays)}")
    if len(sizes):
        print(f"cascade size: min={sizes.min():.0f} max={sizes.max():.0f} "
              f"mean={sizes.mean():.1f} median={np.median(sizes):.0f}")

    ***REMOVED*** --- power-law fit on cascade SIZE ------------------------------------
    fit = fit_clauset_powerlaw(sizes, name="github_cascade_size", discrete=True)
    boot = bootstrap_ci(sizes, n_boot=N_BOOT, discrete=True)

    alpha = fit.alpha
    if alpha is not None:
        lo, hi = PREREG_ALPHA_BAND
        in_band = bool(lo <= alpha <= hi)
        print(f"\nCLAUSET FIT: alpha={alpha:.3f} xmin={fit.xmin} "
              f"n_tail={fit.n_tail} KS={fit.ks_statistic}")
        print(f"  vs lognormal:   R={fit.vs_lognormal_R} p={fit.vs_lognormal_p}")
        print(f"  vs exponential: R={fit.vs_exponential_R} p={fit.vs_exponential_p}")
        print(f"  rejects power-law: {fit.rejects_power_law}")
        if not boot.error:
            print(f"  bootstrap 95% CI: [{boot.ci_low:.3f}, {boot.ci_high:.3f}]")
    else:
        in_band = False
        print(f"\nCLAUSET FIT FAILED: {fit.error}")

    ***REMOVED*** --- Omori-Utsu p on stacked delays -----------------------------------
    omori = fit_omori_p(delays)
    if omori.error:
        print(f"\nOMORI: {omori.error}")
        omori_p_ok = None
    else:
        olo, ohi = PREREG_OMORI_BAND
        omori_p_ok = bool(olo <= omori.p <= ohi)
        print(f"\nOMORI: p={omori.p:.3f}+/-{omori.p_sigma:.3f} "
              f"c={omori.c_days}d R2={omori.R2:.3f} "
              f"n_aftershocks={omori.n_aftershocks_in_fit}")

    ***REMOVED*** --- sensitivity sweep: is the verdict robust to window/sigma? --------
    print("\nsensitivity sweep (window x sigma):")
    sweep = sensitivity_sweep(rows)
    for s in sweep:
        a = f"{s['alpha']:.3f}" if s["alpha"] else "NA"
        print(f"  win={s['window_days']:2d}d sig={s['main_sigma']}: "
              f"n={s['n_cascades']:4d} alpha={a} "
              f"rejects_PL={s['rejects_power_law']} "
              f"R_ln={s['vs_lognormal_R']:.1f}")
    all_reject = all(s["rejects_power_law"] for s in sweep)
    print(f"  -> power-law rejected in ALL settings: {all_reject}")

    verdict, reason = decide(
        alpha, in_band, fit.rejects_power_law, len(sizes)
    )
    if verdict == "FAIL" and all_reject:
        reason += (
            "; robust — power-law is rejected across every window/sigma "
            "setting and alpha drifts with the window, confirming there is "
            "no scale-free regime (not a single-parameter artefact)"
        )
    print(f"\n=== VERDICT: {verdict} ===\n{reason}")

    out = {
        "domain": "GitHub event cascades (issue/PR burst after a hot main event)",
        "phase": 6,
        "predicted_class": "soc_threshold_cascade",
        "cross_domain_test": True,
        "cascade_definition": {
            "main_event": f"issue/PR with (comments+reactions) > mu + "
                          f"{MAIN_SIGMA}*sigma per repo",
            "cascade": f"events opened in same repo within "
                       f"{CASCADE_WINDOW_DAYS}d after a main event",
            "size_observable": "count of derived events per cascade",
            "omori_observable": "stacked delay (s) of derived events vs main",
        },
        "n_events": len(rows),
        "n_repos": cas["n_repos"],
        "n_cascades": int(len(sizes)),
        "n_omori_delays": int(len(delays)),
        "preregistered_alpha_band": list(PREREG_ALPHA_BAND),
        "preregistered_omori_band": list(PREREG_OMORI_BAND),
        "clauset_fit": fit.to_dict(),
        "bootstrap_ci": (
            {"error": boot.error} if boot.error
            else {
                "ci_low": boot.ci_low, "ci_high": boot.ci_high,
                "alpha_mean": boot.alpha_mean, "alpha_std": boot.alpha_std,
                "n_boot_succeeded": boot.n_boot_succeeded,
            }
        ),
        "alpha_in_band": in_band,
        "omori": (
            {"error": omori.error} if omori.error
            else {
                "p": omori.p, "p_sigma": omori.p_sigma,
                "c_days": omori.c_days, "logK": omori.logK, "R2": omori.R2,
                "n_aftershocks_in_fit": omori.n_aftershocks_in_fit,
                "n_bins_used": omori.n_bins_used,
                "p_in_band": omori_p_ok,
            }
        ),
        "verdict": verdict,
        "verdict_reason": reason,
        "sensitivity_sweep": sweep,
        "power_law_rejected_in_all_settings": all_reject,
        "per_repo": cas["per_repo"],
        "method_refs": [
            "Clauset-Shalizi-Newman 2009 (power-law MLE)",
            "Omori 1894 / Utsu 1961 (aftershock-rate decay)",
            "Vuong 1989 (LR model comparison)",
        ],
    }
    with RESULT_JSON.open("w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nwrote {RESULT_JSON}")


if __name__ == "__main__":
    main()
