# Stage 1 benchmark harness v1

Date: 2026-07-12
Status: implementation harness only; Stage 1 formal evidence has **not started**

## Purpose and evidence boundary

This package makes the Stage 1 protocol machine-checkable before any historical
task, model output, human label or scientific result is admitted. The two
included problem packages and result rows are explicitly synthetic. They test
chronology, contamination, budget, arm, VFU and immutability guards only. They
must never enter a scientific denominator, effect estimate, product claim or
publication claim.

The authority for scientific design remains:

- `docs/audit/ai-for-science-paradigm-2026-07-12.md`
- `docs/audit/ai-science-validation-protocol-2026-07-12.md`

## Package layout

- `evaluation/stage1/manifest-v1.json`: sealed implementation manifest, formal
  minimum design, Stage 2 gates, equal-budget arms and eight ablations.
- `evaluation/stage1/schemas/`: strict problem-package and result JSON schemas.
- `evaluation/stage1/fixtures/`: synthetic positive/negative implementation
  fixtures; no real task and no human label.
- `scripts/validate_stage1_benchmark.py`: independent fail-closed sealer and
  validator.
- `tests/test_stage1_benchmark.py`: adversarial boundary tests.

## Arms and attribution

The manifest requires expert-usual, strong general AI+RAG, same-model semantic
retrieval, random/same-domain negative control and the full engine. It also
requires exactly the eight preregistered ablations: structural fingerprint,
cross-domain constraint, REJECT/falsifier, evidence ledger, transfer mapping,
experiment/result feedback, model-family swap and candidate/label permutation.
Removing or renumbering an ablation invalidates the package.

## Validation

Seal only after intentionally changing an artifact:

```bash
python3 scripts/validate_stage1_benchmark.py \
  evaluation/stage1/manifest-v1.json --seal
```

Validate the implementation package and synthetic result rows:

```bash
python3 scripts/validate_stage1_benchmark.py \
  evaluation/stage1/manifest-v1.json \
  --results evaluation/stage1/fixtures/synthetic-results-v1.jsonl
```

The expected summary contains `scientific_evidence: false`. Formal mode must
reject this package:

```bash
python3 scripts/validate_stage1_benchmark.py \
  evaluation/stage1/manifest-v1.json --formal
```

## Formal activation checklist

Formal Stage 1 requires a new manifest and new immutable artifacts. Do not edit
the synthetic package into a real study. Before status can become
`FORMAL_FROZEN`, independently verify:

1. At least three domains and at least 30 frozen historical tasks per domain.
2. Every task outcome is sealed, post-`t0`, explicitly excluded from accessible
   sources, and passes near-duplicate and target-revealing-text checks.
3. Corpus/model/search-cache versions, prompts, budgets, exclusions, primary
   analysis and stopping rules are frozen before outcome exposure.
4. Human gold and blind review procedures are approved; no labels are invented
   from model output.
5. Every arm receives equal information, model/tool budget and output schema.
6. A non-developer clean-room runner validates all digests and reproduces the
   package.
7. The formal results JSONL is itself sealed in the manifest and contains
   exactly one row for every frozen task/arm pair; omitted arms or tasks fail
   closed. Formal validation never accepts an external or symlinked results
   file.

`--seal` writes the manifest atomically and rejects symlinked artifacts. It is
an integrity operation, not authorization to convert this synthetic package
into a formal study. A completed formal package must use a separate historical
manifest, pass model-contamination probes, explicitly permit scientific
analysis, and provide its complete sealed result matrix.

Passing this harness proves only that the instrumentation enforces its declared
boundaries. It does not prove a structural signal, VFU lift, scientific utility
or a new AI-for-Science paradigm.
