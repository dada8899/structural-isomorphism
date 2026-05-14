# Discord Server Scaffold — Structural Isomorphism

This document specifies the channel structure, role hierarchy, and permission
matrix for the **Structural Isomorphism** Discord community server. An admin
should be able to create the server in ~10 minutes by following this doc step by
step.

> **Status**: blueprint. Apply once the BDFL (or delegated server admin) is
> ready to flip the community switch (target W9-E launch window).

## 1. Server identity

| Field | Value |
|---|---|
| Server name | `Structural Isomorphism` |
| Region | Auto |
| Verification level | **Medium** (must have verified email on Discord account) |
| Explicit content filter | Scan messages from all members |
| Default notifications | Only @mentions |
| Server description | "Research community around cross-domain isomorphism detection, the SOC pipeline, and the Phase Detector. Code: github.com/dada8899/structural-isomorphism" |
| Vanity URL (post-Boost L3) | `discord.gg/structuralisomorphism` (see `discord-vanity-url-plan.md`) |
| 2FA requirement for moderation | **ON** |

## 2. Category & channel structure

Eight categories. **20 text channels** + **2 voice channels** = **22 channels total**.

### 📢 Information (read-only for @member; post = @maintainer only)

| Channel | Topic string |
|---|---|
| `#announcements` | "Releases, papers, events. Maintainers post; everyone reads. Mentions you via @subscriber." |
| `#changelog` | "Auto-feed of merged PRs, tagged releases, and arXiv submissions. Bot-driven." |
| `#events` | "Paper-reading sessions, office hours, conference meetups. RSVP via reactions." |
| `#rules` | "Server rules + Code of Conduct. Pinned. Read before posting." |

### 💬 General

| Channel | Topic string |
|---|---|
| `#introductions` | "First post here. Name, where you found us, what you're curious about. Slowmode 30s." |
| `#general` | "Open chat. Pipeline-specific questions go to the 🧪 Pipeline category. Slowmode 5s." |

### 🧪 Pipeline (project-specific support)

| Channel | Topic string |
|---|---|
| `#soc-pipeline-help` | "Help with the SOC pipeline: install, runs, validation harness, fixture restore." |
| `#cross-judge-help` | "Help with the Cross-Judge (multi-LLM consensus). Prompts, scoring, calibration." |
| `#guarded-llm-help` | "Help with the Guarded LLM (refusal layer, retry policy, slowapi tiers)." |

### 🔬 Phase Detector

| Channel | Topic string |
|---|---|
| `#phase-detector-general` | "General Q&A about the Phase Detector v2 model and v3 plans." |
| `#data-requests` | "Ask for a company / sector to be added to the index. Maintainers triage weekly." |
| `#company-deep-dives` | "Long-form per-company analyses written by @verified-researcher or @contributor." |

### 📊 Research

| Channel | Topic string |
|---|---|
| `#pre-registrations` | "Drop a pre-registration plan here before running a study. Mandatory for COI-flag work." |
| `#methodology` | "Stats, identification, robustness checks, anti-p-hacking debate." |
| `#paper-club` | "Weekly paper-reading group. One paper per thread. Slowmode 30s." |
| `#arxiv-watch` | "Daily auto-digest of new arXiv preprints matching saved keyword feeds." |

### 🎓 Tutorials & Learning

| Channel | Topic string |
|---|---|
| `#newcomers` | "New to the project? Ask anything here. No question is too basic." |
| `#tutorial-questions` | "Walking through a tutorial and stuck? Post the step + error here." |
| `#showcase` | "Show off projects built on top of the pipeline. The only place commercial promo is allowed (≤1 post/week/user)." |

### ⚙️ Contributors (restricted — @contributor and above)

| Channel | Topic string |
|---|---|
| `#contributors-only` | "PRs in flight, design discussions, reviewer coordination. @contributor+ only." |
| `#maintainer-council` | "Council deliberation. @maintainer only. Sealed audit log for COC votes." |
| `#coc-reports` | "Private. Open a ticket via TicketTool here. @maintainer + reporter only per ticket." |

### 🔊 Voice

