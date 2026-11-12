# Pre-Registration of Methodology Increment §3.6.5 — (s*, k) Threshold-Tobit Reparametrisation as Targeted Remediation for Over-Specified Logit Binary-Outcome Pre-Registrations

> Date: **2026-05-25** (SESSION-25)
> Status: pre-registered *as a methodological pattern*, not as a single class prediction
> Companion: `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.5; `paper/anti-phacking-unified-2026-05-15.md` §1.2
> Author: dada8899
> Repo state at pre-registration: HEAD `71a5617`

## 1. What is being pre-registered

This document pre-registers a **methodology pattern**, not an empirical band on a single
universality class. The pattern, formalised in v0.5 skeleton §3.6.5, is:

> *When a logit binary-outcome universality-class pre-registration pins both a slope
> band AND two-or-more point follow-through rate constraints on the same fitted curve,
> and the point-rate constraints algebraically imply a slope outside the pre-registered
> slope band, the correct remediation is to switch to a probit / threshold-tobit form,
> reparametrise to (s\*, k) = (midpoint, standardised slope), pre-register independent
> bounds on each, and demote the point-rate constraints to **derived diagnostics** of
> the fitted (s\*, k) box.*

Pre-registering the pattern (rather than a class outcome) is what the anti-p-hacking
companion paper §1.2 calls a *second-order* pre-registration: the unit of credibility
is whether the pattern, applied mechanically when its scope conditions are met,
delivers a feasible pre-registration without re-introducing the over-specification
failure on the next class it is applied to.

## 2. Hypothesis

**H1.** For any binary-outcome class satisfying scope conditions (i)–(iii) below, the
(s\*, k) reparametrisation produces a *feasible* pre-registration — i.e., the set of
parameter pairs `(s*, k)` satisfying the pre-registered bounds is non-empty and the
derived point-rate constraints `p(s) = Φ((β·s − τ)/σ)` evaluated on this set fall
inside what the analyst would have written as the original point-rate targets.

**H2.** A class satisfying scope conditions (i)–(iii) that has previously returned
INCONCLUSIVE-pre-reg-overspec under a logit pre-reg can be re-validated under the
(s\*, k) pre-reg and reach a *substantive* (PASS / FAIL / PARTIAL) verdict driven by
the empirical data, not by the internal inconsistency of the original constraints.

## 3. Scope — where the pattern applies, and where it explicitly does NOT

### 3.1 Scope conditions (must hold conjointly)

(i) The class fits a binary outcome through a logit (or equivalent monotone S-curve)
on a *single* continuous predictor.

(ii) The pre-registration pins the slope band AND two-or-more point follow-through
rates on the same predictor.

(iii) The point-rate constraints algebraically imply a logit slope inconsistent with
the pre-registered slope band — i.e., the pre-registered region of parameter space is
*empty*.

### 3.2 Explicit non-applicability list (audited cases, 2026-05-25)

The audit at `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`
verified non-applicability against three v0.4-era candidates:

| Class | Fit method | Pre-reg structure | (s\*, k) helps? |
|---|---|---|---|
| `hysteresis_first_order_transition` | `linregress` on log-survival; 6-signature gate | Each signature its own identifiable quantity | **No (multi-axis already decoupled)** |
| `adverse_selection_unraveling` | Exponential half-life $q(t) = q_\infty + (q_0 - q_\infty) e^{-t/\tau}$ | Derived ratio α/β + lift | **No (no S-curve, no point-rate conflict)** |
| `gardner_collins_toggle_switch` | Hill function $p = x^n / (K^n + x^n)$ + GMM bistability | Hill (n, K) independent bounds | **No (canonical Hill ≡ canonical (s\*, k); already decoupled)** |

### 3.3 What the pattern is NOT being claimed to cover

- **Non-binary outcomes.** Continuous-response classes (power-law tail fits, Omori-Utsu
  decays, scaling-law fits) are out of scope.
- **Multi-stage / sequential games.** Reflexive or feedback-coupled classes where the
  binary outcome itself depends on the realised dose-response (§3.5 v0.4 3-tier
  battery's domain) require their own pre-registration discipline; (s\*, k) does not
  substitute for the sham-arm null.
- **4-anchor reachability.** The empirical demonstration on schelling sub-run C reaches
  2 of 4 pre-registered anchor outcomes (WTO + dual-class) under the ±0.20 tolerance;
  M&A and sovereign-default anchors are structurally unreachable in the present
  synthetic family (intercept-mixture / high-`s` saturation limits). We do **not**
  claim (s\*, k) makes 4-anchor reproduction reachable in general.
- **The invention of (s\*, k).** The (midpoint, steepness) parametrisation is canonical
  (Hill 1910 in biology; threshold-tobit in econometrics from the 1950s-1980s). The
  v0.5 claim is the **diagnostic use** of the reparametrisation as a remediation
  pattern for the specific over-specification failure mode above, not novelty of the
  parametrisation itself.

## 4. Pre-specified data and procedure

### 4.1 First instance (already executed at HEAD `71a5617`)

`schelling_credible_commitment` v0.4 → v0.5 transition. The v0.4 logit pre-reg with
`b ∈ [1.2, 2.6]`, `p(s>0.4) > 0.75`, `p(s<0.2) < 0.35` is documented to be
mutually inconsistent (point rates require `b > 8.59`). The v0.5 probit pre-reg with
`s* ∈ [0.20, 0.35]` and `k ∈ [4, 12]` independently, anchor-implied from Bown 2009
WTO retaliation cases, returns sub-run C of the anchor-calibrated generator
(a = −3, b = 12, noise = 0.15): `s* = 0.251`, `k = 6.529`, derived `p(0.4) = 0.834`,
derived `p(0.2) = 0.369`, sham null `|k_sham| < 0.05`. Full details at
`v4/validation/schelling-credible-commitment/verdict_v5.md`.

### 4.2 Cross-class non-applicability audit (already executed)

Three classes verified N/A per §3.2 above; retrospective at
`docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`.

### 4.3 Future candidate slot

A 4th binary-outcome class satisfying scope conditions (i)–(iii) is *not currently
known*. If one is identified after the present pre-registration date, it becomes the
secondary validation candidate for H1/H2 above. The pre-registration commitment is
that any such future class will be reported under the present document's discipline:
the (s\*, k) reparam will be applied, the result will be published *whatever the
verdict*, and a negative result (reparam still gives infeasible constraints, or
empirically fails to reach a substantive verdict) will be reported as a falsification
of the pattern (see §5 falsifier).

## 5. Verdict ladder (for the pattern, not the class)

| Outcome | Criterion |
|---|---|
| **PASS — pattern works** | (a) the original logit pre-registration is documented to be mathematically infeasible AND (b) the probit (s\*, k) reparam yields a non-empty feasible region AND (c) at least one anchor-calibrated or empirical sub-run achieves PASS on the (s\*, k) box AND (d) the sham-null arm rejects `|k_sham|` orders of magnitude below the in-band threshold. |
| **FAIL — pattern broken** | A class satisfying scope conditions (i)–(iii) is found where the (s\*, k) reparametrisation still produces a mutually-inconsistent pre-registration (i.e., the implied (s\*, k) feasible region under the analyst's empirical anchors is empty), or where the reparam region is non-empty but no sub-run reaches PASS *for reasons traceable to the reparametrisation* rather than to data quality. |
| **INCONCLUSIVE** | A candidate class is found that satisfies (i)–(ii) but the analyst is uncertain whether (iii) holds (no analytic feasibility audit was performed); pattern is neither demonstrated nor falsified on the candidate. |

Schelling delivers PASS under this ladder at HEAD `71a5617`.

## 6. Falsifiability criterion

The pattern is falsified by exhibiting a **future** class for which:
- scope conditions (i)–(iii) all hold (logit + slope band + 2-or-more point rates +
  mutual inconsistency under the original);
- the (s\*, k) reparametrisation is applied mechanically per §3.6.5;
- the resulting probit pre-registration is *also* mutually inconsistent under the
  anchor-implied (s\*, k) bounds (i.e., the empirical anchors are too tight for any
  smooth probit, not just any smooth logit).

A single such case shifts the pattern from "targeted remediation that works in its
declared scope" to "remediation that resolves logit-form over-specification but does
not resolve the underlying tightness of the empirical anchor set". We commit in advance
to reporting any such case as a falsification, not as a class-specific failure.

## 7. What is explicitly NOT being claimed

- **Universal applicability across binary-outcome classes.** §3.2 above
  documents three classes where the reparametrisation provides no benefit because the
  fitter is already decoupled. The pattern is *not* a generic upgrade.
- **That (s\*, k) is the right form for non-binary outcomes.** Continuous-response
  scaling-law classes (Pythia §4 of v0.5, aggregation_kinetics Layer 1 §3.6.6) use
  power-law or lognormal fits whose own parametrisations are already identifiable;
  (s\*, k) does not transfer.
- **That 4-anchor reproduction is always reachable.** Schelling sub-run C hits 2/4
  anchor outcomes; M&A and sovereign-default are structurally unreachable in the
  present synthetic family. Reaching 4/4 would require a different generator, not a
  different reparametrisation.
- **Authorship of (s\*, k).** Hill 1910 and the econometric threshold-tobit literature
  predate this work by decades-to-a-century.
- **Falsification of the underlying mechanism.** The v0.4 INCONCLUSIVE verdict on
  schelling was forced by pre-registration internal inconsistency, not by an empirical
  failure of the credible-commitment mechanism, which separately passes the sham null
  at `|b_sham| ≈ 0`.

## 8. Resource budget

- **Compute.** Per sub-run on schelling, ~10 s wall clock on Mac mini M4; aggregate v0.5
  schelling re-validation ≤ 5 minutes.
- **LLM cost.** $0 for the pattern itself; cross-class applicability audit consumed
  ≈ 200 K tokens of in-context analysis ($\approx$ $1) on Opus.
- **Human-hours.** Schelling v0.4 → v0.5 transition + audit + this pre-registration
  document: ≈ 4 h cumulative across SESSION-23 to SESSION-25.
- **Future-class budget.** Any future scope-condition-(i–iii) candidate, if identified,
  is expected to consume ≤ 1 h of analyst time to apply the pattern and publish the
  result regardless of verdict.

## 9. Data and script provenance

| File | Purpose |
|---|---|
| `paper/v0.5-draft/v05-draft-skeleton.md` §3.6.5 | Methodology pattern, prose description |
| `paper/v0.5-draft/methodology-increment-checklist.md` §3.6.5 | Reviewer-facing traceability sheet |
| `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md` | 3-class non-applicability audit |
| `v4/validation/schelling-credible-commitment/verdict_v5.md` | First-instance PASS verdict |
| `v4/validation/schelling-credible-commitment/run_validation_v5.py` | Deterministic re-run driver |
| `v4/validation/schelling-credible-commitment/results_v5.json` | Numerical results |
| `paper/anti-phacking-unified-2026-05-15.md` §1.2 | Adversarial pre-registration framing |

End of pre-registration §3.6.5.
