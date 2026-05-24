***REMOVED*** Expansion Candidates — Structural Isomorphism KB

> **Date.** 2026-05-24
> **Author.** Coverage research subagent.
> **Scope.** Identify which disciplines / sub-fields / phenomena should be added to the
> KB over the next 6 months to widen cross-domain isomorphism search hit-rate. Grounded
> in: W7-A academic roadmap (Track A reference dataset path), C1 v0.2 unified preprint
> (5 SOC phases), 13 validated systems + 4 nulls, B3 taxonomy verdicts, and the
> 38-class YAML in `v4/taxonomy/classes/`.
> **Status.** Draft for human review. Not committed.

---

***REMOVED******REMOVED*** 0. Executive Summary

Current KB is concentrated on **threshold-cascade SOC + preferential attachment + a handful
of bifurcation / hysteresis members**. Five universality classes well-established in
the literature have zero or one empirical entry: **KPZ surface growth**, **directed
percolation (DP)**, **Ising / RFIM**, **Manna / Oslo conserved sandpile**, and
**absorbing-state phase transitions** more generally. These are the largest
"empty-class" gaps.

Cross-disciplinarily the KB has **no coverage** in linguistics, urban science, climate,
ecology beyond Scheffer-lake, sociology, biology evolution, epidemiology, psychology,
education, and public health. Sixteen concrete new systems across 8 disciplines are
proposed below, each with paper, dataset URL, and rough size.

**Top-5 recommended additions for Wave 1 (months 1-2)**:

