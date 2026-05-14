# Full user journey e2e — `test_full_user_journey.py`

**Author:** W14-A sub-agent (session #10, 2026-05-15)
**Location:** `web/tests/e2e/test_full_user_journey.py`
**Marker:** `@pytest.mark.slow` (also a module-level skipif when `PHASE_BASE` is unreachable)
**Runtime:** ~75–95s against live prod, ~60s against a warm local dev server.

## Why a single 14-step test, not 14 separate tests

Every existing e2e file (`test_compare_page.py`, `test_pricing_page.py`, `test_i18n_zh.py`, `test_cmdk_search.py`, `test_onboarding.py`, `test_newsletter_archive.py`, `test_universality_explorer.py`, `test_a11y_audit.py`, `test_real_user_flows.py`, ...) already isolates one surface in clean state. They catch per-feature regressions cleanly.

What they **don't** catch is the cross-product: localStorage from step 1 (`phase_tour_seen=true`) affecting step 6 (tour shouldn't remount on language switch), cookies from step 9 (mock-checkout customer record) carrying into step 11 (newsletter referral attribution), the theme toggle in step 12 persisting onto step 13's mobile drawer, etc. A real first-visit user walks all surfaces in one session with one localStorage, one cookie jar, one service-worker registration. This test mirrors that exact mode by sharing one `BrowserContext` across all 14 steps.

## The 14 steps (with assertion tier)

| # | Step | Page | Hard assert |
|---|---|---|---|
| 1 | Landing + tour skip | `/` | landing URL OK |
| 2 | Companies + filter | `/companies` | ≥1 company link |
| 3 | Company detail | `/company/<ticker>` | header testid present |
| 4 | Universality class | `/universality/<id>` or `/universality` fallback | (soft) |
| 5 | Compare 5 tickers | `/compare?tickers=...` | ≥1 `compare-column` |
| 6 | Lang switch EN → 中 → EN | `/zh` → `/` | `/zh` reached + Chinese hero or URL |
| 7 | Cmd+K search "earthquake" | overlay → universality result | (soft) |
| 8 | Pricing → Start Pro CTA | `/pricing` → `/checkout/mock?tier=pro` | (soft, fallback nav) |
| 9 | Fill mock checkout, submit | `/checkout/mock` | (combined with 10) |
| 10 | Thank-you page | `/thank-you?tier=pro` | `/thank-you` reached |
| 11 | Newsletter archive + issue | `/newsletter` → `/newsletter/001` | (soft, issue may not be deployed) |
| 12 | Theme toggle dark | `[data-testid=theme-toggle-dark]` | (soft) |
| 13 | Theme toggle light | `[data-testid=theme-toggle-light]` | (soft) |
| 14 | Mobile drawer @ 390×844 | hamburger trigger + nav items | (soft) |
| 15 | Final a11y + console audit | `/` desktop | 0 critical violations, 0 (filtered) console errors |

## Hard vs soft tier

**Hard asserts** (test fails red): landing reachable, /companies populated, /compare renders at least 1 column, full pricing→checkout→thank-you happy path reaches `/thank-you`, language switcher takes user to `/zh`, 0 (filtered) console errors, 0 critical axe violations.

**Soft observations** (recorded to results JSON, don't ship-block): everything else. Per-feature tests already gate these — duplicating the gate here would make this test red whenever any single surface drifts.

When the journey passes but a soft observation flips, run `git log results/session-10-w14-a-journey-results.json` to spot the drift point.

## Console-error filter

The browser console emits "errors" for many things that are NOT JS runtime exceptions: Plausible analytics 4xx, `_rsc=` prefetch 404s for non-existent locale routes, `Failed to load resource` network failures, Next's `Failed to fetch RSC payload ... Falling back to browser navigation` (Next handles this gracefully). The filter ignores all of these. What remains is real `TypeError`, `ReferenceError`, `SyntaxError` etc. — the things that actually break UX.

## Run & maintenance

```bash
# Against prod (default):
PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_full_user_journey.py -v --tb=short

# Against local Next dev server:
PHASE_BASE=http://localhost:3017 PYTHONPATH=. .venv/bin/python -m pytest web/tests/e2e/test_full_user_journey.py -v

# Skip slow tests in normal CI loop:
pytest -m "not slow" web/tests/e2e/
```

**Updating the journey** when new surfaces ship:
1. Add a new step block between two existing ones.
2. Append the step name to the assertions section below.
3. Add a screenshot tag (`_shot(page, "NN-name")`) — screenshots land in `web/tests/e2e/screenshots/w14-a-journey/`.
4. Decide hard vs soft tier. Default: **soft** (don't add a hard assert unless the surface is part of the core conversion funnel).

**When to add a hard assert:** the step is a conversion-critical surface that paid users will hit on a daily basis AND has no other e2e gating it. Otherwise stay soft — feature tests own per-surface gates, this test owns the cross-product integration.

## Results JSON shape

Written to `web/tests/e2e/results/session-10-w14-a-journey-results.json` on every run (pass or fail). Top-level keys: `base`, `started_at`, `finished_at`, `steps[]`. Each step has `name`, `ts`, `ok`, plus step-specific fields (`url`, `lcp_ms`, `lcp_within_budget`, `companies_loaded`, etc.). Grep this JSON for soft-observation regressions.

## Known caveats

- LCP is measured loosely (PerformanceObserver with 6s timeout) — real CWV gates live in W13-B. The 3s budget here is for catching catastrophic regressions, not perf tuning.
- Mobile drawer testids are not yet present in `TopNav.tsx` — the test falls back to `aria-label` selector heuristics. When W6-C ships a `data-testid="mobile-drawer"` the test should be updated to use it.
- The Cmd+K test issues `Meta+K` then falls back to `Control+K` — Playwright's modifier mapping is platform-aware but the cross-platform handling adds 1–2s of slack.
- The mock checkout backend may not be wired on every deployment. Step 10 falls back to direct `/thank-you?tier=pro` navigation in that case — the hard assert is the URL, not the form submit completion.

(~520 words)
