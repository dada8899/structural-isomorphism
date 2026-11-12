# Audit — C4 paper §4.2 tail-copula attribution

> **Date.** 2026-05-25 (SESSION-24)
> **Trigger.** SESSION-23 handoff §8 outstanding #8: "C4 paper §4.2 可能 tail-copula attribution 同错（下个 session 检查）"
> **Status.** **CLEAN — no attribution issue found.**
> **Methodology.** Read-only audit on `paper/c4-reject-aware-pipeline-2026-05-13.md` §4.2 + §4.3.2 (tail_copula_contagion section).

## Context — the C1 attribution issue that prompted this audit

In SESSION-23, commit `9eb7d91` corrected a conflation in `docs/sessions/C1-unified-preprint-draft-v0.4.md`:

**Before fix (incorrect):**
> `tail_copula_contagion` (Gumbel BIC win 999–3,224 vs SOC across 4 SPX‖VIX pairs)

**After fix (correct):**
> `tail_copula_contagion` (SOC mechanism vs copula descriptor ΔAIC loss 999–3,224 across 4 SPX‖VIX pairs; Gumbel BIC win over alternative copulas 346–1,645)

The bug was conflating two *different* model-selection comparisons:
1. **SOC mechanism vs copula descriptor**: ΔAIC loss 999–3,224 (rejecting SOC as the right family)
2. **Gumbel copula vs alternative copulas (Frank/Clayton)**: BIC win 346–1,645 (the best copula within the copula family)

Both numbers are real and were in the original data; the original text fused them into a misleading "Gumbel BIC win 999–3,224 vs SOC" claim.

## Audit scope — what we checked in C4

`paper/c4-reject-aware-pipeline-2026-05-13.md` is a methodology paper about the **reject-aware filter** (B1 single-Opus vs B3 three-DeepSeek ensemble), distinct from C1 which is the **empirical validation** paper. We checked whether the C1 conflation propagated into C4 §4.2 (Verdict distribution) and §4.3.2 (the `tail_copula_contagion` discussion).

### Findings on C4 §4.2 (Verdict distribution, lines 213-222)

Section contains only **rejection-rate statistics**:
- B1 alone: 11 KEEP / 3 REJECT / 4 SPLIT / 3 MERGE — **14.3% rejection rate**
- B3 ensemble: 5 KEEP / 7 REJECT / 5 SPLIT / 4 MERGE — **33.3% rejection rate**
- B1 ⊗ B3 agreement: 14/21 (66.7%)

**No SOC ΔAIC vs Gumbel BIC numbers appear in §4.2.** Clean.

### Findings on C4 §4.3.2 (`tail_copula_contagion`, lines 239-245)

The section discusses:
- B1's KEEP rationale (Embrechts-Klüppelberg-Mikosch + Joe textbook references)
- B3's REJECT consensus + creative-dissenter SPLIT (verdict-level disagreement only — no numerical claims)
- "Independently corroborated by W2-B real-data test (A2 #6) on DeFi liquidation data ([13], §A2-6): fitting a Hawkes-process model to the on-chain cascade time series yielded a different exponent structure across the three protocols (Aave, Compound, MakerDAO) than the unified tail-copula prediction required."

**Key observation:** the C4 empirical anchor is the **DeFi liquidation / Hawkes-process test** (different data, different model comparison), NOT the **SPX/VIX SOC vs Gumbel** test that C1 §3.5 reports. There is no risk of the SOC-vs-Gumbel conflation propagating to C4 because **C4 doesn't make any such numerical claim**.

The reference to "[13]" is to the unified-pipeline preprint (C1) which has the SPX/VIX numbers; C4 only borrows the verdict (REJECT-corroborated), not the SOC vs Gumbel numbers.

## Conclusion

**Audit verdict: PASS-CONFIRMED-CLEAN.**

C4 paper §4.2 and §4.3.2 do not have the SOC-vs-Gumbel attribution conflation that C1 had. No fix needed.

The SESSION-23 concern was **precautionary** (if C4 had inherited C1's number from a shared source it would have repeated the error). Since C4 is a methodology paper that references empirical results at the verdict level only (not number level), the conflation could not propagate.

## Recommendation

Add a one-line note to `paper/c4-reject-aware-pipeline-2026-05-13.md` near §4.3.2's reference to [13] making the empirical-test distinction explicit:

> "The independent corroboration is a Hawkes-process fit on DeFi liquidation cascade time series — distinct from the SPX/VIX SOC-vs-Gumbel-copula model-selection test that [13] §3.5 reports."

This is a *clarity* improvement, not a correction. Whether to add it is a judgement call.

## Related artifacts

- C1 fix commit: `9eb7d91` (2026-05-25)
- C1 paper draft: `docs/sessions/C1-unified-preprint-draft-v0.4.md`
- C4 paper draft: `paper/c4-reject-aware-pipeline-2026-05-13.md`
- 13-system sibling preprint: `web/frontend/assets/data/papers/unified-pipeline-v0.2-2026-05-13.md`
- SESSION-23 handoff outstanding #8: `docs/sessions/SESSION-23-HANDOFF.md` §8 line 205

End of audit report. Closes SESSION-23 outstanding #8.
