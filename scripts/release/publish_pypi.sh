#!/usr/bin/env bash
# Publish soc-pipeline + guarded-llm to PyPI (1-click)
#
# Requires: PYPI_TOKEN env var (project-scoped recommended)
# Usage:
#   PYPI_TOKEN=pypi-xxx bash scripts/release/publish_pypi.sh
#   # Optional dry-run to TestPyPI first:
#   TESTPYPI_TOKEN=pypi-xxx bash scripts/release/publish_pypi.sh --test
#
# Token format: pypi-AgEIcHlwaS5vcmcCJ...
# Get one at https://pypi.org/manage/account/token/

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

DRY_RUN=0
if [ "${1:-}" = "--test" ]; then
  DRY_RUN=1
fi

if [ $DRY_RUN -eq 1 ]; then
  if [ -z "${TESTPYPI_TOKEN:-}" ]; then
    echo "ERROR: TESTPYPI_TOKEN env var required for --test mode"
    echo "Get token at https://test.pypi.org/manage/account/token/"
    exit 1
  fi
else
  if [ -z "${PYPI_TOKEN:-}" ]; then
    echo "ERROR: PYPI_TOKEN env var required"
    echo "Get token at https://pypi.org/manage/account/token/"
    exit 1
  fi
fi

# Verify wheels exist; if not, build them
for pkg in soc-pipeline guarded-llm; do
  if [ ! -d "packages/$pkg/dist" ] || [ -z "$(ls -A packages/$pkg/dist 2>/dev/null)" ]; then
    echo "Building $pkg (no dist/ found)..."
    pushd "packages/$pkg" > /dev/null
    rm -rf dist/ build/
    python3 -m build
    popd > /dev/null
  fi
done

# Twine check before upload
python3 -m twine check packages/soc-pipeline/dist/* packages/guarded-llm/dist/*

if [ $DRY_RUN -eq 1 ]; then
  echo ""
  echo "=== DRY RUN: uploading to TestPyPI ==="
  python3 -m twine upload --repository testpypi \
    packages/soc-pipeline/dist/* \
    -u __token__ -p "$TESTPYPI_TOKEN"
  python3 -m twine upload --repository testpypi \
    packages/guarded-llm/dist/* \
    -u __token__ -p "$TESTPYPI_TOKEN"
  echo ""
  echo "Test install:"
  echo "  pip install -i https://test.pypi.org/simple/ soc-pipeline guarded-llm"
else
  echo ""
  echo "=== PRODUCTION: uploading to PyPI ==="
  python3 -m twine upload \
    packages/soc-pipeline/dist/* \
    -u __token__ -p "$PYPI_TOKEN"
  python3 -m twine upload \
    packages/guarded-llm/dist/* \
    -u __token__ -p "$PYPI_TOKEN"
  echo ""
  echo "Published soc-pipeline + guarded-llm to PyPI"
  echo "Verify:"
  echo "  https://pypi.org/project/soc-pipeline/"
  echo "  https://pypi.org/project/guarded-llm/"
fi
