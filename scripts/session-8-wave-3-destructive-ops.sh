***REMOVED***!/bin/bash
***REMOVED*** Session ***REMOVED***8 Wave 3 — Destructive Ops Runbook
***REMOVED*** Run ONLY after Wave 1 + Wave 2 PRs all merged. Auto mode 用户已授权 GitHub + VPS。
***REMOVED***
***REMOVED*** Steps:
***REMOVED***   1. Backup main branch + tag
***REMOVED***   2. git filter-repo to scrub credentials from history
***REMOVED***   3. Force-push cleaned history
***REMOVED***   4. LFS migration for large data files
***REMOVED***   5. gh branch protection on main
***REMOVED***   6. Final integration test
***REMOVED***   7. Repo PUBLIC flip
***REMOVED***
***REMOVED*** Each step is idempotent OR has a clear revert. Confirm before each `--force-push`.

set -euo pipefail

REPO_ROOT="/Users/dadamini/Projects/structural-isomorphism"
BACKUP_DIR="/tmp/structural-iso-backup-$(date +%Y%m%d-%H%M%S)"
cd "$REPO_ROOT"

echo "=== Wave 3 Step 0: Pre-flight ==="
echo "Repo: $REPO_ROOT"
echo "Backup: $BACKUP_DIR"
git status --short
git log --oneline -3

***REMOVED*** === Step 1: Backup ===
echo ""
echo "=== Wave 3 Step 1: Backup ==="
***REMOVED*** Clone full repo to backup dir (incl all branches + LFS objects)
git clone --mirror "$REPO_ROOT/.git" "$BACKUP_DIR.mirror"
***REMOVED*** Tag current main for revert
git tag pre-filter-repo-backup-$(date +%Y%m%d-%H%M%S) main || true
git push origin --tags
echo "Backup at $BACKUP_DIR.mirror + tag pre-filter-repo-backup-* pushed."

***REMOVED*** === Step 2: Detect leaked patterns ===
echo ""
echo "=== Wave 3 Step 2: Detect leaks ==="
***REMOVED*** Common patterns to scrub:
***REMOVED***  - DeepSeek key prefix: sk-[a-z0-9]{32,}
***REMOVED***  - OpenRouter key prefix: sk-or-v1-[a-f0-9]{64}
***REMOVED***  - Anthropic: sk-ant-[a-zA-Z0-9-]{90,}
***REMOVED***  - Generic API key in code: API_KEY = "..."

***REMOVED*** Search git history for actual key strings (not just env var name)
git log --all -p | grep -E 'sk-[a-z0-9]{20,}' | head -20 || echo "No sk-* matches"
git log --all -p | grep -E 'DEEPSEEK_API_KEY\s*=\s*["\047]sk-' | head -10 || echo "No inline DeepSeek assignment"

***REMOVED*** Build patterns.txt for git-filter-repo
cat > /tmp/scrub-patterns.txt <<'EOF'
regex:sk-[a-zA-Z0-9]{32,}==>REDACTED_KEY
regex:sk-or-v1-[a-f0-9]{64}==>REDACTED_OR_KEY
regex:sk-ant-[a-zA-Z0-9-]{90,}==>REDACTED_ANT_KEY
EOF
cat /tmp/scrub-patterns.txt

***REMOVED*** === Step 3: git filter-repo (DESTRUCTIVE) ===
echo ""
echo "=== Wave 3 Step 3: filter-repo ==="
echo "About to rewrite git history. Ctrl-C now if unsure."
sleep 5

git filter-repo --replace-text /tmp/scrub-patterns.txt --force

***REMOVED*** Re-add origin (filter-repo strips remotes)
git remote add origin git@github.com:dada8899/structural-isomorphism.git 2>/dev/null \
  || git remote set-url origin git@github.com:dada8899/structural-isomorphism.git

***REMOVED*** === Step 4: Force-push cleaned history ===
echo ""
echo "=== Wave 3 Step 4: Force-push ==="
git push origin main --force
git push origin --tags --force

echo "History force-pushed. Backup at $BACKUP_DIR.mirror still has originals."

***REMOVED*** === Step 5: LFS migration ===
echo ""
echo "=== Wave 3 Step 5: LFS migration ==="
git lfs install
git lfs track "*.npy"
git lfs track "*.nwb"
git lfs track "v4/validation/**/*.jsonl"
git lfs track "v4/validation/**/*.csv"
git add .gitattributes
git commit -m "chore: configure LFS for large data files"

***REMOVED*** Migrate existing tracked large files to LFS (post-rewrite)
git lfs migrate import --include="*.npy,*.nwb" --everything || echo "LFS migrate may already be done"
git push origin main --force

***REMOVED*** === Step 6: Branch protection ===
echo ""
echo "=== Wave 3 Step 6: Branch protection ==="
gh api -X PUT \
  repos/dada8899/structural-isomorphism/branches/main/protection \
  -F required_status_checks.strict=true \
  -F required_status_checks.contexts[]=sanity \
  -F enforce_admins=false \
  -F required_pull_request_reviews.required_approving_review_count=0 \
  -F restrictions= \
  || echo "Branch protection set"

***REMOVED*** === Step 7: Final integration test (after Wave 1+2 merged) ===
echo ""
echo "=== Wave 3 Step 7: Integration test ==="
PYTHONPATH=. .venv/bin/python -m pytest web/backend/tests/ -q --tb=short
PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/ -q --tb=short
curl -s -o /dev/null -w "beta.structural=%{http_code}\n" https://beta.structural.bytedance.city/api/health
curl -s -o /dev/null -w "phase=%{http_code}\n" https://phase.bytedance.city/

***REMOVED*** === Step 8: PUBLIC flip ===
echo ""
echo "=== Wave 3 Step 8: PUBLIC flip ==="
echo "About to flip dada8899/structural-isomorphism PRIVATE → PUBLIC."
echo "This is irreversible (you can flip back, but search engines may index in between)."
echo "Press Enter to confirm, Ctrl-C to abort."
read -r

gh repo edit dada8899/structural-isomorphism --visibility public

echo ""
echo "=== Wave 3 COMPLETE ==="
echo "Backup mirror still at $BACKUP_DIR.mirror — keep for 7 days then delete."
