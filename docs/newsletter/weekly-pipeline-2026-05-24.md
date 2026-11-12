# Weekly signals newsletter — pipeline doc

**Created**: 2026-05-24 (W7-D mini-brief 3)
**Status**: code paths live, automation NOT yet installed.
**Companion**: `docs/newsletter/buttondown-setup.md` (account / DNS / API key).

## Why this exists

`scripts/generate-newsletter.py` (W9-C) is the 4-source digest (arXiv + GitHub
+ phase flips + ask spotlights). `scripts/newsletter/send_weekly.py` (W8-D) is
phase-flip-only.

This **W7-D pipeline** is the explicit "6 near-critical companies + 1 alpha
chart + 1 editor's paragraph" Sarah-persona newsletter described in
[W7-D-product-value-roadmap-2026-05-13.md § 8](../future/W7-D-product-value-roadmap-2026-05-13.md).
It exists because the W9-C digest is too broad for the Sarah persona; she
wants the 6-tickers-per-Tuesday ritual specifically.

## File layout

```
scripts/
  generate_weekly_signals.py        # phase data → markdown + chart
  send_to_buttondown.py             # markdown → Buttondown draft
  launchd/
    com.structural.weekly-newsletter.plist   # weekly 06:00 launchd job

newsletter/
  weekly/
    YYYY-MM-DD.md                   # one issue per week (Monday-dated)
    YYYY-MM-DD-alpha-signal.png     # cohort Δ-signal chart

docs/newsletter/
  weekly-pipeline-2026-05-24.md     # this file
  buttondown-setup.md               # account / API key provisioning
```

## Manual run

```bash
cd /Users/dadamini/Projects/structural-isomorphism

# 1. Generate the markdown + chart
.venv/bin/python3 scripts/generate_weekly_signals.py
# → writes newsletter/weekly/2026-05-25.md (or whatever Monday this is)
# → optionally a -alpha-signal.png next to it

# 2. (optional) preview locally
open newsletter/weekly/2026-05-25.md

# 3. Send to Buttondown as draft (no broadcast)
.venv/bin/python3 scripts/send_to_buttondown.py newsletter/weekly/2026-05-25.md
```

If `BUTTONDOWN_API_KEY` is unset, step 3 logs what it WOULD have sent and
exits 0 — safe for CI. Same for `OPENROUTER_API_KEY` in step 1: missing key
→ deterministic mock editor's note.

## Data sources

`generate_weekly_signals.py` looks for, in order:

1. `data/phase-detector/latest.json` — JSON: list-of-companies OR `{companies: [...]}`
2. `web/frontend/phase/data/companies_struct.jsonl` — JSONL fallback

Each company row shape:

```json
{
  "ticker": "WBA",
  "name": "Walgreens Boots Alliance",
  "phase": "near_critical",           // stable | trending | near_critical | post_crisis
  "confidence": 0.91,                 // 0..1
  "dynamics_family": "bistable",
  "delta_signal": -0.42,              // last-vs-prior quarter
  "primary_quote": "..."
}
```

If no real data is found, the script falls back to a small bundled mock set
and labels the newsletter `Data source: mock` in the footer. This is
intentional and per W7-D guidance — we never silently pass mock as real.

## Cron / automation install

Edit the plist first to fill in API keys:

```bash
vi scripts/launchd/com.structural.weekly-newsletter.plist
# — fill in BUTTONDOWN_API_KEY and OPENROUTER_API_KEY
```

Then install:

```bash
mkdir -p ~/Library/LaunchAgents
cp scripts/launchd/com.structural.weekly-newsletter.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
launchctl enable gui/$(id -u)/com.structural.weekly-newsletter

# verify
launchctl list | grep structural.weekly
```

To uninstall:

```bash
launchctl bootout gui/$(id -u)/com.structural.weekly-newsletter
rm ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
```

The plist is set up to:
- Run every **Monday 06:00 local time**
- Write a Buttondown **draft** (NOT broadcast — human reviews and sends Tuesday morning)
- Log to `logs/launchd-weekly-newsletter.{log,err}`
- Use the repo's `.venv/bin/python3`

`RunAtLoad` is `false` so installing the plist doesn't immediately fire one.

## QA checklist before first real send

- [ ] Phase data JSON is wired (otherwise the issue is mock-labelled — fine for v0.1)
- [ ] `BUTTONDOWN_API_KEY` is in the plist
- [ ] One manual dry-run completed: `python3 scripts/send_to_buttondown.py <md> --dry-run`
- [ ] First real run was status=draft (not about_to_send)
- [ ] Subject line is the H1 from the markdown (or `--subject` override)
- [ ] Chart renders inline in Buttondown's preview (Buttondown supports `![alt](file.png)` for absolute URLs — we'll need to upload PNG to a public CDN or inline as base64 in a follow-up)
- [ ] Sending domain is `newsletter.bytedance.city` per buttondown-setup.md

## Open follow-ups (post W7-D)

- Chart image is currently relative-path only; Buttondown drafts won't render it. Either:
  - upload PNG to S3 / VPS static and rewrite the markdown `![](url)` before send, or
  - inline as base64 (Buttondown supports up to 1MB images inline).
- Make `--week` accept ISO-week labels like `2026-W22` for symmetry with W9-C.
- Add the W9-C 4-source digest sections (arXiv etc.) as optional `--include` flags rather than maintaining two scripts.
