# Newsletter subscriber storage — design (W9-C)

> Status: **v0 design**. v0 implementation exists at
> `web/backend/api/newsletter.py` (flat JSONL, no double opt-in).
> v1 (Buttondown migration) and full GDPR flow are TBD.

## Goals

1. Capture subscribers from the beta site without owning sending infrastructure.
2. Be ready to migrate to a real ESP (Buttondown / Substack) in one move.
3. Privacy-respecting from day 1: easy unsubscribe, data-deletion on request,
   no PII shared with third parties without consent.

## v0 — flat-file JSONL (current)

**Storage**: `web/backend/data/newsletter-subscribers.jsonl` (one row per
signup; append-only with linear-scan dedupe).

**Schema** (one JSON object per line):

```json
{
  "email": "user@example.com",
  "source": "start-here-essay-end",
  "ts": 1715763200,
  "iso": "2026-05-15 12:53:20",
  "ip": "203.0.113.42",
  "ua": "Mozilla/5.0 ...",
  "referrer": "https://phase.bytedance.city/start-here",
  "verified": false,
  "verify_token": null,
  "verified_at": null,
  "unsubscribed_at": null
}
```

**Lifecycle**:

```
[Form submit]
    ↓
[POST /api/newsletter/subscribe]
    ↓ validates email + source, dedupes
[append row {verified=false, verify_token=<uuid>}]
    ↓ (v0.1 — currently NOT implemented; W10 task)
[mock verification email — print to log, not real send yet]
    ↓ user clicks link
[GET /api/newsletter/verify?token=<uuid>]
    ↓ sets verified=true, verified_at=now()
[Subscriber is now eligible for newsletter sends]
```

**v0 gaps (W10 to close)**:

- No double opt-in: every signup is treated as confirmed. Spam risk.
- `verify_token` / `verified` columns are designed but not enforced.
- `GET /api/newsletter/unsubscribe?token=<uuid>` not yet implemented.
- No data-deletion endpoint.

## v1 — Buttondown migration

When subscriber count crosses ~50, migrate to [Buttondown](https://buttondown.email/)
($9/mo). Buttondown gives us:

- Real SMTP sending with deliverability handled.
- Built-in double opt-in.
- Built-in one-click unsubscribe.
- API to import the JSONL.

**Migration script** (planned, `scripts/newsletter/migrate_to_buttondown.py`):

```python
import json, httpx, os
TOKEN = os.environ["BUTTONDOWN_API_KEY"]
with open("web/backend/data/newsletter-subscribers.jsonl") as f:
    for line in f:
        row = json.loads(line)
        if row.get("unsubscribed_at"): continue
        httpx.post(
            "https://api.buttondown.email/v1/subscribers",
            headers={"Authorization": f"Token {TOKEN}"},
            json={
                "email": row["email"],
                "metadata": {"source": row.get("source")},
                # Force send of double-opt-in email — even though we already
                # have implicit consent, re-confirming under the new tool is
                # safer for deliverability.
                "type": "unactivated",
            },
        )
```

After migration: keep the JSONL as **append-only audit log** (also useful if
we ever need to leave Buttondown).

## v2 — separate database table (if needed)

Only if we cross ~10k subscribers AND need queries Buttondown can't do
(per-source funnel analysis, A/B test cohort assignment). At that point:

- `subscribers` table: id, email, source, signup_ts, verified_at,
  unsubscribed_at, esp_id (foreign key to Buttondown).
- `subscriber_events` table: signup / verify / open / click / unsubscribe.
- Postgres. Foreign-key clean. Daily backup.

Until ~10k subs, the JSONL + Buttondown is enough.

## Privacy & compliance

### What we store

- Email (required for sending).
- Source page (for funnel attribution; e.g. `start-here-essay-end`).
- Signup IP + user-agent (for abuse / spam triage only; not used in analytics).
- Verification status + tokens.

We do **not** store:

- Names (we don't ask).
- Open / click events at JSONL layer (Buttondown handles those, separate from PII).
- Demographic / inferred attributes.

### User rights

| Right | How |
|---|---|
| Access (what do you have on me?) | Email the maintainer; we grep the JSONL and reply with your row. |
| Correction (typo in email) | Re-subscribe with the correct email; unsubscribe the old one. |
| Erasure ("right to be forgotten") | Email maintainer; we `unsubscribed_at=now()` + remove from Buttondown. JSONL audit log row deleted within 30 days. |
| Unsubscribe (one-click) | Buttondown footer link, or `GET /api/newsletter/unsubscribe?token=<uuid>` (v0.1 TODO). |
| Portability | Plain-text email + signup date in a JSON file on request. |

### Retention

- Active subscribers: indefinite (until unsubscribed).
- Unsubscribed rows: kept 12 months as suppression list (avoid re-import
  accidents), then deleted.

### Legal basis

- EU/UK (GDPR): consent at signup form (the form copy explicitly states
  "weekly email; can unsubscribe").
- US (CAN-SPAM): unsubscribe link in every email; physical address in footer
  (TBD — currently shows "research preview"; W10 will add Buttondown's
  required address line).
- China (PIPL): same consent rules. Email is not "sensitive personal
  information" under PIPL, but cross-border transfer to Buttondown (US-based)
  requires notice — the signup form's privacy note will reflect this in W10.

## Open questions

1. **Double opt-in (DOI) before W10?** Probably yes — even v0 should send a
   "click here to confirm" email, both for deliverability and to filter
   typos / forms-by-bots. Blocked on: choosing SMTP relay for v0 mocks
   (currently we'd just log to stdout).
2. **Subscriber count as social proof?** `GET /api/newsletter/count` already
   exists and is public. Show "Joined 247 readers" on the form? Probably yes
   after we cross 50.
3. **CCPA "Do Not Sell"?** N/A — we don't sell or share.

## Related

- [`README.md`](./README.md) — pipeline overview.
- `web/backend/api/newsletter.py` — current v0 endpoint.
- `web/frontend/assets/js/newsletter.js` — current v0 signup form.
- `web/frontend/assets/js/analytics.js` — Plausible event tracking.
