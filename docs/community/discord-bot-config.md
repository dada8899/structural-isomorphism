# Discord Bot Configuration

We use **off-the-shelf OSS / freemium bots** rather than writing our own. This
keeps maintenance burden low and avoids us owning a custom bot service. The
only exception is the **arXiv bot**, which is a small custom feed because no
free general-purpose bot handles arXiv keyword filters well.

## 1. Carl-bot — auto-role + welcome

**Why Carl-bot over MEE6**: Carl-bot's free tier covers everything we need
(reaction roles, welcome, automod), while MEE6 paywalls custom welcome
messages. Either works; pick one and stick with it.

### Install

1. Visit `https://carl.gg` → "Add to Discord"
2. Select the `Structural Isomorphism` server
3. Grant requested permissions (Manage Roles, Manage Channels, Read Messages,
   Send Messages, Embed Links, Read Message History, Manage Messages,
   Manage Nicknames, Kick Members, Ban Members)
4. The bot lands with `@bot` role; move `@bot` **above** `@member` but
   **below** `@contributor` in the role hierarchy

### Configure auto-role on join

1. In Carl-bot dashboard → server → **Autoroles**
2. Add `@member` to "On Join" autoroles
3. Toggle "Enabled" ON

Result: every new member is auto-assigned `@member` and can read public
channels immediately.

### Configure welcome DM

1. Dashboard → **Welcome** → enable DM mode (not in-channel — DM is private
   and doesn't spam `#introductions`)
2. Paste the content from `discord-welcome-message.md` into the welcome
   template field
3. Variables to use: `{user.mention}` and `{server.name}`
4. Save & test by sending yourself a test event

### Configure reaction role for `@subscriber`

1. Dashboard → **Reaction Roles** → New Reaction Role
2. Channel: `#announcements`
3. Message: pin a message with text "React with 📬 to opt into newsletter
   pings. We'll @subscriber you in announcements."
4. Emoji: 📬 → role: `@subscriber`
5. Type: "normal" (toggle on / off)

### Configure automod

1. Dashboard → **Automod**
2. Enable: invite-link blocker (block Discord invites except to known
   partner servers); excessive caps filter (>70% caps in 8+ char message);
   excessive mentions (>5 mentions / message)
3. Action on violation: delete + warn (do NOT auto-mute on first offense —
   automod false-positives hit newcomers worst)

## 2. TicketTool — COC report channel

**Purpose**: anyone can open a private 1-on-1 ticket with the maintainer
council to report a COC violation without making it public.

### Install

1. Visit `https://tickettool.xyz` → "Add Bot"
2. Select the server, grant permissions
3. Move `@bot` role above all non-maintainer roles

### Configure

1. Dashboard → server → **Panel**
2. Create panel with:
   - Channel: `#coc-reports`
   - Panel title: "Report a Code of Conduct violation"
   - Panel description: "Open a private ticket to report harassment, abuse,
     or any COC violation. Only the maintainer council will see your report.
     Anonymous reports are accepted but harder to act on."
   - Button text: "Open private ticket"
   - Ticket category: 📩 COC Tickets (auto-create)
   - Pinged on open: `@maintainer`
   - Permissions for opener: read + write inside their own ticket only
   - Permissions for `@maintainer`: read + write all tickets
   - Permissions for everyone else: hidden

3. Configure ticket transcript: ON, save to a `#ticket-logs` channel visible to
   `@maintainer` only

### Set up ticket templates

A first-message template that auto-posts when the ticket opens, prompting the
reporter for:
1. What happened (1-2 paragraphs)
2. Where it happened (channel / DM / off-server)
3. Who was involved (@mention if you can)
4. Links / screenshots if available
5. What outcome you're hoping for

## 3. GitHub bot — PR / issue notifications

**Source**: the official GitHub bot (`gh.io/discord` instructions).

### Install

1. In `#changelog` channel, type `/github subscribe dada8899/structural-isomorphism`
2. Authorize when prompted
3. Default subscription is: pulls, issues, releases, deployments
4. Adjust with `/github subscribe dada8899/structural-isomorphism issues
   pulls releases` (drops the noisy deployments stream)
5. Verify: open a test PR, confirm the embed lands in `#changelog`

### Filter to important events only

To prevent `#changelog` becoming overwhelming, also run:

```
/github subscribe dada8899/structural-isomorphism -issues:comments
/github subscribe dada8899/structural-isomorphism -pulls:reviews
```

This keeps PR-opened / PR-merged / issue-opened / release events but drops
every code-review comment.

## 4. arXiv bot — daily keyword digest

There's no canonical free arXiv-to-Discord bot. Two options:

### Option A — RSS bot (zero custom code)

1. Install `MonitoRSS` (free OSS): `https://monitorss.xyz`
2. Add feed: `http://export.arxiv.org/api/query?search_query=all:%22self-organized+criticality%22+OR+all:%22structural+isomorphism%22+OR+all:%22phase+transition%22+AND+cat:q-fin*&max_results=20&sortBy=submittedDate&sortOrder=descending`
3. Channel: `#arxiv-watch`
4. Filter: only post entries newer than 24h
5. Cron: every 6 hours

This catches ~5-15 papers / day across our keyword set. Tune the query as the
research direction sharpens.

### Option B — Custom small bot (later, if A is too noisy)

If RSS-based filtering is too coarse, write a 100-LOC Python bot that:
- Pulls arXiv API daily at 09:00 UTC
- Filters by our embedding similarity to a seed set of "good" papers we curated
- Posts top 5 with a brief why-this-matters note

Defer to Phase 2; not blocking community launch.

## 5. Bot role hierarchy

Final role order (top → bottom):

```
@maintainer
@bot                      (Carl-bot, TicketTool, GitHub, MonitoRSS)
@contributor
@verified-researcher
@subscriber
@member
@muted
@everyone
```

Bots must sit **above** the roles they manage. Carl-bot needs to assign
`@member` and `@subscriber`, so `@bot` must be above both. But `@bot` sits
below `@maintainer` so humans can override / kick a misbehaving bot.

## 6. Backup / disaster plan

If Carl-bot or TicketTool goes down:

- **Carl-bot down**: new members still join (Discord native), but auto-role and
  welcome DM stop. Manually assign `@member` in batches. Restore when bot
  recovers.
- **TicketTool down**: COC reports route to DMing `@maintainer` directly until
  recovered. Mention this fallback in `#rules`.
- **GitHub bot down**: `#changelog` gets stale. Not urgent; can backfill.
- **arXiv RSS down**: `#arxiv-watch` gets stale. Not urgent.

Document recovery steps in `MAINTAINER_RUNBOOK.md` (W9-A scope or later).
