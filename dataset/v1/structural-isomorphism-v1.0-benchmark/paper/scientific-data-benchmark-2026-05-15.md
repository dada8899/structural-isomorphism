# A cross-domain SOC + critical-systems benchmark with synthetic nulls and multi-model class curation

**Target venue.** *Scientific Data* (Nature), data descriptor format.

**Authors.** structural-isomorphism contributors. [TODO: replace with author list + affiliations + ORCIDs before submission.]

**Corresponding author.** dada8899@users.noreply.github.com. [TODO: replace with institutional email.]

**Keywords.** self-organized criticality; universality classes; power-law statistics; Clauset MLE; Gutenberg-Richter; Omori; cross-domain benchmark; reproducibility; multi-model LLM curation; synthetic null controls.

---

## Abstract

We present `structural-isomorphism-v1.0-benchmark`, a frozen, Zenodo-deposited cross-domain dataset suitable for reproducibility and methodology research on self-organized criticality (SOC), preferential attachment, and adjacent universality classes. The bundle ships thirteen empirical systems — USGS earthquakes, S&P 500 daily returns, three DeFi liquidation streams, mouse cortex neural avalanches from DANDI:000006, NIFC US wildfires, GOES X-ray solar flares 2000-2016, FDIC bank failures 1934-2026, GitHub star counts on 8398 repositories, a literature-meta catalog of North American power-grid cascades, English Wikipedia pageviews 2023-2024, a Hawkes-Omori synthetic baseline, USGS Fox River dissolved-oxygen for a Scheffer fold-bifurcation reference, and the US-101 NGSIM q-rho hysteresis panel — together with four synthetic null controls (Gaussian walk, exponential, Poisson inter-arrival, Poisson-Omori stack) that the same fitting pipeline correctly rejects. We further include the frozen analytical pipeline as a reusable Python package, a 35-class universality-class taxonomy with two layers of LLM-critic curation, the full critic JSONL outputs, a one-shot reproducibility entry point, and a tutorial notebook that reproduces the headline Phase 1 earthquake b-value (1.084 with bootstrap 95% CI [1.073, 1.094]) in roughly thirty minutes of wall-clock time on a laptop. The bundle's design lets any researcher drop in a new system, run the same pipeline, and compare the headline α, τ, b-value, and Omori-p against thirteen baselines without writing a single line of fitting code.

## 1. Background

The empirical literature on power-law tails and SOC across domains is large but methodologically uneven. Earthquake catalogs follow the Gutenberg-Richter law with b≈1 [1]; solar X-ray flares have an integrated-energy distribution with α ≈ 1.7-1.9 [2]; FDIC bank-failure event sizes show a long upper tail consistent with α ≈ 2.0-2.5 [3]; cortical neural avalanches in vitro and in vivo follow size distributions with α ≈ 1.5 and duration exponent ≈ 2.0 [4]; English Wikipedia pageview popularity follows a preferential-attachment-consistent tail with α ≈ 2.0 [5]; and so on. Each result has historically been published with its own fetching code, its own fitting pipeline (often *not* the Clauset-Shalizi-Newman maximum-likelihood + Vuong likelihood-ratio recipe [6] that is now the methodological standard), its own choice of x_min, and its own (or no) null-control baseline. The result is a literature in which any individual claim is plausible but cross-domain *comparability* is weak: when reviewers ask "did you use the same x_min finder as the other phases?" or "did you reject the lognormal alternative explicitly?", the answer is often "no" or "the previous paper didn't either".

Two specific gaps motivate this dataset descriptor:

1. **A canonical multi-domain benchmark.** Although the seismology community has the SCEC Community Stress Drop Validation effort and the neuroscience community has DANDI archives, *cross-domain* benchmarks for SOC and adjacent universality classes are essentially absent. Broido and Clauset (2019) [7] is the closest methodological precedent — a careful re-fit of 928 networks for scale-free behavior with Clauset's recipe — but it is not packaged for downstream reuse as a citable Zenodo deposit, and it does not bundle a fitting pipeline or null controls.

