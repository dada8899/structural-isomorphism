# arXiv Submission Runbook — 6 papers, structural-isomorphism v0.3

This runbook walks you (user) through arXiv submission for the 6 PDFs prepared in `paper/arxiv-submission/`. arXiv requires manual review and final click — **no auto-submit**.

## Pre-requisites (one-time)

### 1. arXiv account
- Register at https://arxiv.org/user/register (email + institutional affiliation)
- Link **ORCID** at https://arxiv.org/user/ → "Connect ORCID iD" (highly recommended; reduces moderation friction)
- Confirm email + complete user profile

### 2. Endorsement (for first-time submitters in some categories)

arXiv has a category-specific endorsement system: first-time submitters to `cond-mat`, `physics.*`, `q-bio.*`, `q-fin.*` need someone already publishing in that area to endorse you. **Check status** at https://arxiv.org/auth/need-endorsement first.

If endorsement needed:
- Find an existing arXiv author publishing in `cond-mat.stat-mech` (look at recent papers in your reference list)
- Email them with: who you are + paper title + abstract + endorsement code (arXiv emails you the code)
- They reply yes/no via arXiv interface
- Endorsement is per primary category — once endorsed in `cond-mat.stat-mech`, it covers all `cond-mat.*` for life

If you have **no endorser**, alternatives:
- Submit to `physics.data-an` instead (sometimes lower endorsement bar)
- Coauthor with someone already endorsed
- Apply for autoendorse: https://arxiv.org/help/endorsement (cite your prior publications elsewhere)

### 3. Pre-submission file prep (ALREADY DONE)

The F3 agent has prepared:
- `paper/arxiv-submission/c1-unified-v0.3.pdf` — 364 KB
- `paper/arxiv-submission/01_earthquake_soc.pdf` — 147 KB
- `paper/arxiv-submission/02_stockmarket_inverse_cubic.pdf` — 139 KB
- `paper/arxiv-submission/03_defi_cross_protocol.pdf` — 158 KB
- `paper/arxiv-submission/04_neural_avalanches.pdf` — 140 KB
- `paper/arxiv-submission/c4-reject-aware.pdf` — 197 KB
- `paper/arxiv-submission/SUBMISSION_METADATA.md` — copy-paste blocks for each paper

These were generated from markdown via `pandoc → weasyprint`. **Quality caveat:** equations render as MathJax-style fallback (not native LaTeX), and the PDFs are usable for preprint but not journal-quality. For higher-fidelity equation rendering, regenerate with `xelatex` (requires BasicTeX/MacTeX install; see "Optional PDF rebuild" below).

### 4. Replace author placeholders

Before submitting, edit each paper's markdown source and replace:
- `dada8899@users.noreply.github.com` → real institutional email
- "Independent researcher" → real affiliation if applicable
- Add ORCID

Then rebuild the PDFs (see below) so the final PDF has the correct author block.

## Submission workflow (per paper)

For each of the 6 PDFs, in order (C1 first, then 01-04, then C4):

### Step 1 — Start new submission

1. Login at https://arxiv.org
2. Click "Start New Submission"
3. License → CC-BY 4.0 (recommended; or arXiv perpetual non-exclusive)
4. Confirm "I agree to authorship rules"

### Step 2 — Upload file

- Format → PDF (not source)
- Upload the PDF from `paper/arxiv-submission/`
- arXiv auto-validates the file (~30s). Passing validation = fonts embedded + page count + image res OK.
- If validator fails, see "Troubleshooting" below.

### Step 3 — Metadata

Open `paper/arxiv-submission/SUBMISSION_METADATA.md` and find the block matching your PDF. Copy fields:

| arXiv form field | Source in SUBMISSION_METADATA.md |
|---|---|
| Title | `**Title.**` line |
| Authors | `**Authors.**` (replace placeholder!) |
| Abstract | `**Abstract**` paragraph |
| Comments | `**Comments.**` line |
| Primary category | `**Primary arXiv category.**` |
| Cross-list categories | `**Cross-list.**` |
| MSC classes (optional) | `**MSC classes**` if present |
| License | `**License.**` |

**Abstract limit:** 1920 chars (arXiv hard). Pre-trimmed versions in metadata file are ~1500 chars. Don't paste the full PDF abstract.

### Step 4 — Preview

arXiv generates an "abs page" preview. Verify:
- Authors in right format ("Lastname, F. M.")
- Abstract renders correctly (no broken markdown)
- Categories show as 1 primary + N cross-list

