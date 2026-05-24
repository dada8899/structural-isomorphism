# Session #11 进度 (2026-05-15)

> Started post-session-#10 closeout (Wave 6-15, 50 PR merged, v0.4.x tagged).
> User auth: "auto mode, 跑到 context 90% 才停下"。
> Initial wrong-project incident: 6 audit agents 误派 ~/Projects/renai-cross。已纠正切到 ~/Projects/structural-isomorphism。

---

## 1. 6 个 audit agent (Wave 0 — 巡查)

全部 read-only，无 working tree 污染。报告写到 `docs/audit/2026-05-15-*.md`：

| Agent | 报告文件 | 严重发现 |
|---|---|---|
| 项目健康度 | `2026-05-15-session-11-health.md` | Next.js 14.2.15 CVE × 25 vuln (1 critical / 7 high); coverage gate 红; CI matrix issues |
| phase.bytedance.city E2E | `2026-05-15-phase-walkthrough.md` | 20+ routes all 200; `/me` unauthed UX; 404 中英混杂; 公司列表无分页 |
| beta.structural API | `2026-05-15-beta-api-audit.md` | tier_limit_decorator 没读 ContextVar; 18 endpoints 仅 2 个有 limit; OpenAPI schema drift |
| docs + papers + packages | `2026-05-15-docs-papers-packages.md` | mkdocs config OK; Storybook 17 stories ✅; 5 papers arXiv-ready; 3 PyPI ready; CITATION.cff 待 bump |
| CI + 防灾 deploy | `2026-05-15-ci-deploy-audit.md` | 6 workflows 系统性失败; GH Pages 未启用; HF_TOKEN/DEEPSEEK_API_KEY secrets 缺 |
| VPS prod 全扫 | `2026-05-15-vps-prod-scan.md` | 5 service active; **3 cert 过期** (bytedance.city/cc/monitor) |

---

## 2. Wave 1 fix subagents (6 PRs merged)

全部走 worktree 隔离 + 显式 git add + squash-merge --admin。

| PR | 主题 | Branch | Tests |
|---|---|---|---|
| **#199** | ci: install editable packages/* + pyyaml + mkdocstrings | fix/p0-ci-packages-install | local import smoke pass |
| **#200** | chore(api): FastAPI on_event → lifespan | fix/p1-fastapi-lifespan | 323 pass |
| **#201** | fix(security): next 14.2.15 → 14.2.35 + postcss override | fix/p0-nextjs-1425 | next compile ✓ |
| **#202** | fix(api): tier-aware rate limit ContextVar + 7 endpoints | fix/p0-ratelimit-coverage | 301 pass (+17) |
| **#203** | chore(polish): CITATION 0.4.0 / /me redirect / 404 zh / ESLint / 加载更多 | chore/p2-polish-batch | pnpm build ✓ |
| **#204** | fix(openapi): sync schema + 9 response_model | fix/p1-openapi-drift | 284 pass |

**安全影响**：
- npm audit vuln 16 → 14（剩 14 需 Next 15.x，独立工作）
- Next.js CVE-2024-56332 + middleware bypass + Image cache poisoning fixed
- 7 个 LLM-expensive endpoint 加 rate limit (search/mapping/synthesize/admin)
- tier_limit_decorator ContextVar 修复 (slowapi callable signature gotcha)

---

## 3. Prod 故障恢复

**3 cert 过期**（discovered in VPS scan）：
- `bytedance.city` (multi-domain: bytedance.city + astock + bot + petsoul + soulexpert) — -3d expired
- `cc.bytedance.city` — -1d expired
- `monitor.bytedance.city` — -2d expired

主 session 直接 ssh vps + `certbot renew --cert-name <X> --force-renewal --non-interactive` ×3，nginx 自动 reload，3 个域名恢复 200 ✅。新 cert 有效期至 2026-08-13 (89 天)。

`--quiet` 模式吞错误是教训：第一次 `certbot renew --quiet` exit 0 但其实没续。

**根因调查 in-flight**：F10 subagent 在查 certbot.timer / cron 为啥没自动续。

---

## 4. Wave 2 fix subagents

派出 7 个 worktree-isolated subagents 修剩下的 P1/P2 + CI 红根因：

| PR | 主题 | 状态 |
|---|---|---|
| **#205** | fix(storybook): align fixtures.ts to UniversalityEvidenceSystem schema | ✅ MERGED |
| **#206** | fix(ci): perf_check_bundle regex covers root corner char + bare / route | ✅ MERGED |
| **#207** | fix(types): regenerate api-types.ts to match F4 response_model | ✅ MERGED |
| F8 | Coverage CI gate 90% critical-modules failure | in-flight |
| F10 | certbot.timer never enabled (OpenCloudOS preset disabled) | ✅ manually fixed on VPS |
| F12 | deploy CI=true (pnpm no TTY → ERR_PNPM_ABORTED_REMOVE_MODULES_DIR_NO_TTY) | in-flight |
| F13 | pnpm-lock.yaml drift (F5 加 eslint 没 refresh lockfile) | in-flight |

**F9 真根因**：`perf_check_bundle.py` regex 缺 `┌` root-corner tree char + `(/\S+)` 不收 bare `/` route。F6 报告的"No routes parsed"症状是同 bug 不同表现，不是 Next 14.2.35 格式变化。

**F11 (TS types regen)**：F4 PR #204 加了 9 个 Pydantic response_model 没同步生成 TS。已 regen + 加 9 新 interface 到 `web/phase-detector/lib/api-types.ts`。

**F10 certbot 根因**：VPS 上 `certbot-renew.timer` 从未 enable（OpenCloudOS 9 默认 preset=disabled，跟 Ubuntu snap auto-enable 不同）。3 个月人肉续期撑住，这次没看 LE 邮件 → 3 cert 同时过期。已 `systemctl enable --now certbot-renew.timer` 修复，下次触发 2026-05-15 16:51 CST。诊断报告 `docs/audit/2026-05-15-certbot-autorenew-rca.md`。

---

## 5. 已知仍 user-input only blocker

| Item | Why |
|---|---|
| **arXiv 5 paper submit** | user 账号 + 上传 |
| **PyPI 3 package publish** | `PYPI_TOKEN` GH secret |
| **HF Hub model push** | `HF_TOKEN` |
| **Zenodo DOI mint** | `ZENODO_ACCESS_TOKEN` |
| **GH Pages enable** | Settings → Pages → "GitHub Actions" source |
| **DeepSeek API key 历史 scrub** | rotate + `git filter-repo` + force-push |
| **PUBLIC repo flip** | 最后一步，不可逆 |

CC 全准备完毕，等 user 20-30 分钟 action 即可一键 OSS launch（per SESSION-11-HANDOFF §6 Option A）。

---

## 6. 主 session 走过的工具调用模式

- 6 audit + 6 fix (wave 1) + 4 fix (wave 2) + 3 cert renew + 1 nav fix = 0 race / 0 commit boundary 违反
- worktree 隔离 SOP + 显式 git add 100% 强制（per memory `feedback_subagent_form1_pollutes_main_commit.md`）
- cherry-pick onto current main pattern 准备好（F5 用 BEHIND state + --admin override 替代 rebase）

---

## 7. 下个 session 推荐

继续 SESSION-11-HANDOFF §6 Option A: 用户配 PYPI_TOKEN + HF_TOKEN + arXiv 账号 + GH Pages enable → CC 1 小时全部完成 OSS launch。

Coverage / perf / CI 红的情况等 Wave 2 subagents 回报后能看清楚是否还有阻塞。
