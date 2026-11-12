# `/api/analyze/stream` — atomic candidate-report protocol

**Protocol version:** `deep-analysis-report-v2`

**Prompt version:** `deep-report-v2`

**Status:** release contract

**Last updated:** 2026-07-14

## 1. Purpose and trust boundary

`POST /api/analyze/stream` accepts a typed JSON request and returns
`text/event-stream`. It produces one source-bound, candidate-only research
report. A retrieved record is a lead, not proof of an isomorphism, shared
mechanism, causal relationship, successful transfer, or independent review.

The model is untrusted. Model prose is buffered on the server and cannot cross
the public boundary until all of the following pass:

1. complete JSON parsing with non-finite values rejected;
2. the strict nested v2 schema (`extra=forbid`);
3. candidate-claim and Unicode guards;
4. fingerprint revision binding;
5. source-reference allow-list and source/target role checks;
6. server-owned source snapshot and artifact/model binding.

There is no partial-report or fallback-report success path. A failed report
ends with `error`; it never ends with a synthetic `done`.

Implementation:

- `web/backend/api/analyze.py`
- `web/backend/services/deep_report.py`
- `web/backend/services/llm_service.py`

## 2. Transport and privacy

- Use `POST /api/analyze/stream` with `Content-Type: application/json`.
- The retired `GET /api/analyze/stream` always returns `410` and does not
  process query parameters.
- Questions, fingerprints and anonymous identifiers belong only in the JSON
  body, never in a URL or custom header.
- Successful SSE responses use `Cache-Control: no-store`, `Pragma: no-cache`
  and `X-Accel-Buffering: no`.
- Production share URLs are pinned to
  `https://beta.structural.bytedance.city`; client-controlled forwarded host or
  proto headers are not an authority source.

An absent API key uses the product's anonymous tier. A present but invalid key
returns HTTP `401` before report generation.

## 3. Request contract

Unknown fields and implicit type coercions are rejected. Strings are
NFKC-normalized; control, bidi and default-ignorable characters are rejected.

### 3.1 Shared fields

| Field | Type | Rule |
|---|---|---|
| `b_id` | string | Required; 1–120 safe ID characters; must resolve to a KB row. |
| `lang` | `"zh" \| "en"` | Optional, default `"zh"`. |
| `persist` | integer `0 \| 1` | Optional, default `0`; booleans are invalid. |
| `anon_id` | string or null | Optional; normalized length 1–128. |
| `fingerprint` | object or null | Query mode only; exact shape below. |
| `origin_discovery_id` | string or null | Must appear with `origin_contract_version`; pair mode only. |
| `origin_contract_version` | string or null | Must match the current discovery contract. |

Exactly one of `text_a` and `a_id` is required. In pair mode, `a_id` must
differ from `b_id`; equality is rejected by request validation before service,
KB, cache, LLM or cost-ledger work.

### 3.2 Query mode

The selected `b_id` is the source record; the user's question is the target.

```json
{
  "b_id": "source-record-id",
  "text_a": "库存为什么会在补货后反复过冲？",
  "lang": "zh",
  "persist": 0,
  "fingerprint": {
    "source_query": "库存为什么会在补货后反复过冲？",
    "summary": "补货反馈存在时滞，库存可能持续过冲",
    "variables": ["库存", "补货时滞"],
    "constraints": ["交付周期不可立即缩短"],
    "unknowns": ["需求冲击与反馈时滞的相对贡献"],
    "revision": 1
  }
}
```

`text_a` is 1–8,000 normalized characters. `fingerprint.source_query` must
equal the normalized `text_a` exactly. Fingerprint limits are:

- `summary`: 8–1,000 characters;
- `variables`, `constraints`, `unknowns`: at most 12 items each;
- each item: 1–120 characters;
- `revision`: integer 1–1,000.

Raw out-of-scope classification runs before cache initialization, KB lookup,
LLM calls and cost charging. A weak selected candidate is also refused before
the `meta` event.

### 3.3 Pair mode

`a_id` is the source record and `b_id` is the comparison target.

```json
{
  "a_id": "source-record-id",
  "b_id": "comparison-record-id",
  "lang": "zh",
  "persist": 0
}
```

Discovery-origin fields are accepted only when they resolve again to the exact
current public pair. URL values alone never establish provenance.

