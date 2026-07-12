# Experiment and data revalidation matrix

Date: 2026-07-12
Status: independent audit; no experiment was rerun by this document
Runtime authority: `NEXT_SESSION.md`

## 1. Decision rules

An asset may remain in the product only when its current evidence supports the
exact user-facing role. “File exists,” “test passes,” “model returns a result”
and “paper reports PASS” are not equivalent to valid data, external validity or
user value.

Revalidation priority is determined by:

`user exposure × claim strength × evidence weakness × irreversibility`

Evidence classes must remain explicit:

- `production-real`: deployed artifact with complete checksum/provenance;
- `research-real`: real observations not necessarily independent or current;
- `manual-coded`: real source material transformed by human judgment;
- `literature-derived`: constants/claims transcribed from publications;
- `synthetic`: generated data or calibrated simulator;
- `model-judged`: labels/claims produced by a model;
- `demo`: frozen product snapshot not suitable for current-world inference.

Global stop conditions:

1. Stop and downgrade if provenance, license or source identity cannot be
   established.
2. Stop positive claims if a frozen holdout or independent replication fails.
3. Preserve all FAIL/REJECT/NULL/INCONCLUSIVE outcomes.
4. Do not expand sample size merely until significance appears.
5. Do not promote model judgments or synthetic anchors to human/real evidence.

## 2. Executable asset matrix

### A. Production KB: 4,443-row artifact

- Asset: `data/kb-expanded.jsonl`, production embeddings and
  `artifacts/production-v2-4443.json`.
- Problem: deployment integrity is strong, but scientific provenance and
  licensing are uneven by row. Many descriptions are assertions rather than
  independently verified structural mappings.
- User impact: every search candidate, evidence card and generated transfer.
- Redo: validate schema/deduplication; stratify rows by provenance class;
  manually audit a risk-weighted sample by type/domain/source; quarantine rows
  without recoverable source or defensible mechanism.
- Metrics: 100% artifact hash/shape agreement; 100% license field coverage;
  >=95% sampled source recovery; >=90% expert mechanism agreement; zero known
  duplicate IDs/content.
- Stop: any source/license ambiguity blocks “verified” presentation but need not
  block clearly labelled candidate retrieval.
- Ownership: schema/hash/dedup automatic; source/license/mechanism review human.
- Priority: P0 for provenance labels, P1 for expert sample, P2 for full registry.

### B. Historical/staged KBs and additions

- Asset: `kb-5000-merged.jsonl`, staged additions, 200-row data-layer overlay
  and historical 4,888/5,333 counts.
- Problem: multiple incompatible counts and schemas; not production data; risk
  of accidental merge or marketing drift.
- User impact: model/data cards, future retrieval expansion, reproducibility.
- Redo: inventory every row against production IDs, source and license; validate
  additions in isolated candidate artifact; run frozen quality regression before
  any merge.
- Metrics: deterministic manifest; zero ID/content collisions; no English,
  Chinese, OOS or latency regression; human quality improvement on new coverage.
- Stop: no merge if benefit is only more rows or taxonomy coverage.
- Ownership: inventory/regression automatic; inclusion decisions human.
- Priority: P1; keep out of current product until then.

### C. Structural-v2 embedding model

- Asset: local 768-dimensional production model and 4,443 embeddings.
- Problem: artifact recovery exists, but training corpus/split/model provenance
  are not sufficiently complete for a generalization claim. Historical 100%
  retrieval used a leaking pair-level split.
- User impact: initial candidate recall and ranking.
- Redo: reconstruct training manifest; group split by description/type/domain/
  source; leave-one-type/domain-out; hard negatives; compare to multilingual and
  general embedding baselines.
- Metrics: frozen human nDCG@5/Success@5; cross-domain rate; calibration; Chinese
  regression; OOS precision/recall; p95 latency and memory.
- Stop: retire any performance claim if training/eval membership is unknown;
  retain production model only as an operational baseline.
