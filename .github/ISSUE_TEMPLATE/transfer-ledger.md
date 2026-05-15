---
name: Transfer ledger report
about: Report the result of running a falsifiable prediction from an /insights case study on your own data.
title: '[transfer-ledger] <case-id>: <pass|fail|inconclusive>'
labels: transfer-ledger
---

## Insight case

<!-- Which case-study did you test? Paste the URL (e.g. https://phase.bytedance.city/insights/earthquake-defi-cascade) -->

URL:

## Prediction tested

<!-- Paste the "If / Then / How to test" block verbatim from the case-study page so reviewers can confirm you tested the exact claim, not a paraphrase. -->

- **If**:
- **Then expect (within N days)**:
- **How to test**:

## Your setup

<!-- One paragraph: what system did you apply this to? What time window? What data source? How many data points / events? Any pre-processing? -->

## Result

<!-- Did the prediction hold? Pass / Fail / Inconclusive. Numbers preferred over adjectives. -->

- Verdict: <!-- pass / fail / inconclusive -->
- Headline number (e.g. fitted exponent, BIC delta, t-statistic, p-value):
- 95% confidence interval (if applicable):
- Comparison to the predicted band:

## Caveats

<!-- Where might selection bias, data quality, regime breaks, or measurement choices have affected the result? Be honest — partials and "I think this failed but my data is thin" reports are more useful than confident wrong ones. -->

## Reproducibility

<!-- Link to code / notebook / data sample if you can share. If you cannot, describe enough that someone with similar data could reproduce the test. -->

- Code / notebook:
- Data sample:
- Random seed (if applicable):

---

*Reports get tagged into the public transfer ledger and feed back into the per-case outcome counts at `/insights/<case-id>`. Anonymous / pseudonymous reports are accepted; please don't include credentials or proprietary data.*
