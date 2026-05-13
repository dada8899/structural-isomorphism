***REMOVED*** API Reference

All public symbols are exported from the top-level `soc_pipeline` namespace.

***REMOVED******REMOVED*** Fit

***REMOVED******REMOVED******REMOVED*** `fit_clauset_powerlaw(x_data, name="values", discrete=False, xmin_method="ks", min_samples=100) -> FitResult`

Fit a power-law to the tail of `x_data` using the Clauset-Shalizi-Newman 2009 method (KS minimization on xmin, MLE on alpha).

**Returns `FitResult`** (dataclass) with:

| field | type | meaning |
|---|---|---|
| `alpha` | float | scaling exponent (P(x) ∝ x^-alpha) |
| `xmin` | float | KS-minimum lower bound |
| `sigma` | float | std error on alpha |
| `n_total` | int | sample size before filtering |
| `n_tail` | int | samples >= xmin |
| `ks_statistic` | float | KS distance between empirical & fit |
| `vs_lognormal_R` / `vs_lognormal_p` | float | Vuong LR vs lognormal |
| `vs_exponential_R` / `vs_exponential_p` | float | Vuong LR vs exponential |
| `vs_powerlaw_lognormal_winner` | str | 'power_law' \| 'lognormal' \| 'inconclusive' |
| `rejects_power_law` | bool | True iff comparison rejected PL |
| `error` | str \| None | non-None when fit failed |

Use `.to_dict()` for a legacy dict view compatible with the v4/lib API.

***REMOVED******REMOVED*** Bootstrap

***REMOVED******REMOVED******REMOVED*** `bootstrap_ci(x_data, n_boot=200, seed=42, discrete=False, ci_pct=(2.5, 97.5), min_samples=200) -> BootstrapResult`

Bootstrap resample the data and refit alpha n_boot times. Returns `BootstrapResult` with `alpha_mean`, `alpha_median`, `alpha_std`, `ci_low`, `ci_high`, `n_boot_succeeded`.

***REMOVED******REMOVED*** Null controls

***REMOVED******REMOVED******REMOVED*** `synthetic_null(kind=None, n=20_000, seed=42)`

If `kind` is None, returns a `dict[str, NullCase]` over three synthetic non-heavy-tail nulls: `gaussian_walk`, `exponential`, `poisson_iat`. Each `NullCase` has `name`, `fit: FitResult`, `correctly_rejected: bool`. A healthy pipeline rejects all three.

If `kind` is one of the names above, returns a single `NullCase`.

***REMOVED******REMOVED*** LR test

***REMOVED******REMOVED******REMOVED*** `vuong_lr_test(x_data, vs="lognormal", discrete=False, alpha_threshold=0.1) -> LRResult`

Stand-alone Vuong 1989 LR test power-law vs `vs` (`"lognormal"` / `"exponential"` / `"stretched_exponential"` / `"truncated_power_law"`).

***REMOVED******REMOVED*** Universal collapse

***REMOVED******REMOVED******REMOVED*** `shape_normalized_collapse(samples, s_star_percentile=99.0, n_points=120) -> CollapseResult`

`samples`: dict mapping system name -> `(event_sizes, known_alpha)`. Returns `CollapseResult.systems` mapping name -> `SystemCurve` (`x_rescaled`, `y_rescaled`, `raw_grid`, `raw_ccdf`, `alpha`, `s_star`, `n`).

***REMOVED******REMOVED*** Omori

***REMOVED******REMOVED******REMOVED*** `fit_omori_p(dts_sec, min_sec=300.0, max_sec=30*86400, n_bins=24, c_grid_days=(0.001, ..., 0.5)) -> OmoriResult`

Stack of aftershock delays after a main shock. Returns `p`, `p_sigma`, `c_days`, `logK`, `R2`, `n_aftershocks_in_fit`, `n_bins_used`, `t_range_days`.

***REMOVED******REMOVED******REMOVED*** `bin_and_omori_from_events(event_times_sec, bin_seconds=60.0, sigma_k=3.0, window_bins=60) -> OmoriResult`

Auto-detect main shocks in an unlabeled event stream and run Omori-Utsu on the stack. Adds `n_main`, `mu`, `sigma`, `threshold` to the result.

***REMOVED******REMOVED*** b-value (Gutenberg-Richter)

***REMOVED******REMOVED******REMOVED*** `fit_b_value(magnitudes, mc=None, bin_width=0.1, bootstrap=False, n_boot=500, seed=42) -> BValueResult`

Aki 1965 MLE. If `mc` is None, estimated by maximum-curvature. Returns `b`, `sigma_b`, `mc`, `n_above_mc`, `alpha_equivalent`, optional `ci_low` / `ci_high`.

***REMOVED******REMOVED******REMOVED*** `b_to_clauset_alpha(b) -> float`

Map G-R b to equivalent Clauset alpha on energy via Hanks-Kanamori: `alpha = 1 + b/1.5`.

***REMOVED******REMOVED*** Time-resolution sweep

***REMOVED******REMOVED******REMOVED*** `time_resolution_sweep(event_times, bin_sizes_sec=(60, 300, 900, 3600, 21600, 86400), stability_threshold=0.15) -> dict`

Sweep bin sizes and fit alpha at each resolution. Returns `sweep` list, `alpha_min/max/median/spread`, `is_stable`.

***REMOVED******REMOVED*** Utilities

***REMOVED******REMOVED******REMOVED*** `empirical_ccdf(vals, n_points=200) -> (grid, ccdf)`

Log-spaced CCDF P(X > s).

***REMOVED******REMOVED******REMOVED*** `verdict_from_alpha_band(alpha, predicted, literature=None) -> str`

3-tier verdict: `'CONFIRMED'` / `'CONFIRMED (literature band)'` / `'DEVIATING'` / `'INCONCLUSIVE'`.
