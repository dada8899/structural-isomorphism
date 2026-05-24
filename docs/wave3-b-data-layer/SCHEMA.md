# Reproducible Data Layer — Schema Spec (Wave 3 B pilot, 2026-05-25)

## 1. Purpose

The KB at `data/kb-5000-merged.jsonl` describes 4 888 structural-isomorphism
candidates with `description` only. To validate any candidate against a
universality class (e.g. Clauset power-law fit, Scheffer EWS) we need
**reproducible bindings** between each KB entry and (a) the public
dataset that lets a third party rerun the test, (b) the sampling schema
that converts raw data into events, and (c) the literature anchor that
defines the prototype.

This schema specifies the additive `data_layer` field. The pilot
deliverable `data/kb-reproducible-data-layer-2026-05-25.jsonl` populates
this field for the top-200 highest-priority KB entries (Wave 2A/B/C
verified-class members + high-confidence anchors).

## 2. Compatibility

The `data_layer` field is **purely additive**. Existing consumers that
ignore unknown keys (the v4 validation pipeline, the JS frontend at
`web/frontend/`, the paper-side dataset card builder) keep working
without modification. Tools that want to use it should look for the
`data_layer` key and degrade gracefully when it is missing.

The main KB file itself is untouched. The merge happens through
`scripts/merge_data_layer.py`, which writes to
`data/kb-5000-merged-with-layer.jsonl` and leaves the source intact.

## 3. Field spec

Each KB entry, after merge, looks like:

```json
{
  "id": "5k-01-001",                    // existing — primary key
  "name": "...",                        // existing
  "domain": "...",                      // existing
  "type_id": "...",                     // existing
  "description": "...",                 // existing

  "data_layer": {
    "dataset_url":            "https://...",
    "dataset_doi":            "10.5066/F7MS3QZH",
    "dataset_license":        "Public Domain (US Govt)",
    "dataset_size_estimate":  "~200 MB (M>=3, 1900-2024)",
    "sampling_schema": {
      "event_definition":     "Earthquake mainshock (declustered) ...",
      "size_unit":            "seismic moment M0 = 10^(1.5*Mw+9.1) (N·m)",
      "min_n_for_clauset":    50,
      "preprocessing_notes":  "USGS ComCat FDSN service; declustered ..."
    },
    "validation_status":      "empirical",
    "validation_command":     "v4 validate soc_threshold_cascade",
    "verified_at":            "2026-04-15",
    "lit_anchor":             "Gutenberg-Richter 1944; Bak 1996",
    "class_id":               "soc_threshold_cascade",
    "class_name_en":          "Self-Organized Criticality (threshold cascade)",
    "physics_prototype":      "Bak-Tang-Wiesenfeld sandpile (1987)",
    "is_hub_member":          false,
    "selection_tier":         1
  }
}
```

### 3.1 Top-level `data_layer` fields

| field | type | nullable | description |
|---|---|---|---|
| `dataset_url` | string (URL) | yes | Public landing page or download endpoint. Must be a real URL — when no curated public dataset is known, set `null` and put the reason in `sampling_schema.preprocessing_notes`. |
| `dataset_doi` | string (DOI) | yes | `10.xxxx/...` format. `null` when no DOI is known. |
| `dataset_license` | string | no | Free-text license tag (`CC-BY-4.0`, `Public Domain (US Govt)`, `Synthetic / model-based`, `Unknown`, etc.). |
| `dataset_size_estimate` | string | no | Human-readable size (`~200 MB`, `~5 GB`, `varies per dataset`). |
| `sampling_schema` | object | no | See §3.2. Always present, even when the dataset is unknown. |
| `validation_status` | enum | no | One of `anchor` / `empirical` / `synthetic` / `pending`. See §3.3. |
| `validation_command` | string | no | Reproducer command, currently `"v4 validate <class_id>"`. |
| `verified_at` | date string (`YYYY-MM-DD`) | yes | When the empirical fit was last verified. `null` when not yet run. |
| `lit_anchor` | string | no | `First-author YYYY` reference for the universality prototype (e.g. `Bak 1996`, `Diamond & Dybvig 1983`, `Gardner-Collins 2000`). |
| `class_id` | string | no | The universality class this KB entry belongs to (matches `universality-classes.json`). |
| `class_name_en` | string | no | Human-readable class name. |
| `physics_prototype` | string | no | English prototype name from the class metadata. |
| `is_hub_member` | bool | no | `true` if this entry is the hub for its class (one per class). |
| `selection_tier` | int | no | 1 = verified class, 2 = high-confidence non-verified class, 3 = other classes. Sets pilot priority. |

