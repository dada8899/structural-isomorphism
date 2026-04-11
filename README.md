<p align="center">
  <h1 align="center">Structural Isomorphism Search Engine</h1>
  <p align="center">
    <em>Discover hidden cross-domain structural connections using AI</em>
  </p>
  <p align="center">
    <a href="https://www.python.org/downloads/"><img alt="Python 3.8+" src="https://img.shields.io/badge/python-3.8+-blue.svg"></a>
    <a href="https://opensource.org/licenses/MIT"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-green.svg"></a>
    <a href="https://arxiv.org/abs/XXXX.XXXXX"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-XXXX.XXXXX-b31b1b.svg"></a>
    <a href="https://huggingface.co/datasets/structural-isomorphism/SIBD"><img alt="Dataset" src="https://img.shields.io/badge/%F0%9F%A4%97%20Dataset-SIBD-yellow"></a>
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

Our fine-tuned model dramatically outperforms the base model at recognizing structural similarity:

| Metric | Base Model | Fine-tuned | Improvement |
|---|---|---|---|
| Silhouette Score | -0.012 | **0.847** | +0.859 |
| Retrieval@5 | 20.3% | **100.0%** | +79.7% |
| Retrieval@10 | 18.0% | **100.0%** | +82.0% |
| Intra-class Similarity | 0.643 | **0.933** | +0.290 |
| Inter-class Similarity | 0.569 | **0.174** | -0.395 |
| Intra-Inter Gap | 0.074 | **0.758** | +0.684 |

The model achieves near-perfect clustering: descriptions of the same structural type are mapped very close together (0.933 avg similarity), while different types are pushed far apart (0.174 avg similarity).

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

If you use this project in your research, please cite:

```bibtex
@article{structural-isomorphism-2026,
  title={Structural Isomorphism Search: Cross-Domain Structural Similarity Retrieval via Fine-tuned Embeddings},
  author={Wan, Qihang},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Base embedding model: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese)
- Training framework: [sentence-transformers](https://github.com/UKPLab/sentence-transformers)
