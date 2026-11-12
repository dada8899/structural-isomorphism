# V4 Layer 3 — Critic Pass on Universality-Class Candidates

**Date**: 2026-05-13
**Pass**: B1 critic rejection
**Classes reviewed**: 21 (15 LLM auto-curated + 6 additional from candidate_classes.jsonl that appeared in Layer 4 predictions)
**Critic principle**: "Power-law tail / shared distributional form is necessary but NOT sufficient for universality class membership. A universality class requires shared equation form + shared scaling exponents + shared critical mechanism."

---

## Overview Table

| class_id | review_verdict | confidence | flagged_count |
|---|---|---|---|
| hysteresis_preisach | SPLIT | medium | 3 |
| scheffer_fold_bifurcation | KEEP | high | 4 |
| motter_lai_network_cascade | KEEP | high | 3 |
| tail_copula_contagion | KEEP | medium | 1 |
| gardner_collins_toggle_switch_Th1Th2 | MERGE_WITH(apoptosis) | high | 1 |
| schelling_credible_commitment | REJECT | medium | 3 |
| extreme_value_tail_class | REJECT | high | 4 |
| delay_differential_debt | KEEP | medium | 0 |
| leaky_integrate_fire_threshold_class | SPLIT | medium | 1 |
| reflexive_fixed_point_class | KEEP | medium | 0 |
| adverse_selection_unraveling_class | SPLIT | high | 2 |
| motter_lai_network_cascade_social | MERGE_WITH(motter_lai_network_cascade) | high | 0 |
| hysteresis_first_order_transition_fertility | KEEP | high | 0 |
| gardner_collins_toggle_switch_apoptosis | MERGE_WITH(Th1Th2) | high | 0 |
| scale_free_percolation_class | KEEP | medium | 1 |
| percolation_connectivity | KEEP | high | 1 |
| preferential_attachment | KEEP | high | 1 |
| reaction_diffusion_steady_state_class | KEEP | high | 0 |
| markov_chain_memory_fidelity_class | REJECT | high | 1 |
| second_order_damped_oscillator | KEEP | high | 0 |
| sir_contagion_network_class | SPLIT | medium | 1 |

**Verdict distribution**: KEEP=11, SPLIT=4, MERGE=3, REJECT=3 (out of 21)
**Confidence**: high=13, medium=8 (no low)
**Total false-positive flags**: 27 (across 14 classes)
**Effective taxonomy after critic** (KEEP + post-merge consolidation): ~12 distinct classes, plus 2 demoted to statistical-descriptor catalogs, plus 4 dissolved into sub-classes.

---

## Top 5 Most Problematic Classes

### 1. extreme_value_tail_class — REJECT (high confidence)

This is the textbook example of the critic-pass concern. EVT (Fisher-Tippett-Gnedenko + Pickands-Balkema-de Haan) is a **statistical limit theorem**, structurally analogous to the Central Limit Theorem. It tells you: if X_i are iid with regularly varying tail, then max(X_i) converges in distribution to GEV. This is true across an enormous diversity of underlying mechanisms — the universality is in the limit object, not in the generating process.

Members include seed dispersal distances (mechanism: Lévy-flight wind transport), catastrophe-bond pricing (mechanism: compound Poisson event arrival), and wind loads on tall buildings (mechanism: Davenport spectrum + atmospheric boundary layer turbulence). These share *literally zero* mechanism in common; they share only the empirical fact that their tails are heavy enough to be GEV-fittable. Calling this a "universality class" in the dynamical-systems sense is a category error. Recommend demoting to a "statistical regularity" catalog rather than claiming it forms a unified class.

### 2. markov_chain_memory_fidelity_class — REJECT (high confidence)

