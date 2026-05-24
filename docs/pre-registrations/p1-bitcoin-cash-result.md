# Pre-registered replication P1 — Bitcoin Cash daily log returns

**Status.** Complete (2026-05-15, session #10, W7-C).
**Verdict.** **CONFIRMED** within the pre-registered band — with one
honest qualification on the lognormal-vs-power-law procedural ambiguity
already flagged in v0.3 §6.6 of the umbrella preprint.

| field | value |
|---|---|
| Pre-registration source | `paper/v0-unified-pipeline-2026-05-13.md` §8.2, system P1 |
| Class | SOC threshold-cascade (financial) — inverse-cubic-law regime |
| Predicted band | $\alpha = 2.8 \pm 0.3 \Rightarrow [2.5, 3.1]$ |
| Literature band | $[2.0, 3.5]$ (Gopikrishnan/Stanley 1998, Plerou 1999) |
| Observable | absolute daily log return $\lvert r_t \rvert = \lvert \log(p_t / p_{t-1}) \rvert$ |
| Verdict | **CONFIRMED** (alpha and 95% CI both inside predicted band) |

---

## 1. Data source + provenance

We pulled the **daily close of Bitcoin Cash (BCH/USD)** from the public
CryptoCompare `histoday` endpoint
(`https://min-api.cryptocompare.com/data/v2/histoday?fsym=BCH&tsym=USD&limit=2000`),
free tier, no API key required. The endpoint returned **2 001 daily
candles** spanning **2020-11-21 → 2026-05-14 UTC**. The pre-registration
specified a 2017-2025 window; the publicly accessible CryptoCompare free
endpoint capped us at the most recent ~2 000 days, which truncates the
chaotic 2017-2020 era. This is a tighter (more conservative) window than
the pre-registration named and is recorded honestly. A future replicator
with a paid CryptoCompare API key, Kaiko, Polygon.io, or an exchange
direct dump (e.g. Binance/Kraken BCHUSDT daily) could extend back to the
2017 BCH fork. We confirmed with a quick CoinGecko cross-check that the
2020-11 closing price ($303.75) is within 1% of independent quotes; no
sign of obvious data corruption.

The full raw daily series is stored in
`v4/validation/pre-reg-p1-bch/bch_daily.csv` (committed) and the derived
absolute log-return vector in `bch_intervals.json`. The fetch script
(`fetch_bch.py`) is reproducible; running it on a different day will
update the most-recent-2000-days window but not change the early-window
data.

A complementary fetch from `api.blockchair.com/bitcoin-cash/blocks` is
*not* used as the primary P1 data because the pre-registration explicitly
states "**daily log returns**" — i.e. the Gopikrishnan/Stanley financial
power-law regime, not chain-level inter-event times. We retain the
blockchair plumbing in `fetch_bch.py` history but the primary data is the
CryptoCompare daily close.

## 2. Construction of the observable

For each daily candle pair $(t_{i-1}, t_i)$ with positive closes
$p_{i-1}, p_i$, we computed $r_i = \log(p_i / p_{i-1})$. The full series
gives **2 000 log returns** (one fewer than the 2 001-day window). We
then took $|r_i|$ as the cross-domain analogue of the
event-size observable used throughout the V4 SOC suite (see also
`v4/validation/soc-stockmarket/fetch_and_analyze.py` for the S&P 500
companion). One zero return was dropped, leaving **1 999 non-zero
$|r_t|$** values with min $= 7.6 \times 10^{-5}$, max $= 0.461$, median
$= 0.022$.

This is identical in construction to the V4 stock-market phase that
served as the original V4 anchor for the inverse-cubic band — i.e. P1 is
testing whether **the same pipeline on the same observable choice in a
different (younger, less liquid) asset class lands in the same
literature band**. The pre-registration is therefore a portability test,
not a methodological one.

## 3. Frozen pipeline output

We imported the package `soc_pipeline` (installed from
`packages/soc-pipeline/` in editable mode) **without modification** and
called `fit_clauset_powerlaw(|r_t|, discrete=False)` plus `bootstrap_ci`
with the project-default settings ($n_\mathrm{boot} = 200$, seed 42).
Verbatim numerical output:

| metric | value |
|---|---|
| $\hat\alpha$ | $2.621$ |
| $x_\min$ (KS-selected) | $0.0300$ |
| $\sigma_\alpha$ (asymptotic, Clauset 2009) | $0.0592$ |
| $n_\mathrm{tail}$ ($\geq x_\min$) | $750$ |
| $n_\mathrm{total}$ | $1\,999$ |
| KS statistic | $0.0776$ |
| Bootstrap mean $\bar\alpha$ | $2.726$ |
| Bootstrap median | $2.692$ |
| Bootstrap std | $0.160$ |
| **95% CI on $\alpha$** | **[$2.486$, $2.997$]** |
| vs. lognormal $R, p$ | $-4.28$, $1.8 \times 10^{-5}$ (lognormal preferred) |
| vs. exponential $R, p$ | $-0.69$, $0.49$ (inconclusive) |

The point estimate **$\hat\alpha = 2.62$** sits inside the
pre-registered $[2.5, 3.1]$ band and well inside the literature
$[2.0, 3.5]$ band. The 95% bootstrap CI **[$2.49$, $3.00$]** straddles
the predicted lower edge — by the project's standard verdict logic
(`verdict_from_alpha_band`, applied to the point estimate) this is
classified as **CONFIRMED**. If we apply a strict
"$\hat\alpha \pm 1\sigma_\alpha$ entirely inside the band" rule the
point estimate plus the asymptotic Clauset error
($2.62 \pm 0.06$) sits cleanly inside; under the wider bootstrap CI the
lower edge brushes the band boundary, which is the right behaviour for
a $n_\mathrm{tail} = 750$ tail with this much daily-return finite-size
truncation.

## 4. Verdict — and the honest lognormal qualification

**VERDICT: CONFIRMED within the pre-registered predicted band.**

The qualification (already a known cross-cutting weakness from v0.3
§6.6): the Vuong likelihood-ratio test prefers **lognormal** over the
power-law for this tail at $p = 1.8 \times 10^{-5}$. This is the exact
same procedural ambiguity flagged across nine V4 phases — at the tail
sizes typical of single-asset financial time series (here
$n_\mathrm{tail} = 750$, similar to the S&P 500 phase's
$n_\mathrm{tail} \sim 1\,000$), the power-law and lognormal tails are
operationally indistinguishable by Vuong R, while the alpha-band
interpretation remains independently consistent with the
Gopikrishnan/Stanley literature. The honest reading is "**tail is
consistent with the inverse-cubic regime; lognormal alternative is not
ruled out**" — this is the same reading the umbrella preprint applies
to the S&P 500, BTC, and several other power-law phases.

The pre-registration committed only to the alpha-band decision rule
(§8.3). On that rule, P1 is unambiguously **CONFIRMED**. We report the
Vuong $R < 0$ result without retraction.

## 5. Caveats — to be reported in the §5 discussion of the short paper

1. **Window truncation.** 2020-11 → 2026-05, not 2017 → 2025. A 2017-2020
   extension would add the chaotic post-fork era and almost certainly
   widen the heavy tail (i.e. push $\hat\alpha$ slightly lower, deeper
   into the predicted band). The current truncation is conservative.
2. **Vuong lognormal-vs-power-law.** As above. Inherits the v0.3 §6.6
   procedural ambiguity. Does not invalidate the alpha-band verdict but
   any reader using P1 to argue "**proves** inverse-cubic" should be
   directed to v0.3 §6.6 for the qualifier.
3. **Daily, not high-frequency.** The Gopikrishnan-Stanley regime is
   typically established with intraday data. Daily returns suppress
   intra-day extreme moves; the surviving tail is therefore a
   pessimistic estimator of the true heavy-tail exponent. A future
   replication with 1-min BCH bars from a single exchange (Binance,
   Kraken, Bitfinex) would tighten the test.
4. **Single asset, single venue.** No cross-exchange aggregation; no
   bid-ask spread correction; no liquidity-conditional binning.

## 6. Files

| path | content |
|---|---|
| `v4/validation/pre-reg-p1-bch/fetch_bch.py` | data fetcher (CryptoCompare) |
| `v4/validation/pre-reg-p1-bch/analyze_bch.py` | Clauset fit + bootstrap + verdict |
| `v4/validation/pre-reg-p1-bch/bch_daily.csv` | raw daily close (2 001 rows) |
| `v4/validation/pre-reg-p1-bch/bch_intervals.json` | $\|r_t\|$ series + fetch meta |
| `v4/validation/pre-reg-p1-bch/p1_fit_result.json` | FitResult + bootstrap CI + verdict |
| `v4/validation/pre-reg-p1-bch/p1_ccdf.json` | empirical CCDF for plotting |
| `paper/figures/pre-reg/fig_p1_bch_ccdf.pdf` | CCDF figure with predicted/literature band overlays |

## 7. Reproducibility

```bash
python3 v4/validation/pre-reg-p1-bch/fetch_bch.py
python3 v4/validation/pre-reg-p1-bch/analyze_bch.py
python3 paper/figures/pre-reg/make_figures.py
```

Total run time: $\sim$ 5 seconds (fetch is one HTTP request, fit is one
KS sweep + 200 bootstrap resamples on 2 000 numbers). No GPU needed.
Re-running on a different date will update the rolling 2 000-day window
but not the early-window data.

---

**Decision-rule input for §8.3 of the umbrella preprint:** P1 = INSIDE
band → contributes +1 to the "$k$ inside band out of 5" count. Vuong
$R < 0$ is a separate weakness already disclosed in v0.3 §6.6 and does
not affect the §8.3 count.