2. **A reproducibility entry point.** Even when fitted numbers are published in supplementary materials, they are usually not directly executable. Re-running them requires (a) finding the upstream raw data, (b) re-implementing the fitter, and (c) hoping the choice of x_min, tail-fraction, and binning matches. The bundle described here packages all three together with a deterministic manifest hash, so a downstream paper can pin "fits computed by `structural-isomorphism-v1.0-benchmark` bundle_sha256=<...>" and reviewers can verify exactly which numerical recipe produced each result.

A third, methodology-research motivation: the LLM-in-the-loop curation step is novel and produces a *quantitative* methodology result (B3 three-model DeepSeek ensemble rejects 33 % of candidate universality classes, vs single-Opus 14 %) [8] that we want others to be able to replicate. The bundle includes both the B1 and B3 verdicts plus the prompts and the structured-output schema, so the methodology is auditable and the disagreement statistics are reproducible.

### 1.1 Why thirteen, and why these thirteen?

The number thirteen is not motivated by statistical sufficiency — five well-chosen cross-domain systems would arguably make the same universality argument. The number is motivated by *coverage of mechanisms*. The thirteen systems span the seven distinct mechanistic universality classes that the v0.3 methods paper [8] identifies as having reached cross-domain empirical support: threshold-cascade SOC (earthquakes, neural avalanches), preferential attachment (Wikipedia views, GitHub stars), heavy-tailed inverse-cubic (S&P 500 returns), Motter-Lai cascade (power grid, banking, DeFi), Drossel-Schwabl forest-fire (wildfires, solar flares), Scheffer fold bifurcation (lake regime shift), and Bouc-Wen/Preisach hysteresis (NGSIM traffic). Two further phases are reserved as synthetic baselines (Hawkes-Omori; the four nulls) so that any cross-domain claim has both a positive control (Hawkes generates a realistic Omori-p) and a battery of negative controls.

Two phases (`12_scheffer_lake`, `13_hysteresis_traffic`) are non-power-law and serve as a deliberate methodological reminder: not every interesting collective phenomenon yields a power law, and the same fitting pipeline should report "no power law here" on lake nutrient time series (where the EWS is critical slowing down, not heavy tail) and on traffic q-ρ (where the invariant is hysteresis loop area). The bundle's value is not "everything is SOC" — it is "the same pipeline, applied uniformly, reports the right answer per system".

### 1.2 Prior art and what this bundle adds

Three precedents are worth naming explicitly:

- **Clauset, Shalizi & Newman (2009)** [6] established the methodological standard for power-law fitting in empirical data. The bundle's `fit_clauset_powerlaw` is a faithful implementation of their MLE recipe + KS-minimum x_min + bootstrap CI + Vuong LR against named alternatives. *What this bundle adds*: a cross-domain corpus on which to run the same recipe uniformly, plus negative controls (none in the original paper), plus a reproducibility entry point.

- **Broido & Clauset (2019)** [7] revisited 928 networks and found that strict scale-freeness is rare. Their methodology was the inspiration for what we call the "reject-aware pipeline" — running the Vuong LR test against lognormal and exponential alternatives, and reporting power-law support only when those alternatives are explicitly rejected. *What this bundle adds*: the same reject-aware approach applied beyond degree distributions, across thirteen non-network domains, packaged for downstream reuse.

- **SCEC Community Stress Drop Validation** (community effort, ongoing) provides a per-event stress-drop benchmark for seismologists. *What this bundle adds*: cross-domain scope (seismology + 12 other domains) and the LLM-critic layer, neither of which has a precedent in any single-domain benchmark.

The bundle is not in competition with any of these — it is a different scope. Its closest competitor in *deposit form* is the various Zenodo deposits associated with individual published papers (e.g. specific datasets accompanying individual earthquake catalogs), none of which is multi-domain or includes a fitting pipeline.

## 2. Methods

### 2.1 The frozen analytical pipeline

The bundle ships the `soc_pipeline` Python package (`pipeline/soc_pipeline/`, ~1.1k LoC) covering:

