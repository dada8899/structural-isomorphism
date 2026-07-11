# English retrieval blind review

This offline workflow collects the 594 human judgments missing from the frozen
English candidate pool. It never asks a model to create human labels. The
bundle is deterministic, bound to the candidate-pool SHA-256 and upstream
artifact fingerprints, and omits rank, retrieval source, provenance, model,
and seed labels.

## Build and serve

```bash
python3 scripts/english_review_tool.py build
python3 -m http.server 8765 --directory evaluation/review
```

Open `http://127.0.0.1:8765/`. Enter a stable, non-secret reviewer ID. Keys
`0`–`3` select relevance, Enter saves and advances, and arrow keys navigate.
Every save is persisted to browser local storage. Export checkpoints regularly;
the complete export refuses to run while tasks are missing.

## Validate and merge

```bash
python3 scripts/english_review_tool.py validate --input reviewer-a.jsonl
python3 scripts/english_review_tool.py validate --allow-partial --input checkpoint.jsonl
python3 scripts/english_review_tool.py merge \
  --input reviewer-a.jsonl reviewer-b.jsonl \
  --output merged.jsonl --report agreement.json --disputes disputes.jsonl
```

Validation is fail-closed for unknown task IDs, query/document identity drift,
pool fingerprint drift, duplicates, invalid enums, and missing judgments.
Merge output includes quadratic-weighted Cohen kappa for every reviewer pair
and a queue for ties, fewer than two reviews, or score gaps of two or more.
`publication_ready` remains false unless every task has at least three distinct
reviewers, no item remains in adjudication, and mean pairwise quadratic-weighted
kappa is at least 0.67. Reviewer IDs are declarations, not identity proof;
study coordination must ensure the files came from independent humans. Only
adjudicated results should be promoted into canonical qrels. The repository
contains no completed human labels and must not claim otherwise.

## WTO independent coding

The WTO work package is separate from retrieval review. Build a blinded bundle
that omits the existing scores, outcomes, notes, and outcome basis:

```bash
python3 scripts/wto_reproducibility.py build-coding-bundle \
  --output evaluation/review/wto-independent-coding-bundle-v1.json
```

Each coder works from official sources without opening the existing coded CSV
or another coder's export. Validate each JSONL independently, then compare the
two complete files. Comparison emits only disputed fields for adjudication; it
does not silently choose a winner or overwrite the original dataset.
