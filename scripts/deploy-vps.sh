#!/usr/bin/env bash
# deploy-vps.sh — sync git source → deploy target SAFELY
#
# 防灾原则:
#   1. 默认 rsync -avu (update, NOT delete)
#   2. 必须传 --prune-with-safety-list 才会 delete
#   3. delete 前 dry-run 显示 list 并要求人工确认
#   4. excludes 包含 models/ + .env + 大数据，避免覆盖 deploy target 独有 fixture
#
# 事故复盘 (2026-05-14, prod 502 25min):
#   `rsync -av --delete --exclude=.git --exclude=.venv v4/ structural-isomorphism/`
#   删了 deploy target 独有 models/structural-v2/ → backend startup fail →
#   systemd loop → 502. 本脚本默认 update-only 杜绝该路径。

set -euo pipefail

SOURCE="${SOURCE:-/root/Projects/structural-isomorphism-v4}"
TARGET="${TARGET:-/root/Projects/structural-isomorphism}"
SERVICE="${SERVICE:-structural-web}"
DRY_RUN=0
PRUNE=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --prune-with-safety-list) PRUNE=1 ;;
    -h|--help)
      cat <<EOF
Usage: $0 [--dry-run] [--prune-with-safety-list]

Default: rsync -avu (update only, no delete). Safe.

Flags:
  --dry-run                   Show what would happen, do not write
  --prune-with-safety-list    Enable --delete, preview list, require confirm

Env vars (with defaults shown):
  SOURCE=$SOURCE
  TARGET=$TARGET
  SERVICE=$SERVICE
EOF
      exit 0 ;;
  esac
done

EXCLUDES=(
  --exclude=.git/
  --exclude=.venv/
  --exclude=venv/
  --exclude=__pycache__/
  --exclude=node_modules/
  --exclude=.next/
  --exclude=*.pyc
  --exclude=.env
  --exclude=.env.production
  --exclude=models/                # CRITICAL: 大文件 fixture, restore-models.sh 维护
  --exclude=data/large_*
  --exclude=*.npy
  --exclude=*.bin
)

RSYNC_FLAGS="-avu"  # update only, NOT delete
if [[ "$PRUNE" == "1" ]]; then
  echo "[deploy] PRUNE mode — dry-run preview:"
  rsync -avn --delete "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/" | grep '^deleting' || echo "  (no files would be deleted)"
  echo
  read -p "[deploy] Proceed with delete? [y/N] " ans
  [[ "$ans" =~ ^[Yy]$ ]] || { echo "[deploy] aborted"; exit 1; }
  RSYNC_FLAGS="$RSYNC_FLAGS --delete"
fi

CMD=(rsync $RSYNC_FLAGS "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/")
if [[ "$DRY_RUN" == "1" ]]; then
  CMD=(rsync -avn "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/")
fi

echo "[deploy] Running: ${CMD[*]}"
"${CMD[@]}" | tail -10

if [[ "$DRY_RUN" == "0" ]]; then
  echo "[deploy] Ensuring models exist..."
  bash "$TARGET/scripts/restore-models.sh"
  echo "[deploy] Restarting $SERVICE..."
  systemctl restart "$SERVICE"
  sleep 5
  systemctl is-active "$SERVICE" || { echo "[deploy] FAIL: service not active"; journalctl -u "$SERVICE" -n 20 --no-pager; exit 1; }
  echo "[deploy] OK"
fi
