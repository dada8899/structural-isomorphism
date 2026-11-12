# Triple-submission plan — C1 v0.4 + C4 v0.4 + methodology short-note

> Date: 2026-05-25 (SESSION-25)
> Phase-2 sub-agent deliverable. Author retains the strategic decision to actually run this; this plan is the prepared materials, not a recommendation.

## Pros and cons (not a recommendation — author decides)

### Pro

- **Three arXiv IDs at once.** Triple the citation surface; each preprint discoverable in its own category cluster.
- **Cross-citation network.** Each preprint cross-cites the other two; the bundle reads as a coherent program rather than as three disconnected pieces.
- **Avoids the 4-6 week wait for v0.4 reviewer feedback** that the alternative (sequential C1 → wait → C4 → wait → methodology note) would require.
- **All three are *already* drafted and pre-registered** at HEAD `14a73c4`. The marginal effort to submit three vs one is moderator-form-filling time (~15 min × 3), not new research.
- **Category differentiation supports discovery.** C1 primary `physics.soc-ph`; C4 primary `cs.LG`; methodology note primary `stat.ME`. Each preprint anchors a different arXiv community.

### Con

- **Reviewer perception of fragmentation.** Three preprints from the same author on the same day may read as artificial split rather than as a coherent program. Mitigation: cross-cite explicitly in each preprint's comments field; the relationship is documented in the moderator-notes blocks of each metadata.yml.
- **Methodology note may be too thin.** At 4295 words / ~5 typeset pages, the note is below the threshold some reviewers (and some moderators) consider standalone-publishable. The note explicitly says it documents pre-registration discipline, not new empirical results.
- **C4 has not been reviewer-vetted as standalone.** C4 originated as the sibling of C1; the v0.4 amendment in this session (§4.3.2 Hawkes-vs-SOC-Gumbel disambiguation, committed `08c5ee4`) is fresh. Submitting C4 without a reviewer pass is faster but accepts more risk of a moderator query.
- **Concurrent submission moderator flag.** Three submissions in a single day from the same author *may* trip moderator suspicion of duplicate submission. The recommended order below spreads the submissions across 2–3 hours to mitigate.

## Recommended submission order (anchor → empirical-companion → methods)

1. **C1 first.** C1 is the most complete and the most likely to clear moderation cleanly (the bundle has been ready since SESSION-23). C1's arXiv ID becomes the anchor for the other two.
2. **C4 second** (≥ 1 hour after C1). C4's metadata.yml `comments` field needs the C1 arXiv ID substituted in (currently `[PENDING_C1_ARXIV_ID]`). Submit C4 only *after* C1 ID is in hand; do the substitution at submission time.
3. **Methodology note third** (≥ 1 hour after C4). The note's `main.md` §7 references [1] and [22] need both C1 and C4 arXiv IDs substituted in. The note is short and the moderation queue tends to clear short notes faster than long preprints.

Rationale: spreading the three submissions across ≥ 2 hours and ≥ 3 separate session-windows reduces the chance a moderator treats them as a bulk-submission anomaly. Each later submission cross-cites the earlier ones, which is normal-looking provenance rather than suspicious replication.

## User checklist per submission

Each of the three submissions follows roughly the same arXiv UI flow. Per-submission specifics are in each bundle's README. The common checklist (≈ 15 min per submission):

