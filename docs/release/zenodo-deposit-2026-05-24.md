# Zenodo deposit instructions — 2026-05-24

**Status.** Local bundle ready. Waiting for user (or designated co-author) to log in and upload. The DOI is **permanent and cannot be retracted** once minted, so confirm metadata before clicking Publish.

**Why now.** W7-A roadmap §7 identifies Zenodo DOI as the highest-leverage 30-day academic action — the arXiv preprint and the GitHub README both need a citable DOI to reference; minting the DOI before arXiv submission unblocks both.

---

## Files prepared (under `release/zenodo/`)

| File | Purpose |
|---|---|
| `dataset-v1.tar.gz` | The bundle to upload (44 MB compressed, 521 files, 206 MB uncompressed) |
| `.zenodo.json` | Metadata in Zenodo's schema — used to fill the upload form |
| `README.md` | Renders as the Zenodo deposit page description |
| `manifest.txt` | SHA-256 of bundle + per-file SHA-256 of every file inside |

Bundle SHA-256:

```
8391a305bf0084bc7624b2725a0b7b24f17153b53236124c65c96fea8c7c9ee9
```

(also recorded in `manifest.txt`; verify with `shasum -a 256 release/zenodo/dataset-v1.tar.gz`)

---

## Step-by-step upload

1. **Log in to Zenodo.** https://zenodo.org → top-right → "Log in" with GitHub or ORCID (use the account you intend to mint the DOI under — the DOI's creator field cannot be changed later).
2. **Pre-check ORCID.** `.zenodo.json` carries an `orcid: 0000-0000-0000-0000` placeholder. Update it with the real ORCID (https://orcid.org/my-orcid) before publishing — it is rendered on the deposit page and indexed by DataCite.
3. **New upload.** Top-right → "New upload" (or https://zenodo.org/uploads/new).
4. **Drag the bundle.** Drag `release/zenodo/dataset-v1.tar.gz` into the upload area. Wait for the green check.
5. **Fill the form using `.zenodo.json`** (most modern Zenodo accepts the JSON directly via "Import from .zenodo.json" if you also drop that file in; otherwise copy fields manually):
   - **Resource type.** Dataset.
   - **Title.** *Structural Isomorphism: Cross-domain SOC validation dataset and pipeline (v1.0)*
   - **Authors.** Wan, Qihui — affiliation "Independent Researcher, Structural Isomorphism Project" — ORCID (real one).
   - **Description.** Paste from `.zenodo.json` `description` field (HTML allowed; do not strip the `<p>` and `<a>` tags).
   - **License.** MIT.
   - **Keywords.** Copy from `.zenodo.json` `keywords`.
   - **Related identifiers.** GitHub repo URL (isSupplementTo), arXiv ID (isSupplementTo — leave blank if not yet submitted; can be edited as a *new version* after arXiv lands), PyPI soc-pipeline URL (isDerivedFrom).
   - **Communities.** Optionally request inclusion in `complex-systems`.
   - **Notes.** Paste from `.zenodo.json` `notes`.
6. **Save as draft.** Click *Save* (not *Publish*) — this creates a draft DOI you can preview.
7. **Final sanity check.** Open the preview page, verify (a) bundle downloads OK, (b) README.md renders inside the deposit page (Zenodo auto-renders top-level README of a tarball under "Description" only if you also paste it; you can paste `release/zenodo/README.md` into the description field as well for redundancy), (c) author + ORCID correct, (d) related identifiers point to the right URLs.
8. **Publish.** Click *Publish*. **This is irreversible.** Zenodo will mint a DOI of the form `10.5281/zenodo.NNNNNNNN`.

---

## After getting the DOI

Hand the DOI back to the main session, which will:

1. **Replace placeholder `10.5281/zenodo.19547879`** in `docs/sessions/C1-unified-preprint-draft-v0.2.md`:
   - line 322 (`Structural Isomorphism Project. V1–V4 snapshot: …`)
   - line 350 (Appendix A "Project Zenodo deposit")
   - the META block's `[待核]` marker at top
2. **Replace placeholder in `release/zenodo/.zenodo.json` `notes` field** if minting a second version later.
3. **Replace placeholder in `release/zenodo/README.md` BibTeX entries** (`10.5281/zenodo.XXXXXXX` x2).
4. **Update `release/arxiv/c1-unified-preprint-v0.3/main.tex`** (and `references.bib`) — DOI goes into Appendix A "Data availability" once the arXiv tex source is built.
5. **Update top-level repository `README.md`** to cite the Zenodo DOI badge: `[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.NNNNNNNN.svg)](https://doi.org/10.5281/zenodo.NNNNNNNN)`.
6. **Update `CITATION.cff`** to add the Zenodo DOI under `identifiers`.

The arXiv submission step (`docs/release/arxiv-submission-2026-05-24.md`) waits on this — the abstract cites the Zenodo DOI explicitly.

---

## Notes / gotchas

- **Bundle versioning.** This is `dataset-v1.0`. If the dataset evolves, mint a *new version* on the same Zenodo concept-DOI (Zenodo's "New version" button), not a brand-new DOI. The concept-DOI always resolves to the latest version; the per-version DOI is what papers cite.
- **Per-system data licences.** The bundle is CC-BY-4.0 for derived/processed data, but upstream raw catalogues have their own licences (USGS public domain, Yahoo Finance ToS, DANDI CC-BY-4.0, NIFC public domain, etc.). The Zenodo deposit description should mention this; per-system folders in the bundle ideally carry a `LICENSE.txt` or `data-license-notes.md`. **Action item before publish.** Spot-check that every system folder makes provenance clear; if any folder is unattributed, decide before publish.
- **File size headroom.** Zenodo single-file limit is 50 GB; we are at 44 MB. Plenty of room to add a `report.pdf` or `figures.tar.gz` later as supplementary files if useful.
- **Editing after publish.** Title / description / authors / keywords / related identifiers can be edited on a published deposit. **The files cannot.** If a bundle bug is found post-publish, mint a new version.

---

## One-line user upload step

> Log in to https://zenodo.org → New upload → drag `release/zenodo/dataset-v1.tar.gz` → import metadata from `release/zenodo/.zenodo.json` (paste into the form) → set real ORCID → Save draft → review preview → Publish → record the DOI back to the main session.