## 4. Normal SSE state machine

Every `data:` value is one UTF-8 JSON object. There are two successful paths.

### 4.1 Validated pair-cache hit

```text
meta
report_validated
section × 9 (canonical order, unique keys)
persisted × 0..1
done
```

### 4.2 Live generation

```text
meta
generation_progress × 1..n
report_validated
section × 9 (canonical order, unique keys)
persisted × 0..1
done
```

The server may make at most two provider attempts. Each attempt has a 115-second
wall-clock deadline. Retry occurs only for transient network/timeout failures,
HTTP 408/429/5xx, or a schema/claim validation failure. HTTP 400/401/403 and
other permanent 4xx failures are non-retryable.

The failure path is terminal:

```text
error
```

or, when generation began:

```text
meta
generation_progress × 1..n
error
```

No `report_validated`, `section`, `persisted` or `done` event may follow an
`error`.

### 4.3 Event payloads

`meta` is emitted exactly once and includes:

- `generation_id`;
- server-owned source (`a`) and target (`b`) snapshots;
- `is_query_mode`, `lang`, `model`, `artifact_id`;
- `prompt_version`, `schema_version`;
- the optional confirmed `fingerprint`;
- `evidence`, `report_boundary`, `source_binding`, `source_refs`;
- the optional validated `origin_candidate`.

`generation_progress` contains only bounded structural progress:

```json
{"stage":"generating","attempt":1}
```

or:

```json
{"stage":"validating","attempt":1,"received_chars":2048}
```

It never contains model-authored prose. `received_chars` is a monotonic integer
from 0 through 96,000.

`report_validated` is the server receipt:

```json
{
  "generation_id": "g_…",
  "report_sha256": "64-lowercase-hex",
  "schema_version": "deep-analysis-report-v2",
  "from_cache": false
}
```

Each `section` is `{ "key": <canonical key>, "data": <validated value> }`.
Sections are compatibility projections of the already validated complete
report; they are not permission to render partial semantics.

`done` contains the same `generation_id`, `report_sha256`, `from_cache`, and
the complete `report` object. The digest is SHA-256 over compact UTF-8 JSON with
recursive object keys sorted and non-ASCII characters unescaped.

## 5. Client acceptance rules

A conforming client must buffer all semantic content and render only after all
of these checks succeed:

1. exactly one `meta`, then exactly one `report_validated`;
2. exactly nine unique sections in canonical order;
3. zero or one `persisted`, then exactly one `done`;
4. no unknown or post-terminal event;
5. generation ID, schema, prompt, model, language, artifact, fingerprint,
   source binding, source refs and report boundary match the request/meta;
6. the complete nested report schema passes locally;
7. Web Crypto recomputes the canonical report SHA-256 and it equals both the
   validation receipt and `done`.

If Web Crypto is unavailable, JSON parsing fails, rendering throws, or any
ordering/binding/hash check fails, the client must fail closed, clear the
generation state and display no report body.

## 6. Canonical report sections

The full report is strict and contains these nine semantic sections:

1. `shared_structure`: candidate status, formal expression, typed
   `observations` containing `signal_to_check`, `candidate_implication` and
   `status="not_checked"`, plus competing explanations, evidence gaps and
   failure conditions. Observation prose cannot set evidence status.
2. `your_problem_breakdown`: typed variables, dynamics, unknowns and the exact
   optional fingerprint revision.
3. `target_domain_intro`: server-bound source description, one source-backed
   phenomenon, one closed-enum server-controlled source-limitation statement,
   and model-proposed `candidate_methods`.
   Every candidate method is explicitly `unverified_proposal`, declares
   `source_support="not_recorded"` and states what evidence would be required.
4. `structural_mapping`: untested hypothesis mappings with evidence for and
   against, observable tests and failure signals.
5. `borrowable_insights`: one to four model-proposed transfers, each explicitly
   `unverified_proposal` with `source_support="not_recorded"`, prerequisites,
   a target-side application and a failure signal. These proposals do not cite
   the source record as support.
6. `how_to_combine`: bounded steps, assumptions, boundaries and one
   discriminating experiment with distinct candidate/competitor hypotheses,
   expected outcomes labelled by `role="candidate"|"competitor"`, a
   closed-enum server-controlled conditional decision rule, rejecting
   falsification rule and stop rule. `threshold_basis` is always `proposal`
   and `calibration_required` is always true.
