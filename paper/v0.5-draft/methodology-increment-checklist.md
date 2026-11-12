# v0.5 Methodology Increment Checklist (Reviewer-Facing)

> Date: 2026-05-25 (SESSION-25)
> Companion to: `paper/v0.5-draft/v05-draft-skeleton.md`
> Purpose: map every methodology claim in §3.6 (and the empirical sections that depend on it) to the in-repo artefact that justifies it. This is the reviewer's traceability sheet — they should be able to verify every methodological claim by following the table entries to source files in the repository.

---

## How to use this checklist

For each methodology claim in §3.6 (and in §3.5.3 inherited from v0.4):

1. **Claim** — one-line statement of the methodological pattern.
2. **First empirical instance** — the universality class where the pattern was first surfaced.
3. **Secondary validation / generalisation evidence** — a second class where the pattern was either applied successfully or where its scope limits were demonstrated.
4. **Source artefacts** — in-repo paths to verdict.md, results.json, or other deterministic outputs.
5. **Scope claim** — explicit statement of where the pattern applies and where it does not.

The matrix below covers the four v0.4 methodology contributions (preserved in v0.5) plus the three v0.5 increments.

---

## §3.5.3 Cross-domain scatter threshold (v0.4, descriptor binary screen)

**Claim.** A candidate class is empirically a descriptor (not a mechanism) when its class-defining invariant satisfies *max/min(median θ across domains) > 10× AND ≥ 2 dynamical regimes are spanned*.

**First instance.** `second_order_damped_oscillator` (W2B.6): ζ-spread 2,395× across 3 regimes (underdamped / critically damped / overdamped).

**Secondary validation.** Applied independently in 5 further v0.4 REJECT-CONFIRMED cases: `extreme_value_tail` (ξ-spread 1.996, 3 Fisher–Tippett–Gnedenko domains of attraction); `tail_copula_contagion` (ΔAIC 999–3,224 vs SOC mechanism); `delay_differential_debt` (T_period CV 1.184); `fractional_brownian_crossings` (H-spread 0.361); `markov_memory_fidelity` (τ_mix log10 spread 2.98 decades). 6 of 6 REJECT-CONFIRMED classes satisfy the screen.

**Source artefacts.**
- `v4/validation/second-order-damped-oscillator/verdict.md`
- `v4/validation/extreme-value-tail-class/verdict.md`
- `v4/validation/tail-copula-contagion/verdict.md`
- `v4/validation/delay-differential-debt/verdict.md`
- `v4/validation/fractional-brownian-crossings/verdict.md`
- `v4/validation/markov-memory-fidelity/verdict.md`
- `docs/sessions/C1-unified-preprint-draft-v0.4.md` §3.5.3 (table)

**Scope claim.** Confirmatory binary screen, not single-statistic verdict. 10×/2-regime numbers are pragmatic, not first-principles. Future batches may need a Halford-1992-style mechanism audit to break ties on classes that sit close to the screen boundary.

---

## §3.5 (v0.4) 3-tier dichotomy battery (active / sham / cross-arm)

**Claim.** Reflexive / measurement-feedback classes require three arms: within-active, within-sham (critical falsifier), and cross-arm comparison.

**First instance.** `reflexive_fixed_point_class` (W2A.4): α = 2.97, ĉ = 0.65, sham null p = 0.94.

**Secondary validation.** Applied to `schelling_credible_commitment` v0.4 (sham null `|b_sham| ≈ 0` holds across all sub-runs); pattern partially generalised to `adverse_selection_unraveling` (no-signal arm as the sham null).

**Source artefacts.**
- `v4/validation/reflexive-fixed-point-class/verdict.md`
- `v4/validation/schelling-credible-commitment/verdict.md`
- `v4/validation/adverse-selection-unraveling/verdict.md`

**Scope claim.** Applies to classes where the *active* dose-response could be confounded by selection / inference effects; the sham arm uses a "cheap-talk" / null-treatment substitute to isolate the mechanism from the descriptor.

---

