# [data] Add `anderson_localization_transition` universality class YAML

## What

Add a universality-class YAML for the Anderson metal-insulator localization transition (disorder-driven phase transition in random Hamiltonians, with characteristic exponents `ν` and `s` differing across spatial dimensions).

## Why

The Anderson transition is one of the most-cited universality classes in condensed-matter physics. Several candidate phenomena in our discovery pipeline (e.g. transport in disordered networks, neural-network capacity collapse with random pruning) plausibly map onto it but currently lack a target class. Adding the YAML unlocks cross-judge verification.

## Where

- New file: `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/classes/anderson_localization_transition.yaml`
- Add entry to: `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/universality_classes.yaml`
- Format reference: `percolation_connectivity.yaml`

## How to start

1. Read [Evers & Mirlin 2008 Rev Mod Phys](https://doi.org/10.1103/RevModPhys.80.1355) for exponents and key invariants.
2. Set `shared_equation` to the conductance scaling `σ ~ (W_c - W)^s` and localization length `ξ ~ |W - W_c|^(-ν)`.
3. Document the dimension dependence (`ν ≈ 1.57` in 3D Anderson; 2D has no transition for orthogonal class).
4. List 3+ positive examples (Anderson tight-binding sim; bond-disordered photonic crystals; possibly DBM neural-net capacity collapse) and 2 negative examples (clean tight-binding; Bose-Einstein condensate).
5. Run `tools/validate_taxonomy.py`.

## Definition of done

- [ ] YAML in `classes/` directory
- [ ] Entry added to `universality_classes.yaml`
- [ ] Schema validation passes
- [ ] References at least 2 review papers in `notes` field
- [ ] CHANGELOG entry under `dataset/v1/.../taxonomy/`

## Difficulty

★★★ (requires familiarity with disordered-systems physics)
