# Discord bot configuration — final cut for launch (2026-05-24)

> **Supersedes**: `discord-bot-config.md` (high-level OSS-bot blueprint).
> This doc adds the missing operational pieces needed to actually flip the
> server on at launch: secret placeholders, the custom GitHub-→-Discord
> webhook bot, channel-by-channel automation, and the role hierarchy
> ready-to-paste into the Discord admin UI.
>
> **Status**: ready for execution as soon as the BDFL creates the server.
> All secret values are placeholders — fill at server-creation time and
> store the real values in `~/Vault/重要信息/discord-secrets.md` (gitignored,
> age-encrypted).
>
> **Maintainer**: @dada8899

## 0. Secret inventory

Five secrets to provision before launch. **Never commit any of these.**

| Key | Where to provision | Stored at | Used by |
|---|---|---|---|
| `DISCORD_BOT_TOKEN` | `https://discord.com/developers/applications` → New Application → Bot → Reset Token | `~/Vault/重要信息/discord-secrets.md` | `scripts/discord-bot.py` |
| `DISCORD_WEBHOOK_RELEASES` | Discord server → `#releases` → channel settings → Integrations → Webhooks → New Webhook → copy URL | `~/Vault/重要信息/discord-secrets.md` | GitHub Actions `release.yml` |
| `DISCORD_WEBHOOK_CHANGELOG` | Discord server → `#changelog` → New Webhook | `~/Vault/重要信息/discord-secrets.md` | GitHub webhook proxy |
| `GITHUB_WEBHOOK_SECRET` | Random 32-byte hex; set in repo Settings → Webhooks | `~/Vault/重要信息/discord-secrets.md` | `scripts/discord-bot.py` HMAC verification |
| `CARLBOT_DASHBOARD_PASSWORD` | First login to `carl.gg` after server creation | `~/Vault/重要信息/discord-secrets.md` | Admin |

Placeholder values used in this doc:
```
DISCORD_BOT_TOKEN=<placeholder-bot-token-fill-at-launch>
DISCORD_WEBHOOK_RELEASES=<placeholder-webhook-url-fill-at-launch>
DISCORD_WEBHOOK_CHANGELOG=<placeholder-webhook-url-fill-at-launch>
GITHUB_WEBHOOK_SECRET=<placeholder-32-byte-hex>
```

## 1. Off-the-shelf bots (already detailed in `discord-bot-config.md`)

Three bots from the v1 plan are kept as-is:

1. **Carl-bot** — auto-role on join + welcome DM + reaction-role for `@subscriber` + automod
2. **TicketTool** — private COC report tickets in `#coc-reports`
3. **MonitoRSS** — arXiv RSS digest into `#arxiv-watch`

Configuration walkthroughs for these three are unchanged; see `discord-bot-config.md` sections 1, 2, 4.

The **GitHub official Discord integration** from v1 (`/github subscribe`) is replaced in this final cut by our **custom webhook bot** (section 3 below) for richer formatting, HMAC verification, and the ability to filter / annotate before posting.

## 2. Channel structure (final, 6 user-facing + Information/Contributors categories)

Per task brief — simplified user-facing surface to 6 primary channels for launch, with the full 22-channel ladder from `discord-setup.md` reachable as the community grows.

### Phase 1 launch channels (first 50 invitees)

| Channel | Purpose | Slowmode | Posted-by |
|---|---|---|---|
| `#general` | Open discussion, watercooler | 5 s | @member+ |
| `#help` | Beginner questions, install issues, "what does X mean" | 5 s | @member+ |
| `#papers` | Paper discussion, methodology, links to new preprints | 30 s | @member+ |
| `#releases` | Auto-feed: new tagged releases on GitHub | n/a | bot-only |
| `#showcase` | "Look what I built with the pipeline" — projects + screenshots | 30 s | @member+ |
| `#questions` | Maintainer-triaged Q&A; like `#help` but for non-install methodology Qs | 5 s | @member+ |

Behind these: the v1 `discord-setup.md` structure remains the long-term target (announcements / changelog / pipeline-help / phase-detector / etc.) and gets layered in as the community crosses 100, 250, 500 members.

### Always-on auxiliaries

