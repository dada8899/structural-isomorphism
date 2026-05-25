# v0.5 Methodology Pre-Registrations — Index

> Date: **2026-05-25** (SESSION-25)
> Repo state at pre-registration: HEAD `71a5617`
> Companion: `paper/v0.5-draft/v05-draft-skeleton.md` §§3.6.5–3.6.7
> Anti-p-hacking framework: `paper/anti-phacking-unified-2026-05-15.md` (especially §1.2 on adversarial pre-registration)
> Prior pre-registration template: `paper/pre-registered-replication-2026-05-15.md`

## Purpose

This directory contains three formal pre-registration documents for the v0.5
methodology increments §3.6.5 / §3.6.6 / §3.6.7. Each pre-registers a **methodology
pattern** (or, in the §3.6.7 case, an **engineering pattern**) rather than an
empirical band on a single class.

The pre-registrations are written under the discipline of the project's anti-p-hacking
companion paper, which formalises **adversarial pre-registration**: every
pre-registered prediction is reported regardless of outcome, the public ledger of
verdicts is itself a primary scientific output, and the unit of credibility is the
joint distribution of outcomes across the pipeline rather than any single confirming
paper. See `paper/anti-phacking-unified-2026-05-15.md` §1.2 for the framing.

Pre-registering *patterns* (rather than per-class bands) is the second-order analogue
of the per-class pre-registration discipline established in
`paper/pre-registered-replication-2026-05-15.md` (P1 = BCH, P2 = Reddit cascades).
Just as the per-class pre-registrations commit to predicted bands and verdict rules
*before* data are touched, the per-pattern pre-registrations commit to scope
conditions, applicability claims, and falsifiers *before* a future class is found
where the pattern would be applied. This is what enables a future negative result
(pattern fails on a class where its scope conditions hold) to count as a falsification
rather than a re-scoping after the fact.

## The three pre-registrations

### §3.6.5 — (s\*, k) Threshold-Tobit Reparametrisation

**File:** [`preregistration-3.6.5-sk-reparam-2026-05-25.md`](preregistration-3.6.5-sk-reparam-2026-05-25.md)

**Tier:** 1 (targeted remediation with explicit scope limits)

**Hypothesis.** For binary-outcome classes with a logit pre-registration that pins both
slope band and 2+ point-rate constraints, where the point-rate constraints
algebraically imply a slope outside the slope band, the (s\*, k) probit
reparametrisation produces a feasible pre-registration with decoupled, jointly
identifiable parameters.

**First instance.** `schelling_credible_commitment` v0.4 → v0.5 (PASS).

**Cross-class audit.** 3 candidates (`hysteresis_first_order_transition`,
`adverse_selection_unraveling`, `gardner_collins_toggle_switch`) verified N/A —
already-decoupled fitters. See
`docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`.

**Scope LIMIT.** ONLY logit binary-outcome over-specification. NOT Hill / linregress /
exp-decay / multi-axis gate / continuous-response classes.

**Falsifier.** A future class where scope conditions hold and (s\*, k) reparametrisation
still gives infeasible constraints under empirical anchors.

### §3.6.6 — Multilayer Test Pattern

**File:** [`preregistration-3.6.6-multilayer-2026-05-25.md`](preregistration-3.6.6-multilayer-2026-05-25.md)

**Tier:** 2 (general test pattern expected to transfer broadly)

**Hypothesis.** Candidate universality classes whose theory predicts different scaling
forms at different hierarchical scales require per-scale pre-registration. Each layer's
verdict is computed against its own functional form and its own band. The combined
verdict ladder distinguishes PASS-CONFIRMED-MULTILAYER, SPLIT, and REJECT-MULTILAYER.

**First instance.** `aggregation_kinetics` (PASS-STRONG-MULTILAYER, 3 biological
domains: Cruz 1997 human cortex + Hartig 2018 mouse cortex + Iwata 2000 / Brú 2003
oncology; Layer 2 = 4/5 Allen Brain TBI Aβ series).

**v0.6+ candidates (4 pre-registered, not yet tested).** Allometric scaling (Kleiber),
network growth (preferential attachment), cascading failures (per-event + waiting
time), earthquake productivity.

**Scope LIMIT.** Does NOT cover single-scale descriptor classes; does NOT substitute
for the §3.5.3 cross-domain scatter threshold (Layer 0 screen); does NOT claim 2-layer
as a universal layer count or lognormal+PL as the only viable combo.

**Falsifier.** A future class where layered protocol returns PASS-CONFIRMED-MULTILAYER
on the initial 2 domains but cross-domain replication on ≥ 2 further domains fails,
indicating false universality from layer-specific over-fitting.

### §3.6.7 — Head-vs-Tail-Aware LLM Validator (Engineering)

**File:** [`preregistration-3.6.7-head-aware-validator-2026-05-25.md`](preregistration-3.6.7-head-aware-validator-2026-05-25.md)

