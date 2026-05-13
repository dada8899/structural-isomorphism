#!/usr/bin/env python3
"""F2 baseline ablation: compare 3 active-learning query selection strategies.

W5-B reviewer feedback flagged that `f2_simulate_active_learning.py` shows the
*after-AL* metric improvement but doesn't compare against trivial baselines
(random sampling) or simple uncertainty sampling. Without those baselines we
can't tell whether the critic-based query selection is doing real work, or
whether *any* labelled signal at the same volume would have done as well.

This script runs all three on the same mined pair pool and writes a
side-by-side comparison report:

    random         — uniform random sampling of training pairs (no AL signal)
    uncertainty    — pick pairs where the baseline encoder is least confident
                     (cosine sim closest to a class boundary)
    critic-based   — original f2 run: use all miner pairs (these come from
                     critic-rejected hard negatives + critic-confirmed positives)

For each strategy we train the same `ContrastiveFinetuner` from the same
starting weights with the same vocabulary, then compare R@5 / R@10 / MRR /
Silhouette on the held-out eval split.

Limitation: this rides the same simulated finetuner as f2_simulate. It's a
*plumbing-level* ablation, not a real fine-tune. The point is to show the
relative deltas between strategies — if random beats critic, the AL signal
isn't useful; if uncertainty beats critic, the critic adds no value beyond
generic uncertainty selection.

CLI:
    python3 v4/scripts/f2_baseline_ablation.py
    python3 v4/scripts/f2_baseline_ablation.py --epochs 10 --eval-frac 0.3
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np

THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
sys.path.insert(0, str(REPO / "v4" / "lib"))
sys.path.insert(0, str(REPO / "v4" / "scripts"))

from embedding_finetune import (  # noqa: E402
    ContrastiveFinetuner,
    FinetuneMetrics,
    TrainingPair,
)
from f2_simulate_active_learning import (  # noqa: E402
    _all_text,
    baseline_metrics,
    load_pairs,
    split_train_eval,
)

logger = logging.getLogger("f2_baseline_ablation")

POSITIVES = REPO / "v4" / "results" / "active_learning" / "positives_v1.jsonl"
NEGATIVES = REPO / "v4" / "results" / "active_learning" / "hard_negatives_v1.jsonl"
REPORT = REPO / "v4" / "results" / "active_learning" / "baseline_comparison.md"


# ---------------------------------------------------------------------------
# Selection strategies
# ---------------------------------------------------------------------------


def select_random(
    train_pairs: list[TrainingPair],
    budget: int,
    seed: int = 42,
) -> list[TrainingPair]:
    """Uniform random sample of `budget` pairs from the training pool."""
    rng = random.Random(seed)
    if budget >= len(train_pairs):
        return list(train_pairs)
    return rng.sample(train_pairs, budget)


def select_uncertainty(
    train_pairs: list[TrainingPair],
    budget: int,
    vocab_corpus: list[str],
) -> list[TrainingPair]:
    """Pick pairs where the baseline encoder is most uncertain.

    Uncertainty proxy: pairs whose cosine similarity (under the unweighted
    TF-IDF encoder) is closest to the decision boundary. We approximate the
    decision boundary as the median similarity across all train pairs.
    """
    baseline = ContrastiveFinetuner(lr=0.0, mode="simulated")
    baseline.fit(train_pairs, epochs=1, batch_size=64, vocab_corpus=vocab_corpus)
    if baseline._weights is not None:  # type: ignore[attr-defined]
        baseline._weights = np.ones_like(baseline._weights)  # type: ignore[attr-defined]

    sims = []
    for p in train_pairs:
        try:
            emb_a = baseline._encode_one(p.text_a)  # type: ignore[attr-defined]
            emb_b = baseline._encode_one(p.text_b)  # type: ignore[attr-defined]
            denom = (np.linalg.norm(emb_a) * np.linalg.norm(emb_b)) or 1.0
            sims.append(float(np.dot(emb_a, emb_b) / denom))
        except Exception:
            sims.append(0.5)  # fallback to neutral

    boundary = float(np.median(sims)) if sims else 0.5
    # Distance from boundary — smaller = more uncertain
    distance = [abs(s - boundary) for s in sims]
    order = np.argsort(distance)
    if budget >= len(train_pairs):
        return list(train_pairs)
    selected = [train_pairs[i] for i in order[:budget]]
    return selected


def select_critic(
    train_pairs: list[TrainingPair],
    budget: int,
) -> list[TrainingPair]:
    """Critic-based: use all miner-mined pairs (these were selected by the
    B1/B3 critic feedback in `f2_mine_hard_negatives.py`). Truncate to budget
    if oversized."""
    # Pairs with higher confidence + non-zero source_verdict carry stronger
    # critic signal; prefer those.
    scored = sorted(
        train_pairs,
        key=lambda p: (1 if p.source_verdict else 0, p.confidence, p.weight),
        reverse=True,
    )
    return scored[:budget] if budget < len(scored) else scored


# ---------------------------------------------------------------------------
# Train + eval per strategy
# ---------------------------------------------------------------------------


def run_strategy(
    name: str,
    selected_train: list[TrainingPair],
    eval_pairs: list[TrainingPair],
    vocab_corpus: list[str],
    epochs: int,
) -> dict[str, Any]:
    if not selected_train:
        logger.warning("Strategy %s selected 0 pairs; skipping fit", name)
        empty = FinetuneMetrics()
        return {
            "name": name,
            "n_selected": 0,
            "n_positives": 0,
            "n_negatives": 0,
            "metrics": empty,
        }
    ft = ContrastiveFinetuner(lr=0.05, mode="simulated")
    ft.fit(selected_train, epochs=epochs, batch_size=32, vocab_corpus=vocab_corpus)
    eval_m = ft.evaluate(eval_pairs)
    return {
        "name": name,
        "n_selected": len(selected_train),
        "n_positives": sum(1 for p in selected_train if p.label == 1),
        "n_negatives": sum(1 for p in selected_train if p.label == 0),
        "metrics": eval_m,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def write_report(
    out: Path,
    baseline: FinetuneMetrics,
    strategies: list[dict[str, Any]],
    budget: int,
    n_train: int,
    n_eval: int,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# F2 Active Learning — Baseline Strategy Comparison")
    lines.append("")
    lines.append("**Goal**: compare three query-selection strategies (random / uncertainty / critic) at the same labelling budget to test whether the critic-based selection adds value beyond a random or uncertainty baseline.")
    lines.append("")
    lines.append(f"- Labelling budget per strategy: {budget} pairs")
    lines.append(f"- Train pool size: {n_train}")
    lines.append(f"- Eval split size: {n_eval}")
    lines.append("")
    lines.append("## Vanilla baseline (no AL, unit TF-IDF weights)")
    lines.append("")
    lines.append(f"- R@5:        {baseline.r_at_5:.3f}")
    lines.append(f"- R@10:       {baseline.r_at_10:.3f}")
    lines.append(f"- MRR:        {baseline.mrr:.3f}")
    lines.append(f"- Silhouette: {baseline.silhouette:.3f}")
    lines.append("")
    lines.append("## Strategy comparison")
    lines.append("")
    lines.append("| Strategy | n_selected | n_pos | n_neg | R@5 | R@10 | MRR | Silhouette | Δ R@5 vs baseline |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for s in strategies:
        m = s["metrics"]
        delta = m.r_at_5 - baseline.r_at_5
        lines.append(
            f"| **{s['name']}** | {s['n_selected']} | {s['n_positives']} | {s['n_negatives']} | "
            f"{m.r_at_5:.3f} | {m.r_at_10:.3f} | {m.mrr:.3f} | {m.silhouette:.3f} | {delta:+.3f} |"
        )
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    by_name = {s["name"]: s["metrics"].r_at_5 for s in strategies}
    if "critic" in by_name and "random" in by_name and "uncertainty" in by_name:
        critic_r5 = by_name["critic"]
        random_r5 = by_name["random"]
        uncertainty_r5 = by_name["uncertainty"]
        if critic_r5 > random_r5 and critic_r5 > uncertainty_r5:
            lines.append(f"Critic-based selection wins on R@5 by {critic_r5 - max(random_r5, uncertainty_r5):+.3f} over the best non-critic baseline. The B1/B3 critic feedback carries genuine signal beyond random or uncertainty sampling.")
        elif critic_r5 <= random_r5:
            lines.append(f"⚠️ Random sampling ties or beats critic-based selection ({random_r5:.3f} ≥ {critic_r5:.3f}). At this budget the critic signal is **not** distinguishable from random labels — consider increasing budget, refining critic prompt, or using a stronger uncertainty model.")
        elif uncertainty_r5 > critic_r5:
            lines.append(f"⚠️ Uncertainty sampling beats critic-based selection ({uncertainty_r5:.3f} > {critic_r5:.3f}). The critic adds no value beyond generic uncertainty — investigate whether the critic is just rejecting hard cases that uncertainty would already flag.")
        else:
            lines.append("Strategies are within noise of each other at this budget; larger budget needed to discriminate.")
    lines.append("")
    lines.append("## Caveat")
    lines.append("")
    lines.append("This is a simulation on TF-IDF char n-grams, not real V1/V2 sentence-transformer fine-tuning. The relative deltas between strategies are informative; absolute numbers are not directly comparable to the production V3 fine-tune. See `f2_simulate_active_learning.py` and `v4/lib/F2_active_learning_design.md` §3 for the real-run swap.")
    lines.append("")
    lines.append("## Method")
    lines.append("")
    lines.append("1. Load all mined pairs (positives + hard negatives) from `f2_mine_hard_negatives.py` output.")
    lines.append("2. Train/eval split (stratified by label, seed=42).")
    lines.append("3. For each strategy, select `budget` pairs from the train pool:")
    lines.append("   - **random**: uniform random sample.")
    lines.append("   - **uncertainty**: pairs whose unit-weight cosine similarity is closest to the median similarity (decision-boundary proxy).")
    lines.append("   - **critic**: top-`budget` pairs ranked by (has_critic_verdict, confidence, weight).")
    lines.append("4. Fit the same `ContrastiveFinetuner` (lr=0.05, simulated mode) on each selection.")
    lines.append("5. Evaluate on the held-out eval split.")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="F2 active-learning baseline ablation (random / uncertainty / critic)"
    )
    parser.add_argument("--positives", type=Path, default=POSITIVES)
    parser.add_argument("--negatives", type=Path, default=NEGATIVES)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument(
        "--budget",
        type=int,
        default=0,
        help="Pairs per strategy. 0 = use all available train pairs (equal-volume comparison).",
    )
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--eval-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pairs = load_pairs(args.positives, args.negatives)
    logger.info("Loaded %d mined pairs", len(pairs))

    train, evalset = split_train_eval(pairs, eval_frac=args.eval_frac, seed=args.seed)
    vocab_corpus = _all_text(train) + _all_text(evalset)
    logger.info("Split: %d train / %d eval", len(train), len(evalset))

    # Equal-budget comparison: default = use the full train pool so each
    # strategy gets the same number of pairs.
    budget = args.budget if args.budget > 0 else len(train)

    # Vanilla baseline (unit weights, no selection)
    baseline = baseline_metrics(evalset, vocab_corpus=vocab_corpus)
    logger.info(
        "Baseline (no AL): R@5=%.3f MRR=%.3f", baseline.r_at_5, baseline.mrr,
    )

    strategies_out: list[dict[str, Any]] = []
    for strategy_name, selector in (
        ("random", lambda tp: select_random(tp, budget, seed=args.seed)),
        ("uncertainty", lambda tp: select_uncertainty(tp, budget, vocab_corpus)),
        ("critic", lambda tp: select_critic(tp, budget)),
    ):
        logger.info("Running strategy: %s (budget=%d)", strategy_name, budget)
        selected = selector(train)
        result = run_strategy(strategy_name, selected, evalset, vocab_corpus, args.epochs)
        strategies_out.append(result)
        m = result["metrics"]
        logger.info(
            "  %s: n=%d R@5=%.3f MRR=%.3f sil=%.3f",
            strategy_name, result["n_selected"], m.r_at_5, m.mrr, m.silhouette,
        )

    write_report(
        args.report,
        baseline,
        strategies_out,
        budget=budget,
        n_train=len(train),
        n_eval=len(evalset),
    )
    logger.info("Wrote report -> %s", args.report)

    # Also dump JSON to stdout for programmatic consumers
    print(json.dumps(
        {
            "baseline_r5": baseline.r_at_5,
            "baseline_mrr": baseline.mrr,
            "strategies": [
                {
                    "name": s["name"],
                    "n_selected": s["n_selected"],
                    "r_at_5": s["metrics"].r_at_5,
                    "mrr": s["metrics"].mrr,
                    "silhouette": s["metrics"].silhouette,
                }
                for s in strategies_out
            ],
            "report": str(args.report),
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    sys.exit(main())
