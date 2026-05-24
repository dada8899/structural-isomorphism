# Discord Vanity URL Plan

Discord's `discord.gg/<vanity>` URLs require **Server Boost Level 3** (14
boosts). For a small research community starting from zero, this is a
non-trivial ask — boosts cost real money ($4.99/month/boost) and we don't
want to bootstrap on paid promotion.

This doc lays out the **interim** (no vanity URL) and **target** (post-boost)
strategy.

## Phase 0 — pre-launch (current)

Server doesn't exist yet. The redirect endpoint at
`structural.bytedance.city/discord` returns a `503 server not yet open` with
a "join the waitlist" form pointing at the W9-C newsletter signup.

## Phase 1 — Interim (launch → 100 members)

Goal: zero friction join, no vanity URL needed.

1. **Permanent invite link**: in Discord server settings → Invites → create
   one **never-expiring, no member-cap** invite from `#rules`. Format:
   `discord.gg/abc123xyz` (7-character random code).
2. **Redirect**: `structural.bytedance.city/discord` (nginx 302) → the
   permanent invite URL. Document the redirect target in
   `docs/community/INDEX.md` so any maintainer can update it if the
   invite is leaked / abused.
3. **Tracking**: include UTM params on internal links so we can tell which
   surface (newsletter / GitHub README / paper supplementary / blog) brings
   people. Discord itself doesn't honor UTM, but the redirect logs do.
4. **Backup invite**: keep a second never-expiring invite in a maintainer-only
   note (1Password vault) for rotation if the primary leaks.

This works perfectly fine; vanity URLs are aesthetic, not functional.

## Phase 2 — Vanity URL (post 100+ members + Boost Level 3)

When the server reaches **~100 active members and Boost Level 3**:

1. Server Settings → Vanity URL → claim `structuralisomorphism`
   (verify availability first — Discord vanity URLs are first-come-first-served
   globally)
2. If `structuralisomorphism` is taken, fallback ladder:
   - `structural-isomorphism`
   - `soc-isomorphism`
   - `structural-research`
3. Once claimed, update:
   - The nginx redirect at `structural.bytedance.city/discord` →
     `discord.gg/structuralisomorphism`
   - GitHub README badge → vanity URL
   - Newsletter footer → vanity URL
   - Paper supplementary → vanity URL
   - All `docs/community/*` references
4. Keep the old random-code invite **active** for 30 days post-cutover (some
   bookmarks will use it); after 30 days, revoke.

## Reaching Boost Level 3

Level 3 = 14 boosts. We will **not** ask members to boost ("please pay us
$5/month for cosmetics"). Acceptable paths:

- **Wait organically**: community members who happen to have Nitro boost the
  server because they like it. Common in active communities at ~500+ members.
- **Maintainer co-boost**: if the maintainer council (5 people) all have
  Nitro and each contribute 1-2 boosts, we get 5-10 boosts for free
  (Nitro includes 2 boosts/month). The remaining gap can come from
  organic boosts over 1-2 months.
- **Don't pay for boosts**: paying for boosts is fine for someone else, but
  it would feel weird for a research project. Skip if it requires real cash.

Estimated timeline: 6-18 months from server launch to vanity URL, depending
on growth rate.

## Interim asset checklist

The redirect-only approach is fine for everything except:
- **arXiv paper supplementary**: must include a stable URL. Use
  `structural.bytedance.city/discord` (the redirect), NOT the raw invite
  code, since invite codes can be revoked and would break the paper.
- **GitHub README badge**: same — use the structural.bytedance.city URL.
- **Conference posters / business cards** (if applicable): same.

The redirect URL stays stable for the lifetime of the project. Invite codes
can rotate freely behind it.

## Risk: vanity URL squatting

If someone hostile claims `structuralisomorphism` before we reach Boost
Level 3, we have limited recourse (Discord won't transfer in absence of
trademark grounds). Mitigation:
- Watch the vanity URL availability quarterly via a maintainer-on-call
  reminder
- If it's claimed by a clear squatter (server has <10 members, no activity,
  obvious sit-on-name), file Discord's trust-and-safety report with our
  GitHub repo as priority-of-use evidence
- If squatted by an unrelated active community: choose the fallback
  vanity (`structural-isomorphism`)

## Summary

| Phase | Have | Use |
|---|---|---|
| 0 (now) | nothing | 503 page with waitlist |
| 1 (launch → 100 members) | random invite code | `structural.bytedance.city/discord` redirect |
| 2 (post-Boost L3) | vanity URL | `discord.gg/structuralisomorphism` direct |

Don't pay for boosts. Use the redirect. Update once we organically hit L3.
