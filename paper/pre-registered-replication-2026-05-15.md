# Honest Adversarial Replication: First Two of Five Pre-Registered Systems

> Draft v0.1 (2026-05-15, session #10 Wave 7 C)
> Status: P1 + P2 shipped with full honest verdicts; P3-P5 tracked as GitHub issues
> Author: dada8899

## Abstract

We report the first two of five pre-registered adversarial replications of
the Layer-5 cross-domain validation pipeline introduced in
`v0-unified-pipeline-2026-05-13.md` §8 and re-anchored against the
companion anti-p-hacking methodology paper
`anti-phacking-unified-2026-05-15.md`. The pre-registration committed
before any data were fetched to predicted Clauset-2009 $\alpha$-bands for
five systems chosen to be **adversarial** in the sense that none of them
contributed to the V4 calibration set. P1 = Bitcoin Cash daily log
returns (SOC financial, $\alpha = 2.8 \pm 0.3$). P2 = Reddit comment
cascade sizes (preferential-attachment + cascade, $\alpha = 2.0 \pm 0.3$).
P3-P5 (FluNet influenza, Flickr photo bursts, ant-colony foraging
recruitment) are tracked as GitHub issues for future replicators. We
report verdicts honestly: P1 — **CONFIRMED**, $\hat\alpha = 2.62$, 95% CI
$[2.49, 3.00]$, $n_\mathrm{tail} = 750$. P2 — **CONFIRMED**,
$\hat\alpha = 1.76$, 95% CI $[1.71, 3.00]$, $n_\mathrm{tail} = 6\,458$.
Both systems land inside their pre-registered predicted bands. Both
inherit the v0.3 §6.6 procedural ambiguity that the Vuong
likelihood-ratio test prefers lognormal over the power-law at these
single-system tail sizes; this is a known cross-cutting weakness of the
pipeline that does not affect the pre-registered alpha-band decision
rule. The aggregate $k/5$ readout from v0.3 §8.3 cannot be evaluated on
2/5 systems alone; we therefore explicitly do *not* claim the framework
is robust or marginal on the basis of P1 + P2, and ship the result with
the partial 2/5 status flagged clearly in §5.

## 1. Why pre-registration matters

The umbrella `v0-unified-pipeline-2026-05-13.md` framework reported 11/11
or 9/9 within-band coverage across the V4 calibration phases — a result
already flagged in v0.3 §6.5(xi) as "suspiciously clean". Within-band
coverage is informative only when the bands were committed *before*
fitting. The §8 pre-registration in v0.3 fixed the bands, the systems,
and the decision rule before any of the P1-P5 data were touched; that
pre-registration is now publicly visible in the project's GitHub
history with a fixed date-stamp commit.

The methodological motivation parallels the companion anti-p-hacking
paper `anti-phacking-unified-2026-05-15.md`, which used four CVE-rate /
liquidation / wildfire / DeFi pre-registrations to demonstrate that the
shared pipeline *can fail* — and that the failure pattern is
informative. The present short paper does the symmetric thing on
**positive predictions**: if the bands are predictive, P1-P5 should land
mostly inside them; if they are too wide, the bands will need
recalibration; if they are too narrow, the framework over-claimed.

### 1.1 Adversarial selection criteria

The pre-registered systems P1-P5 were chosen with two specific
constraints that make them adversarial against the V4 calibration set:

(i) **Out-of-sample by construction.** None of P1-P5 was used to
construct or tune the V4 band values. The bands in §8.2 of the umbrella
were derived from *independent* literature priors — Gopikrishnan-Stanley
1998 for P1, Cheng et al. 2014 for P2, Daley-Gani SIR theory for P3,
Adamic-Huberman 1999 for P4, and the Bonabeau 1996 mean-field BTW limit
for P5. Any successful fit therefore tests a true out-of-sample
prediction rather than a re-fit on the same data.

(ii) **Diverse mechanism families.** P1 (financial threshold cascade),
P2 (preferential attachment + cascade on social network), P3 (SIR
contagion on health network), P4 (preferential attachment on photo
upload graph), P5 (SOC threshold cascade in collective biological
behaviour) span five distinct mechanistic generators that map to four
distinct V4 universality classes. A 5/5 outcome would be evidence for
the framework's cross-class portability; a $\leq 2/5$ outcome would
indicate that the cross-class claim was over-generalised.

### 1.2 What this paper does and does not claim

This paper reports two of the five pre-registered systems. It does **not**
make the aggregate §8.3 readout claim. It does **not** retroactively
modify the pre-registration. It does **not** report any system that was
not on the original pre-registration list. The verdicts on P1 and P2 are
made by `verdict_from_alpha_band` applied mechanically to the
`soc_pipeline.fit_clauset_powerlaw` point estimate against the
pre-committed predicted-band tuple. Each verdict is reported regardless
of whether it would support the umbrella framing — i.e. the publication
threshold for this paper is "P1 and P2 are done", not "P1 and P2 came
back the way we wanted".

## 2. The five pre-registered systems (status table)

| # | System | Class | Predicted band | Status |
|---|---|---|---|---|
| **P1** | Bitcoin Cash daily log returns (2020-2026, CryptoCompare) | SOC threshold-cascade (financial) | $\alpha = 2.8 \pm 0.3$ | **DONE — CONFIRMED** (§3) |
| **P2** | Reddit comment cascade sizes (arctic_shift, 8 top subreddits, 30-day window) | preferential-attachment + cascade | $\alpha = 2.0 \pm 0.3$ | **DONE — CONFIRMED** (§4) |
| P3 | FluNet WHO influenza final-size distribution | SIR network contagion | $\alpha = 1.7 \pm 0.4$ | pending (GitHub issue) |
| P4 | Flickr photo upload bursts | preferential attachment | $\alpha = 2.5 \pm 0.4$ | pending (GitHub issue) |
| P5 | Ant-colony foraging-trail recruitment | SOC threshold-cascade (collective) | $\alpha = 1.5 \pm 0.3$ | pending (GitHub issue) |

This short paper ships P1 + P2 with full honest verdicts and tracks
P3-P5 as GitHub issues for future replicators. The aggregate decision
rule from v0.3 §8.3 (5/5, 4/5, 3/5, $\leq 2/5$) cannot be evaluated
until P3-P5 are also fit; we report the partial 2/5 status and *do not*
make any "framework strengthened / robust / marginal / failed" claim on
this incomplete sample (§5).

## 3. P1 — Bitcoin Cash daily log returns

### 3.1 Methods

Daily close of BCH/USD pulled from `min-api.cryptocompare.com/data/v2/histoday`
(free public endpoint, no API key required) capped at 2 001 days by the
endpoint's free-tier limit; window = 2020-11-21 → 2026-05-14 UTC. The
pre-registration named 2017-2025; the publicly accessible window is
slightly truncated. A future replicator with a paid Kaiko / Polygon /
exchange direct dump could extend back to the 2017 fork; the truncation
in the present run is conservative (excludes the highest-volatility
post-fork era). We then computed $r_i = \log(p_i / p_{i-1})$ and fed
$|r_i|$ into the frozen `soc_pipeline.fit_clauset_powerlaw` function
plus `bootstrap_ci` with project-default settings ($n_\mathrm{boot} =
200$, seed 42). No pipeline code was modified.

### 3.2 Verdict

| metric | value |
|---|---|
| $\hat\alpha$ | $2.621$ |
| 95% bootstrap CI | $[2.486,\, 2.997]$ |
| $x_\min$ | $0.0300$ |
| $n_\mathrm{tail}$ | $750$ |
| KS | $0.0776$ |
| vs. lognormal $R, p$ | $-4.28,\, 1.8 \times 10^{-5}$ (lognormal preferred) |
| vs. exponential $R, p$ | $-0.69,\, 0.49$ (inconclusive) |
| Pre-reg band | $[2.5, 3.1]$ |
| Literature band | $[2.0, 3.5]$ |
| **VERDICT** | **CONFIRMED** |

$\hat\alpha = 2.62$ lies inside the predicted $[2.5, 3.1]$ band and the
95% CI $[2.49, 3.00]$ brushes the lower predicted edge while sitting
entirely inside the wider literature band. The Vuong test prefers
lognormal over power-law at $p = 1.8 \times 10^{-5}$ — this is the same
procedural ambiguity disclosed in v0.3 §6.6 across the S&P 500 and other
financial phases; it does not affect the alpha-band decision rule that
the pre-registration committed to. Full discussion in
`docs/pre-registrations/p1-bitcoin-cash-result.md`. Figure:
`paper/figures/pre-reg/fig_p1_bch_ccdf.pdf`.

## 4. P2 — Reddit comment cascade sizes

### 4.1 Methods

We pulled top-level submissions from 10 high-traffic English-language
subreddits over a 30-day retrospective window (2026-04-12 → 2026-05-12
UTC) using the public **arctic_shift** archive
(`arctic-shift.photon-reddit.com`), the current successor to the defunct
pushshift.io public API. The fetcher (`fetch_reddit.py`) was stopped at
the session time budget after completing **8 of 10** intended
subreddits (AskReddit, news, worldnews, politics, todayilearned,
science, technology, movies; gaming and wallstreetbets unfetched). Per
**Cheng et al. 2014 "Can cascades be predicted?"** we use
`num_comments` as the cascade-size proxy. After dedupe and
positive-cascade filter, $n = 22\,522$ cascades remained. We fed these
into `soc_pipeline.fit_clauset_powerlaw(discrete=True)` plus
`bootstrap_ci`, project-default settings.

### 4.2 Verdict

| metric | value |
|---|---|
| $\hat\alpha$ | $1.764$ |
| 95% bootstrap CI | $[1.714,\, 2.998]$ |
| $x_\min$ | $35$ |
| $n_\mathrm{tail}$ | $6\,458$ |
| KS | $0.0595$ |
| vs. lognormal $R, p$ | $-13.18,\, 1.2 \times 10^{-39}$ (lognormal preferred) |
| vs. exponential $R, p$ | $+14.57,\, 4.6 \times 10^{-48}$ (power-law preferred) |
| Pre-reg band | $[1.7, 2.3]$ |
| Literature band | $[1.5, 2.5]$ |
| **VERDICT** | **CONFIRMED** |

$\hat\alpha = 1.76$ lies inside the predicted $[1.7, 2.3]$ band. The
asymptotic Clauset error is tight ($\sigma_\alpha = 0.01$) but the
bootstrap CI is wide ($[1.71, 3.00]$) due to bimodal $x_\min$ selection
in the bootstrap resamples (a known finite-size artefact of the
KS-$x_\min$ step on heavy-tailed integer data; reported honestly
without retraction). The Vuong vs. lognormal $R < 0$ at extreme
$p = 1.2 \times 10^{-39}$ inherits the v0.3 §6.6 procedural ambiguity;
the Vuong vs. exponential $R > 0$ at $p = 4.6 \times 10^{-48}$ confirms
the tail is heavy-tailed rather than exponentially-truncated. Full
discussion in `docs/pre-registrations/p2-reddit-cascade-result.md`.
Figure: `paper/figures/pre-reg/fig_p2_reddit_ccdf.pdf`.

## 5. Discussion — partial readout against v0.3 §8.3 decision rule

The umbrella pre-registration in v0.3 §8.3 committed to a $k/5$
inside-band readout:

| $k$ inside band | umbrella interpretation |
|---|---|
| 5/5 + Bonferroni | "framework robust; universality-class portability strengthened" |
| 4/5 | "robust with one calibration update" |
| 3/5 | "marginal; framework needs re-pre-registration" |
| $\leq 2/5$ | "predicted-band machinery not informative; class-membership claims need substantial revision" |

The present paper ships **2/5** systems (P1 + P2) and is therefore
**incomplete with respect to the v0.3 §8.3 readout**. Both
P1 and P2 are CONFIRMED — i.e. the partial count is $2/2$ inside band
on the systems shipped. We do *not* claim the framework is robust
on the basis of this partial sample. The honest interpretations of
the present $2/2$ pattern *if it persists* to $5/5$ are:

- if **5/5** holds → consistent with the framework's
  predictions on the full adversarial set; per v0.3 §8.3 this would
  warrant the strengthened framing the umbrella preprint conditionally
  promised (subject to Bonferroni control of out-of-band counts);
- if **4/5** → P3, P4, or P5 deviates; the framework
  is sound with one calibration update needed on the deviating class;
- if **3/5** → marginal; one of P3/P4/P5 deviates and
  bands need targeted recalibration;
- if **2/5** stays at 2/5 with P3-P5 all DEVIATING → strongest signal
  that the bands are too narrow or the cross-class portability claim
  was over-generalised; would warrant publication of an honest
  "framework failed at the pre-registered $\alpha$-level"
  retraction-class follow-up.

**Two additional honest reservations on the current 2/2 result:**

1. **The lognormal Vuong $R < 0$ on both P1 and P2** is consistent with
   the v0.3 §6.6 framing that lognormal-vs-power-law is operationally
   indistinguishable at single-system tail sizes $\lesssim 10^4$. The
   pre-registered alpha-band rule is not invalidated; but a "the
   framework's classes are power-law-mechanistic" claim would be much
   stronger if the Vuong test consistently selected power-law. We
   report the Vuong results unredacted.

2. **The 95% bootstrap CIs on P1 and P2 both straddle the predicted
   band's lower edge** ($[2.49, 3.00]$ vs $[2.5, 3.1]$ for P1; $[1.71,
   3.00]$ vs $[1.7, 2.3]$ for P2). The verdict logic applies to point
   estimates per the standard `verdict_from_alpha_band` function. A
   stricter "CI entirely inside band" rule would change P2 from
   CONFIRMED to a CI-overflow caveat (the upper CI bound is outside
   the band); the pre-registration did not commit to such a rule and
   we do not adopt it post-hoc.

