# [data] Add Twitter / X retweet-cascade inter-arrival dataset

## What

Add a Twitter/X retweet-cascade arrival dataset with pre-registered Omori-law `p` exponent. The dataset measures inter-arrival times of retweets after the seed tweet, and tests whether decay follows Omori law (aftershock relaxation) as predicted by self-excited point-process literature.

## Why

We have `soc-hawkes-omori/` for earthquake aftershocks and `soc-wsb-posts/` for WallStreetBets, but no Twitter cascade study despite [Crane & Sornette 2008 PNAS](https://doi.org/10.1073/pnas.0803685105) being the seminal reference. This issue uses a public dataset (no API quota burn) and gives a direct social-media counterpart to seismic Omori.

## Where

- New directory: `v4/validation/soc-twitter-cascades/`
- Pattern to mirror: `v4/validation/soc-hawkes-omori/`
- Omori fit helper already exists: `packages/soc-pipeline/src/soc_pipeline/omori.py::fit_omori_p`

## How to start

1. Pull a public Twitter-cascade dump (the [SNAP higgs-twitter dataset](https://snap.stanford.edu/data/higgs-twitter.html) is a good starter — 14M edges, no API key needed).
2. For each cascade with ≥ 50 retweets, compute inter-arrival times `Δt` from the seed.
3. Pre-register your guess at `paper/pre-registrations/twitter-cascades.md` (suggested Omori `p ∈ [0.7, 1.2]` per Crane–Sornette).
4. Run `fit_omori_p(arrivals)` and compare.

## Definition of done

- [ ] `v4/validation/soc-twitter-cascades/cascades.jsonl` (one cascade per line, with arrivals array)
- [ ] `v4/validation/soc-twitter-cascades/analyze.py`
- [ ] `verdict.json` with at least: `p`, `p_ci`, `n_cascades`, `endogenous_fraction`
- [ ] Pre-registration committed in a separate prior commit
- [ ] Test in `v4/tests/integration/test_twitter_cascades.py` (skip if data file absent)

## Difficulty

★★ (data parsing + Omori; expect 4–6 h)
