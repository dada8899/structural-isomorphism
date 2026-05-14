# [docs] Fix deprecated `v4.lib.soc_pipeline` references in tutorials and docs

## What

After W8 we extracted the SOC pipeline to a standalone PyPI-ready package at `packages/soc-pipeline/`. The old import path `from v4.lib.soc_pipeline import ...` still works (with a `DeprecationWarning`) but several docs / notebooks / README snippets still show it as the canonical example. Replace them with the new path `from soc_pipeline import ...`.

## Why

External users following the README or tutorials will see deprecation warnings on their first run — which looks unmaintained. We want every published example to use the current import path.

## Where

Files known to reference the deprecated path (find with `grep -rn "v4.lib.soc_pipeline" --include="*.md" --include="*.ipynb" .`):

- `docs/getting-started.md`
- `docs/pipeline.md` (verify)
- `tutorials/01_phase_1_quick.py`
- `notebooks/` (check each)
- `README.md` (verify code blocks)

## How to start

1. Run:
   ```bash
   grep -rn "v4.lib.soc_pipeline\|v4\.lib\.soc_pipeline" --include="*.md" --include="*.py" --include="*.ipynb" .
   ```
2. For each hit: replace `from v4.lib.soc_pipeline import X` with `from soc_pipeline import X`. Verify the symbol still exists in the new package's `__init__.py`.
3. Where the deprecated wrapper has a different return shape (legacy dict vs new `FitResult` dataclass), update the example output accordingly.
4. Re-run any modified notebook end-to-end to confirm it still works.

## Definition of done

- [ ] No remaining `v4.lib.soc_pipeline` imports in any user-facing doc / notebook / tutorial
- [ ] Each modified notebook re-executed (clear output cells if you prefer, but make sure import works)
- [ ] `docs/getting-started.md` quickstart still works copy-paste

## Difficulty

★ (mechanical search-and-replace + verification)
