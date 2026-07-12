# Structural Isomorphism as an AI-for-Science paradigm

Date: 2026-07-12
Status: independent scientific-method audit and falsifiable research program
Runtime authority: `NEXT_SESSION.md`
Evidence boundary: repository evidence only; this document does not establish
external replication, scientific priority, product-market fit, or a new law of
nature

## 1. Decision

Structural Isomorphism can become a genuinely differentiated AI-for-Science
engine, but only under a narrower and more demanding definition than “AI finds
surprising analogies.” The proposed paradigm is:

> **Reject-aware structural transfer science**: a closed-loop method that
> converts an unresolved phenomenon into a mechanism-bearing structural
> fingerprint; retrieves structurally distinct candidate systems; derives
> discriminating predictions and explicit mismatch conditions; preregisters a
> cheapest decisive test; records PASS, FAIL, REJECT, NULL and INCONCLUSIVE
> outcomes symmetrically; and updates the candidate structure graph from the
> observed result.

The potential scientific contribution is not a universal taxonomy produced by
an LLM. It is an **instrument for generating and killing cross-domain
hypotheses under an auditable protocol**. A candidate becomes scientific only
when it predicts an observation that was not used to retrieve or select it and
when a plausible non-isomorphic control can fail differently.

The repository already contains components of this method: a 4,443-item
retrieval artifact, structural taxonomies, critic ensembles, preregistrations,
null controls, real-data pipelines, negative results, a claim-evidence ledger,
and an experiment/outcome product loop. It does not yet contain evidence that
the integrated engine accelerates or improves science prospectively.

## 2. What the new paradigm is—and is not

### 2.1 Unit of discovery

The engine's unit of discovery is not a document, analogy, equation, or fluent
explanation. It is a versioned **Structural Transfer Hypothesis**:

```text
STH = {
  source_system,
  target_system,
  shared_mechanism,
  state_variables,
  interaction_topology,
  governing_transform_or_dynamics,
  invariants_or_scaling_relations,
  boundary_conditions,
  predicted_target_observation,
  discriminating_control,
  falsifier,
  evidence_provenance,
  preregistration,
  terminal_verdict
}
```

An STH is admissible only if the shared mechanism and at least one mismatch are
stated, its target prediction is operational, and its evidence provenance is
recoverable. “Both have power laws,” “both have tipping points,” and “both can
be modeled by networks” are descriptors, not sufficient structural transfer
hypotheses.

### 2.2 Scientific discovery loop

The minimum closed loop has nine state transitions:

1. **Problem registration** — freeze the target question, current evidence,
   observable, decision cost and excluded uses before candidate exposure.
2. **Structuralization** — map prose or data to typed variables, relations,
   dynamics, constraints, symmetries, scale and known boundary conditions.
3. **Divergent retrieval** — retrieve source systems by structure while
   penalizing same-domain lexical overlap and exposing retrieval uncertainty.
4. **Adversarial qualification** — separate mechanism from statistical
   resemblance; require counter-evidence, mismatch and at least one alternative
   explanation; reject generic mathematical frameworks masquerading as classes.
5. **Prediction compilation** — translate a surviving mapping into a new,
   target-specific numerical, ordinal or qualitative prediction plus a matched
   non-class control.
6. **Preregistration** — freeze data, preprocessing, primary metric, threshold,
   multiplicity rule, stop rule, missing-data treatment and verdict ladder.
7. **Execution** — run the cheapest discriminating experiment or analysis in a
   reproducible environment; the model may prepare code but may not alter the
   locked primary analysis after seeing outcomes.
8. **Symmetric adjudication** — publish PASS, FAIL, REJECT, NULL,
   INCONCLUSIVE and protocol deviations with equivalent provenance and retain
   every eligible case in the denominator.
9. **Graph update** — strengthen, split, merge, downgrade or remove structural
   edges/classes; store which transfer changed a prediction and which failed.

The loop must be stateful outside chat. Each transition needs an immutable
artifact ID, actor, timestamp, model/code/data version, and authorization. A
generation without a terminal observation is a hypothesis proposal, not a
scientific discovery.

## 3. Difference from adjacent AI-for-Science approaches

