***REMOVED*** History Key Audit — 2026-05-20

> **Status:** AUDIT ONLY. Scrub commands are documented but **NOT executed**.
> Force-push and history rewrite are user-approval-only operations.

***REMOVED******REMOVED*** TL;DR

Two real API keys are present in PUBLIC git history of `dada8899/structural-isomorphism` (now PUBLIC, 1 fork by `Eudes-Crabe`).

| Key | Vendor | First commit | Last commit (HEAD?) | Days exposed | Files (current HEAD) |
|---|---|---|---|---|---|
| `sk-or-v1-af9ae735…aea878` | OpenRouter | `aa044dd` (2026-04-16) | YES, still at HEAD | **~34 days** | `web/backend/.env.bak-v1` · `web/scripts/deploy.sh` · `docs/sessions/SESSION-9-HANDOFF.md` |
| `sk-ad62cc6d8…0ae1f` | DeepSeek direct | `a88dbef` (2026-05-13) | YES, still at HEAD | **~7 days** | `docs/reviews/W5-B-researcher-review-2026-05-13.md` · `docs/sessions/SESSION-9-HANDOFF.md` |

Both keys still appear in `main` HEAD (not just history). Open PR ***REMOVED***216 plans to untrack `.env.bak-v1` and rotate, **but does not scrub history**.

**Immediate user action:**
1. **Rotate both keys at vendor dashboards FIRST** (before any scrub) — keys are public, rotate is the only honest mitigation.
2. After rotate, decide: (a) Path A = rotate-only, leave history alone; (b) Path B = filter-repo + force-push + delete fork.

---

***REMOVED******REMOVED*** 1. Audit scope

- Searched all branches + tags + dangling commits via `git log --all --full-history`.
- Pattern set: `sk-...{20,}` / `sk-or-v1-...` / vendor-prefix proximity / `(api_key|api-key|API_KEY|secret|SECRET)\s*=\s*['"][a-zA-Z0-9_-]{30,}`.
- Cross-checked: AWS / GCP / Azure / Stripe / GitHub PAT / HuggingFace / Cohere / Together / Fireworks / Groq / Moonshot / Baidu / Aliyun / Tencent / Bytedance / Volc / Doubao prefixes — **no other vendor keys found**.

---

***REMOVED******REMOVED*** 2. Exposure 1 — OpenRouter `sk-or-v1-af9ae735…aea878`

***REMOVED******REMOVED******REMOVED*** 2.1 Full key (for scrub patterns)
```
sk-or-v1-REDACTED-BY-SCRUB-20260524
```

***REMOVED******REMOVED******REMOVED*** 2.2 Commits where introduced / persisted
| Commit | Date | Files |
|---|---|---|
| `aa044dd` | 2026-04-16 12:36 +0545 | `web/backend/.env.bak-v1`, `web/scripts/deploy.sh` |
| `53f997b` | 2026-05-14 22:29 +0800 | `docs/sessions/SESSION-9-HANDOFF.md` (also lists DeepSeek key) |

***REMOVED******REMOVED******REMOVED*** 2.3 Files at current `main` HEAD
- `web/backend/.env.bak-v1` (full key, plaintext, **PR ***REMOVED***216 plans to delete**)
- `web/scripts/deploy.sh` line 39 (plaintext)
- `docs/sessions/SESSION-9-HANDOFF.md` line 84 (plaintext, full key)
- `docs/sessions/SESSION-5-STARTER.md` (truncated `sk-or-v1-af9ae735...` — partial, still identifying)

***REMOVED******REMOVED******REMOVED*** 2.4 Exposure window
- Commit `aa044dd` landed 2026-04-16. Repo flipped PUBLIC at some point before 2026-05-15 (fork created 2026-05-15 07:39 UTC by `Eudes-Crabe`).
- **Conservative bound: ~5 days public, but could be up to 34 days depending on visibility flip date.**
- **Fork has full history including this key.**

