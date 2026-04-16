<p align="center">
  <h1 align="center">Structural Isomorphism Search Engine</h1>
  <p align="center">
    <em>Discover hidden cross-domain structural connections using AI</em>
  </p>
  <p align="center">
    <a href="https://www.python.org/downloads/"><img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-blue.svg"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg"></a>
    <a href="https://doi.org/10.5281/zenodo.19615170"><img alt="Dataset DOI" src="https://img.shields.io/badge/Dataset_DOI-10.5281%2Fzenodo.19615170-blue.svg"></a>
    <a href="https://huggingface.co/qinghuiwan/structural-isomorphism-v2-expanded"><img alt="Model" src="https://img.shields.io/badge/%F0%9F%A4%97%20Model-V2_Expanded-yellow"></a>
    <a href="https://beta.structural.bytedance.city"><img alt="Live Site" src="https://img.shields.io/badge/Live-beta.structural.bytedance.city-2f9e44"></a>
  </p>
</p>

---

```
     Domain A                          Domain B
  ┌───────────┐                    ┌───────────┐
  │  Physics   │    Structural     │  Finance   │
  │  Phase     │   Isomorphism     │  Market    │
  │ Transition │ ════════════════> │  Tipping   │
  │            │  Same underlying  │  Point     │
  └───────────┘    structure       └───────────┘

  "A small change in temperature     "Investor sentiment shifts
   triggers a sudden state change"    suddenly after slow buildup"

         Both share: Threshold Dynamics (Type 16)
```

**Structural Isomorphism** is the phenomenon where systems in completely different domains share the same underlying mathematical or logical structure. This project provides a search engine that, given a natural language description of a phenomenon, retrieves structurally similar phenomena from other domains -- even when they share zero surface-level vocabulary.

## Quick Start

```python
from structural_isomorphism import StructuralSearch

search = StructuralSearch()
results = search.query("Two market participants each wait for the other to act first, so nobody moves")
for r in results[:5]:
    print(f"{r['name']} ({r['domain']}) - similarity: {r['score']:.3f}")
```

```
Nash Equilibrium Deadlock (Game Theory) - similarity: 0.891
Bystander Effect (Social Psychology) - similarity: 0.847
Prisoner's Dilemma (Economics) - similarity: 0.823
Voltage Deadlock (Circuit Theory) - similarity: 0.791
Predator-Prey Standoff (Ecology) - similarity: 0.764
```

## Installation

```bash
# From source
git clone https://github.com/yourusername/structural-isomorphism.git
cd structural-isomorphism
pip install -e .

# Or directly
pip install structural-isomorphism
```

**Requirements**: Python 3.8+, PyTorch, sentence-transformers

## What is This?

Most AI search tools match by **surface similarity** -- they find documents that use similar words. This project matches by **structural similarity** -- it finds phenomena that work the same way, even if they come from completely different fields.

| Input Description | Top Match | Domain | Why |
|---|---|---|---|
| "A thermostat detects temperature below setpoint, turns on heating, then turns off when target is reached" | Blood sugar regulation | Medicine | Both are **negative feedback loops** |
| "A product starts slow, goes viral, then saturates" | Bacterial colony growth | Biology | Both follow **S-curve dynamics** |
| "Small cause, large disproportionate effect" | Nuclear chain reaction | Physics | Both exhibit **cascade amplification** |

### How it Works

1. **Structural Isomorphism Benchmark Dataset (SIBD)**: 1,214 descriptions across 84 structural types, each type described in 10+ different domains
2. **Fine-tuned embedding model**: A sentence-transformer trained to map structurally similar descriptions close together in embedding space, regardless of domain vocabulary
3. **Knowledge base**: 500 real-world phenomena annotated with structural types, serving as the search index

## Key Results

### V1 Model (1214 training samples, original 84-type SIBD)

Our fine-tuned V1 model dramatically outperforms the base model at recognizing structural similarity on the original SIBD test set:

| Metric | Base Model | V1 Fine-tuned | Improvement |
|---|---|---|---|
| Silhouette Score | -0.012 | **0.847** | +0.859 |
| Retrieval@5 | 20.3% | **100.0%** | +79.7% |
| Retrieval@10 | 18.0% | **100.0%** | +82.0% |
| Intra-class Similarity | 0.643 | **0.933** | +0.290 |
| Inter-class Similarity | 0.569 | **0.174** | -0.395 |
| Intra-Inter Gap | 0.074 | **0.758** | +0.684 |

