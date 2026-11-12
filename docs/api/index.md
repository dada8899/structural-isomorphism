# Structural API reference

_Last updated: 2026-07-14_

This directory contains the generated API contract for the Structural beta
product.

- Primary API base: `https://beta.structural.bytedance.city/api`
- Candidate release contract: [`openapi.json`](openapi.json)
- Plain-language guide: [`../api.md`](../api.md)

The OpenAPI file is generated from the current FastAPI app and checked
byte-for-byte during release. Do not manually edit it. Production Swagger and
ReDoc routes are intentionally disabled; serve this directory locally if an
interactive viewer is required.

The contract describes both anonymous and authenticated operations. Security
requirements are per operation: account routes use an email Magic Link session,
selected programmatic routes accept `X-API-Key`, and admin routes require admin
authorization. There is no global anonymous-access or paid-tier promise.

Candidate terminology is intentional. Search, mapping, analysis, daily, and
discovery operations can return items for review; they do not by themselves
establish a verified isomorphism or mechanism transfer.

Legacy compatibility routes are marked deprecated. In the release represented
by this artifact, checkout and email-code privacy routes return `410 Gone`,
while account export and deletion use the signed-in `/api/me/*` flows. Treat
that as the live production contract only after `/api/version` and the public
runtime attestation match the deployed release.
