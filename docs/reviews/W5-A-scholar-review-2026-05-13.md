# W5-A Scholar Review — structural-isomorphism v4/session3

> **Reviewer persona.** Senior statistical-physics / SOC-criticality researcher; referee experience for *PRE*, *Chaos*, *J. Stat. Mech.*, *Nat. Commun.*, *Phys. Rev. Lett.*; SOC / cascade / heavy-tail working group.
> **Date.** 2026-05-13.
> **Scope.** Full project state after session #3 — `paper/v0-unified-pipeline-2026-05-13.md` (C1, ~12.5k words, v0.2), four solo arXiv drafts (`paper/arxiv-drafts/2026-05-13/01..04_*.md`, ~3.3-4.2k words each), the C4 methodology preprint (`paper/c4-reject-aware-pipeline-2026-05-13.md`, ~8.2k words), the reproduction tutorial (`tutorials/01_reproduce_earthquake_soc.ipynb`, 23 cells), and supporting v4/ pipeline + B3 ensemble results.

---

## 1. Overall verdict (TL;DR)

This is an unusually **honest** and **methodologically self-aware** single-author cross-domain SOC project, well above the average preprint of its kind. The infrastructure is impressive — one frozen pipeline, thirteen independently fetched datasets, four explicit synthetic nulls, a multi-model taxonomy critic — and the writing is candid about its weak spots in a way most universality-claim papers refuse to be. **However, the headline "universality class verified across thirteen systems" claim is currently *oversold by half a step*.** The strongest defensible result is **"a single Clauset-grade pipeline recovers literature-consistent exponents across thirteen domains without per-domain tuning, plus a shape-normalized collapse on seven of them"** — which is *already a publishable, novel methodological contribution*. The leap from that to "first quantitative confirmation of universality-class membership" (§4.4, §4.5) is rhetorically larger than the statistics support.

**Disposition if I were on the editorial board.**
- **C1 v0.2 → arXiv (`cond-mat.stat-mech` / `physics.data-an`):** ready, with revision per §7 below. Strong post.
- **C1 v0.2 → PRE:** send to review, expect *major revision*. Two of the four reviewers in this community will hammer §4.5 BIC-vs-Vuong tension and the n=123 power-grid fit.
- **C1 v0.2 → *Nature Phys. Comm.* or *Nature Phys.*:** **desk-reject as currently framed**. The "first cross-domain universality confirmation" framing will not survive the editorial filter; rewrite as a *methods* paper for *Nat. Commun.* (still 50/50).
- **C2 4 solo drafts → arXiv:** 2 ready (Phase 1, Phase 4), 1 borderline (Phase 3), 1 needs major revision (Phase 2).
- **C4 reject-aware methodology paper → *NeurIPS-D&B* track or *J. Stat. Softw.* / *Patterns* (Cell Press) → likely accept** with revision. This may actually be the *strongest* paper in the bundle.

---

## 2. Strengths (what holds up)

1. **The pipeline freeze is a methodological gold standard for this literature.** `v4/lib/soc_pipeline.py` at commit `7ee228c` with zero per-phase tuning, all data loaders externalized, the same `powerlaw` calls everywhere — this is exactly what Clauset, Shalizi & Newman (2009) wished the field would adopt. Reviewer paragraph 1 should and will praise this.

2. **The four-system synthetic null battery (Phase 5) is genuinely discriminating.** Most universality papers skip this entirely; the fact that |dX| Gaussian-walk, exponential, Poisson IAT, and Poisson-Omori-stack all return $R \in [-17, -45]$ versus alternatives is a real validation. C1 §3 paragraph on Phase 5 (lines ~175-178) is the strongest single paragraph in the bundle.

3. **Honest accounting of lognormal coexistence.** §6.2 of C1 is unusually candid: the paper *explicitly* reports that Vuong-on-raw prefers lognormal in Phase 10 (wildfires) and Phase 13 (Wikipedia), and does not pretend BIC-on-binned closes the question. Three quarters of the empirical-power-law literature would have buried this in supplementary. **This is the single most credibility-boosting authorial choice in the manuscript.**

4. **Mouse cortex scaling-relation test (Phase 4) is rigorous.** Reporting bin-factor sensitivity, recovering the BGW $\gamma$ exactly at every bin, and *interpreting* the upward exponent drift as Priesemann-Munk-Wibral sub-critical rather than as a class-membership failure — this is competent SOC physics. Solo arXiv draft 04 is in good shape.

5. **B3 multi-model taxonomy critic is a novel methodological contribution.** Independently of whether SOC universality classes exist, the *reject-aware* pipeline of C4 — "report rejection rate alongside discovery rate" — is genuinely new in this corner of statistical physics + ML methodology. The four B3-driven demotions (`delay_differential_debt`, `hysteresis_preisach` monolith, `scale_free_percolation_class`, `tail_copula_contagion`) on the "mathematical framework masquerading as universality class" filter are *correct*, and the convergence across three reviewers on that filter is the cleanest methodological result in the bundle.

6. **A2 phases (Hysteresis, Scheffer) demonstrate framework portability.** That the *framework* (frozen pipeline + pre-registered bands + synthetic nulls + multi-model taxonomy) extends to non-power-law class invariants (branch-percentile-ratio for Preisach, AR1+Variance Kendall-$\tau$ for Scheffer) is a non-trivial generalization. The reviewer-correct framing here is "the framework, not the SOC pipeline, is what's being demonstrated to be cross-class portable."

7. **C4 reject-aware paper is independently strong.** §1-§3 of C4 read like a real ML methodology paper. The 7/21 = 33% vs 3/21 = 14% B3 vs B1 rejection-rate comparison is a clean, replicable result with cost numbers and wall-clock — exactly the kind of thing *NeurIPS Datasets & Benchmarks* track values.

8. **Author voice is calibrated, not hyperbolic.** Phrases like "small-sample qualified," "lognormal not ruled out," "partly procedural," "first-non-trivial cross-validation" are *appropriate hedges*, not weasel words. Editors notice.

---

## 3. Critical concerns (what doesn't)

1. **§4.4 / §4.5 headline ("first positive proof of universality class membership") is overreach** given the underlying $r_{\rm shape} = 1.11$ ratio depends on (i) only 7 systems, (ii) row-centered log-PDFs (a transformation that absorbs the very prefactor whose dimensional incommensurability is the obstacle to claiming class membership), and (iii) no formal hypothesis test. See §4 below. **Recommended downgrade:** "consistent with shared functional form" rather than "first positive proof."