Per the project's standing methodological commitment to honest
reporting of partial / negative / inconclusive results
(`anti-phacking-unified-2026-05-15.md` §1), this paper exists *whatever
the verdict pattern* and is published in the same repo at the same
date-stamp regardless of the P1/P2 outcomes. The fact that the present
verdict happens to be 2/2 CONFIRMED is reported with the same level of
caveat we would apply to a 2/2 DEVIATING result.

## 6. Future work — P3, P4, P5 + GitHub issues

Three systems remain to complete the v0.3 §8.3 readout:

- **P3 — FluNet WHO influenza final-size distribution** (SIR-network
  contagion, $\alpha = 1.7 \pm 0.4$). Data source: WHO FluNet portal
  (`who.int/tools/flunet`) — country-level weekly counts since 1997.
  Replicator can compute per-country-per-season epidemic final sizes
  and feed into `soc_pipeline.fit_clauset_powerlaw(discrete=True)`.
  Expected $n \sim 60$ countries $\times$ 20 years $\sim 1\,200$
  events. GitHub issue tracked.

- **P4 — Flickr photo upload bursts** (preferential attachment,
  $\alpha = 2.5 \pm 0.4$). Data source: Yahoo YFCC100M dataset (100M
  Flickr photo metadata records, freely downloadable), or Flickr API
  via `flickr.people.getInfo`. Pre-registration target: per-user
  upload-count distribution in the Adamic-Huberman PA regime.
  GitHub issue tracked.

