#!/usr/bin/env python3
"""Local-only robustness and independent double-coding tools for WTO data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import random
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WTO_DIR = ROOT / "v4/validation/schelling-credible-commitment"
DATA = WTO_DIR / "data/bown_wto_disputes.csv"
ANALYSIS = WTO_DIR / "run_validation_real_wto.py"
SCHEMA = "wto-independent-coding-v1"
CODING_FIELDS = {
    "schema_version", "task_id", "bundle_fingerprint", "coder_id", "ds_no",
    "sunk_cost_stage", "sunk_cost_s", "defendant_complied_24mo",
    "source_citations", "confidence", "note",
}

# Policy-level clusters prevent linked complaints from masquerading as
# independent disputes. Unlisted DS numbers remain singleton clusters.
POLICY_CLUSTERS = {
    "ec-hormones": {"26", "48"},
    "canada-dairy": {"103", "113"},
    "us-1916-act": {"136", "162"},
    "us-byrd-amendment": {"217", "234"},
    "us-softwood-lumber": {"257", "264", "277"},
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_rows(path: Path = DATA) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or len({row["ds_no"] for row in rows}) != len(rows):
        raise ValueError("WTO data must contain unique non-empty disputes")
    return rows


def cluster_id(ds_no: str) -> str:
    matches = [name for name, members in POLICY_CLUSTERS.items() if ds_no in members]
    if len(matches) > 1:
        raise ValueError(f"DS{ds_no} belongs to multiple policy clusters")
    return matches[0] if matches else f"ds-{ds_no}"


def _analysis_module():
    spec = importlib.util.spec_from_file_location("wto_real_analysis", ANALYSIS)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load WTO analysis")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def arrays(rows: list[dict[str, str]]) -> tuple[np.ndarray, np.ndarray]:
    return (
        np.asarray([float(row["sunk_cost_s"]) for row in rows]),
        np.asarray([int(row["defendant_complied_24mo"]) for row in rows]),
    )


def cluster_bootstrap(
    rows: list[dict[str, str]], *, samples: int = 2000, seed: int = 20260712
) -> dict[str, Any]:
    if samples < 100:
        raise ValueError("cluster bootstrap requires at least 100 samples")
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(cluster_id(row["ds_no"]), []).append(row)
    clusters = sorted(grouped)
    rng = np.random.default_rng(seed)
    slopes: list[float] = []
    module = _analysis_module()
    for _ in range(samples):
        selected = rng.integers(0, len(clusters), size=len(clusters))
        sample = [row for index in selected for row in grouped[clusters[index]]]
        s, y = arrays(sample)
        if len(np.unique(y)) < 2 or len(np.unique(s)) < 2:
            continue
        fit = module.probit_fit_mle(s, y)
        if fit["converged"] and np.isfinite(fit["k"]):
            slopes.append(float(fit["k"]))
    if len(slopes) < samples // 2:
        raise RuntimeError("too few valid cluster-bootstrap fits")
    values = np.asarray(slopes)
    return {
        "method": "policy-cluster-bootstrap",
        "seed": seed,
        "requested_samples": samples,
        "valid_samples": len(slopes),
        "n_rows": len(rows),
        "n_policy_clusters": len(clusters),
        "policy_clusters": {key: [row["ds_no"] for row in grouped[key]] for key in clusters},
        "k_ci95": [float(np.percentile(values, 2.5)), float(np.percentile(values, 97.5))],
        "k_median": float(np.median(values)),
        "fraction_k_below_zero": float(np.mean(values < 0)),
        "fraction_abs_k_above_20": float(np.mean(np.abs(values) > 20)),
        "separation_warning": bool(np.any(np.abs(values) > 20)),
    }


def leave_one_cluster_out(rows: list[dict[str, str]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        grouped.setdefault(cluster_id(row["ds_no"]), []).append(row)
    module = _analysis_module()
    fits = []
    for omitted in sorted(grouped):
        retained = [row for key, members in grouped.items() if key != omitted for row in members]
        s, y = arrays(retained)
        fit = module.probit_fit_mle(s, y)
        fits.append({
            "omitted_cluster": omitted,
            "omitted_ds": [row["ds_no"] for row in grouped[omitted]],
            "n_rows": len(retained),
            "k": float(fit["k"]),
            "converged": bool(fit["converged"]),
        })
    slopes = [item["k"] for item in fits if item["converged"]]
    return {
        "method": "leave-one-policy-cluster-out",
        "n_policy_clusters": len(grouped),
        "all_converged": len(slopes) == len(grouped),
        "all_k_below_zero": bool(slopes) and all(value < 0 for value in slopes),
        "k_range": [min(slopes), max(slopes)] if slopes else [None, None],
        "fits": fits,
    }


def robustness_report(rows: list[dict[str, str]], *, samples: int = 2000) -> dict[str, Any]:
    module = _analysis_module()
    s, y = arrays(rows)
    fit = module.probit_fit_mle(s, y)
    return {
        "schema_version": "wto-robustness-v1",
        "dataset_sha256": sha256(DATA),
        "scope": "sensitivity analysis; not independent outcome recoding or causal identification",
        "row_fit": {"n": len(rows), "k": fit["k"], "converged": fit["converged"]},
        "cluster_bootstrap": cluster_bootstrap(rows, samples=samples),
        "leave_one_cluster_out": leave_one_cluster_out(rows),
    }


def coding_bundle(rows: list[dict[str, str]]) -> dict[str, Any]:
    fingerprint = sha256(DATA)
    tasks = [{
        "task_id": "wto_" + hashlib.sha256(f"{fingerprint}\0{row['ds_no']}".encode()).hexdigest()[:20],
        "ds_no": row["ds_no"], "title": row["title"], "year_req": row["year_req"],
    } for row in rows]
    random.Random(int(fingerprint[:16], 16)).shuffle(tasks)
    return {
        "schema_version": "wto-independent-coding-bundle-v1",
        "bundle_fingerprint": fingerprint,
        "instructions": {
            "independence": "Do not inspect the existing coded CSV or another coder's export.",
            "sources": "Use Horn-Mavroidis source fields and WTO official case summaries; cite exact locator(s).",
            "unknowns": "Use null rather than inferring an outcome or score from another coded case.",
        },
        "task_count": len(tasks), "tasks": tasks,
    }


def validate_codings(
    records: list[dict[str, Any]], bundle: dict[str, Any], *, require_complete: bool = True
) -> list[dict[str, Any]]:
    tasks = {task["task_id"]: task for task in bundle["tasks"]}
    seen: set[str] = set()
    coders: set[str] = set()
    for row in records:
        if not isinstance(row, dict) or set(row) != CODING_FIELDS or row.get("schema_version") != SCHEMA:
            raise ValueError("coding schema mismatch")
        task = tasks.get(row.get("task_id"))
        if task is None or row["task_id"] in seen or row.get("ds_no") != task["ds_no"]:
            raise ValueError("unknown, duplicate, or mismatched coding task")
        if row.get("bundle_fingerprint") != bundle["bundle_fingerprint"]:
            raise ValueError("coding bundle fingerprint mismatch")
        coder = row.get("coder_id")
        if not isinstance(coder, str) or not coder.strip() or len(coder) > 80:
            raise ValueError("invalid coder_id")
        stage, score, outcome = row.get("sunk_cost_stage"), row.get("sunk_cost_s"), row.get("defendant_complied_24mo")
        if stage is not None and (not isinstance(stage, str) or not stage.strip()):
            raise ValueError("invalid sunk_cost_stage")
        if score is not None and (type(score) not in {int, float} or not 0 <= score <= 1):
            raise ValueError("invalid sunk_cost_s")
        if outcome is not None and outcome not in {0, 1}:
            raise ValueError("invalid defendant_complied_24mo")
        sources = row.get("source_citations")
        if not isinstance(sources, list) or not all(isinstance(value, str) and value.strip() for value in sources):
            raise ValueError("source_citations must be a string list")
        if any(value is not None for value in (stage, score, outcome)) and not sources:
            raise ValueError("non-null coding requires source citations")
        if row.get("confidence") not in {"low", "medium", "high"}:
            raise ValueError("invalid confidence")
        if not isinstance(row.get("note"), str) or len(row["note"]) > 2000:
            raise ValueError("invalid note")
        seen.add(row["task_id"]); coders.add(coder)
    if len(coders) > 1:
        raise ValueError("one coding file must contain exactly one coder_id")
    if require_complete and seen != set(tasks):
        raise ValueError(f"codings missing {len(set(tasks) - seen)} tasks")
    return sorted(records, key=lambda row: row["task_id"])


def coding_disagreements(first: list[dict[str, Any]], second: list[dict[str, Any]]) -> list[dict[str, Any]]:
    left = {row["task_id"]: row for row in first}
    right = {row["task_id"]: row for row in second}
    disputes = []
    for task_id in sorted(set(left) & set(right)):
        fields = [name for name in ("sunk_cost_stage", "sunk_cost_s", "defendant_complied_24mo") if left[task_id][name] != right[task_id][name]]
        if fields:
            disputes.append({"task_id": task_id, "ds_no": left[task_id]["ds_no"], "disputed_fields": fields})
    return disputes


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    robust = sub.add_parser("robustness")
    robust.add_argument("--samples", type=int, default=2000)
    robust.add_argument("--output", type=Path, required=True)
    build = sub.add_parser("build-coding-bundle")
    build.add_argument("--output", type=Path, required=True)
    validate = sub.add_parser("validate-coding")
    validate.add_argument("--bundle", type=Path, required=True)
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--allow-partial", action="store_true")
    compare = sub.add_parser("compare-codings")
    compare.add_argument("--bundle", type=Path, required=True)
    compare.add_argument("--input", type=Path, nargs=2, required=True)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = load_rows()
    if args.command == "robustness":
        write_json(args.output, robustness_report(rows, samples=args.samples))
    elif args.command == "build-coding-bundle":
        write_json(args.output, coding_bundle(rows))
    else:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        if bundle != coding_bundle(rows):
            raise ValueError("coding bundle drift")
        if args.command == "validate-coding":
            values = validate_codings(read_jsonl(args.input), bundle, require_complete=not args.allow_partial)
            print(f"valid: {len(values)} independent codings")
        else:
            first = validate_codings(read_jsonl(args.input[0]), bundle)
            second = validate_codings(read_jsonl(args.input[1]), bundle)
            if first[0]["coder_id"] == second[0]["coder_id"]:
                raise ValueError("independent coding files require distinct coder_id values")
            disputes = coding_disagreements(first, second)
            write_json(args.output, {"schema_version": "wto-coding-comparison-v1", "disputes": disputes})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
