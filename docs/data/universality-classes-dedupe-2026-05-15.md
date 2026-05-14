# Universality classes — duplicate `class_id` resolution

> Decision record. Status: resolved. Last updated: 2026-05-15.

## Problem

`web/frontend/assets/data/universality-classes.json` is the public-facing
taxonomy consumed by:

1. **Structural Search** (beta.structural.bytedance.city) — used to render
   the universality-class detail pages and back-link KB entries to their
   shared structure.
2. **Phase Detector** (phase.bytedance.city) — used to map a company's
   detected `dynamics_family` onto its prototype universality class.
3. **35-class taxonomy YAML** in `v4/taxonomy/` (kept in sync with this
   JSON via the B4 ensemble run pipeline).

Both products key off the `class_id` field as the canonical identifier.

During session #9 (W6-E audit), two duplicate `class_id` values were
discovered in the JSON:

- `motter_lai_network_cascade` (2 entries)
- `gardner_collins_toggle_switch` (2 entries)

The duplicates were not data-entry errors. They are real artifacts of the
Louvain community-detection step that produced the cluster set: in both
cases the B3 consensus graph yielded two genuinely distinct
sub-communities that share the same physics prototype but cover
non-overlapping empirical domains.

For example, `motter_lai_network_cascade` clustered traffic / civil /
geology phenomena into one community and blockchain / social-science /
financial-microstructure phenomena into a second community. Both
communities meet the Motter-Lai load-redistribution cascade prototype but
the cross-edges and member entries differ.

## Options considered

| Option | Pro | Con |
|---|---|---|
| **A. Delete the lower-rank entry** | Single ID, smallest JSON | Loses Louvain signal that two distinct sub-communities exist; downstream taxonomy YAML retains both, would silently drift |
| **B. Merge into one entry with union of members** | Preserves all members | Conflates two communities the clustering deliberately separated; misrepresents the B3 signal |
| **C. Suffix the lower-rank entry with `_v2`** | Both communities preserved with full metadata; matches taxonomy YAML; deterministic and reproducible | Slightly clunky ID; future re-cluster might produce `_v3` etc. |

## Decision

**Option C** (already implemented in commit `bfdf2b0`, 2026-05-14).

Rationale:

- Both Louvain sub-communities are independently meaningful and the B4
  ensemble run treats them separately. Collapsing them (Option A or B)
  loses information that the rest of the pipeline relies on.
- The `_v2` suffix is a stable, reproducible convention. Future
  re-clustering runs can produce `_v3`, `_v4` etc. without churning the
  base identifier — important because external citations may have already
  pinned the base `class_id`.
- Downstream consumers (search engine, phase detector) already treat
  unknown suffixes gracefully — a `_v2` simply renders as a sibling class
  with its own page.

## Resulting state

- `motter_lai_network_cascade` — Traffic / Civil / Geology cluster
  (rank 4).
- `motter_lai_network_cascade_v2` — Blockchain / Social science /
  Financial microstructure cluster (rank 13).
- `gardner_collins_toggle_switch` — Immunology / Molecular biology /
  Developmental biology cluster (rank 6).
- `gardner_collins_toggle_switch_v2` — Gene editing / Microbiology /
  Cell biology cluster (rank 15).

All 23 `class_id` values are now unique. The B4 taxonomy YAML in
`v4/taxonomy/` mirrors this suffix policy.

## Regression guard

`tests/test_universality_classes_unique.py` adds five assertions:

1. The taxonomy file exists.
2. Every entry has a `class_id`.
3. All `class_id` values are unique.
4. Every `class_id` is lowercase snake_case.
5. Any `_v2`-suffixed entry differs from its base on domains / rank /
   name_en / hub_name (otherwise it would be a true duplicate that should
   have been merged, not suffixed).

These run under the `sanity` marker — under 30s, included in the default
CI sweep. A future re-cluster run that re-introduces a collision will be
detected at PR time, not in production.

## Policy for future re-clusters

When the B3 / B4 pipeline produces a fresh taxonomy:

1. Run the pipeline.
2. Run `pytest tests/test_universality_classes_unique.py -v`.
3. If `test_class_ids_are_unique` fails, inspect the colliding entries:
   - **Truly identical** (same domains, same members, same prototype) →
     merge into one entry.
   - **Distinct sub-communities** (different Louvain components, same
     prototype) → suffix the lower-rank entry with the next available
     `_vN`. Update this document with the new entry. Re-run the test.
4. Never delete the base entry to resolve a collision — external
   citations may depend on it.

## References

- Commit `bfdf2b0` — original F1 fix that introduced the `_v2` suffix.
- W6-E session #9 audit report (this PR).
- Louvain methodology: Blondel et al., *Fast unfolding of communities in
  large networks*, J. Stat. Mech. (2008).