### Step 5 — Submit

Click "Submit" — paper enters **mod queue**. Status:
- **submitted**: in queue (typical wait 1-3 business days)
- **on hold**: moderators reviewing; may email you for fixes
- **published**: assigned arXiv ID (format `2605.XXXXX` for May 2026)

You can withdraw / replace until published. After published, only "replace" (creates v2).

### Step 6 — Post-publication

Once you get arXiv ID:
1. Add to companion Zenodo deposition `related_identifiers` → re-publish if Zenodo not yet finalized
2. Update `dataset/v1/CITATION.cff` `preferred-citation` field
3. Update `paper/arxiv-submission/SUBMISSION_METADATA.md` (mark this paper "submitted" with ID)
4. Tweet / Mastodon / 飞书 announce
5. For follow-up papers in this series, cite the C1 arXiv ID in their Comments + introduction

## Submission timing strategy

| Day | Paper |
|---|---|
| Day 0 | C1 unified (`c1-unified-v0.3.pdf`) — establishes framework |
| Day 7 | 01 earthquake_soc — cite C1 arXiv ID |
| Day 8 | 02 stockmarket — cite C1 + 01 |
| Day 9 | 03 defi_cross_protocol — cite C1 + 01 + 02 |
| Day 10 | 04 neural_avalanches — cite C1 + 01-03 |
| Day 14 | C4 reject-aware — cite all 5 prior |

Spacing prevents arXiv mods from flagging the cluster as "duplicate / overlapping submission".

## Optional: PDF rebuild with xelatex (higher quality)

The weasyprint PDFs use HTML-style typography. For native LaTeX equations + better journal-look fonts, install MacTeX (or BasicTeX):

```bash
brew install --cask basictex
# Refresh PATH then install required packages
sudo tlmgr update --self
sudo tlmgr install collection-fontsrecommended xetex amsmath geometry hyperref
```

Then rebuild:
```bash
cd ~/Projects/structural-isomorphism
mkdir -p paper/arxiv-submission-xelatex/

pandoc paper/v0-unified-pipeline-2026-05-13.md \
  -o paper/arxiv-submission-xelatex/c1-unified-v0.3.pdf \
  --pdf-engine=xelatex --toc --variable=geometry:margin=1in \
  --variable=mainfont="Times New Roman"

for p in paper/arxiv-drafts/2026-05-13/*.md; do
  name=$(basename "$p" .md)
  pandoc "$p" -o "paper/arxiv-submission-xelatex/$name.pdf" \
    --pdf-engine=xelatex --variable=geometry:margin=1in
done

pandoc paper/c4-reject-aware-pipeline-2026-05-13.md \
  -o paper/arxiv-submission-xelatex/c4-reject-aware.pdf \
  --pdf-engine=xelatex --variable=geometry:margin=1in
```

xelatex requires `~ 1 GB` install + reboot of shell PATH but produces much better equation rendering.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| arXiv validator: "fonts not embedded" | weasyprint missed a font fallback | Rebuild with xelatex (`mainfont=` flag) |
| arXiv validator: "PDF version too old" | < 1.4 | weasyprint default is 1.7, should not happen; if so, `--pdf-engine-opt=-V=1.7` |
| Endorsement required | first-time submitter in cond-mat | see §1 Prerequisites — get endorser or switch primary category to physics.data-an |
| Moderation hold > 3 days | category mismatch, abstract length, formatting | reply to moderator email with fixes; in pinch, withdraw and resubmit |
| `400 abstract too long` | > 1920 chars | use the pre-trimmed versions in SUBMISSION_METADATA.md |
| "Title already used by author X" | very common false positive | reply confirming distinct work; usually cleared in 1-2 days |

## Future: companion paper revisions

When you upload v2 of any paper:
1. Use "Replace" on the existing arXiv submission (keeps same arXiv ID, new vN suffix)
2. Update Zenodo deposition with new version
3. Bump PyPI package if accompanying code changed
4. Replace, don't withdraw — citers preserve their references

## Withdrawal (rare; only if you regret submission)

arXiv allows withdrawal but it leaves a tombstone "withdrawn" abs page forever. Only withdraw if there's a serious factual error caught post-submission; otherwise prefer "Replace" with a corrected version.

---

**Bottom line**: artifacts are ready. User flow = login arXiv → 6 × (start submission → upload PDF → paste metadata block → submit). Each submission takes ~15 min, so ~1.5 hours total for the burst. Spread across 2 weeks per the timing strategy above.
