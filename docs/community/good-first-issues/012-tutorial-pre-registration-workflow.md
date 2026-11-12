# [tutorial] New tutorial — writing a pre-registration

## What

Add `tutorials/05_pre_registration_workflow.ipynb` (or `.md`) that walks a new contributor through writing a valid pre-registration for a candidate SOC dataset. Show the why, the template, a worked example, and the commit-order discipline (pre-reg committed *before* fit verdict).

## Why

The whole "anti-p-hacking" credibility of the project rests on pre-registrations, but external contributors don't know the format we accept. Today they would have to reverse-engineer from existing `paper/pre-registrations/*.md` files. A dedicated tutorial removes that friction.

## Where

- New file: `tutorials/05_pre_registration_workflow.ipynb` (or `tutorials/05_pre_registration_workflow.md` if you prefer markdown — notebook is fine but not required for this one)
- Reference: existing pre-regs in `paper/pre-registrations/`
- Methodology doc: `docs/methodology/`

## How to start

1. Read 2–3 existing pre-regs in `paper/pre-registrations/` for the canonical structure.
2. Sketch the tutorial as: motivation → template walkthrough → worked example (use a *fake* candidate dataset so the reader can follow without downloading) → commit-order discipline → checklist before opening a PR.
3. Highlight the rule: **the pre-reg commit must precede the fit-verdict commit** (link to `docs/methodology/anti-phacking.md`).
4. End with an exercise: "now write your own pre-reg for `<dataset of your choice>`".

## Definition of done

- [ ] Tutorial file at `tutorials/05_pre_registration_workflow.{ipynb,md}`
- [ ] Linked from `tutorials/README.md`
- [ ] Includes a copy-paste pre-registration template
- [ ] Includes the commit-order rule and the git commands to do it
- [ ] Linked from `CONTRIBUTING.md` under the "Reporting research issues" section

## Difficulty

★ (writing-heavy; minimal code)
