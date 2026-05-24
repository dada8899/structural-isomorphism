# Wave 2 outreach queue · 2026-04-17

After i18n deploys (A/B/C/D/E agents), run `scripts/send_wave2.py` (or create drafts manually from this file) to fire these 8 messages.

Links below currently use raw Chinese URLs. When i18n is live, swap to `?lang=en` variants OR direct GitHub/Zenodo links (also English) depending on what reads cleaner. Integration pass will do that swap before sending.

- **Site base**: `https://beta.structural.bytedance.city`
- **Post-i18n link pattern**: append `?lang=en` to any `/classes`, `/paper/*`, `/about` link
- **Always-English fallbacks**:
  - Zenodo: `https://doi.org/10.5281/zenodo.19615170`
  - GitHub repo: `https://github.com/dada8899/structural-isomorphism`
  - Individual paper MD on GitHub: `https://github.com/dada8899/structural-isomorphism/blob/main/v4/validation/{slug}/paper.md`

---

## PART 1 · Replies to existing threads (3)

### R1. Reply to Keith Holyoak (UCLA)

```yaml
to: kholyoak@g.ucla.edu
thread_id: 19d7d43f6053bec2
subject: (auto from thread)
```

```
Hi Keith,

Thanks for the pointer -- we hadn't benchmarked on AnaloBench yet, and will
give it a try. Our scope so far has been deliberately restricted to analogies
where the mapping bottoms out in a shared equation, because that gave us an
unambiguous empirical test. Running the pipeline through AnaloBench would
be a good way to probe whether the contrastive-learning signal survives when
the "shared structure" is relational/narrative rather than algebraic.

One related update: we finished a 5-domain empirical validation of the SOC
universality class (earthquakes / DeFi / S&P / neural / null) -- paper stack
at https://beta.structural.bytedance.city/classes?lang=en .

Best,
Qinghui
```

---

### R2. Reply to Dirk Helbing (ETH Zurich)

```yaml
to: dirk.helbing@gess.ethz.ch
thread_id: 19d7d4414f47902b
subject: (auto from thread)
```

```
Dear Professor Helbing,

Thank you -- that ("deeper connection vs. model transfer") is precisely
what we moved to test. The sharpest evidence we have is cross-*implementation*:
three DeFi protocols with engineering-distinct liquidation triggers (Aave V2
/ Compound V2 / MakerDAO, 43,065 events) converge to alpha = 1.57-1.68, the
same exponent USGS earthquakes sit at -- and sharply *different* from the
S&P 500's alpha ~ 3.0. That's the operational signature of detail-
independence SOC predicts; spin->opinion model transfers would not pass
this test. Null controls (Poisson / Gaussian) correctly refuse any power-law.

Full stack (5 companion papers): https://beta.structural.bytedance.city/classes?lang=en
Dataset: https://doi.org/10.5281/zenodo.19615170

Any thoughts welcome -- particularly on which social-physics transfers
you'd flag as least likely to pass this kind of cross-implementation test;
we'd like to add those as counterexamples.

Best regards,
Qinghui
```

---

### R3. Reply to Dashun Wang (Northwestern Kellogg)

```yaml
to: dashun.wang@kellogg.northwestern.edu
thread_id: 19d7d446f6d70eb6
subject: (auto from thread)
```

```
Hi Professor Wang,

Fair question -- validation was the reason we didn't stop at the retrieval
numbers. Short answer: we take an analogy class, freeze the exponent it
predicts, then run the *same* Clauset-Shalizi-Newman pipeline across
multiple independent real datasets PLUS a matched synthetic null. For the
SOC class we did this on five: USGS earthquakes (84k, alpha~1.67), DeFi
liquidations across three protocols (43k, alpha=1.57-1.68), S&P 500
(alpha~3.0, a different subclass), mouse V1 avalanches (DANDI, task-state
sub-critical), and Poisson/Gaussian synthetics (which correctly refuse any
power-law -- this is the critical check that rules out "the pipeline fits
power-laws to anything").

Five papers + code + data: https://beta.structural.bytedance.city/classes?lang=en
Dataset: https://doi.org/10.5281/zenodo.19615170

If the methodology passes your bar, we'd be happy to hear which analogy
class you'd most want to see validated next.

Best,
Qinghui
```