| Approach | Primary object | Typical success signal | What this engine adds | Boundary it must respect |
|---|---|---|---|---|
| Literature search / RAG | relevant documents and synthesized answers | recall, relevance, citation coverage | retrieves systems by typed mechanism and compiles a falsifiable transfer | it cannot claim novelty or truth from retrieved prose |
| Scientific knowledge graph | entities and documented relations | graph coverage and link prediction | represents conditional structural mappings, mismatches, falsifiers and outcomes | predicted links remain candidates until prospective tests |
| General AI Scientist / autonomous research agent | end-to-end proposal, code, experiment and manuscript | task completion or model/reviewer score | constrains autonomy with preregistration, reject-aware gates and symmetric negative-result accounting | it is an engine inside a governed research process, not an autonomous author or submitter |
| Analogical reasoning system | source-target mapping | mapping plausibility or human-rated novelty | requires out-of-selection prediction, non-isomorphic controls and graph updates from failures | analogy quality is an intermediate metric only |
| Causal discovery | causal graph over variables within one or linked datasets | graph recovery, intervention prediction | proposes cross-domain mechanism priors and transport hypotheses | it does not identify causality without interventions or valid identification assumptions |
| Equation / symbolic-law discovery | compact equations fitting observations | predictive fit, description length | searches for a structure that may explain why a form transfers across systems | shared functional form alone does not establish shared mechanism |
| Simulation / surrogate modeling | predictions inside a defined model family | held-out error and speed | selects candidate model families from distant domains and proposes discriminating tests | the borrowed simulator must be recalibrated and validated on the target |
| Meta-analysis | aggregated evidence about a defined question | pooled estimate and heterogeneity | can originate a new cross-domain question and organize heterogeneous falsifiers | it cannot pool incomparable observables into false universality |

The clearest distinction is: literature search returns *what is known*;
causal discovery estimates *what causes what under assumptions*; a general AI
Scientist automates *research tasks*; this engine tests *whether a mechanism can
be transported across domains and what novel observation that transport
implies*.

## 4. Core technical engine

### M1 — Evidence and provenance substrate

- Canonical artifact manifests for data, embeddings, models, code and prompts.
- Row/sentence-level provenance classes: real, manual-coded,
  literature-derived, synthetic, model-judged and demo.
- Claim-evidence ledger with conflicts, supersession and submission blockers.
- Immutable experiment and outcome events; no silent deletion of failures.

Repository basis: the production manifest and claim-evidence ledger demonstrate
parts of this substrate. Row-level KB provenance and full raw-to-result DAGs are
not complete.

### M2 — Typed structural representation

- A machine-valid schema for states, operators, topology, dynamics, invariants,
  control parameters, observables, scale and boundary conditions.
- Separate labels for descriptive resemblance, mathematical equivalence,
  mechanistic homology, scaling concordance and candidate universality.
- Confidence decomposition by extraction, mapping, evidence and prediction—not
  one similarity percentage.

Repository basis: 84 historical structure types, StructTuple work and candidate
class YAMLs provide a seed, but external ontology review, leakage-free benchmark
validation and a stable supersession registry remain missing.

### M3 — Structure-first retrieval and graph induction

- Hybrid symbolic, embedding and graph retrieval.
- Same-domain and lexical-shortcut penalties.
- Explicit OOS/abstention and a diversity objective across source domains.
- Candidate graph whose edges store mapping clauses, falsifiers and verdicts,
  not merely similarity.

Repository basis: the 4,443-row production KB and retrieval benchmark are an
operational baseline. The existing qrels are development evidence from one LLM
judge, not a scientific gold standard; English expanded-pool human review is
still absent.

### M4 — Reject-aware hypothesis compiler

- Multiple model families generate and criticize mappings independently.
- Deterministic guards reject schema violations, unsupported citations,
  mechanism/descriptor confusion and hidden scope expansion.
- The compiler produces prediction, alternative explanation, mismatch,
  discriminating control and falsifier together.
- Human/domain-expert approval is mandatory before empirical claims advance.

Repository basis: `cross-judge` and `reject-aware-critic` implement reusable
critic patterns and identified more rejections on one 21-candidate internal
panel. That panel is not an independently labelled measure of false-positive
reduction, and its 33% versus 14% rejection rates are not accuracy estimates.

### M5 — Preregistration and experiment compiler

- Converts a qualified STH into a frozen executable manifest.
- Validates analysis plans, controls, threshold direction, multiplicity, power
  or precision target, stop rule and terminal verdict logic.
- Generates code in a sandbox and tests it on synthetic positive/negative
  controls without exposing target outcomes.
- Separates exploratory analyses from locked confirmatory analyses.

