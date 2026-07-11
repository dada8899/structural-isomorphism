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

> **Canonical production note (2026-07-11).** The live search system does
> not use the historical 4,888/5,333 expansion ledger below. Its verified
> artifact is `structural-v2-kb4443-20260711`: 4,443 unique KB rows paired
> with a `[4443, 768]` embedding matrix and checksums in
> `artifacts/production-v2-4443.json`. The larger counts are retained as
> historical/staged research assets and must not be presented as deployed.

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

The knowledge base of real-world phenomena has been expanded across SESSION-21 → SESSION-23. As of 2026-05-25 the **main KB file** (`data/kb-5000-merged.jsonl`) holds **4,888 entries**, with **445 additional entries staged in `data/kb-additions-2026-05-25-*.jsonl` pending merge** and a **200-entry `data_layer` overlay** in `data/kb-reproducible-data-layer-2026-05-25.jsonl` (applied to existing main-KB rows, so it does not add new rows). The merge ceiling is therefore **5,333 entries**:

| Wave | Δ rows | Cumulative rows | Coverage |
|---|---|---|---|
| Baseline (v0.1) | 500 | 500 | Science (170) + Social (170) + Cross (160) |
| Wave A (SESSION-21) | +3,975 | 4,475 | Mechanism graph backfill |
| Wave X1 (SESSION-22) | +335 | 4,810 | Linguistics 150 / Neuroscience 80 / Urban-Social 105 |
| Wave X3 (SESSION-22) | +78 | 4,888 | KPZ / DP / RFIM / Manna / Oslo / Tracy-Widom textbook classes |
| **Main KB total (current, on disk)** | — | **4,888** | `data/kb-5000-merged.jsonl` |
| Wave 2 (SESSION-23, pending merge) | +145 | 5,033 | 19 class-specific anchor batches under `data/kb-additions-2026-05-25-<class>.jsonl` |
| Wave 3C (SESSION-23, pending merge) | +300 | 5,333 | 10 long-tail domains × 30 entries each (`data/kb-additions-2026-05-25-long-tail-batch.jsonl`) |
| **Merge ceiling** | — | **5,333** | run `python3 scripts/merge_kb_additions.py --apply --output …` to realise |
| Wave 3B `data_layer` overlay | overlay only (200 rows updated, 0 added) | 5,333 | reproducible-data-layer pilot (4 domains × 50 entries) — adds a `data_layer` field to 200 existing main-KB rows |

> Earlier drafts of this card reported **5,388 entries / +500** — that figure double-counted the Wave 3B 200-entry overlay as new rows. The corrected merge ceiling is **5,333**.

KB entries carry the following fields. Wave 3B entries additionally carry a nested `data_layer` object (see schema below):

| Field | Required | Description |
|---|---|---|
| `id` | yes | Unique entry identifier |
| `name` | yes | Short title (often the phenomenon or anchor case name) |
| `type_id` | yes | Two-digit structural type identifier ("01"…"84") tied to the 84-row taxonomy |
| `domain` | yes | Domain label |
| `description` | yes | Plain-language description of the phenomenon |
| `data_layer` | Wave 3B only | Nested object carrying the reproducible-data-layer overlay (raw-data link, fit metadata, provenance notes); structure defined per-domain in `data/kb-reproducible-data-layer-2026-05-25.jsonl`. There is no top-level `data_provenance` field — the earlier draft of this card mentioned one, but it was never written to the KB |

### Universality classes & validation systems (v0.4)

The KB supports a cross-domain universality-class taxonomy. Counts reflect the v0.4 batch closing 2026-05-25:

| Metric | v0.3 (2026-05-24) | v0.4 (2026-05-25) | Δ |
|---|---|---|---|
| KB main-file entries | 4,888 | 4,888 (unchanged on disk) | 0 |
| KB merge ceiling (main + Wave 2 + Wave 3C additions) | 4,888 | **5,333** | +445 |
| KB `data_layer` overlay rows (Wave 3B) | 0 | 200 (overlay on existing rows, no row growth) | new |
| Candidate universality classes | 26 | **~27–28** (net of 5 SPLITs + 1 MERGE) | +1–2 net |
| SOC validation systems with empirical anchor | 27 | **45+** | +18 (Wave 2A/B/C) |
| Closed-verdict classes | 10 of 26 | **18 of 18 v0.4 batch closed** (10 PASS + 6 REJECT + 2 INCONCLUSIVE) | +8 closure |
| SPLIT decisions in taxonomy graph | 0 | **5** | +5 |
| MERGE recommendations | 0 | **1** (preisach_hysteresis_cascade + rfim_barkhausen → crackling_noise_universality) | +1 |

The v0.4 18-class verdict matrix is reported in `docs/sessions/C1-unified-preprint-draft-v0.4.md` §3.5.2. Each class carries a sub-agent verdict report at `docs/sessions/v04-<class>-report.md` and reproducible artefacts at `v4/validation/<class>/{run_validation.py, results.json, verdict.{md,txt}}`.

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
  author={Wan, Qinghui},
  journal={arXiv preprint arXiv:XXXX.XXXXX},
  year={2026}
}
```

## License

MIT
