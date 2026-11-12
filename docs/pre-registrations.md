# Pre-registrations

The full set of pre-registration YAML files lives under
`v4/preregistration/` in the repository. Each file is a falsifiable
prediction committed to git before data acquisition; once pushed, the
predicted band cannot be silently widened post hoc.

See [Pre-registration methodology](methodology/pre-registration.md) for
the schema and rationale.

## Active pre-registrations

| System                | Class                 | Predicted band   | Verdict        | Artifact |
|-----------------------|-----------------------|------------------|----------------|----------|
| `cve-vulnerabilities` | SOC / PA              | $[1.5, 2.5]$     | **FAIL**       | [`v4/validation/cve-vulnerabilities/`](https://github.com/dada8899/structural-isomorphism/tree/main/v4/validation/cve-vulnerabilities) |
| `nyc-fdny-fires`      | SOC threshold cascade | $[1.3, 2.0]$     | **INCONCLUSIVE** (primary), **FAIL** (strict) | [`v4/validation/nyc-fdny-fires/`](https://github.com/dada8899/structural-isomorphism/tree/main/v4/validation/nyc-fdny-fires) |
| `wsb-posts`           | Preferential attachment | $[1.8, 3.0]$   | (pending)       | (pending) |

Additional historical systems (earthquakes, S&P 500, DeFi, neural,
GitHub stars, FDIC, NIFC wildfires, GOES flares, Wikipedia views,
power grid) were validated under earlier pipeline phases and are
documented in the unified preprint (`paper/v0-unified-pipeline-2026-05-13.md`).

## Verdict distribution

At the time of writing the pipeline has produced:

- **PASS**: 13 systems (earthquakes, S&P 500, Aave V2, Compound V2,
  MakerDAO Dog, mouse ALM cortex, GitHub stars, FDIC bank failures,
  NIFC wildfires, GOES solar flares, Wikipedia pageviews, power grid,
  plus the universal-collapse polish).
- **INCONCLUSIVE**: 1 system (NYC FDNY fires, primary series).
- **FAIL**: 1 system (CVE disclosures), 1 secondary series (FDNY
  strict).

The asymmetric distribution of outcomes is itself an argument that the
pipeline is not over-claiming: a pipeline that produced only PASS would
be suspect, and a pipeline that produced only FAIL would not justify the
cross-domain universality claim. The 13/1/1 split, with mechanism-level
explanations for the non-PASS verdicts, is the methodological target.
