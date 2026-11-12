# Session #7 — Master Plan

> Started: 2026-05-14
> Authorization: user 全权授权，5 个方向（#1 #2 #3 #4 #6）做完 + 主页面定型 Perplexity-like 真搜索引擎
> Execution: 多 agent 并行 + worktree 隔离 + 3 wave 推进
> Stop condition: 上下文 ≥ 90% OR 所有 wave 全部 merged + 部署 + smoke 通过

---

## 0. 北极星 (North Star)

**最终主页面 = Perplexity-like 真搜索引擎**：

```
[用户输入复杂问题，例如：
 "为什么硅谷银行挤兑后市场反应那么剧烈？还有什么类似的系统？"]

  ↓ (用户按 Enter)

┌────────────────────────────────────────────────────────┐
│ 📍 Answer (typewriter SSE)                              │
│   银行挤兑属于 SOC + Diamond-Dybvig 临界翻转类。         │
│   关键机制：信息级联 + 资金抽离正反馈... [1] [3]         │
│                                                         │
│ 🔗 Sources (clickable citations)                        │
│   [1] FDIC bank failures (2026, n=3960, α=1.90)         │
│   [2] USGS earthquakes (b=1.08)                         │
│   [3] DeFi liquidation cascades (α=1.57-1.68)           │
│                                                         │
│ 🧬 Structurally Similar Phenomena                       │
│   ┌────────────┐ ┌────────────┐ ┌────────────┐         │
│   │ Earthquake │ │ Power grid │ │ Solar flare│         │
│   │ b=1.08     │ │ α=2.02     │ │ α=2.19     │         │
│   └────────────┘ └────────────┘ └────────────┘         │
│                                                         │
│ 💡 Follow-up Questions                                  │
│   • 银行挤兑能像地震一样预测吗？                          │
│   • 有哪些"前兆"指标？                                    │
│   • 历史上类似 SVB 的级联事件？                           │
│                                                         │
│ 🔬 Run Deep Analysis ▸  (1-2 min, full 9-section report)│
└────────────────────────────────────────────────────────┘
```

新页面：`/` (replace current home) OR `/ask` (并行存在)。我选 **新 `/` 替换**，老页面挪到 `/about-old` 备份。

**核心要求**：
- 复杂任务 = 一次提问能给完整答案 + 引用 + 跨域类比 + 后续追问
- SSE 流式（typewriter），不等完整 60s 才出
- Citations 真实可点（链到 KB 现象详情 / paper / phase detector 卡）
- Follow-up 用户点了直接在同页继续（thread 形态）
- "Run Deep Analysis" 一键升级到 60s 完整 /analyze

---

## 1. 任务全景 (5 directions × N tasks)

### #6 Perplexity-like 真搜索引擎（最高优先级，最终主页面）

**Backend**：
- 新 endpoint `POST /api/ask/stream` (SSE)：
  - Phase A (≤2s)：vector search top-5 KB phenomena
  - Phase B (~5-8s)：DeepSeek-v4-flash 生成 200-400 字 short answer + 5 citations + 3 follow-up questions
  - Phase C (~3s)：搭配 structurally similar phenomena 卡片数据 (top 3 with metrics)
- 复用 `services/search_service.py` + 新 `services/ask_orchestrator.py`
- guardrail: pydantic schema (answer / citations / similar / followups)

**Frontend**：
- 新 `/index.html` (Perplexity-like) — 大 search bar + result thread
- 新 `/assets/js/ask.js` — SSE consumer + thread state + follow-up wiring
- 新 `/assets/css/ask.css` — clean minimal UI (white bg + Inter + Noto Serif SC 字体已就绪)
- "Run Deep Analysis" 按钮 → 跳到 `/analyze.html?text_a=...&b_id=...` (复用现成 60s flow)
- History sidebar 复用（已有 `history-sidebar.js`）

**Acceptance**:
- 输入"为什么银行挤兑这么吓人"按 Enter → ≤2s 出 KB cards / ≤8s 出 short answer / ≤12s 全部完成
- 至少 3 个 citation 可点
- 至少 3 个 follow-up 可点击触发新查询
- Mobile 375px 不破

### #1 Phase Detector backtest + scale 500

**Backtest engine v0.1**：
- `v4/product/d1_phase_detector/backtest.py`
- 输入：100 (后续 500) 家公司 + 历史 StructTuple 时间序列（每月一个 snapshot，至少 12 个月）
- 计算：每月把 `critical_point_state == "near_critical"` 的公司分一组 vs 其他，对比下一个 6 月的实际股价 return（用 yfinance 或 FRED）
- 输出：cumulative return curve + Sharpe ratio + max drawdown，存 JSON + PNG
- 集成到 phase.bytedance.city 新页 `/backtest`

