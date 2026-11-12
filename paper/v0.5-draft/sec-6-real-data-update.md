# §6.6 Real-data WTO retaliation update (SESSION-25 sub-agent A2)

> **Date.** 2026-05-25/26
> **Companion to.** v0.5-draft-skeleton §6 (Schelling credible-commitment v0.5)
> **Status.** **REAL-DATA REJECT** of the monotone-increasing Schelling pre-registration on the Horn-Mavroidis WTO Dispute Settlement Dataset 1995-2006.
> **Files.**
> - Data: `v4/validation/schelling-credible-commitment/data/bown_wto_disputes.csv` (n = 23 disputes)
> - Code: `v4/validation/schelling-credible-commitment/run_validation_real_wto.py`
> - Results: `v4/validation/schelling-credible-commitment/results_real_wto.json`

## TL;DR

A drop-in v0.5 probit fit on **n = 23 real WTO retaliation cases** (Horn-Mavroidis 1995-2006 + WTO Official Case Summaries 2010 + per-dispute manual coding) returns a **negative slope** (`k = -2.92`, 95 % CI `[-7.92, -0.67]`) — the **opposite direction** of the Schelling pre-registration. Probability of defendant compliance within 24 months is **1.00 in the low-sunk-cost half** (n_low = 11, all 11 settled in compliance) and **0.58 in the high-sunk-cost half** (n_high = 12). Per-anchor projection lands **0/4** within ±0.20 on any anchor (including the WTO anchor that the pre-reg explicitly targeted).

This is a **falsification of the pre-reg's monotone-positive assumption on real WTO data**, not a refinement. The pre-reg's `(s_low → p ≈ 0.30, s_high → p ≈ 0.85)` coordinate is *reverse-signed* relative to what the Horn-Mavroidis sample yields.

The most parsimonious explanation is **endogenous selection of `s`**, not a structural anchor mis-fit. In Schelling's pre-commitment model, the complainant exogenously picks `s` (sunk cost) and the defendant's compliance is the outcome. In WTO data, observed escalation `s` is itself the **outcome of bargaining**: cases that travel all the way to Article 22.6 arbitration + authorisation + applied retaliation (high `s`) are precisely the cases where the defendant proved most willing to absorb retaliation rather than comply (Hormones, FSC, Cotton, Gambling). Cases settled at the arbitration-request stage (low `s`) are the ones where the defendant capitulated cheaply.

In other words, the assignment `s ↔ institutional escalation level` does not satisfy the **conditional independence** assumption baked into Schelling's exogenous-pre-commitment model. The 4-anchor pre-registration treats `s` as if it were experimentally manipulable; it is not, in the WTO setting.

## What this means for the (a)-vs-(b) hypothesis

The task asked: **is the 2/4 anchor gap (a) structural (mechanisms genuinely differ across the 4 anchor domains) or (b) framing (pre-reg coords misread from literature)?**

The real-data finding is closer to **(a) with a sharper twist than originally framed**:

- **NOT a "framing" issue in the simple sense.** The 4 anchor `(p_low, p_high)` coordinates from Bown 2009, Bates-Lemmon 2003, Bebchuk-Kastiel 2019, Reinhart-Rogoff 2009 are *theoretically calibrated to exogenous-`s` settings*. Bown 2009's `~30 % follow-through when s<0.1, ~85 % when s>0.4` reflects scenarios where the complainant's commitment varies *across* legally comparable case-sets, not within the censored sub-sample that reached arbitration.
- **A structural barrier larger than the v0.4/v0.5 pre-reg recognised**: the structural barrier is not just inter-anchor heterogeneity but **the difficulty of recovering a Schelling-style exogenous-`s` dose-response from any *observational* dataset where escalation is itself an outcome of bargaining**. The synthetic generator's `s` is exogenously prescribed; observational `s` is selected.
- **The Bown 2009 anchor `(0.30, 0.85)` is still consistent with the underlying mechanism**, but only when one conditions on cases sampled from the population where retaliation-level was *pre-determined* by domestic legal mandate (e.g., automatic safeguards triggered by trade-volume thresholds) rather than chosen ex post by the complainant. The Horn-Mavroidis sample does not provide this conditioning.

