# Pre-registration methodology

Pre-registration is the discipline of committing — in writing, with a
verifiable timestamp — to the prediction, the data extraction recipe, and
the verdict rules **before** data are observed. In this project the
timestamp is supplied by a git commit hash pushed to a public remote, and
the verifiable artifact is a YAML specification under
`v4/preregistration/`. Once pushed, the predicted band cannot be silently
widened post hoc.

## Why this is necessary

In retrospective analysis the analyst has many degrees of freedom:
choice of aggregation, choice of filter, choice of fit method, choice of
rejection threshold. Each degree of freedom is benign on its own, but
their compound effect is to make a positive result almost guaranteed
under sufficient effort. This is the well-known **garden of forking
paths** problem. Pre-registration collapses the degrees of freedom: the
YAML specifies every choice in advance, and the fitter consumes the YAML
byte-for-byte. The verdict is then a function of the data alone.

## Schema

Each pre-registration YAML has the following stanzas (see
`v4/preregistration/cve-vulnerabilities.yaml` for a complete example):

```yaml
system: <slug>
pre_registered_at: <YYYY-MM-DD>
class_id: <SOC | PA | Motter-Lai | Preisach | Scheffer | ...>
universality_class: <human-readable description>
predicted_exponent: <point estimate>
predicted_band: [<low>, <high>]
reasoning: |
  <paragraph explaining the anchor literature and the choice of band>
data_source: <URL or repo path>
data_url: <fetch URL>
data_license: <license string>
data_size_estimate: <approximate total record count>
sample_size_target: <minimum n required>
extraction_method: |
  <step-by-step recipe; must be deterministic>
verification_method: |
  <Clauset + Vuong + bootstrap recipe; must reference soc_pipeline functions>
null_hypothesis_alternatives:
  - exponential
  - log_normal
  - <others>
success_criteria:
  - <list of pass conditions>
verdict_rules:
  PASS: <condition>
  FAIL: <condition>
  INCONCLUSIVE: <condition>
calibration_independence:
  - <stanza confirming the test data was not used in any prior calibration>
risks_and_caveats:
  - <list of known data-quality risks documented in advance>
```

## The verdict triad

The three permitted verdicts are:

- **PASS** — fitted $\alpha$ is in the predicted band, and the power-law
  is not decisively rejected against the alternatives. The system is
  consistent with the predicted universality class.
- **INCONCLUSIVE** — fitted $\alpha$ is in the band but the alternatives
  also fit well, or the bootstrap CI is wide enough to include the band
  edges, or $n_{\mathrm{tail}}$ is too small for the Vuong test to be
  informative. The data does not adjudicate.
- **FAIL** — fitted $\alpha$ is outside the band, or all alternatives
  decisively beat power-law. The system is not in the predicted class.

The discipline is that all three verdicts are equally publishable. A
pipeline that produces only PASS verdicts is suspect; the v4 pipeline has
produced one FAIL (CVE) and one INCONCLUSIVE (NYC FDNY) alongside the
thirteen PASS results, and the asymmetric distribution of outcomes is
itself an argument that the pipeline is not over-claiming.

## Worked example

The CVE falsification is the canonical worked example. The YAML at
`v4/preregistration/cve-vulnerabilities.yaml` was committed on 2026-05-14
(commit `34f2a81`) before any NVD API call. The downstream fitter loaded
the YAML, fetched 10,280 high-severity 2023 CVEs, and applied the
pre-registered verification method. The result: $\alpha = 2.668$ outside
band $[1.5, 2.5]$, Vuong $p = 0.002$ vs lognormal, Vuong $p = 0.0001$ vs
exponential. By the pre-registered verdict rule, this is FAIL. The full
paper [CVE falsification preprint](../papers.md) develops the mechanism:
Patch Tuesday administrative clustering produces a mixture distribution
that is steeper than SOC and is well-fit by lognormal.

The point of the example is that under retrospective analysis the same
data could very plausibly have been reported as "consistent with
preferential attachment at $\alpha \approx 2.7$." Pre-registration
forecloses that move.

## How to write your own

To pre-register a new system:

1. Copy `v4/preregistration/cve-vulnerabilities.yaml` as a template.
2. Replace the `system`, `class_id`, `predicted_band`, `reasoning`,
   `data_source`, and `extraction_method` stanzas.
3. **Do not fetch the data yet.** This is the hardest discipline: it is
   tempting to peek.
4. Commit the YAML to a branch and push. The commit hash is the timestamp.
5. Open a pull request to main. Once merged, the pre-registration is
   public record.
6. Only then fetch the data and run the fitter.

A pull request template under `.github/PULL_REQUEST_TEMPLATE.md` includes
a pre-registration checklist that flags violations (e.g., the same PR
touches both the YAML and the validation directory, which is a sign that
the analyst peeked).
