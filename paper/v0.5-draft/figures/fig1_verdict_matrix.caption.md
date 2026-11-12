**Figure 1.  v0.5 19-class verdict ladder.**

Each row is one universality-class candidate. Bar length encodes the v0.5 final
verdict rung on the 7-step ladder (REJECT-CONFIRMED → INCONCLUSIVE → PARTIAL →
PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT → PASS-CONFIRMED → PASS-CONFIRMED-MULTILAYER
→ PASS-STRONG). White circles mark the v0.4 baseline rung and grey arrows show
the v0.5 upgrade. Three v0.5 deltas are highlighted: `aggregation_kinetics`
(NEW class promoted to PASS-STRONG from v0.4 `beta_amyloid` INCONCLUSIVE);
`schelling_credible_commitment` (INCONCLUSIVE → PASS-CONFIRMED-WITH-PARTIAL-ANCHOR-FIT
via (s\*, k) reparametrisation, sub-run D best-in-band, 2/4 anchor hits);
`llm_scaling` (BROAD_SPREAD → TIGHT_UNIVERSALITY once LAMBADA per-checkpoint
evaluations replace train-loss fits, α̅=0.144, CV=0.126). Aggregate count: 11
PASS-or-stronger, 1 INCONCLUSIVE, 1 PARTIAL, 6 REJECT-CONFIRMED. Source data:
`v4/validation/*/verdict*.md`, `docs/sessions/SESSION-23-HANDOFF.md`,
`docs/sessions/SESSION-25-v05-paper-skeleton-summary.md`.
