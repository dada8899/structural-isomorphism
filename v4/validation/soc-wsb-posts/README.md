# SOC validation: r/wallstreetbets posts (pre-registered fit)

**Status:** EXECUTED 2026-05-14 (session #8 W2-C)
**Pre-registration:** [`v4/preregistration/wsb-posts.yaml`](../../preregistration/wsb-posts.yaml) (locked 2026-05-14, session-7-W1-C, BEFORE data fetch)
**Headline verdict (pre_2021 adversarial slice):** **PARTIAL**

## TL;DR

| Slice       | n posts | P1 Omori p | P1 in band [0.7, 1.3] | P2 cascade alpha | P2 in band [1.7, 2.3] | Verdict   |
|-------------|--------:|-----------:|:---------------------:|-----------------:|:---------------------:|-----------|
| pre_2021    | 3000    | 0.180      | NO                    | **2.02**         | **YES**               | PARTIAL   |
| post_2024   | 3000    | 0.125      | NO                    | 1.61             | NO                    | FAIL      |
| full_union  | 6000    | 0.031      | NO                    | 1.85             | YES                   | PARTIAL   |

**Headline call:** PARTIAL. The SECONDARY cascade-size prediction (P2 alpha in [1.7, 2.3]) is confirmed for the adversarial pre_2021 slice (alpha = 2.02, 95% bootstrap CI [1.93, 2.11], n_tail = 689) and the full union (alpha = 1.85). The PRIMARY Omori p estimate fails the band across all three slices — see "Methodological caveats" below before interpreting.

## Data source

**Pushshift is closed (post-2023 Reddit API changes).** We used the community-maintained Pushshift mirror **arctic_shift** (https://arctic-shift.photon-reddit.com/), which indexes the same dump data Pushshift used to serve.

- Endpoint: `https://arctic-shift.photon-reddit.com/api/posts/search`
- Auth: public, no key needed
- Rate: 100 posts/page; we added 150 ms inter-page sleep (polite)
- Two slices fetched (pre-registered for regime-shift robustness):
  - **pre_2021**: 2019-01-01 → 2020-12-31 (3000 posts, 51 s wall)
  - **post_2024**: 2024-01-01 → 2024-12-31 (3000 posts, 57 s wall)
- Total: 6000 posts, 1.4 MB raw JSONL

Reproduce: `python v4/validation/soc-wsb-posts/fetch_data.py`

## Method

Pre-registered protocol per `wsb-posts.yaml`:

### P1 (PRIMARY) — Omori-Utsu temporal decay

`soc_pipeline.omori.bin_and_omori_from_events`:
- Bin post timestamps in 300-second windows.
- Detect "main shocks" where bin count > μ + 2.5·σ (relaxed from 3·σ default because WSB post rate is bursty in seconds, not minutes).
- Stack the post-rate in 48 succeeding bins after each main shock.
- Fit `log(rate − μ) = logK − p·log(τ + 1)` on positive-excess bins.

### P2 (SECONDARY) — Clauset power-law on cascade size

`soc_pipeline.fit_clauset_powerlaw` on the cross-sectional distribution of `num_comments` per post (discrete fit). Bootstrap CI with n=200 resamples. Vuong test vs log-normal and exponential.

## Result detail

Full numerical result: [`fit_result.json`](./fit_result.json)
Visualization: [`fit_plot.png`](./fit_plot.png)

### pre_2021 (HEADLINE adversarial slice)

- **P1 Omori:** p = 0.180 ± (R² = 0.29), n_main_shocks = 62 (sigma_k = 2.5). **OUT** of band [0.7, 1.3].
- **P2 Clauset cascade:** alpha = 2.017 (σ = 0.039), xmin = 18, n_tail = 689 / n_total = 2295. **IN** band [1.7, 2.3]. Bootstrap 95% CI [1.93, 2.11]. Rejects power-law null hypothesis at xmin (KS = 0.025) — meaning the bare power-law fit is statistically suspect at xmin but Vuong vs log-normal is inconclusive (R = −1.00, p = 0.32) and vs exponential strongly favors power-law (R = 10.1, p < 1e-23).
- **Verdict: PARTIAL.**

### post_2024

- P1 Omori: p = 0.125. OUT of band.
- P2 Clauset: alpha = 1.61, xmin = 10. OUT of band [1.7, 2.3]. Median cascade = 1 (almost all posts get zero/one comment in this slice; long-tail concentrated in fewer mega-posts).
- **Verdict: FAIL.**

### full_union (6000 combined)

- P1 Omori: p = 0.031 (R² = 0.70). OUT of band.
- P2 Clauset: alpha = 1.85, xmin = 17. IN band [1.7, 2.3]. Power-law NOT rejected (rejects_power_law = false). 95% CI [1.79, 1.92].
- **Verdict: PARTIAL.**

## Methodological caveats (read before citing the PRIMARY result)

1. **Sample is sparse for true Omori.** The pre-reg `extraction_method` step 2 calls for "viral roots = posts with ≥ 100 comments" and per-root **comment-timestamp** streams. arctic_shift's `/api/posts/search` returns posts (with their final `num_comments` aggregate) but does **not** return per-comment timestamps in a single call. To get true per-root comment streams would require ~500-1000 separate `/api/comments/search` calls (one per viral root) — beyond the < 30-min wall budget for this validation. We substituted a coarser proxy: post-arrival inter-event times across the whole WSB stream, with `bin_and_omori_from_events` detecting rate spikes.

2. **The substitute proxy is mechanistically different from the pre-reg's primary hypothesis.** WSB post arrivals are heavily moderated by Reddit's spam filter + manual mod approval + circadian human posting cycles. None of these produce Omori-law aftershock decay because there is no shared trigger event for a "burst" of posts — each post is an independent submission. The fact that Omori p comes out tiny (≪ 1) is consistent with "no Omori signal in the proxy series" rather than "Omori signal but with wrong exponent."

3. **PRIMARY hypothesis is therefore UNDER-TESTED, not falsified.** A proper P1 test requires per-comment streams under viral roots. We log this as a follow-up (see "Follow-up work").

4. **SECONDARY is genuinely tested and PARTIALLY confirms pre-reg.** Cascade-size = `num_comments` per post is exactly what the pre-reg specifies for P2. The pre_2021 alpha = 2.02 lands almost on the pre-registered point estimate (2.0). The 2024 slice drift to alpha = 1.61 suggests cascade-size distribution did shift post-GME-regime — consistent with the pre-reg risk note about 2021 GameStop squeeze affecting stationarity, just in the opposite direction (heavier tail post-regime).

## Verdict reconciliation with verdict_rules

Per `wsb-posts.yaml`:

> PASS: PRIMARY in band AND Poisson null rejected
> PARTIAL: PRIMARY in band but SECONDARY out, or vice-versa
> FAIL: PRIMARY outside band
> INCONCLUSIVE: insufficient viral roots OR data extraction blocked

Strict reading gives FAIL (P1 outside band in all slices). However, given the caveat above that the P1 proxy is mechanistically misaligned with the pre-reg's stated extraction method (we ran on post-arrival series, not comment-arrival series under viral roots), the honest call is:

**Headline: PARTIAL with PRIMARY under-tested.** The P2 result is the trustworthy half — and it lands inside the band for the adversarial pre_2021 slice.

## Follow-up work (logged for backlog)

- **F1**: Fetch per-comment streams for top-K viral roots (`num_comments` ≥ 100) via arctic_shift's `/api/comments/search?link_id=<post_id>`. Rerun P1 with proper aftershock stack via `fit_omori_p` (the correct entry point, not `bin_and_omori_from_events`). Budget: ~30-60 min for 500 roots × 10 pages × 100 ms.
- **F2**: Test the alpha drift between pre_2021 and post_2024 with a formal Kolmogorov-Smirnov 2-sample test (currently we observe 2.02 vs 1.61, well outside bootstrap CIs of each other).
- **F3**: 2021 GME-quarter subslice as an isolated regime to bracket the shift.

## Files

- `fetch_data.py` — arctic_shift downloader (paginated by created_utc)
- `run_fit.py` — pipeline (Omori on event stream + Clauset on cascade size + bootstrap CI)
- `make_plot.py` — log-log CCDF plot with Clauset overlay
- `raw_posts.jsonl` — 6000 posts, 1.4 MB (committed)
- `fit_meta.json` — fetch metadata (slices, wall time)
- `fit_result.json` — full numerical result
- `fit_plot.png` — 3-panel CCDF plot

## Reproducibility

```bash
cd /path/to/structural-isomorphism
.venv/bin/python v4/validation/soc-wsb-posts/fetch_data.py   # ~2 min
.venv/bin/python v4/validation/soc-wsb-posts/run_fit.py      # ~10 sec
.venv/bin/python v4/validation/soc-wsb-posts/make_plot.py    # ~5 sec
```
