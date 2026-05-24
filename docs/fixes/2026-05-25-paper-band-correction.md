# Paper §3.5 Band + Attribution Correction Report

> Date: 2026-05-25
> Triggered by: audit-2 P0 findings on C1 v0.4 §3.5 verdict matrix
> Scope: paper draft + handoff only; **no source-of-truth `results.json` touched**, no code changed, no commit/push performed

## Truth sources (read-only, untouched)

- `v4/validation/anderson-localization/results.json`
  - `pre_registered_bands.nu = [1.45, 1.7]`
  - `verdict.primary_nu = 1.62` (label `PASS`, `nu_in_band = true`)
- `v4/validation/percolation-connectivity/results.json`
  - `tau.band_2d = [1.85, 2.2]`
  - `tau.measured = 1.9399196053020216`, `tau.reference = 2.0549450549450547`, `tau.in_band = true`
  - `overall_verdict = PASS`
- Tail-copula sub-agent report (Wave 2A.3): SOC mechanism model loses to copula descriptor model by ΔAIC ∈ [999, 3224] on 4/4 SPX‖VIX pairs; Gumbel copula beats t/Clayton/Frank alternatives by BIC margin ∈ [346, 1645] on 4/4 pairs
- `v4/validation/leaky-integrate-fire/verdict.md`: actual members lif_synthetic / allen_brain / financial_bursts / hydraulic_burst / sensor_cascade (not the 3 brief members Piezo1 / hedonic / token-bucket)

## Fix 1 — Anderson localisation pre-reg band

- **Old (paper)**: ν ∈ [1.50, 1.65]
- **New (corrected from `results.json`)**: ν ∈ [1.45, 1.7]
- **Recovered ν = 1.620**: `in_band` was already `true` even under the old narrow band (1.50 ≤ 1.620 ≤ 1.65); the band was wrong-narrow, not the verdict. No PASS/REJECT flip; the correction restores fidelity to the pre-registration.
- **Files changed**:
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 225 (Table 2, W2C.5 row)
  - `docs/sessions/SESSION-23-HANDOFF.md` line 81 (§3 verdict matrix, W2C.5 row — also added band annotation `[1.45, 1.7]`)

## Fix 2 — Percolation connectivity pre-reg band

- **Old (paper)**: τ ∈ [1.95, 2.15]
- **New (corrected from `results.json`)**: τ ∈ [1.85, 2.2]
- **Recovered τ = 1.94**: under the old paper band [1.95, 2.15] this reads "1.94 < 1.95 → out of band → contradicts the PASS verdict in the table", creating a contradictory reader signal. Under the actual pre-registered band [1.85, 2.2] from `results.json`, 1.94 is comfortably inside (`tau.in_band = true`) and the PASS + SPLIT verdict is internally consistent. This was the most dangerous of the three P0 errors because it gave the appearance of a forced-PASS.
- **Band-half-width annotation added**: The new band [1.85, 2.2] is a 9% half-width around the textbook Stauffer–Aharony 2D Fisher exponent 187/91 ≈ 2.055, deliberately wide to absorb finite-L correction-to-scaling drift (L ∈ {128, 256, 512} in the W2B.2 sweep). This is documented in the new §3.5.6 (d) limitation note.
- **Files changed**:
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 216 (Table 2, W2B.2 row)
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 269 (§3.5.4 (b) prose narrative)
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 295 (new §3.5.6 (d) limitation)
  - `docs/sessions/SESSION-23-HANDOFF.md` line 72 (§3 verdict matrix, W2B.2 row — also added band annotation `[1.85, 2.2]`)

## Fix 3 — Tail copula attribution

- **Old (paper)**: "Gumbel BIC win 999–3,224" reported in three places (abstract line 85, Table 2 W2A.3 line 211, descriptor-screen table line 249)
- **Issue**: the numbers 999–3,224 are correct *in magnitude*, but their *attribution* was wrong by one model-comparison pair. They are the SOC-mechanism-vs-copula-descriptor ΔAIC gap (SOC losing on 4/4 pairs), not the Gumbel-copula-vs-other-copula BIC margin. The actual Gumbel-vs-other-copula BIC win is 346–1,645 (on 4/4 pairs).
- **New (corrected)**: explicit phrasing "SOC mechanism loses to copula descriptor by ΔAIC 999–3,224 (Gumbel BIC win over alternative copulas 346–1,645)" — both numbers retained with correct attribution.
- **§3.5.3 mechanism-vs-descriptor boundary section** (line 249 descriptor table) re-checked and corrected — it was making the same attribution error, which is the most consequential single error since this is the section that defines the descriptor-vs-mechanism binary screen.
- **Files changed**:
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 85 (abstract)
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 211 (Table 2, W2A.3 row)
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 249 (§3.5.3 descriptor table, tail_copula row)
  - `docs/sessions/SESSION-23-HANDOFF.md` line 67 (§3 verdict matrix, W2A.3 key-number column)

## Fix 4 (P1) — Leaky integrate-fire brief → implementation drift