### V2 Model (5689 training samples, expanded 4443-phenomenon KB)

V2 is trained on an expanded dataset (1214 original + 4475 new phenomena). On the harder, more diverse evaluation set it is much more **selective** than V1:

| Metric | V1 | V2 | Delta |
|---|---|---|---|
| Silhouette Score (on 4443 KB) | -0.17 | **0.55** | +0.72 |
| Retrieval@5 (on 4443 KB) | 23% | **96%** | +73% |
| High-similarity cross-domain pairs (T≥0.70) | 339,913 | **4,533** | **75× stricter** |

### Three-Pipeline Discovery Results

Running V1 (broad embedding), V2 (strict embedding), and V3 (StructTuple + LLM rerank) on the 4443-phenomenon KB, followed by multi-stage LLM screening and deep analysis, produced **three complementary sets** with **pairwise zero overlap**:

| Pipeline | Method | Candidates | Paper-worthy | Top-tier |
|---|---|---|---|---|
| **V1 broad** | 1214-sample embedding | 339,913 | 3,167 pass | **24 tier-1** |
| **V2 strict** | 5689-sample embedding | 4,533 | 94 five-score | **19 A-level** |
| **V3 struct-algebra** | StructTuple + LLM rerank | 1,000 | 203 (20.3%) | **20 A + 34 B+** |

**Total: 63 unique top-tier candidate papers**, with three pipelines capturing fundamentally different structural signals:
- V1 excels at computer-science × engineering-systems analogies
- V2 excels at dynamical-systems × critical-phenomena
- V3 excels at equation-level matches (each V3 pair includes `shared_equation` + `variable_mapping`) and uncovered **DeFi as a high-resolution experimental system for traditional finance contagion theory**.

Top V2 A-level findings:
1. Permafrost methane delayed feedback × Extinction debt (Score 8.6)
2. Semiconductor laser relaxation oscillation × Algorithmic stablecoin anchoring (8.6)
3. Percolation threshold × Technology adoption chasm (8.5)
4. MHC over-dominant selection × Model ensemble (8.5)
5. Extinction debt × ENSO delayed oscillator (8.4)

Top V3 A-level findings:
1. DeFi liquidation cascade × Earthquake static-stress triggering (8.6) — Omori-Utsu + Coulomb stress
2. Flash-crash liquidity spiral × Liquidation cascade (8.5)
3. Margin spiral × Bank run (8.5) — Diamond-Dybvig first observable experimental system
4. Grape sunburn × Coral bleaching (8.5) — NOAA DHW metric transfer across biological temperature stress
5. Intersection spillover lock-up × Power grid cascade failure (8.2) — Motter-Lai cross-domain

See `site/docs/v2m-final-ranking.md`, `site/docs/v3-full-run.md`, `site/docs/v1-v2-pipeline-overlap.md`.

## Dataset: SIBD

The **Structural Isomorphism Benchmark Dataset** contains:

- **1,214 descriptions** across **84 structural types**
- Each type has descriptions from **10+ different domains** (physics, economics, biology, law, education, etc.)
- All descriptions are in Chinese, written in plain language without domain jargon
- Format: JSONL with fields `type_id`, `type_name`, `domain`, `description`

Example structural types:
| Type ID | Name | Example Domains |
|---|---|---|
| 01 | Linear Proportion | Physics, Economics, Agriculture, Law |
| 05 | Exponential Growth | Biology, Finance, Technology, Epidemiology |
| 16 | Threshold / Phase Transition | Physics, Sociology, Psychology, Engineering |
| 18 | Self-fulfilling Prophecy | Finance, Education, Politics |
| 21 | Hysteresis | Materials Science, Ecology, Psychology |

## Dataset: SIBD-63 (Seed Bank)

**SIBD-63** is the downstream discovery dataset: 63 A-level cross-domain structural isomorphism pairs produced by running the V1 + V2 + V3 pipelines on a 4,443-phenomenon knowledge base. Each record includes a proposed shared equation, variable mapping, target journal, literature-gap assessment, and a step-by-step empirical execution plan.

- **DOI**: [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170) (CC-BY-4.0, Zenodo)
- **Package**: [`v4/seedbank-sibd63/`](./v4/seedbank-sibd63/) — JSONL + schema + paper + build script
- **Companion paper**: [`v4/seedbank-sibd63/paper.md`](./v4/seedbank-sibd63/paper.md)
- **Intended use**: a seed bank for empirical follow-up papers — domain experts pick a seed matching their expertise and run the empirical study (3-6 months to publication)

