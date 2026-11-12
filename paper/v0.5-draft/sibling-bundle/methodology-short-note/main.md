---
title: "Three methodology patterns surfaced by cross-domain universality validation: a methods note"
author: "Wan Qinghui (万庆徽), Structural Isomorphism Project (independent researcher)"
date: "2026-05-25 (v0.1 short-note, sibling submission to the C1 v0.4 empirical preprint and C4 v0.4 methodology preprint)"
abstract: |
  Cross-domain universality-class validation surfaces methodology problems that single-domain practice rarely encounters: pre-registrations that are mathematically infeasible before any data is collected, theories whose predictions live at different scales than a single-layer cross-section test can probe, and LLM rewrite pipelines whose naïve safety checks false-reject legitimate input. We document three patterns surfaced during the v0.5 universality program of the Structural Isomorphism Project and pre-registered as standalone methodological commitments. Pattern 1 — (s*, k) threshold-tobit reparametrisation — is a *targeted remediation* for the specific over-specification failure mode of binary-outcome logit pre-registrations whose slope and point-rate constraints are mutually inconsistent; the first instance (schelling_credible_commitment) converted v0.4 INCONCLUSIVE to v0.5 PASS, and a three-class non-applicability audit documents the explicit scope limit. Pattern 2 — multilayer testing for hierarchically-scaling classes — is a *general test pattern* requiring per-scale pre-registration and a refined verdict ladder; the first instance (aggregation_kinetics, Smoluchowski power-law per-aggregate + multiplicative-stochastic lognormal per-population) converted v0.4 INCONCLUSIVE to v0.5 PASS-STRONG-MULTILAYER, and four candidate classes are pre-listed for v0.6+ testing. Pattern 3 — head-vs-tail-aware LLM validator — is an *engineering* pattern, explicitly stratified as tier-3 reproducibility provenance and not as scientific methodology; the first instance was the Wave 3 C knowledge-base boilerplate rewrite (117 entries, $0.05, 18 s wall, 0 false-rejects). All three patterns are pre-registered with explicit falsifiability criteria, scope conditions, and non-applicability lists. We argue that surfacing these patterns is *only possible* in a cross-domain program — the failure modes are amplified by the variety of fits, theories, and data conditioning required to validate universality across heterogeneous domains.
keywords: pre-registration; threshold-tobit; multilayer testing; LLM rewrite validation; cross-domain methodology; universality class
---

## 1. Motivation

The Structural Isomorphism Project [1, 2] is a cross-domain validation program: a single fixed pipeline (Clauset-Shalizi-Newman 2009 MLE power-law with KS-driven `x_min`, Vuong likelihood-ratio against alternative distributions, cross-domain replication threshold ≥ 3) [3, 4] applied to candidate universality classes that range from neural avalanches [5] and forest fires [6] to financial-market crashes [7], aggregation kinetics in biochemistry [8], and credible-commitment games in international trade [9]. The unifying empirical claim — "*a universality class has empirical content only if a single fixed pipeline recovers the predicted scaling across systems from different domains*" — is documented in the v0.4 companion preprint [1].

In the course of executing that program, three methodological problems surfaced that *would not have surfaced* in a single-domain replication. Each is a specific failure mode of either pre-registration discipline (Patterns 1 and 2) or the LLM tooling on which a high-throughput taxonomy program now depends (Pattern 3). The point of this note is not that any one pattern is novel in isolation — (s*, k) parametrisations are canonical in econometrics since the 1950s [10], multi-scale physics testing is canonical since the early statistical-mechanics literature, and "slice the LLM output before validating" is canonical software engineering. Rather, the contribution is that **a cross-domain validation program forces a researcher to confront and remediate these problems systematically**, where single-domain practice can paper over them by tacit familiarity with the local fit conventions.

We document each pattern as a *pre-registered methodological commitment* — with explicit scope conditions, falsifiability criteria, and non-applicability audits — rather than as a discovery. The pre-registration files are companion artefacts at `paper/v0.5-draft/preregistrations/` and are referenced individually below. The same three patterns are incorporated into v0.5 of the main universality preprint as §§3.6.5, 3.6.6, and 3.6.7, but we separate them here because the methodology contributions are reusable beyond our specific universality-class taxonomy and warrant standalone visibility. The note is short by design (≈4500 words including this introduction); the substantive empirical claims and the full v0.4 + v0.5 taxonomy are in [1] and [2].

