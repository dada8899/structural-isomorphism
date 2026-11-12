#!/usr/bin/env python3
"""Fetch real Pythia LAMBADA-OpenAI perplexity per checkpoint from GitHub.

Background
----------
The wandb-based fetcher (`fetch_pythia_wandb.py`) recovers training-loss
trajectories for 5 of the 8 Pythia v1 sizes. The remaining 3 (160m, 1b,
6.9b) have no matching public wandb runs — exhaustive search by the
original author confirmed.

This alternative source uses the EleutherAI/pythia GitHub repo's
`evals/pythia-v1/<size>/zero-shot/*.json` files. These are
lm-evaluation-harness benchmark outputs computed per-checkpoint for all
8 sizes × 27 standard step values. Each file has `results.lambada_openai.ppl`
— LAMBADA-OpenAI perplexity, a strong language-modeling signal that
serves as a real-data proxy for Pile val loss (log-ppl ≈ cross-entropy loss
on the LAMBADA evaluation set).

Coverage closes the 3-gap problem: all 8 sizes get real per-checkpoint
data, no more SYNTHETIC fallback for any size.

Output
------
v4/validation/llm-scaling/raw/pythia_lambada_real.csv
  columns: model, n_params, step, tokens, compute_flops, lambada_ppl,
           lambada_log_ppl, lambada_acc, lambada_acc_stderr, provenance

Compute recipe (per existing pipeline)
  tokens = step · batch_size · seq_len  (1024 · 2048 = 2.1e6 tokens/step
                                          for standard 1MtokBS sizes;
                                          0.5MtokBS variants halved)
  compute = 6 · n_params · tokens
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

# Standard Pythia v1 sizes (all 8) + parameter counts (Biderman 2023 Table 1)
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


def list_checkpoint_files(model: str) -> list[dict]:
    """List the per-checkpoint JSON files for a given size; return full
    API items including download_url so we don't have to guess URL formats."""
    url = f"{GITHUB_API}/{model}/zero-shot"
    req = urllib.request.Request(url, headers={"User-Agent": "structural-isomorphism-validation/0.2"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        items = json.load(resp)
    return [it for it in items if it.get("name", "").endswith(".json")]


def parse_step_from_filename(filename: str) -> int | None:
    """Parse step from any of: '160m_step103000.json' /
    '1b-bf16-5shot_step103000.json' / '70m-0.25MtokBS_step1000.json'.
    Look for '_step<N>.json' suffix."""
    if not filename.endswith(".json"):
        return None
    base = filename[:-5]  # strip .json
    # Find rightmost "_step"
    idx = base.rfind("_step")
    if idx < 0:
        return None
    try:
        return int(base[idx + 5:])
    except ValueError:
        return None


def fetch_lambada(item: dict) -> dict | None:
    """Fetch one JSON file via the API-provided download_url, return
    {step, ppl, acc, acc_stderr} or None."""
    download_url = item.get("download_url")
    filename = item.get("name", "")
    if not download_url:
        # Construct from html_url as fallback
        html_url = item.get("html_url", "")
        download_url = html_url.replace("github.com", "github.com").replace("/blob/", "/raw/")
    req = urllib.request.Request(download_url, headers={"User-Agent": "structural-isomorphism-validation/0.2"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception as e:  # noqa: BLE001
        # Fallback: try /raw/main/ URL format (works for some submodule files)
        alt_url = f"https://github.com/EleutherAI/pythia/raw/main/{item['path']}"
        try:
            req = urllib.request.Request(alt_url, headers={"User-Agent": "structural-isomorphism-validation/0.2"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.load(resp)
        except Exception as e2:  # noqa: BLE001
            print(f"  WARN: fetch failed {filename}: {e} / {e2}", file=sys.stderr)
            return None
    step = parse_step_from_filename(filename)
    if step is None:
        return None
    r = data.get("results", {}).get("lambada_openai")
    if not r or "ppl" not in r:
        return None
    return {
        "step": step,
        "lambada_ppl": float(r["ppl"]),
        "lambada_log_ppl": float(math.log(r["ppl"])),
        "lambada_acc": float(r.get("acc", float("nan"))),
        "lambada_acc_stderr": float(r.get("acc_stderr", float("nan"))),
    }


def main() -> None:
    out_path = HERE / "pythia_lambada_real.csv"
    rows = []
    for model, (n_params, short) in SIZES.items():
        print(f"\n[{model}] listing checkpoints...", file=sys.stderr)
        try:
            items = list_checkpoint_files(model)
        except Exception as e:  # noqa: BLE001
            print(f"  WARN: list failed: {e}", file=sys.stderr)
            continue
        print(f"  found {len(items)} checkpoint files", file=sys.stderr)
        per_size_rows = 0
        for item in items:
            rec = fetch_lambada(item)
            if rec is None:
                continue
            tokens = rec["step"] * TOKENS_PER_STEP_DEFAULT
            compute_flops = 6.0 * n_params * tokens
            # Map pythia-1b-bf16 dir → canonical pythia-1b model name for
            # downstream pipeline; bf16 is same model, just lower precision.
            canonical_model = "pythia-1b" if model == "pythia-1b-bf16" else model
            provenance = "REAL_LAMBADA_FROM_GITHUB"
            if model == "pythia-1b-bf16":
                provenance = "REAL_LAMBADA_FROM_GITHUB_BF16_PROXY"
            rows.append({
                "model": canonical_model,
                "n_params": n_params,
                "step": rec["step"],
                "tokens": tokens,
                "compute_flops": compute_flops,
                "lambada_ppl": rec["lambada_ppl"],
                "lambada_log_ppl": rec["lambada_log_ppl"],
                "lambada_acc": rec["lambada_acc"],
                "lambada_acc_stderr": rec["lambada_acc_stderr"],
                "provenance": provenance,
            })
            per_size_rows += 1
        print(f"  [{model}] {per_size_rows} rows extracted", file=sys.stderr)

    if not rows:
        sys.exit("ERROR: no rows fetched")

    # Sort by (model, step) for readability
    rows.sort(key=lambda r: (r["model"], r["step"]))
    fieldnames = list(rows[0].keys())
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} rows to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