Repository basis: several timestamped preregistrations and negative/partial
outcomes show the intended discipline. Clean-room reproduction and prospective
engine-selected experiments are not established.

### M6 — Domain adapters and execution layer

- Typed adapters for observational data, simulation, laboratory protocols and
  external instruments.
- Domain-correct dependence, censoring, missingness, units and uncertainty.
- Containerized execution, checksum verification and resource/cost accounting.
- High-risk domains require human execution authority.

Repository basis: SOC, Phase, WTO and other pipelines show heterogeneous
adapters, but several data licenses/provenance chains and domain-specific
assumptions need independent audit.

### M7 — Verdict, learning and portfolio layer

- Machine-checkable PASS/FAIL/REJECT/NULL/INCONCLUSIVE ladders.
- Calibration by candidate type and domain; failure taxonomy and uncertainty.
- Outcome-conditioned graph update and active selection of the next experiment
  by expected information gain divided by cost/risk.
- Portfolio metrics count eligible hypotheses and terminal outcomes, not pages,
  tokens, candidates or positive discoveries.

Repository basis: the product has structured experiment/outcome concepts and
the research preserves several negative results. There is not yet a prospective
portfolio showing that outcome feedback improves later hypothesis selection.

## 5. Strongest defensible claims today

### Claim A — defensible as an engineering/method proposition

> The repository implements substantial components of a reject-aware,
> provenance-oriented workflow for proposing and testing cross-domain
> structural hypotheses, including retrieval, critic ensembles,
> preregistration, real/synthetic validation pipelines, negative-result
> preservation and claim-evidence checks.

This can be verified from versioned artifacts and tests. It is not a claim that
the integrated workflow is scientifically superior.

### Claim B — defensible as a bounded internal observation

> On the repository's 21-candidate internal panel, a later critic configuration
> rejected more candidates than the earlier single-critic stage and surfaced
> mechanism-versus-framework confusions that warrant empirical rejection.

This must retain panel, model-family and independence limitations. “Reduces
false positives by 57%,” “expert-level review,” and “generalizes across science”
are not supported without external gold labels.

### Claim C — defensible as methodological credibility

> The workflow can preserve predictions that fail or reverse sign instead of
> relabelling them as discoveries.

The repository's CVE/FDNY/WSB/Phase/WTO-related negative or bounded outcomes
support this behavior. Clean-room reproduction and preregistration chronology
still need audit before using them as publication-grade evidence.

### Claim D — the future landmark claim to earn

> On previously unseen scientific problems, the engine produces more valid,
> non-obvious and experimentally confirmed hypotheses per unit time/cost than
> strong literature-search, general-AI-scientist and expert-only baselines,
> while maintaining a lower serious false-positive rate.

This is not currently supported. It is the central prospective claim around
which the next research program should be designed.

## 6. Claims that remain prohibited

- “A general engine for scientific discovery” before multi-domain prospective
  superiority and external replication.
- “Discovers causal mechanisms” without intervention or identification.
- “Maps universal laws across all domains.”
- “Verified universality classes” based on internal LLM critics, synthetic
  anchors or shared distributional shape alone.
- “Autonomously writes publication-ready papers.”
- “Predicts markets,” “identifies alpha,” or any equivalent investment claim.
- Any positive count that omits rejected, null, failed, conflicted or missing
  outcomes from the denominator.

## 7. Falsification and shutdown conditions

The paradigm is weakened or falsified—not merely “in need of UX improvement”—if
one or more preregistered conditions persist:

1. **No predictive lift**: on a sealed benchmark and prospective portfolio, STH
   predictions do not beat matched literature/RAG and strong general-LLM
   baselines after controlling for expert time and information access.
2. **Novelty without validity**: the engine increases surprise ratings but not
   expert-supported predictions or terminal confirmations.
3. **Shape shortcut**: performance collapses when lexical overlap, domain
   labels and generic descriptors such as “power law” or “tipping point” are
   masked.
4. **Mechanism non-discrimination**: purported isomorphic and matched
   non-isomorphic systems yield indistinguishable predictions or errors.
5. **Negative transfer**: serious false-positive or harmful recommendation rate
   exceeds the strongest baseline or a predefined safety ceiling.
6. **Selection leakage**: target outcomes, near-duplicate systems, taxonomy
   labels or post-outcome sources enter retrieval, ranking, prompts or reviewer
   context before prediction lock.
7. **Reviewer dependence**: gains disappear under blinded external domain
   reviewers or clean-room reproduction.
