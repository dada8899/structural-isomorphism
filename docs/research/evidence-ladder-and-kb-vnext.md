# Evidence ladder and KB vNext migration

Date: 2026-07-12
Status: P0 data and public-claim contract

## Evidence ladder

All product/research surfaces use six explicit levels:

1. `candidate` — retrieved or model-ranked connection.
2. `source_backed` — auditable source, license and provenance class.
3. `analysis_recorded` — method and hashed result artifact exist.
4. `falsification_tested` — a fixed failure rule produced PASS, FAIL, REJECT,
   NULL, PARTIAL or INCONCLUSIVE.
5. `externally_reviewed` — independent review and dispute resolution are recorded.
6. `replicated` — an independent team/data reproduction is recorded.

Evidence level and verdict are independent. A FAIL under a strong preregistered
test can have higher evidence quality than a model-ranked PASS. Generic
`verified/confirmed` is prohibited because it hides what was actually checked.

Machine authority:
`evaluation/research/evidence-ladder-v1.json`.

## KB vNext

The current 4,443 rows contain only ID, name, domain, type, and Chinese
description. Migration therefore adds explicit unknowns:

- `language=zh`
- `provenance_class=unknown`
- `source=null`
- `source_review=null`
- `license=unknown`
- `data_layer=null`
- `evidence_level=candidate`

This is not a data enrichment operation. No source, license or empirical status
is inferred from prose, type ID, model output or filename. A row can be promoted
only after its source locator, license and provenance are supplied and an
auditable source-review record is attached.

Machine authority:
`evaluation/research/kb-vnext-schema-v1.json`.

## Discoveries

The runtime normalizer converts both legacy `equations[]` and newer
`shared_equation` into `shared_equations[]`. Existing “confidence” values are
displayed as uncalibrated internal AI scores. Since the 39 records contain no
structured `literature_evidence`, their literature status is downgraded to
`not_systematically_reviewed` and evidence level remains `candidate`.

## Validation

```bash
python3 scripts/validate_evidence_assets.py
python3 -m pytest tests/test_evidence_assets.py
python3 scripts/check_public_claims.py
```

The contracts fail if a legacy KB migration fabricates provenance, a promoted
row lacks source/license/provenance, discovery equation schemas do not normalize,
or current public copy restores prohibited aggregate Verified claims.
