# Session #12 — Pre-launch multi-agent audit (W16)

**Date**: 2026-05-15
**Branch**: `claude/project-progress-update-eZpfc`
**Trigger**: User-requested full review by UX designer / PM / scholar / architect / real-user agents before public flip, PyPI publish, arXiv submission, Zenodo DOI mint.

This handoff documents what shipped in the audit pass, what is still open,
and the residual irreversible-action checklist for the human operator.

---

## 1. Five-agent review summary

Five read-only review agents ran in parallel against the pre-launch repo
state at commit `e3ceab1` (Session #11 closeout). Findings rolled up to
30+ issues split across these buckets:

| Bucket | Reviewer | P0 | P1 | P2 |
|---|---|---|---|---|
| UX / design system | designer | 3 | 4 | 4 |
| Product / GTM | PM | 4 | 5 | 3 |
| Methodology / FAIR | scholar | 3 | 3 | 2 |
| Architecture / security | architect | 5 | 3 | 2 |
| Real-user friction | persona ×3 | 3 | 3 | 2 |

All P0 items from all five reviews have been addressed in this pass.
P1 items are tracked below.

---

## 2. P0 fixes that landed

### Security (architect)
- **Exposed real OpenRouter key** in `web/backend/.env.bak-v1` was tracked
  by git. File removed from tree + `.env.bak*` + `.env.production` added
  to `.gitignore`. **The key is still present in git history** — see
  §5.1 for the rotation + history-scrub runbook. Do not flip the repo
  to PUBLIC until this is closed out.
- **Tracked test API keys** in `web/backend/data/api_keys.jsonl` moved
  to `api_keys.jsonl.example` with `REPLACE_ME` placeholders. Runtime
  store path gitignored.
- **Missing `slowapi` in requirements.txt** — `errors.py` already
  imported `slowapi.errors` but the dep was absent from prod
  `requirements.txt`, so the backend crashed at import in a clean venv.
  Pinned `slowapi>=0.1.9,<0.2`.
- **Missing `JWT_SECRET`** in `.env.example` for the W15-B magic-link
  scaffold. Added with rotation instructions.
- **Frontend domain missing from CORS allow-list**:
  `https://phase.bytedance.city` was not in `_allowed_origins` in
  `web/backend/main.py`. Added.

### Copy / positioning (UX + PM + real-user)
- **TopNav broken link**: first link `公司表 → /` looped to the landing.
  Restored to `/companies` (the actual screener route after W6-C).
- **Hero rewritten** to drop the "alpha screener" framing:
  - Headline: "The same math that explains earthquakes, applied to
    1000+ public companies."
  - Eyebrow: "Cross-domain universality · Research preview"
  - Subhead surfaces the NULL stat inline (Sharpe lift −0.07, p = 0.57)
    instead of behind a tertiary CTA link.
  - CTA row: three competing buttons → two with clear hierarchy
    (`Explore companies` primary, `Read the methodology` secondary).
  - `motion-safe:animate-pulse` respects reduced-motion preference.
- **`HeroCtaText` A/B fallback** updated to `Explore companies` so the
  control bucket no longer renders "Browse signals" while the page
  copy says "classifications."
- **LandingHeroZh** mirrors the new framing for the `/zh` route.
- **TrustSignalsRow**:
  - Section heading made visible (was `sr-only`).
  - Eyebrow "Receipts · 凭证" → "Verifiable claims · 凭证" (English
    readers were parsing "Receipts" as slang).
  - First card "Cross-domain validation" → "Within-class robustness"
    (scholar review flagged within-class aggregation framed as
    cross-domain — see §3.1).
  - NULL number now in the card value, not behind a hover.
  - Stale hint "500 tickers × 5 years" → "927 / 1000 tickers covered,
    59 monthly snapshots over 2020–2025."
- **HowItWorksSteps step 3**: removed "you judge the alpha" phrasing.
- **/pricing page**: header re-positioned for researchers / students /
  journalists / OSS contributors (free) and labs / editorial teams
  (paid). Stripe disclaimer rewritten in English. Explicit "Not an
  alpha screener · backtest NULL" badge.
- **Landing metadata + OG / Twitter cards**: drop "alpha" + "receipts"
  copy; lead with cross-domain framing and NULL stat.

### Number consistency (scholar)
- `CHANGELOG.md` W10-A line had `t=-0.412, p=0.681` — those numbers
  belong to the **W1-A 500-ticker 54-snapshot earlier backtest** cited
  in `paper/anti-phacking-unified-2026-05-15.md`. The current W10-A
  v0.1 1000-ticker 927-covered run gave `Sharpe lift -0.072,
  Welch t = 0.573, p = 0.569, n_months = 59` (see
  `web/phase-detector/public/backtest/result.json`). All user-facing
  surfaces now mirror the current v0.1 number; the paper number is
  preserved in the paper because it documents a specific historical
  experiment.
- Fixed in: `CHANGELOG.md`, `README.md`,
  `web/phase-detector/app/companies/page.tsx`,
  `web/phase-detector/components/FaqAccordion.tsx`,
  `web/phase-detector/components/TrustSignalsRow.tsx`,
  `web/tests/e2e/test_real_user_flows.py`.

### Scholarship (scholar)
- `README.md`: explicit **scope-honesty paragraph** added —
  > The 13 PASS verdicts currently validate within-class robustness of
  > a SOC-grade pipeline across systems that all sit in (or near) the
  > self-organized-criticality universality class. Genuine cross-class
  > universality is reserved for the next coordinated study.
- `README.md`: explicit **bytedance.city domain disclaimer** added —
  it is a personal domain, no ByteDance Ltd. affiliation.
- `CITATION.cff`: added `references:` block citing Bak–Tang–Wiesenfeld
  1987, Clauset–Shalizi–Newman 2009, Scheffer et al. 2009, Motter & Lai
  2002, Beggs & Plenz 2003, Plerou et al. 1999, Diamond & Dybvig 1983,
  and the SIBD-63 dataset. GitHub "Cite this repository" now renders
  the full chain.

### Launch posts
- HN / Reddit / INDEX: stale package names `structural-soc-pipeline` /
  `structural-critics` / `structural-taxonomy` → real names
  `soc-pipeline` / `cross-judge` / `guarded-llm` so day-one
  `pip install` doesn't 404.
- HN: "500-ticker S&P 500 walk-forward" → "927/1000-ticker (S&P 500 +
  Russell-1000 supplement) walk-forward NULL."

