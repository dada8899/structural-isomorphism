# v0.4 plan: 18 unverified universality classes — empirical anchors

**Target**: v4/validation/ from 27 systems → 43+ systems; 26 classes from 8/26 verified → 26/26 verified
**Deliverable**: v0.4 unified preprint (C1) with full taxonomy closure
**Plan version**: draft 2026-05-25
**Source**: `web/frontend/assets/data/universality-classes.json` (26 classes, manifest version 0.3, b3_review_done=true)

> Scope note: the task brief mentioned "16 classes" but the JSON actually contains 18 classes with `verified ≠ true` (15 explicit `false` + 3 with the field missing — `fractional_brownian_crossings`, `anderson_localization`, `preisach_hysteresis_cascade`, all marked as speculative / well-established textbook classes added during the taxonomy-completion sweep). All 18 are planned below.

---

## Class status matrix

Sorted by priority (★★★★★ first), then by est. workload.

| class_id | name_zh | b3 | priority | est. workload | primary data source | dependency | risk |
|---|---|---|---|---|---|---|---|
| `gardner_collins_toggle_switch` | 双稳态 Toggle Switch 类 | MERGE | ★★★★★ | 9 h / 1–1.5 d | Tabula Muris Senis CD4 atlas + ImmPort SDY1412 | scanpy, sklearn | scRNA dropout inflates bimodality |
| `delay_differential_debt` | 延迟反馈与债务累积类 | REJECT | ★★★★★ | 16 h / 2 d | PREDICTS biodiversity time series + NOAA ENSO | jitcdde, lmfit | DDE inference local minima; **expected REJECT is a feature** |
| `tail_copula_contagion` | 尾部相关 / Copula 传染类 | REJECT | ★★★★ | 10 h / 1.5 d | Yahoo Finance S&P + VIX 2000–2025 | yfinance, arch, copulas | survivorship bias; descriptor-not-mechanism |
| `extreme_value_tail_class` | 极值理论重尾分布类 | REJECT | ★★★★ | 7 h / 1 d | Dryad seed-dispersal database | pyextremes, powerlaw | descriptor-not-mechanism collapse |
| `reflexive_fixed_point_class` | 反身性不动点与测量反馈类 | KEEP | ★★★★ | 10 h / 1.5 d | Leiden Ranking + WoS faculty panel | linearmodels (DiD) | WoS access dependency |
| `percolation_connectivity` | 渗流临界相变与 tipping point 类 | SPLIT | ★★★★ | 16 h / 2 d | Reddit Pushshift + Politosphere | networkx, pyzstd | finite-size scaling needs span of 2 orders |
| `gardner_collins_toggle_switch_v2` | Hill 超敏正反馈双稳态开关类 | MERGE | ★★★★ | 11 h / 1.5 d | Anetzberger 2009 V. harveyi QS supplementary | lmfit | merge collision with v1 |
| `reaction_diffusion_steady_state_class` | 稳态反应-扩散梯度场类 | KEEP | ★★★★ | 12 h / 1.5 d | NASA Landsat 8/9 TIR Shanghai/Beijing | rasterio, GEE | cloud cover; centre-detection bias |
| `schelling_credible_commitment` | 可信承诺 / 时间不一致类 | REJECT | ★★★ | 10 h / 1.5 d | WTO Dispute DB (World Bank Horn–Mavroidis) | statsmodels | sunk-cost requires manual coding |
| `leaky_integrate_fire_threshold_class` | 泄漏积分-阈值释放类 | SPLIT | ★★★ | 13 h / 2 d | SOEP life-satisfaction panel + Allen Brain | allensdk, statsmodels | SOEP registration delay (≥ 2 wk) |
| `adverse_selection_unraveling_class` | 逆向选择与柠檬化退化类 | SPLIT | ★★★ | 17 h / 2 d | Reddit Pushshift political subset | bertopic, pyzstd | GPU recommended; topic drift |
| `hysteresis_first_order_transition` | 双稳态陷阱与一阶相变迟滞类 | MERGE | ★★★ | 11 h / 1.5 d | OECD Family DB + WDI fertility | oecd-data, wbdata | merge collision with Scheffer + Preisach |
| `scale_free_percolation_class` | 无标度网络渗流与级联类 | REJECT | ★★★ | 12 h / 1.5 d | DefiLlama LSD + Etherscan | networkx, powerlaw | address clustering ambiguity |
| `second_order_damped_oscillator` | 二阶阻尼振子类 | KEEP | ★★★ | 10 h / 1.5 d | Tamura AIJ damping DB (~200 buildings) | beautifulsoup4, scipy.signal | template-vs-mechanism boundary |
| `fractional_brownian_crossings` | 分数布朗运动零交叉类 | (none) | ★★★ | 11 h / 1.5 d | LOBSTER LOB free sample + USGS streamflow | nolds, MFDFA | H estimator disagreement; **no KB predictions yet** |
| `preisach_hysteresis_cascade` | Preisach 迟滞级联 | (none) | ★★★ | 12 h / 1.5–2 d | Zenodo Barkhausen series (hunt) + LOBSTER stretch | powerlaw | data discovery friction; **no KB predictions yet** |
| `markov_chain_memory_fidelity_class` | 马尔可夫链状态记忆保真类 | REJECT | ★★ | 8 h / 1 d | PJM hourly gen + EIA-860 | hmmlearn, scipy.stats | descriptor-not-mechanism, expected REJECT |
| `anderson_localization` | Anderson 局域化 | (none) | ★★ | 15 h / 2 d | Billy 2008 Nat cold-atom data OR own tight-binding sim | scipy.sparse.linalg, optional cupy | synthetic-not-empirical fallback; **no KB predictions yet** |

