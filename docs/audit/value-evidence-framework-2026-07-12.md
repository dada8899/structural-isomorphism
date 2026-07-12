# Structural Isomorphism value-evidence framework

Date: 2026-07-12  
Status: product-research decision framework; not evidence that product-market fit exists  
Authority for runtime status: `NEXT_SESSION.md`

## 1. Decision

The product should remain a **Validated Transfer Workbench** for research-heavy
product and growth leads. Its defensible job is not “find a surprising analogy”
but:

> turn a stuck decision into a structurally distinct, evidence-bounded and
> testable intervention, then learn from the observed outcome.

The product becomes valuable only when the transfer changes a decision or an
experiment. Retrieval relevance, long reports, attractive explanations and
scientific-looking equations are intermediate signals, not user value.

Phase Detector and the paper are credibility assets, not the main product:

- Phase is a transparent demo/null-result case, not an investment signal.
- The paper should lead with reject-aware methodology and negative results,
  not broad universality.
- WTO is a worked example of self-correction; it cannot currently support a
  causal or precise effect-size claim.

## 2. Value >= 90 evidence score

Score each proposed feature, workflow or market claim on the evidence actually
available, not forecast confidence. The maximum is 100.

| Dimension | Weight | Full-credit evidence |
|---|---:|---|
| Problem reality | 15 | Repeated, recent, costly problem in at least 15 target-user cases; current workaround and decision cost recorded |
| Distinctive transfer | 15 | Blind comparison beats a strong same-domain/general-LLM baseline on usefulness, novelty and non-obviousness |
| Decision quality | 20 | User can identify what decision changed; expert review finds mechanism, boundary and counter-evidence valid |
| Verifiable outcome | 20 | Pre-specified experiment has owner, baseline, metric, threshold and stop rule; outcome is later recorded |
| Trust and scientific honesty | 15 | Provenance, real/synthetic boundary, uncertainty, rejection conditions and version fingerprints are visible and correct |
| Operational experience | 10 | Core journey completes reliably, first value is timely, errors recover, and accessibility/mobile contracts pass |
| Retention and willingness to pay | 5 | Users return for unresolved outcomes and at least some pay or make a credible budget commitment |

### Evidence anchors used inside each dimension

- `0%`: assertion or internal opinion.
- `25%`: synthetic fixture, developer dogfood or historical anecdote.
- `50%`: repeatable offline benchmark or internal expert review.
- `75%`: target-user behavior in a prospective pilot.
- `100%`: independently reproducible result across users/teams and time.

The dimension score is `weight × evidence level`. Interpolation is allowed only
when multiple evidence types fall on different anchors; document why. Round
only the final total. Record source, sample, date, exclusions and failures for
every non-zero score.

### Hard gates

A score cannot be reported as >=90 if any of these is false, regardless of sum:

1. No fabricated human labels, outcomes, external review or real-data claim.
2. Candidate retrieval and generated explanation are visibly separated from
   verified evidence.
3. User explicitly chooses the transfer; Top 1 is never treated as accepted.
4. The experiment and success rule are fixed before its outcome is known.
5. Failed, partial and null outcomes remain in the denominator.
6. English quality is measured on independently human-reviewed candidates.
7. Scientific headline claims pass the claim-evidence gate and unresolved
   conflicts block submission.
8. The main task works end to end in production, not only in fixtures.

`>=90` means “strong enough to scale cautiously,” not “finished forever.” A
feature below 70 should not receive expansion work; 70–89 stays in pilot; below
50 should be retired or reframed unless it is required infrastructure.

## 3. Current evidence assessment

These are conservative audit scores, not measurements from new user research.

`P/D/Q/O/T/X/R` below mean problem, distinctive transfer, decision quality,
verifiable outcome, trust, operational experience, and retention/payment.

