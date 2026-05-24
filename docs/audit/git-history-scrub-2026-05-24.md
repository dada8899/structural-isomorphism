***REMOVED*** Git History Scrub — Audit & Runbook (2026-05-24)

> **Status:** DRY-RUN COMPLETE. Refs were not modified. Force-push is BLOCKED on explicit operator GO.
> **Closes P0 item:** `docs/PUBLIC_READINESS_CHECKLIST.md` line 15 — "Credentials scrubbed from git history".
> **Predecessor audit:** `docs/security/2026-05-20-history-key-audit.md` (same two keys identified, this run prepares the actual scrub).

---

***REMOVED******REMOVED*** TL;DR

- **2 real API keys** still live in `dada8899/structural-isomorphism` PUBLIC history (and in current `main` HEAD too).
- **21 raw occurrences across history** (OpenRouter ×9, DeepSeek ×12); **17 distinct file-blob entries** in the filter-repo fast-export.
- **Dry-run rewrite verified:** filtered fast-export has **0** matches of either key; HEAD unchanged; repo size virtually unchanged (text substitution only).
- **Rotate vendor keys FIRST.** Force-push without rotation = security theater (keys are already mirrored in 1 fork + countless clones/caches).
- After GO: 5 commands (rotate-already-done assumed) → tag backup → filter-repo → re-scan → `push --force-with-lease`.

---

***REMOVED******REMOVED*** 1. Scope & method

Scan command:
```bash
git log --all --full-history -p \
  | grep -E "sk-[a-zA-Z0-9_-]{20,}|sk-ant-[a-zA-Z0-9_-]{20,}|sk-or-v1-[a-zA-Z0-9_-]{20,}|sk-proj-[a-zA-Z0-9_-]{20,}|DEEPSEEK_API_KEY|OPENROUTER_API_KEY|ANTHROPIC_API_KEY|Bearer\s+sk-"
```

Cross-check: `gitleaks 8.30.1` full-history scan (24291 `generic-api-key` candidates = noise; 3 `curl-auth-header` hits = pre-redacted doc samples; **all real keys** captured by the manual scan above).

Refs covered: `--all` includes 572 commits across `main` + 116 side branches + 3 tags (`v0.4.0`, `v0.4.1`, `v0.5.0`, plus `pre-filter-repo-backup-20260514-221702` backup tag from a prior unrelated run).

---

***REMOVED******REMOVED*** 2. Findings (redacted)

***REMOVED******REMOVED******REMOVED*** 2.1 Two confirmed live keys

| ***REMOVED*** | Vendor    | Prefix (first 8) | Length | Hits in history | First commit (ages → today) | Files at current HEAD |
|---|-----------|------------------|--------|-----------------|------------------------------|------------------------|
| 1 | OpenRouter | `sk-or-v1-af9ae735` | 64 char body | 9 | `aa044dd` 2026-04-16 (~38d) | `web/scripts/deploy.sh:39`, `docs/sessions/SESSION-9-HANDOFF.md:84` |
| 2 | DeepSeek   | `sk-ad62cc6d`       | 32 char body | 12 | `a88dbef` 2026-05-13 (~11d) | `docs/reviews/W5-B-researcher-review-2026-05-13.md:111`, `docs/sessions/SESSION-9-HANDOFF.md:83` |

Both keys are **also present in `.git/objects` reachable from `main` HEAD** — i.e. they leak via `git clone` today, not just via `git log -p`.

***REMOVED******REMOVED******REMOVED*** 2.2 Commit list (per key, redacted)

