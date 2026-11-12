"""Generate fit_plot.png: log-log cascade-size distribution + Clauset overlay."""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np

HERE = Path(__file__).parent
_PKG = HERE.resolve().parents[2] / "packages" / "soc-pipeline" / "src"
if str(_PKG) not in sys.path:
    sys.path.insert(0, str(_PKG))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RES = json.loads((HERE / "fit_result.json").read_text())
rows = [json.loads(l) for l in (HERE / "raw_posts.jsonl").open() if l.strip()]


def empirical_ccdf(vals):
    arr = np.sort(np.asarray(vals, dtype=float))
    n = len(arr)
    ccdf = 1.0 - (np.arange(n) + 1) / n
    return arr, ccdf


fig, axes = plt.subplots(1, 3, figsize=(15, 4.5))
labels = ["pre_2021", "post_2024", "full_union"]
for ax, lab in zip(axes, labels):
    if lab == "full_union":
        sl = rows
    else:
        sl = [r for r in rows if r.get("slice") == lab]
    sizes = np.array([r.get("num_comments") or 0 for r in sl], dtype=int)
    sizes = sizes[sizes >= 1]
    x, ccdf = empirical_ccdf(sizes)
    ax.loglog(x, ccdf, ".", ms=3, alpha=0.55, label=f"empirical (n={len(sizes)})")
    # overlay Clauset
    r = RES["slices"][lab]["secondary_cascade_clauset"]
    alpha = r.get("alpha")
    xmin = r.get("xmin")
    in_band = r.get("in_band")
    if alpha and xmin:
        mask = x >= xmin
        x_tail = x[mask]
        if len(x_tail) > 0:
            # CCDF of power law: (x/xmin)^-(alpha-1), normalize at xmin to match data
            ccdf_xmin = ccdf[mask][0]
            ccdf_fit = ccdf_xmin * (x_tail / xmin) ** -(alpha - 1)
            ax.loglog(x_tail, ccdf_fit, "r-", lw=2,
                      label=f"Clauset alpha={alpha:.2f}  xmin={xmin:.0f}\n"
                            f"band {RES['p2_band']} {'IN' if in_band else 'OUT'}")
    ax.set_title(f"WSB cascade-size — {lab}\nverdict: {RES['slices'][lab]['verdict']}")
    ax.set_xlabel("num_comments (cascade size)")
    ax.set_ylabel("CCDF P(X >= x)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8, loc="lower left")

fig.suptitle(
    f"Pre-registered WSB cascade-size fit (P2 secondary)\n"
    f"Headline slice = pre_2021 (adversarial pick before GME regime shift) — verdict: {RES['headline_verdict']}",
    fontsize=11,
)
fig.tight_layout()
out = HERE / "fit_plot.png"
fig.savefig(out, dpi=130, bbox_inches="tight")
print(f"wrote {out} ({out.stat().st_size//1024} KB)")
