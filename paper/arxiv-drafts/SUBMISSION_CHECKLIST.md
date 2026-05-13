# arXiv Submission Checklist

**Generated:** 2026-05-13 by W3-E subagent (structural-isomorphism Phase v4 / Session #3, agent `w3e-arxiv-drafts`).

**Scope.** Markdown drafts only. No LaTeX, no actual upload. The four drafts in `2026-05-13/` are first-pass arXiv-format reorganizations of existing site papers. Before any real arXiv submission, every item in this checklist must be addressed.

---

## Drafts produced

| # | File | Phase | Topic | Word count (approx.) |
|---|------|-------|-------|----------------------|
| 01 | `2026-05-13/01_earthquake_soc.md` | 1 | USGS earthquake SOC (Gutenberg-Richter + Omori-Utsu) | ~5,200 |
| 02 | `2026-05-13/02_stockmarket_inverse_cubic.md` | 2 | S&P 500 inverse-cubic + daily-scale Omori | ~4,600 |
| 03 | `2026-05-13/03_defi_cross_protocol.md` | 3 | DeFi liquidations across Aave/Compound/MakerDAO | ~5,400 |
| 04 | `2026-05-13/04_neural_avalanches.md` | 4 | Mouse ALM neural avalanches (task-active sub-critical) | ~4,900 |

All four follow the same arXiv-style structure: Authors/Affiliation → Abstract → Keywords → Introduction → Data & Methods → Results → Discussion → Conclusion → Data Availability → Code Availability → Acknowledgments → References. Each has 30-35 references covering both the primary scientific topic and the cross-paper Structural Isomorphism context.

---

## Critical pre-submission TODOs

### 1. LaTeX conversion

The arXiv main-stream submission format is LaTeX. The Markdown drafts must be converted before submission:

- [ ] Convert `01_earthquake_soc.md` → `.tex` (suggested class: `revtex4-2` for PRE/SIAM-style; or `article` + `amsmath` for general).
- [ ] Convert `02_stockmarket_inverse_cubic.md` → `.tex` (same class).
- [ ] Convert `03_defi_cross_protocol.md` → `.tex` (same class).
- [ ] Convert `04_neural_avalanches.md` → `.tex` (same class).
- [ ] Build with all bibliographies (recommend `.bbl` files; numerical reference style matches current Markdown drafts).
- [ ] Validate that all math renders correctly under `pdflatex` (check `\langle ... \rangle`, `\mathrm{}`, table cells with math).
- [ ] Run `arxiv-sanity-check` or equivalent to confirm size limits and font embedding.

### 2. Authors and affiliations — placeholder removal

Every draft currently uses:

```
Wan Qinghui (万庆徽)^1,*
^1 Independent Research, Structural Isomorphism Project
*Correspondence: dada8899@users.noreply.github.com (placeholder)
```

Before submission decide:

- [ ] **Sole author vs. co-authors.** If co-authors (e.g., for the neural paper consider domain co-authors from the Beggs-Plenz or Priesemann groups) → reach out, draft co-author invitation emails, get formal commitment.
- [ ] **Real affiliation.** "Independent Research" is technically fine for arXiv but may matter for journal preference downstream. If affiliated with any institution (university, company R&D division), state it.
- [ ] **Real correspondence email.** GitHub no-reply is not appropriate for an arXiv submission — needs a real, monitored address.
- [ ] **ORCID.** Register and include if not already.
- [ ] **Chinese-English name consistency.** Confirm preferred Pinyin form ("Wan Qinghui" vs. "Qinghui Wan" vs. "Q. Wan" — arXiv typically prefers `Q. Wan` for the inline citation form).

### 3. Co-author invitation decisions (D-struct-1)

The Structural Isomorphism project as a whole is currently single-author. Two reasonable models for the Phase 1-4 papers:

- **Solo-author route.** Faster, no coordination cost, fits "Independent Research" framing. Risk: reviewers in domain-specific journals (e.g., *Bull. Seismol. Soc. Am.* for Phase 1) may push back on a non-affiliated solo submission.
- **Domain co-author route.** Invite one credible domain expert per paper (e.g., Beggs/Plenz lab member for Phase 4; an econophysics group for Phase 2). Slower but much stronger credibility. Risk: timeline cost, IP-of-the-pipeline disclosure.

- [ ] **Decision needed: D-struct-1.** Pick the route per paper. Default: solo for Phase 1-3 (where the pipeline-validation framing carries the paper), invite for Phase 4 (where domain knowledge of brain-state classification adds substantively).

### 4. Target journal / preprint server selection

- [ ] **arXiv categories per paper:**
  - Phase 1 (earthquake): primary `physics.geo-ph`, secondary `stat.AP`, `cond-mat.stat-mech`.
  - Phase 2 (stocks): primary `q-fin.ST`, secondary `cond-mat.stat-mech`, `physics.soc-ph`.
  - Phase 3 (DeFi): primary `q-fin.GN`, secondary `cs.CR`, `physics.soc-ph`.
  - Phase 4 (neural): primary `q-bio.NC`, secondary `cond-mat.stat-mech`, `physics.bio-ph`.
- [ ] **Optional formal-journal targets** (post-arXiv):
  - Phase 1: *Bull. Seismol. Soc. Am.* / *Geophys. J. Int.* / *J. Geophys. Res. Solid Earth*.
  - Phase 2: *Phys. Rev. E* / *Eur. Phys. J. B* / *Quant. Finance*.
  - Phase 3: *J. Financ. Cryptogr.* (new) / *Phys. Rev. E* / arXiv-only.
  - Phase 4: *J. Neurosci.* / *Phys. Rev. E* / *Neural Comput.*.
- [ ] **Cross-paper bundling decision.** Consider submitting as a coordinated 4-paper series with mutual cross-citations finalized at the same time (currently drafts cite each other by Phase 1-4 numbers and "this work" rather than by arXiv ID).

### 5. DOI and identifier allocation

- [ ] **Zenodo deposit per paper.** The project-level Zenodo deposit (10.5281/zenodo.19547879) covers the V1-V4 snapshot. Each Phase paper should get its own Zenodo DOI for the analysis code + data subset, cross-referenced from the paper's Data Availability section.
- [ ] **GitHub release per paper.** Tag the analysis code at the exact commit used. Suggested tags: `v4/phase1-earthquake-2026-04-15`, `v4/phase2-stockmarket-2026-04-15`, `v4/phase3-defi-2026-04-16`, `v4/phase4-neural-2026-04-16`.
- [ ] **arXiv IDs.** Once preprints go up, retrofit Markdown drafts (and any LaTeX versions) with the actual arXiv IDs for inter-paper cross-references.

### 6. AI assistance disclosure language

All four drafts include the same Acknowledgments paragraph crediting Anthropic Claude Opus 4.x (via Claude Code) and DeepSeek for code drafting / prose polishing / literature triangulation, with the standard disclaimer that all decisions and claims are the author's responsibility. This matches current arXiv and journal best practice (e.g., *Nature* policy 2023+, *Science* policy 2024+). Re-review the exact disclosure language against target journal policy before submission. Some journals (e.g., *Cell*) require slightly different phrasing.

### 7. Figures

The Markdown drafts contain **no figures** — all numerical results are in tables. Before formal submission, each paper should include at minimum:

- [ ] **Phase 1**: (a) Gutenberg-Richter log-N vs. M plot with Aki MLE fit; (b) Omori-Utsu stacked aftershock rate vs. lag with log-linear fit overlay; (c) Clauset CCDF on seismic energies with $x_\mathrm{min}$ marker.
- [ ] **Phase 2**: (a) CCDF of $|r|$ with power-law fit overlay; (b) post-shock excess $\langle |r| \rangle$ vs. lag with Omori fit; (c) optional volatility regime shading.
- [ ] **Phase 3**: (a) per-protocol CCDF of liquidation sizes (3 panels); (b) per-protocol Omori fits at 1-hour aggregation; (c) summary scatter of $\alpha$ vs. $p$ for the three protocols + Phase 1 + Phase 2 anchors.
- [ ] **Phase 4**: (a) synthetic validation panel ($P(s)$ and $P(T)$ on BGW avalanches with mean-field prediction); (b) real-data $P(s)$ vs. bin factor (5 panels or single overlay); (c) scaling relation $\langle s | T \rangle$ vs. $T$ with $\gamma$ fit.

### 8. License

- [ ] Decide arXiv license per paper. Default recommendation: `CC BY 4.0` (most reuse-permissive consistent with author retention).
- [ ] Confirm GitHub repo license is compatible (currently mixed; pin a single license at repo root before tagging release for paper).

### 9. ATBD-style supplementary materials

For Phase 1 (earthquake) in particular, seismological reviewers will expect more depth on:

- [ ] Catalog query parameters and reproducibility (we have this in `fetch_log.json`, but spell out in supplementary).
- [ ] Sensitivity to $M_c$ method choice (max-curvature vs. b-value-stability vs. EMR).
- [ ] Per-Flinn-Engdahl-region $b$-value breakdown as a supplementary table.

For Phase 4 (neural):

- [ ] Per-trial-phase analysis (delay vs. cue vs. response) as a supplementary if time allows.
- [ ] Subsampling-correction estimate of true cortical $\tau$ following Priesemann 2014.

### 10. Inter-paper citation finalization

Each Markdown draft cites the other three by Phase number and "this work" placeholders. After LaTeX conversion and arXiv submission:

- [ ] Replace all "Phase 1 (this paper)" / "Phase 2 [N]" references with concrete arXiv IDs and / or DOIs once available.
- [ ] If submitting as a 4-paper bundle on the same day, coordinate the cross-citation update before the final upload to avoid orphan references.

---

## Production sanity checks (before any upload)

- [ ] All math compiles: $\alpha$, $\tau$, $\langle \cdot \rangle$, subscripts/superscripts in tables.
- [ ] All hyperlinks resolve: DANDI dataset URL, USGS FDSN endpoint, GitHub repo paths, MakerDAO docs URL.
- [ ] All claimed numbers reproduce when running the cited scripts from the cited commit hashes.
- [ ] No `placeholder` strings remain in author/correspondence blocks.
- [ ] License and copyright lines present.
- [ ] Acknowledgments include AI disclosure paragraph in journal-specific approved phrasing.
- [ ] References numbered consistently with in-text citations.
- [ ] Figure files (when added) are at the right resolution and embedded correctly.

---

## What this checklist deliberately does NOT cover

- Co-author negotiation specifics (who to invite, what fraction of authorship).
- Funding-acknowledgment language (none received; if any retroactive grant is identified before submission, include the grant number).
- Conflict-of-interest disclosure (none expected; verify before submission).
- Reviewer suggestions (some journals ask for these; build a list per paper based on the reference list).
- Cover-letter drafts.

These are downstream of the Markdown-draft scope assigned to this subagent (W3-E, structural-isomorphism Session #3, C2 task) and should be picked up by a follow-on subagent or by the author directly.
