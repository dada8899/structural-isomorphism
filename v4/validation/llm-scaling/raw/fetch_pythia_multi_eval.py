#!/usr/bin/env python3
"""Fetch Pythia per-checkpoint *multi-evaluator* metrics from GitHub.

Background
----------
SESSION-25 cross-evaluator α-universality follow-up. The original
`fetch_pythia_lambada.py` pulls only `lambada_openai.ppl` from each
`evals/pythia-v1/<size>/zero-shot/*.json`. Each JSON also contains a
bunch of other evaluators (PIQA / ARC / WinoGrande / SciQ / LogiQA /
WSC) which can stress-test the cross-eval portion of the universality
claim.

What about LAMBADA-standard / WikiText-103 / HellaSwag?
-------------------------------------------------------
The SESSION-25 brief asked for LAMBADA-standard, WikiText-103, and
HellaSwag in particular. **These three evaluators are NOT present in
the EleutherAI/pythia-v1 zero-shot JSONs.** Probed manually
2026-05-25: only lambada_openai (with ppl) is present from the
LAMBADA family; wikitext / hellaswag are entirely absent. The brief's
preferred eval list was speculative — what's actually available is:

  Perplexity (1 evaluator):
    lambada_openai  →  ppl, acc

  Accuracy (7 evaluators):
    piqa          →  acc, acc_norm
    arc_easy      →  acc, acc_norm
    arc_challenge →  acc, acc_norm
    winogrande    →  acc
    sciq          →  acc, acc_norm
    logiqa        →  acc, acc_norm
    wsc           →  acc

We use what is actually present. Brief's verdict ladder still applies
to the question "is α universal across evaluator choice".

Output
------
v4/validation/llm-scaling/raw/pythia_multi_eval_real.csv
  columns: model, n_params, step, tokens, compute_flops,
           eval_name, metric_name, metric_value, metric_stderr,
           provenance
"""
from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path
import urllib.request

HERE = Path(__file__).resolve().parent

GITHUB_RAW = "https://raw.githubusercontent.com/EleutherAI/pythia/main/evals/pythia-v1"
GITHUB_API = "https://api.github.com/repos/EleutherAI/pythia/contents/evals/pythia-v1"

# Standard Pythia v1 sizes (all 8) + parameter counts (Biderman 2023 Table 1).
# NOTE: the GitHub repo path is `pythia-<size>` (e.g. pythia-70m), unlike
# the original fetch_pythia_lambada.py which uses bare `<size>` and would
# 404 — that script presumably ran against an older repo layout or used
# a different path scheme. We use the actually-working `pythia-<size>` form.
SIZES = {
    "pythia-70m":     (70_426_624,    "70m"),
    "pythia-160m":    (162_322_944,   "160m"),
    "pythia-410m":    (405_334_016,   "410m"),
    # pythia-1b standard has no eval dir on GitHub (only variants do); use
    # pythia-1b-bf16 as proxy — same model, same params, only bf16 precision
    # difference. Provenance flag tracks the variant.
    "pythia-1b-bf16": (1_011_781_632, "1b"),
    "pythia-1.4b":    (1_414_647_808, "1.4b"),
    "pythia-2.8b":    (2_775_208_960, "2.8b"),
    "pythia-6.9b":    (6_857_302_016, "6.9b"),
    "pythia-12b":     (11_846_072_320, "12b"),
}

BATCH_SIZE_DEFAULT = 1024
SEQ_LEN = 2048
TOKENS_PER_STEP_DEFAULT = BATCH_SIZE_DEFAULT * SEQ_LEN  # 2.1e6

# Evaluators to extract. Each entry: eval_name -> list of metric keys to
# pull from results[eval_name]. We keep the primary metric only (no stderr
# columns explosion) plus its stderr for downstream uncertainty work.
EVAL_METRICS = {
    "lambada_openai":  ["ppl", "acc"],
    "piqa":            ["acc", "acc_norm"],
    "arc_easy":        ["acc", "acc_norm"],
    "arc_challenge":   ["acc", "acc_norm"],
    "winogrande":      ["acc"],
    "sciq":            ["acc", "acc_norm"],
    "logiqa":          ["acc", "acc_norm"],
    "wsc":             ["acc"],
}


def list_checkpoint_files(model_dir: str) -> list[dict]:
    url = f"{GITHUB_API}/{model_dir}/zero-shot"
    req = urllib.request.Request(url, headers={"User-Agent": "structural-isomorphism-validation/0.3"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        items = json.load(resp)
    return [it for it in items if it.get("name", "").endswith(".json")]


def parse_step_from_filename(filename: str) -> int | None:
    if not filename.endswith(".json"):
        return None
    base = filename[:-5]
    idx = base.rfind("_step")
    if idx < 0:
        return None
    try:
        return int(base[idx + 5:])
    except ValueError:
        return None


def fetch_one(item: dict) -> dict | None:
    """Fetch one checkpoint JSON; return {step, results_dict} or None."""
    download_url = item.get("download_url")
    filename = item.get("name", "")
    if not download_url:
        return None
    req = urllib.request.Request(download_url, headers={"User-Agent": "structural-isomorphism-validation/0.3"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:  # noqa: BLE001
        print(f"  WARN: fetch failed {filename}: {e}", file=sys.stderr)
        return None
    step = parse_step_from_filename(filename)
    if step is None:
        return None
    return {"step": step, "results": data.get("results", {})}


def main() -> None:
    out_path = HERE / "pythia_multi_eval_real.csv"
    rows = []
    for model_dir, (n_params, short) in SIZES.items():
        print(f"\n[{model_dir}] listing checkpoints...", file=sys.stderr)
        try:
            items = list_checkpoint_files(model_dir)
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: list failed: {e}", file=sys.stderr)
            continue
        print(f"  found {len(items)} checkpoint files", file=sys.stderr)
        per_size_rows = 0
        for item in items:
            rec = fetch_one(item)
            if rec is None:
                continue
            step = rec["step"]
            results = rec["results"]
            tokens = step * TOKENS_PER_STEP_DEFAULT
            compute_flops = 6.0 * n_params * tokens
            canonical_model = "pythia-1b" if model_dir == "pythia-1b-bf16" else model_dir
            provenance = "REAL_MULTI_EVAL_FROM_GITHUB"
            if model_dir == "pythia-1b-bf16":
                provenance = "REAL_MULTI_EVAL_FROM_GITHUB_BF16_PROXY"
            for eval_name, metric_keys in EVAL_METRICS.items():
                r = results.get(eval_name)
                if not r:
                    continue
                for metric_name in metric_keys:
                    if metric_name not in r:
                        continue
                    value = r[metric_name]
                    stderr_key = f"{metric_name}_stderr"
                    stderr = r.get(stderr_key, float("nan"))
                    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                        continue
                    rows.append({
                        "model": canonical_model,
                        "n_params": n_params,
                        "step": step,
                        "tokens": tokens,
                        "compute_flops": compute_flops,
                        "eval_name": eval_name,
                        "metric_name": metric_name,
                        "metric_value": float(value),
                        "metric_stderr": float(stderr) if isinstance(stderr, (int, float)) else float("nan"),
                        "provenance": provenance,
                    })
                    per_size_rows += 1
        print(f"  [{model_dir}] {per_size_rows} (model, eval, metric, step) rows", file=sys.stderr)

    if not rows:
        sys.exit("ERROR: no rows fetched")

    rows.sort(key=lambda r: (r["model"], r["eval_name"], r["metric_name"], r["step"]))
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} rows to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
