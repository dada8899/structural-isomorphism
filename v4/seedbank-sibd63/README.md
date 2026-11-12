# SIBD-63: A Dataset of A-Level Cross-Domain Structural Isomorphism Discoveries

**Author**: Wan Qinghui (万庆徽), Structural Isomorphism Project
**Version**: 1.0 (2026-04-16)
**License**: CC-BY-4.0
**DOI**: pending (will be assigned on Zenodo upload)

---

## What this dataset is

63 independently-discovered **A-level cross-domain structural isomorphism pairs** — each pair consisting of two phenomena from different scientific domains that share the same underlying mathematical structure. Each record includes a shared-equation statement, variable mapping (where available), a suggested target journal for the empirical paper, a literature-gap assessment, and a step-by-step execution plan.

The dataset is the output of three independent discovery pipelines (V1/V2/V3), which have **zero overlap** by construction. It is designed as a **seed bank for empirical follow-up papers**: each entry is a hypothesis that a single researcher can realistically turn into a publishable paper in 3-6 months.

## Why it exists

Most AI-for-Science tools either:
- produce **open-ended text** too vague to be actionable, or
- produce **narrow within-domain findings** that domain experts could have found themselves.

The Structural Isomorphism Project aimed at a different target: **cross-domain structural matches** that are specific enough to have variable mappings, concrete enough to have target journals, and grounded enough to have execution plans — but whose empirical validation requires domain experts we do not have.

This dataset externalizes the discovery work so that domain experts can pick up seeds that overlap with their expertise.

## Quick stats

| Quantity | Value |
|---|---|
| Total entries | 63 |
| Zero-overlap pipelines contributing | 3 (V1 broad-recall embedding = 24; V2 strict-precision embedding = 19; V3 StructTuple + LLM rerank = 20) |
| Unique domain tags | 48 |
| Records with explicit shared-equation LaTeX | 20 (V3 only) |
| Records with variable mapping | 20 (V3 only) |
| Score range (5-dim weighted) | 7.5 – 9.0 (mean 8.17) |
| Records labeled solo-feasible | all 63 |

Top domains (by record count): 金融市场微观结构 (5), 加密货币/DeFi (5), 生态学 (4), 区块链/Web3 (4), 高分子化学 (4), 行为经济学 (3), 金融 (3), 保育生物学 (2).

## Schema

Each line in `SIBD-63.jsonl` is a JSON object with the fields defined in `SIBD-63-schema.json`. Key fields:

- `seed_id`, `pipeline`, `rank_in_pipeline` — identity
- `a_name`, `a_domain`, `b_name`, `b_domain` — the cross-domain pair
- `shared_equation`, `variable_mapping`, `equations` — structural content
- `isomorphism_depth`, `isomorphism_confidence` — strength metrics
- `paper_title`, `target_venue`, `literature_status` — publishability assessment
- `practical_value`, `risk`, `blocking_mechanisms` — empirical-follow-up critical context
- `execution_plan`, `time_estimate`, `solo_feasible` — actionability
- `final_score`, `one_line_verdict`, `full_analysis` — aggregated evaluation
- `transformation_primitives` — how A maps onto B (V4 categorical labels)

See `SIBD-63-schema.json` for the full formal schema.

## How to use

### Browse

Read `SIBD-63.jsonl` line by line; each line is a standalone JSON record.

```python
import json
for line in open("SIBD-63.jsonl"):
    rec = json.loads(line)
    print(rec["seed_id"], rec["a_name"], "↔", rec["b_name"],
          "(score", rec["final_score"], ")")
```

### Filter by domain

```python
import json
defi_records = [json.loads(l) for l in open("SIBD-63.jsonl")
                if "DeFi" in json.loads(l)["a_domain"] + json.loads(l)["b_domain"]]
```

### Filter by score / solo feasibility

```python
high_quality_solo = [r for r in records
                     if r["final_score"] >= 8.5 and r["solo_feasible"]]
```

### Claim a seed for empirical follow-up

If you are a domain expert and want to empirically validate one of these seeds, please:

1. Email the first author (`wanqinghui@gmail.com`) with the seed_id(s) you are interested in
2. Confirm author-order up front in writing (typically first author = lead empirical researcher, last author = seed originator)
3. Cite this dataset in the methods section of any resulting publication

## Citation

If you use this dataset, please cite:

```bibtex
@dataset{wan2026sibd63,
  author       = {Wan, Qinghui},
  title        = {SIBD-63: A Dataset of A-Level Cross-Domain
                  Structural Isomorphism Discoveries with Shared
                  Equations and Variable Mappings},
  year         = 2026,
  publisher    = {Zenodo},
  version      = {1.0},
  doi          = {10.5281/zenodo.19615170},
  url          = {https://doi.org/10.5281/zenodo.19615170}
}
```

Plain-text form:

> Wan, Q. (2026). *SIBD-63: A Dataset of A-Level Cross-Domain Structural Isomorphism Discoveries with Shared Equations and Variable Mappings* (Version 1.0) [Data set]. Zenodo. https://doi.org/10.5281/zenodo.19615170

## Reproducibility

To rebuild the dataset from the underlying V1/V2/V3 pipeline outputs in the parent repository:

```bash
cd structural-isomorphism
python3 v4/seedbank-sibd63/scripts/build.py
```

Inputs used:
- `v3/results/v1v2v3-transformation-labeled.jsonl` (canonical 63-row merge)
- `results/v2m-a-rated.jsonl` (V2 A-rated source with domain fields)
- `v3/results/v3-a-rated.jsonl` (V3 A-rated source with shared-equation and variable-mapping fields)

Dependencies: Python 3.9+, no third-party packages required for the build step.

## Source repository

https://github.com/dada8899/structural-isomorphism — full pipeline source code, prior publications, companion papers for Phases 1-5 of Layer 5 (empirical validation).

## License

**CC-BY-4.0.** You may use, redistribute, and build on this dataset for any purpose, including commercial, provided you cite the original work.

## Acknowledgments

This dataset was produced with extensive assistance from Claude Opus 4.6 (Anthropic) for LLM-as-judge scoring, pairwise rerank, and deep-analysis generation. Methodology follows the V1/V2/V3 pipelines described in the companion manuscripts.
