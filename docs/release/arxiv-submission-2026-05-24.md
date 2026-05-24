# arXiv submission instructions — 2026-05-24

**Status.** Local submission bundle ready. Waiting for user to log in to arXiv and upload. **Once submitted, the announcement is not reversible** — replacements via `replace` are fine, but the v1 fingerprint is permanent and search-indexed within 1–3 days of moderation.

**Why now.** The companion Zenodo DOI should be minted first (see `docs/release/zenodo-deposit-2026-05-24.md`); arXiv abstract cites the DOI. After the DOI lands, the arXiv submission can go.

---

## Files prepared (under `release/arxiv/c1-unified-preprint-v0.3/`)

| File | Purpose |
|---|---|
| `main.tex` | Self-contained LaTeX source (pandoc-converted from C1 v0.2 markdown, manually cleaned — title block, abstract env, section structure, all Chinese characters stripped). 1262 lines. |
| `references.bib` | BibTeX file with all 45 references (numeric ordering matches v0.2). The current `main.tex` inlines references as a numbered list, so `references.bib` is shipped for downstream tooling (e.g. switching to `\cite{}` + `\bibliography{}` later, or for reference-manager import). |
| `main.pdf` | **NOT GENERATED.** LaTeX not installed on this machine. `main.pdf.TODO` is a placeholder note. Either install MacTeX locally and run `pdflatex main.tex; pdflatex main.tex`, or rely on arXiv's server-side TeXLive compile (recommended — arXiv expects to compile from source). |
| `abstract.txt` | 249-word abstract (within arXiv's 250-word soft limit). Plain ASCII (no `\` escapes). |
| `cover-letter.txt` | Cover note: why arXiv, category choices, replicability, suggested reviewers, conflict of interest, companion preprint coordination. |

---

## Recommended arXiv categories

| Slot | Category | Rationale |
|---|---|---|
| **Primary** | `physics.soc-ph` (Physics and Society) | The universality-class methodological backbone (Clauset MLE + Vuong LR + Omori) sits in statistical-physics-applied. Phase 5 nulls and Phase 1 earthquakes also fit `physics.geo-ph`, but soc-ph indexes the cross-domain framing more naturally. |
| **Cross-list** | `q-fin.ST` (Statistical Finance) | Phase 2 (S&P 500 inverse cubic) and Phase 3 (DeFi liquidation cascades) are within q-fin.ST scope. Cross-listing here gets eyes on the finance side. |
| **Cross-list** | `q-bio.NC` (Neurons and Cognition) | Phase 4 (mouse-cortex neural avalanches) is within q-bio.NC scope. Cross-listing here gets eyes on the neuroscience side. |

Optional secondary cross-lists if the moderator pushes back: `nlin.AO` (Adaptation and Self-Organizing Systems) or `physics.geo-ph` (Geophysics). The paper says "five systems, one method" — the moderator may favor reducing the cross-list count; if forced to choose, keep `physics.soc-ph` + `q-bio.NC`.

---

## Step-by-step upload

1. **Log in to arXiv.** https://arxiv.org → top-right → Login. Use an institutionally-endorsed account if available (the independent-researcher endorsement is currently in place via the project's existing arXiv author identifier).
2. **Pre-check endorsement.** First-time submitters to `q-bio.NC` or `q-fin.ST` need a primary-category endorsement. If the account is not yet endorsed for the primary category (`physics.soc-ph`), request endorsement via https://arxiv.org/auth/endorse — endorsement turnaround is usually 24–48 hours; **do not start the submission until endorsement is in hand**, otherwise the submission will be returned without moderation.
3. **Start a new submission.** https://arxiv.org/submit → "Start new submission".
4. **License.** Choose **arXiv non-exclusive license to distribute** (default). The paper itself is the author's, and the code/data licences are separate (MIT/CC-BY).
5. **Upload source.** Create a `.zip` (or `.tar.gz`) containing **only** these files from `release/arxiv/c1-unified-preprint-v0.3/`:
   - `main.tex`
   - `references.bib`
   Do **not** include `main.pdf.TODO`, `abstract.txt`, or `cover-letter.txt` — those are out-of-band metadata. arXiv will compile `main.tex` server-side.
6. **Verify the server-side build.** arXiv shows the compiled PDF preview after upload. Skim it:
   - Title block + author + abstract render correctly
   - All 45 references render correctly (numeric list — no `??` cross-refs)
   - The Phase 1–4 tables render (Tables 1–7 in the markdown body, plus Tables A1, A2 in Appendix A)
   - No obviously dangling pandoc artifacts (escaped underscores in URLs, broken `\texttt` blocks, etc.)
7. **Paste metadata into arXiv's form.**
   - **Title.** *A pipeline for cross-domain validation of self-organized criticality: five systems, one method*
   - **Author.** Wan Qihui (use the official ORCID if linked)
   - **Abstract.** Paste from `abstract.txt`. arXiv strips line breaks; that's fine.
   - **Comments.** `26 pages, Phase 1–5 synthesis; companion Zenodo deposit at doi:10.5281/zenodo.NNNNNNNN (replace before submitting); supersedes no prior preprint.`
   - **Category.** Primary `physics.soc-ph`. Cross-list `q-fin.ST`, `q-bio.NC`.
   - **MSC classification (optional).** 62-07 (Data analysis), 82C99 (Time-dependent stat. mech.), 86A15 (Seismology).
   - **DOI.** Leave blank for now (the arXiv ID itself becomes the canonical handle; a later journal DOI can be added via `replace`).
8. **Cover letter.** arXiv does not have a literal cover-letter field, but does allow free-text in the *Comments* and *Submission notes* fields. Use the *Submission notes* (visible to moderators only) for the content in `cover-letter.txt` — particularly the conflict-of-interest disclosure and the cross-listing justification. The "suggested reviewers" section is mostly useful for journal submissions, not arXiv, but leaving it in the notes does no harm.
9. **Preview the assembled record.** arXiv shows the final summary page before submission. Verify everything one more time.
10. **Submit.** arXiv places the submission in moderator queue. Moderation typically takes 1–3 working days. The submission can be edited up until the announcement; after announcement, only `replace` (with full history) is possible.

---

## After moderation succeeds (= you have an arXiv ID)

Hand the arXiv ID (e.g. `2606.01234`) back to the main session. The main session will then:

1. **Replace placeholder `XXXX.XXXXX`** in:
   - `release/arxiv/c1-unified-preprint-v0.3/references.bib` (refs `wan2026phase1`..`wan2026phase4` — the four sibling preprints — though these are separate submissions, the cross-citation pattern is the same)
   - `release/arxiv/c1-unified-preprint-v0.3/cover-letter.txt` (cross-listing notes)
   - `release/zenodo/.zenodo.json` `related_identifiers` → `arXiv:XXXX.XXXXX` entry
   - **Zenodo deposit (edit metadata after publish; the file bundle stays untouched).**
2. **Update the top-level `README.md`** to cite the arXiv URL/ID via an arXiv badge.
3. **Update `CITATION.cff`** to add the arXiv identifier under `identifiers`.
4. **Update `docs/sessions/C1-unified-preprint-draft-v0.2.md` refs 41–45** — but only if those four sibling preprints (Phase 1, 2, 3, 4 papers) are also being submitted; if not, the placeholders stay.

---

## Notes / gotchas

- **Companion preprints (Phases 1–4).** The cover letter states intent to submit them the same day. If that does NOT happen, the references to `arXiv:XXXX.XXXXX` for refs 41–44 stay as placeholders. The C1 paper should still be submitted alone — it is self-contained. **Decide before submission: solo or coordinated.**
- **`%` in LaTeX comments inside `main.tex`.** Pandoc preserves comment markers correctly; do not strip them, they're load-bearing.
- **Figures.** v0.3 has **no embedded figures** — all numbers are in inline tables. Tables A1, A2 are simple longtable conversions and should compile cleanly. If figures are added in a v0.4 replace, include them as PDF/EPS (no PNG/JPG for arXiv) and submit as a multi-file source bundle.
- **Mismatch with `dataset/v1/manifest.json`.** The Zenodo bundle is keyed to `dataset-v1` while the paper's Appendix A reproducibility table still cites the legacy `v4/lib/soc_pipeline.py` (339-line shim). The §2 provenance caveat already explains the relationship; do not change the reference numbers, just verify a domain reviewer reads §2 in v0.3.
- **Replace vs new submission.** If a reviewer (or you) catches a substantive error after submission, use arXiv's `replace` — this gives a v2 with full diff history, preferred over withdrawing. **Withdrawal is reserved for retraction-level events** (e.g. data error invalidating all numbers).

---

## One-line user upload step

> Log in to https://arxiv.org → New submission → upload a zip containing `main.tex` + `references.bib` → set primary category `physics.soc-ph` and cross-list `q-fin.ST` + `q-bio.NC` → paste `abstract.txt` into the abstract field and `cover-letter.txt` content into the submission notes (with the real Zenodo DOI substituted in) → preview the server-built PDF → Submit → wait 1–3 days for moderation → record the arXiv ID back to the main session.
