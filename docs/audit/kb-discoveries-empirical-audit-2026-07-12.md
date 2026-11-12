# KB, discoveries and empirical surfaces audit

Date: 2026-07-12
Status: independent audit; source data and shared code unchanged
Related plan: `docs/audit/experiment-data-revalidation-matrix-2026-07-12.md`

## 1. Executive decision

The three surfaces contain substantial research material but currently have
different maturity levels:

- The **natural-language KB** is a useful Chinese candidate-retrieval corpus,
  not a source-backed evidence base.
- **Curated discoveries** are model-ranked research hypotheses, not discoveries
  established by peer review or real data.
- **Empirical surfaces** contain real analyses and valuable negative controls,
  but several current pages aggregate them into “13 verified systems” and
  “all predicted signals passed,” exceeding the evidence boundary.

None of the three reaches the 90/100 release bar defined below. They may remain
available only with role-appropriate labels: candidate corpus, validation queue,
and internal/draft empirical record.

## 2. Shared 90-point gate

Each surface is scored out of 100.

| Dimension | Weight | 90-level evidence |
|---|---:|---|
| Functional integrity | 15 | Complete, deterministic, versioned workflow with fail-closed error states |
| Experience | 15 | Non-expert can understand status, uncertainty and next action in both languages |
| Copy accuracy | 10 | No stale counts, black-box scores, implied proof, direct-publication promise or live/predictive drift |
| User/research value | 20 | Output changes a decision, prioritizes a falsifiable study or prevents a bad conclusion |
| Evidence quality | 20 | Claim maps to evidence, counter-evidence, alternatives and independent review |
| Data quality | 20 | Source, license, provenance class, language, version, checksum and sampling limitations are recoverable |

Hard gates override the total:

1. Synthetic, model-judged, literature-derived and real evidence are distinct.
2. “Verified” means a defined verification event, not high model score.
3. No citation, source, journal target or publication path is invented.
4. English is not claimed when only Chinese source text exists.
5. FAIL/REJECT/NULL/INCONCLUSIVE and contradictory evidence are preserved.
6. Current empirical claims are bound to the claim ledger or visibly marked as
   historical/internal drafts.
7. A non-specialist can restate known, uncertain and next step without saying
   “the mechanism is proved.”

## 3. Natural-language KB audit

### 3.1 Inventory evidence

Direct inspection of `data/kb-expanded.jsonl` found:

- 4,443 rows; all have exactly `id`, `name`, `domain`, `type_id`, `description`.
- 183 domain labels and 84 type IDs.
- 4,443/4,443 descriptions contain Chinese; 0 are English-only.
- 0 rows contain `source`, `sources`, `citation`, `provenance`, `data_layer` or
  `language`.
- No exact normalized description duplicates were found in this check.
- High-volume domains include macroeconomics 105, microeconomics 100, market
  microstructure 90, electrical engineering 85 and mechanical engineering 85.

This verifies artifact structure and language composition. It does not verify
the scientific truth of descriptions or type assignments.

### 3.2 Sample findings

The sample intentionally covered early/late rows, different domains and levels
of technicality.

| Row | Strength | Risk |
|---|---|---|
| `sci-001` radioactive decay | Plain-language proportional mechanism | Adds a sand-funnel analogy without source; analogy may influence retrieval independently of the real law |
| `sci-002` free fall | Clear variable relationship | Omits physical assumptions such as constant gravity/drag; acceptable candidate text, not universal statement |
| `sci-101` earthquake | Captures threshold/stress and heavy-tail intuition | “system maintains critical state” is a contested mechanism claim presented as fact |
| `5k-01-004` Anderson localization | Technically informative | Dense jargon, mixed dimensional regimes and “bifurcation” label require expert/type review |
| `5k-06-007` gamma oscillation | Identifies frequency and E/I mechanism | Strong causal wording and no source/session/context qualification |
| `5k-16-034` icing | Concrete operational failure mode | No explicit state equation or reason for its assigned structural type visible to user |
| `5k-26-043` guerrilla population dependence | Actionable causal narrative | Normative/strategic claim, politically sensitive, unsourced and not suitable for automatic intervention advice |
| `5k-ee-500` renewable learning curve | Quantitative and understandable | “about 20%” requires technology/time/source qualification; forecast-like transfer risk |

