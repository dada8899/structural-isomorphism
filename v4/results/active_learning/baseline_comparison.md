# F2 Active Learning — Baseline Strategy Comparison

**Goal**: compare three query-selection strategies (random / uncertainty / critic) at the same labelling budget to test whether the critic-based selection adds value beyond a random or uncertainty baseline.

- Labelling budget per strategy: 65 pairs
- Train pool size: 65
- Eval split size: 15

## Vanilla baseline (no AL, unit TF-IDF weights)

- R@5:        0.400
- R@10:       0.600
- MRR:        0.461
- Silhouette: 0.032

## Strategy comparison

| Strategy | n_selected | n_pos | n_neg | R@5 | R@10 | MRR | Silhouette | Δ R@5 vs baseline |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **random** | 65 | 24 | 41 | 0.400 | 0.800 | 0.460 | 0.037 | +0.000 |
| **uncertainty** | 65 | 24 | 41 | 0.400 | 0.800 | 0.460 | 0.037 | +0.000 |
| **critic** | 65 | 24 | 41 | 0.400 | 0.800 | 0.460 | 0.037 | +0.000 |

## Interpretation

⚠️ Random sampling ties or beats critic-based selection (0.400 ≥ 0.400). At this budget the critic signal is **not** distinguishable from random labels — consider increasing budget, refining critic prompt, or using a stronger uncertainty model.

## Caveat

This is a simulation on TF-IDF char n-grams, not real V1/V2 sentence-transformer fine-tuning. The relative deltas between strategies are informative; absolute numbers are not directly comparable to the production V3 fine-tune. See `f2_simulate_active_learning.py` and `v4/lib/F2_active_learning_design.md` §3 for the real-run swap.

## Method

1. Load all mined pairs (positives + hard negatives) from `f2_mine_hard_negatives.py` output.
2. Train/eval split (stratified by label, seed=42).
3. For each strategy, select `budget` pairs from the train pool:
   - **random**: uniform random sample.
   - **uncertainty**: pairs whose unit-weight cosine similarity is closest to the median similarity (decision-boundary proxy).
   - **critic**: top-`budget` pairs ranked by (has_critic_verdict, confidence, weight).
4. Fit the same `ContrastiveFinetuner` (lr=0.05, simulated mode) on each selection.
5. Evaluate on the held-out eval split.
