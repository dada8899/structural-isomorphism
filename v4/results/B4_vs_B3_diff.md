# B4 vs B3 — heterogeneous-ensemble agreement analysis

**Date**: 2026-05-14
**Session**: session-7 Wave 2 Agent C
**B3 source**: `v4/results/B3_taxonomy_v2.jsonl` (3-reviewer within-vendor DeepSeek ensemble, full 23-class run)
**B4 source**: `v4/results/B4_heterogeneous_ensemble.jsonl` (sample of 8 classes, see Setup notes below)

## Setup note (critical caveat)

**B4 third reviewer fell back to in-vendor probe.** OpenRouter API key not present in env on
this machine, so Kimi-K2.5 cross-architecture probe is unavailable. The third reviewer was
DeepSeek-pro at T=1.0 ("high-creativity" persona) instead. This is documented as a
**weaker** cross-architecture probe in `B4_ensemble_summary.md` and faithfully reproduced
here.

A true cross-architecture B4 (Kimi or Claude or Gemini) is deferred to a future session
once OpenRouter key is provisioned or DeepSeek+Kimi+Gemini direct keys are wired.

## Per-class agreement table

| class_id | B3 consensus | B4 consensus | Agreement | Notes |
|---|---|---|---|---|
| `delay_differential_debt` | REJECT | UNCLEAR | DIFFER | B4 added KEEP+SPLIT votes; degrades B3 REJECT confidence |
| `extreme_value_tail_class` | REJECT | REJECT | AGREE | Strong consensus both rounds |
| `gardner_collins_toggle_switch_Th1Th2` | (not in B3 v2) | MERGE | n/a (B3 didn't have this subclass) | Pure B4 finding |
| `hysteresis_preisach` | REJECT | REJECT | AGREE | Strong consensus |
| `motter_lai_network_cascade` | SPLIT | UNCLEAR | DIFFER | B4 mixed KEEP/REJECT/UNCLEAR → no majority |
| `scheffer_fold_bifurcation` | KEEP | UNCLEAR | DIFFER | T=1.0 reviewer flipped to KEEP; rigorous reviewers UNCLEAR |
| `schelling_credible_commitment` | REJECT | REJECT | AGREE | Strong consensus |
| `tail_copula_contagion` | REJECT | REJECT | AGREE | Strong consensus |

## Aggregate metrics

- **Classes sampled in B4**: 8
- **Direct B3 ↔ B4 comparable**: 7 (excluding `gardner_collins_toggle_switch_Th1Th2` which is a B4-only sub-class)
- **AGREE**: 4 / 7  (57%)
- **DIFFER**: 3 / 7  (43%)
- **All differences degrade B3 confidence**: B3 was *more* decisive (REJECT/SPLIT/KEEP); B4 third
  reviewer's T=1.0 persona introduced enough noise to flip 3/7 to UNCLEAR.

## Interpretation

### What B4 confirms

The 4/7 AGREE cases (extreme_value_tail_class, hysteresis_preisach, schelling_credible_commitment,
tail_copula_contagion) — all consensus REJECTs — are robust to within-vendor temperature
sweep. This is consistent with B3's existing within-vendor finding. **It does not yet probe
cross-architecture disagreement** because the third reviewer was still DeepSeek.

### What B4 destabilises

The 3/7 DIFFER cases reveal something subtler than "Kimi disagrees":

1. `delay_differential_debt` — DeepSeek-pro T=1.0 votes SPLIT instead of REJECT.
   In-vendor temperature noise alone is enough to soften the B3 REJECT.
2. `motter_lai_network_cascade` — three reviewers landed KEEP / REJECT / UNCLEAR, i.e.
   no majority. B3 had reached SPLIT (clean 3-way split into sub-cascades);
   B4 cannot reproduce that SPLIT consensus.
3. `scheffer_fold_bifurcation` — T=1.0 flipped to KEEP, the two rigorous reviewers
   were UNCLEAR. B3's KEEP verdict looks more fragile than the B3 summary
   suggested.

**Honest reading**: even within-vendor (DeepSeek-only) configuration variance shifts
3/7 verdicts. The TRUE cross-architecture B4 (with Kimi) might shift even more.
A re-run with a real Kimi reviewer is **necessary** before treating B3 as locked.

## Recommendation

1. **Do NOT lock B3 v2 yet** for the 3 DIFFER classes — they are sensitive to even
   within-vendor temperature variation.
2. **Re-run B4 with real Kimi-K2.5** as soon as OpenRouter access is restored. Target
   24-class full run (not sample) for the unstable classes.
3. **Document this limitation in any paper-tier deliverable**: B3's 3-reviewer
   within-vendor ensemble systematically over-estimates verdict stability.

## Reproduce

```bash
# Cross-tabulate B3 (full) and B4 (sample) verdicts
.venv/bin/python -c "
import json, re
b3 = {json.loads(l)['class_id']: json.loads(l) for l in open('v4/results/B3_taxonomy_v2.jsonl')}
b4 = {}
for ln in open('v4/results/B4_ensemble_summary.md'):
    m = re.match(r'\| \`([a-z_]+)\` \|.* \*\*(\w+)\*\*.*', ln)
    if m:
        b4[m.group(1)] = m.group(2)
for cid, b4v in b4.items():
    b3v = b3.get(cid, {}).get('b3_consensus', 'N/A')
    print(f'{cid:55s} B3={b3v:8s} B4={b4v}')
"
```
