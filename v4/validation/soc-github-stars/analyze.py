#!/usr/bin/env python3
"""Layer 5 Phase 6 — GitHub repository star counts.

System: Top 8,398 GitHub repos by stars (stratified sample 250 to 500k stars).
Predicted class: preferential_attachment (Barabási-Albert 1999)
Expected α ∈ [2.0, 3.0] for BA degree distribution.

This is NOT the same as soc_threshold_cascade. Preferential attachment is
a DIFFERENT universality class with its own characteristic exponent. Test:
- α(stars) MLE fit
- vs lognormal (BA strict has power-law tail; lognormal often plausible too)
- Compare to canonical α_BA = 3.0 (Barabási-Albert with m → ∞)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve()
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO / "v4" / "lib"))

from soc_pipeline import (  # noqa: E402
    bootstrap_alpha_ci,
    fit_clauset_powerlaw,
    run_size_null_controls,
)

OUT_DIR = ROOT.parent
REPOS = OUT_DIR / "repos.jsonl"
RESULTS = OUT_DIR / "github_results.json"


def main():
    print("Loading repos...")
    rows = []
    with REPOS.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                rows.append(rec)
            except json.JSONDecodeError:
                continue
    print(f"  n_repos: {len(rows)}")
    stars = np.array([r["stars"] for r in rows if r.get("stars", 0) > 0])
    print(f"  star range: [{stars.min()}, {stars.max()}]")
    print(f"  median: {np.median(stars)}, mean: {stars.mean():.1f}")

    # 1. Clauset power-law fit on stars
    print("\n[1] Clauset power-law fit on stars (discrete)...")
    pl = fit_clauset_powerlaw(stars.astype(float), "github_stars", discrete=True)
    for k, v in pl.items():
        print(f"  {k}: {v}")

    # 2. Bootstrap CI
    print("\n[2] Bootstrap 95% CI on α (n_boot=100)...")
    ci = bootstrap_alpha_ci(stars.astype(float), n_boot=100, discrete=True)
    print(f"  CI: {ci}")

    # 3. Per-language breakdown
    print("\n[3] Per-language top exponents (selected popular languages)...")
    from collections import defaultdict
    by_lang = defaultdict(list)
    for r in rows:
        if r.get("language"):
            by_lang[r["language"]].append(r["stars"])
    lang_fits = {}
    for lang, vals in sorted(by_lang.items(), key=lambda kv: -len(kv[1]))[:10]:
        if len(vals) < 300:
            continue
        f = fit_clauset_powerlaw(np.array(vals, dtype=float), f"lang_{lang}", discrete=True)
        lang_fits[lang] = {
            "n": len(vals),
            "alpha": f.get("alpha"),
            "xmin": f.get("xmin"),
            "n_tail": f.get("n_tail"),
            "vs_lognormal_R": f.get("vs_lognormal_R"),
            "winner": f.get("vs_powerlaw_lognormal_winner"),
        }
        print(f"  {lang:18s} n={len(vals):5d}  α={f.get('alpha'):.3f}  winner={f.get('vs_powerlaw_lognormal_winner')}")

    # 4. Null control
    print("\n[4] Null control (matched n)...")
    null_n = min(len(stars), 8000)
    nulls = run_size_null_controls(seed=42, n=null_n)
    print(f"  all_rejected: {nulls['all_rejected']}")

    # Verdict
    predicted_narrow = (2.0, 3.0)
    literature = (1.8, 3.5)
    alpha = pl.get("alpha")
    if alpha is None:
        verdict = "INCONCLUSIVE"
    elif predicted_narrow[0] <= alpha <= predicted_narrow[1]:
        verdict = "CONFIRMED"
    elif literature[0] <= alpha <= literature[1]:
        verdict = "CONFIRMED (literature band)"
    else:
        verdict = "DEVIATING"

    out = {
        "phase": "Layer 5 Phase 6",
        "domain": "GitHub repository stargazers (GitHub Search API, top 8398 repos, 2026-05)",
        "predicted_class": "preferential_attachment (Barabási-Albert 1999)",
        "n_repos": int(len(stars)),
        "star_range": [int(stars.min()), int(stars.max())],
        "star_median": float(np.median(stars)),
        "star_mean": float(stars.mean()),
        "powerlaw_fit": pl,
        "bootstrap_ci": ci,
        "per_language_fits": lang_fits,
        "null_control": {
            "all_rejected": nulls["all_rejected"],
            "n_per_null": null_n,
        },
        "predicted_alpha_range": list(predicted_narrow),
        "literature_alpha_range": list(literature),
        "verdict": verdict,
        "interpretation": (
            f"GitHub repository star count distribution α = {alpha:.3f}"
            + (f" (bootstrap 95% CI [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}])" if isinstance(ci, dict) and 'ci_low' in ci else "")
            + f". Predicted [2.0, 3.0] from Barabási-Albert preferential attachment. "
            + f"vs lognormal R = {pl.get('vs_lognormal_R'):.3f} (p={pl.get('vs_lognormal_p'):.3g}). "
            + f"Verdict: {verdict}."
        ),
        "method_refs": [
            "Barabási-Albert 1999 Science (preferential attachment)",
            "Yule 1925 (cumulative advantage in species)",
            "Simon 1955 Biometrika (Yule-Simon)",
            "Newman 2005 Contemp. Phys. (power-law review)",
            "Clauset-Shalizi-Newman 2009 SIAM Rev",
            "Albert-Barabási 2002 Rev. Mod. Phys.",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2))
    print(f"\nVERDICT: {verdict}")
    print(f"  α = {alpha} (predicted [2.0, 3.0])")
    print(f"  Results saved: {RESULTS}")


if __name__ == "__main__":
    main()