The note is organised one pattern per section. §2 covers Pattern 1 ((s*, k) reparametrisation) with the schelling_credible_commitment first instance and the three-class non-applicability audit. §3 covers Pattern 2 (multilayer testing) with the aggregation_kinetics first instance and four pre-registered v0.6+ candidate classes. §4 covers Pattern 3 (head-aware validator) and explicitly stratifies it as an engineering pattern not a scientific contribution. §5 makes cross-pattern remarks and explicit anti-overclaim hedges. §6 lists the three pre-registration documents and the universality preprint cross-references. §7 is the compressed bibliography.

## 2. Pattern 1 — (s*, k) threshold-tobit reparametrisation as targeted remediation

### 2.1 The failure mode

In a binary-outcome universality class — one whose canonical observable is a yes/no event (does the system follow through on its commitment? does the toggle switch flip? does the trade dispute escalate?) — a common pre-registration practice is to fit a logit S-curve $p(s) = 1/(1 + \exp(-(a + bs)))$ and pre-register both **(i) a band on the slope $b$** (typical of a mechanism-defined class: "the response should scale with rationality stake at slope $b \in [b_{\text{lo}}, b_{\text{hi}}]$") **and (ii) two-or-more point follow-through rates** ("at low $s$, fewer than 35% follow through; at high $s$, more than 75% follow through"). This is a *natural* pre-registration: a slope band fixes the mechanism, and point rates anchor the curve to the empirical anchors a domain expert would intuitively endorse.

The problem is that **the two constraints are not independent**. For a logit with intercept $a$ and slope $b$ at predictor values $s_{\text{lo}}$ and $s_{\text{hi}}$:
$$
\log\frac{p(s_{\text{hi}})}{1 - p(s_{\text{hi}})} - \log\frac{p(s_{\text{lo}})}{1 - p(s_{\text{lo}})} = b\,(s_{\text{hi}} - s_{\text{lo}}).
$$
Once the two point rates are pinned, the *implied* slope is fully determined by the logit. If the pre-registered slope band does not contain that implied slope, **the joint feasible region is empty before any data is collected**. This is not a hypothetical failure mode: the v0.4 logit pre-registration for the `schelling_credible_commitment` universality class pinned $b \in [1.2, 2.6]$ together with $p(s > 0.4) > 0.75$ and $p(s < 0.2) < 0.35$, which jointly imply $b > 8.59$ — an empty feasible region. The v0.4 verdict on the class was forced to INCONCLUSIVE on this pre-registration internal inconsistency, *not* on any empirical failure of the credible-commitment mechanism (which separately passes the sham null at $|b_{\text{sham}}| \approx 0$).

### 2.2 The remediation

The fix is to **switch from logit to a probit / threshold-tobit form** [10, 11] and reparametrise to **$(s^*, k)$**, where $s^*$ is the curve midpoint (the predictor value at which $p = 0.5$) and $k$ is a standardised slope (steepness). The probit form $p(s) = \Phi((s - s^*)\,k)$ separates the two free parameters cleanly — the midpoint and the steepness are independent geometric features of the curve, and an analyst can pre-register *independent* bands on each:
$$
s^* \in [s^*_{\text{lo}}, s^*_{\text{hi}}], \qquad k \in [k_{\text{lo}}, k_{\text{hi}}].
$$
The point-rate constraints are *derived diagnostics* of the fitted $(s^*, k)$ box, not independent constraints: once $s^*$ and $k$ are inside their pre-registered bands, $p(s_{\text{lo}})$ and $p(s_{\text{hi}})$ are *computed* from the fit and reported as side information, but they are no longer free constraints that the pre-registration must satisfy.

For `schelling_credible_commitment`, the v0.5 probit pre-registration with $s^* \in [0.20, 0.35]$ (anchor-implied from Bown 2009 WTO retaliation cases at threshold dispute-size ≈ 0.25) and $k \in [4, 12]$ (anchor-implied from cross-class dispersion of credible-commitment steepness in the Schelling literature) returns sub-run C of the anchor-calibrated generator ($a = -3$, $b = 12$, noise $= 0.15$): $s^* = 0.251$, $k = 6.529$, with derived $p(0.4) = 0.834$ and $p(0.2) = 0.369$ both inside what the v0.4 logit pre-reg would have demanded if it had been feasible. The sham-null arm rejects $|k_{\text{sham}}| < 0.05$, three orders of magnitude under the in-band threshold. The class converts from v0.4 INCONCLUSIVE-pre-reg-overspec to v0.5 PASS [12].