| Asset | P | D | Q | O | T | X | R | Total | Main missing evidence |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Validated Transfer Workbench | 9 | 10 | 10 | 5 | 10 | 10 | 4 | 58 | No prospective 15–20-user outcome cohort or demonstrated willingness to pay |
| English retrieval improvement | 8 | 7 | 7 | 4 | 8 | 10 | 2 | 46 | 594 expanded candidates remain unlabelled; recall/holdout claim unavailable |
| Report → experiment → outcome loop | 10 | 8 | 8 | 8 | 8 | 10 | 2 | 54 | Real start, result-return and decision-change rates unmeasured |
| Reject-aware research method | 10 | 12 | 15 | 12 | 14 | 7 | 2 | 72 | External statistical/domain review and clean-room reproduction absent |
| WTO evidence | 4 | 4 | 8 | 5 | 9 | 7 | 1 | 38 | Manual coding, selection, separation and causal identification unresolved |
| Phase as research preview | 6 | 8 | 10 | 5 | 12 | 10 | 4 | 55 | No repeatable research-decision or paid-tier evidence |
| Phase as investment product | 3 | 2 | 1 | 1 | 2 | 3 | 0 | 12 | Walk-forward evidence is null and cannot support alpha positioning |

No current asset qualifies for a >=90 claim. Engineering completion must not be
converted into product-value or scientific-validation credit.

## 4. Highest-value product hypotheses

### H1 — Decision brief before deep report

For research-heavy PM/growth leads, three selected candidate briefs containing
mechanism match, mismatch, evidence status and one experiment will produce more
accepted and executed transfers than a long generated report.

- Primary: user-selected candidate leads to a pre-specified experiment.
- Guardrails: unsupported-evidence rate, time to first candidate, abandonment.
- Baselines: current workflow; strong general LLM with same problem context.
- Human requirement: blind usefulness review and real task execution.

### H2 — Outcome follow-up is the retention mechanism

Users return because an experiment remains unresolved, not because more analogy
content is available.

- Primary: 14-day result return per created experiment.
- Secondary: 7/30-day return, decision changed, next experiment created.
- Guardrail: notification unsubscribe/complaint and self-reported pressure.
- Do not count login, report reopening or email click alone as retained value.

### H3 — English parity expands the same job, not a separate product

Multilingual retrieval should be adopted only when independently reviewed
English relevance improves without Chinese, OOS, latency or same-domain
regression.

- Primary: human nDCG@5 and Success@5 on a frozen holdout.
- Required: three independent reviewers, adjudication, grouped split.
- Guardrails: Chinese delta, OOS precision/recall, p95 latency, cross-domain rate.
- The current fixed-pool result is model-selection evidence only.

### H4 — Trust detail helps only at the moment of doubt

Provenance and counter-evidence should be one click from every candidate, while
the default brief stays readable. More scientific prose is not automatically
more trust.

- Primary: calibrated acceptance—verified candidates accepted more often than
  unsupported candidates, without hiding null/reject evidence.
- Test: compact status label versus expanded evidence-first card.
- Expert requirement: audit whether labels match underlying evidence.

## 5. Metrics and experiment design

The north-star metric is **Weekly Verified Transfer Outcomes**, counted only
when all conditions hold:

1. A real user submitted a real decision problem.
2. The user explicitly selected a candidate.
3. An experiment was created before execution.
4. A terminal outcome (`worked`, `partial`, `no_effect`, `failed`) was recorded.
5. Evidence and artifact versions are recoverable.

Report the funnel with unique users and eligible tasks:

`eligible problem → fingerprint confirmed → candidate selected → experiment
created → experiment started → terminal outcome → decision changed`

Required metrics:

- Candidate acceptance, with same-domain/general-LLM baseline.
- Experiment creation and verified start rate.
- 14/30-day terminal outcome return rate.
- Worked/partial/no-effect/failed distribution; never success-only.
- Median time to first useful candidate and complete brief.
- Unsupported evidence, misleading mechanism and unsafe recommendation rates.
- English/Chinese quality parity and OOS regression.
- User-level 7/30-day return caused by an open or completed experiment.
- Stated budget, paid conversion and renewal only after outcome evidence.

Pilot design:

- Recruit 15–20 research-heavy PM/growth users with a current costly decision.
- Collect one pre-registered primary task per user before exposing output.
- Randomize order of Workbench and strong general-LLM briefs where feasible.
- Blind independent reviewers to source; preserve all failures.
- Freeze rubric and thresholds before scoring.
- Conduct day 0, 7, 14 and 30 follow-up; record missing outcomes explicitly.
- Analyze by user/task, not by generated section or candidate count.

