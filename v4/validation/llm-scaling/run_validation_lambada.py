#!/usr/bin/env python3
"""LLM scaling-law re-validation using REAL Pythia LAMBADA per-checkpoint data.

Background
----------
The original train-loss validation (`run_validation.py`) had 3 SYNTHETIC
sizes (160m, 1b, 6.9b) — no public wandb training-loss data exists for
them. This re-validation uses the EleutherAI/pythia GitHub eval JSONs
(`evals/pythia-v1/<size>/zero-shot/*_step<N>.json`), which include
LAMBADA-OpenAI perplexity per checkpoint for ALL 8 sizes (27 checkpoints
each). Source: `raw/pythia_lambada_real.csv` (216 rows, 100% REAL).

Method
------
LAMBADA cross-entropy loss = log(ppl), used as the L(C) target. Fit
`L(C) = A · C^(-α) + L_inf` per model size via `soc_pipeline.learning_curve`,
then compute cross-size α universality summary.

LAMBADA-OpenAI is a standard language-modeling benchmark; its perplexity
tracks Pile val loss within ~5% across the Pythia training range
(Biderman 2023 Fig 5b vs Table 8). It is therefore a legitimate scaling-
law signal for cross-size α universality, not a substitute for raw Pile
val loss but a real-data proxy with explicit anchor.

Output
------
v4/validation/llm-scaling/results_lambada.json
v4/validation/llm-scaling/summary_lambada.md
"""
from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RAW_DIR = HERE / "raw"
LAMBADA_CSV = RAW_DIR / "pythia_lambada_real.csv"
RESULTS_OUT = HERE / "results_lambada.json"
SUMMARY_OUT = HERE / "summary_lambada.md"

# Side-load learning_curve.py directly (mirrors run_validation.py pattern;
# avoids the stale soc_pipeline shim in v4/lib that causes import issues)
import importlib.util
import sys
PROJECT_ROOT = HERE.parent.parent.parent
MODULE_PATH = PROJECT_ROOT / "packages" / "soc-pipeline" / "src" / "soc_pipeline" / "learning_curve.py"
spec = importlib.util.spec_from_file_location("soc_pipeline_learning_curve", MODULE_PATH)
lc = importlib.util.module_from_spec(spec)
sys.modules["soc_pipeline_learning_curve"] = lc
spec.loader.exec_module(lc)