8. **No learning from failure**: graph updates based on outcomes do not improve
   calibration or hypothesis yield on later frozen cohorts.
9. **Cost non-advantage**: equivalent validated findings require more expert
   time, elapsed time or total cost than baseline workflows.
10. **Domain fragility**: success is concentrated in one familiar domain or one
    statistical family and does not survive leave-one-domain/type-out tests.

After two well-powered prospective rounds fail conditions 1, 4 or 8, the broad
engine claim should be retired. The useful remainder may be reframed as a
reject-aware research workflow or audit tool rather than a discovery engine.

## 8. Gold benchmark: Structural Transfer Challenge

The required gold standard must test prospective transfer, not retrospective
storytelling. Call it provisionally **Structural Transfer Challenge (STC)**.

### 8.1 Benchmark tracks

1. **Masked known transfer** — historical source-target links with all
   post-discovery and target-revealing text removed; tests recoverability but is
   not evidence of new discovery.
2. **Adversarial non-isomorphism** — visually/statistically similar systems with
   different mechanisms, generic-framework traps and matched nulls.
3. **Prediction compilation** — given a source and partially observed target,
   produce a preregistrable discriminating prediction, mismatch and control.
4. **Prospective hidden-outcome** — target data collected after prediction lock
   or held by an independent evaluator; primary scientific track.
5. **Failure learning** — sequential rounds measure whether terminal outcomes
   improve ranking, calibration and experiment selection.

### 8.2 Composition

- At least 120 target problems across six top-level scientific areas, with no
  fewer than 15 targets per area and a meaningful mix of observational,
  simulated and experimental systems.
- At least one mechanism-positive source, one hard negative, one same-domain
  strong baseline and one cross-domain distractor per target where feasible.
- Query-, source-, structure-type-, domain- and chronology-grouped splits.
- A sealed final set administered by an external evaluation group.
- Real, synthetic and literature-derived cases explicitly separated.
- Dataset licenses, provenance, contamination audit and outcome timestamps.

These sample sizes are design targets, not power guarantees. A statistician
must determine final size from the primary estimand and expected clustering.

### 8.3 Human gold process

- Three independent reviewers per task: target-domain expert, source/mechanism
  expert and methods/statistics reviewer.
- Reviewers blind to system identity and other verdicts where the task allows.
- Predefined rubric for mechanism validity, prediction discriminability,
  novelty relative to frozen literature, actionability and harm.
- Disagreements adjudicated; raw anonymous ratings and exclusions preserved.
- Agreement is reported per dimension; consensus is not manufactured by an
  LLM.

### 8.4 Baselines

- Keyword and semantic literature search with an expert user.
- Strong general-purpose RAG/LLM with the same document and token budget.
- A general AI-research agent with the same tools, compute and elapsed-time cap.
- Same-domain expert workflow without structural retrieval.
- Structure engine without reject-aware critics.
- Structure engine without outcome graph learning.

The ablations are necessary to attribute improvement to the paradigm rather
than more compute, more context or better user interface.

### 8.5 Primary metrics

- **Validated Novel Prediction Yield (VNPY)**: externally adjudicated,
  non-trivial target predictions that pass their locked test divided by all
  eligible targets.
- **Serious False Transfer Rate (SFTR)**: high-confidence transfers judged
  mechanistically invalid or contradicted by decisive tests divided by all
  high-confidence transfers.
- **Time and cost per terminal validated hypothesis**, including expert review,
  failed runs and compute.
- **Calibration** of predicted probability versus terminal verdict.
- **Discriminating-control success**: rate at which positive and matched
  negative systems are correctly separated.

Secondary metrics include hypothesis novelty, expert correction burden,
coverage, abstention quality, reproducibility and negative-result completeness.
LLM-as-judge scores and retrieval nDCG are development diagnostics, not primary
proof of scientific utility.

### 8.6 Suggested initial gates

For a first externally evaluated continuation—not a world-changing claim:

- VNPY absolute lift at least 10 percentage points and relative lift at least
  25% over the strongest baseline, with a cluster-aware 95% interval excluding
  zero;
- SFTR no worse than baseline and below 5% for high-confidence outputs;
- at least 25% reduction in median total time to a terminal hypothesis without
  increasing expert correction burden;
- zero critical provenance, leakage, fabricated-citation or hidden-negative
  failures;
- effect direction positive in at least four of six scientific areas.

