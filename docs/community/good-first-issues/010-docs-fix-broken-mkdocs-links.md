# [docs] Audit and fix broken internal links in MkDocs site

## What

Run the MkDocs strict link-check on the docs site and fix every broken internal link. Specifically: `mkdocs build --strict` currently fails with several "unresolved link" warnings (e.g. paths to renamed files after the W6 reorg). Get the build to pass `--strict` mode.

## Why

Broken links in the docs are the #1 thing that makes a research project look abandoned to a first-time visitor. Putting `--strict` mode in CI prevents future regressions.

## Where

- Config: `mkdocs.yml`
- Docs root: `docs/`
- Suspected broken links — start by running:
   ```bash
   mkdocs build --strict 2>&1 | grep -E "WARNING|ERROR"
   ```

## How to start

1. Install mkdocs and the project's plugins:
   ```bash
   pip install -e .[docs]
   ```
2. Build with strict mode and capture the failures.
3. For each broken link: either fix the path, fix the target filename, or delete the stale reference.
4. Bonus: add a CI step in `.github/workflows/` that runs `mkdocs build --strict` on every PR.

## Definition of done

- [ ] `mkdocs build --strict` exits 0
- [ ] (Optional) GitHub Actions workflow `.github/workflows/docs-link-check.yml` added
- [ ] PR description lists every link that was changed and why

## Difficulty

★ (no programming, just careful link audit)
