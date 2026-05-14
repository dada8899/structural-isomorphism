# Privacy policy

_Last updated: 2026-05-15_

This is a short, plain-language privacy notice for the public sites of the
**Structural Isomorphism** research project:

- `structural.bytedance.city` (main site, paper, classes, discoveries)
- `phase.bytedance.city` / `beta.structural.bytedance.city` (subdomains as they ship)

If you have any question or want your data deleted, email
**riazward110@gmail.com** — or use the self-service endpoints documented
below (§ "Your rights").

## What we collect

### Default (always on)

We use **Plausible Analytics** (self-hosted, see
[`docs/analytics/plausible-deployment.md`](analytics/plausible-deployment.md))
to understand which pages and findings are most useful — but **only after
you opt in** via the cookie consent banner. Plausible is a cookieless,
privacy-friendly analytics platform. Without consent, no analytics script
is loaded at all.

When loaded with your consent, for each page view we record:

- The page URL (e.g. `/paper.html`)
- The HTTP referrer (where you came from)
- A coarse device type (desktop / mobile / tablet)
- The user's country, derived from IP at request time (the IP itself is **not
  stored**)
- The browser family (Chrome, Firefox, etc.) and OS family

### Phase Detector subdomain (`phase.bytedance.city`)

The phase-detector app collects a small amount of data to make the product
work:

| Data | When | Why | Retention |
|---|---|---|---|
| **Session ID** (random, in localStorage) | First visit | Group error reports + history | Cleared when you clear browser storage |
| **Error reports** | Frontend crash | Debug + fix bugs | 90 days, rolling |
| **Newsletter signups** (email + source) | You submit | Send research updates | Until you unsubscribe |
| **Mock checkout entries** (email + name + last-4) | You submit on /pricing | Evaluate PMF (no real charges) | Indefinite, deletable on request |
| **Search history** (per-device, anonymous) | You search | Reload recent queries | Local-only (your device) |

We do **not** collect:

- Personal identifiers tied to an account (we don't have user accounts yet)
- Your IP address as a stored identifier (in-memory only; not written to disk
  by Plausible)
- Cross-site tracking data — no third-party trackers, ad networks, or social
  plugins
- Form contents beyond what you explicitly submit, scroll depth, click
  heatmaps, session recordings

## Web server logs

Our web server (nginx) keeps standard access logs for security and operational
reasons. These include the requesting IP address and User-Agent. We retain
these logs for **14 days** and use them only for:

- Diagnosing site outages and abuse (bots / brute-force probing)
- Aggregated weekly traffic reports (with IPs hashed; see
  [`scripts/analytics/parse_nginx_logs.py`](../scripts/analytics/parse_nginx_logs.py))

After 14 days nginx logs are rotated and deleted.

## Cookies & local storage

We don't set any tracking cookies. We use **localStorage** (a different
browser API than cookies) to store:

- Your theme preference (`phase_theme`)
- Your cookie consent choice (`cookie_consent_v1`) — this records *which*
  optional analytics you opted into, so we don't ask again on every visit
- Your random session ID (`session_id`) — used to group error reports from
  the same browsing session
- Onboarding state (`phase_tour_seen`) — so the welcome tour doesn't loop

localStorage entries are not transmitted to our servers automatically; only
the session ID gets attached to error reports if you trigger a crash.

### Cookie consent banner

On your first visit, a banner asks you to choose:

- **Essential only** (default if you dismiss) — keep the strictly necessary
  localStorage entries above; no analytics script is loaded.
- **Accept all** — same as essential, plus we load Plausible (still no
  cookies, just an analytics script).
- **Customize** — toggle analytics on/off independently.

Marketing cookies are **disabled and inapplicable** — we don't run any
marketing pixels. The checkbox is shown for transparency but cannot be
turned on. We respect the **Do Not Track (DNT)** header: if your browser
advertises DNT, analytics is auto-disabled and the banner doesn't appear.

You can change your mind anytime via the "Manage cookies" link in the
footer (or the button on `/privacy`).

## Third parties

- **Plausible Analytics** (self-hosted) — only loaded if you opt in. See
  [Plausible's data policy](https://plausible.io/data-policy).
- **Fonts**: we load Inter, Noto Serif SC, and JetBrains Mono via Next.js
  `next/font/google` which fetches at build time and self-hosts to avoid
  runtime requests to `fonts.googleapis.com`. The marketing site (separate
  codebase) may still load from `fonts.googleapis.com` directly.
- **KaTeX & Marked.js**: research site loads from `cdn.jsdelivr.net`
  (jsDelivr). jsDelivr may log CDN requests per their privacy policy.

We do **not** use Google Analytics, Facebook Pixel, ad networks, or affiliate
trackers.

## Your rights (GDPR / similar)

You have the following rights regardless of jurisdiction:

### Access / export

```
GET /api/privacy/export?email=<your@email>&code=<6-digit-verification>
```

Returns a JSON document with every record we hold tied to that email or the
session ID you supply. Rate-limited to **1 request per hour per email** to
prevent enumeration abuse.

The verification code is currently mocked (always `123456` in dev / first
real deployment will email a one-time code). The endpoint shape will stay
stable when the real email flow ships.

### Delete

```
DELETE /api/privacy/delete?email=<your@email>&code=<6-digit-verification>
```

Removes records from all data files (newsletter, mock checkouts, error log).
An **audit log entry** stays — recording that a delete was requested, with
the *email and time only* — for compliance traceability. The audit log
itself does not contain the deleted data.

A mock confirmation email is logged (real email send wired when the email
service is configured).

### Object / opt out

- Enable "Do Not Track" in your browser — analytics will auto-disable on
  next page load
- Click "Manage cookies" in the footer and turn off analytics
- Email **riazward110@gmail.com** for any request not covered by the self-
  service endpoints

We aim to respond to manual requests within **7 days**.

## Legal basis (for EU/UK visitors)

For **default analytics-free browsing**, we rely on **legitimate interest**
under GDPR Art. 6(1)(f). For **analytics with your consent**, we rely on
**Art. 6(1)(a) — consent**, captured via the banner and revocable anytime.

## Changes to this policy

If we change what we collect, we'll update the date at the top of this page
and (for material changes) post a short note on the homepage. The Next.js
SSR version at `https://phase.bytedance.city/privacy` is kept in sync with
this Markdown file; if the two disagree, the rendered page (with its more
recent timestamp) is authoritative.

## Contact

Email: **riazward110@gmail.com**

This site is a non-commercial research project. There is no corporate entity
behind it; the data controller is the project maintainer (same email).
