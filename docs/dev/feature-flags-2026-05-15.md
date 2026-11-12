# Feature Flags + A/B Experiments

> Session #10 W15-E. Lightweight, no third-party SaaS (LaunchDarkly / GrowthBook deferred until volume justifies it).

## TL;DR

- Config lives in `config/feature_flags.yaml` at repo root.
- Backend reads it via `web/backend/flags.py`, hot-reloads every 30s.
- Frontend fetches `/api/flags` once per page load into a React context.
- Two primitives: **flags** (binary toggles, optional rollout) and **experiments** (weighted variants).
- Allocation is deterministic per `(user_id, flag_or_experiment_name)` — same user always lands in same bucket.

## Adding a feature flag

1. Edit `config/feature_flags.yaml`:

   ```yaml
   flags:
     my_new_flag:
       enabled: true
       description: One-line purpose (search-friendly)
       rollout:
         type: percentage    # or 'segment'
         value: 100          # 0-100 for percentage
   ```

2. In a backend handler:

   ```python
   from flags import is_enabled
   if is_enabled("my_new_flag", user_id):
       ...
   ```

3. In a React component (must be inside `<FlagsProvider>`, which `app/layout.tsx` already wires):

   ```tsx
   "use client";
   import { useFlag } from "@/lib/flags";
   const on = useFlag("my_new_flag");
   ```

4. Commit YAML change. Production picks it up within 30s (cache TTL); no deploy needed for a pure toggle. **Schema changes (new flag keys) still ship via deploy** because the YAML file is part of the repo.

## Rollout types

### `percentage`

`value: 0..100`. Deterministic per user: bucket = `sha256(user_id + ":" + flag_name)[:8] % 100`. Bucket < value → flag on. Same user always lands in same bucket — no flicker between requests.

Anonymous users (no `X-Anon-Id` cookie) bucket as `_anon` → they all see the same answer. Don't gate critical UX paths on percentage rollouts without an anon-id cookie set.

### `segment`

`segments: [pro, team, admin]`. Reads current tier from `middleware/rate_limit.py`'s `CURRENT_TIER` ContextVar (already populated for every request that goes through `install_rate_limit`). `free` users excluded if not in the list.

Use segment for tier-gated features (Pro-only viz, Team-only export); use percentage for canary rollouts.

## Running an A/B experiment

1. Add to `config/feature_flags.yaml`:

   ```yaml
   experiments:
     hero_cta_text_v2:
       description: A/B test "Browse signals" vs "See live data"
       variants:
         control: "Browse signals"
         treatment: "See live data"
       allocation:
         control: 50
         treatment: 50
   ```

2. Wire the variant content into a client island:

   ```tsx
   "use client";
   import { useVariantValue } from "@/lib/flags";
   const text = useVariantValue("hero_cta_text_v2", "Browse signals");
   return <button>{text}</button>;
   ```

3. `useVariantValue` automatically fires a Plausible `experiment_exposed` event (once per session per experiment) with `{experiment, variant}` props.

4. Measure: in Plausible, segment your conversion goal by the `variant` prop on `experiment_exposed`. Treatment/control conversion rates → decide.

### Allocation tips

- Always include a `control` variant. Even for a no-touch experiment, you want a baseline.
- Equal splits maximize statistical power per sample. Unequal splits (e.g. 90/10) are useful when treatment has risk.
- Allocation weights must sum to a positive number; we mod by the sum, so `50/50` and `5/5` behave identically.

## A/A test recommendation

Before running a real A/B, run an **A/A test** (both variants identical) for ~1 week. If you see a "significant" difference between two identical variants, your tracking or sample sizing is broken — fix it before trusting any real A/B result.

## Graduation criteria (when to remove a flag/experiment)

- **Flag**: once it's at 100% rollout for 2 weeks with no rollback, delete the flag and its `if (useFlag(...))` branches. Stale flags accumulate technical debt.
- **Experiment**: once you have a winner (p < 0.05, or sufficient practical effect size), set the winning variant as the new default, remove the experiment block, and inline the winning text/UX into the component. Keep a one-line note in CHANGELOG about which variant won.

## Hot-reload semantics

- TTL: 30s. After expiry, next call re-stats the YAML and reloads if `mtime` changed.
- A YAML parse error logs an error and keeps the **last good cache** — so a typo can't take down the site.
- A missing file logs a warning and returns empty config (all flags off, all experiments → control). This is the fail-closed default and the right behavior in CI/test where the file may be absent.

## Anonymous identity

- Frontend assigns a stable UUID, stored in `localStorage` under `anon-id`. Sent as `X-Anon-Id` request header.
- This is **not** PII — it's an opaque random ID with no link to email/IP at the application layer. Clears when the user clears localStorage.
- Authenticated users override anon-id via `request.state.user_id` (set by auth middleware).

## Operational tips

- **Don't read flags in hot loops.** `is_enabled` is cheap (dict lookup + 1 hash), but in tight per-row paths, cache the boolean in a local variable.
- **Don't rely on flag values being consistent within a single request** if the request crosses a TTL boundary (rare, but possible). For per-request consistency, cache the result at request entry.
- **Server-side renders use defaults.** A flag-gated UI element will flip from default → resolved on the first client render. Treat that as a 1-frame transition, not a bug. If you can't tolerate the flip, use SSR cookies (not implemented yet — out of scope for W15-E).

## Where things live

| File | Purpose |
|---|---|
| `config/feature_flags.yaml` | Single source of truth — what flags + experiments exist |
| `web/backend/flags.py` | YAML loader, TTL cache, bucketing, segment lookup |
| `web/backend/api/flags.py` | `GET /api/flags` endpoint |
| `web/phase-detector/lib/flags.tsx` | `FlagsProvider`, `useFlag`, `useExperiment`, `useVariantValue` |
| `web/phase-detector/components/HeroCtaText.tsx` | Demo experiment client island |
| `web/backend/tests/test_flags.py` | 23 unit + integration tests |
