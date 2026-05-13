# Phase Detector — Screener UI (D1 / W3-C)

Next.js 14 (app router) + Tailwind frontend for the Structural Isomorphism
**Phase Detector** product. Lets the user filter companies by:

- Dynamics family (SOC / preferential-attachment / fold / hysteresis / other)
- Critical-point state (subcritical / near-critical / supercritical / tipped)
- Sector
- Minimum model confidence

…and shows a **30-second TL;DR card** per company plus a full report detail
page.

## Pages

| Path | Component | Purpose |
| --- | --- | --- |
| `/` | `app/page.tsx` | Screener home: stats bar + filter sidebar + card grid |
| `/company/[ticker]` | `app/company/[ticker]/page.tsx` | Detail page: TL;DR, primary indicators, confidence, caveats, raw response |

## Dev

```bash
cd web/phase-detector
pnpm install   # or: npm install
cp .env.example .env.local
# .env.local default uses NEXT_PUBLIC_USE_MOCK=true → no backend needed
pnpm dev       # next dev on http://localhost:3000
```

To hit the real backend (W3-B):

```bash
# In .env.local
NEXT_PUBLIC_USE_MOCK=false
NEXT_PUBLIC_API_BASE=http://localhost:8000
```

Backend endpoints consumed:

- `GET /screener?dynamics_family=...&critical_point_state=...&sector=...&min_confidence=...&limit=50`
- `GET /company/{ticker}`
- `GET /stats`

Response schema is described in `lib/types.ts`.

## Build

```bash
pnpm build   # production build, must pass before PR merge
pnpm start   # serve built app on :3000
```

## Deploy (planned)

Target subdomain: **phase.bytedance.city**

1. `pnpm build` to produce `.next/` output
2. Reverse-proxy `phase.bytedance.city` → `127.0.0.1:3xxx` via nginx
3. `certbot --nginx -d phase.bytedance.city`
4. Run with `pm2 start "pnpm start" --name phase-detector` (or systemd)

## Architecture notes

- API client (`lib/api.ts`) supports both real-API and mock modes via
  `NEXT_PUBLIC_USE_MOCK`. Mocks are in `lib/mock-data.ts`.
- All taxonomy labels + colour mappings centralised in `lib/labels.ts`
  so backend / docs / UI stay in sync via the same enum constants.
- Styling is Tailwind only — no extra UI lib, no animation lib. Aim is
  Apple HIG / Bear / 飞书 calmness: white background, dense info, no
  decorative motion.
