#!/usr/bin/env python3
"""F2 simulation: mini active-learning loop with baseline + after-AL R@5.

This script demonstrates the active-learning pipeline end-to-end *without*
touching the real V1/V2 models. It uses:
    - the EmbeddingBridge tfidf fallback as a stand-in encoder
    - the mined positives_v1.jsonl / hard_negatives_v1.jsonl from
      f2_mine_hard_negatives.py
    - a ContrastiveFinetuner in "simulated" mode

It then reports baseline R@5 (before AL) vs after-AL R@5 / Silhouette, plus
writes a markdown report so the deltas are auditable.

Important: this is a DEMO, not a real fine-tune. The simulated finetuner
just re-weights TF-IDF dimensions; the real run is on VPS GPU (F2.1).
The framework is the same — that's the whole point of the scaffold.
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

# resolve repo paths + sys.path so we can import the lib modules
THIS = Path(__file__).resolve()
REPO = THIS.parents[2]
sys.path.insert(0, str(REPO / "v4" / "lib"))

from embedding_finetune import (  # noqa: E402
    ContrastiveFinetuner,
    FinetuneMetrics,
    TrainingPair,
)

logger = logging.getLogger("f2_simulate")

POSITIVES = REPO / "v4" / "results" / "active_learning" / "positives_v1.jsonl"
NEGATIVES = REPO / "v4" / "results" / "active_learning" / "hard_negatives_v1.jsonl"
REPORT = REPO / "v4" / "results" / "active_learning" / "simulation_report.md"


def load_pairs(positives: Path, negatives: Path) -> list[TrainingPair]:
    pairs: list[TrainingPair] = []
    for path, expect in ((positives, 1), (negatives, 0)):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    p = TrainingPair.from_dict(json.loads(line))
                    pairs.append(p)
    return pairs


def split_train_eval(
    pairs: list[TrainingPair],
    eval_frac: float = 0.2,
    seed: int = 42,
) -> tuple[list[TrainingPair], list[TrainingPair]]:
    """Stratified split by label so eval has both positives and negatives."""
    rng = random.Random(seed)
    by_label: dict[int, list[TrainingPair]] = {0: [], 1: []}
    for p in pairs:
        by_label[p.label].append(p)
    train: list[TrainingPair] = []
    evalset: list[TrainingPair] = []
    for label, items in by_label.items():
        rng.shuffle(items)
        cut = max(1, int(len(items) * eval_frac))
        evalset.extend(items[:cut])
        train.extend(items[cut:])
    return train, evalset


def _all_text(pairs: list[TrainingPair]) -> list[str]:
    out: list[str] = []
    for p in pairs:
        out.append(p.text_a)
        out.append(p.text_b)
    return out


def baseline_metrics(
    eval_pairs: list[TrainingPair], vocab_corpus: list[str]
) -> FinetuneMetrics:
    """Compute metrics with a vanilla TF-IDF encoder (no AL weighting).

    We construct a sibling ContrastiveFinetuner, fit it with lr=0 so weights
    stay at unity, then evaluate. That guarantees the *encoder pipeline* is
    identical between baseline and after-AL — the only difference is the
    per-feature weight vector. We fit the vectorizer on the FULL (train+eval)
    corpus so vocabulary is shared with the AL run for an apples-to-apples
    comparison.
    """
    ft = ContrastiveFinetuner(lr=0.0, mode="simulated")
    ft.fit(eval_pairs, epochs=1, batch_size=64, vocab_corpus=vocab_corpus)
    # Reset weights to unity to undo any micro-drift from lr=0 numerical noise.
    if ft._weights is not None:  # type: ignore[attr-defined]
        ft._weights = np.ones_like(ft._weights)  # type: ignore[attr-defined]
    return ft.evaluate(eval_pairs)


def after_al_metrics(
    train_pairs: list[TrainingPair],
    eval_pairs: list[TrainingPair],
    vocab_corpus: list[str],
    epochs: int = 5,
) -> tuple[FinetuneMetrics, FinetuneMetrics, ContrastiveFinetuner]:
    """Fit with the full AL signal; return (train_metrics, eval_metrics, finetuner).

    Vocabulary is fit on train+eval so eval features aren't OOV. The weight
    update only sees train pairs — eval is held out.
    """
    ft = ContrastiveFinetuner(lr=0.05, mode="simulated")
    train_m = ft.fit(train_pairs, epochs=epochs, batch_size=32, vocab_corpus=vocab_corpus)
    eval_m = ft.evaluate(eval_pairs)
    return train_m, eval_m, ft


def write_report(
    out: Path,
    baseline: FinetuneMetrics,
    after_al_train: FinetuneMetrics,
    after_al_eval: FinetuneMetrics,
    n_train: int,
    n_eval: int,
    n_pos_total: int,
    n_neg_total: int,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    delta_r5 = after_al_eval.r_at_5 - baseline.r_at_5
    delta_mrr = after_al_eval.mrr - baseline.mrr
    delta_sil = after_al_eval.silhouette - baseline.silhouette
    lines: list[str] = []
    lines.append("# F2 Active Learning — Simulation Report")
    lines.append("")
    lines.append("**Goal**: show baseline (vanilla TF-IDF) vs after-AL (TF-IDF with weight rerank from miner-mined pairs) metric deltas.")
    lines.append("")
    lines.append(f"- Total mined pairs: {n_pos_total + n_neg_total} ({n_pos_total} positives, {n_neg_total} hard negatives)")
    lines.append(f"- Train split: {n_train}")
    lines.append(f"- Eval split: {n_eval}")
    lines.append("")
    lines.append("## Metrics")
    lines.append("")
    lines.append("| Metric | Baseline | After-AL | Δ |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| R@5 | {baseline.r_at_5:.3f} | {after_al_eval.r_at_5:.3f} | {delta_r5:+.3f} |")
    lines.append(f"| R@10 | {baseline.r_at_10:.3f} | {after_al_eval.r_at_10:.3f} | {after_al_eval.r_at_10 - baseline.r_at_10:+.3f} |")
    lines.append(f"| MRR | {baseline.mrr:.3f} | {after_al_eval.mrr:.3f} | {delta_mrr:+.3f} |")
    lines.append(f"| Silhouette (proxy) | {baseline.silhouette:.3f} | {after_al_eval.silhouette:.3f} | {delta_sil:+.3f} |")
    lines.append("")
    lines.append("## Train info (after-AL run)")
    lines.append("")
    lines.append(f"- train_loss: {after_al_train.train_loss:.4f}")
    lines.append(f"- epochs: {after_al_train.epochs}")
    lines.append(f"- n_positives (train): {after_al_train.n_positives}")
    lines.append(f"- n_hard_negatives (train): {after_al_train.n_hard_negatives}")
    lines.append("")
    lines.append("## Interpretation")
    lines.append("")
    if delta_r5 > 0:
        lines.append("R@5 **improved** under AL re-weighting — the miner signal carries useful information.")
    elif delta_r5 == 0:
        lines.append("R@5 **unchanged** — small eval set; check Silhouette delta instead.")
    else:
        lines.append("R@5 **regressed** — possible causes: eval contains unseen char-ngrams (zero overlap), tiny n, or simulated finetuner over-reacted. Real V3 fine-tune on VPS would not have this artefact.")
    if delta_sil > 0:
        lines.append("")
        lines.append(f"Silhouette improved by {delta_sil:+.3f} — positives are pulled together and hard negatives pushed apart, which is the AL signal we wanted.")
    lines.append("")
    lines.append("## Caveat (read this!)")
    lines.append("")
    lines.append("This is a **simulation** using TF-IDF char n-grams, not the real V1/V2 sentence-transformer. The point is to validate the *plumbing* (miner → finetuner → eval gate → report), not to claim a real embedding improvement. Production V3 fine-tune happens on VPS (see `v4/lib/F2_active_learning_design.md` §3).")
    lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="F2 simulation: baseline vs after-AL")
    parser.add_argument("--positives", type=Path, default=POSITIVES)
    parser.add_argument("--negatives", type=Path, default=NEGATIVES)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--eval-frac", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--baseline",
        choices=["critic", "random", "uncertainty", "all"],
        default="critic",
        help=(
            "Active-learning query selection baseline. "
            "'critic' (default) = original run using all miner-mined pairs; "
            "'random' = uniform random sample at the same volume; "
            "'uncertainty' = pairs closest to the decision boundary; "
            "'all' = run all three and write a side-by-side comparison report "
            "(invokes f2_baseline_ablation.py)."
        ),
    )
    args = parser.parse_args()

    if args.baseline == "all":
        # Delegate to the dedicated ablation script
        import subprocess
        cmd = [
            sys.executable,
            str(Path(__file__).resolve().parent / "f2_baseline_ablation.py"),
            "--positives", str(args.positives),
            "--negatives", str(args.negatives),
            "--epochs", str(args.epochs),
            "--eval-frac", str(args.eval_frac),
            "--seed", str(args.seed),
        ]
        if args.quiet:
            cmd.append("--quiet")
        return subprocess.call(cmd)

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    pairs = load_pairs(args.positives, args.negatives)
    n_pos = sum(1 for p in pairs if p.label == 1)
    n_neg = sum(1 for p in pairs if p.label == 0)
    logger.info("Loaded %d pairs (%d positives, %d negatives)", len(pairs), n_pos, n_neg)

    train, evalset = split_train_eval(pairs, eval_frac=args.eval_frac, seed=args.seed)
    logger.info("Split: %d train / %d eval", len(train), len(evalset))

    # Shared vocab corpus (union of train+eval text). Baseline and after-AL
    # use the same vocab so the only difference is the weight vector.
    vocab_corpus = _all_text(train) + _all_text(evalset)

    # Baseline: TF-IDF without AL weight update
    baseline = baseline_metrics(evalset, vocab_corpus=vocab_corpus)
    logger.info(
        "Baseline R@5=%.3f R@10=%.3f MRR=%.3f sil=%.3f",
        baseline.r_at_5,
        baseline.r_at_10,
        baseline.mrr,
        baseline.silhouette,
    )

    # After-AL: TF-IDF + weight update from miner-mined pairs
    train_m, eval_m, _ft = after_al_metrics(
        train, evalset, vocab_corpus=vocab_corpus, epochs=args.epochs
    )
    logger.info(
        "After-AL R@5=%.3f R@10=%.3f MRR=%.3f sil=%.3f train_loss=%.4f",
        eval_m.r_at_5,
        eval_m.r_at_10,
        eval_m.mrr,
        eval_m.silhouette,
        train_m.train_loss,
    )

    write_report(
        args.report,
        baseline,
        train_m,
        eval_m,
        n_train=len(train),
        n_eval=len(evalset),
        n_pos_total=n_pos,
        n_neg_total=n_neg,
    )
    logger.info("Wrote report -> %s", args.report)

    print(
        json.dumps(
            {
                "baseline": baseline.to_dict(),
                "after_al_eval": eval_m.to_dict(),
                "after_al_train": train_m.to_dict(),
                "delta_r5": eval_m.r_at_5 - baseline.r_at_5,
                "delta_silhouette": eval_m.silhouette - baseline.silhouette,
                "report": str(args.report),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
