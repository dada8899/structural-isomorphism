# SIBD-63 Dataset Card

## Overview

**SIBD-63** (Structural Isomorphism Benchmark Dataset, 63 A-level candidates) is a curated dataset of cross-domain structural isomorphism discoveries. Each record pairs two phenomena from disjoint scientific domains that share the same underlying mathematical structure.

## Dataset Details

### Dataset Sources

Three independent discovery pipelines, by construction zero-overlap:

1. **V1 pipeline** (broad-recall embedding)
   - Contribution: 24 tier-1 records
   - Training data: 1,214 positive pairs (SIBD-1214)
   - Model: `text2vec-base-chinese` fine-tuned with contrastive loss
   - Strength: casts the widest net; catches CS/algorithm × engineering-system analogies
   
2. **V2 pipeline** (strict-precision embedding)
   - Contribution: 19 A-level records
   - Training data: 5,689 positive pairs (SIBD-5689-expanded)
   - Evaluation: Silhouette 0.55, R@5 96%
   - Strength: captures dynamics/critical-phenomena universality
   
3. **V3 pipeline** (StructTuple + LLM rerank)
   - Contribution: 20 A-level records
   - Method: Kimi + Opus extraction of dynamics_family / canonical_equation / timescale, then Structural matcher (field-hard-constraint + specificity + timescale gate) → 1000 candidate pairs → 10 parallel Opus reranker agents (pairwise scoring 1-5 + shared_equation + variable_mapping) → deep-analysis layer
   - Strength: produces shared-equation and variable-mapping strings for every record

All 63 records are rated A (top-tier) and include a 5-dimensional weighted score.

### Data Structure

Each of the 63 records contains:

- **Identity**: `seed_id`, `pipeline`, `rank_in_pipeline`
- **Pair**: `a_name`, `a_domain`, `b_name`, `b_domain`
- **Structural content**: `shared_equation` (V3 only, 20 records), `variable_mapping` (V3 only), `equations` (all pipelines, at least one)
- **Strength metrics**: `isomorphism_depth` (1-5 scale), `isomorphism_confidence` (0-1)
- **Publishability**: `paper_title`, `target_venue`, `literature_status` (unexplored / partial / established), `practical_value`, `risk`, `blocking_mechanisms`, `execution_plan`, `time_estimate`, `solo_feasible`, `impact_scope`, `impact_detail`, `final_score`, `one_line_verdict`, `rating`
- **Transformation analysis** (V4 labels): `transformation_primitives`, `transformation_depth`, `is_deep`
- **Context**: `full_analysis` (the LLM's free-text deep-dive rationale)

Records are written one-per-line in JSONL format with UTF-8 encoding. The full schema is in `SIBD-63-schema.json`.

### Example Record

```json
{
  "seed_id": "SIBD-v2-001",
  "pipeline": "v2",
  "rank_in_pipeline": 1381,
  "a_name": "永冻土融化释放甲烷的延迟反馈",
  "a_domain": "环境科学",
  "b_name": "灭绝债务",
  "b_domain": "保育生物学",
  "shared_equation": "",
  "equations": [
    "Delay ODE: dx/dt = f(x(t - tau)) - mu x(t)",
    "Committed change C = integral_{t0}^{infty} [x*(t) - x(t)] dt",
    "Extinction debt D = S_current - S_equilibrium(t -> infty)"
  ],
  "isomorphism_depth": 5,
  "isomorphism_confidence": 0.9,
  "paper_title": "Committed but Concealed: A Unified Delay-Debt Framework for Permafrost Methane and Extinction Debt",
  "target_venue": "Nature Climate Change / Trends in Ecology & Evolution",
  "literature_status": "unexplored",
  "solo_feasible": true,
  "final_score": 8.6,
  "one_line_verdict": "承诺未现的数学结构在两个领域独立发展但无人统一——可以用 x'(t)=f(x(t−τ))−μx(t) 给出两领域'债务余额'的可比较估计。",
  ...
}
```

## Domain Coverage

Records span **48 distinct domain labels**, including:

- **Physical sciences**: geology, geophysics, materials science, solid mechanics, fluid dynamics, electromagnetism, photonics, thermodynamics
- **Life sciences**: ecology, molecular biology, immunology, developmental biology, cell biology, conservation biology, neuroscience, physiology, pharmacology, oncology
- **Social / economic**: finance, microstructure, macroeconomics, behavioral economics, social cascade, sociology, military strategy, political economy
- **Engineering / applied**: civil engineering, power engineering, traffic engineering, aerospace, urban planning, polymer chemistry, catalysis
- **Emerging**: crypto / DeFi / Web3, synthetic biology, computational social science

## Intended Use

- **Seed bank for empirical papers**: domain experts pick a seed matching their expertise and run the empirical study
- **Benchmark for cross-domain similarity methods**: test whether a new embedding or LLM retrieval method can recover these 63 pairs
- **Training data for future V4 / V5 models**: reuse the 4,443-phenomenon knowledge base (separately distributed) + 63 high-confidence positive pairs
- **Teaching**: illustrate how to formalize cross-domain analogies with shared-equation + variable-mapping

**Not intended for**: direct consumer use, claims that these pairs are already empirically validated (most are not), replacement of peer-reviewed mechanistic studies.

## Quality and Limitations

**Strengths**:
- All 63 passed strict LLM-as-judge review from multiple model families (Opus + Kimi for V3)
- Each carries an explicit execution plan and target journal
- Zero-overlap across three independent pipelines increases robustness
- Five-dimensional scoring (novelty, rigor, feasibility, impact, writability) with weights documented in the V2-expanded ranking methodology

**Limitations**:
- **Only 20/63 have an explicit shared_equation** (V3 records); V1 and V2 records describe the structure in natural language
- **Literature-status is LLM-assessed**, not systematic meta-review — several labeled "unexplored" may have partial prior art
- **Chinese-language bias**: both phenomenon corpora and LLM rationales are Chinese-first; translation quality of English terms is variable
- **No empirical validation of any record** (SOC/DeFi Phase 3 paper addresses one SOC-class subset but does not directly validate SIBD-63 records themselves)
- **Single human curator** (author) applied final rating; no inter-rater agreement study

## Versions and Updates

- **1.0** (2026-04-16): initial release, 63 records

## Ethical Considerations

The dataset encodes scientific hypotheses, not personal data. No human subjects are involved beyond the author's curation judgment. Some records touch on high-stakes domains (climate, pandemic epidemiology, financial stability); these are research hypotheses, not policy guidance.

## Contact

Wan Qinghui · wanqinghui@gmail.com · https://structural.bytedance.city

## Related Resources

- **Full source code & pipelines**: https://github.com/dada8899/structural-isomorphism
- **V1 embedding model**: HuggingFace qinghuiwan/structural-isomorphism-v1
- **V2 embedding model**: HuggingFace qinghuiwan/structural-isomorphism-v2-expanded
- **Browse individual records**: https://structural.bytedance.city/discoveries
- **Layer 5 empirical follow-ups**:
  - SOC × earthquakes (Phase 1): `/paper/soc-earthquake-2026-04-15`
  - SOC × S&P 500 (Phase 2): `/paper/soc-stockmarket-2026-04-15`
  - SOC × DeFi cross-protocol (Phase 3): `/paper/soc-defi-2026-04-15`
  - SOC × neural avalanches (Phase 4): `/paper/soc-neural-2026-04-16`
  - SOC null validation (Phase 5): `/paper/soc-null-2026-04-16`