Minimum scale decision gate:

- >=60% candidate acceptance against a strong baseline.
- >=35% experiment creation and >=20% verified start.
- >=15% terminal result return by day 14 and >=25% value-linked return by day 30.
- No critical provenance/safety defect.
- At least five users state a credible budget; at least three complete a paid or
  procurement-intent test without being promised future features.

These are pilot continuation thresholds, not proof of PMF.

## 6. Automation versus human research

### Can be completed automatically

- Produce frozen experiment manifests, cohort denominators and funnel reports.
- Validate experiment fields, state transitions and outcome completeness.
- Run retrieval/OOS/latency regressions and grouped data-split checks.
- Build blinded review bundles, validate fingerprints and calculate agreement.
- Detect missing evidence, claim drift, synthetic/real confusion and conflicts.
- Generate reminder schedules after the user has opted in.
- Produce anonymized failure taxonomies and candidate-level audit queues.
- Enforce that Phase remains demo/null-result and non-investment positioning.

Automation may prepare evidence; it cannot manufacture user behavior, human
judgment, consent, domain expertise, willingness to pay or external replication.

### Must be completed by humans

- ICP problem interviews and observation of current workarounds.
- Independent relevance/usefulness review of the 594 English candidates.
- Real experiment execution and truthful outcome reporting.
- Blind comparison against a general-LLM baseline.
- Domain-expert review of mechanism transfer and harmful boundary failures.
- WTO independent double coding and third-party adjudication.
- External statistics/complex-systems review and clean-room paper reproduction.
- Pricing interviews, paid pilot and procurement decision.

## 7. Retention and commercial boundaries

Do not commercialize access to “more analogies.” Charge only after evidence that
the workflow improves repeated decisions. The first paid object should be a
small team pilot around active experiments, provenance and outcome history—not
Connections, trading signals, unlimited reports or a broad API tier.

Commercialization remains closed until:

- the Workbench reaches >=90 under this framework;
- at least 50 terminal outcomes exist, including failures;
- five teams use it for four consecutive weeks;
- no unresolved critical scientific/product-trust conflict is user-facing;
- support cost and model cost are measured per verified outcome;
- at least three teams pay or complete credible procurement intent.

Phase may support trust through transparent negative results, but must not be
bundled as alpha. Academic publication is not evidence of willingness to pay;
payment is not evidence that a scientific claim is true.

## 8. P0 / P1 / P2

### P0 — Make value claims truthful and measurable

1. Adopt this scorecard as the decision gate for roadmap items.
2. Finish three-human review/adjudication of the 594 English pool; do not ship a
   new embedding based only on the fixed judged pool.
3. Instrument the complete verified-outcome funnel with explicit denominators.
4. Add a strong general-LLM baseline brief to the pilot protocol.
5. Keep WTO/Schelling excluded from universality PASS counts and Phase excluded
   from investment/alpha positioning.

Exit: no roadmap item claims >=90 without a source-backed score and all hard
gates; pilot protocol and analysis plan are frozen before recruitment.

### P1 — Run the prospective value pilot

1. Recruit 15–20 target users with current decisions.
2. Run blinded brief comparison and day 0/7/14/30 outcome collection.
3. Improve only the largest measured funnel loss: candidate trust, experiment
   actionability, follow-up return or English relevance.
4. Complete WTO double coding and external research reviews in parallel; these
   improve trust but are not substitutes for product evidence.

Exit: Workbench >=70 and continuation thresholds met. If not, narrow ICP or
retire the weak workflow rather than adding features.

### P2 — Earn scale and commercial tests

1. Accumulate 50+ terminal outcomes across at least five teams.
2. Test a paid team pilot focused on experiment history, evidence provenance and
   decision learning.
3. Add integrations/API only when they reduce measured workflow friction.
4. Submit the reject-aware methods paper only after external review and
   clean-room reproduction; keep empirical claims bounded.

Exit: Workbench >=90, paid evidence exists, and trust gates remain green. Only
then consider workspace expansion, API monetization or broader ICPs.