- `#rules` — read-only, pinned with COC link
- `#introductions` — new-member self-intros (`@member` can post once, then locked per user via Carl-bot autorole)
- `#coc-reports` — TicketTool surface
- `#contributors-only` — restricted to `@contributor`+

## 3. Custom webhook bot (`scripts/discord-bot.py`)

Receives GitHub webhooks → routes to Discord channels by event type. This is the bot we ship and maintain ourselves (one file, no daemon framework, runs as a single `aiohttp` server).

### Routes

| GitHub event | Discord channel | Posted as |
|---|---|---|
| `issues.opened` | `#help` (if labeled `good first issue`) else `#general` | Bot embed |
| `pull_request.opened` | `#contributors-only` | Bot embed |
| `pull_request.closed` (merged) | `#showcase` if author is new-contributor else `#contributors-only` | Bot embed |
| `release.published` | `#releases` | Bot embed |
| `discussion.created` (category=Q&A) | `#questions` | Bot embed |

### Welcome-on-join (separate from GitHub webhooks)

`on_member_join` discord.py event posts a welcome embed to `#introductions` and DMs the `discord-welcome-message.md` content. Carl-bot already handles auto-role; our bot only adds the DM with the rich-embed welcome card.

### Deployment

- Lives at `scripts/discord-bot.py`
- Runs on the VPS as a systemd service (port 8770, behind nginx proxy with HMAC verification)
- Nginx subdomain: `discord-bot.bytedance.city` (GitHub webhook target)
- Env file: `/root/.config/discord-bot.env` (mode 600, owned by root)
- Logs: `journalctl -u discord-bot -f`

See `scripts/discord-bot.py` for the implementation.

### systemd unit (paste into `/etc/systemd/system/discord-bot.service` at deploy time)

```ini
[Unit]
Description=Structural Isomorphism Discord bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/Projects/structural-isomorphism
EnvironmentFile=/root/.config/discord-bot.env
ExecStart=/usr/bin/python3 scripts/discord-bot.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

### nginx fragment

```nginx
server {
    listen 443 ssl;
    server_name discord-bot.bytedance.city;

    location /webhook/github {
        proxy_pass http://127.0.0.1:8770/webhook/github;
        proxy_set_header X-Hub-Signature-256 $http_x_hub_signature_256;
        proxy_set_header X-GitHub-Event $http_x_github_event;
        proxy_set_header Content-Type $content_type;
    }

    location /healthz {
        proxy_pass http://127.0.0.1:8770/healthz;
    }
}
```

### GitHub webhook setup (one-time, at launch)

1. Go to `https://github.com/dada8899/structural-isomorphism/settings/hooks`
2. Click "Add webhook"
3. Payload URL: `https://discord-bot.bytedance.city/webhook/github`
4. Content type: `application/json`
5. Secret: paste `GITHUB_WEBHOOK_SECRET`
6. SSL verification: enabled
7. Events: "Let me select individual events" → tick: Issues, Pull requests, Releases, Discussions
8. Active: ✅

Verify by opening a test issue and watching `journalctl -u discord-bot -f`.

## 4. Channel-level automation summary

