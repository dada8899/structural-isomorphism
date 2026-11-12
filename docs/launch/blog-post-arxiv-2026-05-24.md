# We tested whether one statistical pipeline can describe 13 different scientific systems. Here's what happened.

*arXiv preprint released today (2026-MM-DD). Code + data + live demos linked below.*

---

## The question

Universality classes in statistical physics are a 50-year-old idea: a small
set of equations describes phase transitions in materials, magnets, and
fluids that look nothing alike. The Ising model captures behavior near a
ferromagnetic transition — and *also* describes critical behavior in
percolation, opinion dynamics, certain neuronal cultures, and certain
financial liquidation cascades. Different substrates, same equations.

The natural question is: how far does this extend? Do messy empirical
systems — neural avalanches, DeFi liquidations, wildfires, citation
cascades, GitHub starring dynamics — share the *same* statistical
signatures, *measured by the same code, with no per-domain tuning*?

Today's preprint reports our answer so far: in 13 of 17 pre-registered
systems, the same 339-LOC Python module returns power-law exponents that
land inside theory-derived bands. Four pre-registered systems returned
**FAIL**, **PARTIAL**, **NULL**, or **INCONCLUSIVE** — and we publish those
verdicts alongside the positives. The methodology is the deliverable.

## The five phases of the work

### Phase 1 — Build a single, frozen, no-knob pipeline

`v4/lib/soc_pipeline.py` is 339 lines of Python at commit `7ee228c`. It
implements Clauset–Shalizi–Newman 2009 discrete MLE for power-law fits:
KS-optimal `xmin`, Hill-form `alpha`, block-bootstrap CIs, Vuong
likelihood-ratio tests against lognormal and exponential alternatives.
The exact same function is called on every system. No per-domain
hyperparameters, no retuning, no "let me try a slightly different `xmin`"
flexibility downstream.

### Phase 2 — Curate the cross-domain dataset with adversarial LLM critics

SIBD-63 is our open dataset on Zenodo (DOI:
[10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)). It
contains 63 candidate cross-domain pairs — for each pair, a shared
equation, a variable-mapping table, and a verdict from a heterogeneous
LLM critic ensemble (Claude Sonnet, DeepSeek v4, Kimi K2.5, GLM-5). Each
critic votes KEEP / REJECT / SPLIT / MERGE. No single vendor can wave a
pair through.

We acknowledge a known weakness: the *statistical-pipeline* ensemble (B3)
is currently within-vendor — three DeepSeek decodings at varied
temperature. The architecturally diverse B4 is partly blocked by region
routing for Anthropic and Google from our China-egress IPs. We document
this in paper § 6 of v0.3 and § 8 of v0.4 rather than pitching B3 as
"multi-vendor".

### Phase 3 — Pre-register exponent bands BEFORE fetching data

For each candidate universality class, we commit a YAML file to the repo
at `v4/preregistration/<system>.yaml` containing:

- the expected exponent band (e.g. `alpha ∈ (1.4, 1.7)`)
- the source paper that justifies the band
- the data source URL
- a `pre_registered_at` git timestamp

The git log is the audit trail. The pre-registration commit must
predate the data-fetch commit; otherwise the verdict for that system
is invalid by protocol. We do not pick bands that fit our data; we pick
bands the literature predicted, *then* fetch.

### Phase 4 — Report adversarial verdicts, including the failures

Of 17 pre-registered systems, 13 return PASS (CI band overlaps the
pre-registered exponent band), 4 do not:

- **FAIL** — 2023 CVE high-severity disclosure cascades. Vuong test
  favors lognormal; not power-law.
- **NULL** — NYC FDNY 2023 fire dispatch unit sizes. CI excludes the
  pre-registered band.
- **PARTIAL** — r/wallstreetbets post cascades. Power-law plausible for
  upper tail only; bulk is lognormal.
- **INCONCLUSIVE** — a commercial trading-signal fork applied
  walk-forward to S&P 500 2020–2024. Sharpe lift indistinguishable
  from zero at the registered confidence.

These four failures are published in `paper/anti-phacking-unified-2026-05-15.md`.
The argument is: 13 positives + 4 published failures from a single
pipeline is more credible than 17 positives from a re-tunable one.

### Phase 5 — Make it touchable

Two live demos let you poke the methodology:

- **[beta.structural.bytedance.city](https://beta.structural.bytedance.city)** —
  search across the cross-domain knowledge base. Type "bank runs" and see
  matched systems with shared equations + variable mappings.
- **[phase.bytedance.city](https://phase.bytedance.city)** — a research
  preview that extracts a dynamical-phase classification (stable /
  near-critical / reversed / recovering) for 500 public companies. With
  source-quote provenance + LLM prompt hash on every prediction. Not
  investment advice; research artifact for analysts.

## How to reproduce

```bash
pip install structural-soc-pipeline
```

```python
from structural_soc.pipeline import fit_powerlaw

result = fit_powerlaw(
    data=my_avalanche_sizes,
    xmin_method="ks",
    bootstrap_reps=1000,
)
print(result.alpha, result.alpha_ci, result.vuong_lognormal)
```

For a full pre-registered system check:

```bash
git clone https://github.com/dada8899/structural-isomorphism
cd structural-isomorphism
pip install -e ".[dev]"
python v4/validate.py neural-avalanches
# → outputs verdict (PASS/FAIL/PARTIAL/NULL/INCONCLUSIVE) + full diagnostic table
```

The pre-registered band YAML files are in `v4/preregistration/`. The
soc pipeline is frozen at `7ee228c`. SIBD-63 is on Zenodo.

## What I want from readers

1. **Try to break a verdict.** If you think any of the 13 PASSes are
   post-hoc band engineering, the YAML files have a `source_paper` field —
   open an issue with a different paper's band and we'll re-run.
2. **Propose new pre-registrations.** The systems we'd most like to test
   next are: Bitcoin Cash transaction sizes, FluNet ILI cascades, Flickr
   photo cascades, Bonabeau wasp dominance interactions. PRs welcome
   against `v4/preregistration/`.
3. **Reproduction reports.** If `python v4/validate.py <system>` does
   not match our published table on your machine, that's a P0 bug.

## Links

- Preprint: [arXiv:ARXIV_ID_PENDING](https://arxiv.org/abs/PENDING) — cond-mat.stat-mech (primary), physics.data-an (cross-list)
- Repo (MIT): [github.com/dada8899/structural-isomorphism](https://github.com/dada8899/structural-isomorphism)
- Dataset (CC-BY-4.0): [doi.org/10.5281/zenodo.19615170](https://doi.org/10.5281/zenodo.19615170)
- PyPI: `pip install structural-soc-pipeline` ([PyPI page](https://pypi.org/project/structural-soc-pipeline/))
- Live demos: [beta.structural.bytedance.city](https://beta.structural.bytedance.city) | [phase.bytedance.city](https://phase.bytedance.city)
- Methodology paper: `paper/anti-phacking-unified-2026-05-15.md` in repo
- Discussion: HN thread (pending — link will be added here on launch day)

---

*Code MIT. Datasets CC-BY-4.0. Looking for reviewers who will try to find
holes. The whole point of adversarial pre-registration is that the
methodology is supposed to fail when applied to a system that shouldn't
pass. Open an issue, fork the repo, send a PR with a counter-example —
that's the contribution model.*

*Word count: ~1050.*