---

## PART 2 · A-group cold emails (5)

### A1. Didier Sornette (ETH Zurich)

```yaml
to: dsornette@ethz.ch
subject: SOC discrete-threshold vs continuous-diffusion: DeFi liquidation cascades as a new test case
```

```
Dear Professor Sornette,

Your work bridging Omori-Utsu aftershock laws to financial crashes and
"dragon kings" has shaped how a generation thinks about self-organized
criticality across domains. We recently completed a cross-domain empirical
test of exactly that premise.

We ran the same Clauset-Shalizi-Newman power-law fitting pipeline on five
independent domains -- USGS earthquakes, S&P 500 daily returns, DeFi
liquidation cascades (43,065 events across Aave V2, Compound V2,
MakerDAO), mouse cortical avalanches (DANDI 000006), and synthetic null
controls. DeFi and earthquakes cluster at alpha ~ 1.6 (discrete-threshold
subclass), S&P 500 sits at alpha ~ 3.0 (continuous-diffusion subclass),
and the null controls correctly refuse a power-law. The cross-protocol
DeFi agreement is particularly striking: three engineering-distinct
liquidation mechanisms converge to the same scaling exponent -- an
operational version of the universality prediction you've argued for.

Papers and data:
- https://beta.structural.bytedance.city/classes?lang=en
- SIBD-63 dataset: https://doi.org/10.5281/zenodo.19615170

Any reaction welcome -- particularly on whether the DeFi subclass framing
holds up and on what would be the sharpest second test.

Best regards,
Qinghui Wan
```

---

### A2. John Beggs (Indiana University)

```yaml
to: jmbeggs@indiana.edu
subject: Replication of your neural avalanche exponents on DANDI 000006 — plus a cross-domain test
```

```
Dear Professor Beggs,

Your 2003 discovery that cortical avalanches follow a power-law with
critical exponents near branching-process SOC kicked off an entire
research line. We recently ran the avalanche analysis pipeline on DANDI
000006 (mouse primary visual cortex Neuropixels sessions) and attempted a
cross-domain universality test.

The neural avalanche exponents we recover sit in the task-state
sub-critical band Priesemann et al (2014) predicted -- partial agreement
with the critical-SOC null, consistent with her shift hypothesis. More
interestingly, when we pool this with our independent Layer 5 empirical
results on earthquakes (USGS, 84k events), DeFi liquidations (43k events
across three protocols), and S&P 500, we find a clean split:
discrete-threshold systems (earthquakes + DeFi) cluster at alpha ~ 1.6;
continuous-diffusion (S&P 500) at alpha ~ 3.0; null controls correctly
refuse any power-law.

Papers and interactive figures: https://beta.structural.bytedance.city/classes?lang=en
Phase 4 (neural) paper: https://beta.structural.bytedance.city/paper/soc-neural-2026-04-16?lang=en

Any reaction welcome -- particularly on whether our window/threshold
choices look defensible, and what the cleanest additional sub-critical
benchmark dataset would be.

Best regards,
Qinghui Wan
```

---

### A3. Viola Priesemann (MPI Göttingen)

```yaml
to: viola.priesemann@ds.mpg.de
subject: Direct empirical test of your task-state sub-critical shift on DANDI 000006
```

```
Dear Professor Priesemann,

Your 2014 finding that task-engaged cortex shifts exponents above the
critical SOC null has structured how people think about "criticality in
task". We put your prediction through a direct test on DANDI 000006
(mouse V1 Neuropixels, 54 sessions) and a cross-domain universality
reference pass.

The neural avalanche exponents we recover on DANDI land in the
sub-critical band, consistent with task-state shift. The novelty is the
cross-domain framing: when compared to a common pipeline across
earthquakes (USGS 84k), DeFi liquidation cascades (43k events, three
protocols), and S&P 500, the neural case is the only one that sits
off-critical in a direction that is task-modulated -- giving a principled
reason for why naive SOC comparisons across domains undercount neural
divergence.

Papers and analysis: https://beta.structural.bytedance.city/classes?lang=en
Phase 4 (neural) paper: https://beta.structural.bytedance.city/paper/soc-neural-2026-04-16?lang=en
Data: SIBD-63, https://doi.org/10.5281/zenodo.19615170

We'd value your reaction -- particularly on whether our window and
threshold choices are defensible, and which additional dataset would
give the cleanest task-state contrast.

Best regards,
Qinghui Wan
```