Companion failure to EVT. First-order Markov property is also a statistical-limit-theorem property: many disparate physical processes are well-approximated by Markovian dynamics in appropriate limits (separation of timescales, weak memory). DNA methylation inheritance (enzymatic copying via DNMT1), X-chromosome inactivation (bistable Xist/Tsix regulatory loop), and generator on/off scheduling (unit-commitment optimization under operating constraints) share the property "transitions are approximately one-step memoryless" — which is true of dice rolls and queueing systems and ion channels and weather states. The shared π = πP equation is a statistical descriptor with no mechanistic content.

This class is exactly what the V4 critic pass is supposed to catch. Demote to descriptor-catalog.

### 3. schelling_credible_commitment — REJECT (medium confidence)

This class clusters game-theoretic concepts — commitment with sunk costs, Kydland-Prescott time inconsistency, holdup with incomplete contracts, multi-issue bargaining linkage. The shared "equation" (payoff(commit) > payoff(flexible) iff sunk_cost > defection_gain) is a static inequality, not a scaling law. There are no critical exponents, no continuous order parameters, no shared dynamics. This is a topical cluster of related strategic-behavior concepts in game theory, not a universality class in the physics sense. It also has the lowest avg_edge_score (5.575) in V4 — the embedding model was already signaling weakness.

### 4. hysteresis_preisach — SPLIT (medium confidence)

The Preisach model is very specific: an ensemble of independent two-state hysterons with a continuous distribution μ(α,β) of switching thresholds, giving wiping-out and congruency properties. Many members of this class share "has a hysteresis loop" surface phenomenology but use different mechanisms: Granovetter threshold cascades (single collective state, one-shot tipping), Maxwell-construction first-order transitions (free-energy double well, single order parameter), and martensitic transformations (strain-compatibility-driven). All produce loops; none uses the Preisach hysteron ensemble. Recommend splitting into (a) genuine Preisach distributed-hysteron class, (b) Maxwell first-order transition class. The hub phenomenon itself (thermoset resin gelation) is actually Flory-Stockmayer percolation, not hysteresis — a structural mis-rooting.

### 5. adverse_selection_unraveling_class — SPLIT (high confidence)

Akerlof lemons unraveling has a *very specific* mechanism: (1) hidden quality dimension, (2) E[q|p] conditioning, (3) monotone exit of high-quality types, (4) market collapse. The auto-curator grouped silent-spiral opinion dynamics (Noelle-Neumann) and recommender-algorithm filter bubbles into this class on the surface basis that "diversity decreases over time." But silent-spiral has no hidden quality dimension — everyone observes opinions; the driver is conformity pressure. Filter bubbles are algorithmic engagement-optimization feedback; no information asymmetry. Recommend splitting into (a) genuine economic adverse-selection (lemons, insurance death spiral, credit rationing), (b) social conformity-driven homogenization (handled by DeGroot, Deffuant, opinion-dynamics models).

---

## Top 5 Rock-Solid Classes

### 1. second_order_damped_oscillator — KEEP (high)

The cleanest universality class in V4. All three members (tall-building wind vibration with TMD, power-system small-signal oscillation with PSS, transient-stability swing equation) reduce to M·ẍ + C·ẋ + K·x = F(t) in the small-amplitude limit. The TMD↔PSS duality is well-established. ω₀ and ζ are real shared scaling parameters. The Q-factor 1/(2ζ) is a universal invariant. Could be expanded with LCR circuits, MEMS resonators, atomic spectroscopy linewidths — all share the same mathematical skeleton.

### 2. reaction_diffusion_steady_state_class — KEEP (high)

All three members (urban heat island, dewatering groundwater funnel, morphogen-gradient axis polarization) solve identically: ∂c/∂t = D∇²c − kc + S = 0, giving exponential or logarithmic radial profiles with characteristic length λ = √(D/k). Linear PDE, clean. The only caveat is the misnomer "reaction-diffusion" (which conventionally implies nonlinear reaction terms and Turing patterns) — should be renamed to "linear screening/diffusion" or "modified Helmholtz steady-state" to avoid confusion with the actual nonlinear reaction-diffusion universality class.

### 3. gardner_collins_toggle_switch (after merging Th1Th2 + apoptosis) — KEEP (high)

