# Structural Signals — newsletter pipeline (W9-C)

Weekly digest combining four data sources:

1. **Phase flips** — companies whose critical-point classification changed
   week-over-week (sourced from D1 `structtuples_*.jsonl` or live phase API).
2. **arXiv preprints** — last 7 days of cross-domain SOC / universality
   submissions matching our query.
3. **GitHub activity** — stars, forks, external PRs, new issues via
   `gh api`.
4. **Methodology spotlight** — rotating 2-paragraph essay from a pool of
   8 topics (auto-picked by ISO week % pool size, or `--spotlight <slug>`).

## Files

- [`template.md`](./template.md) — canonical markdown template with `{{placeholder}}` markers.
- [`template.mjml`](./template.mjml) — MJML email-friendly version (for Buttondown / Mailchimp).
- [`issue-NNN.md`](./) — generated weekly issues (committed via CI for human review).

The generator + data-source module live in:

- `scripts/generate-newsletter.py`
- `scripts/newsletter_data_sources.py`

Tests: `tests/test_generate_newsletter.py`.

## Quick start

```bash
# Generate the current week's digest (auto data sources, no real send)
python scripts/generate-newsletter.py --week 2026-W19 --out docs/community/newsletters/issue-001.md

# Preview (stdout, no file write)
python scripts/generate-newsletter.py --week 2026-W19 --dry-run

# Force a specific methodology spotlight
python scripts/generate-newsletter.py --week 2026-W19 \
    --spotlight ews-variance-autocorr --dry-run

# CI-friendly: skip arXiv + GitHub fetches (deterministic, offline)
python scripts/generate-newsletter.py --week 2026-W19 --skip-network --dry-run

# List spotlight topic slugs
python scripts/generate-newsletter.py --list-spotlights
```

## Rendering the MJML email

```bash
# Install MJML CLI (Node)
npm install -g mjml

# Render
mjml docs/community/newsletters/template.mjml -o /tmp/structural-signals.html

# (Currently the MJML template has its own placeholders; W10 will add a
# markdown-to-MJML build step that compiles each section.)
```

## Idempotency contract

The generator is deterministic: given the same `--week`, the same
upstream inputs (structtuples file + arXiv API response + gh api output),
and the same template, it produces **byte-identical** output.

Practical implication: re-running on Monday produces the same digest as
Sunday for the same week label. CI tests assert this.

## CI workflow

`.github/workflows/newsletter.yml` runs every Sunday 23:00 UTC and:

1. Generates the current ISO week's digest.
2. Commits it to `docs/community/newsletters/issue-{ISO-WEEK}.md`.
3. Opens a PR labeled `newsletter` for a human reviewer to read, edit, and
   merge before any real send.

> **Important**: this pipeline produces the *artifact*. Sending to real
> subscribers is a separate, manual step gated on PR merge. See
> [`newsletter-subscribe-design.md`](./newsletter-subscribe-design.md) for
> the subscription-storage plan.

## See also

- Older single-source phase-flip-only pipeline: `scripts/newsletter/send_weekly.py` (W8-D)
- Subscription-storage design: [`newsletter-subscribe-design.md`](./newsletter-subscribe-design.md)
- Beta-site signup form: `web/frontend/assets/js/newsletter.js` (W2-A)
- Backend endpoint: `web/backend/api/newsletter.py`
