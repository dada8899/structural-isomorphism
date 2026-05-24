# web/shared — cross-site assets

Files that BOTH the Structural site (`web/frontend`) and the Phase Detector
Next.js app (`web/phase-detector`) need to share, so we don't drift.

## tokens.css — the 5-var brand palette

Single source of truth for the 5 brand tokens:

| Var               | Used as                | Default |
|-------------------|------------------------|---------|
| `--brand-ink`     | primary text           | `#18181B` |
| `--brand-paper`   | primary background     | `#F5F5F4` |
| `--brand-accent`  | links, focus, highlight| `#2563EB` |
| `--brand-line`    | hairline border        | `#E4E4E7` |
| `--brand-muted`   | tertiary text / caption| `#71717A` |

Plus a small extended palette (`--brand-paper-card`, `--brand-accent-hover`,
`--brand-success`, etc.) that both sites share.

### How it's wired

Each site has a **byte-identical mirror** of `tokens.css` because each
bundler / static server can only see files inside its own root:

- `web/shared/tokens.css` — canonical
- `web/frontend/assets/css/shared-tokens.css` — Structural mirror, loaded as
  the FIRST stylesheet in every HTML page (before `reset.css` / `design-system.css`)
- `web/phase-detector/app/shared-tokens.css` — Phase Detector mirror,
  `@import`-ed from the top of `globals.css`

The site-local tokens (`--text-primary`, `--bg-primary`, etc.) are aliases
over `--brand-*` so the rest of the codebase keeps working unchanged:

```css
/* web/frontend/assets/css/design-system.css */
--text-primary: var(--brand-ink, #18181B);
--accent:       var(--brand-accent, #2563EB);
```

### To change a brand color

1. Edit `web/shared/tokens.css`
2. Run `web/shared/sync-tokens.sh` — copies to both mirrors
3. Commit all three files together (the mirrors are checked-in, not generated
   at build time, so CI sees the change)

The sync script verifies the copies are byte-identical and exits non-zero
if anything diverges. Add a CI step that runs the script and fails on
non-empty `git diff` to prevent silent drift.

## sync-tokens.sh

Run after editing `tokens.css`:

```bash
./web/shared/sync-tokens.sh
```
