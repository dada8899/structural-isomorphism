#!/usr/bin/env python3
"""
Layer 5 Phase 4 — Step 1: Generate synthetic neural avalanche data.

Ground truth: a critical branching process on N nodes with mean branching
ratio m = 1 produces avalanches whose size s and duration T distributions
follow universal power laws:

  P(s) ∝ s^(-tau),   tau  = 3/2
  P(T) ∝ T^(-alpha), alpha = 2
  <s|T> ∝ T^(1/(alpha-1)) = T^1

These are the canonical mean-field SOC exponents predicted by
Beggs-Plenz 2003 for neural avalanches.

We generate avalanches by running a standard Bienaymé-Galton-Watson
branching process at criticality and record each run's size (total
descendants) and duration (generation count).

Output:
  synthetic_avalanches.jsonl  — one avalanche per line: {size, duration}
"""

import json
import math
from pathlib import Path

import numpy as np

OUT = Path(__file__).resolve().parent / "synthetic_avalanches.jsonl"


def simulate_avalanche(m: float, rng: np.random.Generator, cap: int = 50000):
    """One Bienaymé-Galton-Watson avalanche seeded by a single ancestor.

    Offspring distribution: Poisson(m). At criticality m=1, size and
    duration follow the canonical mean-field SOC power laws.
    Cap prevents infinite runs on super-critical parameter draws.
    """
    gen = 1  # start with the seed
    size = 1
    alive = 1
    duration = 1
    while alive > 0 and size < cap:
        offspring = rng.poisson(m, size=alive).sum()
        alive = int(offspring)
        if alive == 0:
            break
        size += alive
        duration += 1
    return size, duration


def main():
    rng = np.random.default_rng(42)
    n_avalanches = 200_000   # big enough to see a clean power-law tail
    m = 1.0                  # critical

    sizes, durations = [], []
    for i in range(n_avalanches):
        s, T = simulate_avalanche(m, rng)
        sizes.append(s)
        durations.append(T)
        if (i + 1) % 25000 == 0:
            print(f"  {i+1}/{n_avalanches} ... max size so far = {max(sizes)}")

    print(f"Generated {len(sizes)} avalanches.")
    print(f"  size   range [{min(sizes)}, {max(sizes)}], mean {np.mean(sizes):.1f}")
    print(f"  duration range [{min(durations)}, {max(durations)}], mean {np.mean(durations):.1f}")

    with OUT.open("w") as f:
        for s, T in zip(sizes, durations):
            f.write(json.dumps({"size": int(s), "duration": int(T)}) + "\n")
    print(f"Saved: {OUT}")


if __name__ == "__main__":
    main()