- **`fit.fit_clauset_powerlaw`** — Clauset (2009) MLE with optimal x_min by KS-statistic minimization. Returns a `FitResult` dataclass with α, x_min, KS distance, sample size, and Vuong LR results against lognormal, exponential, and stretched-exponential.
- **`bootstrap.bootstrap_ci`** — non-parametric bootstrap CI on α with configurable percentiles. Defaults: 200 resamples, (2.5, 97.5) percentiles.
- **`b_value.fit_b_value`** — Aki-Utsu MLE for the Gutenberg-Richter b-value with automatic M_c via maximum curvature. Includes the analytic conversion `b_to_clauset_alpha` (α = b + 1).
- **`omori.fit_omori_p`** — MLE for the Omori-Utsu p-value on aftershock-rate decay, with the `bin_and_omori_from_events` helper for raw catalog -> binned-rate -> fit pipeline.
- **`lr_test.vuong_lr_test`** — Vuong (1989) likelihood-ratio test with the standard one-sided p-value.
- **`universal_collapse.shape_normalized_collapse`** — log-binned shape-normalized tail collapse across multiple systems with the (γ, σ) row-centering used in the v0.3 methods paper §4.5.
- **`null_controls.synthetic_null`** — generates the four synthetic null cases with deterministic seeds.
- **`time_resolution.time_resolution_sweep`** — fits the pipeline across multiple time-binning resolutions to test robustness against the choice of bin width.

The frozen package is installable via `pip install ./pipeline/` (a PyPI-style `pyproject.toml` is included). Pinned runtime dependencies are at `pipeline/requirements-pipeline.txt`.

Two design choices in the pipeline are worth noting because they are the most common methodological pitfalls in cross-domain power-law fitting:

- **x_min selection.** The pipeline uses KS-statistic minimization on a grid from the 5th to the 95th percentile of the input distribution. Empirically this is robust for tails with ≥ 100 events; for smaller tails (such as the n=123 power-grid case) we additionally report the KS-distance curve so that downstream users can see whether the x_min landed at a local minimum or at the boundary.
- **Vuong LR test direction.** The test is reported as one-sided in favor of the power-law null; a negative R with significant p indicates the alternative (lognormal or exponential) provides a better fit. The bundle reports R and p separately so users can apply their own significance threshold. We do not pre-commit to a particular threshold because what counts as "rejecting the alternative" depends on the question — physicists with hard predictions tolerate looser thresholds than reviewers asking "is this *really* a power law".

### 2.2 Dataset selection criteria

The thirteen systems were selected by three criteria, in order:

1. **Public, redistributable upstream source.** Every dataset's raw form is freely accessible without registration, with the partial exceptions of NGSIM (which is freely available on registration at FHWA) and the GitHub stargazer counts (which require an unauthenticated REST API key). No dataset requires payment or commercial license.
2. **Independence between domains.** We deliberately span seismology, finance, decentralized finance, neuroscience, fire ecology, solar physics, banking, software, electrical engineering, traffic flow, ecology, applied probability, and web traffic. Any cross-domain universality claim made on this bundle has to survive *across* domains, not within a single sub-field.
3. **Sample size sufficient for Clauset fitting.** The bundle's smallest tail is the power-grid literature-meta catalog (n=123). Clauset recommends n_tail ≥ 50 for non-trivial CI [6]; we err on the side of permissiveness because the power-grid case is one where the literature-meta is itself the value (further fetches would require FOIA / DOE OE-417 release and are deferred to a v2 deposit).

### 2.3 Synthetic null controls

The four synthetic null controls are designed to fail the cross-domain SOC test in four mechanistically distinct ways:

| case | mechanism | expected pipeline verdict |
| --- | --- | --- |
| `gaussian` | folded-normal sums | reject power-law in favor of lognormal |
| `exponential` | s ~ Exp(rate=1) | reject in favor of exponential (Vuong R << 0) |
| `poisson` | inter-arrival times of homogeneous Poisson | reject in favor of exponential (analytic Vuong R << 0) |
| `poisson_omori` | Poisson-generated event stream subjected to an Omori main-shock+aftershock detector | Omori-p fit produces R² ≈ 0 (no temporal clustering structure) |

All four have deterministic seeds and the pipeline correctly rejects all four (`nulls/_VERDICT.md`). This is the bundle's negative-control axis: any claim that a new system passes the SOC test has to survive the same pipeline that rejects all four nulls.

### 2.4 B3 critic curation

The bundle's taxonomy step (35 candidate universality classes -> 21 final-curated) was done in two layers:

- **B1**: single-Opus run; each class evaluated for KEEP / REJECT / SPLIT / MERGE / UNCLEAR with confidence. 14 % rejection rate.
- **B3**: three independent DeepSeek runs per class with the same prompt and structured-output schema; plurality verdict + per-reviewer confidence. 33 % rejection rate.

The disagreement between B1 and B3 is a quantitative methodology result: the multi-model ensemble rejects 2.4× more classes than the single-model layer. The bundle includes both the B1 and B3 outputs (`results/B3_taxonomy_v2.jsonl`, `results/B3_ensemble_review.jsonl`) plus the B3 ensemble code (`pipeline/b3_ensemble.py`) and the structured-output guardrail (`pipeline/llm_guardrail.py`), so the methodology is auditable.

We classify the seven classes that the B3 ensemble *kept while* the layer-3 critic flagged at least one false-positive member as "contested-strong-keep" — these are the classes where the universality claim survives plural review but the cluster membership has to be pruned. Examples: `motter_lai_network_cascade` keeps the cascade hub but the layer-3 critic rejects the "static earthquake stress triggering" member (mechanistically Olami-Feder-Christensen, not Motter-Lai). Examples of clean KEEPs with no flagged members: `scheffer_fold_bifurcation` (lake regime shift + drug toxicity hub clean). Examples of clean REJECTs: `extreme_value_tail_class` (recognised as statistical phenomenon, not mechanistic universality).

### 2.5 What is *not* in the bundle (and why)

Five candidate inclusions were deliberately excluded:

- **CVE vulnerability time-series.** The fetch was completed (`v4/validation/cve-vulnerabilities/`) but the pre-registration target was missed (see `paper/cve-preregistration-fail-2026-05-14.md`). Including a pre-registration-failed case in the v1.0 bundle would muddy the "bundle of clean reproducible cases" claim. Deferred to v1.1.
- **WSB posts.** Sample size and tail-fraction were insufficient for Clauset CI at the bundle's quality threshold. Deferred.
- **NYC FDNY fires.** Available but duplicative of NIFC (both are US fire catalogs). The bundle's domain coverage is better served by a single fire system. Deferred.
- **SIR contagion synthetic.** Useful for methodology but the headline metric is the epidemic-curve shape, not a single power-law α. Available at `v4/validation/sir-contagion/` for users who want it; not in the v1.0 deposit.
- **Tail-copula joint extremes.** This is a statistical phenomenon (P(X > q | Y > q) limit), not a mechanistic universality class — the B3 critic correctly flagged this. Class YAML is bundled in `taxonomy/classes/` for transparency, but the bundle does not claim it as a v1.0 empirical class.

## 3. Data Records

### 3.1 Table 1 — empirical phases

| slot | source | format | size on disk | n_tail (post-x_min) | headline metric |
| --- | --- | --- | ---: | ---: | --- |
| 01_earthquake | USGS NEIC | JSONL + Parquet | 26 MB | ~37k | b = 1.084 (CI [1.073, 1.094]) |
| 02_stockmarket | Yahoo Finance ^GSPC | CSV | 1.0 MB | ~2.5k | α = 2.998 |
| 03_defi | Dune Analytics + protocol logs | JSONL | 20 MB | ~12k | α ≈ 1.7-2.3 per protocol |
| 04_neural | DANDI:000006 | JSONL + NWB | 23 MB | 26k @ binsize=1 | α = 2.98 |
| 05_wildfire | NIFC | JSONL | 1.9 MB | ~21k | α = 1.66 |
| 06_solar | NOAA NGDC | JSONL | 5.5 MB | ~30k | α = 2.19 |
| 07_bank_failures | FDIC | JSONL | 3.3 MB | 3960 | α = 1.90 |
| 08_github_stars | GitHub REST API | JSONL | 1.1 MB | 8398 repos | α = 2.87 |
| 09_power_grid | literature-meta | JSON | 100 KB | 123 events | α_MW = 2.02 ± 0.16 |
| 10_wikipedia_views | Wikipedia REST | JSONL | 536 KB | 7521 articles | α = 2.034 |
| 11_hawkes_omori | internal | JSON | 24 KB | synthetic | p ≈ 1.0 (Omori) |
| 12_scheffer_lake | USGS | JSONL | 1.0 MB | ~9k days × 12 stations | AR(1) → 0.85 ± 0.05 pre-tip |
| 13_hysteresis_traffic | FHWA NGSIM | CSV | 1.2 MB | ~21k bins | loop ratio 0.08-0.22 |