2. **n=123 literature-meta catalog for Phase 7 (power grid) cannot bear the weight placed on it.** The paper labels Phase 7 a "13-system" confirmation, but Phase 7 is not an *independent* empirical measurement — it's a curated literature-meta whose anchor values are Carreras 2016 ($\alpha = 2.16$) and Hines 2009 ($\alpha = 2.2$), and the catalog was assembled with knowledge of those anchors. The "Clauset MLE recovered $\alpha = 2.018$ on this set" is therefore approximately *the consistency check of curating-the-known-against-itself*, not a fresh test. The honest framing is: "$n=123$ literature-meta corroborates Carreras 2016 and Hines 2009." Treating it as the thirteenth system materially weakens the headline count.

3. **Multiple comparisons / familywise error rate is nowhere controlled.** 13 systems × at least 2 LR tests each + 7-system BIC + universal collapse + 4 nulls = at minimum 30 statistical decisions in the manuscript. No Bonferroni, no Benjamini-Hochberg, no $\alpha$-inflation discussion. At nominal $\alpha = 0.05$ per test, an FWER above 0.5 is likely. This is the **single most important reviewer-pass issue** for *PRE* / *Chaos* — it will come up in reviewer 1's first comment.

4. **B3 "multi-model ensemble" claim is procedurally weak.** Three DeepSeek reviewers (v4-pro rigorous, v4-flash rigorous, v4-pro creative) constitute a *temperature/decoding-variant ensemble within a single model family*, not a multi-model ensemble in the architectural sense. The paper says so honestly in §5.5 ("same-vendor cross-model"), but the surrounding language still calls it "multi-model ensemble" and the B1-vs-B3 disagreement analysis (C4 §4) reads it that way. **An LLM auto-curated taxonomy reviewed by three forward-passes of one company's model is closer to a self-consistency check than to a true ensemble.** Cross-family (Kimi K2.5 + GLM-5 + DeepSeek + Claude Opus + GPT-5) is required for the claim. The current B3 result is *suggestive* not *demonstrative*.

5. **Phase 13 (Wikipedia) framing partially erases its own caveat.** §3 reports Vuong $R = -6.31$ ($p = 2.7 \times 10^{-10}$, decisively favoring lognormal), then defends the PA verdict with "the point estimate matching $\alpha = 2$ to three decimal places is the operative evidence" (line 201). This is *post-hoc point-estimate reasoning* and exactly the failure mode Stumpf & Porter (2012, [17]) warn against. The paper cites Stumpf & Porter elsewhere but doesn't apply their critique here. Reviewer 2 of any econophysics-aware journal will pull this thread.

6. **Bootstrap n=100 is below current best practice across the board.** §2.2 acknowledges this ("low end of best practice") but does not re-run at $n=1000$ for the headline phases. Phase 7 small-sample bumps to 300, but the other 12 phases stay at 100. This is fixable trivially (`for i in range(1000)`) and there is no defensible reason to publish at 100; the only cost is overnight compute.

7. **Vuong test below n=50 reported as "inconclusive"** in Phase 7 ($n_{\rm tail} = 40$) — this is correct Clauset usage, but the verdict label "CONFIRMED, lit-anchored" then *anchors against literature values that share the same n-floor problem*. Phase 7 should report verdict as "consistent within literature uncertainty, sample-size-limited"; the current language reads like an empirical confirmation it isn't.

8. **`xmin` selection rigor for small-n phases not stress-tested.** The Clauset KS-minimization for `xmin` is known to overfit for $n < 200$ tail samples (cf. Deluca & Corral 2013, *Acta Geophys.*; Voitalov et al. 2019, *Phys. Rev. Res.*). Phase 7 ($n_{\rm tail} = 40$) absolutely needs an `xmin` sensitivity scan — vary `xmin` across the 10th–90th percentile of the support and report the $\alpha$ envelope. Without this, the point estimate $\alpha = 2.018$ is one of a family of plausible values, several of which fall outside the $[1.3, 2.0]$ Motter-Lai band.

9. **AR(1) $p = 1.6 \times 10^{-186}$ (Scheffer, Fox River)** is almost certainly **numerical underflow / asymptotic Kendall-$\tau$ misuse on 4,686 highly autocorrelated samples**, not the literal probability. Daily DO observations have lag-1 autocorrelation ~0.9 (the paper itself reports AR(1) drift from 0.80 to 0.90); under serial dependence the nominal Kendall-$\tau$ variance is severely under-estimated, inflating $|z|$ by $1/\sqrt{1-\rho^2}$ at minimum. A block-bootstrap or pre-whitened time-series Kendall test would land somewhere in $p \in [10^{-10}, 10^{-30}]$ — still extraordinarily significant, but reporting $10^{-186}$ invites desk-reject from any ecology / time-series-aware editor.

10. **No held-out / out-of-sample prediction.** The paper *retrofits* exponent bands to the data ("every observed $\alpha$ in Table 1 sits inside the predicted band" — §5.4 line 294, then immediately notes the 11/11 coverage is "suspiciously high"). This is honest but not curative: pre-register the next 5 systems' bands *before* fitting them, then publish the prediction success rate. Otherwise §5.4 reads as confirmation bias documented but not addressed.

---

## 4. Methodological assessment

### 4.1 Statistical inference (Clauset 2009 pipeline)

**`xmin` selection.** Standard `powerlaw.Fit` with KS-distance minimization is used throughout (C1 §2.1, line 68). This is correct in principle but has documented edge-case behavior on small $n$ and on distributions with curvature near the candidate `xmin` regime. The paper does not report sensitivity of $\alpha$ to perturbations in `xmin`. For Phase 7 ($n_{\rm tail} = 40$), Phase 4 ($\tau$ varying across bin factors 2-16), Phase 13 (Top-1000-truncated catalog), and Phase 11 (GOES bandpass-thermal effects), this is a real concern. **Recommended:** for each phase, add a supplementary figure showing $\alpha(x_{\rm min})$ on a sliding window across the support, with the chosen KS-minimum `xmin` marked. Existing best-practice references: Corral & González 2019 (*Geophys. J. Int.*); Voitalov et al. 2019.

**Bootstrap CI coverage.** $n_{\rm boot} = 100$ throughout (300 for Phase 7), §2.2. For a 95% bootstrap percentile interval, 100 resamples gives ~$\pm 1$ resample uncertainty at the 2.5 and 97.5 percentile — entirely inadequate for the precision claims in Table 1 (e.g., Phase 2 reports CI $[2.74, 3.00]$ at 100 resamples). The fact that this is documented as "conservatively widens the reported CI" is not quite right: at 100 resamples, the *CI endpoints themselves* have ~10% standard error. Rerun at $n_{\rm boot} = 10000$. (Cost: ~1 CPU-hour per phase. Trivial.)