### 2.3 Scope and non-applicability

Pattern 1 is *targeted*, not general. It applies *only* when the following three scope conditions hold conjointly:

(i) the class fits a binary outcome through a logit (or equivalent monotone S-curve) on a single continuous predictor;
(ii) the pre-registration pins the slope band AND two-or-more point rates on the same predictor;
(iii) the point-rate constraints algebraically imply a slope outside the pre-registered slope band — i.e., the original pre-registered region is empty.

The explicit non-applicability audit [13] verified three v0.4-era candidates where the pattern does *not* help:

| Class | Fit method | Why (s*, k) does not help |
|---|---|---|
| `hysteresis_first_order_transition` | `linregress` on log-survival + 6-signature gate | Each signature is its own identifiable quantity; multi-axis already decoupled |
| `adverse_selection_unraveling` | Exponential half-life $q(t) = q_\infty + (q_0 - q_\infty)e^{-t/\tau}$ | No S-curve, no point-rate conflict |
| `gardner_collins_toggle_switch` | Hill function $p = x^n / (K^n + x^n)$ + GMM bistability | Canonical Hill $(n, K)$ already plays the (s*, k) role |

We deliberately published the non-applicability audit *before* publishing the pattern itself, on the discipline that a remediation pattern advertised as a general upgrade is more dangerous than one with explicit scope limits. The pre-registration document (companion `paper/v0.5-draft/preregistrations/preregistration-3.6.5-sk-reparam-2026-05-25.md`) records a falsifier: a future class satisfying scope conditions (i)–(iii) for which the (s*, k) reparam *also* produces an empty feasible region under empirical anchors would shift the pattern from "targeted remediation that works in its declared scope" to "remediation that resolves logit-form over-specification but does not resolve the underlying tightness of the empirical anchor set". We commit in advance to reporting any such case as a falsification, not as a class-specific failure.

### 2.4 What the pattern is not

The pattern is *not* novel in form — Hill 1910 functions in biology and threshold-tobit models in econometrics from the 1950s–1980s [10, 11] long predate this work. What is contributed is the **diagnostic use** of the reparametrisation as a remediation pattern for the specific over-specification failure mode in §2.1, plus the pre-registered scope discipline and non-applicability audit. The cost-benefit of running the pattern systematically (one new universality class transformed from INCONCLUSIVE to substantive PASS for ≈ 4 hours of analyst time) is itself the methodological contribution.

## 3. Pattern 2 — multilayer testing for hierarchically-scaling classes

### 3.1 The failure mode

A second class of pre-registration error appears when the candidate universality class has **theoretically-predicted scale-dependent scaling**: the theory says that at *one* hierarchical scale (per-individual, per-particle, per-event) the observable scales one way, and at a *different* hierarchical scale (cross-individual, per-population, cross-event) it scales another way [14]. A single-layer cross-section test will recover *a* signal, but it is the signal at the wrong scale for the wrong functional form, and the verdict either misses real universality or spuriously rejects.

