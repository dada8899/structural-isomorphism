# Discord Welcome Message (auto-DM)

This is the auto-DM that Carl-bot sends every new member when they join the
**Structural Isomorphism** server. Aim: ~300 words, warm, three concrete next
steps, no walls of text.

---

## Welcome DM template

```
Hey {user.mention} — welcome to **Structural Isomorphism**.

We're a small research community studying when seemingly unrelated systems
(financial crashes, neural avalanches, wildfires, DeFi liquidations) follow
the same mathematical signatures, and what those signatures tell us about
how fragile a system is. The code, data, and papers all live in the open at
`github.com/dada8899/structural-isomorphism`.

Three things to do in the next 5 minutes:

**1. Read the rules.** Head to #rules and skim. Short version: be kind, stay
on topic per channel, no harassment, no spam. We take Code of Conduct
violations seriously — if something feels off, open a private ticket in
#coc-reports.

**2. Introduce yourself in #introductions.** A sentence or two is plenty:
your name (or handle), where you found us, and one thing you're curious
about. Researchers, engineers, students, and curious tinkerers are all
welcome — no PhD required.

**3. Pick a role.** React to the 📬 message in #announcements to get pinged
when we ship something or post research updates. If you've got an academic
affiliation and want access to #pre-registrations and #company-deep-dives,
post a request in your #introductions message (we'll DM you for ORCID).
Once a PR of yours gets merged on GitHub, the @contributor role and access
to #contributors-only land automatically.

Looking for a starter task? `github.com/dada8899/structural-isomorphism/labels/good-first-issue`
has ~20 issues sized for ~2-hour first contributions, ranging from docs
fixes to validation harness extensions.

Subscribe to the newsletter (`structural.bytedance.city/newsletter`) for a
monthly digest of releases, papers, and community highlights — strictly
opt-in, never spam.

Stuck on anything? #newcomers is the no-dumb-questions channel — actually,
unironically, no question is too basic there. Maintainers and contributors
hang out and answer.

Glad to have you. See you in the channels.

— The maintainers
```

## Notes for the admin pasting this

- Replace `{user.mention}` with Carl-bot's variable syntax in the dashboard
  (it's `{user.mention}` literal — Carl-bot interpolates).
- Don't add emoji-heavy flourishes; the tone is intentionally low-key and
  text-forward. Members opt into a research community, not a hype Discord.
- Word count target: 300 (currently 290). If you trim, keep the 3-step
  orientation and the COC pointer.
- Test by joining the server with a burner Discord account; verify the DM
  arrives within 30 seconds.