**Total estimated workload**: ~190 hours of sub-agent compute (parallelisable across 16–18 sub-agents in 2–3 days wall-clock, calendar 2–3 weeks accounting for data-access registrations).

---

## Execution waves (recommended)

### Wave A (week 1) — high-priority, low-risk (6 classes)

Run first because: clean math, free/fast data, mechanism interpretation defensible, and PASS/REJECT both informative.

| class | rationale |
|---|---|
| `gardner_collins_toggle_switch` | Tabula Muris is free + immediate; cleanest mechanism class |
| `extreme_value_tail_class` | Dryad seed-dispersal: 1-day turnaround; tests "descriptor-vs-mechanism" boundary |
| `tail_copula_contagion` | yfinance + VIX: 1.5-day turnaround; high industry interest |
| `reflexive_fixed_point_class` | Leiden Ranking is free + clean natural experiment |
| `reaction_diffusion_steady_state_class` | Landsat TIR is free; closed-form prediction makes verdict crisp |
| `gardner_collins_toggle_switch_v2` | runs paired with v1 to settle the MERGE question |

### Wave B (week 2–3) — medium priority (6 classes)

| class | rationale |
|---|---|
| `delay_differential_debt` | high paper value (B3-confirmed REJECT or surprise PASS) but DDE compute slower |
| `percolation_connectivity` | Pushshift bulk is heavy; finite-size scaling is slow |
| `schelling_credible_commitment` | manual sunk-cost coding is the bottleneck |
| `hysteresis_first_order_transition` | OECD data clean; needs Scheffer cross-comparison |
| `scale_free_percolation_class` | Etherscan rate-limits slow data acquisition |
| `second_order_damped_oscillator` | Tamura scrape easy; cross-domain test needs PMU which may be restricted |

### Wave C (week 4) — high-risk / high-reward, or low-yield-but-needed-for-completeness (6 classes)

| class | rationale |
|---|---|
| `leaky_integrate_fire_threshold_class` | SOEP registration delay forces calendar wait; defer |
| `adverse_selection_unraveling_class` | BERTopic compute-heavy; GPU recommended |
| `fractional_brownian_crossings` | **no KB predictions yet** — needs brief-extension work before validation |
| `preisach_hysteresis_cascade` | **no KB predictions yet** + dataset hunting friction |
| `anderson_localization` | textbook class, fallback to own simulation, low yield for paper |
| `markov_chain_memory_fidelity_class` | expected REJECT, low yield, but cheap so include |

