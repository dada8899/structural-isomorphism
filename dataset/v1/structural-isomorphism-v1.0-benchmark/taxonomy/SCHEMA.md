# V4 Per-Class YAML Taxonomy Schema

## Overview

The V4 taxonomy is a corpus of universality-class definitions used by the Structural Isomorphism pipeline. Each class file at `v4/taxonomy/classes/<class_id>.yaml` is a self-contained declarative spec covering: identity, mechanism (shared equation), measurable invariants, verified positive examples, plausible-but-rejected negatives, contested edge cases, and reference literature.

The corpus is intentionally normative: each class makes falsifiable claims about which phenomena are members, which are not, and what the quantitative signatures are. New phenomena are classified by matching against this corpus; new candidate classes are admitted only after a maturity audit against the same schema.

The legacy single-file seed taxonomy at `v4/taxonomy/universality_classes.yaml` is preserved unchanged for backwards compatibility with the V4 Layer 3 / 4 pipeline. The new per-class files in `v4/taxonomy/classes/` are the authoritative source going forward.

## File location & naming

- Directory: `v4/taxonomy/classes/`
- Filename: `<class_id>.yaml`
- `class_id` is snake_case, ASCII, lowercase, globally unique within the taxonomy
- Sub-class variants follow `<parent>_<variant_suffix>` (e.g. `gardner_collins_toggle_switch_Th1Th2`)

## Required keys

```yaml
class_id: <snake_case_string>          # globally unique identifier
status: <tier>                          # well-established | emerging | speculative
display_name: <english_short_title>     # human-readable English name
display_name_zh: <chinese_short_title>  # human-readable Chinese name
hub_phenomenon: <one_line_summary>      # the central phenomenon the class describes
shared_equation: <multiline_string>     # master equation(s) defining the class
key_invariants:                         # 3-7 measurable scaling laws / structural features
  - <string>
  - <string>
positive_examples:                      # phenomena confirmed (or strongly candidate) as members
  - phenomenon: <name>
    evidence: <one-paragraph quantitative summary>
    verified_at: <YYYY-MM-DD | "candidate">
    paper: <path_to_validation_paper>   # optional; only when Layer 5 verified
negative_examples:                      # 3-5 plausible near-misses
  - phenomenon: <name>
    reason: <mechanism mismatch + correct class assignment>
edge_cases:                             # 1-3 contested / borderline phenomena
  - phenomenon: <name>
    debate: <description of why class membership is uncertain>
references:                             # 5-10 canonical literature pointers
  - <citation_string>
```

Optional keys (used when needed):

```yaml
notes: <multiline string>               # extra context, especially for speculative classes
```

## Status tiers

The `status` field declares the maturity of class evidence and governs how the pipeline weights membership claims.

### `well-established`
- ≥ 1 Layer 5 phase verification has been completed (real-data fit of predicted exponents within band, controls passed, paper drafted)
- Class definition is stable; new members map cleanly without redefining the equation
- Currently: 2 classes — `soc_threshold_cascade` (6 verified systems: earthquake, S&P 500, DeFi × 3 protocols, mouse cortex, wildfire, solar flare) and `preferential_attachment` (1 verified: GitHub stars Phase 6)

### `emerging`
- Strong theoretical basis (canonical physics/math prototype identified)
- ≥ 3 cross-domain candidate members listed in V3 mechanism graph
- No Layer 5 verification yet, but predictions are concrete and falsifiable
- Currently: 13 classes — `delay_differential_debt`, `extreme_value_tail_class`, `gardner_collins_toggle_switch`, `hysteresis_first_order_transition`, `leaky_integrate_fire_threshold_class`, `markov_chain_memory_fidelity_class`, `motter_lai_network_cascade`, `percolation_connectivity`, `reaction_diffusion_steady_state_class`, `reflexive_fixed_point_class`, `scale_free_percolation_class`, `second_order_damped_oscillator`, `sir_contagion_network_class`, `adverse_selection_unraveling_class`

### `speculative`
- LLM-proposed sub-class or cluster from automated taxonomy match
- Either narrows an emerging class to a specific domain instance, or aggregates loosely-related phenomena without sharp quantitative invariant
- May overlap heavily with a parent class; consolidation review pending
- Currently: 9 classes — `gardner_collins_toggle_switch_Th1Th2`, `gardner_collins_toggle_switch_apoptosis`, `hysteresis_first_order_transition_fertility`, `hysteresis_preisach`, `motter_lai_network_cascade_social`, `schelling_credible_commitment`, `scheffer_fold_bifurcation`, `tail_copula_contagion`

Promotion path: `speculative` → `emerging` requires consolidation review + canonical prototype identification. `emerging` → `well-established` requires Layer 5 paper with positive verdict.

## How to use the corpus

### For automated taxonomy match (Layer 3)
1. Score candidate hub against each class's `shared_equation` and `key_invariants` for semantic similarity
2. Boost scores for `well-established` classes (prior weight)
3. Penalize matches that fall into any `negative_examples` entry (mechanism mismatch is a strong signal)
4. Flag `edge_cases` matches for human review

### For Layer 4 prediction generation
1. Read the class's `shared_equation` and `key_invariants` to construct testable numerical bands
2. Use `positive_examples` evidence as calibration anchors for prediction ranges
3. The `paper` field links to ground-truth validation runs for transferable exponent values

### For Layer 5 verification audit
1. After running a real-data fit, compare result against `key_invariants` quantitative bands
2. Pass → append to `positive_examples` with `verified_at` and `paper` path
3. Mismatch but mechanism still applies → record as `edge_cases` with debate description
4. Mismatch and mechanism fails → record as `negative_examples` to prevent future misclassification

### For new-class admission
1. Draft full yaml against this schema (status: `speculative` initial)
2. Confirm uniqueness of `class_id` against existing files
3. Add ≥ 3 candidate `positive_examples` and ≥ 3 `negative_examples`
4. Submit for consolidation review; merge with parent class if overlap > 70%

## Validation

The schema can be validated programmatically (planned: `v4/lib/taxonomy_lint.py`):
- All required keys present
- `status` ∈ {well-established, emerging, speculative}
- `well-established` requires ≥ 1 `positive_examples` entry with non-null `paper` field
- `verified_at` matches `YYYY-MM-DD` regex or literal "candidate"
- Cross-reference: every `paper` path exists on disk
- Uniqueness: no two yaml files share the same `class_id`

## Versioning

Files are tracked in git. Schema changes go through:
1. Update this SCHEMA.md
2. Migrate existing files (or document grandfather exceptions)
3. Bump `v4/taxonomy/version` (planned)

Current schema version: **0.1** (initial release, 2026-05-13).
