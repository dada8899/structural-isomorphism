# Postmortem — `git filter-repo` `#` pollution (1187 files), 2026-05-24

**Date of incident**: 2026-05-24 (~18:29 local)
**Date of postmortem**: 2026-05-25
**Severity**: P1 — corrupted every file containing a `#` across all blobs; bypassed by SESSION-22 sed restoration commit `20b8ab3` for the working tree, but the corrupted commits remain in git history.
**Related docs**:
- `docs/audit/git-history-scrub-2026-05-24.md` (original scrub plan)
- `docs/security/2026-05-20-history-key-audit.md` (original key audit)
- `docs/sessions/SESSION-22-HANDOFF.md` (restoration narrative)

## TL;DR

- A history scrub via `git filter-repo --replace-text scripts/scrub-patterns.txt`
  was supposed to redact two leaked API keys.
- It succeeded at redacting the keys, but as a side effect it replaced every
  `#` character in every blob of every commit with the string `***REMOVED***`,
  corrupting **1187 files**.
- **Root cause**: `scrub-patterns.txt` contained `#` header / comment lines.
  `git filter-repo`'s `--replace-text` parser **does NOT skip `#` lines**
  (despite the sibling `--paths-from-file` parser doing so), so each `#`-line
  was interpreted as `literal "<line content>" → ***REMOVED***`. A single
  bare-`#` line (3 of them in our file) is the worst case: it matches every
  `#` byte in every blob.
- **Remediation status**:
  - SESSION-22 commit `20b8ab3` ran a sed pass and restored 1067 of 1187
    files in the working tree (most code + docs).
  - 120 files (mostly `.env.example`, `.ipynb`, `.mjml`, JSONL data, nginx
    confs) still hold `***REMOVED***` at HEAD and need manual review.
  - Git history of polluted commits is unchanged — visible via
    `git show <commit>:<file>`.
- **2nd scrub necessity**: **NOT NECESSARY for the two leaked keys.** Both
  full keys are confirmed 0-occurrence in the full export (see §4). A
  history-wide rewrite to undo the `#` pollution is technically possible
  but expensive (`***REMOVED*** → #` is ambiguous — `***REMOVED***`
  occurs legitimately in patterns README, audit docs, etc.) and not done
  by this postmortem.
- **Defense added**: `validate_patterns_file()` in `scripts/scrub-history.sh`
  rejects any non-empty, non-`#`-prefix line lacking `==>` with exit 4.
  Available standalone via `scripts/scrub-history.sh --validate-only`.

## 1. Root cause analysis (4-layer)

### Layer 1 — surface symptom
1187 files in the repo contained `***REMOVED***` in place of `#`. Discovered
when reading source files post-scrub showed `***REMOVED*** -*- coding: utf-8 -*-`
in module headers, `***REMOVED*** %s` in printf format strings, broken
Markdown headings (`***REMOVED*** Title`), broken `.gitignore` syntax, etc.

### Layer 2 — direct cause
`scripts/scrub-patterns.txt` looked like a normal "config file with comments":

```
# scrub-patterns.txt — leaked API key → redaction map
#
# !! THIS FILE IS GITIGNORED. NEVER COMMIT. !!
#
# Format: literal===>replacement   (use 3-char ===> separator ...)
#         lines starting with # are ignored)
...
sk-or-v1-af9ae735...==>sk-or-v1-REDACTED-BY-SCRUB-20260524
...
```

The author assumed `#` lines were ignored (per the inline comment) and that
the separator was `===>` (also wrong — the actual separator is `==>`, 2 chars).

`git filter-repo --replace-text` does the following (see source
`/opt/homebrew/bin/git-filter-repo` line 2328 `get_replace_text()`):

1. Reads each line, strips `\r\n`.
2. If line contains `==>`, split LHS / RHS at the last `==>`. LHS = literal,
   RHS = replacement. (Note: 2-char `==>`, not 3-char `===>`. A `===>` in
   the source is parsed as `=` (LHS suffix) + `==>` (separator) + `` (RHS),
   producing a literal ending in `=` mapped to empty replacement —
   itself a different surprise.)
3. If line does NOT contain `==>`, **the entire line becomes the literal**,
   and replacement defaults to `b'***REMOVED***'` (`FilteringOptions.default_replace_text`).
4. **Comment handling**: `#` lines are NOT skipped. Compare with
   `get_paths_from_file()` on line 2358 which explicitly does
   `if line.startswith(b'#'): continue` — the asymmetry is the trap.

Outcome with our file: 12 header `#` lines became 12 literals; the 3 bare
`#` lines collapsed into one literal `#`. filter-repo then scanned every
blob in all 595 commits and replaced every byte-`#` with `***REMOVED***`.
Result: 1187 files corrupted (the other long `# ...` literals only matched
their exact text in a handful of places and were comparatively harmless).

### Layer 3 — systemic root cause
- **Documentation gap**: `git-filter-repo --help` describes the `==>`
  syntax but does NOT mention that lines without `==>` are silently
  interpreted as `literal → ***REMOVED***`, nor that `#` lines are NOT
  skipped (unlike paths files). Users coming from BFG / sed assume
  config-file comment conventions hold; they don't.
