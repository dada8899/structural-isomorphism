# scrub-patterns.txt — metadata and provenance

This README documents the *companion* file `scrub-patterns.txt`, which is the
literal expressions file consumed by `git filter-repo --replace-text`.

## CRITICAL — why metadata lives here, not in patterns.txt

`git filter-repo --replace-text EXPRESSIONS_FILE` parses each non-empty line
as:

```
<literal_to_match>==><replacement_text>
```

If a line has **no `==>` separator** (e.g. a `#` header comment, a blank
description, a single `#`), filter-repo treats the *entire line* as a literal
to find and replaces every occurrence with the default `***REMOVED***`.

`#` comment lines are **NOT skipped** by `get_replace_text()` in
`/opt/homebrew/bin/git-filter-repo` (the corresponding `get_paths_from_file()`
DOES skip them, but `get_replace_text()` does not — see source ~line 2328
vs ~line 2358). This is a long-standing documentation/behaviour gap.

**Consequence of putting a single `#` line in patterns.txt**: every `#`
character in every blob across all of history gets replaced with
`***REMOVED***`. On 2026-05-24 this happened in this repo and corrupted
**1187 files** (every Python comment, Markdown heading, shell shebang
fragment, pytest.ini config, etc.). See
`docs/audit/git-history-scrub-postmortem-2026-05-25.md` for the full
post-mortem.

Therefore: **`scrub-patterns.txt` must contain ONLY lines of the form
`literal==>replacement`. No blank lines, no `#` lines, no header.**

The `scrub-history.sh` wrapper enforces this via `validate_patterns_file()`
(exit 4 on any non-conforming line) before invoking filter-repo.

## File is gitignored

`scripts/scrub-patterns.txt` contains raw leaked API keys and is therefore
listed in `.gitignore`. NEVER commit it. This README (`.README.md`) is safe
to commit because it contains only key *prefixes* and metadata.

## Current patterns (audited 2026-05-24)

Two leaked keys identified by the 2026-05-24 history audit
(cross-referenced against `docs/security/2026-05-20-history-key-audit.md`).
Both keys MUST be rotated at the vendor dashboard BEFORE force-pushing
scrubbed history.

### Pattern 1 — OpenRouter

| field | value |
|---|---|
| prefix | `sk-or-v1-af9ae735` |
| body length | 64 chars after prefix |
| first leaked commit | `aa044dd` (2026-04-16) |
| occurrences in history | ~9 commits |
| representative leak sites | `web/scripts/deploy.sh:39`, `docs/sessions/SESSION-9-HANDOFF.md:84` |
| replacement | `sk-or-v1-REDACTED-BY-SCRUB-20260524` |

### Pattern 2 — DeepSeek direct

| field | value |
|---|---|
| prefix | `sk-ad62cc6d` |
| body length | 32 chars total |
| first leaked commit | `a88dbef` (2026-05-13) |
| occurrences in history | ~12 commits |
| representative leak sites | `docs/reviews/W5-B-researcher-review-2026-05-13.md:111`, `docs/sessions/SESSION-9-HANDOFF.md:83` |
| replacement | `sk-REDACTED-BY-SCRUB-20260524` |

## Optional truncated forms (NOT currently enabled)

Audit and handoff docs sometimes reference keys in truncated form
(`sk-or-v1-af9ae735...`). These are not secrets and do not need scrubbing.
If a future audit decides to scrub them anyway, add lines to
`scripts/scrub-patterns.local.txt` (also gitignored) — do **not** edit
`scrub-patterns.txt` to add commentary; keep the data file pure.

## Format reference (filter-repo --replace-text)

From `git-filter-repo --help`:

> A file with expressions that, if found, will be replaced. By default, each
> expression is treated as literal text, but `regex:` and `glob:` prefixes
> are supported. You can end the line with `==>` and some replacement text
> to choose a replacement choice other than the default of `***REMOVED***`.

Separator is exactly **`==>`** (2 chars, two equals + one greater-than).
A previous version of this README incorrectly said `===>` (3 chars) —
that is wrong. `==>` is the only separator filter-repo recognises.

## How scrub-history.sh validates this file

`validate_patterns_file()` in `scripts/scrub-history.sh`:

1. Reads every line.
2. Allows: empty lines, lines starting with `#` (defensive — but we recommend
   NEVER putting `#` lines in this file).
3. Every other line MUST contain the substring `==>` AND have a non-empty
   left side (the literal). Otherwise: print error with line number and
   `exit 4`.
4. Runnable in isolation via `bash scripts/scrub-history.sh --validate-only`.
