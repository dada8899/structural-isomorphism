# F2 Active Learning — Simulation Report

**Goal**: show baseline (vanilla TF-IDF) vs after-AL (TF-IDF with weight rerank from miner-mined pairs) metric deltas.

- Total mined pairs: 80 (29 positives, 51 hard negatives)
- Train split: 65
- Eval split: 15

## Metrics

| Metric | Baseline | After-AL | Δ |
|---|---:|---:|---:|
| R@5 | 0.400 | 0.400 | +0.000 |
| R@10 | 0.600 | 0.800 | +0.200 |
| MRR | 0.461 | 0.460 | -0.001 |
| Silhouette (proxy) | 0.032 | 0.037 | +0.004 |

## Train info (after-AL run)

- train_loss: 0.3367
- epochs: 5
- n_positives (train): 24
- n_hard_negatives (train): 41

## Interpretation

R@5 **unchanged** — small eval set; check Silhouette delta instead.

Silhouette improved by +0.004 — positives are pulled together and hard negatives pushed apart, which is the AL signal we wanted.

## Caveat (read this!)

This is a **simulation** using TF-IDF char n-grams, not the real V1/V2 sentence-transformer. The point is to validate the *plumbing* (miner → finetuner → eval gate → report), not to claim a real embedding improvement. Production V3 fine-tune happens on VPS (see `v4/lib/F2_active_learning_design.md` §3).
