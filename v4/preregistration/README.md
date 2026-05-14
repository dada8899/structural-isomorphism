# Adversarial Pre-Registration

> Date-stamped predictions locked **before** data acquisition. This directory implements the §8 protocol in `paper/v0-unified-pipeline-2026-05-13.md`.

## Why pre-register?

The §5.4 internal calibration noted that 11/11 verified systems fell inside their predicted bands — a coverage rate sufficiently clean to raise the concern that:

1. The bands are too wide.
2. The predictions were made post-hoc on the same data being used to test them.
3. Both.

The pre-registration protocol attempts to falsify the v4 framework on systems that were **not** used to construct the bands. If the locked predictions still hold on adversarially-chosen new systems, the framework gains credibility. If they fail, the failure mode tells us exactly where the universality-class portability story breaks.

## How it works (the rule, not the wish)

1. **Before** acquiring any data on a candidate system, we write a yaml file in this directory specifying:
   - `system`: short id
   - `class_id`: which v4 universality class the system is claimed to belong to
   - `predicted_exponent` + `predicted_band`: the locked prediction
   - `reasoning`: why we predict this band, citing **only** independent literature anchors (not v4 calibration data)
   - `data_source` + `data_url`: where the data will come from
   - `success_criteria` + `verdict_rules`: the prediction-resolution rule, also locked
2. We `git add` + `git commit` + `git push` the yaml. The commit timestamp becomes the immutable date stamp.
3. **Then** we acquire the data and run `v4/scripts/run_preregistered_validation.py <yaml>`.
4. The script writes `v4/validation/<system>/result.json` with verdict ∈ {PASS, FAIL, INCONCLUSIVE}.
5. Verdicts are aggregated at session-end into a single pre-registration table for the v0.4 paper revision.

## Why these 3 systems for W1-C

The paper §8.2 lists 5 candidate adversarial systems (BCH returns, Reddit comment cascades, FluNet influenza, Flickr uploads, ant-colony foraging). The 3 systems pre-registered here are **additional** to those, chosen for the following reasons:

| System | Class hypothesis | Why adversarial |
|---|---|---|
| `nyc-fdny-fires` | SOC cascade (`soc_cascade`) | NYC urban fire data was not used in any v4 phase. The SOC wildfire band was anchored on Malamud 1998 forest fires, not on urban dispatch records. Tests whether the urban-confined geometry breaks the open-landscape α band. |
| `cve-vulnerabilities` | SOC cascade vs preferential attachment (two-pronged) | NVD/CVE data was not used in any v4 phase. Tests cross-domain portability into the cybersecurity domain, where SOC vs PA is genuinely ambiguous a priori. |
| `wsb-posts` | SOC Hawkes/Omori | r/wallstreetbets was not used in any v4 phase. The Hawkes/Omori band is anchored on Crane-Sornette 2008 YouTube + earthquake aftershock literature. The 2021 GameStop regime shift is a known confound, which makes the test sharper, not weaker. |

All 3 have:
- Public, well-curated data sources.
- Independent literature anchors for the predicted band.
- No overlap with the calibration set.

## What "PASS" means (and does not)

- **PASS** means the locked α (or `p`) landed inside the locked band, with the locked null-hypothesis rejection criteria satisfied. It does **not** prove universality-class membership; it provides one more piece of evidence that the v4 framework's predictions generalize.
- **FAIL** is informative. A FAIL on `nyc-fdny-fires` would tell us urban geometry breaks the SOC wildfire band; a FAIL on `cve-vulnerabilities` would tell us security data sits outside the SOC/PA spectrum; a FAIL on `wsb-posts` would tell us social-media Hawkes is structurally different from earthquake / YouTube Hawkes.
- **INCONCLUSIVE** means the data acquisition was blocked, the sample size was insufficient, or the null-hypothesis tests were ambiguous (Vuong p ~ 0.5). This is **not** a soft PASS; it is recorded honestly as inconclusive.

## What's locked vs what's not

Locked the moment the yaml is committed:
- predicted exponent
- predicted band
- success criteria
- verdict rules
- data source identity
- extraction method (the specific metric definition — e.g. "incident size = units dispatched")

Not locked (and explicitly allowed to vary):
- The specific date the data is downloaded (we'll record the snapshot date in `result.json`).
- The bootstrap seed (we record the seed used; we do not re-seed if a fit produces an unwelcome verdict).
- The visualization scripts.

## Re-running a pre-registration

`run_preregistered_validation.py` is **idempotent** by design. If `v4/validation/<system>/result.json` exists, the script refuses to overwrite without `--force`. A re-run with `--force` records the previous result in `result.history.jsonl` so the history of verdicts is preserved. This prevents accidental p-hacking via repeated re-fits.

## Honest accounting

The protocol does not prevent all forms of researcher degree-of-freedom, but it does:
- Forbid post-hoc widening of the band.
- Forbid post-hoc switching of the metric (e.g. "incident-size = duration" vs "= units").
- Forbid post-hoc switching of the null-hypothesis rejection rule.
- Force any deviation to be logged explicitly in `result.json` as a "protocol deviation".

A pre-registration that is partly violated is still more informative than no pre-registration, **provided** the violation is logged with the same prominence as the result.

## Index

- `nyc-fdny-fires.yaml` — NYC FDNY fire-incident dispatch (SOC cascade)
- `cve-vulnerabilities.yaml` — NIST NVD vulnerability disclosures (SOC vs PA)
- `wsb-posts.yaml` — Reddit r/wallstreetbets post cascades (SOC Hawkes/Omori)

Additional pre-registrations may be added in future sessions; each new yaml must follow the same locking rule (commit before data acquisition).
