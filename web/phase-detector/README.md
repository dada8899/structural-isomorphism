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

## Deploy

Target subdomain: **phase.bytedance.city** (live).

1. `pnpm build` to produce `.next/` output
2. Reverse-proxy `phase.bytedance.city` → `127.0.0.1:3210` via nginx; `/api/` 反代到 `127.0.0.1:8200` (phase-detector-api)
3. `certbot --nginx -d phase.bytedance.city`
4. systemd: `phase-detector-web` (3210) + `phase-detector-api` (8200)

### ⚠️ build-time env (重要)

Next.js `NEXT_PUBLIC_*` 是 **build-time** 烧入 bundle 的。**必须**在 `pnpm build`
前准备好 `.env.production`（已 commit 到 repo）：

```
NEXT_PUBLIC_API_BASE=/api
NEXT_PUBLIC_USE_MOCK=false
```

- `/api` 是相对路径，浏览器走 `https://phase.bytedance.city/api/...` → nginx 反代到 8200
- 缺这个文件时 build 会用源码默认值 `http://localhost:8000`，前端到用户浏览器的本地端口（不存在）→ "Failed to fetch"
- 改了 `.env.production` 后必须 **rebuild + restart**（不是 dev hot reload）

部署 SOP（手动 fallback）：

```bash
cd /root/Projects/structural-isomorphism-v4/web/phase-detector
git pull --ff-only origin main
export NVM_DIR="/root/.nvm" && . "$NVM_DIR/nvm.sh"
pnpm build && systemctl restart phase-detector-web
```

## Auto-deploy

Push 到 `main` 且改动落在 `web/phase-detector/**` 时，GitHub Actions
workflow [`.github/workflows/deploy-phase-detector.yml`](../../.github/workflows/deploy-phase-detector.yml)
自动跑：

1. CI runner 用专用 SSH key（GH secret `VPS_DEPLOY_KEY`）登 VPS
2. VPS `~/.ssh/authorized_keys` 上的 `command=` 限制强制只会跑
   `/root/scripts/deploy-phase-detector.sh`（key 不能执行任意命令）
3. 脚本流程：`git fetch && reset --hard origin/main` →
   guard `.env.production` 存在（缺则非零退出）→
   `pnpm install --frozen-lockfile` → `pnpm build` →
   `systemctl restart phase-detector-web` → curl smoke
   `https://phase.bytedance.city/`
4. CI runner 再做一次外部 curl smoke 兜底

手动触发：`gh workflow run deploy-phase-detector.yml`。

防回 2026-05-14 故障：脚本第一步就检查 `.env.production`，缺则
非零退出，不会以损坏配置 build 出问题 bundle。改 `.env.production`
本身就会触发本 workflow（`web/phase-detector/**` paths 命中）。

## Architecture notes

- API client (`lib/api.ts`) supports both real-API and mock modes via
  `NEXT_PUBLIC_USE_MOCK`. Mocks are in `lib/mock-data.ts`.
- All taxonomy labels + colour mappings centralised in `lib/labels.ts`
  so backend / docs / UI stay in sync via the same enum constants.
- Styling is Tailwind only — no extra UI lib, no animation lib. Aim is
  Apple HIG / Bear / 飞书 calmness: white background, dense info, no
  decorative motion.
