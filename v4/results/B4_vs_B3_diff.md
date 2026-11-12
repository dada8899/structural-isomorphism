# B4 vs B3 — heterogeneous-ensemble agreement analysis

**Date**: 2026-05-14 (full ensemble re-run, session #7 post-deploy)
**Session**: session-7 post-deploy scale tasks
**B3 source**: `v4/results/B3_taxonomy_v2.jsonl` (3-reviewer within-vendor DeepSeek ensemble, 21 classes)
**B4 source**: `v4/results/B4_heterogeneous_ensemble.jsonl` (**full 21-class** run, 63 verdicts)

## Setup note (critical caveat — unchanged from sample run)

**B4 third reviewer still falls back to in-vendor probe.** OpenRouter API key not present
on this machine, so Kimi-K2.5 cross-architecture probe remains unavailable. The third reviewer
was DeepSeek-pro at T=1.0 ("high-creativity" persona) instead of a true cross-vendor probe.

This caveat is documented in `B4_ensemble_summary.md`. A true cross-architecture B4
(with Kimi-K2.5 or Claude or Gemini) is deferred to a future session once OpenRouter
key (or equivalent direct keys) is provisioned.

## Full per-class agreement table (21 classes)

| class_id | B3 consensus | B4 consensus | Agreement |
|---|---|---|---|
| `adverse_selection_unraveling_class` | SPLIT | REJECT | DIFFER |
| `delay_differential_debt` | REJECT | UNCLEAR | DIFFER |
| `extreme_value_tail_class` | REJECT | REJECT | AGREE |
| `gardner_collins_toggle_switch_Th1Th2` | MERGE | MERGE | AGREE |
| `gardner_collins_toggle_switch_apoptosis` | MERGE | MERGE | AGREE |
| `hysteresis_first_order_transition_fertility` | MERGE | REJECT | DIFFER |
| `hysteresis_preisach` | REJECT | UNCLEAR | DIFFER |
| `leaky_integrate_fire_threshold_class` | SPLIT | REJECT | DIFFER |
| `markov_chain_memory_fidelity_class` | REJECT | REJECT | AGREE |
| `motter_lai_network_cascade` | SPLIT | REJECT | DIFFER |
| `motter_lai_network_cascade_social` | MERGE | MERGE | AGREE |
| `percolation_connectivity` | SPLIT | KEEP | DIFFER |
| `preferential_attachment` | KEEP | UNCLEAR | DIFFER |
| `reaction_diffusion_steady_state_class` | KEEP | REJECT | DIFFER |
| `reflexive_fixed_point_class` | KEEP | UNCLEAR | DIFFER |
| `scale_free_percolation_class` | REJECT | REJECT | AGREE |
| `scheffer_fold_bifurcation` | KEEP | UNCLEAR | DIFFER |
| `schelling_credible_commitment` | REJECT | REJECT | AGREE |
| `second_order_damped_oscillator` | KEEP | UNCLEAR | DIFFER |
| `sir_contagion_network_class` | SPLIT | REJECT | DIFFER |
| `tail_copula_contagion` | REJECT | REJECT | AGREE |

## Aggregate metrics (full 21-class run)

- **Classes compared**: 21
- **AGREE**: 8 / 21  (38%)
- **DIFFER**: 13 / 21  (62%)

## What the full run reveals vs. the prior sample

The Wave 2 W2-C sampled 8 classes and reported 4/7 AGREE (57%). The **full 21-class run shows
substantially worse agreement (38% AGREE vs B3)** — confirming the prior caveat that B3's
within-vendor 3-reviewer ensemble systematically over-estimates verdict stability.

### Pattern of disagreement

Most B4 DIFFER cases push B3 toward less-decisive verdicts:

1. **KEEP → UNCLEAR / REJECT** (5 of 13 differs):
   - `preferential_attachment`, `reflexive_fixed_point_class`, `scheffer_fold_bifurcation`,
     `second_order_damped_oscillator` — B3 said KEEP, B4 says UNCLEAR
   - `reaction_diffusion_steady_state_class` — B3 said KEEP, B4 says REJECT outright

   This is the most worrying pattern: B3's KEEP verdicts (the "we have a robust class" finding)
   are the most fragile to within-vendor temperature variation.

2. **SPLIT → REJECT** (4 of 13 differs):
   - `adverse_selection_unraveling_class`, `leaky_integrate_fire_threshold_class`,
     `motter_lai_network_cascade`, `sir_contagion_network_class`,
     `percolation_connectivity` (→ KEEP, atypical)

   B3 found clean 3-way splits warranting sub-class taxonomy; B4 reviewers are more skeptical
   and reject these wholesale. The B4 high-creativity reviewer often votes KEEP while
   rigorous reviewers reject — splitting verdict.

3. **REJECT → UNCLEAR** (2 of 13 differs):
   - `delay_differential_debt`, `hysteresis_preisach` — B3 was confident reject,
     B4's high-creativity reviewer flips to KEEP or SPLIT, degrading consensus.

4. **MERGE → REJECT** (1 of 13 differs):
   - `hysteresis_first_order_transition_fertility` — B3 said merge into broader hysteresis,
     B4 rejects the class outright.

### What B4 confirms

The 8 / 21 AGREE cases (38%) form a tight robust core:
- 4 strong REJECTs: extreme_value_tail, markov_chain_memory, scale_free_percolation,
  tail_copula_contagion, schelling_credible_commitment
- 3 MERGEs into broader classes: gardner_collins_Th1Th2, gardner_collins_apoptosis,
  motter_lai_social

These are robust to within-vendor temperature sweep. **They still do not yet probe
cross-architecture disagreement** (third reviewer was still DeepSeek). A true Kimi or
Claude reviewer pass might further degrade.

## Interpretation

The full 21-class B4 ensemble corroborates and extends the prior 8-class caveat:

> **B3's 3-reviewer within-vendor ensemble materially over-estimates verdict stability.**
> Even within-vendor temperature variance flips 62% of class verdicts. The classes that
> survive (8 / 21 = 38%) form the robust core of the V2 taxonomy; the rest warrant
> re-litigation before being treated as load-bearing for any downstream artefact.

The KEEP fragility is the most actionable finding: B3's KEEPs are the verdicts that
downstream artefacts most rely on (these are the "we have a class!" decisions), and they
are the least temperature-stable. **Any paper-tier deliverable that cites a B3 KEEP must
qualify with a B4 re-check.**

## Recommendation

1. **Do NOT lock B3 v2 yet** for the 13 DIFFER classes — they are sensitive to even
   within-vendor temperature variation.
2. **The 8 AGREE classes** (62% of which are REJECT, 38% MERGE) are the safe-to-publish
   verdicts; the 13 DIFFER classes need either re-litigation, a Kimi/Claude reviewer,
   or explicit confidence-degradation in downstream artefacts.
3. **Re-run B4 with real cross-architecture reviewer (Kimi-K2.5 / Claude / Gemini)**
   as soon as OpenRouter access or equivalent direct keys is restored. Target the
   13 DIFFER classes for the unstable verdicts first.
4. **Document this limitation in any paper-tier deliverable**: B3's 3-reviewer
   within-vendor ensemble systematically over-estimates verdict stability by ~62%
   on the 21-class V2 taxonomy.

## Reproduce

```bash
# Cross-tabulate full B3 ↔ B4 verdicts
.venv/bin/python -c "
import json
from collections import Counter

def consensus(votes):
    c = Counter(votes)
    top = c.most_common()
    if len(top) > 1 and top[0][1] == top[1][1]:
        return 'UNCLEAR'
    return top[0][0]

b3 = {json.loads(l)['class_id']: json.loads(l) for l in open('v4/results/B3_taxonomy_v2.jsonl')}
b4_rows = [json.loads(l) for l in open('v4/results/B4_heterogeneous_ensemble.jsonl')]
b4_by_class = {}
for r in b4_rows:
    b4_by_class.setdefault(r['class_id'], []).append(r)
agree = differ = 0
for cid in sorted(set(b3) | set(b4_by_class)):
    b3v = b3.get(cid, {}).get('b3_consensus', 'N/A')
    verds = [r['verdict'] for r in b4_by_class.get(cid, []) if r['verdict'] != 'PARSE_FAIL']
    b4v = consensus(verds) if verds else 'N/A'
    if b3v != 'N/A' and b4v != 'N/A':
        flag = 'AGREE' if b3v == b4v else 'DIFFER'
        if flag == 'AGREE': agree += 1
        else: differ += 1
    print(f'{cid:50s} B3={b3v:8s} B4={b4v:10s} {flag}')
print(f'\\nAGREE={agree} DIFFER={differ}')
"
```