## §3.5 (v0.4) OZ Lorentzian over exp fit (spatial autocorrelation)

**Claim.** For spatial autocorrelation in steady-state reaction-diffusion / critical systems, the Ornstein-Zernike Lorentzian form `C(r) ∝ K_0(r/λ)` beats the exponential form `C(r) ∝ e^(−r/λ)` by R² gain 2–5× while recovering the same λ.

**First instance.** `reaction_diffusion_steady_state` (W2A.5): 3 spatial domains (Rietkerk 2008 ecology Turing system, FitzHugh-Nagumo neural-style, MODIS UHI urban-heat-island). λ = 5.54 ± 1.24 km in band [1.5, 8.0]. OZ R² beats exp R² by 2–5× on every domain.

**Secondary validation.** None in v0.4 batch (no other v0.4 class had a spatial autocorrelation measurement). Cross-class transferability is asserted on theoretical grounds: OZ Lorentzian is the canonical critical-point spatial correlator [Ornstein-Zernike 1914, Domb 1996], whereas the exponential form is a coarse short-range approximation.

**Source artefacts.**
- `v4/validation/reaction-diffusion-steady-state/verdict.md`
- `v4/validation/reaction-diffusion-steady-state/results.json`

**Scope claim.** Methodological gift, not a class-defining contribution. Transferable to any spatial-correlation work near criticality (climate, neuroscience, urban form).

---

## §3.5 (v0.4) 6-signature gate (first-order vs Preisach vs saddle-node)

**Claim.** Discriminating discontinuous-jump dynamics from Preisach hysteresis and from saddle-node fold bifurcations requires six independent signatures: S1 jump strength / S2 inner-loop R² / S3 Arrhenius lifetime / S4 pre-jump critical slowing down / S5 Clauset α + LR / S6 BIC bimodality.

**First instance.** `hysteresis_first_order_transition` (W2B.4): 116 empirical transitions (12 NBER recessions + 104 WTI regime flips) + synthetic Preisach + synthetic Scheffer fold. Inner-loop R² = 0.005 vs Preisach 1.000, jump magnitude ΔL = 2.73, 0/8 NBER recessions showing pre-jump CSD.

**Secondary validation.** The 2-way SPLIT decision (hysteresis_first_order vs hysteresis_preisach AND vs scheffer_fold) rests on the 6-signature gate's discriminating power. Applied independently to `preisach_hysteresis_cascade` (W2C.4) where τ_s = 1.490 cleanly differentiates from non-coupled Preisach (α ≈ 3.0).

**Source artefacts.**
- `v4/validation/hysteresis-first-order-transition/verdict.md`
- `v4/validation/preisach-hysteresis-cascade/verdict.md`

**Scope claim.** Targeted gate for the discontinuous-vs-smooth-bifurcation taxonomy boundary; not a generic methodology for all bistable-classification problems.

---

## §3.6.5 (s\*, k) threshold-tobit reparametrisation [v0.5 NEW]

**Claim.** Logit binary-outcome pre-registrations with slope band + 2+ point-rate constraints can produce mutually inconsistent bounds (logit slope implied by point rates outside the pre-registered slope band). Fix: switch to probit, reparametrise to (s\* = midpoint, k = standardised slope), pre-register independent bounds on each, derive point-rate diagnostics from the fitted box.

**First instance.** `schelling_credible_commitment` v0.5 (`schelling-credible-commitment/verdict_v5.md`):
- v0.4 logit pre-reg: b ∈ [1.2, 2.6], p(s>0.4) > 0.75, p(s<0.2) < 0.35 → mutually inconsistent (point rates require b > 8.59).
- v0.5 probit pre-reg: s\* ∈ [0.20, 0.35], k ∈ [4, 12] independently → sub-run C with anchor-calibrated generator (a=−3, b=12, noise=0.15) delivers s\* = 0.251 ✓, k = 6.529 ✓, p(0.4) = 0.834 ✓, p(0.2) = 0.369 ✓, sham null |k_sham| < 0.05 ✓.

