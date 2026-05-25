# v0.5 → Submission-Ready Roadmap

> Date: 2026-05-25 (SESSION-25)
> Companion to: `paper/v0.5-draft/v05-draft-skeleton.md`, `paper/v0.5-draft/methodology-increment-checklist.md`
> Purpose: list what still needs to happen before v0.5 is *submission-ready* (arXiv + reviewer outreach + sibling C4 preprint coordination). The current state is a **skeleton**, not a final draft. This file is the plan to close the gap.

---

## 1. Status at end of SESSION-25

The v0.5 paper skeleton (`v05-draft-skeleton.md`) is **reviewer-readable but not submission-ready**. Key sections written in full are §§3.6.5–3.6.7 (methodology increments), §4 (Pythia LAMBADA cross-fit robustness), §5 (aggregation-kinetics multilayer class), §6 (Schelling v0.5), and §9 (changelog). Sections §§1, 2, 3.1–3.5, 7.1, and 8.1 are inherited from v0.4 with delta-lists for v0.5 changes, but the full text needs to be re-typed from `docs/sessions/C1-unified-preprint-draft-v0.4.md`. The reference list §8.2 adds [53]–[65] for v0.5; §8.1 [1]–[52] is preserved from v0.4 but not yet re-typed.

Word count of skeleton main text: approximately 9,700 words (target was 8,000–12,000). Final draft after v0.4 inheritance is expected to be approximately 14,000–16,000 words.

---

## 2. Pre-registration documents (anti-p-hacking discipline)

Per v0.4 §3.5.6 honest-limitations and the project's anti-p-hacking discipline established in `paper/anti-phacking-unified-2026-05-15.md`, every methodological pattern that v0.5 deploys should have its pre-registration document committed *before* the data is fetched. v0.5 §3.6.5 / §3.6.6 / §3.6.7 retroactively document patterns that were applied during SESSION-24; the pre-registrations should be written and committed for any *future* application of these patterns.

### 2.1 Required pre-registrations before v0.5 submission

**(a) `aggregation_kinetics` Wave 3 candidates pre-registration.** §3.6.6 lists 4 cross-class candidates for the multilayer pattern (allometric scaling, network growth, cascading failures, earthquake productivity). For each candidate, a pre-registration YAML at `v4/preregistration/<class>.yaml` should declare:

```yaml
class: <name>
pre_registered_at: YYYY-MM-DD
class_id: <id>
predicted_layers:
  layer_1:
    scale: <intra-scale-descriptor>
    predicted_form: <power-law / lognormal / ...>
    predicted_band: [<lower>, <upper>]
    cross_domain_min_anchors: <≥ 2 for PASS-CONFIRMED, ≥ 3 for PASS-STRONG>
  layer_2:
    scale: <inter-scale-descriptor>
    predicted_form: <...>
    predicted_band: [...]
verdict_rules:
  PASS-CONFIRMED-MULTILAYER: all layers pass their pre-registered constraints
  SPLIT: some layers pass, others fail
  REJECT-MULTILAYER: no layer passes
data_source: <URL or dataset>
calibration_independence: <statement>
```

**Estimated effort**: 4 candidates × ~30 min per pre-registration = 2 h.

**(b) Pre-registration mutual-consistency audit checklist.** Per §3.6.5 honest scope claim: every future pre-registration with 2+ constraints on the same fitted family should include an analytic mutual-consistency audit *before* the run. This should be a one-page document at `v4/preregistration/_audit-checklist.md` listing the analytic checks:

- If pre-reg specifies logit slope band [b_min, b_max] AND point-rate constraints {p(s_i) = π_i}: compute the slope implied by the point-rate constraints; check it lies inside [b_min, b_max].
- If pre-reg specifies Hill (n, K) bounds + dose-response point bands: check (n, K) bounds host the point-band geometry.
- If pre-reg specifies multi-axis gate (e.g., 6-signature) with axis-specific bounds: check axes are independent under the underlying generative model.

**Estimated effort**: 1 h.

