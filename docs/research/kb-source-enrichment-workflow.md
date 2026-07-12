# KB source enrichment workflow

Date: 2026-07-12
Status: offline human evidence collection; no sources have been auto-filled

The production KB has 4,443 Chinese candidate descriptions and no row-level
source, license or provenance fields. This workflow creates a stable review
queue without inferring those missing facts.

## Build a queue

```bash
python3 scripts/kb_source_enrichment.py build \
  --batch-size 100 \
  --output evaluation/review/kb-source-enrichment-bundle-v1.json
```

Outputs are fail-closed: an existing file or symlink is never replaced unless
the operator explicitly supplies `--overwrite`. JSON with duplicate keys or
non-finite numbers is rejected.

Priority is deterministic and favors descriptions containing quantitative,
causal, universal/critical or high-impact domain claims. Priority is only an
audit order; it is not a truth or risk probability. Each task is bound to:

- the full KB SHA-256;
- the complete review bundle and policy fingerprint;
- stable KB ID;
- description SHA-256;
- name, domain and type ID.

Changing the KB or description invalidates the old bundle/review.

## Human review record

One JSONL file contains one reviewer identity. Each row uses schema
`kb-source-review-v1` and includes:

```json
{
  "schema_version": "kb-source-review-v1",
  "task_id": "kbs_...",
  "kb_id": "...",
  "description_sha256": "...",
  "bundle_fingerprint": "complete bundle review_fingerprint",
  "reviewer_id": "human-reviewer-a",
  "reviewed_at": "2026-07-12",
  "source_review": "accepted",
  "source_url": "https://...",
  "citation": "Complete human-checked citation",
  "license": "source-specific",
  "provenance_class": "literature-derived",
  "note": "What was checked and any scope limit"
}
```

Accepted review requires HTTPS source URL, complete citation, an allowed
license and provenance class. The tool never checks scientific support merely
because a URL resolves; the human must verify that the source supports the
description and record limitations.

When no defensible source exists, use `source_review=insufficient`, set source,
citation, license and provenance to `null`, and explain why. Do not select a
plausible-looking source to complete the field.

## Validate and merge

```bash
python3 scripts/kb_source_enrichment.py validate \
  --bundle evaluation/review/kb-source-enrichment-bundle-v1.json \
  --input reviewer-a.jsonl

python3 scripts/kb_source_enrichment.py merge \
  --bundle evaluation/review/kb-source-enrichment-bundle-v1.json \
  --input reviewer-a.jsonl reviewer-b.jsonl \
  --output merged-source-records.jsonl \
  --conflicts source-conflicts.jsonl \
  --report source-progress.json
```

A row reaches `source_backed` only when at least two distinct reviewer files
agree unanimously on accepted status, URL, citation, license, provenance class
and the scope/limitation note. The merged record preserves the agreeing
reviewer IDs for audit. Majority voting is not used: one dissenting review
blocks promotion even if two other reviewers agree.
Disagreement, rejection, insufficient evidence, a single review or no review
keeps the row at `candidate`. The conflict queue includes both reviews for a
third human adjudicator; the tool does not choose the most convenient source.

## Progress and completion

The report tracks reviewed, source-backed, conflict/insufficient and unreviewed
counts. Completing a batch means every task has two independent reviews, every
conflict has a documented adjudication, and accepted sources pass domain review.
It does not mean the entire 4,443-row KB is source-backed.

The current repository contains a 100-task queue but no completed source-review
records. Do not report source coverage until human review files exist and pass
the validator.