**Secondary validation (cross-class scope test — N/A for all 3).** Three candidate binary-outcome classes audited explicitly per `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`:

| Class | Fit method | Why (s\*, k) doesn't help |
|---|---|---|
| `hysteresis_first_order_transition` | `linregress` + 6-signature gate | Multi-axis already decoupled |
| `adverse_selection_unraveling` | Exponential half-life on q(t) | Single τ + asymptote, no over-spec |
| `gardner_collins_toggle_switch` | Hill function `x^n / (K^n + x^n)` | Hill (n, K) ≡ canonical (s\*, k) — already decoupled |

The Hill-function case is the most informative: Hill K ↔ s\*, Hill n ↔ k. The threshold-tobit reparametrisation re-derives a parametrisation that biological dose-response fitters have used canonically for a century. The cross-class audit *confirms* the scope limit: (s\*, k) is a targeted remediation for a specific failure mode, not a generic upgrade.

**Source artefacts.**
- `v4/validation/schelling-credible-commitment/verdict_v5.md`
- `v4/validation/schelling-credible-commitment/run_validation_v5.py`
- `v4/validation/schelling-credible-commitment/results_v5.json`
- `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md`

**Scope claim.** Targeted remediation for one specific over-specification failure mode: (i) binary outcome with logit / S-curve on single predictor, (ii) pre-reg pins slope AND 2+ point follow-through rates on the same predictor, (iii) point-rate constraints imply slope outside pre-registered slope band. Classes using Hill / linregress / exp-decay / multi-axis gate are *not* candidates for the reparametrisation; they are already decoupled. The generalisable lesson is *not* "always use threshold-tobit" but *"every pre-registration with 2+ constraints on the same fitted family should be audited for mutual consistency before the run, not after"*.

---

## §3.6.6 Multilayer test pattern [v0.5 NEW]

**Claim.** Candidate universality classes whose theory predicts *different* scaling forms at *different* scales (intra-individual vs inter-individual; per-particle vs per-population; per-event vs per-waiting-time) require layered pre-registration. Each layer's verdict is computed against its own functional form; PASS-CONFIRMED-MULTILAYER requires all layers' constraints to hold; partial = SPLIT; no layer = REJECT-MULTILAYER.

**First instance.** `aggregation_kinetics` (v0.5, `v4/validation/aggregation-kinetics/verdict.md`):
- Layer 1 (per-aggregate Smoluchowski PL): α ∈ {1.70, 2.10, 2.05} across 3 distinct biological domains (Cruz 1997 human cortex / Hartig 2018 mouse cortex / Iwata 2000 + Brú 2003 oncology). All 3 in band [1.7, 3.5].
- Layer 2 (cross-population multiplicative-stochastic lognormal): 4 of 5 Allen Brain TBI Aβ series with Vuong R < 0 vs PL at p < 0.05 (Hyman 2008 multiplicative-growth theory).
- Combined verdict: PASS-STRONG-MULTILAYER.

**Secondary validation (transitive evidence from v0.4 single-layer test failure).** The v0.4 `beta_amyloid_aggregation` INCONCLUSIVE single-layer test (4/5 series lognormal-preferred → INCONCLUSIVE under "candidate class predicts power-law cross-section") was the *wrong test*: Hyman 2008 predicts cross-section lognormal as expected signature of multiplicative-stochastic patient-level growth. The single-layer test recovered a real signal but tested the wrong prediction; the multilayer test recovers the predicted signature at each scale.

**Cross-class candidates (NOT v0.5 empirical claims; v0.6+ candidates).**

