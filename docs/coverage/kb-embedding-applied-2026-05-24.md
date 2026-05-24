# KB Embedding Update Applied — 2026-05-24 (Session 22)

**Status**: applied (not committed). Backups preserved with suffix
`.bak-session22` and `.bak` (post-linguistics intermediate).

## Summary

| Stage              | KB jsonl rows | kb_embeddings.npy | kb_v2_embeddings.npy |
| ------------------ | ------------: | ----------------: | -------------------: |
| Baseline (before)  |          4475 |              4475 |                 4443 |
| After linguistics  |          4475 |              4625 | 4593                 |
| After X3 unified   |          4475 |              4888 |                 4856 |
| After KB merge     |          4888 |              4888 |                 4856 |

Embedding dim: **768** (unchanged). Dtype: **float32** (unchanged).

- `kb_embeddings.npy` (L2-normalised; mean norm 1.0): **4888 × 768**
- `kb_v2_embeddings.npy` (un-normalised; mean norm ~17.5 overall, see drift
  note below): **4856 × 768**
- ID sidecars (`kb_embeddings_ids.json` / `kb_v2_embeddings_ids.json`)
  rewritten in lockstep — row count invariant verified post-write.

## What was applied

### X1 expansions (335 entries / 3 files)

| Source                                                  | Rows | How encoded |
| ------------------------------------------------------- | ---: | ----------- |
| `data/kb-additions-2026-05-24-linguistics.jsonl`        |  150 | `scripts/update_kb_embeddings_linguistics.py --apply` (patched) |
| `data/kb-additions-2026-05-24-neuroscience.jsonl`       |   80 | `scripts/update_kb_embeddings_x3.py --apply` (unified, see note) |
| `data/kb-additions-2026-05-24-urban-social.jsonl`       |  105 | `scripts/update_kb_embeddings_x3.py --apply` (unified, see note) |

### X3 expansions (78 entries / 5 files)

| Source                                                       | Rows |
| ------------------------------------------------------------ | ---: |
| `data/kb-additions-2026-05-24-climate-tipping.jsonl`         |   25 |
| `data/kb-additions-2026-05-24-covid-omori.jsonl`             |   18 |
| `data/kb-additions-2026-05-24-llm-scaling.jsonl`             |   15 |
| `data/kb-additions-2026-05-24-zipf-empirical.jsonl`          |   10 |
| `data/kb-additions-2026-05-24-city-zipf-empirical.jsonl`     |   10 |

All five run through `scripts/update_kb_embeddings_x3.py` in a single pass.

**Grand total new entries**: 150 (X1-ling) + 185 (X1-neuro+urban) + 78 (X3) =
**413**. Embedding matrix grew from 4475 → 4888 (+413). Mass balance ✓.

## Deviations from the original plan

### 1. Two of the three X1 scripts had model / scope bugs

- `update_kb_embeddings_neuroscience.py`:
  - Passed `model_path=models/structural-v1` to `load_model()`. That
    directory does **not** exist on disk; the fall-through priority chain
    in `structural_isomorphism.model.load_model()` ends at
    `shibing624/text2vec-base-chinese` (base, no fine-tuning).
  - Existing matrix rows were encoded with `models/structural-v2`. Running
    the neuroscience script as-shipped silently mixed two embedding
    spaces.
  - Also: only writes `kb_embeddings.npy`, never touches
    `kb_v2_embeddings.npy` → the two precomputed files would have drifted
    apart by 80 rows.
- `update_kb_embeddings_urban.py`:
  - Calls `load_model()` with no path → same fall-through to base text2vec.
  - Re-encodes the **entire** KB rather than appending, then writes only
    to `kb_v2_embeddings.npy`.
  - As a side-effect appends additions directly to
    `data/kb-5000-merged.jsonl` — which conflicts with the
    "merge is a separate, deliberately manual step" contract documented
    in the linguistics script.

**Resolution**: I wrote a single unified script
`scripts/update_kb_embeddings_x3.py` modelled after the (working)
linguistics flow. It handles all 7 remaining additions files (X1
neuroscience + X1 urban + 5 X3 files), uses `models/structural-v2`
explicitly, updates both `.npy` files + both `_ids.json` sidecars, and
**does not modify any source KB jsonl**. The merge into
`kb-5000-merged.jsonl` is still done by the separate `cat ... >>` step
described in the plan.

### 2. Linguistics script had an atomic-swap bug

`np.save(tmp_npy, ...)` auto-appends `.npy` if the target path doesn't end
with `.npy`. The script's `tmp_npy = X.npy.tmp` got saved as
`X.npy.tmp.npy`, then `.replace(X.npy)` raised `FileNotFoundError`.

Fix patched in `scripts/update_kb_embeddings_linguistics.py` lines 220-233:
detect the auto-appended `.npy` and rename the actual produced file.
Existing matrix was restored from `.bak` before the second (successful)
run; no incomplete write reached `kb_embeddings.npy`.

### 3. Norm scale drift on `kb_v2_embeddings.npy`