- Ownership: reconstruction/evaluation automatic where data exists; split audit
  and final relevance judgment human.
- Priority: P0 claim downgrade already required; P1 scientific rerun.

### D. Historical structural-v1 / SIBD benchmark

- Asset: 1,214 descriptions, 84 types, historical model and cards.
- Problem: description leakage across random pair split; Chinese-only; placeholder
  arXiv citation; training examples may be synthetic/editor-authored.
- User impact: public credibility, model comparison and developer adoption.
- Redo: immutable dataset manifest, group/source split, provenance/license per
  item, external benchmark review.
- Metrics: no group leakage; complete source/provenance; held-out retrieval with
  confidence intervals and baseline comparison.
- Stop: remove 100% Retrieval@5/10 from promotional tables and remove placeholder
  formatted citations until a real identifier exists.
- Ownership: leakage/card checks automatic; provenance and external review human.
- Priority: P0 public-claim hygiene, P2 benchmark rehabilitation.

### E. Frozen 100-query bilingual retrieval evaluation

- Asset: `evaluation/retrieval-v1.jsonl`, 400 graded qrels and baseline results.
- Problem: qrels are from one LLM judge and function as a development set;
  possible taxonomy/type dependence; not a publication gold standard.
- User impact: model selection and CI release gate.
- Redo: retain as dev set; create untouched query-level holdout stratified by
  language/OOS/type/domain; use three independent human reviewers and expert
  adjudication; compare direct search and Ask retrieval separately.
- Metrics: nDCG@5, Success@5, MRR, same-domain-only error, bilingual consistency,
  Krippendorff alpha or pairwise weighted kappa, confidence intervals.
- Stop: do not optimize repeatedly against the human holdout; one final model
  selection followed by sealed evaluation.
- Ownership: bundling/metrics automatic; labels/adjudication human.
- Priority: P0.

### F. Expanded English candidate pool: 594 unjudged items

- Asset: deterministic blinded bundle under `evaluation/review/`.
- Problem: no human labels yet; candidate pool is not recall-complete; reviewer
  identity/independence cannot be established by code.
- User impact: English model launch decision.
- Redo: three independent reviewers for every task, adjudicate all disputes,
  reserve an untouched query holdout, and document reviewer expertise.
- Metrics: every task has >=3 reviews; no disputes; mean quadratic kappa >=0.67;
  human nDCG/Success improvement with lower paired CI >0; no Chinese regression.
- Stop: no model promotion on fixed-pool gain alone; stop labeling if rubric
  failure appears, repair rubric prospectively, restart affected batch.
- Ownership: tool/validation/metrics automatic; all labels/adjudication human.
- Priority: P0.

### G. Multilingual MiniLM experiment

- Asset: offline fixed-pool signal and cached public model.
- Problem: positive nDCG signal is selection-limited; expanded Top-50 includes
  many unjudged documents; no endpoint/OOS/concurrency production gate.
- User impact: possible English quality improvement and latency/cost.
- Redo: evaluate on adjudicated expanded pool and sealed holdout; encode all KB
  locally; compare hybrid/rerank variants; production-shadow latency/OOS test.
- Metrics: English nDCG@5 +0.05 and Success@5 +0.08 with paired lower CI >0;
  English/Chinese gap halved; Chinese delta non-negative within tolerance; OOS
  precision/recall >=0.98; p95 retrieval <=1.5s.
- Stop: no launch if recall gain is unmeasured, Chinese falls, or operational
  budget fails. Do not tune threshold on sealed holdout.
- Ownership: automatic after human qrels exist; final error analysis human.
- Priority: P1 following F.

### H. Scope/OOS evaluation

- Asset: rule-based guard tests and production smoke examples.
- Problem: curated cases may not reflect adversarial or ambiguous real queries;
  multilingual false positives/negatives and domain-specific safety remain weak.
