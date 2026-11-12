# Reddit cross-posts — arXiv launch — 2026-05-24

**Posted**: T+1 day after arXiv (Wednesday US mid-morning).
**Targets**: r/Physics, r/MachineLearning, r/datascience.
**Companion**: `reddit-2026-05-15.md` already has /r/Physics + /r/datascience.
This doc adds **/r/MachineLearning** (different framing — methodology +
LLM-in-the-loop curation angle) and **updates** the existing two with
the arXiv ID + the published-failure framing.

**Subreddit rules summary** (read before posting):

- **r/Physics**: self-posts only; submit-link-and-discuss flair is preferred.
  No "what is the physics of X" generic questions. arXiv link in body, not
  title.
- **r/MachineLearning**: [R] flair for research, [P] for project. Discussion
  posts must include either code or paper. Self-promotion blast = ban-able.
  Standard etiquette: lead with the methodology, not the product.
- **r/datascience**: no direct self-promotion in title; "Sharing a project"
  framing acceptable. Mod-mail before posting if you have < 100 karma on
  the subreddit (we should already meet this).

---

## Post 1 — /r/Physics

**Title**: *17 cross-domain SOC systems, single Clauset MLE pipeline, 4 pre-registered failures — arXiv preprint released today*

**Flair**: `Research`

**Body**:

> Sharing the preprint of a project I have been working on — at the
> intersection of self-organized criticality, statistical methodology, and
> LLM-assisted scientific curation. Preprint went live today on arXiv:
> **arXiv:ARXIV_ID_PENDING** (cond-mat.stat-mech primary, physics.data-an
> cross-list).
>
> **The question.** Universality classes in statistical physics describe
> phase transitions across systems that look nothing alike — Ising-like
> behavior in fluids, magnets, percolation, opinion dynamics. The natural
> question: does the *same* idea, with the *same* statistical pipeline and
> *no per-domain tuning*, transfer to noisy empirical domains — financial
> contagion, neural avalanches, DeFi liquidations, wildfires, GitHub
> stars, citation cascades?
>
> **The pipeline.** One frozen Python module, `v4/lib/soc_pipeline.py`,
> 339 LOC. Clauset–Shalizi–Newman 2009 discrete MLE: KS-optimal `xmin`,
> Hill `alpha`, block-bootstrap CIs on the exponent, Vuong likelihood-ratio
> tests against lognormal and exponential. No per-system tuning anywhere
> downstream.
>
> **The discipline.** Three commitments to make the framework falsifiable,
> not confirmatory:
>
> 1. **Pre-registered exponent bands** — every claimed universality class
>    declares its expected band in a YAML committed to the repo *before*
>    data is fetched. `pre_registered_at` timestamps are git-anchored. Out-
>    of-band fits are FAIL, not retroactively re-classified.
> 2. **Null controls** — four synthetic nulls (uniform, exponential,
>    lognormal, shuffled) go through the same pipeline. A framework that
>    does not reject them is broken; ours rejects all four.
> 3. **Adversarial reporting** — every pre-registered system gets a
>    verdict, regardless of outcome. The 4 published FAILs/PARTIALs are
>    paired with the 13 positives in a public ledger.
>
> **Current state.** 13 of 17 pre-registered systems land in-band. The 4
> non-passes: 2023 CVE high-severity disclosures (Vuong → lognormal), NYC
> FDNY 2023 fire dispatch unit sizes (CI excludes registered band),
> r/wallstreetbets post cascades (PARTIAL — tail-only), S&P 500
> walk-forward trading signal commercial fork (INCONCLUSIVE — Sharpe
> lift indistinguishable from zero).
>
> **Honest limitations.** The LLM critic ensemble is currently within-vendor
> multi-decoding (3x DeepSeek at varied temperature), not cross-architecture;
> the architecturally diverse version is partly blocked by region routing
> for some vendors. One v0.3 collapse statistic (`r_shape`) was a
> combinatorial artifact, fixed in v0.4 with surrogate-null permutation
> tests. Several `alpha` estimates (S&P 500, GitHub stars) sit close to the
> inverse-cubic boundary with CIs overlapping classical regimes. The
> hardest test — predicting whether a *new* system will pass — is the
> active replication round.
>
> **Artifacts.** Code MIT, dataset CC-BY-4.0.
>
> - Preprint: https://arxiv.org/abs/ARXIV_ID_PENDING
> - Repo: https://github.com/dada8899/structural-isomorphism
> - Dataset DOI: https://doi.org/10.5281/zenodo.19615170
> - Live demos: https://beta.structural.bytedance.city /
>   https://phase.bytedance.city
>
> **AMA-ready, happy to discuss limitations.** Specifically interested in
> critique on (a) band assignment for the boundary-case systems, (b)
> whether the within-vendor B3 ensemble actually buys what a
> multi-vendor B4 would, (c) any system in the 13 you think should not
> have passed under the pre-registered protocol.

---

## Post 2 — /r/MachineLearning

**Title**: *[R] LLM-in-the-loop dataset curation with adversarial multi-vendor critics — 63-pair cross-domain dataset on Zenodo + open methodology paper*