---

## Cross-cutting needs

### New directories under `v4/validation/`

Each of the 18 classes gets a new directory mirroring the existing `soc-earthquake/`, `kpz-interface/`, `manna-sandpile/` template:

```
v4/validation/<class_id>/
  ├── run_validation.py       # entry point
  ├── fetch_data.py           # or inline fetch in run_validation
  ├── results.json            # numeric outputs
  ├── verdict.md              # one-page conclusion
  └── paper.md (optional)     # if section-worthy for v0.4 preprint
```

### Budget estimation

- **LLM costs**: each sub-agent ~$0.50–$2.00 per class (Opus for orchestration + Sonnet/MiniMax for bulk code-gen). Total ~**$30–$50**.
- **Compute**: most pipelines run on CPU. GPU recommended for `adverse_selection_unraveling_class` (BERTopic) and optional for `anderson_localization` (tight-binding FSS).
- **Storage**: peak ~50 GB total — driven by Reddit Pushshift slice (~30 GB) and Landsat TIR (~50 GB max). Allocate **100 GB scratch** for the wave.

### API-key / registration matrix

| Service | Cost | Lead time | Needed for |
|---|---|---|---|
| yfinance (Yahoo / Stooq) | free | none | tail_copula_contagion |
| Etherscan API | free key | minutes | scale_free_percolation_class |
| DefiLlama API | free | none | scale_free_percolation_class |
| NASA Earthdata / Google Earth Engine | free | hours | reaction_diffusion_steady_state_class |
| ECMWF Copernicus CDS (ERA5-Land) | free | hours | reaction_diffusion_steady_state_class (fallback) |
| ImmPort | free | days | gardner_collins_toggle_switch (fallback) |
| SOEP | free academic | **1–2 weeks** | leaky_integrate_fire_threshold_class |
| WoS / OpenAlex | institutional / free | varies | reflexive_fixed_point_class |
| WRDS (Compustat) | institutional | varies | hysteresis_first_order_transition (stretch only) |
| LOBSTER paid | $$ | hours | fractional_brownian_crossings (paid extension) |
| EIA / PJM | free | minutes | markov_chain_memory_fidelity_class |
| EM-DAT (CRED) | free academic | hours | extreme_value_tail_class (fallback) |

---

## Sub-agent dispatch template

Each sub-agent should be invoked with **exactly** this prompt skeleton (parametrised by `<class_id>`):

```
Task: Validate <class_id> empirically against the pre-registered alpha band.

Input artifacts:
  - docs/v04-validation-plan/per-class/<class_id>.md  (this brief)
  - web/frontend/assets/data/universality-classes.json  (class metadata)
  - v4/validation/soc-earthquake/run_validation.py  (template — Gutenberg-Richter MLE pattern)
  - v4/validation/kpz-interface/run_validation.py  (template — finite-size scaling pattern)
  - v4/validation/manna-sandpile/run_validation.py  (template — power-law avalanche pattern)

Workflow:
  1. Read the per-class brief in full
  2. Implement fetch_data step (download to data/<class_id>/)
  3. Implement run_validation.py using the closest template above
  4. Run pipeline, write results.json + verdict.md
  5. Append 5+ entries to data/kb-additions-2026-<MM-DD>-<class_id>.jsonl

Output artifacts (place in v4/validation/<class_id>/):
  - run_validation.py
  - results.json
  - verdict.md
  - paper.md (only if PASS or surprising REJECT — section-worthy)
  - data/kb-additions-2026-<MM-DD>-<class_id>.jsonl  (5+ KB entries)
  - docs/sessions/v04-<class_id>-report.md  (one-page session summary)

Commit policy: DO NOT commit. Leave working-tree changes for main session review.
Budget cap: $5 LLM spend; abort and report if exceeded.
Pre-registration discipline: the alpha band in the per-class brief is binding.
  Do not adjust band after seeing data; INCONCLUSIVE > post-hoc adjustment.
```

