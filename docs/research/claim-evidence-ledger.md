# Claim–evidence ledger

Date: 2026-07-12
Status: internal reproducibility control; the v0.5 manuscript remains **reviewer-readable / do not submit**.

The machine-readable authority is
`evaluation/research/claim-evidence-ledger-v1.json`. It records each headline
claim's exact wording, bounded scope, status, evidence hashes, reproduction
command, environment or seed, result location, provenance, independence, and
caveats. “Internal review” is not external peer review.

Run the fail-closed check from the repository root:

```bash
python3 scripts/research_claim_gate.py
python3 -m pytest tests/test_research_claim_gate.py
```

The gate rejects missing evidence, changed hashes, incomplete headline entries,
placeholder DOI/arXiv identifiers, false external-review status, and absolute
universality wording. It also scans strong-claim lines in the manuscript's
Abstract and Contributions. Each such line is content-addressed in
`manuscript_claim_inventory`, must link to one or more ledger claims, and every
ledger claim must link back to a current manuscript line. Adding, editing, or
removing a strong line therefore fails closed until the scientific scope and
evidence mapping are reviewed. Hash updates are allowed only after rerunning the
recorded analysis, inspecting the changed result, and updating the associated
claim and caveats.

## Submission-blocking conflict surfaced by the ledger

The B1 taxonomy rejects `schelling_credible_commitment` as a dynamical
universality class, while the manuscript later assigns a positive label to a
synthetic response-model fit. The real WTO sample independently rejects the
pre-registered positive observational slope: `k_ci95 = [-7.917, -0.670]`.
`conflict_register` therefore blocks submission and requires Schelling to be
excluded from universality-class PASS counts. The synthetic run may be retained
only as a bounded generator/response-model experiment; the selected,
manually-coded 23-dispute WTO result may be retained only as an observational
rejection requiring independent double-coding.

`legacy-conflict-blocked` inventory entries make historical manuscript claims
auditable without endorsing them. They are not a waiver: the manuscript remains
reviewer-readable / do not submit until those lines are rewritten and the
conflict is independently reviewed.
