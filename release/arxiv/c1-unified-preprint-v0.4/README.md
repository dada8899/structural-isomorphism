# arXiv v0.4 Submission — Step-by-step (5 min)

This directory contains the C1 unified preprint v0.4 submission bundle.

**Contents.**

| File | Purpose |
|------|---------|
| `main.tex` | Self-contained LaTeX source (built on v0.3 baseline + v0.4 §3.6 increment) |
| `references.bib` | BibTeX (50 entries; refs 46–50 new in v0.4) |
| `abstract.txt` | Plain ASCII abstract (1882 chars; < 1900 arXiv limit) |
| `cover-letter.md` | Cover note for arXiv moderators (paste content into Submission notes) |
| `figures/` | Figure assets (empty placeholder; v0.5 will add `taxonomy-v0.4.png`) |
| `README.md` | This file |

---

## Prerequisites

- **arXiv account in good standing.** First-time submitters to `q-bio.NC` / `q-fin.ST` may need endorsement; verify via https://arxiv.org/auth/endorse before starting.
- **Zenodo DOI**: status PENDING — if you want the cover letter to cite a live DOI, mint the new Phase-1–5 + v0.4 §3.6 Zenodo deposit first; otherwise the `[PENDING_ZENODO_DOI]` placeholder ships as-is and can be filled later via arXiv `replace`.
- **No LaTeX install needed.** arXiv compiles `main.tex` server-side under TeXLive.

---

## Submission steps

1. **Log in** to https://arxiv.org → top right → Login.
2. **Start new submission** → https://arxiv.org/submit → choose "Start new submission" → **License**: arXiv non-exclusive license to distribute (default).
3. **Upload source.** Create a `.zip` (or `.tar.gz`) containing **only** these files from this directory:
   - `main.tex`
   - `references.bib`
   - (figures are not included in v0.4; v0.5 will add `figures/taxonomy-v0.4.png`)
   Do **not** include `abstract.txt`, `cover-letter.md`, `README.md` — those are out-of-band metadata.
4. **Verify server-side build.** arXiv shows the compiled PDF after upload. Skim it:
   - Title block, author block, abstract render correctly
   - 50 references render with no `??` placeholders
   - Tables 1, 2, A1, A2, A3, A4 render cleanly
   - No dangling pandoc artifacts (escaped underscores in URLs, broken `\texttt` blocks)
5. **Paste metadata into arXiv's form.**
   - **Title:** *A pipeline for cross-domain validation of self-organized criticality: completing the taxonomy*
   - **Author:** Wan Qinghui (or use ORCID if linked)
   - **Abstract:** Paste content of `abstract.txt` (arXiv strips line breaks; that's fine)
   - **Comments:** `v0.4 supersedes v0.3 with full 18-class taxonomy closure; companion package: github.com/dada8899/structural-isomorphism; companion Zenodo deposit DOI:[PENDING_ZENODO_DOI]`
   - **Primary category:** `physics.soc-ph`
   - **Cross-list:** `q-fin.ST`, `q-bio.NC`, `cond-mat.stat-mech`
   - **MSC classification (optional):** 62-07 (Data analysis), 82C99 (Time-dependent stat. mech.), 86A15 (Seismology).
   - **DOI:** leave blank (arXiv ID becomes canonical handle; journal DOI can be added later via `replace`)
6. **Cover letter** → arXiv has no literal cover-letter field. Paste content of `cover-letter.md` into the **Submission notes** field (visible to moderators only). Particularly important: the conflict-of-interest disclosure and the cross-listing justification.
7. **Preview the assembled record** → arXiv shows a final summary page before submission.
8. **Submit.** Submission goes into moderator queue. Moderation typically 1–3 working days.
9. **After moderation succeeds** → you have an arXiv ID (format `YYMM.NNNNN`). Record it back to the main session.
10. **Replace `[PENDING_ARXIV_ID]`** placeholders in all files by running:

    ```bash
    bash scripts/replace_arxiv_placeholder.sh <new-arxiv-id>
    ```

    (script not yet built; manually grep+sed equivalent works fine.)
11. **Replace `[PENDING_ZENODO_DOI]`** when the new Zenodo deposit is minted (same pattern; both placeholders are independent).

---

## After arXiv ID is in hand

1. Update top-level `README.md` with arXiv badge.
2. Update `CITATION.cff` to add arXiv identifier under `identifiers`.
3. Update Zenodo deposit metadata (file bundle stays untouched).
4. Update `docs/sessions/C1-unified-preprint-draft-v0.4.md` to reflect v1 (this submission's first announced version).
5. If publishing the 4 companion phase preprints (refs 41–44) in coordinated waves, link their arXiv IDs into v0.4's `references.bib` and use arXiv `replace` to push the linked v2.

---

## Notes / gotchas

- **No figures in v0.4.** The `figures/` directory is a placeholder; the v0.5 taxonomy-v0.4 PNG (per §3.6.7 textual spec) is the explicit v0.5 deliverable (Pre-submission checklist item 8).
- **% in LaTeX comments inside `main.tex`** are load-bearing — do not strip them.
- **arxiv.org accepts PDF/EPS figures only** (no PNG/JPG). When v0.5 figures land, embed as PDF/EPS or compile through `\includegraphics` with TeXLive's PNG support.
- **Replace vs new submission.** Substantive errors caught after submission → use arXiv `replace` (gives v2 with full diff history). Withdrawal is reserved for retraction-level events.
- **`physics.soc-ph` requires endorsement** for first-time submitters. Endorsement turnaround typically 24–48 hours; do not start submission until endorsement is in hand.

---

## One-line user upload step

> Log in to https://arxiv.org → New submission → upload a zip of `main.tex` + `references.bib` → set primary category `physics.soc-ph` and cross-list `q-fin.ST` + `q-bio.NC` + `cond-mat.stat-mech` → paste `abstract.txt` into the abstract field and `cover-letter.md` content into the Submission notes (with real Zenodo DOI substituted if minted) → preview the server-built PDF → Submit → wait 1–3 days for moderation → record the arXiv ID back to the main session.