### 3.2 `sampling_schema` sub-object

| field | type | required | description |
|---|---|---|---|
| `event_definition` | string | yes | Concrete operational definition of what counts as a single event in this dataset. **No placeholders allowed** — every row in the pilot satisfies this. |
| `size_unit` | string | yes | Physical unit of the event size used for Clauset-style power-law fit. |
| `min_n_for_clauset` | int | yes | Minimum N events to attempt a Clauset fit. Default 50 for the pilot. |
| `preprocessing_notes` | string | yes | How to go from raw download to the event vector. Includes anchor references to which Wave-2 phase already exercised this pipeline, when applicable. |

### 3.3 `validation_status` enum

| value | meaning | typical population in pilot |
|---|---|---|
| `empirical` | A Clauset (or class-specific) fit has been run on this exact (class, domain) pair in Wave 2A/B/C and the binding survives. The `verified_at` date is filled and `dataset_url` points to the actual dataset used. | 34 / 200 (17 %) |
| `anchor` | A textbook anchor (literature prototype) binds the class to this entry; dataset URL is real but no in-repo fit has been re-run for this specific KB id yet. | 1 / 200 (≈0.5 %) |
| `synthetic` | The natural validation route is a model simulation (Ising / BTW / Gardner toggle) — no archival dataset, but reproducible via the model spec in `preprocessing_notes`. | 5 / 200 (2.5 %) |
| `pending` | We have a credible dataset / anchor for the class but no fit has been run on this exact KB row, and no curated override exists for `(class_id, domain)`. Default fallback. | 160 / 200 (80 %) |

## 4. Cardinality & population strategy

The pilot populates **200 entries** out of 4 888 (≈ 4.1 %). Selection is
priority-based — see `docs/wave3-b-data-layer/pilot-200-report.md`.

The pilot operates on a **catalog of `(class_id, domain)` overrides** for
the high-confidence Wave 2 anchors and a **per-domain default
template** for everything else. When a row has no override, it falls
through to its domain default; when neither exists, it falls through to
a final `null + pending` triple with an honest "no curated dataset
known" note in `preprocessing_notes`. **No URLs are fabricated.**

For the full 4 888-row roll-out (Wave 3 B+ / Wave 4) we expect the
override catalog to grow by roughly 10x and the per-domain defaults to
remain stable.

## 5. Merge protocol

```
$ python3 scripts/merge_data_layer.py --dry-run
$ python3 scripts/merge_data_layer.py
$ mv data/kb-5000-merged-with-layer.jsonl data/kb-5000-merged.jsonl   # user does this manually
```

- The script never writes to the main KB.
- `--dry-run` prints match stats without producing output.
- Match key is `id`. Layer rows without a matching KB id are reported as
  `orphans`; KB rows without a matching layer row are passed through
  unchanged with no `data_layer` field.
- Re-running the merge is idempotent — the new layer overwrites any
  prior `data_layer` value (the script logs an `overwritten_existing_layer`
  count when this happens).

## 6. Versioning

This is version `2026-05-25` of the layer. Future layers should:

1. Use a new filename pattern `data/kb-reproducible-data-layer-YYYY-MM-DD.jsonl`.
2. Bump a top-level `data_layer.layer_version` field once we add it (not
   in the pilot — kept additive-only for now).
3. Preserve the field names above; treat changes as breaking.

## 7. Validation rules (consumers SHOULD enforce)

- `dataset_url` either `null` or matches `^https?://`.
- `dataset_doi` either `null` or matches `^10\.\d{4,9}/`.
- `validation_status` is one of the four enum values in §3.3.
- `verified_at` either `null` or matches `^\d{4}-\d{2}-\d{2}$`.
- `sampling_schema.event_definition` is a non-empty string with at
  least 20 characters (no placeholders).
- `sampling_schema.min_n_for_clauset` ≥ 1.