7. `research_directions`: `literature_status="not_checked"`, one closed-enum
   server-controlled explanation that precedent/novelty remain unknown, search
   questions, source types and an empty `suggested_references` list.
8. `risks_and_limits`: one to six risks with severity, observable signals and
   stop rules.
9. `action_plan`: two or three ranked measurement/diagnostic/experiment actions
   with closed-enum server-controlled decision/stop copy,
   `threshold_basis="proposal"` and `calibration_required=true`.

Top-level server-bound fields are:

```text
schema_version = deep-analysis-report-v2
evidence_level = candidate
generation_status = validated
source_binding
report_boundary
source_refs
```

`report_boundary` is fixed to candidate-only values: mechanism not verified,
independent review not recorded, and literature not checked.

## 7. Source-role rules

- Every source ref is a server-created `internal_kb` reference.
- The source record and, in pair mode, comparison target each have one unique
  declared ref.
- Only the corresponding-phenomenon description is source-derived and must
  cite exactly the source record.
- Candidate methods and borrowable insights are model proposals, contain no
  source ref, and must not attribute unrecorded methods, deployments or results
  to the source domain.
- The comparison target ref records input provenance only; it cannot be used to
  launder a source claim.
- Source record name/domain/description are overwritten from the current
  server-owned KB row after model validation.

## 8. Persistence and sharing

Persistence is opt-in only (`persist=1`). When creation succeeds, one
`persisted` event appears before `done`:

```json
{
  "id": "opaque-report-id",
  "share_token": "opaque-capability-token",
  "share_url": "https://beta.structural.bytedance.city/report/share/<token>",
  "created_at": "RFC-3339 timestamp",
  "is_partial": false,
  "origin_candidate": null,
  "generation_id": "g_…",
  "report_sha256": "64-lowercase-hex"
}
```

`generation_id` and `report_sha256` must match the receipt and `done`.
`is_partial` is always `false`; v2 never publishes or persists a partial report.
The token is a bearer capability and must not be logged, sent as referrer data,
or exposed to third-party scripts.

Persistence failure does not downgrade a valid report. In that case there is
no `persisted` event and the client must not claim the report was saved or
shared.

## 9. Cache contract

- Query mode never reads or writes the durable generation cache.
- Pair-mode cache identity binds the source and target record digests, KB
  artifact, model, prompt and schema.
- Every cached object is revalidated against the exact current source binding,
  refs, source snapshot, nested schema and candidate-claim guard.
- A stale or forged cache row is ignored and regenerated live.
- `persist=0` performs no report-store creation; query mode also performs no
  cache get or put.

## 10. Error contract

HTTP errors occur before the SSE report state machine:

| Status | Meaning |
|---|---|
| `401` | A supplied API credential is invalid. |
| `404` | A requested KB record does not exist. |
| `409` | Discovery-origin identity is stale or does not match the pair. |
| `410` | Retired GET transport. |
| `422` | Strict body, mode, ID, Unicode, length or fingerprint validation failed. |
| `503` | Search/artifact/provenance service is not ready. |

SSE `error` is `{code, message, retryable}`. Codes are stable and do not expose
provider URLs, credentials or exception text. Representative codes include:

- `out_of_scope`, `candidate_not_supported`, `budget_exceeded`;
- `provider_auth_failed`, `provider_request_rejected`,
  `provider_rate_limited`, `provider_unavailable`;
- `upstream_timeout`, `upstream_unreachable`, `upstream_error`;
- `report_validation_failed`, `report_protocol_failed`,
  `report_binding_failed`, `report_unavailable`.

## 11. Example

```bash
curl --no-buffer \
  --header 'Content-Type: application/json' \
  --header 'Accept: text/event-stream' \
  --data '{"b_id":"source-record-id","text_a":"库存为什么反复过冲？","lang":"zh","persist":0}' \
  'https://beta.structural.bytedance.city/api/analyze/stream'
```

Expected live success:

```text
meta → generation_progress… → report_validated → 9 sections → done
```

Expected validated failure:

```text
meta → generation_progress… → error
```
