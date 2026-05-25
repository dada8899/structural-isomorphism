# Threshold-Tobit (s\*, k) Reparametrisation — Cross-Class Applicability Retrospective

> **Date.** 2026-05-25 (SESSION-24)
> **Trigger.** SESSION-24 task (g): apply the schelling v0.5 (s\*, k) reparametrisation to other binary-outcome universality classes (hysteresis_first_order / adverse_selection_unraveling / gardner_collins_toggle).
> **Verdict.** **N/A — 3 of 3 candidates already use direct, identifiable parametrisations.** The (s\*, k) reparam is specific to the over-spec failure mode where a logit pre-reg pins both slope AND point-rates with mutually-inconsistent bounds. None of the 3 candidates exhibit this pattern.

## Why we considered this task

Schelling v0.5 (commit `71edaf4`) replaced the v0.4 logit pre-reg with a probit / threshold-tobit reparametrisation into (s\*, k):

- `s* = -α/β` (midpoint of the dose-response curve)
- `k  = β` (probit standardised slope)

This decoupled the v0.4 over-spec — three constraints (slope band + 2 point-rates) that were mutually inconsistent for any smooth logit. The reparam succeeded because (s\*, k) are jointly identifiable and have direct empirical meaning.

The methodology question: do other binary-outcome universality-class validations have the same over-spec pattern, and can (s\*, k) help?

## 3 candidates audited

### Candidate 1 — `hysteresis_first_order_transition`

**Fit method.** `scipy.stats.linregress` on log-survival curve `S(r)` (decimated returns) — power-law tail exponent extraction.

**Pre-reg structure.** Survival-function power-law exponent τ + Arrhenius lifetime + inner-loop R² + jump magnitude + Clauset α + BIC bimodality (6-signature gate, commit `009782f`).

**Why (s\*, k) doesn't apply.** No logit; no binary outcome with point-rate pre-reg; no slope-vs-rate conflation. The 6-signature gate is *already* a decoupled, multi-axis check (each signature is its own identifiable quantity).

**Verdict:** **already-decoupled-pre-reg.** No reparam needed.

### Candidate 2 — `adverse_selection_unraveling`

**Fit method.** Exponential half-life fit on quality-trajectory `q(t)` — `q_t = q_∞ + (q_0 - q_∞) · exp(-t/τ)`.

**Pre-reg structure.** Spence-signal `q_floor` lift + ratio `α/β ∈ [1.15, 2.40]` + sham null (no-signal arm). The pre-reg is a single ratio constraint plus a lift threshold — no point-rate constraints, no slope-band conflation.

**Why (s\*, k) doesn't apply.** Fit method is exponential decay (a single τ + asymptote q_∞), not a logit on a binary outcome. The exponential fit's parameters (τ, q_∞) are already direct, identifiable quantities. Pre-reg is on a derived ratio α/β, not on the fit parameters individually — there's no slope-vs-point conflict.

**Verdict:** **already-decoupled-pre-reg.** No reparam needed.

### Candidate 3 — `gardner_collins_toggle_switch` (v1 + v2)

**Fit method.** Hill function `p = x^n / (K^n + x^n)` fit on dose-response (cells vs inducer concentration) — `fit_hill_from_cells()`. Plus GMM 2-component for bistability check.

**Pre-reg structure.** Hill coefficient `n ∈ [2.5, 4.5]` + Hill K `∈ [0.5, 1.5]` + dwell time + dip ratio + bimodality criterion.

**Why (s\*, k) doesn't apply — *and this is the most interesting case*.** The Hill function IS structurally the (s\*, k) parametrisation:
- Hill `K` ≡ schelling `s*` (the inducer concentration where p = 0.5)
- Hill `n` ≡ schelling `k` (the steepness of the transition)

The Hill function is *the* canonical (midpoint, steepness) parametrisation for biological dose-response. The schelling v0.5 reparam essentially re-derived the Hill form for a probit kernel. Gardner-Collins already uses it natively — the v0.4 pre-reg is internally consistent because (n, K) are jointly identifiable and the pre-reg places independent bounds on each.

**Verdict:** **already-decoupled-pre-reg (canonical Hill).** No reparam needed.

## Conclusion

| Class | Fit method | Pre-reg structure | Over-spec risk | (s\*, k) helps? |
|---|---|---|---|---|
| `hysteresis_first_order_transition` | `linregress` on log-survival | 6-signature multi-axis gate | None (multi-axis already) | No |
| `adverse_selection_unraveling` | Exponential half-life on q(t) | Derived ratio α/β + lift | None | No |
| `gardner_collins_toggle_switch` | Hill function `x^n/(K^n+x^n)` | Hill (n, K) independent bounds | None (canonical Hill = canonical (s*, k)) | No |
| `schelling_credible_commitment` | Logit + 2 point-rate constraints | Slope + 2 points (mutually inconsistent) | **High** | **Yes — fixed in v0.5** |

The (s\*, k) reparam is a **targeted fix for the specific over-spec pattern** of pre-registering both a logit slope band AND two point-rate constraints that together imply a stricter slope band than the original. It is NOT a generic improvement applicable across all classes.

## Methodology note for the v0.4 paper

When the v0.4 §3 lists methodology contributions:
1. Cross-domain scatter threshold (descriptor binary screen)
2. 3-tier dichotomy battery (active / sham / cross-arm)
3. OZ Lorentzian over exp fit (spatial autocorrelation)
4. 6-signature gate (first-order vs Preisach vs saddle-node)
5. **Threshold-tobit (s\*, k) reparametrisation** — *applies specifically to logit binary-outcome classes with point-rate pre-reg; check the pre-reg constraints for mutual consistency BEFORE pre-registering, not after*

The last bullet should explicitly note the **scope limit** — it's a remediation pattern for an over-spec failure mode, not a universal upgrade. Classes that use Hill / linregress / exp-decay / multi-axis gate parametrisations should not be re-parametrised.

## When (s\*, k) IS the right tool

Use this reparam when ALL of the following hold:
1. The class fits a binary outcome with a logit (or equivalent S-curve) on a single predictor.
2. The pre-reg pins the slope AND two or more point follow-through rates on the same predictor.
3. The point-rate constraints imply a slope inconsistent with the pre-registered slope band.

Then the fix is: switch to probit, reparametrise to (s\*, k), pre-register independent bounds on each, and derive the point-rate diagnostics from the (s\*, k) box rather than pre-registering them independently.

## Related artifacts

- Schelling v0.5 verdict (closes SESSION-23 outstanding #11): `v4/validation/schelling-credible-commitment/verdict_v5.md` (commit `71edaf4` + `39226c1` + `8183a45`)
- Schelling v0.5 session report: `docs/sessions/v04-schelling-credible-commitment-v5-report.md`
- SESSION-24 (g) task brief: SESSION-23 handoff §10 candidate (g)

End of retrospective. Closes SESSION-24 (g).
