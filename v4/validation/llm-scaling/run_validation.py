"""LLM scaling-law learning-curve validation runner.

Fits the Chinchilla / Kaplan power-law L(C) = A·C^(-alpha) + L_inf on:
    - 7 observed Pythia model sizes (per-size checkpoint trajectories vs compute)
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

import argparse
import csv
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import scipy

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parents[2]  # v4/validation/llm-scaling → project root
MODULE_PATH = (
    PROJECT_ROOT / "packages" / "soc-pipeline" / "src" / "soc_pipeline" / "learning_curve.py"
)
RAW_DIR = HERE / "raw"
GENERATOR_REQUIREMENTS = HERE / "requirements-generator.txt"
GENERATOR_PYTHON = (3, 11)
CANONICAL_SIGNIFICANT_DIGITS = 12
COMPARISON_REL_TOL = 1e-4
COMPARISON_ABS_TOL = 1e-10
GENERATOR_PACKAGES = frozenset(
    {
        "contourpy",
        "cycler",
        "fonttools",
        "kiwisolver",
        "matplotlib",
        "numpy",
        "packaging",
        "pandas",
        "pillow",
        "pyparsing",
        "python-dateutil",
        "scipy",
        "six",
    }
)


def _generator_pins() -> dict[str, str]:
    pins: dict[str, str] = {}
    for raw_line in GENERATOR_REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.fullmatch(r"([a-z0-9][a-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+-]*)", line)
        if match is None:
            raise RuntimeError(f"non-exact generator requirement: {line!r}")
        name, version = match.groups()
        if name in pins:
            raise RuntimeError(f"duplicate generator requirement: {name}")
        pins[name] = version
    if set(pins) != GENERATOR_PACKAGES:
        missing = sorted(GENERATOR_PACKAGES - set(pins))
        extra = sorted(set(pins) - GENERATOR_PACKAGES)
        raise RuntimeError(
            "generator requirements must exactly pin the complete scientific "
            f"rendering closure: missing={missing!r} extra={extra!r}"
        )
    return pins


def _assert_generator_environment() -> dict[str, str]:
    pins = _generator_pins()
    actual = {name: importlib.metadata.version(name) for name in pins}
    if sys.version_info[:2] != GENERATOR_PYTHON:
        raise RuntimeError(
            "LLM scaling artifacts require Python "
            f"{GENERATOR_PYTHON[0]}.{GENERATOR_PYTHON[1]}"
        )
    if actual != pins:
        raise RuntimeError(
            f"LLM scaling generator dependency mismatch: expected={pins!r} actual={actual!r}"
        )
    _assert_canonical_data_source()
    return pins


def _assert_canonical_data_source() -> None:
    if os.environ.get("PYTHIA_DATA", "real") != "real":
        raise RuntimeError("canonical LLM scaling artifacts require PYTHIA_DATA=real")
    canonical_input = RAW_DIR / "pythia_checkpoints_combined.csv"
    if not canonical_input.is_file():
        raise RuntimeError(f"canonical LLM scaling input is missing: {canonical_input}")


def generator_environment_matches() -> bool:
    try:
        _assert_generator_environment()
    except RuntimeError:
        return False
    return True


def _canonicalize(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("LLM scaling artifact contains a non-finite float")
        rounded = float(format(value, f".{CANONICAL_SIGNIFICANT_DIGITS}g"))
        return 0.0 if rounded == 0.0 else rounded
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonicalize(item) for key, item in value.items()}
    return value


def assert_artifact_equivalent(expected, observed, *, path: str = "$") -> None:
    if isinstance(expected, bool) or isinstance(observed, bool):
        if expected is not observed:
            raise ValueError(f"artifact mismatch at {path}")
        return
    if isinstance(expected, float) and isinstance(observed, float):
        if not math.isclose(
            expected,
            observed,
            rel_tol=COMPARISON_REL_TOL,
            abs_tol=COMPARISON_ABS_TOL,
        ):
            raise ValueError(f"numeric artifact mismatch at {path}")
        return
    if isinstance(expected, dict) and isinstance(observed, dict):
        if expected.keys() != observed.keys():
            raise ValueError(f"artifact keys mismatch at {path}")
        for key in expected:
            assert_artifact_equivalent(
                expected[key], observed[key], path=f"{path}.{key}"
            )
        return
    if isinstance(expected, list) and isinstance(observed, list):
        if len(expected) != len(observed):
            raise ValueError(f"artifact length mismatch at {path}")
        for index, (expected_item, observed_item) in enumerate(
            zip(expected, observed, strict=True)
        ):
            assert_artifact_equivalent(
                expected_item, observed_item, path=f"{path}[{index}]"
            )
        return
    if type(expected) is not type(observed) or expected != observed:
        raise ValueError(f"artifact mismatch at {path}")


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


def _classify_fit(fit: dict, *, pythia: bool) -> tuple[str, str | None]:
    """Separate raw optimizer output from inference eligibility.

    Narrow-tail captures can be descriptive records but do not identify a
    learning-curve exponent. Boundary and negative-R² fits are rejected
    rather than silently entering cross-size universality statistics.
    """
    if fit.get("error"):
        return "rejected", f"optimizer error: {fit['error']}"
    required = ("alpha", "A", "L_inf", "R2")
    if any(
        type(fit.get(field)) not in {int, float}
        or not np.isfinite(float(fit[field]))
        for field in required
    ):
        return "rejected", "non-finite or missing fitted parameter"
    if not 0.0 < float(fit["alpha"]) < 1.0:
        return "rejected", "alpha is outside the open scientific sanity range (0, 1)"
    if not 0.0 <= float(fit["L_inf"]) < 10.0:
        return "rejected", "L_inf is outside the scientific sanity range [0, 10)"
    provenance = str(fit.get("provenance", ""))
    if pythia and "REAL_TAIL_NARROW" in provenance:
        if float(fit["R2"]) < 0.0:
            return "rejected", "narrow-tail fit has negative R-squared"
        return (
            "descriptive_only",
            "narrow compute range is not eligible for exponent inference",
        )
    if float(fit["R2"]) <= 0.9:
        return "rejected", "fit R-squared does not exceed 0.9"
    return "fit_quality_eligible", None


def _annotate_fit(fit: dict, *, pythia: bool) -> None:
    status, reason = _classify_fit(fit, pythia=pythia)
    fit["fit_status"] = status
    fit["exclusion_reason"] = reason


def main(*, write: bool = True) -> dict:
    if write:
        _assert_generator_environment()
    lc = _load_learning_curve()

    data_kind = os.environ.get("PYTHIA_DATA", "real")
    if data_kind not in {"real", "synthetic"}:
        raise ValueError("PYTHIA_DATA must be exactly 'real' or 'synthetic'")
    if data_kind == "real":
        pythia_csv = RAW_DIR / "pythia_checkpoints_combined.csv"
        if not pythia_csv.exists():
            raise FileNotFoundError(f"required real input is missing: {pythia_csv}")
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
        _annotate_fit(d, pythia=True)
        fits[model] = d
        provenance[model] = prov

    # --- Kaplan 2020 ---
    kap_rows = _read_csv(RAW_DIR / "kaplan2020_compute.csv")
    C, L = _flat_series(kap_rows)
    r = lc.fit_learning_curve(C, L, name="kaplan2020-gpt", L_inf_bounds=(0.0, 0.5))
    d = r.to_dict()
    d["provenance"] = "LITERATURE_ANCHORED (Kaplan 2020 eq. 1.5)"
    _annotate_fit(d, pythia=False)
    fits["kaplan2020-gpt"] = d

    # --- Hoffmann 2022 (Chinchilla) ---
    hof_rows = _read_csv(RAW_DIR / "hoffmann2022_compute.csv")
    C, L = _flat_series(hof_rows)
    r = lc.fit_learning_curve(C, L, name="hoffmann2022-chinchilla")
    d = r.to_dict()
    d["provenance"] = "LITERATURE_ANCHORED (Hoffmann 2022 Table 4 Approach 3)"
    _annotate_fit(d, pythia=False)
    fits["hoffmann2022-chinchilla"] = d

    # --- Summary stats across Pythia sizes ---
    # Fit-quality eligibility is a numerical diagnostic only. It deliberately
    # includes synthetic fitter checks, so scientific inference remains a
    # separate REAL_FULL-only subset below.
    fit_quality_eligible = [
        m for m in pythia if fits[m]["fit_status"] == "fit_quality_eligible"
    ]
    pythia_alphas_eligible = [fits[m]["alpha"] for m in fit_quality_eligible]
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

    summary_eligible = _stats(pythia_alphas_eligible)
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
        "pythia_n_fit_quality_eligible": len(fit_quality_eligible),
        "provenance_per_model": provenance,
        "fit_status_per_model": {model: fits[model]["fit_status"] for model in pythia},
        "exclusions_from_fit_spread": {
            model: fits[model]["exclusion_reason"]
            for model in pythia
            if fits[model]["fit_status"] != "fit_quality_eligible"
        },
        "alpha_fit_quality_eligible_sizes": summary_eligible,
        "alpha_real_wide_only": summary_real_wide,
        "fit_spread_diagnostic_fit_quality_eligible": _spread_diagnostic(summary_eligible),
        "fit_spread_diagnostic_real_wide": _spread_diagnostic(summary_real_wide),
        "scientific_conclusion": (
            "INSUFFICIENT_REAL_WIDE_SERIES_FOR_UNIVERSALITY_INFERENCE"
            if summary_real_wide["n"] < 3
            else "FIT_SPREAD_DIAGNOSTIC_ONLY"
        ),
        "benchmark": benchmark,
    }

    out = {
        "schema_version": "1.3",
        "validation": "llm-scaling",
        "date": "2026-05-25",
        "module": "soc_pipeline.learning_curve.fit_learning_curve",
        "generation_contract": {
            "python": f"{GENERATOR_PYTHON[0]}.{GENERATOR_PYTHON[1]}",
            "requirements": _generator_pins(),
            "float_significant_digits": CANONICAL_SIGNIFICANT_DIGITS,
            "comparison_rel_tol": COMPARISON_REL_TOL,
            "comparison_abs_tol": COMPARISON_ABS_TOL,
            "canonical_data_kind": "real",
            "canonical_input": (
                "v4/validation/llm-scaling/raw/pythia_checkpoints_combined.csv"
            ),
        },
        "fits": fits,
        "summary": summary,
    }
    out = _canonicalize(out)

    if write:
        (HERE / "results.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8"
        )
        _write_summary_md(out)
    return out


def _spread_diagnostic(stats):
    """Describe fitted-exponent spread without upgrading it to universality."""
    cv = stats.get("cv")
    if cv is None or stats.get("n", 0) < 2:
        return "UNKNOWN"
    if cv < 0.1:
        return "NARROW_SPREAD"
    if cv < 0.2:
        return "MODERATE_SPREAD"
    return "BROAD_SPREAD"


def _render_summary_md(out: dict) -> str:
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
        "| Model | α | α_se | L∞ | A | R² | n | status | provenance |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, fit in out["fits"].items():
        prov = fit.get("provenance", "?")
        if fit.get("error"):
            lines.append(
                f"| {name} | — | — | — | — | — | {fit.get('n_points', 0)} | rejected | {prov} (err: {fit['error']}) |"
            )
            continue
        lines.append(
            f"| {name} | {fit['alpha']:.4f} | "
            f"{fit['alpha_se']:.4f} | "
            f"{fit['L_inf']:.4f} | "
            f"{fit['A']:.3g} | "
            f"{fit['R2']:.4f} | "
            f"{fit['n_points']} | {fit['fit_status']} | {prov} |"
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

    lines += [
        "",
        "## Fit-spread diagnostics (not universality evidence)",
        "",
        f"**Scientific conclusion.** `{s['scientific_conclusion']}`",
        "",
    ]
    lines += _stat_block(
        "Fit-quality-eligible sizes (mixed real/synthetic; diagnostic only)",
        s["alpha_fit_quality_eligible_sizes"],
        s["fit_spread_diagnostic_fit_quality_eligible"],
    )
    lines += _stat_block("REAL wide-range sizes only",
                          s["alpha_real_wide_only"], s["fit_spread_diagnostic_real_wide"])

    lines += ["### Excluded from exponent inference", ""]
    for model, reason in s["exclusions_from_fit_spread"].items():
        lines.append(f"- `{model}`: {reason}")
    lines.append("")

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

    return "\n".join(lines)


def _write_summary_md(out: dict) -> None:
    (HERE / "summary.md").write_text(_render_summary_md(out), encoding="utf-8")


def _check_committed_artifacts() -> dict:
    _assert_generator_environment()
    generated = main(write=False)
    expected_json = json.dumps(generated, indent=2) + "\n"
    expected_summary = _render_summary_md(generated)
    if (HERE / "results.json").read_text(encoding="utf-8") != expected_json:
        raise RuntimeError("results.json differs from the locked generator output")
    if (HERE / "summary.md").read_text(encoding="utf-8") != expected_summary:
        raise RuntimeError("summary.md differs from the locked generator output")
    return generated


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="write canonical artifacts")
    mode.add_argument("--check", action="store_true", help="check canonical artifacts")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    result = _check_committed_artifacts() if args.check else main(write=True)
    print(json.dumps(result["summary"], indent=2))