OpenRouter `sk-or-v1-af9ae735…` introduced/persisted by:
- `aa044dd` 2026-04-16 — `web/backend/.env.bak-v1`, `web/scripts/deploy.sh`
- `e264e35` — `web/backend/.env.bak-v1` (touched)
- `3c90bb7` — `web/backend/.env.bak-v1` (untrack-only, did not remove)
- `53f997b` 2026-05-14 — `docs/sessions/SESSION-9-HANDOFF.md`
- `1e3282a` 2026-05-20 — `docs/security/2026-05-20-history-key-audit.md` (audit doc; the **audit itself contains the key value** — that's intentional pre-scrub but inflates count)

DeepSeek `sk-ad62cc6d…` introduced/persisted by:
- `a88dbef` 2026-05-13 — `v4/product/d1_phase_detector/extract_structtuple.py`
- `fb9a41d` — `v4/scripts/b3_ensemble.py`
- `3e7bd95` — `v4/product/d1_phase_detector/extract_structtuple.py`, `v4/scripts/b3_ensemble.py`
- `ed9d73e` — `docs/reviews/W5-B-researcher-review-2026-05-13.md`
- `53f997b` 2026-05-14 — `docs/sessions/SESSION-9-HANDOFF.md`
- `1e3282a` 2026-05-20 — `docs/security/2026-05-20-history-key-audit.md`

***REMOVED******REMOVED******REMOVED*** 2.3 No other vendor keys found

Cross-checked patterns for: `sk-ant-` (Anthropic), `sk-proj-` (OpenAI Projects), `AKIA*` (AWS), `xoxb-` (Slack), Stripe, GitHub PAT (`ghp_`/`gho_`), HuggingFace, Cohere, Together, Fireworks, Groq, Moonshot, Volc, Doubao, Tencent — **0 hits**.

The current `.env` (gitignored, untracked) holds the **rotated** DeepSeek key `sk-b34ab7372…` — that one is **NOT in history** (`git log -p | grep` = 0 hits). Good.

---

***REMOVED******REMOVED*** 3. Dry-run results

Command run (via `scripts/scrub-history.sh --dry-run`):
```
git filter-repo --dry-run --force --replace-text scripts/scrub-patterns.txt
```

Output (key numbers):
- Parsed: **578 commit objects** (572 reachable + 6 tag/ref objects)
- Wrote new history in 0.78s
- `.git/filter-repo/fast-export.original`: 261 MB / 2,349,296 lines
- `.git/filter-repo/fast-export.filtered`: 261 MB / 2,345,355 lines (-3941 lines from replacement)
- **17 distinct `REDACTED-BY-SCRUB-20260524` insertions** in filtered export
- **0 matches** of either raw key in filtered export
- Refs **not modified** — `git rev-parse HEAD` unchanged (still `4169928…`); `git log --all --oneline | wc -l` still 572

Repo size delta after `--execute` + `git gc --aggressive`: expected to be **roughly unchanged** (these are short text strings, not large blobs; the same 17 blobs get rewritten with marginally shorter content). Don't expect MB savings — the goal is correctness, not size.

---

***REMOVED******REMOVED*** 4. Artifacts produced

| Path | Tracked? | Purpose |
|---|---|---|
| `scripts/scrub-history.sh` | **YES** (commit it) | Idempotent runner: dry-run / execute / auto-patterns from gitleaks |
| `scripts/scrub-patterns.txt` | **NO** (`.gitignore`d) | Holds RAW leaked keys — never commit |
| `docs/audit/git-history-scrub-2026-05-24.md` | YES | This report |
| `.gitignore` | YES (already tracked) | Added patterns for `scrub-patterns.txt`, `.gitleaks-report.json`, `.scrub-dry-run.log`, `.scrub-pre-backup/` |
| `.scrub-dry-run.log` | NO (`.gitignore`d) | Last dry-run filter-repo stdout |
| `.gitleaks-report.json` (optional) | NO (`.gitignore`d) | Only created when `--auto-patterns` used |

---

***REMOVED******REMOVED*** 5. Run plan (after operator GO)

**Pre-condition:** Both keys must already be **rotated at the vendor dashboard** (the keys have been public for 11–38 days, so rotation is irreducible — scrubbing history without rotation is theater).

***REMOVED******REMOVED******REMOVED*** 5.1 Prep

```bash
cd ~/Projects/structural-isomorphism
git fetch --all --prune
git status   ***REMOVED*** MUST be clean — commit / stash all in-flight first
git checkout main
git pull --ff-only
```

***REMOVED******REMOVED******REMOVED*** 5.2 Rotate keys (vendor dashboard — manual)

- OpenRouter dashboard → revoke `sk-or-v1-af9ae735…`, mint new key
- DeepSeek dashboard → revoke `sk-ad62cc6d…`, mint new key (note: `sk-b34ab7372…` already in `.env` may itself be a rotated successor — confirm chain)
- Update `~/.env`, deploy server `.env`, VPS `~/Projects/structural-isomorphism/web/backend/.env`, GitHub Actions secrets

***REMOVED******REMOVED******REMOVED*** 5.3 Execute scrub

```bash
***REMOVED*** 1. Final confirmation dry-run
bash scripts/scrub-history.sh --dry-run

***REMOVED*** 2. Tag backup + bundle + rewrite history
bash scripts/scrub-history.sh --execute

***REMOVED*** 3. Verify zero residuals
git log --all --full-history -p | grep -c "sk-or-v1-REDACTED-BY-SCRUB-20260524"   ***REMOVED*** → 0
git log --all --full-history -p | grep -c "sk-REDACTED-BY-SCRUB-20260524"                                          ***REMOVED*** → 0
gitleaks detect --no-banner --redact --log-level=warn                                                                    ***REMOVED*** → no high-confidence findings

***REMOVED*** 4. Inspect a sample
git show ${LEAK_COMMIT}:web/scripts/deploy.sh | grep OPENROUTER   ***REMOVED*** should show REDACTED marker
```

***REMOVED******REMOVED******REMOVED*** 5.4 Push (THIS is the irreversible step)

```bash
git remote -v   ***REMOVED*** CONFIRM 'origin' == github.com/dada8899/structural-isomorphism.git
git push --force-with-lease --all origin
git push --force-with-lease --tags origin
```

> `--force-with-lease` aborts if remote moved since last fetch. Run `git fetch` immediately before pushing to refresh the lease.

***REMOVED******REMOVED******REMOVED*** 5.5 Post-push

```bash
***REMOVED*** Re-scan remote
git clone --bare https://github.com/dada8899/structural-isomorphism.git /tmp/post-scrub-check
cd /tmp/post-scrub-check
gitleaks detect --no-banner --redact --log-level=warn   ***REMOVED*** → 0 high-conf
git log --all -p | grep -c "sk-or-v1-af9ae735\|sk-ad62cc6d"   ***REMOVED*** → 0
rm -rf /tmp/post-scrub-check
```

GitHub side:
- The 1 known fork (`Eudes-Crabe/structural-isomorphism`) **WILL NOT** be rewritten — file a takedown request via `https://github.com/contact/dmca` if removal needed, or accept the leak (keys are rotated anyway).
- GitHub support: open a ticket asking to purge cached commit refs for any orphaned SHAs (https://support.github.com/contact — "Sensitive data in commits" template).
- Open PRs / CI runs from before the rewrite will reference dead SHAs — close + reopen if needed.

---

***REMOVED******REMOVED*** 6. Downstream impact

| Stakeholder | What changes | Action required |
|---|---|---|
| Existing clones (you, anyone else) | All commit SHAs change | **Re-clone**, do NOT `git pull` (will produce a merge from old → new history that re-introduces the keys) |
| Open PRs (none at time of dry-run) | Base SHAs invalidated | Recreate against new history |
| CI badges, blog post links pointing to specific commits | Dead SHAs | Update or accept breakage |
| Forks (`Eudes-Crabe/…` × 1) | Untouched | Keys already mirrored — rotation is the only honest fix |
| Zenodo / arXiv links | Bundle DOIs reference repo state at mint time; if pre-scrub, the linked code-state still contains keys, but vendor side already revoked | No action; rotate is sufficient |
| GitHub Actions cache | Will rebuild | None |

---

***REMOVED******REMOVED*** 7. Rollback plan

The `--execute` script creates two safety nets before touching refs:

1. **Backup tag:** `pre-scrub-backup-YYYYMMDD-HHMMSS` on current HEAD (local only — not pushed).
2. **Full bundle:** `.scrub-pre-backup/repo-YYYYMMDD-HHMMSS.bundle` (mirror of all refs at pre-scrub state).

**Recovery (before pushing):**
```bash
git reset --hard refs/tags/pre-scrub-backup-YYYYMMDD-HHMMSS
git tag -d <scrub backup tag>   ***REMOVED*** only after confidence
```

**Recovery (after pushing — disaster path):**
```bash
git clone --mirror .scrub-pre-backup/repo-YYYYMMDD-HHMMSS.bundle restore.git
cd restore.git
git remote set-url origin https://github.com/dada8899/structural-isomorphism.git
git push --mirror --force origin
```
Note: this re-introduces the keys publicly. Only do this if the scrub itself caused unrecoverable data corruption (extremely unlikely with `--replace-text` since blobs are only rewritten in-place).

Keep `refs/original/*` and the bundle for **at least 30 days** after the push, then prune:
```bash
git for-each-ref --format="%(refname)" refs/original/ | xargs -n1 git update-ref -d
rm .scrub-pre-backup/repo-*.bundle
git reflog expire --expire=now --all && git gc --prune=now --aggressive
```

---

***REMOVED******REMOVED*** 8. Why this is final-pre-flip

`PUBLIC_READINESS_CHECKLIST.md` P0 list — once this scrub + push + re-scan succeeds **and** keys are rotated, the only remaining P0 is the TODO sweep in `setup.py` / `pyproject.toml` / papers.

Decision gate ownership: founder `@dada8899` — see checklist line 35 ("Force push scrubbed git history").

---

***REMOVED******REMOVED*** 9. Open questions for operator GO

1. Confirm both keys are rotated? (yes/no — if no, rotate first)
2. Coordinate timing with any in-flight PRs / collaborators? (`gh pr list` showed 0 at dry-run time)
3. Acceptable fork-leak risk for `Eudes-Crabe/structural-isomorphism`? (rotation makes it moot; takedown is optional)
4. Run a `git gc --aggressive` after the rewrite to actually shrink `.git`? (recommended; will drop ~196 prune-packable objects + reachable blob duplicates)

Answer these in the GO message, then run section 5.3 / 5.4.
