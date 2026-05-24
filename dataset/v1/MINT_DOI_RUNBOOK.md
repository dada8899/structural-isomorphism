# Mint DOI runbook (Zenodo v1)

**Status:** pre-mint snapshot. The DOI is not yet reserved. This document is
the step-by-step recipe for minting the permanent DOI for
`dataset/v1/` once user authorization is given.

**Important:** Minting a DOI is permanent and not retractable. Do not run
step 4 (publish) without explicit user sign-off.

---

## Prerequisites

- A Zenodo account at https://zenodo.org (use ORCID-linked if available).
- Optional: link the GitHub repo to Zenodo (Account → GitHub) so that future
  releases auto-mint DOIs.
- A clean checkout of the bundle: `git clone ... && cd structural-isomorphism
  && python3 dataset/v1/scripts/compute_manifest.py` should report 244 files
  / ~99 MB / 16 / 4 / 35 / 17.

---

## Step 1 — Prepare the upload artifact

The bundle uses symlinks to keep the in-repo footprint near zero. Zenodo
needs concrete files. Choose one of:

### Option A: Tarball (recommended for direct upload)

```bash
cd /path/to/structural-isomorphism
# Dereference symlinks (-h) so the tarball is self-contained
tar -czhf zenodo-soc-dataset-v1-2026-05-13.tar.gz dataset/v1/
ls -lh zenodo-soc-dataset-v1-2026-05-13.tar.gz
# Expected: ~25-40 MB compressed
```

### Option B: GitHub release link

```bash
# Tag the bundle commit
git tag -a dataset-v1.0.0 -m "Zenodo dataset v1.0.0 release"
git push origin dataset-v1.0.0
# Then on GitHub: Releases → Create release from tag dataset-v1.0.0
# Zenodo can ingest the release via its GitHub integration.
```

We recommend **Option A** for the first mint (full control over what gets
uploaded), then **Option B** for future v1.1+ revisions via the
auto-Zenodo-on-GitHub-release pipeline.

---

## Step 2 — Create the Zenodo upload

1. Log in to https://zenodo.org
2. **Upload → New Upload**
3. **Files:** drag in `zenodo-soc-dataset-v1-2026-05-13.tar.gz`. Wait for
   upload to complete (~1 min on a fast connection).
4. **Communities:** add the upload to relevant communities. Suggestions:
   - `zenodo` (default)
   - `complexsystems` (if exists)
   - `physics-and-astronomy` (if exists)
   - Any university / institution community you belong to.
5. **Reserve DOI:**
   - In the "Basic information" section, click **Reserve DOI**
   - Zenodo returns a DOI like `10.5281/zenodo.12345678`. Write this down.
   - At this point the DOI exists but the deposit is not yet published.
6. **Resource type:** Dataset.
7. **Title:** `Cross-domain SOC validation dataset (v1, 2026-05-13)`
8. **Authors:** dada8899 (Independent Research). Add ORCID if available.
9. **Description:** paste the contents of `dataset/v1/README.md § 1`
   (the Overview section, ~600 words). Format as Markdown.
10. **Version:** `1.0.0`
11. **Publication date:** `2026-05-13`
12. **License:** Creative Commons Attribution 4.0 International (CC BY 4.0)
13. **Keywords:** copy from `CITATION.cff` (self-organized criticality,
    universality classes, power-law, Clauset MLE, Omori law,
    Gutenberg-Richter, cross-domain validation, LLM ensemble critic,
    reproducibility benchmark, synthetic null controls).
14. **Related identifiers:**
    - GitHub repo URL (`is supplement to`)
    - Forthcoming Scientific Data manuscript (when arXiv'd, add as
      `is documented by`)
15. **Funding:** leave blank unless applicable.
16. **Save** (do *not* publish yet).

---

## Step 3 — Update bundle with the reserved DOI

Once Step 2 reserves a DOI like `10.5281/zenodo.12345678`, update the
in-bundle references **before** publishing:

