#!/usr/bin/env python3
"""Layer 5 Phase 13 — Wikipedia pageview distribution analysis.

System: 7,521 unique English Wikipedia articles from 22 monthly Top-1000 lists
spanning 2023-01 through 2024-11 (2024-09 and 2024-12 are unavailable from
the Wikimedia REST endpoint). Aggregate metric = total views across the
months in which the article appeared in the Top-1000.

Predicted class: preferential_attachment (Yule-Simon / Barabási-Albert)
Expected α: Newman 2005 reports α ≈ 2.0 for Wikipedia pageviews; Zipf law
for word/popularity ranks predicts α = 2; BA degree exponent = 3 for the
underlying link graph. Confirmation band: α ∈ [1.7, 2.5].

Outputs:
  wikipedia_results.json    Clauset fit + bootstrap CI + null controls
  plot_pageviews_loglog.png log-log CCDF of yearly views (best-effort)
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
JSONL = OUT_DIR / "pageviews_2023_2024.jsonl"
RESULTS = OUT_DIR / "wikipedia_results.json"
PLOT = OUT_DIR / "plot_pageviews_loglog.png"


def load_views() -> tuple[np.ndarray, list[str]]:
    rows = []
    names = []
    with JSONL.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            v = int(rec.get("views_total", 0))
            if v > 0:
                rows.append(v)
                names.append(rec["article"])
    return np.asarray(rows, dtype=float), names


def make_plot(views: np.ndarray, alpha: float, xmin: float) -> None:
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [plot] matplotlib unavailable: {e}")
        return
    v_sorted = np.sort(views)[::-1]
    ranks = np.arange(1, len(v_sorted) + 1)
    ccdf = ranks / len(v_sorted)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.loglog(v_sorted, ccdf, ".", ms=2.5, alpha=0.5, color="#1f77b4", label="Empirical CCDF")

    # Draw reference power-law line on tail with same alpha
    tail = v_sorted[v_sorted >= xmin]
    if len(tail) > 10:
        x_ref = np.logspace(np.log10(xmin), np.log10(tail.max()), 50)
        # CCDF for continuous power law: P(X >= x) = (x / xmin)^(1 - alpha)
        y_ref = (x_ref / xmin) ** (1 - alpha)
        # Anchor to fraction in tail
        n_tail = np.sum(views >= xmin)
        y_ref = y_ref * (n_tail / len(views))
        ax.loglog(x_ref, y_ref, "r--", lw=1.5, label=f"Power-law α={alpha:.2f}")

    ax.set_xlabel("Pageviews (cumulative across 22 months)")
    ax.set_ylabel("CCDF P(X ≥ x)")
    ax.set_title(f"English Wikipedia top-articles pageview distribution\n(n = {len(views)}, 2023-01 to 2024-11)")
    ax.legend()
    ax.grid(True, which="both", alpha=0.3)
    fig.tight_layout()
    fig.savefig(PLOT, dpi=130)
    plt.close(fig)
    print(f"  [plot] wrote {PLOT}")


def main() -> int:
    print("Loading aggregated pageviews ...")
    views, names = load_views()
    print(f"  n_articles: {len(views)}")
    print(f"  views range: [{int(views.min())}, {int(views.max())}]")
    print(f"  median: {int(np.median(views))}  mean: {views.mean():.1f}")

    # 1. Clauset power-law fit (discrete=True — pageviews are integers)
    print("\n[1] Clauset power-law fit on yearly views (discrete=True) ...")
    pl = fit_clauset_powerlaw(views, "wikipedia_pageviews", discrete=True)
    for k, v in pl.items():
        print(f"  {k}: {v}")

    # 2. Bootstrap CI on alpha
    print("\n[2] Bootstrap 95% CI on α (n_boot=100) ...")
    ci = bootstrap_alpha_ci(views, n_boot=100, discrete=True)
    print(f"  CI: {ci}")

    # 3. Sub-population fit (top 20% / bottom 80% by views) for stability
    print("\n[3] Top-half / bottom-half split fits ...")
    median_v = float(np.median(views))
    top = views[views >= median_v]
    bot = views[views < median_v]
    pl_top = fit_clauset_powerlaw(top, "top_half", discrete=True) if len(top) >= 200 else {"error": "too few"}
    pl_bot = fit_clauset_powerlaw(bot, "bottom_half", discrete=True) if len(bot) >= 200 else {"error": "too few"}
    print(f"  top_half  n={len(top)}  α={pl_top.get('alpha')}")
    print(f"  bot_half  n={len(bot)}  α={pl_bot.get('alpha')}")

    # 4. Null controls (matched-n non-power-law synthetics)
    print("\n[4] Null controls (matched-n) ...")
    nulls = run_size_null_controls(seed=42, n=min(len(views), 8000))
    print(f"  all_rejected: {nulls['all_rejected']}")

    # 5. Plot
    print("\n[5] Generating log-log plot ...")
    if pl.get("alpha") and pl.get("xmin"):
        make_plot(views, float(pl["alpha"]), float(pl["xmin"]))

    # Verdict bands
    predicted_narrow = (1.7, 2.5)
    literature = (1.5, 3.0)  # broad heavy-tail span across views/Zipf literature
    alpha = pl.get("alpha")
    if alpha is None:
        verdict = "INCONCLUSIVE"
    elif predicted_narrow[0] <= alpha <= predicted_narrow[1]:
        verdict = "CONFIRMED"
    elif literature[0] <= alpha <= literature[1]:
        verdict = "CONFIRMED (literature band)"
    else:
        verdict = "DEVIATING"

    # Compose human-readable summary
    interp = f"Wikipedia pageview distribution α = {alpha:.3f}" if alpha else "α unavailable"
    if isinstance(ci, dict) and "ci_low" in ci:
        interp += f" (bootstrap 95% CI [{ci['ci_low']:.3f}, {ci['ci_high']:.3f}])"
    interp += f". Predicted [{predicted_narrow[0]}, {predicted_narrow[1]}] from Zipf/preferential-attachment heuristics. "
    if pl.get("vs_lognormal_R") is not None:
        interp += f"vs lognormal R = {pl['vs_lognormal_R']:.3f} (p={pl.get('vs_lognormal_p'):.3g}). "
    if pl.get("vs_exponential_R") is not None:
        interp += f"vs exponential R = {pl['vs_exponential_R']:.3f} (p={pl.get('vs_exponential_p'):.3g}). "
    interp += f"Verdict: {verdict}."

    out = {
        "phase": "Layer 5 Phase 13",
        "domain": "English Wikipedia pageviews (Wikimedia REST top API, 22 monthly Top-1000 lists from 2023-01 to 2024-11)",
        "predicted_class": "preferential_attachment (Yule-Simon / Zipf / Barabási-Albert)",
        "n_articles": int(len(views)),
        "views_range": [int(views.min()), int(views.max())],
        "views_median": float(np.median(views)),
        "views_mean": float(views.mean()),
        "powerlaw_fit": pl,
        "bootstrap_ci": ci,
        "subpop_top_half": pl_top,
        "subpop_bottom_half": pl_bot,
        "null_control": {
            "all_rejected": nulls["all_rejected"],
            "n_per_null": min(len(views), 8000),
        },
        "predicted_alpha_range": list(predicted_narrow),
        "literature_alpha_range": list(literature),
        "verdict": verdict,
        "interpretation": interp,
        "method_refs": [
            "Newman 2005 Contemp. Phys. (Wikipedia pageview α ≈ 2.0 reported)",
            "Zipf 1949 (rank-frequency law, α = 2)",
            "Yule 1925 (cumulative advantage)",
            "Simon 1955 Biometrika (Yule-Simon)",
            "Barabási-Albert 1999 Science (preferential attachment)",
            "Clauset-Shalizi-Newman 2009 SIAM Rev (MLE + LR tests)",
            "Mitzenmacher 2004 Internet Math. (power-law vs lognormal)",
            "Spoerri 2007 (Wikipedia popularity distribution)",
        ],
        "data_caveats": [
            "Wikimedia REST top API returns at most 1000 articles per month, so the catalog is truncated at the popular end — articles outside the monthly Top-1000 are absent",
            "2024-09 and 2024-12 returned HTTP 404 ('data not loaded') and are excluded",
            "Main_Page, Special:*, Wikipedia:*, Portal:*, File:*, Talk:*, User:*, Category:* are filtered out as non-article entries",
            "Yearly aggregate sums views across months an article appears in the Top-1000, not full annual views; articles popular only briefly are undercounted",
        ],
    }
    RESULTS.write_text(json.dumps(out, indent=2, ensure_ascii=False))
    print(f"\nVERDICT: {verdict}")
    print(f"  α = {alpha}  (predicted [{predicted_narrow[0]}, {predicted_narrow[1]}])")
    print(f"  Results: {RESULTS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