- **P5 — Ant-colony foraging-trail recruitment** (SOC threshold-cascade,
  $\alpha = 1.5 \pm 0.3$). The Bonabeau 1996 dataset family is the
  original referent; if inaccessible the pre-registration permits a
  trail-pheromone-mediated cascade-size proxy from a published
  contemporary ant-tracking study (e.g. Stroeymeyt et al. 2018 Nature).
  GitHub issue tracked.

Each is a self-contained $\sim$ 1-day replication for a future session;
once shipped, the v0.3 §8.3 readout becomes fully evaluable.

## 6.1 Why P3-P5 are not in this paper

The pre-registration in v0.3 §8.2 listed all five systems as a single
adversarial set. We separate P1+P2 (this paper) from P3-P5 (issues) for
two reasons:

(i) **Wall-clock cost.** Each of P3-P5 has a non-trivial data
acquisition step (WHO FluNet portal scrape; YFCC100M 50 GB download;
ant-colony dataset hunt) that is bounded by external rate limits or
data-availability rather than analyst time. Bundling them into one
session would either rush the data acquisition (raising the risk of
unclean inputs) or push session-time past auto-mode limits.

(ii) **Pre-registration integrity.** A bundled release of all five
would tempt the analyst into "I'll just check P3 numerically before
finalising P1's writeup". Keeping P1+P2 frozen-and-shipped before
P3-P5 even begins enforces the pre-registration's no-peeking
discipline. The GitHub issues we create explicitly forbid future
contributors from previewing the data before committing the analysis
script.

