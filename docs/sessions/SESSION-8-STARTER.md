# Session #8 Starter

> Session #7 完成时间：2026-05-14 ~15:30 CST
> Main HEAD: `23484f7`
> 累计 PRs in session #7: **15** (#64-#79)
> 用户身份：达达 (dada8899)，repo PUBLIC
>
> Session #8 第一件事：读本文件 §0，跑起手扫描，然后按 §3 优先级队列推进。

---

## §0 起手 60 秒

```bash
cd ~/Projects/structural-isomorphism
git pull origin main
git log --oneline -8         # HEAD 应该是 23484f7 或更新
gh auth status               # 必须 ✓ logged in dada8899
ls .env                      # 本地 DeepSeek key
.venv/bin/python -m pytest web/backend/tests/ -q   # 30 backend tests 应全过
.venv/bin/python -m pytest web/tests/e2e/ -q       # 11 e2e 应全过
curl -s -o /dev/null -w "%{http_code}\n" https://beta.structural.bytedance.city/   # 应 200
```

### 凭证状态

| 凭证 | 位置 | 状态 |
|---|---|---|
| DeepSeek API key | `.env` | ✅ 本地，VPS 部署生效（VPS env） |
| OpenRouter API key | `.env` / VPS env | ✅ Anthropic Sonnet 4.6 (默认 LLM) + DeepSeek (ask orchestrator default) |
| OpenRouter Kimi key | — | ❌ B4 ensemble 用 fallback (T 变化 DeepSeek) |
| GitHub auth | keyring | ✅ |
| PYPI_TOKEN | — | ❌ session #6 P0 #1 仍待用户 |
| ZENODO_ACCESS_TOKEN | — | ❌ session #6 P0 #2 仍待用户 |
| arXiv account | — | ❌ session #6 P0 #3 仍待用户 web |
| Sentry DSN | — | ❌ Sentry SDK 集成 ready，DSN 不存在则 no-op |
| NVD API key | — | ❌ session #7 W2-C 跑 CVE 2023 用 unauth 24k records；2010-2025 全量需要 API key |
| STRUCTURAL_API_TOKENS env on VPS | — | ⚠️ paid tier 测试用，未配置 |

### 关键路径（活的产线）

| 角色 | 域名 | 部署位置 | service |
|---|---|---|---|
| **Structural (Perplexity-like)** | `beta.structural.bytedance.city` | `/root/Projects/structural-isomorphism/web/{frontend,backend}/` | `structural-web` (5004) |
| Structural 学术老站 | `structural.bytedance.city` | (legacy 静态) | nginx 直供 |
| **Phase Detector** | `phase.bytedance.city` | `/root/Projects/structural-isomorphism-v4/web/phase-detector/` | `phase-detector-web` (3210) + `phase-detector-api` |

---

## §1 Session #7 落地清单（不要重复做）

✅ Session #7 一次性 ship 5 个 direction + Perplexity-like 主页面 + 部署 + e2e 11/11 pass。完整 PR 表在 `HANDOFF.md` §1。

### 已生效的新能力

1. **POST /api/ask/stream** — SSE 7-event Perplexity 流（meta/kb_cards/answer_chunk\*/answer_done/similar_phenomena/followups/done）
2. **新 /index.html** — 大 search bar + 4 example chips + thread view + AbortController + ?q= deep-link
3. **/learn** — 旧 home 备份，保 marketing + SEO
4. **GitHub Actions CI** — sanity.yml on push/PR + site-smoke.yml every 6h
5. **History SQLite** — GET/POST/DELETE /api/history（X-Device-ID 头，前端 opt-in remote merge）
6. **Observability** — JSON structured logger + Sentry SDK guarded import
7. **Auth tier** — STRUCTURAL_API_TOKENS=paid:xxx,free:yyy env config，verify_api_token 中间件
8. **i18n EN 100%** — 244/244 HTML keys
9. **Phase Detector 500 ticker + 55 sample StructTuple + backtest engine v0.1**
10. **Pre-registration infra + B4 ensemble script + CVE preregister FAIL 已记录**
11. **GlossaryTooltip v2** — 相变 / 标度形式 / 涌现 / 反馈环 / 阈值效应
12. **Plausible 14 自定义 events** — ask_submitted / kb_cards_received / answer_completed / similar_card_clicked / followup_clicked / deep_analysis_triggered / citation_clicked / example_chip_clicked / tldr_card_shown / analyze_section_expanded / glossary_tooltip_opened / discoveries_loaded / ...
13. **Mobile ≤480px nav 修** — 隐藏次要 nav-link + overflow-x: hidden