***REMOVED******REMOVED******REMOVED*** 2.5 Verification — does key still match in vendor?
**Unknown.** PR ***REMOVED***216 description says rotation "MUST" be done before public flip — implies it may still be live.

---

***REMOVED******REMOVED*** 3. Exposure 2 — DeepSeek `sk-REDACTED-BY-SCRUB-20260524`

***REMOVED******REMOVED******REMOVED*** 3.1 Full key (for scrub patterns)
```
sk-REDACTED-BY-SCRUB-20260524
```

***REMOVED******REMOVED******REMOVED*** 3.2 Commits where introduced / persisted
| Commit | Date | Files |
|---|---|---|
| `a88dbef` | 2026-05-13 14:09 +0800 | `v4/product/d1_phase_detector/extract_structtuple.py` |
| `fb9a41d` | 2026-05-13 14:26 +0800 | `v4/scripts/b3_ensemble.py` |
| `ed9d73e` | 2026-05-13 16:40 +0800 | `docs/reviews/W5-B-researcher-review-2026-05-13.md` |
| `3e7bd95` | 2026-05-13 16:57 +0800 | `v4/product/d1_phase_detector/extract_structtuple.py`, `v4/scripts/b3_ensemble.py` (migrated to env, but key still cited in review) |
| `53f997b` | 2026-05-14 22:29 +0800 | `docs/sessions/SESSION-9-HANDOFF.md` |

***REMOVED******REMOVED******REMOVED*** 3.3 Files at current `main` HEAD
- `docs/reviews/W5-B-researcher-review-2026-05-13.md` line 111 (plaintext, full key — review cites the bug)
- `docs/sessions/SESSION-9-HANDOFF.md` line 83 (plaintext, full key)
- `v4/scripts/b3_ensemble.py` — **now uses `os.getenv("DEEPSEEK_API_KEY")`** (clean at HEAD, still in history)
- `v4/product/d1_phase_detector/extract_structtuple.py` — **now uses `os.getenv`** (clean at HEAD, still in history)

***REMOVED******REMOVED******REMOVED*** 3.4 Exposure window
- First commit 2026-05-13 14:09, ~7 days. Fully overlaps public window. Fork has it.

***REMOVED******REMOVED******REMOVED*** 3.5 Verification — does key still match in vendor?
**Likely still live.** Per global memory `reference_deepseek_direct_api_2026_05_06.md`, this is the active production DeepSeek direct key. Rotation has NOT been confirmed.

---

***REMOVED******REMOVED*** 4. PUBLIC repo impact assessment

- **Visibility:** PUBLIC since at least 2026-05-15 (fork timestamp evidence).
- **Fork:** `Eudes-Crabe/structural-isomorphism` created 2026-05-15 07:39 UTC, pushed once — **full git history with both keys is mirrored**.
- **Stars:** 1.
- **Open PRs touching .env / secrets:** ***REMOVED***216 (this PR plans rotation, deletes `.env.bak-v1`, but explicitly leaves history alone).
- **Search engines / GitHub code-search indexing:** assume keys are findable by `sk-or-v1-` or `DEEPSEEK_KEY` queries. **Treat both keys as compromised.**

---

***REMOVED******REMOVED*** 5. Pre-scrub clean-up at HEAD (must precede filter-repo)

These plaintext occurrences must first be replaced in a **normal commit** so the post-scrub history doesn't reintroduce them via merge/rebase artifacts:

| File | Action |
|---|---|
| `web/backend/.env.bak-v1` | Delete (PR ***REMOVED***216 already does this) |
| `web/scripts/deploy.sh` line 39 | Replace `sk-or-v1-af9ae735…aea878` → `${OPENROUTER_API_KEY:?set OPENROUTER_API_KEY}` |
| `docs/sessions/SESSION-9-HANDOFF.md` lines 83-84 | Replace key strings with `sk-or-v1-***REDACTED***` and `sk-ad62***REDACTED***` |
| `docs/reviews/W5-B-researcher-review-2026-05-13.md` line 111 | Replace `sk-REDACTED-BY-SCRUB-20260524` → `sk-ad62***REDACTED***` |
| `docs/sessions/SESSION-5-STARTER.md` | Replace truncated `sk-or-v1-af9ae735...` → `sk-or-v1-***REDACTED***` |

