#!/usr/bin/env bash
# Mint Zenodo DOI for dataset/v1/ bundle (1-click, NOT auto-publish)
#
# Requires: ZENODO_ACCESS_TOKEN env var
# Usage:
#   ZENODO_ACCESS_TOKEN=xxx bash scripts/release/mint_zenodo.sh
#   # Optional sandbox dry-run:
#   ZENODO_ACCESS_TOKEN=xxx ZENODO_SANDBOX=1 bash scripts/release/mint_zenodo.sh
#
# Get personal access token at https://zenodo.org/account/settings/applications/tokens/new/
# Scopes required: deposit:write, deposit:actions

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

if [ -z "${ZENODO_ACCESS_TOKEN:-}" ]; then
  echo "ERROR: ZENODO_ACCESS_TOKEN env var required"
  echo "Get token at https://zenodo.org/account/settings/applications/tokens/new/"
  echo "Scopes: deposit:write + deposit:actions"
  exit 1
fi

# Choose endpoint
if [ "${ZENODO_SANDBOX:-0}" = "1" ]; then
  ZENODO_API="https://sandbox.zenodo.org/api"
  ZENODO_WEB="https://sandbox.zenodo.org"
  echo "Using Zenodo SANDBOX (test environment)"
else
  ZENODO_API="https://zenodo.org/api"
  ZENODO_WEB="https://zenodo.org"
  echo "Using Zenodo PRODUCTION"
fi

if [ ! -d "dataset/v1" ]; then
  echo "ERROR: dataset/v1/ not found. Run W8-A scripts first."
  exit 1
fi

if [ ! -f "scripts/release/zenodo-metadata.json" ]; then
  echo "ERROR: scripts/release/zenodo-metadata.json missing"
  exit 1
fi

# Step 1: Tarball
TARBALL="/tmp/structural-isomorphism-dataset-v1.tar.gz"
echo "Creating tarball: $TARBALL"
tar czf "$TARBALL" \
  --exclude='.DS_Store' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  -C dataset v1
TARBALL_SIZE=$(du -h "$TARBALL" | cut -f1)
echo "  size: $TARBALL_SIZE"

# Step 2: Create deposition
echo ""
echo "Step 2: Create deposition..."
DEPOSITION=$(curl -s -X POST "$ZENODO_API/deposit/depositions" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZENODO_ACCESS_TOKEN" \
  -d '{}')

DEPOSITION_ID=$(echo "$DEPOSITION" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('id') or (_:=sys.stderr.write(json.dumps(d, indent=2)+chr(10))) or sys.exit(1))")
BUCKET_URL=$(echo "$DEPOSITION" | python3 -c "import sys,json; print(json.load(sys.stdin)['links']['bucket'])")
echo "  deposition_id: $DEPOSITION_ID"
echo "  bucket: $BUCKET_URL"

# Step 3: Upload tarball
echo ""
echo "Step 3: Upload tarball to bucket..."
curl -s -X PUT "$BUCKET_URL/structural-isomorphism-dataset-v1.tar.gz" \
  -H "Authorization: Bearer $ZENODO_ACCESS_TOKEN" \
  --data-binary "@$TARBALL" > /tmp/zenodo_upload_resp.json
UPLOAD_SIZE=$(python3 -c "import json; d=json.load(open('/tmp/zenodo_upload_resp.json')); print(d.get('size', 'unknown'))")
echo "  uploaded bytes: $UPLOAD_SIZE"

# Step 4: Attach metadata
echo ""
echo "Step 4: Attach metadata..."
curl -s -X PUT "$ZENODO_API/deposit/depositions/$DEPOSITION_ID" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $ZENODO_ACCESS_TOKEN" \
  -d @scripts/release/zenodo-metadata.json > /tmp/zenodo_meta_resp.json
META_STATUS=$(python3 -c "import json; d=json.load(open('/tmp/zenodo_meta_resp.json')); print(d.get('state', 'error'))")
echo "  state: $META_STATUS"

# Step 5: Print review URL — NOT auto-publish
echo ""
echo "========================================================"
echo "DEPOSITION CREATED (not yet published)"
echo "========================================================"
echo ""
echo "Review URL:"
echo "  $ZENODO_WEB/deposit/$DEPOSITION_ID"
echo ""
echo "Steps to complete:"
echo "  1. Visit the URL above"
echo "  2. Review metadata + file"
echo "  3. Click 'Publish' button (this mints the DOI)"
echo "  4. Copy the DOI (format: 10.5281/zenodo.XXXXXXX)"
echo "  5. Update:"
echo "     - dataset/v1/CITATION.cff (set 'doi' field)"
echo "     - dataset/v1/README.md (add DOI badge)"
echo "     - paper/arxiv-submission/SUBMISSION_METADATA.md (add to Comments)"
echo "     - scripts/release/zenodo-metadata.json (update related_identifiers if needed)"
echo ""
echo "Once published, dataset will be at:"
echo "  $ZENODO_WEB/records/<published-id>"
echo "  DOI: https://doi.org/10.5281/zenodo.<published-id>"