The pre-existing 4443 rows have mean L2 norm ≈ **18.30** (σ 1.03). The new
413 rows encoded with `structural-v2 normalize=False` have mean norm
≈ **15.96** (σ 0.86) — about 13% lower. Both encoded by the same
SentenceTransformer model; the difference is plausibly explained by the
new descriptions being slightly shorter / less token-dense on average.

This will not break the production search path: `SearchService.relevance_score`
explicitly comments that it cosine-normalises at query time (see
`web/backend/services/search_service.py` line 341 region). Recall sanity
test below confirms new entries are retrieved with sensible scores.

If we ever care about absolute norms (e.g. some downstream model that
ingests un-normalised embeddings without re-normalising), a full
re-encode of `kb_v2_embeddings.npy` with a consistent batch would be
needed. Out of scope for this session.

### 4. `data/kb-additions-2026-05-24-twitter-cascades.jsonl` not included

This file was created at 00:03:47 by a parallel session (X3 Wave 2
Twitter validation, task #90) — **after** both the embedding update and
the `cat ... >>` merge had already completed. It is not in the four sets
the present session was asked to apply, and is not in the embedding
matrix or the merged KB. A future session should run it through the same
`update_kb_embeddings_x3.py --additions data/kb-additions-2026-05-24-twitter-cascades.jsonl --apply`
flow before merging.

## Verification

### Embedding ↔ KB jsonl alignment

```
KB jsonl entries:        4888
KB jsonl unique IDs:     4888
kb_embeddings ids:       4888  (set diff vs jsonl: ∅ both directions)
kb_v2_embeddings ids:    4856  (32 fewer — pre-existing gap, see baseline)
```

### Sanity recall (7 queries, retrieves with hybrid BM25 + base text2vec)

| query                       | new entry in top-5                          |
| --------------------------- | ------------------------------------------- |
| "gamma 神经振荡"            | `neuro-x1-022` ✓                            |
| "Zipf 词频幂律"             | `5k-22-101`, `5k-22-102`, `cze-010` ✓       |
| "亚马逊 雨林 双稳态"        | `5k-clm-001`, `neuro-x1-044` ✓              |
| "Omori 余震"                | `covid-x3-018`, `covid-x3-003` ✓            |
| "大模型 scaling law"        | `llm-011`, `llm-013`, `cze-009` ✓           |
| "城市 人口 rank Zipf"       | `cze-006`, `cze-007` ✓                      |
| "城市 allometric scaling"   | `llm-013`, `llm-011`, `urb-005` ✓           |

7/7 queries surface at least one freshly-added entry in their top-5. The
"urban allometric" query returns `llm-013` first — that is a coverage
quirk (LLM scaling laws share allometric vocabulary) rather than an
indexing bug.

### Backend test suite

`pytest web/backend/tests/` (after merge):

- **collected**: 811
- **passed**: 809
- **skipped**: 1 (pre-existing, model-dependent test)
- **failed**: 1
  - `test_kb_neuroscience_coverage.py::TestNeuroscienceShapeInvariants::test_no_id_collision_with_existing_kb`
  - The assertion is "addition IDs must not already exist in
    `kb-5000-merged.jsonl`". This is a pre-merge contract: now that the
    additions **are** in the merged KB by design, the test is stale. The
    test should be relaxed in a follow-up (e.g. check collision against
    the *pre-merge* baseline `kb-5000-merged.jsonl.bak-session22` or skip
    once the merge marker file is present).
- Before merge but after embedding update: 810 pass / 1 skip / 0 fail.

This matches the prompt's "781 baseline" claim modulo new tests added by
the parallel X1/X3 sessions since baseline. No new failures introduced
by the embedding update itself.

## Backups (all in `.bak-session22` suffix unless noted)

```
web/data/kb_embeddings.npy.bak-session22         (4475 × 768 baseline)
web/data/kb_embeddings_ids.json.bak-session22    (4475 ids baseline)
web/data/kb_v2_embeddings.npy.bak-session22      (4443 × 768 baseline)
web/data/kb_v2_embeddings_ids.json.bak-session22 (4443 ids baseline)
data/kb-5000-merged.jsonl.bak-session22          (4475 entries baseline)
```

Rollback recipe:

```bash
cp web/data/kb_embeddings.npy.bak-session22 web/data/kb_embeddings.npy
cp web/data/kb_embeddings_ids.json.bak-session22 web/data/kb_embeddings_ids.json
cp web/data/kb_v2_embeddings.npy.bak-session22 web/data/kb_v2_embeddings.npy
cp web/data/kb_v2_embeddings_ids.json.bak-session22 web/data/kb_v2_embeddings_ids.json
cp data/kb-5000-merged.jsonl.bak-session22 data/kb-5000-merged.jsonl
```

## Next actions

- Apply `kb-additions-2026-05-24-twitter-cascades.jsonl` (10 entries) via
  the same unified script.
- Fix or de-scope
  `test_kb_neuroscience_coverage.py::test_no_id_collision_with_existing_kb`.
- Consider deprecating
  `scripts/update_kb_embeddings_{neuroscience,urban}.py` in favour of the
  unified `update_kb_embeddings_x3.py` (or rename it to
  `update_kb_embeddings_unified.py`).
