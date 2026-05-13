# W7-A · structural-isomorphism 18-month Academic Value Roadmap

> **Author.** W7-A subagent (research strategy persona — SOC physics / complex systems / cross-disciplinary statistical inference, PRE + Nature Phys referee experience).
> **Date.** 2026-05-13.
> **Inputs.** `docs/sessions/HANDOFF.md` (session #2 state), `paper/v0-unified-pipeline-2026-05-13.md` v0.3 (§8 pre-registration + §9 submission path), `docs/reviews/W5-A-scholar-review-2026-05-13.md` (scholar review with 9 statistical concerns + 12-month patch roadmap), `v4/results/B3_taxonomy_v2.jsonl` (KEEP=5/REJECT=7/SPLIT=5/MERGE=4 ensemble verdict).
> **Question this document answers.** What is the most leverage-producing 18-month academic agenda for this project, distinct from "PR fluff" and distinct from "patch the existing draft until PRE accepts it"?

---

## 0. TL;DR

The most leverage-producing 18-month path is **not** to maximize papers published. It is to shift the project from "interesting single-author cross-domain SOC catalogue" to **one of three substantive contributions to how the field works**:

- **L1 — Reference dataset / open benchmark.** Thirteen independently fetched datasets + frozen 339-line pipeline + four synthetic nulls + B3 taxonomy verdicts, packaged with Zenodo DOI and replication scripts, becomes the canonical "Clauset 2009 + null controls + multi-model critic" cross-domain test bed. **This is the highest-leverage path and the one most underweighted in the current submission plan.**
- **L2 — Reject-aware methodology paper (C4).** The 7/21 ↔ 14% vs 33% B1-vs-B3 rejection-rate result, generalized to a *reject-aware pipeline* template, is a contribution to LLM-in-the-loop research methodology that exists nowhere else in the literature. C4 may already be the strongest paper in the bundle (W5-A scholar review §5.3 concurs).
- **L3 — Pre-registered adversarial replication (§8 of v0.3).** Doing the five-system pre-registration *for real*, then publishing the prediction success rate, is the single most credibility-buying action available — and is independent of whether the universality-class membership headline ever wins.

The current submission plan (§9 of v0.3) targets PRE + Chaos + EPL for C1 — these are fine but **deliverable-bounded**. The reference-dataset / benchmark / reject-aware-methodology axis is *path-bounded* and compounds far harder over 18 months because every external reuse of the dataset is a citation and every external rejection-rate replication is a methodology citation.

**Top single recommended action (next 30 days):** *Freeze v0.3 + ship Zenodo dataset DOI*. This is the action whose 18-month citation pull dominates all others by 5× to 10× even if every paper venue choice goes sideways. Detailed mini-brief at §7.

---

## 1. What counts as "real academic value" (not PR fluff)

Five concrete contribution types, ranked by how a senior physicist / referee would actually value them:

| Tier | Contribution type | Lifecycle | Examples | Citation pull |
|---|---|---|---|---|
| **T1** | Paradigm-shifting framework / question | 5-20 years | Bak 1996 SOC; Wilson 1975 RG; Clauset-Shalizi-Newman 2009 power-law statistics | 10³-10⁴ |
| **T2** | Widely reused method | 3-10 years | `powerlaw` Python (Alstott 2014); Kendall-τ EWS (Scheffer 2009); LIGO data-quality pipeline | 10²-10³ |
| **T3** | Reference dataset / benchmark | 5-15 years | ImageNet; SkyServer; LIGO OSC; SCEC Community Stress Drop Validation | 10³-10⁴ |
| **T4** | Question reframing | 2-5 years | Broido & Clauset 2019 "Scale-free networks are rare"; Stumpf & Porter 2012 "Critical truths about power laws" | 10²-10³ |
| **T5** | Single empirical confirmation | 1-3 years | "X system shows SOC", "Y system has PA exponent ≈ 2" | 10¹-10² |

**The current C1 v0.3 manuscript is positioned as T5** (13 systems × Clauset pipeline → universality-class consistency). Even at best-case PRE acceptance, T5-tier citation pull caps around 100. The post-hoc scholar-driven downgrade in v0.3 ("consistent with shared functional form" instead of "first proof of universality-class membership") also tightens the manuscript's T5 envelope.

**The latent T2/T3/T4 contributions in the same project are systematically underclaimed:**

1. **T2 (method).** The reject-aware pipeline (C4) is a reusable LLM-critic methodology — *Patterns* / NeurIPS-D&B / *J. Open Source Softw.* venue. Citation pull caps around 500 over 5 years if the field adopts it.
2. **T3 (dataset).** Thirteen independently fetched + frozen-pipeline + null-controlled + B3-curated datasets is *exactly* the kind of reference set that gets cited every time someone wants to test a new universality claim. Citation pull could exceed C1 itself within 3 years if packaged correctly.
3. **T4 (question reframing).** The Phase 5 four-null + B3 rejection-rate combination *operationalizes* Broido & Clauset 2019's "scale-free networks are rare" methodology onto SOC claims. Every SOC paper that wants to dodge the "marginal evidence" critique would need to engage. The current v0.3 doesn't claim this loudly enough — §6.5 limitations buries it.

**Strategic insight.** A senior physicist's most-cited paper is rarely their most-publicized one — it's the one that turned into a reusable tool, dataset, or methodological standard. The structural-isomorphism project has *three* such latent contributions and is currently optimizing the C1 single-empirical-confirmation axis. **The 18-month agenda below explicitly rebalances toward T2/T3/T4.**

---

## 2. Honest weakness assessment (after scholar review)

W5-A scholar review (2026-05-13) listed 9 statistical / methodological issues. Triaged into *fixable* vs *fundamental*:

### 2.1 Fixable (1-4 weeks, no path constraint)

| # | Issue | Fix | Cost |
|---|---|---|---|
| F1 | bootstrap n=100 → should be 10,000 | rerun overnight | 1 CPU-night |
| F2 | Scheffer p=10⁻¹⁸⁶ (serial-correlation artifact) | block-bootstrap (already done in v0.3) | done ✓ |
| F3 | FWER not controlled across 30+ tests | Bonferroni / B-H paragraph | 1 hour |
| F4 | xmin sensitivity not stress-tested for small-n phases | sliding-window xmin scan supplementary figures | 1 day |
| F5 | r_shape=1.11 lacks null distribution | 10k surrogate-null permutation test on row-centered ratio | 1-2 days |

### 2.2 Fundamental (requires structural change to project)

| # | Issue | Why fundamental | Implication |
|---|---|---|---|
| Φ1 | 11/11 in-band coverage is suspiciously high | "post-hoc curve-fitting concern" — only pre-registration on *fresh* systems can absolve | §8 pre-registration must actually be run, not just listed |
| Φ2 | B3 single-vendor "ensemble" is not real architectural ensemble | DeepSeek × 3 temperature variants ≠ Claude+GPT+DeepSeek+Kimi+GLM cross-family | B4 cross-family ensemble is a separate paper, not a v0.4 fix |
| Φ3 | Phase 7 (power grid n=123) is literature-curated against itself | OE-417 FOIA / DOE collaboration is the only credible replacement | 6-12 month timeline; not in v1 of paper |
| Φ4 | "First quantitative confirmation of universality-class membership" is overreach | already downgraded in v0.3 (good) | maximum claim ceiling is "consistent with shared functional form" |
| Φ5 | Cross-pipeline-implementation confound (only `powerlaw` package used) | Voitalov 2019 `plfit` or independent re-implementation needed | 1-3 month independent re-runner project |

**Decision.** Path forward = *fix all 5 F-items by month 2*, *publicly own the Φ-items as scope limitations*, *invest in T2/T3/T4 deliverables that don't depend on raising the C1 ceiling*. Trying to "fix Φ1-Φ5 inside C1" is fighting the wrong battle — they're fundamental to single-author cross-domain SOC at this resource level, and the published literature accepts honest scope limitations far more readily than the project has assumed.

---

## 3. 18-month academic agenda — six tracks, ranked by leverage

### Track A — Open dataset + benchmark (T3, HIGHEST LEVERAGE) ★

**Deliverable.** A Zenodo-deposited DOI-stamped dataset bundle: `structural-isomorphism-v1.0-benchmark.zip`. Contents:
- 13 independently fetched datasets (raw + cleaned)
- 4 synthetic nulls (raw + generator code)
- `v4/lib/soc_pipeline.py` at frozen commit hash, with `requirements.txt` pinning every dep
- `v4/results/*.jsonl` (B1 / B3 / B3-taxonomy-v2 / layer3_critic / layer4 verdicts)
- `v4/taxonomy/classes/*.yaml` × 24 candidate classes
- `tutorials/01_reproduce_earthquake_soc.ipynb` + extension to all 13 phases
- README with provenance, license (CC-BY-4.0 for data + MIT for code), and citation request
- Companion paper: **"A cross-domain SOC + critical-systems benchmark with synthetic nulls and multi-model class curation"** (~5k words) → *Scientific Data* (Nature) or *Earth System Science Data* style.

**Why highest leverage.**
- Citation pull: every paper that wants to test a new universality claim against a reusable benchmark cites the dataset. ImageNet-style compounding. Realistic 5-year citation: 200-1000.
- Cross-disciplinary: a hydrologist using the Scheffer fold benchmark + an economist using the FDIC bank-failure benchmark + a neuroscientist using the DANDI cortex avalanche benchmark all need the same dataset — *one* deposit produces citations across 4-6 fields.
- Removes the "single-vendor / single-author" critique automatically — the dataset becomes community infrastructure regardless of whether C1 is accepted at PRE.
- *Scientific Data* (Nature) acceptance rate ~50% with strong data provenance. Vastly higher than Nature Phys at 7%.

**18-month deliverables.**
- Month 1-2: Zenodo deposit v1.0 (no embargo).
- Month 3-4: companion paper draft → *Scientific Data*.
- Month 6-9: first external citation / first external replication attempt (track via Google Scholar alerts + Zenodo download counter).
- Month 9-12: v1.1 release with §8 pre-registered new systems folded in.
- Month 12-18: integration with `awesome-soc-datasets` / OpenML / `papers-with-code` ecosystem index.

**Cost.** Mostly already-done work. ~2 weeks packaging + 2 weeks paper drafting. No new compute, no new fieldwork. **This is the dominant near-term opportunity.**

### Track B — Reject-aware methodology paper (T2, near-finished) ★

**Deliverable.** C4 paper (`paper/c4-reject-aware-pipeline-2026-05-13.md`, 8164 words, exists at v0.1) → *Patterns* (Cell Press) or *NeurIPS-D&B* or *J. Stat. Software*.

W5-A scholar review §5.3 explicitly flagged this as "probably the best paper in the bundle." Three reasons reinforced:
1. The B3 ensemble pass result (7/21 ↔ 33% rejection rate vs single Opus 14%) is a *quantitative* claim with a comparable baseline — exactly what ML methodology venues value.
2. The "mathematical framework masquerading as universality class" filter (delay-differential, copula, scale-free percolation, Preisach monolith) is genuinely novel.
3. Cost / latency framing ($<1 per panel, 41 min wall clock) is operationally relevant.

**Critical revisions before submission (1-2 weeks):**
- Acknowledge or fix the model-architecture-confound (B1 = single Opus, B3 = 3× DeepSeek) → either (i) add Opus-single vs Opus-3×, OR (ii) explicitly frame as "within-vendor multi-decoding" instead of "multi-model ensemble".
- Compress 5-layer pipeline → 3-layer (extract / curate / critic+predict) for legibility.
- Cut "0 API errors" from headline; immaterial to method.

**18-month deliverables.**
- Month 1-2: C4 v0.2 revisions per scholar review + submit to *Patterns*.
- Month 3-6: editorial review cycle (Patterns typical ~3-month first decision).
- Month 6-9: revision round → likely acceptance.
- Month 9-18: track adoption — does any other LLM-in-loop research methodology paper cite the reject-aware pattern?

**Cost.** 2 weeks revision + 0 compute. No fieldwork.

### Track C — Pre-registered adversarial replication (T4, credibility-buying)

**Deliverable.** Run the five §8 pre-registered systems (P1 Bitcoin Cash; P2 Reddit cascade; P3 FluNet influenza; P4 Flickr photo bursts; P5 ant-colony foraging). Publish results regardless of outcome.

**Decision rules (already committed in v0.3 §8.3):**
- 5/5 inside → strengthen claim
- 4/5 inside → "robust with one recalibration"
- 3/5 inside → "marginal"
- ≤2/5 inside → "calibration framework needs substantial revision"

**Why high-leverage.**
- Absolves Φ1 (11/11 in-band suspicion). Resolves *the* central reviewer concern of W5-A scholar §3.10.
- Short paper material: "Adversarial pre-registered replication of cross-domain universality (5 systems pre-registered, X/5 confirmed)" → arXiv + *PRE* or *Phys. Rev. Research* short report.
- Even at 3/5 the paper is publishable as "honest pre-registration with mixed outcome" — Patterns / open-science venues *value* honest negative replications.

**Realistic outcome estimate.** P1, P2, P4 are likely in-band (well-studied PA / SOC sub-cases); P3 and P5 are adversarial choices and could go either way. Expected: 3/5 to 4/5 confirmed. **3/5 is the most credibility-buying outcome** because it's an honest mixed result, not a suspiciously-clean 5/5.

**18-month deliverables.**
- Month 2-4: data acquisition + fits for P1, P2, P4.
- Month 4-6: data acquisition for P3 (FluNet WHO + finite-size correction modeling) + P5 (Bonabeau 1996 dataset family + alternatives).
- Month 6-8: write-up + arXiv.
- Month 8-12: submit short paper to *Phys. Rev. Research* / *J. Phys. Complex.* / *Patterns*.

**Cost.** ~$30 in LLM if any taxonomy reruns. Mostly compute + literature search. 2-3 weeks effective work.

### Track D — Method paper series (T2, complement to C4)

**Three method papers, each independent:**

1. **D1 — Block-bootstrap for tipping-point indicators.** The Scheffer Kendall-τ on autocorrelated time series p=10⁻¹⁸⁶ → block-bootstrap fix in v0.3 is *itself* a reusable methodology contribution. Ecology + EWS community (Dakos, Scheffer, van Nes) does not consistently apply block-bootstrap to rolling EWS. **Short paper material:** "Block-bootstrap correction for Kendall-τ early-warning signals on autocorrelated environmental time series" → *Methods in Ecology and Evolution* or *J. Theor. Biol.* — venue Dakos / Scheffer themselves publish in.
2. **D2 — Reject-aware critic for taxonomy panels.** Extracted from C4 §4 (mechanism-vs-limit-theorem filter). Method-of-the-paper for *J. Phys. Complex.* or *J. Stat. Mech.* methodology issue.
3. **D3 — Universal collapse with row-centered null distribution.** The W5-A §4.4 critique that "r<2 is borrowed from within-system finite-size scaling" → response is to compute the surrogate-null distribution (Track A's F5 fix), and publish *the null distribution computation itself* as a reusable method. Short methodology paper for *EPL* / *Comput. Phys. Commun.*

**Why these are separate from C1.** C1's headline is empirical (13 systems × 5 classes). The three D-papers are each a *generalizable algorithm* that applies far beyond the specific 13 systems. Citation pull adds without subtracting.

**18-month deliverables.**
- Month 6-9: D1 drafted + submitted.
- Month 9-12: D2 drafted (depends on Track B C4 acceptance trajectory).
- Month 12-15: D3 drafted (depends on Track A's null-distribution computation).

**Cost.** ~$0 compute. 2-3 weeks/each.

### Track E — Senior co-author / collaboration ecosystem (legitimacy)

**Goal.** Convert single-author preprints to joint-authored papers with senior physicists who add credibility AND who already have referee networks at PRE / Chaos / Patterns.

**Outreach candidates (ranked by fit):**

| Rank | Researcher | Affiliation | Why this fit |
|---|---|---|---|
| **1** | **Dietmar Plenz** (NIMH, Bethesda) | NIH | Phase 4 (mouse cortex) directly draws on Plenz-Beggs 2003 — collaboration on neural avalanches gives credibility for both empirical and methodology framings. Plenz publishes in PRL, PNAS, Nat. Neurosci. — high citation networks. |
| **2** | **Viola Priesemann** (MPI Göttingen) | MPI DS | Phase 4 sub-critical interpretation cites Priesemann-Munk-Wibral 2014. Phase reframing as sub-critical reverberation rather than class-membership failure aligns with her published view. |
| **3** | **Marten Scheffer** (Wageningen) | WUR | Phase A2-Scheffer block-bootstrap correction is *directly* his framework. A2 phase paper co-authored with Scheffer = high acceptance prob at *Nature*-tier ecology venues. |
| **4** | **Aaron Clauset** (CU Boulder) | CU Boulder | Pipeline is built on Clauset 2009. Broido & Clauset 2019 is the exact rejection-aware methodology spirit. Co-author on the dataset paper (Track A) would essentially canonize the benchmark. |
| **5** | **Didier Sornette** (ETH Zürich → SUSTech) | SUSTech | Finance / cascade / dragon-king cross-domain credibility. Phase 2 (S&P) + Phase 7 (power grid) directly cite his work. |
| **6** | **Vasiliki Plerou / H. Eugene Stanley network** (BU) | BU | Phase 2 inverse-cubic confirmation is Plerou-Gopikrishnan-Stanley territory. |
| **7** | **Ben Carreras** (BACV Solutions / Oak Ridge alum) | freelance | Phase 7 power grid: Carreras 2016 catalog is the literature anchor. FOIA / OE-417 access via Carreras' DOE connections. |
| **8** | **Vito Latora / Petter Holme** (network science) | QMUL / Tokyo Tech | Network universality + taxonomy critique cross-checks. |

**Outreach mechanics:**
- Cold email to senior with C1 preprint + "would you have 30 min to discuss limitations and possible co-authorship" — accept rate ~10-20% if preprint quality is high (W5-A scholar gave C1 a 7.5/10).
- Conference / workshop introduction first if possible (NetSci, Conference on Complex Systems, APS March Meeting).
- ResearchGate / Twitter / Mastodon visibility: post arXiv + Zenodo links + short threadable summary. Plenz / Priesemann / Sornette / Scheffer all have social-media presence.
- Open-science / Mastodon scientist networks (e.g. fediscience.org) for community visibility.

**18-month deliverables.**
- Month 2-3: arXiv preprint (C1 v0.4 post-revisions, conditional on Tracks A + F1-F5 closure).
- Month 3-6: outreach to top-3 candidates (Plenz, Priesemann, Scheffer).
- Month 6-12: 1-2 co-authored revision rounds; ideally Plenz on a v2 neural avalanche solo paper; Scheffer on the A2-Scheffer + D1 block-bootstrap paper.
- Month 12-18: APS March Meeting 2027 talk or NetSci 2027 oral; Conference on Complex Systems 2027 submission.

**Cost.** Time, not money. ~1-2 day/week if pursued aggressively.

### Track F — Heterogeneous LLM ensemble B4 (T2 methodology, deferred)

**Deliverable.** Replace B3 (3× DeepSeek) with B4 (Claude Opus + GPT-5 + DeepSeek-pro + Kimi K2.5 + GLM-5) — a real architectural cross-family ensemble.

**Why deferred vs fast.**
- OpenRouter CN region-block on Anthropic + Google currently blocks half the ensemble. Resolution timeline uncertain.
- Even when unblocked, costs scale (5 models × 21 candidate classes × multiple decoding temperatures = $50-200 vs B3's <$10).
- The Φ2 "single-vendor ensemble" concern is acknowledged in v0.3 already; addressing it is *strengthening* not *fixing*.

**18-month plan.**
- Month 3-6: VPS-side OpenRouter region routing / proxy alternative tested.
- Month 6-9: B4 run (if region unblocked) → separate ~5k word paper "Cross-family LLM ensembles for scientific taxonomy review: vendor variance vs ensemble effect" → *Patterns* or *NeurIPS-D&B*.
- Month 9-12: comparison data feeds back into C4 v2 or D2 (Track D-2).

**Cost.** $50-200 LLM. 1-2 weeks if region resolved.

### Track G — Long-term: ML benchmark on papers-with-code (compounding)

**18-month is too early — this is months 12-24+.** But seed it now:

**Deliverable.** Public benchmark task: "Given 100 raw event-size time series, predict (a) which class invariant best describes each, (b) which Vuong-LR alternative wins. Submit predictions; system scores against B3-curated ground truth." → papers-with-code listing → community submissions.

**Why this is the long-game endpoint.**
- Once papers-with-code has it as a task with multiple submissions, the project becomes "the benchmark for cross-domain class curation by language models," which is a T2/T3 hybrid.
- Cited every time someone proposes a new LLM-evaluation framework.
- Compounds because every external submission = new method paper that cites the benchmark.

**Plant the seed in months 12-18.** Full bloom at 24-36 months.

---

## 4. What NOT to do (kill list)

Explicit anti-recommendations:

| # | NOT to do | Why |
|---|---|---|
| ¬1 | Add a 14th, 15th, 16th system to chase headline count | Diminishing returns; 13 is enough; resources better spent on Track A packaging or Track C pre-registration |
| ¬2 | Polish C1 to Nature Phys / Nat. Commun. submission | W5-A explicit: desk-reject likely; arXiv + PRE + Chaos is the realistic ceiling |
| ¬3 | Build D1 phase-detector product (consumer app) | Distracts from academic agenda; PM track is parallel, not a substitute. D1 belongs to product line, not academic-value line. Defer or fork off |
| ¬4 | Argue with W5-A scholar reviewer's downgrade of "first proof of universality-class membership" | The downgrade is correct; accepting it makes C1 more credible, not less |
| ¬5 | Run more single-vendor B3 ensembles to "increase rigor" | Returns diminishing; the architectural diversity (B4) is the real gap, not within-vendor ensemble size |
| ¬6 | Chase social media virality / SEO blog content | Citation pull from non-academic visibility is near-zero; academic pull comes from referee networks + DOI infrastructure |
| ¬7 | Write a popular-science book version | Premature; viable in years 3-5 after T2/T3 contributions land |
| ¬8 | Submit to predatory journals to inflate publication count | Long-term reputation cost > short-term metric inflation |
| ¬9 | Spend 2+ months chasing FOIA / DOE for OE-417 data right now | Track A + Track C are higher leverage in the same time budget. OE-417 is v2-of-C1 material (~12-18 months out). |
| ¬10 | "Pivot" away from SOC framing toward more general critical-systems framing without empirical addition | Framing-only pivots don't earn citations; resource better spent on Track A / B / C concrete deliverables |

---

## 5. Month-by-month milestone roadmap

| Month | Milestone | Deliverable | Decision gate |
|---|---|---|---|
| **1** | F1-F5 statistical fixes done | bootstrap@10k re-run; surrogate-null for r_shape; xmin sensitivity; FWER paragraph; Bonferroni discussion | C1 v0.4 internal sign-off |
| **1-2** | **Track A — Zenodo DOI ship** | dataset bundle frozen + DOI minted + Zenodo record live | DOI assigned y/n |
| **2** | C1 v0.4 → arXiv | arXiv preprint cond-mat.stat-mech + physics.data-an | submit y/n |
| **2-3** | Track B — C4 v0.2 revisions | C4 v0.2 → submit *Patterns* / *NeurIPS-D&B* / *J. Stat. Softw.* | submit y/n |
| **2-3** | Track E — outreach round 1 | email Plenz / Priesemann / Scheffer with arXiv + DOI links | response received y/n |
| **3-4** | Track A — *Scientific Data* paper drafted | companion paper ~5k words | submit y/n |
| **3-4** | Track C — P1 (Bitcoin Cash) + P2 (Reddit) data acquired + fit | results JSONL committed | in-band / out-of-band logged |
| **4-5** | Track C — P4 (Flickr) data acquired + fit | results JSONL committed | in-band / out-of-band logged |
| **5-6** | Track C — P3 (FluNet) + P5 (Bonabeau) data acquired + fit | results JSONL committed | 5/5 / 4/5 / 3/5 / ≤2/5 readout |
| **6** | Track C — pre-registered replication paper drafted | short paper ~4k words | arXiv + journal submission |
| **6-9** | Track D — D1 block-bootstrap-for-EWS paper | drafted + submitted *Methods in Ecology and Evolution* | submit y/n |
| **6-9** | **Track B — C4 first revision round** | revisions back | accept / revise / reject |
| **6-9** | C1 PRE submission (post-revision based on arXiv feedback) | full submission to *Phys. Rev. E* | accept / major revise / reject |
| **9-12** | Track F — B4 cross-family ensemble (if region resolved) | B4_taxonomy_v3 run + paper drafted | submit y/n |
| **9-12** | Track E — co-author negotiation closed for ≥1 paper | joint authorship secured for either D1 or A2-Scheffer | y/n |
| **9-12** | Track D — D2 reject-aware critic methodology paper | drafted + submitted | submit y/n |
| **12-15** | C1 PRE second revision round + acceptance | C1 accepted at PRE | published y/n |
| **12-15** | Track D — D3 universal-collapse null methodology paper | drafted + submitted *EPL* / *Comput. Phys. Commun.* | submit y/n |
| **12-18** | Track G seeding — papers-with-code listing | benchmark task page live | community submissions y/n |
| **15-18** | Conference talks — APS March Meeting / NetSci / CCS 2027 | accepted talks ≥ 1 | y/n |
| **15-18** | Track A v1.1 dataset release (with pre-registered new systems integrated) | new Zenodo version | DOI assigned y/n |
| **18** | **Milestone review** | total: arXiv preprints ≥ 5, journal submissions ≥ 4, accepted papers ≥ 2, Zenodo dataset ≥ 100 downloads | continue / pivot |

---

## 6. Immediately actionable — next 30 days (top 10)

Concrete tasks startable in session #3 or #4. Each tagged with effort (S/M/L) + suggested owner:

| # | Task | Effort | Owner | Output |
|---|---|---|---|---|
| **N1** | **Track A start — assemble Zenodo dataset bundle** (manifest + LICENSE + README + provenance) | M | main session or W8 agent | `dataset/v1.0/manifest.json` + `dataset/v1.0/README.md` |
| **N2** | **F1 fix — bootstrap rerun at n=10,000 for headline phases (1, 4, 12, A2-Scheffer)** | M | bash bg + monitor | `v4/results/bootstrap_v2_10k.jsonl` |
| **N3** | **F5 fix — surrogate-null permutation test for r_shape=1.11** (10k iid lognormal-matched 7-system surrogates) | M | bash bg + W8 agent | `v4/results/r_shape_surrogate_null.json` + `figures/r_shape_null_dist.png` |
| **N4** | **F4 fix — xmin sensitivity scan figures for Phase 7, 13, 4, 11** (sliding xmin across 10-90 percentile) | S | W8 agent | `paper/figures/xmin_sensitivity_*.png` × 4 |
| **N5** | **Track A — register Zenodo project + reserve DOI** (no upload yet) | S | main session | reserved DOI string |
| **N6** | **C4 v0.2 — model-architecture-confound paragraph + 5→3 layer compression** | S | W8 agent | `paper/c4-reject-aware-pipeline-2026-05-13.md` v0.2 |
| **N7** | **Track E — outreach email draft template + top-3 senior researcher email list** | S | W8 agent | `docs/outreach/round-1-template.md` + `docs/outreach/contacts.json` |
| **N8** | **Track C — P1 (Bitcoin Cash) data acquisition script** | S | W8 agent | `v4/validation/preregistration-p1-bitcoincash/fetch.py` + JSONL |
| **N9** | **Track C — P2 (Reddit cascade) Pushshift-alternative data acquisition strategy** (Pushshift dead per HANDOFF §3; identify replacement) | M | W8 agent | `docs/preregistration/p2-data-strategy.md` |
| **N10** | **C1 v0.4 changelog + FWER discussion paragraph (F3 fix)** | S | W8 agent | `paper/v0-unified-pipeline-2026-05-13.md` v0.4 |

---

## 7. Wave 8 dispatch — 5 mini-briefs ready to fire

Each is a self-contained subagent-startable task with effort sizing + acceptance criteria.

### W8-1 — Zenodo dataset bundle assembly

**Goal.** Package the 13 datasets + nulls + frozen pipeline + B3 taxonomy + tutorial into a Zenodo-ready bundle at `dataset/v1.0/`.

**Inputs.** `v4/validation/*/` (13 phase data dirs), `v4/results/B3_taxonomy_v2.jsonl`, `v4/lib/soc_pipeline.py`, `v4/taxonomy/classes/*.yaml`, `tutorials/01_reproduce_earthquake_soc.ipynb`.

**Deliverables.**
- `dataset/v1.0/manifest.json` — file inventory + SHA-256 hashes + source URL + license per file
- `dataset/v1.0/README.md` — provenance + citation request + replication-quickstart (5-min)
- `dataset/v1.0/LICENSE-data.txt` — CC-BY-4.0 for data
- `dataset/v1.0/LICENSE-code.txt` — MIT for code
- `dataset/v1.0/CITATION.cff` — machine-readable citation file
- `dataset/v1.0/requirements.txt` — pinned Python deps (snapshot of `.venv` site-packages)
- short shell script `bin/replicate-phase1.sh` that reruns Phase 1 in <5min from cold

**Acceptance.** PR opens; reviewer can run `bin/replicate-phase1.sh` and reproduce b=1.084 ± 0.01 within ~5min. Manifest passes a "no stale paths" check.

**Effort.** M (1 day). **LLM.** None.

### W8-2 — Surrogate-null for r_shape=1.11

**Goal.** Compute the empirical p-value of r_shape=1.11 against a 10,000-iid-lognormal-matched surrogate null distribution.

**Method.**
1. For each of 7 universal-collapse systems, fit lognormal with empirical (μ, σ²) on the same tail used for the row-centered log-PDF.
2. Sample 10,000 surrogate 7-tuples of lognormal datasets, matched in n and (μ, σ²) per system.
3. For each surrogate 7-tuple, recompute row-centered log-PDF on the same rescaled grid + cross-system/within-system variance ratio.
4. Compare empirical r_shape=1.11 to the 10k-sample null distribution; report percentile rank + 95% CI of the null mean.

**Deliverables.**
- `v4/scripts/r_shape_surrogate_null.py` (reusable script)
- `v4/results/r_shape_surrogate_null.json` — null mean, std, percentile rank of 1.11
- `paper/figures/r_shape_null_dist.png` — histogram + empirical-value marker
- `paper/v0-unified-pipeline-2026-05-13.md` v0.4 § 4.5 paragraph cited

**Acceptance.** Reviewer can re-run the script and recover the percentile rank to 2 decimal places. p-value (one-tailed) reported as either p<0.001 or p=X.YYY.

**Effort.** M (1-2 days). **LLM.** None — pure numerical.

### W8-3 — Bootstrap rerun at n=10,000 for headline phases

**Goal.** Rerun bootstrap CIs at n_boot=10,000 (not 100) for Phases 1, 4, 12, A2-Scheffer.

**Method.** For each phase, regenerate the bootstrap loop with `n_boot=10000`. Use bash background (per HANDOFF §3) to avoid Monitor-armed-fallback. Save full bootstrap distribution to `.jsonl`, then compute 95% percentile CI.

**Deliverables.**
- `v4/scripts/bootstrap_v2.py` (parametric — phase as CLI arg, n_boot configurable)
- `v4/results/bootstrap_v2_10k_phase1.jsonl`, `..._phase4.jsonl`, `..._phase12.jsonl`, `..._a2scheffer.jsonl`
- Updated Table 1 in `paper/v0-unified-pipeline-2026-05-13.md` with refined CI columns
- Brief diff note: how (if at all) the CI shifted from n=100 → n=10,000

**Acceptance.** All 4 phases re-run, CI endpoints reported, paper Table 1 updated, original n=100 values preserved in changelog as "v0.3 CIs (deprecated)".

**Effort.** M (1 day wall + 1 night compute). **LLM.** None.

### W8-4 — C4 v0.2 revisions (model-architecture confound + layer compression)

**Goal.** Produce C4 v0.2 with W5-A §5.3 critical fixes applied.

**Edits.**
1. Acknowledge or fix the model-architecture-confound: B1 = single Opus, B3 = 3× DeepSeek. Add either (a) section "5.X Limitations: vendor confound" honestly framing, OR (b) data from a within-vendor Opus×3 self-consistency test to isolate ensemble effect from vendor effect.
2. Compress 5-layer pipeline diagram → 3-layer (extract / curate / critic+predict).
3. Cut "0 API errors" from headline; move to §3 robustness footnote.
4. Add 1-paragraph framing the result as "within-vendor consistency check, pending B4 cross-family" rather than "multi-model ensemble".
5. Update §4 with explicit "rejection-rate baseline vs ensemble-size effect" disentangling discussion.
6. Update target-venue § with primary = *Patterns* (Cell Press), secondary = *NeurIPS Datasets & Benchmarks*, tertiary = *J. Stat. Software*.

**Acceptance.** PR opens with v0.2 paper. Word count delta < 1500 (compression preferred). Internal reviewer can confirm the model-architecture-confound is addressed.

**Effort.** S-M (4-6 hours). **LLM.** $0.

### W8-5 — Pre-registration P1 (Bitcoin Cash) end-to-end run

**Goal.** Execute the first of the 5 §8 pre-registered systems: Bitcoin Cash daily log returns (2017-2025), predicted band α = 2.8 ± 0.3.

**Method.**
1. Fetch BCH daily OHLC from Yahoo Finance / CryptoCompare / Binance API (whichever has full 2017-2025 history).
2. Compute daily log returns: r_t = log(close_t / close_{t-1}).
3. Filter |r_t| ≥ threshold (use same threshold convention as Phase 2 S&P 500).
4. Run frozen `v4/lib/soc_pipeline.py` to fit Clauset α + bootstrap CI + Vuong vs LN.
5. Verdict per v0.3 §8.3: in-band [2.5, 3.1] / out-of-band.
6. Write `v4/validation/preregistration-p1-bitcoincash/paper.md` (~1-2k words).
7. Append result to `v4/results/preregistration_results.jsonl`.

**Acceptance.** Result reproducible via single `python v4/cli.py validate preregistration-p1-bitcoincash`. JSONL row exists with verdict + CI + Vuong R. Paper draft committed.

**Effort.** M (1 day data + 0.5 day write-up). **LLM.** $0 (pure stats).

---

## 8. Single highest-leverage action (top-1 pick)

**Action.** Ship the Zenodo dataset bundle (Track A start) in the next 2 weeks.

**Why this beats every alternative.**

1. **18-month citation pull projection.**
   - Track A (dataset DOI): realistic 50-200 citations in 18 months once *Scientific Data* paper lands and ecology / network / finance / physics communities discover it. Reuse compounds.
   - Track B (C4 methodology): realistic 10-50 citations in 18 months at *Patterns* / *NeurIPS-D&B*.
   - Track C (pre-registered replication): realistic 5-30 citations in 18 months.
   - C1 (current PRE submission target): realistic 10-50 citations in 18 months *if accepted*, 0-5 if stuck in revision.

2. **Risk profile.** Track A acceptance probability at *Scientific Data* is ~50% (high for Nature-family). Zenodo deposit itself is *zero-risk* — DOI is minted regardless of paper acceptance. The dataset earns citations even if no paper ever lands.

3. **Resource cost.** ~2 weeks of packaging + 2 weeks of paper drafting. All inputs already exist. No new compute. No new LLM. No external dependencies.

4. **Compound effect.** Every external researcher who cites the dataset is *also* a referee-network node + a potential collaborator. Co-author outreach (Track E) gets easier when the project already has a DOI.

5. **Removes scope critiques in one move.** "Single-author" / "single-vendor B3" / "single-pipeline-implementation" are all critiques that lose force when the *dataset itself* becomes community infrastructure that anyone can re-analyze with their own pipeline / vendor / co-authors.

**The C1 PRE submission is fine and should still happen, but it is not where the 18-month leverage is.**

---

## 9. Scoring rubric — "did we produce real academic value?"

Specific metrics with 18-month and 36-month targets:

| Metric | Source | 18-month target | 36-month target | Why this number |
|---|---|---|---|---|
| Total citations on project preprints + papers | Google Scholar | ≥ 30 | ≥ 100 | Median single-author cross-domain physics preprint at 18 months: 5-15. Reaching 30 implies above-median, dataset-reuse-driven |
| Zenodo dataset total downloads | Zenodo download counter | ≥ 100 | ≥ 500 | Comparable: SCEC Community Stress Drop benchmark gets ~50/year. Dataset paper acceptance + papers-with-code listing should push 100+ |
| Replication attempts by external groups | direct outreach + Google Scholar | ≥ 2 | ≥ 5 | Even 1 external replication is a significant academic-value signal in single-author SOC literature |
| Co-author papers with senior physicists | author list | ≥ 1 | ≥ 3 | Track E success metric. 1 co-authored paper at 18 months = significant credibility lift |
| Invited talks (workshops / conferences / departments) | direct invitation | ≥ 1 | ≥ 5 | APS / NetSci / CCS 2027 talk submission. 1 at 18 months is realistic, 5 at 36 months requires Track A / E success |
| arXiv preprints posted | arXiv | ≥ 5 (C1, C4, Track A companion, Track C pre-reg, Track D-D1) | ≥ 8 | Five distinct preprints across the six tracks is a reasonable mid-pace |
| Peer-reviewed published papers | journal acceptance | ≥ 2 | ≥ 4 | Modest, realistic; one journal cycle typically 9-12 months |
| Inclusion in review article / textbook section | Google Scholar full-text search | ≥ 0 (stretch goal) | ≥ 1 | Textbook inclusion is the strongest legitimacy signal but typically 3-5 years out |
| papers-with-code submissions to benchmark | PWC platform | not seeded yet | ≥ 1 external submission | Track G seed in months 12-18; first external submission at month 24-30 |
| Bonafide T2/T3 contribution recognition | citation in another methodology paper (e.g. someone calling "reject-aware pipeline" by that name) | ≥ 0 | ≥ 1 | Hardest metric, but the most diagnostic of "real academic value" vs "PR" |

**Hardest test.** At month 36, ask: "Has someone outside the project replicated, cited, or extended the methodology in a way the author had not personally requested?" If yes ≥ 3 times, this project produced real academic value. If no, it produced craftsmanship — still valuable, but not field-shifting.

---

## 10. Open questions for user / PM (none currently blocking; decisions can be deferred)

| # | Question | Default if no answer |
|---|---|---|
| Q1 | Is the project willing to use a non-`gmail.com` / non-`github.com` email for arXiv submission? arXiv moderation rejects placeholders. | Use `wanqh@u.illinois.edu`-style alumni email if available, else `riazward110@gmail.com` standalone; do not block on this |
| Q2 | Track G papers-with-code seeding: when to fork D1-phase-detector product line vs keep academic-only | Defer to month 12; D1 product is currently parallel track in HANDOFF §2 Sprint A |
| Q3 | Co-author outreach: cold-email vs conference-introduction-first | Default cold-email at month 2-3 with arXiv + DOI links in-hand; switch to conference if low response |
| Q4 | Funding source if any track needs >$200 compute (Track F B4 cross-family possible) | Default self-fund up to $500 total over 18 months; if more needed, defer until Track A / B traction justifies it |
| Q5 | Zenodo DOI single-author attribution vs add Claude / contributors | Single-author for v1.0; future versions can credit co-authors per Track E outcome |

---

## 11. Document version + provenance

- **v0.1 — 2026-05-13.** Initial W7-A subagent draft. Builds on W5-A scholar review, paper v0.3, HANDOFF session-2-end.
- **Author.** W7-A subagent persona (research-strategist).
- **PR target.** structural-isomorphism main branch.
- **Status.** Ready for W8 dispatch + user review.

---

**End of W7-A roadmap.**
