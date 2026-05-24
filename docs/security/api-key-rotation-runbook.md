# API Key Rotation Runbook

> **Status**: 2026-05-13 — this runbook documents the process for rotating LLM
> API keys (DeepSeek, OpenRouter, etc.) used by the structural-isomorphism
> codebase, and for **scrubbing** keys that were accidentally committed to git
> history.

Audience: maintainers of `structural-isomorphism`. Anyone with merge access.

---

## When to rotate

Rotate **immediately** if any of these is true:

1. A key was ever committed to a public-facing branch (even if reverted —
   git history retains it).
2. A key appears in any pre-merge PR diff that touched `*.py`, `*.md`,
   `*.ipynb`, `*.sh`, `*.yaml`, `*.json`, `*.env*` (other than `.env.example`).
3. A key was pasted into Slack, Discord, GitHub Issues, screenshots, or any
   third-party tool (LLM agents, code search, log aggregators, monitoring).
4. A key is in a Docker image, container registry, CI artifact, or any
   uploaded archive (tarball, zip, S3 bucket).
5. A teammate left the team / lost a device that had the key.
6. Provider notifies you of suspicious usage / billing spike.

If unsure, **rotate**. Keys are cheap to rotate; breaches are not.

---

## Step 1 — Provision a new key

### DeepSeek

1. Visit https://platform.deepseek.com/api_keys
2. Click **Create API Key** → name it descriptively (e.g.
   `structural-isomorphism-2026-05-13`).
3. Copy the new key. **Do not** paste it into a chat / commit / screenshot.

### OpenRouter (if used)

1. Visit https://openrouter.ai/settings/keys
2. **Create Key** → name it.
3. Copy the new key.

Put the new key in `~/.env.local` or a password manager — **never** in repo
files other than `.env` (which is gitignored).

---

## Step 2 — Update local environment

Edit your local `.env` (which is gitignored):

```bash
cd /path/to/structural-isomorphism
cp .env.example .env  # if you don't already have one
$EDITOR .env
# Fill in: DEEPSEEK_API_KEY=<new-key>
set -a; source .env; set +a
```

Verify the new key works:

```bash
.venv/bin/python -c "
import os, urllib.request, json
k = os.environ['DEEPSEEK_API_KEY']
req = urllib.request.Request(
    'https://api.deepseek.com/v1/chat/completions',
    data=json.dumps({
        'model': 'deepseek-v4-flash',
        'messages': [{'role': 'user', 'content': 'say ok'}],
        'max_tokens': 5,
    }).encode(),
    headers={'Authorization': f'Bearer {k}', 'Content-Type': 'application/json'},
)
r = urllib.request.urlopen(req, timeout=30)
print('OK:', r.status)
"
```

Should print `OK: 200`. If it doesn't, the key is wrong or the account is
out of credit.

---

## Step 3 — Update CI / production secrets

If keys are used in CI or on the VPS, update them there too:

```bash
# GitHub Actions secrets (if used)
gh secret set DEEPSEEK_API_KEY --body "$DEEPSEEK_API_KEY" --repo dada8899/structural-isomorphism

# VPS (43.156.233.71)
ssh root@43.156.233.71 'cat > /root/Projects/structural-isomorphism/.env <<EOF
DEEPSEEK_API_KEY=<new-key>
EOF
chmod 600 /root/Projects/structural-isomorphism/.env'

# Then restart any services that read the env at startup
ssh root@43.156.233.71 'systemctl restart si-* 2>/dev/null || true'
```

---

## Step 4 — Revoke the old key

**Only after step 3 succeeds and you have verified the new key works in
production.**

### DeepSeek

1. https://platform.deepseek.com/api_keys
2. Click the **Delete** icon next to the old key.
3. Confirm.

### OpenRouter

1. https://openrouter.ai/settings/keys
2. Find the old key → click ⋯ → **Revoke**.

---

## Step 5 — Scrub git history (if key was committed)

If the key was ever in a commit (even a reverted one), `git log` and any
GitHub fork / mirror / cache still has it. You must rewrite history.

