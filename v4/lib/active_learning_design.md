# F2 — Active Learning Data Flow

**Status**: scaffold (session #3, W4-C) — design + miner + simulation + interface. Real V1/V2 fine-tune deferred to F2.1 (VPS GPU run).
**Owner**: W4-C subagent
**Related**: `v4/lib/embedding_finetune.py`, `v4/lib/F2_active_learning_design.md`, `v4/lib/embedding_bridge.py` (F1)

## 1. Goal

Close the loop between V4 critic verdicts (Layer 3 KEEP/REJECT/SPLIT on candidate classes) and the V1/V2 embedding model that powers F1 candidate expansion. Today, the model is frozen — V4 only *consumes* its similarity signal. F2 makes the model *learn* from V4 by harvesting REJECT verdicts as hard negatives and KEEP verdicts as positives, then contrastive-fine-tuning the embedding so future candidate-class expansion (via F1 bridge) yields better recall.

This is a **positive feedback loop**: better critic verdicts → better embedding training set → better F1 candidates → better critic verdicts (because the critic has fewer false positives to wade through).

## 2. Data flow

```
Layer 3 critic                          V1/V2 embedding model
   |                                            |
   | REJECT verdicts (B3 ensemble)              |
   |   - class_id                               |
   |   - phenomenon_pair                        |
   |   - rejection_reason                       |
   |   - confidence                             |
   v                                            |
[hard_negative_pool.jsonl]                      |
   |                                            |
   | sample N hard negatives per epoch          |
   |    + N positive pairs (KEEP)               |
   v                                            v
[training_batch] -----------------> [contrastive fine-tune]
                                            |
                                            v
                                   [new embedding weights]
                                            |
                                            v
[Layer 3 candidate expansion (F1 bridge)] <-+
```

The loop is *bounded*: each round of fine-tune produces a checkpoint (V3, V4, …). We do not re-tune online; instead we ship a new checkpoint per V4 critic batch (e.g. after every 50 new B3 verdicts), evaluate offline, and only deploy if R@5 / Silhouette / class-purity metrics all improve.

## 3. Sources (concrete files)

| Signal | Source file | What we extract |
|---|---|---|
| REJECT verdicts | `v4/results/B3_taxonomy_v2.jsonl` + `v4/results/B3_ensemble_review.jsonl` | classes with `b3_consensus="REJECT"` or `final_verdict` containing `REJECT` — their positive_examples were *wrongly* clustered, so any pair of those examples becomes a hard negative |
| KEEP verdicts | same | classes with `final_verdict` containing `KEEP` — any pair within positive_examples is a positive |
| Class definitions | `v4/taxonomy/classes/*.yaml` | source of `positive_examples` per class |
| Existing KB | `data/kb-5000-merged.jsonl` | 4475 phenomena (text + domain + description) for richer hard-negative mining (later) |

We deliberately use *only* B3 ensemble verdicts (not B1, not single-model B3) for the training signal: ensemble cuts down stochastic LLM disagreement and gives a `b3_avg_confidence` field we use as a per-pair training weight.

## 4. Hard-negative semantics

A REJECT verdict on class X means the LLM critic believes X's `positive_examples` do **not** share a universality class. So for every pair `(a, b)` drawn from X's positives, the contrastive loss should push `embed(a)` and `embed(b)` **apart** — that's a hard negative because the original V1/V2 model (or the Layer 3 LLM proposer) *thought* they were close.

A KEEP verdict on class Y means Y's `positive_examples` *do* share a class. So pairs `(a, b)` within Y's positives are positives.

A SPLIT verdict means *some subsets* of Y's positives share a class but not all of them. We could in principle mine intra-subset positives + inter-subset negatives if SPLIT verdicts came with subset annotations — currently they do not, so we treat SPLIT as **excluded** from training (neither positive nor negative).

## 5. Weighting

Each training pair carries a `weight ∈ (0, 1]` derived from `b3_avg_confidence`:
- weight = 1.0 if confidence ≥ 0.9 (strong verdict)
- weight = 0.7 if confidence ∈ [0.75, 0.9)
- weight = 0.4 if confidence ∈ [0.6, 0.75)
- pair dropped if confidence < 0.6 (too noisy to learn from)

This caps the influence of low-confidence verdicts on the embedding without throwing them away entirely.

## 6. Loss function (InfoNCE with hard negatives)

For a batch of size B with B positives `(a_i, b_i)` and per-positive `K` hard negatives `n_i^1, … n_i^K`, the per-example InfoNCE loss is:

```
L_i = -log[ exp(sim(a_i, b_i) / τ) / Σ_j exp(sim(a_i, *) / τ) ]
```

where the denominator sums over `b_i` plus the in-batch negatives plus the `K` mined hard negatives. We use τ = 0.05 (standard SimCSE default).

Total loss = mean(L_i · weight_i).

## 7. Evaluation

Offline metrics computed on a held-out 20% of KEEP-class positives (never seen at training time):
- **R@5**: for each query phenomenon, % of true class-mates in top-5 NN
- **R@10**: same, top-10
- **MRR**: mean reciprocal rank of first true class-mate
- **Silhouette**: clustering quality on the labelled holdout
- **Cross-domain transfer R@5**: same as R@5 but restricted to NN with `domain ≠ query.domain`

Acceptance bar (must meet **all** to deploy V3 checkpoint):
- R@5 ≥ V2's R@5 (no regression on already-good metric)
- Cross-domain R@5 strictly improves by ≥ 2pp
- Silhouette improves or holds (Δ ≥ -0.02)
- Critic agreement rate on top-100 NN expansions improves (separate online check)

## 8. Files this design produces

| File | Purpose |
|---|---|
| `v4/lib/embedding_finetune.py` | `ContrastiveFinetuner` class — scaffold for VPS run |
| `v4/lib/active_learning_design.md` | this doc |
| `v4/lib/F2_active_learning_design.md` | longer planning doc (VPS deploy, hyperparam search, Q4/Q1 timeline) |
| `v4/scripts/f2_mine_hard_negatives.py` | extract `(positives.jsonl, hard_negatives.jsonl)` from B3 outputs |
| `v4/scripts/f2_simulate_active_learning.py` | end-to-end demo with TF-IDF baseline + rerank |
| `v4/results/active_learning/positives_v1.jsonl` | mined positives (label=1) |
| `v4/results/active_learning/hard_negatives_v1.jsonl` | mined hard negatives (label=0) |
| `v4/results/active_learning/simulation_report.md` | baseline vs after-AL R@5 / Silhouette deltas |
| `v4/tests/sanity/test_active_learning.py` | miner correctness + finetuner interface + simulation monotonicity |

## 9. Interface with F1

After a successful V3 fine-tune (on VPS), the new checkpoint replaces `models/structural-v1/` and the cached `kb_embeddings.npy` is regenerated with the new model. F1's `EmbeddingBridge` then transparently uses the new geometry — no API change needed. The handshake is purely **on-disk**: checkpoint + npy cache.

## 10. Out of scope here

- Actual GPU fine-tune (requires VPS provisioning, see `F2_active_learning_design.md` §3)
- Embedding endpoint over HTTP (F1.1)
- SPLIT-verdict subset mining (needs richer critic output schema)
- Per-domain hard-negative balancing (Phase 2)
