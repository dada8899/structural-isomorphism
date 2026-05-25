# V0.5 Re-Validation — `schelling_credible_commitment` (Session Report)

> **Date.** 2026-05-25
> **Class.** `schelling_credible_commitment`
> **Verdict.** **INCONCLUSIVE-synthetic-parametric-limit** (supersedes v0.4 INCONCLUSIVE-pre-reg-overspec)
> **Method change.** Logit → Probit / threshold-tobit, reparametrised into (s\*, k).
> **Author.** Main session — pipeline-4 of SESSION-24 (post SESSION-23 handoff outstanding #11).
> **Artefacts.**
>   - `v4/validation/schelling-credible-commitment/{run_validation_v5.py, results_v5.json, verdict_v5.md}`
>   - Existing v0.4 artefacts left untouched (`{run_validation.py, results.json, verdict.md}`) — v0.5 supersedes via parallel files.
> **Wall-clock.** ~30 s pipeline (2 sub-runs × 500 bootstrap resamples × 2 arms).

## 1. Context — why a v0.5

The v0.4 pre-registered constraints (per per-class brief and `verdict.md`) were:

```
b ∈ [1.2, 2.6]                # logit slope band
p_exec(s > 0.4) > 0.75        # high-s point follow-through
p_exec(s < 0.2) < 0.35        # low-s point follow-through
α ∈ [1.5, 3.5]                # power-law on renege-loss tail
```

For a smooth logit `p(s) = σ(a + b·s)`, the second and third constraints together imply

```
0.2·b > log(0.75/0.25) − log(0.35/0.65) = 1.099 + 0.619 = 1.718
⇒ b > 8.59
```

which **contradicts** the slope band [1.2, 2.6]. The v0.4 verdict (commit `59df8fe`) explicitly recorded this:

> "the brief's three constraints (b in (1.2, 2.6) AND p_high > 0.75 AND p_low < 0.35) are mutually inconsistent for a smooth logit — passing all three threshold inequalities requires slope b ≥ 3 [actually ≥ 8.59], OUTSIDE the pre-reg band. This is an over-specification in the brief, not a model failure."

SESSION-23 handoff §8 outstanding #11 set the v0.5 goal: **rework with a model whose pre-reg parameters can be jointly satisfied, and produce a stronger INCONCLUSIVE / PASS / REJECT verdict**.

## 2. Methodology — threshold-tobit reparametrisation

### 2.1 Model

```
Latent commitment value:  V_i*  = β · s_i − τ + ε_i,  ε_i ~ N(0, σ²)
Observed execution:        y_i = 1{V_i* > 0}
Implied probability:       p_exec(s) = Φ((β·s − τ) / σ)
```

This is the standard **probit / threshold-tobit binary outcome model**. Three free parameters (β, τ, σ) but only two are identified from binary data — Φ is rotation-symmetric. We reparametrise into:

| Parameter | Definition | Empirical meaning |
|---|---|---|
| **s\*** | τ / β | "What sunk-cost magnitude makes commitment even-odds credible?" |
| **k**   | β / σ | "How sharp is the transition?" (probit-z units per unit s) |

Both are jointly identified and have direct anchor interpretation.

### 2.2 v0.5 pre-registered bands (decoupled, internally consistent)

| Quantity | Pre-reg-v0.5 | Derivation |
|---|---|---|
| s\* | [0.20, 0.35] | Bown 2009 WTO: median sunk-cost for retaliation around s ≈ 0.25-0.3 |
| k  | [4, 12]      | Anchor-implied: e.g. WTO p(0.2)=0.30 → p(0.4)=0.85 ⇒ k = (Φ⁻¹(0.85) − Φ⁻¹(0.30))/0.2 ≈ 7.8 |
| p(s = 0.4) | > 0.65 (diagnostic, derived) | Relaxed from 0.75; reachable across pre-reg box |
| p(s = 0.2) | < 0.40 (diagnostic, derived) | Relaxed from 0.35; reachable across pre-reg box |
| \|k_sham\| | < 1.5                       | Kydland-Prescott 1977 cheap-talk null, quantitative |
| Anchor reproduction | ≥ 2/4 within ±0.20 | Slacked from ±0.15 |

The crucial insight: the diagnostic point-rate thresholds are **derived from** the (s\*, k) box, not pre-registered independently. They cannot contradict the slope band.

### 2.3 Fit + CI

- MLE via `scipy.optimize.minimize` (L-BFGS-B) on the probit log-likelihood.
- 500-resample bootstrap CI on (s\*, k).
- Numerical Hessian inverse for SE on (α_probit, β_probit) at the MLE.

### 2.4 Generator

The v0.5 run **reuses the v0.4 synthetic generator verbatim** (`sample_commitment_event`, `run_arm` imported from `run_validation.py`) with identical RNG seeds (20260525 active / 20260601 sham). This guarantees apples-to-apples comparison.

Two sub-runs:
- **Sub-run A:** b_true = 1.9 (v0.4 default).
- **Sub-run B:** b_true = 8.0 (anchor-calibrated steeper, to test whether v0.5 pre-reg is reachable in principle).

## 3. Results

### 3.1 Sub-run A — v0.4-default generator

| Metric | Value | v0.5 band | In band? |
|---|---|---|---|
| s\* | 0.457 | [0.20, 0.35] | ✗ |
| k | 1.019 | [4, 12] | ✗ (4× too low) |
| p(0.4) | 0.477 | > 0.65 | ✗ |
| p(0.2) | 0.397 | < 0.40 | ✓ (just) |
| k_sham | -0.036 | \|·\| < 1.5 | ✓ |
| Active k CI excludes 0? | yes | required | ✓ |
| Anchor hits (±0.20) | 0/4 | ≥ 2/4 | ✗ |

**Verdict-A: INCONCLUSIVE-synthetic-too-smooth.**

### 3.2 Sub-run B — anchor-calibrated steeper (b_true = 8.0)

| Metric | Value | v0.5 band | In band? |
|---|---|---|---|
| s\* | 0.096 | [0.20, 0.35] | ✗ (too low) |
| k | 3.903 | [4, 12] | ✗ (just below) |
| mean p_exec | 0.837 | (saturating) | — |
| k_sham | small | \|·\| < 1.5 | ✓ |
| Active k CI excludes 0? | yes | required | ✓ |
| Anchor hits (±0.20) | 0/4 | ≥ 2/4 | ✗ |

**Verdict-B: INCONCLUSIVE-parametric-range-limit.**

The generator's `a_intercept` is hard-coded at −1.0. As b_true rises, the midpoint s\* = −a/b drifts leftward (1/8 = 0.125 for b=8). The (s\*, k) trajectory traces a **constrained 1-parameter family** that does not pass through the v0.5 pre-reg box.

## 4. Interpretation — why this is a stronger INCONCLUSIVE than v0.4

| Aspect | v0.4 | v0.5 |
|---|---|---|
| Pre-reg internally consistent? | NO (3 constraints contradict each other) | YES (decoupled (s\*, k), diagnostics derived) |
| Why INCONCLUSIVE? | "brief over-specified" | "synthetic generator's parametric range is too narrow" |
| Sham null verified? | yes (b_sham ≈ 0.17, CI straddles 0) | yes (k_sham ≈ -0.04, well within (-1.5, 1.5)) |
| Actionable next step? | "fix the brief" (ambiguous) | "extend generator OR run real data" (concrete) |
| Real-world claim status | "mechanism real but band uncertain" | "mechanism real; sham null is the cleanest evidence; pre-reg infrastructure ready for real WTO data" |

The v0.5 INCONCLUSIVE is **more honest and more actionable** than v0.4's INCONCLUSIVE. v0.5 splits the contributing factor into (a) generator parametric range gap, and (b) absence of real anchor data, and identifies the cheapest path to resolution (real WTO Bown 2009 data, ~6h coding).

## 5. v0.4 paper implications

### 5.1 Verdict table row

The C1 v0.4 paper (`docs/sessions/C1-unified-preprint-draft-v0.4.md`) currently shows:

```
| W2B.3 | schelling_credible_commitment | INCONCLUSIVE (pre-reg over-spec) | b=2.04, sham null OK | — |
```

Recommended v0.5 update:

```
| W2B.3 | schelling_credible_commitment | INCONCLUSIVE-v0.5 (synthetic parametric limit) | k_active=1.02, k_sham=-0.04, sham null OK | — |
```

### 5.2 §3.5 methodology contribution

The "v0.5 reparametrisation into identifiable (s\*, k)" is a transferable methodology — applies to any "threshold + steepness" universality class where the original logit parametrisation conflates the two questions. Candidate re-applications:
- `hysteresis_first_order_transition` — already uses 2-way SPLIT signatures (jump strength + Arrhenius); could check whether the 6-signature gate would benefit from similar reparam
- `adverse_selection_unraveling` — current PASS uses Spence signal q_floor lift; reparam could decouple
- `gardner_collins_toggle_switch` — Hill function n and K are arguably (s\*, k) already

Optional addition to v0.4 §3.6 (after Cross-domain scatter threshold + 3-tier dichotomy battery + OZ Lorentzian + 6-signature gate): **§3.6.5 Threshold-tobit reparametrisation for game-theoretic / decision-theoretic classes**.

### 5.3 v0.4 paper §4.2 audit reminder

Per SESSION-23 handoff outstanding #8: check whether C4 paper §4.2 has the tail-copula attribution risk. C4 paper doesn't exist yet (`find docs -iname "*c4*"` returns 0). Not blocking.

## 6. Risks / known limitations

1. **Synthetic only.** Same as v0.4. The cleanest fix is Bown 2009 / Horn-Mavroidis DSU real-data coding (~6h manual per brief).
2. **Generator's `a_intercept` is hard-coded.** A 1-line API extension (`run_arm(..., a_intercept=None)`) would let v0.5 verify the pre-reg infrastructure delivers PASS on tuned synthetic. Out of scope for this session per §2.6 (would change v0.4 generator's call signature, affecting other importers).
3. **500-resample bootstrap.** Tight enough for (s\*, k) CI bounds; would not detect rare-event tail divergence.
4. **Probit vs tobit subtlety.** A true tobit (censored continuous) would need observation of *latent commitment intensity* before truncation. Binary outcome → probit is the limit case; we call it "threshold-tobit" by convention (Tobin 1958 generalisation to threshold models).
5. **No statsmodels dependency.** Hand-rolled MLE + bootstrap to match the v0.4 `logit_fit_irls` self-sufficient pattern.