- User impact: refusal quality, trust and misuse exposure.
- Redo: freeze balanced multilingual OOS/near-boundary set from real-like tasks;
  blind human ground truth; evaluate both rule and model layers.
- Metrics: precision/recall >=0.98 for explicit prohibited classes; boundary
  abstention and appeal rate; zero investment guarantee/prediction bypass.
- Stop: high-risk false negative blocks release; ambiguous research questions
  should be routed to clarification rather than forced accept/reject.
- Ownership: generation of adversarial fixtures automatic; labels human.
- Priority: P0/P1.

### I. Transfer report and outcome experiment data

- Asset: report store, selected candidate, structured experiments and outcomes.
- Problem: implementation exists but no prospective cohort proves decisions or
  outcomes; self-report and missing-not-at-random follow-up are expected.
- User impact: the product's actual value and retention claim.
- Redo: 15–20 target-user prospective pilot; freeze primary task and success rule
  before output; strong general-LLM baseline; day 0/7/14/30 follow-up.
- Metrics: candidate acceptance >=60%; experiment creation >=35%; verified start
  >=20%; terminal outcome return >=15% by day 14; value-linked day-30 return
  >=25%; failures included.
- Stop: do not expand features if users like reports but do not start experiments;
  narrow ICP or workflow instead.
- Ownership: telemetry/reminders/analysis automatic; real tasks/outcomes human.
- Priority: P0 protocol, P1 execution.

### J. Phase Detector 597-ticker demo snapshot

- Asset: `ews_meta.json`, demo prices/results and 597 company surfaces.
- Problem: frozen demo provenance, not current market data; EWS and company
  classifications can be mistaken for live or predictive signals.
- User impact: research exploration and reputational/financial risk.
- Redo: for research only, rebuild from licensed timestamped prices with an
  immutable universe and walk-forward procedure; distinguish point-in-time
  constituents and survivorship; independently reproduce.
- Metrics: data coverage/missingness, timestamp correctness, constituent
  point-in-time accuracy, calibration and walk-forward null/positive results.
- Stop: null backtest keeps investment commercialization closed; demo may remain
  only with prominent frozen/non-investment labeling.
- Ownership: pipeline automatic; data license and financial-method review human.
- Priority: P0 keep downgraded; P2 only if research question justifies rerun.

### K. Phase walk-forward backtest

- Asset: v0.2 negative result and historical backtest artifacts.
- Problem: no alpha evidence; possible universe/data/version dependence; repeated
  reruns risk specification search.
- User impact: must not support trading, pricing or “this week's signals.”
- Redo: only under a new timestamped preregistration with point-in-time data,
  transaction costs, delisting/survivorship controls and untouched final period.
- Metrics: preregistered risk-adjusted lift, confidence interval, turnover/cost,
  calibration and multiple-testing accounting.
- Stop: do not rerun merely to seek significance. A second null closes the alpha
  branch unless a genuinely new mechanism is preregistered.
- Ownership: analysis automatic; data licensing, design and interpretation human.
- Priority: remove/downgrade product now; optional P2 research.

### L. WTO manually-coded retaliation sample

- Asset: 23 complaint rows, row-level probit, 17-cluster bootstrap and LOO.
- Problem: manual coding, linked cases, selected retaliation-request sample,
  separation tail and no causal assignment. Cluster sensitivity preserves sign
  but not coefficient precision.
- User impact: manuscript credibility and product evidence examples.
- Redo: two trade-law experts code independently from blinded bundle; third
  adjudicator; review policy clusters; fit cluster-aware/Firth or Bayesian
  sensitivity; retain selection limitation.
- Metrics: complete double coding, agreement, zero unresolved disputes; LOO sign,
  separation diagnostics, posterior/penalized interval; coding provenance.
- Stop: disagreement or source ambiguity prevents strong claim; no observational
  analysis upgrades to causal confirmation.
- Ownership: bundle/statistics automatic; coding/adjudication/domain review human.
- Priority: P0 submission block; P1 completion.