Land these as normal commits, then proceed to §6.

---

***REMOVED******REMOVED*** 6. Scrub commands (READY-TO-RUN — do NOT execute without user approval)

***REMOVED******REMOVED******REMOVED*** 6.1 Pre-flight (already partly done)
```bash
***REMOVED*** Backup tag already exists from 2026-05-14:
git tag --list 'pre-filter-repo-backup-*'
***REMOVED*** → pre-filter-repo-backup-20260514-221702

***REMOVED*** Take a fresh backup before any new operation:
cd /Users/dadamini/Projects/structural-isomorphism
git fetch --all --tags
git tag "pre-filter-repo-backup-$(date +%Y%m%d-%H%M%S)"
git push origin --tags
***REMOVED*** Also: full clone backup to ~/Archive/
git clone --mirror . /Users/dadamini/Archive/structural-isomorphism-pre-scrub-$(date +%Y%m%d).git
```

***REMOVED******REMOVED******REMOVED*** 6.2 Install git-filter-repo
```bash
brew install git-filter-repo
git-filter-repo --version  ***REMOVED*** ≥ 2.38 recommended
```

***REMOVED******REMOVED******REMOVED*** 6.3 Create replacement-text file
```bash
cd /Users/dadamini/Projects/structural-isomorphism
cat > /tmp/scrub-replacements.txt <<'EOF'
sk-or-v1-REDACTED-BY-SCRUB-20260524==>sk-or-v1-***REDACTED***
sk-REDACTED-BY-SCRUB-20260524==>sk-ad62***REDACTED***
EOF
```

