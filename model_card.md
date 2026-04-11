---
language:
  - zh
license: mit
library_name: sentence-transformers
pipeline_tag: sentence-similarity
tags:
  - sentence-transformers
  - structural-isomorphism
  - cross-domain
  - analogy
base_model: shibing624/text2vec-base-chinese
---

# structural-isomorphism/structural-v1

A sentence-transformer model fine-tuned for **structural similarity** -- recognizing that phenomena from completely different domains share the same underlying structure.

Unlike standard semantic similarity models that match by surface vocabulary, this model maps descriptions with the same structural pattern close together in embedding space, regardless of domain.

## Model Description

- **Base model**: [shibing624/text2vec-base-chinese](https://huggingface.co/shibing624/text2vec-base-chinese) (BERT-based, 768-dim)
- **Training data**: [SIBD](https://huggingface.co/datasets/structural-isomorphism/SIBD) -- 1,214 descriptions across 84 structural types
- **Training objective**: MultipleNegativesRankingLoss (positive pairs = same structural type, different domain)
- **Epochs**: 10 | **Batch size**: 16 | **Learning rate**: 2e-5 | **Warmup**: 10%

## Evaluation Results

| Metric | Base Model | This Model | Improvement |
|---|---|---|---|
| Silhouette Score | -0.012 | **0.847** | +0.859 |
| Retrieval@5 | 20.3% | **100.0%** | +79.7% |
| Retrieval@10 | 18.0% | **100.0%** | +82.0% |
| Intra-class Similarity | 0.643 | **0.933** | +0.290 |
| Inter-class Similarity | 0.569 | **0.174** | -0.395 |

## Usage

### With sentence-transformers

```python
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("structural-isomorphism/structural-v1")

# Encode two descriptions from different domains
emb1 = model.encode("A thermostat detects low temperature and turns on heating")
emb2 = model.encode("The pancreas detects high blood sugar and releases insulin")

similarity = util.cos_sim(emb1, emb2).item()
print(f"Structural similarity: {similarity:.3f}")
# Both are negative feedback loops -> high similarity
```

### With the search engine

```python
from structural_isomorphism import StructuralSearch

search = StructuralSearch()
results = search.query("Small input causes disproportionately large output")
for r in results[:5]:
    print(f"{r['name']} ({r['domain']}) - {r['score']:.3f}")
```

## Intended Use

- Cross-domain structural similarity search
- Finding analogies and inspiration across fields
- Scientific discovery: identifying unknown structural connections
- Educational tools for teaching structural thinking

## Limitations

- Language: Currently trained on Chinese text only
- Domain coverage: 84 structural types may not cover all possible patterns
- The model recognizes structural types present in training data; novel structural types may not be well represented

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
