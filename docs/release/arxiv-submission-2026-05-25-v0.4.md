# arXiv submission instructions — 2026-05-25 (C1 v0.4)

**Status.** Local submission bundle ready at `release/arxiv/c1-unified-preprint-v0.4/`. Waiting for user to log in to arXiv and upload. v0.4 supersedes v0.3 with the §3.6 18-class taxonomy-completion increment; if v0.3 was never submitted, post v0.4 only.

**Once submitted, the announcement is not reversible.** Replacements via arXiv `replace` are fine — but the v1 fingerprint is permanent and search-indexed within 1–3 days of moderation.

---

## v0.4 vs v0.3 — what changed

| Aspect | v0.3 (2026-05-24) | v0.4 (2026-05-25) |
|---|---|---|
| Title | "five systems, one method" | **"completing the taxonomy"** |
| Validated systems | 5 (Phase 1–5 SOC core) | **45+** (5 core + 27 SOC + 18 v0.4) |
| Sections | §1–§7, §3.1–§3.5 | + **§3.6 Completing the taxonomy** (7 subsections) |
| Tables | T1 (4-system) + A1–A3 | + **T2** (18-class verdict matrix) + **A4** (repro map) |
| References | 1–45 | + **46–50** (verdict reports, C4 paper, Halford 1992, Stumpf–Porter 2012, Cohen 2000) |
| Pre-submission items | 6 | + **7** (Wave 3 plan) + **8** (taxonomy diagram) |
| KB | 4,888 entries main | 4,888 + **445 pending** (ceiling 5,333) |
| Verdicts | 4 PASS (real) + 4 REJECT (null) | + **10 PASS / 6 REJECT / 2 INCONCLUSIVE / 5 SPLIT / 1 MERGE** |
| Methodological tool | Clauset MLE + Omori | + **cross-domain scatter threshold** binary screen |

Key new finding: **descriptor-vs-mechanism binary screen.** When a candidate class's parameter spread satisfies max/min(median θ) > 10× AND spans ≥ 2 dynamical regimes, the class is empirically a descriptor (EVT, copula, fBm, Markov, damped-oscillator, delay-differential). All 6 REJECT-CONFIRMED classes in the v0.4 batch satisfy this screen.

---

## Files prepared (under `release/arxiv/c1-unified-preprint-v0.4/`)

| File | Purpose | Size |
|---|---|---|
| `main.tex` | Self-contained LaTeX source (built on v0.3 baseline) | ~2.5K lines |
| `references.bib` | BibTeX file with 50 references (refs 46–50 new in v0.4) | ~530 lines |
| `abstract.txt` | Plain ASCII abstract (1882 chars; < 1900 arXiv soft limit) | 281 words |
| `cover-letter.md` | Cover note (paste content into Submission notes field) | 503 words |
| `README.md` | Step-by-step submission guide for user | ~95 lines |
| `figures/.gitkeep` | Placeholder; v0.4 ships no figures (v0.5 deliverable) | — |

---

## Recommended arXiv categories

| Slot | Category | Rationale |
|---|---|---|
| **Primary** | `physics.soc-ph` | Same as v0.3 — universality-class methodological backbone |
| **Cross-list** | `q-fin.ST` | Phase 2 + Phase 3 + adverse-selection unraveling (econ-side, W2C.2) |
| **Cross-list** | `q-bio.NC` | Phase 4 + leaky-integrate-fire neural sub-class |
| **Cross-list (NEW in v0.4)** | `cond-mat.stat-mech` | §3.6 invokes Ornstein–Zernike Lorentzian / Anderson localization / percolation scaling — all sit in stat-mech |

Optional fallback if moderator pushes back: drop `q-fin.ST` (sibling 13-system manuscript will carry the q-fin angle independently).

---

## Cover letter copy (preview)

The full cover letter is at `release/arxiv/c1-unified-preprint-v0.4/cover-letter.md`. Key paragraphs:

> v0.4 of this preprint adds §3.6 "Completing the taxonomy" using the same frozen Clauset/Omori pipeline. New result: a mechanism-vs-descriptor binary screen (cross-domain scatter threshold). Empirical base 27 → 45+ SOC validation systems; 10 PASS / 6 REJECT / 2 INCONCLUSIVE / 5 SPLIT / 1 MERGE across 18 candidate classes.
>
> Honest disclosures: 11 of 18 v0.4 classes carry **synthetic** anchors only; a public out-of-sample Layer-4 prediction backtest returned **Sharpe = −0.23** (publicly reported in the project's null-control track). v0.4 is a methodology contribution, not a prediction-validated claim.

---

## Step-by-step upload

See `release/arxiv/c1-unified-preprint-v0.4/README.md` for the full 11-step user-facing guide. Highlights:

1. Verify `physics.soc-ph` endorsement is in place (24–48h turnaround if not).
2. Mint new Zenodo DOI for Phase-1–5 + v0.4 §3.6 deposit (optional — `[PENDING_ZENODO_DOI]` placeholder ships and can be filled via `replace` later).
3. Zip `main.tex` + `references.bib` (exclude metadata files).
4. Upload + verify server-side PDF compile (50 refs, T1/T2/A1–A4 render cleanly).
5. Paste metadata (title / abstract / categories / comments) per `README.md` step 5.
6. Paste `cover-letter.md` content into Submission notes (moderator-visible only).
7. Submit; wait 1–3 days for moderation; record arXiv ID.
8. Run placeholder replacement (`[PENDING_ARXIV_ID]` / `[PENDING_ZENODO_DOI]`) and push linked v2 via `replace` if DOI arrives later.

---

## Expected timeline

| Step | Time | Owner |
|---|---|---|
| Endorsement check (if needed) | 24–48h | arXiv community |
| Upload + server compile + form fill | 10–15 min | User |
| Moderation queue | 1–3 working days | arXiv moderators |
| arXiv ID announced | T + 1–3 d | Auto |
| Placeholder replacement + linked v2 | 30 min | Main session |
| Companion preprints (refs 41–44 + C4) | 6–8 weeks | Coordinated wave |

---

## Notes / gotchas

- **v0.4 vs v0.3 supersession.** If v0.3 has already been submitted to arXiv, post v0.4 as `replace` (gives v2 with full diff history). If v0.3 was never submitted, post v0.4 as a fresh submission and skip v0.3 entirely.
- **Tex section numbering note.** The v0.4 markdown labels the taxonomy section "§3.5 Completing the taxonomy" but the tex renumbers it as **§3.6** to avoid colliding with the existing §3.5 Phase 5 (null controls). The mapping is noted explicitly in a `%`-comment inside `main.tex`. Reviewers cross-reading against the markdown should map `tex §3.6 <-> markdown §3.5`.
- **Cross-list `cond-mat.stat-mech` is new in v0.4.** v0.3 had 2 cross-lists (q-fin + q-bio); v0.4 has 3 (adds cond-mat). Justified by §3.6's Ornstein–Zernike / Anderson / percolation content.
- **Sharpe = −0.23 disclosure is in cover letter.** Honest about the public Layer-4 prediction backtest failure; reinforces that v0.4 ships as a methodology contribution.

---

## One-line user upload step

> Log in to https://arxiv.org → New submission → upload a zip of `release/arxiv/c1-unified-preprint-v0.4/{main.tex,references.bib}` → set primary `physics.soc-ph` and cross-list `q-fin.ST` + `q-bio.NC` + `cond-mat.stat-mech` → paste `abstract.txt` into abstract field and `cover-letter.md` content into Submission notes → preview the server-built PDF → Submit → wait 1–3 days for moderation → record the arXiv ID back to the main session.