| Channel | Topic string |
|---|---|
| `#voice-paper-reading` | "Paper-reading group voice room. Open during scheduled sessions." |
| `#voice-pair-programming` | "Drop in for ad-hoc pair programming on the pipeline." |

## 3. Role structure (5 tiers, lowest → highest)

| Role | Color | How granted | Capabilities |
|---|---|---|---|
| `@member` | grey (default) | Auto on join | Read all public channels; post in 💬 / 🎓 / 🔬 / 📊 (rate-limited) |
| `@subscriber` | teal | Self-assign reaction-role after subscribing to newsletter | Pinged in `#announcements`; nothing extra otherwise |
| `@verified-researcher` | blue | Manual: post ORCID + institutional email screenshot in `#coc-reports` ticket | Can post in `#company-deep-dives` and `#pre-registrations`; higher slowmode caps |
| `@contributor` | green | Auto-granted via GitHub bot once a PR is merged on `dada8899/structural-isomorphism` | Access to ⚙️ `#contributors-only`; post in all research channels |
| `@maintainer` | gold | Manual; council vote required (see `coc-enforcement-playbook.md`) | Full mod tools; access to `#maintainer-council` and `#coc-reports` |

Two **special-purpose** invisible roles (no color, no listing):

- `@bot` — for MEE6, Carl-bot, TicketTool, GitHub bot, arXiv bot
- `@muted` — applied via moderation; cannot send messages anywhere (timeout shim)

## 4. Permission matrix

Rows = roles, columns = channel category. `R` = read, `W` = write, `M` = manage (pin/delete others' messages), `–` = no access.

| Category | @member | @subscriber | @verified-researcher | @contributor | @maintainer |
|---|---|---|---|---|---|
| 📢 Information | R | R | R | R | R W M |
| 💬 General | R W | R W | R W | R W | R W M |
| 🧪 Pipeline | R W | R W | R W | R W M | R W M |
| 🔬 Phase Detector | R (W limited) | R W | R W | R W M | R W M |
| 📊 Research | R (W limited) | R W | R W | R W | R W M |
| 🎓 Tutorials | R W | R W | R W | R W M | R W M |
| ⚙️ Contributors | – | – | – | R W (council excl.) | R W M |
| 🔊 Voice | connect | connect | connect | connect | connect + mod |

**Special rules**:
- `#company-deep-dives` and `#pre-registrations`: write requires `@verified-researcher`+
- `#maintainer-council`: write requires `@maintainer`
- `#coc-reports`: write requires `@maintainer` OR being the ticket opener for that specific ticket

## 5. Slowmode policy

| Channel | Slowmode |
|---|---|
| `#general` | 5 seconds |
| `#introductions` | 30 seconds |
| `#paper-club` | 30 seconds |
| `#arxiv-watch` | 6 hours (effectively bot-only) |
| `#contributors-only` | OFF |
| `#maintainer-council` | OFF |
| All other text channels | 5 seconds default |

Slowmode protects against burst spam without throttling real conversation. The
30s cap on `#paper-club` is intentional: forces thoughtful comments over chat-blast.

## 6. Pinned messages (per channel)

Each public channel gets a single pinned message linking to:
1. `#rules`
2. The relevant doc in `docs/community/` (e.g. `#contributors-only` pins
   `CONTRIBUTING.md`)
3. The good-first-issues label on GitHub (for `#newcomers` and
   `#tutorial-questions`)

## 7. Server setup checklist (10-minute admin flow)

1. Create server with name "Structural Isomorphism"; pick the project logo from
   `docs/branding/logo-512.png` (W7-D) as server icon
2. Server Settings → Safety Setup → set verification = Medium, content filter
   = all members, 2FA = ON for moderation
3. Create the 5 roles in section 3, in order (lowest first); set colors
4. Create the 8 categories from section 2
5. Create the 22 channels under their categories; paste in the topic strings
6. Apply the permission matrix (Discord lets you sync category → channel)
7. Set slowmodes per section 5
8. Install bots per `discord-bot-config.md`
9. Pin the messages from section 6
10. Post `discord-welcome-message.md` content as a draft in `#rules` for review,
    then publish

Done. Server is ready to invite members.