| Class | Layer 1 (intra-scale) | Layer 2 (inter-scale) | Source-paper anchors |
|---|---|---|---|
| Allometric scaling (Kleiber) | $M^{3/4}$ intra-species | Log-mass × log-rate slope cross-species | Kleiber 1932; West-Brown-Enquist 1997; Glazier 2005 |
| Network growth (preferential attachment) | Per-node degree PL | Cross-network giant-component size distribution | Barabási-Albert 1999; Newman 2003; Faloutsos 1999 |
| Cascading failures (per-event + waiting-time) | Per-event magnitude SOC PL | Cross-event waiting-time (Omori or Hawkes branching) | Bak 1996; Sornette 2003; Carreras 2016 |
| Earthquake productivity | Per-mainshock aftershock-count PL | Cross-mainshock magnitude-productivity correlation | Felzer-Brodsky 2006; Helmstetter 2003 |

Each is a *pre-registered candidate* for v0.6 testing under the multilayer pattern. No v0.5 empirical work on these.

**Source artefacts.**
- `v4/validation/aggregation-kinetics/verdict.md` (PASS-STRONG-MULTILAYER, 3 domains)
- `v4/validation/aggregation-kinetics/results.json` (Layer 1 + Layer 2 numbers)
- `v4/validation/aggregation-kinetics/run_validation.py` (deterministic driver)
- `data/kb-additions-2026-05-25-aggregation-kinetics.jsonl` (8 KB entries)
- `docs/sessions/v04-aggregation-kinetics-report.md` (narrative)

**Scope claim.** General-purpose test pattern for any candidate class where the underlying theory predicts scale-dependent scaling forms. Does *not* solve the descriptor-vs-mechanism problem (§3.5.3 cross-domain scatter threshold remains the Layer 0 screen). Expected to apply broadly across cross-domain mechanism families with hierarchical structure.

---

## §3.6.7 Head-vs-tail-aware LLM validator [v0.5 NEW, ENGINEERING NOT METHODOLOGY]

**Claim.** LLM rewrite tasks that must preserve a fixed head + replace a tail should run forbidden-substring checks ONLY on the LLM-generated tail (`new_only = new_full[len(head):]`), not on the whole output. A naïve whole-output check false-rejects outputs whose forbidden substring legitimately appears in the head.

**First instance.** `scripts/rewrite_wave3c_boilerplate.py` (SESSION-24): 117 Wave 3 C KB entries shared a 7-template boilerplate suffix; rewrite ran 117/117 entries through OpenRouter (Kimi K2.5, ~$0.05 total, 18 s wall-clock) with 0 false-rejects.

**Secondary validation / follow-up.** The slicer is incomplete for head-internal collision: 23 public-health entries shared a 30-character connector phrase ("该干预的成本效益(QALY/DALY)评估是政策决策核心") *inside their heads*. The follow-up fix `scripts/strip_wave3c_head_collisions.py` is a deterministic strip (no LLM cost) that removes exactly that 30-character substring from the affected 23 entries. The slicer + strip combination removed both pollution sources without false-rejecting any entries.

**Source artefacts.**
- `scripts/rewrite_wave3c_boilerplate.py`
- `scripts/strip_wave3c_head_collisions.py`
- KB master file (5341 entries post v0.5 merge): `data/kb-5000-merged.jsonl`

**Scope claim.** **Engineering pattern, not scientific methodology.** Documented for reproducibility of the v0.5 KB cleanup (which downstream affects Layer 1 community discovery via embedding similarity). Reusable in any LLM-driven text-rewrite task with a fixed-prefix structure. Should *not* be weighted alongside §3.6.5 / §3.6.6 as a scientific methodology contribution.

---

## Cross-cutting reviewer notes

**Note 1 — methodology stratification.** v0.5 explicitly stratifies its methodology contributions into three tiers: (a) targeted remediation patterns with explicit scope limits (§3.6.5); (b) general test patterns expected to transfer broadly (§3.6.6); (c) engineering patterns documented for reproducibility (§3.6.7). Reviewers should evaluate each tier with the appropriate weight: (a) is a fix for a specific failure mode; (b) is a tool we expect to be used widely; (c) is provenance, not science.

**Note 2 — falsifiability.** The (s\*, k) reparametrisation could be wrong (i.e., its scope claim could fail). The cross-class applicability retrospective at `docs/methodology/2026-05-25-threshold-tobit-cross-class-applicability.md` *audits the failure mode* on three candidate classes and finds none of them apply. If a future class is found where (i)–(iii) of the scope hold and the reparametrisation does *not* help, the methodology is falsified. We invite that test.

