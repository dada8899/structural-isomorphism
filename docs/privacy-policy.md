# Privacy policy

_Last updated: 2026-07-14_

This plain-language notice covers the Structural research sites:

- `structural.bytedance.city` — project and research documentation;
- `beta.structural.bytedance.city` — the primary Structural product;
- `phase.bytedance.city` — the Structural Labs · Phase subproduct.

Questions or data requests can be sent to **hello@bytedance.city**.

## What we collect

We collect only what is needed to run the service or what you choose to submit:

| Data | When | Purpose |
|---|---|---|
| Email and account timestamps | You request a Magic Link or create an account | Sign-in, account recovery, and registration notice |
| One-time-link hash, expiry, and used state | A Magic Link is issued | Prevent token replay; the raw token is not stored |
| Necessary session records | You sign in | Keep you signed in and revoke old sessions safely |
| Reports, bookmarks, experiments, and outcomes | You explicitly save them | Provide “My Research” and cross-device continuity |
| Newsletter or waitlist email and source | You submit the form | Send requested research updates |
| Content-free frontend error metadata | The product reports a crash | Diagnose failures using an event name, error type, opaque incident ID, timestamp, and fatal/non-fatal state |
| Optional aggregate analytics | You explicitly enable it | Understand which pages are useful |
| Content-free operational telemetry | You access the sites | Security, abuse prevention, performance, and outage diagnosis |

Anonymous search history, unsynced bookmarks, display preferences, consent
choices, and onboarding state can be stored in your browser. They are not
account data until you explicitly sign in and merge or save them.

Production does **not** collect card details or mock checkout submissions.
There is no live paid checkout. The retired checkout simulator returns
`410 Gone` before recording submitted fields.

New newsletter, waitlist, and retired-checkout rows do not store IP address,
User-Agent, or referrer. Frontend crash records do not persist the error
message, stack, page URL, User-Agent, session ID, IP address, query, cookie, or
referrer. Nginx access telemetry is limited to an opaque request ID, request
method, status, response byte count, request duration, and upstream duration;
it does not include the IP address, URL/path, query string, User-Agent, cookie,
or referrer. Application logs use route templates rather than raw paths and
drop arbitrary fields, exception messages, and tracebacks.

## What we do not do

- We do not sell personal data.
- We do not use ad networks, social pixels, or session-recording tools.
- We do not store passwords; sign-in uses one-time email links.
- We do not treat saved research outcomes as independent scientific proof.
- We do not use client-supplied mock tiers to grant production entitlements.

## Cookies and local storage

Signed-in sessions use necessary `HttpOnly`, `Secure`, `SameSite=Lax` cookies.
They are not available to page JavaScript. Local storage may hold theme,
consent, onboarding, anonymous history, and unsynced bookmark state.

Self-hosted Plausible analytics loads only after consent. It does not use
tracking cookies or store raw IP addresses. Do Not Track disables optional
analytics. Capability-bearing report-share routes never load analytics, even
after consent, so a share token is not sent to the analytics service.

## Email delivery and other processors

We use an email delivery provider only to send one-time sign-in links,
registration notices, and updates you requested. We may also use:

- self-hosted Plausible for consented aggregate analytics;
- optional exception monitoring, if enabled, using only content-free event
  IDs, error types, status codes, and opaque correlation/incident IDs;
- jsDelivr for selected public JavaScript assets;
- hosting and network providers required to operate the sites.

These providers may process the minimum technical data needed to deliver their
service. Browser fonts are served by the site rather than fetched from Google
Fonts at runtime.

The exception-monitoring boundary does not export request URLs, headers,
cookies, bodies, user records, breadcrumbs, messages, stack variables, or raw
transactions.

## Retention

- Magic Links become unusable after 15 minutes and cannot be replayed.
- Session cookies last at most 30 days and can be revoked earlier.
- Account records and explicitly saved assets remain until you delete the
  account, subject to limited security records required to enforce deletion.
- Newsletter records remain until you unsubscribe or request deletion.
- Content-free frontend error logs use size-bounded rotation. The current
  service keeps the active segment and one recent rotated segment; it does not
  promise a fixed calendar retention period.
- Web-server access logs are retained only as operationally needed and follow
  the host's rotation policy; no fixed public calendar period is promised.
- Optional analytics are aggregate and do not retain raw IP addresses.

## Your rights

### Access and export

Sign in to the Structural primary product and open
[My Research and account controls](https://beta.structural.bytedance.city/reports).
The authenticated `/api/me/export` operation downloads a JSON copy of the
account and linked server-side assets without modifying them.

### Permanent deletion

Use the same account controls to confirm permanent deletion. The authenticated
`/api/me/delete` operation removes the account and linked server-side assets and
revokes active sessions. This action cannot be undone.

The old email-plus-code `/api/privacy/export` and `/api/privacy/delete`
operations are retired and return `410 Gone` in production. They must not be
used as a substitute for identity-bound account controls.

If you cannot sign in, email **hello@bytedance.city**. We may ask you to prove
control of the relevant email or account before exporting, correcting, or
deleting data. We aim to answer manual requests within seven days.

### Analytics choice

You can reject optional analytics, change the choice through “Manage cookies,”
or enable Do Not Track in your browser.

## Security

Secrets, raw Magic Link tokens, and passwords are not written to public project
documents. Authentication and user assets are stored outside the Git checkout
in production. Conflicting credentials fail closed, and account deletion
revokes both direct and cross-product sessions.

No online service can promise absolute security. If you believe you found a
problem, contact **hello@bytedance.city** without including passwords, tokens,
or other secrets in the message.

## Legal basis

Where GDPR or similar law applies, necessary service operation and security are
based on legitimate interests or contract-like service delivery; optional
analytics and requested email updates rely on consent. You may withdraw consent
for optional processing at any time.

## Changes and controller

Material changes update the date above. The rendered `/privacy` pages and the
actual authenticated data controls take precedence over older historical
documents. Structural is currently a non-commercial research project rather
than a separate corporate entity; the project maintainer is the data controller.