**Vuong test sample size.** Clauset et al. (2009) §6.3 cautions against Vuong below $n_{\rm tail} = 50$. Phase 7 explicitly acknowledges this. **But** Phase 2 ($n_{\rm tail} = 2{,}327$), Phase 13 ($n_{\rm tail} = 2{,}817$), Phase 10 ($n_{\rm tail} = 1{,}591$), Phase 11 ($n_{\rm tail} = 4{,}336$) all have ample $n$ and Vuong-test results are reported as primary evidence — these are the cases where the lognormal-vs-power-law disagreement is real, not an artifact of low power. The paper hedges these with BIC-on-binned in Phase 12, but BIC and Vuong are testing different things on differently weighted data. See §4.6 of C1 — the author flags this as "procedural tension" — but the resolution offered ("the V4 universality-class claim is strongest at the shape-collapse + BIC-on-binned level") is *unilaterally privileging the test that wins*. **A reviewer-defensible resolution would be: report both, do not declare a winner, and treat Phase 2 / 10 / 13 as "power-law consistent with lognormal coexistence under multiplicative-growth models (Mitzenmacher 2004)" rather than as straightforward PL confirmations.**

**Multiple testing correction.** Not addressed (see §3.3). The Vuong $p$-values reported as $10^{-9}$, $10^{-25}$, etc. for raw exponential rejection are so far below any reasonable FWER threshold that they survive even paranoid Bonferroni; the lognormal *failures* and the *inconclusive* verdicts (Phase 6, Phase 8, Phase 11) are where multiple-testing matters and is absent.

### 4.2 Universality class taxonomy (B3 ensemble)

**24 → 21 → 5 KEEP convergence.** Layer 3 reduces 24 candidates to 21 by curator-driven merger. B1 (single Opus) keeps 11, splits 4, merges 3, rejects 3. B3 (3× DeepSeek) keeps 5, rejects 7, splits 5, merges 4. The B3 convergence on the "mathematical framework masquerading as universality class" filter — converging across all three DeepSeek calls on `delay_differential_debt`, `tail_copula_contagion`, `scale_free_percolation_class`, and `hysteresis_preisach` monolith — is the **single most defensible methodological result in the project**. The filter is correct: each of these four is genuinely a parametric family / limit theorem / generative model, not a mechanism-defined universality class. **Keep this; even if everything else weakens under reviewer scrutiny, this section is publishable as a standalone methodology contribution.**

**B3 rejections of `tail_copula_contagion` and `scale_free_percolation_class`.** These are the right calls. Copulas are joint-distribution parametric families that cross-cut SOC-cascade, network-effect, and EVT contagion — the cross-domain "shared equation" is the copula integral, which is generative-model infrastructure, not class identity. Scale-free percolation is a property of a connection-probability kernel, not of the resulting equivalence class of critical exponents. **Both are defensible REJECTs and would survive PRE referee scrutiny.**

**B3 demotion of `hysteresis_preisach` (monolith).** Correct call, with one subtlety: the A2 phase verified the *traffic-Preisach* sub-class empirically (§3.A2-Hysteresis), and the §5.5 reasoning explicitly splits Preisach into magnetic / traffic / capillary sub-classes. This is the right answer, but the C1 abstract still credits the verification to "the Preisach hysteresis prediction" generally. **Tighten the abstract: "the traffic-Preisach sub-class prediction."**

**"ensemble" claim — three DeepSeek runs.** Already discussed in §3.4. The single-vendor ensemble is *not* an architectural disagreement test; it's a temperature/decoding-variant self-consistency test on one model. The B3 7/21 = 33% rejection rate vs B1 3/21 = 14% comparison in C4 §4 *is real and methodologically interesting* (because it tells us a fresh forward pass at $T=0.6$ catches things a single $T=0$ Opus call missed), but the lift from 14% → 33% says **"DeepSeek-flash and DeepSeek-pro at $T=0$ and $T=0.6$ disagree with Opus at $T=0$ on 4 cases"** — which is a within-vs-cross-model disagreement test, not a within-vs-within-model false positive rate test. The paper should be more careful with the framing. **Recommended downgrade:** "cross-vendor reviewer disagreement" → "cross-vendor reviewer comparison."

### 4.3 Empirical validation depth

Per-phase verdict-evidence-strength inventory:

| Phase | Evidence | Holds up? |
|---|---|---|
| **1 USGS earthquakes** | $b = 1.084$, $\alpha_E = 1.79$, Omori $p = 0.94$, $R^2 = 0.99$, $n = 37{,}281$ | **Strong.** Canonical-recovery cross-check on a well-validated system, two independent fitting routes agree within $3\sigma$. |
| **2 S&P 500** | $\alpha = 3.00 \pm 0.04$, Vuong-LN $R = -6.12$ | **Moderate.** Point estimate matches Gopikrishnan-Plerou-Stanley canonical, but lognormal cleanly wins on Vuong; the "0.07% match to canonical $\alpha = 3$" is post-hoc reasoning. |
| **3 DeFi (3 protocols)** | $\alpha \in [1.567, 1.684]$, spread 0.12, Omori $p \in [0.69, 0.76]$ across 3 protocols | **Strong.** Three-protocol cross-validation with architecturally distinct mechanisms is the **strongest novel result in the bundle.** |
| **4 mouse cortex** | $\gamma = (\alpha_T - 1)/(\tau - 1) = 1.10$ at $R^2 = 0.998$ across bin factors 2-16 | **Strong.** Scaling-relation invariance across a 16-fold binning sweep is the cleanest critical-systems signature available. |
| **5 4 synthetic nulls** | $R \in [-17, -45]$ vs alternatives, Omori-Poisson $R^2 = 0.0015$ | **Strong.** Discriminates correctly. |
| **6 GitHub stars** | $\alpha = 2.87$, Vuong-LN $R = -1.45$ (inconc.) | **Moderate.** PA confirmation reasonable, but per-language sub-fits at $\alpha = 2.61-3.00$ raise the same lognormal-coexistence concern as Phase 13. |
| **7 power grid** | $\alpha_{\rm MW} = 2.02 \pm 0.16$ on $n = 123$ literature-meta | **Weak.** Catalog curated against the literature anchors; not an independent test. Verdict label "confirmed" is too strong. |
| **8 FDIC bank failures** | $\alpha = 1.90$, no Omori, Vuong-LN inconc. | **Moderate.** Size confirmed, but the "no Omori = expected because the L01 sub-class doesn't predict Omori" is post-hoc rationalization; an a-priori prediction of no-Omori in this sub-class would have been better. |
| **10 NIFC wildfires** | $\alpha = 1.66$, Vuong-LN $R = -4.73$ (LN wins) | **Weak as PL claim; strong as honest reporting.** Lognormal beats PL decisively; the verdict "confirmed but lognormal preferred" is technically accurate but rhetorically contradictory. |
| **11 GOES solar** | $\alpha = 2.19$, Vuong-LN $R = +0.44$ (inconc.) | **Moderate.** PL not beaten by LN; Omori-null is expected per Wheatland. |
| **12 universal collapse polish** | $r_{\rm shape} = 1.11$ across 7 systems | **Moderate.** See §4.4 below. The shape-normalized ratio computation absorbs the unit prefactor that is itself the obstacle to claiming class membership across systems with incommensurate units. |
| **13 Wikipedia** | $\alpha = 2.03$, Vuong-LN $R = -6.31$ (LN wins) | **Weak.** Top-1000 truncation is dominant artifact, LN beats PL by $> 10\sigma$, "matches canonical $\alpha = 2$ to three decimal places" is post-hoc. |
| **A2-Hysteresis** | First-order signature 45% of locations, literature anchors $q_{c1}/q_{c2} = 1.38$ | **Moderate.** NGSIM-direct loop ratio $0.93$ is *outside* the band (paper rationalizes this as one-half-cycle artifact, which is plausible but not testable without PeMS data). |
| **A2-Scheffer** | $\tau_{\rm AR1} = +0.284$, $\tau_{\rm Var} = +0.234$, secular trend on 4,686-day series | **Strong on trend direction, weak on reported p-values** (see §3.9). |