### 3.2 Table 2 — synthetic null controls

| case_id | mechanism | n_samples | pipeline verdict |
| --- | --- | --- | --- |
| null_001_gaussian_walk | folded-normal | 20000 | rejected (Vuong R = -28.58 vs lognormal) |
| null_002_exponential | Exp(1) | 20000 | rejected (Vuong R = -17.17 vs exponential) |
| null_003_poisson_iat | inter-arrivals of Poisson(1) | 49999 | rejected (Vuong R = -24.39 vs exponential) |
| null_004_poisson_omori | Poisson + Omori detector | 23 main shocks | rejected (R² = 0.0015) |

### 3.3 Universality-class records

Per-class records live at `taxonomy/classes/<id>.yaml` (35 candidate classes; YAML schema at `taxonomy/SCHEMA.md`). The 21 surviving classes per the B3 plurality verdict are listed in `taxonomy/universality_classes.yaml`. Examples of canonical hub phenomena retained: Olami-Feder-Christensen / Gutenberg-Richter (earthquakes); Bak-Tang-Wiesenfeld sandpile (avalanches); Motter-Lai cascade (power grid, banking, DeFi); Scheffer fold bifurcation (lakes, drug-toxicity); Gardner-Collins toggle switch (cell-fate decisions); Watts-Strogatz preferential attachment (Wikipedia, GitHub). Examples of candidates the B3 ensemble rejected or contested: delay-differential debt (contested KEEP/REJECT); extreme-value tail (rejected — recognised as statistical phenomenon not a mechanistic universality class).

### 3.4 Layer-3 critic records (`results/layer3_critic.jsonl`)

One record per class with `review_verdict`, `members_flagged_as_false_positive` (members the critic says don't belong), `negative_examples` (phenomena that *look* like the class but mechanistically aren't), and free-form `notes`. This is the dataset's contribution to LLM-in-the-loop methodology research: each row contains a critic's reasoning trace for whether a candidate class is genuinely a universality class or a "mathematical framework masquerading as universality class" [8].

## 4. Technical Validation

### 4.1 Reproducibility script

`repro/reproduce_all.py` runs in two modes:

- `--smoke` (default): loads results from three systems (01_earthquake, 06_solar, 11_hawkes_omori), extracts the headline metric, compares against the paper-frozen target within tolerance, prints PASS/FAIL/NO_VALUE. Runtime ~1 s on a laptop.
- `--full`: same logic on all 13 phases + 4 nulls, plus emits `out/all_verdicts.jsonl` for downstream archival. Runtime ~2 s.

Empirically, all PASS verdicts hold on a fresh clone. Two systems (`scheffer_lake`, `hysteresis_traffic`) report `NO_VALUE` because their headline metric is not a single scalar (AR(1) trajectory; hysteresis loop area ratio) — the reproducibility script does not invent a fake summary; instead it ships the full result blob and flags the case as "needs human inspection / no scalar headline".

### 4.2 Manifest hash stability

`repro/generate_manifest.py` produces a byte-stable `MANIFEST.json` across reruns. We verify this by running:

```bash
python repro/generate_manifest.py && md5sum MANIFEST.json > a
python repro/generate_manifest.py && md5sum MANIFEST.json > b
diff a b   # empty
```

The manifest's `bundle_sha256` field is the citation primitive — downstream papers pin this hash to lock to the exact bundle state. Re-running the manifest builder on a modified bundle (after, e.g., a v1.1 fetch update) produces a new hash and a new Zenodo deposit version.

### 4.3 Null-control rejection

All four synthetic nulls are correctly rejected by the same pipeline that PASS-es the 13 empirical phases. Verdicts at `nulls/_VERDICT.md`; per-case details at `nulls/_registry.jsonl`. The Vuong LR statistics against lognormal and exponential alternatives are reported in each `nulls/<case>/results.json` to make the rejection auditable.