Five of the SOC-class seeds already have companion empirical validation papers (earthquakes, S&P 500, DeFi cross-protocol, neural avalanches, null controls), browsable at [https://beta.structural.bytedance.city/classes](https://beta.structural.bytedance.city/classes).

## Knowledge Base

The search index contains **500 real-world phenomena** across 87 domains, organized in three files:

- `kb-science.jsonl` (170 entries): Natural science phenomena
- `kb-social.jsonl` (170 entries): Social science & humanities phenomena
- `kb-cross.jsonl` (160 entries): Cross-disciplinary phenomena

Each entry includes: `id`, `name`, `domain`, `type_id`, `description`

## Usage Examples

### 1. Basic Search

```python
from structural_isomorphism import StructuralSearch

search = StructuralSearch()

# Describe a phenomenon in natural language
results = search.query(
    "After a river floods, the water recedes slowly and the landscape "
    "doesn't return to its original state -- it follows a different path back"
)

for r in results[:3]:
    print(f"  {r['name']} ({r['domain']}): {r['score']:.3f}")
    print(f"  {r['description'][:80]}...")
    print()
```

### 2. Cross-domain Inspiration

```python
# Find structural analogies for a business problem
results = search.query(
    "Our company's departments each optimize for their own metrics, "
    "but this local optimization makes the whole organization perform worse"
)

# Might return: Braess's Paradox (Traffic), Tragedy of the Commons (Economics),
# Prisoner's Dilemma (Game Theory) -- all share the structure of
# "local optimization leading to global suboptimality"
```

### 3. Scientific Discovery Pipeline

```python
from structural_isomorphism import StructuralSearch

search = StructuralSearch()

# Find potentially unknown cross-domain connections
all_pairs = search.find_cross_domain_pairs(threshold=0.7)
for pair in all_pairs[:10]:
    print(f"{pair['item_a']['name']} ({pair['item_a']['domain']}) "
          f"<-> {pair['item_b']['name']} ({pair['item_b']['domain']}) "
          f"| sim={pair['similarity']:.3f}")
```

## Model

- **Base model**: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese) (BERT-based Chinese sentence embedding)
- **Training**: Fine-tuned with MultipleNegativesRankingLoss on SIBD
- **Training pairs**: Positive pairs = descriptions of the same structural type from different domains
- **Epochs**: 10, Batch size: 16, Learning rate: 2e-5

## Project Structure

```
structural-isomorphism/
├── structural_isomorphism/    # Python package
│   ├── __init__.py
│   ├── search.py              # StructuralSearch main class
│   ├── model.py               # Model loading & encoding
│   └── data.py                # Data loading utilities
├── data/
│   ├── clean.jsonl            # SIBD training data (1,214 entries)
│   ├── kb-science.jsonl       # Knowledge base: science (170)
│   ├── kb-social.jsonl        # Knowledge base: social (170)
│   └── kb-cross.jsonl         # Knowledge base: cross-domain (160)
├── scripts/
│   ├── train.py               # Training script
│   ├── evaluate.py            # Evaluation script
│   └── v2_pipeline.py         # Discovery pipeline
├── demo/
│   └── app.py                 # Gradio web demo
├── notebooks/
│   └── quickstart.ipynb       # Getting started notebook
├── models/                    # Model weights (not in git)
├── results/                   # Evaluation results
└── paper/                     # Paper drafts
```

## Citation

If you use the **SIBD-63 seed bank dataset** in your research, please cite:

```bibtex
@dataset{sibd63-2026,
  author       = {Wan, Qinghui},
  title        = {{SIBD-63: A Dataset of A-Level Cross-Domain
                   Structural Isomorphism Discoveries with Shared
                   Equations and Variable Mappings}},
  year         = {2026},
  publisher    = {Zenodo},
  version      = {1.0},
  doi          = {10.5281/zenodo.19615170},
  url          = {https://doi.org/10.5281/zenodo.19615170}
}
```

If you cite the V1-V3 methodology (embedding + StructTuple pipelines):

```bibtex
@article{structural-isomorphism-2026,
  title={Structural Isomorphism Search: Cross-Domain Structural Similarity Retrieval via Fine-tuned Embeddings},
  author={Wan, Qinghui},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Base embedding model: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese)
- Training framework: [sentence-transformers](https://github.com/UKPLab/sentence-transformers)
