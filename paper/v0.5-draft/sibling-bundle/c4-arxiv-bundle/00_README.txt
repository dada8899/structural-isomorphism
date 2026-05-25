arXiv submission bundle — C4 v0.4 reject-aware pipeline preprint
==================================================================

Title:    A reject-aware pipeline for cross-domain universality discovery
Author:   Wan Qinghui (万庆徽), Structural Isomorphism Project
Source:   paper/c4-reject-aware-pipeline-2026-05-13.md (v0.2 methodology preprint,
          recently amended with §4.3.2 Hawkes-vs-SOC-Gumbel disambiguation note)
Bundled:  2026-05-25 (SESSION-25)

Companion preprint
------------------
C1 v0.4 (release/arxiv/c1-unified-preprint-v0.4/) — empirical companion.
Recommended: submit C1 first, then C4 cross-citing C1's arXiv ID.

Contents
--------
- main.tex                          Self-contained LaTeX (pandoc-generated, 1844 lines)
- references.bib                    45 BibTeX entries (exact bibliography of §10)
- figures/fig_3layer_pipeline.pdf   Figure 1 (PDF — arXiv-required format)
- abstract.txt                      1900-char plain abstract (under 1920 arXiv limit;
                                    main.tex carries the longer 3242-char version verbatim)
- metadata.yml                      arXiv classification + companion-preprint linkage
- 00_README.txt                     This file

Submission steps (5-10 min after C1 ID in hand)
------------------------------------------------
1. Log in to https://arxiv.org → New submission → arXiv non-exclusive licence.
2. Upload a .zip containing ONLY:
     main.tex
     references.bib
     figures/fig_3layer_pipeline.pdf
   Do NOT include abstract.txt, metadata.yml, 00_README.txt — those are out-of-band
   moderator metadata, not part of the source archive.
3. Verify arXiv's server-side compile renders:
   - Title + author + abstract block
   - 45 references (no ?? placeholders)
   - Figure 1 inline at §2 with caption
   - 21-class verdict table in §4.1
   - Appendix A (B3 prompt verbatim), Appendix B (verdict-matrix schema), Appendix C (operational reliability)
4. Paste form metadata (from metadata.yml):
   - Title: A reject-aware pipeline for cross-domain universality discovery
   - Author: Wan Qinghui (ORCID if linked)
   - Abstract: paste abstract.txt content (arXiv strips newlines; OK)
   - Primary category: cs.LG
   - Cross-list: stat.ME, cond-mat.stat-mech, physics.data-an, q-bio.QM
   - MSC: 62-07, 68T50, 82C99
   - Comments: per metadata.yml `comments:` field — REPLACE [PENDING_C1_ARXIV_ID]
                with the C1 arXiv ID earned earlier in the day.
5. Paste moderator_notes (from metadata.yml) into the Submission notes field.
6. Preview the server-built PDF → Submit → moderation queue (1-3 working days).
7. Record the C4 arXiv ID back to the main session.

Known caveats
-------------
- main.tex was pandoc-converted from Markdown. Spot-check the server-built PDF for:
  - any escaped underscores in URLs (would render as \_ literally; rare but possible)
  - any \texttt{} blocks that overflow margins
  - the YAML-style frontmatter at top should NOT have made it into main.tex; if it did,
    delete those lines before resubmit (pandoc usually strips it correctly).
- Figure 1 is a PDF, not PNG. arXiv requires PDF/EPS only — do not substitute.
- The escaped-dollar costs ("\$0.10", "\$1.50") are intentional LaTeX literals.

If pandoc rebuild is needed
---------------------------
The current main.tex was built with:
  pandoc paper/c4-reject-aware-pipeline-2026-05-13.md \
    --from=markdown --to=latex --standalone \
    --variable=documentclass:article --variable=classoption:11pt \
    --variable=geometry:margin=1in --variable=fontfamily:lmodern \
    --variable=colorlinks:true --variable=linkcolor:blue --variable=urlcolor:blue \
    --variable=papersize:letter \
    -o main.tex
(with the image path pre-substituted from figures/c4/fig_3layer_pipeline.png to
figures/fig_3layer_pipeline.pdf, done via a one-line sed on /tmp/c4-arxiv-input.md.)

After arXiv ID is in hand
-------------------------
1. Replace [PENDING_C1_ARXIV_ID] in metadata.yml `comments:` field (if not already done at submission time).
2. Update top-level README.md / CITATION.cff to add the C4 arXiv badge.
3. Update C1's arXiv comments via `replace` to link the C4 arXiv ID (cross-pointer).
4. Update the methodology-short-note's metadata to link both C1 and C4 arXiv IDs.
