#!/usr/bin/env bash
# Canonical target of the forced-command dispatcher's
# `beta-backend <full-sha>` route.
set -euo pipefail

DEPLOY_SHA="${1:-}"
REPO="${STRUCTURAL_BETA_REPO:-/root/Projects/structural-isomorphism-v4}"
LOCK_FILE="${STRUCTURAL_BETA_DEPLOY_LOCK:-/var/lock/structural-isomorphism-deploy.lock}"

[[ "$#" -eq 1 && "$DEPLOY_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[beta-dispatch] ERROR: expected one full lowercase Git SHA" >&2
  exit 2
}
[[ "$REPO" = /* && -d "$REPO/.git" && ! -L "$REPO" ]] || {
  echo "[beta-dispatch] ERROR: canonical source checkout is missing" >&2
  exit 1
}
[[ "$LOCK_FILE" = /* ]] || {
  echo "[beta-dispatch] ERROR: deploy lock path must be absolute" >&2
  exit 1
}

exec 9>"$LOCK_FILE"
flock -w 2700 9

git -C "$REPO" fetch --prune origin \
  '+refs/heads/main:refs/remotes/origin/main'
git -C "$REPO" cat-file -e "${DEPLOY_SHA}^{commit}"
FETCHED_MAIN_SHA="$(git -C "$REPO" rev-parse --verify refs/remotes/origin/main)"
[[ "$FETCHED_MAIN_SHA" =~ ^[0-9a-f]{40}$ ]] || {
  echo "[beta-dispatch] ERROR: fetched main identity is invalid" >&2
  exit 1
}
git -C "$REPO" merge-base --is-ancestor "$DEPLOY_SHA" "$FETCHED_MAIN_SHA" || {
  echo "[beta-dispatch] ERROR: requested commit is not reachable from origin/main" >&2
  exit 1
}
git -C "$REPO" reset --hard "$DEPLOY_SHA"
[[ "$(git -C "$REPO" rev-parse HEAD)" == "$DEPLOY_SHA" ]] || {
  echo "[beta-dispatch] ERROR: checkout identity changed before deploy" >&2
  exit 1
}

# These three files execute before deploy-vps can build its immutable source
# snapshot. Prove their working-tree bytes are exactly the requested commit,
# so ignored/untracked bootstrap substitutions cannot run.
for bootstrap in \
  scripts/deploy-vps.sh \
  scripts/deploy-versioned-runtime.sh \
  scripts/deploy-retired-module.sh; do
  [[ -f "$REPO/$bootstrap" && ! -L "$REPO/$bootstrap" ]] || {
    echo "[beta-dispatch] ERROR: deploy bootstrap is missing or unsafe" >&2
    exit 1
  }
  EXPECTED_BLOB="$(git -C "$REPO" rev-parse --verify "$DEPLOY_SHA:$bootstrap")"
  ACTUAL_BLOB="$(git -C "$REPO" hash-object --no-filters "$REPO/$bootstrap")"
  [[ "$EXPECTED_BLOB" == "$ACTUAL_BLOB" ]] || {
    echo "[beta-dispatch] ERROR: deploy bootstrap bytes differ from requested commit" >&2
    exit 1
  }
done

SOURCE="$REPO" DEPLOY_COMMIT="$DEPLOY_SHA" STRUCTURAL_DEPLOY_LOCK_HELD=1 \
  bash "$REPO/scripts/deploy-vps.sh"