### 3.3 Language and experience

- The KB is Chinese-only while the product accepts English queries. English
  retrieval therefore depends on cross-lingual model behavior, translation or
  surface similarity rather than English evidence text.
- Many descriptions explain the phenomenon by inserting another analogy. This
  helps readability but can leak the intended class into the embedding and make
  retrieval evaluation partly circular.
- Technical rows contain undefined terms such as mobility edge,
  renormalization-group flow, inhibitory interneuron and percolation.
- The five-field schema cannot tell users whether a result is textbook fact,
  debated interpretation, synthetic example, manual analogy or empirical fit.

### 3.4 Same-domain suppression

The corpus has uneven domain frequencies. A generic “economy/market/organization”
query can draw many near-surface results from macroeconomics, microeconomics and
market microstructure before a useful distant-domain result appears. Current
type/domain labels are insufficient because:

- domain strings are not a controlled hierarchy;
- adjacent finance/economics labels can evade a simple unequal-domain rule;
- no source/user-domain field defines what “cross-domain” means for the query;
- candidate relevance and cross-domain novelty are different objectives.

Required evaluation: report relevance and domain distance separately; compare a
relevance-first list with a constrained diverse list; never improve cross-domain
rate by returning irrelevant distant items.

### 3.5 KB score

| Dimension | Score |
|---|---:|
| Functional integrity | 13/15 |
| Experience | 7/15 |
| Copy accuracy | 6/10 |
| User/research value | 12/20 |
| Evidence quality | 4/20 |
| Data quality | 5/20 |
| **Total** | **47/100 — candidate corpus only** |

### 3.6 KB rework

P0 automatic:

- Generate field coverage, language, duplicate, domain imbalance and jargon
  reports in CI.
- Add a sidecar provenance registry keyed by immutable row ID rather than
  mutating the production artifact immediately.
- Add automated source-format, license-enum and provenance-class validation.
- Build same-domain/adjacent-domain suppression diagnostics on frozen queries.
- Detect analogical label leakage phrases and route them to review; do not
  automatically delete them.

P1 human or mixed:

- Risk-stratified audit across all 84 types and high-volume domains.
- Domain experts approve type assignment, mechanism wording and contested status.
- Obtain source locator and license for every row promoted beyond “candidate.”
- Author or source genuine English descriptions; do not machine-translate them
  and call that independent English evidence.

Stop conditions:

- Rows without recoverable source/license remain retrievable only as
  `candidate-description`.
- A row with contested causal mechanism cannot receive a verified badge.
- KB expansion stops if human usefulness does not improve over the 4,443 baseline.

## 4. Curated discoveries audit

### 4.1 Inventory evidence

`web/data/a_discoveries_merged.json` contains 39 records. Every record includes
names/domains in Chinese and English, model score, risk, blocking mechanisms,
execution plan, journal target and practical-value prose. Coverage is uneven:

- `shared_equation`: 20/39; older 19 use a different `equations` field.
- English shared equation: 2/39.
- English variable mapping: 18 records; Chinese structured mapping: 20.
- English target venue: 1/39.
- All 39 contain an “isomorphism confidence” number, but it is an internal model
  score, not a calibrated probability.
- Literature status values are internal labels such as `unexplored` or `partial`,
  not the result of a recorded systematic review.

### 4.2 Function and experience

Strengths:

- Cards expose risk, blocking mechanism and execution ideas rather than only a
  headline analogy.
- Filters and expanded detail support research triage.
- The updated public copy now calls these validation candidates and explains the
  AI score boundary.

Remaining defects:

- Records mix two schemas, making comparable rendering and evaluation fragile.
- “target venue,” “paper title,” “solo feasible” and time estimate imply a
  publication pathway before citation/data verification.
- A numeric 0–100 model score remains visually precise despite no calibration.
- “Unexplored” can only mean “not found in the search performed,” but no search
  corpus, date, query or reviewer is recorded.
- English readers receive translated headlines/plans but often lack English
  equations/mappings, producing asymmetric evidence.
- There is no direct action to create a preregistered validation task with data,
  baseline and stop rule; “generate report” can produce more prose instead.

### 4.3 Value sample

High-potential, conditional candidates:

- Intersection spillback ↔ grid cascading: measurable network intervention and
  strong falsification baseline.
- Liquidation cascades ↔ network clearing: high risk-control value, but common
  shock and exposure reconstruction are decisive alternatives.
- Stablecoin peg ↔ damped control oscillation: testable recovery features, but
  strategic/reflexive regimes weaken the physical mapping.
- Supply-chain cascade ↔ financial contagion: useful topology intervention if a
  complete partner graph exists.

Low-value or downgrade examples:

- Piezo1 gating ↔ hedonic adaptation: incompatible mechanism/time scale.
- Cognitive dissonance ↔ Lyapunov stability: descriptor-level word match.
- CRISPR spacer acquisition ↔ VC return tails: selection language without a
  shared generating intervention.
- Trust collapse ↔ coral bleaching: memorable metaphor, underspecified state.
- Repeated DeFi/earthquake pairs inflate discovery count and should be one
  research program.

### 4.4 Discoveries score

| Dimension | Score |
|---|---:|
| Functional integrity | 11/15 |
| Experience | 10/15 |
| Copy accuracy | 7/10 |
| User/research value | 12/20 |
| Evidence quality | 5/20 |
| Data quality | 8/20 |
| **Total** | **53/100 — validation queue** |

### 4.5 Discoveries rework

P0 automatic:

- Normalize the two record schemas and fail on missing bilingual evidence fields.
- Rename confidence to internal structure-match score everywhere; show no percent
  symbol unless calibrated.
- Replace publication target/time with validation readiness and evidence gaps.
- Deduplicate pairs into research programs and expose the number of variants.
- Add a one-click **Create validation plan**, not “write paper”: hypothesis,
  alternatives, data, baseline, metric, stop rule and provenance.

P1 human or mixed:

- Conduct systematic literature searches with query/date/corpus and two reviewers.
- Domain expert validates variable mapping and mechanism-discriminating test.
- Run cheap falsification pilots for candidates scoring >=65 under the new
  high-value framework; deep fund at most two concurrently.

Stop conditions:

- No source/data/baseline means no “priority discovery.”
- Shared equation without a discriminating prediction caps research depth.
- A general-LLM or same-domain baseline that yields the same intervention removes
  the claim of distinctive transfer value.

## 5. Empirical validation surfaces audit

### 5.1 Surfaces inspected

- `/classes`: candidate class list and prediction badges.
- `/papers`: summaries of 13 phase records and draft papers.
- `/methods`: pipeline, empirical and synthetic-control narrative.
- Discoveries/whitespace cross-links into these evidence surfaces.
- Underlying dated paper files remain historical research artifacts and were not
  silently rewritten in this audit.

### 5.2 Evidence and copy conflicts

Current source still contains claims such as:

- “13 independent domains empirically validated.”
- “all predicted signals fell in their predicted bands.”
- verified badges derived from status strings in class JSON.
- papers described collectively as empirical verification/preprints.
- same code/no tuned parameter language applied across heterogeneous domains.

These conflict with the current research audit:

- some anchors are synthetic, literature-derived or single-session;
- lognormal/other alternatives are not uniformly rejected;
- neural results vary with bin/session and do not establish a single mechanism;
- stock heavy tails do not prove common SOC dynamics;
- taxonomy has internal REJECT/SPLIT/conflict decisions;
- only a subset of experiments is demonstrably timestamp-preregistered;
- external statistical/domain review and clean-room replication are incomplete.

Negative-result value is real and should remain prominent:

- Phase walk-forward NULL/no alpha;
- WTO sign reversal and observational-selection problem;
- CVE/FDNY/WSB FAIL/PARTIAL outcomes;
- synthetic nulls that validate implementation behavior.

Synthetic null success proves the code can reject selected null families. It
does not independently validate real-domain mechanism membership.

### 5.3 Experience defects

- “Universality,” “critical slowing down,” “null,” “Clauset,” “Vuong,” “BIC” and
  “universal collapse” often appear before a decision-level explanation.
- A non-expert cannot reliably distinguish candidate class, model-reviewed
  mapping, real result, synthetic control and externally replicated result.
- Verified badges compress incompatible evidence levels into one green state.
- Paper cards direct users to long drafts without an upfront result boundary,
  provenance class, strongest counter-result or next validation step.
