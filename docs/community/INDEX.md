# `docs/community/` — Index

Landing page for everything community-facing in the Structural Isomorphism
project. One-line summary per doc, grouped by purpose.

> **Status keys**: ✅ shipped & live · 🟢 ready, awaiting launch · 🟡 draft ·
> ⚪ scoped, not yet built.

---

## Discord server (W9-E)

🟢 [`discord-setup.md`](./discord-setup.md) — server name, 8 categories,
22 channels, 5 roles, permission matrix, slowmode policy. 10-min admin
flow to spin up.

🟢 [`discord-bot-config.md`](./discord-bot-config.md) — Carl-bot
(welcome + auto-role), TicketTool (COC reports), GitHub bot (PR/release
notifications), arXiv RSS bot. Step-by-step install + permission
ordering + disaster fallbacks.

🟢 [`discord-welcome-message.md`](./discord-welcome-message.md) — the
~300-word auto-DM new members receive. 3-step orientation (rules → intro
→ role) + pointers to good-first-issues, newsletter, COC.

🟢 [`discord-rules.md`](./discord-rules.md) — 10 server rules pinned in
`#rules`, aligned with `CODE_OF_CONDUCT.md`. Covers harassment,
on-topic, commercial promo, pre-reg, COI, doxing, reporting flow.

🟢 [`coc-enforcement-playbook.md`](./coc-enforcement-playbook.md) —
**maintainer-facing** 5-step playbook (triage → gather → engage →
escalate → log) + 4-tier escalation (warning / 24h / 7d / ban) + 4
standard DM templates + 14-day appeals process + 4 edge cases
(maintainer-vs-maintainer, contributor-vs-newcomer, brigade, doxing).

🟢 [`discord-vanity-url-plan.md`](./discord-vanity-url-plan.md) — interim
nginx redirect (`structural.bytedance.city/discord`) until server hits
Boost L3 (~100 members), then claim `discord.gg/structuralisomorphism`.
Don't pay for boosts.

## Code-of-Conduct & governance (W9-B / project root)

✅ [`/CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md) — the *what*: rules
& values. The *how* lives in `coc-enforcement-playbook.md` above.

✅ [`/GOVERNANCE.md`](../../GOVERNANCE.md) — BDFL + 5-member maintainer
council + decision process + recusal rules.

✅ [`/CONTRIBUTING.md`](../../CONTRIBUTING.md) — how to make your first
PR; quality bar; review process; conventional commit format.

✅ [`/.github/SECURITY.md`](../../.github/SECURITY.md) — security-issue
reporting (private channel, 90-day disclosure window).

✅ [`NUMFOCUS_APPLICATION.md`](./NUMFOCUS_APPLICATION.md) — Fiscally
Sponsored Project application draft for NumFOCUS membership.

## First-contribution onramps (W9-A)

✅ [`good-first-issues/INDEX.md`](./good-first-issues/INDEX.md) — index of
15 sized-down first-time-contributor issues across datasets, classes,
tests, docs, tutorials, perf, i18n, web. Each in its own
`NNN-<category>-<slug>.md` file with scope, expected effort (≤4h),
acceptance criteria, mentor.

## Outreach & roadmap (W7-C)

✅ [`/docs/future/W7-C-community-roadmap-2026-05-13.md`](../future/W7-C-community-roadmap-2026-05-13.md)
— umbrella roadmap that schedules W9-A through W9-E (and beyond).

✅ [`/docs/newsletter/buttondown-setup.md`](../newsletter/buttondown-setup.md)
— Buttondown account config for the monthly digest.

✅ [`/docs/newsletter/templates/weekly-digest-template.md`](../newsletter/templates/weekly-digest-template.md)
— template for the recurring digest.

✅ [`/docs/newsletter/samples/digest-2026-05-13.md`](../newsletter/samples/digest-2026-05-13.md)
— sample digest issue.

## Scoped, upcoming

⚪ **W9-C newsletter v2** — issue #2, signup-to-issue funnel polish.

⚪ **W9-D launch announcement** — coordinated HN / arXiv / Twitter / mailing-list
announcement post.

⚪ **Maintainer runbook** — daily/weekly maintainer chores, ticket SLAs,
on-call rotation. Currently lives partially in `coc-enforcement-playbook.md`
and `discord-bot-config.md`. Extract & consolidate in a future wave.

⚪ **Annual COC review memo** — January each year, posted in
`#announcements`. First instance: January 2027.

---

## Quick links for new community members

If you're a **new member** landing here, start with:

1. [`/CODE_OF_CONDUCT.md`](../../CODE_OF_CONDUCT.md) — what we expect
2. [`/CONTRIBUTING.md`](../../CONTRIBUTING.md) — how to contribute
3. [`good-first-issues/INDEX.md`](./good-first-issues/INDEX.md) — pick a
   first task

If you're a **maintainer** landing here:

1. [`coc-enforcement-playbook.md`](./coc-enforcement-playbook.md) — when
   a ticket lands
2. [`discord-bot-config.md`](./discord-bot-config.md) — when a bot
   breaks
3. [`/GOVERNANCE.md`](../../GOVERNANCE.md) — when a decision needs
   council vote

If you're an **admin spinning up the Discord server**:

1. [`discord-setup.md`](./discord-setup.md) — the 10-minute setup flow
2. [`discord-bot-config.md`](./discord-bot-config.md) — install bots in
   order
3. [`discord-welcome-message.md`](./discord-welcome-message.md) — paste
   into Carl-bot welcome template
4. [`discord-rules.md`](./discord-rules.md) — pin in `#rules`
5. [`discord-vanity-url-plan.md`](./discord-vanity-url-plan.md) — set up
   the redirect; defer vanity URL

---

*Last updated: W9-E (2026-05-15). PRs welcome on any of the above.*