1. **COVID-19 daily case counts (Omori-decay test)** — JHU CSSE archive, n≈1.5M rows, datasets frozen, replicates the Omori p-value test from Phase 1 in an epidemic system.
2. **TikTok/YouTube video view-count power-law (preferential attachment)** — Kaggle YouTube Trending dataset, n≈400K, fills the social-cascade slot.
3. **English word frequency (Zipf's law)** — Google Books Ngrams, instant fetch, canonical KPZ-adjacent / preferential-attachment test (Mandelbrot 1953, Piantadosi 2014).
4. **City population rank-size (Zipf-Gibrat)** — UN World Urbanization Prospects + US Census, gives a sister-class result to S&P 500 inverse-cubic.
5. **LLM scaling-law loss curves (Chinchilla / emergent ability)** — public training logs from BLOOM / Pythia / LLaMA HF model cards, novel modern candidate, no prior cross-domain SOC paper has tested this.

The complete top-10 priority ranking with scores is in §4. Wave structure for the next
6 months is in §6.

---

***REMOVED******REMOVED*** 1. Discipline-Level Coverage Matrix

***REMOVED******REMOVED******REMOVED*** 1.1 Current 13 systems by universality class

| ***REMOVED*** | System | Phase | Universality class | Saturation |
|---|---|---|---|---|
| 1 | USGS earthquakes | P1 | `soc_threshold_cascade` | gate test |
| 2 | S&P 500 daily returns | P2 | `extreme_value_tail_class` (inverse-cubic) | 1 of class |
| 3 | DeFi Aave/Compound/Maker | P3 | `soc_threshold_cascade` (cascade sub-cluster) | 3 (saturated) |
| 4 | Mouse cortex neural avalanches | P4 | `soc_threshold_cascade` (task-active sub-class) | 1 |
| 5 | Synthetic nulls × 4 | P5 | non-SOC controls | 4 (saturated) |
| 6 | Solar flares | A1 | `soc_threshold_cascade` | (member) |
| 7 | NYC wildfires (FDNY) | A1 | INCONCLUSIVE / FAIL | rejected |
| 8 | US bank failures (FDIC) | A1 | `motter_lai_network_cascade` | 1 |
| 9 | Wikipedia page views | A1 | `preferential_attachment` | 1 |
| 10 | OE-417 power grid | A2 | `motter_lai_network_cascade` (small-n caveat) | 1 |
| 11 | NGSIM US-101 traffic | A2-hyst | `preisach_hysteresis_cascade` | 1 |
| 12 | GitHub stars | A1 | `preferential_attachment` | 2 (saturated) |
| 13 | Fox-River dissolved O2 (Scheffer) | A2-Scheffer | `scheffer_fold_bifurcation` | INCONCLUSIVE |

**Saturation diagnosis**: 3 classes have ≥2 examples (saturating); 10+ classes have
single example or zero.

***REMOVED******REMOVED******REMOVED*** 1.2 Well-established literature classes NOT in KB (empty-class gaps)

| Universality class | Literature anchor | Status in KB | Why this matters |
|---|---|---|---|
| **KPZ surface growth (1+1 d)** | Kardar-Parisi-Zhang 1986; Takeuchi-Sano 2010 LC turbulence | ZERO entries | Most well-validated non-equilibrium class outside of SOC; experimental data is plentiful |
| **Directed Percolation (DP)** | Hinrichsen 2000 review; Take Eda-Hatano 2007 LC | ZERO | Conjecture: any absorbing-state phase transition with single absorbing state + short-range falls in DP. Massive empirical class |
| **2D Ising / RFIM** | Onsager 1944; Sethna RFIM hysteresis 1993 | ZERO | Magnetization, Barkhausen noise, RFIM crackling noise — direct hysteresis kin |
| **Manna / Oslo conserved sandpile** | Manna 1991; Pruessner Oslo rice pile | ZERO | The "conserved" SOC class — distinct exponents from BTW; experimentally validated on real rice piles, snow avalanches |
| **OFC (Olami-Feder-Christensen)** | OFC 1992 | mentioned but no empirical entry beyond earthquakes | The non-conserved SOC sub-class; key for synthetic generator validation |
| **Absorbing-state phase transition (general)** | Henkel-Hinrichsen-Lubeck 2008 book | ZERO | Parent class of DP / Manna / branching; bridges epidemiology and ecology |
| **First-passage / extreme-value (Fisher-Tippett-Gnedenko)** | Embrechts Klüppelberg Mikosch 1997 | partial (S&P 500) | Generic for tail-risk: insurance, geophysical extremes, climate |
| **Burgers / Tracy-Widom** | Tracy-Widom 1994; Corwin 2012 KPZ review | ZERO | Universality class for largest eigenvalue / largest fluctuation; bridges RMT and growth |
| **Random matrix theory (GOE/GUE)** | Mehta 1991 | ZERO | Nuclear physics, finance correlation matrices, neural connectivity |
| **Self-Organized Bistability (SOB)** | Di Santo-Burioni-Vezzani-Munoz 2016 | ZERO | The "first-order" SOC with hysteresis — bridges Preisach hysteresis and SOC |

**Per-class new system recommendations** (2-3 each):

| Class | Candidate systems | Data |
|---|---|---|
| **KPZ** | (a) Liquid-crystal turbulent front (Takeuchi-Sano 2010, Sci Rep 2011); (b) Combustion paper-burn fronts (Maunuksela 1997); (c) Bacterial colony edge growth | (a) supplementary CSV from Takeuchi 2011; (b) Maunuksela supplementary; (c) Bonachela 2011 |
| **DP** | (a) Catalytic surface reactions (Ziff-Gulari-Barshad 1986 sim + LeRoy 2011 exp); (b) Forest-fire transitions (Drossel-Schwabl 1992) | (a) Open Surface Science DB; (b) Drossel sim — `landlab` library |
| **Ising / RFIM** | (a) Barkhausen noise in ferromagnets (Spasojević 1996); (b) Crackling noise in compressed crystals (Dimiduk-Greer 2006); (c) Magnetic switching in disk drives | (a) Sethna group public data; (b) Materials Cloud; (c) UCI ML repo |
| **Manna/Oslo** | (a) Real rice-pile experiment (Frette-Christensen-Malthe-Sørensen 1996); (b) Snow avalanche size distribution (Birkeland-Landry 2002) | (a) Oslo group archive; (b) Avalanche.org US-AAIC database (n≈40K) |
| **SOB** | (a) Vegetation transitions in semi-arid ecosystems (Kéfi 2007); (b) Magnetization with disorder (Sethna RFIM hysteresis) | Both have published datasets |
| **Tracy-Widom** | (a) S&P 500 correlation-matrix eigenvalue extremes (Laloux Cizeau Bouchaud Potters 1999); (b) Polynuclear growth (PNG, Prähofer-Spohn 2000) | (a) WRDS academic license; (b) numerical sim |

---

***REMOVED******REMOVED*** 2. Cross-Disciplinary Bridging — 8 Disciplines × 2 Candidates

| ***REMOVED*** | Discipline | Candidate phenomenon | Expected class | Data source | n | Cost |
|---|---|---|---|---|---|---|
| L1a | **Linguistics** | Zipf's law on word frequencies (English+Chinese) | `preferential_attachment` (Simon-Yule) | Google Books Ngrams JSON v2 (https://storage.googleapis.com/books/ngrams/books/datasetsv2.html) | 10M tokens easy | 1 day |
| L1b | **Linguistics** | Hapax legomena / vocabulary growth (Heaps law) | `preferential_attachment` (sublinear variant) | NLTK Project Gutenberg corpus, 25K books | 4M words | 1 day |
| L2a | **Urban science** | City population rank-size (Zipf-Gibrat) | `preferential_attachment` (Gabaix-Ioannides 2004) | UN World Urbanization Prospects 2024, US Census, Eurostat | 30K cities | 2 days |
| L2b | **Urban science** | Crime hotspot scaling (Bettencourt 2010 superlinear) | new class candidate `urban_scaling` (superlinear β≈1.15) | Bettencourt 2010 SI / FBI UCR open API | 1K MSAs × 30 yr | 2 days |
| L3a | **Climate** | Drought duration distribution (Palmer Drought Severity Index extremes) | `extreme_value_tail_class` | NOAA NCEI Climate Indices archive | 120 yr × 344 climate divisions | 2 days |
| L3b | **Climate** | Atlantic hurricane intensity (Saffir-Simpson categories) | `soc_threshold_cascade` candidate (Corral 2006) | NOAA HURDAT2 | n≈2000 events 1851-2024 | 1 day |
| L4a | **Ecology / Biology** | Species body-mass / abundance distribution (Brown-Maurer power law) | `extreme_value_tail_class` | GBIF + Pantheria mammal traits DB | 6K mammals | 2 days |
| L4b | **Ecology / Evolution** | Species extinction event sizes (Sepkoski / Newman 1996) | `soc_threshold_cascade` (Newman power-law) | Sepkoski 2002 Compendium (public via PaleoDB) | 36K marine genera | 1 day |
| L5a | **Sociology / Comms** | Twitter / X cascade size (retweet trees) | `motter_lai_network_cascade` or `preferential_attachment` | Goel-Anderson-Hofman-Watts 2016 dataset; SNAP Stanford twitter dump | n≈1.4B tweets | 3 days |
| L5b | **Sociology** | Income/wealth distribution (Pareto tail) | `extreme_value_tail_class` (α≈2-3) | World Inequality Database (WID.world) + US IRS SOI | 100 yr × 175 countries | 2 days |
| L6a | **Psychology** | Reaction-time distributions (Logan-Cowan 1984 ex-Gaussian tail) | `extreme_value_tail_class` (heavy tail) + scaling | Stroop Open Data, OSF datasets aggregating 30+ RT studies | 200K trials | 2 days |
| L6b | **Psychology** | Wikipedia editing burst inter-arrival times (Barabási 2005) | `soc_threshold_cascade` (queuing-based) | Wikipedia edit-history dumps (public); replicate Barabási 2005 figure 2 | 100M edits | 2 days |
| L7a | **Epidemiology** | COVID-19 daily case counts (Omori-decay during waves) | `soc_threshold_cascade` (Omori-like) | JHU CSSE Github archive (https://github.com/CSSEGISandData/COVID-19) | 1.5M rows, 200+ countries | 1 day |
| L7b | **Epidemiology** | Measles outbreak sizes pre-vaccine (Rhodes-Anderson 1996) | `sir_contagion_network_class` | Tycho v2.0 (https://www.tycho.pitt.edu/) | 100yr US notifiable | 2 days |
| L8a | **Innovation / Education** | Patent citation network (preferential attachment + first-mover) | `preferential_attachment` | NBER Patent Citation Data + USPTO open API | 8M patents, 100M citations | 3 days |
| L8b | **Education** | Educational achievement test-score distribution by school size scaling | superlinear/sublinear scaling | PISA 2022 microdata (https://www.oecd.org/pisa/data/) | 690K students, 80 countries | 3 days |

---

***REMOVED******REMOVED*** 3. Modern / Hot Candidates (5)

| ***REMOVED*** | Candidate | Expected class | Data source | Why this is hot |
|---|---|---|---|---|
| M1 | **LLM scaling-law loss curves** (Chinchilla, BLOOM, Pythia) | new candidate `power_law_learning_curve` (Hestness 2017 / Kaplan 2020) | HuggingFace Open LLM Leaderboard logs + Pythia training checkpoints (Biderman 2023, public); BIG-bench task-loss CSVs | First serious cross-domain SOC test on neural-network training dynamics. Would directly engage Wei 2022 "emergent abilities" debate |
| M2 | **LLM emergence (task accuracy vs scale)** | new candidate `phase_transition_emergence` | Schaeffer-Miranda-Koyejo 2023 "Mirage" dataset; Wei et al. 2022 SI | Most-cited 2023 ML paper category; would test whether "emergence" is a real phase transition or measurement artifact |
| M3 | **Bitcoin hash-rate / mempool dynamics** | `soc_threshold_cascade` + Omori | Blockchain.com API; mempool.space; Glassnode public datasets | Direct extension of Phase 3 DeFi to L1 dynamics. Hash difficulty Omori-decay never tested |
| M4 | **TikTok / Douyin / YouTube video virality** | `preferential_attachment` (Crane-Sornette 2008 endo/exo) | Kaggle YouTube Trending dataset (n=400K, daily, 6 countries) + DDPS TikTok Public API | 2024-relevant; user-search high; tests endo/exo dichotomy |
| M5 | **Climate tipping points** (Amazon, AMOC, WAIS, Arctic sea ice) | `scheffer_fold_bifurcation` + EWS Kendall-τ | NOAA AMOC reanalysis; NASA MODIS Amazon NDVI; NSIDC Arctic sea ice extent; Lenton 2023 Earth System Dynamics SI | Lenton-Scheffer 2023 keystone paper; direct extension of Phase A2-Scheffer to systems with real human-stakes signal |

**Bonus M6** (deferred to Wave 3): **AI-generated content detection** — power-law of false-positive rates as a function of model scale (Tian 2023). Public datasets in HuggingFace `ai-text-detection`.

---

***REMOVED******REMOVED*** 4. Priority Matrix — Scoring & Top 10

**Scoring (each dimension 0-5):**
- A. Academic impact (citation / venue ceiling)
- D. Data availability (5 = one-click public; 1 = FOIA / paywall)
- N. Novelty distance from existing 13 (5 = entirely new class; 1 = near-duplicate)
- U. User search likelihood (5 = top-10 query on phase.bytedance.city / structural.bytedance.city)

**Weighted total** = A×0.3 + D×0.3 + N×0.2 + U×0.2 → 5.0 max.

| Rank | Candidate | A | D | N | U | Score | Data URL | Effort |
|---|---|---|---|---|---|---|---|---|
| **1** | M5 Climate tipping points (Amazon NDVI + AMOC) | 5 | 4 | 4 | 5 | **4.5** | NSIDC + NOAA + Lenton 2023 SI | 5 days |
| **2** | L7a COVID-19 Omori decay | 4 | 5 | 4 | 5 | **4.5** | github.com/CSSEGISandData/COVID-19 | 2 days |
| **3** | M1 LLM scaling-law loss curves | 5 | 5 | 5 | 3 | **4.5** | HuggingFace Pythia logs + BIG-bench | 4 days |
| **4** | L1a Zipf's law (English/Chinese words) | 4 | 5 | 3 | 4 | **4.2** | Google Books Ngrams v2 | 2 days |
| **5** | L2a City population rank-size (Zipf-Gibrat) | 4 | 5 | 3 | 4 | **4.2** | UN WUP 2024 + US Census | 2 days |
| **6** | L4b Sepkoski extinction event sizes | 4 | 5 | 4 | 3 | **4.1** | paleobiodb.org public API | 2 days |
| **7** | M3 Bitcoin hash-rate / mempool | 3 | 5 | 4 | 5 | **4.1** | blockchain.com API + mempool.space | 3 days |
| **8** | KPZ — Takeuchi-Sano LC turbulence (KPZ-1) | 5 | 3 | 5 | 2 | **4.0** | Takeuchi 2011 Sci Rep supplementary | 4 days |
| **9** | M4 YouTube / TikTok virality (preferential attachment) | 3 | 5 | 3 | 5 | **4.0** | Kaggle YouTube Trending + TikTok DDPS API | 3 days |
| **10** | L5b Wealth distribution Pareto tail (WID) | 4 | 5 | 3 | 3 | **4.0** | wid.world public CSV | 2 days |

**Honorable mentions** (score 3.8-3.9): L8a patent citations, RFIM Barkhausen noise (Sethna data), Manna/Oslo rice pile (Frette 1996), Tycho v2.0 measles, M2 LLM emergence.

---

***REMOVED******REMOVED*** 5. Disciplinary Coverage Matrix (After Top 10 Added)

| Discipline | Before | After Top 10 | Class breadth gained |
|---|---|---|---|
| Geophysics | 1 (earthquakes) | 1 | — |
| Equity/DeFi finance | 4 | 5 (+Bitcoin hash) | adds crypto-L1 |
| Neuroscience | 1 | 1 | — |
| Networks (banks/grid) | 2 | 2 | — |
| Social/web (Wiki/GitHub) | 2 | 4 (+YouTube/TikTok, Twitter optional) | adds video virality |
| Ecology (Scheffer) | 1 | 3 (+Sepkoski, climate tipping NDVI) | adds extinction + ESS bifurc |
| Linguistics | 0 | 1 (Zipf) | new |
| Urban | 0 | 1 (city sizes) | new |
| Climate | 0 | 1 (tipping points) | new |
| Epidemiology | 0 | 1 (COVID Omori) | new |
| ML / AI | 0 | 1 (LLM scaling) | new |
| Physics-condensed | 0 | 1 (KPZ) | new |
| Public economics | 0 | 1 (wealth Pareto) | new |

Net: from 7 disciplines to 13 disciplines, from 3 saturated classes to 6 saturated classes, KPZ empty-class gap closed.

---

***REMOVED******REMOVED*** 6. 6-Month Milestone — 3 Waves × 3 Systems

***REMOVED******REMOVED******REMOVED*** Wave 1 (months 1-2): **High data-availability, low compute, fast wins**

| System | Class | Coupling to soc-pipeline | Reused module |
|---|---|---|---|
| **L7a COVID-19 Omori-decay** | `soc_threshold_cascade` | direct — use Phase 1 Omori stack | `omori.py` |
| **L1a Zipf's law words** | `preferential_attachment` | extends Phase A1 Wikipedia/GitHub | `fit.py` (Clauset PL) |
| **L2a City population rank-size** | `preferential_attachment` | sibling of Zipf — shares fit code | `fit.py` + Vuong lognormal |

**Strategy**: All 3 use existing `packages/soc-pipeline/` unchanged. Only new code = per-system loader (≈80 LoC each). Total estimated effort: 1 person-week. Deliverables: 3 new `v4/validation/<system>/paper.md` + JSONL data + verdict cards. Push to dataset v1.1 release at end of Wave 1.

***REMOVED******REMOVED******REMOVED*** Wave 2 (months 3-4): **High-impact / novelty, moderate effort**

| System | Class | Coupling | New module |
|---|---|---|---|
| **M5 Climate tipping points (Amazon NDVI)** | `scheffer_fold_bifurcation` | reuse A2-Scheffer block-bootstrap pipeline (Phase A2-Scheffer fix) | uses `bootstrap.py` block-CI |
| **L4b Sepkoski extinction events** | `soc_threshold_cascade` (Newman 1996) | direct extension of Phase 1 | `fit.py` |
| **M1 LLM scaling-law loss curves** | new class candidate `power_law_learning_curve` | requires new fitter — fit `L(N) = a*N^(-b) + L_∞` (Kaplan 2020 form) | **NEW** module `learning_curve.py`, ≈150 LoC |

**Strategy**: M1 introduces a *new physics submodel* (irreducible loss floor + power law), which is a deliberate KPI for Wave 2 — proves the pipeline is extensible beyond Clauset PL. Co-write with the Track A *Scientific Data* companion paper (which already wants v1.1 systems folded in per W7-A roadmap month 9-12).

***REMOVED******REMOVED******REMOVED*** Wave 3 (months 5-6): **Hardest, biggest novelty, paper-worthy**

| System | Class | Coupling | Risk / mitigation |
|---|---|---|---|
| **KPZ — Takeuchi-Sano liquid-crystal data** | KPZ universality class (new) | needs **new collapse module** (Tracy-Widom scaling + 2-point correlation fit) | high — first KPZ entry; mitigation = run as inconclusive-allowed pre-registration |
| **M4 YouTube / TikTok virality** | `preferential_attachment` + endo/exo (Crane-Sornette 2008) | reuse `fit.py` + Hawkes branching from `soc-hawkes-omori` validation | medium — data noisy; mitigation = bootstrap CI |
| **M3 Bitcoin hash-rate / mempool** | `soc_threshold_cascade` candidate | reuse Phase 3 DeFi loaders pattern | low — well-documented API |

**Strategy**: Each Wave-3 system has paper-publication ambition — KPZ entry alone is *J. Stat. Mech.* worthy; YouTube virality fits *Patterns* methodology paper; Bitcoin mempool fits *Phys. Rev. E*. The wave doubles as Tracks B/C/D content for the W7-A roadmap month 9-15 window.

---

***REMOVED******REMOVED*** 7. Coupling Strategy — Reuse soc-pipeline

**Per W7-A roadmap Track A goals**, every new system MUST:

1. Inherit from `packages/soc-pipeline/` (`fit.py`, `omori.py`, `lr_test.py`, `bootstrap.py`).
2. Add a `v4/validation/<system>/fetch_and_analyze.py` ≤200 LoC, mirroring `soc-defi/analyze_multiprotocol.py`.
3. Emit identical JSONL schema: `{system_id, n_tail, alpha, alpha_se, xmin, R_lognormal, p_lognormal, R_exponential, p_exponential, omori_p, omori_c, omori_R2, verdict}`.
4. Be added to `dataset/v1/manifest.json` with SHA-256 + source URL + license.
5. Run through B3 taxonomy critic (or B4 if region resolved per Track F roadmap) before being claimed in any paper.

**Module additions allowed (gated by clear necessity)**:
- `learning_curve.py` (M1 LLM scaling) — only if Wave 2 commits to it
- `kpz_collapse.py` (Wave 3 KPZ) — adds Tracy-Widom + 2-pt correlation
- `superlinear_scaling.py` (Bettencourt urban scaling) — if L2b included later
- `epidemic_branching.py` (already covered by sir-contagion code, can be reused for Tycho measles)

**Veto rule**: any new system that requires modifying the *core* `fit.py` is rejected; that would invalidate the "single fixed pipeline" claim that powers C1's headline.

---

***REMOVED******REMOVED*** 8. Notes & Caveats

- **Data freshness pitfalls**: Kaggle YouTube Trending stops 2020; TikTok DDPS API is academic-only and slow. Plan double-source.
- **Sociology / Twitter cascade caveat**: post-X API closure, getting cascades >2023 is hard; use SNAP archived 2010-2020 cascades, accept the staleness.
- **Avoid these traps**: (i) Don't add another stock index (Russell 2000, FTSE) — diminishing returns vs S&P, hits W7-A ¬1 anti-recommendation. (ii) Don't add another DeFi protocol — Phase 3 is already saturating at 3 protocols. (iii) Don't pile on more solar / wildfire — Phase 6/7 already cover.
- **Pre-registration alignment**: Wave 1's L7a COVID-19 + Wave 3's KPZ should each be pre-registered before fetching data, per Track C of W7-A roadmap (months 2-8 window). Wave-1 L1a Zipf is so canonical it's almost a sanity-check, not a real prediction.

---

***REMOVED******REMOVED*** 9. Recommended Decision Gates

| Gate | When | Pass criterion |
|---|---|---|
| G1 — Wave 1 sign-off | end month 2 | 3 systems analyzed, JSONL + paper.md committed, ≥2 pass B3 taxonomy critic |
| G2 — Wave 2 sign-off | end month 4 | 3 more systems + LLM learning-curve module + Scheffer block-bootstrap reuse demonstrated on Amazon NDVI |
| G3 — Wave 3 sign-off | end month 6 | 3 more systems + KPZ entry passes Tracy-Widom collapse + dataset v1.2 Zenodo deposit |
| G4 — Decision: Wave 4 plan | month 6 | Review external citations / replications of v1.0; if ≥2 external uses, plan Wave 4; if not, pivot to outreach (Track E) |

---

**End of expansion candidates report.**