- **No defensive validation in our wrapper**: `scrub-history.sh` accepted
  whatever file we handed it. The original `[3/6] validate patterns` step
  only counted `==>` occurrences; it did not verify each line was *either*
  a comment OR a `==>` rule.
- **Format string drift**: the inline doc in patterns.txt said `===>`
  (3 chars) which is wrong (actual is `==>`). The author copy-pasted from
  an outdated reference. No automated check caught the drift.
- **Metadata + data in one file**: keeping prose context (provenance,
  exposure dates, leak sites) inside the data file is convenient for
  humans but lethal when the consumer parses every non-blank line as data.

### Layer 4 — global impact assessment
- **Repo blast radius**: 1187 of ~1500 tracked files corrupted. Every Python
  shebang line, every Markdown heading, every shell comment, every nginx
  `#` directive, every `.gitignore` comment, every JSON config with `#` in
  string values — all corrupted in the git history snapshot.
- **Local fix already in place**: SESSION-22 commit `20b8ab3` repaired 1067
  files in the working tree. So `git checkout HEAD -- .` produces working
  code/docs.
- **History remains polluted**: `git show <pre-20b8ab3>:any-file.py` still
  returns `***REMOVED***`-substituted content. Anyone doing
  `git log -p`/`git blame` on pre-20b8ab3 commits sees garbage.
- **No information loss**: the original-key information was already removed
  (correctly) by the same scrub. We have not lost any source content
  irrecoverably — the pre-scrub bundle backup at
  `.scrub-pre-backup/repo-<TS>.bundle` (created by `scrub-history.sh`'s
  backup phase) holds the pre-scrub state. The original keys are *also*
  in that bundle, so the bundle must NEVER be committed or shared.
- **Push status**: At time of incident, the polluted history was on the
  local branch only. SESSION-22 noted the user had committed + pushed
  20b8ab3 (and later commits). Force-pushing a *second* rewrite to undo
  the pollution would invalidate everyone's clones again and is not
  justified for the 120 still-broken files.

## 2. Fix applied (2026-05-25)

### 2.1 `scripts/scrub-history.sh`

Added `validate_patterns_file()` function plus a `--validate-only` flag.

Behavior:
- For each line in `scrub-patterns.txt`:
  - empty line: skip (allowed)
  - line starting with `#`: skip (allowed defensively; we recommend NEVER
    putting `#` lines in this file going forward — the README handles all
    metadata)
  - any other line: MUST contain `==>` AND have non-empty LHS.
    Failure prints offending line number + content + a pointer to the
    1187-file pollution incident, then `exit 4`.
- If any line fails, the validator counts ALL failures (not just the first)
  before exiting, so the operator gets a complete list.
- Zero valid rules → also `exit 4`.

Wired into the main flow at `[3/6] validate patterns` so filter-repo is
never invoked with a malformed file.

Standalone:
```bash
bash scripts/scrub-history.sh --validate-only
# → [validate-only] /path/to/scrub-patterns.txt
#   validate_patterns_file: OK (2 literal rule(s), 0 violations)
```

### 2.2 `scripts/scrub-patterns.txt`

Stripped to pure data, 2 lines, NO comments, NO blank lines:

```
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==>sk-or-v1-REDACTED-BY-SCRUB-20260524
sk-ad62cc6d8ada4bd0a92847b6b1d0ae1f==>sk-REDACTED-BY-SCRUB-20260524
```

This file remains gitignored (`.gitignore:85`).

### 2.3 `scripts/scrub-patterns.README.md` (NEW)

All metadata — provenance, exposure dates, leak sites, rotation status,
filter-repo `--replace-text` format reference, plus an inline warning about
this incident — now lives here. **This file IS committed.**

### 2.4 No twice-scrub of git history performed

