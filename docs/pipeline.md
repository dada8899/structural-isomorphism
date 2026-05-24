# Pipeline

The shared analysis stack is implemented in `v4/lib/soc_pipeline.py` and
is frozen at commit `7ee228c`. It exposes one function per analytical
operation; phase scripts call those functions with a domain-specific data
loader and write the verdict to disk.

## Design principles

1. **One module, no per-system tuning.** Every phase paper calls the same
   function signatures. Tuning a parameter on one system would invalidate
   the cross-domain claim, so the module is frozen and tagged.
2. **Pre-registered YAML drives the run.** The fitter reads the YAML
   predicted band and rejection thresholds; the verdict is computed by code,
   not by the orchestrating agent.
3. **Verdict is one of PASS / INCONCLUSIVE / FAIL.** The semantics are
   spelled out in the [pre-registration methodology](methodology/pre-registration.md).
4. **All artifacts are committed.** Raw data, intermediate burst-size
   vectors, fit logs, and result JSON files are all under
   `v4/validation/<system>/` and can be re-fit deterministically.

## The seven analytical operations

The pipeline supplies one function per operation. The names below are the
canonical exports.

### `fit_clauset_powerlaw(sizes, discrete=False)`

Continuous or discrete power-law tail fit per Clauset, Shalizi, and Newman
(2009). $x_{\mathrm{min}}$ is selected by minimizing the Kolmogorov-Smirnov
distance between empirical and fitted CDFs over a candidate grid; $\alpha$
is then estimated by maximum likelihood on the resulting tail using the
Hill-form estimator. Returns $\alpha$, the Hill-form $\sigma(\alpha)$,
$x_{\mathrm{min}}$, and $n_{\mathrm{tail}}$.

### `bootstrap_ci(sizes, fit, n_boot=1000)`

Non-parametric block bootstrap on $\alpha$ with default block length
$\sqrt{n}$. The block bootstrap is used because most empirical burst series
have serial correlation that an i.i.d. bootstrap would systematically
narrow. Phases with very small $n_{\mathrm{total}}$ (under 200) widen the
percentile band to 5-95 and use 300 resamples instead of the standard 100.

### `vuong_lr(sizes, fit, alternative)`

Clauset-Shalizi-Newman normalized log-likelihood ratio $R$ against
`alternative` $\in \{$ "lognormal", "exponential" $\}$ with Vuong-style
$p$-values. Positive $R$ favors power-law; $p < 0.05$ indicates statistical
distinguishability. Rejection of exponential is necessary but not
sufficient for a power-law claim; the harder test is against lognormal,
which can mimic a power-law over finite dynamic range.

### `omori_utsu_stack(events, T_window, n_bootstrap=1000)`

Time-domain aftershock-decay fit per Omori-Utsu. For systems with
identifiable main-shock events (earthquakes, neural avalanches, market
cascades), the aftershock density should follow
$\lambda(t) \propto (t + c)^{-p}$ with $p \in [0.6, 1.4]$. Bootstrap is
used for the CI on $p$.

### `null_control(generator, n, alternative)`

Synthetic null control: generate $n$ samples from a non-power-law generator
(Gaussian-walk increments, exponential variates, homogeneous Poisson
inter-arrival times, homogeneous Poisson Omori stack) and pass them through
the same fitting pipeline. The pipeline should reject power-law against
the relevant alternative; if it does not, the pipeline is over-claiming.

### `log_binned_density(sizes, n_bins=40)`

Logarithmically spaced density estimator with Poisson error bars on each
bin. Used for the universal collapse polish (the cross-system
shape-normalized log-variance ratio $r_{\mathrm{shape}}$).

### `bic_select(sizes, fit, alternatives)`

Bayesian Information Criterion ranking on a log-binned density. The
universal collapse polish prefers power-law + exponential cutoff to
lognormal in 5 of 7 systems with $\Delta\mathrm{BIC} \in [33, 967]$
(decisive on the standard Kass-Raftery scale).

## Verdict assembly

The orchestrating script `v4/scripts/run_preregistered_validation.py`
composes the operations into a single fit, applies the verdict rules from
the pre-registration YAML, and writes the result to disk. The verdict
function is:

```python
def verdict(alpha, ci, vuong_ln, vuong_exp, band):
    if alpha < band[0] or alpha > band[1]:
        return "FAIL"
    if vuong_ln.R < 0 and vuong_ln.p < 0.05:
        if vuong_exp.R < 0 and vuong_exp.p < 0.05:
            return "FAIL"
        return "INCONCLUSIVE"
    return "PASS"
```

The CVE falsification (see [Papers](papers.md)) is an example of the
first branch: $\alpha = 2.668$ outside band $[1.5, 2.5]$ yields FAIL.
The FDNY result is an example of the third branch: point estimate in
band but CI extending past the band and Vuong rejection in favor of
both alternatives yields INCONCLUSIVE on the primary series.

## Frozen at commit `7ee228c`

The module is intentionally frozen. Improvements proceed by versioning:
a v5 pipeline would be a separate module with its own tag, not an edit
of v4. This preserves the cross-domain replication guarantee — every
phase paper is reproducible at the byte level against the same code.