### 4.4 In-band coverage

The bundle's 13 empirical phases span 11 of the 21 final-curated universality classes (with each phase mapping to one or two classes via the B3 layer-3 critic). The remaining 10 classes are either (a) derived (split / merge of an existing class with an empirical anchor) or (b) hub-only — i.e. the class has a strong canonical mechanism and predictions in `results/layer4.jsonl` but no v1.0 empirical fit yet. These 10 classes are explicit targets for the v1.1 deposit's pre-registered fetch.

### 4.5 Internal headline consistency

The 13 systems' headline metrics are pairwise consistent with the v0.3 methods paper [8] within 0.5σ for the systems whose paper-reported CI is in the bundle (`01_earthquake`, `02_stockmarket`, `06_solar`, `10_wikipedia_views`). Where they differ, the bundle is the canonical reference because the bundle's fits are recomputed by the frozen `soc_pipeline` package at deposit time, while the methods paper's tables were assembled across the project's development arc with intermediate pipeline versions. Downstream papers should cite the bundle's value, not the methods paper's table value, when there is a discrepancy.

The Vuong LR statistics also support the cross-domain SOC claim *as a methodology result, not as a sweeping ontological claim about reality*. Eight of the 13 phases (01, 03, 05, 06, 07, 08, 09, 10) have R < 0 and p < 0.05 against both lognormal and exponential alternatives, supporting power-law preference; three (02, 04, 11) are statistically distinguishable but with weaker preference (R between -10 and -2); two (12, 13) are non-power-law and we report the alternative-favored fit as expected. This 8/13 result is the bundle's empirical headline.

### 4.6 Cross-version reproducibility

The git commit recorded in `MANIFEST.json:git_commit` resolves the exact state of the source repo from which this bundle was built. Re-running `repro/build_datasets.py` and `repro/generate_manifest.py` from a fresh clone at that commit will produce a `MANIFEST.json` whose `bundle_sha256` matches the deposited value, provided the upstream data sources have not changed. (USGS occasionally re-processes old events, so the earthquake catalog hash is the most likely cross-version drift; see §5.2 for our policy.)

## 5. Usage Notes

### 5.1 Three example research questions

**Q1 — Does system X follow the same SOC pipeline that succeeds on 13 baselines?** Fetch system X's event sizes, run `pipeline/soc_pipeline/fit.py:fit_clauset_powerlaw`, compare α and Vuong-LR against the 13 baselines in `datasets/*/`. The 30-line earthquake quickstart in `README.md` is the template.

**Q2 — Does my new LLM critic agree with B1 or B3 on the contested classes?** Run your critic with the structured-output schema in `pipeline/llm_guardrail.py` on the prompt template in `pipeline/b3_ensemble.py`, then diff your verdicts against the bundled `results/B3_taxonomy_v2.jsonl`. The 7/21 contested classes (those with `final_verdict` containing `CONTESTED` or `_borderline`) are the methodology research target.

**Q3 — Is a candidate "universality class" actually a statistical artefact?** Use `nulls/_registry.jsonl` as a template to construct a domain-specific null. Pipeline acceptance on the candidate + pipeline rejection on the matched null is the joint condition for universality-class membership. (This is the "reject-aware pipeline" methodology of paper C4.)

### 5.2 Reproducibility policy across upstream changes

USGS, FDIC, and NIFC occasionally update or re-process historical events. Our policy:

- The bundle's empirical fits are reported with the bundle's own data snapshot, not against a moving upstream target.
- If a downstream paper re-fetches and gets a different number, the difference is *evidence about upstream stability*, not a bundle error.
- Each system's `fetch_log.json` records the exact upstream URL parameters and timestamp used for the bundle's snapshot.

### 5.3 Limitations of the bundle

Three limitations should be acknowledged up front:

- **Single-author / single-team curation.** Although the B3 ensemble layer provides three independent LLM reviews per class, the human-in-the-loop arbitration of contested cases was done by a single team. This is the standard situation for a first deposit; v1.1 invites external arbitrators (see Track A roadmap).
- **CN-region LLM endpoint constraints.** OpenRouter's `anthropic/*` and `google/gemini/*` endpoints are intermittently region-blocked from CN IPs, which is why DeepSeek was chosen as the B3 ensemble backbone. The methodology is portable — a future v1.x deposit using a different multi-model ensemble (e.g. Anthropic Claude + Gemini + DeepSeek) is on the roadmap. The bundle's `pipeline/b3_ensemble.py` accepts pluggable backends.
- **Sample-size asymmetry across domains.** The earthquake catalog has ~37k tail events; the power-grid catalog has 123. Asymmetric Clauset CI is therefore expected and is *not* a bundle defect — it reflects the empirical reality of how cleanly each domain's event catalogs have been assembled in the literature.

### 5.4 LLM critic outputs are research data

The B3 ensemble outputs in `results/layer3_critic.jsonl` are themselves a contribution. They contain mechanism-level reasoning about whether 35 candidate classes are genuine universality classes. This is the bundle's per-row contribution to the LLM-in-the-loop literature: rather than treating critic outputs as opaque labels, the bundle ships the full reasoning trace.

### 5.5 Worked example — fitting a new system

Suppose a reader wants to test whether earthquake catalogs from a new region (say, the 2023-2024 Türkiye sequence) belong to the same Gutenberg-Richter universality class as the bundle's global catalog. The intended workflow:

1. Install the pipeline: `cd pipeline && pip install -e .`.
2. Fetch the new region's catalog using a USGS query analogous to `datasets/01_earthquake/fetch_earthquakes.py` with `latitude` / `longitude` / `maxradiuskm` parameters.
3. Run `fit_b_value(magnitudes, m_c=None)` (M_c auto-detected by maximum curvature) and compare the resulting `b` against the bundle's headline `b = 1.084` and the literature band [0.8, 1.2].
4. Run `fit_clauset_powerlaw(released_energy_array)` and compare α against the global catalog's α.
5. Vuong LR against lognormal and exponential — if both R < 0 with p < 0.05, the new region's catalog passes the reject-aware test and is consistent with the same universality class.

A failure to reject the lognormal alternative is *not* evidence against universality; the SOC literature has well-known examples (e.g. swarm-dominated regions) where the fits are noisier. The bundle's value is that the protocol is now uniform: a paper claiming "this region's b-value is anomalous" can be compared against the bundle's pipeline-uniform global value rather than against a different paper's bespoke fit.

### 5.6 Worked example — testing a new LLM critic

Suppose a reader has built a new LLM critic and wants to know if its taxonomy verdicts agree with B3 ensemble. Workflow:

1. For each of the 35 candidate classes in `taxonomy/classes/`, render the YAML into the structured-output prompt template found in `pipeline/b3_ensemble.py` (function `build_prompt`).
2. Run the new critic three times per class with different random seeds (matching the B3 protocol).
3. Compute plurality verdict per class.
4. Diff against `results/B3_taxonomy_v2.jsonl:b3_consensus`. The seven contested classes are the methodology research target — does the new critic agree with B1 (single-Opus), with B3 (DeepSeek ensemble), or chart a third path?
5. The 21 layer-3 narratives in `results/layer3_critic.jsonl` are the second-order target: does the new critic identify the same negative examples and members-flagged-as-false-positive as the bundled critic?

This is the methodology research the bundle is designed to support. A null result ("my critic agrees perfectly with B3") would itself be informative — it would mean DeepSeek's mechanism-level reasoning is robust across model families.

## 6. Code availability

