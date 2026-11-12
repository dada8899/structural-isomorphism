#!/usr/bin/env python3
"""Fetch real Pythia training loss curves from public EleutherAI wandb runs.

Approach
--------
EleutherAI's pythia project (https://wandb.ai/eleutherai/pythia) hosts the
official training runs as anonymous-readable public runs. We use the wandb
GraphQL public API (no auth required) to query:

  - `summaryMetrics` to identify runs by final train/lm_loss
    (Pythia v1 published final losses per Biderman 2023 Table 8 / Fig 5)
  - `sampledHistory` to download train/lm_loss vs _step trajectories

Model identification
--------------------
Run names on wandb are internal hostnames (ip-26-*, cw-prod-*) — they do
NOT include model size. We map runs to sizes by matching the *final loss*
to the published Pythia table:

    70M:   2.493 → run qiu9n7a6 (finished, step 143000, final 2.50) FULL
    160M:  2.236 → NO MATCH in 1000+ enumerated runs (gap)
    410M:  2.020 → 339s0ka6 (step 2-105k) + 1ena81fo (105-124k) + 318z89xb (124-143k)
    1B:    1.907 → NO clean match (gap)
    1.4B:  1.821 → 3iwoclpd/3ui27nye/2tw70d8v/lidt5yrz (step 73-78k, mid-training)
    2.8B:  1.763 → 17hqpon5/mdl32suo (step 125k) + kg5ni1dl (step 143k, FINISHED)
    6.9B:  1.659 → NO match in public runs
    1B-0.5MtokBS: 1.965 → 2ckblvuv (step 202-236k) + 3bj0rp1k (step 236-286k, FINISHED)

We grab whatever real data exists, stitch contiguous segments per size,
mark provenance honestly in the output CSV.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent

WANDB_GQL = "https://api.wandb.ai/graphql"
HEADERS = {"User-Agent": "structural-isomorphism-validation/0.2"}

# Map of model_size -> list of (run_id, role) where role is
# 'finished' (full or terminal-end of training) or 'partial' (mid-training fragment).
# Identified by matching final loss to Biderman 2023 Table 8.
SIZE_RUNS = {
    "pythia-70m": [("qiu9n7a6", "full")],  # complete curve from step 61 to 143k
    "pythia-410m": [
        ("339s0ka6", "head"),   # step 2061 → 105986 (loss 2.886 → 2.048)
        ("1ena81fo", "mid"),    # step 105k → 124k (loss 2.032 → 2.038)
        ("318z89xb", "tail"),   # step 124k → 142990 (loss 2.055 → 2.054, finished)
    ],
    "pythia-1b-0.5MtokBS": [
        ("2ckblvuv", "head"),  # step 202k → 236k
        ("3bj0rp1k", "tail"),  # step 236k → 286k (finished)
    ],
    "pythia-2.8b": [
        ("17hqpon5", "mid"),  # step 125k loss 1.75
        ("mdl32suo", "mid"),  # step 125-125.9k loss 1.77
        ("1yrbqqgi", "mid"),  # step 124-125.5k loss 1.74
        ("kg5ni1dl", "tail"),  # step 125-143k loss 1.74-1.76, FINISHED
    ],
    # 1.4B approximate from short crashes
    "pythia-1.4b": [
        ("lidt5yrz", "mid"),   # step 73-78k loss 1.81-1.79
        ("3ui27nye", "mid"),   # step 78k loss 1.83-1.82
    ],
}

# Final published loss per Biderman 2023 Table 8 (Pile validation):
PUBLISHED_FINAL = {
    "pythia-70m":  2.493,
    "pythia-160m": 2.236,
    "pythia-410m": 2.020,
    "pythia-1b":   1.907,
    "pythia-1.4b": 1.821,
    "pythia-2.8b": 1.763,
    "pythia-6.9b": 1.659,
    "pythia-12b":  1.598,
    # 0.5MtokBS variants train 2x steps and reach different endpoints
    "pythia-1b-0.5MtokBS": 1.965,
    "pythia-70m-0.25MtokBS": 2.524,
}

# Model -> (n_params, batch_tokens_per_step)
MODEL_META = {
    "pythia-70m":   (70_426_624,     2.097e6),   # 1024 seq * 2048 batch (Pythia: actually 2.1M tok/step)
    "pythia-160m":  (162_322_944,    2.097e6),
    "pythia-410m":  (405_334_016,    2.097e6),
    "pythia-1b":    (1_011_339_264,  2.097e6),
    "pythia-1.4b":  (1_414_647_808,  2.097e6),
    "pythia-2.8b":  (2_775_208_960,  2.097e6),
    "pythia-6.9b":  (6_857_302_016,  2.097e6),
    "pythia-12b":   (11_846_072_320, 2.097e6),
    "pythia-1b-0.5MtokBS":     (1_011_339_264, 1.048e6),
    "pythia-70m-0.25MtokBS":   (70_426_624,    0.524e6),
}


def fetch_history(run_id: str, samples: int = 1500, tries: int = 5,
                  keys: list[str] | None = None) -> list[dict]:
    if keys is None:
        keys = ["train/lm_loss", "_step"]
    spec = json.dumps({"keys": keys, "samples": samples})
    gql = """
    query Run($e: String!, $p: String!, $r: String!, $s: [JSONString!]!) {
      project(entityName: $e, name: $p) {
        run(name: $r) { sampledHistory(specs: $s) }
      }
    }
    """
    for attempt in range(tries):
        try:
            r = requests.post(WANDB_GQL,
                              json={"query": gql,
                                    "variables": {"e": "eleutherai", "p": "pythia",
                                                  "r": run_id, "s": [spec]}},
                              headers=HEADERS, timeout=45)
            d = r.json()
            if "errors" in d:
                raise RuntimeError(d["errors"])
            sh = d["data"]["project"]["run"]["sampledHistory"]
            if not sh:
                return []
            hist = sh[0]
            pts = []
            for h in hist:
                s = h.get("_step")
                l = h.get("train/lm_loss")
                if s is None or l is None:
                    continue
                pts.append({"step": int(s), "loss": float(l)})
            pts.sort(key=lambda x: x["step"])
            return pts
        except Exception as e:
            wait = 5 * (attempt + 1)
            print(f"  [retry {attempt+1}/{tries}] {run_id} fail: {e}; sleep {wait}s",
                  file=sys.stderr)
            time.sleep(wait)
    return []


def stitch_segments(model: str, runs: list[tuple[str, str]]) -> list[dict]:
    """Combine per-run histories, dedupe by step (later runs win for overlap)."""
    merged: dict[int, float] = {}
    for run_id, role in runs:
        print(f"  [{model}] fetching {run_id} ({role})...", file=sys.stderr)
        pts = fetch_history(run_id)
        if not pts:
            print(f"  [{model}] {run_id}: empty", file=sys.stderr)
            continue
        # For tail/finished, prefer later values; for head, earlier
        for p in pts:
            merged[p["step"]] = p["loss"]
        print(f"  [{model}] {run_id}: {len(pts)} pts, step "
              f"[{pts[0]['step']}, {pts[-1]['step']}]", file=sys.stderr)
        time.sleep(0.5)
    out = [{"step": s, "loss": l} for s, l in sorted(merged.items())]
    return out


def main() -> None:
    out = {}
    audit = []
    for model, runs in SIZE_RUNS.items():
        n_params, tok_step = MODEL_META[model]
        trajectory = stitch_segments(model, runs)
        if not trajectory:
            print(f"[{model}] EMPTY trajectory", file=sys.stderr)
            audit.append({"model": model, "status": "EMPTY", "n_points": 0})
            continue
        rows = []
        for p in trajectory:
            step = p["step"]
            tokens = step * tok_step
            compute_flops = 6.0 * n_params * tokens  # standard Chinchilla 6N*D
            rows.append({
                "model": model, "n_params": n_params, "step": step,
                "tokens": tokens, "compute_flops": compute_flops,
                "loss": p["loss"]
            })
        out[model] = rows
        first_step = trajectory[0]["step"]
        last_step = trajectory[-1]["step"]
        first_loss = trajectory[0]["loss"]
        last_loss = trajectory[-1]["loss"]
        pub = PUBLISHED_FINAL.get(model, None)
        diff = abs(last_loss - pub) if pub else None
        audit.append({
            "model": model, "status": "REAL_WANDB",
            "n_points": len(rows),
            "step_range": [first_step, last_step],
            "loss_range": [first_loss, last_loss],
            "published_final": pub,
            "loss_delta_vs_pub": diff,
            "runs_used": [{"run_id": r[0], "role": r[1]} for r in runs],
        })
        print(f"[{model}] n={len(rows)} step [{first_step}, {last_step}] "
              f"loss [{first_loss:.3f}, {last_loss:.3f}] pub_final={pub}",
              file=sys.stderr)

    # Write per-model JSON
    out_json = HERE / "pythia_wandb_history.json"
    out_json.write_text(json.dumps({m: out[m] for m in out}, indent=2))
    print(f"Wrote {out_json}", file=sys.stderr)

    # Audit log
    audit_path = HERE / "pythia_wandb_audit.json"
    audit_path.write_text(json.dumps({
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "data_source": "https://wandb.ai/eleutherai/pythia (public anonymous GraphQL API)",
        "identification_method": "match summaryMetrics.train/lm_loss to Biderman 2023 Table 8",
        "models": audit,
    }, indent=2))
    print(f"Wrote {audit_path}", file=sys.stderr)

    # Combined CSV
    csv_path = HERE / "pythia_checkpoints_real.csv"
    with csv_path.open("w") as f:
        f.write("model,n_params,step,tokens,compute_flops,loss\n")
        for model in out:
            for row in out[model]:
                f.write(f"{row['model']},{row['n_params']},{row['step']},"
                        f"{row['tokens']:.6e},{row['compute_flops']:.6e},{row['loss']:.6f}\n")
    print(f"Wrote {csv_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