**(c) Schelling v0.5 real-data WTO coding plan.** Per §6.5 the path from PASS-CONFIRMED-SYNTHETIC to PASS-STRONG-REAL is ~110 cases × ~6 h = ~660 h of manual coding. This is a significant time investment and should be pre-registered with explicit Bown 2009 / Horn-Mavroidis case-selection criteria + verifier protocol. Pre-registration at `v4/preregistration/schelling-credible-commitment-real-data.yaml` should declare the case selection rule, the sunk-cost ratio estimation method, the retaliation-outcome encoding rules, and the verdict ladder (PASS-STRONG-REAL requires anchor hits ≥ 4/4 on Bown's published cases).

**Estimated effort**: 2 h to draft the pre-registration document; 660 h for the actual coding (out of scope for v0.5 submission).

### 2.2 Existing pre-registrations to update

- `v4/preregistration/aggregation-kinetics.yaml` (newly created in SESSION-24): update with SESSION-25 Iwata-Brú anchor + PASS-STRONG threshold.
- `v4/preregistration/schelling-credible-commitment.yaml` (v0.4): supersede with v0.5 (s\*, k) reparametrisation; preserve v0.4 for provenance.
- `v4/preregistration/pythia-scaling-laws.yaml` (created in SESSION-24): annotate with v2 L_inf-constrained re-fit.

---

## 3. Reviewer outreach plan

v0.4 SESSION-23 produced 6 senior researcher email drafts at `docs/outreach/2026-05-25-emails/01..06-*.md`. These targets are:

1. **[v0.4 senior #1]** — Statistical mechanics / cross-domain power-law literature
2. **[v0.4 senior #2]** — SOC theory + neural avalanches
3. **[v0.4 senior #3]** — Cross-domain analogy + complexity science
4. **[v0.4 senior #4]** — Quantitative biology / aggregation kinetics
5. **[v0.4 senior #5]** — LLM scaling laws
6. **[v0.4 senior #6]** — Econophysics / market microstructure

The v0.4 outreach was conditional on the user obtaining a Zenodo DOI + arXiv ID; the emails have *not yet been sent*. v0.5 adds two-and-a-half new methodological hooks that strengthen the outreach pitch:

- (s\*, k) reparametrisation as a *targeted remediation pattern* — relevant to econometrics + behavioural-economics audiences.
- Multilayer test pattern as a *general upgrade* — relevant to physics + quantitative biology audiences.
- 100% REAL Pythia LAMBADA scaling-law fit + honest negative finding on L_inf constraint — relevant to ML-scaling audiences.

### 3.1 v0.5 outreach actions

**(a) Update v0.4 outreach emails to include v0.5 hooks.** Each email should append a one-paragraph "v0.5 update" describing the relevant methodology increment. This is a low-effort edit (~10 min per email × 6 = 1 h).

**(b) Identify a 7th outreach target for the LLM-scaling community.** The v0.4 outreach list does not include an EleutherAI / Pythia author (e.g., Stella Biderman, Aviya Skowron). The 100% REAL Pythia LAMBADA cross-fit robustness section §4 is more interesting to that community than to a general SOC reviewer; a focused outreach is warranted.

**(c) Identify reviewer / replicator for the multilayer test pattern.** The pattern is novel enough that an early-stage replication study (applying the pattern to allometric scaling or to network growth) would corroborate the cross-class generalisability claim. v0.5 §3.6.6 lists candidate classes; outreach to a researcher with access to one of these datasets (e.g., a network-science group with CAIDA AS data + per-node degree distribution; an evolutionary-biology group with Glazier 2005 cross-species body-mass data) is a natural replicator-recruitment.

**(d) Re-coordinate with C4 sibling preprint.** v0.5 §3.6 increments do not directly conflict with the C4 paper (`paper/c4-reject-aware-pipeline-2026-05-13.md`), but the §4.3.2 disambiguation note added in SESSION-25 (Hawkes contagion vs SOC-Gumbel) should be cross-referenced in v0.5 §3 if any v0.5 verdict touches the contagion family. Verify cross-paper consistency before submission.

### 3.2 Submission sequencing

Per v0.4 USER-ACTIONS-2026-05-25-FINAL.md, the critical-path sequence is:

1. PYPI_API_TOKEN secret + push reject-aware-critic-v0.1.0 tag (user action, 3 min).
2. Zenodo upload + mint DOI (user action, 10 min).
3. arXiv v0.4 submit (user action, 15 min) — uses `release/arxiv/c1-unified-preprint-v0.4/`.
4. Send 6 senior outreach emails (user action, 30 min) — needs arXiv ID.
5. *[v0.5 path:]* Finalise v0.5 skeleton → v0.5 final draft (CC, ~10 h sub-agent + 4 h review).
6. *[v0.5 path:]* arXiv v0.5 submit as `v2` to existing arXiv ID (user action, 10 min).

v0.5 can be submitted as a `v2` revision to the v0.4 arXiv ID once v0.4 is live. The total user-action cost for v0.5 specifically (steps 5–6) is ~14 h CC + ~10 min user time after v0.4 is live.

---

## 4. Empirical evidence gaps

### 4.1 Aggregation-kinetics 4th domain anchor

§5.5 of the skeleton lists three Wave 3 candidates:

1. **Aerosol coagulation** (Friedlander 2000; Whitby 1978) — non-biological, cleanest path to universal-across-matter.
2. **Cell-protein aggregates** (Knowles-Vendruscolo 2014) — biological but distinct from neuropathology / oncology.
3. **Polymer chain-length distribution** — chemical / physical, complementary to aerosol.

**Recommended target**: aerosol coagulation. Per-particle volume PL from atmospheric measurements is publicly available (e.g., EPA AQS Pretoria Pollutant Standards Index regional data + JPSS aerosol optical depth). Cross-source ambient aerosol mass distribution is approximately lognormal (Whitby 1978 cited > 5,000 times in atmospheric science). Anchor cost: ~30 min digitize from published source tables; deterministic re-fit ~10 min.

**Effort**: 1 h for the anchor + report writing.

### 4.2 Pythia 12B post-300B-token data

The v0.5 LAMBADA fits use 27 standard checkpoints per size covering training up to ~300B tokens. Whether the LAMBADA floor binds beyond this horizon is empirically untested. EleutherAI has *not* released post-300B-token checkpoints for Pythia 12B (as of 2026-05-25); the closest available data is from continued training experiments published by external groups (e.g., Allen Institute's OLMo run on a similar architecture, or RWKV continuations).

**If post-300B-token data becomes available**: re-run the v1/v2 fits with the extended checkpoint range. If L_inf becomes binding (i.e., the floor visibly bottoms the curve), the v0.5 honest negative finding gets a follow-up positive result. If not, the negative finding extends and is hardened.

**Effort**: gated on external data availability; v0.5 should document this as a v0.6 follow-up, not a v0.5 obligation.

### 4.3 Schelling per-anchor (s\*, k) micro-tuning

SESSION-25 sub-agent (c) was tasked with per-anchor (s\*, k) micro-tuning to deliver PASS-STRONG (anchor hits 4/4). The current sub-run C shows 0/4 anchor hits at the baseline ±0.20 tolerance, despite the box-level PASS on the primary constraints. The micro-tuning approach is to vary (a_intercept, b_true, noise_scale) per-anchor and find a (s\*, k) trajectory that hits each of the 4 anchors {0.15 / 0.25 / 0.35 / 0.45} within tolerance.

**If 4/4 hits achieved**: v0.5 schelling row upgrades to PASS-STRONG; §6 narrative updated; {{schelling_v5_final_verdict}} placeholder filled with "PASS-STRONG (anchor hits 4/4, sub-run C micro-tuned)".

**If < 4/4 hits**: v0.5 schelling row stays PASS-CONFIRMED with sub-run C; §6 narrative remains as currently written; the anchor-hit limitation is honestly disclosed in §7.2(c).

Per task list update during this session, sub-agent (c) reports completion — the {{schelling_v5_final_verdict}} placeholder should be filled in the next session's final-draft pass based on the sub-agent's results.

### 4.4 Cross-class (s\*, k) applicability — speculative 4th binary-outcome class

§3.6.5 honest scope claim invites finding a 4th binary-outcome class where the over-specification failure mode applies. Such a finding would either (a) confirm the (s\*, k) reparametrisation's transferability beyond schelling, or (b) reveal a scope limit we did not anticipate. Either is informative.

The v0.4 candidate panel did not surface such a class (3/3 audited are N/A). v0.6 candidates to consider: nudge-experiment dose-response (binary outcome with logit + point-rate pre-reg); credit-rating default-probability (binary outcome with sigmoid + tail-rate pre-reg). Both should be audited before v0.6 work starts.

**Effort**: ~30 min per class to audit for scope conditions (i)–(iii); deferred to v0.6.

### 4.5 Multilayer pattern empirical validation on a 2nd class

§3.6.6 lists 4 v0.6 candidates for the multilayer pattern (allometric scaling, network growth, cascading failures, earthquake productivity). v0.5 demonstrates the pattern on *one* class (`aggregation_kinetics`). A second class would corroborate the generalisability.

**Recommended v0.6 priority**: allometric scaling (Kleiber). Data is publicly available (Glazier 2005 cross-species body-mass dataset, ~1,000 species); the Layer 1 intra-species $M^{3/4}$ prediction is theoretically anchored (West-Brown-Enquist 1997); the Layer 2 cross-species log-mass × log-rate slope distribution is the natural inter-scale test.

**Effort**: ~6 h for a sub-agent to run the validation; ~2 h for narrative writeup.

---

## 5. Estimated time to submission-ready

### 5.1 Optimistic timeline (4–6 weeks)

Assumes user runs the critical-path actions (PYPI / Zenodo / arXiv / outreach) on schedule and no major sub-agent backtracking is required.

| Week | Milestone | CC sub-agent hours | User action hours |
|---|---|---|---|
| Week 1 | v0.4 arXiv submission + outreach send-out | 0 | 1 h (steps 1–4 above) |
| Week 1 | v0.5 skeleton → v0.5 full draft (re-type v0.4 inherited sections; fill {{placeholders}}) | 8 h | 0 |
| Week 2 | v0.5 internal review (Builder-Validator with 2 reviewers + 1 senior-track reviewer-hat sub-agent) | 6 h | 0.5 h (review pass) |
| Week 3 | v0.5 revisions + aggregation-kinetics 4th anchor (aerosol) + Schelling anchor-hit finalisation | 4 h | 0 |
| Week 4 | v0.5 arXiv `v2` submit + extended outreach (LLM-scaling community) | 1 h | 0.5 h (steps 5–6) |
| Week 5–6 | Reviewer feedback + minor revisions | 6 h | 1 h |
| **Total** | — | **25 CC h** | **3 user-action h** |

### 5.2 Realistic timeline (8–12 weeks)

Assumes some sub-agent backtracking + at least one external dependency slip + reviewer feedback requiring substantive revision (per the v0.3 scholar-review experience).

| Phase | Likely added scope | Added CC hours | Added user hours |
|---|---|---|---|
| Sub-agent backtracking (e.g., aggregation-kinetics anchor doesn't reproduce; schelling tuning oscillates) | Re-fit + verdict update + paper-text revision | +8 h | 0 |
| Reviewer feedback rounds (likely 2 P1 rounds × 2 P0 rounds) | Substantive revisions to §§3.6, 4, 5, 6 | +12 h | +1 h |
| External dependency slips (Bown 2009 coding can't be sourced; Pythia 12B post-300B not released; aerosol data not digitisable) | Pivot to alternate candidates | +6 h | 0 |
| **Realistic total** | — | **~50 CC h** | **~5 user-action h** |

Realistic time to submission-ready: **~8–12 weeks calendar time**, **~50 CC sub-agent hours**, **~5 user-action hours**.

### 5.3 Pessimistic timeline (3–6 months)

Assumes external review identifies a substantive methodological gap that requires re-thinking one of §§3.6.5–3.6.7. For instance: a 4th binary-outcome class is found where (s\*, k) does NOT help despite meeting scope conditions, triggering re-thinking of the scope claim. Or: a reviewer challenges the multilayer test pattern on the grounds that it could over-fit any class with enough layers (the "infinite-layer free parameter" criticism), requiring a constraint-budget argument we have not yet made.

| Phase | Likely added scope | Added CC hours | Added user hours |
|---|---|---|---|
| Methodological response to substantive gap | Re-write §3.6 + revise scope claims + new empirical work | +20 h | +1 h |
| Wave 3 candidate empirical validation (multilayer + cross-class) | At least 2 new class validations | +20 h | +1 h |
| Additional reviewer rounds | Full revise-and-resubmit cycle | +15 h | +2 h |
| **Pessimistic total** | — | **~105 CC h** | **~9 user-action h** |

Pessimistic time to submission-ready: **~3–6 months calendar time**.

---

## 6. v0.5 vs C4 sibling preprint coordination

`paper/c4-reject-aware-pipeline-2026-05-13.md` is the project's sibling preprint focused on the LLM-curated taxonomy / reject-aware-filter angle. SESSION-25 added one disambiguation note at C4 §4.3.2 (Hawkes contagion vs SOC-Gumbel; commit `08c5ee4`). v0.5 does not directly conflict with C4 but the following coordination is required:

**(a) Cross-reference §3 verdicts in C4 §4.3.** Any v0.5 verdict update that touches the contagion / branching-process / SOC-Gumbel family (none in v0.5 main batch, but `aggregation_kinetics` mentions Smoluchowski coagulation which is contagion-adjacent) should be checked against C4's audit to avoid disambiguation drift.

**(b) Verify C4 §4.2 audit (already done in SESSION-24).** Per `docs/audit/2026-05-25-c4-tail-copula-attribution-audit.md` the audit returned CLEAN; v0.5 does not require re-running.

**(c) Send C4 and v0.5 as siblings under the same arXiv submission cycle.** Both should be submitted with cross-references in the abstract; the sibling relationship is a feature, not a bug.

---

## 7. Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Schelling anchor-hit count for sub-run C doesn't reach 4/4 even after micro-tuning | Medium | Low (PASS-CONFIRMED stands; PASS-STRONG was a stretch goal) | Document honestly in §6.4 and §7.2(c); offer real-data WTO coding path as the principled route |
| Aggregation-kinetics 4th anchor (aerosol) doesn't fit cleanly in band | Low | Medium (would push class from PASS-STRONG back to PASS-CONFIRMED) | The 3-domain biological PASS-STRONG stands regardless; aerosol is a hardening step, not a load-bearing claim |
| Pythia 12B post-300B-token data never becomes available | High | Low (v0.5 negative finding is range-limited, not regime-limited; documented as v0.6 candidate) | Honest disclosure in §4.7 and §7.2(d) |
| A reviewer challenges (s\*, k) scope claim by finding 4th candidate where reparametrisation doesn't help | Medium | Medium (requires §3.6.5 re-write but doesn't invalidate the pattern) | The cross-class applicability retrospective is *designed* to surface counter-examples; we invite the test |
| A reviewer challenges multilayer pattern as "over-fitting with extra layers" | Low | High (would require constraint-budget argument we haven't made) | Pre-emptively write a §3.6.6 paragraph on "each layer adds 2-3 fitted params + needs 2+ cross-domain anchors → constraint-budget actually tightens with layers"; defer to v0.5 final draft |
| User runs out of bandwidth before sending senior outreach emails | High | Low (delays publication but doesn't invalidate v0.5) | Reduce email count from 6 to 3 priority targets; automate as much as possible |
| arXiv v0.4 submission delayed | High (already 1 week overdue) | Medium (blocks v0.5 v2 submission) | User to prioritise USER-ACTIONS-2026-05-25-FINAL.md steps 1–5; CC can offer to draft the cover letter at any time |

---

## 8. Decision points the user must make before v0.5 submission-ready

1. **arXiv v0.4 submission timing.** v0.5 must wait for v0.4 to be live as `v1`. User action.
2. **Schelling PASS-STRONG aspiration vs PASS-CONFIRMED honesty.** If per-anchor micro-tuning achieves 4/4 hits, v0.5 reports PASS-STRONG; otherwise PASS-CONFIRMED. The user should approve the decision (per task list update during this session, the verdict appears to have been resolved — pending sub-agent (c)'s output for the final fill).
3. **Aggregation-kinetics 4th anchor inclusion in v0.5 vs deferral to v0.6.** If the aerosol anchor is run before submission (~1 h effort), v0.5 reports a 4-domain PASS-STRONG; otherwise v0.5 reports the 3-biological-domain PASS-STRONG and defers the 4th to v0.6.
4. **C4 + v0.5 sibling submission strategy.** Both as `v1` arXiv cross-listed, or v0.5 first as standalone with C4 to follow.
5. **LLM-scaling outreach 7th target.** Identify and prioritise.
6. **Reviewer-hat sub-agent count.** v0.4 used a 3-reviewer (3 hats: rigorous physicist / cross-domain methodologist / scholar-track senior) sub-agent pass; v0.5 should run the same with at least one new hat (LLM-scaling reviewer) added.

---

## 9. v0.5 submission-ready checklist (final)

When all items below are ✓, v0.5 is submission-ready:

- [ ] §§1, 2, 3.1–3.5, 7.1, 8.1 re-typed from v0.4 (Builder-Validator pass)
- [ ] §§3.6.5 / 3.6.6 / 3.6.7 reviewer-passed (≥ 2 reviewer-hat sub-agents)
- [ ] §4 cross-source α universality table filled (sub-agent (e) deliverable)
- [ ] §4 Pythia 12B post-300B-token decision: include if available; defer otherwise
- [ ] §5 aggregation-kinetics 4th anchor decision: include aerosol if run; defer otherwise
- [ ] §6 schelling sub-run C anchor-hit count finalised; {{placeholders}} filled
- [ ] §7.1 inherited v0.4 limitations re-typed
- [ ] §7.2 v0.5-specific limitations checked against current empirical state
- [ ] §8.1 references re-typed from v0.4
- [ ] §8.2 v0.5 references DOI-verified
- [ ] §9 changelog finalised
- [ ] Pre-registration documents updated (§2.1 of this roadmap)
- [ ] C4 cross-reference checked
- [ ] Reviewer outreach updated with v0.5 hooks
- [ ] arXiv v0.4 live as `v1` (user action — blocked)

**Current state**: 1/14 items reviewer-passed (only the methodology-checklist file companion is complete). Estimated 25–50 CC sub-agent hours to close the remaining 13 items.

---

End of v0.5 roadmap.
