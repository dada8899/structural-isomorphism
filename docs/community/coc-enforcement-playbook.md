# Code of Conduct Enforcement Playbook

A **maintainer-facing** playbook for handling Code of Conduct (COC) reports in
the Structural Isomorphism community (Discord, GitHub, mailing list, off-
server harassment connected to the project). This document is the operational
companion to `CODE_OF_CONDUCT.md` (which states the *what*) and answers the
*how*.

> **Audience**: `@maintainer` role on Discord + GitHub repo maintainers. Do
> not share verbatim outside this group — the *templates* and *escalation
> tiers* are public (linked from `discord-rules.md`), but internal triage
> notes stay sealed.

---

## Step 1 — Triage (who responds)

When a new COC ticket opens in `#coc-reports` or arrives via
`coc@structural.bytedance.city`:

**Default responder**: the BDFL (project founder).
**If the BDFL is unavailable for >48h**: rotating on-call council member
(rotation tracked in `#maintainer-council` pinned message; weekly).
**If conflict of interest**: any maintainer named in the report (or who has
a close personal/professional relationship with named parties) **must
recuse**. Recusal is logged in the ticket; another council member takes over.

A "conflict of interest" includes:
- Being the subject of the report
- Being the reporter (you can't triage your own report)
- Co-authoring a paper with a named party in the past 12 months
- Sharing an employer with a named party
- Personal relationship (friend, partner, family) with a named party

**Triage SLA**: acknowledge ticket within 24h, decision within 7 days for
tier 1-2 cases, within 14 days for tier 3-4 cases.

---

## Step 2 — Gather evidence

Before any response, lock down the evidence:

1. **Restrict the offending message** if still public: in Discord, react with
   a flag emoji and `@maintainer` ping in `#maintainer-council` so the team
   sees it; do *not* delete yet (you'll need the message for the audit log).
2. **Copy raw text** of the message into the ticket: full text, exact
   timestamp, channel name, author Discord ID (right-click → Copy ID with
   Developer Mode on).
3. **Screenshot** with timestamps visible. Discord-stored, not phone-camera.
4. **Capture context**: 5 messages before + 5 messages after, for tone /
   provocation context.
5. **Cross-reference**: search the reported user's recent message history
   for pattern (one-off vs. repeat). Note any past COC tickets involving this
   user — the **prior-record check** is critical for tier selection.

For GitHub COC reports: archive the issue/PR comment via the GitHub API or
a manual screenshot; GitHub edit history is publicly visible but can be
deleted by the author.

For off-server reports (e.g., Twitter harassment connected to a project
member): screenshot, archive via `archive.org`, note the harasser's
identity link to the project (Discord handle, GitHub username, etc.).

---

## Step 3 — Engage

Send the standard first-contact DM (see templates below). Tone: warm but
firm. We're not trying to escalate; we're naming a behavior, requesting a
change, and documenting it. First contact is **always private** (DM in
Discord or email), never a public callout.

**Listen first**: if the reported party responds within 48h with context
(e.g., misunderstanding, joke gone wrong, autism-spectrum communication
mismatch), weigh it. Not all violations are malicious; many are first-time
slips. Tier 1 (warning) handles ~70% of cases.

**Do not negotiate the rule itself.** "I didn't think that was harassment"
is not a defense; the rule is the rule. We can discuss intent (which
affects tier), but not whether the rule applies.

**Loop in the reporter.** Once the maintainer engages with the reported
party, send a brief update to the reporter via the ticket: "We've reached
out to [user]. We'll let you know the outcome within 7 days." Do not share
the reported party's responses unless they consent.

---

## Step 4 — Escalate (4-tier policy)

| Tier | Action | When |
|---|---|---|
| **1** | **Warning** (DM, no public action) | First offense, low severity (e.g., mild snark, off-topic spam, single dismissive comment) |
| **2** | **24-hour timeout** (@muted role) | Second offense after warning, OR first offense of medium severity (e.g., personal attack, repeated tone-policing, mild slur usage that wasn't clearly "ironic") |
| **3** | **7-day timeout** (@muted role) | Third offense, OR first offense of high severity (e.g., targeted harassment, doxxing-adjacent behavior, severe slur usage) |
| **4** | **Permanent ban** (server removal + GitHub block if applicable) | Fourth offense, OR first offense of extreme severity (e.g., doxing, off-server harassment campaign, threats of violence, repeated bigoted language after warning) |

**Severity multipliers** (escalate by one tier if any apply):
- Targeted at a member of a marginalized group on the basis of identity
- Targeted at a newcomer (<7 days in server) — newcomer protection
- Maintainer-on-member abuse — maintainers held to a higher standard
- Coordinated with off-server actors (brigading)

**Severity de-multipliers** (de-escalate by one tier if all apply):
- First offense AND
- Genuine apology offered AND
- No similar pattern in prior 6 months

Tier 4 (permanent ban) requires **council vote** (≥3 of 5 maintainers, BDFL
final). Tiers 1-3 can be enacted by any maintainer unilaterally, with
council notification within 24h.

---

## Step 5 — Log

Every COC action is logged in two places:

**Public-facing summary** (anonymized, posted quarterly in
`#announcements`):
> "This quarter the maintainer council issued: N warnings, N 24h timeouts,
> N 7d timeouts, N bans. Most common rule violated: [rule]. No reports
> remain unresolved."

**Sealed audit log** (private, in `#maintainer-council`, age-encrypted to
the maintainer set, retained 3 years):
- Ticket ID
- Date opened, date resolved
- Reporter (named) and reported party (named)
- Behavior summary (paraphrased to protect victim privacy)
- Triage maintainer + recusals
- Evidence locations (screenshot paths, raw text)
- Decision tier + reasoning
- Appeal status
- Any subsequent re-offense

The sealed log is **never deleted** during the 3-year retention. It is the
only memory of patterns across cases.

---

## Standard templates

### Template A — First-warning DM (tier 1)

```
Hi [name],

I'm reaching out as a maintainer of the Structural Isomorphism community.
A member raised a concern about your message in #[channel] on [date]:

> [quoted text]

Under server rule #[N] ([rule short name]), this isn't something we allow
here. I want to be clear: this is a first-step conversation, not a punishment.
We're asking you to:

1. Acknowledge the message and (if you choose) reach out to anyone harmed.
2. Not do this again. A similar pattern would escalate to a 24-hour
   timeout per our enforcement policy:
   structural.bytedance.city/community/coc-enforcement-playbook

You're welcome to reply with context. We read every reply. If you'd prefer
a voice call to discuss, we can arrange one. We want you to stay and
contribute — the bar is "don't do that thing again," not "be a different
person."

Thanks,
[maintainer name], on behalf of the Structural Isomorphism maintainer council
```

### Template B — Timeout notice (tier 2-3)

```
Hi [name],

A second/third concern was raised about your conduct in
#[channel]/#[GitHub thread]. Specifically:

> [quoted text or summary]

Per our enforcement policy
(structural.bytedance.city/community/coc-enforcement-playbook), this
escalates to a [24-hour / 7-day] timeout starting now. During the timeout
you'll keep server access but can't send messages.

If you believe this decision is wrong, you have 14 days from today to
appeal. The appeal process is:

1. Reply to this DM with your appeal (≤500 words).
2. The maintainer council (excluding the maintainer who issued this) votes.
3. The BDFL makes the final call.

We'll respond within 14 days of receiving your appeal.

Thanks,
[maintainer name]
```

### Template C — Appeal-rejection notice

```
Hi [name],

We've reviewed your appeal regarding the [tier] action issued on [date].
The maintainer council voted [X-Y] to uphold the original decision. The
BDFL has affirmed.

Reasoning:
- [reason 1]
- [reason 2]
- [reason 3]

The original action stands. Your timeout ends on [date].

Per policy, this is the final internal appeal. If you believe the decision
was procedurally unfair (not on the merits — those are settled), you may
write to coc-appeals@structural.bytedance.city; an external mediator (not
on the council) will review procedure only.

Thanks,
[maintainer name], on behalf of the maintainer council
```

### Template D — Permanent ban notice (tier 4)

```
[name],

After review of repeated/severe Code of Conduct violations, the maintainer
council has voted [X-Y] to permanently remove you from the Structural
Isomorphism community. The BDFL has affirmed.

This decision covers:
- Discord server (removed, IP-banned)
- GitHub organization (blocked from new contributions)
- Mailing list (unsubscribed)

The specific violations:
- [violation 1, date]
- [violation 2, date]
- [violation 3, date]

The rationale, in summary:
- [1-2 sentences, factual]

You have 14 days to appeal per the standard process. Note: tier-4 appeals
require new evidence; re-litigation of the original facts is not in scope.

This is a final decision absent successful appeal. We will not respond to
further communication outside the appeal channel.

The maintainer council
```

---

## Appeal process

**Window**: 14 days from the date the action notice was sent.

**Channel**: reply to the DM (Discord) or email
`coc-appeals@structural.bytedance.city` (preferred for tier 4).

**Process**:
1. Appellant submits ≤500-word appeal stating what should be reversed and why
2. Council members not involved in the original decision review
3. Council votes (simple majority of non-recused members)
4. BDFL has final affirmation/override
5. Decision communicated via Template C within 14 days of appeal receipt

**Procedural appeals** (tier 4 only, post-final): one external mediator
(rotating list of 3 external research community maintainers we keep on
standby) reviews **procedure only** — not merits. If procedural failure is
found, the case re-opens with corrected procedure. This is a safety valve
against council capture.

---

## Edge cases

### Maintainer-vs-maintainer

The accused maintainer recuses. The reporting maintainer recuses. The
remaining 3 maintainers handle as a normal tier triage; if conflict
prevents a quorum, an external mediator joins for the single case.
Maintainer-on-maintainer cases default to **one tier higher** than a
non-maintainer case with identical facts (we hold ourselves to a higher
standard).

### Contributor-vs-newcomer (power asymmetry)

Newcomer-on-contributor: standard triage.
Contributor-on-newcomer: escalate by **one tier** (newcomer-protection
multiplier; codified in the severity multiplier list). A first offense
becomes tier 2 instead of tier 1.

### Mass-spam / brigade attacks

If 5+ accounts show similar suspicious patterns within 24h (linked usernames,
similar message content, similar join times), enact temporary server-wide
slowmode (Carl-bot lockdown), then ban the ringleader account and apply tier
2 timeouts to follower accounts pending investigation. Do not engage publicly.
Document the pattern thoroughly — these patterns repeat.

### External doxing / off-server harassment

If a member is doxed or harassed off-server by another member, treat as
tier 4 (immediate permanent ban) regardless of prior record. The harm done
off-server is the same harm done on-server. Coordinate with platform
reporting (Twitter, Reddit, etc.) and consider whether law-enforcement
referral is appropriate. The BDFL coordinates external reporting.

### Reporter retaliation

If a reporter is retaliated against (publicly named, harassed, "called out"
by allies of the reported party), the retaliation is itself a tier-3 or
tier-4 offense, separately. This rule has zero tolerance: it protects the
reporting pipeline itself.

---

## Annual policy review

Every January, the maintainer council reviews:
- All COC tickets from the prior year (sealed log)
- Pattern of tier selections (are we under- or over-escalating?)
- Newcomer survival rate (do newcomers stay after a COC interaction?)
- Whether this playbook needs updates

The review output is a 1-page memo posted in `#announcements` (anonymized
stats) and the full playbook diff (public PR on this file).
