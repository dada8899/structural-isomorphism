# Install: weekly-newsletter LaunchAgent

> **Status.** 2026-05-24 — plist generated at
> `scripts/launchd/com.structural.weekly-newsletter.plist` and validated with
> `plutil -lint` (returns `OK`). **Not yet installed.** This doc is the
> install runbook; the actual `launchctl load` step is for the user to run.
>
> **Schedule.** Mondays 06:00 local. Job calls
> `scripts/generate_weekly_signals.py` to produce
> `newsletter/weekly/<this-monday>.md` + chart PNG, then
> `scripts/send_to_buttondown.py <that .md> --status draft` to push a
> **Buttondown DRAFT** (not auto-sent — human reviews and presses send
> Tuesday morning per the W7-D § 8 plan).

## 0. Pre-install checklist

```bash
cd ~/Projects/structural-isomorphism

# 1. Source plist is well-formed?
plutil -lint scripts/launchd/com.structural.weekly-newsletter.plist
#   → "OK" is the only acceptable output. Anything else → stop, fix.

# 2. Generator scripts exist and import cleanly?
.venv/bin/python3 -c "import importlib.util; \
    [importlib.util.spec_from_file_location('s', f).loader.exec_module(importlib.util.module_from_spec(importlib.util.spec_from_file_location('s', f))) \
     for f in ['scripts/generate_weekly_signals.py', 'scripts/send_to_buttondown.py']]"
#   → no traceback. (This is heavyweight; alternative: just `python3 -m py_compile <file>`.)

# 3. Logs dir exists?
mkdir -p logs

# 4. .venv python exists at the plist-encoded path?
ls -la .venv/bin/python3
#   → must resolve. Plist hard-codes /Users/dadamini/Projects/structural-isomorphism/.venv/bin/python3.
```

If any of the four fails, **do not install** — fix first.

## 1. One-line install

```bash
bash scripts/install_weekly_newsletter_launchagent.sh
```

What the installer does (idempotent — safe to re-run):

1. `cp` plist into `~/Library/LaunchAgents/`
2. `plutil -lint` the installed copy
3. `launchctl unload` any previous copy (ignores errors on first install)
4. `launchctl load` the fresh copy
5. `launchctl list | grep com.structural.weekly-newsletter` — verify

Exit codes:

| Code | Meaning |
|------|---------|
| 0    | installed + loaded + verified |
| 1    | source plist missing |
| 2    | `plutil -lint` failed on installed copy |
| 3    | `launchctl load` failed |
| 4    | post-install verify failed (job not in `launchctl list`) |

## 2. Verify install

```bash
# 2a. Job is registered?
launchctl list | grep structural
#   Expected: a line like
#   -    0    com.structural.weekly-newsletter
#   PID  EXIT LABEL
#   PID is "-" because the job is scheduled, not running right now.
#   EXIT is "0" until a run fires.

# 2b. Plist contents match the source?
diff scripts/launchd/com.structural.weekly-newsletter.plist \
     ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
#   → no output = identical.

# 2c. Scheduled time decoded?
launchctl print gui/$(id -u)/com.structural.weekly-newsletter 2>/dev/null \
  | grep -E "(state|run interval|next start|last exit)"
#   → look for "state = waiting" and a sensible "next start" timestamp.
#   On macOS 14+/15+ this is the supported introspection command.
```

## 3. First dry-run (manual trigger)

```bash
# 3a. Force an immediate run — bypasses the Monday-06:00 schedule.
launchctl start com.structural.weekly-newsletter

# 3b. Watch logs.
tail -F logs/launchd-weekly-newsletter.log \
       logs/launchd-weekly-newsletter.err

# 3c. After ~30s, verify outputs.
ls -lat newsletter/weekly/ | head -5
#   → expect a fresh <YYYY-MM-DD>.md (today's Monday).

# 3d. Verify Buttondown got the DRAFT (only if BUTTONDOWN_API_KEY set).
#     If keys are empty (MOCK mode), send_to_buttondown.py prints a
#     "would POST to https://api.buttondown.email/v1/emails" line + exits 0.
grep -E "(would POST|created Buttondown email|MOCK)" logs/launchd-weekly-newsletter.log | tail -5
```

**What a successful dry-run output looks like (MOCK mode):**

```
[generate_weekly_signals] reading data/phase-detector/latest.json … missing, falling back to mock-data v0.1
[generate_weekly_signals] selected 6 near-critical companies
[generate_weekly_signals] rendered sparkline → newsletter/weekly/2026-05-25-alpha.png
[generate_weekly_signals] LLM editorial: no OPENROUTER_API_KEY → mock sentence used
[generate_weekly_signals] wrote newsletter/weekly/2026-05-25.md
newsletter/weekly/2026-05-25.md
[send_to_buttondown] MOCK MODE — no BUTTONDOWN_API_KEY; would POST to https://api.buttondown.email/v1/emails (status=draft)
```

**What a successful dry-run output looks like (real keys set):**

Same as above except:

```
[generate_weekly_signals] LLM editorial: 247 tokens, $0.0008
[send_to_buttondown] created Buttondown DRAFT id=abc123 (status=draft)
```

## 4. Inject API keys (optional, for live mode)

The default plist has empty `BUTTONDOWN_API_KEY` and `OPENROUTER_API_KEY`
strings — both downstream scripts gracefully fall back to MOCK mode. To
go live:

```bash
# 4a. Edit the installed copy in place.
$EDITOR ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
#   Fill in:
#     <key>BUTTONDOWN_API_KEY</key><string>YOUR_BUTTONDOWN_KEY</string>
#     <key>OPENROUTER_API_KEY</key><string>YOUR_OPENROUTER_KEY</string>

# 4b. Lint after edit.
plutil -lint ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist

# 4c. Reload to pick up new env.
bash ~/Projects/structural-isomorphism/scripts/install_weekly_newsletter_launchagent.sh
#   The installer is idempotent — re-running it will unload + reload.
```

**Why not store the keys in `.env` and source them?** LaunchAgents do not
source `~/.zshrc` / `~/.bash_profile` / project `.env` automatically.
Either inject via the plist (this section) or wrap the `ProgramArguments`
shell line with `set -a; . /path/to/.env; set +a; ...`. Plist injection is
the macOS-native pattern.

**Security note.** `~/Library/LaunchAgents/` is per-user, mode 0644 by
default. Keys in the plist are visible to any process running as your
user. If the keys are PRODUCTION live keys (not test mode), consider
chmod 0600 the plist after install. Note that `launchctl` will still
read it.

## 5. Troubleshooting

### 5.1 `launchctl load` fails with "Bootstrap failed: 5: Input/output error"

Cause: the plist was previously loaded under a different `Label` or path,
and the launchd cache is confused.

Fix:

```bash
launchctl bootout gui/$(id -u)/com.structural.weekly-newsletter || true
launchctl unload ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist || true
sleep 2
bash ~/Projects/structural-isomorphism/scripts/install_weekly_newsletter_launchagent.sh
```

### 5.2 `launchctl list | grep structural` returns nothing after install

Cause: launchd silently rejected the plist (usually permissions or
malformed key).

Diagnostic:

```bash
plutil -p ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist | head -30
log show --predicate 'process == "launchd" AND subsystem == "com.apple.launchd"' --info --last 5m \
  | grep -i structural
```

Most common culprit: `ProgramArguments` references a python binary that
doesn't exist (`.venv/bin/python3` missing). Fix: `pip install` the deps
into `.venv` first, then re-install.

### 5.3 Job runs but writes nothing to logs/

Cause: the `StandardOutPath` / `StandardErrorPath` directories don't exist.

Fix: `mkdir -p ~/Projects/structural-isomorphism/logs` before install.

### 5.4 Job runs but `newsletter/weekly/` has no new file

Cause: `generate_weekly_signals.py` errored before writing, but the error
went to stdout instead of stderr.

Diagnostic:

```bash
cat ~/Projects/structural-isomorphism/logs/launchd-weekly-newsletter.log
cat ~/Projects/structural-isomorphism/logs/launchd-weekly-newsletter.err
```

The plist runs `MD=$($PY generate_weekly_signals.py | tail -1)`; if the
generator fails after printing the path line but before writing the file,
`send_to_buttondown.py` will get a bogus filename. Re-run manually:

```bash
.venv/bin/python3 scripts/generate_weekly_signals.py
.venv/bin/python3 scripts/send_to_buttondown.py newsletter/weekly/<that>.md --status draft
```

### 5.5 Mondays come and go but no run fires

Cause: launchd missed the calendar slot because the Mac was asleep / off /
in Low Power Mode.

Diagnostic:

```bash
launchctl print gui/$(id -u)/com.structural.weekly-newsletter | grep -E "last exit|next start"
```

Fix options:

- Wake the Mac before 06:00 Monday (`pmset` / Energy Saver).
- Add a fallback `KeepAlive` policy to the plist (not recommended for a
  weekly job; risks burst re-runs).
- Move the job to the VPS `cc-daemon` scheduler (already runs other weekly
  jobs — see `CLAUDE.md` § "VPS cc-daemon 调度"). This is the long-term
  fix; the local-mac plist is the bridge while waiting for that migration.

### 5.6 Uninstall

```bash
launchctl unload ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
rm ~/Library/LaunchAgents/com.structural.weekly-newsletter.plist
# Optional: clear logs
rm ~/Projects/structural-isomorphism/logs/launchd-weekly-newsletter.{log,err} 2>/dev/null || true
```

The project copy at `scripts/launchd/com.structural.weekly-newsletter.plist`
is left untouched (it's the source of truth in the repo).

## 6. Long-term: migrate to VPS cc-daemon

Per `CLAUDE.md` § "自动化任务", the long-term home for this job is the VPS
`cc-daemon` scheduler (joins `daily-summary` / `heartbeat` /
`webhook-trigger` / `weekly-review` / `astock-agent` / `vault-git-backup`).
Reasons:

- Local Mac sleeps. VPS does not.
- VPS already has a single point of API-key management.
- Logs centralized with the rest of the daemon's stdout.

When migrating, the local plist becomes obsolete — `launchctl unload` it
and add the equivalent cron-expr-only entry to the cc-daemon registry.

Current launch (2026-05-24): local plist is the bridge. Migrate after
the first 4 successful Monday runs verify the pipeline produces a usable
draft.

---

*Last updated 2026-05-24. Plist source:
`scripts/launchd/com.structural.weekly-newsletter.plist`. Installer:
`scripts/install_weekly_newsletter_launchagent.sh`. **Not yet installed.***
