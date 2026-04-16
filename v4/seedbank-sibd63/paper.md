# SIBD-63: A Seed Bank of 63 A-Level Cross-Domain Structural Isomorphism Discoveries with Shared Equations, Variable Mappings, and Publication-Ready Execution Plans

**Author.** Wan Qinghui (万庆徽), Structural Isomorphism Project.
**Affiliation.** Independent researcher. https://structural.bytedance.city
**Date.** 2026-04-16
**Version.** Companion dataset paper for SIBD-63 v1.0
**License.** CC-BY-4.0

---

## Abstract

We release **SIBD-63**, a curated dataset of 63 cross-domain structural isomorphism discoveries produced by three independent AI-assisted pipelines operating on a 4,443-phenomenon natural-language knowledge base. By construction the pipelines (V1 broad-recall embedding, V2 strict-precision embedding, V3 StructTuple + LLM rerank) have zero overlap; each contributes 24, 19, and 20 records respectively. Each record pairs two phenomena from disjoint scientific domains that share the same underlying mathematical structure, and is annotated with a proposed shared equation (for 20 records) or dynamical family, a variable mapping (20 records), a suggested target journal, a literature-gap assessment, and a step-by-step empirical execution plan. Records span 48 domain labels across geology, condensed-matter physics, ecology, molecular biology, finance market microstructure, decentralized finance, behavioral economics, civil and power-grid engineering, pharmacology, and more. All 63 records are rated A by a weighted five-dimensional scoring pipeline (novelty, rigor, feasibility, impact, writability); all are marked solo-feasible. We position SIBD-63 as a **seed bank for empirical follow-up papers**: domain experts can pick a seed matching their expertise and convert it into a publishable paper in 3-6 months, with the originator offered a standing author-order on resulting publications. The dataset is released under CC-BY-4.0 with a companion reproduction pipeline; code and trained V1/V2 embedding models are separately available on GitHub and Hugging Face.

---

## 1. Introduction

Cross-domain analogies — the observation that two superficially unrelated systems share the same mathematical structure — are among the most productive patterns in the history of science. Hamilton's optico-mechanical analogy unlocked quantum mechanics a century later; Dirac's recognition of the commutator/Poisson-bracket correspondence unified classical and quantum dynamics; and Anderson's observation that superconductivity, superfluidity, and Higgs-mechanism symmetry breaking share a common structure remade both condensed-matter and particle physics.

The bottleneck for systematic cross-domain discovery has always been human domain coverage. An individual researcher expert in turbulence is unlikely to spot the exact analogy with a phenomenon in synthetic biology; a behavioral economist is unlikely to notice an isomorphism with a geological process. Large language models combined with retrieval over structured phenomenon descriptions now make it possible to search this space at scale.

The Structural Isomorphism Project is an independent research program whose goal is to turn cross-domain analogy from an opportunistic craft into a systematic discovery pipeline. The project released three independent pipelines (V1 / V2 / V3) that together surfaced 63 A-level candidate isomorphisms from a 4,443-phenomenon knowledge base. The present paper documents the consolidated dataset — SIBD-63 — and the companion metadata that supports downstream empirical follow-up.

## 2. Data and methods

### 2.1 Source pipelines

**V1 (broad-recall embedding).** A Chinese sentence-transformer (`text2vec-base-chinese`) was fine-tuned with contrastive loss on 1,214 positive cross-domain isomorphism pairs (the SIBD-1214 training set, separately distributed). The model was then used to embed all 4,443 phenomena; all pairwise cosine similarities were computed; pairs above a permissive threshold (339,913 pairs) were filtered by a 50-batch Opus judge, then deep-analysed, yielding 272 grade-A candidates of which 24 reached tier-1 after a final single-curator pass.

**V2 (strict-precision embedding).** An expanded training set (5,689 positive pairs, SIBD-5689-expanded) with harder negatives was used to train a tighter model (Silhouette 0.55, R@5 96%). Applied to the same KB, it produced 4,533 candidate pairs (75× tighter than V1), from which a strict-screening LLM cascade (94 five-scores + 667 four-scores) yielded 94 deep-analysis candidates and 19 A-rated records.

**V3 (StructTuple + LLM rerank).** Each phenomenon was first extracted into a `StructTuple` (dynamics_family enum, canonical_equation, characteristic_timescale, spatial_extent, ...) by Kimi-K2 (9 shards) and verified by Opus (12 chunks), yielding 4,443 structured representations of which 2,625 matched a controlled-vocabulary dynamics family. A rule-based matcher imposed dynamics-family-equal + specificity + timescale-gate + equation-quality constraints, producing 1,000 candidate pairs. Each was then rated 1-5 by one of 10 parallel Opus reranker agents that also produced `shared_equation` and `variable_mapping` strings. 203 pairs scored ≥ 4 (5.5% pure-5). Deep-analysis in 10 parallel agents graded 20 records A and 34 as B+.

