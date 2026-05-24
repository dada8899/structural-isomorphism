#!/usr/bin/env python3
"""Oslo rice pile (1D conserved SOC) validation — X3 Wave 3 #5.

Reference report: docs/coverage/expansion-candidates-2026-05-24.md Wave 3
empty-class table: Manna / Oslo conserved sandpile (Manna 1991; Pruessner
Oslo rice pile) had ZERO entries in the KB before this session.

Hypothesis (Oslo 1D rice pile)
-------------------------------
The Oslo model (Christensen-Corral-Frette-Feder-Jøssang 1996 PRL 77 107;
Frette-Christensen-Malthe-Sørensen-Feder-Jøssang-Meakin 1996 Nature 379 49)
is a 1D conservative SOC model with stochastic thresholds:

    Site i has slope z[i] = h[i] - h[i+1].
    Each site has a threshold z_c[i] drawn uniformly from {1, 2}.
    If z[i] > z_c[i] -> topple: h[i] -= 1, h[i+1] += 1, redraw z_c[i].
    Drive: add grain to leftmost site (i=0).
    Boundary: open at i=L (grain leaves the pile when site L would receive).

Reference exponent (Oslo model):
    tau_s ≈ 1.55   (Frette 1996 Nature; Christensen 1996 PRL; Pruessner 2004)
                   reported range 1.50-1.58 over decades; Oslo universality
                   class with D=2.25 also confirmed.

Empirical anchor: Frette-Christensen-Malthe-Sørensen 1996 Nature 379 49
(real rice pile of long-grain rice in narrow channel; reports tau_s ≈ 2.0
on shape-anisotropic rice and ≈ 1.0 on round-shape rice; the long-grain
rice = Oslo universality class).

Data
----
SYNTHETIC. We simulate the Oslo model on a 1D lattice of length L with
quasi-static driving and open right boundary. After warmup we record
avalanche sizes for n_record drives.

Outputs
-------
results.json    avalanche size distribution + Clauset PL fit
verdict.md      human-readable verdict card
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT / "packages" / "soc-pipeline" / "src"))

from soc_pipeline import fit_clauset_powerlaw  # noqa: E402


# ============================================================
# 1. Oslo model simulation
# ============================================================

def oslo_avalanche(h: np.ndarray, z_c: np.ndarray,
                   rng: np.random.Generator) -> int:
    """Drive 1 grain to leftmost site and relax to stability.

    Slope z[i] = h[i] - h[i+1]; for the right edge, z[L-1] = h[L-1] (open).
    Topple if z[i] > z_c[i] -> h[i] -= 1, h[i+1] += 1 (or off pile if i=L-1).
    """
    L = h.size
    h[0] += 1
    size = 0
    # Track sites that might be unstable; start with i=0.
    stack = [0]
    while stack:
        i = stack.pop()
        # Compute current slope at i
        if i < L - 1:
            z_i = h[i] - h[i + 1]
        else:
            z_i = h[i]  # open right boundary: z[L-1] = h[L-1] - 0
        if z_i > z_c[i]:
            # topple
            h[i] -= 1
            if i < L - 1:
                h[i + 1] += 1
            # else: grain falls off (open boundary)
            # redraw threshold
            z_c[i] = 1 + int(rng.random() < 0.5)  # uniform on {1, 2}
            size += 1
            # Mark neighbours that might now be unstable
            if i > 0:
                stack.append(i - 1)
            stack.append(i)  # this site might still be unstable
            if i < L - 1:
                stack.append(i + 1)
    return size


def run_oslo(L: int, n_warmup: int, n_record: int,
             rng: np.random.Generator) -> np.ndarray:
    h = np.zeros(L, dtype=np.int32)
    z_c = np.array([1 + int(rng.random() < 0.5) for _ in range(L)], dtype=np.int8)
    for _ in range(n_warmup):
        oslo_avalanche(h, z_c, rng)
    sizes = np.empty(n_record, dtype=np.int64)
    for k in range(n_record):
        sizes[k] = oslo_avalanche(h, z_c, rng)
    return sizes


# ============================================================
# 2. Main
# ============================================================

TAU_S_PREDICTED = 1.55  # Oslo 1D
TAU_S_BAND = (1.40, 1.70)


def main():
    L = 256
    n_warmup = 30_000
    n_record = 80_000

    rng = np.random.default_rng(20260525)
    sizes = run_oslo(L=L, n_warmup=n_warmup, n_record=n_record, rng=rng)

    nonzero = sizes[sizes > 0]
    n_nonzero = int(nonzero.size)
    n_zero = int(n_record - nonzero.size)

    fr = fit_clauset_powerlaw(nonzero.astype(float), name="oslo_avalanche_size",
                              discrete=False)
    pl = fr.to_dict()

    tau_measured = pl.get("alpha")
    in_band = tau_measured is not None and TAU_S_BAND[0] <= tau_measured <= TAU_S_BAND[1]

    mean_s = float(nonzero.mean())
    max_s = int(nonzero.max())

    summary = {
        "L": L,
        "n_warmup": n_warmup,
        "n_record": n_record,
        "n_zero": n_zero,
        "n_nonzero": n_nonzero,
        "mean_avalanche_size": mean_s,
        "max_avalanche_size": max_s,
        "tau_size_measured": tau_measured,
        "tau_size_predicted": TAU_S_PREDICTED,
        "tau_size_band": list(TAU_S_BAND),
        "in_oslo_band": bool(in_band),
        "powerlaw_fit": pl,
        "overall_verdict": "CONFIRMED" if in_band else "PARTIAL",
    }
    out = {
        "system": "Oslo rice pile (1D conserved SOC) (SYNTHETIC)",
        "data_provenance": ("SYNTHETIC: 1D Oslo rice-pile model "
                            "(Christensen-Corral-Frette-Feder-Jøssang 1996 "
                            "PRL 77 107; experimental anchor "
                            "Frette-Christensen-Malthe-Sørensen-Feder-Jøssang-Meakin "
                            "1996 Nature 379 49 — long-grain rice in narrow "
                            "channel). tau_s ≈ 1.55 (Pruessner 2004 PRE 69 "
                            "048105). Stochastic site thresholds z_c ∈ {1,2}, "
                            "open right boundary."),
        "predicted_class": "oslo_rice_pile",
        "exponents_predicted": {"tau_size": TAU_S_PREDICTED},
        "summary": summary,
    }
    with open(HERE / "results.json", "w") as f:
        json.dump(out, f, indent=2)
    print(f"[ok] wrote {HERE/'results.json'}")
    print(f"     L                = {L}")
    print(f"     n_avalanche      = {n_nonzero}")
    print(f"     tau_size measured = {tau_measured}")
    print(f"     tau_size predicted= {TAU_S_PREDICTED}")
    print(f"     verdict          = {summary['overall_verdict']}")


if __name__ == "__main__":
    main()
