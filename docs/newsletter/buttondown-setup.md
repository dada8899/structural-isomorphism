# Buttondown setup for the Structural Signals newsletter

**Status (W8-D / 2026-05-13):** Code paths are wired, account is **not yet
provisioned**. Once the account exists, no further code changes are required
— set `BUTTONDOWN_API_KEY` in `phase-api.env` on the VPS and signups will
start forwarding automatically.

## Why Buttondown

| Choice | Why |
|---|---|
| **Buttondown** ✅ | Cheap (free up to 100 subscribers, $9/mo to 1k), simple HTTP API, supports markdown, low setup overhead, no template engine to learn. |
| Substack | Free but no API for programmatic sends; vendor-locked. |
| ConvertKit | $25/mo entry; bloated for our 1 newsletter / week need. |
| Mailgun + own template | More control but we'd write a sender loop + bounce handling. Pre-Alpha — not worth the cycles. |
| Self-host (Listmonk / Mailtrain) | Free but VPS-time vs. value tradeoff is bad pre-Alpha. |

Decision: **Buttondown** until ≥500 subscribers, then re-evaluate.

## Provisioning (manual, ~10 min — needs user action)

1. Go to https://buttondown.email/register
2. Sign up with the project email
3. Pick a newsletter slug — proposed: `structural-signals`
4. Confirm sending domain: use a subdomain so it doesn't pollute the main domain reputation
   - DNS: `CREATE CNAME newsletter.bytedance.city → buttondown.email` (DNSPod)
   - Buttondown will verify SPF/DKIM after the CNAME propagates
5. In Buttondown → Settings → API → copy the API token
6. SSH to VPS: `vi /root/Projects/structural-isomorphism/.env` (or wherever phase-api env lives), add:

   ```bash
   BUTTONDOWN_API_KEY=btn_pat_xxxxxxxxxxxxxxxxxxxxxxxxx
   ```

7. Restart phase-api: `systemctl restart phase-api`
8. Test: from a non-existing test email, sign up via https://phase.bytedance.city → verify it appears in Buttondown subscribers list.

## Code touchpoints (already wired)

- `v4/product/d1_phase_detector/api/main.py::_maybe_forward_buttondown`
  - No-op when `BUTTONDOWN_API_KEY` is unset (no error path noise)
  - On any HTTP error from Buttondown: swallowed (DB is source of truth; backfill cron can later re-push missed signups)
- `scripts/newsletter/send_weekly.py` — composes + sends the weekly digest

## Backfill safety net

If Buttondown forwarding fails silently for a while, the DB has every signup.
To backfill manually:

```bash
sqlite3 /var/lib/phase-api/d1.sqlite \
  "SELECT email, source FROM waitlist WHERE confirmed = 0 ORDER BY signed_up_at;"
```

Then bulk-import via Buttondown's CSV importer or the API.

## Open items (post-W8-D)

- [ ] User authorizes spend (~$0-9/mo)
- [ ] DNS CNAME added
- [ ] First test send (to user + 2 friends)
- [ ] Cron entry on VPS: `weekly-digest` job at Sunday 22:00 Asia/Shanghai
- [ ] Decide: confirmed opt-in vs. single opt-in (legal: stick with double opt-in for EU users — Buttondown handles this if toggled on)
