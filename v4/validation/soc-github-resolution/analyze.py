#!/usr/bin/env python3
"""Run the frozen SOC pipeline on GitHub-issue resolution times.

Pre-registered band (committed *before* inspecting the verdict):
    alpha ∈ [1.5, 3.0] for resolution_s tail.

We also legitimately flag "lognormal-preferred" as a successful adversarial
outcome (the task spec explicitly invites this).

Outputs:
    verdict.json
    RESULT.md (written separately)
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

DATA = ROOT.parent / "github_resolutions.jsonl"
VERDICT_PATH = ROOT.parent / "verdict.json"

PREREG_BAND = (1.5, 3.0)


def _verdict_to_dict(v):
    d = asdict(v)
    for k, val in d.items():
        if isinstance(val, tuple):
            d[k] = list(val)
    return d


def main():
    if not DATA.is_file():
        print(f"missing {DATA}; run fetch_github_resolutions.py first", file=sys.stderr)
        sys.exit(2)
    rows = []
    with DATA.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    durations = np.array(
        [r["resolution_s"] for r in rows if r.get("resolution_s")],
        dtype=float,
    )
    print(f"n_rows={len(rows)}, n_durations={len(durations)}")
    v = validate(
        durations,
        label="github_issue_resolution_s",
        expected_band=PREREG_BAND,
        n_boot=200,
    )
    print(
        f"RESOLUTION: verdict={v.verdict}, alpha={v.alpha:.3f}, "
        f"CI=[{v.alpha_ci_low:.3f}, {v.alpha_ci_high:.3f}], "
        f"in_band={v.in_band}, n_tail={v.n_tail}"
    )
    print(
        f"  vs_lognormal_R={v.vs_lognormal_R:.3f} p={v.vs_lognormal_p:.3g}"
    )
    print(
        f"  vs_exponential_R={v.vs_exponential_R:.3f} p={v.vs_exponential_p:.3g}"
    )
    out = {
        "verdict": _verdict_to_dict(v),
        "n_rows": len(rows),
        "n_durations": len(durations),
        "preregistered_band": list(PREREG_BAND),
    }
    with VERDICT_PATH.open("w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"wrote {VERDICT_PATH}")


if __name__ == "__main__":
    main()
