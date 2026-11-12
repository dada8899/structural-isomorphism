# F2 — Active Learning Loop (Production Plan)

**Status**: scaffold shipped, GPU fine-tune deferred to F2.1.
**Owner**: W4-C subagent (this session) → operations owner TBD for F2.1.
**Related**: `v4/lib/active_learning_design.md`, `v4/lib/embedding_finetune.py`, `v4/scripts/f2_simulate_active_learning.py`.

## 1. Goal

Close the loop:

V4 critic (B3 ensemble) → curated REJECT/KEEP pairs → contrastive fine-tune of V1/V2 → V3 checkpoint → regenerate cached embeddings → F1 bridge serves expansion candidates with better recall → V4 critic sees fewer false positives → more reliable verdicts.

Net effect: every batch of human-or-LLM critique becomes embedding weight.

## 2. Data flow (mermaid)

```mermaid
flowchart TD
    subgraph "online (per V4 critic run)"
        A[Layer 3 candidate proposals] --> B[B3 ensemble critic]
        B -->|REJECT| R[(reject_verdicts.jsonl)]
        B -->|KEEP|   K[(keep_verdicts.jsonl)]
    end

    subgraph "offline batch (every N=50 verdicts)"
        R --> M[f2_mine_hard_negatives.py]
        K --> M
        M --> P[(positives_vN.jsonl)]
        M --> N[(hard_negatives_vN.jsonl)]
        P --> F[ContrastiveFinetuner.fit]
        N --> F
        BASE[(V2 base checkpoint)] --> F
        F --> CK[(V3 checkpoint)]
        CK --> E[ContrastiveFinetuner.evaluate]
        E --> RPT[(eval_report.md)]
    end

    subgraph "deploy gate"
        RPT --> G{accept?}
        G -- yes --> DEPLOY[regen kb_embeddings.npy<br/>swap models/structural-v1]
        G -- no --> ROLL[archive, keep V2]
    end

    DEPLOY --> F1[F1 bridge serves V3]
    F1 --> B
```

## 3. VPS deployment plan

**Target box**: existing VPS `43.156.233.71` (the box already holds the 782 MB V1 model + V2 cache; same path conventions).

**Hardware**: VPS is CPU-only today; SentenceTransformer fine-tune fits in CPU + 32 GB RAM for batch ≤ 32 + seq_len ≤ 128 — feasible but slow (~20 min/epoch on 1.5 k pairs). For the production loop we provision a temporary GPU box (rent ~$2/h spot) when batches exceed ~5 k pairs.

**Directories** (VPS-side):

```
/root/Projects/structural-isomorphism/
├── models/
│   ├── structural-v1/                  # frozen V1 (768d, 782 MB)
│   ├── structural-v2/                  # frozen V2
│   └── structural-v3/                  # produced by F2 fine-tune  ⟵ NEW
├── data/
│   └── kb-5000-merged.jsonl
├── v4/results/
│   ├── active_learning/
│   │   ├── positives_v3.jsonl
│   │   ├── hard_negatives_v3.jsonl
│   │   ├── eval_report_v3.md
│   │   └── ckpt_v3/                    # transient training artefacts
└── web/data/
    ├── kb_v2_embeddings.npy
    └── kb_v3_embeddings.npy            # regenerated post-deploy
```

**Cron / batch trigger** (initially manual, eventually weekly):

```
# /etc/cron.d/structural-iso-active-learn (proposed)
0 3 * * 0 root /root/Projects/structural-isomorphism/scripts/active_learning_weekly.sh
```

That weekly script:
1. Pulls latest `B3_ensemble_review.jsonl` from main.
2. Runs `f2_mine_hard_negatives.py` to refresh `positives_vN+1.jsonl` / `hard_negatives_vN+1.jsonl`.
3. If # new pairs ≥ 50: kick off `embedding_finetune.py` with V_{N} as base, produce V_{N+1}.
4. Evaluate; auto-approve and swap *only if* every gate in §7 of `active_learning_design.md` passes.
5. Push commit (artifacts only, model checkpoints gitignored — pushed to private S3 bucket).
6. Notify via daily-summary cron.

**Monitoring**:
- Training loss curve → `v4/results/active_learning/runs/<ckpt>/loss.png`
- Per-epoch holdout R@5 → same dir, `eval.jsonl`
- Wall-clock per epoch → systemd journal, parseable
- If R@5 drops > 5 pp mid-training → auto-abort the run

## 4. Base model checkpoint location

- V1: `models/structural-v1/` (sentence-transformer, 768d, miniLM-style backbone, fine-tuned on 1217 cross-domain pairs in 2025-Q4).
- V2: `models/structural-v2/` (V1 + 3017 additional pairs in 2026-Q1).
- V3 (produced by F2): branched from V2.