- **Issue**: the original B3 brief pre-registered 3 representative members (Piezo1 mechanotransduction / hedonic adaptation / token-bucket); the actual W2C.1 validation used 5 alternative members (`lif_synthetic` / `allen_brain` Neuropixels / `financial_bursts` GARCH-OU / `hydraulic_burst` Pareto / `sensor_cascade` Poisson) due to data-availability constraints. The paper did not flag the substitution, making the verdict ("R ∈ [1.02, 6.48], 2/5 in band, spread 6.35×") read as if applied to the briefed members.
- **Fix**: new §3.5.6 (e) limitation note explicitly documents the brief → implementation drift, names all 5 actual members, and points to `v4/validation/leaky-integrate-fire/verdict.md` data-provenance line for the substitution rationale (SOEP registration delay; no licensable Piezo1 single-cell patch-clamp; no token-bucket trace dump in compatible licence).
- **Files changed**:
  - `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 297-ish (new §3.5.6 (e) limitation, appended after the new (d) note)

## §3.5.6 prologue count

- **Old**: "consciously conservative in **three** respects"
- **New**: "consciously conservative in **five** respects" (added (d) percolation band re-baseline + (e) leaky drift)
- **Files changed**: `docs/sessions/C1-unified-preprint-draft-v0.4.md` line 287

## Files modified

1. `/Users/dadamini/Projects/structural-isomorphism/docs/sessions/C1-unified-preprint-draft-v0.4.md`
   - Abstract (line 85): tail_copula attribution
   - Table 2 W2A.3 (line 211): tail_copula attribution
   - Table 2 W2B.2 (line 216): percolation band [1.95, 2.15] → [1.85, 2.2] (+ "9% half-width" annotation)
   - Table 2 W2C.5 (line 225): anderson band [1.50, 1.65] → [1.45, 1.7]
   - §3.5.3 descriptor table (line 249): tail_copula attribution
   - §3.5.4 (b) (line 269): percolation prose narrative band [1.95, 2.15] → [1.85, 2.2]
   - §3.5.6 prologue (line 287): "three" → "five"
   - §3.5.6 (d) (new, after line 293): percolation band half-width rationale
   - §3.5.6 (e) (new, after the (d) addition): leaky brief → implementation drift footnote

2. `/Users/dadamini/Projects/structural-isomorphism/docs/sessions/SESSION-23-HANDOFF.md`
   - §3 W2A.3 row (line 67): tail_copula attribution
   - §3 W2B.2 row (line 72): percolation band annotation
   - §3 W2C.5 row (line 81): anderson band annotation

## Files added

- `/Users/dadamini/Projects/structural-isomorphism/docs/fixes/2026-05-25-paper-band-correction.md` (this file)

## What was deliberately NOT changed

- `v4/validation/anderson-localization/results.json` — source of truth; untouched
- `v4/validation/percolation-connectivity/results.json` — source of truth; untouched
- `v4/validation/leaky-integrate-fire/verdict.md` and `results.json` — source of truth; untouched
- `scripts/train_v2.py` — in-flight from another session per SESSION-23 §2.6; untouched
- `packages/*` — out of scope; untouched
- No `git add`, no `git commit`, no `git push`

## Verification (post-edit)

```bash
grep -n "1.45, 1.7\|1.85, 2.2\|999.*3,224.*346.*1,645\|346.*1,645" docs/sessions/C1-unified-preprint-draft-v0.4.md
```
- Anderson band [1.45, 1.7]: present at table line 225
- Percolation band [1.85, 2.2]: present at table line 216, prose line 269, limitation (d)
- Tail-copula corrected attribution: present at abstract line 85, table line 211, descriptor-screen line 249, handoff line 67

## Open ambiguities for user decision

1. **Aggregate counts unchanged.** The corrections do not change the 10 PASS / 6 REJECT / 2 INCONCLUSIVE / 5 SPLIT / 1 MERGE aggregate, because both Anderson and percolation were already PASS in the source `results.json` (the paper's narrow band was the artefact, not the verdict). No downstream counts in §3.5.2, §3.5.3, §3.5.7, or the abstract need adjustment beyond the in-place phrase-level edits already made.
2. **C4 paper cross-reference.** The tail-copula correction makes the "C4 paper §4.2" footnote (line 249) more accurate, because C4's "mechanism-vs-descriptor" framing is precisely the ΔAIC mechanism-vs-descriptor comparison, not a within-copula-family comparison. If C4 is co-submitted, its §4.2 should be cross-checked for the same attribution error — out of scope for this fix.
3. **v0.5 P0 hardening.** Suggest two v0.5 actions in addition to the corrections above:
   - Schema-validate every `Pre-reg band` cell in §3.5.2 against the corresponding `results.json[pre_registered_bands]` or `results.json[<invariant>][band_*]` field via an automated CI check, so future paper drafts cannot drift from `results.json`.
   - For every "ΔAIC / BIC win" number reported in the paper, require an inline `(model-A vs model-B)` attribution rather than a bare margin — exactly the discipline this fix had to retrofit.
4. **Handoff §3 vs §4.** SESSION-23 §3 was updated for the three P0 items; §4 (user operation checklist), §5 (start-prompt), §6 (outstanding) were not touched because they do not reference the affected numbers. If the user later wants the start-prompt to flag "P0 corrections applied 2026-05-25", a single-line addition under §5 would close it.