**Zero-overlap property.** The three pipelines use different similarity signals and different scoring functions. Empirically the V1-V2, V1-V3, and V2-V3 overlaps are all zero at the A-rated tier. The 63-record consolidation therefore preserves genuinely distinct discoveries from three independent angles.

### 2.2 Consolidation and schema

The three A-rated jsonl outputs were merged into a single JSON-per-line file (SIBD-63.jsonl), with records from each pipeline tagged by a `pipeline` field. A superset schema (SIBD-63-schema.json) documents every field with type, enum constraints, and descriptions. Records from pipelines that did not compute a particular field leave that field as empty string or null.

Fields fall into five groups:
- **Identity** (seed_id, pipeline, rank_in_pipeline)
- **Pair** (a_name, a_domain, b_name, b_domain)
- **Structural content** (shared_equation, variable_mapping, equations, isomorphism_depth, isomorphism_confidence)
- **Publishability** (paper_title, target_venue, literature_status, practical_value, risk, blocking_mechanisms, execution_plan, time_estimate, solo_feasible, impact_scope, impact_detail, final_score, one_line_verdict, rating)
- **Transformation analysis** (transformation_primitives, transformation_depth, is_deep)

### 2.3 Scoring

All 63 records carry a weighted five-dimensional `final_score` with the following dimension weights (SIBD-weighting v2m-final):
- novelty (N): 25%
- rigor (R): 30%
- feasibility (F): 15%
- impact (I): 10%
- writability (Wr): 25%

The dominant contributions to `final_score` come from rigor and writability, reflecting the project's bias toward *empirically-testable and paper-ready* analogies over speculatively interesting ones. The A-rating threshold corresponds roughly to final_score ≥ 7.5.

## 3. Dataset characteristics

### 3.1 Size and score distribution

63 records, mean `final_score` 8.17 (range 7.5–9.0). Pipeline split: V1 = 24 (38.1%), V2 = 19 (30.2%), V3 = 20 (31.7%).

### 3.2 Domain coverage

48 distinct domain labels. The most frequent are:

| Domain | Count |
|---|---|
| 金融市场微观结构 (financial-market microstructure) | 5 |
| 加密货币/DeFi | 5 |
| 生态学 (ecology) | 4 |
| 区块链/Web3 | 4 |
| 高分子化学 (polymer chemistry) | 4 |
| 行为经济学 (behavioral economics) | 3 |
| 金融 (finance) | 3 |
| 保育生物学 (conservation biology) | 2 |

The long tail covers geophysics, astrophysics, molecular biology, immunology, materials science, civil engineering, power systems, traffic engineering, pharmacology, oncology, military strategy, sociology, and more.

### 3.3 Literature-gap assessment

The `literature_status` field carries one of: `unexplored`, `partial`, `established`. The dataset is biased toward unexplored and partial records (A-rating requires novelty). Users who need strictly-never-published isomorphisms should filter to `literature_status ∈ {unexplored, 未有先例, 未发表}`.

### 3.4 Examples of high-impact records

- **V2 rank-1** (score 8.6): *permafrost methane delayed feedback × extinction debt*, unified under `dx/dt = f(x(t-τ)) - μx(t)`. Target venue: Nature Climate Change perspective.
- **V2 rank-2** (score 8.5): *semiconductor laser relaxation oscillation × stablecoin anchoring mechanism*. Second-order damped oscillator; Terra/UST crash data available.
- **V3 rank-1** (score 8.6): *earthquake static stress triggering × DeFi liquidation cascades*, unified via Coulomb-stress-transfer equation. Target venue: Nature Physics / PNAS. **Empirically validated in Layer 5 Phase 3 of the companion project; see** `/paper/soc-defi-2026-04-15`.
- **V3 rank-5** (score 8.2): *intersection gridlock × power-grid cascading failures* via Motter-Lai cascade equation.
- **V3 rank-6** (score 8.5): *grape sunburn × coral bleaching* via NOAA Degree-Heating-Weeks indicator transfer.

## 4. Known limitations