| Channel | Bot | Behavior |
|---|---|---|
| `#general` | Carl-bot automod | Block invite links + 5s slowmode |
| `#help` | Carl-bot automod + custom bot | Auto-cross-post good-first-issue events |
| `#papers` | None (manual) | — |
| `#releases` | Custom bot + GitHub webhook | One embed per published release |
| `#showcase` | Carl-bot automod | 30s slowmode + 1-promo-per-week rule (manual moderation) |
| `#questions` | Custom bot | Mirror new GitHub Q&A discussions |
| `#changelog` | Custom bot | Mirror merged PRs (de-duped with #contributors-only via PR-author role check) |
| `#arxiv-watch` | MonitoRSS | Daily digest, 6h cron |
| `#coc-reports` | TicketTool | Private 1-on-1 with maintainer council |
| `#rules` | None (manual pin) | Pinned message links to CODE_OF_CONDUCT.md |
| `#introductions` | Custom bot (welcome embed) | Per-user post-once via Carl-bot autorole |

## 5. Role hierarchy (final)

Copy-paste in this exact order, top → bottom, in Discord server settings → Roles. Bots must sit above the roles they manage.

```
@maintainer              gold       — manual / council vote
@bot                     no-color   — Carl-bot, TicketTool, custom bot, MonitoRSS
@contributor             green      — auto via GitHub-merged-PR (custom bot grants)
@verified-researcher     blue       — manual after ORCID verification
@subscriber              teal       — self-assign via reaction role in #announcements
@member                  grey       — auto on join (Carl-bot)
@muted                   no-color   — moderation timeout shim
@everyone                grey       — default
```

## 6. First 50 invitations — candidate list

Three pools, ~17 names each. Send personalized DMs, not a generic blast.

### Pool A — X3 / cross-domain review network (W7-A senior outreach list + extensions)

These are senior researchers we've already drafted cold-emails to (`docs/community/launch/senior-outreach-2026-05-15.md`). Invite to Discord as a soft second touch — even passive presence helps.

1. Dietmar Plenz (NIMH) — neural avalanches
2. Viola Priesemann (MPI Göttingen) — sub-sampling / branching-ratio
3. Marten Scheffer (WUR) — EWS / tipping points
4. Aaron Clauset (CU Boulder) — power-law fitting (Clauset–Shalizi–Newman)
5. Per Bak (legacy — Bak-Tang-Wiesenfeld lab alumni network; reach via Christensen or Jensen)
6. Kim Christensen (Imperial) — SOC, Oslo rice pile
7. Henrik Jeldtoft Jensen (Imperial) — SOC criticality
8. Daniel B. Larremore (CU Boulder) — networks + statistical inference
9. Cosma Shalizi (CMU) — methodology + heavy-tailed distributions
10. Sándor Beggs (Indiana) — neural avalanches in vitro
11. Tim Lenton (Exeter) — climate tipping
12. Vasilis Dakos (Montpellier) — early-warning signals
13. Egbert van Nes (WUR) — alternate stable states
14. Ryan Sweke (IBM Quantum) — Anderson localization / disordered systems
15. Lev Levitov (MIT) — Anderson localization theory
16. Sarah K. Watson (BAS / British Antarctic Survey) — solar wind data ops
17. Pete Riley (Predictive Science Inc.) — solar wind statistics

### Pool B — SOC scholar audience (W7-A audience-validation extension)

Mid-career and rising researchers actively publishing in adjacent fields. Lower-stakes invitation; goal is to seed `#papers` and `#methodology` discussions.

1. Wei Chen (UC Irvine) — earthquake statistics
2. Yamir Moreno (Zaragoza) — complex networks / cascades
3. Filippo Radicchi (Indiana) — network science + criticality
4. Manlio De Domenico (Padua) — multilayer networks
5. Alessandro Vespignani (Northeastern) — epidemic spreading
6. Roberta Sinatra (ITU Copenhagen) — science-of-science / careers
7. Cesar Hidalgo (Toulouse) — complexity economics
8. Lada Adamic (Meta) — information cascades on social platforms
9. Duncan Watts (UPenn) — small-world / cascades
10. Sinan Aral (MIT Sloan) — viral spreading
11. Petter Holme (Aalto) — temporal networks
12. Alexandre Arenas (URV Tarragona) — synchronization
13. Renaud Lambiotte (Oxford) — network dynamics
14. Iacopo Iacopini (NEU London) — higher-order networks
15. Federico Battiston (CEU) — higher-order interactions
16. Jure Leskovec (Stanford) — large-scale graph mining
17. Roger Guimera (URV / ICREA) — complex systems / inference

### Pool C — Practitioner / user candidates (W7-D pre-launch user testing pool)

Quant-curious engineers, hedge-fund quants, DeFi-risk teams, journalists. These are the people who will use the Phase Detector + Cross-Judge in anger, file the most issues, and become the first `@contributor`s.

1. Cliff Asness team (AQR) — public-facing quant
2. Patrick McKenzie (Stripe / Bits about Money) — practitioner journalism
3. Matt Levine (Bloomberg) — Money Stuff readership overlap
4. Byrne Hobart (The Diff) — capital-markets newsletter
5. Tracy Alloway / Joe Weisenthal (Bloomberg Odd Lots) — podcast pickup
6. Hempton (Bronte Capital) — short-side analyst
7. Marc Andreessen / Vitalik Buterin's research engineers (not the principals) — DeFi risk angle
8. Trail of Bits research team — formal methods + smart-contract risk
9. OpenZeppelin Defender team — DeFi alert tooling
10. Gauntlet team — DeFi risk modeling
11. Chaos Labs team — onchain risk
12. Galaxy Research analysts — crypto research
13. Coinbase Institutional research — institutional crypto
14. arXiv-Sanity Lite community / Andrej Karpathy's readership — methodology curious
15. Distill alumni / Chris Olah's network — interpretability + methodology
16. AI Safety field — Anthropic, OpenAI, DeepMind safety researchers (cross-domain SOC has alignment / interp parallels)
17. Mod-tier subreddits: `r/badeconomics`, `r/statistics`, `r/AcademicStatistics` mods (for cross-posting permission, not as inviteees per se — but invite the most-engaged mods)

### Sourcing notes

- All names are public researchers / public-facing figures whose handles or institutional emails are findable via Google Scholar / arXiv / personal websites
- **Never post the Discord invite link in a public forum until the server is hardened** — partial invite-leak is fine, full public listing waits for the W9-E launch window
- Use the vanity URL `discord.gg/structuralisomorphism` (per `discord-vanity-url-plan.md`) only after Boost Level 3 is reached
- Pre-launch: use the auto-generated invite link from Discord, set to single-use + 7-day expiry per invitee

### Outreach cadence

| Day | Action |
|---|---|
| T-3 | Invite Pool A (17 people, personalized — reuse `senior-outreach-2026-05-15.md` cold-email cadence) |
| T-1 | Invite Pool B (17 people) — short DM with a 2-line "what is this server" + link |
| T+0 | Public launch — invite Pool C (17 people) + post invite in HN / Mastodon / Twitter threads (from `launch/`) |
| T+7 | Follow-up DM to non-joiners in Pool A only |

## 7. Pre-launch checklist (admin)

Run through this once when creating the server, in order:

- [ ] Server created with name "Structural Isomorphism", icon, description, 2FA-for-mod
- [ ] 5 roles in section 5 created with correct colors and order
- [ ] 6 launch channels + 4 always-on auxiliaries created
- [ ] `discord-welcome-message.md` content pasted into `#rules` and pinned
- [ ] Carl-bot installed, autorole = `@member`, welcome DM enabled, reaction-role for `@subscriber` configured
- [ ] TicketTool installed and pointed at `#coc-reports`
- [ ] MonitoRSS installed and pointed at `#arxiv-watch` with the arXiv keyword feed
- [ ] Custom bot deployed on VPS (systemd unit running, healthz green)
- [ ] GitHub webhook configured and tested with a throwaway issue
- [ ] First 50 invitations queued in personal DM drafts
- [ ] Secrets stored in `~/Vault/重要信息/discord-secrets.md` (age-encrypted)
- [ ] One end-to-end test: open a test issue → confirm `#help` embed lands

## 8. Failure modes & rollback

| Failure | Symptom | Rollback |
|---|---|---|
| Custom bot crashes | No new issues mirroring | `systemctl restart discord-bot` + check logs |
| GitHub webhook delivery fails | Webhook page shows red ❌ | Re-deliver from GitHub Settings → Webhooks → recent deliveries |
| Carl-bot down | New members don't get `@member` role | Manual role-assign for backlog; works in batches |
| Token leaked | Bot suddenly DMs spam to all members | Reset token via Discord Dev Portal, restart bot with new env file |
| Discord rate-limited | Bot stops posting for 10–60 min | Wait it out; logs will say `429 Too Many Requests`; reduce post frequency |

## 9. Post-launch metrics to track

- New-member rate (target: 5–15/day for first 30 days)
- `#introductions` post rate (proxy for actual engagement; target: ≥ 60 % of joiners)
- `#help` resolution time (median; target: < 4 h during launch month)
- `@contributor` grants (proxy for GitHub→Discord conversion; target: ≥ 3 in launch month)
- COC reports filed via TicketTool (no target — track as signal)

Weekly snapshot in `docs/community/discord-metrics-<YYYY-WW>.md`, written by the maintainer.
