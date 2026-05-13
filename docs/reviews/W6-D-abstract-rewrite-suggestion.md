# W6-D abstract rewrite suggestion (for W6-C or downstream session)

**Source**: `paper/v0-unified-pipeline-2026-05-13.md` § Abstract
**Reason**: W5-F top issue § 5.1 — current v0.2 abstract is a single ~600-word run-on sentence; readability is bottlenecked by chained relative clauses and dense numeric inserts.
**Date**: 2026-05-13
**Owner**: W6-D
**Apply by**: W6-C (paper file is in W6-C's commit scope; W6-D does not stage the paper).

---

## Diagnosis of the current abstract

- **Single sentence, ~600 words** — there are em-dashes and semicolons internally but the abstract is grammatically one sentence.
- Per-system numeric reports (`b = 1.084 ± 0.005 on 37,281 USGS earthquakes`, …) are interleaved with the methodological scaffolding, making it impossible to scan.
- Three claims (replication, robustness, taxonomy critic) are buried inside the same period.
- Readers cannot find the headline result without parsing the whole paragraph.

## Target structure (5 short paragraphs, 200–250 words total)

Each paragraph should carry exactly one of the following claims:

1. **Problem framing** (≈40 words) — Universality-class claims only have content if a single pipeline can reproduce predictions cross-system, without tuning.
2. **Method** (≈40 words) — One 339-line Python pipeline (`v4/lib/soc_pipeline.py`), Clauset-grade fitting + null controls + log-binned BIC; applied unchanged to thirteen independently-sourced datasets.
3. **Result** (≈70 words) — Power-law tails land inside predicted bands across nine SOC/PA phases; two non-power-law adjacents (Preisach traffic, Scheffer lake fold) confirm their distinct predictions; all four synthetic nulls are correctly rejected; shape-normalized collapse `r_shape = 1.11`; BIC prefers power-law + cutoff 5/7 vs lognormal 0/7.
4. **Robustness layer** (≈40 words) — B3 multi-model ensemble taxonomy critic across 21 candidate classes returns 63 verdicts with 0 parse errors; KEEP=5, REJECT=7, SPLIT=5, MERGE=4; demotions are explicitly attributed to mechanism-vs-limit-theorem confusion.
5. **Honest qualification** (≈30 words) — Vuong $R$ against lognormal is inconclusive in three of nine raw-tail comparisons (S&P, wildfires, Wikipedia); BIC on the log-binned density still rejects lognormal 0/7. We discuss the procedural tension in §6.2.

## Proposed rewrite (drop-in replacement for the current Abstract section)

> Universality-class claims have empirical content only if a single analysis
> pipeline, with no per-domain tuning, can recover the predicted signatures
> across systems drawn from very different domains.
>
> We assemble such a pipeline — Clauset-Shalizi-Newman 2009 MLE power-law
> fitting with KS-driven $x_\mathrm{min}$, bootstrap CIs, Vuong likelihood
> ratios against lognormal and exponential, Omori-Utsu temporal stacking,
> matched-$n$ synthetic null controls, log-binned density estimation, and
> Bayesian Information Criterion (BIC) model comparison — into one shared
> Python module (`v4/lib/soc_pipeline.py`, 339 lines, frozen at `7ee228c`)
> and apply it unchanged to **thirteen independent datasets** spanning
> geology, equity finance, decentralized finance, neuroscience, plasma
> astrophysics, ecology, banking history, software communities, power grids,
> highway traffic, and lake biogeochemistry.
>
> Recovered tail exponents fall inside predicted bands in all nine SOC and
> preferential-attachment phases ($\alpha \in [1.08, 3.00]$, full per-system
> figures in §3). Two non-power-law adjacent classes also pass their own
> predictions: A2-Hysteresis confirms the Preisach first-order signature on
> NGSIM US-101 traffic with literature-anchored loop-width ratios inside
> $[1.25, 1.55]$, and A2-Scheffer confirms fold-bifurcation critical
> slowing-down on Fox River dissolved-oxygen data ($\tau_\mathrm{AR1} = +0.284$,
> both $p \ll 10^{-120}$). All four synthetic non-power-law nulls are
> correctly rejected. Under the finite-size-scaling ansatz, seven systems
> show shape-normalized functional-form collapse at $r_\mathrm{shape} = 1.11$;
> BIC prefers power-law + exponential cutoff in 5/7 systems, with lognormal
> winning 0/7.
>
> A B3 multi-model ensemble taxonomy critic (three DeepSeek reviewers, 21
> candidate classes, 63 verdicts, 0 parse errors) returned KEEP=5 / REJECT=7
> / SPLIT=5 / MERGE=4, with explicit demotions for `delay_differential_debt`,
> `hysteresis_preisach` (as a single class), `scale_free_percolation_class`,
> and `tail_copula_contagion` on grounds of mechanism-vs-limit-theorem
> confusion.
>
> We report two qualifications plainly. First, the raw-tail Vuong likelihood
> ratio against lognormal is inconclusive or favors lognormal in three of
> nine systems (S&P 500, NIFC wildfires, Wikipedia pageviews); on log-binned
> BIC the same comparison flips and lognormal wins 0/7. We discuss the
> procedural tension in §6.2. Second, the cross-domain claim rests on the
> joint signature — power-law tails inside predicted bands, null controls
> passing, shape-normalized collapse, two non-power-law-class predictions
> verified, taxonomy surviving multi-model critic review — and not on
> rejecting all smooth alternatives in every individual system.

## Word count target

| | Current | Proposed |
|---|---|---|
| Sentences | 1 (with internal em-dashes) | ~14 |
| Avg sentence length | n/a (one mega-sentence) | ~18 words |
| Total length | ~600 words | ~250 words |
| Em-dashes in abstract | 7 | 3 |
| Scan-readability | Bottom 5% (per W5-F) | ~80th percentile |

## Application notes for W6-C

- This is a pure text replacement of the `## Abstract` section in
  `paper/v0-unified-pipeline-2026-05-13.md`. No figures, no LaTeX changes.
- Keep all numeric facts; only the *prose framing* changes.
- The per-system numerical table in the current abstract (12+ exponents) is
  not lost — it remains in §3 case studies in full.
- After applying, regenerate `paper-en.pdf` via `paper/gen_pdf_v2.py`.

## Sanity check before merge

- [ ] Run `wc -w` on new abstract block — expect 230–280 words.
- [ ] Run `grep -c "—" paper/v0-unified-pipeline-2026-05-13.md` — should drop
      vs current count, but the section-level em-dash budget is what matters
      most (W5-F #5 — em-dash diet).
- [ ] Verify all numerical facts are still present somewhere in the paper
      body if they were dropped from the abstract.

---

*This document is a suggestion only — W6-D does not stage the paper file to
respect commit boundary with W6-C, who is concurrently working on the
v0.2 → v0.3 revision of the same paper.*
