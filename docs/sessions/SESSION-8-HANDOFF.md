# Session #8 起手交接文档

> 上 session (#7) 完成于 2026-05-14 ~17:00 CST
> Main HEAD: `cf343c8` · 22 PRs merged (#64-#85)
> Git tags: `v0.4.0` (5 directions ship) + `v0.4.1` (post-deploy scale)
> 用户身份: 达达 (dada8899) · repo PUBLIC

---

## 0. 起手第一步（60 秒）

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -10                 # HEAD = cf343c8 或更新
gh auth status                        # ✓ dada8899
ls .env                               # 本地 DeepSeek + OpenRouter key

# Backend imports + tests
cd web/backend && PYTHONPATH=. ../../.venv/bin/python -m pytest tests/ -q
# 应 30 passed

# E2E live prod (5 主要 URL + Perplexity SSE)
cd ../.. && .venv/bin/python -m pytest web/tests/e2e/ -q
# 应 11 passed in ~20s

# Production health
curl -s https://beta.structural.bytedance.city/api/health
# {"status":"ok","kb_size":4443,"llm_model":"anthropic/claude-sonnet-4.6"}

curl -s -N -X POST -H "Content-Type: application/json" \
  -d '{"query":"test","lang":"zh"}' \
  https://beta.structural.bytedance.city/api/ask/stream | head -3
# event: meta / event: kb_cards / event: answer_chunk
```

如有任何步骤失败，先看 `docs/sessions/session-7-deploy-verified.md` 的部署 SOP。

---

## 1. Session #7 已 ship 的（不要重复做）

✅ **22 PR merged** (#64-#85)，**5 directions all delivered** + post-deploy scale。

| Direction | 主要交付 |
|---|---|
| **#6 Perplexity-like 真搜索引擎** (北极星) | POST /api/ask/stream 7-event SSE + 新 /index.html + ask.js (574 LOC) + ask.css (705 LOC) + /learn 旧 home 备份 |
| **#1 Phase Detector** | **500/500 ticker StructTuple** (full SP500, $0.30) + backtest engine v0.1 + 9 pytest + .env.production fix (今天) |
| **#2 UX 第三轮** | mobile fix + Plausible 14 events + /discoveries skeleton + glossary v2 (5 新词) |
| **#3 科学纵深** | **B4 full 21 classes (62% disagree vs B3)** + 35/35 yaml expanded + **CVE FAIL** + **NYC FDNY INCONCLUSIVE** + CVE paper draft v0.1 |
| **#4 工程平台** | GitHub Actions CI + history SQLite + observability + auth tier + i18n EN 100% + 30 backend tests |

### Live prod URLs (全部 200 + e2e verified)

- https://beta.structural.bytedance.city/ — **Perplexity-like 主页面**
- https://beta.structural.bytedance.city/learn — 老 home backup
- https://beta.structural.bytedance.city/api/ask/stream — SSE endpoint
- https://beta.structural.bytedance.city/api/health
- https://phase.bytedance.city/ — Phase Detector（今天修了 .env.production，筛选 OK）

---

## 2. 今天最后的修复（用户反馈触发）

**用户报错**: phase.bytedance.city 点筛选 "Failed to fetch"

**根因**: VPS 上 `web/phase-detector/.env.production` 不存在 → Next.js build 时把 `NEXT_PUBLIC_API_BASE` 烧成源码默认值 `http://localhost:8000`（用户浏览器自己的本地端口） → 任何 fetch 都失败 + mixed content。

**Fix (PR #85)**: 
- 在 repo commit `.env.production` (`NEXT_PUBLIC_API_BASE=/api` + `NEXT_PUBLIC_USE_MOCK=false`)
- README 加 build-time env 警告 + 部署 SOP
- VPS 重 build + restart `phase-detector-web`

**Verify**: Playwright 真浏览器测，3 个 `/api/screener` 调用全 200，0 error。

**Memory**: 这是 Next.js `NEXT_PUBLIC_*` 是 build-time 烧入的典型 trap —— 任何下次 redeploy phase-detector 时如果忘加 `.env.production`，bug 会复发。README 已加警示。

---

## 3. Session #8 优先级 P0/P1/P2 队列

### P0 — Token deps（仍待用户提供凭证）

1. **PyPI publish** — `soc-pipeline` + `guarded-llm` wheels (since session #3 ready)
2. **Zenodo DOI mint** — dataset/v1 99MB bundle
3. **arXiv submission** — C1 v0.3.1 + 4 solo + C4 + 今天加的 CVE preregister FAIL paper (cv-preregistration-fail-2026-05-14.md)

每项启动需要用户在对话首段贴 token。

### P1 — Phase Detector 商业化（推荐 session #8 主菜，无 token 依赖）

**4. 真实价格数据接入 + walk-forward backtest** ←—— **首选**

W2-B 已写好 backtest 算法 + 9 pytest，但当前用 synthetic 价格（GBM 模拟）。真数据下结果：
- 55 sample StructTuple: 8 near_critical / 47 other → t=-0.48, p=0.65 (synthetic noise as expected)
- 现在 **500/500 全量 StructTuple 已就绪**，可以做真数据 backtest

步骤：
```bash
# 1. 接入价格数据（选其一）
.venv/bin/pip install yfinance
# 或写 Stooq daily CSV fetcher（fetch_prices.py --real 已支持但不稳定）

# 2. 跑 walk-forward backtest（滚动窗口 6mo return）
.venv/bin/python v4/product/d1_phase_detector/backtest.py \
  --companies v4/product/d1_phase_detector/companies_500.jsonl \
  --period 6m \
  --real-prices

# 3. 看 t-test p-value：
# - p < 0.05 → 商业化路径打开！设计 free/paid tier
# - p > 0.05 → 回头 review critical_point_state 抽取 prompt
```

这是项目从"科普 demo"→"alpha-bearing product"的分水岭实验。

**5. /backtest 页面集成到 phase.bytedance.city**

`serve_backtest.py` stdlib http.server 已就绪。需要 Next.js 新增 `/backtest` 页 + 调用 `/api/backtest-result` + `/api/backtest-cumulative`。

### P1 — Perplexity 增强（用户使用数据驱动）

**6. VPS LLM 升级 sonnet-4.6 for /api/ask/stream A/B test**

当前 default `deepseek/deepseek-chat`（快、便宜）。升级到 `anthropic/claude-sonnet-4.6` 答案质量预期 ↑↑，cost ×3-5。env: `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6` 加到 `/root/Projects/structural-isomorphism/web/backend/.env`，restart。

A/B 方式：同时跑两个 endpoint 或随机 50/50，对比用户停留时间 / followup 点击率（已埋 Plausible 事件）。

**7. citation click → /phenomenon/{kb_id}**

当前 ask.js 已生成 `<a href="/phenomenon.html?id=...">` 但 click handler 没 polish。需要：
- 验证 `/phenomenon/{pid}` 路由实际能渲染 KB 详情
- 加 `aria-label` + 鼠标 hover 显示 KB description

**8. History sidebar remote-sync 默认 on**

当前 `localStorage.structural_use_remote_history = '1'` 才启用 remote。可以默认 on（API 已 ready）。

**9. /discoveries CLS metric 终极验证**

W3-B 加了 skeleton，需要 Playwright Lighthouse CLS metric 跑一遍对比。

### P1 — 科学纵深

**10. OpenRouter Kimi key** —— **关键 unblocker**

让 B4 ensemble 真正异构（当前 fallback DeepSeek T=1.0/0.5/0.0 模拟）。带 Kimi K2.5 后：
- 重跑 B4 21 类 → 是否仍 62% disagree？
- 真异构信号比 in-vendor T 变化强很多

**11. WSB posts pre-registration real fit**

`v4/preregistration/wsb-posts.yaml` 已写。Pushshift 停服，需要找替代源（archive.org / IA WSB scraper）。

**12. CVE FAIL paper finalize → arXiv `cs.CR` + `physics.data-an`**

`paper/cve-preregistration-fail-2026-05-14.md` v0.1 outline + result block 已写。需要：
- §1 Introduction 全 prose
- §5 Discussion 全 prose
- Refs 验证
- 4500 字目标

### P2 — Long-term staged

13. **Plausible 数据回看** — Wait 1-2 周看 ask_submitted / similar_card_clicked / followup_clicked 等真实使用率
14. **Adversarial pre-registration 整篇 paper** — CVE FAIL + NYC FDNY INCONCLUSIVE 两个 case study 合写
15. **Backtest paper / blog** — 看 backtest 显著性结果决定写法
16. **VPS DeepSeek key rotate sync** — 如果用户 rotate 过 key
17. **Branch protection on main** — CI required to merge

---

## 4. 必备 quirks（继承 session #7）

### 多 subagent 并行
1. **`isolation: "worktree"` flag 不可靠** —— form 4 silent fallback 全部 11 个 agent 撞。subagent prompt 强制开头 `git worktree add -b <branch> /tmp/<unique> main && cd /tmp/<unique>` 自救。
2. **Cherry-pick rebase 是 wave merge 标配** —— agent branch 基于 old main，merge 时 diff 显示几千行 deletion。`git checkout -b <new> main && git cherry-pick <sha>` 比 rebase 干净（特别是 LFS pointer 多的 repo）。
3. **commit boundary 永不 `git add -A`** —— subagent prompt 强制只 `git add <specific-file>`。commit 前必 `git diff --cached --name-only` 验证。
4. **并行 ≤5 agent**（memory `feedback_parallel_agent_quota_burn.md`）。

### Frontend
5. **Next.js `NEXT_PUBLIC_*` 是 build-time 烧入** —— 改 env 必须 rebuild + restart。`.env.production` 必须 commit 到 repo（已 fix in PR #85）。
6. **FastAPI 静态文件路由必须显式声明** —— `/learn` 不会自动 fallback 到 `learn.html`，每个新页面要 `@app.get("/X") async def X_page(): return FileResponse(FRONTEND_DIR / "X.html")`。

### Backend
7. **slowapi 动态限速 callable 不收 request** —— `_spec_for(request)` 会 TypeError。要 tier-aware 必须 contextvar 不是 closure。当前回退到静态 default_anon（PR #75）。
8. **OpenRouter Anthropic/Gemini CN 区域 block** —— 从 CN IP 出口 403。LLM agent 用 DeepSeek 直连或 fallback。VPS 在 Singapore 不受影响。

### 部署
9. **VPS 部署管道** ——见 `docs/sessions/session-7-deploy-verified.md` §部署管道。rsync + ssh restart + curl smoke 三件套。
10. **`structural-isomorphism-v4` 是同一 repo 的旧 checkout 名** —— git remote = `dada8899/structural-isomorphism`。VPS 上 phase-detector 的 working copy 在那里。

---

## 5. 关键文件入口

| 文件 | 用途 |
|---|---|
| `docs/sessions/HANDOFF.md` | 永久 entry point（已更新指向 session #7 状态） |
| `docs/sessions/SESSION-7-end.md` | 完整 retrospective |
| `docs/sessions/SESSION-8-STARTER.md` | session #8 详细 P0/P1/P2 队列 |
| `docs/sessions/session-7-deploy-verified.md` | 部署 SOP + 实测 SSE event log |
| **本文件** (`SESSION-8-HANDOFF.md`) | 起手快速摘要（你正在读） |
| `paper/cve-preregistration-fail-2026-05-14.md` | CVE FAIL paper v0.1 outline |
| `v4/results/B4_vs_B3_diff.md` | B4 vs B3 ensemble 对比（13 DIFFER） |
| `v4/validation/cve-vulnerabilities/README.md` | CVE FAIL 实验报告 |
| `v4/validation/nyc-fdny-fires/README.md` | NYC FDNY INCONCLUSIVE 实验报告 |
| `web/phase-detector/.env.production` | **不要删** — 没它 phase 筛选会再坏 |

---

## 6. Session #8 起手 prompt 模板

### 推荐 Option A — Phase Detector 商业化（无 token，最高 leverage）

> 接 session #7。500 ticker 全量 StructTuple 已就绪 (`v4/product/d1_phase_detector/companies_500.jsonl`)，backtest 算法 + tests 都通。今天做 walk-forward real-data backtest：
> 
> 1. 接入 yfinance（或 Stooq stable）拉 500 ticker 过去 24mo 月度价格
> 2. 跑 `backtest.py --period 6m --real-prices --companies companies_500.jsonl`
> 3. 输出 backtest_result.json + cumulative.csv + PNG
> 4. 看 near_critical 组 vs other 组的 t-test p-value
> 5. 显著 → 设计 free/paid tier 接入 phase.bytedance.city + /backtest 页面
> 6. 不显著 → 回头审 critical_point_state 抽取 prompt

### Option B — Perplexity 增强 + Plausible 数据驱动

> 看 https://plausible.bytedance.city 跑了 N 天的 prod 数据，对比 14 个埋点事件的真实使用率。基于真实数据决定：
> - /api/ask/stream LLM 升级 sonnet-4.6 (cost ×3-5) 是否值得
> - 哪些 follow-up 类型用户最常点
> - 哪些 citation 真被点击 → 暗示 KB 哪些条目最有价值

### Option C — Token 发布

> 我提供 PYPI_TOKEN + ZENODO_ACCESS_TOKEN + arXiv 账号。请按 session #4 SESSION-4-STARTER.md 的 9-step runbook 跑完 P0 #1-#3。CVE FAIL paper 也一并 arXiv 提交。

### Option D — 科学完整（需 OpenRouter Kimi key）

> 用户提供 OpenRouter Kimi K2.5 API key。重跑 B4 ensemble 21 类（这次 3 vendor 真异构，不是 T 变化 fallback）。对比 8/13 AGREE/DIFFER 是否仍成立。如果稳定 → C1 unified preprint §B 用 B4 替换 B3。

---

## 7. Session #7 stats（参考）

- **22 PR merged** in 1 session
- **13 subagents** in 4 waves with worktree 自救
- **8 hotfix iterations** in main session
- ~$1.85 total LLM cost
- ~4h main session + ~6h agent wall time
- 11/11 e2e PASS on live prod
- 30 backend tests pass
- 全部停在 context 90% 之前自然收尾

**唯一规模可比的历史 session**: session #26 (33 PR, 28 subagent, 5h rate limit hit)。session #7 通过 cherry-pick + worktree 自救 + ≤5 并行 agent 控量，全程无 quota burn。

---

## 8. 用户当下需求理解

session #7 大量交付后，用户在试用 phase.bytedance.city 时撞到了**今天才修的 .env 坑**（PR #85）。这说明用户正在认真用产品。

下个 session 起手时，**建议先问用户**：
- 是继续主推 Phase Detector 商业化（Option A）？
- 还是基于真实使用体验做 Perplexity-like 主页面的 polish（Option B）？
- 还是上发布路径（Option C）？

不要默认走 Option A —— 用户的实际触发点是产品 bug，可能想先稳定再扩张。

---

## 9. 最后一件事

**永远先读 `docs/sessions/HANDOFF.md` 的 §0 起手扫描**，不要跳。session #7 起手时通过这步发现了 baseline 状态 + LFS pointer 风险 + worktree 隔离 form 4，节省了至少 2 个 wave 的混乱。

祝 session #8 顺利。
