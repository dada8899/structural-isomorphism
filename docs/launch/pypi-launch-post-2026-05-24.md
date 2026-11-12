# PyPI launch post — three packages live — 2026-05-24

**Released today on PyPI** (2026-05-24):

- [`structural-soc-pipeline`](https://pypi.org/project/structural-soc-pipeline/) — the frozen 339-LOC SOC pipeline
- [`structural-critics`](https://pypi.org/project/structural-critics/) — the multi-vendor LLM critic ensemble
- [`structural-taxonomy`](https://pypi.org/project/structural-taxonomy/) — the cross-domain taxonomy + variable-mapping registry

This post is the short-form companion to the full arXiv launch post.
Aimed at the "show me the package, not the paper" reader.

---

## 30-second demo

```bash
pip install structural-soc-pipeline
```

```python
from structural_soc.pipeline import fit_powerlaw

# Any heavy-tailed dataset works. Try yours.
sizes = [3, 1, 2, 7, 4, 12, 1, 1, 5, 8, 22, 3, 1, 2, 6, 4, 1, 91, 2, ...]

result = fit_powerlaw(
    data=sizes,
    xmin_method="ks",      # KS-optimal xmin selection
    bootstrap_reps=1000,   # block-bootstrap CI
)

print(f"alpha = {result.alpha:.3f} (CI: {result.alpha_ci})")
print(f"xmin  = {result.xmin}")
print(f"vs lognormal: R={result.vuong_lognormal.R:.2f}, p={result.vuong_lognormal.p:.3f}")
print(f"vs exponential: R={result.vuong_exponential.R:.2f}, p={result.vuong_exponential.p:.3f}")
```

If `R > 0` and `p < 0.05` against both lognormal and exponential, you have
non-negligible evidence for power-law behavior. If `R < 0` against either,
that alternative is preferred — and the package returns that verdict
*regardless* of what you wanted to find. This is the point.

## What's in each package

### `structural-soc-pipeline` — the frozen pipeline

- One module, 339 LOC, frozen at commit `7ee228c`.
- Discrete Clauset–Shalizi–Newman 2009 MLE.
- KS-optimal `xmin`, Hill-form `alpha`, block-bootstrap CIs.
- Vuong likelihood-ratio tests against lognormal + exponential.
- Zero downstream tuning knobs. Same function, every system.

### `structural-critics` — the LLM critic ensemble

- Multi-vendor critic protocol used to curate SIBD-63.
- Voting: `KEEP / REJECT / SPLIT / MERGE` with written rationale.
- Vendor adapters: Claude (Anthropic), DeepSeek, Kimi (Moonshot), GLM (Zhipu).
- Vote-vector format documented in the package README.
- Region-routing note: Anthropic and Google adapters require US/EU egress IPs.

### `structural-taxonomy` — the cross-domain registry

- Variable-mapping tables for the 63 A-level pairs in SIBD-63.
- Pre-registered exponent bands for 17 systems (4 of which returned non-PASS).
- Each entry: shared equation, variable-mapping table, source-paper citation,
  verdict (`PASS / FAIL / PARTIAL / NULL / INCONCLUSIVE`).

## The pre-registered system check

If you want to reproduce one of the paper's verdicts on your machine:

```bash
git clone https://github.com/dada8899/structural-isomorphism
cd structural-isomorphism
pip install -e ".[dev]"

python v4/validate.py neural-avalanches
# Reads v4/preregistration/neural-avalanches.yaml,
# fetches the dataset, runs the frozen pipeline,
# prints verdict (PASS/FAIL/PARTIAL/NULL/INCONCLUSIVE) + full diagnostics.
```

If your run does NOT match our published table, that's a P0 bug — open an
issue with your `python -V` + `pip freeze` + the full output.

## What you do not get from these packages

- **Not a forecasting library.** The pipeline measures the dynamical state
  of a current series. It does not predict where the next value goes.
- **Not financial advice.** The phase detector demo at
  [phase.bytedance.city](https://phase.bytedance.city) is a research
  preview. The disclaimer is on every page.
- **Not a "one-click power-law fit" tool.** You need to think about whether
  your data plausibly comes from a process where heavy-tailed analysis
  even applies. The pipeline will return verdicts for nonsensical inputs;
  it cannot stop you from asking the wrong question.

## Links

- arXiv preprint: arXiv:ARXIV_ID_PENDING (cond-mat.stat-mech primary)
- Repo (MIT): [github.com/dada8899/structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
- Dataset (CC-BY-4.0): [doi.org/10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)
- Long-form companion blog: `docs/launch/blog-post-arxiv-2026-05-24.md`
- HN thread: pending (link added on launch day)

---

## License

- Code: MIT
- Datasets: CC-BY-4.0

## Reporting issues

Open at [`github.com/dada8899/structural-isomorphism/issues`](https://github.com/dada8899/structural-isomorphism/issues).
P0 = published-verdict reproduction failure; P1 = installation failure on a
supported Python / OS combo; P2 = anything else.

---

*Word count: ~530.*