### M. Taxonomy and 18-class verdict sweep

- Asset: class YAMLs, B1/B3/B4 reviews, PASS/REJECT/SPLIT/MERGE summaries.
- Problem: model/internal critic judgments, synthetic/literature anchors,
  incomplete preregistration and researcher degrees of freedom. Schelling is
  internally rejected as a universality class but later positively relabelled.
- User impact: candidate explanations, “verified class” labels and paper counts.
- Redo: immutable supersession registry; distinguish mechanism class from
  statistical descriptor; independent complex-systems/domain review; rerun only
  a small real-data core under frozen criteria.
- Metrics: inter-reviewer agreement, external-review completion, class-specific
  falsifiers, matched non-class controls, no unresolved contradictory verdict.
- Stop: classes lacking dynamical mechanism or real anchors cannot be presented
  as verified universality classes; keep as candidate analogies if labelled.
- Ownership: consistency checks automatic; class validity external human.
- Priority: P0 label downgrade/conflict block, P2 rehabilitation.

### N. SOC real-data core: earthquake, stock, DeFi, neural

- Asset: shared Clauset/SOC pipeline outputs and per-domain datasets.
- Problem: real systems differ in dependence, sampling, observables and data
  quality; lognormal is not always rejected; some neural evidence is session-
  sensitive; stock heavy tails do not imply common mechanism.
- User impact: scientific credibility and evidence shown for structural transfer.
- Redo: re-download from authoritative snapshots where permitted; checksum raw
  data; domain-correct preprocessing; block/bootstrap dependence; xmin/tail-size
  sensitivity; alternative distributions; leave-one-system/session-out; matched
  non-class controls.
- Metrics: bootstrap GOF, tail n/xmin stability, likelihood ratios, heterogeneity,
  session/protocol robustness and reproducible clean-run outputs.
- Stop: call results “scaling concordance” unless mechanism-discriminating tests
  and external domain review support universality.
- Ownership: downloads/pipeline largely automatic; license/domain interpretation
  and external replication human.
- Priority: P1 methods paper core, P2 broader empirical claim.

### O. Synthetic validation systems and null controls

- Asset: simulator results, synthetic anchors and matched null generators.
- Problem: useful for implementation falsification but sometimes counted toward
  empirical class confirmation; calibrated generators risk circular success.
- User impact: confidence badges and manuscript PASS counts.
- Redo: registry of generator purpose, parameters chosen before/after anchors,
  seeds and expected failure; additional adversarial nulls generated by someone
  other than pipeline author.
- Metrics: false-positive rate across frozen null families; sensitivity to seed
  and generator family; explicit exclusion from real-world evidence counts.
- Stop: synthetic PASS never upgrades a real mechanism claim.
- Ownership: automatic experiments; independent null design human/external.
- Priority: P0 claim classification, P1 robustness.

### P. Preregistered CVE, FDNY and WSB experiments

- Asset: timestamped YAMLs followed by real-data FAIL/PARTIAL results.
- Problem: data extraction and observable choices need source/license review;
  administrative burstiness and regime shifts complicate interpretation.
- User impact: strongest demonstration that the pipeline can reject hypotheses.
- Redo: verify commits predate acquisition, archive source snapshot/checksum,
  reproduce in clean environment, audit deviations and alternative definitions
  without changing the primary verdict.
- Metrics: source recoverability, checksum, exact prereg compliance, clean-run
  equality, deviation ledger and domain reviewer assessment.
- Stop: do not refit primary definitions; sensitivity analyses remain secondary.
- Ownership: timestamps/reproduction automatic; source/license/domain review human.
- Priority: P1; retain negative results prominently.

### Q. Claim-evidence ledger and v0.5 manuscript

- Asset: manuscript, four/five bounded claims, conflict register and headline
  inventory.
