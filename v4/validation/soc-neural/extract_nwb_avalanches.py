#!/usr/bin/env python3
"""
Layer 5 Phase 4 — Step 3: Extract neural avalanches from a DANDI NWB file.

Beggs-Plenz 2003 avalanche definition:
  - Bin all spikes (across all units) into a time bin of width <IEI>
    where <IEI> = average inter-event interval of the pooled spike train
  - An avalanche = a run of consecutive non-empty bins, bracketed by
    at least one empty bin on each side
  - size     = total spike count in the avalanche (sum across all units)
  - duration = number of bins spanned by the avalanche

Input  : NWB (HDF5) file with /units/spike_times + /units/spike_times_index
Output : avalanches.jsonl  — one avalanche per line  {size, duration}
"""

import argparse
import json
from pathlib import Path

import h5py
import numpy as np


HERE = Path(__file__).resolve().parent


def load_spikes(nwb_path: Path):
    with h5py.File(nwb_path, "r") as f:
        spike_times = f["units/spike_times"][:]
        # spike_times_index[i] is the cumulative end index for unit i
        idx = f["units/spike_times_index"][:]
        unit_ids = f["units/id"][:]
    print(f"  n_units: {len(unit_ids)}, n_spikes: {len(spike_times)}")
    # Reconstruct per-unit times for reference, but we mainly need the
    # pooled time series for avalanche analysis
    return spike_times, idx, unit_ids


def pool_all_spikes(spike_times: np.ndarray):
    """Return a sorted 1D array of all spike times across all units."""
    return np.sort(spike_times)


def bin_and_detect_avalanches(pooled: np.ndarray, bin_width_s: float):
    """Bin pooled spikes into fixed-width bins. Return (sizes, durations)."""
    t0 = pooled.min()
    t1 = pooled.max()
    n_bins = int(np.ceil((t1 - t0) / bin_width_s)) + 1
    bin_idx = ((pooled - t0) / bin_width_s).astype(np.int64)
    bin_idx = np.clip(bin_idx, 0, n_bins - 1)
    # counts[j] = number of spikes in bin j
    counts = np.bincount(bin_idx, minlength=n_bins).astype(np.int64)

    sizes = []
    durations = []
    in_ava = False
    cur_size = 0
    cur_dur = 0
    for c in counts:
        if c > 0:
            cur_size += int(c)
            cur_dur += 1
            in_ava = True
        else:
            if in_ava:
                sizes.append(cur_size)
                durations.append(cur_dur)
                cur_size = 0
                cur_dur = 0
                in_ava = False
    if in_ava:
        sizes.append(cur_size)
        durations.append(cur_dur)
    return np.array(sizes, dtype=np.int64), np.array(durations, dtype=np.int64)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nwb", default=str(HERE / "data" / "sample.nwb"))
    ap.add_argument("--out", default=str(HERE / "neural_avalanches.jsonl"))
    ap.add_argument("--meta", default=str(HERE / "neural_fetch_log.json"))
    ap.add_argument("--bin-factor", type=float, default=1.0,
                    help="bin width = bin-factor * <IEI>; 1.0 is Beggs-Plenz 2003")
    args = ap.parse_args()

    nwb_path = Path(args.nwb)
    print(f"Loading {nwb_path.name} ...")
    spike_times, idx, unit_ids = load_spikes(nwb_path)
    pooled = pool_all_spikes(spike_times)
    print(f"  pooled spike time range: {pooled.min():.3f} → {pooled.max():.3f} s  "
          f"(span {pooled.max() - pooled.min():.1f} s)")

    # Compute average IEI
    iei = np.diff(pooled)
    # Drop zero-diff ties (simultaneous spikes across units)
    iei_pos = iei[iei > 0]
    mean_iei = float(np.mean(iei_pos))
    bin_width_s = mean_iei * args.bin_factor
    print(f"  mean inter-event interval: {mean_iei*1000:.3f} ms  "
          f"(using bin-factor={args.bin_factor} → bin width = {bin_width_s*1000:.3f} ms)")

    print("Detecting avalanches ...")
    sizes, durations = bin_and_detect_avalanches(pooled, bin_width_s)
    print(f"  n_avalanches: {len(sizes)}")
    print(f"  size     range [{sizes.min()}, {sizes.max()}], mean {sizes.mean():.2f}")
    print(f"  duration range [{durations.min()}, {durations.max()}], mean {durations.mean():.2f}")

    # Write
    out_path = Path(args.out)
    with out_path.open("w") as f:
        for s, T in zip(sizes, durations):
            f.write(json.dumps({"size": int(s), "duration": int(T)}) + "\n")
    print(f"Saved: {out_path}")

    meta = {
        "nwb_file": str(nwb_path.name),
        "n_units": int(len(unit_ids)),
        "n_spikes_total": int(len(spike_times)),
        "pooled_time_span_sec": float(pooled.max() - pooled.min()),
        "mean_iei_ms": mean_iei * 1000,
        "bin_factor": args.bin_factor,
        "bin_width_ms": bin_width_s * 1000,
        "n_avalanches": int(len(sizes)),
        "size_range": [int(sizes.min()), int(sizes.max())],
        "duration_range": [int(durations.min()), int(durations.max())],
    }
    Path(args.meta).write_text(json.dumps(meta, indent=2))
    print(f"Meta: {args.meta}")


if __name__ == "__main__":
    main()
