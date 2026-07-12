# Evidence-bound paper drafting product design

Date: 2026-07-12
Status: independent product/science audit; design only
Scope: generating an editable research draft from validated project artifacts

## 1. Decision

Do not build “one-click paper submission.” Build an **Evidence-bound Draft
Composer** whose promise is:

> assemble a reviewer-readable draft from an approved claim-evidence ledger,
> preserve negative results and provenance, expose every unsupported sentence,
> and return control to accountable human authors.

The product may reduce clerical synthesis, table construction, traceability and
revision work. It cannot decide authorship, certify novelty, invent citations,
resolve scientific conflicts, approve ethical compliance or submit a paper.

The primary user is a researcher who already has analyses and results but needs
an auditable first draft. “Turn any report into a paper” is out of scope: most
reports do not contain publication-grade evidence.

## 2. User value hypothesis

The valuable job is not prose generation. It is maintaining consistency across:

- claim wording and scope;
- raw/processed data and analysis provenance;
- result, table, figure and manuscript references;
- real, synthetic, literature-derived and manually-coded evidence;
- PASS, FAIL, REJECT, INCONCLUSIVE and protocol deviations;
- citations and the exact assertions they support;
- author decisions across revisions.

Success means fewer unsupported claims and faster reviewer-ready revision, not
more words or a higher “paper quality” score from another model.

## 3. Non-negotiable boundaries

The system must never:

1. Create a citation identifier, quotation, dataset fact or numerical result not
   present in an approved source artifact.
2. Convert a synthetic or literature-calibrated result into a real-data claim.
3. turn `REJECT`, `FAIL`, `NULL`, `PARTIAL` or `INCONCLUSIVE` into positive
   confirmation through omission or rhetorical reframing.
4. Hide protocol deviations, multiple-testing exposure, missing data, failed
   runs, selection effects or unresolved conflicts.
5. infer author names/order, contribution statements, conflicts of interest,
   ethics approval, consent, funding or institutional affiliation.
6. mark external review, independent replication or human coding complete based
   on model output.
7. write directly into the authoritative ledger, result files or submitted
   manuscript without a human-approved patch.
8. submit to a journal, preprint server or repository.

If evidence is missing, the output is a visible `EVIDENCE GAP`, not fluent prose.

## 4. Value >= 90 release gate

Score on evidence from a frozen evaluation set. Maximum 100.

| Dimension | Weight | Required evidence for full credit |
|---|---:|---|
| Claim fidelity | 20 | Every empirical sentence maps to approved claim IDs; no direction, scope or uncertainty drift |
| Citation truth | 15 | Every citation resolves to a supplied source and supports the attached assertion; zero invented identifiers |
| Provenance fidelity | 15 | Every number/figure/table maps to immutable artifacts, hashes, command, environment and data class |
| Negative-result preservation | 15 | Every REJECT/FAIL/NULL/INCONCLUSIVE and protocol deviation is present with equivalent prominence |
| Scientific structure | 10 | Methods/results/discussion boundaries are correct; observation, interpretation and speculation are distinct |
| Author control/editability | 10 | Sentence-level evidence panel, accept/reject patch, version diff, lock and rollback all work |
| Reproducibility | 10 | Clean-run evaluator reproduces bundle and identical draft manifest from frozen inputs |
| Usability | 5 | Target researchers produce an auditable draft faster without increased correction burden |

### Hard gates

The feature cannot score >=90 or be called production-ready unless:

- invented citation/result rate is exactly zero in adversarial evaluation;
- 100% of empirical sentences have a valid claim/evidence link;
- 100% of negative and conflicting results are preserved;
- no synthetic/real provenance confusion occurs;
- unresolved submission-blocking conflicts remain visible and block export as
  `submission-ready`;
- three independent domain reviewers reach >=0.80 precision on “sentence is
  adequately supported” and adjudicate all disagreements;
- author identity, contribution, COI, ethics and funding fields remain human
  supplied and explicitly unverified by the system;
- draft generation is deterministic given frozen content inputs, model/version
  manifest and approved author decisions;
- no external submission action exists in the product.

Before those conditions, label the output `internal research draft`.

## 5. Product flow

### Step 1 — Create a draft workspace

User selects a frozen validation/report bundle. The system shows artifact date,
hashes, data provenance classes and known conflicts before allowing generation.

### Step 2 — Evidence readiness scan

The scanner builds four queues:

- eligible claims: bounded wording, evidence and reproduction metadata present;
- blocked claims: unresolved conflict or submission gate;
- evidence gaps: missing raw/result/citation/figure links;
- author-only fields: authorship, contribution, ethics, funding and COI.