The strongest evidence-rich class in V4 once the two duplicate hubs are merged. The skeleton dS/dt = αS^n/(K^n + S^n) − βS with Hill coefficient n>1 giving bistability via saddle-node-pair geometry holds across Caspase apoptosis, T-helper polarization (Th1/Th2), synthetic-biology toggle switches, X-inactivation, cell-cycle G1/S Rb switch, and bacterial quorum sensing. Hill function ultrasensitivity is the shared mechanism, not just analogy. Recovers ~10 members across immunology, developmental biology, synthetic biology, and microbiology.

### 4. percolation_connectivity — KEEP (high)

Order parameter ∝ (p − p_c)^β with explicit critical exponents (β_{2D} = 5/36, ν = 4/3) is a genuine universality class in the statistical-physics sense. Members (social identity contagion, competitive defense thresholds) plausibly share these exponents — though that's the layer-4 prediction to validate. The class definition is conceptually airtight; the question is empirical membership. Just remove the active/index liquidity outlier which is a continuous price-impact feedback rather than connectivity percolation.

### 5. motter_lai_network_cascade (after merging social variant) — KEEP (high)

Load-redistribution cascade with capacity-bounded nodes, Eisenberg-Noe clearing vector. The shared equation is explicit and mechanism-specific (not just "things cascade"). Solid members: electric-grid blackouts, progressive building collapse, flash-crash liquidity spirals, bank runs, DeFi protocol liquidations. Recommend pruning bystander-effect (no load redistribution, no capacity), GPS rerouting (congestion game not load-shedding), and Coulomb earthquake stress transfer (continuous-medium elasticity, belongs in SOC). The remaining core is one of the most physically grounded classes in the catalog.

---

## Methodology

The critic pass applied four explicit filters:

1. **Shared mechanism, not shared descriptor.** Statistical limit theorems (CLT, EVT, Markov property) produce universal limit objects from disparate mechanisms; that is not a universality class in the dynamical sense. Two classes were rejected on this basis (extreme_value, markov_chain_memory).

2. **Equation form must be specific, not generic.** "Has a hysteresis loop" is too generic — Preisach distributed-hysteron mechanism is very different from Maxwell first-order transition. "Has a power-law tail" is too generic — preferential-attachment growth differs from cumulative-advantage scoring without graph growth. Two classes were split on this basis (hysteresis_preisach, preferential_attachment partially).

3. **Mechanism must imply shared scaling exponents.** True universality classes share not just the existence of critical points but the values of β, ν, etc. (or analogous invariants). Where the V4 candidates share a critical point but not a specific exponent prediction, confidence was downgraded.

4. **Provenance artifacts must be merged.** Two M-L cascade classes (one connected-component, one Louvain-community) describe the same mechanism. Two Gardner-Collins toggle-switch classes (Th1/Th2 hub, apoptosis hub) describe the same mechanism. These should be merged on second pass.

For the five LLM-auto-proposed classes flagged in the task prompt as requiring extra skepticism (extreme_value, leaky_integrate_fire, Akerlof_lemons, Markov_fidelity, SIR_contagion), three were rejected/split substantially (extreme_value REJECT, leaky_integrate_fire SPLIT, Akerlof_lemons SPLIT, Markov_fidelity REJECT), and two were kept with strong qualifications (SIR_contagion SPLIT to restrict to true SIR rather than financial cascades; reflexive_fixed_point KEEP with merge candidates noted). The bias toward over-broad universality claims predicted by the task prompt was strongly confirmed.