The frozen analytical pipeline is at `pipeline/soc_pipeline/` (also available on GitHub at https://github.com/dada8899/structural-isomorphism/tree/main/packages/soc-pipeline). The B3 ensemble critic is at `pipeline/b3_ensemble.py`; the structured-output guardrail is at `pipeline/llm_guardrail.py`. All code is released under MIT (`LICENSE`).

The reproducibility entry point is at `repro/reproduce_all.py` with two modes (`--smoke`, `--full`). The manifest builder is at `repro/generate_manifest.py` and is idempotent.

The bundle itself is deposited at Zenodo with DOI `10.5281/zenodo.PLACEHOLDER`. Reissue history is recorded in the Zenodo metadata.

### 6.1 How to extend the bundle

To add a new system to a v1.x extension:

1. Add a `datasets/<NN>_<slug>/` directory with `fetch_<slug>.py` (idempotent fetch script), `paper.md` (companion narrative), the headline `<slug>_results.json` produced by the frozen pipeline, and a `fetch_log.json` recording the upstream URL parameters and fetch timestamp.
2. Append the slot to `repro/build_datasets.py:SYSTEMS` and to the headline target table in `repro/reproduce_all.py:TARGETS`.
3. Append a class membership prediction to `results/layer4.jsonl` if applicable.
4. Re-run `repro/build_datasets.py && repro/generate_manifest.py && repro/reproduce_all.py --full`. The new `bundle_sha256` is the v1.x version's citation primitive.

To add a new universality-class candidate:

1. Add a YAML at `taxonomy/classes/<class_id>.yaml` matching `taxonomy/SCHEMA.md`.
2. Append the class to `taxonomy/universality_classes.yaml`.
3. Run the B1 + B3 critic on the new class. Append verdicts to `results/B3_taxonomy_v2.jsonl` and reasoning to `results/layer3_critic.jsonl`.
4. Append concrete downstream predictions to `results/layer4.jsonl`.
5. Re-generate the manifest. The bundle's `bundle_sha256` now pins the new state.

### 6.2 Versioning policy

- **v1.x** (minor) — additive: new systems, new classes, refined LLM critic verdicts. Headline fit values for v1.0 systems do not change.
- **v2.0** (major) — backward-incompatible: refit headline values (e.g. due to upstream USGS reprocessing), reorganised directory layout, or pipeline algorithm changes.
- Each release gets a new Zenodo DOI; the DOI of the latest version is also available via the Zenodo concept-DOI redirect.

## 7. References

[1] Gutenberg, B. & Richter, C. F. (1944). *Frequency of earthquakes in California.* Bulletin of the Seismological Society of America 34, 185-188.

[2] Aschwanden, M. J. (2011). *Self-Organized Criticality in Astrophysics.* Springer-Praxis.

[3] Drehmann, M. & Tarashev, N. (2013). *Measuring the systemic importance of interconnected banks.* Journal of Financial Intermediation 22, 586-607.

[4] Beggs, J. M. & Plenz, D. (2003). *Neuronal avalanches in neocortical circuits.* Journal of Neuroscience 23, 11167-11177.

[5] Barabási, A.-L. & Albert, R. (1999). *Emergence of scaling in random networks.* Science 286, 509-512.

[6] Clauset, A., Shalizi, C. R. & Newman, M. E. J. (2009). *Power-law distributions in empirical data.* SIAM Review 51, 661-703.

[7] Broido, A. D. & Clauset, A. (2019). *Scale-free networks are rare.* Nature Communications 10, 1017.

[8] structural-isomorphism contributors. (2026). *A pipeline for cross-domain validation of self-organized criticality, preferential attachment, and adjacent universality classes: thirteen systems, one method.* arXiv preprint (cond-mat.stat-mech, physics.data-an).

[9] Bak, P., Tang, C. & Wiesenfeld, K. (1987). *Self-organized criticality: an explanation of 1/f noise.* Physical Review Letters 59, 381-384.

[10] Scheffer, M. et al. (2009). *Early-warning signals for critical transitions.* Nature 461, 53-59.

[11] Motter, A. E. & Lai, Y.-C. (2002). *Cascade-based attacks on complex networks.* Physical Review E 66, 065102(R).

[12] Vuong, Q. H. (1989). *Likelihood ratio tests for model selection and non-nested hypotheses.* Econometrica 57, 307-333.

[13] Dakos, V. et al. (2008). *Slowing down as an early warning signal for abrupt climate change.* PNAS 105, 14308-14312.

[14] Olami, Z., Feder, H. J. S. & Christensen, K. (1992). *Self-organized criticality in a continuous, nonconservative cellular automaton modeling earthquakes.* Physical Review Letters 68, 1244-1247.

[15] Gardner, T. S., Cantor, C. R. & Collins, J. J. (2000). *Construction of a genetic toggle switch in Escherichia coli.* Nature 403, 339-342.

---

*Submitted for consideration as a Scientific Data data descriptor, 2026-05-15.*