---

### A4. Álvaro Corral (CRM Barcelona)

```yaml
to: acorral@crm.cat
subject: Gutenberg-Richter b ≈ 1.08 and Omori p ≈ 0.94 on USGS global — plus a universality-across-domains test
```

```
Dear Professor Corral,

Your work on earthquake statistical physics -- from universal size
distributions to the Omori-Utsu aftershock law -- sets the analytical
bar. We applied the canonical pipeline to the USGS global catalog (84k
events since 1990) and, in the same pass, ran it on four entirely
different systems.

On USGS: b = 1.084 +/- 0.005 (Gutenberg-Richter, consistent with global
ranges), Omori p = 0.941 for the largest M >= 7 sequences, and energy
exponent tau ~ 1.67 -- in the discrete-threshold SOC subclass. Critically,
when we ran the same pipeline on DeFi liquidation cascades (43k events,
three engineering-distinct protocols), they also converge to alpha ~ 1.6,
while S&P 500 daily returns sit separately at alpha ~ 3.0, and
Poisson/Gaussian null controls correctly refuse a power-law.
Cross-implementation universality within the DeFi subclass is, as far as
we know, novel.

Paper + data: https://beta.structural.bytedance.city/paper/soc-earthquake-2026-04-15?lang=en
SIBD-63 dataset (63 tier-1 seeds): https://doi.org/10.5281/zenodo.19615170

Any reaction welcome -- particularly on whether our completeness-magnitude
cut is defensible, and whether there is a regional catalog you would
prefer for a sharper test.

Best regards,
Qinghui Wan
```

---

### A5. Ariah Klages-Mundt (Gauntlet)

```yaml
to: ariah@gauntlet.xyz
subject: Cross-protocol DeFi liquidation cascades — α clusters at 1.6 across Aave V2 + Compound V2 + MakerDAO (43k events)
```

```
Dear Ariah,

Your dissertation and Gauntlet work on DeFi risk dynamics directly
informed how I set up the Phase 3 analysis I want to show you. We ran
Clauset-Shalizi-Newman power-law fits on 43,065 liquidation events
spanning Aave V2, Compound V2, and MakerDAO -- deliberately picked
because their liquidation triggers are engineering-distinct (health
factor / utilization rate / stability fee).

Per-protocol alpha lands in [1.57, 1.68]. All three agree, and they match
the exponent we recover on USGS earthquakes (84k events) and sit in the
discrete-threshold SOC subclass -- distinct from S&P 500 at alpha ~ 3.0
(continuous-diffusion) and synthetic Poisson/Gaussian controls which
correctly refuse a power-law. The cross-implementation agreement is the
key result: three independent protocol designs converge to the same
universality-class exponent, which is an operational version of
"detail-independence" SOC predicts.

Phase 3 paper: https://beta.structural.bytedance.city/paper/soc-defi-2026-04-15?lang=en
SIBD-63 (63 seeds, ~20 on DeFi / finance): https://doi.org/10.5281/zenodo.19615170

Any reaction is welcome -- particularly on whether the cross-protocol
pooling is defensible, and if there is a wider liquidation dataset (e.g.,
Euler, Spark, Morpho) whose inclusion would be a useful next check.

Best regards,
Qinghui Wan
```

---

## Send plan

1. Wait for all 5 i18n agents (A/B/C/D/E) to complete
2. Integration pass: merge, verify, deploy to VPS
3. Smoke test: `?lang=en` works on /classes, /about, all /paper/* pages
4. Verify every URL in this file returns 200 with English content
5. Create 8 Gmail drafts (3 replies with threadId, 5 cold emails with fresh subject)
6. User reviews drafts in Gmail, clicks Send on each
7. Archive: move this file to `outreach/wave2-sent-2026-04-XX.md` with send date appended
