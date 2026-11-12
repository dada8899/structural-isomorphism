# gardner_collins_toggle_switch_v2

**Name (zh)**: Hill 超敏正反馈双稳态开关类
**Name (en)**: Hill Ultrasensitive Positive-Feedback Toggle Switch
**Pre-registered exponent band**: Hill coefficient n ∈ [2.5, 4.5]; bistable hysteresis ratio (existence-range width / threshold) ∈ [0.30, 0.70]. Rationale: quorum-sensing literature (Waters–Bassler 2005 Annu Rev Cell Dev Biol 21:319; Anetzberger 2009 V. harveyi n ≈ 3); Bagowski–Ferrell 2001 MAPK cascade n ≈ 4.
**Verified status**: false (target: v0.4). B3 consensus = MERGE (with `gardner_collins_toggle_switch`). See companion file for the merge analysis plan.

## Why this class needs an empirical anchor

v2 sharpens v1 by isolating the *positive-feedback Hill* sub-mechanism (one equation, not two mutually-repressing variables). The empirical question is whether population-level QS systems (V. harveyi luminescence, P. aeruginosa virulence) show a tighter Hill band than v1's mutually-repressing two-gene systems. If the bands overlap and dwell-time distributions are statistically indistinguishable, MERGE is supported.

KB linkage: 3 members — apoptotic caspase cascade (irreversible digital switch), QS density-dependent switch, V. harveyi synchronised induction.

## Candidate empirical data sources (ranked)

| # | Dataset | URL / DOI | License | Size | Why fits this class | Risk |
|---|---|---|---|---|---|---|
| 1 [primary] | Anetzberger et al. 2009 Mol Microbiol 73:267 V. harveyi single-cell QS dose–response (LuxR-GFP reporter, AI-2 + CAI-1 titration) | Supplementary tables on Wiley Online | Free supplementary | ~30 conditions × 10⁴ cells | Canonical mechanistic anchor for Hill n in QS | Older study; reporter may not equal native LuxR |
| 2 [fallback] | NCBI GEO published P. aeruginosa quorum-sensing transcriptomic time courses (search "GEO Pseudomonas quorum sensing" 2015–2024) | https://www.ncbi.nlm.nih.gov/geo/ | Public | ~20 datasets | Multi-strain replication of Hill n | Batch effects across studies |
| 3 [stretch] | Albeck et al. 2008 Mol Cell 30:11 single-cell caspase-3 activation FRET dynamics (apoptosis switch) | Supplementary movies + tables | Free supplementary | ~200 single-cell trajectories | Apoptosis member of the class; tests cross-system n band | Different reporter chemistry; needs FRET decoding |

## Validation procedure (concrete)

```bash
mkdir -p data/gardner_collins_toggle_switch_v2

# 1. Reconstruct Anetzberger 2009 dose–response from Wiley supplementary
# (manual extract; small N so feasible)
# columns: [autoinducer_conc_uM, luminescence_per_cell, cell_count]

# 2. Hill + hysteresis fit
python -m v4.cli validate gardner_collins_toggle_switch_v2 \
  --data data/gardner_collins_toggle_switch_v2/vharveyi_doseresp.csv \
  --method hill-bistability --bidirectional-scan \
  --alpha-band 2.5,4.5 --null-controls michaelis-menten,linear

# 3. Expected verdicts
#   PASS:  Hill n ∈ [2.5, 4.5], hysteresis ratio ∈ [0.30, 0.70] in fwd/bwd titration,
#          Hill preferred over Michaelis–Menten (n=1) by AIC
#   FAIL:  n outside band OR no hysteresis OR MM preferred
```

## Estimated workload

- Data acquisition: 4 h (Anetzberger supplementary requires manual digitisation if not pre-tabulated)
- Pipeline run: 3 h
- Verdict + writeup + cross-compare with v1: 4 h
- **Total: ~11 h / 1.5 days** (extra time vs v1 because of the explicit merge comparison)

## Risks specific to this class

1. **Merge collision**: must run with identical pipeline to v1 — same bootstrap seed, same priors — to make the comparison fair.
2. Hysteresis observability requires *both* forward (low→high inducer) and backward (high→low) titrations; many QS datasets only have forward — pre-screen.
3. Quorum-sensing Hill n estimates in the literature span 2–6 with assay-dependent bias; document assay (luminescence vs transcriptional vs proteomic) in the verdict.

## Priority

⭐⭐⭐⭐ (rationale: textbook mechanism; needed for v1 merge decision; modest data hunting required)

## Dependencies

- `scipy.optimize`, `lmfit`, `numpy`
- Optional: `flowio` if working with raw flow-cytometry FCS files
- No paid API
- Storage: < 100 MB