---

## §2 Defer 到 session #8 的事

按优先级：

### P0 — Token-dependent 发布动作（仍待用户）

1. **PyPI publish** — soc-pipeline + guarded-llm wheels 已 ready（session #3）
2. **Zenodo DOI mint** — dataset/v1 已打包（session #3）
3. **arXiv submission** — C1 v0.3.1 + 4 solo + C4 (6 PDFs)
4. **GitHub release v0.4.0** — session #7 milestone tag（可用 `git tag v0.4.0 23484f7 && git push origin v0.4.0`，不依赖 token）

### P1 — Phase Detector 商业化（无 token 依赖，session #8 主菜）

5. **跑完剩余 445 ticker StructTuple** — `~/Projects/structural-isomorphism/v4/product/d1_phase_detector/extract_structtuple_batch.py --limit 500`（~$0.45，~45 min）
6. **Backtest 真实价格数据接入** — Stooq 或 yfinance API key
   - 跑 walk-forward backtest（每月滚动 6mo return）
   - 数据如不显著（synthetic 跑出 t=-0.48），需要回头 review StructTuple 抽取逻辑
7. **/backtest 页面接入 phase.bytedance.city** — serve_backtest.py stdlib http.server 已就绪，需 Next.js page 调用
8. **Free / Paid tier subscriptions** — Stripe 集成 OR Buttondown newsletter（design 文档 plans/company-analysis-product.md v0.2 已写）

### P1 — Perplexity-like 增强（用户反馈驱动）

9. **VPS LLM 模型切换** — VPS 当前 /api/health 显示 `anthropic/claude-sonnet-4.6`，但 /api/ask/stream 默认是 `deepseek/deepseek-chat`。考虑 `ASK_LLM_MODEL=anthropic/claude-sonnet-4.6` 升级答案质量（成本 ×3-5）
10. **followups click handler 集成** — W2-A 已支持 followup 触发新 thread item，但需要 user 用真实使用看 follow-up 质量
11. **citation click 跳转** — 当前 [N] 显示但点击行为待 polish（链到 KB 现象详情页 /phenomenon/<id>）
12. **History sidebar 远程同步默认 on** — 当前 opt-in `localStorage.structural_use_remote_history = '1'`
13. **/discoveries layout shift 终极验证** — W3-B 加了 skeleton，需要 Playwright 对比 CLS metric

### P1 — 科学纵深

14. **B4 ensemble 跑完 23 类** — W2-C 跑了 8 类 sample，3/7 DIFFER 提示 B3 fragile
15. **NYC FDNY fires + WSB posts real fit** — pre-registration yaml 已写，data fetch 待实施
16. **OpenRouter Kimi key** — 让 B4 ensemble 真正异构（不是 fallback T 变化）

### P2 — 长期 staged

17. **Adversarial pre-registration paper 写作** — CVE FAIL 是最强 anti-p-hacking 证据，单独成 paper
18. **Backtest 商业化 path 判定** — 真数据出来后看是否走 alpha 产品 vs narrative
19. **Plausible 数据回看** — session #7 ship 14 events，跑 1-2 周后看真实使用率

---

## §3 Session #8 起手推荐顺序