**Universal collapse Phase 12 (shape-norm = 1.11)** — this is the headline claim and the most overstated one in the manuscript. See §4.4-4.5 of C1, then §4 below.

### 4.4 The shape-normalized collapse number — what does $r_{\rm shape} = 1.11$ actually buy?

The mathematics: take seven systems' log-binned PDFs on a shared rescaled grid, compute $M_{ij} = \log y'_{ij}$, then **row-center** to get $\tilde M_{ij} = M_{ij} - \overline{M_{i \cdot}}$, and report cross-system variance / within-system variance = 1.11.

Two concerns:

(a) **Row-centering absorbs $s^{*\,(\alpha-1)}$ exactly.** The paper acknowledges this in §4.4 (line 240): "Each row centered, absorbing the unit prefactor that $s^{*\,\alpha-1}$ does not." This is true and correct — but it means $r_{\rm shape} = 1.11$ is measuring the residual *shape* variance after the dominant systematic is removed. The corresponding *un-centered* ratio is $r_{\rm abs} = 184$, which the paper reports honestly. So the operational content is: "after subtracting the system-specific mean log-PDF, the remaining residual variance is small." This is informative but **does not constitute "first quantitative confirmation that seven systems share tail shape."** A reviewer-defensible claim: "after row-centering, the residual cross-system variance is within an order of magnitude of within-system Poisson variance, consistent with shared tail shape modulo systematic prefactor." Demote "first positive proof" to "consistent with."

(b) **No null distribution for $r_{\rm shape}$.** What is the expected value of $r_{\rm shape}$ under (i) seven *independent* lognormal tails matched to the observed $\mu$ and $\sigma^2$ of each system? (ii) seven independent power laws with mismatched exponents but matched $x_{\rm min}$? Without a permutation null, "1.11 is excellent because $r < 2$" is asserting a threshold without a sampling distribution. Christensen & Moloney is cited as the source of the $r < 2$ threshold, but that's about strict universality where the prediction is collapse onto a single curve, not residual log-PDF variance after row-centering. The threshold is being repurposed.

**Recommended:** generate 10,000 surrogate datasets where each of the 7 systems is independently fitted by lognormal with the empirical $\mu, \sigma^2$, then run the same row-centered ratio computation. Report $r_{\rm shape}$ from those surrogates. The empirical value's percentile rank against that null distribution is the actual significance statement.

**For literature benchmarks:** Beggs & Plenz (2003) shape collapse was on $\sim 3$ systems of the same type (cortical cultures of varying $n$), and was *visually* matched by curve overlay, with no $r$ value reported. Lübeck (2004) reviews finite-size scaling for sandpile-class systems where collapse $r \in [0.1, 0.5]$ is reported on single systems with varying $L$. Pruessner (2012) *Self-Organized Criticality* chapter 5 reports $r$ values for sandpile finite-size collapses in the 0.05-0.5 range. **A cross-system shape-collapse $r = 1.11$ is *not* in the "excellent" range by within-system finite-size-scaling standards; it's in the "marginal" range.** That said, **cross-system collapse is a much harder problem than within-system finite-size scaling, and 1.11 is a non-trivially small number.** The honest framing: "the cross-system shape collapse is at the level of the best within-system finite-size scaling collapses in the literature, modulo the methodological caveats of row-centering."

---

## 5. Paper-by-paper detailed feedback

### 5.1 C1 unified preprint v0.2 (`paper/v0-unified-pipeline-2026-05-13.md`)

**Length.** 12,538 words / 60 references / 1 mermaid figure / 1 numeric table. Slightly long for a single-letter venue, fine for *PRE* / *Chaos* / *arXiv*. **Recommended cuts:** §1 introduction can lose 200 words (lines 32-46 over-rehearse the history every SOC reader knows); §6.4 ("cross-class portability") can fold into §6.1; the Acknowledgments boilerplate around OpenRouter/DeepSeek can be cut to one sentence.

**Strongest sections.** §2 (pipeline spec — clean and reproducible), §3 Phase 5 (synthetic null discussion), §6.2 (lognormal honesty), §5.5 (B3 demotion explanations).

**Weakest sections.** §4.5 ("first positive proof of universality class membership" — see §4.4 above), §3 Phase 7 (n=123 literature-meta presented as 13th system), §3 Phase 13 (Wikipedia point-estimate post-hoc reasoning).

**Statistical issues already detailed in §3 and §4.**

**Figure 1 (mermaid).** Acceptable for arXiv but not publication-grade. The arrows are mostly decorative; the actual logical structure ("each phase calls these primitives in this order") doesn't come through. Replace with a proper data-flow / dependency DAG. The fact that A → B → C → ... is mostly linear means most of the diagram is dressing.

**Tables.** Table 1 is the workhorse and well-constructed. Add columns for `n_tail` and bootstrap-method (analytic Hill vs percentile) — currently only `n_total` is shown and these matter for interpretation.

**Recommended journal.** **arXiv `cond-mat.stat-mech` + `physics.data-an` immediate post.** Then *PRE* (high probability major-revision but eventually accept) or *Chaos* (high probability accept after minor revision). Nature Phys / Nature Phys Commun is desk-reject as currently framed; the "first cross-domain universality confirmation" language will not survive the editorial filter — they will see it as a *methods* paper, not a *physics* paper.

