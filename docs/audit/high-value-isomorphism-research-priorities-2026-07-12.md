# High-value structural-transfer research priorities

Date: 2026-07-12
Status: internal prioritization; candidate hypotheses, not verified discoveries
Source pool: current curated discoveries, KB, taxonomy and empirical assets

## 1. Scoring rule

Shared equations alone receive no more than 15/100. A high-priority transfer
must generate a mechanism-discriminating prediction and change an intervention.

| Dimension | Weight | Question |
|---|---:|---|
| Novelty | 10 | Is the transfer meaningfully different from the obvious same-domain baseline? |
| Structural mapping | 15 | Are variables, state, feedback, boundary and timescale mapped without metaphor drift? |
| Mechanism discriminability | 15 | Can data distinguish the proposed mechanism from plausible alternatives? |
| Preregisterable predictions | 15 | Are there directional, quantitative and time-bounded failure conditions? |
| Intervention value | 15 | Does the transfer select a different action, not merely explain the past? |
| Reproducibility | 10 | Can an independent team obtain data and rerun the analysis? |
| Industry leverage | 10 | Would a true result materially change cost, safety or allocation decisions? |
| Governance and misuse safety | 10 | Can the work avoid harmful automation, financial overclaim or opaque targeting? |

Interpretation:

- `>=80`: deep-research candidate after external expert scoping.
- `65–79`: run a cheap falsification pilot first.
- `50–64`: retain as an exploratory analogy.
- `<50`: downgrade from curated discovery.

No current candidate scores >=90 because none has prospective intervention and
independent replication evidence. Scores below are research-priority estimates,
not probabilities of truth.

## 2. Shortlist

| Candidate | N | S | M | P | I | R | L | G | Total | Decision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Intersection spillback ↔ power-grid cascading failure | 7 | 13 | 13 | 13 | 14 | 8 | 9 | 8 | 85 | Top deep-research candidate |
| Margin/DeFi liquidation cascades ↔ network clearing | 5 | 14 | 13 | 13 | 15 | 8 | 10 | 6 | 84 | High leverage; strict financial boundary |
| Stablecoin peg dynamics ↔ damped control-system oscillation | 8 | 12 | 12 | 13 | 14 | 7 | 10 | 6 | 82 | Pilot with historical/offline data only |
| Supply-chain cascade ↔ financial contagion network | 6 | 13 | 12 | 12 | 14 | 7 | 10 | 7 | 81 | Deep research after data-access check |
| Product retention hysteresis ↔ magnetic hysteresis | 7 | 11 | 10 | 11 | 14 | 8 | 9 | 9 | 79 | Product pilot; not physics confirmation |
| Immune diversity ↔ model ensemble diversity | 8 | 10 | 9 | 10 | 12 | 8 | 9 | 7 | 73 | Cheap falsification before expansion |
| Secondary sanctions ↔ supply-chain bullwhip | 7 | 10 | 8 | 9 | 12 | 5 | 9 | 5 | 65 | Data/governance feasibility first |

The product-retention item comes from observed Workbench value testing rather
than the 39-item curated file. It is included because it has a direct user
intervention path, while many higher-scored “discoveries” do not.

## 3. Research dossiers

### D1 — Intersection spillback and power-grid cascading failure

Decision summary: test whether traffic control should optimize **network
containment and recovery**, not only local queue throughput.

Evidence available:

- Both systems have capacity-constrained networks and cascades after a local
  overload.
- The current discovery is internally rated, not externally validated.
- Traffic and grid assets already exist separately in the repository, but no
  shared prospective intervention test is recorded.

Counter-evidence and alternatives:

- Traffic queues conserve vehicles and have controllable signals; grid flows
  follow different physical constraints and protection logic.
- Ordinary demand peaks, poor signal timing or incidents may explain spillback
  without a Motter-Lai-like cascade.
- Similar cascade pictures do not establish common critical exponents.

Key unknown: does a topology-aware containment policy outperform the strongest
traffic-specific adaptive-signal baseline under held-out demand shocks?

Literature/competition baseline to verify:

- traffic cell-transmission/queueing and adaptive-signal control;
- grid cascading/load-redistribution models;
- graph cut, perimeter control and max-pressure control.

Data:

- public trajectory/signal datasets plus a reproducible traffic simulator;
- synthetic grid benchmark used only to validate implementation;
- road topology, signal plans, demand and incident logs with license checks.

Experiment:

1. Freeze networks, demand regimes, incident locations and evaluation horizon.
2. Compare local timing, max-pressure/perimeter baseline and transferred
   cascade-containment policy.