- The useful decision is usually “what should I trust/do next?”, but pages lead
  with class count and pipeline sophistication.

Required two-layer card:

1. Decision summary: observed result, what it does not establish, next test.
2. Evidence details: dataset/source/license, sample, method, alternatives,
   preregistration status, provenance class, code/result hash and reviewer state.

### 5.4 Empirical surface score

| Dimension | Score |
|---|---:|
| Functional integrity | 12/15 |
| Experience | 6/15 |
| Copy accuracy | 4/10 |
| User/research value | 13/20 |
| Evidence quality | 10/20 |
| Data quality | 10/20 |
| **Total** | **55/100 — internal research record** |

### 5.5 Empirical rework

P0 automatic:

- Derive badges from explicit provenance/evidence state, not free-text status.
- Add claim-ledger IDs and submission/conflict status to every current paper/class
  card; fail current-public contract on unbounded verified claims.
- Generate result-boundary summaries from structured records, not LLM prose.
- Surface negative results and missing alternatives with equal prominence.
- Add raw→processed→result→figure checksum chain where artifacts exist.

P1 rerun/import/human:

- Re-download authoritative snapshots where licenses permit and freeze hashes.
- Rerun 3–4 strongest real systems with dependence-aware bootstrap, xmin/tail
  sensitivity, alternatives and leave-one-system/session-out.
- Clean-room reproduce CVE/FDNY/WSB preregistered negative/partial results.
- Complete WTO double coding/adjudication and penalized/cluster sensitivity.
- Obtain domain experts and a complex-systems statistician before any verified
  mechanism badge.

Stop conditions:

- If source/license/raw snapshot is unrecoverable, keep only a historical result.
- If mechanism alternatives remain observationally indistinguishable, use
  “scaling concordance,” not universality confirmation.
- No external review means no externally verified badge.

## 6. Cross-surface product redesign

The product should expose one evidence ladder consistently:

1. `Candidate` — retrieved or model-ranked structural connection.
2. `Source-backed` — row/claim has recoverable source and license.
3. `Analysis recorded` — real/synthetic/literature provenance and reproducible
   result exist.
4. `Falsification passed/failed` — preregistered criterion and alternatives are
   reported; failure remains visible.
5. `Externally reviewed` — named independent review and resolution are auditable.
6. `Replicated` — independent data/team reproduction exists.

“Verified” should disappear as a generic state. If retained, it must specify
what was verified: artifact checksum, source identity, analysis reproduction,
human outcome, external review or replication.

User journey:

`KB candidate → choose comparison → inspect evidence/counter-evidence → create
validation plan → run/import experiment → record PASS/FAIL/NULL → update claim`

This connects product value to the experiment-data matrix instead of generating
more ungrounded reports.

## 7. Execution matrix

| Asset | P0 automatic | P1 rerun/human | Product status until complete |
|---|---|---|---|
| KB | field/language/jargon/imbalance report; provenance sidecar schema | source/license/type audit; genuine English corpus | Candidate retrieval only |
| Discoveries | schema normalization; dedupe; score rename; validation-plan export | literature double review; expert mapping; cheap pilots | Validation queue |
| Classes | evidence-state badges; claim IDs; remove aggregate verified count | external taxonomy/domain review | Candidate taxonomy |
| Papers | boundary/provenance/negative-result cards | clean-room and external review | Internal drafts/results |
| Methods | separate implementation checks from empirical confirmation | statistician review and 3–4-system rerun | Reject-aware protocol description |
| Phase | frozen/demo/NULL invariant | optional new preregistered point-in-time study | Research preview, no alpha |
| WTO | cluster/LOO tooling already present | double coding, adjudication, penalized fit | Submission-blocked observational rejection |

## 8. 90-point exit criteria

KB reaches 90 only when every promoted row has provenance/license/language,
expert-audited type accuracy and independently measured retrieval value.

Discoveries reach 90 only when the leading candidates beat strong baselines,
produce preregistered discriminating predictions and change real interventions.

Empirical surfaces reach 90 only when all current claims are ledger-bound,
negative/conflicting results are complete, key real systems reproduce cleanly,
and external reviewers approve the mechanism boundary.

Until then, honest labels preserve the assets' value better than inflated class,
paper or verification counts.
