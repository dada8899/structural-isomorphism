# LinkedIn B2B pilot probe — 2026-05-25

**Purpose**: surface 1–2 pilot users (academic lab / government risk function / hedge-fund quant risk desk) who would find a single-pipeline cross-domain "phenomenon screener" useful, after our walk-forward backtest came back null. This is a probe, not a sales post. We want use cases we have not thought of, not buyers.

**Tone anchor**: honest about the null result; specific about what the tool *does* (not what it might do); a single low-friction ask at the end (a 30-min walk-through with the full repo, no pitch deck).

---

## The post (~400 words)

We spent the last four months building a frozen, no-knob statistical pipeline that asks one question across very different scientific domains: does this dataset show the kind of power-law tail that signals self-organized criticality, and does the fitted exponent land where the literature predicts?

The same 339 lines of Python — Clauset-Shalizi-Newman MLE, KS-optimal xmin, block-bootstrap CIs, Vuong likelihood ratios against lognormal and exponential — get called on neural avalanches, DeFi liquidation cascades, wildfires, FDIC bank failures, citation cascades, and 12 other systems. We pre-register the exponent band, in YAML, in a public git commit, before fetching the data. The pre-registration commit hash is the audit trail.

Two weeks ago we finished the most commercially loaded test of the whole programme: a walk-forward backtest on US equities, 2020–2024, asking whether our structural-phase classifier carries standalone alpha. The Sharpe lift versus SPY came in at -0.23. Annualized CAPM alpha was -0.24% with a t-stat of -0.02 — a clean null. Our pre-committed gate said: if lift is below +0.3, pivot the positioning. So we are pivoting.

Before we lock in the next product direction, we want to ask people we have not yet asked. The pipeline is real, the methodology is published (arxiv:PENDING_ID), the code is on PyPI today (`pip install structural-soc-pipeline`, PENDING_VERSION), and we have run it end-to-end on 17 pre-registered systems with full PASS / FAIL / NULL / PARTIAL / INCONCLUSIVE verdicts.

Specifically, if you work in one of these and would find a single-pipeline cross-domain validator useful, we would like to talk:

1. **Macro-prudential risk monitoring** (central bank, regulator, large bank risk function) — screening heterogeneous event streams (defaults, credit events, market microstructure breaks) for shared critical signatures.
2. **Clinical or biomedical anomaly screening** (hospital network, public-health agency, biotech) — flagging time-series with the same statistical fingerprint as known cascade phenomena (sepsis onset, outbreak ignition, drug-event clustering).
3. **Supply-chain phase-shift detection** (logistics, energy, semiconductor capacity planning) — identifying when an order/inventory time-series is approaching a regime-change rather than fluctuating around equilibrium.

The ask is small. We will send you the full repo, the three PyPI packages, the Zenodo dataset (DOI:PENDING_DOI), and book a 30-minute walk-through. No cost, no commitment, no pitch deck. We want to know whether the pipeline solves a problem you already have — or whether it solves a problem nobody actually has, which is also a useful thing to know early.

Reply or DM. Happy to talk in English or Chinese.

---

## Recommended hero image (described, not generated)

A single horizontal banner image, 1200 × 627 (LinkedIn-recommended OG size). Left two-thirds: a clean log-log plot on a white background, showing the CCDF of one of our PASS systems (DeFi liquidation cascades, α ≈ 1.64) and the CCDF of our FAIL system (CVE high-severity disclosures, α = 2.668) overlaid in two muted colours (#1a4d8f for PASS, #c14b3a for FAIL). Both with their pre-registered bands shaded. Right one-third: three lines of text in a serif system font (Charter / Iowan Old Style), left-aligned:

> One pipeline.
> Seventeen systems.
> Thirteen PASS, four published failures.

No logo, no decorative elements, no gradient. The visual is the data plus the receipts. Style references: the Apple Health "Cycle Tracking" research-page hero, the Stratechery weekly chart style, the Bear app's writing-mode screenshots.

## Recommended hashtags (3)

- `#ComplexSystems`
- `#OpenScience`
- `#QuantResearch`

(We deliberately avoid `#AI`, `#MachineLearning`, and `#DataScience` — they are too broad, the post is not about an AI product, and the surfacing audience we want is narrower.)

## Send timing

Post **48 hours after the arXiv preprint goes live**. The arXiv ID needs to be live and the abstract page indexable before this post drops, because every concrete number in the post (Sharpe lift, alpha t-stat, 17/13/4 funnel, three PyPI packages) is also in the preprint and the LinkedIn post should be the *short* version that points to the *long* version, not the other way around. T+48h also clears the first wave of arXiv-cross-list traffic so this post recruits a fresh audience (LinkedIn professional graph) rather than competing with the arXiv-day traffic on Twitter and HN.

Best slot: **Wednesday 09:30–10:30 local Asia time** (corresponds to Tuesday evening US East Coast, which catches both Asia daytime and US end-of-day LinkedIn scroll). Avoid Monday (post-weekend noise) and Friday (decay before weekend).

---

## First reply template (if someone responds, ~150 words)

> Thanks for reaching out. Short version of what we'd do next:
>
> 1. I'll send you three links right now: the GitHub repo (MIT), the Zenodo dataset DOI (CC-BY-4.0), and the PyPI install line. You can poke without committing to anything.
>
> 2. If you want a guided 30-minute walk-through, I have slots [INSERT 3 SPECIFIC HALF-HOUR SLOTS in the next 5 working days, across 2 timezones]. Pick whichever works. Zoom or Google Meet, your call.
>
> 3. Before the call, one question that helps me prepare: in your team's current workflow, what does the *closest existing tool* to this look like — Splunk-style alerting, a domain-specific change-point detector, manual review by a senior analyst, nothing at all? I'd rather build the walk-through against your real baseline than my imagined one.
>
> Looking forward to it.

*Document word count: ~780.*