**Critical statistical issue to fix before posting (highest priority):**
1. Rerun all bootstraps at $n_{\rm boot} = 10{,}000$ (not 100). This is a 1-hour fix and removes a guaranteed reviewer comment.
2. Add a `xmin` sensitivity scan supplementary figure for Phases 7, 13, 4 (small or curved-support cases).
3. Rerun Scheffer Kendall-$\tau$ with block-bootstrap to get a defensible $p$-value (not $10^{-186}$).
4. Demote §4.5 headline to "consistent with shared tail shape" and add the surrogate-null permutation test for $r_{\rm shape}$.
5. Add a Bonferroni / B-H discussion sidebar somewhere in §2 or §6 — even a paragraph saying "we report nominal $p$-values; FWER across 30+ tests would shift inconclusive verdicts to inconclusive at $\alpha_{\rm FWER}$ but does not change any rejected/confirmed verdict" would close the issue.

### 5.2 C2 4 solo arXiv drafts (`paper/arxiv-drafts/2026-05-13/01..04_*.md`)

Words: Earthquake 4249 / S&P 3279 / DeFi 3870 / Neural 3335. References: ~35 each.

**Quality ranking (best to worst):**

1. **Paper 4 (Neural avalanches, DANDI 000006).** Cleanest paper of the four. The 200,000-synthetic-BGW-avalanche pre-validation is exactly the right move; the bin-factor sweep across $f \in \{1, 2, 4, 8, 16\}$ with $\gamma$-stability is rigorous SOC; the sub-class interpretation is consistent with Priesemann-Munk-Wibral 2014 and refines rather than contradicts class membership. **Ready for arXiv.** Minor: the writing slightly overstates "first application to a biological SOC system" — Plenz, Shew, Beggs etc. have applied near-equivalent pipelines extensively. Reframe as "first application of the Structural Isomorphism V4 pipeline to a biological SOC member."

2. **Paper 1 (Earthquake SOC).** The pipeline-validation paper. Solid, honest, well-written, the right level of caveat (limitations §5 is exemplary). **Ready for arXiv.** Minor:
   - Section 3.1 reports both Aki MLE $b = 1.084$ and Clauset $\alpha = 1.794$, and says they agree via $\alpha = 1 + b/1.5 = 1.722$ "within three Clauset standard errors." Three is wider than most readers will tolerate; the discrepancy 1.794 vs 1.722 is $\Delta = 0.072$, vs $\sigma_\alpha = 0.024$ — that's exactly $3\sigma$. Better framing: report this as a known small discrepancy attributable to the energy-domain `xmin` selecting a more restrictive tail than $M \geq M_c$, with the $b$-based prediction conservative.
   - Calibration band note (§4: "energy exponent prediction band $[1.3, 1.7]$ slightly too conservative on upper end") — flag this in abstract too, not just §4.

3. **Paper 3 (DeFi cross-protocol).** Methodologically the strongest result (three architecturally distinct protocols, $\alpha$ spread 0.12), but the writing leans on the "cross-protocol consistency = universality class confirmation" framing harder than the data supports. Three protocols with $\alpha \in [1.567, 1.684]$ is a 7% relative spread, which is large by the standards of within-class universality (canonical seismicity $b$-variance across tectonic domains is ~10%; that's the *upper* end of what within-class can absorb). Either argue more carefully for why 7% is class-consistent rather than mechanism-distinguishing, or weaken the claim to "consistent with shared sub-class." **Borderline; revise before arXiv.**

4. **Paper 2 (S&P 500 inverse cubic).** The least defensible of the four. Reproducing the Gopikrishnan-Plerou-Stanley result on 9k samples is fine, but Vuong-LN $R = -6.12$ ($p < 10^{-9}$ in favor of lognormal) and the explicit narrative that "the power-law verdict rests on $\alpha = 2.998$ matching the canonical 3.0 to within 0.07%" is **post-hoc point-estimate reasoning of exactly the kind Stumpf & Porter 2012 warn against** — and Stumpf & Porter is in the project's reference list. The Omori-Utsu $p = 0.286$ being labeled "inside Weber et al.'s [9] published daily-scale band $[0.3, 0.6]$" is *outside* the band; the rationalization "but Lillo-Mantegna intraday is $[0.7, 1.0]$, this is a scale-dependent feature" hand-waves the actual measurement (0.286) into compatibility with the band by appealing to scale-dependence. **Needs major revision before arXiv.** Either (a) reframe as honest report of LN-preferred tail with PL-consistent point estimate, with explicit Mitzenmacher 2004 cite for the LN/PA equivalence at finite $n$; or (b) reanalyze with intraday data (TAQ / 5-min bars from Wharton) and recover the canonical intraday $p \approx 1$ that would close the question.

**Inter-paper citation consistency.** Papers 1, 2, 3, 4 cite each other as `[5]`, `[6]`, etc. — confirm during finalization that the cross-citation numbers resolve correctly after author-list-finalization and Zenodo-doi assignment. **Currently the placeholder email `dada8899@users.noreply.github.com` and "*placeholder — author affiliation and contact details to be finalized prior to formal submission*"** appears in all four — this must be resolved (real institutional email + ORCID) before any arXiv post; arXiv's moderation pipeline will reject placeholders.

### 5.3 C4 reject-aware pipeline (`paper/c4-reject-aware-pipeline-2026-05-13.md`)

8164 words / 45 references / Mermaid pipeline diagram.

**This is probably the best paper in the bundle**, despite being labeled "v0.1 methodology preprint." Several reasons:

- The thesis (multi-model critic ensembles materially raise rejection rate over single-model critics, with cost numbers) is **clean, replicable, and interesting**. The B3 7/21 = 33% vs B1 3/21 = 14% rejection-rate difference is a quantitative claim with a baseline.
- The "mathematical framework masquerading as universality class" filter (§4.x) is a genuine methodological contribution that generalizes far beyond SOC. The four examples (delay-differential, copula, scale-free percolation, Preisach as monolith) are exactly right.
- The cost/latency framing (<\$1 per panel, 41 minutes) is **operationally relevant** for the LLM-in-the-loop research methodology community in a way most stat-phys papers aren't.
- The honest reporting of "same-vendor ensemble" as a methodological limitation, with explicit roadmap to cross-vendor (B4 with Kimi/GLM-5), is the right framing.

**Independent value.** Yes. This paper does **not** require any of the C2 results to stand; it could be posted standalone to *NeurIPS-D&B*, *J. Open Source Software*, *Patterns*, *J. Stat. Software*, or *Phys. Rev. Research* (data-driven physics) on its own merits. **Recommended venue:** *Patterns* (Cell Press) first choice, *NeurIPS Datasets & Benchmarks* second, *Phys. Rev. Research* third. ML venues will appreciate the LLM-eval methodology contribution; physics venues will appreciate the taxonomy-rigor contribution. arXiv `cs.AI` + `cond-mat.stat-mech` cross-listing.

**Overlap with C1.** Significant (B3 ensemble description, the 21-class panel results, the four demotion analyses). This is **fine** — the two papers can co-exist with C1 referring to C4 for the methodology details and C4 referring to C1 for the empirical-validation application. Keep them as separate papers; don't merge.

**Critical concerns.**
- The "rejection rate" comparison (B1 14% vs B3 33%) is a comparison of (single Opus reviewer at one read) vs (three DeepSeek reviewers at majority vote). This is a model-architecture-confound, not purely a within-model vs ensemble comparison. To isolate the ensemble effect, you'd need (i) Opus single vs Opus majority-of-3-at-different-temps, (ii) DeepSeek single vs DeepSeek majority-of-3. The current setup confounds vendor with ensemble-size. Acknowledge or fix.
- "0 API errors" is a robustness claim that's nice to make but immaterial to the methodology. Cut from headline; keep in §3.
- The five-layer pipeline diagram (§2) is sound but could compress to three layers (extract / curate / critic+predict / validate); the L3.5 / L3.6 distinction is fine-grained and probably better as a single "critic gate" layer with two sub-stages.

### 5.4 Tutorial (`tutorials/01_reproduce_earthquake_soc.ipynb`)

23 cells / 385 lines / ~30 min ETA / produces $b$-value, Clauset $\alpha$, Vuong LR, log-log plot, verdict.

**Does it deliver 30-min reproducibility?** Almost. Specific concerns:

(a) **The tutorial computes $b$ on 1 year (2020) of data (~15,700 events), but the paper reports $b = 1.084$ on 5 years (2020-2025, 37,281 events).** Cell 22 (Discussion) honestly tells the reader to "re-run with `starttime=2020-01-01, endtime=2025-01-01` to reproduce the published result." This is fine but means **the headline tutorial number won't match the headline paper number**. A reader running the notebook gets ~$b = 1.08 \pm 0.02$ on 1 year (wider CI), not $b = 1.084 \pm 0.005$. State this delta explicitly in cell 0 (Goal) to avoid reader confusion.

(b) **The "α≈1.67 predicted from b/1.5" comment in Cell 14** does not match the paper's report of $\alpha = 1.794$ from the Clauset fit on energies. The reason is the Clauset fit selects $x_{\rm min}$ in *seismic-moment units* substantially above $10^{1.5 \cdot M_c}$, so the effective magnitude threshold is higher and the resulting $\alpha$ is on a more selective tail. This is exactly the discrepancy noted in C2 paper 1 (3$\sigma$). Tutorial cell 14 should *explain this*, otherwise readers will see "predicted 1.67, got ~1.79" and incorrectly think the tutorial failed. Reframe: "$b \approx 1$ predicts a magnitude-domain power-law exponent equivalent to $\alpha = 1 + b/1.5 \approx 1.67$ if we fit on a tail starting at $M_c$. The Clauset MLE chooses its own (more restrictive) $x_{\rm min}$, typically giving $\alpha$ closer to 1.79 on a smaller tail. Both numbers are consistent SOC measurements on different tail definitions."

(c) **Cell 21 (Verdict)** uses `narrow = (0.9 <= b <= 1.1)` and `lit = (0.8 <= b <= 1.2)`. The narrow band is correct for global tectonic; the literature band is generous. Fine for a tutorial.

(d) **Cell 22 reference numbers.** The tutorial says "expect $b \approx 1.084$, CI $[1.07, 1.09]$" — these are the *reference values from the paper*, not a tutorial-derivable verification. Reader needs to know whether the tutorial computes them or just compares against them.

(e) **The numeric mismatch in the user-prompt context — "α=1.882 in tutorial vs b=1.084 in paper headline"** — is *not* what the tutorial actually outputs. The tutorial outputs $b \approx 1.08$ (Aki MLE) and $\alpha \approx 1.67$-$1.79$ depending on `xmin`. The α=1.882 figure does not appear in either the tutorial or the paper's Phase 1 section (Phase 8 bank-failure $\alpha = 1.899 \pm 0.045$ is the closest number, but that's an entirely different system). **The reported confusion is real but the source value is misidentified; treat this as a clarification opportunity in cell 0.**

