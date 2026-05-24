# [i18n] Add Mandarin Chinese translation of the README

## What

Translate the project README from English to Simplified Mandarin Chinese. Save as `README.zh-CN.md` at the repo root, and add a language switcher block at the top of both `README.md` and `README.zh-CN.md`.

## Why

A large fraction of the complex-systems and quantitative-finance audience reads Chinese-language sources first. We already maintain a Chinese-language paper draft at `paper/paper-zh.md`, so terminology consistency is achievable. Adding a README translation is the lowest-friction signal that we welcome Chinese-speaking contributors.

## Where

- New file: `README.zh-CN.md` at repo root
- Source: `README.md`
- Terminology consistency: cross-check terms against `paper/paper-zh.md` (e.g. how we render "self-organized criticality", "power-law exponent", "pre-registration")

## How to start

1. Copy `README.md` to `README.zh-CN.md`.
2. Translate every section. Preserve all code blocks, file paths, and badge URLs unchanged.
3. Cross-check key terms against `paper/paper-zh.md` so the same concept renders the same way across docs.
4. Add a top-of-file switcher block:
   ```markdown
   > 🌐 [English](./README.md) | **简体中文**
   ```
   and the mirror at the top of `README.md`.
5. Ask any native-speaker reviewer to do a pass before merging.

## Definition of done

- [ ] `README.zh-CN.md` committed
- [ ] Language switcher present in both README files
- [ ] Terminology consistent with `paper/paper-zh.md`
- [ ] Native-speaker reviewer approves in PR (tag `@dada8899`)

## Difficulty

★ (translation, not engineering)