Negative examples ("near-miss" phenomena that look like they should belong but don't) were generated by selecting phenomena that:
- share the surface descriptor (heavy tail, hysteresis loop, threshold tipping)
- but use a different generating mechanism
- and would be confusable in informal analysis

Common patterns of false-positive membership in candidate classes:
- Cascades vs branching processes (different topology dependence, often confused)
- Continuous vs discontinuous percolation (k-core, bootstrap, explosive are NOT classical 2nd-order)
- SI vs SIS vs SIR vs Hawkes (different recovery/replication structure; often called "contagion" generically)
- Bistability vs metastability vs limit cycle (different attractor topology — relaxation oscillator looks bistable on short timescale)
- Lognormal vs power-law tail (visually similar in log-log plots over finite range; mechanism differs)

---

## Recommended Taxonomy v2 Changes

**Mergers** (reduces 21 → 18):
- `gardner_collins_toggle_switch_Th1Th2` + `gardner_collins_toggle_switch_apoptosis` → single `gardner_collins_toggle_switch` (recovers taxonomy seed name).
- `motter_lai_network_cascade` + `motter_lai_network_cascade_social` → single `motter_lai_network_cascade`.
- Optional: `hysteresis_first_order_transition_fertility` + `scheffer_fold_bifurcation` are sister classes (both fold-pair geometry); could be unified under `fold_bifurcation_bistability` with two diagnostic emphases (critical slowing down vs loop area), but keeping them separate preserves useful empirical distinctions.

**Demotions** (statistical descriptors, not universality classes — reduces 18 → 16 active classes):
- `extreme_value_tail_class` → demote to "Statistical tail catalog" (heavy-tailed phenomena); members keep their tail-fitting predictions but are no longer claimed as a universality class.
- `markov_chain_memory_fidelity_class` → demote to "Memoryless-approximation catalog"; same treatment.

**Rejections** (game-theoretic clusters, not dynamical universality — reduces 16 → 15 active):
- `schelling_credible_commitment` → dissolve into separate game-theoretic taxa (commitment-with-sunk-costs, time-inconsistency, holdup, issue-linkage). Not a universality class.

**Splits** (preserves total class count but disentangles mechanisms):
- `hysteresis_preisach` → (a) Preisach distributed-hysteron class, (b) Maxwell first-order transition class. Re-root (b) on magnetism or soil-moisture, not on resin gelation (which is percolation).
- `leaky_integrate_fire_threshold_class` → restrict to genuine LIF (neurons, token bucket). Move Piezo1 to mechano-gating class, hedonic adaptation to continuous-setpoint-adaptation class.
- `adverse_selection_unraveling_class` → (a) economic adverse-selection (lemons, insurance, credit), (b) social conformity opinion dynamics (silent spiral, echo chamber).
- `sir_contagion_network_class` → restrict to true SIR (epidemics, rumor-with-stifling, marketing-fatigue). Move financial-cascade members to motter_lai_network_cascade.

**Renaming**:
- `reaction_diffusion_steady_state_class` → `linear_screening_diffusion_class` or `modified_helmholtz_steady_state` (the current name suggests Turing pattern formation, which is a different universality class with nonlinear reaction terms).

**Pruning false-positive members** (does not change class count but improves membership accuracy): 27 members across 14 classes flagged for removal. Highest-impact prunes:
- scheffer_fold_bifurcation: drop 4 cooking-science / metallurgy outliers (果胶凝胶, 淀粉糊化, 形状记忆合金, 热障涂层).
- extreme_value_tail_class: all 4 members lose universality-class claim though tail-fitting predictions remain valid.
- motter_lai_network_cascade: drop bystander-effect, GPS rerouting, Coulomb earthquake stress transfer.
- hysteresis_preisach: drop technology-adoption and Fischer-Tropsch reconstruction.

**Net result of taxonomy v2**: 15 active universality classes (down from 21 candidates) + 2 statistical-descriptor catalogs + dissolved game-theoretic cluster. The 15 active classes are mechanistically well-grounded and most have explicit scaling-exponent predictions, satisfying the standard for genuine universality classes from statistical physics.

**Highest-priority next-pass action**: re-run Layer 4 prediction generation only on the 15 surviving active classes with pruned membership, dropping the 27 flagged false-positive predictions. This should significantly improve the layer-4 calibration scores by removing predictions made on mechanism-mismatched members.