So the **PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT** verdict from sub-run D stands as the v0.5 final, but its caveat should be sharpened: **the v0.5 synthetic generator is a fair representation of Schelling's exogenous-`s` theory, but no presently-available observational dataset (including Horn-Mavroidis) cleanly identifies Schelling's exogenous-`s` predictions** — at least not without a credible instrument for retaliation-level assignment.

## Data and method

### Source

- **Horn-Mavroidis WTO Dispute Settlement Dataset**, World Bank Data Catalog, dataset ID 0037789, last updated 23 Apr 2019.
  Download URL: `https://datacatalogfiles.worldbank.org/ddh-published/0037789/1/DR0045701/horn_mavroidis_wtodataset110311.xlsx`
  1.38 MB Excel; 351 disputes 1995-2006 with event-level tracking through 2010; 7 sheets: Consultation, Panel, Panel(claims), AB, AB(claims), Implementation, Suspension of Concessions.
- **WTO Official Case Summaries** (2010 edition, 1.86 MB PDF) for compliance-outcome cross-reference.

### Sample selection

We extracted the **23 disputes whose `Suspension of Concessions / SuspconcessReq1Date` field is populated** — i.e., disputes that reached at least the retaliation-request stage. This is the only sub-sample where Schelling's commitment mechanism is actually tested (cases that never reach DSB retaliation-request stage either settled at panel stage or were dropped, and provide no variation in the relevant `s` regime).

### Coding scheme

`s ∈ [0, 1]` was assigned by escalation stage (5 categorical levels) modulated by a value multiplier:

| Stage | s_base | Description |
|---|---|---|
| arb_req_no_auth | 0.20 | Arbitration requested but never authorised; bilateral settle |
| arb_req_settled_in_arb | 0.25-0.30 | Arb requested then settled during arbitration |
| auth_granted_settled_in_arb | 0.40 | Authorisation issued, but arb suspended for settlement |
| auth_granted_no_retal | 0.45-0.50 | Authorisation, no actual retaliation applied |
| auth_granted_retal_applied | 0.55-0.85 | Authorisation + retaliation actually imposed (value-multiplier toward 0.85 for FSC-scale cases) |

`y ∈ {0, 1}` was assigned by **defendant compliance within 24 months** of the relevant event (panel-final-ruling for non-authorisation cases; authorisation date for authorisation cases). Source of compliance status: WTO official one-page case summaries 2010 edition; cross-checked against Horn-Mavroidis Implementation sheet (`ImplPan1RepAdoDate`, `SuspconcessImp1Date`).

The coding for each of 23 disputes is in `data/bown_wto_disputes.csv` `outcome_basis` column with per-row citation back to (a) HM event fields and (b) WTO case-summary content.

### Limitations explicitly acknowledged

1. **n = 23 is small.** The pre-reg implicit minimum was n ≥ 10; we're above floor but not in the range where bootstrap CIs would be tight. n_effective ≈ 19 once 4 linked-complainant duplicates are dropped (DS113/162/234/277).
2. **Outcome coding is necessarily judgment-based.** 22 of 23 disputes have widely documented compliance outcomes (these are landmark WTO cases). The one borderline judgment is DS267 (US-Upland Cotton): authorisation granted 2009 but compliance never fully achieved within 24 months → coded `0`. Sensitivity check (recoding DS267 = 1) flips k from -2.92 to -2.48 — same sign and same verdict.
3. **The sunk-cost coding is categorical, not continuous.** Five `s` levels populated; this is the right structure for the WTO data but the resulting probit fit has near-singular Fisher information at `b ≈ 0`. Bootstrap CIs are wide.
4. **Selection-on-defendant-type confound** (the most important): the disputes that reach Article 22.6 arbitration + authorisation are precisely the disputes where the defendant was unwilling to comply at lower escalation levels. We do *not* observe the counterfactual: "what would compliance look like if a case where the defendant was willing to settle were instead pushed all the way to arbitration?" This is a fundamental observational-vs-experimental gap, and no amount of better coding fixes it.

### Audit subsample

Per the task's honesty rule: a 10 % audit subsample (n = 3, DS18 / DS108 / DS217) was hand-cross-checked against the WTO one-page case summaries (https://www.wto.org/english/tratop_e/dispu_e/cases_e/ds{N}_e.htm). All three outcome codings were confirmed:

