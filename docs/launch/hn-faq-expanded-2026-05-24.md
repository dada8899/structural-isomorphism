# HN expanded FAQ — 20 Q&A — 2026-05-24

**Purpose**: unblock HN readiness § 1 "FAQ — 20 high-frequency Q&A".
**Companion**: `hn-launch-readiness-2026-05-24.md` § 3 already lists Q1–Q10.
This doc keeps Q1–Q10 unchanged + adds Q11–Q20 covering objection categories
the original list missed.

**How to use on launch day**: paste this entire doc into a Google Doc tab
open in a browser pinned beside the HN thread. Cmd+F by keyword to locate
the answer in ≤ 5 seconds. Founder responds within 15 minutes of each
top-level comment.

**Tone discipline**:
- Acknowledge concern in the first sentence
- Cite a specific repo file or paper section in the second sentence
- Promise a concrete next action where applicable (issue link, follow-up post)
- Length: 80–160 words per answer. HN penalizes both walls of text and
  curt non-answers.

---

## Original Q1–Q10 (from hn-launch-readiness § 3)

See `hn-launch-readiness-2026-05-24.md` § 3 for full text. Topics:

1. "13/13 in-band feels like p-hacking"
2. "Several alpha values sit near 3.0"
3. "Why no Claude / GPT-5 in ensemble?"
4. "Is this financial advice?"
5. "Is the alpha real?"
6. "How does this differ from Bloomberg / Sentieo?"
7. "Power laws are everywhere"
8. "Open source?"
9. "Sample size — 13 systems is small"
10. "How do you make money?"

---

## New Q11–Q20

### Q11: "Power-law fits are notoriously fragile — Clauset's own paper says so. Why trust your αs?"

> Stipulated, and we use Clauset's own diagnostic stack precisely because of
> that. Every system gets (a) KS-optimal `xmin` selection so we are not
> cherry-picking the tail, (b) Vuong tests against lognormal AND exponential
> alternatives — if either wins, the power-law claim is dropped, and (c)
> block-bootstrap CIs on `alpha` so the band-overlap test uses the full
> uncertainty interval, not a point estimate. Of our 17 pre-registrations,
> 4 returned non-power-law verdicts (PARTIAL / NULL / FAIL / INCONCLUSIVE),
> which is exactly the failure rate you would expect from a non-confirmatory
> protocol. See `paper/anti-phacking-unified-2026-05-15.md` § 4 for the
> Vuong + bootstrap protocol.

### Q12: "What about the lognormal alternative? Reality is usually lognormal."

> Concur — and this is exactly what the Vuong test in our pipeline answers.
> For each candidate system, we report `R` (Vuong test statistic) and `p`
> for lognormal-vs-powerlaw and exponential-vs-powerlaw. Where the test
> favors lognormal (e.g. our NYC FDNY fire dispatch dataset) we record
> PARTIAL or NULL, not PASS. The full Vuong table is in
> `paper/anti-phacking-unified-2026-05-15.md` Table 3. We do not claim
> "this is a power law" — we claim "the data is not distinguishable from
> a power-law in a pre-registered band, and the band test would have
> rejected a re-tunable lognormal fit".

### Q13: "Pre-registration without an OSF / PRP registry is just timestamps in your own repo."

> Fair critique. Current pre-registration uses git timestamps on
> `v4/preregistration/<system>.yaml` files. The git commit hash + the
> public GitHub log are a verifiable timestamp anchor — you can verify
> the pre-registration commit on `dada8899/structural-isomorphism`
> predates the data-fetch commit. The next replication round (Bitcoin
> Cash, FluNet ILI, Flickr cascades) will dual-register on OSF as an
> external witness. We agree the dual-registration is stronger and have
> filed it as a roadmap item — see paper § 8 "next batch".

### Q14: "What's the type-I error rate of the band test? Have you computed it?"

> Yes, on the null controls. We run four synthetic nulls (uniform,
> exponential, lognormal, shuffled-empirical) through the same pipeline
> with the same pre-registered bands. The band test rejects all four in
> 100% of bootstrap replicates — i.e. the synthetic-null type-I rate is
> effectively 0 at the band level. The *empirical* type-I rate (would a
> *real* system that "shouldn't" pass actually fail?) is what the
> next-batch replication round tries to estimate. Currently this is a
> known gap; we own it in paper § 4.

### Q15: "How do you choose the pre-registered band? Couldn't you just pick a wide one to guarantee a hit?"

