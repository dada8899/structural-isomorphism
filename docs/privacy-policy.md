# Privacy policy

_Last updated: 2026-05-13_

This is a short, plain-language privacy notice for the public sites of the
**Structural Isomorphism** research project:

- `structural.bytedance.city` (main site, paper, classes, discoveries)
- `phase.bytedance.city` / `beta.structural.bytedance.city` (subdomains as they ship)

If you have any question or want your data deleted, email
**riazward110@gmail.com**.

## What we collect

We use **Plausible Analytics** (self-hosted, see
[`docs/analytics/plausible-deployment.md`](analytics/plausible-deployment.md))
to understand which pages and findings are most useful. Plausible is a
cookieless, privacy-friendly analytics platform.

For each page view we record:

- The page URL (e.g. `/paper.html`)
- The HTTP referrer (where you came from, e.g. a Google search, an arXiv page,
  Hacker News)
- A coarse device type (desktop / mobile / tablet)
- The user's country, derived from IP at request time (the IP itself is **not
  stored**)
- The browser family (Chrome, Firefox, etc.) and OS family

We do **not** collect:

- Personal identifiers (name, email, account ID — we don't have user accounts)
- Your IP address (it's used in-memory by Plausible to derive country and a
  daily-rotated visitor hash, then discarded — never written to disk)
- Cookies (Plausible is cookieless)
- Cross-site tracking data (we have no third-party trackers, ad networks, or
  social plugins)
- Form contents, scroll depth, click heatmaps, session recordings

## Web server logs

Our web server (nginx) keeps standard access logs for security and operational
reasons. These include the requesting IP address and User-Agent. We retain
these logs for **14 days** and use them only for:

- Diagnosing site outages and abuse (bots / brute-force probing)
- Aggregated weekly traffic reports (with IPs hashed; see
  [`scripts/analytics/parse_nginx_logs.py`](../scripts/analytics/parse_nginx_logs.py))

After 14 days nginx logs are rotated and deleted.

## Cookies

We don't set any cookies on the marketing/research site. The phase-detector
subdomain (`phase.bytedance.city`) may set a single technical cookie for
session state if/when login is added; this would be a first-party,
strictly-necessary cookie and we will update this page when that happens.

## Third parties

- **Fonts**: we load Inter, Noto Serif SC, and JetBrains Mono from Google
  Fonts (`fonts.googleapis.com`). Google may log these requests per their own
  policy. To avoid this you can disable web fonts in your browser.
- **KaTeX**: math rendering uses `cdn.jsdelivr.net` (jsDelivr). jsDelivr may
  log CDN requests per their privacy policy.
- **Marked.js**: same CDN as KaTeX.

We do **not** use Google Analytics, Facebook Pixel, ad networks, or affiliate
trackers.

## Your rights (GDPR / similar)

Even though we collect almost nothing, you have the right to:

- Ask what we have about you (answer: practically nothing, but we'll confirm
  in writing)
- Ask us to delete it (we can delete the Plausible record of your country +
  date if you tell us a rough time window)
- Opt out of analytics entirely by enabling "Do Not Track" in your browser —
  Plausible respects DNT and skips recording when it's set.

To exercise any of these rights, email **riazward110@gmail.com** with a brief
note. We aim to respond within 7 days.

## Legal basis (for EU/UK visitors)

We rely on **legitimate interest** under GDPR Art. 6(1)(f): operating a
research site and understanding which findings reach which audiences. Because
the data is fully pseudonymous, cookieless, and not shared with anyone, the
balancing test favours us. No consent banner is required per EDPB guidance
for non-tracking analytics.

## Changes to this policy

If we change what we collect, we'll update the date at the top of this page
and (for material changes) post a short note on the homepage.

## Contact

Email: **riazward110@gmail.com**

This site is a non-commercial research project. There is no corporate entity
behind it; the data controller is the project maintainer (same email).
