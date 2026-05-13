#!/usr/bin/env bash
# Create GitHub release v0.3.0 with wheels + dataset runbook as attachments
#
# Requires: gh CLI authenticated (gh auth status)
# Usage:
#   bash scripts/release/create_github_release.sh
#   # Optional draft mode:
#   DRAFT=1 bash scripts/release/create_github_release.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

VERSION="v0.3.0"

if ! command -v gh > /dev/null 2>&1; then
  echo "ERROR: gh CLI not installed. brew install gh"
  exit 1
fi

if ! gh auth status > /dev/null 2>&1; then
  echo "ERROR: gh CLI not authenticated. Run: gh auth login"
  exit 1
fi

# Verify wheels exist (rebuild if missing)
for pkg in soc-pipeline guarded-llm; do
  if [ ! -d "packages/$pkg/dist" ] || [ -z "$(ls -A packages/$pkg/dist 2>/dev/null)" ]; then
    echo "Building $pkg (no dist/ found)..."
    pushd "packages/$pkg" > /dev/null
    rm -rf dist/ build/
    python3 -m build
    popd > /dev/null
  fi
done

if [ ! -f "docs/release/v0.3.0-release-notes.md" ]; then
  echo "ERROR: docs/release/v0.3.0-release-notes.md missing"
  exit 1
fi

DRAFT_FLAG=""
if [ "${DRAFT:-0}" = "1" ]; then
  DRAFT_FLAG="--draft"
  echo "Mode: DRAFT (review before publish)"
else
  echo "Mode: PUBLISH"
fi

# Check tag doesn't already exist
if git rev-parse "$VERSION" >/dev/null 2>&1; then
  echo "Tag $VERSION already exists locally. Skipping tag creation."
else
  echo "Creating tag $VERSION on HEAD..."
  git tag -a "$VERSION" -m "structural-isomorphism v0.3.0 — session #3 mega-sprint + session #4 F-track release prep"
  git push origin "$VERSION"
fi

# Create release
echo ""
echo "Creating GitHub release..."
gh release create "$VERSION" \
  --title "structural-isomorphism v0.3.0 — session #3 mega-sprint" \
  --notes-file docs/release/v0.3.0-release-notes.md \
  --target main \
  $DRAFT_FLAG \
  packages/soc-pipeline/dist/soc_pipeline-*.whl \
  packages/soc-pipeline/dist/soc_pipeline-*.tar.gz \
  packages/guarded-llm/dist/guarded_llm-*.whl \
  packages/guarded-llm/dist/guarded_llm-*.tar.gz \
  dataset/v1/MINT_DOI_RUNBOOK.md \
  dataset/v1/README.md \
  dataset/v1/CITATION.cff

echo ""
echo "Release created."
echo "URL: $(gh release view "$VERSION" --json url -q .url)"