**Scale 100 → 500**：
- 选 500 ticker（S&P 500 全部即可）
- 跑 DeepSeek-v4-flash 抽 StructTuple（参考 `companies.jsonl` 现有 100 家）
- Cost: ~$5 (500 × $0.01)
- 输出 `companies_500.jsonl`

**Acceptance**:
- `python v4/product/d1_phase_detector/backtest.py --period 12m` 跑通
- 至少 500 家公司有 StructTuple
- phase.bytedance.city 加 `/backtest` 页面（基础版可以）

### #3 科学纵深

**(a) Adversarial pre-registration (3 systems)**：
- 复盘 C1 v0.3 §8 列的 5 个候选系统
- 选 3 个：(i) 城市火灾 (NYC FDNY) (ii) 网络攻击事件 (CVE size) (iii) Twitter cascade (替代源)
- 流程：
  1. Pre-register exponent band（基于理论预测）写入 `v4/preregistration/<system>.yaml`
  2. **再** 拉数据 + 跑 soc_pipeline
  3. 对比预登记 band vs 实测 → 记录 success/fail
- Output: 3 个 `v4/validation/<system>/` + 1 个 summary paper draft

**(b) B4 异构 ensemble**：
- 原 B3 是 3 × DeepSeek (同模型 = 重复偏见)
- 新：DeepSeek-v4-pro + Kimi-K2.5 + DeepSeek-v4-flash（3 vendor 模拟，note: OpenRouter Anthropic/Gemini CN block，所以用 DeepSeek 直连 + OpenRouter Kimi）
- 跑 23 类 verdict 重判
- Output: `v4/results/B4_heterogeneous_ensemble.jsonl` + diff vs B3

**(c) yaml schema 扩展**：
- 24 个 `v4/taxonomy/classes/*.yaml` 加 negative_examples + edge_cases 字段
- Script: `v4/scripts/expand_taxonomy_yaml.py` (LLM-assisted)

### #4 工程平台

**(a) GitHub Actions CI**：
- `.github/workflows/sanity.yml` — push/PR 跑 38 sanity tests + lint
- `.github/workflows/site-smoke.yml` — 部署后 curl 5 关键 endpoint
- Branch protection: main 必须 CI 过

**(b) API auth + rate limit**：
- 当前 `services/rate_limit.py` 已有 slowapi
- 加 simple bearer token 层（env `STRUCTURAL_API_TOKEN`）
- Frontend 无 token = anonymous tier (10/min)，有 token = paid tier (60/min)
- Document in `docs/API_AUTH.md`

**(c) History sidebar 持久化**：
- 当前 localStorage
- 新 SQLite (`web/backend/data/history.db`) + 匿名 device-id (cookie) + 跨设备同步可选（暂只本地，但 schema 准备好）
- Migration: 老 localStorage data 一次性导入

**(d) Sentry / 结构化日志**：
- `services/observability.py`：JSON structured logger + Sentry SDK (optional)
- 关键 endpoint 入口/出口 + try-catch + cost log

**(e) i18n 全站英文**：
- 检查 `i18n.js` 缺哪些 key
- 补齐英文翻译（重点新 `/` 页 + /analyze + /search）

### #2 UX 第三轮

**(a) Playwright MCP 跑全栈 e2e**：
- 测试新 `/` Perplexity-like 全流（input → short answer → similar cards → follow-up → deep analysis link）
- 测试老 /search /analyze /discoveries (regression)
- 截图存档 `docs/screenshots/session-7/`

**(b) Mobile 视口 375px 审计**：
- 重点：新 `/` + /analyze + /search + /discoveries
- 修发现的问题（最多 3-5 个 PR）

**(c) Plausible 自定义事件**：
- 加 `ask_submitted` / `short_answer_streamed` / `citation_clicked` / `similar_card_clicked` / `followup_clicked` / `deep_analysis_triggered`
- 老页面也补 `glossary_tooltip_opened` / `tldr_card_shown`

**(d) /discoveries layout shift 修**：
- PR-6 模式应用：`#disc-hero-stats / #disc-filter / #disc-list` 加 skeleton

**(e) GlossaryTooltip v2 词汇**：
- 加 5 词：相变 / 标度形式 / 涌现 / 反馈环 / 阈值效应
- 在 GLOSSARY map 加 entries

---

## 2. Wave 结构 (3 waves, agent assignment)

### Wave 1 — Foundations & long-running (4 agents parallel, isolated worktrees)

