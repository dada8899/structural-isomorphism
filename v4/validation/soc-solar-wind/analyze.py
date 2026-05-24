#!/usr/bin/env python3
"""Run the frozen SOC pipeline on solar-wind burst statistics.

Pre-registered bands (committed to fetch_solar_wind.py and RESULT.md
*before* any verdict was inspected):
    - burst-size (integrated_excess_kms_s): alpha ∈ [1.8, 2.4]
      following Freeman & Watkins 2002 (doi:10.1126/science.1075962)
    - inter-event time: alpha ∈ [1.5, 2.5] broader band; less well
      anchored in the SW literature.

Outputs:
    verdict.json — full Verdict dataclass dump (PASS / FAIL / INCONCLUSIVE)
    RESULT.md    — narrative writeup (written separately)
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve()
REPO = ROOT.parents[3]
sys.path.insert(0, str(REPO / "packages" / "soc-pipeline" / "src"))

from soc_pipeline import validate  # noqa: E402

DATA = ROOT.parent / "solar_wind_bursts.jsonl"
VERDICT_PATH = ROOT.parent / "verdict.json"

PREREG_BAND_BURST_SIZE = (1.8, 2.4)
PREREG_BAND_INTER_EVENT = (1.5, 2.5)


def _verdict_to_dict(v):
    d = asdict(v)
    # Replace tuples/Nones with JSON-safe types
    for k, val in d.items():
        if isinstance(val, tuple):
            d[k] = list(val)
    return d


def main():
    if not DATA.is_file():
        print(f"missing {DATA}; run fetch_solar_wind.py first", file=sys.stderr)
        sys.exit(2)
    bursts = []
    with DATA.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                bursts.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    sizes = np.array(
        [b["integrated_excess_kms_s"] for b in bursts if b.get("integrated_excess_kms_s")],
        dtype=float,
    )
    inter = np.array(
        [b["inter_event_s"] for b in bursts if b.get("inter_event_s")],
        dtype=float,
    )

    print(f"n_bursts={len(bursts)}, n_sizes={len(sizes)}, n_inter={len(inter)}")

    v_size = validate(
        sizes,
        label="solar_wind_bursts__size",
        expected_band=PREREG_BAND_BURST_SIZE,
        n_boot=200,
    )
    print(
        f"BURST SIZE: verdict={v_size.verdict}, alpha={v_size.alpha:.3f}, "
        f"CI=[{v_size.alpha_ci_low:.3f}, {v_size.alpha_ci_high:.3f}], "
        f"in_band={v_size.in_band}, n_tail={v_size.n_tail}"
    )

    v_inter = validate(
        inter,
        label="solar_wind_bursts__inter_event",
        expected_band=PREREG_BAND_INTER_EVENT,
        n_boot=200,
    )
    print(
        f"INTER-EVENT: verdict={v_inter.verdict}, alpha={v_inter.alpha:.3f}, "
        f"CI=[{v_inter.alpha_ci_low:.3f}, {v_inter.alpha_ci_high:.3f}], "
        f"in_band={v_inter.in_band}, n_tail={v_inter.n_tail}"
    )

    out = {
        "burst_size": _verdict_to_dict(v_size),
        "inter_event": _verdict_to_dict(v_inter),
        "n_bursts": len(bursts),
        "preregistered_bands": {
            "burst_size": list(PREREG_BAND_BURST_SIZE),
            "inter_event": list(PREREG_BAND_INTER_EVENT),
        },
    }
    with VERDICT_PATH.open("w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"wrote {VERDICT_PATH}")


if __name__ == "__main__":
    main()
