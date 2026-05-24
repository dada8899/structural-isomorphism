# KB Number Correction & type_id Normalisation Fix Report

**Date:** 2026-05-25
**Trigger:** Audit-3 P0 findings
**Status:** P0 #1–#4 closed; 40 unmapped `type_id` entries still need user decision.

---

## P0 #1 — KB row-count claim: 5,388 → real ceiling 5,333

### Real numbers (computed from the JSONL files on disk)

| Source file | Rows | Notes |
|---|---|---|
| `data/kb-5000-merged.jsonl` (main KB) | **4,888** | unchanged on disk |
| `data/kb-additions-2026-05-25-<class>.jsonl` × 19 (Wave 2) | **+145** | pending merge |
| `data/kb-additions-2026-05-25-long-tail-batch.jsonl` (Wave 3C) | **+300** | pending merge |
| `data/kb-reproducible-data-layer-2026-05-25.jsonl` (Wave 3B) | 200 rows of overlay | merges `data_layer` field onto 200 existing main-KB rows; **does not add new rows** |
| **Merge ceiling (main + Wave 2 + Wave 3C)** | **5,333** | |

The earlier "5,388 / +500" figure double-counted the 200-row Wave 3B overlay as if it added rows.

### Files updated

- `docs/sessions/C1-unified-preprint-draft-v0.4.md`
  - L30 (front-matter changelog): "KB 4888 → 5388 entries" → "KB main 4,888 (unchanged) + 445 pending-merge additions (Wave 2 +145 + Wave 3C +300; Wave 3B 200 is `data_layer` overlay; merge ceiling 5,333)".
  - L85 (Abstract): "5,388 entries (4,888 + 200 ... + ~300 ...)" → "main 4,888 + 445 pending-merge + 200-entry `data_layer` overlay; merge ceiling 5,333"; explicit note that the original prose double-counted.
  - L456 (session deltas): same correction with an explicit "earlier '5,388 / +500' was an arithmetic error" annotation.
- `docs/sessions/SESSION-23-HANDOFF.md`
  - L23 (deliverables): updated to "KB merge ceiling 5,333 ... pending merge ... 原文档误写 5,388 / +500, audit-3 修订".
  - L34 (Δ table): split into three rows — KB main (4,888 unchanged), merge ceiling (5,333, +445), Wave 3B `data_layer` overlay (200, no row growth).
  - L118 (起手指令): "KB 5,388 entries" → "KB main 4,888 + merge ceiling 5,333 ... pending merge via `scripts/merge_kb_additions.py`".
  - L177 (path lookup): dataset_card row updated.
- `dataset_card.md`
  - §Knowledge Base table rewritten: main-KB row at 4,888 + Wave 2 / Wave 3C as "pending merge" rows + a separate row for the Wave 3B overlay marked "overlay only".
  - Inline blockquote added flagging the prior "5,388 / +500" double-count.
  - v0.4 vs v0.3 metric table: "KB entries 4,888 → 5,388 (+500)" replaced with three lines (main unchanged, merge ceiling 5,333 +445, data_layer overlay rows 200).

### Files NOT touched

- `data/kb-5000-merged.jsonl` (main KB) — per scope, user does the merge manually with `scripts/merge_kb_additions.py`.
- `README.md` / `README-zh.md` — grepped; no 5,388 / +500 mention found, nothing to fix.

---

## P0 #2 — `data_provenance` field never existed; dataset_card schema corrected

### Finding

A grep across `data/*.jsonl` shows no entry, in any KB layer, carries a top-level `data_provenance` field. The schemas observed are:

- Main KB / Wave 2 / Wave 3C: `id, name, domain, type_id, description`
- Wave 3B layer: `id, name, domain, type_id, description, data_layer` (where `data_layer` is a nested object)

The earlier `dataset_card.md` L67 claimed:

> "KB entries include `id`, `name`, `type_id`, `domain`, `description`, and (from Wave 3B onward) `data_provenance` ∈ {REAL, SYNTHETIC, MIXED} + source citation."

The promise of a top-level `data_provenance` enum was never implemented.