3. Hold out entire networks and incident types, not random timesteps.
4. Primary: network recovery time and fraction of links in spillback.
5. Guardrails: total delay, pedestrian/transit delay and spatial inequity.

Pilot: offline simulation followed by one traffic-engineering partner's shadow
replay; never alter live signals in the initial study.

Stop conditions:

- no held-out improvement over traffic-specific baseline;
- benefit disappears after equal control budget;
- safety/equity guardrail worsens materially;
- mapping requires grid-only variables with no traffic operational meaning.

Depth: Level 3 — mechanism-discriminating offline experiment; not yet field
causality.

### D2 — Liquidation cascades and network clearing

Decision summary: test whether risk controls should target **exposure topology
and loss absorption** rather than account-level collateral ratios alone.

Evidence available:

- Repository contains real DeFi liquidation analyses and finance-cascade
  taxonomy assets.
- Cross-protocol heavy-tail/temporal signatures are recorded, but shared tails
  do not establish a common clearing mechanism.
- Phase alpha backtest is NULL and is unrelated to this risk-control hypothesis.

Counter-evidence and alternatives:

- DeFi liquidations depend on oracle timing, gas, bots and protocol rules;
  traditional network clearing has different legal and balance-sheet dynamics.
- Common market shocks can create correlated liquidations without propagation.
- Event reconstruction may miss private positions and off-chain hedges.

Key unknown: after conditioning on the common price shock, does network position
and absorption capacity predict secondary liquidation propagation?

Baselines to verify:

- account-level health factor and volatility models;
- clearing-network/cascading-default models;
- self-exciting process and common-shock nulls.

Data:

- timestamped on-chain events, oracle prices, block/gas conditions and protocol
  state; immutable chain ranges and extraction hashes;
- no user deanonymization or individual targeting.

Experiment:

1. Preregister cascade event, exposure proxy and common-shock controls.
2. Train on older protocol periods; hold out protocol and stress episodes.
3. Compare topology-aware propagation prediction against volatility/health
   baselines and shuffled-network nulls.
4. Simulate bounded risk controls: liquidation throttles, reserves or circuit
   breakers, without executing trades.

Metrics: secondary liquidations, cascade size calibration, false alarm, reserve
cost, bad debt and time to recovery.

Stop conditions:

- topology adds no held-out information after common-shock controls;
- inferred exposure is too incomplete for calibration;
- result is useful only as a trading signal rather than system-risk control;
- intervention transfers loss to users without transparent governance.

Depth: Level 3/4 — real observational mechanism test plus offline policy
simulation; no causal or investment claim.

### D3 — Stablecoin peg dynamics and damped control oscillation

Decision summary: test whether peg controllers should be tuned and stress-tested
using damping/recovery diagnostics rather than static deviation thresholds.

Evidence available:

- A curated candidate connects peg recovery to relaxation oscillation/damping.
- Historical stablecoin time series and protocol-rule changes are in principle
  observable; no repository experiment currently validates the transfer.

Counter-evidence and alternatives:

- Peg dynamics are strategic, reflexive and liquidity-constrained, not a fixed
  linear physical controller.
- Runs, governance intervention and oracle failure create regime changes.
- Apparent oscillation may be exchange microstructure or sampling aliasing.

Key unknown: do preregistered damping features predict recovery versus runaway
depeg better than liquidity, volatility and reserve baselines across protocols?

Baselines to verify:

- control-system damping/step-response diagnostics;
- market-liquidity and bank-run models;
- protocol-specific health/risk dashboards.

Data:

- multi-venue prices, liquidity depth, mint/burn, collateral/reserve and rule
  changes with time-aligned provenance;
- exclude unverifiable reserve claims or label them explicitly.

Experiment:

1. Define perturbation onset without looking at eventual recovery.
2. Estimate damping/recovery features from a fixed early window.
3. Hold out entire protocols and later episodes.
4. Compare to liquidity/volatility/reserve baselines.
5. Use an offline digital-twin stress test; no automated trading.

Metrics: recovery classification, time-to-recovery calibration, runaway-depeg
recall, false alarm and robustness across sampling intervals.

Stop conditions:

- features depend on post-outcome data;
- no protocol-held-out improvement;
- nonstationarity prevents stable early-window estimation;
- product use drifts toward price prediction or financial advice.

Depth: Level 2 now; Level 3 after held-out historical validation.

### D4 — Supply-chain cascade and financial contagion

Decision summary: test whether procurement resilience improves by identifying
**loss-amplifying network positions**, not merely high-spend suppliers.

Evidence available:

- Both domains have directed obligations/dependencies, buffers and cascades.
- Repository labels the connection partial; no independent industry dataset or
  intervention outcome is recorded.