---

## v0.4 paper integration plan

1. After all 18 verdicts arrive, write **C1 v0.4 §3.5 "Completing the taxonomy"**:
   - Subsection by wave (Wave A high-priority results first, then B, then C)
   - One paragraph per class summarising: alpha band, verdict, headline number, what it means for the B3 consensus
2. Tabulate verdicts in a single matrix: rows = 18 classes, columns = (B3 prior, alpha band, observed alpha + CI, verdict, B3 prior overturned y/n).
3. Highlight three categories of result:
   - **Expected REJECT confirmed** (descriptor-not-mechanism): `extreme_value_tail_class`, `tail_copula_contagion`, `markov_chain_memory_fidelity_class`, `delay_differential_debt` (if REJECT) — these *strengthen* the C4 thesis with empirical teeth.
   - **MERGE settled**: `gardner_collins_toggle_switch` × `_v2`, `hysteresis_first_order_transition` × `hysteresis_preisach` × `scheffer_fold_bifurcation`, `scale_free_percolation_class` × `percolation_connectivity`.
   - **KEEP surprises**: any class where the empirical PASS contradicts the B3 consensus REJECT (would warrant a stand-alone short note).
4. Negative results = positive science. Don't bury REJECTs — feature them as evidence that the taxonomy *discriminates*.

---

## Risks at plan level

1. **Public-data gaps**: `fractional_brownian_crossings`, `anderson_localization`, `preisach_hysteresis_cascade` have no KB predictions yet — brief-extension work needed before sub-agent dispatch.
2. **Cross-judge instability**: gardner_v2 / motter_lai_v2 already shows the taxonomy is alive; new MERGE/SPLIT decisions from these validations may force re-running already-verified classes.
3. **Descriptor-vs-mechanism cluster**: 4 of 18 are pre-flagged as statistical descriptors, not mechanisms. Even if they PASS the empirical band, the v0.4 paper position must remain "these are stylised facts, not universality classes" — pre-register the interpretation.
4. **SOEP / WRDS access delays**: Wave C may slip if institutional licences aren't already in place. Confirm before dispatch.
5. **B3 consensus drift**: future cross-judge sessions may reassign some of these classes between waves; this plan is keyed to the 2026-05-15 manifest snapshot.

---

## Acceptance criteria

- [x] 18/18 per-class briefs in `docs/v04-validation-plan/per-class/`
- [x] Each brief lists ≥ 2 candidate datasets (most list 3)
- [x] INDEX has wave assignment, workload, dependency, risk for each class
- [x] Sub-agent dispatch template included with hard budget cap
- [x] v0.4 paper integration narrative drafted
- [ ] User signs off on wave A → dispatch sub-agents (next session)
- [ ] All 18 verdicts collected → §3.5 of C1 v0.4 drafted (target 4 weeks from sign-off)

---

## File manifest

```
docs/v04-validation-plan/
├── 16-classes-empirical-anchors.md          (this file — index)
└── per-class/
    ├── adverse_selection_unraveling_class.md
    ├── anderson_localization.md
    ├── delay_differential_debt.md
    ├── extreme_value_tail_class.md
    ├── fractional_brownian_crossings.md
    ├── gardner_collins_toggle_switch.md
    ├── gardner_collins_toggle_switch_v2.md
    ├── hysteresis_first_order_transition.md
    ├── leaky_integrate_fire_threshold_class.md
    ├── markov_chain_memory_fidelity_class.md
    ├── percolation_connectivity.md
    ├── preisach_hysteresis_cascade.md
    ├── reaction_diffusion_steady_state_class.md
    ├── reflexive_fixed_point_class.md
    ├── scale_free_percolation_class.md
    ├── schelling_credible_commitment.md
    ├── second_order_damped_oscillator.md
    └── tail_copula_contagion.md
```