- [ ] Log in to arXiv (https://arxiv.org/login) and verify account in good standing.
- [ ] Open "New submission" → arXiv non-exclusive licence.
- [ ] Upload the .zip / .tar.gz of source files (see bundle README for the exact file list — each bundle ships with a `README.md` or `00_README.txt` listing the upload-included vs out-of-band files).
- [ ] Wait for arXiv's server-side compile (≈ 1–3 minutes). Download and skim the PDF.
- [ ] Paste form metadata from the bundle's `metadata.yml` (title, authors, abstract, primary category, cross-list, MSC, comments).
- [ ] Paste moderator-notes from `metadata.yml` `moderator_notes:` into the Submission notes field.
- [ ] Preview → Submit. arXiv assigns a submission ID; the actual arXiv ID is released after moderation (1–3 working days for first-time submitters, ~24 h for known authors).
- [ ] Record the submission ID and the arXiv ID once issued; substitute into the *next* preprint's metadata before submitting it.

## Per-preprint specifics

### C1 v0.4 — empirical companion
- Bundle location: `release/arxiv/c1-unified-preprint-v0.4/`
- Primary category: `physics.soc-ph` (verify endorsement *before* starting — fall back to `physics.data-an` if not endorsed)
- Files to upload: `main.tex` + `references.bib` (no figures in v0.4)
- Pre-submission status: 7-file bundle present and verified since SESSION-23
- Detailed walk-through: in-bundle `README.md` (11-step)

### C4 v0.4 — methodology companion (reject-aware pipeline)
- Bundle location: `paper/v0.5-draft/sibling-bundle/c4-arxiv-bundle/`
- Primary category: `cs.LG`
- Files to upload: `main.tex` + `references.bib` + `figures/fig_3layer_pipeline.pdf`
- Pre-submission status: built this session by pandoc + hand-edited title block
- Detailed walk-through: in-bundle `00_README.txt`
- **Pre-submission edit required**: replace `[PENDING_C1_ARXIV_ID]` in `metadata.yml` `comments:` field with the C1 arXiv ID earned earlier in the day.

### Methodology short-note
- Bundle location: `paper/v0.5-draft/sibling-bundle/methodology-short-note/`
- Primary category: `stat.ME`
- Files to upload: build `main.tex` from `main.md` at submission time via pandoc (one-line command in `metadata.yml` `build_instruction:`), then upload the resulting `main.tex` as a single self-contained file.
- Pre-submission status: markdown ready, 4295 words, no figures, 22-reference inline bibliography
- **Pre-submission edits required**: replace `[PENDING_C1_ARXIV_ID]` and `[PENDING_C4_ARXIV_ID]` in `main.md` §7 (references [1] and [22]) with the actual arXiv IDs earned earlier in the day.

## Time estimate

| Phase | Duration | Notes |
|---|---|---|
| Pre-submission endorsement check (C1) | 24–48 h (background) | One-time; do early in the week if not already endorsed |
| C1 submission (active user time) | ~15 min | Per in-bundle README §"One-line user upload step" |
| C1 moderation wait | 1–3 working days | After moderation, C1 arXiv ID is issued |
| C1 ID substitution into C4 metadata | ~5 min | sed-style replace in metadata.yml `comments:` |
| C4 submission | ~15 min | Per c4-arxiv-bundle/00_README.txt |
| C4 moderation wait | 1–3 working days | Often faster for known author |
| C4 ID substitution into methodology note | ~5 min | sed-style replace in main.md §7 [22] |
| Methodology note pandoc build | ~2 min | One-line command from metadata.yml `build_instruction:` |
| Methodology note submission | ~15 min | Single .tex upload |
| Methodology moderation wait | 1–3 working days | Short note → typically fastest |

**Critical-path duration**: ~7–10 calendar days if submissions are sequenced (C1 submit → wait → C4 submit → wait → methods submit). **All-three-same-day duration**: ~2–3 hours of active user time, plus the moderation waits in parallel (each moderator decision is independent). The recommended order anchors C1 first to get the ID for cross-citation, but C4 and methods do *not* technically require the C1 ID — `[PENDING_C1_ARXIV_ID]` placeholders can ship and be replaced via arXiv `replace` later.

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | arXiv endorsement delay on `physics.soc-ph` (C1) | Medium | Blocks C1; cascades to C4 + methods (cross-citations broken) | Fall back to `physics.data-an` primary for C1; same cross-list set |
| R2 | Methodology short-note rejected as too thin (< 5 pages) | Medium | Loses the third arm; C1 + C4 still posted | Reframe as "Companion methods note" in the comments field; cross-cite C1 + C4 prominently. If outright rejected, fold into v0.5 main preprint |
| R3 | Moderator flags 3 same-day submissions as duplicate | Low-medium | Submissions held in queue for clarification | Spread the three across ≥ 2 hours; cross-cite explicitly; respond promptly to moderator query with the documented relationship in metadata.yml `moderator_notes:` |
| R4 | C4 pandoc-built LaTeX has render artefact | Low | C4 server-build fails or PDF is malformed | Skim the arXiv server-built PDF carefully; if needed, regenerate `main.tex` from source markdown with the published pandoc command in `00_README.txt` |
| R5 | C1 + C4 + methods cross-citation creates a citation loop visible to bibliometric scoring | Low | Citation-count inflation visible in Google Scholar | Disclosed in moderator notes; the cross-citation is *bibliographically warranted* (each preprint genuinely references the others) and is normal for companion preprints |
| R6 | User runs the three submissions in the wrong order | Low | `[PENDING_*]` placeholders ship; arXiv `replace` fixes | Recommend the order in this plan; placeholders are explicit and substitutable later |
| R7 | C4 main.tex was edited to inject title/author block; pandoc round-trip from updated markdown would lose the edit | Low | If a re-pandoc is needed, the title block has to be re-applied | Document the title block injection in `00_README.txt` so a future re-pandoc operator knows to re-apply |

## Decision points the user should think about *before* submitting

1. **Submit C1 alone first, wait 4-6 weeks, then C4 + methods?** This is the conservative alternative to the all-three strategy. Pro: lets reviewer feedback shape C4 + methods; reduces fragmentation perception. Con: 4-6 week delay; methods note may be obsoleted by v0.5 full paper before it's submitted.
2. **Skip the methods note entirely; fold into v0.5 main paper?** The three patterns are documented in v0.5 main paper §§3.6.5/6/7 already. The standalone note adds discoverability + cross-cite-ability but is partially redundant. If reviewer thinness risk (R2) is decisive, this is the fallback.
3. **Reframe the methods note as a software/code paper?** *Journal of Statistical Software* or similar would accept a code-release + pre-registration paper format. The pre-registrations + the methodology checklist + the verdict ladders are reusable assets; a software-paper framing may suit reviewer expectations better than a methods-only framing.

The plan above assumes the all-three-at-once strategy. The conservative alternative (1) is a strict subset of this plan — C1 first, the rest paused.

## What this plan does NOT cover

- **Journal submission strategy.** This plan is arXiv-only. The C4 paper targets *Patterns* (Cell Press) as the primary journal venue (§8 of C4); the methods note has no firm journal target yet and may suit *Journal of Statistical Software* or a *Patterns* methods slot. Journal selection is downstream of arXiv posting and not in scope here.
- **Zenodo deposit minting.** Each preprint references a `[PENDING_ZENODO_DOI]` placeholder. Zenodo minting is independent of arXiv submission; the placeholder can ship and be filled later via arXiv `replace`. If you want a live DOI in the cover letter / comments, mint Zenodo *before* arXiv.
- **Press / outreach / Twitter announcement.** This is a separate decision; the project's README and CITATION.cff are the persistent records.

End of triple-submission plan.