***REMOVED******REMOVED******REMOVED*** 6.4 Dry-run (analyze, don't write)
```bash
cd /Users/dadamini/Projects/structural-isomorphism
git-filter-repo --replace-text /tmp/scrub-replacements.txt --dry-run
***REMOVED*** Inspect the .git/filter-repo/ output — confirm files touched and replacements counts
```

***REMOVED******REMOVED******REMOVED*** 6.5 Actual rewrite (DESTRUCTIVE — user-approval-only)
```bash
cd /Users/dadamini/Projects/structural-isomorphism
***REMOVED*** filter-repo refuses to run on non-fresh clone by default; use --force after backup confirmed:
git-filter-repo --replace-text /tmp/scrub-replacements.txt --force

***REMOVED*** filter-repo strips remotes for safety; re-add:
git remote add origin git@github.com:dada8899/structural-isomorphism.git
***REMOVED*** or HTTPS:
***REMOVED*** git remote add origin https://github.com/dada8899/structural-isomorphism.git
```

***REMOVED******REMOVED******REMOVED*** 6.6 Force-push all branches + tags
```bash
git push --force --all origin
git push --force --tags origin
***REMOVED*** OR if you want to nuke just main + a few branches:
git push --force origin main
```

***REMOVED******REMOVED******REMOVED*** 6.7 Delete the pre-scrub backup tag from remote (optional, recommended)
After verifying scrub success, remove the backup tag from origin so the old history isn't trivially recoverable from GitHub:
```bash
***REMOVED*** Keep local backup tag — only delete remote
git push --delete origin pre-filter-repo-backup-20260514-221702
***REMOVED*** (keep your own local mirror clone in ~/Archive/ as belt-and-suspenders)
```

***REMOVED******REMOVED******REMOVED*** 6.8 Fork handling
The `Eudes-Crabe/structural-isomorphism` fork retains full history. GitHub will NOT propagate force-push to forks. Options:
- **Contact fork owner** and request they delete or sync from new history.
- **Contact GitHub Support** at https://support.github.com/contact/private-information — request privacy purge of cached views and ask GitHub to flush the fork's old commits.
- **Accept** that the key is mirrored — rotation is the only true mitigation.

---

***REMOVED******REMOVED*** 7. Verification steps (after scrub)

```bash
cd /Users/dadamini/Projects/structural-isomorphism

***REMOVED*** 1. No key in history
git log --all --full-history -p | rg "sk-or-v1-REDACTED-BY-SCRUB-20260524" && echo "FAIL: OpenRouter key still present" || echo "OK: OpenRouter key scrubbed"
git log --all --full-history -p | rg "sk-REDACTED-BY-SCRUB-20260524" && echo "FAIL: DeepSeek key still present" || echo "OK: DeepSeek key scrubbed"

***REMOVED*** 2. No key at HEAD
git grep "sk-or-v1-REDACTED-BY-SCRUB-20260524" || echo "OK"
git grep "sk-REDACTED-BY-SCRUB-20260524" || echo "OK"

***REMOVED*** 3. Branch/tag commit IDs all changed
git for-each-ref --format='%(refname) %(objectname)' refs/heads refs/tags

***REMOVED*** 4. GitHub UI: open any old commit URL (e.g. github.com/dada8899/structural-isomorphism/commit/aa044dd)
***REMOVED*** → should 404 or redirect after force-push + cache flush
```

---

***REMOVED******REMOVED*** 8. Post-scrub impact (must be communicated to team)

- **CI** will re-run on all branches because all commit SHAs change.
- **Open PRs** (***REMOVED***215, ***REMOVED***216, plus any others) will break — must be rebased or recreated against new history.
- **External clones / forks** (including the existing `Eudes-Crabe` fork) will diverge — anyone who pulled will need to `git fetch --all && git reset --hard origin/main` or re-clone.
- **Local working trees on all dev machines** (A 机 / B 机 / VPS) will diverge — same reset needed.
- **`pre-filter-repo-backup-20260514-221702` tag** on remote still holds old history with keys — must be deleted from remote after verification (§6.7).
- **`auto-agent` / cc-daemon** that pull from this repo on schedule must be paused during the rewrite window or they'll auto-restore the old refs.

---

***REMOVED******REMOVED*** 9. Recommended action sequence (user decision required at each step)

1. **NOW (user, no scrub yet):**
   - Rotate OpenRouter key at https://openrouter.ai/keys.
   - Rotate DeepSeek key at https://platform.deepseek.com/api_keys.
   - Update local `.env` + VPS systemd env files with new keys.
   - Restart `phase.bytedance.city` / `cc-daemon` / any service using the keys.

2. **NEXT (auditor → user):**
   - Confirm new keys work end-to-end on prod.
   - Confirm old keys are revoked at vendor dashboard (try a curl against vendor — expect 401).

3. **THEN (user decides Path A vs B):**
   - **Path A (recommended if rotation succeeds):** rotate-only, leave history. Document in CHANGELOG that historical keys are revoked. Lower disruption, lower cleanliness.
   - **Path B (clean cut):** execute §6 scrub. Higher disruption (PRs break, fork diverges, CI re-runs) but historical key strings disappear from GitHub UI.

4. **AFTER:** add `gitleaks` or `detect-secrets` pre-commit hook + GitHub Actions secret scan to prevent recurrence.

---

***REMOVED******REMOVED*** 10. Audit metadata

- Auditor: Claude subagent
- Worktree: `/tmp/wt-audit-p0-history-key-scrub-1779210404`
- Branch: `audit/p0-history-key-scrub-1779210404`
- Base: `origin/main` at `7d4a0b6`
- Commands run: read-only (`git log`, `git grep`, `git show`, `gh api`)
- Destructive ops attempted: **none**
- Output: this document only
