# Stage 1 pilot sourcing protocol v1

Date: 2026-07-12
Status: sourcing infrastructure only; no real problem, answer, expert assignment or scientific evidence is included

## Boundary

The checked-in queue contains 12 **sourcing slots**, not 12 benchmark questions.
Its purpose is to force coverage of four candidate domains and three task
families before anyone selects attractive cases. Domain names describe sampling
strata; they do not assert that a suitable time-split problem exists.
The validator requires exactly one slot in every 4-domain × 3-task-family cell,
the exact `pilot-01` through `pilot-12` sequence, the same budget for every
cell, and the preregistered negative-control type for each task family. A
10-slot subset, duplicated stratum, substituted domain, or unequal budget is
invalid rather than a smaller pilot.

Every slot records the required expert role, equal-budget limits, three strong
baselines and one negative-control design. It deliberately leaves `t0`, corpus
cutoff, outcome date and expert identity null. The outcome source is
`NOT_IMPORTED`, with no locator or digest. Filling those values requires an
independent sourcing and custody process; this repository must not invent them.

## Artifacts

- `evaluation/stage1/pilot-sourcing-queue-v1.json`: 12 placeholder slots.
- `evaluation/stage1/contamination-checklist-v1.json`: unrun leakage checklist.
- `evaluation/stage1/schemas/pilot-sourcing-slot-v1.schema.json`: strict slot contract.
- `scripts/prepare_stage1_pilot.py`: validator and answer-blind expert-packet generator.
- `tests/test_stage1_pilot_sourcing.py`: adversarial no-promotion and no-leakage tests.

Validate the queue without creating packets:

```bash
python3 scripts/prepare_stage1_pilot.py
```

Create private draft packets in a new directory:

```bash
python3 scripts/prepare_stage1_pilot.py --output-dir /private/path/stage1-pilot-packets
```

The generator uses create-exclusive writes, mode `0600`, fsync and stable
content digests. It will not overwrite an existing packet. Packets contain the
contamination questions but no answer locator, digest or outcome.
The output directory must not already exist, is created with mode `0700`, and
is held by a no-follow directory descriptor while all 12 files are written;
this prevents path replacement and symlink races. Queue and checklist inputs
are also opened through no-follow directory descriptors and checked for a
stable inode, size and modification time while read.

All nine contamination question IDs and texts are frozen exactly. Packet
redaction questions may mention the words “answer”, “locator” or “digest”, but
the packet schema contains no corresponding answer value: its only answer
state is the literal `NOT_IMPORTED`. Packet generation revalidates the entire
queue and checklist before creating the private directory.

`--dispatch-ready` intentionally fails for the checked-in queue. Packet creation
does not make a slot ready to dispatch.

## Human sourcing and custody sequence

For each slot, a protocol committee independent of engine development must:

1. identify a candidate whose outcome became available strictly after a
   defensible `t0`;
2. assign an independent domain expert and a separate outcome custodian;
3. freeze the pre-`t0` corpus, model identities, search cache and budget;
4. keep the answer outside model-visible and developer-visible artifacts;
5. run every checklist item, including near-duplicate, target-revealing-text,
   model-training-risk and developer-exposure review;
6. freeze the matched negative control before viewing any arm output;
7. sign and seal the expert packet and outcome envelope separately;
8. use the 10–15 question pilot only to repair procedure, never to estimate the
   Stage 1 effect or choose favorable endpoints.

The pilot must preserve all failures and cannot be promoted into the formal
denominator. Formal Stage 1 still requires a new preregistered manifest, at
least 30 tasks per domain across at least three domains, blinded adjudication,
complete arm results and the predeclared statistical analysis.

## Current decision

- Pilot sourcing infrastructure: **READY FOR INDEPENDENT REVIEW**.
- Pilot questions: **NOT SOURCED**.
- Expert packets: **NOT ASSIGNED / NOT SEALED**.
- Contamination scans: **NOT RUN**.
- Formal Stage 1: **NO-GO**.
- Scientific or product claim from this queue: **PROHIBITED**.