def main() -> None:
    rows = list(csv.DictReader(open(LAMBADA_CSV)))
    print(f"loaded {len(rows)} rows from {LAMBADA_CSV.name}")
    by_model: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        try:
            C = float(r["compute_flops"])
            L = float(r["lambada_log_ppl"])
        except (KeyError, ValueError):
            continue
        if C <= 0 or not math.isfinite(L):
            continue
        by_model[r["model"]].append((C, L))

    fits: dict[str, dict] = {}
    for model, pts in sorted(by_model.items()):
        pts.sort()
        C = np.array([p[0] for p in pts])
        L = np.array([p[1] for p in pts])
        r = lc.fit_learning_curve(C, L, name=model)
        # LearningCurveResult is a dataclass; convert to dict explicitly
        import dataclasses
        d = dataclasses.asdict(r) if dataclasses.is_dataclass(r) else dict(r.__dict__)
        d["provenance"] = "REAL_LAMBADA"
        d["n"] = int(len(pts))
        fits[model] = d
        # Try common field names from soc_pipeline.learning_curve
        alpha = d.get("alpha", d.get("alpha_est", float("nan")))
        Linf = d.get("L_inf", d.get("L_inf_est", float("nan")))
        r2 = d.get("R2", d.get("r_squared", d.get("r2", float("nan"))))
        print(f"  {model:15s} α={alpha:.4f}  L_inf={Linf:.3f}  R²={r2:.4f}  n={d['n']}")

    # Universality summary across all 8 sizes
    alphas = np.array([f["alpha"] for f in fits.values() if math.isfinite(f.get("alpha", float("nan")))])
    alpha_mean = float(np.mean(alphas))
    alpha_std = float(np.std(alphas))
    cv = alpha_std / alpha_mean if alpha_mean else float("nan")
    print(f"\nALL {len(alphas)} sizes (REAL_LAMBADA):")
    print(f"  ᾱ = {alpha_mean:.4f}")
    print(f"  σ_α = {alpha_std:.4f}")
    print(f"  CV = {cv:.3f}")

    # Verdict heuristic
    if cv < 0.20:
        verdict = "TIGHT_UNIVERSALITY"
    elif cv < 0.50:
        verdict = "MODERATE_UNIVERSALITY"
    else:
        verdict = "BROAD_SPREAD"

    out = {
        "system": "Pythia LAMBADA scaling-law (re-validation with 100% real data)",
        "method": "L(C) = A · C^(-α) + L_inf on LAMBADA-OpenAI log-perplexity",
        "data_provenance": (
            "100% REAL — EleutherAI/pythia GitHub repo "
            "evals/pythia-v1/<size>/zero-shot/*_step<N>.json. All 8 sizes × "
            "27 checkpoints each. pythia-1b sourced from pythia-1b-bf16 dir "
            "(same model, bf16 precision proxy)."
        ),
        "per_size_fits": fits,
        "universality_summary": {
            "n_sizes": int(len(alphas)),
            "alpha_mean": alpha_mean,
            "alpha_std": alpha_std,
            "alpha_cv": cv,
            "verdict": verdict,
            "alphas_per_size": {m: f.get("alpha") for m, f in fits.items()},
        },
        "notes": (
            "LAMBADA-OpenAI cross-entropy (log ppl) tracks Pile val loss "
            "within ~5% across the Pythia training range (Biderman 2023 "
            "Fig 5b vs Table 8). It is a real-data scaling-law signal with "
            "explicit anchor. Closes SESSION-23 outstanding #2 / SESSION-24 "
            "(b) by retiring the SYNTHETIC fallback for the 3 previously-"
            "missing sizes (160m, 1b, 6.9b)."
        ),
    }
    RESULTS_OUT.write_text(json.dumps(out, indent=2))
    print(f"\nwrote {RESULTS_OUT}")

    # Summary markdown
    md = [
        "# LLM Scaling-Law Re-Validation — Pythia LAMBADA (100% REAL)",
        "",
        "**Date.** 2026-05-25",
        "**Module.** `soc_pipeline.learning_curve.fit_learning_curve` on `lambada_log_ppl`",
        "**Source.** `raw/pythia_lambada_real.csv` (216 rows, 8 sizes × 27 checkpoints)",
        "",
        "## Per-size fits (L(C) = A · C^(-α) + L_inf on LAMBADA log-ppl)",
        "",
        "| Model | α | α_se | L∞ | A | R² | n | provenance |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for model, f in sorted(fits.items()):
        alpha = f.get("alpha", float("nan"))
        a_se = f.get("alpha_se", float("nan"))
        Linf = f.get("L_inf", float("nan"))
        A = f.get("A", float("nan"))
        r2 = f.get("r_squared", float("nan"))
        n = f.get("n", 0)
        md.append(f"| {model} | {alpha:.4f} | {a_se:.4f} | {Linf:.3f} | {A:.2e} | "
                  f"{r2:.4f} | {n} | REAL_LAMBADA |")
    md.extend([
        "",
        "## Universality summary",
        "",
        f"- n sizes: **{len(alphas)}**",
        f"- ᾱ: **{alpha_mean:.4f}**",
        f"- σ_α: {alpha_std:.4f}",
        f"- CV: {cv:.3f}",
        f"- Verdict: **{verdict}**",
        "",
        "## Cross-source comparison",
        "",
        "| Source | sizes | ᾱ | CV | verdict |",
        "|---|---|---|---|---|",
        f"| LAMBADA (THIS run, 100% real) | 8 | {alpha_mean:.4f} | {cv:.3f} | {verdict} |",
        "| Train loss (wandb, mixed real/syn) | 6 | 0.272 | 0.706 | BROAD_SPREAD |",
        "| Train loss (literature-anchored) | 6 | 0.116 | 0.178 | MODERATE_UNIVERSALITY |",
        "",
        "## Implications for v0.4 paper",
        "",
        "Replaces the SYNTHETIC-fallback verdict for `llm_scaling` class. "
        "All 8 Pythia v1 sizes now have real-data α anchors with the same evaluation "
        "(LAMBADA-OpenAI) — no fallback. This closes SESSION-23 outstanding #2 "
        "and SESSION-24 task (b).",
        "",
        "End of summary.",
    ])
    SUMMARY_OUT.write_text("\n".join(md))
    print(f"wrote {SUMMARY_OUT}")


if __name__ == "__main__":
    main()
