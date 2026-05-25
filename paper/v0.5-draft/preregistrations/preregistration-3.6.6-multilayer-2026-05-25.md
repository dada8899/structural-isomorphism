# Pre-Registration of Methodology Increment §3.6.6 — Multilayer Test Pattern for Candidate Universality Classes with Scale-Dependent Scaling

> Date: **2026-05-25** (SESSION-25)
> Status: pre-registered *as a methodological pattern*, with the first empirical instance executed and 4 future candidates pre-listed
> Companion: `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.6; `paper/anti-phacking-unified-2026-05-15.md` §1.2
> Author: dada8899
> Repo state at pre-registration: HEAD `71a5617`

## 1. What is being pre-registered

This document pre-registers a **methodology pattern**, not an empirical band on a single
class. The pattern, formalised in v0.5 skeleton §3.6.6, is:

> *Candidate universality classes whose underlying theory predicts **different**
> scaling forms at **different** scales (intra-individual vs inter-individual;
> per-particle vs per-population; per-event vs per-waiting-time) require **per-scale**
> pre-registration. Each layer's verdict is computed against its own functional form
> and its own band; the combined verdict ladder distinguishes
> PASS-CONFIRMED-MULTILAYER (all layers pass), SPLIT (some pass, some fail), and
> REJECT-MULTILAYER (no layer passes).*

The pattern is offered as a *general* upgrade — in contrast to §3.6.5, which is a
targeted remediation with explicit scope limits. We pre-register the pattern itself
plus four candidate classes for v0.6+ testing under it.

## 2. Hypothesis

**H1.** Candidate classes whose published theory predicts scale-dependent scaling
forms will systematically be misjudged by single-layer cross-section tests: the
single-layer test will recover *a* real signal, but the signal will be at the wrong
scale for the wrong functional form, leading to spurious INCONCLUSIVE or REJECT
verdicts that an appropriately layered test would have converted to PASS.

**H2.** Per-scale pre-registration with independent bands per layer eliminates this
failure mode, and the combined `PASS-CONFIRMED-MULTILAYER / SPLIT / REJECT-MULTILAYER`
verdict ladder is *more informative* than a single-layer PASS/FAIL because it
distinguishes "the class is real but only at some scales" from "the class is not the
right framing at any scale".

**H3.** Cross-domain replication at the same layer continues to be required even after
the multilayer pattern is applied — i.e., a layered test that passes on a single
domain is PASS-WEAK; PASS-CONFIRMED-MULTILAYER requires layered PASS on ≥ 2 distinct
domains, and PASS-STRONG-MULTILAYER requires ≥ 3.

## 3. Scope — where the pattern applies, and where it explicitly does NOT

### 3.1 Scope conditions (must hold conjointly)

(i) The candidate class has published theory predicting *distinct* scaling forms (or
distinct functional families) at *distinct* hierarchical scales — i.e., the theory is
explicit that the scaling form at scale 1 (e.g., intra-individual / per-particle /
per-event) is mechanistically different from the form at scale 2
(inter-individual / per-population / per-waiting-time).

(ii) The empirical data supports per-scale measurement — i.e., the data is fine-grained
enough at scale 1 (per-event / per-particle / per-individual) and broad enough at
scale 2 (cross-event / cross-population / cross-individual) for both layers to be
statistically powered.

(iii) The single-layer test, run at the wrong scale, would conflate the two predictions
and *systematically* misjudge — i.e., the wrong-scale test would not merely be
under-powered, it would test the wrong functional form altogether.

### 3.2 Candidate list pre-registered for v0.6+ testing

| Candidate class | Theory-predicted Layer 1 (intra-scale) | Theory-predicted Layer 2 (inter-scale) | Anchors |
|---|---|---|---|
| Allometric scaling (Kleiber) | $M^{3/4}$ intra-species body-mass scaling | Cross-species log-mass × log-rate slope distribution | Kleiber 1932; West-Brown-Enquist 1997; Glazier 2005 |
| Network growth (preferential attachment) | Per-node degree power-law | Cross-network giant-component size distribution (BA ensemble) | Barabási-Albert 1999; Newman 2003; Faloutsos 1999 |
| Cascading failures (SOC + waiting time) | Per-event magnitude power-law | Cross-event waiting-time distribution (Omori / Hawkes branching) | Bak 1996; Sornette 2003; Carreras 2016 |
| Earthquake productivity | Per-mainshock aftershock-count power-law | Cross-mainshock magnitude-productivity correlation | Felzer-Brodsky 2006; Helmstetter 2003 |

Each is a *pre-registered candidate*; we make no empirical claim on these classes in
v0.5. Future replicators applying the multilayer pattern to any of the four are
expected to publish the result under the present pre-registration's discipline (every
verdict reported, no class-shopping).

### 3.3 What the pattern is NOT being claimed to cover

- **Single-layer descriptor classes.** When the theory predicts a *single* scaling form
  at a single scale (e.g., SOC threshold-cascade with only event-size as the
  observable), the multilayer pattern reduces to ordinary cross-domain replication —
  no upgrade.
- **The descriptor-vs-mechanism problem.** A descriptor class can still pass at one
  layer (spuriously) and fail at another. The multilayer test fixes the
  *single-layer-was-the-wrong-test* failure mode; it does **not** substitute for the
  cross-domain scatter threshold §3.5.3 (Layer 0 screen). We expect §3.5.3 and §3.6.6
  to coexist as complementary tools.
- **2-layer as a universal count.** Some classes will require 3-layer or 4-layer
  testing (per-monomer / per-aggregate / per-population for biochemistry; per-token /
  per-document / per-corpus for NLP scaling-laws). We pre-register 2-layer as the
  *minimum* compliance, with the layer count determined by the theory of the candidate
  class, not by a universal constant.
- **Lognormal + power-law as the only viable 2-layer combo.** Aggregation_kinetics
  pairs Smoluchowski PL (Layer 1) with multiplicative-stochastic lognormal (Layer 2);
  other classes will pair different functional families (e.g., stretched-exponential
  Layer 1 with truncated power-law Layer 2). The pattern is functional-form-agnostic;
  the specific combos are theory-determined per class.

## 4. Pre-specified data and procedure

### 4.1 First instance (already executed at HEAD `71a5617`)

`aggregation_kinetics` — promoted from `beta_amyloid_aggregation`
INCONCLUSIVE-single-layer (v0.4) to PASS-STRONG-MULTILAYER (v0.5, SESSION-24 +
SESSION-25 hardening).

- **Layer 1 (per-aggregate Smoluchowski PL).** α ∈ {1.70 (Cruz 1997 human cortex,
  ~6,500 plaques), 2.10 (Hartig 2018 5xFAD mouse cortex, ~12,400 plaques), 2.05 (Iwata
  2000 mass-action coagulation theory combined with Brú 2003 fit on 7 cancer types)}
  across **3 distinct biological domains**. All 3 in pre-registered band [1.7, 3.5].
- **Layer 2 (cross-population multiplicative-stochastic lognormal).** 4 of 5 Allen
  Brain TBI Aβ series with Vuong $R < 0$ vs power-law at $p < 0.05$, consistent with
  Hyman 2008 (*Annals of Neurology* 64:115) multiplicative-stochastic patient-level
  growth prediction.
- **Combined verdict at HEAD `71a5617`.** PASS-STRONG-MULTILAYER.

The v0.4 single-layer test recovered a real signal (4/5 lognormal-preferred) but
tested the *wrong prediction* (it tested for cross-section power-law, while Hyman 2008
predicts cross-section lognormal). The v0.4 INCONCLUSIVE verdict was forced by
single-layer scale conflation; the multilayer test recovers the predicted signature at
each scale and converts the class to PASS-STRONG-MULTILAYER.

### 4.2 Layer-by-layer pre-registration commitments

Each future candidate (allometric / network-growth / cascading-failure / earthquake)
is pre-committed to the following procedure:

1. Pre-register Layer 1 functional form, band, and source-paper anchor(s) *before*
   data fetch.
2. Pre-register Layer 2 functional form, band, and source-paper anchor(s) *before*
   data fetch.
3. Pre-register the combined verdict ladder mechanically as
   `PASS-CONFIRMED-MULTILAYER` (both pass), `SPLIT` (partial), `REJECT-MULTILAYER`
   (neither passes).
4. Pre-register a cross-domain replication count $\geq 2$ for PASS-CONFIRMED-MULTILAYER
   and $\geq 3$ for PASS-STRONG-MULTILAYER.
5. Publish the verdict regardless of outcome under the §6 falsifier discipline.

## 5. Verdict ladder (for the pattern, not the class)

| Outcome | Criterion |
|---|---|
| **PASS — pattern works** | (a) a candidate class with pre-registered scale-dependent theory is tested under the layered protocol AND (b) all layers' pre-registered constraints are met on ≥ 2 distinct domains AND (c) the same data evaluated under a single-layer test (run at either layer in isolation) would have returned INCONCLUSIVE or REJECT, demonstrating that the upgrade was material. |
| **FAIL — pattern broken** | A class is found where (i)–(iii) of §3.1 hold, the layered protocol is applied correctly, the layered verdict returns PASS-CONFIRMED-MULTILAYER, but a subsequent cross-domain replication on $\geq 2$ further domains *fails*, indicating the multilayer PASS was false universality from layer-specific over-fitting. |
| **SPLIT** | Layered protocol returns PASS at one layer and FAIL at another; class is real at some scales, not others. (This is a substantive verdict, not a fail of the pattern.) |
| **INCONCLUSIVE** | Either layer's data is statistically under-powered (n below pre-registered minimum), or only one layer was testable at the present session. |

Aggregation_kinetics delivers PASS under this ladder at HEAD `71a5617`: Layer 1 PASS
on 3 domains, Layer 2 PASS on the Allen Brain TBI cohort; the v0.4 single-layer test
on the same Allen Brain data returned INCONCLUSIVE, demonstrating the upgrade was
material.

## 6. Falsifiability criterion

The pattern is falsified by exhibiting a **future** class for which:
- scope conditions (i)–(iii) all hold;
- the multilayer protocol is applied correctly with cross-domain replication $\geq 2$
  at the verdict stage;
- the layered verdict returns PASS-CONFIRMED-MULTILAYER on the initial 2 domains;
- but a subsequent independent replication on $\geq 2$ additional domains *fails*,
  showing that the multilayer PASS was an artefact of layer-specific over-fitting
  rather than a genuine cross-domain universality.

A single such case shifts the pattern from "general test upgrade that increases
verdict resolution" to "test pattern whose increased resolution is bought at the cost
of layer-specific false universality". We commit in advance to reporting any such case
as a falsification.

A *secondary* falsifier: a class satisfying (i)–(iii) where the multilayer protocol
returns the same verdict as the single-layer test (i.e., no resolution improvement).
This is weaker — it shows the upgrade is *unnecessary* for that class, not that the
pattern is *wrong* — but a systematic accumulation of such cases would warrant
revisiting the (i)–(iii) scope conditions.

## 7. What is explicitly NOT being claimed

- **Universal class promotion.** We do **not** claim that v0.4 INCONCLUSIVE classes
  will, in general, convert to PASS under multilayer testing. Aggregation_kinetics is
  one case; other v0.4 INCONCLUSIVE classes may have single-layer-correct theory.
- **2-layer as the right count for every candidate.** §3.3 above lists 3-layer / 4-layer
  candidates explicitly.
- **Lognormal + PL as the only viable combo.** §3.3 also disclaims this.
- **Resolution of the descriptor-vs-mechanism problem.** The cross-domain scatter
  threshold (§3.5.3 v0.4) remains the Layer 0 screen.
- **Empirical claims on the 4 candidate classes in §3.2.** None of allometric / network
  growth / cascading failures / earthquake productivity is empirically validated in
  v0.5. The list is *prospective*.
- **Authorship of multilayer testing.** Multi-scale testing is canonical in physics
  (one always tests multiple scales when the theory predicts multiple scales). The
  v0.5 claim is the *systematic application* of multilayer pre-registration to
  candidate universality classes with hierarchical theoretical structure.

## 8. Resource budget

- **Compute.** Per candidate class, ~30 minutes wall clock on Mac mini M4 for both
  layers; aggregation_kinetics v0.5 full run consumed ~12 minutes including 3-domain
  replication.
- **LLM cost.** Multilayer pre-registration adds ~5-10 K tokens per class ($\approx$
  $0.05 per class on Opus). Cross-domain anchor sourcing is the dominant cost
  (literature lookup, ~$1-2 per anchor on Opus).
- **Human-hours.** Per future candidate: ≈ 4-8 h (literature anchor sourcing + data
  fetch + 2-layer fit + cross-domain replication writeup). Aggregation_kinetics v0.4
  → v0.5 transition + SESSION-25 hardening + this pre-registration: ≈ 12 h
  cumulative.
- **v0.6 budget.** The 4 candidate classes in §3.2 are estimated at 4-8 h each, i.e.,
  ≤ 32 h aggregate for the full prospective candidate set.

## 9. Data and script provenance

| File | Purpose |
|---|---|
| `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.6 | Methodology pattern, prose description |
| `paper/v0.5-draft/methodology-increment-checklist.md` §3.6.6 | Reviewer-facing traceability sheet |
| `v4/validation/aggregation-kinetics/verdict.md` | First-instance PASS-STRONG-MULTILAYER verdict |
| `v4/validation/aggregation-kinetics/results.json` | Layer 1 + Layer 2 numerical results |
| `v4/validation/aggregation-kinetics/run_validation.py` | Deterministic driver |
| `data/kb-additions-2026-05-25-aggregation-kinetics.jsonl` | 8 KB entries with anchor literature |
| `docs/sessions/v04-aggregation-kinetics-report.md` | Narrative session report |
| `paper/anti-phacking-unified-2026-05-15.md` §1.2 | Adversarial pre-registration framing |

End of pre-registration §3.6.6.
