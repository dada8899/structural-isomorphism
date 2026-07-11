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
universality wording. Hash updates are allowed only after rerunning the recorded
analysis, inspecting the changed result, and updating the associated claim and
caveats.

## Known inconsistency surfaced by the ledger

`results_real_wto.json` contains numeric `k_ci95 = [-7.917, -0.670]`, which
excludes zero, but its legacy verdict string says the interval includes zero.
The ledger treats the numeric fields as evidence and records the stale verdict
text as a caveat. The manuscript must not silently generalize this selected
23-dispute observational result into confirmation or rejection of Schelling
theory as a whole.