### Option A: `git filter-repo` (preferred)

```bash
# Install once
pip install --user git-filter-repo

# Back up the repo first
cd /tmp
git clone --mirror git@github.com:dada8899/structural-isomorphism.git si-backup.git

# Then in your working clone:
cd /path/to/structural-isomorphism
git filter-repo --replace-text <(echo 'sk-OLDKEYHEX==><REDACTED-KEY>')

# Force-push (DESTROYS shared history; coordinate with all collaborators)
git push --force --all origin
git push --force --tags origin
```

### Option B: BFG Repo-Cleaner (faster for large repos)

```bash
brew install bfg

cd /path/to/structural-isomorphism
bfg --replace-text <(echo 'sk-OLDKEYHEX==><REDACTED-KEY>') --no-blob-protection
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force --all origin
git push --force --tags origin
```

### After force-push

1. Notify all collaborators — they must `git fetch && git reset --hard origin/main`
   on their local clones. Anyone who has the repo cached locally (or in a
   subagent worktree, in an editor's index, etc.) will retain the leaked key
   until they sync.
2. **Delete all forks** of the repo. GitHub Support can help if a fork is
   unresponsive. Forks retain leaked secrets forever otherwise.
3. Open a **GitHub Support ticket** asking for "secret scanning + cache
   invalidation" on the repo. They can purge their internal caches.
4. Update the README with a note: "history rewritten YYYY-MM-DD; pre-history
   clones must be reset".

---

## Step 6 — Audit + lessons

After every rotation, fill in:

| Field | Value |
|---|---|
| Date detected | YYYY-MM-DD |
| Date rotated | YYYY-MM-DD |
| Was key in public commit? | yes / no |
| Estimated exposure window | hours / days / weeks |
| Provider billing — any anomaly? | (paste link to dashboard) |
| Root cause | (e.g. "hardcoded in `b3_ensemble.py`, missed in pre-commit hook") |
| Preventive fix | (e.g. "added `gitleaks` to pre-commit, env-var enforced") |

File this audit at `docs/security/incidents/YYYY-MM-DD-deepseek-key-leak.md`.

---

## Preventive checklist (do this once, then forget)

- [ ] `.env` and `.env.local` in `.gitignore` (verify: `grep -E '^\.env' .gitignore`)
- [ ] `.env.example` committed with placeholder values only
- [ ] All code reads keys via `os.getenv("PROVIDER_API_KEY")` and aborts loudly
      if unset (no hidden fallback to a hardcoded default!)
- [ ] Pre-commit hook (`gitleaks` / `trufflehog`) scans staged diff for
      `sk-[a-zA-Z0-9]{20,}`-shaped strings
- [ ] CI runs the same scan on every PR (catch keys missed locally)
- [ ] Code review: any diff that adds `sk-` to a source file is auto-rejected

```bash
# One-time pre-commit setup
cat >> .git/hooks/pre-commit <<'SH'
#!/usr/bin/env bash
if git diff --cached --name-only -z | xargs -0 grep -lE 'sk-[a-zA-Z0-9]{20,}' 2>/dev/null; then
    echo "ERROR: API-key-shaped string detected in staged diff. Aborting commit." >&2
    echo "If this is a false positive (test fixture etc.), add to .gitleaks-allow." >&2
    exit 1
fi
SH
chmod +x .git/hooks/pre-commit
```

---

## Incident log

| Date | Key | Action | Notes |
|---|---|---|---|
| 2026-05-13 | DeepSeek (key prefix redacted in this doc; see W5-B review for full string) | env-var migration | Key still active; **not yet rotated**. Was hardcoded in `v4/scripts/b3_ensemble.py:48` and `v4/product/d1_phase_detector/extract_structtuple.py:46` from session #1-2; this commit replaces both with `os.getenv("DEEPSEEK_API_KEY")` and adds the loud-abort guard. **The leaked string still lives in `git log` and must be rotated + history-scrubbed before any public release. Requires user authorization to rotate.** |

When rotation completes, append a new row.
