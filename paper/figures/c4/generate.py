"""Generate the 3-layer pipeline figure for C4 v0.2.

Output: fig_3layer_pipeline.pdf and fig_3layer_pipeline.png

The compressed pipeline replaces the v0.1 5-layer description
(extract / curate / critic / ensemble / predict) with a legibility-first
3-layer view (extract / curate / critic+predict), where the critic stage
is shown as a two-stage adversarial review (B1 single-model + B3 ensemble)
feeding directly into quantitative prediction.
"""
from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib.lines import Line2D


def render(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # palette
    extract_color = "#2c7fb8"
    curate_color = "#7a0177"
    critic_color = "#cc4c02"
    arrow_color = "#444444"

    def box(x, y, w, h, label, sublabel, color):
        patch = FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.04,rounding_size=0.18",
            linewidth=1.6,
            edgecolor=color,
            facecolor="white",
        )
        ax.add_patch(patch)
        ax.text(
            x + w / 2, y + h - 0.35, label,
            ha="center", va="top",
            fontsize=13, fontweight="bold", color=color,
        )
        ax.text(
            x + w / 2, y + h / 2 - 0.15, sublabel,
            ha="center", va="center",
            fontsize=9, color="#222222",
        )

    # Layer 1: extract
    box(
        0.3, 3.4, 2.6, 1.8,
        "1. Extract",
        "KB pairs\n(V1+V2+V3, ~8000)\n→ Louvain communities\n→ ~24 candidate classes",
        extract_color,
    )

    # Layer 2: curate
    box(
        3.6, 3.4, 2.8, 1.8,
        "2. Curate",
        "LLM curator (Opus)\nshared equation / invariants /\npositive + negative examples\n→ 21 candidate classes",
        curate_color,
    )

    # Layer 3: critic + predict (joint)
    box(
        7.1, 3.4, 2.6, 1.8,
        "3. Critic + Predict",
        "B1 (single Opus)\n→ B3 ensemble (3× DeepSeek)\n→ KEEP / REJECT / SPLIT / MERGE\n→ exponent bands + CIs",
        critic_color,
    )

    # arrows between layers
    def arrow(xa, ya, xb, yb):
        a = FancyArrowPatch(
            (xa, ya), (xb, yb),
            arrowstyle="->", mutation_scale=18,
            color=arrow_color, linewidth=1.4,
        )
        ax.add_patch(a)

    arrow(2.95, 4.3, 3.55, 4.3)
    arrow(6.45, 4.3, 7.05, 4.3)

    # downstream validation (dashed, outside the 3-layer)
    box(
        2.9, 0.4, 4.2, 1.6,
        "Empirical validation (downstream)",
        "13 systems + 4 nulls + A2 phases\nKEEP-verdict predictions tested\nagainst real data",
        "#3f3f3f",
    )

    # dashed connector
    ax.annotate(
        "", xy=(5.0, 2.0), xytext=(8.4, 3.35),
        arrowprops=dict(arrowstyle="->", color="#666666",
                        linestyle="dashed", linewidth=1.2),
    )

    # title
    ax.text(
        5.0, 5.7,
        "Reject-aware pipeline (v0.2, compressed 3-layer)",
        ha="center", va="center",
        fontsize=14, fontweight="bold", color="#111111",
    )
    ax.text(
        5.0, 5.35,
        "extract → curate → critic+predict",
        ha="center", va="center",
        fontsize=10.5, color="#444444",
        style="italic",
    )

    # legend (B1 vs B3)
    legend_handles = [
        Line2D([0], [0], marker="s", linestyle="",
               markerfacecolor="white", markeredgecolor=critic_color,
               markersize=10, label="B1: single Opus critic (3/21 REJECT, 14%)"),
        Line2D([0], [0], marker="s", linestyle="",
               markerfacecolor="white", markeredgecolor="#a63603",
               markersize=10, label="B3: 3× DeepSeek ensemble (7/21 REJECT, 33%)"),
    ]
    ax.legend(
        handles=legend_handles, loc="lower center",
        bbox_to_anchor=(0.5, -0.05), frameon=False, fontsize=9,
        ncol=2,
    )

    plt.tight_layout()
    pdf_path = out_dir / "fig_3layer_pipeline.pdf"
    png_path = out_dir / "fig_3layer_pipeline.png"
    fig.savefig(pdf_path, bbox_inches="tight")
    fig.savefig(png_path, bbox_inches="tight", dpi=180)
    plt.close(fig)

    print(f"Wrote {pdf_path}")
    print(f"Wrote {png_path}")


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    render(here)