We never re-train from scratch; F2 is always a small delta on V_{latest}.

## 5. Training data scale per round

| Source | Per round (today) | Per round (1-year target) |
|---|---|---|
| KEEP positives (pairs within KEEP class) | ~50 | ~500 |
| REJECT hard negatives (pairs within REJECT class) | ~30 | ~300 |
| Augmented positives (KB-NN ≥ 0.85 + LLM-verified) | 0 | ~1000 |
| Augmented hard negatives (KB-NN within REJECT-class context) | 0 | ~500 |
| **Total** | **~80** | **~2300** |

Small numbers are OK because we only fine-tune (not pre-train). Even 80 high-quality pairs shift the geometry meaningfully when the model already has a ~5 k-pair head start.

## 6. Loss function

InfoNCE / SimCSE with hard negatives (see §6 of `active_learning_design.md`).

**Hyperparameters** (defaults; sweep in §8 below):
- learning rate: 1e-5 (cosine schedule)
- batch size: 32 (8 query · 4 in-batch neg expansion)
- temperature τ: 0.05
- epochs: 3
- per-positive K mined hard negatives: 4
- weight decay: 0.01
- max sequence length: 128 tokens

## 7. Hyperparameter search (one-time, before production)

We will run a small (4-way) grid before locking the recipe:

| Knob | Values |
|---|---|
| learning rate | {5e-6, 1e-5, 2e-5} |
| epochs | {2, 3, 5} |
| temperature | {0.03, 0.05, 0.07} |
| K hard negatives per positive | {2, 4, 8} |

Pick the combination that maximises Cross-domain R@5 on the holdout split while not regressing R@5 on in-domain. Lock the recipe; future rounds only re-tune if eval gates ever fail (signal of distribution shift).

## 8. F1 handshake

F1 (`v4/lib/embedding_bridge.py`) is **version-agnostic** by design: it loads whatever `web/data/kb_<version>_embeddings.npy` we point it at via the `version=` argument. F2's deploy step *replaces those npy files in place* (after the eval gate passes). F1 picks up the new geometry on next process boot — zero code change, zero migration.

For zero-downtime: deploy step (a) writes `kb_v3_embeddings.npy` alongside V2's, (b) flips a config feature flag `EMBEDDING_VERSION=v3`, (c) F1 reads the flag at startup. Rollback = flip the flag back.

## 9. Q4 2026 / Q1 2027 timeline

| Quarter | Milestone | Acceptance |
|---|---|---|
| 2026-Q4 | F2.0 (this session): scaffold + miner + simulation + tests | tests green, PR merged |
| 2026-Q4 (Nov) | F2.1: VPS provisioning + first real V3 fine-tune on 80-pair seed | V3 deployed if eval gates pass; otherwise rollback documented |
| 2026-Q4 (Dec) | F2.2: hyperparam sweep + recipe lockdown | sweep report committed; recipe in `embedding_finetune.py` defaults |
| 2027-Q1 (Jan) | F2.3: weekly cron live + monitoring + Slack/feishu notifier | cron green 4 weeks in a row, ≥1 successful auto-deploy |
| 2027-Q1 (Feb) | F2.4: augmented training data via KB-NN harvesting | training set ≥ 500 pairs/round |
| 2027-Q1 (Mar) | F2.5: SPLIT verdict subset mining | critic schema extended; SPLIT contributes train pairs |

## 10. Risk register

| Risk | Mitigation |
|---|---|
| Overfit to LLM critic's biases | hold out 20% of pairs; auto-abort if cross-domain R@5 regresses |
| LLM-confidence calibration drift | recompute confidence-to-weight curve every 3 rounds against B2 calibration set |
| Catastrophic forgetting on V2 strengths | small LR + low epochs + always branch from V2 (not V_{N}) for the first 4 rounds |
| Hard-negative collisions with future KEEP labels | mine timestamp + verdict version; expire pairs older than 6 months |
| Cost runaway (GPU rental) | budget cap per round = $5; abort if epoch wall-clock × LR-schedule predicts > cap |

## 11. Out of scope

- Online (per-query) fine-tune
- Multi-modal embedding (text + equation LaTeX)
- Auto-curation of REJECT pairs by a *second* LLM critic (we keep human-curated B3 as the gold signal)

## 12. Open questions (carry to next session)

1. Should we keep V3 alongside V2 indefinitely (parallel cache, A/B routing) or hard-cut over once gates pass?
   - Tentative: keep both for 4 weeks, then archive V2.
2. Threshold for "enough new verdicts to retrain"?
   - Tentative: 50 new B3 verdicts since last checkpoint.
3. Notification channel for auto-deploy success / failure?
   - Tentative: feishu bot to the OpenClaw channel (already wired).
