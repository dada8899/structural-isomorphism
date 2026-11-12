# SESSION-25 — v0.5 Paper Skeleton Summary

> Date: 2026-05-25
> Author: SESSION-25 v0.5 paper skeleton sub-agent (CC main path)
> Parent: SESSION-24-HANDOFF.md (HEAD `1960783`); SESSION-25 in progress (HEAD `50c960e` at start of this task)
> Scope: 1-page summary of the v0.5 paper skeleton deliverables for the next session's pickup.

---

## What was delivered

Three new files under `paper/v0.5-draft/` (new directory):

1. **`paper/v0.5-draft/v05-draft-skeleton.md`** — main paper skeleton, ~9,700 words. Reviewer-readable. Sections §§3.6.5–3.6.7, §4, §5, §6, §9 written in full; §§1, 2, 3.1–3.5, 7.1, 8.1 are outlines + delta-lists with v0.4 text to be re-typed in final draft.
2. **`paper/v0.5-draft/methodology-increment-checklist.md`** — reviewer-facing checklist mapping every methodology claim in §3.6 (4 v0.4 inherited + 3 v0.5 new) to its empirical first-instance + cross-class status + scope claim. Includes a cross-reference index table.
3. **`paper/v0.5-draft/v05-roadmap.md`** — what still needs to happen to make v0.5 submission-ready: pre-registration documents, reviewer outreach updates, empirical evidence gaps, 3 timeline scenarios (optimistic 4–6 weeks / realistic 8–12 weeks / pessimistic 3–6 months), risk register, decision points for the user.

Plus this 1-page summary file: **`docs/sessions/SESSION-25-v05-paper-skeleton-summary.md`**.

No commits. No pushes. Main session will commit after review.

---

## What's new in v0.5 vs v0.4

| Increment | Type | First instance | Where in skeleton |
|---|---|---|---|
| **`aggregation_kinetics` PASS-STRONG-MULTILAYER** | New universality class promoted from v0.4 `beta_amyloid_aggregation` INCONCLUSIVE | 3 biological-domain Layer 1 anchors (Cruz 1997, Hartig 2018, Iwata 2000 + Brú 2003) + 4/5 Allen Brain TBI Aβ Layer 2 series | §3 (delta row) + §5 (full narrative) |
| **`schelling_credible_commitment` INCONCLUSIVE → PASS-CONFIRMED** | Methodology fix + sub-run C verification | (s\*, k) threshold-tobit reparametrisation; sub-run C (a=−3, b=12, noise=0.15) delivers s\*=0.251, k=6.529, p(0.4)=0.834, p(0.2)=0.369, sham null |k|<0.05 | §3 (delta row) + §6 (full narrative) |
| **`llm_scaling` (Pythia) BROAD_SPREAD → TIGHT_UNIVERSALITY** | Data upgrade + honest negative methodological finding | 100% REAL Pythia LAMBADA across 8 sizes via EleutherAI per-checkpoint eval JSONs (216 rows); v1 unconstrained α̅=0.144 CV=0.118 and v2 L_inf-constrained α̅=0.159 CV=0.116 both → TIGHT_UNIVERSALITY | §3 (delta row) + §4 (full narrative + cross-source comparison) |
| **§3.6.5 (s\*, k) threshold-tobit reparametrisation** | NEW methodology (targeted remediation) | Schelling v0.5; 3/3 cross-class candidates audited N/A (Hill ≡ canonical (s\*, k)) | §3.6.5 (full methodology) |
| **§3.6.6 Multilayer test pattern** | NEW methodology (general upgrade) | Aggregation-kinetics; 4 v0.6 candidates listed (allometric, network growth, cascading failures, earthquake productivity) | §3.6.6 (full methodology) |
| **§3.6.7 Head-aware LLM validator** | NEW engineering pattern (not methodology) | Wave 3 C 117-entry boilerplate rewrite + 23-entry head-collision strip | §3.6.7 (engineering provenance) |

**Net v0.5 verdict count:** 19 classes empirically anchored (18 v0.4 + 1 v0.5 new); 11 PASS-CONFIRMED-or-stronger (up from 10), 1 INCONCLUSIVE (down from 2), 6 REJECT-CONFIRMED (unchanged), 5 SPLIT decisions (unchanged), 1 MERGE recommendation (unchanged).

---

## Key {{placeholders}} that block final readiness

