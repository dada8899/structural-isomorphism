---
language:
  - zh
license: mit
task_categories:
  - sentence-similarity
  - feature-extraction
tags:
  - structural-isomorphism
  - cross-domain
  - analogy
  - benchmark
size_categories:
  - 1K<n<10K
---

# SIBD: Structural Isomorphism Benchmark Dataset

## Dataset Description

SIBD (Structural Isomorphism Benchmark Dataset) is a dataset of 1,214 natural language descriptions spanning 84 distinct structural types. Each structural type is described in 10+ different real-world domains, using plain language without domain-specific jargon.

The dataset is designed to train and evaluate models that recognize **structural similarity** across domains -- the ability to see that a thermostat and blood sugar regulation share the same feedback loop structure, even though they come from completely different fields.

## Dataset Structure

### Data Format

Each entry is a JSON object with the following fields:

| Field | Type | Description |
|---|---|---|
| `type_id` | string | Two-digit structural type identifier (e.g., "01") |
| `type_name` | string | Human-readable type name (e.g., "Linear Proportion") |
| `domain` | string | Domain of the description (e.g., "Physics", "Economics") |
| `description` | string | Plain-language description of a phenomenon exhibiting this structure |

### Example

```json
{"type_id": "05", "type_name": "Exponential Growth", "domain": "Biology", "description": "A bacterial colony doubles every 20 minutes..."}
{"type_id": "05", "type_name": "Exponential Growth", "domain": "Finance", "description": "Compound interest means your money grows faster and faster..."}
```

### Statistics

- **Total entries**: 1,214
- **Structural types**: 84
- **Average entries per type**: ~14.5
- **Language**: Chinese
- **Domains include**: Physics, Chemistry, Biology, Economics, Law, Education, Medicine, Agriculture, Engineering, Sports, and 70+ more

### Knowledge Base (Supplementary)

In addition to the training data, we provide a knowledge base of 500 real-world phenomena:

| File | Entries | Coverage |
|---|---|---|
| `kb-science.jsonl` | 170 | Natural science phenomena |
| `kb-social.jsonl` | 170 | Social science & humanities |
| `kb-cross.jsonl` | 160 | Cross-disciplinary phenomena |

Knowledge base entries include an additional `id` and `name` field.

## Usage

```python
from datasets import load_dataset

# Load training data
dataset = load_dataset("structural-isomorphism/SIBD", split="train")

# Or load locally
import json
with open("data/clean.jsonl") as f:
    data = [json.loads(line) for line in f if line.strip()]
```

## Intended Use

- Training embedding models for structural similarity
- Evaluating cross-domain analogy recognition
- Research on structural isomorphism and knowledge transfer
- Building search engines for cross-domain inspiration

## Citation

```bibtex
@article{structural-isomorphism-2026,
  title={Structural Isomorphism Search: Cross-Domain Structural Similarity Retrieval via Fine-tuned Embeddings},
  author={Wan, Qihang},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## License

MIT