The textbook example is the `beta_amyloid_aggregation` / `aggregation_kinetics` class. Smoluchowski coagulation theory [15] predicts a per-aggregate size distribution scaling as a power law $P(s) \propto s^{-\alpha}$ with $\alpha \in [1.7, 3.5]$ across the kernel-family. Hyman 2008 [16] separately predicts that *cross-population* aggregate-size distributions (across Alzheimer's patients, for example) should be **multiplicative-stochastic lognormal** because patient-level growth rates compound multiplicatively over decades of disease progression. These are *different* scaling forms at *different* hierarchical scales; the per-aggregate Smoluchowski power-law and the per-population lognormal are *both* features of the class, not alternatives. A single-layer cross-section test on the Allen Brain TBI cohort (which is a *cross-patient* dataset) tested only for cross-section power-law and returned INCONCLUSIVE in v0.4 because the data preferred lognormal — *which was the predicted Layer-2 signature*. The v0.4 verdict was forced by single-layer scale conflation.

### 3.2 The remediation

The fix is to **pre-register per-scale**: pre-register a Layer 1 functional form, band, and anchor(s) *before* data fetch, and pre-register a Layer 2 functional form, band, and anchor(s) *before* data fetch. The combined verdict ladder is:

| Verdict | Criterion |
|---|---|
| `PASS-CONFIRMED-MULTILAYER` | All layers' pre-registered constraints met on ≥ 2 distinct domains |
| `PASS-STRONG-MULTILAYER` | All layers' constraints met on ≥ 3 distinct domains |
| `SPLIT` | One layer passes, another fails; class is real at some scales, not others |
| `REJECT-MULTILAYER` | No layer passes |
| `INCONCLUSIVE` | At least one layer's data is under-powered |

For `aggregation_kinetics`, the v0.5 multilayer pre-registration ([17]) returned:

- **Layer 1 (per-aggregate Smoluchowski PL).** $\alpha \in \{1.70$ (Cruz 1997 human cortex, ~6,500 plaques), $2.10$ (Hartig 2018 5xFAD mouse cortex, ~12,400 plaques), $2.05$ (Iwata 2000 mass-action theory + Brú 2003 fit on 7 cancer types)$\}$ across **3 distinct biological domains**; all 3 inside pre-registered band $[1.7, 3.5]$.
- **Layer 2 (cross-population multiplicative-stochastic lognormal).** 4 of 5 Allen Brain TBI Aβ series with Vuong $R < 0$ vs power-law at $p < 0.05$, consistent with Hyman 2008's multiplicative-stochastic patient-level growth prediction.
- **Combined verdict at HEAD `71a5617`:** `PASS-STRONG-MULTILAYER`.

The same data evaluated under the v0.4 single-layer protocol returned INCONCLUSIVE, demonstrating that the multilayer upgrade was *material* — not a cosmetic procedural change.

### 3.3 Scope and pre-registered candidates

Pattern 2 is offered as a *general* test pattern (in contrast to Pattern 1's targeted remediation), applicable whenever:

(i) the class has published theory predicting *distinct* scaling forms at *distinct* hierarchical scales;
(ii) the empirical data supports per-scale measurement (statistically powered at each layer);
(iii) the single-layer test, run at the wrong scale, would systematically misjudge (not merely under-power).

Four candidate classes are pre-listed for v0.6+ testing under the pattern:

| Candidate | Layer 1 (intra-scale) | Layer 2 (inter-scale) | Anchors |
|---|---|---|---|
| Allometric scaling (Kleiber) | $M^{3/4}$ intra-species | Cross-species log-mass × log-rate slope dist. | Kleiber 1932; West-Brown-Enquist 1997; Glazier 2005 |
| Network growth (preferential attachment) | Per-node degree power-law | Cross-network giant-component size dist. | Barabási-Albert 1999; Newman 2003 |
| Cascading failures (SOC + waiting time) | Per-event magnitude PL | Cross-event waiting-time dist. (Omori/Hawkes) | Bak 1996; Sornette 2003; Carreras 2016 |
| Earthquake productivity | Per-mainshock aftershock-count PL | Cross-mainshock magnitude-productivity correlation | Felzer-Brodsky 2006; Helmstetter 2003 |

Each is **pre-registered as a candidate** under the pattern's discipline — i.e., whatever verdict the multilayer protocol returns on these classes, it will be published, with no class-shopping. The pattern is falsified by exhibiting a class satisfying scope conditions (i)–(iii) where the multilayer protocol returns `PASS-CONFIRMED-MULTILAYER` on the initial 2 domains but a subsequent independent replication on ≥ 2 further domains fails, showing the multilayer PASS was an artefact of layer-specific over-fitting rather than genuine cross-domain universality. The pre-registration ([18]) commits to reporting any such case as a falsification.

### 3.4 What the pattern is not

The pattern is *not* claiming that multi-scale testing is original — multiple-scale tests are canonical in physics. The contribution is the **systematic application** of per-scale pre-registration to candidate universality classes with hierarchical theoretical structure, together with the refined verdict ladder, the cross-domain replication threshold per layer (≥ 2 for `PASS-CONFIRMED-MULTILAYER`, ≥ 3 for `PASS-STRONG-MULTILAYER`), and a public pre-registered candidate list for prospective testing. Nor is the pattern a universal upgrade: classes whose theory predicts a single scaling form at a single scale reduce to ordinary cross-domain replication and do not benefit from the upgrade.

## 4. Pattern 3 — head-vs-tail-aware LLM validator (engineering)

### 4.1 Stratification: this is engineering, not methodology

We document Pattern 3 explicitly as a **tier-3 engineering pattern**, distinct from Pattern 1 (tier-1 targeted remediation) and Pattern 2 (tier-2 general methodology). The pattern is recorded for reproducibility because (i) it changed the operating constraint on knowledge-base hygiene at scale and (ii) the cleanup directly affects the embedding-similarity and pair-mining steps of the project's Layer 1 community discovery. It is *not* a scientific universality claim; reviewers should weight it as engineering provenance only.

### 4.2 The failure mode

The cross-domain universality program ingests a multi-thousand-entry knowledge base of phenomenon descriptions (5341 entries post v0.5 merge in `data/kb-5000-merged.jsonl`). Several waves of the KB were generated by LLM expansion of seed entries, and one wave (Wave 3 C, 117 entries on public-health interventions) shared a 7-template boilerplate suffix that polluted embedding-based retrieval — the cosine-similarity matrix on Wave 3 C entries was systematically inflated by the shared suffix, spuriously clustering entries that had no semantic kinship beyond the boilerplate.

The remediation requires an LLM rewrite: replace the boilerplate tail of each entry with a domain-faithful continuation, then re-embed. A standard rewrite pipeline reads the head + tail, holds the head fixed, asks an LLM to rewrite the tail, and validates the *whole output* against a forbidden-substring list (the boilerplate suffix patterns themselves). The validator is *necessary* because the LLM occasionally regenerates a tail with the same boilerplate it was asked to replace.

The naïve whole-output validator **false-rejects** outputs whose forbidden substring legitimately appears in the *preserved head*. Concretely: the head contains the phrase "成本效益评估" (cost-effectiveness evaluation) in 23 of the 117 public-health entries because that phrase is a legitimate domain term in the head, not a piece of boilerplate the LLM regenerated. A whole-output check counts these 23 entries as failed rewrites, blocking the cleanup; an inspection of the rewritten tails shows the *tails* are clean.

### 4.3 The remediation

The fix is a two-line change: validate the **tail only**, where the tail is the slice of the LLM output starting at the known head boundary:

```python
new_only = new_full[len(head):]
if any(forbidden in new_only for forbidden in FORBIDDEN_SUBSTRINGS):
    flag(entry)
```

For Wave 3 C, the head-aware validator processed 117 entries through OpenRouter (Kimi K2.5) in 18 s wall clock at total LLM cost $0.05, with **0 false-rejects** on the head side. A counterfactual whole-output check on the same 117 outputs would have false-rejected at least the 23 entries with the shared head connector phrase.

A separate **deterministic strip pass** (no LLM call, no cost) removes the 30-character connector phrase from the affected 23 entries' heads, eliminating the embedding-pollution downstream. The two-pass combination (head-aware LLM rewrite of tails + deterministic strip of head collisions) is the pre-registered procedure for any future KB cleanup with the same structure.

### 4.4 Scope, falsifier, and explicit non-claims

The pattern applies when (i) the LLM task is a *rewrite*, not a fresh generation; (ii) the safety check is intended to certify the LLM has not introduced forbidden content (rather than that the input was free of forbidden content); (iii) the head boundary is deterministically computable.

The falsifier is an **adversarial LLM behaviour**: if the LLM moves forbidden content from the legitimately-containing head into the LLM-generated tail (paraphrasing the head into the tail while replacing the original tail), the tail-only check passes but a whole-output check would have caught the violation. The mitigation is a *cross-check*: compare the rewritten tail's forbidden-substring profile to the head's, and flag any forbidden substring that appeared in the head AND now appears in the tail. We did not exercise the falsifier in Wave 3 C because the Kimi K2.5 outputs did not move boilerplate from head into tail on any of the 117 entries; the pre-registration ([19]) commits to running the cross-check as standard practice on subsequent KB cleanups.

The pattern is explicitly *not* claimed to be (a) a scientific universality claim; (b) safe against adversarial LLM behaviour; (c) the only way to handle fixed-prefix rewrite tasks (alternatives include constrained-decoding harnesses and pre-classifying the head for forbidden content separately). It is the *cheapest* of the options at the scale we deployed, not the only one.

## 5. Cross-pattern remarks and explicit anti-overclaim hedges

The three patterns share a structural feature: each was surfaced not by a single failed experiment but by the **cross-domain accumulation of failure modes** that the universality program's scope forced into view. Pattern 1 only became visible because two binary-outcome classes were being co-validated and their respective pre-registration internal consistencies could be cross-checked. Pattern 2 only became visible because the aggregation_kinetics class spans biology + biochemistry + cancer and the per-population vs per-aggregate split is forced by the data heterogeneity, not by a single-domain habit. Pattern 3 only became visible because the KB hygiene problem hit the embedding-similarity stage of a Layer 1 community-detection pipeline, where head-internal collisions visibly *broke* the clustering.

We hedge each contribution explicitly:

- **Pattern 1 is targeted, not general.** Three explicit non-applicability cases [13] are publicly recorded. The pattern is offered as a sharp tool for a specific failure mode, not as a universal upgrade.
- **Pattern 2 is general but does not substitute for cross-domain replication.** The verdict ladder explicitly requires ≥ 2 distinct domains for `PASS-CONFIRMED-MULTILAYER` and ≥ 3 for `PASS-STRONG-MULTILAYER`. Multilayer testing *increases* the number of pre-registered constraints, it does not *replace* the cross-domain replication count threshold §3.5.1 of the universality preprint [1]. Nor is multilayer testing a substitute for the cross-domain scatter threshold (Layer 0 descriptor-vs-mechanism screen) of the v0.4 universality preprint.
- **Pattern 3 is engineering, not methodology.** §4.1 stratifies it explicitly as tier-3 in the v0.5 methodology checklist [20]. Reviewers should not weight it alongside the scientific contributions.
- **None of the three patterns is novel in its underlying mathematical or engineering form.** Threshold-tobit models (Pattern 1) are canonical in econometrics since the 1950s; multi-scale testing (Pattern 2) is canonical in physics; head/tail slicing for safety checks (Pattern 3) is canonical in software engineering. The contribution is the **systematic application**, the **pre-registered scope discipline**, and the **explicit non-applicability audits** — not the underlying mathematical or engineering ideas.

Why publish a methods note rather than fold these into the main universality preprint? Two reasons. First, the three patterns are **reusable beyond our specific universality-class taxonomy** — the (s*, k) reparametrisation is useful for any binary-outcome pre-registration with the over-specification failure mode; multilayer testing is useful for any candidate class with hierarchically-scaling theory; the head-aware validator is useful for any LLM rewrite pipeline. Locking them inside a domain-specific preprint reduces their discoverability. Second, the empirical sections of the universality preprint [1] are dense; the methodology patterns benefit from a standalone presentation where each scope condition and non-applicability case can be read without the surrounding empirical context.

We emphasise one risk we have *not* fully retired: the present note describes three patterns surfaced in a single cross-domain program led by a single analyst, with the LLM-tooling decisions on a single research stack. We expect the patterns to transfer; we have not yet verified transfer on an independently-led cross-domain program with different tooling. The pre-registration commitments are designed to keep that verification honest: each pattern's pre-registration document lists explicit candidates for future replication and commits to publishing the verdict regardless of outcome.

## 6. Pre-registration references

The three patterns are formally pre-registered as standalone methodology commitments. The pre-registration documents are checked into the project repository at:

| Pattern | Pre-registration file | Tier |
|---|---|---|
| (s*, k) reparametrisation | `paper/v0.5-draft/preregistrations/preregistration-3.6.5-sk-reparam-2026-05-25.md` | 1 (targeted remediation) |
| Multilayer testing | `paper/v0.5-draft/preregistrations/preregistration-3.6.6-multilayer-2026-05-25.md` | 2 (general methodology) |
| Head-aware LLM validator | `paper/v0.5-draft/preregistrations/preregistration-3.6.7-head-aware-validator-2026-05-25.md` | 3 (engineering provenance) |

Each pre-registration document records: (1) the hypothesis statement of the pattern; (2) the scope conditions under which the pattern is claimed to apply; (3) an explicit non-applicability list; (4) a verdict ladder for *the pattern* (not the class to which it is applied); (5) a falsifiability criterion; (6) what is explicitly not being claimed; (7) the resource budget for the pattern's first instance and for future applications; (8) the data and script provenance.

The pre-registration discipline is consistent with the adversarial-pre-registration framing of [21] — the unit of credibility is whether the pattern, applied mechanically when its scope conditions are met, delivers a feasible pre-registration without re-introducing the failure mode it remediates on the next class it is applied to.

The full v0.5 incorporation of the three patterns into the main universality preprint is in `paper/v0.5-draft/v05-draft-skeleton.md` §§3.6.5, 3.6.6, and 3.6.7, with the reviewer-facing traceability sheet at `paper/v0.5-draft/methodology-increment-checklist.md`.

## 7. References

[1] W. Qinghui, "A pipeline for cross-domain validation of self-organized criticality: completing the taxonomy," Structural Isomorphism Project preprint v0.4 (2026-05). arXiv:[PENDING_C1_ARXIV_ID].

[2] Structural Isomorphism Project. Code and data: github.com/dada8899/structural-isomorphism; taxonomy browser at https://structural.bytedance.city.

[3] A. Clauset, C. R. Shalizi, and M. E. J. Newman, "Power-law distributions in empirical data," *SIAM Rev.* **51**, 661 (2009).

[4] Q. H. Vuong, "Likelihood ratio tests for model selection and non-nested hypotheses," *Econometrica* **57**, 307 (1989).

[5] J. M. Beggs and D. Plenz, "Neuronal avalanches in neocortical circuits," *J. Neurosci.* **23**, 11167 (2003).

[6] B. D. Malamud, G. Morein, and D. L. Turcotte, "Forest fires: An example of self-organized critical behavior," *Science* **281**, 1840 (1998).

[7] D. Sornette, *Critical Phenomena in Natural Sciences*, 2nd ed., Springer (2006).

[8] M. V. Smoluchowski, "Versuch einer mathematischen Theorie der Koagulationskinetik kolloider Lösungen," *Z. Phys. Chem.* **92**, 129 (1917).

[9] T. C. Schelling, *The Strategy of Conflict*, Harvard University Press (1960); C. P. Bown, "The WTO and antidumping in developing countries," *Econ. Polit.* **20**, 287 (2008).

[10] A. C. Cameron and P. K. Trivedi, *Microeconometrics: Methods and Applications*, Cambridge University Press (2005). [threshold-tobit reference]

[11] J. M. Wooldridge, *Econometric Analysis of Cross Section and Panel Data*, 2nd ed., MIT Press (2010).

[12] Structural Isomorphism Project, `v4/validation/schelling-credible-commitment/verdict_v5.md`. First-instance PASS verdict under (s*, k) reparametrisation.

[13] Structural Isomorphism Project, `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`. Three-class non-applicability audit.

[14] G. B. West, J. H. Brown, and B. J. Enquist, "A general model for the origin of allometric scaling laws in biology," *Science* **276**, 122 (1997).

[15] M. V. Smoluchowski, op. cit. [8].

[16] B. T. Hyman, J. C. Augustinack, and M. Ingelsson, "Transcriptional and conformational changes of the tau cytoskeletal protein in Alzheimer's disease," *Ann. Neurol.* **64**, 115 (2008). [multiplicative-stochastic prediction]

[17] Structural Isomorphism Project, `v4/validation/aggregation-kinetics/verdict.md`. First-instance `PASS-STRONG-MULTILAYER` verdict.

[18] Structural Isomorphism Project, `paper/v0.5-draft/preregistrations/preregistration-3.6.6-multilayer-2026-05-25.md`. Multilayer pattern pre-registration with 4 v0.6+ candidates.

[19] Structural Isomorphism Project, `paper/v0.5-draft/preregistrations/preregistration-3.6.7-head-aware-validator-2026-05-25.md`. Head-aware validator pre-registration (tier-3 engineering).

[20] Structural Isomorphism Project, `paper/v0.5-draft/methodology-increment-checklist.md`. Reviewer-facing traceability sheet stratifying the three patterns by tier.

[21] Structural Isomorphism Project, `paper/anti-phacking-unified-2026-05-15.md` §1.2. Adversarial pre-registration framing.

[22] W. Qinghui, "A reject-aware pipeline for cross-domain universality discovery," Structural Isomorphism Project preprint v0.4 (2026-05). arXiv:[PENDING_C4_ARXIV_ID]. Companion methodology preprint covering the LLM critic stages (B1 single-Opus + B3 within-vendor multi-decoding ensemble); the head-aware validator pattern in §4 of the present note is a sibling engineering contribution.

End of methodology short-note.
