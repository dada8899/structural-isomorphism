***REMOVED*** B2 — Layer 4 prediction 95% confidence intervals

**Generated**: by `scripts/add_prediction_ci.py`

***REMOVED******REMOVED*** Coverage

- Class records: **21**
- Predictions: **24**
- Numerical bands extracted: **49**
- Bands with a 95% CI: **49** / 49
- Bands `ci_available=false`: **0**
- Predictions with NO numerical band at all: **0**
- Predictions with a verified cross-reference: **4**

***REMOVED******REMOVED*** CI method breakdown

- `analytic_normal_sigma`: 4
- `bayesian_band_prior`: 45

***REMOVED******REMOVED*** CI width distribution (CI-available bands)

- min: 0.0134
- median: 0.3955
- max: 94.9090

***REMOVED******REMOVED*** Method

All 24 predictions have status=待验证 — the numerical bands are LLM
structural-isomorphism extrapolations, and the target data has not
been collected (sources are external DBs: Dune, NOAA, FAERS, ...).
There is therefore no observed sample to bootstrap *for the
prediction itself*.

- **`bayesian_band_prior`** — the prediction's CI. Monte-Carlo
  (n=50000) over a triangular prior on the LLM band + 10% Gaussian
  tail. Honestly a prior-based credible interval, not a frequentist
  CI on data.
- **`verified_cross_reference`** — where a prediction structurally
  matches an already-verified system (DeFi liquidations, S&P 500
  returns, Reddit cascades), that system's real bootstrap/MLE 95% CI
  is attached for comparison. It is NOT the prediction's own CI.
- **`ci_available=false`** — degenerate (zero-width) bands get no
  fabricated number, only a reason.

***REMOVED******REMOVED*** Limitations

- The triangular prior assumes the LLM band marks the central
  plausible region; the LLM never specified band semantics.
- A genuine frequentist CI for each prediction needs the target data
  to be collected first (future B2 follow-up after data fetch).
