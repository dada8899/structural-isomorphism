# 👋 Hi, next-session Claude — read this first

User authorized everything in session #3 close-out but ran out of time to actually execute the irreversible / token-gated last-mile actions.

## Your single source of truth

→ **`docs/sessions/SESSION-4-STARTER.md`** ← read this, follow §0 → §2 step by step

It has:
- §0 environment + credential scan (gh / PYPI_TOKEN / ZENODO_ACCESS_TOKEN / arXiv)
- §2 the 9-step runbook (rotate key → scrub history → PUBLIC flip → PyPI → Zenodo → arXiv → cross-ref updates → GitHub release)
- §3 rollback plans for irreversible steps (history scrub, PyPI, Zenodo, arXiv)
- §5 acceptance checklist (10 boxes)
- §6 prompt template if user wants to re-prime you

## TL;DR for the first turn

```bash
cd ~/Projects/structural-isomorphism
git pull
git log --oneline -3                            # head should be 0380327 or later
cat docs/sessions/SESSION-4-STARTER.md | head -80
gh auth status
env | grep -iE "deepseek|pypi|zenodo" | sed 's/=.*/=<SET>/'
```

Then ask the user once: "Tokens to supply now (PYPI_TOKEN / ZENODO_ACCESS_TOKEN), or shall I do auto-only steps first (history scrub + PUBLIC flip)?"

After that, full auto mode. Don't re-plan — the plan is in SESSION-4-STARTER.md.

## What NOT to redo

- Don't re-read session #3 W*-* reviews / roadmaps unless user asks. They're cited in SESSION-4-STARTER.md when needed.
- Don't re-build packages/wheels — they're already in `packages/*/dist/`. Just `twine check` to confirm.
- Don't write new paper drafts — 6 are ready (`paper/v0-unified-pipeline-2026-05-13.md` v0.3, `paper/arxiv-drafts/2026-05-13/01-04*.md`, `paper/c4-reject-aware-pipeline-2026-05-13.md`).

## Hard rule

The 2 P1 bugs from W6-E are already fixed in F1 (PR #44). Don't accidentally reintroduce them.

Good luck. The hard work is done — session #4 is just shipping it.