**Improvement priorities for the tutorial:**

1. Cell 0: state explicit numeric expectation deltas for 1-year vs 5-year run (in a small table).
2. Cell 14 (Clauset fit): add the 1.67 vs 1.79 explanation paragraph above.
3. Cell 21 (Verdict): print both Aki-$b$-implied $\alpha$ and Clauset-fitted $\alpha$, with the explanation that they differ because of `xmin` choice.
4. Add a 24th cell at the end: "Run on your own incident-size data" template — currently mentioned in cell 22 prose but not given as a runnable cell. This is the bridge from tutorial to cross-domain transfer.

**Verdict on tutorial:** publishable as a companion to the arXiv post, with the cell 14 explanation paragraph added.

---

## 6. Universality / cross-domain claim strength assessment

**Maximum claim being made:** "universal collapse across 7 systems (shape-norm = 1.11), first quantitative confirmation of universality-class membership rather than isolated coincident power laws."

**Is this the first systematic cross-domain universal collapse?** *Approximately yes, with strong caveats.* Cross-domain collapse attempts in the SOC literature have been (i) **within-class same-domain** (Lübeck 2004 review of sandpile finite-size collapse across system sizes; Beggs-Plenz 2003 across cortical preparation types), (ii) **cross-class within-physics** (Pruessner 2012 chapter 5 across sandpile / forest-fire / Manna model), and (iii) **cross-domain narrative** (Bak 1996 *How Nature Works*, Sornette 2006 *Critical Phenomena*, where the claims are by example without quantitative collapse). **The present project's attempt is the first to assemble 7+ cross-domain systems with one frozen pipeline and report a quantitative collapse ratio.** That is genuinely novel, even after demoting "first positive proof" to "consistent with."

**Is shape-norm = 1.11 "excellent" / "good" / "mediocre"?** By the literature thresholds I'm aware of:
- Within-system finite-size collapse: excellent < 0.1, good 0.1-0.5, mediocre 0.5-2.0 (Pruessner 2012; Lübeck 2004).
- Cross-domain row-centered collapse: no established threshold; this paper is the first to report one.

So 1.11 is *mediocre* by within-system finite-size scaling standards, but those standards don't apply directly. The honest framing is **"consistent with shared functional form modulo prefactor, at a residual variance level that for within-system collapses would be called mediocre, but with no published benchmark for cross-domain row-centered collapses to compare against."** The paper currently calls 1.11 "excellent by the $r < 2$ threshold" (§4.4) — that's borrowing a within-system threshold and applying it cross-domain without justification.