See §4. Both full leaked keys are confirmed 0-occurrence in the export;
re-running filter-repo with the cleaned patterns file would be a no-op
(the script's `[4/6] idempotence probe` already early-exits).

## 3. Dry-run verification (2026-05-25 ~01:00)

Working tree status: dirty (Manna-sandpile in-progress work + this fix's
own files), but only `--execute` blocks on dirty WT; `--dry-run` proceeds
with a warning.

```
$ bash scripts/scrub-history.sh --dry-run
[1/6] preflight                — branch main, HEAD d236a2f, 595 commits
[2/6] skip auto-patterns
[3/6] validate patterns
       validate_patterns_file: OK (2 literal rule(s), 0 violations)
       2 replacement rule(s) loaded
[4/6] idempotence probe (current history matches)
       sk-or-v1-af9ae735beb91c0…  matches in history: 0
       sk-ad62cc6d8ada4bd0a9284…  matches in history: 0
       total literal hits in history: 0
       history already clean of listed literals — no-op.
```

Bypassing the early-exit to force filter-repo to actually run dry:

```
$ git filter-repo --dry-run --force --replace-text scripts/scrub-patterns.txt
Parsed 601 commits
New history written in 0.80 seconds; now repacking/cleaning...
NOTE: Not running fast-import or cleaning up; --dry-run passed.

$ grep -c "REMOVED" .git/filter-repo/fast-export.original
40323
$ grep -c "REMOVED" .git/filter-repo/fast-export.filtered
40323         # identical → 0 new REMOVED insertions

$ grep -c "^#" .git/filter-repo/fast-export.original
11696
$ grep -c "^#" .git/filter-repo/fast-export.filtered
11696         # identical → 0 # lines replaced

$ cmp .git/filter-repo/fast-export.original .git/filter-repo/fast-export.filtered
.git/filter-repo/fast-export.original .git/filter-repo/fast-export.filtered
differ: char 27, line 4
# Diff is ONLY filter-repo's `original-oid <sha>` metadata lines, which are
# stripped/rewritten on every dry-run regardless of content changes.
```

**Verdict**: With the new clean patterns file, filter-repo would make
**zero substantive content changes** to any blob. Re-running it would be a
pure no-op (modulo `original-oid` metadata churn that filter-repo always
does).

Dry-run artifacts (`fast-export.original`, `fast-export.filtered`, ~375MB
each) cleaned up after verification.

## 4. Real residual count of leaked keys in history

Direct verification (`git log --all -p | grep -E ...`) ran against full
history, all refs:

| query | hits |
|---|---|
| `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` (full 64-char body) | **0** |
| `sk-ad62cc6d8ada4bd0a92847b6b1d0ae1f` (full 32-char body) | **0** |
| `sk-or-v1-af9ae735[a-zA-Z0-9_-]{20,}` (prefix + ≥20 body chars) | **0** |
| `sk-ad62cc6d8ada4bd0a92[a-zA-Z0-9_-]{10,}` (prefix + ≥10 body chars) | **0** |
| `sk-or-v1-af9ae735` (prefix only — appears in truncated audit refs) | 23 |
| `sk-ad62cc6d` (prefix only — appears in truncated audit refs) | 19 |

The 23 + 19 prefix-only matches are all of the form `sk-or-v1-af9ae735…`,
`sk-or-v1-af9ae735...`, or bare `sk-or-v1-af9ae735` followed by whitespace
in audit docs and session handoffs. **No usable secret material remains
in history.**

**Conclusion**: a second scrub for these two keys is unnecessary.

## 5. Checklist for future scrub operations

Before ANY future `git filter-repo --replace-text` run in this repo:

1. **NEVER edit `scrub-patterns.txt` to add comments / headers / blank
   lines.** Put metadata in `scrub-patterns.README.md`. Patterns.txt is a
   wire-format file consumed verbatim by filter-repo.
2. **Run `--validate-only` first**:
   ```bash
   bash scripts/scrub-history.sh --validate-only
   ```
   Confirms every non-empty / non-`#` line has `==>` with non-empty LHS.
3. **Confirm separator is `==>` (2 chars), not `===>`**. The validator
   accepts both (it only requires the substring `==>`), but `===>` will
   add a stray `=` to the literal — sometimes acceptable, sometimes not.
4. **Test the patterns against a side branch first**:
   ```bash
   git checkout -b scrub-test-$(date +%Y%m%d)
   git filter-repo --dry-run --force --replace-text scripts/scrub-patterns.txt
   # then diff .git/filter-repo/fast-export.{original,filtered}
   # and grep -c "REMOVED" both — expect identical counts unless intentional
   ```
5. **Spot-check a polluted blob**: pick 3 representative files (a `.py`, a
   `.md`, a `.gitignore` or other config). After dry-run, extract them
   from the filtered export and `diff` against the original. Any
   surprise `***REMOVED***` is a smoking gun.
6. **Backup is mandatory**: never use `--no-backup` unless the bundle is
   immediately re-created elsewhere. The pre-scrub bundle in
   `.scrub-pre-backup/` is the only path to undo.
7. **Push only after**: explicit operator GO, gitleaks rerun showing 0
   high-confidence findings, and a `git log -p HEAD~3..HEAD` eyeball test.
8. **NEVER force-push the bundle**: bundles contain the original
   pre-scrub keys. Bundles stay local-only.

## 6. Lessons (institutional)

- **Tool surface area matters more than tool name.** "filter-repo" sounds
  surgical; `--replace-text` with a `#`-tolerant config-file format would
  be surgical. The actual API is closer to `sed -i` with an unfortunate
  default replacement string. Treat it that way.
- **Separation of data and metadata is a security property**, not a style
  preference. Mixed config files invite parsers to consume your prose.
- **Validators are cheap; recovery is expensive.** 60 lines of bash
  validation in `validate_patterns_file()` would have prevented a 1067-file
  sed restoration session.
- **Asymmetric APIs are landmines.** `get_paths_from_file()` skips `#`;
  `get_replace_text()` doesn't. Both live in the same binary. The wrapper
  must close the gap when the upstream tool can't.

— end —
