# [data] Add `fractional_brownian_crossings` universality class YAML

## What

Add a new universality-class YAML to the taxonomy describing the level-crossing process of fractional Brownian motion (fBm). The class governs return-time distributions in long-range-correlated time series with Hurst exponent `H ≠ 0.5`.

## Why

The current taxonomy under `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/classes/` (35 YAMLs) has good coverage of percolation, hysteresis, and threshold processes but no class for long-memory diffusion. Several existing validation systems (Wikipedia page-view fluctuations, network-traffic anomalies) likely belong here but currently get force-fit into `markov_chain_memory_fidelity_class.yaml`. Adding fBm crossings gives a proper home.

## Where

- New file: `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/classes/fractional_brownian_crossings.yaml`
- Format reference: `percolation_connectivity.yaml` in the same directory
- Schema: `dataset/v1/structural-isomorphism-v1.0-benchmark/taxonomy/SCHEMA.md`

## How to start

1. Read `SCHEMA.md` for required fields (`class_id`, `status`, `display_name`, `hub_phenomenon`, `shared_equation`, `key_invariants`, `positive_examples`, `negative_examples`).
2. Pull the canonical equations from [Ding & Yang 1995](https://doi.org/10.1103/PhysRevE.52.207) — return-time PDF goes as `P(τ) ~ τ^(H-2)` for H ∈ (0,1).
3. Add 3 positive examples (e.g. fBm-simulated returns, river-flow Hurst > 0.5, internet packet arrivals) and 2 negative examples (memoryless Poisson, pure white noise).
4. Run `python tools/validate_taxonomy.py` to confirm schema compliance.
5. Open a parallel discussion thread (mention "needs cross-judge ensemble verification") so a maintainer can dispatch the LLM verifier.

## Definition of done

- [ ] YAML file passes `tools/validate_taxonomy.py`
- [ ] At least 3 positive examples + 2 negative examples
- [ ] Citation to Ding & Yang 1995 (or equivalent) in `shared_equation` block
- [ ] Listed in `universality_classes.yaml` index
- [ ] PR description includes the rationale for breaking out from `markov_chain_memory_fidelity_class`

## Difficulty

★★ (no code, but requires reading a probability-theory paper)
