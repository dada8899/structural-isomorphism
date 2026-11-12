# API

_Last updated: 2026-07-14_

Structural's primary product API is served from:

```text
https://beta.structural.bytedance.city/api
```

The generated [OpenAPI artifact](api/openapi.json) is the candidate release's
route, request, response, and status-code contract. It is regenerated from the
FastAPI application and checked byte-for-byte in the release gate. Production
interactive Swagger and ReDoc pages are disabled. Before treating the
committed artifact as the live contract, verify that `/api/version` and the
runtime attestation identify the same deployed release.

The schema is dependency-sensitive. Generate it only with the backend's
declared release lock:

```text
make openapi-env       # explicit one-time environment setup
make openapi-generate
make openapi-check
```

The generator rejects a FastAPI, Pydantic, or Starlette version that differs from
`web/backend/requirements.txt`; CI runs the same check after installing that
file. Deployment must separately attest that the active service environment
matches the release lock before this target contract is called production.

## What the API does

The public product surface supports:

- retrieving cross-domain **candidates** from the internal knowledge base;
- drafting evidence-bounded analyses, mappings, and method-transfer plans;
- inspecting candidate provenance, counterevidence, and validation status;
- email Magic Link authentication;
- saving reports, research bookmarks, experiments, and outcomes to an account;
- exporting or permanently deleting the signed-in account and its linked data.

Search scores and generated mappings are retrieval or drafting signals. They
do not prove structural identity, a shared mechanism, or successful transfer.
The exact evidence boundary travels with each result and is authoritative over
older prose examples.

## Authentication

Authentication depends on the endpoint:

- Public read endpoints can be called anonymously within their rate limits.
- Account endpoints use the secure session established by the email Magic Link
  flow. Cookie-authenticated mutations also enforce same-origin checks.
- Selected programmatic endpoints accept `X-API-Key`; admin routes require an
  admin credential. A test-looking key is not a production entitlement.
- Conflicting direct and cross-product credentials fail closed instead of
  choosing one account silently.

Consult each OpenAPI operation for its actual security and error responses;
there is no blanket promise that every endpoint is anonymous.

## Operational probes

Two read-only endpoints are useful when validating a deployment:

```text
GET /api/version
GET /api/health?deep=1
```

The deep health response verifies the current knowledge-base artifact, model,
embedding shape, and required services. HTTP 200 from the homepage alone is not
a sufficient health signal.

## Retired compatibility endpoints — release target

The legacy checkout simulator and email-code privacy endpoints are retained
only for isolated development compatibility tests. For the release described
by the committed OpenAPI artifact, after that release is deployed and runtime
attestation matches:

- `POST /api/checkout/mock` returns `410 Gone` and records nothing;
- mock tier headers, cookies, and query parameters cannot unlock paid limits;
- `/api/privacy/export` and `/api/privacy/delete` return `410 Gone`;
- signed-in users use `/api/me/export` and `/api/me/delete` instead.

Structural currently has no live paid checkout or purchasable entitlement.

## Phase subproduct

`https://phase.bytedance.city` is a Structural Labs subproduct with its own
frozen-demo API. Its market snapshot contains 597 tickers with demo provenance
and a published NULL backtest; it is not a real-time feed or investment signal.
Use the Phase route contracts for that subproduct rather than assuming the beta
API paths are interchangeable.

## Stability

This is a research beta. Backward compatibility is maintained where practical,
but the OpenAPI artifact from the attested deployed release and response
`schema_version` fields—not historical session documents or an unreleased
working-tree artifact—define the live contract.