```
1. §0 起手扫描（git pull / pytest backend e2e / curl prod health）
2. 用户决策：本 session 走哪条路？

   Option A — Phase Detector 商业化（P1 #5 #6 #7 #8）
     需要外部数据源 (Stooq/yfinance 价格 API)。先跑完 500 ticker StructTuple
     做 walk-forward backtest，看真数据下 t-test 是否显著。

   Option B — 发布优先（P0 #1 #2 #3）
     用户给 PYPI_TOKEN + ZENODO_ACCESS_TOKEN + arXiv 账号

   Option C — Perplexity 增强（P1 #9-#13）
     用户反馈驱动，需要先看 prod 真实使用数据

   Option D — 科学纵深（P1 #14 #15 #16）
     OpenRouter Kimi key 拿到 → 跑完 B4 23 类 → 论文级 verdict
```

---

## §4 已知 quirks

继承 session #6-STARTER §6 12 条 + 新加 6 条：

13. **slowapi 动态限速 callable 不收 request** — `__limit_provider()` 无参（或 key 单参）。tier-aware rate limit 要靠 contextvar 不是 closure。
14. **session #7 form 4 silent fallback 仍然真实** — `isolation: "worktree"` flag 不可靠。subagent 主动 `git worktree add -b <branch> /tmp/<name>` 自救最稳。
15. **cherry-pick rebase 是 wave 1/2/3 标配** — agent branch 都基于 old main，merge 时全量 deletion。`git checkout -b <new> main && git cherry-pick <sha>` 比 rebase 干净。
16. **FastAPI 静态文件路由必须显式声明** — `/learn` 不会自动 fallback 到 `learn.html`。每个新页面加 `@app.get("/X") async def X_page(): return FileResponse(FRONTEND_DIR / "X.html")`。
17. **Mobile nav overflow 是 pre-existing 全站问题** — `.site-header__nav` 300px 在 375px viewport 越界。session #7 加了 `@media (max-width: 480px) { .site-header__nav .site-header__nav-link { display: none } }` 兜底。
18. **VPS 部署管道（实证 SOP）** — 看 `docs/sessions/session-7-deploy-verified.md` §部署管道，rsync + ssh restart + curl smoke 三件套。

---

## §5 起手 prompt 模板

### Option A (Phase Detector 商业化)

```
继续 session #7 留的 P1 #5-#8。
1. 跑 v4/product/d1_phase_detector/extract_structtuple_batch.py --limit 500 把 445 剩余 ticker 全跑了 (resume-safe, ~$0.45, ~45min)
2. 真实价格数据接入：用 yfinance pip install 或 Stooq daily CSV（看 fetch_prices.py --real 行为）
3. 跑 walk-forward backtest，输出 backtest_result.json + cumulative.csv，看 t-test 是否显著
4. 如果显著 → 商业化路径打开（设计 free/paid tier）；否则回头 review StructTuple critical_point_state 抽取 prompt
```

### Option B (发布)

```
继续 session #7 P0 #1-#4。用户给 PYPI_TOKEN + ZENODO_ACCESS_TOKEN（在对话首段贴）：
1. PyPI publish soc-pipeline + guarded-llm
2. Zenodo mint DOI for dataset/v1
3. arXiv 提交 (web 操作，user-driven)
4. GitHub release v0.4.0 (session #7 milestone) — 即使没 token 也能做
```

### Option C (Perplexity 增强)

```
看 Plausible 跑了 1-2 周的 prod 数据 (https://plausible.bytedance.city) — 哪些 event 高频，哪些零调用。
基于真实数据决定：
- /api/ask/stream 升级 LLM 到 anthropic/claude-sonnet-4.6（成本 ×3）
- followups + citations 行为优化
- History remote sync 默认 on
- /discoveries CLS 终极 polish
```

---

## §6 Session #7 Stats

- **15 PRs merged in main** (#64-#79)
- **11 subagents** in 3 waves with worktree isolation
- **6 hotfix iterations** in main session (#75 #76 #78 + 3 manual cherry-pick rebase)
- **Total LOC delivered**: ~9700+ insertions, ~500 deletions
- **Backend tests**: 30 pass (3 ask + 11 history + 16 auth)
- **E2E tests**: 11/11 pass
- **Cost**: ~$0.5 LLM calls (W1-B 55 sample $0.055 + W2-C $0.35 + W2-D batch tests + tries)
- **Time**: ~2.5 hours main session + 4 hours total agent wall time

---