- Problem: ledger coverage now guards Abstract/Contributions but the manuscript
  contains broader legacy claims, synthetic-heavy counts and unresolved external
  review. References/cards contain placeholder citation identifiers.
- User impact: academic trust, public claims and future paper-drafting feature.
- Redo: narrow to reject-aware method plus 3–4 real systems; full raw→result→
  figure provenance DAG; external statistician/domain review; clean-room rerun;
  remove placeholder/fabricated-looking citations.
- Metrics: 100% headline and empirical-sentence evidence mapping; zero placeholder
  citation; all conflicts resolved or prominently blocking; external reviewers
  recorded; clean-run reproduction.
- Stop: submission remains NO-GO until external review, WTO coding boundary and
  taxonomy contradictions are resolved.
- Ownership: consistency/reproduction automation; scientific judgment/authorship
  and external review human.
- Priority: P0 submission block, P1 methods draft, P2 submission decision.

### R. Model-generated transfer reports

- Asset: Ask/report generation using the production LLM and retrieved candidates.
- Problem: model output can synthesize unsupported causal mechanisms, evidence or
  citations beyond retrieval; version/model changes affect reproducibility.
- User impact: the central decision artifact.
- Redo: structured claim/citation guards; sentence-level provenance categories;
  frozen adversarial cases; compare models on unsupported-claim and correction
  burden, not eloquence.
- Metrics: zero invented citations/numbers in guarded fields; unsupported
  mechanism rate; evidence/counter-evidence completeness; user/expert correction
  rate; model/version manifest coverage.
- Stop: generated prose is never “verified evidence”; unsafe unsupported claims
  block report completion or receive an explicit unverified label.
- Ownership: validation automatic; expert usefulness/safety review human.
- Priority: P0/P1.

## 3. Cross-asset execution order

### P0 — Prevent unsupported product and paper claims

1. Keep the 4,443 artifact canonical; label row-level provenance and quarantine
   “verified” presentation without sources/licenses.
2. Finish human design/recruitment for bilingual qrels and keep multilingual
   model launch blocked.
3. Preserve Phase as demo/null result and remove investment/alpha implications.
4. Keep WTO/Schelling and unresolved taxonomy conflicts submission-blocking.
5. Remove historical 100% retrieval and placeholder citations from promotional
   surfaces; retain only as explicitly historical provenance.
6. Freeze the prospective product-outcome pilot before collecting results.

### P1 — Rebuild the evidence core

1. Complete three-reviewer English judgments and sealed holdout evaluation.
2. Run the 15–20-user verified-transfer outcome pilot.
3. Complete WTO independent double coding/adjudication and cluster-aware
   penalized sensitivity.
4. Reproduce the 3 preregistered negative/partial experiments cleanly.
5. Revalidate the 3–4 strongest real SOC systems with domain-correct dependence
   controls, alternatives and leave-one-system/session-out.
6. Produce a narrower methods manuscript and full provenance bundle.

### P2 — External validity and scale decisions

1. External complex-systems statistician plus application-domain reviews.
2. Clean-room computational reproduction.
3. Expert-audited KB provenance registry and staged expansion decision.
4. Optional point-in-time Phase research rerun only under a new preregistration.
5. Submission and commercialization decisions only after the evidence thresholds
   in the value framework are reached.

## 4. What should be removed or downgraded now

- Remove all current or implied investment-alpha positioning from Phase.
- Remove historical 100% retrieval metrics from any current-performance claim.
- Remove placeholder arXiv/BibTeX entries from citation-ready surfaces.
- Downgrade KB “verified” labels to candidate/literature/synthetic/manual/real
  provenance unless row-level evidence supports verification.
- Exclude Schelling synthetic PASS from universality class PASS counts.
- Do not call the 400 LLM qrels or 594 unjudged pool human gold labels.
- Do not call four literature exponents “universal across matter.”
- Do not count synthetic/null implementation tests as independent empirical
  replications.

These changes do not destroy the assets. They align each asset with the role its
evidence can actually support.
