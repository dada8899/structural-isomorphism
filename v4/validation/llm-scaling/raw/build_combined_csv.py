#!/usr/bin/env python3
"""Build a combined Pythia checkpoint CSV from real wandb history plus
literature-anchored synthetic for sizes without public wandb runs.

Inputs:
  pythia_wandb_history.json — real wandb data per size (5 sizes)
  pythia_checkpoints.csv    — original synthetic for all 6 sizes (fallback)

Outputs:
  pythia_checkpoints_combined.csv   — combined data with provenance column
  pythia_checkpoints_provenance.json — per-size source description
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
WANDB_JSON = HERE / "pythia_wandb_history.json"
SYNTH_CSV = HERE / "pythia_checkpoints.csv"
OUT_CSV = HERE / "pythia_checkpoints_combined.csv"
OUT_AUDIT = HERE / "pythia_checkpoints_provenance.json"

# Original 6 Pythia model sizes + 1.4b (real wandb fragment available, Biderman
# reports it as a documented size in Table 8). We expose 1.4b in the combined
# CSV so the learning-curve fit can use the real REAL_PARTIAL_WIDE trajectory.
TARGET_SIZES = ["pythia-70m", "pythia-160m", "pythia-410m",
                "pythia-1b", "pythia-1.4b", "pythia-2.8b", "pythia-6.9b"]


def thin_to_log(rows: list[dict], n_target: int = 30) -> list[dict]:
    """Pick ~n_target rows log-spaced in step from a dense trajectory."""
    if len(rows) <= n_target:
        return rows
    steps = [r["step"] for r in rows]
    s_min, s_max = min(steps), max(steps)
    if s_min <= 0:
        s_min = 1
    log_targets = [s_min * (s_max / s_min) ** (i / (n_target - 1))
                   for i in range(n_target)]
    out_idx = []
    for t in log_targets:
        # binary search nearest by step
        best = 0
        best_d = abs(rows[0]["step"] - t)
        for i, r in enumerate(rows):
            d = abs(r["step"] - t)
            if d < best_d:
                best_d = d; best = i
        if best not in out_idx:
            out_idx.append(best)
    out_idx.sort()
    return [rows[i] for i in out_idx]


def main():
    wandb_data = json.loads(WANDB_JSON.read_text())
    # Load synthetic CSV as fallback
    synth_by_model: dict[str, list[dict]] = {}
    with SYNTH_CSV.open() as f:
        for row in csv.DictReader(f):
            synth_by_model.setdefault(row["model"], []).append(row)

    out_rows = []
    audit = {}
    for size in TARGET_SIZES:
        # Direct match in wandb_data
        if size in wandb_data and wandb_data[size]:
            real = wandb_data[size]
            thinned = thin_to_log(real, n_target=40)
            # Determine step coverage
            step_min = min(r["step"] for r in real)
            step_max = max(r["step"] for r in real)
            loss_min = min(r["loss"] for r in real)
            loss_max = max(r["loss"] for r in real)
            # Provenance categorisation
            if step_min < 5000 and step_max > 100000:
                kind = "REAL_FULL"  # head + tail
            elif loss_max - loss_min > 0.2:
                kind = "REAL_PARTIAL_WIDE"  # has dynamic range
            else:
                kind = "REAL_TAIL_NARROW"  # narrow tail only
            audit[size] = {
                "source": "wandb-eleutherai-pythia (real training run)",
                "kind": kind,
                "n_points_raw": len(real),
                "n_points_used": len(thinned),
                "step_range": [step_min, step_max],
                "loss_range": [loss_min, loss_max],
                "dynamic_range": loss_max - loss_min,
            }
            for r in thinned:
                out_rows.append({
                    "model": size,
                    "n_params": r["n_params"],
                    "step": r["step"],
                    "tokens": r["tokens"],
                    "compute_flops": r["compute_flops"],
                    "loss": r["loss"],
                    "provenance": kind,
                })
        else:
            # Fallback to synthetic
            audit[size] = {
                "source": "synthetic (Biderman 2023 Fig 5 parameterisation)",
                "kind": "SYNTHETIC",
                "n_points": len(synth_by_model.get(size, [])),
                "reason": "no public wandb run identified for this size",
            }
            for r in synth_by_model.get(size, []):
                out_rows.append({
                    "model": size,
                    "n_params": int(r["n_params"]),
                    "step": int(r["step"]),
                    "tokens": float(r["tokens"]),
                    "compute_flops": float(r["compute_flops"]),
                    "loss": float(r["loss"]),
                    "provenance": "SYNTHETIC",
                })

    # Sort by model then step
    out_rows.sort(key=lambda r: (r["model"], r["step"]))

    with OUT_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "n_params", "step", "tokens",
                                          "compute_flops", "loss", "provenance"])
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    OUT_AUDIT.write_text(json.dumps(audit, indent=2))

    print(f"Wrote {OUT_CSV} ({len(out_rows)} rows)")
    print(f"Wrote {OUT_AUDIT}")
    print()
    print("Per-size summary:")
    for size, info in audit.items():
        print(f"  {size}: {info['kind']} (n={info.get('n_points_used', info.get('n_points'))})"
              f"  range={info.get('loss_range', 'N/A')}"
              f"  dyn={info.get('dynamic_range', 'N/A')}")


if __name__ == "__main__":
    main()