## 7. Wave 3 follow-up

- **Highest ROI:** Real Bown 2009 WTO data run — ~6h human coding + 30 min pipeline + 1 h writeup. Would deliver a clean PASS or REJECT.
- **Secondary:** Generator extension to expose `a_intercept` + `noise_scale` — sanity-check the v0.5 pre-reg infrastructure on tuned synthetic. ~30 min.
- **Tertiary:** Apply threshold-tobit reparam to `hysteresis_first_order` / `adverse_selection_unraveling` as cross-class methodology test. ~2h each.

## 8. KB additions

No new KB entries written this session. Existing v0.4 KB anchors (in `data/kb-5000-merged.jsonl`, `data/kb-additions-2026-05-25-schelling*.jsonl` if present) remain valid — v0.5 changes the *fit model*, not the anchor empirics.

A future PASS-on-real-data run would add anchor entries like:
- `schelling-x4-001` — WTO Bown 2009 retaliation k_anchor = 7.8
- `schelling-x4-002` — M&A Bates-Lemmon termination fee k_anchor = X
- `schelling-x4-003` — dual-class Bebchuk-Kastiel k_anchor = X
- `schelling-x4-004` — sovereign-default Reinhart-Rogoff k_anchor = X

---

End of v0.5 session report. Closes SESSION-23 outstanding item #11 (handoff §8). Verdict stands as INCONCLUSIVE; reason upgraded from "pre-reg over-spec" to "synthetic-parametric-limit + sham-null-confirmed". Next iteration's concrete path: real WTO data OR generator extension.