> Bands come from published exponent values for the canonical universality
> class. For example: SOC sandpile predicts `alpha ∈ (1.4, 1.6)`; Ising
> 2D `alpha` is theoretical at `15/8 = 1.875` with classical-MFT-corrected
> band; neural-avalanche `alpha ∈ (1.4, 1.7)` (Beggs & Plenz 2003). Bands
> are inherited, not engineered. The yaml files have a `source_paper` field
> per band. You could argue the bands could be inherited from a *different*
> paper that happens to fit better — and yes, that's a degree of freedom.
> Our defense: every band file commits the source citation, so a critic
> can swap in their preferred band and re-run the verdict in ≤ 1 hr.

### Q16: "How long does the pipeline take to run end-to-end?"

> For one system, ~3 min on a laptop M2 — dominated by the 1000-rep
> block bootstrap. For all 17 pre-registered systems with full nulls and
> Vuong tests, ~45 min single-threaded; ~12 min parallelized over 4
> cores. The frozen pipeline is `v4/lib/soc_pipeline.py` (339 LOC) — no
> GPU, no external API calls, no async. The LLM critic ensemble (which is
> *not* part of the statistical pipeline — only used in dataset curation)
> takes ~30 min for one critic pass over SIBD-63 at moderate cost (~$3 per
> full pass).

### Q17: "Why is the phase detector consumer-grade if the methodology is research-grade?"

> The phase detector is a research preview, not a finished product. It
> exists to make the methodology touchable — you can put in a ticker and
> see (a) the dynamics_family classification, (b) the extracted source
> quote justifying that classification, and (c) the prompt + model hash
> used. It explicitly does NOT predict price; it extracts a structural
> state from disclosure language. The footer disclaimer is on every
> page, and the methodology page (linked from every page) is in plain
> English. If you think any of the UX makes it look more predictive
> than it is, open an issue — we'll fix it before any further launch.

### Q18: "Have you talked to Sornette / Clauset / Plenz / Priesemann?"

> Outreach drafted (see `docs/community/launch/senior-outreach-2026-05-15.md`)
> but not yet sent. The plan is to send T+3 to T+14 after this launch,
> not before — they get the published preprint + the public reception
> as context, so the cold email lands with more substance and they can
> see what's already on record. Plenz first (T+3) because the neural
> sub-paper most needs his eye. Sornette last (T+14) because his comments
> typically focus on the dragon-king finance sub-paper which has had
> the most independent attention.

### Q19: "Why both a marketing site AND a research preview product? Pick a lane."

> Honest answer: we don't know yet whether the right business is
> a methodology-publishing org or an alpha-screener product. The v0.2
> backtest gates that decision. If Sharpe lift ≥ 0.5 → lean into
> alpha-screener (B2B Structural Index API + retail Pro tier). If
> ≤ 0.1 → pivot to a Substack-style narrative product on top of the
> open methodology. The two sites are a deliberate hedge until the
> data picks the lane. The README states this explicitly.

### Q20: "Why China? Why not US-based?"

> The author is based in China; the project is in English; the code is
> on GitHub (`dada8899/structural-isomorphism`); the dataset is on
> Zenodo (CERN-hosted, EU); the preprint is on arXiv (Cornell-hosted, US).
> The only China-specific aspect is the VPS hosting for the marketing
> site (Tencent Cloud Singapore). One real consequence: B4 LLM ensemble
> is blocked partly by Anthropic + Google region routing from China IPs.
> We acknowledge this in v0.3 § 6 and v0.4 § 8 — within-vendor B3
> is what's reproducible from our infra; cross-architecture B4 would be
> straightforward from a US/EU IP.

---

## Index — quick keyword lookup

| Topic | Q# |
|---|---|
| p-hacking / 13-of-13 / coverage | Q1, Q9, Q13, Q14 |
| boundary alpha / α≈3 / power-law fragility | Q2, Q11, Q12 |
| LLM ensemble / B3 vs B4 / vendor diversity | Q3, Q20 |
| Financial advice / disclaimer | Q4, Q17 |
| Backtest / Sharpe / alpha | Q5, Q19 |
| Competitor positioning | Q6 |
| Methodology rigor | Q7, Q11, Q13, Q14, Q15 |
| License / openness | Q8 |
| Pricing / monetization | Q10, Q19 |
| Pre-registration / OSF | Q13, Q15 |
| Performance / reproducibility | Q16 |
| Domain experts / outreach | Q18 |

---

## Tone guard-rails

The 2 things to NEVER say on HN, regardless of provocation:

1. **"Trust me"** — replace with "here is the file / here is the commit hash"
2. **"It works"** — replace with "this is what the pipeline returned; here
   is the verdict criterion"

The 2 phrases that work disproportionately well on HN:

1. **"You're right that..."** then state the concession explicitly
2. **"Here's the file / commit / line number"** with an actual link

The 1 fatal mistake:

- Editing or deleting comments. HN flags all edits visibly; do not edit
  a response after first publish unless the edit is purely typo correction
  in the same minute.
