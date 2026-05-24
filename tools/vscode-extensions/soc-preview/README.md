# SOC Preview (VS Code extension — skeleton)

Status: skeleton only. Wiring is real (activation events + status-bar + Python
helper), packaging as `.vsix` is left for follow-up.

## What it does

Opens a CSV file whose name starts with `soc:` (e.g. `soc:my_data.csv`), reads
the first numeric column, fits a Clauset 2009 power-law via the
`soc-pipeline` Python package, and writes the verdict + α̂ to the VS Code
status bar:

```
SOC: PASS α=2.51
```

## Files

- `package.json` — extension manifest (activation events, command, status bar)
- `src/extension.js` — JS entrypoint (activate / status bar / dispatch)
- `src/fit_helper.py` — Python helper that calls `soc_pipeline.validate()`

## To finish packaging

```bash
cd .vscode/extensions/soc-preview
npm install -g vsce
vsce package   # produces soc-preview-0.1.0.vsix
```

## Why a skeleton?

The PR (Wave 8 sub-agent E) was scoped to "ergonomic affordances" — primary
deliverables are the Jupyter widget + Pandas accessor. The VS Code piece is a
stretch goal and ships as a working scaffold that other contributors can
finish.