Generation stops if the user tries to promote blocked claims. It may continue
with them explicitly documented as limitations or conflicts.

### Step 3 — Human claim selection

The researcher chooses the paper question and which eligible claims belong in
scope. The system proposes a claim hierarchy but cannot silently add claims.
Each claim has one of:

- primary result;
- secondary result;
- negative result;
- limitation/conflict;
- contextual prior work;
- excluded with recorded reason.

Excluding a negative result linked to an included analysis triggers a blocking
warning and requires a written scientific justification.

### Step 4 — Outline with evidence coverage

The outline is generated before prose. Each section displays included claim IDs,
tables/figures, citations, negative results and evidence gaps. Empty sections
remain visible. The user freezes the outline revision used for drafting.

### Step 5 — Section drafting

Draft one section at a time. The model receives only approved claim packets and
verified citation snippets/metadata for that section. It returns structured
sentences with support links, not raw Markdown.

### Step 6 — Sentence-level verification

Every empirical sentence receives one status:

- `supported`;
- `partially_supported`;
- `interpretation`;
- `speculation`;
- `unsupported`;
- `conflict_blocked`.

Only `supported`, reviewed `partially_supported`, and clearly marked
interpretation/speculation can enter an export. Unsupported prose stays in a
separate repair queue.

### Step 7 — Human revision and sign-off

The editor presents manuscript text on the left and evidence/citations/diff on
the right. Authors accept patches, edit wording, lock paragraphs, request a
regeneration of only unlocked blocks, and record decisions.

### Step 8 — Export an audit bundle

Export editable Markdown/DOCX/LaTeX plus a machine-readable manifest. Export
status is one of:

- `internal-draft`;
- `reviewer-readable-do-not-submit`;
- `external-review-candidate`;
- `submission-blocked`.

There is intentionally no `submission-ready` auto-state. A human publication
checklist outside generation must make that decision.

## 6. Data model

```text
DraftWorkspace
  id, title, research_question, status
  source_bundle_hash, ledger_hash, created_by, created_at
  model_manifest, frozen_outline_revision

ClaimPacket
  claim_id, exact_wording, bounded_scope, verdict
  evidence_ids[], citation_assertion_ids[]
  provenance_class, independence_level, caveats[]
  conflict_ids[], submission_blocking

EvidenceArtifact
  evidence_id, kind, path_or_registry_id, sha256
  data_provenance, command, environment, seed
  result_locator, generated_at

CitationAssertion
  citation_assertion_id, citation_id, assertion
  source_locator, verified_metadata, verification_status
  allowed_paraphrase_scope

OutlineNode
  node_id, parent_id, section_type, title
  claim_ids[], required_negative_claim_ids[]
  evidence_gap_ids[], order, revision

DraftBlock
  block_id, node_id, revision, text
  sentence_records[], locked, author_decision

SentenceRecord
  sentence_id, text, rhetorical_role
  claim_ids[], evidence_ids[], citation_assertion_ids[]
  support_status, verifier_findings[], author_override_reason

ConflictRecord
  conflict_id, competing_claim_ids[], evidence_ids[]
  resolution, submission_blocking, external_review_required

AuthorDeclaration
  authors[], contributions[], affiliations[]
  coi, funding, ethics, consent
  supplied_by, signed_at

DraftManifest
  workspace_revision, input_hashes, model_manifest
  included/excluded claims, unresolved gaps/conflicts
  negative_result_coverage, citation_verification_summary
  author_decision_log, export_status
```

Author declarations must never be populated from repository usernames or model
inference.

## 7. API design

All mutations are revision-bound and return a new revision.

```text
POST /api/drafts
  source_bundle, research_question

POST /api/drafts/{id}/readiness-scan
  -> eligible, blocked, evidence_gaps, author_required

PUT /api/drafts/{id}/claim-selection
  base_revision, included_claims, excluded_claims_with_reason

POST /api/drafts/{id}/outline
  base_revision, section_policy

POST /api/drafts/{id}/sections/{node_id}/generate
  base_revision, approved_claim_ids
  -> structured DraftBlock; never raw authoritative-file write

POST /api/drafts/{id}/blocks/{block_id}/verify
  base_revision
  -> sentence-level support findings

PATCH /api/drafts/{id}/blocks/{block_id}
  base_revision, text_patch, lock_state, author_decision

POST /api/drafts/{id}/conflicts/{conflict_id}/decision
  base_revision, decision, rationale
  -> cannot clear external-review-required automatically

POST /api/drafts/{id}/export
  base_revision, format, requested_status
  -> bundle or fail-closed gate errors
```

API guardrails:

- strict schemas and allowlists for all model output;
- content hashes checked immediately before generation and export;
- no citation accepted without a verified registry/source record;
- generated numeric tokens must match an evidence locator or be rejected;
- retries are idempotent and preserve the same evidence context;
- author overrides are logged, never silently treated as machine verification;
- export cannot suppress linked negative results or unresolved conflicts.

## 8. UI design

Use a restrained document editor, not a chat-first interface.

### Workspace header

- draft status and source freeze date;
- evidence coverage percentage;
- unresolved claims/citations/conflicts count;
- current revision and model manifest;
- export button disabled with exact blocking reasons.

### Left rail

- outline and section completeness;
- claim inventory grouped by positive/negative/conflict/gap;
- author-only checklist;
- revision history.

### Center editor

- normal editable manuscript;
- sentence underline colors encode support status;
- lock block, accept patch, reject patch and restore revision;
- no global “make it more convincing” action.

### Right evidence panel

- exact claim and bounded scope;
- result/table/figure locator and hash;
- provenance class badge: real, synthetic, literature-derived,
  manually-coded or model-generated;
- citation assertion and source locator;
- caveats, conflicting evidence and protocol deviations;
- why this sentence is or is not supported.

### Negative-result review

A dedicated screen compares all negative/conflicting claims in the source bundle
against their manuscript placement and prominence. Missing items block export.

## 9. Citation truth protocol

Citation ingestion and scientific drafting must be separate operations.

1. Accept only sources already supplied by the user or resolved through an
   authoritative bibliographic service.
2. Store DOI/arXiv/PMID/title/authors/year plus the source response and access
   timestamp; identifier metadata agreement is required.
3. Link a citation to a specific assertion and source locator, not merely a
   paragraph bibliography.
4. If full text is unavailable, mark the verification limit. Metadata alone
   cannot verify a scientific assertion.
5. Never generate a quotation unless the exact source text is present and the
   locator is recorded.
6. Detect retracted/corrected status when authoritative metadata provides it;
   do not infer absence of retraction.
7. Unverified references remain placeholders labelled `SOURCE REQUIRED`, never
   formatted as finished citations.

## 10. Minimum implementable P1

P1 should support one bounded path: claim-evidence ledger → editable Methods,
Results and Limitations draft.

Included:

1. Read-only import of the current claim-evidence ledger and evidence hashes.
2. Readiness scan and hard-blocked claim list.
3. Human claim selection and outline freeze.
4. Section-by-section structured draft generation.
5. Sentence-to-claim/evidence links and deterministic numeric-token validator.
6. Negative-result coverage gate.
7. Editable Markdown view with block lock/diff/rollback.
8. Export Markdown plus DraftManifest, always labelled
   `reviewer-readable-do-not-submit` or `submission-blocked`.
9. Adversarial fixtures covering invented DOI, altered number, synthetic→real,
   omitted REJECT, unresolved conflict and false external-review status.

Excluded from P1:

- automated literature discovery or full-text interpretation;
- DOCX/LaTeX formatting polish;
- journal templates;
- coauthor collaboration;
- authorship/contribution recommendation;
- submission integrations;
- “novelty score,” acceptance prediction or reviewer simulation;
- automatic conflict resolution.

P1 success criteria:

- zero invented citations/numbers across the adversarial frozen set;
- 100% empirical sentence linkage;
- 100% negative-result/conflict coverage;
- a researcher can repair or reject every generated block;
- median time to an auditable three-section draft is reduced by >=40% versus
  manual assembly, without increasing unsupported-sentence correction time;
- at least five researchers complete the workflow and independently confirm the
  audit manifest matches the manuscript.

## 11. Evaluation plan

Build a frozen set containing:

- supported positive results;
- real REJECT/NULL/PARTIAL results;
- conflicting taxonomy and empirical verdicts;
- synthetic and real results with similar numbers;
- stale hashes and superseded files;
- plausible but nonexistent citations;
- citations whose metadata exists but does not support the assertion;
- author-only fields intentionally absent.

Compare Evidence-bound Draft Composer against:

- manual assembly;
- unconstrained general-LLM drafting;
- template-only document generation.

Primary outcomes are unsupported empirical sentence rate, invented citation
rate, negative-result omission rate and researcher correction time. Fluency,
word count and reviewer-style scores are secondary and cannot compensate for a
truthfulness failure.

## 12. Final product boundary

This feature is worth building only as a provenance-preserving editor around
already validated research. It should not become a funnel that turns product
reports into academic claims. The strongest product behavior is refusal:

- refuse when a report has no publication-grade evidence;
- show gaps instead of filling them;
- preserve negative results;
- block conflicted claims;
- make every human override auditable;
- stop before authorship and submission.

If users primarily want persuasive prose or instant submission, this project
should not serve that demand.
