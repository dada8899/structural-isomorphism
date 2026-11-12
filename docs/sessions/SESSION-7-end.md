# Session #7 — Retrospective (WIP)

> Started: 2026-05-14 ~13:00 CST
> End: TBD (still in session)
> User authorization: full delegation, do all 5 directions (#1/#2/#3/#4/#6) + Perplexity-like 主页面 + 一直跑到 context 90% / 完全没事可做为止

---

## Session Summary

Session #7 是 session #5 之后第一次系统性大跨度 ship —— 5 个方向同时推进，最终目标 = 主页面定型为 Perplexity-like 真搜索引擎。

**全部 merge 进 main 的 PR**:

| PR | Title | Wave / Agent | Commit |
|---|---|---|---|
| #64 | SESSION-7-PLAN master plan | main | f3e9c92 |
| #65 | POST /api/ask/stream Perplexity SSE orchestrator | W1-A | f29c85b |
| #67 | CI workflows + history SQLite + observability | W1-D | 0529b68 |
| #68 | Phase Detector 100→500 + batch extract | W1-B | db68684 |
| #69 | Pre-registration infra + B4 ensemble script + taxonomy expand | W1-C | 34f2a81 |
| #70 | Perplexity-like /index.html (frontend) | W2-A | 2566c39 |
| #71 | Backtest engine v0.1 (near_critical vs other) | W2-B | 8b2fc68 |
| #72 | API auth tier + history remote + i18n EN 100% | W2-D | 42888c0 |
| #73 | B4 ensemble sample + taxonomy expand + CVE preregister FAIL | W2-C | 53b0f32 |
| (Wave 3) | TBD | W3-A/B/C | — |

---

## 方向交付 summary

### #1 Phase Detector (W1-B + W2-B)

✅ **shipped**:
- 503 SP500 ticker (Wikipedia + fallback)
- 500 companies_500_input.jsonl
- 55 sample StructTuple extracted (100% ok, $0.055)
- Resume-safe batch pipeline
- Backtest engine v0.1: near_critical vs other group return + Welch t-test + cumulative curve
- 9 pytest tests pass
- README_BACKTEST.md 设计文档
- /backtest API endpoint (stdlib http.server, NOT auto-started)

⚠️ **deferred to session #8**:
- 剩余 445 ticker 全量 LLM StructTuple pass (~$0.45, ~45min)
- 真实价格数据接入（当前 synthetic + provenance flag）
- Backtest 跑全部 500 公司 + walk-forward validation

### #2 UX 第三轮 (W3-A + W3-B)

🔄 **in progress (Wave 3)**:
- Playwright e2e 套件 + baseline 截图
- Mobile 375px 审计 + 修
- Plausible 自定义事件埋点
- /discoveries layout shift skeleton
- GlossaryTooltip v2 5 新词 (相变 / 标度形式 / 涌现 / 反馈环 / 阈值效应)

### #3 科学纵深 (W1-C + W2-C)

✅ **shipped**:
- 3 pre-registration yaml (NYC fires / CVE / WSB)
- run_preregistered_validation.py runner + dry-run gate
- B4 异构 ensemble script (DeepSeek-pro + flash + Kimi-K2.5 with fallback)
- 24/24 B4 verdicts on 8 sample classes (0 errors)
- **3/7 DIFFER from B3** — B3 consensus more fragile than v2 summary implied
- 12 taxonomy yaml expanded with negative_examples + edge_cases
- expand_taxonomy_yaml.py LLM-assisted enrichment script

✅ **CVE pre-registration — REAL FIT (verdict=FAIL)**:
- 24k/28.7k CVEs 2023, CVSS>=7.0, n=10280 over 277 days
- α=2.668 [2.40, 2.98] outside band [1.5, 2.5]
- Lognormal (p=0.002) + exponential (p=0.0001) beat power-law
- Patch-Tuesday clustering visible — administrative bursts not SOC critical events
- **Pre-registration discipline working** — band locked before fit, FAIL is interpretable

⚠️ **deferred**:
- NYC FDNY fires + WSB posts real fits (deferred for data source SOP)
- Full B4 ensemble on remaining 15/23 classes
- Full 2010-2025 NVD CVE pull (needs API key)

### #4 工程平台 (W1-D + W2-D)

✅ **shipped**:
- GitHub Actions CI: sanity.yml (push/PR pytest) + site-smoke.yml (every-6h curl 3 hosts)
- History SQLite: HistoryDB class + WAL + device isolation + GET/POST/DELETE /api/history
- Observability: JSON structured logger + optional Sentry SDK
- API auth tier middleware: services/auth.py + slowapi-aware rate_limit decorator
  - env STRUCTURAL_API_TOKENS="paid:tok_xxx,free:tok_yyy" 
  - 60/min paid · 10/min free · 5/min anonymous
- i18n EN 100% coverage (244/244 HTML keys, was 201/244)
- 27 backend tests pass (16 auth + 11 history_db)

⚠️ **deferred**:
- Sentry DSN 实接入 (script ready, no DSN provided yet)
- History frontend remote-source 默认 enable (currently localStorage authoritative + opt-in remote)
- Branch protection rules on main

### #6 Perplexity-like 主搜索引擎 (W1-A + W2-A) — 北极星目标

✅ **shipped** —— 这是 session 的核心交付:

**Backend** (`web/backend/services/ask_orchestrator.py` + `services/ask_schemas.py` + `api/ask.py`):
- POST /api/ask/stream SSE endpoint
- 7-event 序列：meta → kb_cards → answer_chunk\* → answer_done → similar_phenomena → followups → done
- 一次 LLM call (DeepSeek/OpenRouter) 返回 answer + citations + followups (pydantic-validated)
- typewriter cadence 8-char chunks @ 25ms
- 1 retry on JSON failure → fallback payload on second failure (SSE always completes)
- rate limit 5/min (升级至 auth tier 后变 5/10/60)

**Frontend** (`web/frontend/index.html` + `assets/css/ask.css` + `assets/js/ask.js` + `learn.html`):
- 新 `/index.html` = Perplexity-like (replace 老首页)
- empty state: 72px serif "Structural" brand + searchbox + 4 example chips
- thread state: query → KB cards → typewriter answer with [N] citations → similar phenomena × 3 → followups × 3 → deep-analysis CTA
- sticky-bottom followup form
- AbortController 中断流（用户在生成中点 followup 自动 abort）
- `?q=...` deep-link auto-run
- mobile 768px breakpoint (W3-B 加 480px 更紧凑断点)
- 老首页备份到 `/learn` (保 marketing + SEO)
- Legacy /search.html /analyze.html /discoveries.html 不动 (regression safety)

⚠️ **deferred (Wave 3 ongoing)**:
- Playwright e2e 端到端真跑验证（W3-A 在做）
- 部署到 VPS prod (主 session 做)
- 实际 LLM 配置（VPS env 是 anthropic/claude-sonnet-4.6，ask orchestrator default 是 deepseek/deepseek-chat — 需在 VPS 配 ASK_LLM_MODEL）

---

## Quirks / lessons (写 memory)

### Form 4 silent fallback 重现 (所有 4 个 Wave 1 agent)

主 worktree 不隔离 — 4 个并行 subagent (W1-A/B/C/D) 全部检测到主 worktree 被 sibling agents 切 HEAD / 留 untracked。

✅ **存活策略**：每个 agent 主动创建 `/tmp/si-<name>` linked worktree 自救：
- W1-D: `/tmp/si-worktrees/eng-foundation`
- W1-B: `/tmp/struct-iso-phase500` (用 `GIT_LFS_SKIP_SMUDGE=1` 绕开 LFS 报错)
- W1-A: stash + 显式 checkout 清理 sibling pollution
- W1-C: explicit `git add <file>` discipline

❌ **未来改进**：subagent prompt 强制开头加 `git worktree add ...` 命令而不是依赖 `isolation: "worktree"` flag（实测 form-4 silent fallback 仍发生）

### Cherry-pick rebase 必备

Wave 1/2 所有 agent branch 都基于老 main (5d66bee 或 d6f2191)，merge 时显示几千行 deletion (其他 agent 的文件)。**全部用 cherry-pick 重做到 current main 解决**（无 conflict on 不相交文件）。仅 `web/backend/main.py` 需要手动解 conflict (W1-A + W1-D 都加 router import)。

### CVE pre-registration 第一次真出 FAIL — 科学完整性信号

W2-C 跑 CVE NVD 2023 数据，α=2.668 outside pre-registered band [1.5, 2.5]。这是 V4 pipeline 第一次 verdict=FAIL 在 pre-registration 流程下 —— **方法论上是好事**：band 先锁定，失败可解释（Patch-Tuesday administrative bursts ≠ SOC）。写论文 §8 时这个 case 是最强的 anti-p-hacking 证据。

### B4 ensemble 揭示 B3 fragility

3/7 类在 B4 ensemble (DeepSeek-pro/flash + Kimi/T-fallback) 下从 B3 的 KEEP/REJECT 降级到 UNCLEAR：
- `delay_differential_debt`
- `motter_lai_network_cascade`
- `scheffer_fold_bifurcation`

意味 B3 的 KEEP=5 / REJECT=7 verdict 可能过度自信。**正式 paper 必须用 B4 (or 更广 ensemble) re-classify**。

---

## Final HEAD + git status

```
$ git log --oneline -10
7025b72 Merge pull request #73 from dada8899/session7/b4-ensemble-v2
53b0f32 feat(v4): B4 ensemble sample + taxonomy expand batch + CVE preregister real fit (#3 W2-C)
f9c1637 Merge pull request #72 from dada8899/session7/eng-polish-v2
42888c0 feat(eng): API auth tier + history remote endpoint + i18n EN expansion (#4 W2-D)
d7aa0b0 Merge pull request #71 from dada8899/session7/backtest
8b2fc68 feat(phase-detector): backtest engine v0.1 (near_critical vs other) (#1 W2-B)
04b81d5 Merge pull request #70 from dada8899/session7/ask-ui
2566c39 feat(structural-web): Perplexity-like /index.html — unified search engine (#6 W2-A)
159205e Merge pull request #69 from dada8899/session7/preregister-setup-v2
145a6cc Merge pull request #68 from dada8899/session7/phase-500-v2
```

---

## Wave 3 完成（所有 5 directions ship + verified）

✅ W3-A (PR #74): Playwright e2e 11 tests + 8 baseline screenshots
✅ W3-B (PR #77): mobile 480px + Plausible 14 events + /discoveries skeleton + glossary v2
✅ W3-C (主 session): VPS deploy + smoke verify + post-deploy screenshots
✅ 主 session 中 3 hotfix:
  - PR #75: tier_limit_decorator slowapi 签名 mismatch
  - PR #76: /learn route missing
  - PR #78: mobile ≤480px nav overflow
✅ PR #79: docs(sessions) deploy verified + 8 post-deploy screenshots + SOP

**Live verification (post-deploy)**:
- `curl https://beta.structural.bytedance.city/api/ask/stream` 完整 7-event SSE ✓
- `pytest web/tests/e2e/ -v` → **11/11 PASS in 20s**
- 8 post-deploy screenshots saved to `docs/screenshots/session-7/post-deploy/`

---

## Deferred to Session #8 (优先级降序)

**P0 — Token 依赖（不动）**:
- PyPI publish soc-pipeline + guarded-llm (wheels ready since session #3)
- Zenodo mint DOI for dataset/v1
- arXiv submission C1 v0.3.1 + 4 solo + C4

**P1 — Phase Detector 商业化（推荐 session #8 主菜）**:
- 跑完剩余 445 ticker StructTuple ($0.45, 45min)
- 真实价格数据接入（Stooq / yfinance）
- Walk-forward backtest 真数据 t-test
- /backtest 接入 phase.bytedance.city

**P1 — Perplexity 增强（用户反馈驱动）**:
- VPS LLM 升级 sonnet-4.6 for /api/ask/stream (cost ×3-5)
- citation click → /phenomenon/<id>
- History remote sync 默认 on
- /discoveries CLS metric 终极验证

**P1 — 科学纵深**:
- B4 ensemble 跑完 23 类 (3/7 DIFFER 提示 B3 fragile)
- NYC FDNY fires + WSB real fit
- OpenRouter Kimi key → 异构 ensemble

**P2 — 长期 staged**:
- Adversarial pre-registration paper（CVE FAIL 单独成稿）
- Backtest 商业化 path 判定（alpha vs narrative）
- Plausible 数据回看（1-2 周后）

详见 `SESSION-8-STARTER.md`。

---

## Session #7 Final HEAD

```
$ git log --oneline -16
23484f7 Merge pull request #79 from dada8899/session7/deploy-verify
98c8d5f docs(sessions): session #7 deploy verified + 8 post-deploy screenshots
3255586 Merge pull request #78 from dada8899/session7/fix-mobile-overflow
70ce543 fix(structural-web): mobile ≤480px nav overflow
817e77a Merge pull request #77 from dada8899/session7/ux-polish-v2
bcf10e4 feat(structural-web): UX 3rd round — mobile + Plausible + discoveries skeleton + glossary v2 (#2 W3-B)
2ddb55f Merge pull request #76 from dada8899/session7/learn-route
7ce45dd feat(structural-web): add /learn route for legacy home backup
1c971de Merge pull request #75 from dada8899/session7/fix-rate-limit
e439aeb fix(eng): tier_limit_decorator slowapi dynamic-limit signature
7264937 Merge pull request #74 from dada8899/session7/e2e-v2
9d2942f test(e2e): Playwright Perplexity flow + baseline screenshots (#2 W3-A)
7025b72 Merge pull request #73 from dada8899/session7/b4-ensemble-v2
53b0f32 feat(v4): B4 ensemble sample + taxonomy expand batch + CVE preregister real fit (#3 W2-C)
f9c1637 Merge pull request #72 from dada8899/session7/eng-polish-v2
42888c0 feat(eng): API auth tier + history remote endpoint + i18n EN expansion (#4 W2-D)
```

15 PR merged · 11 subagents in 3 waves · 6 hotfix iterations · ~9700 LOC insertions · 30 backend tests + 11 e2e all pass · ~$0.5 total LLM cost · ~2.5h main session + 4h total agent wall time