```bash
# In the working checkout of structural-isomorphism (any branch will do —
# the bundle update is a regular commit on the working branch):

# 3a. Update manifest.json
python3 -c "
import json
m = json.load(open('dataset/v1/manifest.json'))
m['doi_placeholder'] = '10.5281/zenodo.12345678'
m['doi'] = '10.5281/zenodo.12345678'
json.dump(m, open('dataset/v1/manifest.json', 'w'), indent=2)
"

# 3b. Update CITATION.cff
sed -i.bak 's|10.5281/zenodo.PLACEHOLDER|10.5281/zenodo.12345678|' dataset/v1/CITATION.cff
rm dataset/v1/CITATION.cff.bak

# 3c. Update README.md DOI placeholder
sed -i.bak 's|10.5281/zenodo.PLACEHOLDER|10.5281/zenodo.12345678|g; s|10.5281/zenodo.XXXXXXX|10.5281/zenodo.12345678|g' dataset/v1/README.md
rm dataset/v1/README.md.bak

# 3d. Commit
git add dataset/v1/manifest.json dataset/v1/CITATION.cff dataset/v1/README.md
git commit -m "dataset(v1): lock-in Zenodo DOI 10.5281/zenodo.12345678"
git push

# 3e. Rebuild the upload tarball with the locked-in DOI
tar -czhf zenodo-soc-dataset-v1-2026-05-13.tar.gz dataset/v1/

# 3f. On Zenodo, REPLACE the uploaded file (Files → Delete old,
#     Upload new) — the reserved DOI is preserved.
```

Now the bundle Zenodo sees has the DOI baked into manifest.json, CITATION.cff,
and README.md.

---

## Step 4 — Publish (PERMANENT)

⚠️ **This step is irreversible.** Once published, the DOI is permanent and
the deposit cannot be deleted, only superseded by a v1.1.

1. Re-check Steps 2 + 3 — title, authors, description, license, files all
   match what you want forever.
2. Click **Publish**.
3. The DOI page is now live: https://doi.org/10.5281/zenodo.12345678
4. Zenodo emails you the citation snippet — paste it back into the
   structural-isomorphism README and the forthcoming Scientific Data
   manuscript.

---

## Step 5 — Update upstream references

After publishing:

```bash
# 5a. Top-level repo README — add the DOI badge
# (Zenodo provides a badge URL like:
#  https://zenodo.org/badge/DOI/10.5281/zenodo.12345678.svg)

# 5b. Forthcoming Scientific Data manuscript — update Section "Data Records"
#     with the DOI

# 5c. The C1 manuscript (paper/c4-reject-aware-pipeline-2026-05-13.md) —
#     add the DOI to the "Code and Data Availability" section
```

---

## Step 6 — Future versions (v1.1, v2.0)

Zenodo's *version* feature gives each subsequent version a new
DOI plus a parent "concept DOI" that resolves to the latest. To release
v1.1:

1. From the v1 Zenodo page, click **New version**.
2. Upload the v1.1 tarball + update description with changelog.
3. Reserve + publish — you get a fresh DOI like `10.5281/zenodo.12345679`.
4. The concept DOI (typically `10.5281/zenodo.12345677`, one less than
   v1's record DOI) automatically points at v1.1.

Recommended cadence for this dataset:

- **v1.1** (month 6-9): fold in §8 pre-registered new systems (Bitcoin
  Cash, Reddit cascade, FluNet influenza, Flickr bursts, ant-colony
  foraging) — see `docs/future/W7-A-academic-value-roadmap-2026-05-13.md`
  for the pre-registration spec.
- **v2.0** (month 12-18): integrate with `awesome-soc-datasets` /
  OpenML / `papers-with-code` ecosystem index.

---

## Troubleshooting

**"My tarball is too big for Zenodo."** Zenodo's default per-file limit is
50 GB. This dataset is ~25-40 MB compressed → no issue.

**"I forgot to update the DOI placeholders before publishing."** Not fatal,
but unprofessional. Create a v1.0.1 with the DOI baked in (same procedure,
fresh DOI; explain in the description that v1.0.1 is identical content +
metadata fix).

**"I want to delete the deposit."** Not possible after publication. You can
only mark it as "superseded" by a new version. This is by design — DOIs
must be permanent. This is why Step 4 is gated on user sign-off.

**"The cffconvert tool says my CITATION.cff is invalid."**

```bash
pip install -q cffconvert
python -c "from cffconvert.cli.main import main; main(['validate', '-i', 'dataset/v1/CITATION.cff'])"
```

Common issues: indentation, missing required fields (cff-version, title,
authors, message). Fix and re-validate.

---

## Approval gates

- [ ] User confirms: dataset content is final at git commit 607906c.
- [ ] User confirms: tarball was rebuilt with the DOI locked-in (Step 3).
- [ ] User confirms: authorship and affiliation are correct.
- [ ] User confirms: license CC-BY-4.0 is OK.
- [ ] User explicitly says "publish v1.0.0 now" before Step 4.

This subagent (W8-A) does **not** mint the DOI itself. The bundle is
fully prepared but minting requires the user's explicit consent because
the DOI is permanent.