Thresholds must be frozen before seeing sealed outcomes and revisited only for
the next benchmark version. Failure to clear them is reported as failure.

## 9. Prospective validation ladder

### Stage 0 — Integrity and retrospective rehabilitation

Goal: prove the instrument is trustworthy enough to test.

- Complete canonical data/model/claim manifests and row-level provenance.
- Reproduce preregistered negative and positive assets in a clean environment.
- Build the supersession registry and remove contradictory universality counts.
- Complete English human review and leakage-free retrieval evaluation.
- Independently audit chronology of preregistrations and data access.

Exit: no critical provenance conflict; all retrospective claims are bounded and
reproducible. This establishes integrity, not discovery utility.

### Stage 1 — Historical blind reconstruction

Goal: test whether the engine can recover useful transfers without outcome or
identity shortcuts.

- 30–40 masked cases plus matched hard negatives across at least four domains.
- External reviewers, strong baselines and full ablations.
- Freeze candidate generation before revealing target outcomes.

Exit: discriminating-control and false-transfer gates pass; failure modes are
stable enough to preregister a prospective study.

### Stage 2 — Low-cost prospective predictions

Goal: demonstrate new target predictions on already scheduled or inexpensive
data collections.

- 20–30 target problems selected before outcomes are available.
- Prefer domains with authoritative future releases, ongoing simulations or
  low-risk bench/computational experiments.
- Independent escrow timestamps predictions and controls.

Exit: lift over strongest baseline with no critical trust failure. Positive
results remain a pilot and must include every null and missing outcome.

### Stage 3 — Prospective intervention portfolio

Goal: show that transfers alter experiment choice and survive interventions.

- 40+ hypotheses across at least five independent labs/teams and four domains.
- Randomize or matched-assign engine-assisted versus baseline workflow where
  ethically and operationally possible.
- Measure scientific yield, time, cost, expert burden and downstream decisions.

Exit: preregistered multi-domain superiority and at least one independently
replicated engine-originated prediction.

### Stage 4 — Independent replication and challenge benchmark

Goal: determine whether the engine is a field-level method rather than a
founder/repository-specific workflow.

- External consortium owns the sealed STC set and evaluation.
- At least two teams reproduce the engine without private context.
- At least three engine-originated predictions receive independent replication,
  including one failed replication if that is the outcome.

Exit: only now is “a general AI-for-Science discovery engine” a discussable,
bounded claim.

### Stage 5 — Scientific infrastructure

Goal: establish durable public value.

- Community benchmark governance, versioned evidence graph and reproducibility
  service.
- Domain-specific safety boards and data/access rules.
- Public failure registry and post-publication corrections.
- Open interfaces for competing retrieval, critic and experiment modules.

The engine should become infrastructure only if independent groups continue to
produce validated outcomes, not because the taxonomy or website becomes large.

## 10. First research portfolio

The first portfolio should maximize discrimination and provenance, not glamour.

### Track A — Method core: reject-aware transfer versus analogy generation

- Build externally labelled mechanism/framework trap cases.
- Compare multiple model families, single critics, ensembles and deterministic
  guards.
- Primary result: serious false-transfer reduction at matched recall and cost.
- Why first: it tests the engine's most distinctive existing component.

### Track B — Scaling concordance versus true mechanism transfer

- Revalidate a narrow real-data SOC core with matched non-SOC heavy-tail
  controls, dependence-aware uncertainty and mechanism-discriminating tests.
- Do not use “same exponent” as the primary proof.
- Primary result: whether structural variables predict out-of-domain observables
  better than distributional resemblance.
- Why first: existing assets make this feasible and expose the central trap.

### Track C — Prospective computational science

- Choose targets where fresh simulation or scheduled public data can be
  collected after preregistration.
- Require the engine to select source system, prediction and hard negative
  before execution.
- Primary result: VNPY and SFTR versus equal-budget baselines.
- Why first: lower ethical/logistical burden and clean chronology.

### Track D — Outcome-conditioned learning

- Test whether storing rejected and failed transfers improves later calibration
  and candidate ranking.
- Compare static KB, positive-only learning and symmetric-outcome learning.
- Primary result: prospective reduction in SFTR without loss of VNPY.
- Why first: this is the difference between a search product and a learning
  scientific engine.

WTO should remain a self-correction/coding case, not a flagship causal discovery
track. Phase should remain a transparent null-result research asset, not a
market-prediction track. Paper drafting is downstream scientific infrastructure,
not proof that the engine discovers anything.