Counter-evidence and alternatives:

- Supply chains include substitution, lead times and physical capacity;
  financial obligations are more fungible and differently observable.
- Firm-level data are censored and commercially sensitive.
- Correlated macro shocks can mimic propagation.

Key unknown: does a contagion-style centrality/clearing model identify disruption
impact beyond spend, tier, geography and single-source baselines?

Baselines to verify:

- multi-tier supply-risk scoring, inventory/lead-time simulation;
- financial contagion and clearing networks;
- causal common-shock and geographic controls.

Data:

- one consenting firm's de-identified supplier graph, lead times, inventory,
  substitutions and historical disruptions;
- public shipment/trade data only where license and entity matching are sound.

Experiment:

1. Freeze disruption episodes and data cut.
2. Train on older events and hold out supplier regions/categories.
3. Compare topology-aware scores to procurement baselines.
4. Prospective shadow pilot: prioritize audits/buffers, not supplier exclusion.

Metrics: disruption recall, recovery time, inventory cost, false-positive audit
load and small-supplier fairness.

Stop conditions:

- graph coverage below a preregistered completeness floor;
- topology adds no held-out value;
- model causes opaque supplier exclusion or discriminatory procurement;
- no partner can reproduce entity matching.

Depth: Level 3 if a partner dataset is secured; otherwise retain as exploratory.

### D5 — Retention hysteresis and user-state segmentation

Decision summary: test whether retention teams should first identify reversible
versus near-zero-repeat-demand cohorts before optimizing generic onboarding.

Evidence available:

- Internal dogfood found this reframe actionable and more distinctive than a
  generic LLM answer.
- No prospective user experiment or validated hysteresis curve exists.
- Magnetic terminology is a thinking scaffold, not evidence of a physical law
  in users.

Counter-evidence and alternatives:

- one-time product demand, acquisition mix, novelty decay and measurement error
  can explain low retention without path dependence.
- push exposure is confounded by user intent.
- cohort segmentation may simply rediscover standard lifecycle analysis.

Key unknown: does history-dependent segmentation change which intervention wins
in a prospective test relative to standard lifecycle cohorts?

Baselines to verify:

- lifecycle/cohort survival analysis;
- uplift/heterogeneous-treatment modeling;
- generic LLM/product analytics recommendation.

Data:

- consented product event data with acquisition, activation, exposure and return;
- minimize personal data, enforce cohort-size/privacy thresholds.

Experiment:

1. Define state/history features before observing treatment outcome.
2. Compare standard cohort, hysteresis-inspired state model and simple survival
   baseline.
3. Randomize a low-risk intervention within eligible cohorts.
4. Primary: incremental retained users, not model fit.

Stop conditions:

- no treatment-effect heterogeneity beyond simple cohorts;
- segment is not stable prospectively;
- benefit relies on manipulative notification pressure;
- privacy or fairness guardrails fail.

Depth: Level 3 product pilot; never label as confirmed universality.

## 4. Candidates to downgrade

- Trust collapse ↔ coral bleaching: memorable but constructs and interventions
  are too underspecified; keep as metaphor until measurable state variables and
  discriminating alternatives exist.
- CRISPR spacer acquisition ↔ VC power-law returns: shared selection language
  does not map the generating process; financial outcome tails add little
  intervention value and invite overclaim.
- Piezo1 gating ↔ hedonic adaptation: incompatible discrete molecular gating and
  continuous psychological adaptation; taxonomy review already flagged this
  class split.
- Cognitive dissonance ↔ Lyapunov stability: a mathematical stability word is
  not a mechanism; no defensible state equation or intervention is supplied.
- Thermoset gel point ↔ technology adoption: threshold/percolation resemblance
  is weaker than established diffusion/network-adoption baselines unless a
  network-critical prediction beats them.
- Exothermic temperature curve ↔ shadow-bank multiplier: superficial nonlinear
  feedback with incompatible conservation and control variables.
- Morale collapse ↔ social-proof threshold: likely same-domain social mechanism,
  reducing distinctive transfer value.
- Multiple DeFi/earthquake duplicate pairs should be one research program, not
  separately counted discoveries.

## 5. Portfolio rule

Fund no more than two deep dossiers simultaneously: one public/safety network
case (D1 or D4) and one product/financial system case (D2, D3 or D5). Require a
cheap falsification milestone before data expansion. Publish stopped studies and
negative results with equal visibility.

The research portfolio succeeds when a transfer changes a decision under
held-out evidence. It does not succeed by increasing the number of candidate
pairs, equations, classes or draft papers.
