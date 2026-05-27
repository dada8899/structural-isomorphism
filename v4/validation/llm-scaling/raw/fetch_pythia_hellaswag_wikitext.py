#!/usr/bin/env python3
"""Fetch Pythia per-model leaderboard eval metrics for cross-eval α universality.

Background (SESSION-26 outstanding #7)
--------------------------------------
SESSION-25 cross-evaluator α-universality used 8 evaluators from
EleutherAI/pythia-v1/<size>/zero-shot/*.json (lambada_openai, piqa,
arc_easy, arc_challenge, winogrande, sciq, logiqa, wsc), pooled across
8 model sizes (14M..12B), giving CV(α)=2.50% — strong evaluator
universality.

The SESSION-26 outstanding asks for HellaSwag, WikiText-103, and
LAMBADA-standard. None of the three is in the EleutherAI/pythia-v1
zero-shot JSONs (probed manually). The honest options are:

  Path A (real-run via lm-eval-harness):
    - No lm-eval / torch / transformers installed
    - 24GB RAM Mac M4 Pro is enough for ≤2.8B but not 6.9B/12B
    - HellaSwag (~10k items × 4 endings) on 7 sizes ≈ several hours
    - WikiText-103 perplexity on 245k tokens × 7 sizes ≈ hours
    → Not feasible within 30-min budget. Reported as path-C status in
      summary, but Path B salvages HellaSwag.

  Path B (third-party scrape — what this script does):
    Open LLM Leaderboard v1 published full eval JSONs for Pythia
    non-deduped 7 sizes (70m / 160m / 410m / 1.3b / 2.7b / 6.7b / 12b)
    via `open-llm-leaderboard-old/details_EleutherAI__pythia-<size>`.
    Each contains:
       - HellaSwag (10-shot)          ← target eval #1
       - ARC-challenge (25-shot)      ← extra cross-eval source
       - Winogrande (5-shot)          ← extra cross-eval source
       - MMLU (57 subjects, 5-shot)   ← extra cross-eval source
       - TruthfulQA-MC (0-shot)       ← extra cross-eval source
       - DROP (3-shot)                ← extra cross-eval source
       - GSM8K (5-shot)               ← extra cross-eval source (mostly zero
                                       at small scale, may not fit a clean
                                       power-law — we record but treat as
                                       qualitative)

    What's NOT here:
       - WikiText-103 perplexity      ← Path C (honest negative)
       - LAMBADA-standard             ← Path C (honest negative;
                                       LAMBADA-openai still available
                                       from EleutherAI/pythia-v1)

Why this still answers the universality question
------------------------------------------------
The cross-eval α universality claim asks: *given a power-law in N
(model size), does α depend on the evaluator chosen?*. SESSION-25
showed CV(α)=2.50% across 8 zero-shot evals. Path-B adds 7 new
few-shot evals at distinct shot counts (0/5/10/25). Independent
universality test on a new evaluator family.

Caveat: leaderboard evals are few-shot, SESSION-25 was zero-shot.
A small α shift between regimes is normal. The test is whether
within the few-shot family α is again low-CV across evaluators.

Output
------
v4/validation/llm-scaling/raw/pythia_leaderboard_eval.csv
  columns: model, n_params, eval_name, num_shot, metric_name,
           metric_value, metric_stderr, n_samples, provenance
"""
from __future__ import annotations

import csv
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent

# Non-deduped Pythia v1 — same blood-line as SESSION-25 lambada data.
# Parameter counts from Biderman et al. 2023 Table 1.
SIZES: Dict[str, int] = {
    "70m":   70_426_624,
    "160m":  162_322_944,
    "410m":  405_334_016,
    "1.3b":  1_313_343_488,   # Pythia old-naming = "1b" new-naming, but
                              # leaderboard uses old "1.3b" non-deduped
                              # name (param count incl. embedding).
    "2.7b":  2_646_435_840,
    "6.7b":  6_650_785_280,
    "12b":   11_846_072_320,
}

LEADERBOARD_BASE = "https://huggingface.co/datasets/open-llm-leaderboard-old/details_EleutherAI__pythia-{size}"

# Tasks we extract. (task_key, num_shot, primary_metric).
# Primary metric chosen per leaderboard convention.
TASK_SPECS: List[Tuple[str, int, str]] = [
    ("harness|hellaswag|10",     10, "acc_norm"),
    ("harness|arc:challenge|25", 25, "acc_norm"),
    ("harness|winogrande|5",      5, "acc"),
    ("harness|truthfulqa:mc|0",   0, "mc2"),   # truthfulqa primary
    ("harness|drop|3",            3, "f1"),
    ("harness|gsm8k|5",           5, "acc"),
]