**Literature benchmarks for cross-domain $\alpha$-band consistency:**
- Newman 2005 *Contemp. Phys.* surveys 24 systems with reported $\alpha$ values; the cross-system variance after class-stratification is comparable to or larger than within-class variance.
- Broido & Clauset 2019 *Nat. Commun.* "Scale-free networks are rare" found that strict scale-free claims survive rigorous testing in <5% of network datasets surveyed. **Apply the same standard to SOC claims and the present paper's 9/11 power-law confirmation rate is suspiciously high** (§5.4 of C1 already flags this). This is the single biggest reviewer concern after multiple-testing.
- Stumpf & Porter 2012 *Science* "Critical truths about power laws" — applies in full to Phases 10, 13, and arguably 2.

---

## 7. Statistical concerns / red flags (consolidated)

Five (actually nine) statistical / methodological issues, in priority order:

1. **Multiple-testing not controlled.** 30+ tests, no FWER discussion. Fix with one supplementary paragraph; non-blocking for arXiv but blocking for *PRE*.

2. **Bootstrap n_boot = 100 throughout.** Below current best practice (1000-10000); CI endpoints have ~10% standard error. Fix by re-running overnight at 10,000.

3. **`xmin` sensitivity not stress-tested for small-n / curved-support phases.** Phase 7 ($n_{\rm tail} = 40$), Phase 13 (truncated catalog), Phase 4 (bin-factor sensitivity). Fix with sliding-`xmin` supplementary figures.

4. **Vuong-LN preference in Phase 2 / 10 / 13 rationalized rather than confronted.** Stumpf-Porter 2012 in own bibliography but not applied to own results. Fix by reframing those three phases as "PL-LN coexistence consistent with multiplicative-growth equivalence (Mitzenmacher 2004)" rather than as PL confirmations.

5. **AR(1) $p = 10^{-186}$ in Phase Scheffer is numerical / serial-correlation artifact.** Daily DO data has lag-1 autocorrelation 0.8-0.9; Kendall-$\tau$ variance is severely underestimated under that serial dependence. Fix with block-bootstrap / pre-whitening; expect $p \in [10^{-10}, 10^{-30}]$, still extraordinarily significant but defensible.

6. **$r_{\rm shape} = 1.11$ lacks a null distribution.** "Excellent because $r < 2$" borrows a within-system threshold. Fix with surrogate-null permutation test (10,000 fits on independently lognormal-matched seven systems, then row-centered ratio).

7. **B3 "multi-model ensemble" is single-vendor.** Decoding/temperature variants of one company's model are not architectural disagreement. Acknowledge in C1 (already done in §5.5) and in C4 (currently underweighted). Fix by reframing as "within-vendor consistency check" pending B4 cross-vendor.

8. **Phase 7 (power grid) catalog is curated from the literature anchors it's being compared to.** Verdict "confirmed" is too strong; "consistent with literature anchors" is the right framing. Fix in abstract + §3 Phase 7 verdict label.

9. **n=123 ($n_{\rm tail} = 40$) Vuong inconclusive used as evidence in either direction.** Honest reporting in §3 ("inconclusive, small-$n$"), but verdict label "CONFIRMED, lit-anchored" implies more positive evidence than the data carries. Fix verdict to "lit-band consistent, sample-size-limited."

---

## 8. If I were arXiv (PRE) referee

Three reviewer paragraphs I'd write:

> **R1 (positive).** The authors apply a single Clauset-grade analysis stack to thirteen independently fetched datasets across five candidate universality-class regions, including four explicit synthetic-null controls and two non-power-law class invariant tests (Preisach hysteresis, Scheffer fold bifurcation). The pipeline freeze at one commit hash with no per-domain tuning is methodological best practice and would be welcomed even as a standalone "Clauset-pipeline reproducibility study" in *PRE*. The paper's honesty about lognormal coexistence in Phases 2, 10, and 13 sets it apart from the standard universality-claim literature.

> **R2 (critical, methodology).** The central claim of "first quantitative confirmation of universality-class membership" rests on a row-centered cross-system log-PDF variance ratio $r_{\rm shape} = 1.11$ across seven systems, with the row-centering step explicitly absorbing the system-specific log-PDF mean (i.e., the unit prefactor). The authors acknowledge this in §4.4, but the headline framing then treats the residual cross-system variance as evidence for shared shape. Two specific concerns: (a) no surrogate-null distribution is computed for $r_{\rm shape}$, so the threshold "excellent because $r < 2$" is borrowed from within-system finite-size-scaling literature where the prediction is collapse onto a single curve, not residual after row-centering — the threshold does not transfer; (b) the BIC-on-binned vs Vuong-on-raw tension (§6.2) is honestly flagged but the resolution offered ("the V4 claim is strongest at the shape-collapse + BIC-on-binned level") unilaterally privileges the test that wins. I recommend (i) compute a surrogate-null distribution for $r_{\rm shape}$, (ii) downgrade the headline from "first quantitative confirmation" to "consistent with shared tail shape modulo prefactor," and (iii) explicitly report Phase 2 / 10 / 13 as "power-law / lognormal coexistence at currently available tail sizes" rather than as PL confirmations.

> **R3 (critical, sample / FWER).** Phase 7 (power grid) is curated as a 13th independent system but is in fact a literature-meta catalog assembled with knowledge of the Carreras 2016 and Hines 2009 anchors against which the Clauset fit is then compared. This is closer to a curating-against-itself consistency check than an independent measurement, and the verdict label "CONFIRMED" overstates the evidence. Familywise error rate is not controlled across the 30+ statistical tests reported (Vuong LR × 13 systems × 2 alternatives, BIC × 7 systems × 3 models, plus Kendall-$\tau$ on Scheffer). At nominal $\alpha = 0.05$ this likely exceeds FWER 0.5; a Bonferroni discussion is warranted. Bootstrap CIs are reported at $n_{\rm boot} = 100$ throughout, well below current best practice; please rerun at $n_{\rm boot} \geq 1000$. The Scheffer Kendall-$\tau$ $p = 10^{-186}$ on autocorrelated daily DO data appears to ignore serial correlation; a block-bootstrap is required.

**Expected outcome of this review:** major revision, no rejection. Most concerns are addressable with 1-2 weeks of additional compute and a clarifying rewrite of §4-§5.

---

## 9. Path to legitimacy — 12-month roadmap

In priority order (urgent first):

1. **Pre-register prediction bands for 5 new systems.** Before fitting them. Choose adversarial systems where prior literature exponents are uncertain (e.g., reaction-diffusion steady-state on chemical microreactor data, Hawkes contagion on Twitter cascade timestamps, second-order damped oscillator on macroeconomic NBER recession data). Publicly commit the bands. Then fit. Report success rate. **This is the single most credibility-buying action available.**

2. **Rerun all bootstraps at $n_{\rm boot} = 10000$.** Overnight compute. Removes one guaranteed reviewer comment.