### Architect P1 housekeeping
- Standardize `license` field across all 3 packages to
  `license = { file = "LICENSE" }` (was a mix; mixed forms trigger
  build warnings).
- Coverage CI: hard-fail on `pip install -e packages/*` and
  `pip install slowapi` (soft-fail was masking broken builds and
  silently dropping coverage). Soft-fail kept only for scientific
  wheels (numpy / scipy / pandas / powerlaw) which occasionally
  regress on fresh CI images.
- Footer reorganized: bilingual labels (`About · 关于`,
  `Methodology · 方法`), explicit `Contribute ↗` link to
  `CONTRIBUTING.md`, in-footer domain disclaimer.
- `setup.py` version 0.1.0 → 0.4.0 to match CHANGELOG state.

---

## 3. P1 items still open

### 3.1 Scholar — cross-domain vs within-class framing in the papers
The 4 arXiv drafts in `paper/arxiv-drafts/2026-05-13/` still use
"cross-domain universality" framing. The README scope-honesty note
helps, but the paper titles + abstracts should be re-read with the
within-class-robustness framing in mind before submission. **Not done
in this pass** because paper content changes require careful read by
the author; flagged in §5.4 below.

### 3.2 Scholar — Anderson / Preisach falsifiability
`taxonomy-v1.md` lists Preisach hysteresis with a purely descriptive
"closed-loop on Y(X)" criterion, and the README mentions Anderson
localization but the 84-class taxonomy has no Anderson entry. Either
operationalize both with a quantitative test (e.g. dimensionless
conductance scaling for Anderson, coercivity-histogram for Preisach)
or move them to a non-empirical "conceptual morphology" appendix.