# MMLU is 57 subtasks; we average them by un-weighted mean of acc
# (matching leaderboard MMLU aggregate convention).
MMLU_PREFIX = "harness|hendrycksTest-"


def _fetch_results_url(size: str) -> str:
    """Find the actual results JSON file path (timestamp-suffixed)."""
    api = f"https://huggingface.co/api/datasets/open-llm-leaderboard-old/details_EleutherAI__pythia-{size}/tree/main"
    with urllib.request.urlopen(api, timeout=10) as r:
        d = json.load(r)
    for x in d:
        n = x.get("path", "")
        if n.startswith("results_") and n.endswith(".json"):
            return f"https://huggingface.co/datasets/open-llm-leaderboard-old/details_EleutherAI__pythia-{size}/resolve/main/{n}"
    raise RuntimeError(f"No results JSON found for pythia-{size}")


def _load_results(size: str) -> dict:
    url = _fetch_results_url(size)
    print(f"  GET {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "structural-isomorphism-validation/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        txt = r.read().decode("utf-8")
    # leaderboard JSONs contain literal NaN — invalid JSON; sanitize.
    txt = re.sub(r":\s*NaN", ": null", txt)
    txt = re.sub(r":\s*-Infinity", ": null", txt)
    txt = re.sub(r":\s*Infinity", ": null", txt)
    return json.loads(txt)


def _extract_mmlu_avg(results: dict) -> Tuple[float, float, int]:
    """Average MMLU 57-subject accuracy (un-weighted)."""
    accs, stderrs, n_subj = [], [], 0
    for k, v in results.items():
        if not k.startswith(MMLU_PREFIX):
            continue
        a = v.get("acc")
        s = v.get("acc_stderr")
        if a is None:
            continue
        accs.append(a)
        if s is not None:
            stderrs.append(s)
        n_subj += 1
    if not accs:
        return float("nan"), float("nan"), 0
    mean_acc = sum(accs) / len(accs)
    # Pool stderr via quadrature average (rough; subjects approx indep).
    if stderrs:
        pooled_se = (sum(s * s for s in stderrs) ** 0.5) / len(stderrs)
    else:
        pooled_se = float("nan")
    return mean_acc, pooled_se, n_subj


def main() -> int:
    rows: List[dict] = []
    for size, n_params in SIZES.items():
        print(f"[pythia-{size}] params={n_params:,}", file=sys.stderr)
        try:
            d = _load_results(size)
        except Exception as e:
            print(f"  ! FAILED: {e}", file=sys.stderr)
            continue
        results = d.get("results", {})

        # Standard tasks
        for task_key, shot, metric in TASK_SPECS:
            entry = results.get(task_key, {})
            if not entry:
                print(f"    {task_key}: MISSING", file=sys.stderr)
                continue
            val = entry.get(metric)
            stderr_key = f"{metric}_stderr"
            stderr_val = entry.get(stderr_key)
            if val is None:
                # try alternate metric names
                for alt in (f"{metric}_norm", "acc"):
                    if alt in entry and entry[alt] is not None:
                        val = entry[alt]
                        stderr_val = entry.get(f"{alt}_stderr")
                        metric = alt
                        break
            if val is None:
                print(f"    {task_key}: metric {metric} not found, available={list(entry.keys())}", file=sys.stderr)
                continue
            eval_name = task_key.split("|")[1]
            rows.append({
                "model": f"pythia-{size}",
                "n_params": n_params,
                "eval_name": eval_name,
                "num_shot": shot,
                "metric_name": metric,
                "metric_value": val,
                "metric_stderr": stderr_val if stderr_val is not None else "",
                "n_samples": "",  # leaderboard JSON does not always carry
                "provenance": "open-llm-leaderboard-old/details_EleutherAI__pythia-" + size,
            })
            print(f"    {eval_name}: {metric}={val:.4f}", file=sys.stderr)

        # MMLU aggregate
        mmlu_mean, mmlu_se, n_subj = _extract_mmlu_avg(results)
        if n_subj > 0:
            rows.append({
                "model": f"pythia-{size}",
                "n_params": n_params,
                "eval_name": "mmlu",
                "num_shot": 5,
                "metric_name": "acc_avg57",
                "metric_value": mmlu_mean,
                "metric_stderr": mmlu_se,
                "n_samples": n_subj,
                "provenance": "open-llm-leaderboard-old/details_EleutherAI__pythia-" + size + " (mean of 57 subjects)",
            })
            print(f"    mmlu(57-avg): acc={mmlu_mean:.4f}  n_subj={n_subj}", file=sys.stderr)

    out_csv = HERE / "pythia_leaderboard_eval.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "model", "n_params", "eval_name", "num_shot",
            "metric_name", "metric_value", "metric_stderr",
            "n_samples", "provenance",
        ])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"\nwrote {len(rows)} rows → {out_csv}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