3. **Surrogate-null permutation test for $r_{\rm shape}$.** Generate 10,000 synthetic 7-system datasets where each system is independently lognormal with empirical $\mu, \sigma^2$; row-center; compute ratio. Report empirical $r_{\rm shape} = 1.11$ percentile rank.

4. **Replace single-vendor B3 ensemble with cross-family B4** as soon as OpenRouter CN region issues resolve. Kimi K2.5 + GLM-5 + DeepSeek + Claude Opus + GPT-5 = real architectural ensemble. Until B4 is run, the "multi-model" framing in C1 §5.5 and C4 should be softened to "within-vendor consistency."

5. **Rerun Scheffer with block-bootstrap.** Fix the $p = 10^{-186}$ artifact. Will land at $p \in [10^{-10}, 10^{-30}]$, still highly significant, defensible to time-series reviewers.

6. **`xmin` sensitivity scans for small-$n$ / curved phases.** Phase 7, 4, 13, 11. Supplementary figures only.

7. **Independent re-implementation of the Clauset pipeline** by a second researcher or via a non-`powerlaw` package (e.g., Voitalov et al. 2019's `plfit` family). Cross-implementation reproducibility is a real differentiator.

8. **FOIA / DOE collaboration for raw OE-417 catalog.** Replaces Phase 7's literature-meta with a fresh independent measurement. 6-12 month timeline; worth doing for the v1 of the paper.

9. **PeMS multi-day archival Preisach loop measurement.** Closes the A2-Hysteresis loop-width-from-literature gap. 1-2 month timeline.

10. **Cross-site Scheffer replication** on 3-5 more USGS lake/river sites + EPA STORET. Closes single-site limitation.

11. **Submit C1 v0.3 (post all of 1-6 above) to *PRE* or *Chaos*.** Expect major revision; acceptance likely on second round.

12. **Submit C4 to *Patterns* or *NeurIPS-D&B* in parallel with C1.** This paper is independent and benefits from publication priority on the reject-aware methodology.

---

## 10. Final score (each /10)

| Dimension | Score | Note |
|---|---|---|
| **Methodology (pipeline rigor)** | **7.5/10** | Pipeline-freeze + null controls are excellent; bootstrap-$n=100$ + no FWER + Scheffer-$p=10^{-186}$ are clear weaknesses, all easily fixable. |
| **Empirical validation depth** | **6.5/10** | 13 systems is impressive coverage; Phase 7 (n=123 lit-meta) and Phase 13 (truncated catalog) are weaker than the count implies; 9/11 power-law confirmations is suspiciously high pending pre-registration. |
| **Writing** | **8.5/10** | Unusually candid, well-organized, calibrated voice; minor cuts and one headline downgrade away from publication-quality. |
| **Significance** | **7.5/10** | Genuinely novel cross-domain single-pipeline-with-frozen-commit + multi-model taxonomy critic + non-power-law A2 extensions; significance partly downgraded by single-author / no-replication / single-vendor-B3. |
| **arXiv readiness (C1 v0.2)** | **7/10** | Ready to post with: bootstrap rerun at 10k, §4.5 headline downgrade, Scheffer p-value fix, FWER paragraph, affiliation/email finalized. ~1 week of work. |
| **Overall** | **7.5/10** | **Solid B+ / A- preprint. Above the median single-author cross-domain SOC paper. Below the threshold where I'd recommend send-to-review-without-revision. Send to *PRE* expecting major revision, with realistic acceptance probability ~65% on second round.** |

---

## Appendix A: Specific line-level edits for C1 v0.2

Highest-impact edits:

- **Abstract (line 28).** "Under the finite-size-scaling ansatz... seven systems exhibit *shape-normalized* functional-form collapse at cross-system/within-system log-variance ratio $r_{\rm shape} = 1.11$ (well inside the 'excellent' threshold $r < 2$)." → "Under the finite-size-scaling ansatz... seven systems exhibit residual cross-system variance after row-centering at $r_{\rm shape} = 1.11$, consistent with shared tail shape modulo system-specific prefactors."
- **§4.5 (line 258, last paragraph).** "This is the first positive proof of universality class membership, not merely the absence of evidence against." → "This is the strongest positive evidence to date for shared functional form across cross-domain heavy-tail systems, while acknowledging that the row-centering step absorbs system-specific log-PDF means and that no surrogate-null distribution for $r_{\rm shape}$ is yet available."
- **§3 Phase 7 verdict (line 185).** "CONFIRMED (literature band), small-sample qualified" → "consistent with Carreras 2016 / Hines 2009 literature anchors; the $n=123$ catalog is curated against those same anchors and does not constitute an independent measurement; independent OE-417 acquisition (FOIA / DOE collaboration) is the natural next step."
- **§3 Phase 13 paragraph (line 201).** Soften "the point estimate matching $\alpha = 2$ to three decimal places is the operative evidence" to "the point estimate is consistent with the PA-Zipf canonical at $\alpha = 2$, with the Vuong-LN preference at $R = -6.31$ acknowledged as evidence for PA-LN coexistence at $n_{\rm tail} \sim 10^3$ per Mitzenmacher 2004."
- **§5.5 (line 298).** "To address the single-model bias of B1, we ran a B3 ensemble pass" → "To probe within-vendor consistency on the B1 verdicts, we ran a B3 within-vendor multi-decoding pass... A cross-family ensemble (Kimi, GLM-5, Claude Opus, GPT-5) is deferred to B4 pending OpenRouter region access."
- **§6.5 Limitations.** Add: "(ix) Multiple-testing correction is not applied to the 30+ statistical tests reported; under nominal $\alpha = 0.05$ per test, FWER may exceed 0.5. Bonferroni-adjusted threshold would shift Phase 6 / Phase 8 / Phase 11 inconclusive verdicts only marginally and would not alter any 'confirmed' or 'rejected' verdict."
- **§7 Conclusion.** "the most extensive single-pipeline empirical test... known to us, conservative in its claims, externally falsifiable, and demonstrably portable" → "the most extensive single-pipeline empirical test ... known to us. The claim is **demonstrably portable across class invariant families** (power-law and non-power-law); the claim of **first cross-domain universality-class confirmation** is qualified by the row-centering procedure underlying $r_{\rm shape}$ and by the within-vendor B3 ensemble."

---

## Appendix B: What this project is, framed honestly

Strip the universality-class rhetoric and the project is: **a working cross-domain empirical-analysis pipeline at one commit hash, applied honestly to 13 datasets, with a multi-model taxonomy critic that catches mechanism-vs-limit-theorem confusions.** That framing is publishable, novel, and would survive peer review.

The "first quantitative confirmation of universality class membership" framing is a stretch. Demote it. The reframed paper is still publishable and *more credible*.

**End of review.**