**Tier:** 3 (**engineering pattern**, NOT scientific methodology — see
`methodology-increment-checklist.md` Note 1)

**Hypothesis.** For LLM rewrite tasks with a deterministic head boundary, applying the
forbidden-substring validator to the LLM-generated tail only (`new_only =
new_full[len(head):]`) yields a strictly lower false-reject rate than whole-output
validation, while preserving the safety property.

**First instance.** Wave 3 C boilerplate rewrite, 117/117 entries via OpenRouter Kimi
K2.5, ~$0.05, 18 s wall clock, 0 false-rejects on the head-side.

**Follow-up.** Head-internal collision deterministic strip on 23 public-health entries
sharing a 30-character connector phrase ("该干预的成本效益(QALY/DALY)评估是政策决策核心"),
no LLM cost.

**Scope LIMIT.** ONLY rewrite tasks with deterministic head boundary; NOT full
generation; NOT adversarial LLM behaviour where the LLM can relocate forbidden content
between head and tail.

**Falsifier.** A rewrite task where the LLM moves forbidden content from head to tail,
making the head-aware validator blind to a safety case the whole-output validator
would have caught.

**Acknowledged limit.** Head-aware validation does NOT remove the need for downstream
embedding-cluster audits. Head-internal collisions still need a separate deterministic
strip pass.

## Tier classification (per `methodology-increment-checklist.md` Note 1)

| Tier | Pattern type | v0.5 instance |
|---|---|---|
| **1** | Targeted remediation with explicit scope limits | §3.6.5 (s\*, k) reparam |
| **2** | General test pattern expected to transfer broadly | §3.6.6 multilayer test |
| **3** | Engineering pattern documented for reproducibility | §3.6.7 head-aware validator |

Reviewers should weight each tier appropriately: tier 1 fixes a specific failure mode
on a class with documented over-specification; tier 2 is a methodological tool
expected to transfer across multiple classes; tier 3 is provenance for the v0.5 KB
cleanup and should **not** be weighted as a scientific contribution alongside tier 1
or tier 2.

## Why pre-register patterns (not just per-class bands)

Per-class pre-registration (the discipline established in
`paper/pre-registered-replication-2026-05-15.md` and applied to all v0.4 / v0.5
empirical class verdicts) commits the analyst to specific bands and verdict rules
before any data are touched.

**Pattern-level pre-registration** is a second-order discipline: it commits the
analyst, before a future class is identified, to:

1. **Scope conditions** under which the pattern *applies*. A class outside the scope
   is not a falsification — it is simply not a test of the pattern.
2. **Applicability claims** — what the pattern is expected to deliver when applied to
   a class within its scope.
3. **Falsifiers** — what evidence would refute the pattern. This is the key
   anti-overclaiming hedge: by writing down in advance the specific class-shape that
   would refute the pattern, the analyst forfeits the ability to retroactively
   re-scope after a negative result.
4. **Explicit NOT-claims** — what the pattern is *not* being claimed to cover. This
   is the second anti-overclaiming hedge: by enumerating the cases that lie outside
   the pattern's scope, the analyst forfeits the ability to retroactively expand the
   scope after a positive result.

The expected effect is that future replicators applying any of the three patterns to a
new class will, regardless of outcome, be able to map the outcome cleanly onto the
verdict ladder of the appropriate pre-registration. A positive result is a
substantive PASS for the pattern; a negative result is a substantive falsification;
an out-of-scope result is neither.

## Honest reservations on the present three pre-registrations

1. **All three patterns have N = 1 first instance.** Schelling for §3.6.5,
   aggregation_kinetics for §3.6.6, Wave 3 C boilerplate rewrite for §3.6.7. The
   first-instance PASS verdicts are necessary but not sufficient evidence for
   pattern-level credibility; future cross-class application is the real test.
2. **The §3.6.5 cross-class audit is N = 3 negatives (N/A).** This is *consistent*
   with the targeted-remediation scope claim (most binary-outcome classes don't have
   the over-spec failure), but it does not provide an *independent positive*
   instance of (s\*, k) helping on a class beyond schelling.
3. **The §3.6.6 candidate list (4 classes) is prospective, not retrospective.** No
   v0.5 empirical work has been done on allometric / network growth / cascading
   failures / earthquake productivity. The pattern's expected broad transferability
   is a *prediction*, not a demonstrated property.
4. **The §3.6.7 first-instance success rate (0/117 false-rejects) is on a single
   rewrite task.** Reuse on other rewrite tasks is expected but has not yet been
   demonstrated.

These reservations are pre-registered alongside the patterns themselves to anchor the
honest reading of the v0.5 paper's §3.6 contributions.

## File manifest

```
preregistrations/
├── README.md  (this file)
├── preregistration-3.6.5-sk-reparam-2026-05-25.md
├── preregistration-3.6.6-multilayer-2026-05-25.md
└── preregistration-3.6.7-head-aware-validator-2026-05-25.md
```

End of pre-registration index.
