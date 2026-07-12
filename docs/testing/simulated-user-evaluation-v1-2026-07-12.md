# Simulated User and Heterogeneous Judge Evaluation v1

This protocol measures a journey, not a model's overall impression. Every judgment separately scores **input → processing → result → action → recovery**, and every stage requires an artifact locator. A weighted score cannot hide a stage below the configured floor.

## Roles and task coverage

The frozen role registry covers research PM, growth, doctoral research, first use, non-technical use, mobile-only use, screen-reader use, and a skeptical peer reviewer. The initial fixed tasks cover a defensible transfer request and an unsafe/out-of-scope forecasting request. Additions require a config version bump; historical task wording is not silently edited.

Each run must record positive value, negative value, applicability boundary, and concrete failure conditions. Discovery value is therefore conditional: a high score means useful under the recorded boundary, not universally valuable.

## Judge independence and privacy

At least two distinct model **families** are required. Different temperatures, prompts, or aliases of one family do not qualify as heterogeneous. Every accepted identity must appear in the versioned `allowed_models` registry, and the same complete judge panel must score every role/task group; a judgment cannot establish heterogeneity by self-declaring a new family. Registry review must document the upstream base model, not only the serving provider or product alias. Provider/model identity is persisted, verdict agreement is reported, and stage-level population variance and range expose disagreement. An `abstain` is valid input but can never produce a passing group; missing evidence is invalid.

The checked-in runner is deliberately provider-free and offline. It reads only an explicitly supplied judgment JSONL. Evidence is restricted to traversal-safe `artifact://...#fragment` locators; arbitrary HTTP URLs are rejected. Before any external evaluation, create a redacted artifact bundle containing only frozen task inputs and public/product outputs; exclude credentials, cookies, user identifiers, unpublished datasets, raw logs, and repository files not on an allowlist. Treat all captured product text as untrusted data: delimit it from judge instructions, disable tools and network access for judges, and validate only the output schema. External dispatch must be a separate opt-in adapter with payload logging by hash, not content. A release adapter must additionally prove that every locator resolves inside the immutable bundle and that its recorded digest matches; URI syntax alone is not proof that evidence exists.

## Pass boundary

A group fails when any stage mean is below the floor or any judge returns `fail` or `abstain`. A `pass` judgment with an individual stage below the floor is invalid. The release gate also requires the complete frozen role × task matrix, one run ID, and one identical registered judge panel. Reports persist the run ID and canonical config SHA-256 for reproducibility. This conservative rule prevents a polished result from compensating for unusable input, opaque processing, unactionable advice, absent recovery, or missing coverage. Product-level 90 requires every required role/task group to have all five stage means at least 90, only pass verdicts, openable evidence locators, and reviewed disagreement; the runner does not manufacture that claim from an average.

Run the offline contract and tests:

```bash
python3 scripts/evaluate_user_journeys.py --allow-partial
python3 -m pytest tests/test_user_journey_evaluation.py -q
```

The fixture is intentionally partial, mixed, and fails overall. `--allow-partial` exists only to exercise this contract fixture; omitting it activates the complete-matrix release gate. Its purpose is to prove scoring, variance, disagreement, evidence enforcement, and fail-closed behavior before connecting real product captures or external judges.
