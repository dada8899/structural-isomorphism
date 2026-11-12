# Newsletter (W8-D)

Weekly _Structural Signals_ digest pipeline.

## Files

- `send_weekly.py` — main pipeline. Reads latest `structtuples_*.jsonl`, diffs
  against `state/last_week_state.json`, renders markdown via
  `docs/newsletter/templates/weekly-digest-template.md`, optionally sends via
  Buttondown.
- `state/last_week_state.json` — **runtime artifact**, gitignored. Created on
  the first successful run. Used to diff week-over-week.

## Quick start

```bash
# Dry-run to stdout (does not write any state)
python scripts/newsletter/send_weekly.py --dry-run

# Write a sample to docs/newsletter/samples/ without updating state
python scripts/newsletter/send_weekly.py --no-state-update

# Real weekly run: write file + update state + (optionally) send
python scripts/newsletter/send_weekly.py --send
```

## Proposed cron

```bash
# /etc/cron.d/newsletter on VPS
0 22 * * 0  cd /root/Projects/structural-isomorphism && \
            .venv/bin/python scripts/newsletter/send_weekly.py --send \
            >> /var/log/newsletter.log 2>&1
```

## See also

- `docs/newsletter/buttondown-setup.md` — Buttondown provisioning steps
- `docs/newsletter/templates/weekly-digest-template.md` — markdown template
- `docs/newsletter/samples/` — generated sample digests
