# Publishing our failures: a -0.23 Sharpe lift, a 33% rejection rate, and what cross-domain science needs more of

*Companion to the arXiv launch (arxiv:PENDING_ID). Repo, dataset, and PyPI links at the bottom.*

---

## The moment we decided to publish the failure

Two weeks ago we finished a walk-forward backtest of our cross-domain "phase classifier" on 100 US tickers, 2020–2024, 59 monthly rebalances. The Sharpe lift versus SPY was **-0.23**. Annualized CAPM alpha came in at **-0.24% with a t-statistic of -0.02** — indistinguishable from noise, and on the wrong side of zero. We had pre-committed, in writing, that any Sharpe lift below +0.3 would trigger a positioning pivot rather than another round of tuning. Our first instinct was not to debug the pipeline. It was to publish the verdict.

This post is about why. It is also about a second failure we published the week before — a reject-aware critic ensemble that demoted 33% of our auto-curated "universality classes", including four classes a single strong reviewer had voted to keep. Both failures were predictable consequences of taking the methodology seriously. Both made the project better. We think there is a generalisable lesson here for the way cross-domain science is reported.

## The first failure: a -0.23 alpha on the only test that pays for itself

The walk-forward design was simple by construction. Our D1 classifier assigns each ticker to a structural phase (`stable`, `approaching_critical`, `at_critical`, `reversed`, `recovering`) from public signals. We pre-committed before fetching prices that the `near_critical` cohort — the union of `approaching_critical` and `at_critical` — would, if the classifier carried any standalone alpha, outperform SPY on a risk-adjusted basis over the 2020–2024 window. The cohort that fell out of the 2026-05-13 snapshot contained 29 names spanning biotech, EVs, energy, streaming, and fintech.

The numbers, reported in `backtest/results/walk-forward-v0.2.md`, were unambiguous. Cumulative return came in at +111.7% versus SPY's +95.8%, which sounds like a win until you adjust for risk: annualized Sharpe was 0.60 for the cohort versus 0.84 for SPY, max drawdown was -47.8% versus -24.0%, and the cohort's beta against SPY was 1.40. We did not beat the benchmark; we just took more risk to roughly track it. The CAPM regression made that explicit. Alpha = -0.020% monthly, t-stat = -0.02, R² = 0.535. The cohort behaves like a slightly noisier, more drawdown-prone version of SPY plus 40% leverage. There is no alpha here to defend.

What matters for this post is what we did *not* do. We did not search for an `xmin` cut that would have improved the Sharpe. We did not switch from monthly to weekly rebalances to see if turnover absorbed some of the loss. We did not exclude 2022. We did not re-define `near_critical`. We did not try the next twenty obvious things that would have eventually delivered a flattering number. That kind of post-hoc rescue is exactly the failure mode pre-registration is designed to prevent, and W7-D § 3 of our methodology paper had written the pivot rule down before any prices were fetched: Strong (lift ≥ +0.5) → lean into alpha-screener positioning; Inconclusive (+0.3 to +0.5) → extend evidence on a wider universe; Null (< +0.3) → pivot to structured-research narrative. The verdict on -0.23 was already decided. The only honest action was to write it up.

