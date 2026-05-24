"""LLM scaling-law learning-curve validation runner.

Fits the Chinchilla / Kaplan power-law L(C) = A·C^(-alpha) + L_inf on:
    - 6 Pythia model sizes (per-size checkpoint trajectories vs compute)
    - Kaplan 2020 GPT-family compute frontier
    - Hoffmann 2022 Chinchilla compute frontier

Outputs:
    results.json  — per-series alpha, A, L_inf, R^2, residual_rms, n_points
    summary.md    — human-readable comparison table + Chinchilla benchmark

Run:
    python v4/validation/llm-scaling/run_validation.py
"""
from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]  # v4/validation/llm-scaling → project root
MODULE_PATH = (
    PROJECT_ROOT / "packages" / "soc-pipeline" / "src" / "soc_pipeline" / "learning_curve.py"
)
RAW_DIR = HERE / "raw"


def _load_learning_curve():
    """Side-load learning_curve.py without going through soc_pipeline/__init__.

    Why: the installed soc_pipeline package is editable-linked to a /tmp path
    in this checkout (scrub-pre-backup state). Bypassing __init__ lets us run
    learning_curve.py standalone and keeps the main soc_pipeline API untouched.
    """
    spec = importlib.util.spec_from_file_location("soc_pipeline_learning_curve", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["soc_pipeline_learning_curve"] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _pythia_series(rows: list[dict]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Bucket Pythia rows by model → (compute_flops, loss) arrays."""
    by_model: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for r in rows:
        by_model[r["model"]].append((float(r["compute_flops"]), float(r["loss"])))
    out = {}
    for m, pairs in by_model.items():
        pairs.sort()
        C = np.array([p[0] for p in pairs])
        L = np.array([p[1] for p in pairs])
        out[m] = (C, L)
    return out


def _flat_series(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    C = np.array([float(r["compute_flops"]) for r in rows])
    L = np.array([float(r["loss"]) for r in rows])
    order = np.argsort(C)
    return C[order], L[order]


def main() -> dict:
    lc = _load_learning_curve()

    # --- Pythia (6 sizes) ---
    pythia_rows = _read_csv(RAW_DIR / "pythia_checkpoints.csv")
    pythia = _pythia_series(pythia_rows)

    fits = {}
    for model in sorted(pythia.keys()):
        C, L = pythia[model]
        r = lc.fit_learning_curve(C, L, name=model)
        fits[model] = r.to_dict()

    # --- Kaplan 2020 ---
    kap_rows = _read_csv(RAW_DIR / "kaplan2020_compute.csv")
    C, L = _flat_series(kap_rows)
    # Kaplan has L_inf = 0 (pure power law). Force the floor low so the
    # fitter doesn't get pulled toward a spurious nonzero floor on noisy data.
    r = lc.fit_learning_curve(C, L, name="kaplan2020-gpt", L_inf_bounds=(0.0, 0.5))
    fits["kaplan2020-gpt"] = r.to_dict()

    # --- Hoffmann 2022 (Chinchilla) ---
    hof_rows = _read_csv(RAW_DIR / "hoffmann2022_compute.csv")
    C, L = _flat_series(hof_rows)
    r = lc.fit_learning_curve(C, L, name="hoffmann2022-chinchilla")
    fits["hoffmann2022-chinchilla"] = r.to_dict()

    # --- Summary stats across Pythia sizes ---
    pythia_alphas = [fits[m]["alpha"] for m in pythia.keys() if fits[m].get("alpha") is not None]
    pythia_alpha_mean = float(np.mean(pythia_alphas)) if pythia_alphas else None
    pythia_alpha_std = float(np.std(pythia_alphas, ddof=1)) if len(pythia_alphas) > 1 else None
    pythia_alpha_cv = (
        pythia_alpha_std / pythia_alpha_mean
        if pythia_alpha_mean and pythia_alpha_std is not None
        else None
    )

    # Chinchilla benchmark: alpha_C ≈ 0.155 (compute frontier), or
    # alpha_N ≈ 0.34 if fitting vs N. The Pythia per-size trajectories
    # are vs *compute within a fixed N*, which is closer to alpha_D ≈ 0.28
    # (token-axis exponent from Hoffmann 2022 Table 4) — i.e. for a fixed N,
    # adding more tokens reduces loss at rate ~D^(-0.28).
    benchmark = {
        "chinchilla_alpha_compute": 0.155,
        "chinchilla_alpha_N": 0.34,
        "chinchilla_alpha_D": 0.28,
        "kaplan_alpha_C": 0.050,
        "stevens_psychophysics_alpha": 0.50,
    }

    summary = {
        "pythia_n_sizes": len(pythia),
        "pythia_alpha_mean": pythia_alpha_mean,
        "pythia_alpha_std": pythia_alpha_std,
        "pythia_alpha_cv": pythia_alpha_cv,
        "universality_verdict": _universality_verdict(pythia_alpha_cv),
        "benchmark": benchmark,
    }

    out = {
        "schema_version": "1.0",
        "validation": "llm-scaling",
        "date": "2026-05-24",
        "module": "soc_pipeline.learning_curve.fit_learning_curve",
        "fits": fits,
        "summary": summary,
    }

    (HERE / "results.json").write_text(json.dumps(out, indent=2))
    _write_summary_md(out)
    return out


def _universality_verdict(cv: float | None) -> str:
    """Coarse universality verdict from coefficient-of-variation on alpha.

    CV < 0.1  → tight cluster (strong universality signal)
    CV < 0.2  → moderate cluster (consistent with universality given noise)
    CV >= 0.2 → broad spread (likely not a single universality class)
    """
    if cv is None:
        return "UNKNOWN"
    if cv < 0.1:
        return "STRONG_UNIVERSALITY"
    if cv < 0.2:
        return "MODERATE_UNIVERSALITY"
    return "BROAD_SPREAD"


def _write_summary_md(out: dict) -> None:
    s = out["summary"]
    lines = [
        "# LLM Scaling-Law Learning-Curve Validation — Summary",
        "",
        f"**Date.** {out['date']}",
        f"**Module.** `{out['module']}`",
        f"**Pythia sizes fitted.** {s['pythia_n_sizes']}",
        "",
        "## Per-series fits  (L(C) = A · C^(-α) + L∞)",
        "",
        "| Model | α | α_se | L∞ | A | R² | n |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, fit in out["fits"].items():
        if fit.get("error"):
            lines.append(f"| {name} | — | — | — | — | — | {fit.get('n_points', 0)} (error: {fit['error']}) |")
            continue
        lines.append(
            f"| {name} | {fit['alpha']:.4f} | "
            f"{fit['alpha_se']:.4f} | "
            f"{fit['L_inf']:.4f} | "
            f"{fit['A']:.3g} | "
            f"{fit['R2']:.4f} | "
            f"{fit['n_points']} |"
        )

    lines += [
        "",
        "## Universality summary (Pythia 6 sizes)",
        "",
        f"- α̅ (mean across 6 sizes): **{s['pythia_alpha_mean']:.4f}**" if s["pythia_alpha_mean"] else "- α̅: N/A",
        f"- σ_α: {s['pythia_alpha_std']:.4f}" if s["pythia_alpha_std"] else "- σ_α: N/A",
        f"- CV (σ_α/α̅): {s['pythia_alpha_cv']:.3f}" if s["pythia_alpha_cv"] else "- CV: N/A",
        f"- Verdict: **{s['universality_verdict']}**",
        "",
        "## Benchmarks",
        "",
        f"- Chinchilla compute exponent α_C ≈ {s['benchmark']['chinchilla_alpha_compute']}",
        f"- Chinchilla model-size exponent α_N ≈ {s['benchmark']['chinchilla_alpha_N']}",
        f"- Chinchilla token-axis exponent α_D ≈ {s['benchmark']['chinchilla_alpha_D']}",
        f"- Kaplan 2020 compute exponent α_C ≈ {s['benchmark']['kaplan_alpha_C']}",
        f"- Stevens psychophysics α ≈ {s['benchmark']['stevens_psychophysics_alpha']}",
        "",
    ]
    (HERE / "summary.md").write_text("\n".join(lines))


if __name__ == "__main__":
    result = main()
    print(json.dumps(result["summary"], indent=2))