Future replicators should ship P3-P5 as separate PRs, each updating
the §2 status table in this paper and the §8.3 readout count.

## 6.2 What we did *not* do

For transparency, here are choices we considered and rejected:

- **Pre-registered band tightening.** We did not tighten the
  literature bands to be narrower than the umbrella §8.2 values.
  Doing so post-hoc would amount to band-narrowing-after-fit, which
  is precisely the anti-pattern the pre-registration is designed to
  defeat.
- **Replacing P1's daily-returns construction with high-frequency
  intraday data.** Although intraday BCH returns are more diagnostic
  of the Gopikrishnan-Stanley regime, the pre-registration named
  "daily log returns" explicitly. We executed exactly that.
- **Excluding the lognormal Vuong result from the verdict report.**
  The Vuong $R < 0$ is uncomfortable in a paper whose verdicts are
  both CONFIRMED. Excluding it would be motivated under-reporting; we
  include it in every relevant table.
- **Aggregating P1 + P2 into a "framework holds" headline.** Per §5
  this would be over-claim on $n = 2$ adversarial systems. We do not
  do this.

## 7. Reproducibility

```bash
# P1
python3 v4/validation/pre-reg-p1-bch/fetch_bch.py
python3 v4/validation/pre-reg-p1-bch/analyze_bch.py

# P2
python3 v4/validation/pre-reg-p2-reddit/fetch_reddit.py   # or stop early + convert_partial.py
python3 v4/validation/pre-reg-p2-reddit/analyze_reddit.py

# figures
python3 paper/figures/pre-reg/make_figures.py
```

Run time end-to-end: P1 is $\sim$ 5 seconds; P2 fetch is $\sim$ 25-30
minutes on the free-tier arctic_shift API (10 subreddits × 30 days × ~100
posts per page × 1.2 s sleep), fit is $\sim$ 10 seconds.

## 8. Data + script provenance

| file | purpose |
|---|---|
| `paper/v0-unified-pipeline-2026-05-13.md` §8.2 | original pre-registration |
| `paper/anti-phacking-unified-2026-05-15.md` | companion methodology |
| `v4/validation/pre-reg-p1-bch/*` | P1 data + scripts + result |
| `v4/validation/pre-reg-p2-reddit/*` | P2 data + scripts + result |
| `docs/pre-registrations/p1-bitcoin-cash-result.md` | P1 long-form writeup |
| `docs/pre-registrations/p2-reddit-cascade-result.md` | P2 long-form writeup |
| `paper/figures/pre-reg/*.pdf` | CCDF figures |
| `packages/soc-pipeline/` | frozen analysis pipeline (no edits) |
