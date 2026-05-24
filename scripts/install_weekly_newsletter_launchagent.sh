#!/usr/bin/env bash
# install_weekly_newsletter_launchagent.sh
# One-step installer for the weekly-newsletter LaunchAgent.
#
# Idempotent: safe to re-run; existing copy gets unloaded → replaced → reloaded.
#
# What it does:
#   1. cp scripts/launchd/com.structural.weekly-newsletter.plist → ~/Library/LaunchAgents/
#   2. plutil -lint the installed copy
#   3. launchctl unload (ignore-errors) — needed if a previous version is loaded
#   4. launchctl load on the installed copy
#   5. launchctl list | grep com.structural.weekly-newsletter — verify it's registered
#
# What it does NOT do:
#   - Inject the BUTTONDOWN_API_KEY or OPENROUTER_API_KEY into the plist.
#     Both default to empty inside the plist; the scripts gracefully fall back
#     to MOCK mode (creates a draft markdown + Buttondown DRAFT without an LLM
#     intro sentence) when keys are empty. To set them: edit the installed
#     copy in ~/Library/LaunchAgents/ AFTER this script runs, then re-run
#     this script to reload.
#   - Trigger a one-shot run. Use `launchctl start com.structural.weekly-newsletter`
#     after install for that.
#
# Exit codes:
#   0 = installed & loaded & verified
#   1 = plist source missing
#   2 = plutil lint failed
#   3 = launchctl load failed
#   4 = post-install verify failed (job not in launchctl list)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$REPO_ROOT/scripts/launchd/com.structural.weekly-newsletter.plist"
DST_DIR="$HOME/Library/LaunchAgents"
DST="$DST_DIR/com.structural.weekly-newsletter.plist"
LABEL="com.structural.weekly-newsletter"

echo "[install-weekly-newsletter] repo root: $REPO_ROOT"
echo "[install-weekly-newsletter] source:    $SRC"
echo "[install-weekly-newsletter] target:    $DST"

# Step 0: source must exist
if [[ ! -f "$SRC" ]]; then
    echo "[install-weekly-newsletter] FATAL: source plist not found at $SRC" >&2
    exit 1
fi

# Step 1: copy
mkdir -p "$DST_DIR"
cp "$SRC" "$DST"
echo "[install-weekly-newsletter] copied"

# Step 2: lint
if ! plutil -lint "$DST" > /dev/null; then
    echo "[install-weekly-newsletter] FATAL: plutil -lint failed on $DST" >&2
    plutil -lint "$DST" || true
    exit 2
fi
echo "[install-weekly-newsletter] plutil lint OK"

# Step 3: unload previous (ignore errors — first install)
if launchctl list 2>/dev/null | grep -q "$LABEL"; then
    echo "[install-weekly-newsletter] previous version detected — unloading"
    launchctl unload "$DST" 2>/dev/null || true
fi

# Step 4: load fresh
if ! launchctl load "$DST"; then
    echo "[install-weekly-newsletter] FATAL: launchctl load failed" >&2
    exit 3
fi
echo "[install-weekly-newsletter] launchctl load OK"

# Step 5: verify it's registered
if ! launchctl list | grep -q "$LABEL"; then
    echo "[install-weekly-newsletter] FATAL: post-install verify failed — $LABEL not in launchctl list" >&2
    exit 4
fi

echo ""
echo "[install-weekly-newsletter] SUCCESS — $LABEL installed & loaded."
echo ""
echo "Next steps:"
echo "  - Dry-run now:    launchctl start $LABEL"
echo "  - Inspect:        launchctl list | grep structural"
echo "  - Tail logs:      tail -F $REPO_ROOT/logs/launchd-weekly-newsletter.{log,err}"
echo "  - Edit keys:      \$EDITOR $DST   (BUTTONDOWN_API_KEY / OPENROUTER_API_KEY); then re-run this script"
echo "  - Uninstall:      launchctl unload $DST && rm $DST"
echo ""