| Agent | Branch | 任务 | 估时 | 输出 |
|---|---|---|---|---|
| **W1-A** | `session7/ask-orchestrator` | #6 Backend: `/api/ask/stream` + `ask_orchestrator.py` + pydantic schema + test | 30-45min | endpoint + 1 unit test + curl example |
| **W1-B** | `session7/phase-500` | #1 Scale 100→500 + StructTuple batch extract (DeepSeek-v4-flash) | 60-90min (LLM batch) | `companies_500.jsonl` |
| **W1-C** | `session7/preregister-setup` | #3 Adversarial pre-register infra (3 yaml + soc_pipeline runner) + B4 ensemble script | 30-45min | infra + scripts + 1 system run example |
| **W1-D** | `session7/eng-foundation` | #4 GitHub Actions CI + history DB schema + SQLite migration script | 30-45min | `.github/workflows/*.yml` + history.db schema |

**Wave 1 必须先于 Wave 2 完成。** Wave 1 全 merged 后启 Wave 2。

### Wave 2 — Frontend rebuild + science follow-up (4 agents parallel)

| Agent | Branch | 任务 | 估时 | 输出 |
|---|---|---|---|---|
| **W2-A** | `session7/ask-ui` | #6 Frontend: new `/` Perplexity-like UI + ask.js SSE + ask.css | 60-90min | new `index.html` + `ask.js` + `ask.css` |
| **W2-B** | `session7/backtest` | #1 Backtest engine math + JSON output + `/backtest` page on phase | 60-90min | `backtest.py` + result JSON + UI page |
| **W2-C** | `session7/b4-ensemble-run` | #3 B4 ensemble run 23 类 + yaml schema 扩展 + 2 个 pre-register system 跑 | 60-90min (LLM batch) | `B4_*.jsonl` + 24 yaml updated + 2 system validation |
| **W2-D** | `session7/eng-polish` | #4 auth/rate limit + Sentry + i18n EN | 45-60min | auth middleware + structured logger + i18n EN coverage |

### Wave 3 — UX verification + integration + deploy (3 agents parallel + main session)

| Agent | Branch | 任务 | 估时 | 输出 |
|---|---|---|---|---|
| **W3-A** | `session7/e2e-playwright` | #2 (a) Playwright MCP 跑全栈 e2e + 截图 | 45-60min | screenshots + 1 markdown report |
| **W3-B** | `session7/ux-polish` | #2 (b)+(c)+(d)+(e) mobile + Plausible + /discoveries + glossary v2 | 60-90min | 多 PR |
| **W3-C** | `session7/preregister-3rd` | #3 第 3 个 pre-register system 跑 + summary draft | 45-60min | 1 system + draft md |
| **Main** | n/a | 部署 VPS + smoke + HANDOFF.md + SESSION-7-end.md + Git tag v0.4.0 | 30-45min | deploy verified + retro shipped |

---

## 3. 协同规则（避免踩 commit boundary 雷）

1. **每个 agent 用 `isolation: "worktree"`** — 给独立 branch + 独立 fs（防 form 1-6 silent fallback）
2. **每个 agent 报告 commit SHA**，主 session 验证后 squash merge + delete branch
3. **跨 wave 之间必 git pull** — Wave 2 起手前主 session 已 merge Wave 1 全部
4. **绝对路径** — agent prompt 必须含 `cd /Users/dadamini/Projects/structural-isomorphism` 强制开头
5. **不动其他 agent 的 scope** — Wave 1 W1-A 只改 backend `web/backend/`，W1-D 只改 `.github/` + history schema，禁交叉
6. **commit 标 scope**：`feat(structural-web)`/`feat(phase-detector)`/`feat(v4)`/`chore(ci)`/`feat(eng)`/`docs(sessions)`
7. **每个 PR ≤ 600 行 diff**（防大文件 stall）；超出 split

---

## 4. Stop conditions

继续做的条件：
- ✅ 上下文 < 90%
- ✅ 当前 wave 还有 agent in_progress
- ✅ 还有 P0 PR pending review

立即停下的条件：
- ❌ 上下文 ≥ 90% (auto compact 触发)
- ❌ Quota burn 5h（按 memory `feedback_session_26_lessons`）
- ❌ 触碰 prod 数据 / 不可逆操作 → 必停 ask

---

## 5. Session 收尾产物

1. `docs/sessions/SESSION-7-end.md` — 完整 retro，commits 表，PR 表，verdict
2. `docs/sessions/HANDOFF.md` 更新指向 session #8
3. `docs/sessions/SESSION-8-STARTER.md` — 下个 session 起手扫描
4. Git tag `v0.4.0`（如果 #6 完整 ship + 3 wave 全过）
5. 部署 + smoke verified（beta.structural / phase / 主 `/` 新页面）

---
