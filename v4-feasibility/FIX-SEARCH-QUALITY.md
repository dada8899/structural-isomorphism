# FIX-SEARCH-QUALITY — Raw Query Recall Upgrade

**Date**: 2026-04-13
**Scope**: `beta.structural.bytedance.city` `/api/search` raw (non-LLM) path
**Constraint**: no embedding retraining; work within existing infra

## Options implemented

All three: **A** (BM25 hybrid) + **B** (StructTuple dynamics boost) + **C** (domain collapse guard).

- **A — Hybrid BM25 + embedding**: `rank_bm25` + `jieba cut_for_search` tokenization over `name name description` (name doubled for weighting). Both scores min-max normalized to [0,1], fused `0.45*bm25 + 0.55*emb`.
- **B — StructTuple boost**: loads `v3/results/kb-expanded-struct.jsonl` (4443 records) keyed by `phenomenon_id`. Rule-based trigger table maps query phrases (延迟/阈值/反馈/崩盘/共识/相变/传播/振荡 and English equivalents) to `dynamics_family` and `feedback_topology` tags. Matching phenomena get `+0.10` on the fused score.
- **C — Domain collapse guard**: MMR-lite. Pull a candidate pool of `top_k * 4` (min 40), then walk ranked indices capping any single domain at 2 within the top-5 window; surplus pushed to tail.

Final display score scaled `10*fused + 6` so the frontend bars keep their ~[6, 17] visual proportions (legacy code expected raw dot-products around that range).

## File changes

- `web/backend/services/search_service.py` — full rewrite: new helpers `_tokenize` (L55), `_infer_dynamics_families` (L76), `_minmax` (L91), `_fused_scores` (L215), `_domain_guard` (L252), rewritten `search()` (L284). Constructor (L96) now builds BM25 index (L138) and loads StructTuple file (L151). Backup kept at `search_service.py.bak`.
- Dependencies installed on VPS: `rank_bm25==0.2.2`, `jieba==0.42.1`.
- Service restarted via `systemctl restart structural-web`.

Startup log confirms: `BM25 index built (4443 docs)` + `Loaded 4443 StructTuple records`.

## Before/after on 15 test queries (top-5 avg relevance, 1-5 scale)

| # | Query | Before | After | Δ |
|---|---|---|---|---|
| 1 | 为什么创业公司早期更容易创新 | 1.0 | 4.0 | +3.0 |
| 2 | 延迟反馈的系统 | 3.2 | 3.6 | +0.4 |
| 3 | 阈值突变 | 3.8 | 4.4 | +0.6 |
| 4 | 正反馈循环导致失控 | 4.0 | 4.8 | +0.8 |
| 5 | 相变 | 2.8 | 4.8 | +2.0 |
| 6 | 为什么流言传得那么快 | 3.2 | 3.6 | +0.4 |
| 7 | 为什么市场会崩盘 | 2.0 | 4.2 | +2.2 |
| 8 | 生态系统的临界点 | 2.8 | 4.0 | +1.2 |
| 9 | 神经元如何学习 | 1.0 | 3.6 | +2.6 |
| 10 | 为什么有些语言会死亡 | 1.2 | 3.4 | +2.2 |
| 11 | `a` | 1.0 | 1.0 | 0 |
| 12 | 为什么 | 1.0 | 1.0 | 0 |
| 13 | superconductor phase transition | 1.0 | 1.4 | +0.4 |
| 14 | 量子纠缠的非定域性 | 1.0 | 4.8 | +3.8 |
| 15 | 团队规模扩大后沟通成本反而增加 | 1.4 | 3.0 | +1.6 |

**Average: 2.09 → 3.44 (+1.35, +65%).** Exceeds the 3.2 target; well above the +35% bar.

Highlights:
- **创业早期创新**: now returns "竞争对手进入的临界规模防御门槛" / "早期创业公司的首个机构客户价值" / "创业公司的J曲线增长" (was Slepian-Wolf / immunology / literary theory).
- **市场崩盘**: exact-name hit "市场崩盘" at #1 plus "NFT市场泡沫-崩溃周期" / "相关性崩溃" / "止损流动性螺旋" (was ASLR / 公共领域殖民 / 档案沉默).
- **相变**: all 5 hits are real phase-transition phenomena across materials/statistical mechanics (was 仪式遗存惯性 / 压力测试 noise).
- **生态系统的临界点**: top-3 all ecological tipping phenomena (was 地基承载力 / 最低效率规模).
- **量子纠缠的非定域性**: top-5 are all actual quantum-entanglement phenomena (was 光学涡旋 / 诱饵选项中庸 / 格点QCD noise).
- **流言传播**: "谣言传播" #1, "谣言传播的SIR模型" #4 — StructTuple cascade family boost worked.

## Latency impact

| Path | Before | After |
|---|---|---|
| Avg wall-clock (15 queries, client-side HTTPS) | ~0.85 s | ~0.76 s |
| Max | 1.06 s | 0.96 s |
| Min | 0.66 s | 0.66 s |

No regression. BM25 scoring on 4443 docs with jieba tokenization is ~5-10 ms per query; dominated by existing embedding dot-product. First-request jieba cache warmup is one-shot at startup.

Memory footprint: +~15 MB (BM25 index + 4443 StructTuple records), total service RSS 419 MB.

## Regressions / limitations

- **Pure English queries** ("superconductor phase transition") still under-perform because jieba emits whole English tokens and KB descriptions are Chinese — BM25 contributes zero, so the result is embedding-only, same as before. Fix: add `opencc` or pre-translate English heads, or maintain an English surface-form index. Not done here.
- **Degenerate queries** ("a", "为什么") unchanged — correct behavior, these are caught by the LLM assessment gate.
- **Short keyword "相变"** now dominated by materials/chemistry phase-transition phenomena — the domain guard correctly kept them under cap (5 results, 3 distinct sub-domains).
- Display score band changed from legacy ~[6, 18] to scaled ~[6, 17]; frontend bars auto-scale so no UI change needed.

## Rollback

```
ssh vps "cp /root/Projects/structural-isomorphism/web/backend/services/search_service.py.bak \
             /root/Projects/structural-isomorphism/web/backend/services/search_service.py \
         && systemctl restart structural-web"
```

## Test artifacts

- `/tmp/baseline_test.py` — 15-query HTTPS probe driver
- `/tmp/after_results.jsonl` — post-deploy top-5 dump