1. **Single-curator bias**: the final A-rating was assigned by the first author. No inter-rater agreement study was performed.
2. **Chinese-language bias**: both the phenomenon corpus and the LLM rationales are Chinese-first. English target-journal names and equations are generally accurate but not uniformly proof-read.
3. **Literature-status is LLM-assessed**, not a systematic meta-review. Several records labeled "unexplored" may have partial prior art not surfaced by the LLM.
4. **Not all records have shared_equation**: only V3's 20 records provide an explicit LaTeX-style shared equation. V1 and V2 describe the structure in natural language.
5. **No empirical validation of individual records** is included in this dataset. The companion Layer 5 phases empirically validate a subset of the SOC-class records (V3 ranks 1, 4, 5, 9 and related) against geological / financial / DeFi / neural data, but 59 of the 63 records remain empirically open.
6. **Domain labels are uncontrolled**: 48 labels is expressive but means two records marked "加密货币/DeFi" and "区块链/Web3" could be comparable but group-filtered as different.

## 5. Use cases

### 5.1 As a seed bank for empirical papers

The intended primary use. Domain experts select a seed whose phenomena fall in their expertise, follow the `execution_plan`, and publish. The first author stands as last / senior author per the collaboration norms described in the README.

### 5.2 As a benchmark for cross-domain similarity systems

The 63 A-rated pairs plus the ~4,000 non-pair phenomena form a benchmark for any new cross-domain retrieval method. Recall-at-k (R@k) and MRR on the 63 pairs provide a discriminating test since the pairs are by construction far apart in natural-language surface similarity.

### 5.3 As training data for next-generation V4/V5 models

The 63 positive pairs + 5,689 V2-training positives + 4,443 phenomenon descriptions + variable-mapping annotations give substantial training signal for fine-tuning next-generation cross-domain representation models.

### 5.4 As a teaching resource

The one-line-verdict + full-analysis fields give worked examples of how to formalize a cross-domain analogy with variable mapping and shared equation.

## 6. Reproducibility

The dataset is rebuildable from source by a single command:

```bash
cd structural-isomorphism
python3 v4/seedbank-sibd63/scripts/build.py
```

The build script consumes the three pipeline outputs committed to the repository and produces both the consolidated `SIBD-63.jsonl` and the formal `SIBD-63-schema.json`. No third-party dependencies beyond the Python standard library. Full pipeline code (embedding training, StructTuple extraction, LLM rerank) is separately committed in the `/results/`, `/v3/`, and `/scripts/` subtrees of the source repository.

## 7. Data and code availability

- **Dataset**: Zenodo DOI 10.5281/zenodo.19615170 (this record).
- **Source code & pipelines**: https://github.com/dada8899/structural-isomorphism
- **V1 / V2 embedding models**: https://huggingface.co/qinghuiwan/structural-isomorphism-v1 · https://huggingface.co/qinghuiwan/structural-isomorphism-v2-expanded
- **Companion Layer 5 empirical validations**: `/paper/soc-earthquake-2026-04-15`, `/paper/soc-stockmarket-2026-04-15`, `/paper/soc-defi-2026-04-15`, `/paper/soc-neural-2026-04-16`, `/paper/soc-null-2026-04-16`

## 8. Citation

```bibtex
@dataset{wan2026sibd63,
  author    = {Wan, Qinghui},
  title     = {SIBD-63: A Dataset of A-Level Cross-Domain Structural
               Isomorphism Discoveries with Shared Equations and
               Variable Mappings},
  year      = 2026,
  publisher = {Zenodo},
  version   = {1.0},
  doi       = {10.5281/zenodo.19615170},
}
```

## References

- Wan, Q. (2026). *Structural Isomorphism Project: V1-V4 Methodology and Results*. Project technical document, https://structural.bytedance.city
- Wan, Q. (2026). *Recovering SOC Universality on a Global Earthquake Catalog*. Layer 5 Phase 1 companion paper.
- Wan, Q. (2026). *Cross-Domain SOC Validation: Inverse Cubic Law and Omori Decay on S&P 500 Daily Returns*. Layer 5 Phase 2 companion.
- Wan, Q. (2026). *Cross-Protocol SOC Universality in DeFi Liquidation Cascades: 43,065 Events Across Aave V2, Compound V2, and MakerDAO*. Layer 5 Phase 3 companion.
- Wan, Q. (2026). *Criticality Without Mean-Field SOC: Neural Avalanches on Task-Active Mouse Cortex*. Layer 5 Phase 4 companion.
- Clauset, A., Shalizi, C. R. & Newman, M. E. J. (2009). "Power-law distributions in empirical data." *SIAM Review* **51**, 661.