**Flair**: `Research`

**Body**:

> Releasing today: an open dataset + companion methodology paper that may
> interest folks who work on LLM-assisted scientific curation, reproducible
> data pipelines, or empirical heavy-tailed analysis. The framing is
> methodology-first; empirical results are secondary.
>
> **What's released:**
>
> - **arXiv preprint**: ARXIV_ID_PENDING (cond-mat.stat-mech, physics.data-an).
>   *Adversarial Pre-Registration as Anti-p-Hacking Methodology*.
> - **Dataset SIBD-63** on Zenodo (DOI:
>   [10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)) —
>   63 A-level cross-domain candidate pairs, each with shared equation,
>   variable mapping, provenance, and a *vote vector* from a 4-vendor
>   LLM critic ensemble (Claude Sonnet, DeepSeek v4, Kimi K2.5, GLM-5).
> - **Code** (MIT): https://github.com/dada8899/structural-isomorphism.
>   PyPI: `pip install structural-soc-pipeline`.
>
> **LLM curation methodology that may interest this sub:**
>
> 1. **Cross-vendor adversarial voting**. Each candidate pair is shown to
>    four LLMs from different vendors. Each votes one of
>    `KEEP / REJECT / SPLIT / MERGE` with a written rationale. No single
>    vendor can wave a pair through; unanimous KEEP is the bar for the
>    A-tier dataset. Vote vectors are released alongside the data so you
>    can rebuild the curation step with a different critic family.
> 2. **Statistical pipeline ensemble** (separate from curation). Currently
>    within-vendor multi-decoding (3x DeepSeek at varied temperature).
>    The architecturally diverse version (B4: Claude Opus + GPT-5 +
>    DeepSeek + Kimi + GLM-5) is partly blocked by region routing for
>    some vendors. We document this explicitly rather than presenting
>    B3 as cross-vendor.
> 3. **Pre-registered exponent bands.** Each scientific claim attached to
>    a dataset entry has a YAML pre-registration committed to git before
>    data fetch. The protocol records FAIL where the data does not
>    support the band. Of 17 pre-registrations, 4 returned PARTIAL/NULL/
>    FAIL/INCONCLUSIVE. They are published in the paper alongside the 13
>    PASSes.
>
> **Why this might matter for ML folks:** the LLM-as-judge literature has
> mostly compared LLM judges against human gold labels. We're trying a
> different test — can a multi-vendor critic ensemble be a reproducible
> *first-pass filter* in scientific data curation? The vote-vector
> release lets you test whether your favorite open-weight model would
> have agreed.
>
> **AMA-ready.** Particularly interested in feedback on (a) whether the
> 4-vendor critic ensemble actually buys what the methodology claims,
> (b) what additional null controls would meaningfully strengthen the
> falsifiability claim, (c) whether the SIBD-63 LLM curation step would
> survive a re-run with a different critic family.

---

## Post 3 — /r/datascience

(Update of `reddit-2026-05-15.md` Post 2 — replaces "arXiv: pending" with the
real ID.)

**Title**: *Sharing an open falsifiable cross-domain data pipeline + 63-pair LLM-curated dataset, with 4 published negative verdicts — arXiv today*

**Body**: See `reddit-2026-05-15.md` Post 2, with the following diff:

- Replace line `arXiv: pending` → `arXiv: https://arxiv.org/abs/ARXIV_ID_PENDING`
- Add at end: *"Just went up on arXiv today; HN thread is at [link added on launch day]; happy to engage in either thread."*
- Update the "Limitations I want to be direct about" section to call out the **4 published negatives** as the headline detail (the existing draft has it lower).

---

## Posting cadence

- /r/Physics: T+1 Wed 10:00 ET
- /r/MachineLearning: T+1 Wed 13:00 ET (3-hour stagger from /r/Physics so we are not split-attention)
- /r/datascience: T+2 Thu 10:00 ET (one-day stagger to let /r/Physics + /r/ML discussion settle)

## Engagement strategy

- **First 2h after each post**: respond to every top-level comment within 30 min
- **AMA flair on the original** if a Reddit moderator suggests it; do not request unsolicited
- **DO NOT cross-link** the three posts to each other in body text. Reddit auto-detects cross-posting and demotes self-promotion patterns. Each post lives standalone.
- **For r/MachineLearning specifically**: the [R] flair carries strict expectations. The post body must have a code link AND a paper link in first 200 chars or it gets removed by AutoModerator.

## Failure modes to avoid

- Don't post to r/algotrading even if the phase detector seems on-topic. It is
  not a trading-signal product, and r/algotrading will (correctly) interpret
  the "near critical" labels as financial advice. We pre-empt this by
  staying off that sub.
- Don't post to r/Anthropic or r/LocalLLaMA. The B3 ensemble is multi-decoding,
  not cross-architecture; framing it as an "LLM project" oversells.
- Don't engage with comments that fork into "but what about [adjacent
  scientific topic we did not study]". Polite redirect to the paper's § 8
  roadmap; do not adjudicate scope expansions in comments.
