# Security Policy

> **Last reviewed**: 2026-05-15
> **Maintainer**: structural-isomorphism BDFL + (eventual) Maintainer Council

We take the security of structural-isomorphism seriously — both the code and the integrity of our published datasets and statistical claims. This document explains how to report a vulnerability privately, what to expect from us, and our coordinated-disclosure policy.

## Supported versions

| Version | Supported |
|---|---|
| latest `main` / latest tagged release | ✅ yes — security fixes land here |
| previous minor (one release back) | ✅ yes — backported for 6 months |
| older than two minors back | ❌ no — please upgrade |
| pre-v1.0 alphas | best-effort only |

## Reporting a vulnerability

**Please do not report security issues via public GitHub issues, public Discord, or any public channel.** Public disclosure before a fix is available puts users at risk.

### Preferred channel: email

Send a report to **`security@structural-isomorphism.org`** (alias — currently routes to @dada8899; will route to council security subcommittee once formed per GOVERNANCE.md).

If you want to encrypt your report (recommended for serious vulnerabilities):

```
-----BEGIN PGP PUBLIC KEY BLOCK-----
[TODO: BDFL PGP key to be added before NumFOCUS submission. Until then,
 encrypt with the GitHub-published SSH key on the @dada8899 profile via
 age (https://age-encryption.org) OR contact via direct GitHub DM to
 arrange a key exchange.]
-----END PGP PUBLIC KEY BLOCK-----
```

Key fingerprint: `[TODO: fingerprint to be published once key is generated]`

### Alternative channel: GitHub Security Advisories

If you have a GitHub account, you can use [GitHub's private vulnerability reporting](https://github.com/dada8899/structural-isomorphism/security/advisories/new). This routes directly to maintainers and supports coordinated disclosure timelines.

### What to include

A useful report typically contains:

1. **Description** of the vulnerability (1-2 paragraphs)
2. **Affected component(s)** — file paths, function names, API endpoints, dataset paths
3. **Reproduction steps** — minimal code, curl command, or input that triggers the issue
4. **Impact** — what an attacker could do (data exfiltration? code execution? data integrity? DoS?)
5. **Suggested mitigation** (optional but appreciated)
6. **Your name + affiliation** (or "anonymous" if preferred) — for credit in the eventual advisory
7. **Embargo preference** — default is 90 days; ask for a different window if needed

### Scope

**In scope**:

- Code in this repository (`v4/`, `web/`, `packages/`, `apps/`)
- Published datasets (integrity, provenance, or content-addressed-hash mismatches)
- LLM-judging pipeline (prompt injection, judge manipulation that affects published results)
- Documentation that includes runnable commands (e.g. tutorial steps that silently exfiltrate data)
- CI / supply-chain (GitHub Actions, pre-commit hooks, package dependencies)

**Out of scope** (please don't report these as security issues; open a regular bug instead):

- Statistical methodology disagreements (use `research` label on GitHub Issues)
- Performance issues that don't have a security angle
- Issues in third-party dependencies that don't affect us (report upstream)
- Theoretical vulnerabilities with no practical exploit path
- "Vulnerabilities" in published research findings — that's what peer review and adversarial replication are for

### What is **not** considered a vulnerability

- Pipeline produces a numerically inconvenient result on a real dataset (this is data science, not a bug)
- A reviewer-LLM disagrees with another reviewer-LLM (this is a feature; we publish the disagreement)
- Someone forks the project and uses it badly (their problem, not ours)
- An adversarially-crafted dataset produces a wrong universality-class label, **as long as the pipeline's confidence interval honestly reflects the uncertainty**

## What to expect from us

### Triage SLA

- **Acknowledgement**: within **14 calendar days** of receiving your report. We will confirm receipt and tell you whether we're treating it as a security issue.
- **Triage decision**: within **30 days**. We will tell you our assessment of severity and our planned timeline.
- **Fix released**: within **90 days** for most issues. Critical-severity issues may be fixed faster (target: 14 days). Lower-severity issues may take longer if they require breaking changes; we will negotiate timeline with the reporter.

### Embargo

- **Default embargo**: 90 days from report to public disclosure.
- We may ask for an extension if a fix requires coordinated upstream changes (e.g. a dependency CVE).
- You may request a shorter embargo if the issue is already being actively exploited.
- After the embargo lifts, we will publish a GitHub Security Advisory and a CVE if applicable.

### Credit

Unless you request anonymity, we will credit you in:

- The Security Advisory
- The release notes
- A "Hall of Thanks" page under `docs/community/security-thanks.md`

We do not currently run a paid bug bounty. If/when NumFOCUS sponsorship and funding allow, we will consider one.

### Coordinated disclosure

If your finding implicates a third-party project (e.g. a CVE in our dependency that we surface), we will:

1. Notify the upstream project privately
2. Coordinate fix timing
3. Cross-link advisories on release

If you have already notified upstream, please tell us so we can coordinate.

## Our security practices

Things we already do:

- Dependabot enabled for all package managers (Python, JS, GitHub Actions)
- DCO sign-off required on all commits
- Branch protection on `main`: PR + review required, status checks required
- Secrets scanned in CI (`detect-secrets` pre-commit hook)
- Dataset integrity verified via content-addressed SHA-256 on every pipeline run

Things we are working on (W7-B engineering roadmap):

- Reproducible builds with pinned `pip` lockfile
- Sigstore signing for releases
- SLSA-3 compliance for the published Python package
- Adversarial-replication CI gate that blocks releases on judge-disagreement spikes

## Disclosure history

(empty as of 2026-05-15 — no security advisories filed yet)

## Questions

For non-sensitive questions about this security policy, open a [GitHub Discussion](https://github.com/dada8899/structural-isomorphism/discussions) in the Meta category.

For sensitive questions, use the email channel above.