The single-snapshot caveat matters and we report it openly. Our D1 labels are dated 2026-05-13 and applied ex-post to 2020-2024 returns, which makes this an ex-post discriminative test (does today's structural label correlate with past risk-adjusted returns?) rather than a true ex-ante forecast. A clean walk-forward test requires monthly D1 snapshots reconstructed at each historical timestamp, which is the v0.3 roadmap. The point of v0.2 was not to ship a tradable signal; it was to honour the gate.

## The second failure: 33% of our universality classes were wrong

The other failure came from the methodology side. Our reject-aware pipeline (preprint `paper/c4-reject-aware-pipeline-2026-05-13.md`) takes an LLM-auto-curated set of candidate "universality classes" — bundles of cross-domain phenomena claimed to share a critical mechanism — and runs each through two adversarial critic stages before any quantitative prediction is generated. B1 is a single Claude Opus reviewer told to apply the Clauset-Shalizi-Newman (2009, pp. 661–703) standard: shared equation form, shared scaling exponents, shared critical mechanism. B3 is a three-decoding DeepSeek ensemble at temperatures 0.0, 0.0, and 0.6 with a deliberately adversarial dissenter persona on the third decoding.

On a 21-class auto-curated panel, B1 alone rejected 3 classes outright — a 14.3% rejection rate. B3 rejected 7 — 33.3%. Four of those seven additional rejections were classes B1 had voted KEEP, and that is where the methodological interest lives. The four demotions, documented in §4.3 of the c4 preprint, are:

- **`delay_differential_debt`** (KEEP → REJECT). B1 read the shared delay-differential normal form $dx/dt = f(x(t-\tau)) - \mu x(t)$ as evidence for a universality class. Two of the three B3 reviewers flagged the textbook problem: no shared scaling exponents are identified — only a generic Hopf-bifurcation normal form, which is far weaker than what Clauset-Stumpf-Porter requires. This is the *mechanism-vs-limit-theorem confusion* in its purest form: shared equation *form* mistaken for shared *mechanism* and shared *exponents*.
- **`tail_copula_contagion`** (KEEP → REJECT). Two systems can share a tail copula and have entirely incompatible underlying dynamics (Hawkes self-excitation vs network-cascade vs leverage feedback). The empirical Hawkes/copula fit on Aave, Compound, and MakerDAO DeFi liquidations (A2 #6) independently corroborated the B3 rejection downstream.
- **`scale_free_percolation_class`** (KEEP → REJECT). Percolation on scale-free networks gives quantitatively different exponents depending on the degree-distribution parameter γ. Calling the whole basin one class is a surface-similarity error.
- **`hysteresis_preisach`** (SPLIT → REJECT). The candidate class lumped magnetic hysterons, traffic-flow first-order transitions, and ecological saddle-node bifurcations together. These are mathematically incompatible bistability mechanisms wearing the same name.

The framing we now use, in the preprint and on the project site, is that 14% → 33% is the *summary statistic* and the four demotions are the *content*. A different panel and a different reviewer line-up will produce different numbers; what should be stable across panels is the pattern of error the filter surfaces — *generic mathematical framework masquerading as mechanism-defined universality class*. Stumpf and Porter's *Critical truths about power laws* (Science, 2012, pp. 665–666) is the canonical statement of why this matters: sharing a tail exponent is not enough.

## Why we publish both, and why we made it harder to retract

Negative results in cross-domain science are taxed twice. They are harder to write up because there is no positive headline to anchor on. And they are easier to bury because no journal asks where they went. The CVE pre-registration falsification we published a week earlier (`paper/cve-preregistration-fail-2026-05-14.md`) is a third instance from the same project: we pre-registered a power-law band α ∈ [1.5, 2.5] for daily-burst sizes of high-severity 2023 CVE disclosures, fetched 10,280 records, and the fitted exponent landed at **α = 2.668 with bootstrap CI [2.40, 2.98]** — outside the band, with Vuong tests decisively favouring lognormal (p = 0.002) and exponential (p = 0.0001) alternatives. The visible signature is the Patch Tuesday clustering of Microsoft's second-Tuesday release cadence, which is administrative burstiness rather than SOC critical dynamics. We pre-registered a clean SOC reading, we got an unambiguous falsification, and the FAIL verdict is now in the paper rather than in a discarded notebook.

What made these publications stick is not virtue. It was infrastructure. The arXiv preprint, the public GitHub repo, the Zenodo DOI (PENDING_DOI) for the SIBD-63 dataset, and the three PyPI packages (`structural-soc-pipeline`, `structural-preregistration`, `structural-critic-ensemble`, all PENDING_VERSION) collectively make the failures unforgeable. The pre-registration commit hash (`34f2a81` for the CVE band, `7ee228c` for the frozen SOC pipeline) lives in the git log. The walk-forward gate was written in W7-D § 3 before any prices were fetched. The B3 verdict matrix sits in `v4/results/B3_taxonomy_v2.jsonl` with every individual reviewer's rationale preserved. If we ever quietly walked back the -0.23 Sharpe or the 33% rejection rate, anyone with `git clone` could catch us. The technical setup is the credible commitment device — not the prose.

This is what we mean by *publishing failures with teeth*. A blog post saying "we got a negative result and we are pivoting" is cheap. A blog post backed by a frozen pipeline at a public commit, a tagged pre-registration YAML, a public dataset, and an installable package that anyone can `pip install` and re-run is a different artefact. The cost to retract is high enough that the methodology is the binding commitment, not the narrative around it.

The reason this matters for cross-domain science specifically is Halford's old observation (Halford 1992, *Analogical reasoning*, pp. 96–112): analogical reasoning fails predominantly through surface-feature retrieval, and the corrective is explicit relational-structure alignment. Modern LLMs are extremely good at producing fluent surface analogies and have no native incentive to police mechanism. The reject-aware filter is one operationalisation of the corrective. The walk-forward gate is another. The pre-registered exponent band is a third. All three only have teeth if the failures they produce are published, indexable, and irretractable.

## What we want from readers

The repo is MIT, the dataset is CC-BY-4.0, the PyPI packages are installable today. If you find a mistake in any of our 27 system fits — the 13 PASS verdicts, the 4 published failures (CVE FAIL, FDNY NULL, WSB PARTIAL, walk-forward INCONCLUSIVE), the 7 B3 rejections, or the 3 v0.2 caveats above — please file an issue against [github.com/dada8899/structural-isomorphism](https://github.com/dada8899/structural-isomorphism). If you can falsify a PASS by pointing at a different source paper's band, we will re-run on your band and publish the new verdict alongside the old one. That is the contribution model.

- Preprint: arxiv:PENDING_ID
- Repo: github.com/dada8899/structural-isomorphism
- Dataset: doi.org/PENDING_DOI (Zenodo SIBD-63)
- PyPI: `pip install structural-soc-pipeline` (PENDING_VERSION)
- Methodology paper: `paper/c4-reject-aware-pipeline-2026-05-13.md`
- Walk-forward report: `backtest/results/walk-forward-v0.2.md`
- CVE pre-registration failure: `paper/cve-preregistration-fail-2026-05-14.md`

*Word count: ~1480.*