- **DS18** (Australia-Salmon): July 1999 AQIS lifted ban + June 2000 mutual agreement → `complied=1` ✓
- **DS108** (US-FSC): replaced FSC with ETI, also struck down; EC tariffs 2004-2006; only partially compliant via AJCA 2004 → coded `complied=0` within 24-mo of 2002 authorisation ✓
- **DS217** (US-Byrd Amendment): Byrd Amendment repealed Feb 2006 (Deficit Reduction Act, ~16 months after 2004 authorisation) → coded `complied=1` ✓

## Results table

| Quantity | v0.5 pre-reg | Real WTO (n=23) | In band? |
|---|---|---|---|
| `s*` | [0.20, 0.35] | **0.765** (CI [0.51, 1.99]) | ✗ (way too high) |
| `k` | [4, 12] (POSITIVE) | **-2.92** (CI [-7.92, -0.67]) | ✗ (WRONG SIGN) |
| p(s = 0.2) | < 0.40 | **0.950** | ✗ (way too high) |
| p(s = 0.4) | > 0.65 | **0.857** | ✓ (passes high threshold but trivially: real data has positive p at low s) |
| 95 % CI on k excludes 0 | yes | yes (excludes 0 from below) | ✓ (mechanism is real, but anti-Schelling) |
| Per-anchor hits @ ±0.20 | ≥ 2/4 → CONFIRMED, 4/4 → STRONG | **0/4** | ✗ |
| WTO-anchor-specific hit | — | **NO** (residual_low = 0.63, residual_high = 0.18) | — |

**Probit fit (real data):** `α̂ = 2.23`, `β̂ = -2.92`, both with 95 % CIs excluding 0.

## Why the slope flips negative — the selection mechanism

Look at the cell-level breakdown (s_value → empirical p_comply, n_disputes-no-duplicates):

| s | n | p_comply | Disputes |
|---|---|---|---|
| 0.20 | 1 | 1.00 | DS18 (Salmon) |
| 0.25 | 5 | 1.00 | DS103, DS245, DS257, DS268, DS291 (all settled in arbitration) |
| 0.30 | 2 | 1.00 | DS264, DS294 |
| 0.40 | 1 | 1.00 | DS160 (110(5) copyright) |
| 0.45 | 2 | 0.50 | DS136 (1916 Act), DS267 (Cotton) |
| 0.50 | 2 | 0.50 | DS222 (Aircraft credit), DS285 (Gambling) |
| 0.55 | 1 | 0.00 | DS48 (Hormones-Canada) |
| 0.65 | 1 | 0.00 | DS26 (Hormones-US) |
| 0.70 | 2 | 1.00 | DS27 (Bananas), DS46 (Aircraft) |
| 0.80 | 1 | 1.00 | DS217 (Byrd) |
| 0.85 | 1 | 0.00 | DS108 (FSC) |

**Pattern**: p = 1.0 for all s ≤ 0.40; p = 0.5-0.6 for s ∈ [0.45, 0.85]. The transition is at the *escalation boundary* — cases that escalate past `auth_granted_no_retal` (s ≥ 0.45) split roughly 50-50, while everything that settled before authorisation complied. This is the **textbook selection pattern**:

- *Cooperative defendants* lose to "no escalation needed" — they comply early → low observed `s`, high `p`.
- *Resistant defendants* escalate by definition (the case wouldn't reach arbitration otherwise) → high observed `s`, lower `p`.

Schelling's mechanism predicts the opposite: *higher sunk cost should crowd in compliance*. The negative slope here doesn't reject Schelling's theoretical mechanism — it rejects the **observational identification** of Schelling's mechanism from the Horn-Mavroidis sample.

## Decision: structural (a) with a methodological twist

The original (a) hypothesis was: "4 mechanisms genuinely differ; no single (s*, k) family fits all". The real-data verdict supports a sharper version:

> **(a′) Structural with selection caveat**: the synthetic generator's exogenous-`s` family does not match the observational distribution of WTO retaliation outcomes because the WTO sample is selected on defendant intransigence. The 2/4-anchor gap in sub-run D is not artefactual mis-coding of literature anchors; it reflects a genuine difference between the synthetic and observational regimes. Schelling-style commitment effects may still hold across the *true* exogenous-`s` distribution (which is unobservable from Horn-Mavroidis), but the v0.5 pre-reg's identification strategy is **not testable** on this sample without an instrument for retaliation level.

This does not refute Schelling's theory; it refutes the claim that **Horn-Mavroidis retaliation data alone identifies the Schelling commitment dose-response**.

## Implications for v0.5 paper §6 + §6.5

1. **§6.4 verdict.** Sub-run D's `PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT` remains the v0.5 final on synthetic data. No upgrade to `PASS-STRONG-REAL` on Horn-Mavroidis evidence.
2. **§6.5 path-forward** should be revised: the "drop-in WTO real data" path **does not deliver** what v0.5 §6.5 anticipated. The honest path forward requires either:
   - **An instrument for retaliation-level assignment**: e.g., legally pre-authorised retaliation under domestic safeguard laws (US Section 301, EC Trade Barrier Regulation) — these create exogenous variation in `s` independent of defendant type. The Bown CP / Crowley 2009 working papers list 8-12 such cases — possibly enough for an instrumented sub-analysis.
   - **A non-WTO Schelling test-bed** where `s` is genuinely experimentally varied: lab game-theoretic experiments (Cooper-Kagel 2006; Camerer-Fehr 2004) have run Schelling pre-commitment games with assigned `s`; reanalysis of those datasets would deliver a cleaner test.
   - **Accepting that the synthetic generator's predictions cannot be directly tested** on observational WTO data and re-framing the v0.5 contribution as "PASS-CONFIRMED on synthetic generator + identification-strategy critique on real-data path".
3. **§6.6 (this section)** should be added to the v0.5 paper as an "Empirical falsification of the simple identification strategy" subsection. The paper's net contribution becomes *stronger*, not weaker: v0.5 now offers (i) the threshold-tobit reparametrisation as a clean methodological innovation, (ii) the synthetic-generator PASS-CONFIRMED, (iii) per-anchor microtune ladder, and (iv) **a real-data sanity check that revealed a substantive identification problem**, with explicit recommendations for cleaner test designs.

## Path forward — explicit, prioritised

In order of cost:

1. **(Cheap, ~2 h)** Re-frame v0.5 §6.5 + §6.6 to acknowledge identification failure. No new data. Done in this document.
2. **(Medium, ~6 h)** Locate the **US Section 301 sub-sample** of WTO disputes — cases where USTR was statutorily mandated to retaliate at a pre-defined level under §301(b). Cross-reference with Bown's PIIE Section 301 dataset (https://www.piie.com/blogs/realtime-economic-issues-watch/usitc-section-301-database). This provides a natural instrument: `s` is exogenously fixed by US law independently of defendant type.
3. **(Heavier, ~20 h)** Reanalysis of Cooper-Kagel 2006 / Camerer 2003 lab Schelling experiments. Open data on Open Science Framework; would need ~2 days to download, clean, and fit.
4. **(Open-ended)** Build a new lab/observational dataset with credible `s`-randomisation. Outside v0.5 scope.

## Reproducibility

Everything in this analysis is reproducible from this commit:

```bash
# Download HM dataset (1.38 MB)
curl -sSL -o /tmp/horn_mavroidis.xlsx \
  "https://datacatalogfiles.worldbank.org/ddh-published/0037789/1/DR0045701/horn_mavroidis_wtodataset110311.xlsx"

# Run real-data fit
cd structural-isomorphism/
.venv/bin/python3 v4/validation/schelling-credible-commitment/run_validation_real_wto.py
# Outputs results_real_wto.json
```

The CSV `data/bown_wto_disputes.csv` documents per-dispute coding decisions. RNG seed for bootstrap = 20260525 (matches v0.5 main runs).

## One-line summary for the paper §6 placeholder fills

> The Horn-Mavroidis real-data sanity check (n = 23 disputes reaching DSB Article 22.6 retaliation-request stage) returns a negative-slope probit fit (k = -2.92, 95 % CI [-7.92, -0.67]) — sign-reversed relative to the pre-registration. The reversal reflects observational selection on defendant intransigence rather than a refutation of Schelling commitment theory: cases that travel all the way to applied retaliation are exactly those where the defendant was least willing to comply at any lower escalation level. The synthetic-generator PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT (sub-run D) is the v0.5 final verdict; PASS-STRONG-REAL is not delivered on Horn-Mavroidis and requires either an instrument for retaliation-level (e.g., US §301 sub-sample) or a lab-experimental Schelling dataset.

End of §6.6.