The multilayer test pattern (§3.6.6) is falsifiable by finding a class where the theory predicts scale-dependent scaling, the layered pre-registration is applied correctly, but the verdict fails to discriminate from a single-layer test. We have not yet run such a counter-example; v0.6+ candidates (§3.6.6 table) provide the testing ground.

**Note 3 — pre-existing patterns that v0.5 does not claim.** The (s\*, k) parametrisation itself is canonical (Hill function in biology dates to 1910; threshold-tobit in econometrics dates to the 1950s-1980s). What v0.5 claims is *not* the invention of (s\*, k) but the diagnostic use of it as a remediation pattern for a specific over-specification failure mode in pre-registration design. Similarly, multilayer testing is canonical in physics (one always tests multiple scales when the theory predicts multiple scales); what v0.5 claims is the *systematic application* of multilayer pre-registration to candidate universality classes with hierarchical structure.

**Note 4 — what's NOT in v0.5.** The following are explicitly out of scope:

- A new empirical claim on real WTO retaliation data for Schelling. (We have a synthetic anchor-calibrated PASS; real data is the path to PASS-STRONG-REAL.)
- A 4th cross-domain anchor for aggregation_kinetics. (3 biological is PASS-STRONG; 4th non-biological is the path to universal-across-matter.)
- A cross-evaluation Pythia α universality test. (LAMBADA-only; cross-eval is v0.6 candidate.)
- A joint global L_inf fit for Pythia (Hoffmann 2022 style). (Per-size only; joint fit is v0.6 candidate.)
- Cross-class application of the (s\*, k) reparametrisation to a 4th binary-outcome class. (None known to satisfy scope conditions (i)–(iii) at this time.)

**Note 5 — what should a reviewer flag if they disagree.** A reviewer who reads v0.5 §3.6.6 and disagrees that aggregation_kinetics deserves PASS-STRONG should focus on Caveats A (clinical-stage selection truncation), B (pre-Clauset literature anchors), or C (3-domain minimum). A reviewer who reads §3.6.5 and disagrees with the scope claim should attempt to find a 4th binary-outcome class that exhibits the over-specification failure mode and try the reparametrisation. A reviewer who reads §4 and disagrees with the cross-fit robustness reading should attempt a joint global L_inf fit and check whether the cross-size CV moves.

---

## Cross-reference index

| Methodology contribution | Section(s) in v0.5 skeleton | First instance verdict file | Cross-class status |
|---|---|---|---|
| Cross-domain scatter threshold | §3.5.3 (v0.4 inherited) | `second-order-damped-oscillator/verdict.md` | 6/6 v0.4 REJECT-CONFIRMED satisfy |
| 3-tier dichotomy battery | §3.5 (v0.4 inherited) | `reflexive-fixed-point-class/verdict.md` | Partial transfer to schelling + adverse-selection |
| OZ Lorentzian over exp | §3.5 (v0.4 inherited) | `reaction-diffusion-steady-state/verdict.md` | Asserted theoretical transferability |
| 6-signature gate | §3.5 (v0.4 inherited) | `hysteresis-first-order-transition/verdict.md` | Applied to preisach-hysteresis-cascade |
| **(s\*, k) threshold-tobit** | **§3.6.5 (v0.5 NEW)** | **`schelling-credible-commitment/verdict_v5.md`** | **3/3 cross-class candidates N/A — scope-limited** |
| **Multilayer test pattern** | **§3.6.6 (v0.5 NEW)** | **`aggregation-kinetics/verdict.md`** | **4 v0.6 candidates pre-registered** |
| **Head-aware LLM validator** | **§3.6.7 (v0.5 NEW, engineering)** | **`scripts/rewrite_wave3c_boilerplate.py`** | **Reusable in any LLM rewrite task with fixed prefix** |

End of methodology checklist.
