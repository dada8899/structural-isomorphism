"""LLM scaling-law learning-curve validation runner.

Fits the Chinchilla / Kaplan power-law L(C) = A·C^(-alpha) + L_inf on:
    - 6 Pythia model sizes (per-size checkpoint trajectories vs compute)
    - Kaplan 2020 GPT-family compute frontier
    - Hoffmann 2022 Chinchilla compute frontier

Data source priority (set by PYTHIA_DATA env var):
    "real"     -> pythia_checkpoints_combined.csv (real wandb where available,
                  synthetic fallback for 160M / 1B / 6.9B)  [DEFAULT]
    "synthetic"-> pythia_checkpoints.csv (original literature-anchored)

Outputs:
    results.json  — per-series alpha, A, L_inf, R^2, residual_rms, n_points + provenance
    summary.md    — human-readable comparison table + Chinchilla benchmark

Run:
    python v4/validation/llm-scaling/run_validation.py
"""
from __future__ import annotations

import csv
import importlib.util
import json
import os
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
    """Side-load learning_curve.py without going through soc_pipeline/__init__."""
    spec = importlib.util.spec_from_file_location("soc_pipeline_learning_curve", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["soc_pipeline_learning_curve"] = mod
    spec.loader.exec_module(mod)
    return mod


def _read_csv(path: Path) -> list[dict]:
    with path.open() as f:
        return list(csv.DictReader(f))


def _pythia_series(rows: list[dict]) -> dict[str, tuple[np.ndarray, np.ndarray, str]]:
    """Bucket Pythia rows by model → (compute_flops, loss, provenance) arrays."""
    by_model: dict[str, list[tuple[float, float, str]]] = defaultdict(list)
    for r in rows:
        prov = r.get("provenance", "SYNTHETIC")
        by_model[r["model"]].append((float(r["compute_flops"]), float(r["loss"]), prov))
    out = {}
    for m, triples in by_model.items():
        triples.sort()
        C = np.array([t[0] for t in triples])
        L = np.array([t[1] for t in triples])
        # All rows in a model share the same provenance
        prov = triples[0][2] if triples else "UNKNOWN"
        out[m] = (C, L, prov)
    return out


def _flat_series(rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    C = np.array([float(r["compute_flops"]) for r in rows])
    L = np.array([float(r["loss"]) for r in rows])
    order = np.argsort(C)
    return C[order], L[order]


def main() -> dict:
    lc = _load_learning_curve()

    data_kind = os.environ.get("PYTHIA_DATA", "real")
    if data_kind == "real":
        pythia_csv = RAW_DIR / "pythia_checkpoints_combined.csv"
        if not pythia_csv.exists():
            print("WARN: combined CSV not present; falling back to synthetic", file=sys.stderr)
            pythia_csv = RAW_DIR / "pythia_checkpoints.csv"
    else:
        pythia_csv = RAW_DIR / "pythia_checkpoints.csv"

    pythia_rows = _read_csv(pythia_csv)
    pythia = _pythia_series(pythia_rows)

    fits = {}
    provenance = {}
    for model in sorted(pythia.keys()):
        C, L, prov = pythia[model]
        r = lc.fit_learning_curve(C, L, name=model)
        d = r.to_dict()
        d["provenance"] = prov
        fits[model] = d
        provenance[model] = prov

    # --- Kaplan 2020 ---
    kap_rows = _read_csv(RAW_DIR / "kaplan2020_compute.csv")
    C, L = _flat_series(kap_rows)
    r = lc.fit_learning_curve(C, L, name="kaplan2020-gpt", L_inf_bounds=(0.0, 0.5))
    d = r.to_dict()
    d["provenance"] = "LITERATURE_ANCHORED (Kaplan 2020 eq. 1.5)"
    fits["kaplan2020-gpt"] = d

    # --- Hoffmann 2022 (Chinchilla) ---
    hof_rows = _read_csv(RAW_DIR / "hoffmann2022_compute.csv")
    C, L = _flat_series(hof_rows)
    r = lc.fit_learning_curve(C, L, name="hoffmann2022-chinchilla")
    d = r.to_dict()
    d["provenance"] = "LITERATURE_ANCHORED (Hoffmann 2022 Table 4 Approach 3)"
    fits["hoffmann2022-chinchilla"] = d

    # --- Summary stats across Pythia sizes ---
    # Stratified: ALL sizes vs only REAL_FULL / REAL_PARTIAL_WIDE (excluding narrow-tail)
    pythia_alphas_all = [fits[m]["alpha"] for m in pythia.keys()
                          if fits[m].get("alpha") is not None]
    real_full = [m for m in pythia.keys()
                  if fits[m].get("provenance", "").startswith("REAL_FULL")
                  or fits[m].get("provenance", "").startswith("REAL_PARTIAL_WIDE")]
    pythia_alphas_real_wide = [fits[m]["alpha"] for m in real_full
                                if fits[m].get("alpha") is not None]

    def _stats(arr):
        if not arr:
            return {"n": 0, "mean": None, "std": None, "cv": None}
        a = float(np.mean(arr))
        s = float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0
        return {"n": len(arr), "mean": a, "std": s,
                "cv": (s / a if a else None)}

    summary_all = _stats(pythia_alphas_all)
    summary_real_wide = _stats(pythia_alphas_real_wide)

    benchmark = {
        "chinchilla_alpha_compute": 0.155,
        "chinchilla_alpha_N": 0.34,
        "chinchilla_alpha_D": 0.28,
        "kaplan_alpha_C": 0.050,
        "stevens_psychophysics_alpha": 0.50,
    }

    summary = {
        "data_kind": data_kind,
        "pythia_csv": str(pythia_csv.relative_to(PROJECT_ROOT)),
        "pythia_n_sizes": len(pythia),
        "provenance_per_model": provenance,
        "alpha_all_sizes": summary_all,
        "alpha_real_wide_only": summary_real_wide,
        "universality_verdict_all": _universality_verdict(summary_all["cv"]),
        "universality_verdict_real_wide": _universality_verdict(summary_real_wide["cv"]),
        "benchmark": benchmark,
    }

    out = {
        "schema_version": "1.1",
        "validation": "llm-scaling",
        "date": "2026-05-25",
        "module": "soc_pipeline.learning_curve.fit_learning_curve",
        "fits": fits,
        "summary": summary,
    }

    (HERE / "results.json").write_text(json.dumps(out, indent=2))
    _write_summary_md(out)
    return out


def _universality_verdict(cv):
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
        f"**Pythia CSV.** `{s['pythia_csv']}`",
        f"**Pythia sizes fitted.** {s['pythia_n_sizes']}",
        "",
        "## Per-series fits  (L(C) = A · C^(-α) + L∞)",
        "",
        "| Model | α | α_se | L∞ | A | R² | n | provenance |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for name, fit in out["fits"].items():
        prov = fit.get("provenance", "?")
        if fit.get("error"):
            lines.append(
                f"| {name} | — | — | — | — | — | {fit.get('n_points', 0)} | {prov} (err: {fit['error']}) |"
            )
            continue
        lines.append(
            f"| {name} | {fit['alpha']:.4f} | "
            f"{fit['alpha_se']:.4f} | "
            f"{fit['L_inf']:.4f} | "
            f"{fit['A']:.3g} | "
            f"{fit['R2']:.4f} | "
            f"{fit['n_points']} | {prov} |"
        )

    def _stat_block(label, st, verdict):
        out = [f"### {label}", ""]
        if st["n"] == 0:
            out += ["(no qualifying sizes)", ""]
            return out
        out += [
            f"- n sizes: {st['n']}",
            f"- α̅: **{st['mean']:.4f}**" if st["mean"] is not None else "- α̅: N/A",
            f"- σ_α: {st['std']:.4f}" if st["std"] is not None else "- σ_α: N/A",
            f"- CV: {st['cv']:.3f}" if st["cv"] is not None else "- CV: N/A",
            f"- Verdict: **{verdict}**",
            "",
        ]
        return out

    lines += ["", "## Universality summary (Pythia)", ""]
    lines += _stat_block("All 6 sizes", s["alpha_all_sizes"], s["universality_verdict_all"])
    lines += _stat_block("REAL wide-range sizes only",
                          s["alpha_real_wide_only"], s["universality_verdict_real_wide"])

    lines += [
        "## Benchmarks",
        "",
        f"- Chinchilla compute exponent α_C ≈ {s['benchmark']['chinchilla_alpha_compute']}",
        f"- Chinchilla model-size exponent α_N ≈ {s['benchmark']['chinchilla_alpha_N']}",
        f"- Chinchilla token-axis exponent α_D ≈ {s['benchmark']['chinchilla_alpha_D']}",
        f"- Kaplan 2020 compute exponent α_C ≈ {s['benchmark']['kaplan_alpha_C']}",
        f"- Stevens psychophysics α ≈ {s['benchmark']['stevens_psychophysics_alpha']}",
        "",
        "## Provenance per model",
        "",
    ]
    for m, p in s["provenance_per_model"].items():
        lines.append(f"- `{m}`: {p}")
    lines.append("")

    (HERE / "summary.md").write_text("\n".join(lines))


if __name__ == "__main__":
    result = main()
    print(json.dumps(result["summary"], indent=2))