### 3.3 Scholar — FWER correction surfaced in papers
`v4/results/F3_fwer_corrected.jsonl` exists but the antipage paper §3.5
doesn't quote Bonferroni-corrected p-values. Reviewer #2 will ask.

### 3.4 PM — academic citation surface on the web
No `/cite` page or BibTeX modal on the live product. The README has
the BibTeX block but a cold academic visitor on `phase.bytedance.city`
can't cite without leaving for GitHub.

### 3.5 Architect — Dep upper bounds + repo housekeeping
- Add `,<3` / `,<1` upper bounds on `pydantic` / `httpx` /
  `tenacity` in `packages/*/pyproject.toml` (skipped pending a test
  pass to confirm no existing wheel breaks).
- Quarantine `v3/`, `v4-feasibility/`, `phase/`, `validation/` to an
  `archived/` branch before public flip to reduce a 17.2 MB cold clone.

### 3.6 UX — small polish
- `.text-zinc-400` on the "Five phases · 五种状态" caption fails WCAG AA
  contrast on white. Switch to `text-zinc-500`.
- Dark-mode hero CTA uses hardcoded `bg-indigo-700` — won't flip to
  the `#A78BFA` dark accent. Use semantic `bg-accent text-accent-fg`.

---

## 4. Tests touched in this pass

| File | Reason |
|---|---|
| `web/tests/e2e/test_phase_landing_v2.py` | New hero copy + CTA destinations |
| `web/tests/e2e/test_i18n_zh.py` | Updated /zh hero assertions to match new framing |
| `web/tests/e2e/test_real_user_flows.py` | Banner p-value now `p = 0.57` (was `0.681`) |

No new tests added. Existing tests will continue to gate the contract.

---

## 5. Residual irreversible-action checklist (for the human operator)

### 5.1 Rotate the exposed OpenRouter key + scrub history
The key `sk-or-v1-af9ae735…aea878` was committed in
`web/backend/.env.bak-v1` and remains in `git log`.

```bash
# 1. Rotate at https://openrouter.ai/keys (revoke the old key; mint a new one).
# 2. Update STRUCTURAL_DEPLOY env files on the VPS with the new key.
# 3. Scrub the file from history before flipping PUBLIC:
git filter-repo --path web/backend/.env.bak-v1 --invert-paths
#    (or BFG: bfg --delete-files .env.bak-v1)
# 4. Force-push to your remote AFTER you have confirmed all team members
#    have stopped pushing to the affected branches.
```

### 5.2 PyPI publish (3 packages)
With `PYPI_TOKEN` set:

```bash
for p in soc-pipeline cross-judge guarded-llm; do
  cd packages/$p
  python -m build
  python -m twine check dist/*
  python -m twine upload dist/*
  cd ../..
done
```

### 5.3 Zenodo DOI mint
With `ZENODO_ACCESS_TOKEN` set, follow `docs/sessions/SESSION-4-STARTER.md`
§2.5.

### 5.4 arXiv submission (5 papers)
Before submitting, re-read each paper's abstract with the scope-honesty
framing in §3.1 of this doc — replace any literal "cross-domain
universality" claim that's actually within-class robustness.

### 5.5 GitHub repo PUBLIC flip
- Confirm §5.1 (key rotation + history scrub) is done.
- Confirm `git ls-files | xargs grep -l "sk-or-v1\|sk_test_"` returns
  nothing.
- Confirm CI is green on `claude/project-progress-update-eZpfc`.
- Then flip the visibility from the GitHub settings page.

### 5.6 GH Pages
Enable for mkdocs (docs/) and Storybook (web/phase-detector/) from
Settings → Pages.

---

## 6. What this audit did NOT touch (intentionally)

- Paper drafts under `paper/` — content changes are author-driven and
  in scope for §3.1 above.
- `taxonomy-v1.md` — see §3.2.
- v4 pipeline source — frozen at `7ee228c`, not in scope.
- Deprecated dirs (`v3/`, `v4-feasibility/`, `phase/`, `validation/`)
  — see §3.5; archiving is destructive enough to wait for explicit
  approval.

---

*Audit performed by a five-agent parallel review on
`claude/project-progress-update-eZpfc`; all P0 findings landed in
commit `e264e35` and successors.*