### Fix

- `dataset_card.md` §Knowledge Base now lists the real schema in a per-field table and explicitly states: *"There is no top-level `data_provenance` field — the earlier draft of this card mentioned one, but it was never written to the KB."* The Wave 3B `data_layer` nested-object field is listed as the actual mechanism.

---

## P0 #3 — Wave 2 `type_id` normalisation

### Scope

19 `data/kb-additions-2026-05-25-<class>.jsonl` files (excluding `long-tail-batch.jsonl`), totalling 145 entries.

### Pre-fix `type_id` distribution

| `type_id` value | count | class | status |
|---|---|---|---|
| `"24"` | 37 | (multiple files) | ok |
| `"23"` | 21 | (multiple files) | ok |
| `"12"` | 11 | (hysteresis / preisach) | ok |
| `"27"` | 8 | adverse_selection | ok |
| `"37"` | 8 | reaction-diffusion | ok |
| `"26"` | 2 | gardner-collins-toggle-v2 | ok |
| `"11"` | 2 | hysteresis-first-order | ok |
| `"7"` | 8 | delay-differential-debt | **zero-fill → `"07"`** |
| `"6"` | 8 | tail-copula-contagion | **zero-fill → `"06"`** |
| `"extreme_value_tail_class"` | 8 | extreme-value-tail | **FLAGGED (unmapped)** |
| `"gardner_collins_toggle_switch"` | 8 | gardner-collins-toggle | **FLAGGED (unmapped)** |
| `"markov_chain_memory_fidelity_class"` | 8 | markov-memory-fidelity | **FLAGGED (unmapped)** |
| `"rfp"` | 8 | reflexive-fixed-point | **FLAGGED (unmapped)** |
| `"scale_free_percolation_class"` | 8 | scale-free-percolation | **FLAGGED (unmapped)** |

Main KB (`data/kb-5000-merged.jsonl`) uses 84 two-digit IDs `"01"…"84"`. Anything outside that set is wrong.

### Action

Wrote `scripts/normalize_kb_additions.py`. Default dry-run; `--apply` writes in-place with `.bak` siblings.

Two safe transforms only:

1. **Zero-fill** numeric strings whose padded form lives in main-KB: `"6"` → `"06"`, `"7"` → `"07"`.
2. **Flag** non-numeric strings (e.g. `"rfp"`). These are universality-class names from the separate taxonomy at `web/frontend/assets/data/universality-classes.json` — they don't map cleanly to the 84-row structural-type taxonomy that the KB uses. Left untouched; user decides whether to coin new `type_id`s or remap.

### Result (after `--apply`)

```
unchanged    89
zerofilled   16
flagged      40
total        145
```

Files modified in-place (with `.bak` backups):

- `data/kb-additions-2026-05-25-delay-differential-debt.jsonl` (8 entries: `"7"` → `"07"`)
- `data/kb-additions-2026-05-25-tail-copula-contagion.jsonl` (8 entries: `"6"` → `"06"`)

Files left untouched, awaiting user decision:

- `data/kb-additions-2026-05-25-extreme-value-tail.jsonl` (8 entries, `type_id="extreme_value_tail_class"`)
- `data/kb-additions-2026-05-25-gardner-collins-toggle.jsonl` (8 entries, `type_id="gardner_collins_toggle_switch"`)
- `data/kb-additions-2026-05-25-markov-memory-fidelity.jsonl` (8 entries, `type_id="markov_chain_memory_fidelity_class"`)
- `data/kb-additions-2026-05-25-reflexive-fixed-point.jsonl` (8 entries, `type_id="rfp"`)
- `data/kb-additions-2026-05-25-scale-free-percolation.jsonl` (8 entries, `type_id="scale_free_percolation_class"`)

### User decision required for the 40 flagged entries

For each of the five files above, pick one of:

1. **Remap to an existing 84-row ID** (preferred if the content reads as e.g. "first-order phase transition" → `"12"` etc.). Inspect the `name`/`description` and choose.
2. **Coin new `type_id`** entries `"85"`, `"86"`, … (will widen the KB taxonomy beyond 84 — needs a corresponding row in whatever defines the 84-row vocabulary, e.g. `data/types.jsonl` or its equivalent, plus a write-up in dataset_card).
3. **Drop these 40 rows** from the merge (Wave 2 ceiling would then be +105 instead of +145, and total merge ceiling 5,293 instead of 5,333).

Until one of the three is chosen, do not run `merge_kb_additions.py --apply` on these five files — they will pass through with broken `type_id`s.

### Sanity check

After `--apply` the only remaining non-84-set `type_id`s are the five class-name strings listed above (40 entries). All numeric `type_id`s in Wave 2 are now `01..84`.

---

## P0 #4 — `scripts/merge_kb_additions.py` (unified merge helper)

### Design

Single-CLI tool that:

- Reads `--main <jsonl>` as baseline (default `data/kb-5000-merged.jsonl`); never modified.
- For every `--additions <glob>` file, appends entries that don't collide with `id`.
- For the optional `--layer <jsonl>`, looks up by `id` and merges the `data_layer` field onto matching main-KB rows (no row growth).
- For the optional `--long-tail <jsonl>`, appends with `id` dedup.
- Default is dry-run; `--apply --output <path>` writes the merged file (refuses to overwrite an existing path).

### Dry-run result (today)

```
Loaded main KB: 4,888 entries from data/kb-5000-merged.jsonl
  additions (19 Wave 2 files)           +145  skipped_dup=0
  layer  kb-reproducible-data-layer     updated=200 appended=0
  long-tail  kb-additions-...long-tail  +300  skipped_dup=0
=== Merge summary ===
  main baseline                          4,888
  additions added                        +145
  layer entries with data_layer merged   200
  long-tail appended                     +300
  ----
  final merged total                     5,333
```

### Recommended next step (user)

```bash
cd ~/Projects/structural-isomorphism
# (Optional) first resolve the 40 flagged type_id entries; then:
python3 scripts/merge_kb_additions.py \
  --main data/kb-5000-merged.jsonl \
  --additions "data/kb-additions-2026-05-25-*.jsonl" \
  --layer data/kb-reproducible-data-layer-2026-05-25.jsonl \
  --long-tail data/kb-additions-2026-05-25-long-tail-batch.jsonl \
  --output data/kb-5333-merged-2026-05-25.jsonl \
  --apply

# Inspect; if happy, replace main KB:
# mv data/kb-5000-merged.jsonl data/kb-5000-merged.jsonl.pre-5333.bak
# mv data/kb-5333-merged-2026-05-25.jsonl data/kb-5000-merged.jsonl
```

---

## Files modified

- `docs/sessions/C1-unified-preprint-draft-v0.4.md`  (3 edits, KB number lines)
- `docs/sessions/SESSION-23-HANDOFF.md`  (4 edits, KB number lines)
- `dataset_card.md`  (2 edits, KB table + schema field list)
- `data/kb-additions-2026-05-25-delay-differential-debt.jsonl`  (8 entries: `"7"` → `"07"`; `.bak` left behind)
- `data/kb-additions-2026-05-25-tail-copula-contagion.jsonl`  (8 entries: `"6"` → `"06"`; `.bak` left behind)

## Files added

- `scripts/normalize_kb_additions.py`
- `scripts/merge_kb_additions.py`
- `docs/fixes/2026-05-25-kb-number-correction.md` (this report)
- `data/kb-additions-2026-05-25-delay-differential-debt.jsonl.bak`
- `data/kb-additions-2026-05-25-tail-copula-contagion.jsonl.bak`

## Files explicitly NOT touched

- `data/kb-5000-merged.jsonl` (main KB) — user does the merge.
- `scripts/train_v2.py` — out of scope.
- `packages/**` — out of scope.
- `README.md` / `README-zh.md` — grepped clean; no 5,388 reference.
- No `git add` / `git commit` / `git push` was run.

## Still pending user decision

- The 40 entries with non-numeric `type_id` across five Wave 2 files. See §P0 #3 "User decision required" above. Until resolved, the merged KB will carry bad `type_id`s in those rows.