## 11. Industry-change potential

Potential should be graded by evidence and counterfactual impact, not narrative
importance.

### Level 0 — Research interface

Evidence: reliable provenance-aware search and hypothesis workspace.
Impact: better organization; useful, but not a new scientific paradigm.
Current status: substantial engineering exists, scientific utility unproven.

### Level 1 — Reject-aware hypothesis audit standard

Evidence: externally validated reduction in serious cross-domain false
transfers, with reusable preregistration and claim-evidence tooling.
Impact: could become a standard safety/quality layer for AI-generated science.
Current status: the most plausible near-term defensible contribution; external
gold labels and clean reproduction are missing.

### Level 2 — Scientific transfer accelerator

Evidence: prospective multi-domain lift in validated hypotheses per time/cost,
with safe abstention and independent replication.
Impact: changes how labs search model space and choose experiments.
Current status: no prospective evidence.

### Level 3 — Outcome-learning discovery network

Evidence: multiple independent labs contribute symmetric outcomes; the graph's
future hypothesis yield improves measurably from failures and replications.
Impact: creates a shared memory of mechanism transfer that conventional papers
and search engines do not provide.
Current status: architecture concept only.

### Level 4 — General structural science engine

Evidence: sustained independent superiority across mature benchmark versions,
scientific areas and intervention types; several important replicated findings
originated from the engine.
Impact: a new layer of scientific infrastructure and potentially a new method
of theory formation.
Current status: aspirational and prohibited as a present claim.

The most credible path to world-level value is Level 1 → Level 2 → Level 3.
Skipping directly to Level 4 would turn the strongest methodological idea into
an unfalsifiable brand claim.

## 12. Governance and scientific integrity

- Separate builder, validator, domain reviewer and outcome adjudicator roles.
- Freeze prompts, models, retrieval corpus and analysis before sealed tests.
- Record all eligible candidates, exclusions, costs and missing outcomes.
- Give external evaluators control of benchmark secrets and final adjudication.
- Preserve public corrections and supersession rather than rewriting history.
- Require domain approval for hazardous laboratory, medical, legal, financial
  or dual-use experiments.
- Never infer authorship, ethics approval, novelty, causality or replication
  from model output.
- Avoid optimizing public metrics against one sealed benchmark; rotate future
  sets under independent governance.

## 13. Twelve-month scientific decision plan

### Months 0–2: instrument integrity

- Finish provenance, leakage, chronology and clean-room audits.
- Specify STH schema and outcome graph as versioned standards.
- Build 30–40 masked/hard-negative benchmark cases and external review rubric.
- Freeze prohibited claims and a public failure registry.

Decision: stop broad discovery claims if the engine cannot distinguish
mechanism from matched shape/framework traps.

### Months 3–5: blinded retrospective challenge

- Run baselines and module ablations under equal budgets.
- Publish all cases, including failures, after adjudication.
- Select prospective domains from error analysis, not convenience or expected
  positive results.

Decision: proceed only if false-transfer and discriminating-control gates pass.

### Months 6–9: prospective computational portfolio

- Lock 20–30 future-outcome hypotheses with independent timestamping.
- Execute low-risk computational/scheduled-data experiments.
- Measure yield, cost, time, correction burden and calibration.

Decision: narrow or retire the discovery-engine claim if there is no lift over
the strongest equal-budget baseline.

### Months 10–12: external lab pilot

- Hand the protocol to independent teams with no private repository context.
- Run a small intervention portfolio and clean-room replication.
- Submit a methods paper only around evidence that survived these gates.

Decision: call it a scientific transfer accelerator only after prospective and
independent evidence; otherwise publish the reject-aware audit method and its
negative result honestly.

## 14. Final scientific position

The repository's most important opportunity is not to claim that many systems
are isomorphic. It is to make **cross-domain transfer itself experimentally
accountable**. Today, Structural Isomorphism is an unusually rich prototype of
that method, not yet proof of a new AI-for-Science engine.

The field-level proposition is powerful and falsifiable:

> scientific AI should not be judged by how many hypotheses it writes, but by
> how efficiently it produces preregistered, discriminating predictions that
> survive new observations—and how reliably it learns from the ones that fail.

If prospective benchmarks and independent labs support that proposition, this
could move AI-for-Science from answer generation toward a shared, outcome-
learning engine for theory transfer. If they do not, the same protocol must be
strong enough to say so and reduce the claim.