1. **`{{schelling_v5_final_verdict}}`** / **`{{schelling_v5_final_verdict_section}}`** / **`{{schelling_v5_final_verdict_placeholder}}`** / **`{{schelling_anchor_hits_subrun_C}}`** / **`{{schelling_anchor_hits_status}}`** — all 5 placeholders refer to the same outstanding question: did sub-agent (c)'s per-anchor (s\*, k) micro-tuning achieve PASS-STRONG (4/4 anchor hits at ±0.20 tolerance)? **Per task list update during this skeleton session, task #5 (c) is now marked completed.** The next session should harvest sub-agent (c)'s output and fill these placeholders. If hits are 4/4 → §3 row says PASS-STRONG and §6 narrative is upgraded; if < 4/4 → PASS-CONFIRMED with sub-run C stands and §7.2(c) honestly discloses.
2. **`{{cross_source_summary_table}}`** — the cross-source Pythia α universality comparison table in §4.6. **Per task list update during this skeleton session, task #6 (e) is now marked completed.** Next session should harvest sub-agent (e)'s output (Pythia 12B numbers + 4-source α comparison) and fill.
3. **`{{v1_*}}` and `{{Δ_R2_*}}` placeholders in §4.2 and §4.3** — Pythia LAMBADA v1 per-size numerical detail (α / α_se / A / R² per size). All derivable from `v4/validation/llm-scaling/results_lambada.json` and `results_lambada_v2.json`. ~15 min of mechanical extraction to fill.
4. **`{{word_count}}`** — final draft word count after v0.4 inheritance re-typing. Current skeleton 9,697 words; expected final ~14,000–16,000.

---

## What's NOT in v0.5 (out of scope; deferred to v0.6+)

- Real-data WTO retaliation coding for Schelling (~660 h of manual work).
- 4th non-biological cross-domain anchor for aggregation-kinetics (aerosol / cell-protein / polymer).
- Cross-evaluation α universality for Pythia (only LAMBADA-OpenAI tested).
- Joint global L_inf fit (Hoffmann 2022 style) for Pythia.
- Multilayer pattern empirical validation on a 2nd class (only aggregation-kinetics in v0.5).
- Cross-class application of (s\*, k) to a 4th binary-outcome class.
- Pythia 12B post-300B-token data (not publicly available as of 2026-05-25).

---

## Files NOT touched (§2.6 boundary respected)

- `scripts/train_v2.py` (other session in-flight)
- `v4/results/active_learning/simulation_report.md` (other session in-flight)
- All existing v0.4 paper files in `paper/` root (frozen for arXiv)
- All files outside `paper/v0.5-draft/` and `docs/sessions/`

Working tree at end of this task: same as at start (`scripts/train_v2.py` + `v4/results/active_learning/simulation_report.md` modified by other sessions). 4 new files created (3 in `paper/v0.5-draft/`, 1 in `docs/sessions/`). No commits made by this sub-agent.

---

## Next session pickup instructions

```
Read paper/v0.5-draft/v05-draft-skeleton.md (~9,700 words; reviewer-readable).
Read paper/v0.5-draft/methodology-increment-checklist.md (methodology traceability).
Read paper/v0.5-draft/v05-roadmap.md (path to submission-ready).
Read this file (1-page summary).

Then either:

(A) Harvest sub-agent (c) + (e) deliverables and fill the {{placeholders}} —
    Schelling anchor-hit count → §3 delta row + §6 narrative + §7.2(c) limitation;
    Pythia cross-source table → §4.6 placeholder.
    Estimated 1-2 h sub-agent + 30 min review.

(B) Begin v0.4 inheritance re-typing (§§1, 2, 3.1-3.5, 7.1, 8.1) to produce the
    full v0.5 draft from the skeleton. Estimated 8-12 h sub-agent + 2-4 h review.

(C) Send the skeleton to a reviewer-hat sub-agent for first feedback pass
    before any final-draft work. Estimated 2 h sub-agent + 1 h response triage.

Recommended order: (A) first (cheap, unblocks §6 + §4), then (C) (reviewer
feedback on the new sections), then (B) (re-typing).
```

---

## Honesty notes

- The skeleton is **honest about negative results**: §4.4 explicitly states the L_inf constraint did NOT improve R² (mean R² −0.018); §6.3 sub-run A INCONCLUSIVE-synthetic-too-smooth is reported alongside sub-run C PASS-CONFIRMED; §5.6 caveats list 3 limitations of the aggregation-kinetics PASS-STRONG.
- The skeleton is **honest about scope claims**: §3.6.5 explicitly limits (s\*, k) to the over-spec failure mode; §3.6.6 lists *candidate* cross-class extensions, not empirical claims; §3.6.7 explicitly says "engineering, not scientific methodology".
- The skeleton **does not invent reviewer feedback**: no "Reviewer X said Y" statements; §7.1 inherits v0.4 limitations only.
- The skeleton **does not over-sell**: PASS-STRONG-MULTILAYER (3 biological domains) is *not* claimed to be universal-across-matter; PASS-CONFIRMED (Schelling sub-run C) is *not* claimed to be real-data verified.

---

End of SESSION-25 v0.5 paper skeleton summary.
