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

# CI=true tells pnpm (and most other JS tooling) to skip interactive prompts.
# Without it, pnpm hits ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY when it
# detects a modules dir change and asks the operator to confirm the purge —
# SSH sessions launched by GitHub Actions don't allocate a TTY, so the
# deploy aborts. Exporting here covers any pnpm invocation downstream
# (restore-models.sh, systemd unit PreStart, web/* installs, etc.).
# Mirrors session-10 W2-F 防灾 deploy three-piece: deploy must work
# non-interactive.
export CI=true

SOURCE="${SOURCE:-/root/Projects/structural-isomorphism-v4}"
TARGET="${TARGET:-/root/Projects/structural-isomorphism}"
SERVICE="${SERVICE:-structural-web}"
ARTIFACT_ROOT="${ARTIFACT_ROOT:-/root/structural-artifacts/current}"
PREVIOUS_SHA="${PREVIOUS_SHA:-}"
DRY_RUN=0
PRUNE=0
RUNTIME_BACKUP=""

rollback_deploy() {
  local reason="$1"
  echo "[deploy] FAIL: $reason — rolling back" >&2
  set +e
  if [[ -n "$PREVIOUS_SHA" ]] && git -C "$SOURCE" cat-file -e "$PREVIOUS_SHA^{commit}" 2>/dev/null; then
    git -C "$SOURCE" reset --hard "$PREVIOUS_SHA"
    rsync -av "${EXCLUDES[@]}" "$SOURCE/" "$TARGET/"
  fi
  if [[ -n "$RUNTIME_BACKUP" && -f "$RUNTIME_BACKUP" ]]; then
    cp -a "$RUNTIME_BACKUP" "$TARGET/web/backend/.env.runtime"
  fi
  systemctl restart "$SERVICE"
  systemctl is-active "$SERVICE" || true
  exit 1
}

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

  echo "[deploy] Validating production artifact bundle..."
  for required in \
    "$ARTIFACT_ROOT/manifest.json" \
    "$ARTIFACT_ROOT/kb-expanded.jsonl" \
    "$ARTIFACT_ROOT/kb_v2_embeddings.npy" \
    "$ARTIFACT_ROOT/structural-v2"; do
    [[ -e "$required" ]] || { echo "[deploy] FAIL: missing artifact $required" >&2; exit 1; }
  done
  (
    cd "$TARGET/web/backend"
    "$TARGET/venv/bin/python" - <<PY
from services.artifact_manifest import validate_artifact_bundle
print(validate_artifact_bundle(
    "$ARTIFACT_ROOT/manifest.json",
    kb_path="$ARTIFACT_ROOT/kb-expanded.jsonl",
    embeddings_path="$ARTIFACT_ROOT/kb_v2_embeddings.npy",
    model_path="$ARTIFACT_ROOT/structural-v2",
))
PY
  )

  # Session #16: write build/deploy fingerprint so /api/version returns real
  # values. Without this, prod returns git_sha="unknown" and dogfood scripts
  # can't fingerprint-check what code is actually running (session #15 root
  # cause: 5 days of stale-code deploys went undetected).
  echo "[deploy] Writing runtime fingerprint to web/backend/.env.runtime..."
  RUNTIME_BACKUP="$(mktemp)"
  if [[ -f "$TARGET/web/backend/.env.runtime" ]]; then
    cp -a "$TARGET/web/backend/.env.runtime" "$RUNTIME_BACKUP"
  else
    rm -f "$RUNTIME_BACKUP"
    RUNTIME_BACKUP=""
  fi
  # Validator session-#16 P2 — warn early if SOURCE has no .git, since
  # that's exactly when git_sha silently becomes 'unknown' and the
  # session-#15 incident class can re-emerge.
  if [[ ! -d "$SOURCE/.git" ]]; then
    echo "[deploy] WARN: $SOURCE has no .git directory; git_sha will be 'unknown'." >&2
  fi
  GIT_SHA="$(cd "$SOURCE" && git rev-parse --short=12 HEAD 2>/dev/null || echo unknown)"
  DEPLOYED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  cat > "$TARGET/web/backend/.env.runtime" <<EOF
# Auto-generated by deploy-vps.sh on every deploy. DO NOT edit by hand —
# next deploy overwrites it. Loaded by main.py with override=True so it wins
# over anything in .env.
STRUCTURAL_GIT_SHA=$GIT_SHA
STRUCTURAL_BUILD_DATE=$DEPLOYED_AT
STRUCTURAL_DEPLOYED_AT=$DEPLOYED_AT
STRUCTURAL_ENV=prod
STRUCTURAL_ARTIFACT_MANIFEST=$ARTIFACT_ROOT/manifest.json
STRUCTURAL_DATA_DIR=$ARTIFACT_ROOT
STRUCTURAL_KB_FILE=kb-expanded.jsonl
STRUCTURAL_MODEL_PATH=$ARTIFACT_ROOT/structural-v2
STRUCTURAL_PRECOMPUTED_EMBEDDINGS=$ARTIFACT_ROOT/kb_v2_embeddings.npy
EOF
  echo "[deploy]   git_sha=$GIT_SHA"
  echo "[deploy]   deployed_at=$DEPLOYED_AT"

  echo "[deploy] Restarting $SERVICE..."
  systemctl restart "$SERVICE"
  sleep 5
  systemctl is-active "$SERVICE" || rollback_deploy "service not active"
  HEALTH="$(curl -fsS --max-time 10 'http://127.0.0.1:5004/api/health?deep=1')" \
    || rollback_deploy "deep health request failed"
  if ! HEALTH="$HEALTH" "$TARGET/venv/bin/python" - <<'PY'
import json
import os

body = json.loads(os.environ["HEALTH"])
assert body["status"] == "ok", body
assert body["kb_size"] == 4443, body
assert body["artifact_id"] == "structural-v2-kb4443-20260711", body
assert body["embedding_shape"] == [4443, 768], body
PY
  then
    rollback_deploy "deep health payload invalid"
  fi
  rm -f "$RUNTIME_BACKUP"
  echo "[deploy] OK"
fi
